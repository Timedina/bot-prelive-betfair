import re
import os
import time
import json
import logging
import betfair_client as bf
import saude
try:
    import resultado_jogos
    import telegram_commands
    import apostas
    APOSTAS_DISPONIVEL = True
    COMANDOS_DISPONIVEL = True
    RESULTADO_DISPONIVEL = True
except ImportError:
    RESULTADO_DISPONIVEL = False
    COMANDOS_DISPONIVEL = False
    APOSTAS_DISPONIVEL = False
from telegram_client import enviar_mensagem
from confianca import classificar_confianca, formatar_para_telegram
import supabase_integration as sb
from datetime import datetime, timezone, timedelta


# ============================================================
# CONFIGURACOES DO BOT PRE-LIVE
# ============================================================

LIQUIDEZ_MINIMA_CS_DISPONIVEL = 150   # £ disponíveis para lay nos runners 1-0 e 0-1 (soma)
LIQUIDEZ_MINIMA_CS_TOTAL      = 500   # £ totalMatched do mercado CS (usado como info)
LIQUIDEZ_MINIMA_GOALS         = 1000  # reservado para uso futuro

# Fuso horario
FUSO_BRASILIA = timezone(timedelta(hours=-3))

# Agendamento
MINUTOS_ANTES_INICIO    = 5
MINUTOS_APOS_INICIO     = 15
INTERVALO_VERIFICACAO   = 5      # minutos na janela de entrada
INTERVALO_LONGE         = 15     # minutos para jogos > 30 min antes
LIMIAR_JANELA_ENTRADA   = 30     # minutos: abaixo disso usa intervalo curto
INTERVALO_RECARGA_HORAS = 0.25
INTERVALO_RESULTADO_MIN  = 30   # minutos entre verificacoes de resultado pos-kickoff
HORA_HEARTBEAT           = 8    # hora do heartbeat diario (Brasilia)

# Filtros Correct Score
ODD_10_MINIMA = 0
ODD_10_MAXIMA = 25.0
ODD_01_MINIMA = 0
ODD_01_MAXIMA = 18.0  # reduzido apos backtest: zero derrotas ate 18.0 vs 91.9% acerto geral

# Filtros Match Odds
ODD_FAVORITO_MAX = 2.20
ODD_FAVORITO_MAX_COPA = 2.50  # limite especial para jogos da Copa do Mundo

# Filtros Over 1.5
ODD_OVER15_MINIMA = 1.10
ODD_OVER15_MAXIMA = 1.35
ODD_OVER15_MAXIMA_COPA = 1.50  # limite especial para jogos da Copa do Mundo

# Filtros Ambas Marcam (BTTS)
ODD_BTTS_MINIMA = 1.55
ODD_BTTS_MAXIMA = 2.30
ODD_BTTS_MAXIMA_COPA = 2.60  # limite especial para jogos da Copa do Mundo

# Filtro de entrada
APENAS_LAY_01 = True  # True = so entra no LAY 0-1, ignora LAY 1-0
APENAS_LAY_10 = False  # True = so entra no LAY 1-0, ignora LAY 0-1
RAZAO_ODD_MAXIMA = 1.8  # max razao odd_01/odd_10 para entrar
ODD_FAVORITO_SUSPEITO = 1.15  # abaixo disso, favorito e considerado muito forte
RAZAO_10_01_MAX_FAVORITO_FORTE = 0.75  # odd_10 deve ser <= 75% da odd_01 quando favorito for forte

# Reconexao automatica
MAX_ERROS_CONSECUTIVOS = 5
ESPERA_APOS_ERRO       = 30


def aplicar_filtros_supabase():
    """Sobrescreve as constantes de filtro com os valores configurados no Supabase
    (editaveis pelo dashboard). Se o Supabase estiver fora do ar ou um filtro nao
    existir la, mantem o valor fixo atual sem quebrar nada."""
    global ODD_10_MINIMA, ODD_10_MAXIMA, ODD_01_MINIMA, ODD_01_MAXIMA
    global ODD_FAVORITO_MAX, ODD_FAVORITO_MAX_COPA
    global ODD_OVER15_MINIMA, ODD_OVER15_MAXIMA, ODD_OVER15_MAXIMA_COPA
    global ODD_BTTS_MINIMA, ODD_BTTS_MAXIMA, ODD_BTTS_MAXIMA_COPA
    global RAZAO_ODD_MAXIMA, LIQUIDEZ_MINIMA_CS_DISPONIVEL

    f = sb.carregar_filtros()
    if not f:
        return
    ODD_10_MINIMA = f.get("ODD_10_MINIMA", ODD_10_MINIMA)
    ODD_10_MAXIMA = f.get("ODD_10_MAXIMA", ODD_10_MAXIMA)
    ODD_01_MINIMA = f.get("ODD_01_MINIMA", ODD_01_MINIMA)
    ODD_01_MAXIMA = f.get("ODD_01_MAXIMA", ODD_01_MAXIMA)
    ODD_FAVORITO_MAX = f.get("ODD_FAVORITO_MAX", ODD_FAVORITO_MAX)
    ODD_FAVORITO_MAX_COPA = f.get("ODD_FAVORITO_MAX_COPA", ODD_FAVORITO_MAX_COPA)
    ODD_OVER15_MINIMA = f.get("ODD_OVER15_MINIMA", ODD_OVER15_MINIMA)
    ODD_OVER15_MAXIMA = f.get("ODD_OVER15_MAXIMA", ODD_OVER15_MAXIMA)
    ODD_OVER15_MAXIMA_COPA = f.get("ODD_OVER15_MAXIMA_COPA", ODD_OVER15_MAXIMA_COPA)
    ODD_BTTS_MINIMA = f.get("ODD_BTTS_MINIMA", ODD_BTTS_MINIMA)
    ODD_BTTS_MAXIMA = f.get("ODD_BTTS_MAXIMA", ODD_BTTS_MAXIMA)
    ODD_BTTS_MAXIMA_COPA = f.get("ODD_BTTS_MAXIMA_COPA", ODD_BTTS_MAXIMA_COPA)
    RAZAO_ODD_MAXIMA = f.get("RAZAO_ODD_MAXIMA", RAZAO_ODD_MAXIMA)
    LIQUIDEZ_MINIMA_CS_DISPONIVEL = f.get("LIQUIDEZ_MINIMA_CS_DISPONIVEL", LIQUIDEZ_MINIMA_CS_DISPONIVEL)
    apostas.LIABILITY_FIXA = f.get("LIABILITY_FIXA", apostas.LIABILITY_FIXA)

# Tipos de mercado permitidos
MARKET_TYPES_FILTRO = ['MATCH_ODDS', 'CORRECT_SCORE', 'OVER_UNDER_15', 'BOTH_TEAMS_TO_SCORE']

# Melhoria A: Deteccao de movimento de odds
MOVIMENTO_SUBIDA_ALERTA = 0.20   # +20% na odd -> alerta "entrada melhorou"
MOVIMENTO_QUEDA_ALERTA  = 0.15   # -15% na odd -> alerta "mercado indo contra"
INTERVALO_MONITOR_ODDS  = 90     # segundos entre verificacoes pos-aprovacao

# Melhoria B: Monitoramento de saida
QUEDA_SAIDA_PERCENTUAL   = 0.20  # odd cai 20%+ -> alerta de saida
MINUTOS_MONITOR_POS_KICK = 15    # quantos minutos apos o kickoff monitorar

# IA - Analise Gemini (gratuito via Google AI Studio)
IA_ATIVA  = False                         # False para desativar sem remover o codigo
IA_MODELO = "gemini-flash-latest"  # alias sempre aponta pro modelo flash atual (2.0-flash-lite perdeu cota free tier em 31/07/2026)

# ============================================================
# LIGAS PERMITIDAS
# ============================================================
LIGAS_PERMITIDAS = []

# ============================================================
# PASTAS E LOGS
# ============================================================
PASTA_DADOS = 'dados_bot'
HORA_RESUMO_RESULTADOS = 23  # Hora para enviar resumo de resultados
PASTA_LOGS  = 'logs'
os.makedirs(PASTA_DADOS, exist_ok=True)
os.makedirs(PASTA_LOGS,  exist_ok=True)


def configurar_log():
    data_hoje = datetime.now(FUSO_BRASILIA).strftime('%Y-%m-%d')
    log_file  = os.path.join(PASTA_LOGS, f'bot_{data_hoje}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('bot')

log = configurar_log()


# ============================================================
# ARQUIVO DE PERSISTENCIA -- aprovados
# ============================================================

def arquivo_do_dia() -> str:
    data = datetime.now(FUSO_BRASILIA).strftime('%Y-%m-%d')
    return os.path.join(PASTA_DADOS, f'aprovados_{data}.json')


def carregar_aprovados_do_dia() -> dict:
    path = arquivo_do_dia()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f'Erro ao carregar aprovados: {e}')
    return {}


def arquivo_historico() -> str:
    data = datetime.now(FUSO_BRASILIA).strftime('%Y-%m-%d')
    return os.path.join(PASTA_DADOS, f'historico_{data}.json')


def salvar_historico_completo(info: dict, aprovado: bool, motivos: list = None):
    """Salva TODOS os jogos analisados com suas odds para backtest futuro."""
    path = arquivo_historico()
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                historico = json.load(f)
        else:
            historico = []

        historico.append({
            'event_id':            info.get('event_id', ''),
            'nome_jogo':           info.get('nome_jogo', ''),
            'competition':         info.get('competition', ''),
            'horario':             info.get('horario', '--:--'),
            'aprovado':            aprovado,
            'motivos':             motivos or [],
            'odd_01':              info.get('odd_01'),
            'odd_10':              info.get('odd_10'),
            'odd_favorito':        info.get('odd_favorito'),
            'odd_zebra':           info.get('odd_zebra'),
            'odd_empate':          info.get('odd_empate'),
            'favorito':            info.get('favorito', ''),
            'odd_over15':          info.get('odd_over15'),
            'odd_btts':            info.get('odd_btts'),
            'liquidez_disponivel': info.get('liquidez_disponivel', 0),
            'liquidez_total':      info.get('liquidez_total', 0),
            'minutos':             info.get('minutos', 0),
            'ia_motivo':           info.get('ia_motivo', ''),
            'analisado_em':        datetime.now(FUSO_BRASILIA).strftime('%H:%M:%S'),
        })

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(historico, f, ensure_ascii=False, indent=2)

        sb.registrar_analise_supabase(info, aprovado, motivos)
    except Exception as e:
        log.warning(f'  Erro ao salvar historico: {e}')


