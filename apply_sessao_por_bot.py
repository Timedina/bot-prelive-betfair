import ast
import shutil
import sys
import datetime

PATH = "supabase_integration.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

OLD_REGISTRAR = """def registrar_sessao_betfair(inicio):
    \"\"\"Registra o horario real de inicio de sessao continua na Betfair (reseta so no logout de verdade).\"\"\"
    if not SUPABASE_ATIVO:
        return
    try:
        import os
        _client.table('sessao_betfair').upsert({
            'id': 1,
            'iniciada_em': inicio.isoformat(),
            'bot_origem': os.getenv('SUPABASE_BOT_ID', 'desconhecido'),
            'atualizada_em': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning(f'  Erro ao registrar sessao_betfair: {e}')


def obter_sessao_betfair():
    \"\"\"Retorna o timestamp ISO de inicio da sessao Betfair atual, ou None.\"\"\"
    if not SUPABASE_ATIVO:
        return None
    try:
        resp = _client.table('sessao_betfair').select('iniciada_em').eq('id', 1).execute()
        if resp.data:
            return resp.data[0]['iniciada_em']
    except Exception as e:
        log.warning(f'  Erro ao obter sessao_betfair: {e}')
    return None"""

if content.count(OLD_REGISTRAR) != 1:
    print(f"ABORTA: ancora encontrada {content.count(OLD_REGISTRAR)}x (esperado 1)")
    sys.exit(1)

NEW_REGISTRAR = """def registrar_sessao_betfair(inicio):
    \"\"\"Registra o horario real de inicio de sessao continua na Betfair (reseta so no logout de verdade).
    Uma linha por bot_origem — cada bot mantem seu proprio registro de sessao.\"\"\"
    if not SUPABASE_ATIVO:
        return
    try:
        import os
        bot_id = os.getenv('SUPABASE_BOT_ID', 'desconhecido')
        _client.table('sessao_betfair').upsert({
            'iniciada_em': inicio.isoformat(),
            'bot_origem': bot_id,
            'atualizada_em': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        }, on_conflict='bot_origem').execute()
    except Exception as e:
        log.warning(f'  Erro ao registrar sessao_betfair: {e}')


def obter_sessao_betfair(bot_id=None):
    \"\"\"Retorna o timestamp ISO de inicio da sessao Betfair atual para o bot_id informado
    (ou o bot do proprio processo, via SUPABASE_BOT_ID, se nao informado), ou None.\"\"\"
    if not SUPABASE_ATIVO:
        return None
    try:
        import os
        alvo = bot_id or os.getenv('SUPABASE_BOT_ID', 'desconhecido')
        resp = _client.table('sessao_betfair').select('iniciada_em').eq('bot_origem', alvo).execute()
        if resp.data:
            return resp.data[0]['iniciada_em']
    except Exception as e:
        log.warning(f'  Erro ao obter sessao_betfair: {e}')
    return None"""

new_content = content.replace(OLD_REGISTRAR, NEW_REGISTRAR, 1)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{PATH}.bak_sessao_por_bot_{ts}"
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
