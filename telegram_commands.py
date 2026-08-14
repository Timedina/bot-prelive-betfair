"""
telegram_commands.py
Listener de comandos do Telegram para controle do bot
Comandos: /resultado /jogos /status /aprovados /filtros
"""

import requests
import json
import os
import threading
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(override=True)

TOKEN  = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

_ultimo_update_id = 0
_lock = threading.Lock()
_inicializado = False


def get_updates():
    global _ultimo_update_id, _inicializado
    try:
        url  = f'https://api.telegram.org/bot{TOKEN}/getUpdates'

        # Na primeira chamada, descarta updates antigos
        if not _inicializado:
            resp = requests.get(url, params={'offset': -1, 'timeout': 1}, timeout=5)
            if resp.status_code == 200:
                results = resp.json().get('result', [])
                if results:
                    _ultimo_update_id = results[-1]['update_id']
            _inicializado = True
            return []

        resp = requests.get(url, params={'offset': _ultimo_update_id + 1, 'timeout': 5}, timeout=10)
        if resp.status_code == 200:
            return resp.json().get('result', [])
    except:
        pass
    return []


def responder(chat_id, texto):
    try:
        url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
        requests.post(url, json={
            'chat_id': chat_id,
            'text': texto,
            'parse_mode': 'Markdown'
        }, timeout=10)
    except Exception as e:
        print(f'[Telegram] Erro ao responder comando: {e}')