def salvar_aprovado(info: dict):
    aprovados = carregar_aprovados_do_dia()
    aprovados[info['event_id']] = {
        'nome_jogo':           info['nome_jogo'],
        'competition':         info.get('competition', ''),
        'horario':             info.get('horario', '--:--'),
        'odd_10':              info.get('odd_10'),
        'odd_01':              info.get('odd_01'),
        'odd_over15':          info.get('odd_over15'),
        'odd_btts':            info.get('odd_btts'),
        'odd_favorito':        info.get('odd_favorito'),
        'favorito':            info.get('favorito', ''),
        'liquidez_disponivel': info.get('liquidez_disponivel', 0),
        'liquidez_total':      info.get('liquidez_total', 0),
        'market_id_cs':        info.get('market_id_cs', ''),
        'runners_cs_map':      info.get('runners_cs_map', {}),
        'ia_motivo':           info.get('ia_motivo', ''),
        'salvo_em':            datetime.now(FUSO_BRASILIA).strftime('%H:%M:%S'),
    }
    with open(arquivo_do_dia(), 'w', encoding='utf-8') as f:
        json.dump(aprovados, f, ensure_ascii=False, indent=2)


def atualizar_aprovado_com_aposta(event_id: str, res_aposta: dict):
    """Grava no JSON do dia os dados reais da aposta (stake, odd_lay, placar_lay),
    para que resultado_jogos.py calcule o P&L corretamente depois."""
    aprovados = carregar_aprovados_do_dia()
    if event_id in aprovados:
        aprovados[event_id]['stake']      = res_aposta.get('stake')
        aprovados[event_id]['odd_lay']    = res_aposta.get('odd_lay')
        aprovados[event_id]['placar_lay'] = res_aposta.get('placar_lay')
        aprovados[event_id]['betId']      = res_aposta.get('betId')
        with open(arquivo_do_dia(), 'w', encoding='utf-8') as f:
            json.dump(aprovados, f, ensure_ascii=False, indent=2)


# ============================================================
# MELHORIA C: LOG PERSISTENTE DE REPROVACOES
# ============================================================

def arquivo_reprovados_do_dia() -> str:
    data = datetime.now(FUSO_BRASILIA).strftime('%Y-%m-%d')
    return os.path.join(PASTA_DADOS, f'reprovados_{data}.json')


def carregar_reprovados_do_dia() -> dict:
    path = arquivo_reprovados_do_dia()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f'Erro ao carregar reprovados: {e}')
    return {}


def registrar_reprovacao_persistente(event_id: str, nome_jogo: str, competition: str,
                                      horario: str, motivos: list):
    """
    Acumula cada tentativa de reprovacao no JSON do dia.
    Estrutura: { event_id: { nome_jogo, competition, horario, tentativas: [{hora, motivos}] } }
    """
    reprovados = carregar_reprovados_do_dia()
    agora_str  = datetime.now(FUSO_BRASILIA).strftime('%H:%M:%S')

    if event_id not in reprovados:
        reprovados[event_id] = {
            'nome_jogo':   nome_jogo,
            'competition': competition,
            'horario':     horario,
            'tentativas':  [],
        }

    reprovados[event_id]['tentativas'].append({
        'hora':    agora_str,
        'motivos': motivos,
    })

    try:
        with open(arquivo_reprovados_do_dia(), 'w', encoding='utf-8') as f:
            json.dump(reprovados, f, ensure_ascii=False, indent=2)
        log.info(f'  📝 Reprovacao salva: {nome_jogo} | {motivos}')
    except Exception as e:
        log.warning(f'Erro ao salvar reprovado: {e}')
        log.warning(f'  Caminho: {arquivo_reprovados_do_dia()}')


def resumo_reprovados_telegram():
    """
    Envia resumo analitico dos motivos de reprovacao do dia,
    incluindo distribuicao das odds rejeitadas para calibrar filtros.
    """
    reprovados = carregar_reprovados_do_dia()
    data_hoje  = datetime.now(FUSO_BRASILIA).strftime('%d/%m/%Y')

    if not reprovados:
        enviar_mensagem(
            f'📋 *Reprovações — {data_hoje}*\n'
            f'_Nenhuma reprovação registrada hoje._'
        )
        return

    # ── Contagem de motivos e coleta de valores para distribuição ──
    contagem: dict = {}
    total_tentativas = 0

    # Distribuições de odds rejeitadas
    dist_favorito  = []
    dist_over15    = []
    dist_btts      = []
    dist_liq       = []

    for dados in reprovados.values():
        for tent in dados['tentativas']:
            total_tentativas += 1
            for motivo in tent['motivos']:
                chave = motivo.split(':')[0].strip()
                contagem[chave] = contagem.get(chave, 0) + 1

                try:
                    valor_str = motivo.split(':')[1].strip().split()[0]
                    valor = float(valor_str.replace('£', '').replace(',', ''))
                    if 'Favorito fora faixa' in motivo:
                        dist_favorito.append(valor)
                    elif 'Over 1.5 fora faixa' in motivo:
                        dist_over15.append(valor)
                    elif 'BTTS fora faixa' in motivo:
                        dist_btts.append(valor)
                    elif 'Liquidez CS insuficiente' in motivo:
                        dist_liq.append(valor)
                except:
                    pass

    top = sorted(contagem.items(), key=lambda x: x[1], reverse=True)[:8]

    linhas = [
        f'📋 *Reprovações do Dia — {data_hoje}*',
        f'━━━━━━━━━━━━━━━━━━━━',
        f'🔍 Jogos únicos: {len(reprovados)} | 🔁 Tentativas: {total_tentativas}',
        f'━━━━━━━━━━━━━━━━━━━━',
        f'*Top motivos:*',
    ]
    for motivo, n in top:
        barra = '\u2593' * min(10, n) + '\u2591' * max(0, 10 - n)
        linhas.append(f'`{barra}` {motivo}: *{n}x*')

    if dist_favorito:
        linhas.append(f'\n━━━━━━━━━━━━━━━━━━━━')
        linhas.append(f'📊 *Distribuição — Favorito rejeitado* (limite atual: {ODD_FAVORITO_MAX})')
        faixas = [
            (0,    2.0,  'abaixo 2.0 (passou)'),
            (2.0,  2.1,  '2.00–2.10'),
            (2.1,  2.2,  '2.10–2.20'),
            (2.2,  2.5,  '2.20–2.50'),
            (2.5,  3.0,  '2.50–3.00'),
            (3.0,  99.0, 'acima 3.00'),
        ]
        for lo, hi, label in faixas:
            n = sum(1 for v in dist_favorito if lo <= v < hi)
            if n > 0:
                linhas.append(f'  `{label}`: {n}x')

    if dist_over15:
        linhas.append(f'\n📊 *Distribuição — Over 1.5 rejeitado* (faixa atual: {ODD_OVER15_MINIMA}–{ODD_OVER15_MAXIMA})')
        faixas = [
            (0,    1.15, 'abaixo 1.15'),
            (1.15, 1.35, '1.15–1.35 (passou)'),
            (1.35, 1.50, '1.35–1.50'),
            (1.50, 1.75, '1.50–1.75'),
            (1.75, 99.0, 'acima 1.75'),
        ]
        for lo, hi, label in faixas:
            n = sum(1 for v in dist_over15 if lo <= v < hi)
            if n > 0:
                linhas.append(f'  `{label}`: {n}x')

    if dist_btts:
        linhas.append(f'\n📊 *Distribuição — BTTS rejeitado* (faixa atual: {ODD_BTTS_MINIMA}–{ODD_BTTS_MAXIMA})')
        faixas = [
            (0,    1.55, 'abaixo 1.55'),
            (1.55, 2.30, '1.55–2.30 (passou)'),
            (2.30, 2.60, '2.30–2.60'),
            (2.60, 99.0, 'acima 2.60'),
        ]
        for lo, hi, label in faixas:
            n = sum(1 for v in dist_btts if lo <= v < hi)
            if n > 0:
                linhas.append(f'  `{label}`: {n}x')

    if dist_liq:
        linhas.append(f'\n📊 *Distribuição — Liquidez CS rejeitada* (mín atual: £{LIQUIDEZ_MINIMA_CS_DISPONIVEL})')
        faixas = [
            (0,   50,  '£0–50'),
            (50,  100, '£50–100'),
            (100, 150, '£100–150'),
            (150, 300, '£150–300 (passaria)'),
        ]
        for lo, hi, label in faixas:
            n = sum(1 for v in dist_liq if lo <= v < hi)
            if n > 0:
                linhas.append(f'  `{label}`: {n}x')

    linhas.append(f'\n━━━━━━━━━━━━━━━━━━━━')
    linhas.append(f'_Use estes dados para ajustar os filtros no topo do bot._')
    enviar_mensagem('\n'.join(linhas))


# ============================================================
# ESTATISTICAS DA SESSAO
# ============================================================

