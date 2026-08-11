# ============================================================
# INTEGRACAO SUPABASE (opcional, nao quebra o bot se falhar)
# ============================================================
import os
import logging
import telegram_client as tg
import saude

log = logging.getLogger('bot')

SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
SUPABASE_BOT_ID = os.getenv('SUPABASE_BOT_ID', '')

_client = None
SUPABASE_ATIVO = False

if SUPABASE_URL and SUPABASE_KEY and SUPABASE_BOT_ID:
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        SUPABASE_ATIVO = True
    except Exception as e:
        logging.getLogger('bot').warning(f'  Supabase indisponivel (rodando so com JSON local): {e}')
else:
    logging.getLogger('bot').info('  Supabase nao configurado no .env - rodando so com JSON local')




def _validar_analise(info: dict) -> tuple[bool, str]:
    """Valida se uma análise tem todos os campos obrigatórios.
    Retorna (é_válida, motivo_se_inválida)."""
    if not info.get('event_id'):
        return False, 'event_id vazio'
    if not info.get('nome_jogo'):
        return False, 'nome_jogo vazio'
    # runners_cs_map pode ser vazio no início, é preenchido depois
    return True, ''


def _validar_aposta(info: dict, res_aposta: dict) -> tuple[bool, str]:
    """Valida se uma aposta tem todos os campos obrigatórios."""
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
    return True, ''


def registrar_analise_supabase(info: dict, aprovado: bool, motivos: list = None):
    """Espelha o que salvar_historico_completo grava localmente, na tabela `analises`."""
    if not SUPABASE_ATIVO:
        return
    
    # Validar antes de tentar insert
    valido, motivo = _validar_analise(info)
    if not valido:
        log.warning(f'  ⚠️ ANALISE NAO VALIDADA ({info.get("nome_jogo", "?")}): {motivo}')
        return
    
    # Checar circuit breaker
    if not _circuit_breaker.pode_tentar():
        log.debug(f'  ⏭️  Circuit breaker ABERTO — pulando insert de {info.get("nome_jogo", "?")}')
        return
    
    try:
        _client.table('analises').insert({
            'bot_id':              SUPABASE_BOT_ID,
            'event_id':            info.get('event_id', ''),
            'nome_jogo':           info.get('nome_jogo', ''),
            'competition':         info.get('competition', ''),
            'horario':             info.get('horario', '--:--'),
            'aprovado':            aprovado,
            'motivos':             motivos or [],
            'odd_favorito':        info.get('odd_favorito'),
            'odd_zebra':           info.get('odd_zebra'),
            'odd_empate':          info.get('odd_empate'),
            'nome_favorito':       info.get('favorito', ''),
            'odd_01':              info.get('odd_01'),
            'odd_10':              info.get('odd_10'),
            'odd_over15':          info.get('odd_over15'),
            'odd_btts':            info.get('odd_btts'),
            'liquidez_disponivel': info.get('liquidez_disponivel', 0),
            'liquidez_total':      info.get('liquidez_total', 0),
            'minuto':              info.get('minuto') or info.get('minutos'),
            'ia_motivo':           info.get('ia_motivo', ''),
            'market_id_cs':        info.get('market_id_cs', ''),
            'runners_cs_map':      info.get('runners_cs_map', {}),
            'no_limite':           info.get('no_limite', False),
            'no_limite_detalhes':  info.get('no_limite_detalhes', ''),
            'sombra_razao_estreita': info.get('sombra_razao_estreita'),
            'sombra_odd01_min25': info.get('sombra_odd01_min25'),
            'sombra_odd01_min30': info.get('sombra_odd01_min30'),
            'sombra_favorito_1_9_2_1': info.get('sombra_favorito_1_9_2_1'),
        }).execute()
    except Exception as e:
        _circuit_breaker.registrar_falha()
        saude.registrar("supabase", False, str(e))
        log.warning(f'  Erro ao gravar analise no Supabase: {e}')
        try:
            erro_dict = e.response.json() if hasattr(e, 'response') else {'message': str(e)}
        except:
            erro_dict = {'message': str(e)}
        # Só alerta se for erro crítico (não alerta se circuit tá aberto)
        if _circuit_breaker.estado == 'FECHADO':
            tg.alerta_erro_supabase('INSERT', 'analises', erro_dict, 
                                     f"Jogo: {info.get('nome_jogo', '?')}")
    else:
        _circuit_breaker.registrar_sucesso()
        saude.registrar("supabase", True)


