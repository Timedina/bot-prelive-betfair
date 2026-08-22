import os
import sys, time, json, logging
import betfair_client as bf
try:
    import telegram_commands
    COMANDOS_DISPONIVEL = True
except ImportError:
    COMANDOS_DISPONIVEL = False
from telegram_client import enviar_mensagem
import supabase_integration as sb
import saude
sb.SUPABASE_BOT_ID = "4101d27c-2130-4517-b596-3969cf06f049"
print(f"[STARTUP] bot_id fixado: {sb.SUPABASE_BOT_ID}", flush=True)
from datetime import datetime, timezone, timedelta

FUSO_BRASILIA = timezone(timedelta(hours=-3))
HORA_DESCANSO_INICIO = 2  # 22/08: janela diaria de descanso forcado -- inicio (hora Brasilia)
HORA_DESCANSO_FIM    = 5  # 22/08: janela diaria de descanso forcado -- fim (hora Brasilia)
INTERVALO_LOOP = 60
HORA_HEARTBEAT = 8
ODD_MINIMA = 1.8
ODD_MAXIMA = 2.1
LIQUIDEZ_MINIMA = 150.0
STAKE_FIXO = 50.0
ENTRADA_MINUTOS_MAX = 5
SAIDA_MINUTOS = 10
SAIDA_LUCRO_PCT = 10.0
FOLGA_ANTES_MIN = 1
MARGEM_EXTRA_MIN = 2
HORAS_JANELA_BUSCA = 6
INTERVALO_LOOP_OCIOSO = 300
INTERVALO_ATUALIZACAO_JANELAS_SEG = 7200

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bot_under25")
apostas_ativas = {}
heartbeat_enviado_em = None
primeira_vez_visto = {}  # market_id -> timestamp primeira vez visto
checagens_feitas = {}    # market_id -> {"check1": bool, "check2": bool}

def get_filtros():
    f = sb.carregar_filtros()
    saude.registrar("supabase", f is not None, "carregar_filtros")
    return {
        "ODD_MINIMA":          f.get("ODD_MINIMA",          ODD_MINIMA),
        "ODD_MAXIMA":          f.get("ODD_MAXIMA",          ODD_MAXIMA),
        "LIQUIDEZ_MINIMA":     f.get("LIQUIDEZ_MINIMA",     LIQUIDEZ_MINIMA),
        "STAKE_FIXO":          f.get("STAKE_FIXO",          STAKE_FIXO),
        "ENTRADA_MINUTOS_MAX": int(f.get("ENTRADA_MINUTOS_MAX", ENTRADA_MINUTOS_MAX)),
        "SAIDA_MINUTOS":       f.get("SAIDA_MINUTOS",       SAIDA_MINUTOS),
        "SAIDA_LUCRO_PCT":     f.get("SAIDA_LUCRO_PCT",     SAIDA_LUCRO_PCT),
    }

def buscar_mercados_under25_ao_vivo():
    rpc = json.dumps({"jsonrpc":"2.0","method":"SportsAPING/v1.0/listMarketCatalogue","params":{"filter":{"eventTypeIds":["1"],"marketTypeCodes":["OVER_UNDER_25"],"inPlayOnly":True},"maxResults":"200","marketProjection":["COMPETITION","EVENT","RUNNER_DESCRIPTION","MARKET_START_TIME"]},"id":1})
    mercados = bf.chamar_api(rpc) or []
    saude.registrar("betfair", mercados is not None, "listMarketCatalogue Under 2.5")
    from datetime import datetime, timezone
    agora = datetime.now(timezone.utc)
    for m in mercados:
        runners = m.get("runners", [])
        under_id = None
        for r in runners:
            if "under" in r.get("runnerName", "").lower():
                under_id = r.get("selectionId")
                break
        m["_under_selection_id"] = under_id
        start_str = m.get("marketStartTime", "")
        try:
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            m["_minuto"] = max(0, int((agora - start).total_seconds() / 60))
        except Exception:
            m["_minuto"] = 999
    return mercados