class Estatisticas:
    def __init__(self):
        self.jogos_analisados    = 0
        self.jogos_aprovados     = 0
        self.jogos_pulados_cache = 0
        self.chamadas_api        = 0
        self.alertas_movimento   = 0
        self.alertas_saida       = 0
        self.motivos_reprovacao: dict = {}
        self.erros_consecutivos  = 0
        self.inicio_sessao       = datetime.now(FUSO_BRASILIA)

    def registrar_reprovacao(self, motivos: list):
        self.jogos_analisados += 1
        for motivo in motivos:
            chave = motivo.split(':')[0].strip()
            self.motivos_reprovacao[chave] = self.motivos_reprovacao.get(chave, 0) + 1

    def registrar_aprovacao(self):
        self.jogos_analisados  += 1
        self.jogos_aprovados   += 1
        self.erros_consecutivos = 0

    def registrar_pulado(self):
        self.jogos_pulados_cache += 1

    def registrar_chamada_api(self, n: int = 1):
        self.chamadas_api += n

    def registrar_erro(self):
        self.erros_consecutivos += 1

    def registrar_sucesso(self):
        self.erros_consecutivos = 0

    def resumo_telegram(self) -> str:
        uptime  = datetime.now(FUSO_BRASILIA) - self.inicio_sessao
        horas   = int(uptime.total_seconds() // 3600)
        minutos = int((uptime.total_seconds() % 3600) // 60)
        reprovados  = self.jogos_analisados - self.jogos_aprovados
        top_motivos = sorted(self.motivos_reprovacao.items(), key=lambda x: x[1], reverse=True)[:3]
        motivos_str = ' | '.join([f'{m}: {n}x' for m, n in top_motivos]) or 'Nenhum'
        return (
            f'📊 *Estatísticas da Sessão*\n'
            f'━━━━━━━━━━━━━━━━━━━━\n'
            f'⏱ Uptime: {horas}h {minutos}min\n'
            f'🔍 Analisados: {self.jogos_analisados}\n'
            f'✅ Aprovados: {self.jogos_aprovados}\n'
            f'⛔ Reprovados: {reprovados}\n'
            f'⏭ Pulados (cache): {self.jogos_pulados_cache}\n'
            f'📡 Chamadas API: {self.chamadas_api}\n'
            f'💹 Alertas movimento: {self.alertas_movimento}\n'
            f'🚪 Alertas saída: {self.alertas_saida}\n'
            f'📋 Top motivos: {motivos_str}'
        )

stats = Estatisticas()


# ============================================================
# CACHE DE JOGOS DESCARTAVEIS
# ============================================================

# Motivos que bloqueiam permanentemente (estruturais)
CACHE_MOTIVOS_PERMANENTES = [
    
    'Sem Match Odds',
    'Liga nao permitida',
]
# Motivos que expiram em N minutos (filtros de odds podem mudar)
CACHE_TTL_MINUTOS = 10

class CacheEventos:
    def __init__(self):
        self._pulados: dict = {}  # {event_id: {motivo, expira_em}}
        self._carregar()

    def _path(self):
        from datetime import datetime, timezone, timedelta
        data = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d')
        return os.path.join(PASTA_DADOS, f'cache_{data}.json')

    def _carregar(self):
        try:
            import glob
            from datetime import datetime, timezone, timedelta
            hoje = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d')
            for arq in glob.glob(os.path.join(PASTA_DADOS, 'cache_*.json')):
                if hoje not in arq:
                    os.remove(arq)
            if os.path.exists(self._path()):
                with open(self._path()) as f:
                    self._pulados = json.load(f)
                log.info(f'  Cache carregado: {len(self._pulados)} eventos bloqueados')
        except:
            self._pulados = {}

    def _salvar(self):
        try:
            with open(self._path(), 'w') as f:
                json.dump(self._pulados, f)
        except:
            pass

    def _permanente(self, motivo: str) -> bool:
        return any(m in motivo for m in CACHE_MOTIVOS_PERMANENTES)

    def deve_pular(self, event_id: str) -> bool:
        if event_id not in self._pulados:
            return False
        entrada = self._pulados[event_id]
        # Suporte ao formato antigo (string simples)
        if isinstance(entrada, str):
            return True
        # Formato novo: verifica expiracao
        expira_em = entrada.get('expira_em')
        if expira_em is None:
            return True  # permanente
        from datetime import datetime, timezone
        if datetime.now(timezone.utc).isoformat() < expira_em:
            return True  # ainda dentro do TTL
        # Expirou — remove do cache
        del self._pulados[event_id]
        self._salvar()
        log.debug(f'  Cache expirado: {event_id}')
        return False

    def registrar(self, event_id: str, motivo: str, ttl_minutos: int = None):
        from datetime import datetime, timezone, timedelta
        if self._permanente(motivo):
            self._pulados[event_id] = {'motivo': motivo, 'expira_em': None}
            log.debug(f'  Cache permanente: {event_id} — {motivo}')
        else:
            ttl = ttl_minutos if ttl_minutos is not None else CACHE_TTL_MINUTOS
            expira = (datetime.now(timezone.utc) + timedelta(minutes=ttl)).isoformat()
            self._pulados[event_id] = {'motivo': motivo, 'expira_em': expira}
            log.debug(f'  Cache TTL {ttl}min: {event_id} — {motivo}')
        self._salvar()

    def total(self) -> int:
        return len(self._pulados)

cache_eventos = CacheEventos()


# ============================================================
# MELHORIA A: MONITOR DE MOVIMENTO DE ODDS
# ============================================================

class MonitorOdds:
    def __init__(self):
        self._monitorados: dict = {}

    def adicionar(self, info: dict):
        self._monitorados[info['event_id']] = {
            'nome_jogo':             info['nome_jogo'],
            'odd_10_ref':            info['odd_10'],
            'odd_01_ref':            info['odd_01'],
            'market_id_cs':          info['market_id_cs'],
            'open_date':             info.get('open_date', ''),
            'ultimo_check':          datetime.now(timezone.utc),
            'alerta_subida_enviado': False,
            'alerta_queda_enviado':  False,
        }
        log.info(f'  📡 Monitor de odds iniciado: {info["nome_jogo"]}')

    def remover(self, event_id: str):
        self._monitorados.pop(event_id, None)

    def total(self) -> int:
        return len(self._monitorados)

    def verificar_todos(self):
        agora      = datetime.now(timezone.utc)
        encerrados = []

        for event_id, dados in self._monitorados.items():
            try:
                inicio_utc = datetime.fromisoformat(dados['open_date'].replace('Z', '+00:00'))
                limite     = inicio_utc + timedelta(minutes=MINUTOS_MONITOR_POS_KICK)
                if agora > limite:
                    encerrados.append(event_id)
                    log.info(f'  📡 Monitor encerrado (tempo): {dados["nome_jogo"]}')
                    continue
            except:
                pass

            if (agora - dados['ultimo_check']).total_seconds() < INTERVALO_MONITOR_ODDS:
                continue

            try:
                stats.registrar_chamada_api()
                books = bf.listar_odds([dados['market_id_cs']], ['EX_BEST_OFFERS'])
                if not books:
                    continue

                runners = books[0].get('runners', [])
                dados['ultimo_check'] = agora

                def odd_lay_por_nome(nome_alvo):
                    for r in runners:
                        if r.get('runnerName', '') == nome_alvo:
                            return bf.get_lay(r)
                    return None

                odd_10_atual = odd_lay_por_nome('1 - 0')
                odd_01_atual = odd_lay_por_nome('0 - 1')
                if odd_10_atual is None or odd_01_atual is None:
                    continue

                ref_10 = dados['odd_10_ref']
                ref_01 = dados['odd_01_ref']

                if not dados['alerta_subida_enviado']:
                    subiu_10 = (odd_10_atual - ref_10) / ref_10 >= MOVIMENTO_SUBIDA_ALERTA
                    subiu_01 = (odd_01_atual - ref_01) / ref_01 >= MOVIMENTO_SUBIDA_ALERTA
                    if subiu_10 or subiu_01:
                        dados['alerta_subida_enviado'] = True
                        stats.alertas_movimento += 1
                        partes = []
                        if subiu_10:
                            partes.append(f'1-0: {ref_10:.2f} -> *{odd_10_atual:.2f}* '
                                          f'(+{(odd_10_atual/ref_10 - 1)*100:.0f}%)')
                        if subiu_01:
                            partes.append(f'0-1: {ref_01:.2f} -> *{odd_01_atual:.2f}* '
                                          f'(+{(odd_01_atual/ref_01 - 1)*100:.0f}%)')
                        enviar_mensagem(
                            f'💹 *ODDS EM MOVIMENTO — entrada melhorou*\n'
                            f'━━━━━━━━━━━━━━━━━━━━\n'
                            f'⚽ {dados["nome_jogo"]}\n'
                            f'📈 ' + '\n'.join(partes) + '\n'
                            f'✅ _Odd mais alta = lay mais lucrativo_'
                        )
                        log.info(f'  💹 Alerta subida: {dados["nome_jogo"]}')

                if not dados['alerta_queda_enviado']:
                    caiu_10 = (ref_10 - odd_10_atual) / ref_10 >= MOVIMENTO_QUEDA_ALERTA
                    caiu_01 = (ref_01 - odd_01_atual) / ref_01 >= MOVIMENTO_QUEDA_ALERTA
                    if caiu_10 or caiu_01:
                        dados['alerta_queda_enviado'] = True
                        stats.alertas_movimento += 1
                        partes = []
                        if caiu_10:
                            partes.append(f'1-0: {ref_10:.2f} -> *{odd_10_atual:.2f}* '
                                          f'(-{(1 - odd_10_atual/ref_10)*100:.0f}%)')
                        if caiu_01:
                            partes.append(f'0-1: {ref_01:.2f} -> *{odd_01_atual:.2f}* '
                                          f'(-{(1 - odd_01_atual/ref_01)*100:.0f}%)')
                        enviar_mensagem(
                            f'⚠️ *ODDS EM QUEDA — mercado indo contra*\n'
                            f'━━━━━━━━━━━━━━━━━━━━\n'
                            f'⚽ {dados["nome_jogo"]}\n'
                            f'📉 ' + '\n'.join(partes) + '\n'
                            f'🔎 _Acompanhe. Se continuar caindo, considere saída._'
                        )
                        log.info(f'  ⚠️ Alerta queda: {dados["nome_jogo"]}')

            except Exception as e:
                log.warning(f'  Monitor odds erro ({dados["nome_jogo"]}): {e}')

        for eid in encerrados:
            self.remover(eid)

monitor_odds = MonitorOdds()


# ============================================================
# MELHORIA B: MONITOR DE SAIDA
# ============================================================

class MonitorSaida:
    def __init__(self):
        self._monitorados: dict = {}

    def adicionar(self, info: dict):
        self._monitorados[info['event_id']] = {
            'nome_jogo':         info['nome_jogo'],
            'odd_10_ref':        info['odd_10'],
            'odd_01_ref':        info['odd_01'],
            'total_matched_ref': info.get('liquidez_total', 0),
            'market_id_cs':      info['market_id_cs'],
            'open_date':         info.get('open_date', ''),
            'ultimo_check':      datetime.now(timezone.utc),
            'alerta_enviado':    False,
        }
        log.info(f'  🚪 Monitor de saída iniciado: {info["nome_jogo"]}')

    def remover(self, event_id: str):
        self._monitorados.pop(event_id, None)

    def total(self) -> int:
        return len(self._monitorados)

    def verificar_todos(self):
        agora      = datetime.now(timezone.utc)
        encerrados = []

        for event_id, dados in self._monitorados.items():
            if dados['alerta_enviado']:
                encerrados.append(event_id)
                continue

            try:
                inicio_utc   = datetime.fromisoformat(dados['open_date'].replace('Z', '+00:00'))
                minutos_jogo = (agora - inicio_utc).total_seconds() / 60
                if minutos_jogo > MINUTOS_MONITOR_POS_KICK:
                    encerrados.append(event_id)
                    log.info(f'  🚪 Monitor saída encerrado (tempo): {dados["nome_jogo"]}')
                    continue
                if minutos_jogo < 0:
                    continue
            except:
                pass

            if (agora - dados['ultimo_check']).total_seconds() < INTERVALO_MONITOR_ODDS:
                continue

            try:
                stats.registrar_chamada_api()
                books = bf.listar_odds([dados['market_id_cs']], ['EX_BEST_OFFERS'])
                if not books:
                    continue

                book          = books[0]
                runners       = book.get('runners', [])
                total_matched = book.get('totalMatched', 0)
                dados['ultimo_check'] = agora

                def odd_lay_por_nome(nome_alvo):
                    for r in runners:
                        if r.get('runnerName', '') == nome_alvo:
                            return bf.get_lay(r)
                    return None

                odd_10_atual = odd_lay_por_nome('1 - 0')
                odd_01_atual = odd_lay_por_nome('0 - 1')
                if odd_10_atual is None or odd_01_atual is None:
                    continue

                ref_10  = dados['odd_10_ref']
                ref_01  = dados['odd_01_ref']
                ref_vol = dados['total_matched_ref']

                queda_10    = (ref_10 - odd_10_atual) / ref_10 >= QUEDA_SAIDA_PERCENTUAL
                queda_01    = (ref_01 - odd_01_atual) / ref_01 >= QUEDA_SAIDA_PERCENTUAL
                gol_provavel = ref_vol > 0 and total_matched >= ref_vol * 2

                if queda_10 or queda_01 or gol_provavel:
                    dados['alerta_enviado'] = True
                    stats.alertas_saida += 1

                    try:
                        min_jogo = int((agora - inicio_utc).total_seconds() / 60)
                    except:
                        min_jogo = '?'

                    razoes = []
                    if queda_10:
                        razoes.append(f'LAY 1-0 caiu: {ref_10:.2f} -> *{odd_10_atual:.2f}* '
                                      f'(-{(1 - odd_10_atual/ref_10)*100:.0f}%)')
                    if queda_01:
                        razoes.append(f'LAY 0-1 caiu: {ref_01:.2f} -> *{odd_01_atual:.2f}* '
                                      f'(-{(1 - odd_01_atual/ref_01)*100:.0f}%)')
                    if gol_provavel:
                        razoes.append(f'Volume CS explodiu: £{ref_vol:,.0f} -> £{total_matched:,.0f} '
                                      f'(+{(total_matched/ref_vol - 1)*100:.0f}%)')

                    enviar_mensagem(
                        f'🚨 *ALERTA DE SAÍDA*\n'
                        f'━━━━━━━━━━━━━━━━━━━━\n'
                        f'⚽ {dados["nome_jogo"]}\n'
                        f'🕐 ~{min_jogo} min de jogo\n'
                        f'━━━━━━━━━━━━━━━━━━━━\n'
                        f'🔴 ' + '\n'.join(razoes) + '\n'
                        f'━━━━━━━━━━━━━━━━━━━━\n'
                        f'⚠️ _Considere fechar o lay agora._'
                    )
                    log.info(f'  🚨 Alerta saída: {dados["nome_jogo"]} — {" | ".join(razoes)}')
                    encerrados.append(event_id)

            except Exception as e:
                log.warning(f'  Monitor saída erro ({dados["nome_jogo"]}): {e}')

        for eid in encerrados:
            self.remover(eid)

monitor_saida = MonitorSaida()


# ============================================================
# SAUDE E ALERTAS
# ============================================================

def verificar_telegram() -> bool:
    try:
        enviar_mensagem('🔧 _Verificação de saúde — Telegram OK_')
        return True
    except Exception as e:
        log.error(f'Telegram não está funcionando: {e}')
        return False


def alerta_bot_caiu(motivo: str):
    try:
        enviar_mensagem(
            f'🚨 *BOT PARADO*\n'
            f'━━━━━━━━━━━━━━━━━━━━\n'
            f'❌ Motivo: {motivo}\n'
            f'🕐 Horário: {datetime.now(FUSO_BRASILIA).strftime("%H:%M:%S")}\n'
            f'⚠️ _Reinicie o bot manualmente na VM._'
        )
    except:
        pass


# ============================================================
# FUNCOES AUXILIARES
# ============================================================

def utc_para_brasilia(open_date_str: str) -> str:
    try:
        inicio = datetime.fromisoformat(open_date_str.replace('Z', '+00:00'))
        return inicio.astimezone(FUSO_BRASILIA).strftime('%H:%M')
    except:
        return '--:--'


def tempo_para_inicio(open_date_str: str) -> float:
    try:
        inicio = datetime.fromisoformat(open_date_str.replace('Z', '+00:00'))
        return (inicio - datetime.now(timezone.utc)).total_seconds() / 60
    except:
        return 999


_ciclos_zerados_consecutivos = 0


def buscar_todos_jogos_do_dia() -> list:
    global _ciclos_zerados_consecutivos

    agora_brasilia      = datetime.now(FUSO_BRASILIA)
    inicio_dia_brasilia = agora_brasilia.replace(hour=0, minute=0, second=0, microsecond=0)
    fim_dia_brasilia    = agora_brasilia.replace(hour=23, minute=59, second=59, microsecond=0)
    inicio_utc = inicio_dia_brasilia.astimezone(timezone.utc)
    fim_utc    = fim_dia_brasilia.astimezone(timezone.utc)

    rpc = json.dumps({
        'jsonrpc': '2.0',
        'method': 'SportsAPING/v1.0/listMarketCatalogue',
        'params': {
            'filter': {
                'eventTypeIds': ['1'],
                'marketTypeCodes': ['CORRECT_SCORE'],
                'marketStartTime': {
                    'from': inicio_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'to':   fim_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                }
            },
            'maxResults': '1000',
            'marketProjection': ['COMPETITION', 'EVENT', 'MARKET_START_TIME'],
        },
        'id': 1
    })

    # A API da Betfair BR as vezes responde vazio sem erro algum (instabilidade
    # intermitente ja observada em producao). Tenta ate 3x com pequeno intervalo
    # antes de aceitar que realmente nao ha mercados nesse ciclo.
    mercados = []
    for tentativa in range(1, 4):
        stats.registrar_chamada_api()
        mercados = bf.chamar_api(rpc) or []
        if mercados:
            break
        if tentativa < 3:
            log.warning(f'  Betfair retornou 0 mercados (tentativa {tentativa}/3) — retry em 3s...')
            time.sleep(3)

    vistos = set()
    jogos  = []
    for m in mercados:
        evento = m.get('event', {})
        event_id  = evento.get('id')
        nome_jogo = evento.get('name', '')
        open_date = evento.get('openDate', '')

        if not event_id or not open_date:
            continue
        if event_id in vistos:
            continue
        if nome_jogo.lower().startswith('test'):
            continue
        vistos.add(event_id)
        jogos.append({'event': evento, 'market_id_cs': m.get('marketId', '')})

    log.info(f'  CS disponiveis na Betfair BR: {len(mercados)} mercados | {len(jogos)} jogos unicos')

    if sb and hasattr(sb, 'registrar_metrica_simples'):
        sb.registrar_metrica_simples('mercados_cs_disponiveis', len(mercados))

    if len(mercados) == 0:
        _ciclos_zerados_consecutivos += 1
        # Ciclo de recarga roda a cada ~15min -> 8 ciclos ~= 2h de instabilidade continua.
        if _ciclos_zerados_consecutivos == 8:
            enviar_mensagem(
                '⚠️ *Alerta: Betfair sem mercados de Correct Score*\n'
                '━━━━━━━━━━━━━━━━━━━━\n'
                f'Ja sao {_ciclos_zerados_consecutivos} consultas seguidas retornando 0 mercados '
                '(~2h). Pode ser instabilidade da API da Betfair BR — vale checar '
                'manualmente no app/site se os mercados de Placar Correto estao disponiveis.'
            )
    else:
        _ciclos_zerados_consecutivos = 0

    return jogos


def calcular_liquidez_disponivel_lay(runners_book: list, runners_map: dict, nomes: list) -> float:
    total = 0.0
    for runner in runners_book:
        if runners_map.get(runner['selectionId'], '') in nomes:
            for ordem in runner.get('ex', {}).get('availableToLay', []):
                total += ordem.get('size', 0)
    return total


def get_odd_runner(book_runners, runners_map, nome):
    for runner in book_runners:
        if runners_map.get(runner['selectionId'], '') == nome:
            return bf.get_lay(runner)
    return None


def get_odd_back_runner(book_runners, runners_map, nome):
    for runner in book_runners:
        if runners_map.get(runner['selectionId'], '') == nome:
            return bf.get_back(runner)
    return None


def listar_mercados_filtrado(event_id: str) -> list:
    stats.registrar_chamada_api()
    return bf.listar_mercados(event_id, tipos=MARKET_TYPES_FILTRO)


def verificar_favorito_rapido(event_id: str, mercados: list, competition: str = '') -> tuple:
    mo_mercado = next((m for m in mercados if m['marketName'] == 'Match Odds'), None)
    if not mo_mercado:
        return False, None, None, None, None, None
    stats.registrar_chamada_api()
    books = bf.listar_odds([mo_mercado['marketId']], ['EX_BEST_OFFERS'])
    if not books:
        return False, None, None, None, None, None
    book_mo         = books[0]
    runners_mo_map  = {r['selectionId']: r['runnerName'] for r in mo_mercado.get('runners', [])}
    runners_mo_book = book_mo.get('runners', [])
    odd_empate = None
    times = []
    for runner in runners_mo_book:
        back   = bf.get_back(runner)
        nome_r = runners_mo_map.get(runner['selectionId'], '')
        if nome_r == 'The Draw':
            odd_empate = back
            continue
        times.append((back, nome_r))
    odd_favorito  = None
    nome_favorito = None
    odd_zebra     = None
    times_validos = [(o, n) for o, n in times if o]
    if times_validos:
        times_validos.sort(key=lambda t: t[0])
        odd_favorito, nome_favorito = times_validos[0]
        if len(times_validos) > 1:
            odd_zebra = times_validos[1][0]
    fav_max = ODD_FAVORITO_MAX_COPA if 'World Cup' in competition else ODD_FAVORITO_MAX
    if not odd_favorito or odd_favorito > fav_max:
        return False, odd_favorito, nome_favorito, None, odd_zebra, odd_empate
    return True, odd_favorito, nome_favorito, book_mo, odd_zebra, odd_empate


def buscar_mercados_restantes_batch(cs_mercado, over15_mercado, btts_mercado) -> dict:
    ids = [cs_mercado['marketId']]
    if over15_mercado:
        ids.append(over15_mercado['marketId'])
    if btts_mercado:
        ids.append(btts_mercado['marketId'])

    stats.registrar_chamada_api()
    books = bf.listar_odds(ids, ['EX_BEST_OFFERS'])
    if not books:
        return {}
    return {b['marketId']: b for b in books}


# ============================================================
# IA: ANALISE CLAUDE
# ============================================================

def consultar_ia(info: dict) -> tuple:
    """
    Consulta Gemini Flash para validar o jogo após todos os filtros passarem.
    Retorna (aprovado: bool, motivo: str)
    Se a IA estiver indisponível, aprova por padrão para não bloquear o bot.
    Chave gratuita em: https://aistudio.google.com/apikey
    """
    import urllib.request
    import urllib.error

    prompt = f"""Você é um analista de trading esportivo especialista em lay no Betfair.
Analise este jogo pré-live e decida se vale entrar com LAY no Correct Score (1-0 e/ou 0-1).

DADOS DO JOGO:
- Jogo: {info['nome_jogo']}
- Liga: {info.get('competition', 'N/A')}
- Minutos para início: {info['minutos']}
- Favorito: {info.get('favorito', 'N/A')} @ {info.get('odd_favorito', 0):.2f}
- LAY 1-0: {info.get('odd_10', 0):.2f}
- LAY 0-1: {info.get('odd_01', 0):.2f}
- Over 1.5 Goals: {info.get('odd_over15', 'N/A')}
- Ambas Marcam (BTTS): {info.get('odd_btts', 'N/A')}
- Liquidez disponível CS: £{info.get('liquidez_disponivel', 0):.0f}
- Liquidez total CS: £{info.get('liquidez_total', 0):.0f}

CRITÉRIOS DE APROVAÇÃO:
- Favorito forte (odd baixa) indica jogo desequilibrado, bom para lay CS
- Over 1.5 baixo (1.10–1.35) indica jogo com tendência de gols, mas cuidado se muito baixo
- BTTS alto (próximo de 2.30) pode indicar risco de ambas marcarem
- Liquidez alta (>£300 disponível) = mercado saudável
- LAY 0-1 ideal entre 8–16, LAY 1-0 ideal entre 6–14
- Jogos de ligas fracas ou nomes incomuns merecem mais cautela

Responda APENAS em JSON, sem texto extra:
{{"aprovado": true/false, "motivo": "explicação em uma linha"}}"""

    import time

    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{IA_MODELO}:generateContent?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.1}
    }).encode("utf-8")

    # Espacamento minimo entre chamadas para nao estourar o limite de RPM do free tier.
    global _ia_ultima_chamada
    try:
        agora = time.monotonic()
        espera = 4.0 - (agora - _ia_ultima_chamada)
        if espera > 0:
            time.sleep(espera)
    except NameError:
        pass
    _ia_ultima_chamada = time.monotonic()

    tentativas = 3
    for tentativa in range(1, tentativas + 1):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                texto = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                texto = texto.replace("```json", "").replace("```", "").strip()
                resultado = json.loads(texto)
                saude.registrar("ia", True)
                return resultado.get("aprovado", True), resultado.get("motivo", "")

        except urllib.error.HTTPError as e:
            if e.code == 429 and tentativa < tentativas:
                espera_backoff = 5 * tentativa
                log.warning(f"  \U0001f916 IA rate-limited (429), tentativa {tentativa}/{tentativas} - aguardando {espera_backoff}s...")
                time.sleep(espera_backoff)
                continue
            motivo = f"IA indisponivel (HTTP {e.code})"
            log.warning(f"  \U0001f916 {motivo}, aprovando sem filtro IA: {e}")
            saude.registrar("ia", False, motivo)
            return True, motivo

        except json.JSONDecodeError as e:
            motivo = "IA indisponivel (resposta invalida/truncada)"
            log.warning(f"  \U0001f916 {motivo}: {e}")
            saude.registrar("ia", False, motivo)
            return True, motivo

        except Exception as e:
            motivo = f"IA indisponivel ({type(e).__name__})"
            log.warning(f"  \U0001f916 {motivo}, aprovando sem filtro IA: {e}")
            saude.registrar("ia", False, motivo)
            return True, motivo

    return True, "IA indisponivel (limite de tentativas)"


