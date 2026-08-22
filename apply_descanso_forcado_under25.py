import sys, shutil, datetime

ARQ = "bot_under25.py"
ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{ARQ}.bak_descanso_forcado_{ts}"

with open(ARQ, "r", encoding="utf-8") as f:
    conteudo = f.read()

edicoes = []

anchor1 = "FUSO_BRASILIA = timezone(timedelta(hours=-3))\n"
novo1 = anchor1 + (
    "HORA_DESCANSO_INICIO = 2  # 22/08: janela diaria de descanso forcado -- inicio (hora Brasilia)\n"
    "HORA_DESCANSO_FIM    = 5  # 22/08: janela diaria de descanso forcado -- fim (hora Brasilia)\n"
)
edicoes.append((anchor1, novo1))

anchor2 = '''            ativo = dentro_de_janela(agora, janelas_do_dia) or len(apostas_ativas) > 0

            if ativo:'''
novo2 = '''            ativo = dentro_de_janela(agora, janelas_do_dia) or len(apostas_ativas) > 0

            # 22/08: janela diaria de descanso forcado (02h-05h Brasilia) -- garante que a
            # conta Betfair fica realmente sem NENHUMA sessao aberta por um bloco todo dia,
            # coincidindo com a mesma janela do bot LAY. So forca o descanso quando nao ha
            # aposta aberta (nunca abandona o monitoramento de saida de uma posicao real).
            hora_br_idle = datetime.now(FUSO_BRASILIA).hour
            em_janela_descanso = HORA_DESCANSO_INICIO <= hora_br_idle < HORA_DESCANSO_FIM
            if em_janela_descanso and len(apostas_ativas) == 0:
                ativo = False

            if ativo:'''
edicoes.append((anchor2, novo2))

anchor3 = '''            else:
                if bf.SESSION_TOKEN is not None:
                    bf.logout()
                    log.info("Fora de janela ativa e sem apostas abertas - sessao encerrada")'''
novo3 = '''            else:
                if bf.SESSION_TOKEN is not None:
                    bf.logout()
                    if em_janela_descanso:
                        log.info("Janela de descanso forcado (02h-05h) - sessao encerrada")
                    else:
                        log.info("Fora de janela ativa e sem apostas abertas - sessao encerrada")'''
edicoes.append((anchor3, novo3))

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

print(f"OK -- 3 edicoes aplicadas. Backup: {bak}")