def obter_odd_e_liquidez_under(market_id, selection_id=None):
    rpc = json.dumps({"jsonrpc":"2.0","method":"SportsAPING/v1.0/listMarketBook","params":{"marketIds":[market_id],"priceProjection":{"priceData":["EX_BEST_OFFERS"],"virtualise":"true"}},"id":1})
    livros = bf.chamar_api(rpc) or []
    saude.registrar("betfair", livros is not None, f"listMarketBook {market_id}")
    if not livros:
        return None, 0
    for runner in livros[0].get("runners", []):
        if selection_id and runner.get("selectionId") == selection_id:
            backs = runner.get("ex", {}).get("availableToBack", [])
            if backs:
                odd = backs[0].get("price", 0)
                liq = sum(b.get("size", 0) for b in backs[:3])
                return odd, liq
    return None, 0

def placar_ainda_0x0(event_id):
    rpc_cat = json.dumps({
        "jsonrpc": "2.0",
        "method": "SportsAPING/v1.0/listMarketCatalogue",
        "params": {
            "filter": {"eventIds": [str(event_id)], "marketTypeCodes": ["CORRECT_SCORE"]},
            "maxResults": "1",
            "marketProjection": ["RUNNER_DESCRIPTION"],
        },
        "id": 1
    })
    mercados_cs = bf.chamar_api(rpc_cat) or []
    if not mercados_cs:
        log.warning(f"  Placar: sem mercado Correct Score para event_id={event_id}, assumindo 0x0")
        return True
    mercado_cs = mercados_cs[0]
    sel_id_00 = None
    for r in mercado_cs.get("runners", []):
        if r.get("runnerName", "").replace(" ", "") == "0-0":
            sel_id_00 = r.get("selectionId")
            break
    if sel_id_00 is None:
        log.warning(f"  Placar: runner 0-0 nao encontrado no CS de event_id={event_id}, assumindo 0x0")
        return True
    rpc_book = json.dumps({
        "jsonrpc": "2.0",
        "method": "SportsAPING/v1.0/listMarketBook",
        "params": {"marketIds": [mercado_cs.get("marketId")], "priceProjection": {"priceData": ["EX_BEST_OFFERS"]}},
        "id": 1
    })
    livros_cs = bf.chamar_api(rpc_book) or []
    if not livros_cs:
        log.warning(f"  Placar: sem book do CS para event_id={event_id}, assumindo 0x0")
        return True
    for runner in livros_cs[0].get("runners", []):
        if runner.get("selectionId") == sel_id_00:
            backs = runner.get("ex", {}).get("availableToBack", [])
            return len(backs) > 0
    return True