# ============================================================
# ANALISE PRINCIPAL
# ============================================================

LIGAS_EXCLUIDAS_PADROES = [
    r"\(w\)",
    r"\bwomen\b",
    r"feminin",
    r"\bu-?1[5-9]\b",
    r"\bu-?2[0-3]\b",
    r"friendl",
    r"amistos",
    r"north american leagues cup",
]

def liga_ou_categoria_excluida(nome_jogo, competition):
    texto = (str(nome_jogo or "") + " " + str(competition or "")).lower()
    for padrao in LIGAS_EXCLUIDAS_PADROES:
        if re.search(padrao, texto):
            return "Categoria excluida (padrao: " + padrao + ")"
    return None

def analisar_jogo(event_id: str, nome_jogo: str, minutos: float, market_id_cs_hint: str = '') -> dict:
    resultado = {
        'aprovado': False,
        'motivo_reprovacao': [],
        'nome_jogo': nome_jogo,
        'minutos': int(minutos),
        'event_id': event_id,
        'competition': '',
        'horario': '--:--',
        'ia_motivo': '',
    }

    if cache_eventos.deve_pular(event_id):
        resultado['motivo_reprovacao'].append('Cache: reprovado permanente')
        stats.registrar_pulado()
        return resultado

    mercados = listar_mercados_filtrado(event_id)
    if mercados is None:
        # Falha real na API (erro de rede/HTTP/rate limit) — cacheia com TTL curto
        # para nao retentar a cada poucos minutos e sobrecarregar a API da Betfair
        motivo_temp = 'Sem mercados (falha temporaria API)'
        resultado['motivo_reprovacao'].append(motivo_temp)
        log.warning(f"  Falha real na API Betfair para event_id={event_id} ({nome_jogo})")
        cache_eventos.registrar(event_id, motivo_temp)  # expira em CACHE_TTL_MINUTOS
        return resultado
    if not mercados:
        # Resposta valida da API, mas sem nenhum mercado para o evento
        # (evento sem cobertura da Betfair) — TTL bem mais longo, pois
        # nao ha motivo pra tentar de novo a cada poucos minutos
        motivo_vazio = 'Sem mercados disponiveis na Betfair'
        resultado['motivo_reprovacao'].append(motivo_vazio)
        log.warning(f"  Sem mercados disponiveis (resposta valida vazia) para event_id={event_id} ({nome_jogo}) - evento provavelmente sem cobertura")
        ttl = CACHE_TTL_MINUTOS if minutos >= 0 else 240
        cache_eventos.registrar(event_id, motivo_vazio, ttl_minutos=ttl)
        return resultado

    cs_mercado     = next((m for m in mercados if m['marketName'] == 'Correct Score'), None)
    mo_mercado     = next((m for m in mercados if m['marketName'] == 'Match Odds'), None)
    over15_mercado = next((m for m in mercados if m['marketName'] == 'Over/Under 1.5 Goals'), None)
    btts_mercado   = next((m for m in mercados if m['marketName'] == 'Both teams to Score?'), None)

    if cs_mercado:
        resultado['market_id_cs'] = cs_mercado['marketId']
        resultado['runners_cs_map'] = {str(r['selectionId']): r['runnerName'] for r in cs_mercado.get('runners', [])}
    if not cs_mercado:
        resultado['motivo_reprovacao'].append('Sem Correct Score')
        cache_eventos.registrar(event_id, 'Sem Correct Score')
        return resultado
    if not mo_mercado:
        resultado['motivo_reprovacao'].append('Sem Match Odds')
        cache_eventos.registrar(event_id, 'Sem Match Odds')
        return resultado

    competition = cs_mercado.get('competition', {}).get('name', '')
    resultado['competition'] = competition

    motivo_categoria = liga_ou_categoria_excluida(nome_jogo, competition)
    if motivo_categoria:
        resultado['motivo_reprovacao'].append(motivo_categoria)
        cache_eventos.registrar(event_id, motivo_categoria)
        return resultado

    if LIGAS_PERMITIDAS:
        if not any(liga.lower() in competition.lower() for liga in LIGAS_PERMITIDAS):
            motivo = f'Liga nao permitida: {competition}'
            resultado['motivo_reprovacao'].append(motivo)
            cache_eventos.registrar(event_id, motivo)
            return resultado

    fav_ok, odd_favorito, nome_favorito, book_mo, odd_zebra, odd_empate = verificar_favorito_rapido(event_id, mercados, competition)
    if not fav_ok:
        resultado['motivo_reprovacao'].append(f'Favorito fora faixa: {odd_favorito}')
        return resultado

    resultado['favorito']     = nome_favorito
    resultado['odd_favorito'] = odd_favorito
    resultado['odd_zebra']    = odd_zebra
    resultado['odd_empate']   = odd_empate

    books_restantes = buscar_mercados_restantes_batch(cs_mercado, over15_mercado, btts_mercado)
    if not books_restantes:
        resultado['motivo_reprovacao'].append('Sem dados de odds (batch)')
        return resultado

    book_cs = books_restantes.get(cs_mercado['marketId'])
    if not book_cs:
        resultado['motivo_reprovacao'].append('Sem dados CS')
        return resultado

    runners_cs_map  = {r['selectionId']: r['runnerName'] for r in cs_mercado.get('runners', [])}
    runners_cs_book = book_cs.get('runners', [])

    liquidez_disponivel = calcular_liquidez_disponivel_lay(
        runners_cs_book, runners_cs_map, ['1 - 0', '0 - 1']
    )
    liquidez_total = book_cs.get('totalMatched') or 0

    if liquidez_disponivel < LIQUIDEZ_MINIMA_CS_DISPONIVEL:
        status_mercado = book_cs.get('status', '?')
        resultado['motivo_reprovacao'].append(
            f'Liquidez CS insuficiente: £{liquidez_disponivel:.0f} disp. '
            f'(historico £{liquidez_total:.0f}, min £{LIQUIDEZ_MINIMA_CS_DISPONIVEL}, status={status_mercado})'
        )
        if status_mercado != 'OPEN':
            log.info(f'    Mercado CS status={status_mercado} (provavelmente suspenso temporariamente)')
        return resultado

    odd_10 = get_odd_runner(runners_cs_book, runners_cs_map, '1 - 0')
    odd_01 = get_odd_runner(runners_cs_book, runners_cs_map, '0 - 1')
    resultado['odd_10'] = odd_10
    resultado['odd_01'] = odd_01
    resultado['liquidez_disponivel'] = liquidez_disponivel
    resultado['liquidez_total'] = liquidez_total

    if not odd_01:
        resultado['motivo_reprovacao'].append('Sem odd 0-1')
        return resultado
    if not (ODD_01_MINIMA <= odd_01 <= ODD_01_MAXIMA):
        resultado['motivo_reprovacao'].append(f'Odd 0-1 fora faixa: {odd_01}')
        return resultado

    # Barra o jogo se LAY 1-0 tiver odd maior que LAY 0-1 (so entra quando 0-1 e o mais vantajoso)
    if odd_10 and odd_10 > odd_01:
        resultado['motivo_reprovacao'].append(f'LAY 1-0 com odd maior que 0-1: {odd_10} > {odd_01}')
        return resultado
    # Filtro de razao entre odds (evita desequilibrio extremo)
    if odd_10 and odd_10 > 0:
        razao = round(odd_01 / odd_10, 2)
        if razao > RAZAO_ODD_MAXIMA:
            resultado['motivo_reprovacao'].append(f'Razao odd_01/odd_10 alta: {razao} (max {RAZAO_ODD_MAXIMA})')
            return resultado

    # Filtro de sanity-check: favorito muito forte mas odd_10 nao reflete isso
    # (dados de Correct Score suspeitos/inconsistentes com o favoritismo real)
    if odd_favorito and odd_favorito <= ODD_FAVORITO_SUSPEITO and odd_10 and odd_10 > 0:
        razao_10_01 = odd_10 / odd_01
        if razao_10_01 > RAZAO_10_01_MAX_FAVORITO_FORTE:
            resultado['motivo_reprovacao'].append(
                f'Dados CS suspeitos: favorito forte (odd={odd_favorito}) mas odd_10/odd_01={razao_10_01:.2f}'
            )
            return resultado

    resultado['market_id_cs']        = cs_mercado['marketId']
    resultado['runners_cs_map']      = {str(sid): nome for sid, nome in runners_cs_map.items()}

    if over15_mercado:
        book_over15 = books_restantes.get(over15_mercado['marketId'])
        if book_over15:
            runners_over15_map = {r['selectionId']: r['runnerName'] for r in over15_mercado.get('runners', [])}
            odd_over15 = get_odd_back_runner(book_over15.get('runners', []), runners_over15_map, 'Over 1.5 Goals')
            resultado['odd_over15'] = odd_over15
            over15_max = ODD_OVER15_MAXIMA_COPA if 'World Cup' in competition else ODD_OVER15_MAXIMA
            if odd_over15 and not (ODD_OVER15_MINIMA <= odd_over15 <= over15_max):
                resultado['motivo_reprovacao'].append(f'Over 1.5 fora faixa: {odd_over15}')
                return resultado
        else:
            resultado['odd_over15'] = None
    else:
        resultado['odd_over15'] = None

    if btts_mercado:
        book_btts = books_restantes.get(btts_mercado['marketId'])
        if book_btts:
            runners_btts_map = {r['selectionId']: r['runnerName'] for r in btts_mercado.get('runners', [])}
            odd_btts = get_odd_back_runner(book_btts.get('runners', []), runners_btts_map, 'Yes')
            resultado['odd_btts'] = odd_btts
            btts_max = ODD_BTTS_MAXIMA_COPA if 'World Cup' in competition else ODD_BTTS_MAXIMA
            if odd_btts and not (ODD_BTTS_MINIMA <= odd_btts <= btts_max):
                resultado['motivo_reprovacao'].append(f'BTTS fora faixa: {odd_btts}')
                return resultado
        else:
            resultado['odd_btts'] = None
    else:
        resultado['odd_btts'] = None

    # ── Filtro IA ──────────────────────────────────────────────────
    if IA_ATIVA:
        ia_ok, ia_motivo = consultar_ia(resultado)
        resultado['ia_motivo'] = ia_motivo
        log.info(f'  🤖 IA: {"✅" if ia_ok else "⛔"} {ia_motivo}')
        if not ia_ok:
            resultado['motivo_reprovacao'].append(f'IA recusou: {ia_motivo}')
            return resultado

    # ── Auditoria de "no limite" ─────────────────────────────────
    margem = 0.10
    detalhes_limite = []
    razao_val = locals().get('razao')
    if odd_01 >= ODD_01_MAXIMA * (1 - margem):
        detalhes_limite.append(f'odd_01={odd_01} perto do teto {ODD_01_MAXIMA}')
    if odd_10 and odd_10 >= ODD_10_MAXIMA * (1 - margem):
        detalhes_limite.append(f'odd_10={odd_10} perto do teto {ODD_10_MAXIMA}')
    if razao_val is not None and razao_val >= RAZAO_ODD_MAXIMA * (1 - margem):
        detalhes_limite.append(f'razao={razao_val} perto do teto {RAZAO_ODD_MAXIMA}')
    if resultado.get('liquidez_disponivel', 0) <= LIQUIDEZ_MINIMA_CS_DISPONIVEL * (1 + margem):
        detalhes_limite.append(f'liquidez={resultado.get("liquidez_disponivel")} perto do piso {LIQUIDEZ_MINIMA_CS_DISPONIVEL}')
    resultado['no_limite'] = bool(detalhes_limite)
    resultado['no_limite_detalhes'] = '; '.join(detalhes_limite)
    from confianca import classificar_confianca
    _conf = classificar_confianca(resultado.get('minuto'), resultado.get('no_limite'))
    resultado['confianca_grupo'] = _conf.grupo
    resultado['confianca_pct'] = _conf.win_rate_pct
    resultado['aprovado'] = True

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

    return resultado


