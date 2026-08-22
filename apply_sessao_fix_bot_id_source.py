import ast
import shutil
import sys
import datetime

PATH = "supabase_integration.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

OLD_REGISTRAR = """    try:
        import os
        bot_id = os.getenv('SUPABASE_BOT_ID', 'desconhecido')
        _client.table('sessao_betfair').upsert({
            'iniciada_em': inicio.isoformat(),
            'bot_origem': bot_id,
            'atualizada_em': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        }, on_conflict='bot_origem').execute()
    except Exception as e:
        log.warning(f'  Erro ao registrar sessao_betfair: {e}')"""

if content.count(OLD_REGISTRAR) != 1:
    print(f"ABORTA: ancora registrar encontrada {content.count(OLD_REGISTRAR)}x (esperado 1)")
    sys.exit(1)

NEW_REGISTRAR = """    try:
        import os
        bot_id = os.getenv('SUPABASE_BOT_ID_OVERRIDE', SUPABASE_BOT_ID)
        _client.table('sessao_betfair').upsert({
            'iniciada_em': inicio.isoformat(),
            'bot_origem': bot_id,
            'atualizada_em': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        }, on_conflict='bot_origem').execute()
    except Exception as e:
        log.warning(f'  Erro ao registrar sessao_betfair: {e}')"""

OLD_OBTER = """    try:
        import os
        alvo = bot_id or os.getenv('SUPABASE_BOT_ID', 'desconhecido')
        resp = _client.table('sessao_betfair').select('iniciada_em').eq('bot_origem', alvo).execute()"""

if content.count(OLD_OBTER) != 1:
    print(f"ABORTA: ancora obter encontrada {content.count(OLD_OBTER)}x (esperado 1)")
    sys.exit(1)

NEW_OBTER = """    try:
        import os
        alvo = bot_id or os.getenv('SUPABASE_BOT_ID_OVERRIDE', SUPABASE_BOT_ID)
        resp = _client.table('sessao_betfair').select('iniciada_em').eq('bot_origem', alvo).execute()"""

new_content = content.replace(OLD_REGISTRAR, NEW_REGISTRAR, 1)
new_content = new_content.replace(OLD_OBTER, NEW_OBTER, 1)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{PATH}.bak_fix_bot_id_source_{ts}"
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