def obter_minuto_jogo(market_id):
    rpc = json.dumps({"jsonrpc":"2.0","method":"SportsAPING/v1.0/listMarketBook","params":{"marketIds":[market_id],"priceProjection":{"priceData":[]}},"id":1})
    livros = bf.chamar_api(rpc) or []
    if not livros:
        return 999
    livro = livros[0]
    elapsed = livro.get("timeElapsed")
    if elapsed is not None:
        return int(elapsed // 60)
    start_str = livro.get("marketStartTime") or livro.get("openDate")
    if start_str:
        from datetime import datetime, timezone
        try:
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            minutos = (datetime.now(timezone.utc) - start).total_seconds() / 60
            return max(0, int(minutos))
        except Exception:
            pass
    return 999

def formatar_entrada(jogo, competition, odd, stake, minuto, market_id):
    return (
        f"🟢 *BACK UNDER 2.5 — ENTRADA*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 *Liga:* {competition}\n"
        f"⚽ *Jogo:* {jogo}\n"
        f"⏱ *Minuto:* {minuto}'\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Odd:* {odd:.2f}\n"
        f"💵 *Stake:* £{stake:.2f}\n"
        f"🆔 `{market_id}`\n"
        f"📡 _Monitorando saida automaticamente_"
    )

def formatar_saida(jogo, odd_entrada, odd_saida, stake, pnl, motivo, market_id):
    emoji = "✅" if pnl > 0 else "❌"
    return (
        f"{emoji} *BACK UNDER 2.5 — SAIDA*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚽ *Jogo:* {jogo}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 *Odd entrada:* {odd_entrada:.2f}\n"
        f"📤 *Odd saida:* {odd_saida:.2f}\n"
        f"💵 *Stake:* £{stake:.2f}\n"
        f"📉 *PnL estimado:* £{pnl:+.2f}\n"
        f"🔔 *Motivo:* {motivo}\n"
        f"🆔 `{market_id}`"
    )

def enviar_alerta(texto):
    try:
        enviar_mensagem(texto)
        saude.registrar("telegram", True)
    except Exception as e:
        log.warning(f"  Erro Telegram: {e}")
        saude.registrar("telegram", False, str(e))

def buscar_kickoffs_futuros(horas_a_frente=HORAS_JANELA_BUSCA):
    agora = datetime.now(timezone.utc)
    fim = agora + timedelta(hours=horas_a_frente)
    rpc = json.dumps({
        "jsonrpc": "2.0", "method": "SportsAPING/v1.0/listMarketCatalogue",
        "params": {
            "filter": {
                "eventTypeIds": ["1"],
                "marketTypeCodes": ["OVER_UNDER_25"],
                "marketStartTime": {"from": agora.isoformat(), "to": fim.isoformat()}
            },
            "maxResults": "200",
            "marketProjection": ["MARKET_START_TIME"]
        }, "id": 1
    })
    mercados = bf.chamar_api(rpc) or []
    saude.registrar("betfair", mercados is not None, "listMarketCatalogue kickoffs futuros")
    kickoffs = []
    for m in mercados:
        ts = m.get("marketStartTime")
        if ts:
            try:
                kickoffs.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except Exception:
                pass
    return kickoffs

def construir_janelas(kickoffs, entrada_max_min, saida_min):
    folga_depois = entrada_max_min + saida_min + MARGEM_EXTRA_MIN
    brutas = sorted([
        (k - timedelta(minutes=FOLGA_ANTES_MIN), k + timedelta(minutes=folga_depois))
        for k in kickoffs
    ])
    if not brutas:
        return []
    fundidas = [brutas[0]]
    for ini, fim in brutas[1:]:
        if ini <= fundidas[-1][1]:
            fundidas[-1] = (fundidas[-1][0], max(fundidas[-1][1], fim))
        else:
            fundidas.append((ini, fim))
    return fundidas

def dentro_de_janela(agora, janelas):
    return any(ini <= agora <= fim for ini, fim in janelas)

def verificar_entradas(filtros):
    mercados = buscar_mercados_under25_ao_vivo()
    log.info(f"Mercados Under 2.5 ao vivo: {len(mercados)}")
    sb.registrar_metrica_simples("mercados_under25_disponiveis", len(mercados))

    ids_atuais = {m.get("marketId", "") for m in mercados}
    for mid in list(checagens_feitas.keys()):
        if mid not in ids_atuais and mid not in apostas_ativas:
            del checagens_feitas[mid]

    for m in mercados:
        market_id   = m.get("marketId", "")
        nome_jogo   = m.get("event", {}).get("name", market_id)
        competition = m.get("competition", {}).get("name", "")
        event_id    = m.get("event", {}).get("id")
        under_sel_id = m.get("_under_selection_id")
        if market_id in apostas_ativas:
            continue
        minuto = m.get("_minuto", 999)
        if minuto > filtros["ENTRADA_MINUTOS_MAX"]:
            log.info(f"  {nome_jogo} - min {minuto} > max {filtros['ENTRADA_MINUTOS_MAX']}, skip")
            continue

        estado = checagens_feitas.setdefault(market_id, {"check1": False, "check2": False})
        if estado["check1"] and estado["check2"]:
            continue

        if not estado["check1"]:
            estado["check1"] = True
        elif minuto >= 5 and not estado["check2"]:
            estado["check2"] = True
            if not placar_ainda_0x0(event_id):
                log.info(f"  {nome_jogo} - placar nao esta mais 0x0, skip checagem 2")
                continue
        else:
            continue

        odd, liq = obter_odd_e_liquidez_under(market_id, under_sel_id)
        if odd is None:
            continue
        if not (filtros["ODD_MINIMA"] <= odd <= filtros["ODD_MAXIMA"]):
            sb.registrar_metrica_reprovacao("Odd fora do intervalo")
            continue
        liq_minima = filtros["LIQUIDEZ_MINIMA"]
        if liq < liq_minima:
            sb.registrar_metrica_reprovacao("Liquidez insuficiente")
            continue
        stake = filtros["STAKE_FIXO"]
        log.info(f"    ENTRADA — stake=£{stake} @ {odd:.2f}")
        apostas_ativas[market_id] = {"nome_jogo": nome_jogo, "competition": competition, "odd_entrada": odd, "stake": stake, "entrada_em": time.time(), "minuto_entrada": minuto, "under_sel_id": under_sel_id}
        try:
            sb.registrar_analise_supabase({"event_id": market_id, "nome_jogo": nome_jogo, "competition": competition, "minuto": minuto, "liquidez_disponivel": liq}, aprovado=True, motivos=[f"odd={odd:.2f}", f"min={minuto}"])
            saude.registrar("supabase", True)
        except Exception as e:
            log.warning(f"  Erro Supabase (analise aprovada): {e}")
            saude.registrar("supabase", False, str(e))
        try:
            sb.registrar_aposta_supabase(
                {"event_id": market_id, "nome_jogo": nome_jogo, "competition": competition, "market_id_cs": market_id},
                {"odd_lay": odd, "stake": stake, "simulado": True},
                tipo_aposta="BACK",
            )
            saude.registrar("supabase", True)
        except Exception as e:
            log.warning(f"  Erro Supabase (registrar aposta): {e}")
            saude.registrar("supabase", False, str(e))
        sb.registrar_metrica_aprovacao(datetime.now(timezone.utc).strftime("%H:00"))
        enviar_alerta(formatar_entrada(nome_jogo, competition, odd, stake, minuto, market_id))

def verificar_saidas(filtros):
    for market_id, ap in list(apostas_ativas.items()):
        odd_atual, _ = obter_odd_e_liquidez_under(market_id, ap.get("under_sel_id"))
        if not odd_atual:
            odd_atual = ap["odd_entrada"]
        minutos_passados = (time.time() - ap["entrada_em"]) / 60
        stake = ap["stake"]
        odd_entrada = ap["odd_entrada"]
        pnl = round(stake * (odd_entrada / odd_atual - 1), 2) if odd_atual > 0 else 0
        lucro_pct = (pnl / stake) * 100 if stake else 0
        motivo = None
        if lucro_pct >= filtros["SAIDA_LUCRO_PCT"]:
            motivo = f"Lucro alvo {filtros['SAIDA_LUCRO_PCT']}% atingido ({lucro_pct:.1f}%)"
        elif minutos_passados >= filtros["SAIDA_MINUTOS"]:
            motivo = f"Tempo limite ({filtros['SAIDA_MINUTOS']} min)"
        if motivo:
            log.info(f"  SAIDA {ap['nome_jogo']} — {motivo} | pnl=£{pnl:+.2f}")
            enviar_alerta(formatar_saida(ap['nome_jogo'], odd_entrada, odd_atual, stake, pnl, motivo, market_id))
            try:
                sb.atualizar_resultado_aposta_supabase(market_id, "VITORIA" if pnl > 0 else "PERDA", "--", pnl)
                saude.registrar("supabase", True)
            except Exception as e:
                log.warning(f"  Erro Supabase (resultado): {e}")
                saude.registrar("supabase", False, str(e))
            del apostas_ativas[market_id]

def verificar_heartbeat():
    global heartbeat_enviado_em
    agora = datetime.now(FUSO_BRASILIA)
    if agora.hour == HORA_HEARTBEAT:
        hoje = agora.date()
        if heartbeat_enviado_em != hoje:
            heartbeat_enviado_em = hoje
            enviar_alerta(f"🟢 *Bot Under 2.5 — Online*\n🟢 {agora.strftime('%d/%m/%Y %H:%M')} (Brasilia)\n🎯 Apostas ativas: {len(apostas_ativas)}")

def main():
    log.info("=== BOT BACK UNDER 2.5 INICIANDO (modo sob demanda) ===")
    enviar_alerta("Bot Under 2.5 iniciado - modo sob demanda (login so durante janelas de jogo)")
    janelas_do_dia = []
    ultima_atualizacao_janelas = None

    while True:
        ativo = False
        try:
            agora = datetime.now(timezone.utc)
            filtros = get_filtros()
            sb.gravar_metricas_periodico()

            precisa_atualizar_janelas = (
                ultima_atualizacao_janelas is None
                or (agora - ultima_atualizacao_janelas).total_seconds() > INTERVALO_ATUALIZACAO_JANELAS_SEG
            )

            if precisa_atualizar_janelas:
                if bf.SESSION_TOKEN is None:
                    if bf.login():
                        sb.registrar_sessao_betfair(datetime.now(timezone.utc))
                if bf.SESSION_TOKEN is not None:
                    kickoffs = buscar_kickoffs_futuros()
                    janelas_do_dia = construir_janelas(kickoffs, filtros["ENTRADA_MINUTOS_MAX"], filtros["SAIDA_MINUTOS"])
                    ultima_atualizacao_janelas = agora
                    log.info(f"Janelas atualizadas: {len(janelas_do_dia)} bloco(s) nas proximas {HORAS_JANELA_BUSCA}h")
                else:
                    log.error("Falha no login para atualizar janelas, tentando no proximo ciclo.")

            ativo = dentro_de_janela(agora, janelas_do_dia) or len(apostas_ativas) > 0

            hora_br_idle = datetime.now(FUSO_BRASILIA).hour
            em_janela_descanso = HORA_DESCANSO_INICIO <= hora_br_idle < HORA_DESCANSO_FIM
            if em_janela_descanso and len(apostas_ativas) == 0:
                ativo = False

            if ativo:
                if bf.SESSION_TOKEN is None:
                    if bf.login():
                        sb.registrar_sessao_betfair(datetime.now(timezone.utc))
                    else:
                        log.error("Falha no login em janela ativa, tentando no proximo ciclo.")
                        ativo = False
                if bf.SESSION_TOKEN is not None:
                    bf.renovar_token_se_necessario()
                    log.info(f"Filtros: odd={filtros['ODD_MINIMA']}-{filtros['ODD_MAXIMA']} liq={filtros['LIQUIDEZ_MINIMA']} stake={filtros['STAKE_FIXO']} entrada<{filtros['ENTRADA_MINUTOS_MAX']}min")
                    verificar_heartbeat()
                    verificar_entradas(filtros)
                    verificar_saidas(filtros)
            else:
                if bf.SESSION_TOKEN is not None:
                    bf.logout()
                    if em_janela_descanso:
                        log.info("Janela de descanso forcado (02h-05h) - sessao encerrada")
                    else:
                        log.info("Fora de janela ativa e sem apostas abertas - sessao encerrada")

        except KeyboardInterrupt:
            log.info("Interrompido.")
            enviar_alerta("Bot Under 2.5 encerrado.")
            if bf.SESSION_TOKEN is not None:
                bf.logout()
            break
        except Exception as e:
            log.error(f"Erro no loop: {e}")
            enviar_alerta(f"Bot Under 2.5 - erro: {e}")

        time.sleep(INTERVALO_LOOP if ativo else INTERVALO_LOOP_OCIOSO)

if __name__ == "__main__":
    main()