# ============================================================
# FORMATACAO
# ============================================================

def formatar_alerta(info: dict) -> str:
    over15_str = f"Over 1.5 @ *{info['odd_over15']:.2f}*" if info.get('odd_over15') else 'Over 1.5: N/A'
    btts_str   = f"Ambas Marcam @ *{info['odd_btts']:.2f}*" if info.get('odd_btts') else 'BTTS: N/A'
    minutos    = info['minutos']
    tempo_str  = f'⏰ *Inicia em:* {minutos} min' if minutos >= 0 else f'🔴 *Ao vivo:* {abs(minutos)} min de jogo'
    ia_str     = f'\n🤖 _IA: {info["ia_motivo"]}_' if info.get('ia_motivo') and info['ia_motivo'] != 'IA indisponível' else ''
    _confianca = classificar_confianca(minutos, info.get('no_limite'))
    confianca_str = formatar_para_telegram(_confianca)
    if APENAS_LAY_01:
        lays_str = f'🔴 LAY *0-1* @ {info["odd_01"]:.2f} _(filtro: apenas 0-1)_'
    elif APENAS_LAY_10:
        lays_str = f'🔴 LAY *1-0* @ {info["odd_10"]:.2f} _(filtro: apenas 1-0)_'
    else:
        lays_str = f'🔴 LAY *1-0* @ {info["odd_10"]:.2f}\n🔴 LAY *0-1* @ {info["odd_01"]:.2f}'
    return (
        f'🚨 *PRE-LIVE ALERT*\n'
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'🏆 *Liga:* {info.get("competition", "")}\n'
        f'⚽ *Jogo:* {info["nome_jogo"]}\n'
        f'{tempo_str}\n'
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'🎯 *ESTRATEGIA: LAY Correct Score*\n'
        f'{lays_str}\n'
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'📊 *FILTROS CONFIRMADOS*\n'
        f'⭐ Favorito: {info.get("favorito", "")} @ {info.get("odd_favorito", 0):.2f}\n'
        f'📈 {over15_str}\n'
        f'🤝 {btts_str}\n'
        f'💧 Liquidez disp: £{info.get("liquidez_disponivel", 0):,.0f} '
        f'| Total: £{info.get("liquidez_total", 0):,.0f}\n'
        f'━━━━━━━━━━━━━━━━━━━━\n'
        f'🆔 `{info.get("market_id_cs", "")}`\n'
        f'{confianca_str}\n'
        f'📡 _Monitorando odds e saída automaticamente_{ia_str}'
    )