def registrar_aposta_supabase(info: dict, res_aposta: dict):
    """Registra a aposta REAL colocada (com stake, liability, betId) na tabela `apostas`."""
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
        liability = round(stake * (odd_lay - 1), 2) if odd_lay > 1 else 0
        # odd_matched so tem valor real em apostas nao-simuladas (avgPrice=0 sempre em simulacao)
        avg_price = res_aposta.get('avgPrice') or 0
        odd_matched = avg_price if (not res_aposta.get('simulado', True) and avg_price > 0) else None

        _client.table('apostas').insert({
            'bot_id':       SUPABASE_BOT_ID,
            'event_id':     info.get('event_id', ''),
            'nome_jogo':    info.get('nome_jogo', ''),
            'competition':  info.get('competition', ''),
            'placar_lay':   res_aposta.get('placar_lay'),
            'odd_lay':      odd_lay,
            'odd_matched':  odd_matched,
            'stake':        stake,
            'liability':    liability,
            'market_id':    info.get('market_id_cs', ''),
            'bet_id':       str(res_aposta.get('betId', '')),
            'simulado':     res_aposta.get('simulado', True),
            'status':       'PENDENTE',
        }).execute()
        saude.registrar("supabase", True)
    except Exception as e:
        log.warning(f'  Erro ao gravar aposta no Supabase: {e}')
        saude.registrar("supabase", False, str(e))
        try:
            erro_dict = e.response.json() if hasattr(e, 'response') else {'message': str(e)}
        except:
            erro_dict = {'message': str(e)}
        tg.alerta_erro_supabase('INSERT', 'apostas', erro_dict, 
                                 f"Jogo: {info.get('nome_jogo', '?')}")


def atualizar_resultado_aposta_supabase(event_id: str, resultado_geral: str, placar_final: str, pnl: float):
    """Atualiza uma aposta existente com o resultado final (VITORIA/PERDA) e o PnL."""
    if not SUPABASE_ATIVO:
        return
    if not resultado_geral:
        log.info(f'  Resultado ainda indeterminado para event_id={event_id} (placar: {placar_final}) — mantendo PENDENTE')
        return
    try:
        status = 'VITORIA' if resultado_geral == 'VITORIA' else 'PERDA'
        _client.table('apostas').update({
            'status':       status,
            'placar_final': placar_final,
            'pnl':          pnl,
            'resolvido_em': 'now()',
        }).eq('bot_id', SUPABASE_BOT_ID).eq('event_id', str(event_id)).eq('status', 'PENDENTE').execute()
        saude.registrar("supabase", True)
    except Exception as e:
        log.warning(f'  Erro ao atualizar resultado no Supabase: {e}')
        saude.registrar("supabase", False, str(e))
        try:
            erro_dict = e.response.json() if hasattr(e, 'response') else {'message': str(e)}
        except:
            erro_dict = {'message': str(e)}
        tg.alerta_erro_supabase('UPDATE', 'apostas', erro_dict, 
                                 f"Event ID: {event_id}")
# ============================================================
# FILTROS DINAMICOS (lidos do Supabase, editaveis pelo dashboard)
# ============================================================
import time

_filtros_cache = {}
_filtros_cache_em = 0
FILTROS_TTL_SEGUNDOS = 300  # recarrega no maximo a cada 5 minutos


def carregar_filtros() -> dict:
    """Busca os filtros configurados na tabela `filtros` do Supabase, com cache de 5 min.
    Retorna dict tipo {'ODD_01_MAXIMA': 18.0, 'ODD_FAVORITO_MAX_COPA': 2.5, ...}.
    Se o Supabase estiver fora do ar, retorna o que tiver em cache (ou {} se nunca carregou)."""
    global _filtros_cache, _filtros_cache_em
    agora = time.time()
    if _filtros_cache and (agora - _filtros_cache_em) < FILTROS_TTL_SEGUNDOS:
        return _filtros_cache
    if not SUPABASE_ATIVO:
        return _filtros_cache
    try:
        bot_id_atual = os.getenv('SUPABASE_BOT_ID_OVERRIDE', os.getenv('SUPABASE_BOT_ID', SUPABASE_BOT_ID))
        resp = (
            _client.table('filtros')
            .select('chave,valor,valor_copa,valor_texto')
            .eq('bot_id', bot_id_atual)
            .execute()
        )
        novo = {}
        for row in resp.data:
            if row.get("valor") is not None:
                novo[row["chave"]] = float(row["valor"])
            elif row.get("valor_texto") is not None:
                novo[row["chave"]] = row["valor_texto"]
            if row.get('valor_copa') is not None:
                novo[row['chave'] + '_COPA'] = float(row['valor_copa'])
        _filtros_cache = novo
        _filtros_cache_em = agora
    except Exception as e:
        log.warning(f'  Erro ao carregar filtros do Supabase (mantendo valores atuais): {e}')
        try:
            erro_dict = e.response.json() if hasattr(e, 'response') else {'message': str(e)}
        except:
            erro_dict = {'message': str(e)}
        # Só alerta se for erro crítico (PGRST204), não pra timeouts normais
        if 'PGRST' in str(erro_dict):
            tg.alerta_erro_supabase('SELECT', 'filtros', erro_dict)
    return _filtros_cache


