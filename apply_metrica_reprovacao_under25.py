import shutil, time, sys

ARQUIVO = "bot_under25.py"
backup = f"{ARQUIVO}.bak_metrica_reprovacao_{int(time.time())}"

with open(ARQUIVO, "r", encoding="utf-8") as f:
    conteudo = f.read()

ANCORA = """        odd, liq = obter_odd_e_liquidez_under(market_id, under_sel_id)
        if odd is None:
            continue
        if not (filtros["ODD_MINIMA"] <= odd <= filtros["ODD_MAXIMA"]):
            continue
        liq_minima = filtros["LIQUIDEZ_MINIMA"]
        if liq < liq_minima:
            continue"""

NOVO = """        odd, liq = obter_odd_e_liquidez_under(market_id, under_sel_id)
        if odd is None:
            continue
        if not (filtros["ODD_MINIMA"] <= odd <= filtros["ODD_MAXIMA"]):
            sb.registrar_metrica_reprovacao("Odd fora do intervalo")
            continue
        liq_minima = filtros["LIQUIDEZ_MINIMA"]
        if liq < liq_minima:
            sb.registrar_metrica_reprovacao("Liquidez insuficiente")
            continue"""

count = conteudo.count(ANCORA)
if count != 1:
    print(f"ABORTADO: ancora encontrada {count}x (esperado 1). Nada foi alterado.")
    sys.exit(1)

shutil.copy(ARQUIVO, backup)
conteudo = conteudo.replace(ANCORA, NOVO)

with open(ARQUIVO, "w", encoding="utf-8") as f:
    f.write(conteudo)

print(f"OK - patch aplicado. Backup salvo em {backup}")
