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
# Carrega ID do bot do .env para nao hardcodar
SB_BOT_ID = os.getenv("SUPABASE_BOT_ID_UNDER25", "")
if SB_BOT_ID:
    sb.SUPABASE_BOT_ID = SB_BOT_ID
from datetime import datetime, timezone, timedelta

FUSO_BRASILIA = timezone(timedelta(hours=-3))
INTERVALO_LOOP = 60
HORA_HEARTBEAT = 8
ODD_MINIMA = 1.8
ODD_MAXIMA = 2.1
LIQUIDEZ_MINIMA = 150.0
STAKE_FIXO = 50.0
ENTRADA_MINUTOS_MAX = 5
SAIDA_MINUTOS = 10
SAIDA_LUCRO_PCT = 10.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bot_under25")
apostas_ativas = {}
heartbeat_enviado_em = None
primeira_vez_visto = {}  # market_id -> timestamp primeira vez visto

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

def obter_minuto_jogo(market_id):
    rpc = json.dumps({"jsonrpc":"2.0","method":"SportsAPING/v1.0/listMarketBook","params":{"marketIds":[market_id],"priceProjection":{"priceData":[]}},"id":1})
    livros = bf.chamar_api(rpc) or []
    if not livros:
        return 999
    livro = livros[0]
    elapsed = livro.get("timeElapsed")
    if elapsed is not None:
        return int(elapsed // 60)
    # fallback: calcula pelo horario de inicio do mercado
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
        f"\U0001f7e2 *BACK UNDER 2.5 — ENTRADA*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\U0001f3c6 *Liga:* {competition}\n"
        f"\u26bd *Jogo:* {jogo}\n"
        f"\u23f1 *Minuto:* {minuto}\'\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\U0001f4b0 *Odd:* {odd:.2f}\n"
        f"\U0001f4b5 *Stake:* \xa3{stake:.2f}\n"
        f"\U0001f194 `{market_id}`\n"
        f"\U0001f4e1 _Monitorando saida automaticamente_"
    )

def formatar_saida(jogo, odd_entrada, odd_saida, stake, pnl, motivo, market_id):
    emoji = "\u2705" if pnl > 0 else "\u274c"
    return (
        f"{emoji} *BACK UNDER 2.5 — SAIDA*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\u26bd *Jogo:* {jogo}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\U0001f4e5 *Odd entrada:* {odd_entrada:.2f}\n"
        f"\U0001f4e4 *Odd saida:* {odd_saida:.2f}\n"
        f"\U0001f4b5 *Stake:* \xa3{stake:.2f}\n"
        f"\U0001f4c9 *PnL estimado:* \xa3{pnl:+.2f}\n"
        f"\U0001f514 *Motivo:* {motivo}\n"
        f"\U0001f194 `{market_id}`"
    )


def enviar_alerta(texto):
    """Envia mensagem Telegram com monitoramento de saude."""
    try:
        enviar_mensagem(texto)
        saude.registrar("telegram", True)
    except Exception as e:
        log.warning(f"  Erro Telegram: {e}")
        saude.registrar("telegram", False, str(e))