# Health check do Supabase (detecta PGRST204 cedo)
_ultima_verificacao_saude = 0
_intervalo_verificacao_saude = 300  # a cada 5 minutos




# ============================================================
# CIRCUIT BREAKER (evita travamento se Supabase cair)
# ============================================================
import time

class CircuitBreaker:
    """Circuit breaker pra Supabase — evita spam de requisições se tiver down."""
    def __init__(self, threshold=5, timeout=60):
        self.falhas_consecutivas = 0
        self.threshold = threshold  # Quantas falhas antes de "abrir" o circuito
        self.timeout = timeout      # Segundos pra tentar reconectar
        self.ultima_tentativa = 0
        self.estado = 'FECHADO'     # FECHADO (ok), ABERTO (falhas), SEMI_ABERTO (testando)
    
    def registrar_falha(self):
        """Registra uma falha de Supabase."""
        self.falhas_consecutivas += 1
        if self.falhas_consecutivas >= self.threshold:
            self.estado = 'ABERTO'
            self.ultima_tentativa = time.time()
            log.warning(f'  🔴 CIRCUIT BREAKER ABERTO: Supabase pode estar fora')
    
    def registrar_sucesso(self):
        """Registra sucesso — reseta contador."""
        self.falhas_consecutivas = 0
        if self.estado != 'FECHADO':
            self.estado = 'FECHADO'
            log.info(f'  🟢 CIRCUIT BREAKER FECHADO: Supabase voltou online')
    
    def pode_tentar(self) -> bool:
        """Verifica se deve tentar conexão com Supabase."""
        if self.estado == 'FECHADO':
            return True
        
        if self.estado == 'ABERTO':
            # Tenta reconectar após timeout
            agora = time.time()
            if (agora - self.ultima_tentativa) >= self.timeout:
                self.estado = 'SEMI_ABERTO'
                return True  # Tenta uma vez
            return False  # Ainda esperando timeout
        
        # SEMI_ABERTO — tenta uma requisição pra testar
        return True

_circuit_breaker = CircuitBreaker(threshold=5, timeout=300)  # 5 falhas = abre, 5 min pra retry


def verificar_saude_supabase() -> bool:
    """Verifica se o schema do Supabase está acessível (detecta PGRST204 cedo).
    Retorna True se OK, False se há problema crítico."""
    global _ultima_verificacao_saude
    import time
    
    if not SUPABASE_ATIVO:
        return True
    
    agora = time.time()
    if (agora - _ultima_verificacao_saude) < _intervalo_verificacao_saude:
        return True  # Já verificamos recentemente
    
    _ultima_verificacao_saude = agora
    
    try:
        # Faz um SELECT leve na tabela analises pra testar acesso ao schema
        resp = _client.table('analises').select('id').limit(1).execute()
        saude.registrar("supabase", True)
        log.debug('  ✅ Saude Supabase: OK')
        return True
    except Exception as e:
        log.warning(f'  ⚠️ Saude Supabase: {e}')
        saude.registrar("supabase", False, str(e))
        try:
            erro_dict = e.response.json() if hasattr(e, 'response') else {'message': str(e)}
        except:
            erro_dict = {'message': str(e)}
        
        # Só alerta se for erro crítico (PGRST204 = schema)
        if erro_dict.get('code') == 'PGRST204':
            tg.alerta_erro_supabase('SELECT (health check)', 'analises', erro_dict, 
                                     'Schema desincronizado — execute NOTIFY pgrst no painel Supabase!')
            return False
        # Erros transitórios (connection, timeout) ignoramos
        return True


# ============================================================
# METRICAS (coleta de dados pra observabilidade)
# ============================================================
import json
from datetime import datetime, timezone

_metricas_buffer = {
    'aprovacoes_por_hora': {},
    'reprovacoes_por_motivo': {},
    'tentativas_insert': {'sucesso': 0, 'falha': 0},
    'latencias': [],
}


