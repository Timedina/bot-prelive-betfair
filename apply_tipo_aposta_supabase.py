import shutil, time, sys

ARQUIVO = "supabase_integration.py"
backup = f"{ARQUIVO}.bak_tipo_aposta_{int(time.time())}"

with open(ARQUIVO, "r", encoding="utf-8") as f:
    conteudo = f.read()

ANCORA_1 = """def _validar_aposta(info: dict, res_aposta: dict) -> tuple[bool, str]:
    \"\"\"Valida se uma aposta tem todos os campos obrigatórios.\"\"\"
    if not info.get('event_id'):
        return False, 'event_id vazio'
    if not info.get('nome_jogo'):
        return False, 'nome_jogo vazio'
    if not res_aposta.get('placar_lay'):
        return False, 'placar_lay não definido'
    if not res_aposta.get('odd_lay'):
        return False, 'odd_lay não definido'
    if res_aposta.get('stake', 0) <= 0:
        return False, f'stake inválido: {res_aposta.get("stake")}'
    return True, ''"""

NOVO_1 = """def _validar_aposta(info: dict, res_aposta: dict, tipo_aposta: str = 'LAY') -> tuple[bool, str]:
    \"\"\"Valida se uma aposta tem todos os campos obrigatórios.
    tipo_aposta='LAY' (padrao, estrategia LAY Correct Score) exige placar_lay.
    tipo_aposta='BACK' (ex: Under 2.5) nao exige placar_lay, coluna fica NULL.\"\"\"
    if not info.get('event_id'):
        return False, 'event_id vazio'
    if not info.get('nome_jogo'):
        return False, 'nome_jogo vazio'
    if tipo_aposta == 'LAY' and not res_aposta.get('placar_lay'):
        return False, 'placar_lay não definido'
    if not res_aposta.get('odd_lay'):
        return False, 'odd_lay não definido'
    if res_aposta.get('stake', 0) <= 0:
        return False, f'stake inválido: {res_aposta.get("stake")}'
    return True, ''"""

count_1 = conteudo.count(ANCORA_1)
if count_1 != 1:
    print(f"ABORTADO: ancora 1 encontrada {count_1}x (esperado 1). Nada foi alterado.")
    sys.exit(1)

ANCORA_2 = """def registrar_aposta_supabase(info: dict, res_aposta: dict):
    \"\"\"Registra a aposta REAL colocada (com stake, liability, betId) na tabela `apostas`.\"\"\"
    if not SUPABASE_ATIVO:
        return
    
    # Validar antes de tentar insert
    valido, motivo = _validar_aposta(info, res_aposta)
    if not valido:
        log.warning(f'  ⚠️ APOSTA NAO VALIDADA ({info.get("nome_jogo", "?")}): {motivo}')
        return
    
    try:
        odd_lay = res_aposta.get('odd_lay') or 0
        stake = res_aposta.get('stake', 0) or 0
        liability = round(stake * (odd_lay - 1), 2) if odd_lay > 1 else 0"""

NOVO_2 = """def registrar_aposta_supabase(info: dict, res_aposta: dict, tipo_aposta: str = 'LAY'):
    \"\"\"Registra a aposta REAL/simulada colocada (com stake, liability) na tabela `apostas`.
    tipo_aposta='LAY': liability = stake*(odd-1) (perda potencial da lay), placar_lay obrigatorio.
    tipo_aposta='BACK': liability = stake (perda maxima de uma back e o proprio stake), placar_lay fica NULL.\"\"\"
    if not SUPABASE_ATIVO:
        return
    
    # Validar antes de tentar insert
    valido, motivo = _validar_aposta(info, res_aposta, tipo_aposta)
    if not valido:
        log.warning(f'  ⚠️ APOSTA NAO VALIDADA ({info.get("nome_jogo", "?")}): {motivo}')
        return
    
    try:
        odd_lay = res_aposta.get('odd_lay') or 0
        stake = res_aposta.get('stake', 0) or 0
        if tipo_aposta == 'BACK':
            liability = stake
        else:
            liability = round(stake * (odd_lay - 1), 2) if odd_lay > 1 else 0"""

count_2 = conteudo.count(ANCORA_2)
if count_2 != 1:
    print(f"ABORTADO: ancora 2 encontrada {count_2}x (esperado 1). Nada foi alterado.")
    sys.exit(1)

shutil.copy(ARQUIVO, backup)
conteudo = conteudo.replace(ANCORA_1, NOVO_1)
conteudo = conteudo.replace(ANCORA_2, NOVO_2)

with open(ARQUIVO, "w", encoding="utf-8") as f:
    f.write(conteudo)

print(f"OK - patch aplicado. Backup salvo em {backup}")
