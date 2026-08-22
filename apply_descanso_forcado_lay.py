import sys, shutil, datetime

ARQ = "bot_prelive.py"
ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{ARQ}.bak_descanso_forcado_{ts}"

with open(ARQ, "r", encoding="utf-8") as f:
    conteudo = f.read()

edicoes = []

anchor1 = "MARGEM_LOGOUT_MIN       = 15     # 21/08: folga minima (min) sem nada pendente pra deslogar da Betfair\n"
novo1 = anchor1 + (
    "HORA_DESCANSO_INICIO    = 2      # 22/08: janela diaria de descanso forcado -- inicio (hora Brasilia)\n"
    "HORA_DESCANSO_FIM       = 5      # 22/08: janela diaria de descanso forcado -- fim (hora Brasilia)\n"
)
edicoes.append((anchor1, novo1))

anchor2 = '''                candidatos = [t for t in (min(proximas) if proximas else None,
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
novo2 = '''                candidatos = [t for t in (min(proximas) if proximas else None,
                                           proxima_recarga, proxima_resultado) if t is not None]
                prox_evento = min(candidatos)
                agora_utc_idle = datetime.now(timezone.utc)
                folga_min = (prox_evento - agora_utc_idle).total_seconds() / 60

                # 22/08: janela diaria de descanso forcado (02h-05h Brasilia) -- garante que
                # a conta Betfair fica realmente sem NENHUMA sessao aberta por um bloco todo
                # dia, mesmo que a folga normal (MARGEM_LOGOUT_MIN) nao justificasse deslogar
                # agora. So se aplica quando ja estamos no ramo ocioso (nao pula verificacao
                # de jogo real que porventura caia dentro da janela).
                hora_br_idle = agora_utc_idle.astimezone(FUSO_BRASILIA).hour
                em_janela_descanso = HORA_DESCANSO_INICIO <= hora_br_idle < HORA_DESCANSO_FIM

                # Nada precisando da Betfair nos proximos MARGEM_LOGOUT_MIN minutos -> desloga.
                # chamar_api() faz login sozinho na proxima chamada real (recarga, analise ou
                # checagem de resultado), entao nao ha necessidade de relogar preventivamente.
                deve_deslogar = folga_min > MARGEM_LOGOUT_MIN or em_janela_descanso
                if deve_deslogar:
                    bf.logout()  # no-op barato se ja estiver deslogado

                sufixo_log = ''
                if em_janela_descanso:
                    sufixo_log = ' | sessao Betfair encerrada (janela de descanso 02h-05h)'
                elif deve_deslogar:
                    sufixo_log = ' | sessao Betfair encerrada'

                if proximas:
                    prox   = min(proximas)
                    espera = max(10, min(60, (prox - agora_utc_idle).total_seconds()))
                    log.info(f'  Proxima: {prox.astimezone(FUSO_BRASILIA).strftime("%H:%M")} — aguardando {int(espera)}s' + sufixo_log)
                    time.sleep(espera)
                else:
                    log.info('  Sem jogos na fila. Aguardando 60s...' + sufixo_log)
                    time.sleep(60)
                continue
'''
edicoes.append((anchor2, novo2))

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

print(f"OK -- 2 edicoes aplicadas. Backup: {bak}")