def registrar_metrica_aprovacao(hora: str):
    """Registra uma aprovação pra taxa de aprovação por hora."""
    global _metricas_buffer
    if hora not in _metricas_buffer['aprovacoes_por_hora']:
        _metricas_buffer['aprovacoes_por_hora'][hora] = 0
    _metricas_buffer['aprovacoes_por_hora'][hora] += 1


def registrar_metrica_reprovacao(motivo: str):
    """Registra uma reprovação por motivo."""
    global _metricas_buffer
    # Simplificar motivo pra agrupar similar
    motivo_chave = motivo.split('|')[0].strip() if '|' in motivo else motivo[:30]
    if motivo_chave not in _metricas_buffer['reprovacoes_por_motivo']:
        _metricas_buffer['reprovacoes_por_motivo'][motivo_chave] = 0
    _metricas_buffer['reprovacoes_por_motivo'][motivo_chave] += 1


def registrar_metrica_insert(sucesso: bool):
    """Registra tentativa de insert no Supabase."""
    global _metricas_buffer
    if sucesso:
        _metricas_buffer['tentativas_insert']['sucesso'] += 1
    else:
        _metricas_buffer['tentativas_insert']['falha'] += 1


def registrar_metrica_latencia(ms: float):
    """Registra latência de uma operação (em ms)."""
    global _metricas_buffer
    _metricas_buffer['latencias'].append(ms)


def registrar_metrica_simples(tipo_metrica: str, valor: float, detalhes: dict = None):
    """Grava uma metrica avulsa direto no Supabase (sem passar pelo buffer horario)."""
    if not SUPABASE_ATIVO:
        return
    try:
        _client.table('metricas').insert({
            'bot_id': SUPABASE_BOT_ID,
            'tipo_metrica': tipo_metrica,
            'valor': float(valor),
            'detalhes': detalhes or {},
        }).execute()
    except Exception as e:
        log.warning(f'  Erro ao gravar metrica simples ({tipo_metrica}) no Supabase: {e}')


def gravar_metricas_periodico():
    """Grava métricas coletadas no buffer pro Supabase (deve rodar a cada 1h)."""
    global _metricas_buffer
    
    if not SUPABASE_ATIVO:
        return
    
    try:
        agora = datetime.now(timezone.utc).strftime('%H:00')
        
        # Taxa de aprovação pra essa hora
        aprovacoes = _metricas_buffer['aprovacoes_por_hora'].get(agora, 0)
        _client.table('metricas').insert({
            'bot_id': SUPABASE_BOT_ID,
            'tipo_metrica': 'taxa_aprovacao',
            'valor': float(aprovacoes),
            'detalhes': {'hora': agora},
        }).execute()
        
        # Distribuição de reprovações
        for motivo, count in _metricas_buffer['reprovacoes_por_motivo'].items():
            _client.table('metricas').insert({
                'bot_id': SUPABASE_BOT_ID,
                'tipo_metrica': 'reprovacao_motivo',
                'valor': float(count),
                'detalhes': {'motivo': motivo},
            }).execute()
        
        # Taxa de sucesso de insert no Supabase
        total_insert = (_metricas_buffer['tentativas_insert']['sucesso'] + 
                       _metricas_buffer['tentativas_insert']['falha'])
        if total_insert > 0:
            taxa = (_metricas_buffer['tentativas_insert']['sucesso'] / total_insert) * 100
            _client.table('metricas').insert({
                'bot_id': SUPABASE_BOT_ID,
                'tipo_metrica': 'taxa_sucesso_insert',
                'valor': taxa,
                'detalhes': _metricas_buffer['tentativas_insert'],
            }).execute()
        
        # Latência média
        if _metricas_buffer['latencias']:
            latencia_media = sum(_metricas_buffer['latencias']) / len(_metricas_buffer['latencias'])
            latencia_max = max(_metricas_buffer['latencias'])
            _client.table('metricas').insert({
                'bot_id': SUPABASE_BOT_ID,
                'tipo_metrica': 'latencia_media',
                'valor': latencia_media,
                'detalhes': {'max': latencia_max, 'amostras': len(_metricas_buffer['latencias'])},
            }).execute()
        
        # Limpar buffer
        _metricas_buffer = {
            'aprovacoes_por_hora': {},
            'reprovacoes_por_motivo': {},
            'tentativas_insert': {'sucesso': 0, 'falha': 0},
            'latencias': [],
        }
        
        log.info('  📊 Métricas gravadas no Supabase')
        
    except Exception as e:
        log.warning(f'  Erro ao gravar métricas: {e}')