def verificar_entradas(filtros):
    mercados = buscar_mercados_under25_ao_vivo()
    log.info(f"Mercados Under 2.5 ao vivo: {len(mercados)}")
    for m in mercados:
        market_id   = m.get("marketId", "")
        nome_jogo   = m.get("event", {}).get("name", market_id)
        competition = m.get("competition", {}).get("name", "")
        under_sel_id = m.get("_under_selection_id")
        if market_id in apostas_ativas:
            continue
        minuto = m.get("_minuto", 999)
        if minuto > filtros["ENTRADA_MINUTOS_MAX"]:
            log.info(f"  {nome_jogo} - min {minuto} > max {filtros['ENTRADA_MINUTOS_MAX']}, skip")
            continue
        odd, liq = obter_odd_e_liquidez_under(market_id, under_sel_id)
        if odd is None:
            log.info(f"  {nome_jogo} — runner Under 2.5 nao encontrado")
            try:
                sb.registrar_analise_supabase({"event_id": market_id, "nome_jogo": nome_jogo, "competition": competition}, aprovado=False, motivos=["Runner Under 2.5 nao encontrado"])
                saude.registrar("supabase", True)
            except Exception as e:
                log.warning(f"  Erro Supabase (analise): {e}")
                saude.registrar("supabase", False, str(e))
            continue
        log.info(f"  {nome_jogo} | min={minuto} | odd={odd:.2f} | liq=£{liq:.0f}")
        if not (filtros["ODD_MINIMA"] <= odd <= filtros["ODD_MAXIMA"]):
            log.info(f"    Odd fora do intervalo [{filtros['ODD_MINIMA']}, {filtros['ODD_MAXIMA']}]")
            try:
                sb.registrar_analise_supabase({"event_id": market_id, "nome_jogo": nome_jogo, "competition": competition, "minuto": minuto}, aprovado=False, motivos=[f"Odd {odd:.2f} fora do intervalo [{filtros['ODD_MINIMA']}, {filtros['ODD_MAXIMA']}]"])
                saude.registrar("supabase", True)
            except Exception as e:
                log.warning(f"  Erro Supabase (analise): {e}")
                saude.registrar("supabase", False, str(e))
            continue
        liq_minima = filtros["LIQUIDEZ_MINIMA"]
        if minuto <= 2:
            liq_minima = min(50.0, liq_minima)
        elif minuto <= 4:
            liq_minima = min(100.0, liq_minima)
        if liq < liq_minima:
            log.info(f"    Liquidez £{liq:.0f} < minimo £{liq_minima:.0f}")
            try:
                sb.registrar_analise_supabase({"event_id": market_id, "nome_jogo": nome_jogo, "competition": competition, "minuto": minuto}, aprovado=False, motivos=[f"Liquidez £{liq:.0f} < minimo £{liq_minima:.0f}"])
                saude.registrar("supabase", True)
            except Exception as e:
                log.warning(f"  Erro Supabase (analise): {e}")
                saude.registrar("supabase", False, str(e))
            enviar_alerta(f"⚠️ *Under 2.5 — Liquidez insuficiente*\n⚽ {nome_jogo}\n⏱ Min: {minuto}\n💰 Odd: {odd:.2f} (no intervalo)\n💵 Liquidez: £{liq:.0f} < £{liq_minima:.0f}")
            continue
        stake = filtros["STAKE_FIXO"]
        log.info(f"    ENTRADA — stake=£{stake} @ {odd:.2f}")
        apostas_ativas[market_id] = {"nome_jogo": nome_jogo, "competition": competition, "odd_entrada": odd, "stake": stake, "entrada_em": time.time(), "minuto_entrada": minuto, "under_sel_id": under_sel_id}
        try:
            sb.registrar_analise_supabase({"event_id": market_id, "nome_jogo": nome_jogo, "competition": competition, "minuto": minuto}, aprovado=True, motivos=[f"odd={odd:.2f}", f"min={minuto}"])
            saude.registrar("supabase", True)
        except Exception as e:
            log.warning(f"  Erro Supabase (analise aprovada): {e}")
            saude.registrar("supabase", False, str(e))
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
            enviar_alerta(formatar_saida(ap["nome_jogo"], odd_entrada, odd_atual, stake, pnl, motivo, market_id))
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
            enviar_alerta(f"\U0001f49a *Bot Under 2.5 — Online*\n\U0001f4c5 {agora.strftime('%d/%m/%Y %H:%M')} (Brasilia)\n\U0001f3af Apostas ativas: {len(apostas_ativas)}")

def main():
    log.info("=== BOT BACK UNDER 2.5 INICIANDO ===")
    if not bf.login():
        log.error("Falha no login Betfair. Abortando.")
        sys.exit(1)
    enviar_alerta("Bot Under 2.5 iniciado - modo simulacao")
    while True:
        try:
            bf.renovar_token_se_necessario()
            filtros = get_filtros()
            log.info(f"Filtros: odd={filtros['ODD_MINIMA']}-{filtros['ODD_MAXIMA']} liq={filtros['LIQUIDEZ_MINIMA']} stake={filtros['STAKE_FIXO']} entrada<{filtros['ENTRADA_MINUTOS_MAX']}min")
            verificar_heartbeat()
            verificar_entradas(filtros)
            verificar_saidas(filtros)
        except KeyboardInterrupt:
            log.info("Interrompido.")
            enviar_alerta("Bot Under 2.5 encerrado.")
            break
        except Exception as e:
            log.error(f"Erro no loop: {e}")
            enviar_alerta(f"Bot Under 2.5 - erro: {e}")
        time.sleep(INTERVALO_LOOP)

if __name__ == "__main__":
    main()
