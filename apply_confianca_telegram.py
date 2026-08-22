import ast
import shutil
import sys
import datetime

PATH = "bot_prelive.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

IMPORT_ANCHOR = "from telegram_client import enviar_mensagem\n"
IMPORT_NEW = "from telegram_client import enviar_mensagem\nfrom confianca import classificar_confianca, formatar_para_telegram\n"

if content.count(IMPORT_ANCHOR) != 1:
    print(f"ABORTA: ancora de import encontrada {content.count(IMPORT_ANCHOR)}x (esperado 1)")
    sys.exit(1)

ALERTA_ANCHOR = (
    "    ia_str     = f'\\n🤖 _IA: {info[\"ia_motivo\"]}_' if info.get('ia_motivo') and info['ia_motivo'] != 'IA indisponível' else ''\n"
)
if content.count(ALERTA_ANCHOR) != 1:
    print(f"ABORTA: ancora de formatar_alerta encontrada {content.count(ALERTA_ANCHOR)}x (esperado 1)")
    sys.exit(1)

ALERTA_NEW = (
    ALERTA_ANCHOR +
    "    _confianca = classificar_confianca(minutos, info.get('no_limite'))\n"
    "    confianca_str = formatar_para_telegram(_confianca)\n"
)

RETURN_ANCHOR = (
    "        f'🆔 `{info.get(\"market_id_cs\", \"\")}`\\n'\n"
    "        f'📡 _Monitorando odds e saída automaticamente_{ia_str}'\n"
    "    )\n"
)
if content.count(RETURN_ANCHOR) != 1:
    print(f"ABORTA: ancora de return encontrada {content.count(RETURN_ANCHOR)}x (esperado 1)")
    sys.exit(1)

RETURN_NEW = (
    "        f'🆔 `{info.get(\"market_id_cs\", \"\")}`\\n'\n"
    "        f'{confianca_str}\\n'\n"
    "        f'📡 _Monitorando odds e saída automaticamente_{ia_str}'\n"
    "    )\n"
)

new_content = content.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)
new_content = new_content.replace(ALERTA_ANCHOR, ALERTA_NEW, 1)
new_content = new_content.replace(RETURN_ANCHOR, RETURN_NEW, 1)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{PATH}.bak_confianca_telegram_{ts}"
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