def gerar_resumo_diario():
    aprovados = carregar_aprovados_do_dia()
    data_hoje = datetime.now(FUSO_BRASILIA).strftime('%d/%m/%Y')
    if not aprovados:
        enviar_mensagem(
            f'📋 *Resumo Diário — {data_hoje}*\n'
            f'━━━━━━━━━━━━━━━━━━━━\n'
            f'_Nenhum jogo aprovado até agora hoje._\n'
            f'_Os alertas serão enviados conforme os jogos forem detectados._'
        )
        return
    lista = sorted(aprovados.values(), key=lambda x: x.get('horario', ''))
    linhas = [
        f'📋 *Resumo Diário — {data_hoje}* (Horário de Brasília)',
        f'━━━━━━━━━━━━━━━━━━━━',
        f'✅ Aprovados hoje: {len(lista)}',
        f'━━━━━━━━━━━━━━━━━━━━',
    ]
    for i, info in enumerate(lista, 1):
        over15_str = f"O1.5 @ {info['odd_over15']:.2f}" if info.get('odd_over15') else 'O1.5: N/A'
        btts_str   = f"BTTS @ {info['odd_btts']:.2f}"   if info.get('odd_btts')   else 'BTTS: N/A'
        linhas += [
            f'\n*{i}. {info["nome_jogo"]}*',
            f'🏆 {info.get("competition", "")} | 🕐 {info["horario"]} | 🔔 Alertado: {info.get("salvo_em", "--")}',
            f'🔴 LAY 1-0 @ *{info["odd_10"]:.2f}* | LAY 0-1 @ *{info["odd_01"]:.2f}*',
            f'⭐ {info.get("favorito", "")} @ {info.get("odd_favorito", 0):.2f} | {over15_str} | {btts_str}',
            f'💧 CS disp: £{info.get("liquidez_disponivel", 0):,.0f} | total: £{info.get("liquidez_total", 0):,.0f}',
        ]
    linhas += ['\n━━━━━━━━━━━━━━━━━━━━', '_Odds registradas no momento do alerta pré-jogo._']
    enviar_mensagem('\n'.join(linhas))


