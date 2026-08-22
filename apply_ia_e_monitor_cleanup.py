import sys, shutil, datetime

ARQ = "bot_prelive.py"
ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{ARQ}.bak_ia_monitor_cleanup_{ts}"

with open(ARQ, "r", encoding="utf-8") as f:
    conteudo = f.read()

edicoes = []

anchor1 = '''    ia_str     = f'\n🤖 _IA: {info["ia_motivo"]}_' if info.get('ia_motivo') and info['ia_motivo'] != 'IA indisponível' else ''
'''
novo1 = '''    ia_str     = f'\n🤖 _IA: {info["ia_motivo"]}_' if info.get('ia_motivo') and not info['ia_motivo'].startswith('IA indisponivel') else ''
'''
edicoes.append((anchor1, novo1))

anchor2 = "        f'📡 Monitor de odds e saída: *ativo*'\n"
novo2 = "        f'🔌 Sessão Betfair: sob demanda (desloga se ocioso >{MARGEM_LOGOUT_MIN}min)'\n"
edicoes.append((anchor2, novo2))

anchor3 = '''        return (f'Fila: {aguardando} aguardando | '
                f'Cache: {cache_eventos.total()} bloqueados | '
                f'Monitor odds: {monitor_odds.total()} | '
                f'Monitor saida: {monitor_saida.total()}')
'''
novo3 = '''        return (f'Fila: {aguardando} aguardando | '
                f'Cache: {cache_eventos.total()} bloqueados')
'''
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
