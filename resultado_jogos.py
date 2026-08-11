"""
resultado_jogos.py
Busca o resultado final dos jogos aprovados via Betfair API
e atualiza o arquivo JSON com o placar real
"""

import json
import os
from datetime import datetime, timezone, timedelta
import betfair_client as bf

FUSO_BRASILIA = timezone(timedelta(hours=-3))
PASTA_DADOS   = 'dados_bot'


def arquivo_do_dia(data_str=None) -> str:
    if not data_str:
        data_str = datetime.now(FUSO_BRASILIA).strftime('%Y-%m-%d')
    return os.path.join(PASTA_DADOS, f'aprovados_{data_str}.json')


def carregar_aprovados(data_str=None) -> dict:
    path = arquivo_do_dia(data_str)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def salvar_aprovados(dados: dict, data_str=None):
    path = arquivo_do_dia(data_str)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def buscar_resultado_mercado(market_id: str) -> dict:
    """
    Busca o resultado final de um mercado Correct Score na Betfair
    Retorna dict com placar e status
    """
    import json as _json
    import urllib.request
    import urllib.error

    rpc = _json.dumps({
        'jsonrpc': '2.0',
        'method': 'SportsAPING/v1.0/listMarketBook',
        'params': {
            'marketIds': [market_id],
            'priceProjection': {'priceData': ['EX_BEST_OFFERS']},
        },
        'id': 1
    })

    resultado = bf.chamar_api(rpc)
    if not resultado:
        return {'status': 'erro', 'placar': None}

    book = resultado[0] if isinstance(resultado, list) else resultado
    status = book.get('status', '')

    # Mercado encerrado — busca o runner vencedor
    if status in ('CLOSED', 'SETTLED'):
        runners = book.get('runners', [])
        for r in runners:
            if r.get('status') == 'WINNER':
                return {
                    'status':    'encerrado',
                    'runner_id': r.get('selectionId'),
                    'placar':    None  # será preenchido pelo nome do runner
                }
        return {'status': 'encerrado_sem_vencedor', 'placar': None}

    elif status == 'OPEN':
        inplay = book.get('inplay', False)
        return {'status': 'ao_vivo' if inplay else 'aberto', 'placar': None}

    return {'status': status.lower(), 'placar': None}


def buscar_nome_runner_vencedor(market_id: str, selection_id: int) -> str:
    """Busca o nome do runner vencedor no catálogo"""
    import json as _json

    rpc = _json.dumps({
        'jsonrpc': '2.0',
        'method': 'SportsAPING/v1.0/listMarketCatalogue',
        'params': {
            'filter': {'marketIds': [market_id]},
            'maxResults': '1',
            'marketProjection': ['RUNNER_DESCRIPTION']
        },
        'id': 1
    })

    resultado = bf.chamar_api(rpc)
    if not resultado:
        return None

    mercado = resultado[0] if isinstance(resultado, list) else resultado
    for runner in mercado.get('runners', []):
        if runner.get('selectionId') == selection_id:
            return runner.get('runnerName', '')

    return None


def determinar_resultado_lay(placar_final: str, info_jogo: dict) -> dict:
    """
    Determina o resultado do LAY que foi REALMENTE colocado na Betfair.

    A execucao atual (apostas.py) coloca UM unico LAY (0-1 por padrao, pois
    APENAS_LAY_01=True), com stake = liability/(odd-1) e liability fixa de
    LIABILITY_FIXA=100. O PnL deve refletir esa unica posicao (nao o antigo
    modelo "duplo" 1-0 + 0-1 simultaneos com stake fixo de £10):

      - placar_final == placar_lay -> LAY perde (liability perdida)
      - caso contrario             -> LAY ganha (stake liquido apos comissao)

    Usa os dados reais gravados pela aposta (stake/odd_lay/placar_lay) em
    `atualizar_aprovado_com_aposta`; quando ausentes, faz fallback para o
    cenario histórico (LAY 0-1, liability 100).
    """
    resultado = {
        'placar_final': placar_final,
        'lay_10': None,
        'lay_01': None,
        'resultado_geral': None,
        'pnl_estimado': None,
    }

    if not placar_final:
        return resultado

    # Normaliza placares ("1 - 0" / "1–0" -> "1-0")
    placar = placar_final.replace(' ', '').replace('–', '-')

    # Lay colocado (gravado pela aposta). Fallback 0-1 (APENAS_LAY_01).
    placar_lay = (info_jogo.get('placar_lay') or '0-1').replace(' ', '').replace('–', '-')
    odd_lay = float(info_jogo.get('odd_lay') or 0)
    if odd_lay <= 0:
        odd_lay = float(info_jogo.get('odd_01') or 0)

    comissao = 0.0636  # comissao Betfair usada nos backtests de producao

    # Stake real gravado; fallback = liability fixa 100 / (odd-1)
    stake = float(info_jogo.get('stake') or 0)
    if stake <= 0:
        if odd_lay > 1:
            stake = 100.0 / (odd_lay - 1)  # LIABILITY_FIXA
        else:
            stake = 0.0

    if placar == placar_lay:
        pnl = -(stake * (odd_lay - 1)) if odd_lay > 1 else 0.0
        resultado['resultado_geral'] = 'PERDA'
    else:
        pnl = stake * (1 - comissao)
        resultado['resultado_geral'] = 'VITORIA'

    resultado['lay_10'] = 'GANHO' if placar != '1-0' else 'PERDA'
    resultado['lay_01'] = 'GANHO' if placar != '0-1' else 'PERDA'
    resultado['pnl_estimado'] = round(pnl, 2)
    return resultado


