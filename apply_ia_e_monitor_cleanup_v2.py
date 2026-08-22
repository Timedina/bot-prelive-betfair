import re, sys, shutil, datetime

ARQ = "bot_prelive.py"
ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"{ARQ}.bak_ia_monitor_cleanup_{ts}"

with open(ARQ, "r", encoding="utf-8") as f:
    conteudo = f.read()

mudancas = 0

padrao1 = re.compile(
    r"^(\s*ia_str\s*=\s*f'\\n🤖 _IA: \{info\[\"ia_motivo\"\]\}_' if info\.get\('ia_motivo'\) and info\['ia_motivo'\] )\!= '[^']*'( else '')\s*$",
    re.MULTILINE
)
conteudo, n1 = padrao1.subn(r"\1and not info['ia_motivo'].startswith('IA indisponivel')\2", conteudo)
if n1 != 1:
    print(f"ABORTADO -- EDIT 1: padrao encontrado {n1}x (esperado 1x)")
    sys.exit(1)
mudancas += 1

anchor2 = "        f'📡 Monitor de odds e saída: *ativo*'\n"
n2 = conteudo.count(anchor2)
if n2 == 1:
    conteudo = conteudo.replace(anchor2, "        f'🔌 Sessão Betfair: sob demanda (desloga se ocioso >{MARGEM_LOGOUT_MIN}min)'\n", 1)
    mudancas += 1
else:
    print(f"ABORTADO -- EDIT 2: anchor encontrado {n2}x (esperado 1x)")
    sys.exit(1)

anchor3 = '''        return (f'Fila: {aguardando} aguardando | '
                f'Cache: {cache_eventos.total()} bloqueados | '
                f'Monitor odds: {monitor_odds.total()} | '
                f'Monitor saida: {monitor_saida.total()}')
'''
n3 = conteudo.count(anchor3)
if n3 == 1:
    conteudo = conteudo.replace(anchor3, '''        return (f'Fila: {aguardando} aguardando | '
                f'Cache: {cache_eventos.total()} bloqueados')
''', 1)
    mudancas += 1
else:
    print(f"ABORTADO -- EDIT 3: anchor encontrado {n3}x (esperado 1x)")
    sys.exit(1)

anchor4 = "        f'📡 _Monitorando odds e saída automaticamente_{ia_str}'\n"
n4 = conteudo.count(anchor4)
if n4 == 1:
    conteudo = conteudo.replace(anchor4, "        f'{ia_str}'\n", 1)
    mudancas += 1
else:
    print(f"AVISO -- EDIT 4: anchor encontrado {n4}x (esperado 1x) -- pulando essa edicao, resto aplicado normalmente")

shutil.copy(ARQ, bak)
with open(ARQ, "w", encoding="utf-8") as f:
    f.write(conteudo)

print(f"OK -- {mudancas} edicoes principais aplicadas (+ EDIT 4 se nao avisado acima). Backup: {bak}")