# ============================================================
# ANALISE POR COMPETICAO (relatórios de performance por liga)
# ============================================================

def gerar_relatorio_competicoes() -> dict:
    """Gera relatório consolidado de P&L, aprovação e motivos por competição."""
    if not SUPABASE_ATIVO:
        return {}
    
    try:
        relatorio = {}
        
        # 1. Buscar todas as apostas aprovadas (VITORIA/PERDA)
        resp_apostas = _client.table('apostas').select(
            'competition,status,pnl,placar_final'
        ).eq('bot_id', SUPABASE_BOT_ID).in_('status', ['VITORIA', 'PERDA']).execute()
        
        # Agrupar por competição
        for aposta in resp_apostas.data:
            comp = aposta.get('competition', 'Desconhecida')
            if comp not in relatorio:
                relatorio[comp] = {
                    'vitorias': 0,
                    'derrotas': 0,
                    'pnl_total': 0.0,
                    'taxa_aprovacao': 0,
                    'motivos_top': {},
                }
            
            if aposta.get('status') == 'VITORIA':
                relatorio[comp]['vitorias'] += 1
            else:
                relatorio[comp]['derrotas'] += 1
            
            relatorio[comp]['pnl_total'] += float(aposta.get('pnl') or 0)
        
        # 2. Buscar taxa de aprovação por competição
        resp_analises = _client.table('analises').select(
            'competition,aprovado,motivos'
        ).eq('bot_id', SUPABASE_BOT_ID).execute()
        
        analises_por_comp = {}
        for analise in resp_analises.data:
            comp = analise.get('competition', 'Desconhecida')
            if comp not in analises_por_comp:
                analises_por_comp[comp] = {'total': 0, 'aprovadas': 0, 'motivos': {}}
            
            analises_por_comp[comp]['total'] += 1
            if analise.get('aprovado'):
                analises_por_comp[comp]['aprovadas'] += 1
            else:
                # Agrupa motivos
                motivos = analise.get('motivos', [])
                if motivos:
                    motivo_principal = motivos[0][:30] if motivos else 'Desconhecido'
                    analises_por_comp[comp]['motivos'][motivo_principal] = \
                        analises_por_comp[comp]['motivos'].get(motivo_principal, 0) + 1
        
        # Combinar dados
        for comp in analises_por_comp:
            if comp not in relatorio:
                relatorio[comp] = {
                    'vitorias': 0,
                    'derrotas': 0,
                    'pnl_total': 0.0,
                    'taxa_aprovacao': 0,
                    'motivos_top': {},
                }
            
            total = analises_por_comp[comp]['total']
            aprovadas = analises_por_comp[comp]['aprovadas']
            relatorio[comp]['taxa_aprovacao'] = round((aprovadas / total * 100) if total > 0 else 0, 1)
            relatorio[comp]['motivos_top'] = dict(sorted(
                analises_por_comp[comp]['motivos'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:3])  # Top 3 motivos
        
        return relatorio
    
    except Exception as e:
        log.warning(f'  Erro ao gerar relatório de competições: {e}')
        return {}


def formatar_relatorio_telegram(relatorio: dict) -> str:
    """Formata relatório pra enviar no Telegram."""
    if not relatorio:
        return '📊 Nenhum dado de competição disponível ainda.'
    
    msg = '📊 *RELATÓRIO POR COMPETIÇÃO*\n'
    msg += '━━━━━━━━━━━━━━━━━━━━\n'
    
    for comp in sorted(relatorio.keys()):
        dados = relatorio[comp]
        total_apostas = dados['vitorias'] + dados['derrotas']
        taxa_vitoria = round((dados['vitorias'] / total_apostas * 100) if total_apostas > 0 else 0, 1)
        
        msg += f'\n🏆 *{comp}*\n'
        msg += f'  📈 P&L: {("+" if dados["pnl_total"] >= 0 else "")}{dados["pnl_total"]:.2f}u\n'
        msg += f'  ✅ Apostas: {dados["vitorias"]}V / {dados["derrotas"]}D ({taxa_vitoria}%)\n'
        msg += f'  📋 Taxa Aprovação: {dados["taxa_aprovacao"]}%\n'
        
        if dados['motivos_top']:
            msg += f'  ⚠️  Top Rejeições:\n'
            for motivo, count in dados['motivos_top'].items():
                msg += f'    • {motivo}: {count}x\n'
    
    msg += '\n━━━━━━━━━━━━━━━━━━━━'
    return msg
