import re, sys, shutil, datetime

ARQ = "bot_prelive.py"
ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{ARQ}.bak_logout_ocioso_{ts}"

with open(ARQ, "r", encoding="utf-8") as f:
    conteudo = f.read()

edicoes = []

# EDIT 1 -- constante nova, perto de INTERVALO_LONGE
anchor1 = "INTERVALO_LONGE         = 15     # minutos para jogos > 30 min antes\n"
novo1 = anchor1 + "MARGEM_LOGOUT_MIN       = 15     # 21/08: folga minima (min) sem nada pendente pra deslogar da Betfair\n"
edicoes.append((anchor1, novo1))

# EDIT 2 -- remove keep-alive proativo do topo do loop
anchor2 = "            bf.renovar_token_se_necessario()  # fix 19/08: LAY nunca chamava isso, so o Under25 -- causa provavel do bloqueio de conta perto das ~23h\n"
novo2 = (
    "            # 21/08: keep-alive proativo removido -- causa raiz real do bloqueio de ~23h e\n"
    "            # sessao continua demais, nao token vencido. Login/renovacao agora e' sob demanda\n"
    "            # (chamar_api() ja loga sozinho quando nao ha sessao valida) + logout explicito\n"
    "            # nos periodos ociosos, mais abaixo no loop.\n"
)
edicoes.append((anchor2, novo2))

# EDIT 3 -- remove chamada dos monitores + reescreve branch ocioso com logout
anchor3 = '''            if monitor_odds.total() > 0:
                monitor_odds.verificar_todos()
            if monitor_saida.total() > 0:
                monitor_saida.verificar_todos()

            para_verificar = agendador.jogos_para_verificar_agora()

            if not para_verificar:
                proximas = [d['proxima_verificacao'] for d in agendador.jogos.values()
                            if d['estado'] == 'aguardando']
                if proximas:
                    prox   = min(proximas)
                    espera = max(10, min(60, (prox - datetime.now(timezone.utc)).total_seconds()))
                    log.info(f'  Proxima: {prox.astimezone(FUSO_BRASILIA).strftime("%H:%M")} — aguardando {int(espera)}s')
                    time.sleep(espera)
                else:
                    log.info('  Sem jogos na fila. Aguardando 60s...')
                    time.sleep(60)
                continue
'''
novo3 = '''            # 21/08: monitor de odds/saida pos-aprovacao removido -- aposta e' mantida ate o
            # resultado final (sem cash-out antecipado), entao o monitoramento continuo de
            # odds no pos-jogo nao tem efeito pratico e so mantinha a sessao Betfair ocupada
            # sem necessidade. Resultado final continua sendo resolvido via resultado_jogos.py
            # (rotina separada, ja existente, INTERVALO_RESULTADO_MIN).

            para_verificar = agendador.jogos_para_verificar_agora()

            if not para_verificar:
                proximas = [d['proxima_verificacao'] for d in agendador.jogos.values()
                            if d['estado'] == 'aguardando']
                proxima_recarga   = ultima_recarga + timedelta(hours=INTERVALO_RECARGA_HORAS)
                proxima_resultado = (ultimo_resultado_auto + timedelta(minutes=INTERVALO_RESULTADO_MIN)
                                      if RESULTADO_DISPONIVEL else None)
                candidatos = [t for t in (min(proximas) if proximas else None,
                                           proxima_recarga, proxima_resultado) if t is not None]
                prox_evento = min(candidatos)
                agora_utc_idle = datetime.now(timezone.utc)
                folga_min = (prox_evento - agora_utc_idle).total_seconds() / 60

                # Nada precisando da Betfair nos proximos MARGEM_LOGOUT_MIN minutos -> desloga.
                # chamar_api() faz login sozinho na proxima chamada real (recarga, analise ou
                # checagem de resultado), entao nao ha necessidade de relogar preventivamente.
                if folga_min > MARGEM_LOGOUT_MIN:
                    bf.logout()  # no-op barato se ja estiver deslogado

                if proximas:
                    prox   = min(proximas)
                    espera = max(10, min(60, (prox - agora_utc_idle).total_seconds()))
                    log.info(f'  Proxima: {prox.astimezone(FUSO_BRASILIA).strftime("%H:%M")} — aguardando {int(espera)}s'
                             + (' | sessao Betfair encerrada' if folga_min > MARGEM_LOGOUT_MIN else ''))
                    time.sleep(espera)
                else:
                    log.info('  Sem jogos na fila. Aguardando 60s...'
                             + (' | sessao Betfair encerrada' if folga_min > MARGEM_LOGOUT_MIN else ''))
                    time.sleep(60)
                continue
'''
edicoes.append((anchor3, novo3))

# EDIT 4 -- remove alimentacao dos monitores apos aprovacao
anchor4 = "                    monitor_odds.adicionar(info)\n                    monitor_saida.adicionar(info)\n\n                else:\n"
novo4 = "                else:\n"
edicoes.append((anchor4, novo4))

# Validacao: cada anchor deve aparecer exatamente 1 vez
erros = []
for i, (anchor, _) in enumerate(edicoes, 1):
    n = conteudo.count(anchor)
    if n != 1:
        erros.append(f"EDIT {i}: anchor encontrado {n}x (esperado 1x)")

if erros:
    print("ABORTADO -- anchors nao batem com o arquivo atual:")
    for e in erros:
        print(" -", e)
    sys.exit(1)

shutil.copy(ARQ, bak)
for anchor, novo in edicoes:
    conteudo = conteudo.replace(anchor, novo, 1)

with open(ARQ, "w", encoding="utf-8") as f:
    f.write(conteudo)

print(f"OK -- 4 edicoes aplicadas. Backup: {bak}")
