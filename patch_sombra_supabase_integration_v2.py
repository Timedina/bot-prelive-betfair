#!/usr/bin/env python3
"""
Patch (v2, corrigido): adiciona os campos de modo sombra ao dict de insert
da tabela 'analises' em supabase_integration.py.
"""
import ast
import shutil

ARQUIVO = "supabase_integration.py"
BACKUP = "supabase_integration.py.bak_sombra_v2"

with open(ARQUIVO, "r", encoding="utf-8") as f:
    linhas = f.readlines()

shutil.copy(ARQUIVO, BACKUP)
print(f"Backup salvo em {BACKUP}")

ALVO = "'no_limite_detalhes':"

indices = [i for i, linha in enumerate(linhas) if ALVO in linha]

if len(indices) == 0:
    print(f"ERRO: nenhuma linha contendo {ALVO!r} encontrada. Nenhuma alteracao feita.")
    raise SystemExit(1)
if len(indices) > 1:
    print(f"AVISO: {len(indices)} linhas contendo {ALVO!r} encontradas. Abortando (ambiguo).")
    for i in indices:
        print(f"  linha {i+1}: {linhas[i].rstrip()}")
    raise SystemExit(1)

idx = indices[0]
linha_alvo = linhas[idx]

indentacao = linha_alvo[: len(linha_alvo) - len(linha_alvo.lstrip())]

novas_linhas = [
    f"{indentacao}'sombra_razao_estreita': info.get('sombra_razao_estreita'),\n",
    f"{indentacao}'sombra_odd01_min25': info.get('sombra_odd01_min25'),\n",
    f"{indentacao}'sombra_odd01_min30': info.get('sombra_odd01_min30'),\n",
    f"{indentacao}'sombra_favorito_1_9_2_1': info.get('sombra_favorito_1_9_2_1'),\n",
]

linhas_final = linhas[: idx + 1] + novas_linhas + linhas[idx + 1 :]
nova_conteudo = "".join(linhas_final)

try:
    ast.parse(nova_conteudo)
except SyntaxError as e:
    print(f"ERRO de sintaxe apos patch: {e}. Nenhuma alteracao escrita.")
    raise SystemExit(1)

with open(ARQUIVO, "w", encoding="utf-8") as f:
    f.write(nova_conteudo)

print(f"Patch aplicado com sucesso na linha {idx+1} (indentacao: {len(indentacao)} chars).")
print("Sintaxe validada (ast.parse OK).")