# ============================================================
# AGENDADOR
# ============================================================

class AgendadorJogos:
    def __init__(self):
        self.jogos: dict = {}

    def carregar_jogos_do_dia(self):
        log.info('Buscando lista de jogos do dia...')
        jogos_api    = buscar_todos_jogos_do_dia()
        ja_aprovados = set(carregar_aprovados_do_dia().keys())

        if not jogos_api:
            log.warning('Nenhum jogo retornado pela API Betfair!')
            enviar_mensagem('⚠️ *Atenção* — Nenhum jogo encontrado na Betfair para hoje.\n_Pode ser erro de API ou dia sem jogos._')
            return 0

        novos = 0
        for jogo in jogos_api:
            evento    = jogo.get('event', {})
            event_id  = evento.get('id')
            nome_jogo = evento.get('name', '')
            open_date = evento.get('openDate', '')
            if not event_id or not open_date:
                continue
            if event_id in ja_aprovados or event_id in self.jogos:
                continue
            try:
                inicio_utc = datetime.fromisoformat(open_date.replace('Z', '+00:00'))
                proxima    = inicio_utc - timedelta(minutes=MINUTOS_ANTES_INICIO)
            except:
                continue
            limite = inicio_utc + timedelta(minutes=MINUTOS_APOS_INICIO)
            if datetime.now(timezone.utc) > limite:
                continue
            competition_nome = jogo.get('competition', {}).get('name', '') if isinstance(jogo.get('competition'), dict) else jogo.get('competition', '')
            self.jogos[event_id] = {
                'nome_jogo':           nome_jogo,
                'open_date':           open_date,
                'estado':              'aguardando',
                'proxima_verificacao': proxima,
                'market_id_cs':        jogo.get('market_id_cs', ''),
                'competition':         competition_nome,
            }
            if 'World Cup' in competition_nome:
                horario_br = inicio_utc.astimezone(FUSO_BRASILIA).strftime('%H:%M')
                enviar_mensagem(
                    f'🏆 *Jogo da Copa detectado!*\n'
                    f'⚽ {nome_jogo}\n'
                    f'🕐 {horario_br} (Brasília)\n'
                    f'_Monitorando para entrada..._'
                )
                log.info(f'  🏆 Copa detectada: {nome_jogo} às {horario_br}')
            novos += 1

        log.info(f'Jogos agendados: {novos} novos | Total ativo: {len(self.jogos)}')
        return novos

    def jogos_para_verificar_agora(self) -> list:
        agora = datetime.now(timezone.utc)
        return [(eid, d) for eid, d in self.jogos.items()
                if d['estado'] == 'aguardando' and d['proxima_verificacao'] <= agora]

    def avancar_verificacao(self, event_id: str):
        dados     = self.jogos[event_id]
        agora     = datetime.now(timezone.utc)
        minutos   = tempo_para_inicio(dados['open_date'])
        intervalo = INTERVALO_LONGE if minutos > LIMIAR_JANELA_ENTRADA else INTERVALO_VERIFICACAO

        try:
            inicio_utc = datetime.fromisoformat(dados['open_date'].replace('Z', '+00:00'))
        except:
            self._descartar(event_id, 'Erro ao parsear data')
            return

        limite  = inicio_utc + timedelta(minutes=MINUTOS_APOS_INICIO)
        proxima = agora + timedelta(minutes=intervalo)

        if proxima > limite:
            self._descartar(event_id, f'Janela encerrada (+{MINUTOS_APOS_INICIO} min)')
        else:
            dados['proxima_verificacao'] = proxima
            log.info(f'    -> Proxima: {proxima.astimezone(FUSO_BRASILIA).strftime("%H:%M")} '
                     f'(intervalo {intervalo} min — {int(minutos)} min p/ inicio)')

    def marcar_aprovado(self, event_id: str):
        self.jogos[event_id]['estado'] = 'aprovado'

    def _descartar(self, event_id: str, motivo: str):
        self.jogos[event_id]['estado'] = 'descartado'
        log.info(f'    Descartado: {self.jogos[event_id]["nome_jogo"]} — {motivo}')

    def limpar_encerrados(self):
        antes = len(self.jogos)
        self.jogos = {eid: d for eid, d in self.jogos.items() if d['estado'] == 'aguardando'}
        removidos = antes - len(self.jogos)
        if removidos:
            log.info(f'  Agendador: {removidos} jogos removidos da fila')
    
    def limpar_antigos(self, minutos_passado=120):
        """Remove jogos que já passaram faz >N minutos (padrão: 2h).
        Libera memória de eventos que nunca mais vão ser analisados."""
        agora = datetime.now(timezone.utc)
        antes = len(self.jogos)
        
        jogos_novos = {}
        para_limpar = []
        
        for eid, dados in self.jogos.items():
            open_date_str = dados.get('open_date', '')
            try:
                # Parse ISO format: "2026-07-04T20:30:00Z"
                if 'T' in open_date_str:
                    open_date = datetime.fromisoformat(open_date_str.replace('Z', '+00:00'))
                else:
                    continue
                
                minutos_desde = (agora - open_date).total_seconds() / 60
                
                if minutos_desde > minutos_passado:
                    para_limpar.append((dados.get('nome_jogo', '?'), minutos_desde))
                else:
                    jogos_novos[eid] = dados
            except:
                # Se der erro parsing, mantém
                jogos_novos[eid] = dados
        
        self.jogos = jogos_novos
        removidos = antes - len(self.jogos)
        
        if removidos > 0:
            log.info(f'  🧹 Cache limpo: {removidos} jogos antigos removidos (>120 min passado)')
            for nome, mins in para_limpar[:3]:  # Log só os 3 primeiros
                log.debug(f'    - {nome} ({int(mins)} min atrás)')

    def status(self) -> str:
        aguardando = sum(1 for d in self.jogos.values() if d['estado'] == 'aguardando')
        return (f'Fila: {aguardando} aguardando | '
                f'Cache: {cache_eventos.total()} bloqueados | '
                f'Monitor odds: {monitor_odds.total()} | '
                f'Monitor saida: {monitor_saida.total()}')


