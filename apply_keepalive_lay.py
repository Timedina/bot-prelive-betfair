import ast
import shutil
import sys
import datetime

PATH = "bot_prelive.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

ANCHOR = (
    "    while True:\n"
    "        try:\n"
    "            aplicar_filtros_supabase()\n"
)

if content.count(ANCHOR) != 1:
    print(f"ABORTA: ancora encontrada {content.count(ANCHOR)}x (esperado 1)")
    sys.exit(1)

NEW = (
    "    while True:\n"
    "        try:\n"
    "            bf.renovar_token_se_necessario()  # fix 19/08: LAY nunca chamava isso, so o Under25 -- causa provavel do bloqueio de conta perto das ~23h\n"
    "            aplicar_filtros_supabase()\n"
)

new_content = content.replace(ANCHOR, NEW, 1)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{PATH}.bak_keepalive_lay_{ts}"
shutil.copy(PATH, backup_path)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(new_content)

try:
    ast.parse(new_content)
    print(f"OK: patch aplicado, backup em {backup_path}, ast.parse validado.")
except SyntaxError as e:
    shutil.copy(backup_path, PATH)
    print(f"ERRO DE SINTAXE, revertido: {e}")
    sys.exit(1)
