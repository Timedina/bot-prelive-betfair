#!/usr/bin/env python3
"""
Patch: adiciona calculo de flags de modo sombra (filtros candidatos, NAO bloqueiam)
logo apos o bloco de auditoria 'no_limite' em bot_prelive.py.
"""
import ast
import shutil

ARQUIVO = "bot_prelive.py"
BACKUP = "bot_prelive.py.bak_sombra"

with open(ARQUIVO, "r", encoding="utf-8") as f:
    conteudo = f.read()

shutil.copy(ARQUIVO, BACKUP)
print(f"Backup salvo em {BACKUP}")

ANCORA = "resultado['aprovado'] = True"

count = conteudo.count(ANCORA)
if count == 0:
    print("ERRO: ancora nao encontrada. Nenhuma alteracao feita.")
    raise SystemExit(1)
if count > 1:
    print(f"AVISO: ancora encontrada {count} vezes. Abortando para evitar patch no lugar errado.")
    raise SystemExit(1)

PATCH = ANCORA + """

    # --- MODO SOMBRA: filtros candidatos, apenas logados, NAO bloqueiam aprovacao ---
    try:
        _razao_sombra = (odd_01 / odd_10) if odd_10 else None
        resultado['sombra_razao_estreita'] = (
            _razao_sombra is not None and not (1.2 <= _razao_sombra <= 1.6)
        )
        resultado['sombra_odd01_min25'] = odd_01 < 25
        resultado['sombra_odd01_min30'] = odd_01 < 30
        resultado['sombra_favorito_1_9_2_1'] = not (1.90 <= odd_favorito <= 2.09)
    except Exception as _e_sombra:
        log.warning(f"Modo sombra: falha ao calcular flags ({_e_sombra}), seguindo sem elas")
"""

nova_conteudo = conteudo.replace(ANCORA, PATCH, 1)

try:
    ast.parse(nova_conteudo)
except SyntaxError as e:
    print(f"ERRO de sintaxe apos patch: {e}. Nenhuma alteracao escrita.")
    raise SystemExit(1)

with open(ARQUIVO, "w", encoding="utf-8") as f:
    f.write(nova_conteudo)

print("Patch aplicado com sucesso e sintaxe validada (ast.parse OK).")
