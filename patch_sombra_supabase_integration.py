#!/usr/bin/env python3
"""
Patch: adiciona os campos de modo sombra ao dicionario de insert da tabela 'analises'
em supabase_integration.py.
"""
import ast
import shutil

ARQUIVO = "supabase_integration.py"
BACKUP = "supabase_integration.py.bak_sombra"

with open(ARQUIVO, "r", encoding="utf-8") as f:
    conteudo = f.read()

shutil.copy(ARQUIVO, BACKUP)
print(f"Backup salvo em {BACKUP}")

ANCORA = "'no_limite': resultado.get('no_limite'),"

count = conteudo.count(ANCORA)
if count == 0:
    print("ERRO: ancora exata nao encontrada.")
    print("Rode: grep -n \"no_limite\" supabase_integration.py")
    print("e mande o output para ajustar o patch.")
    raise SystemExit(1)
if count > 1:
    print(f"AVISO: ancora encontrada {count} vezes. Abortando (ambiguo).")
    raise SystemExit(1)

PATCH = ANCORA + """
            'sombra_razao_estreita': resultado.get('sombra_razao_estreita'),
            'sombra_odd01_min25': resultado.get('sombra_odd01_min25'),
            'sombra_odd01_min30': resultado.get('sombra_odd01_min30'),
            'sombra_favorito_1_9_2_1': resultado.get('sombra_favorito_1_9_2_1'),"""

nova_conteudo = conteudo.replace(ANCORA, PATCH, 1)

try:
    ast.parse(nova_conteudo)
except SyntaxError as e:
    print(f"ERRO de sintaxe apos patch: {e}. Nenhuma alteracao escrita.")
    raise SystemExit(1)

with open(ARQUIVO, "w", encoding="utf-8") as f:
    f.write(nova_conteudo)

print("Patch aplicado com sucesso e sintaxe validada (ast.parse OK).")