def atualizar_resultados_do_dia(data_str=None, verbose=True):
    """
    Busca e atualiza os resultados de todos os jogos aprovados do dia
    """
    aprovados = carregar_aprovados(data_str)

    if not aprovados:
        if verbose:
            print('Nenhum jogo aprovado encontrado.')
        return

    atualizados = 0

    for event_id, info in aprovados.items():
        market_id = info.get('market_id_cs')
        if not market_id:
            continue

        # Já tem resultado? Pula
        if info.get('placar_final') and info.get('resultado_geral'):
            if verbose:
                print(f"  {info['nome_jogo']}: já tem resultado ({info['placar_final']})")
            continue

        if verbose:
            print(f"  Buscando resultado: {info['nome_jogo']}...")

        # Busca status do mercado
        res = buscar_resultado_mercado(market_id)

        if res['status'] not in ('encerrado', 'encerrado_sem_vencedor'):
            if verbose:
                print(f"    Status: {res['status']} — jogo ainda não encerrado")
            continue

        # Busca nome do runner vencedor
        placar_final = None
        if res.get('runner_id'):
            runner_id = res['runner_id']
            mapa_cs = info.get('runners_cs_map') or {}
            nome = mapa_cs.get(str(runner_id))
            if not nome:
                nome = buscar_nome_runner_vencedor(market_id, runner_id)
            if nome:
                placar_final = nome.replace(' ', '').replace('–', '-')

        # Calcula resultado do LAY
        resultado_lay = determinar_resultado_lay(placar_final, info)

        # Atualiza info do jogo
        info['placar_final']    = placar_final or 'Indisponível'
        info['lay_10_resultado']= resultado_lay['lay_10']
        info['lay_01_resultado']= resultado_lay['lay_01']
        info['resultado_geral'] = resultado_lay['resultado_geral']
        info['pnl_estimado']    = resultado_lay['pnl_estimado']
        info['resultado_em']    = datetime.now(FUSO_BRASILIA).strftime('%H:%M:%S')

        atualizados += 1

        if verbose:
            emoji = '✅' if resultado_lay['resultado_geral'] == 'VITORIA' else '⚠️'
            pnl_val = resultado_lay['pnl_estimado']
            pnl_txt = f"{pnl_val:+.2f}" if pnl_val is not None else "N/A"
            print(f"    {emoji} Placar: {placar_final} | {resultado_lay['resultado_geral']} | PnL: {pnl_txt}")

    if atualizados > 0:
        salvar_aprovados(aprovados, data_str)
        if verbose:
            print(f'\n  {atualizados} resultado(s) atualizados!')
    else:
        if verbose:
            print('  Nenhum resultado novo encontrado.')

    return aprovados


def atualizar_resultados_pendentes(dias_atras: int = 14, verbose: bool = False) -> dict:
    """
    Atualiza os resultados pendentes dos ultimos `dias_atras` dias (incluindo hoje),
    reutilizando a mesma logica de atualizacao diaria (`atualizar_resultados_do_dia`).

    Usado pelo bot (bot_prelive.py) no acompanhamento automatico de resultados.
    Retorna dict {data_str (YYYY-MM-DD): {event_id: info}} apenas com os dias
    que possuem jogos aprovados salvos, para o chamador processar sem falhar.
    """
    por_dia: dict = {}
    hoje = datetime.now(FUSO_BRASILIA)
    for offset in range(dias_atras, -1, -1):
        data_str = (hoje - timedelta(days=offset)).strftime('%Y-%m-%d')
        try:
            aprovados = atualizar_resultados_do_dia(data_str=data_str, verbose=verbose)
        except Exception as e:
            if verbose:
                print(f'  Erro ao atualizar resultados de {data_str}: {e}')
            continue
        if aprovados:
            por_dia[data_str] = aprovados
    return por_dia


def resumo_resultados(data_str=None) -> str:
    """Gera resumo dos resultados do dia para o Telegram"""
    aprovados = carregar_aprovados(data_str)
    data = data_str or datetime.now(FUSO_BRASILIA).strftime('%d/%m/%Y')

    if not aprovados:
        return f'📋 Sem jogos aprovados em {data}'

    vitorias   = 0
    derrotas   = 0
    pendentes  = 0
    pnl_total  = 0.0
    linhas = [f'📊 *Resultados — {data}*', '━━━━━━━━━━━━━━━━━━━━']

    for info in sorted(aprovados.values(), key=lambda x: x.get('horario','')):
        nome   = info.get('nome_jogo', '')
        horario= info.get('horario', '--:--')
        placar = info.get('placar_final', '')
        result = info.get('resultado_geral', '')
        pnl    = info.get('pnl_estimado', 0) or 0

        result_norm = result.replace('Ó', 'O')  # tolera dados legados com acento
        if result_norm == 'VITORIA':
            emoji = '✅'
            vitorias += 1
            pnl_total += pnl
        elif result_norm == 'PERDA':
            emoji = '⚠️'
            derrotas += 1
            pnl_total += pnl
        else:
            emoji = '⏳'
            pendentes += 1

        placar_str = f' | {placar}' if placar else ''
        pnl_str    = f' | PnL: {pnl:+.1f}u' if result else ''
        linhas.append(f'{emoji} {horario} {nome}{placar_str}{pnl_str}')

    linhas += [
        '━━━━━━━━━━━━━━━━━━━━',
        f'✅ Vitórias: {vitorias} | ⚠️ Perdas: {derrotas} | ⏳ Pendentes: {pendentes}',
        f'💰 PnL Total: {pnl_total:+.1f} unidades (liability £100/LAY)',
    ]

    return '\n'.join(linhas)


if __name__ == '__main__':
    print('Atualizando resultados do dia...')
    bf.login()
    atualizar_resultados_do_dia(verbose=True)
    print()
    print(resumo_resultados())