def imprimir_agenda_do_dia(agendador: AgendadorJogos):
    jogos = sorted(agendador.jogos.values(), key=lambda x: x['open_date'])
    log.info('=' * 55)
    log.info(f'   AGENDA DO DIA — {datetime.now(FUSO_BRASILIA).strftime("%d/%m/%Y")} | {len(jogos)} jogos')
    log.info('=' * 55)
    hora_atual = None
    for dados in jogos:
        horario = utc_para_brasilia(dados['open_date'])
        if horario[:2] != hora_atual:
            hora_atual = horario[:2]
            log.info(f'  {hora_atual}h')
        log.info(f'    {horario}  {dados["nome_jogo"]}')


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def rodar_bot():
    log.info('=' * 55)
    log.info('   BOT PRE-LIVE LAY 0x1 / 1x0')
    log.info('=' * 55)

    if not bf.login():
        alerta_bot_caiu('Falha no login Betfair')
        return

    if not verificar_telegram():
        log.error('Telegram não está respondendo. Verifique o token.')
        return

    agendador = AgendadorJogos()
    agendador.carregar_jogos_do_dia()
    imprimir_agenda_do_dia(agendador)

    ia_status = '✅ ativa' if IA_ATIVA else '⛔ desativada'
    ligas_msg = '\n'.join(f'  • {l}' for l in LIGAS_PERMITIDAS) if LIGAS_PERMITIDAS else '  • Todas as ligas'
    enviar_mensagem(
        f'🤖 *Bot Pre-Live LAY 0x1/1x0 iniciado!*\n'
        f'🏆 *Ligas:* {ligas_msg}\n'
        f'📅 *Jogos hoje:* {len(agendador.jogos)}\n'
        f'⏱ Janela: {MINUTOS_ANTES_INICIO} min antes até {MINUTOS_APOS_INICIO} min após início\n'
        f'🔄 Intervalo dinâmico: {INTERVALO_LONGE}min (longe) / {INTERVALO_VERIFICACAO}min (janela)\n'
        f'🧠 Análise IA: {ia_status}\n'
        f'📡 Monitor de odds e saída: *ativo*'
    )
    gerar_resumo_diario()

    ultima_recarga        = datetime.now(timezone.utc)
    ultimo_heartbeat      = None
    ultimo_resumo_noturno  = None
    ultimo_resultado_auto = datetime.now(timezone.utc)

    while True:
        try:
            bf.renovar_token_se_necessario()  # fix 19/08: LAY nunca chamava isso, so o Under25 -- causa provavel do bloqueio de conta perto das ~23h
            aplicar_filtros_supabase()
            # Gravar métricas a cada ciclo (função tem controle interno de 1h)
            sb.gravar_metricas_periodico()
            log.info(f'{agendador.status()} | ✅ {stats.jogos_aprovados} aprovados | '
                     f'🔍 {stats.jogos_analisados} analisados | 📡 {stats.chamadas_api} chamadas API')

            agora_utc = datetime.now(timezone.utc)
            if (agora_utc - ultima_recarga).total_seconds() >= INTERVALO_RECARGA_HORAS * 3600:
                novos = agendador.carregar_jogos_do_dia()
                ultima_recarga = agora_utc
                if novos > 0:
                    imprimir_agenda_do_dia(agendador)

            agora_br   = datetime.now(FUSO_BRASILIA)
            data_hoje  = agora_br.strftime('%Y-%m-%d')
            hora_atual = agora_br.hour
            if hora_atual >= 23 and ultimo_resumo_noturno != data_hoje:
                ultimo_resumo_noturno = data_hoje
                log.info('  📋 Enviando resumo noturno de reprovações...')
                resumo_reprovados_telegram()

            if hora_atual == HORA_HEARTBEAT and ultimo_heartbeat != data_hoje:
                ultimo_heartbeat = data_hoje
                aprovados_hoje   = carregar_aprovados_do_dia()
                agendados        = sum(1 for d in agendador.jogos.values() if d['estado'] == 'aguardando')
                vitorias_hoje    = sum(1 for i in aprovados_hoje.values() if i.get('resultado_geral') == 'VITORIA')
                derrotas_hoje    = sum(1 for i in aprovados_hoje.values() if i.get('resultado_geral') == 'PERDA')
                pendentes_hoje   = sum(1 for i in aprovados_hoje.values() if not i.get('resultado_geral'))
                pnl_hoje         = sum(i.get('pnl_estimado', 0) or 0 for i in aprovados_hoje.values())
                enviar_mensagem(
                    f'💓 *Bot ativo — Bom dia!*\n'
                    f'━━━━━━━━━━━━━━━━━━━━\n'
                    f'📅 {agora_br.strftime("%d/%m/%Y %H:%M")} (Brasília)\n'
                    f'📋 Jogos agendados hoje: *{agendados}*\n'
                    f'✅ Aprovados ontem: *{len(aprovados_hoje)}* '
                    f'({vitorias_hoje}V/{derrotas_hoje}D/{pendentes_hoje}P)\n'
                    f'⏱ Uptime: {stats.resumo_telegram().split(chr(10))[2]}'
                )
                log.info('  💓 Heartbeat enviado')

            mins_desde_resultado = (agora_utc - ultimo_resultado_auto).total_seconds() / 60
            if mins_desde_resultado >= INTERVALO_RESULTADO_MIN and RESULTADO_DISPONIVEL:
                ultimo_resultado_auto = agora_utc
                try:
                    aprovados_por_dia = resultado_jogos.atualizar_resultados_pendentes(dias_atras=14, verbose=False)
                    aprovados_agora = {}
                    for _dia, _info_dia in aprovados_por_dia.items():
                        for _eid, _info in _info_dia.items():
                            _info.setdefault('event_id', _eid)
                        aprovados_agora.update(_info_dia)
                    if aprovados_agora:
                        novos_resultados = [
                            info for info in aprovados_agora.values()
                            if info.get('resultado_geral')
                            and info.get('placar_final') != 'Indisponivel'
                            and not info.get('_telegram_enviado')
                        ]
                        for info in novos_resultados:
                            result  = info.get('resultado_geral', '')
                            emoji   = '✅' if result == 'VITORIA' else '❌'
                            pnl     = info.get('pnl_estimado', 0) or 0
                            placar  = info.get('placar_final', '?')
                            lay     = info.get('placar_lay', '')
                            odd_lay = info.get('odd_lay', 0)
                            fonte   = info.get('fonte_placar', '')
                            aviso   = '\n⚠️ _Placar via fallback — verifique manualmente_' if fonte == 'fallback' else ''
                            enviar_mensagem(
                                f'{emoji} *RESULTADO FINAL*\n'
                                f'━━━━━━━━━━━━━━━━━━━━\n'
                                f'⚽ {info["nome_jogo"]}\n'
                                f'🏁 Placar: *{placar}*\n'
                                f'🔴 LAY {lay} @ {odd_lay}\n'
                                f'💰 PnL: *{("+" if pnl >= 0 else "")}{pnl}u*\n'
                                f'━━━━━━━━━━━━━━━━━━━━\n'
                                f'📊 {resultado_jogos.resumo_resultados()}{aviso}'
                            )
                            info['_telegram_enviado'] = True
                            log.info(f'  {emoji} Resultado auto: {info["nome_jogo"]} | {placar} | {result}')
                            sb.atualizar_resultado_aposta_supabase(
                                event_id=info.get('event_id', ''),
                                resultado_geral=result,
                                placar_final=placar,
                                pnl=pnl
                            )

                        if novos_resultados:
                            resultado_jogos.salvar_aprovados(aprovados_agora)
                        stats.alertas_movimento += len(novos_resultados)
                except Exception as e:
                    log.warning(f'  Resultado auto erro: {e}')

            if COMANDOS_DISPONIVEL:
                try:
                    telegram_commands.processar_comandos(
                        agendador=agendador,
                        stats=stats,
                        resultado_jogos=resultado_jogos,
                        carregar_aprovados_do_dia=carregar_aprovados_do_dia,
                        carregar_reprovados_do_dia=carregar_reprovados_do_dia,
                        FUSO_BRASILIA=FUSO_BRASILIA,
                        ODD_10_MINIMA=ODD_10_MINIMA,
                        ODD_10_MAXIMA=ODD_10_MAXIMA,
                        ODD_01_MINIMA=ODD_01_MINIMA,
                        ODD_01_MAXIMA=ODD_01_MAXIMA,
                        ODD_FAVORITO_MAX=ODD_FAVORITO_MAX,
                        ODD_OVER15_MINIMA=ODD_OVER15_MINIMA,
                        ODD_OVER15_MAXIMA=ODD_OVER15_MAXIMA,
                        ODD_BTTS_MINIMA=ODD_BTTS_MINIMA,
                        ODD_BTTS_MAXIMA=ODD_BTTS_MAXIMA,
                        LIQUIDEZ_MINIMA_CS_DISPONIVEL=LIQUIDEZ_MINIMA_CS_DISPONIVEL,
                        LIQUIDEZ_MINIMA_CS_TOTAL=LIQUIDEZ_MINIMA_CS_TOTAL,
                    )
                except Exception as e:
                    log.warning(f'  Comandos Telegram erro: {e}')

            if monitor_odds.total() > 0:
                monitor_odds.verificar_todos()
            if monitor_saida.total() > 0:
                monitor_saida.verificar_todos()

            para_verificar = agendador.jogos_para_verificar_agora()

            if not para_verificar:
                proximas = [d['proxima_verificacao'] for d in agendador.jogos.values()
                            if d['estado'] == 'aguardando']
                if proximas:
                    prox   = min(proximas)
                    espera = max(10, min(60, (prox - datetime.now(timezone.utc)).total_seconds()))
                    log.info(f'  Proxima: {prox.astimezone(FUSO_BRASILIA).strftime("%H:%M")} — aguardando {int(espera)}s')
                    time.sleep(espera)
                else:
                    log.info('  Sem jogos na fila. Aguardando 60s...')
                    time.sleep(60)
                continue

            for event_id, dados in para_verificar:
                nome_jogo = dados['nome_jogo']
                minutos   = tempo_para_inicio(dados['open_date'])
                horario   = utc_para_brasilia(dados['open_date'])

                log.info(f'  🔍 {nome_jogo} ({horario}) | {int(minutos):+d} min')
                market_id_cs_hint = dados.get('market_id_cs', '')
                info = analisar_jogo(event_id, nome_jogo, minutos, market_id_cs_hint)

                if info['aprovado']:
                    info['horario']   = horario
                    info['open_date'] = dados['open_date']

                    log.info(f'  ✅ APROVADO! {info.get("competition", "")} | {info["nome_jogo"]} | '
                             f'1-0@{info["odd_10"]:.2f} | 0-1@{info["odd_01"]:.2f} | '
                             f'Fav@{info["odd_favorito"]:.2f} | IA: {info.get("ia_motivo", "N/A")}')

                    enviar_mensagem(formatar_alerta(info))
                    salvar_aprovado(info)
                    salvar_historico_completo(info, aprovado=True)
                    agendador.marcar_aprovado(event_id)
                    stats.registrar_aprovacao()

                    if APOSTAS_DISPONIVEL:
                        try:
                            res_aposta = apostas.apostar_jogo_aprovado(info)
                            sim_tag = " *(SIMULACAO)*" if res_aposta.get("simulado") else ""
                            if res_aposta.get("status") == "SUCCESS":
                                stake_real = res_aposta.get("stake", apostas.STAKE_LAY)
                                liability  = round(stake_real * (res_aposta["odd_lay"] - 1), 2)
                                enviar_mensagem(
                                    f"🎰 *APOSTA COLOCADA{sim_tag}*\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"⚽ " + info["nome_jogo"] + "\n"
                                    "🔴 LAY " + str(res_aposta["placar_lay"]) + " @ " + str(res_aposta["odd_lay"]) + "\n"
                                    "💰 Stake: £" + f"{stake_real:.2f}" + " | Liability: £" + f"{liability:.2f}" + "\n"
                                    "🆔 betId: `" + str(res_aposta["betId"]) + "`"
                                )
                                sb.registrar_aposta_supabase(info, res_aposta)
                                atualizar_aprovado_com_aposta(event_id, res_aposta)
                            else:
                                enviar_mensagem(
                                    f"⚠️ *APOSTA FALHOU{sim_tag}*\n"
                                    "⚽ " + info["nome_jogo"] + "\n"
                                    "❌ Motivo: " + str(res_aposta.get("motivo", "?")) + "\n"
                                    f"_Coloque manualmente._"
                                )
                        except Exception as e:
                            log.error(f"  Aposta auto erro: {e}")

                    monitor_odds.adicionar(info)
                    monitor_saida.adicionar(info)

                else:
                    motivos = info['motivo_reprovacao']
                    log.info(f'  ⛔ {" | ".join(motivos)}')

                    if not any('Cache' in m for m in motivos):
                        registrar_reprovacao_persistente(
                            event_id=event_id,
                            nome_jogo=nome_jogo,
                            competition=info.get('competition', ''),
                            horario=horario,
                            motivos=motivos,
                        )
                        salvar_historico_completo(info, aprovado=False, motivos=motivos)
                    agendador.avancar_verificacao(event_id)

                    stats.registrar_reprovacao(motivos)

            agendador.limpar_encerrados()
            stats.registrar_sucesso()

        except KeyboardInterrupt:
            log.info('Bot encerrado pelo usuário.')
            resumo_reprovados_telegram()
            enviar_mensagem(f'🛑 *Bot encerrado.*\n{stats.resumo_telegram()}')
            break

        except Exception as e:
            stats.registrar_erro()
            log.error(f'Erro ({stats.erros_consecutivos}/{MAX_ERROS_CONSECUTIVOS}): {e}')
            if stats.erros_consecutivos >= MAX_ERROS_CONSECUTIVOS:
                alerta_bot_caiu(f'Muitos erros seguidos: {e}')
                break
            time.sleep(ESPERA_APOS_ERRO)
            bf.login()


if __name__ == '__main__':
    rodar_bot()