def processar_comandos(agendador, stats, resultado_jogos, carregar_aprovados_do_dia,
                        carregar_reprovados_do_dia, FUSO_BRASILIA,
                        ODD_10_MINIMA, ODD_10_MAXIMA, ODD_01_MINIMA, ODD_01_MAXIMA,
                        ODD_FAVORITO_MAX, ODD_OVER15_MINIMA, ODD_OVER15_MAXIMA,
                        ODD_BTTS_MINIMA, ODD_BTTS_MAXIMA,
                        LIQUIDEZ_MINIMA_CS_DISPONIVEL, LIQUIDEZ_MINIMA_CS_TOTAL):
    global _ultimo_update_id

    updates = get_updates()
    import logging
    logging.getLogger('bot').info(f'  [Telegram] updates recebidos: {len(updates)}')
    if not updates:
        return

    for update in updates:
        _ultimo_update_id = update['update_id']
        msg = update.get('message', {})
        chat_id = str(msg.get('chat', {}).get('id', ''))
        texto   = msg.get('text', '').strip().lower()

        # Seguranca: so responde ao chat autorizado
        import logging
        logging.getLogger('bot').info(f'  [Telegram] chat_id={chat_id} | CHAT_ID={CHAT_ID} | texto={texto}')
        if chat_id != str(CHAT_ID):
            logging.getLogger('bot').warning(f'  [Telegram] chat_id nao autorizado: {chat_id}')
            continue

        agora_br  = datetime.now(FUSO_BRASILIA)
        data_hoje = agora_br.strftime('%d/%m/%Y')

        # ── /resultado ────────────────────────────────────────────
        if texto == '/resultado':
            try:
                from datetime import timedelta as _timedelta
                hoje_str  = agora_br.strftime('%Y-%m-%d')
                ontem_str = (agora_br - _timedelta(days=1)).strftime('%Y-%m-%d')
                resultado_jogos.atualizar_resultados_do_dia(data_str=ontem_str, verbose=False)
                resultado_jogos.atualizar_resultados_do_dia(data_str=hoje_str, verbose=False)
                resumo_ontem = resultado_jogos.resumo_resultados(data_str=ontem_str)
                resumo_hoje  = resultado_jogos.resumo_resultados(data_str=hoje_str)
                responder(chat_id, resumo_ontem + chr(10) + chr(10) + resumo_hoje)
            except Exception as e:
                responder(chat_id, f'❌ Erro ao buscar resultado: {e}')

        # ── /jogos ────────────────────────────────────────────────
        elif texto == '/jogos':
            aguardando = [(eid, d) for eid, d in agendador.jogos.items()
                          if d['estado'] == 'aguardando']
            if not aguardando:
                responder(chat_id, '📋 *Fila vazia* — nenhum jogo aguardando análise.')
            else:
                linhas = [f'📋 *Fila de jogos — {data_hoje}*',
                          f'━━━━━━━━━━━━━━━━━━━━',
                          f'Total: {len(aguardando)} jogo(s)\n']
                for eid, d in sorted(aguardando, key=lambda x: x[1]['open_date']):
                    try:
                        inicio = datetime.fromisoformat(d['open_date'].replace('Z', '+00:00'))
                        horario = inicio.astimezone(FUSO_BRASILIA).strftime('%H:%M')
                        mins = int((inicio - datetime.now(timezone.utc)).total_seconds() / 60)
                        tempo = f'+{mins}min' if mins >= 0 else f'{abs(mins)}min atrás'
                    except:
                        horario = '--:--'
                        tempo   = '?'
                    linhas.append(f'⏰ {horario} ({tempo}) — {d["nome_jogo"]}')
                responder(chat_id, '\n'.join(linhas))

        # ── /status ───────────────────────────────────────────────
        elif texto == '/status':
            uptime   = datetime.now(FUSO_BRASILIA) - stats.inicio_sessao
            horas    = int(uptime.total_seconds() // 3600)
            minutos  = int((uptime.total_seconds() % 3600) // 60)
            aguardando = sum(1 for d in agendador.jogos.values() if d['estado'] == 'aguardando')
            reprovados = stats.jogos_analisados - stats.jogos_aprovados
            responder(chat_id,
                f'🤖 *Status do Bot*\n'
                f'━━━━━━━━━━━━━━━━━━━━\n'
                f'✅ Online há: *{horas}h {minutos}min*\n'
                f'📋 Fila: *{aguardando}* jogos aguardando\n'
                f'🔍 Analisados: *{stats.jogos_analisados}*\n'
                f'✅ Aprovados: *{stats.jogos_aprovados}*\n'
                f'⛔ Reprovados: *{reprovados}*\n'
                f'📡 Chamadas API: *{stats.chamadas_api}*\n'
                f'💹 Alertas movimento: *{stats.alertas_movimento}*\n'
                f'🕐 {agora_br.strftime("%d/%m/%Y %H:%M:%S")}'
            )

        # ── /aprovados ────────────────────────────────────────────
        elif texto == '/aprovados':
            aprovados = carregar_aprovados_do_dia()
            if not aprovados:
                responder(chat_id, f'📋 Nenhum jogo aprovado hoje ({data_hoje}).')
            else:
                linhas = [f'✅ *Aprovados hoje — {data_hoje}*',
                          f'━━━━━━━━━━━━━━━━━━━━']
                for info in sorted(aprovados.values(), key=lambda x: x.get('horario', '')):
                    result  = info.get('resultado_geral', '')
                    emoji   = '✅' if result == 'VITORIA' else ('❌' if result == 'PERDA' else '⏳')
                    placar  = f' | {info["placar_final"]}' if info.get('placar_final') else ''
                    pnl     = f' | PnL: {info["pnl_estimado"]}u' if info.get('pnl_estimado') else ''
                    linhas.append(
                        f'{emoji} {info["horario"]} {info["nome_jogo"]}\n'
                        f'   LAY 1-0@{info["odd_10"]} | 0-1@{info["odd_01"]}'
                        f'{placar}{pnl}'
                    )
                responder(chat_id, '\n'.join(linhas))

        # ── /filtros ──────────────────────────────────────────────
        elif texto == '/filtros':
            from bot_prelive import (APENAS_LAY_01, APENAS_LAY_10, RAZAO_ODD_MAXIMA,
                MINUTOS_APOS_INICIO, MINUTOS_ANTES_INICIO,
                ODD_FAVORITO_MAX_COPA, ODD_OVER15_MAXIMA_COPA, ODD_BTTS_MAXIMA_COPA)
            from apostas import LIABILITY_FIXA
            modo = 'Apenas LAY 0-1' if APENAS_LAY_01 else ('Apenas LAY 1-0' if APENAS_LAY_10 else 'LAY 0-1 e 1-0')
            responder(chat_id,
                f'\u2699\ufe0f *Filtros Ativos*\n'
                f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
                f'\U0001f3af *Modo:* {modo}\n'
                f'\U0001f4b0 *Liability fixa:* \xa3{LIABILITY_FIXA:.0f}\n'
                f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
                f'\U0001f4ca *Correct Score LAY 0-1*\n'
                f'  Faixa: {ODD_01_MINIMA} - {ODD_01_MAXIMA}\n'
                f'  Razao max: {RAZAO_ODD_MAXIMA}\n'
                f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
                f'\u2b50 *Favorito*\n'
                f'  Padrao: {ODD_FAVORITO_MAX} | \U0001f3c6 Copa: {ODD_FAVORITO_MAX_COPA}\n'
                f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
                f'\U0001f4c8 *Over 1.5*\n'
                f'  Padrao: {ODD_OVER15_MINIMA}-{ODD_OVER15_MAXIMA} | \U0001f3c6 Copa: ate {ODD_OVER15_MAXIMA_COPA}\n'
                f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
                f'\U0001f91d *BTTS*\n'
                f'  Padrao: {ODD_BTTS_MINIMA}-{ODD_BTTS_MAXIMA} | \U0001f3c6 Copa: ate {ODD_BTTS_MAXIMA_COPA}\n'
                f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
                f'\U0001f4a7 *Liquidez CS min:* \xa3{LIQUIDEZ_MINIMA_CS_DISPONIVEL}\n'
                f'\u23f1 *Janela:* {MINUTOS_ANTES_INICIO}min antes ate {MINUTOS_APOS_INICIO}min apos'
            )

        elif texto == '/reprovados':
            reprovados = carregar_reprovados_do_dia()
            if not reprovados:
                responder(chat_id, f'📋 Nenhuma reprovação registrada hoje.')
            else:
                contagem = {}
                for dados in reprovados.values():
                    for tent in dados['tentativas']:
                        for motivo in tent['motivos']:
                            chave = motivo.split(':')[0].strip()
                            contagem[chave] = contagem.get(chave, 0) + 1
                top = sorted(contagem.items(), key=lambda x: x[1], reverse=True)[:8]
                linhas = [f'⛔ *Reprovações — {data_hoje}*',
                          f'Jogos únicos: {len(reprovados)}\n',
                          '*Top motivos:*']
                for motivo, n in top:
                    linhas.append(f'  • {motivo}: *{n}x*')
                responder(chat_id, '\n'.join(linhas))

        # ── /historico ───────────────────────────────────────────
        elif texto == '/historico':
            try:
                import os, json as _json
                fuso = FUSO_BRASILIA
                pasta = 'dados_bot'
                arquivos = sorted([f for f in os.listdir(pasta) if f.startswith('aprovados_')])
                if not arquivos:
                    responder(chat_id, 'Nenhum historico encontrado.')
                else:
                    linhas_msg = ['📋 *Histórico de Jogos*', '━━━━━━━━━━━━━━━━━━━━']
                    total_v = total_d = total_p = 0
                    pnl_geral = 0.0
                    for arq in arquivos:
                        data_str = arq.replace('aprovados_', '').replace('.json', '')
                        with open(os.path.join(pasta, arq)) as ff:
                            jogos = _json.load(ff)
                        if not jogos: continue
                        v = sum(1 for j in jogos.values() if j.get('resultado_geral') == 'VITORIA')
                        d = sum(1 for j in jogos.values() if j.get('resultado_geral') == 'PERDA')
                        p = sum(1 for j in jogos.values() if not j.get('resultado_geral'))
                        pnl = sum(j.get('pnl_estimado', 0) or 0 for j in jogos.values())
                        total_v += v; total_d += d; total_p += p; pnl_geral += pnl
                        sinal = '+' if pnl >= 0 else ''
                        linhas_msg.append(f'📅 *{data_str}* | {len(jogos)} jogos | {v}V/{d}D/{p}P | {sinal}R${abs(round(pnl,2))}')
                    linhas_msg.append('━━━━━━━━━━━━━━━━━━━━')
                    sinal_g = '+' if pnl_geral >= 0 else ''
                    linhas_msg.append(f'📊 *Total:* {total_v}V/{total_d}D/{total_p}P | Lucro: *{sinal_g}R${abs(round(pnl_geral,2))}*')
                    responder(chat_id, '\n'.join(linhas_msg))
            except Exception as e:
                responder(chat_id, 'Erro: ' + str(e))

        # ── /simulacoes ──────────────────────────────────────────────
        elif texto == '/simulacoes':
            try:
                import os, json as _json
                pasta = 'dados_bot'
                arquivos = sorted([f for f in os.listdir(pasta) if f.startswith('aprovados_')])
                linhas_msg = ['🎰 *Simulações de Apostas*', '━━━━━━━━━━━━━━━━━━━━']
                total_sim = 0
                pnl_sim = 0.0
                for arq in arquivos:
                    data_str = arq.replace('aprovados_', '').replace('.json', '')
                    with open(os.path.join(pasta, arq)) as ff:
                        jogos = _json.load(ff)
                    for info in jogos.values():
                        if not info.get('placar_lay'): continue
                        total_sim += 1
                        pnl = info.get('pnl_estimado', 0) or 0
                        pnl_sim += pnl
                        result = info.get('resultado_geral', 'Pendente')
                        emoji = '✅' if result == 'VITORIA' else ('❌' if result == 'PERDA' else '⏳')
                        placar = info.get('placar_final', '?')
                        lay = info.get('placar_lay', '')
                        odd = info.get('odd_lay', 0)
                        sinal = '+' if pnl >= 0 else ''
                        linhas_msg.append(f'{emoji} {data_str} | {info["nome_jogo"]}')
                        linhas_msg.append(f'   LAY {lay}@{odd} | Placar: {placar} | {sinal}R${abs(round(pnl,2))}')
                if total_sim == 0:
                    responder(chat_id, 'Nenhuma simulacao encontrada ainda.')
                else:
                    linhas_msg.append('━━━━━━━━━━━━━━━━━━━━')
                    sinal_t = '+' if pnl_sim >= 0 else ''
                    linhas_msg.append(f'💰 *Lucro Total Simulado: {sinal_t}R${abs(round(pnl_sim,2))}* ({total_sim} jogos)')
                    responder(chat_id, '\n'.join(linhas_msg))
            except Exception as e:
                responder(chat_id, 'Erro: ' + str(e))

        # ── /odds ────────────────────────────────────────────────
        elif texto.startswith('/odds'):
            partes = texto.replace('/odds', '').strip()
            if not partes:
                responder(chat_id, '/odds Rangers Torino\n_Separe os times por espaco_')
            else:
                times = [t.strip() for t in partes.split() if t.strip()]
                responder(chat_id, 'Buscando odds para: ' + ', '.join(times) + '...')
                try:
                    resultado = buscar_odds_por_times(times)
                    responder(chat_id, resultado)
                except Exception as e:
                    responder(chat_id, 'Erro: ' + str(e))

        # ── /semana ──────────────────────────────────────────────
        elif texto == '/semana':
            try:
                import os, json as _json
                fuso2 = FUSO_BRASILIA
                hoje = datetime.now(fuso2)
                inicio_semana = hoje - timedelta(days=hoje.weekday())
                pasta = 'dados_bot'
                arquivos = sorted([f for f in os.listdir(pasta) if f.startswith('aprovados_')])
                total_v = total_d = total_p = 0
                pnl = 0.0
                linhas_msg = ['📅 *Resumo da Semana*', '━━━━━━━━━━━━━━━━━━━━']
                for arq in arquivos:
                    data_str = arq.replace('aprovados_', '').replace('.json', '')
                    try:
                        dt = datetime.strptime(data_str, '%Y-%m-%d').replace(tzinfo=fuso2)
                        if dt < inicio_semana: continue
                    except: continue
                    with open(os.path.join(pasta, arq)) as ff:
                        jogos = _json.load(ff)
                    v = sum(1 for j in jogos.values() if j.get('resultado_geral') == 'VITORIA')
                    d = sum(1 for j in jogos.values() if j.get('resultado_geral') == 'PERDA')
                    p = sum(1 for j in jogos.values() if not j.get('resultado_geral'))
                    pnl_dia = sum(j.get('pnl_estimado', 0) or 0 for j in jogos.values())
                    total_v += v; total_d += d; total_p += p; pnl += pnl_dia
                    sinal = '+' if pnl_dia >= 0 else ''
                    linhas_msg.append(f'📅 *{data_str}* | {v}V/{d}D/{p}P | {sinal}R${abs(round(pnl_dia,2))}')
                taxa = round(total_v / (total_v + total_d) * 100, 1) if (total_v + total_d) > 0 else 0
                sinal_t = '+' if pnl >= 0 else ''
                linhas_msg.append('━━━━━━━━━━━━━━━━━━━━')
                linhas_msg.append(f'✅ *{total_v}V* / ❌ *{total_d}D* / ⏳ *{total_p}P*')
                linhas_msg.append(f'🎯 Taxa de acerto: *{taxa}%*')
                linhas_msg.append(f'💰 Lucro: *{sinal_t}R${abs(round(pnl,2))}*')
                responder(chat_id, '\n'.join(linhas_msg))
            except Exception as e:
                responder(chat_id, 'Erro /semana: ' + str(e))

        # ── /mes ─────────────────────────────────────────────────
        elif texto == '/mes':
            try:
                import os, json as _json
                fuso2 = FUSO_BRASILIA
                hoje = datetime.now(fuso2)
                mes_atual = hoje.strftime('%Y-%m')
                pasta = 'dados_bot'
                arquivos = sorted([f for f in os.listdir(pasta) if f.startswith('aprovados_')])
                total_v = total_d = total_p = 0
                pnl = 0.0
                linhas_msg = [f'📆 *Resumo de {hoje.strftime("%B/%Y")}*', '━━━━━━━━━━━━━━━━━━━━']
                for arq in arquivos:
                    data_str = arq.replace('aprovados_', '').replace('.json', '')
                    if not data_str.startswith(mes_atual): continue
                    with open(os.path.join(pasta, arq)) as ff:
                        jogos = _json.load(ff)
                    v = sum(1 for j in jogos.values() if j.get('resultado_geral') == 'VITORIA')
                    d = sum(1 for j in jogos.values() if j.get('resultado_geral') == 'PERDA')
                    p = sum(1 for j in jogos.values() if not j.get('resultado_geral'))
                    pnl_dia = sum(j.get('pnl_estimado', 0) or 0 for j in jogos.values())
                    total_v += v; total_d += d; total_p += p; pnl += pnl_dia
                    sinal = '+' if pnl_dia >= 0 else ''
                    linhas_msg.append(f'📅 *{data_str}* | {v}V/{d}D/{p}P | {sinal}R${abs(round(pnl_dia,2))}')
                taxa = round(total_v / (total_v + total_d) * 100, 1) if (total_v + total_d) > 0 else 0
                sinal_t = '+' if pnl >= 0 else ''
                linhas_msg.append('━━━━━━━━━━━━━━━━━━━━')
                linhas_msg.append(f'✅ *{total_v}V* / ❌ *{total_d}D* / ⏳ *{total_p}P*')
                linhas_msg.append(f'🎯 Taxa de acerto: *{taxa}%*')
                linhas_msg.append(f'💰 Lucro: *{sinal_t}R${abs(round(pnl,2))}*')
                responder(chat_id, '\n'.join(linhas_msg))
            except Exception as e:
                responder(chat_id, 'Erro /mes: ' + str(e))

        # ── /jogo ─────────────────────────────────────────────────
        elif texto.startswith('/jogo'):
            partes = texto.replace('/jogo', '').strip()
            if not partes:
                responder(chat_id, '/jogo Rangers Motherwell')
            else:
                responder(chat_id, 'Analisando: ' + partes + '...')
                try:
                    resultado = buscar_analise_jogo(partes)
                    responder(chat_id, resultado)
                except Exception as e:
                    responder(chat_id, 'Erro /jogo: ' + str(e))

        # ── /setfiltro ────────────────────────────────────────────
        elif texto.startswith('/setfiltro'):
            partes = texto.replace('/setfiltro', '').strip().split()
            if len(partes) != 2:
                responder(chat_id, 'Uso: /setfiltro favorito 2.2')
            else:
                nome_f, valor_f = partes[0], partes[1]
                mapa = {
                    'favorito': 'ODD_FAVORITO_MAX', 'oddmax': 'ODD_10_MAXIMA',
                    'oddmin': 'ODD_10_MINIMA', 'over15min': 'ODD_OVER15_MINIMA',
                    'over15max': 'ODD_OVER15_MAXIMA', 'bttsmin': 'ODD_BTTS_MINIMA',
                    'bttsmax': 'ODD_BTTS_MAXIMA', 'liquidez': 'LIQUIDEZ_MINIMA_CS_DISPONIVEL',
                }
                if nome_f not in mapa:
                    responder(chat_id, 'Filtro desconhecido: ' + nome_f)
                else:
                    try:
                        _filtros_dinamicos[mapa[nome_f]] = float(valor_f)
                        responder(chat_id, f'✅ *{nome_f}* = *{valor_f}* (válido até reiniciar)')
                    except:
                        responder(chat_id, 'Valor inválido: ' + valor_f)

        # ── /hoje ─────────────────────────────────────────────────
        elif texto == '/hoje':
            try:
                import json
                import betfair_client as bf

                agora_br    = datetime.now(FUSO_BRASILIA)
                inicio      = agora_br.replace(hour=0, minute=0, second=0, microsecond=0)
                fim         = agora_br.replace(hour=23, minute=59, second=59)
                inicio_utc  = inicio.astimezone(timezone.utc)
                fim_utc     = fim.astimezone(timezone.utc)
                data_hoje2  = agora_br.strftime('%d/%m/%Y')

                responder(chat_id, f'🔍 Buscando jogos para hoje {data_hoje2} e filtrando Over 1.5...')

                rpc_cs = json.dumps({
                    'jsonrpc': '2.0',
                    'method': 'SportsAPING/v1.0/listMarketCatalogue',
                    'params': {
                        'filter': {
                            'eventTypeIds': ['1'],
                            'marketTypeCodes': ['CORRECT_SCORE'],
                            'marketStartTime': {
                                'from': inicio_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'to':   fim_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                            }
                        },
                        'maxResults': '1000',
                        'marketProjection': ['COMPETITION', 'EVENT', 'MARKET_START_TIME'],
                    },
                    'id': 1
                })
                mercados_cs = bf.chamar_api(rpc_cs) or []

                vistos = set()
                eventos_map = {}
                for m in mercados_cs:
                    evento   = m.get('event', {})
                    event_id = evento.get('id')
                    if not event_id or event_id in vistos:
                        continue
                    vistos.add(event_id)
                    open_date = evento.get('openDate', '')
                    try:
                        dt_utc  = datetime.fromisoformat(open_date.replace('Z', '+00:00'))
                        horario = dt_utc.astimezone(FUSO_BRASILIA).strftime('%H:%M')
                    except:
                        horario = '--:--'
                    comp = m.get('competition', {}).get('name', '')
                    eventos_map[event_id] = {
                        'horario':  horario,
                        'nome':     evento.get('name', ''),
                        'comp':     comp,
                        'odd_over': None,
                    }

                rpc_over = json.dumps({
                    'jsonrpc': '2.0',
                    'method': 'SportsAPING/v1.0/listMarketCatalogue',
                    'params': {
                        'filter': {
                            'eventTypeIds': ['1'],
                            'marketTypeCodes': ['OVER_UNDER_15'],
                            'marketStartTime': {
                                'from': inicio_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'to':   fim_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                            }
                        },
                        'maxResults': '1000',
                        'marketProjection': ['EVENT', 'MARKET_START_TIME', 'RUNNER_DESCRIPTION'],
                    },
                    'id': 2
                })
                mercados_over = bf.chamar_api(rpc_over) or []

                over_ids = {}
                for m in mercados_over:
                    event_id = m.get('event', {}).get('id')
                    if event_id in eventos_map:
                        over_ids[m['marketId']] = event_id

                market_ids = list(over_ids.keys())
                for i in range(0, len(market_ids), 50):
                    lote  = market_ids[i:i+50]
                    books = bf.listar_odds(lote, ['EX_BEST_OFFERS']) or []
                    for book in books:
                        mid      = book['marketId']
                        event_id = over_ids.get(mid)
                        if not event_id:
                            continue
                        mercado_over = next((m for m in mercados_over if m.get('event', {}).get('id') == event_id and m['marketId'] == mid), None)
                        runners_map  = {}
                        if mercado_over:
                            runners_map = {r['selectionId']: r['runnerName'] for r in mercado_over.get('runners', [])}
                        for runner in book.get('runners', []):
                            nome_runner = runners_map.get(runner.get('selectionId'), '')
                            if 'Over' in nome_runner and '1.5' in nome_runner:
                                back = bf.get_back(runner)
                                if back:
                                    eventos_map[event_id]['odd_over'] = back
                                break

                aprovados = []
                sem_odd   = []
                for event_id, info in eventos_map.items():
                    odd = info['odd_over']
                    if odd is None:
                        sem_odd.append(info)
                    elif 1.10 <= odd <= 1.35:
                        aprovados.append(info)

                aprovados.sort(key=lambda x: x['horario'])

                if not aprovados:
                    responder(chat_id,
                        f'📋 *Jogos hoje — {data_hoje2}*\n'
                        f'━━━━━━━━━━━━━━━━━━━━\n'
                        f'Nenhum jogo com Over 1.5 na faixa 1.10–1.35\n'
                        f'_(odds ainda não disponíveis para {len(sem_odd)} jogos)_'
                    )
                else:
                    linhas = [
                        f'📅 *Possíveis entradas hoje — {data_hoje2}*',
                        f'_(Over 1.5 entre 1.10–1.35)_',
                        f'━━━━━━━━━━━━━━━━━━━━',
                        f'✅ *{len(aprovados)}* jogos pré-filtrados',
                        f'⏳ {len(sem_odd)} sem odd disponível ainda\n',
                    ]
                    hora_atual = None
                    for info in aprovados:
                        if info['horario'][:2] != hora_atual:
                            hora_atual = info['horario'][:2]
                            linhas.append(f'🕐 *{hora_atual}h*')
                        linhas.append(
                            f'  {info["horario"]} — {info["nome"]} @ O1.5: *{info["odd_over"]}* _[{info["comp"]}]_'
                        )

                    mensagem = '\n'.join(linhas)
                    if len(mensagem) > 4000:
                        partes  = []
                        bloco   = []
                        tamanho = 0
                        for linha in linhas:
                            if tamanho + len(linha) > 3800:
                                partes.append('\n'.join(bloco))
                                bloco   = [linha]
                                tamanho = len(linha)
                            else:
                                bloco.append(linha)
                                tamanho += len(linha)
                        if bloco:
                            partes.append('\n'.join(bloco))
                        for parte in partes:
                            responder(chat_id, parte)
                    else:
                        responder(chat_id, mensagem)

            except Exception as e:
                responder(chat_id, f'❌ Erro ao buscar jogos de hoje: {e}')

        # ── /amanha ───────────────────────────────────────────────
        elif texto == '/amanha':
            try:
                import json
                import betfair_client as bf

                agora_br    = datetime.now(FUSO_BRASILIA)
                inicio      = (agora_br + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                fim         = inicio.replace(hour=23, minute=59, second=59)
                inicio_utc  = inicio.astimezone(timezone.utc)
                fim_utc     = fim.astimezone(timezone.utc)
                data_amanha = inicio.strftime('%d/%m/%Y')

                responder(chat_id, f'🔍 Buscando jogos para {data_amanha} e filtrando Over 1.5...')

                # 1) Busca todos os jogos com CS amanha
                rpc_cs = json.dumps({
                    'jsonrpc': '2.0',
                    'method': 'SportsAPING/v1.0/listMarketCatalogue',
                    'params': {
                        'filter': {
                            'eventTypeIds': ['1'],
                            'marketTypeCodes': ['CORRECT_SCORE'],
                            'marketStartTime': {
                                'from': inicio_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'to':   fim_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                            }
                        },
                        'maxResults': '1000',
                        'marketProjection': ['COMPETITION', 'EVENT', 'MARKET_START_TIME'],
                    },
                    'id': 1
                })
                mercados_cs = bf.chamar_api(rpc_cs) or []

                # Monta mapa event_id -> info
                vistos = set()
                eventos_map = {}
                for m in mercados_cs:
                    evento   = m.get('event', {})
                    event_id = evento.get('id')
                    if not event_id or event_id in vistos:
                        continue
                    vistos.add(event_id)
                    open_date = evento.get('openDate', '')
                    try:
                        dt_utc  = datetime.fromisoformat(open_date.replace('Z', '+00:00'))
                        horario = dt_utc.astimezone(FUSO_BRASILIA).strftime('%H:%M')
                    except:
                        horario = '--:--'
                    comp = m.get('competition', {}).get('name', '')
                    eventos_map[event_id] = {
                        'horario':  horario,
                        'nome':     evento.get('name', ''),
                        'comp':     comp,
                        'odd_over': None,
                    }

                # 2) Busca mercados Over 1.5 para os mesmos eventos
                rpc_over = json.dumps({
                    'jsonrpc': '2.0',
                    'method': 'SportsAPING/v1.0/listMarketCatalogue',
                    'params': {
                        'filter': {
                            'eventTypeIds': ['1'],
                            'marketTypeCodes': ['OVER_UNDER_15'],
                            'marketStartTime': {
                                'from': inicio_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'to':   fim_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                            }
                        },
                        'maxResults': '1000',
                        'marketProjection': ['EVENT', 'MARKET_START_TIME', 'RUNNER_DESCRIPTION'],
                    },
                    'id': 2
                })
                mercados_over = bf.chamar_api(rpc_over) or []

                # Filtra so eventos que ja temos no CS
                over_ids = {}
                for m in mercados_over:
                    event_id = m.get('event', {}).get('id')
                    if event_id in eventos_map:
                        over_ids[m['marketId']] = event_id

                # 3) Busca odds Over 1.5 em lotes de 50
                market_ids = list(over_ids.keys())
                for i in range(0, len(market_ids), 50):
                    lote  = market_ids[i:i+50]
                    books = bf.listar_odds(lote, ['EX_BEST_OFFERS']) or []
                    for book in books:
                        mid      = book['marketId']
                        event_id = over_ids.get(mid)
                        if not event_id:
                            continue
                        # Busca runner Over 1.5 Goals pelo nome no catalogo
                    mercado_over = next((m for m in mercados_over if over_ids.get(book['marketId']) == m.get('event', {}).get('id')), None)
                    runners_map  = {}
                    if mercado_over:
                        runners_map = {r['selectionId']: r['runnerName'] for r in mercado_over.get('runners', [])}
                    for runner in book.get('runners', []):
                        nome_runner = runners_map.get(runner.get('selectionId'), '')
                        if 'Over' in nome_runner and '1.5' in nome_runner:
                            back = bf.get_back(runner)
                            if back:
                                eventos_map[event_id]['odd_over'] = back
                            break

                # 4) Filtra jogos com Over 1.5 na faixa 1.10-1.35
                aprovados = []
                sem_odd   = []
                for event_id, info in eventos_map.items():
                    odd = info['odd_over']
                    if odd is None:
                        sem_odd.append(info)
                    elif 1.10 <= odd <= 1.35:
                        info['odd_over'] = odd
                        aprovados.append(info)

                aprovados.sort(key=lambda x: x['horario'])

                if not aprovados:
                    responder(chat_id,
                        f'📋 *Jogos amanhã — {data_amanha}*\n'
                        f'━━━━━━━━━━━━━━━━━━━━\n'
                        f'Nenhum jogo com Over 1.5 na faixa 1.10–1.35\n'
                        f'_(odds ainda não disponíveis para {len(sem_odd)} jogos)_'
                    )
                else:
                    linhas = [
                        f'📅 *Possíveis entradas — {data_amanha}*',
                        f'_(Over 1.5 entre 1.10–1.35)_',
                        f'━━━━━━━━━━━━━━━━━━━━',
                        f'✅ *{len(aprovados)}* jogos pré-filtrados',
                        f'⏳ {len(sem_odd)} sem odd disponível ainda\n',
                    ]
                    hora_atual = None
                    for info in aprovados:
                        if info['horario'][:2] != hora_atual:
                            hora_atual = info['horario'][:2]
                            linhas.append(f'🕐 *{hora_atual}h*')
                        linhas.append(
                            f'  {info["horario"]} — {info["nome"]} @ O1.5: *{info["odd_over"]}* _[{info["comp"]}]_'
                        )

                    mensagem = '\n'.join(linhas)
                    if len(mensagem) > 4000:
                        partes  = []
                        bloco   = []
                        tamanho = 0
                        for linha in linhas:
                            if tamanho + len(linha) > 3800:
                                partes.append('\n'.join(bloco))
                                bloco   = [linha]
                                tamanho = len(linha)
                            else:
                                bloco.append(linha)
                                tamanho += len(linha)
                        if bloco:
                            partes.append('\n'.join(bloco))
                        for parte in partes:
                            responder(chat_id, parte)
                    else:
                        responder(chat_id, mensagem)

            except Exception as e:
                responder(chat_id, f'❌ Erro ao buscar jogos de amanhã: {e}')

        # ── /backtest ─────────────────────────────────────────────
        elif texto == '/backtest':
            try:
                import glob as _glob
                pasta = 'dados_bot'
                arquivos = sorted(_glob.glob(os.path.join(pasta, 'historico_*.json')))
                if not arquivos:
                    responder(chat_id, '📊 Nenhum dado de histórico ainda.\n_O bot precisa rodar por alguns dias para acumular dados._')
                else:
                    total = aprovados_bt = reprovados_bt = 0
                    linhas = ['📊 *Histórico de Análises (Backtest)*', '━━━━━━━━━━━━━━━━━━━━']
                    for arq in arquivos:
                        data_str = os.path.basename(arq).replace('historico_','').replace('.json','')
                        with open(arq) as ff:
                            d = json.load(ff)
                        ap  = sum(1 for j in d if j.get('aprovado'))
                        rep = sum(1 for j in d if not j.get('aprovado'))
                        total += len(d)
                        aprovados_bt  += ap
                        reprovados_bt += rep
                        contagem = {}
                        for j in d:
                            if not j.get('aprovado'):
                                for m in j.get('motivos', []):
                                    chave = m.split(':')[0].strip()
                                    contagem[chave] = contagem.get(chave, 0) + 1
                        top = sorted(contagem.items(), key=lambda x: x[1], reverse=True)[:3]
                        top_str = ' | '.join(f'{k}: {v}x' for k,v in top) or 'sem dados'
                        linhas.append(f'📅 *{data_str}* | {len(d)} jogos | {ap} aprov | {rep} reprov')
                        linhas.append(f'   _{top_str}_')
                    taxa_aprov = round(aprovados_bt / total * 100, 1) if total else 0
                    linhas += [
                        '━━━━━━━━━━━━━━━━━━━━',
                        f'📈 Total analisados: *{total}*',
                        f'✅ Aprovados: *{aprovados_bt}* ({taxa_aprov}%)',
                        f'⛔ Reprovados: *{reprovados_bt}*',
                        f'_Use esses dados para calibrar os filtros._',
                    ]
                    responder(chat_id, '\n'.join(linhas))
            except Exception as e:
                responder(chat_id, f'❌ Erro /backtest: {e}')

        # ── /restart ─────────────────────────────────────────────
        elif texto == '/saude':
            try:
                import json as _json, os as _os
                from saude import ARQUIVO_SAUDE
                if not _os.path.exists(ARQUIVO_SAUDE):
                    responder(chat_id, 'Sem dados de saude ainda.')
                else:
                    with open(ARQUIVO_SAUDE) as f:
                        dados = _json.load(f)
                    linhas = []
                    for nome, info in dados.items():
                        fail_streak = info.get('fail_streak', 0)
                        emoji = '\U0001f534' if fail_streak >= 3 else ('\U0001f7e1' if fail_streak > 0 else '\U0001f7e2')
                        ultimo_ok = info.get('ultimo_ok')
                        minutos = '?'
                        if ultimo_ok:
                            delta = datetime.now(timezone.utc) - datetime.fromisoformat(ultimo_ok)
                            minutos = int(delta.total_seconds() // 60)
                        linhas.append(f'{emoji} {nome}: OK ha {minutos}min (falhas seguidas: {fail_streak})')
                    responder(chat_id, '\n'.join(linhas) if linhas else 'Sem dados ainda')
            except Exception as e:
                responder(chat_id, f'Erro /saude: {e}')

        elif texto == '/sessao':
            try:
                import supabase_integration as sb
                iniciada_em_str = sb.obter_sessao_betfair()
                if not iniciada_em_str:
                    responder(chat_id, 'Sem sessao registrada ainda.')
                else:
                    iniciada_em = datetime.fromisoformat(iniciada_em_str.replace('Z', '+00:00'))
                    agora = datetime.now(timezone.utc)
                    decorrido_seg = (agora - iniciada_em).total_seconds()
                    limite_seg = 23 * 3600
                    restante_seg = limite_seg - decorrido_seg
                    h_dec = int(decorrido_seg // 3600)
                    m_dec = int((decorrido_seg % 3600) // 60)
                    if restante_seg > 0:
                        h_rest = int(restante_seg // 3600)
                        m_rest = int((restante_seg % 3600) // 60)
                        if restante_seg > 2 * 3600:
                            emoji = '\U0001f7e2'
                        else:
                            emoji = '\U0001f7e1'
                        responder(chat_id, f'{emoji} Sessao Betfair ha {h_dec}h{m_dec:02d}min\nFaltam ~{h_rest}h{m_rest:02d}min para o limite de 23h')
                    else:
                        responder(chat_id, f'\U0001f534 Sessao Betfair ha {h_dec}h{m_dec:02d}min - pode ja ter passado do limite de 23h')
            except Exception as e:
                responder(chat_id, f'Erro /sessao: {e}')

        elif texto == '/restart':
            responder(chat_id, '🔄 Reiniciando bot LAY (bot-betfair.service)...')
            try:
                import subprocess
                subprocess.run(
                    ['sudo', '-n', 'systemctl', 'restart', 'bot-betfair.service'],
                    check=True, timeout=15
                )
                responder(chat_id, '✅ Bot LAY reiniciado com sucesso.')
            except Exception as e:
                responder(chat_id, f'❌ Erro ao reiniciar: {e}')
        # ── /pausar ──────────────────────────────────────────────
        elif texto == '/pausar':
            responder(chat_id, '⏸️ Pausando bot LAY (bot-betfair.service)...')
            try:
                import subprocess
                subprocess.run(
                    ['sudo', '-n', 'systemctl', 'stop', 'bot-betfair.service'],
                    check=True, timeout=15
                )
                responder(chat_id, '⏸️ Bot LAY pausado. Use /retomar para religar.')
            except Exception as e:
                responder(chat_id, f'❌ Erro ao pausar: {e}')
        # ── /retomar ─────────────────────────────────────────────
        elif texto == '/retomar':
            responder(chat_id, '▶️ Retomando bot LAY (bot-betfair.service)...')
            try:
                import subprocess
                subprocess.run(
                    ['sudo', '-n', 'systemctl', 'start', 'bot-betfair.service'],
                    check=True, timeout=15
                )
                responder(chat_id, '▶️ Bot LAY retomado com sucesso.')
            except Exception as e:
                responder(chat_id, f'❌ Erro ao retomar: {e}')

        # ── /restart_under25 ─────────────────────────────────────
        elif texto == '/restart_under25':
            responder(chat_id, '🔄 Reiniciando bot Under 2.5 (bot-under25.service)...')
            try:
                import subprocess
                subprocess.run(
                    ['sudo', '-n', 'systemctl', 'restart', 'bot-under25.service'],
                    check=True, timeout=15
                )
                responder(chat_id, '✅ Bot Under 2.5 reiniciado com sucesso.')
            except Exception as e:
                responder(chat_id, f'❌ Erro ao reiniciar: {e}')

        # ── /ia_stats ────────────────────────────────────────────
        elif texto == '/ia_stats':
            try:
                import os, json as _json
                pasta = 'dados_bot'
                arquivos = sorted([f for f in os.listdir(pasta) if f.startswith('aprovados_')])
                if not arquivos:
                    responder(chat_id, 'Nenhum dado de aprovados encontrado ainda.')
                else:
                    grupos = {
                        'ia_ok':   {'v': 0, 'd': 0, 'p': 0},
                        'ia_indisp': {'v': 0, 'd': 0, 'p': 0},
                    }
                    for arq in arquivos:
                        with open(os.path.join(pasta, arq)) as ff:
                            jogos = _json.load(ff)
                        for info in jogos.values():
                            ia_motivo = info.get('ia_motivo', '')
                            grupo = 'ia_indisp' if ia_motivo.startswith('IA indisponivel') else 'ia_ok'
                            result = info.get('resultado_geral', '')
                            if result == 'VITORIA':
                                grupos[grupo]['v'] += 1
                            elif result == 'PERDA':
                                grupos[grupo]['d'] += 1
                            else:
                                grupos[grupo]['p'] += 1

                    def taxa(g):
                        total_decidido = g['v'] + g['d']
                        return round(g['v'] / total_decidido * 100, 1) if total_decidido else 0

                    linhas = [
                        '🤖 *Estatísticas do Filtro IA*',
                        '━━━━━━━━━━━━━━━━━━━━',
                        f'*IA avaliou de fato:*',
                        f'  ✅ {grupos["ia_ok"]["v"]}V / ❌ {grupos["ia_ok"]["d"]}D / ⏳ {grupos["ia_ok"]["p"]}P',
                        f'  🎯 Taxa de acerto: *{taxa(grupos["ia_ok"])}%*\n',
                        f'*IA indisponível (aprovado sem filtro):*',
                        f'  ✅ {grupos["ia_indisp"]["v"]}V / ❌ {grupos["ia_indisp"]["d"]}D / ⏳ {grupos["ia_indisp"]["p"]}P',
                        f'  🎯 Taxa de acerto: *{taxa(grupos["ia_indisp"])}%*',
                    ]
                    responder(chat_id, '\n'.join(linhas))
            except Exception as e:
                responder(chat_id, f'❌ Erro /ia_stats: {e}')

        # ── comando desconhecido ──────────────────────────────────
        elif texto.startswith('/'):
            responder(chat_id,
                '❓ *Comandos disponíveis:*\n'
                '/resultado — resultados do dia em R$\n'
                '/jogos — fila de jogos aguardando\n'
                '/status — status e uptime do bot\n'
                '/aprovados — jogos aprovados hoje\n'
                '/filtros — filtros ativos\n'
                '/reprovados — motivos de reprovação\n'
                '/historico — histórico de todos os dias\n'
                '/simulacoes — apostas simuladas\n'
                '/semana — resumo da semana atual\n'
                '/mes — resumo do mês atual\n'
                '/odds [times] — odds LAY de times\n'
                '/jogo [times] — analisa jogo completo\n'
                '/setfiltro [filtro] [valor] — altera filtro\n'
                '/amanha — jogos com CS disponíveis amanhã\n'
                '/hoje — possíveis entradas hoje (Over 1.5)\n'
                '/backtest — histórico completo de análises'
            )


def buscar_odds_por_times(nomes_times: list) -> str:
    import betfair_client as bf
    import json

    # Busca mercados CS do dia e amanha
    rpc = json.dumps({
        'jsonrpc': '2.0',
        'method': 'SportsAPING/v1.0/listMarketCatalogue',
        'params': {
            'filter': {
                'eventTypeIds': ['1'],
                'marketTypeCodes': ['CORRECT_SCORE'],
            },
            'maxResults': '1000',
            'marketProjection': ['EVENT', 'MARKET_START_TIME'],
        },
        'id': 1
    })

    mercados = bf.chamar_api(rpc) or []

    # Filtra jogos que contem algum dos times
    encontrados = {}
    for m in mercados:
        nome_jogo = m.get('event', {}).get('name', '')
        if any(t.lower() in nome_jogo.lower() for t in nomes_times):
            encontrados[m['marketId']] = {
                'nome': nome_jogo,
                'horario': m.get('marketStartTime', ''),
            }

    if not encontrados:
        return '❌ Nenhum jogo encontrado para: ' + ', '.join(nomes_times)

    # Busca odds
    books = bf.listar_odds(list(encontrados.keys()), ['EX_BEST_OFFERS'])

    linhas = ['📊 *Odds LAY — Correct Score*', '━━━━━━━━━━━━━━━━━━━━']

    for book in books:
        mid     = book['marketId']
        runners = book.get('runners', [])
        info    = encontrados.get(mid, {})
        nome    = info.get('nome', mid)

        try:
            from datetime import datetime, timezone, timedelta
            fuso    = timezone(timedelta(hours=-3))
            dt      = datetime.fromisoformat(info['horario'].replace('Z', '+00:00'))
            horario = dt.astimezone(fuso).strftime('%d/%m %H:%M')
        except:
            horario = '?'

        odd_10 = None
        odd_01 = None
        for r in runners:
            sid = r.get('selectionId')
            if sid == 2: odd_10 = bf.get_lay(r)
            if sid == 4: odd_01 = bf.get_lay(r)

        linhas.append(f'\n⚽ *{nome}* — {horario}')

        if odd_10 and odd_01:
            melhor    = '1-0' if odd_10 >= odd_01 else '0-1'
            melhor_odd = max(odd_10, odd_01)
            ok_10  = '✅' if 10 <= (odd_10 or 0) <= 22 else '❌'
            ok_01  = '✅' if 10 <= (odd_01 or 0) <= 22 else '❌'
            linhas.append(f'{ok_10} LAY 1-0 @ *{odd_10}*')
            linhas.append(f'{ok_01} LAY 0-1 @ *{odd_01}*')
            linhas.append(f'🎯 Entrar: LAY *{melhor}* @ *{melhor_odd}*')
        else:
            linhas.append('⏳ Odds ainda não disponíveis')

    linhas.append('\n✅ = dentro do filtro (10-22) | ❌ = fora')
    return '\n'.join(linhas)


def buscar_analise_jogo(busca: str) -> str:
    import betfair_client as bf
    import json

    rpc = json.dumps({
        'jsonrpc': '2.0',
        'method': 'SportsAPING/v1.0/listMarketCatalogue',
        'params': {
            'filter': {'eventTypeIds': ['1'], 'marketTypeCodes': ['CORRECT_SCORE', 'MATCH_ODDS', 'OVER_UNDER_15', 'BOTH_TEAMS_TO_SCORE']},
            'maxResults': '200',
            'marketProjection': ['COMPETITION', 'EVENT', 'MARKET_START_TIME', 'RUNNER_DESCRIPTION'],
        },
        'id': 1
    })

    mercados = bf.chamar_api(rpc) or []

    eventos = {}
    for m in mercados:
        evento = m.get('event', {})
        eid = evento.get('id')
        nome = evento.get('name', '')
        if not eid: continue
        termos = busca.lower().split()
        if not all(t in nome.lower() for t in termos): continue
        if eid not in eventos:
            eventos[eid] = {'nome': nome, 'mercados': [], 'open_date': evento.get('openDate', '')}
        eventos[eid]['mercados'].append(m)

    if not eventos:
        return '❌ Jogo não encontrado para: ' + busca

    linhas = ['🔍 *Análise de Jogo*', '━━━━━━━━━━━━━━━━━━━━']

    for eid, ev in list(eventos.items())[:2]:
        try:
            from datetime import datetime, timezone, timedelta
            fuso = timezone(timedelta(hours=-3))
            dt = datetime.fromisoformat(ev['open_date'].replace('Z', '+00:00'))
            horario = dt.astimezone(fuso).strftime('%d/%m %H:%M')
        except:
            horario = '?'

        linhas.append(f'\n⚽ *{ev["nome"]}* — {horario}')

        cs_m  = next((m for m in ev['mercados'] if m['marketName'] == 'Correct Score'), None)
        mo_m  = next((m for m in ev['mercados'] if m['marketName'] == 'Match Odds'), None)
        o15_m = next((m for m in ev['mercados'] if m['marketName'] == 'Over/Under 1.5 Goals'), None)
        bt_m  = next((m for m in ev['mercados'] if m['marketName'] == 'Both teams to Score?'), None)

        ids = [m['marketId'] for m in [cs_m, mo_m, o15_m, bt_m] if m]
        if not ids:
            linhas.append('❌ Sem mercados disponíveis')
            continue

        books = {b['marketId']: b for b in (bf.listar_odds(ids, ['EX_BEST_OFFERS']) or [])}

        fails = 0

        if cs_m and cs_m['marketId'] in books:
            book = books[cs_m['marketId']]
            runners = {r['selectionId']: r['runnerName'] for r in cs_m.get('runners', [])}
            bk = book.get('runners', [])
            odd_10 = next((bf.get_lay(r) for r in bk if runners.get(r['selectionId']) == '1 - 0'), None)
            odd_01 = next((bf.get_lay(r) for r in bk if runners.get(r['selectionId']) == '0 - 1'), None)
            liq = sum(o.get('size',0) for r in bk if runners.get(r['selectionId']) in ['1 - 0','0 - 1'] for o in r.get('ex',{}).get('availableToLay',[]))
            ok_10 = '✅' if odd_10 and 0 <= odd_10 <= 22 else '❌'
            ok_01 = '✅' if odd_01 and 0 <= odd_01 <= 22 else '❌'
            ok_liq = '✅' if liq >= 150 else '❌'
            if ok_10 == '❌': fails += 1
            if ok_01 == '❌': fails += 1
            if ok_liq == '❌': fails += 1
            linhas.append(f'{ok_10} LAY 1-0 @ *{odd_10}*')
            linhas.append(f'{ok_01} LAY 0-1 @ *{odd_01}*')
            linhas.append(f'{ok_liq} Liquidez: £{liq:,.0f}')

        if mo_m and mo_m['marketId'] in books:
            book = books[mo_m['marketId']]
            runners = {r['selectionId']: r['runnerName'] for r in mo_m.get('runners', [])}
            bk = book.get('runners', [])
            fav_odd = None
            fav_nome = None
            for r in bk:
                back = bf.get_back(r)
                nome_r = runners.get(r['selectionId'], '')
                if nome_r == 'The Draw': continue
                if back and (fav_odd is None or back < fav_odd):
                    fav_odd = back
                    fav_nome = nome_r
            ok_fav = '✅' if fav_odd and fav_odd <= 2.0 else '❌'
            if ok_fav == '❌': fails += 1
            linhas.append(f'{ok_fav} Favorito: {fav_nome} @ *{fav_odd}*')

        if o15_m and o15_m['marketId'] in books:
            book = books[o15_m['marketId']]
            runners = {r['selectionId']: r['runnerName'] for r in o15_m.get('runners', [])}
            bk = book.get('runners', [])
            odd_over = next((bf.get_back(r) for r in bk if runners.get(r['selectionId']) == 'Over 1.5 Goals'), None)
            ok_over = '✅' if odd_over and 1.15 <= odd_over <= 1.35 else '❌'
            if ok_over == '❌': fails += 1
            linhas.append(f'{ok_over} Over 1.5 @ *{odd_over}*')

        if bt_m and bt_m['marketId'] in books:
            book = books[bt_m['marketId']]
            runners = {r['selectionId']: r['runnerName'] for r in bt_m.get('runners', [])}
            bk = book.get('runners', [])
            odd_btts = next((bf.get_back(r) for r in bk if runners.get(r['selectionId']) == 'Yes'), None)
            ok_btts = '✅' if odd_btts and 1.55 <= odd_btts <= 2.30 else '❌'
            if ok_btts == '❌': fails += 1
            linhas.append(f'{ok_btts} BTTS @ *{odd_btts}*')

        linhas.append('━━━━━━━━━━━━━━━━━━━━')
        if fails == 0:
            linhas.append('🟢 *APROVADO — todos os filtros passaram*')
        else:
            linhas.append(f'🔴 *REPROVADO — {fails} filtro(s) falharam*')

    return '\n'.join(linhas)
