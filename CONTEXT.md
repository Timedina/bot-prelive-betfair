# Contexto do Projeto — BetBots Platform

> Cole este arquivo no início de qualquer conversa nova (em qualquer login) para retomar
> o trabalho sem precisar reexplicar tudo.

## Infraestrutura
- VPS: Oracle Cloud Ubuntu, IP 152.70.220.118, alias SSH oracle-bot
- Supabase: projeto betbots-platform, ID rxqotlcxujokzujodyhv
- Dashboard: React em Vercel (betbots-dashboard.vercel.app), repo Timedina/betbots-dashboard
- Bots (systemd): bot_prelive.py/bot-betfair.service (LAY) e bot_under25.py/bot-under25.service (BACK U2.5)

## Filtros do bot LAY
- ODD_01_MAXIMA = 20.0
- RAZAO_ODD_MAXIMA = 1.8 (odd_10/odd_01)
- Stake = Liability / (Odd - 1), liability fixa £100
- Ligas: LaLiga, Premier League, Serie A, Ligue 1, Bundesliga, Eredivisie, MLS, Brasileirao A/B, Copa do Brasil, Copa Libertadores, Europa League (Champions League EXCLUIDA)

## Credenciais
- ODDSPAPI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY -> guardar em .env, nunca em texto puro em chat
- SUPABASE_URL = https://rxqotlcxujokzujodyhv.supabase.co

## OddsPapi - odds historicas (Betfair Exchange)
- Host: https://api.oddspapi.io/v4
- Bookmaker: betfair-ex (nao usar betfair-ex2, e teste)
- Mercado Correct Score Full Time: marketId=10336 (sportId 10 = futebol)
  - Outcome 1:0 -> outcomeId=10337
  - Outcome 0:1 -> outcomeId=10344
- Limitacoes API para betfair-ex:
  - /v4/odds-by-tournaments: max 3 tournamentIds por chamada
  - /v4/historical-odds: exige exatamente 1 outcomeId por chamada
  - /v4/historical-odds so retorna dados uteis para fixtures FINALIZADAS (statusId=2)
  - Rate limit (429) - usar pausa entre chamadas
  - /v4/fixtures aceita tournamentId + from/to (YYYY-MM-DD) para achar jogos finalizados
- tournamentIds mapeados: LaLiga=8, Premier League=17, Serie A=23, Ligue 1=34, Bundesliga=35, Eredivisie=37, MLS=242, Brasileiro A=325, Copa do Brasil=373, Copa Libertadores=384, Brasileiro B=390, Europa League=679

## Tabela historical_odds (ja criada no Supabase)
fixture_id, bookmaker_slug, market_id, outcome_id, player_id, odds_record_id, price, bet_limit, active, exchange_back, exchange_lay, odds_created_at, fetched_at, raw_payload

## Script: ingest_historical_odds.py
Uso principal (jogos finalizados):
python ingest_historical_odds.py --finished-tournament 325 --date-from 2026-07-16 --date-to 2026-07-23
Requer env vars: ODDSPAPI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY

## Proximos passos em aberto
- [ ] Integracao historical_odds ainda NAO ligada ao backtest_lay_v2.py (rodar manual antes de automatizar)
- [ ] Rotacionar ODDSPAPI_API_KEY e SUPABASE_SERVICE_KEY (foram expostas em chat)
- [ ] Mover credenciais para .env no VPS

*Ultima atualizacao: 25/07/2026*

## Atualização 25/07/2026 18:11
- Testado e validado endpoint OddsPapi /v4/historical-odds para Betfair Exchange: exige exatamente 1 outcomeId por chamada (mercado 10336=correct score, outcomes 10337=1:0 e 10344=0:1), so retorna dados uteis para fixtures com statusId=2 (finalizadas), e tem rate limit 429 que exige pausa entre chamadas. Endpoint /v4/odds-by-tournaments tem limite de 3 tournamentIds por chamada para betfair-ex. Script ingest_historical_odds.py atualizado com modo --finished-tournament (busca via /v4/fixtures + from/to) que busca os 2 outcomes por jogo e grava na tabela historical_odds do Supabase, ja criada e testada. Criado fluxo CONTEXT.md + update_context.sh para persistir contexto entre logins/sessoes sem gastar token.

## Atualização 25/07/2026 18:39
- Coleta completa: 7 jogos do Brasileirao (16-23/07/2026), 2 outcomes cada (1:0 e 0:1), 24178 registros gravados em historical_odds. Todos os 429 de rate limit resolvidos aumentando sleep-seconds para 8. Fluxo .env + script direto no VPS funcionando de ponta a ponta, sem depender de Windows/PowerShell.

## Atualização 25/07/2026 18:58
- Ativado RLS nas 3 tabelas que estavam expostas (backtest_resultados, metricas, historical_odds), com politica de leitura publica (FOR SELECT USING true) para nao quebrar o dashboard, mantendo escrita bloqueada para quem nao usa service_role_key. Confirmado via Supabase MCP: as 9 tabelas do projeto agora tem RLS ativo.

## Atualização 25/07/2026 20:25
- Corrigido bug de active=false em historical_odds; benchmark de calibracao rodando ok com filtro de outliers

## Atualização 25/07/2026 23:30
- Bug critico corrigido: ambos os bots (bot-betfair e bot-under25) estavam em crash loop (200+ restarts) por erro "Expecting value: line 1 column 1 (char 0)" no login da Betfair. Causa raiz: rotacao/reorganizacao do .env (22:48) renomeou as credenciais para BETFAIR_USERNAME/BETFAIR_PASSWORD/BETFAIR_APP_KEY, mas betfair_client.py ainda lia os nomes antigos EMAIL/SENHA/APP_KEY, resultando em credenciais None e HTTP 400 no certlogin.
- Fix aplicado em betfair_client.py: EMAIL = os.getenv("BETFAIR_USERNAME"), SENHA = os.getenv("BETFAIR_PASSWORD"), APP_KEY = os.getenv("BETFAIR_APP_KEY").
- Ambos os servicos confirmados saudaveis as 23:26: bot-betfair fazendo login OK e analisando jogos com filtros normais; bot-under25 buscando mercados ao vivo e aplicando filtro de janela de entrada (<5min).

## Atualização 26/07/2026 00:20 — Diagnóstico e correção: dashboard "travado" (analises paradas)
- Sintoma: dashboard mostrava só registros de 13:06 (horário local), sem atualizar mesmo com bots rodando e gravando localmente.
- Causa raiz 1 (afetou os DOIS bots, LAY e Under 2.5): supabase_integration.py lia a variavel de ambiente `SUPABASE_KEY`, mas o .env so tinha `SUPABASE_SERVICE_KEY` (renomeada em algum momento do dia, provavelmente durante o setup do OddsPapi/historical_odds). Isso fazia `SUPABASE_ATIVO` ficar False silenciosamente (mensagem de aviso é INFO e é engolida pq acontece antes do logging ser configurado). Ultimo insert real: LAY parou as 16:06:16 UTC, Under25 parou as 13:35:43 UTC.
- Fix: supabase_integration.py linha 11 alterada para `SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')`.
- Causa raiz 2 (so afetava o bot LAY): `SUPABASE_BOT_ID` nunca existiu no .env. O bot Under25 nao sofre com isso pq o start_under25.sh exporta SUPABASE_BOT_ID diretamente antes de rodar o python. O bot-betfair.service roda direto (sem wrapper script), entao dependia 100% do .env, que nunca teve essa chave.
- Fix: adicionado `SUPABASE_BOT_ID=7449c515-4a4e-4ad3-acda-32916034e9c1` ao .env.
- Validado: apos os dois fixes + restart (23:55 e depois 00:15), bot-betfair voltou a fazer GET /filtros e POST /metricas com sucesso (200/201). bot-under25 confirmado gravando em /apostas (PATCH 200 OK). Insert real em /analises ainda pendente de confirmacao pois nao houve analise completa disparada no momento do teste (fila aguardando janela de horario dos jogos).
- Licao aprendida: nomes de env vars devem ser padronizados entre .env e os scripts que os leem (EMAIL/SENHA/APP_KEY vs BETFAIR_USERNAME/PASSWORD/APP_KEY tambem tiveram o mesmo tipo de bug hoje, corrigido em betfair_client.py). Vale criar um script de validacao de .env que checa se todas as env vars esperadas pelos bots existem, antes de reiniciar os servicos.

## Atualização 26/07/2026 00:25 — Script de validação de .env criado
- Criado validar_env.sh: checa presenca e tamanho de todas as env vars esperadas (BETFAIR_*, SUPABASE_*, TELEGRAM_*, ODDSPAPI_API_KEY) e alerta se nomes legados (EMAIL, SENHA, APP_KEY, SUPABASE_KEY) ainda estiverem no .env.
- Uso recomendado antes de qualquer restart: ./validar_env.sh && sudo systemctl restart bot-betfair.service bot-under25.service
- Rodado e validado: todas as 9 vars OK, nenhum nome legado presente.

## Atualização 26/07/2026 19:31 — Travamento silencioso do bot-betfair: causa raiz corrigida + watchdog criado

- **Sintoma**: dashboard mostrava análises paradas desde ~10:05-10:10 (horário local). Investigação mostrou que o bot ficou **~6h mudo** (das 13:10 às 18:45) sem gravar nenhum `POST /analises`, mesmo continuando "vivo" — agendando jogos novos e gravando métricas normalmente, sem nenhum erro/warning no log.

- **Diagnóstico**: `top`/`ps` mostraram o processo com 0% CPU. `strace -p <pid> -f -tt` revelou `read()` em loop retornando `EAGAIN` nos dois sockets HTTPS abertos (conexões `ESTAB`, nunca fechadas, nunca retornando dado) — padrão clássico de I/O bloqueado indefinidamente por falta de timeout.

- **Causa raiz confirmada**: nenhuma chamada HTTP em `betfair_client.py` tinha `timeout` configurado:
  - `login()` — `requests.post(...)` sem timeout
  - `chamar_api()` — `urllib.request.urlopen(req)` sem timeout (a mais crítica, chamada em todo ciclo via `listar_mercados_filtrado`)
  
  Se a rede/Betfair engolisse a resposta silenciosamente, a chamada ficava pendurada pra sempre, sem exceção nem log — travando o loop principal sem qualquer sintoma visível.

- **Fix aplicado** (`betfair_client.py`):
  - `login()`: adicionado `timeout=(10, 20)` no `requests.post`
  - `chamar_api()`: adicionado `timeout=15` no `urllib.request.urlopen`
  - O tratamento de erro já existente (`except Exception`, retorno `None` tratado como falha temporária com cache de TTL curto em `listar_mercados_filtrado`/`analisar_jogo`) passa a disparar corretamente em caso de timeout, em vez do processo ficar pendurado.

- **Validado**: após restart às 19:25:05 UTC, bot voltou a analisar e gravar `/analises` normalmente (4 analisados / 7 chamadas de API no primeiro minuto, fila caindo de 59 → 41).

- **Rede de segurança criada**: `watchdog_bot.sh`, rodando via cron a cada 5 minutos:
  - Reinicia `bot-betfair.service` se o journal ficar **mudo por 5min** (travamento total)
  - Reinicia se ficar **sem nenhum `POST /analises` por 3h** (travamento silencioso, mesmo com processo "vivo")
  - Log em `~/bot-prelive-betfair/watchdog.log`
  - Sudoers configurado em `/etc/sudoers.d/watchdog-bot` para permitir restart sem senha interativa (necessário pro cron)
  - **Pendência**: o limite de 3h sem análise foi um chute baseado no incidente de hoje — observar por alguns dias se gera restart falso-positivo em horários de pouco jogo (madrugada) e ajustar `LIMITE_SEM_ANALISE_MIN` em `watchdog_bot.sh` se necessário.

- **Lição aprendida**: qualquer chamada de rede no projeto sem timeout é um risco de travamento silencioso idêntico a este. Vale revisar se `supabase_integration.py` e outras integrações (Telegram, OddsPapi) têm timeout configurado — ainda não verificado.

## Atualização 26/07/2026 21:41 — Bug real encontrado: analises com market_id_cs vazio nunca gravavam no Supabase

- **Sintoma**: usuário reportou que jogos começando agora (Flamengo, Grêmio, América-MG, Bragantino, Caxias do Sul — todos Brasileirão, dentro do filtro de ligas do bot) não apareciam na aba Analises do dashboard, mesmo com o bot rodando saudável (systemd ok, sem crash, sem travamento de I/O).

- **Investigação**:
  - "Dash parou" inicial (mais cedo no dia) era alarme falso — dashboard batia com o banco, gap de análises se devia ao mecanismo de cache de jogos já reprovados permanentemente (que só grava em `/metricas`, não em `/analises`).
  - Mas o segundo caso (jogos do Brasileirão às 21:25 UTC) era diferente: log mostrava `Sem mercados disponiveis (resposta valida vazia) — evento provavelmente sem cobertura` seguido de `⚠️ ANALISE NAO VALIDADA: market_id_cs vazio`. Confirmado via Supabase que zero desses jogos foram inseridos em `analises`.

- **Causa raiz confirmada**: `_validar_analise()` em `supabase_integration.py` exigia `market_id_cs` não-vazio como campo obrigatório para permitir o insert em `analises`. Quando a Betfair não tinha (ainda) o mercado Correct Score aberto para um evento — comum logo após o apito inicial —, a análise inteira era descartada silenciosamente, mesmo `market_id_cs` sendo nullable no schema (`event_id` e `nome_jogo` são os únicos campos realmente NOT NULL).

- **Fix aplicado**: removidas as 2 linhas de validação de `market_id_cs` em `_validar_analise()` (`supabase_integration.py`, backup salvo como `.bak`). Diff conferido manualmente antes do restart.

- **Validado**: `bot-betfair.service` reiniciado às 21:41:26 UTC (PID 1247702), subiu limpo, fila recalculada (28→18 aguardando).

- **Pendência de confirmação**: aguardando ~21:55 UTC (próximo jogo real entrando na janela de análise) para confirmar que uma análise com `market_id_cs` vazio agora É gravada corretamente em `analises`.

- **Observação separada, não investigada ainda**: campo `horario` está vindo como `"--:--"` em todos os registros recentes de `analises` — possível bug de preenchimento, verificar depois.

- **Confirmado nesta sessão (não é bug)**: bot Under25 só grava em `analises` quando encontra candidato dentro da janela de entrada (<5min), diferente do LAY que grava todo ciclo — por isso gaps longos (32h+) no Under25 são esperados e não indicam bot travado.

## Atualização 31/07/2026 00:50 — TTL de "sem mercados" corrigido para jogos ao vivo + comando /restart no Telegram

- Bug: `analisar_jogo()` em bot_prelive.py gravava reprovacao "Sem mercados disponiveis na Betfair" com ttl_minutos=240 fixo, independente do jogo ja estar ao vivo. Como uma partida dura ~105min, esse TTL de 4h bania o evento pelo resto do jogo mesmo quando o mercado Correct Score abria minutos depois (confirmado com Coritiba x Cruzeiro: reprovado as 21:25 com "sem mercado", mas mercado real ja aberto com R$43mil correspondidos as 21:30).
- Fix: `cache_eventos.registrar(event_id, motivo_vazio, ttl_minutos=240)` alterado para usar `CACHE_TTL_MINUTOS` (10min) quando `minutos >= 0` (jogo ao vivo), mantendo 240min so para jogos pre-live. Backup: bot_prelive.py.bak_ttl_fix. Cache do dia (dados_bot/cache_YYYY-MM-DD.json) foi apagado para forcar reavaliacao imediata dos ~85 jogos bloqueados. Servico reiniciado as 00:41 UTC (31/07) sem erros, Cache: 0 bloqueados confirmado no log.
- Nota: cache usa fuso UTC-3 (Brasilia) no nome do arquivo, nao UTC. Nota: log "Cache: reprovado permanente" e texto fixo generico (aparece tanto para cache realmente permanente quanto para cache dentro de TTL) - nao confiar nesse texto para diagnostico.
- Nota separada: LIGAS_PERMITIDAS esta vazia/sem restricao atualmente, qualquer liga passa pela checagem de mercado.
- Adicionado comando /restart (reinicia bot-betfair.service) e /restart_under25 (reinicia bot-under25.service) em telegram_commands.py, reaproveitando sudoers ja configurado para o watchdog (sudo -n systemctl restart funciona sem senha). Backup: telegram_commands.py.bak_restart_cmd.
- Confirmado separadamente nesta sessao: bug do 26/07 (market_id_cs vazio nao gravava em analises) segue corrigido; observacao pendente do campo "horario" vindo como "--:--" em analises segue nao investigada.

## Atualização 31/07/2026 02:05 — Auditoria "no_limite" e diagnóstico do filtro de IA

- **Feature nova**: auditoria "no_limite" adicionada em `analisar_jogo()` (bot_prelive.py), logo antes de `resultado['aprovado'] = True`. Marca `resultado['no_limite']` (bool) e `resultado['no_limite_detalhes']` (texto) quando odd_01, odd_10, razão odd_01/odd_10 ou liquidez_disponivel estão a até 10% (margem=0.10) do teto/piso configurado nos filtros. Campos gravados em `supabase_integration.py` na tabela `analises` (`no_limite`, `no_limite_detalhes`).
  - Primeira tentativa de patch via script Python falhou silenciosamente (string `old` sem a linha em branco real do arquivo → `count()==0` → abortou sem quebrar nada). Segunda tentativa corrigida, sintaxe validada (`ast.parse`), diff conferido, `bot-betfair.service` reiniciado sem erros no journal.
  - Backups: `bot_prelive.py.bak_no_limite`, `bot_prelive.py.bak_no_limite2`, `supabase_integration.py.bak_no_limite`.

- **Causa raiz encontrada — filtro de IA nunca vetou nenhum jogo**: query no Supabase confirmou 0 vetos da IA em 4050 análises reprovadas no histórico, e apenas 21 consultas reais registradas (`ia_motivo` sem "IA indisponivel"). Causa: **Gemini 2.0 Flash Lite perdeu a cota do free tier em 31/07/2026**, fazendo toda chamada cair em fallback (aprova automaticamente sem checagem real da IA).
  - Fix: `IA_MODELO` em `bot_prelive.py` (linha 118) trocado de `"gemini-2.0-flash-lite"` para o alias `"gemini-flash-latest"` (sempre aponta pro modelo Flash mais atual do Google, evita quebra por descontinuação de versão específica — trade-off: menos controle sobre quando o comportamento do modelo muda).
  - Medições históricas de desempenho com_ia vs sem_ia (feitas antes da troca) refletem majoritariamente o modelo antigo/quebrado — **precisam ser refeitas** olhando só `analisado_em >= '2026-07-31'`.
  - Validação pendente: ainda não foi possível confirmar o modelo novo respondendo de verdade — na janela testada (madrugada, ligas menores como Colômbia/Costa Rica) todos os jogos foram reprovados pelos filtros numéricos (odd fora de faixa, razão odd_01/odd_10 alta) antes de chegar na etapa da IA. Repetir teste em horário com jogos de ligas do filtro principal (Brasileirão, Premier League etc.) com: `journalctl -u bot-betfair.service --since "1 hour ago" | grep "🤖 IA:"`

- **Melhorias sugeridas para o filtro de IA (ainda não implementadas)**:
  1. Alerta via Telegram se N consultas seguidas caírem em fallback "IA indisponivel" (hoje é só log silencioso — foi assim que a quebra do free tier passou despercebida)
  2. Gravar qual modelo respondeu em cada análise (hoje `ia_motivo` não registra isso; como `gemini-flash-latest` é alias, o modelo por trás pode mudar sem aviso)

## Atualização 31/07/2026 02:40 — Systemd validando .env antes do start + limpeza e commit do repositório

- **ExecStartPre no unit file**: adicionado `ExecStartPre=/home/ubuntu/bot-prelive-betfair/validar_env.sh` em `bot-betfair.service` (editado via `systemctl edit --full`). O `validar_env.sh` já retornava `exit 1` nos caminhos de erro (confirmado antes de aplicar) — agora o systemd bloqueia o start/restart do serviço se faltar env var esperada ou sobrar nome legado (EMAIL, SENHA, APP_KEY, SUPABASE_KEY), automaticamente, seja restart manual, via watchdog ou via comando `/restart` do Telegram. Validado com `daemon-reload` + restart: subiu limpo, sem erro no `ExecStartPre`.

- **Organização do repositório `bot-prelive-betfair`**: `git status` revelou 7 arquivos modificados nunca commitados (todos os patches recentes: timeouts, IA_MODELO, no_limite, TTL fix, comandos Telegram) e vários scripts de infra nunca versionados.
  - Removidos arquivos de lixo gerados por comando mal digitado: `.gitignorecd` (continha `.env /home/ubuntu/bot-prelive-betfair`), `0`, `=` (vazios).
  - Pasta `betbots-dashboard/` estava clonada por engano dentro do repo do bot — movida para `~/betbots-dashboard` (é outro projeto/repo separado).
  - Scripts de backtest/calibração pontuais apagados: `backtest_filtros_relaxados.py`, `backtest_relaxados_dedup.py`, `batch_collect.py`, `calibration_benchmark.py`, `fetch_fixture_results.py`, `test_supabase2.py`.
  - `backtest_odd01_18_vs_20.py` mantido localmente, fora do controle de versão — documenta o teste que definiu `ODD_01_MAXIMA=18.0` em produção.
  - 3 commits organizados enviados ao GitHub (`515af83..c5b8923`):
    1. `fix: timeouts betfair_client, IA_MODELO gemini-flash-latest, feature no_limite, TTL sem-mercados, comandos telegram restart` (5 arquivos)
    2. `chore: adiciona scripts de infra (validacao env, watchdog, context, ingest odds)` (validar_env.sh, watchdog_bot.sh, update_context.sh, ingest_historical_odds.py — nunca tinham sido versionados)
    3. `docs: atualiza CONTEXT.md e gitignore`
  - `git status` final: repo limpo, sem lixo, sem modificações pendentes.

- **Próximo passo decidido**: revisar depois de um período com o modelo novo (`gemini-flash-latest`) se o filtro de IA realmente veta jogos ruins ou é só "carimbo de aprovado" sem impacto real — comparar grupos com/sem veto real usando `analisado_em >= '2026-07-31'`.

## Atualização 03/08/2026 23:00 — Segundo bug de mascaramento (status PERDA falso) + GEMINI_API_KEY ausente corrigida

- **Bug encontrado**: `atualizar_resultado_aposta_supabase()` em `supabase_integration.py` tinha `status = 'VITORIA' if resultado_geral == 'VITORIA' else 'PERDA'` — qualquer `resultado_geral` que não fosse exatamente `'VITORIA'`, incluindo `None` (resultado ainda indeterminado, placar não obtido), virava `'PERDA'` no banco. Encontrado no jogo Deportes Limache v Nublense (Chilean Primera Division, event_id 35870119, 02/08): mercado com liquidez muito baixa (£139 disponível), odd_lay nunca foi capturada (`null` no JSON local), placar nunca resolvido (`"Indisponivel"`), mas apareceu no dashboard como PERDA com PnL=0.

- **Fix aplicado**: adicionado `if not resultado_geral: return` (mantém PENDENTE) antes de decidir o status. Backup: `supabase_integration.py.bak_status_fix`.

- **Correção do dado histórico**: consultado via Supabase MCP todos os registros com `status='PERDA' AND (pnl IS NULL OR pnl=0)` — encontrado apenas esse 1 registro (não é padrão espalhado). Corrigido manualmente de volta para `PENDENTE` (placar_final e pnl limpos) direto no Supabase.

- **Verificação do gráfico PnL**: dia 01/08 mostrava -69,14u — conferido registro a registro, bate exatamente com a soma dos 6 jogos do dia (-100 do FC Basel v Lausanne + 5 vitórias pequenas somando +30,86). Não há mais nenhum registro com bug nesse dia; é variância real da estratégia (perde a liability inteira raramente, ganha pouco na maioria das vezes).

- **GEMINI_API_KEY ausente**: descoberto que a variável não existia no `.env`, causando `"IA indisponivel (HTTP 403)"` em toda consulta desde sempre (diferente da causa de 31/07, que foi cota esgotada — aqui era falta de credencial). Como o código aprova por padrão quando a IA falha ("para não bloquear o bot"), toda análise estava passando sem checagem real de IA. Chave gerada em https://aistudio.google.com/apikey e adicionada ao `.env`.

- **`validar_env.sh` atualizado**: criada categoria de variáveis opcionais (`VARS_OPCIONAIS`) que geram aviso mas não bloqueiam o restart — `GEMINI_API_KEY` adicionada nessa lista, já que o bot tem fallback funcional na ausência dela, mas fica degradado (sem checagem real de IA). Backup: `validar_env.sh.bak_gemini`.

- **Pendência de confirmação**: aguardando um jogo passar por todos os filtros numéricos e chegar na etapa de consulta de IA para confirmar que o Gemini está respondendo de verdade agora (não em fallback). Checar com: `journalctl -u bot-betfair.service --since "X minutes ago" | grep -i "🤖 IA\|ia_motivo"`.

- **Nota de segurança**: a chave `GEMINI_API_KEY` foi colada em texto puro numa sessão de chat durante a configuração — mesmo padrão de exposição já registrado para `ODDSPAPI_API_KEY` e `SUPABASE_SERVICE_KEY` anteriormente. Considerar rotacionar via https://aistudio.google.com/apikey se for prudente.


## Atualização 03/08/2026 23:30 — Análise de melhorias do projeto (pendente de execução)

- **Medir consumo real de API Betfair**: comando pra somar chamadas do dia (contador zera a cada restart):
  `journalctl -u bot-betfair.service --since "today" --no-pager | grep -oP '(?<=📡 )\d+(?= chamadas API)' | awk 'BEGIN{max=0; total=0} {if($1<max){total+=max; max=$1} else {max=$1}} END{total+=max; print "Total estimado hoje:", total}'`
  Ainda não executado/confirmado nesta sessão.

- **Melhorias prioridade ALTA**:
  1. Batching de `listar_mercados()`: hoje faz 1 chamada por event_id. A API da Betfair aceita lista de eventIds no mesmo filtro — trocar para 1 chamada por ciclo em vez de N reduziria consumo de API substancialmente.
  2. Padronizar tratamento de erro: criar `class BetfairSessionError(Exception)` e usar de forma consistente em vez de `return None`/`return []`, que já causou 2 bugs de "falha silenciosa" hoje (chamar_api mascarando sessão expirada, e status PERDA falso). Erro deveria sempre ser explícito, nunca inferido por ausência de dado.

- **Melhorias prioridade MÉDIA**:
  1. Repopular `LIGAS_PERMITIDAS` (está vazia hoje) — bot analisa qualquer liga incluindo femininas/sub-21/menores sem cobertura Betfair, gerando ruído e chamadas de API desperdiçadas.
  2. Investigar duplicação de log ("Login OK!" aparecendo 10x no mesmo segundo em 02/08) — sugere handler de logging duplicado.
  3. Dashboard/heartbeat de saúde da API (última chamada OK, taxa de erro recente, status sessão/IA) — hoje só se descobre problema pelo sintoma no dashboard de apostas.
  4. Relatório por liga só deveria mostrar conclusões com n >= 10 (hoje quase todas as ligas têm n=1 — risco de decisão por ruído estatístico).
  5. Organizar backups `.bak_*` em pasta `backups/` com timestamp em vez de acumular soltos no diretório principal.
  6. Expandir `test_resultado_jogos.py` para cobrir casos de borda (placar indisponível, odd_lay nula) — pegaria automaticamente bugs como o do Deportes Limache antes de produção.
  7. `betfair_client.py` duplicado entre `bot-prelive-betfair` e `bot-under25` — risco de aplicar fix em um e esquecer o outro. Considerar módulo compartilhado.

- **Melhorias prioridade BAIXA**: rotacionar chaves expostas em chat (ODDSPAPI_API_KEY, SUPABASE_SERVICE_KEY, GEMINI_API_KEY); considerar secrets manager da Oracle Cloud.

- **Estratégico**: formalizar regra tipo "não altero filtro de produção sem N>=30 amostras + teste de significância" antes de decidir incluir/excluir ligas ou ajustar thresholds, dado o volume ainda baixo por segmento.


## Atualização 03/08/2026 23:55 — Dashboard de saúde simples implementado (/saude no Telegram)

- **Feature nova**: módulo `saude.py` criado com função `registrar(integracao, ok, detalhe="")` que grava em `dados_bot/saude.json` (escrita atômica via `.tmp` + `os.replace`) o histórico de `ok_streak`, `fail_streak`, `ultimo_ok` e `ultimo_erro` por integração. Nunca derruba o bot (`except: pass` interno).

- **Pontos instrumentados**:
  - `betfair_client.py`: `login()` (sucesso/falha) e `chamar_api()` (sucesso, erro JSON-RPC, HTTPError, erro genérico de tentativa) — 7 pontos no total.
  - `bot_prelive.py`: `consultar_ia()` — sucesso e os 3 caminhos de falha (HTTPError, JSONDecodeError, Exception genérica).
  - `supabase_integration.py`: `registrar_analise_supabase()`, `registrar_aposta_supabase()`, `atualizar_resultado_aposta_supabase()` e `verificar_saude_supabase()` — sucesso e falha em cada uma, 9 pontos no total.
  - `telegram_commands.py`: comando `/saude` novo (não usei `/status` porque esse nome já existia pra outra coisa — uptime/fila/aprovados). Formata cada integração com 🟢 (fail_streak=0), 🟡 (1-2 falhas seguidas) ou 🔴 (3+), e minutos desde o último sucesso.

- **Bug encontrado e corrigido durante a implementação**: `from datetime import datetime, timezone` como import local dentro do handler do `/saude` em `telegram_commands.py` sombreava o `datetime` já importado no topo do arquivo (linha 11) — como Python resolve escopo de variável pra função inteira (não por bloco), isso quebrou qualquer uso de `datetime` que rodasse antes dessa linha dentro da mesma função, com erro `local variable 'datetime' referenced before assignment`. Corrigido removendo o import local, usando o que já existe no topo do módulo.

- **Lição de processo (importante pra próximos patches via heredoc colado no SSH)**: usar `\` como delimitador de string old/new com emoji ou acento (ex: `⚠️`, `não`, `Só`) faz o `count()` do replace falhar silenciosamente com `match count = 0`, porque o paste no terminal corrompe esses bytes multi-byte. Solução: sempre usar âncoras 100% ASCII (sem emoji, sem acento) nas strings de busca/substituição dos scripts de patch em Python.

- **Backups criados**: `betfair_client.py.bak_saude2`, `bot_prelive.py.bak_saude2`, `supabase_integration.py.bak_saude2`, `telegram_commands.py.bak_saude2` (versões anteriores ao patch de saúde, para rollback se necessário).

- **Validado em produção**: `/saude` no Telegram respondendo corretamente após restart, `dados_bot/saude.json` sendo populado (confirmado `betfair: OK ha 0min, falhas seguidas: 0` logo após o restart).

- **Pendente**: aguardar mais tempo de execução pra confirmar que `supabase` e `ia` também aparecem no `/saude` (dependem de inserts/consultas reais acontecerem).

## Atualização 06/08/2026 — Filtro de exclusão de ligas femininas, sub-categorias e amistosos

- **Motivação**: análise das 5 perdas do bot LAY (95 vitórias / 5 perdas, PnL +£89,45) mostrou que o segmento "feminino + sub-15 a sub-23 + amistosos" tinha 13 vitórias / 1 perda mas era **líquido negativo (-£29,17)** — vitórias pequenas (~£5-6) não compensavam a única perda de -£100. Simulação indicou que excluir esse segmento levaria o PnL total de +£89,45 para +£118,62.
- **Outras hipóteses testadas e descartadas nessa análise** (sem sinal preditivo): `odd_favorito` (perdas espalhadas pela distribuição normal, não concentradas em nenhum extremo relevante com n=5), campo `no_limite` (win rate igual entre no_limite=true/false: ~95% em ambos), `liquidez_disponivel` (média quase idêntica entre vitórias e perdas, ~£1.336 vs £1.362 — nenhuma perda veio de mercado raso).
- **Nota de dado**: `odd_matched` está `null` em 100% das apostas (todas `simulado=true`) — não existe "dinheiro correspondido" real registrado, só o `stake` teórico calculado por `Liability/(Odd-1)`. Não há ainda captura de profundidade de book (bid/ask) pra estimar risco de execução real.
- **Implementação em `bot_prelive.py`**:
  - Adicionado `import re` no topo do arquivo (nao existia antes).
  - Criada lista `LIGAS_EXCLUIDAS_PADROES` (regex, antes de `analisar_jogo()`): `\(w\)`, `\bwomen\b`, `feminin`, `\bu-?1[5-9]\b`, `\bu-?2[0-3]\b`, `friendl`, `amistos`.
  - Criada função `liga_ou_categoria_excluida(nome_jogo, competition)` que retorna o motivo se algum padrão bater, ou `None`.
  - Gancho inserido dentro de `analisar_jogo()`, logo após `resultado['competition'] = competition` e **antes** do filtro `LIGAS_PERMITIDAS` (linha ~1197) — reprova cedo, economizando a chamada de `verificar_favorito_rapido()` (bate na API) em jogos que já seriam excluídos de qualquer forma.
  - Reprovação registrada em `resultado['motivo_reprovacao']` e no cache (`cache_eventos.registrar`) com o texto `"Categoria excluida (padrao: <padrao>)"`, no mesmo formato dos outros motivos (`Sem Correct Score`, `Liga nao permitida`, etc) — aparece no dashboard normalmente.
  - Validado: `ast.parse` OK, `validar_env.sh` OK, `bot-betfair.service` reiniciado sem erro.
  - Commit `7338101` (`feat: filtro de exclusao para ligas femininas, sub-categorias e amistosos`), push feito pro GitHub (`Timedina/bot-prelive-betfair`, branch main).
- **Pendências**:
  - Confirmar no log real (`journalctl -u bot-betfair.service`) um evento sendo pego pelo motivo `Categoria excluida`, ainda nao presenciado ao vivo no momento do deploy.
  - Reavaliar PnL com dados pos-filtro daqui a alguns dias/semanas pra confirmar o ganho estimado de +£29 na pratica.
  - `LIGAS_PERMITIDAS` continua vazia (nao mexemos nela) — os dois filtros coexistem, esse novo e o antigo (que so entra em acao se a lista for repopulada).
  - Seguem em aberto de sessoes anteriores: confirmar `gemini-flash-latest` vetando de verdade (nao em fallback), medir consumo real de API Betfair do dia, rotacionar chaves expostas em chat.

## Atualização 06/08/2026 (cont.) — Captura de odd_zebra/odd_empate (EM ANDAMENTO)

- **Motivação**: para simular filtro de "diferença de odds do 1x2" (odd_zebra - odd_favorito), verificado que esse dado nunca foi persistido — só `odd_favorito` existe em `analises`. Backtest retroativo via OddsPapi descartado: `fixture_id` da OddsPapi (formato `id1000...`) não bate com `event_id` da Betfair usado nas tabelas do bot, e dos 148 jogos em `backtest_resultados` só ~9-13 caem em ligas com `tournamentId` já mapeado (resto espalhado em 75+ competições nao mapeadas) — amostra pequena demais, mapear tudo seria caro. Decidido capturar ao vivo daqui pra frente em vez de reconstruir historico.
- **Confirmado via OddsPapi `/v4/markets?sportId=10`**: mercado 1X2 real e `marketId=101` (Full Time Result), outcomes `101`=casa(1), `102`=empate(X), `103`=fora(2) — nao usado ainda, decidimos nao ir por esse caminho (ver acima).
- **Progresso no codigo (`bot_prelive.py`)**:
  - `verificar_favorito_rapido()` reescrita: em vez de so guardar a menor odd (favorito) e descartar o resto, agora coleta os 2 times + empate do `book_mo` (que ja vinha completo, sem chamada extra a API) e retorna tambem `odd_zebra` (odd do 2 colocado) e `odd_empate`. Assinatura mudou de 4 pra 6 valores de retorno.
  - Call site dentro de `analisar_jogo()` (linha ~1215) atualizado pra desempacotar os 2 valores novos e gravar `resultado['odd_zebra']` e `resultado['odd_empate']`.
  - Ambas as edicoes aplicadas por substituicao posicional de linhas (nao por match de string) porque o arquivo tem quebras de linha em branco inconsistentes que quebravam o `str_replace` por conteudo — mesmo problema ja visto em patches anteriores (`no_limite`, filtro de categoria). Licao reforcada: sempre conferir via `sed -n` as linhas exatas antes de montar o patch.
  - Backup: `bot_prelive.py.bak_odd_zebra`.
  - Sintaxe validada (`ast.parse`) apos cada etapa.
- **RESOLVIDO (07/08/2026)**: migration ja tinha sido aplicada (colunas odd_zebra/odd_empate numeric em analises), supabase_integration.py ja incluia os campos no insert (nao precisou editar), bot-betfair.service reiniciado as 23:55:35 UTC (06/08). Confirmado via Supabase MCP que a fiacao do codigo esta correta ponta a ponta. Poucas analises no restart inicial ainda nao tinham odd_favorito preenchido (esperado, so preenche apos passar do filtro de favorito) — nao era bug, so falta de volume. Commit + push feitos (b27358a) junto com o filtro de Leagues Cup abaixo.
- **Pendente real**: deixar rodando alguns dias pra acumular amostra de odd_zebra/odd_empate antes de simular filtro de diferenca 1x2.

## Atualização 07/08/2026 — Filtro para "North American Leagues Cup"

- Motivação: jogo Cruz Azul v Philadelphia (North American Leagues Cup) foi aprovado pelo bot LAY apesar de ser uma competição que deveria ser excluída — filtro `LIGAS_EXCLUIDAS_PADROES` (criado 06/08 para feminino/sub/amistoso) não cobria "copa"/"cup" de propósito, já que Copa do Brasil e Copa Libertadores fazem parte da lista de ligas permitidas do bot.
- Decisão: bloquear especificamente essa competição (`"north american leagues cup"`), sem afetar Copa do Brasil/Libertadores, em vez de um filtro genérico "cup|copa".
- Fix: adicionado o padrão `r"north american leagues cup"` à lista `LIGAS_EXCLUIDAS_PADROES` em `bot_prelive.py`. Backup: `bot_prelive.py.bak_leagues_cup`.
- Validado: `ast.parse` OK, `validar_env.sh` OK, `bot-betfair.service` reiniciado ~00:14 UTC (07/08) sem erros no journal, fila e métricas normais.
- Commit `b27358a` (`feat: captura odd_zebra/odd_empate + filtro North American Leagues Cup`), push feito pro GitHub (`Timedina/bot-prelive-betfair`, branch main). CONTEXT.md commitado separadamente.

*Ultima atualizacao: 07/08/2026*

## Atualização 07/08/2026 (cont.) — Comandos /pausar e /retomar no Telegram

- Motivação: não havia forma de pausar o bot LAY manualmente sem SSH.
- Implementação em `telegram_commands.py`: `/pausar` roda `sudo -n systemctl stop bot-betfair.service`, `/retomar` roda `sudo -n systemctl start bot-betfair.service`, seguindo o mesmo padrão do `/restart` já existente. Backup: `telegram_commands.py.bak_pausar`.
- Sudoers ajustado: criado `/etc/sudoers.d/watchdog-bot-pause` liberando `stop`/`start` de `bot-betfair.service` sem senha (sudoers anterior só liberava `restart`/`is-active`). Corrigida permissão do arquivo para 0440 (criação inicial ficou com permissão errada, `visudo -c` acusou); validado `visudo -c` OK em todos os arquivos de sudoers.
- Validado: `ast.parse` OK, `validar_env.sh` OK, `bot-betfair.service` reiniciado ~00:35 UTC (07/08) sem erros no journal.
- Commit `f1a1762` (`feat: comandos /pausar e /retomar no Telegram para bot LAY`), push feito pro GitHub (`Timedina/bot-prelive-betfair`, branch main).
- Pendência aberta: checar se `watchdog_bot.sh` (reinicia se journal mudo por 5min) não vai tentar religar o bot automaticamente enquanto pausado via `/pausar` — ainda não verificado.

*Ultima atualizacao: 07/08/2026*

## Atualização 07/08/2026 (cont.) — Comandos /pausar e /retomar no Telegram

- Motivação: não havia forma de pausar o bot LAY manualmente sem SSH.
- Implementação em `telegram_commands.py`: `/pausar` roda `sudo -n systemctl stop bot-betfair.service`, `/retomar` roda `sudo -n systemctl start bot-betfair.service`, seguindo o mesmo padrão do `/restart` já existente. Backup: `telegram_commands.py.bak_pausar`.
- Sudoers ajustado: criado `/etc/sudoers.d/watchdog-bot-pause` liberando `stop`/`start` de `bot-betfair.service` sem senha (sudoers anterior só liberava `restart`/`is-active`). Corrigida permissão do arquivo para 0440 (criação inicial ficou com permissão errada, `visudo -c` acusou); validado `visudo -c` OK em todos os arquivos de sudoers.
- Validado: `ast.parse` OK, `validar_env.sh` OK, `bot-betfair.service` reiniciado ~00:35 UTC (07/08) sem erros no journal.
- Commit `f1a1762` (`feat: comandos /pausar e /retomar no Telegram para bot LAY`), push feito pro GitHub (`Timedina/bot-prelive-betfair`, branch main).
- Pendência aberta: checar se `watchdog_bot.sh` (reinicia se journal mudo por 5min) não vai tentar religar o bot automaticamente enquanto pausado via `/pausar` — ainda não verificado.

*Ultima atualizacao: 07/08/2026*

## Atualização 11/08/2026 — Bugs criticos corrigidos: jogos pendentes nunca resolviam (placar + Supabase)

- **Sintoma**: dashboard mostrava dezenas de apostas travadas em PENDENTE por dias (desde 02/08), mesmo com o bot rodando saudavel e outros jogos resolvendo normalmente.

- **Bug 1 (raiz) em `resultado_jogos.py`**: quando o mercado Correct Score ja estava fechado, o codigo fazia uma segunda chamada a Betfair (`buscar_nome_runner_vencedor` via `listMarketCatalogue`) pra descobrir o nome do placar vencedor — mas a Betfair para de retornar mercados ja fechados ha muito tempo nesse endpoint, entao a chamada voltava `None` e o jogo nunca era marcado como resolvido, tentando de novo (e falhando) todo ciclo, sem nenhum log de erro em producao (o crash real `unsupported format string passed to NoneType.__format__` so aparecia com `verbose=True`, mascarando o bug quando `verbose=False`).
  - Fix: usar primeiro o `runners_cs_map` (mapa `selectionId -> placar`) que ja fica salvo localmente na hora da analise, so cair pro `listMarketCatalogue` como fallback. Corrigido tambem o crash de formatacao do print verbose quando `pnl_estimado` for `None`.
  - Backup: `resultado_jogos.py.bak_placar_pendente`.

- **Bug 2 (Supabase nunca atualizava, mesmo com o placar resolvido) em `bot_prelive.py`**: o loop que envia resultado pro Supabase montava `aprovados_agora` com `.update(_info_dia)` e depois iterava com `.values()`, perdendo a chave `event_id` do dicionario. A chamada `sb.atualizar_resultado_aposta_supabase(event_id=info.get('event_id', ''), ...)` sempre ia com `event_id` vazio — o UPDATE no Supabase nao batia em nenhuma linha (sem erro, 0 linhas afetadas), e o log `Resultado auto: ... VITORIA` aparecia normalmente mesmo sem nada ser gravado (o `log.info` roda antes da chamada ao Supabase, entao nao prova que ela funcionou).
  - Fix: ao montar `aprovados_agora`, injetar `_info.setdefault('event_id', _eid)` usando a chave do dicionario antes do `.update()`.
  - Os 16 jogos ja resolvidos localmente (que tinham `_telegram_enviado=True` e por isso nao seriam reprocessados automaticamente pelo bot) foram corrigidos com UPDATE manual direto no Supabase, usando os dados de PnL/placar ja calculados no log.
  - Backup: `bot_prelive.py.bak_event_id_fix`.

- **Validacao**: 17 jogos de 09-11/08 resolvidos de uma vez apos os dois patches (PnL calculado corretamente, gravado no Supabase). Unico caso que continua PENDENTE: `Deportes Limache v Nublense` (mesmo jogo de liquidez baixissima ja tratado manualmente em 03/08) — nao tem `runners_cs_map` salvo, parece ser dado insuficiente daquele jogo especifico, nao um bug sistemico.

- **Deploy do dashboard (nao-bug)**: um deploy antigo (commit `refactor: atualiza arquivos principais do projeto`, branch `refactor/v2-foundation`) falhou no Vercel com `vite: command not found` — mas ja tinha sido superado por dois commits seguintes na `main` que buildaram normalmente; producao (`betbots-dashboard.vercel.app`) esta servindo a versao boa, sem acao necessaria.

- **Pendencia nao resolvida nessa sessao**: RLS ainda desativado em 4 tabelas do Supabase (`apostas`, `metricas`, `historical_odds`, `resultados_reais`) — expostas a leitura/escrita via chave anon. SQL de correcao ja levantado, aguardando decisao de aplicar junto com politica de leitura publica.

- **Licao de processo**: log de sucesso emitido antes de confirmar o retorno de uma chamada de rede/DB nao garante que a chamada funcionou — nesse caso um UPDATE de 0 linhas nao gera excecao, entao o log mentiu por dias sem ninguem perceber. Preferir logar depois de confirmar sucesso, ou logar o retorno real da chamada.

*Ultima atualizacao: 11/08/2026*

## Atualização 11/08/2026 (cont.) — Modo sombra para filtros candidatos (razão odd_01/odd_10, odd_01 mínima, faixa odd_favorito)

- **Motivação**: análise de perdas mostrou win rate real (~92%) abaixo do breakeven teórico (~94%) na odd média (~17), e nenhuma variável isolada (razão CS, diferença 1X2, liquidez, odd_favorito, minuto, IA, no_limite) separou vitória de derrota de forma confiável na amostra disponível (13 perdas / 146 vitórias) — sinal fraco demais pra virar filtro direto sem violar a regra de N>=30 por segmento.
- **Implementação**: bloco novo em `bot_prelive.py`, logo após `resultado['aprovado'] = True` (mesmo padrão do bloco `no_limite`), calculando 4 flags booleanas SEM bloquear aprovação: `sombra_razao_estreita` (razão odd_01/odd_10 fora de 1.2-1.6), `sombra_odd01_min25` (odd_01 < 25), `sombra_odd01_min30` (odd_01 < 30), `sombra_favorito_1_9_2_1` (odd_favorito fora de 1.90-2.09).
- **Patch em `supabase_integration.py` precisou de 2 tentativas**: a v1 assumiu âncora `resultado.get('no_limite')`, mas o dict real usa `info.get('no_limite', False)` com espaçamento de alinhamento — abortou sem quebrar nada (comportamento esperado). v2 corrigida: em vez de bater string exata, localiza a LINHA contendo `'no_limite_detalhes':` e insere as novas linhas logo depois, copiando a indentação real (12 espaços). Aplicado na linha 97.
- **Migration no Supabase**: 4 colunas booleanas novas adicionadas via MCP direto (`ALTER TABLE analises ADD COLUMN...`): `sombra_razao_estreita`, `sombra_odd01_min25`, `sombra_odd01_min30`, `sombra_favorito_1_9_2_1`.
- **Backups**: `bot_prelive.py.bak_sombra`, `supabase_integration.py.bak_sombra` (v1, não usado), `supabase_integration.py.bak_sombra_v2` (backup real, pré-patch v2).
- **Validado**: `ast.parse` OK nos dois patches, `validar_env.sh` OK, `bot-betfair.service` reiniciado 23:35:33 UTC (11/08) sem erro no journal.
- **Pendência**: aguardando primeira análise aprovada pós-restart pra confirmar que as flags estão sendo gravadas de verdade (checado 23:36 UTC, ainda `null` nas últimas aprovações — todas anteriores ao restart).
- **Query de avaliação pronta**: `avaliar_filtros_sombra.sql` (fora do repo, mantido junto ao chat) — 3 passos: (0) checa N>=30 nos dois lados de cada flag, (1) win rate/PnL por flag, (2) teste de diferença de proporção. Só promover um filtro sombra a filtro real de produção se passar nos 3 critérios (N>=30 + win rate visivelmente menor + diferença > 2x erro padrão).

## Atualização 12/08/2026 — fix liquidez_total None + watchdog LIMITE_SEM_ANALISE_MIN

- Motivação: watchdog gerando muitas mensagens de madrugada; investigação revelou dois problemas distintos e nao relacionados entre si.
- Bug real (prioridade alta): em analisar_jogo() (bot_prelive.py, linha 1244), liquidez_total = book_cs.get('totalMatched', 0) so usa o default quando a chave esta ausente -- mas a Betfair as vezes retorna totalMatched: null explicitamente (chave presente, valor None), fazendo .get() retornar None e a formatacao f'...£{liquidez_total:.0f}...' estourar TypeError: unsupported format string passed to NoneType.__format__. Ocorreu 2x seguidas (18:59:35 e 19:02:35 UTC, 11/08) com o jogo Banks O'Dee v Peterhead, esgotando MAX_ERROS_CONSECUTIVOS=5 e derrubando a sessao Betfair (INVALID_SESSION_INFORMATION), causando restart via Restart=on-failure do systemd (nao do watchdog).
- Fix: linha 1244 alterada para liquidez_total = book_cs.get('totalMatched') or 0; backup bot_prelive.py.bak_liquidez_none; validado com ast.parse; bot-betfair.service reiniciado 00:02:39 UTC (12/08) sem erro; commit 81d0914, push feito.
- Falso-positivo do watchdog (prioridade menor): watchdog_bot.sh (cron a cada 5min) disparou "TRAVAMENTO SILENCIOSO" 9x seguidas entre 21:15-21:55 UTC (11/08) com o bot saudavel (mudo ha 0min a cada checagem), so porque LIMITE_SEM_ANALISE_MIN=90 era curto demais pra horarios de baixo volume de jogos elegiveis.
- Fix: LIMITE_SEM_ANALISE_MIN alterado de 90 para 180 minutos (watchdog_bot.sh, linha 11); backup watchdog_bot.sh.bak_limite180; validado com bash -n; script roda via cron (nao systemd), efeito imediato no proximo ciclo, sem necessidade de restart; commit a56178c, push feito.
- Contexto separado (mesma sessao): fix em resultado_jogos.py -- cache de nome de runner via info.get('runners_cs_map') antes de chamar buscar_nome_runner_vencedor() (evita chamada de API redundante), e protecao contra pnl_estimado is None no print verbose (formata "N/A" em vez de estourar TypeError). Commit a20297f (junto com o modo sombra de filtros candidatos). Rebase sobre origin/main trouxe 2 commits paralelos sem conflito: refactor do bot_under25.py e remocao do robo2.py legado. Push final 2c2ec91.
- Estado atual: main sincronizado com origin/main, bot-betfair.service ativo sem erros, watchdog com limiar ajustado. Pendencia antiga do modo sombra continua aberta: aguardar volume suficiente pra rodar avaliar_filtros_sombra.sql.

## Atualização 13/08/2026 — Bloqueio de conta Betfair por rajada de login + keep-alive implementado

- **Sintoma**: conta Betfair bloqueada (login manual no site/app retornando "conta bloqueada/suspensa temporariamente"), coincidindo com sessão da Betfair expirando perto de ~23h de conexão.
- **Causa raiz confirmada via journalctl** (`bot-betfair.service`, 23:09:42 UTC): quando a sessão expira, `chamar_api()` batia em `INVALID_SESSION_INFORMATION`, chamava `login()` dentro do próprio retry loop — mas o dict `headers` era montado **uma vez antes do loop**, então mesmo após `login()` buscar um token novo e válido, a tentativa seguinte reenviava com o token velho, falhando de novo e disparando outro `login()`. Isso se repetia jogo a jogo na fila, gerando uma rajada de POSTs de login reais em sequência apertada — padrão que a Betfair identifica como "tráfego incomum" e bloqueia (confirmado via docs oficiais: TEMPORARY_BAN_TOO_MANY_REQUESTS / lock de segurança por excesso de tentativas).
- **Confirmado via docs oficiais da Betfair**: sessão expira num prazo fixo a partir do login (não é "hora do dia", é relógio por sessão — até 12h pra maioria dos mercados internacionais hoje, pode variar pro regulado BR) e **não se renova sozinha por atividade da API** — é preciso chamar o endpoint Keep-Alive explicitamente. O bot não fazia isso, só relogava por completo a cada 2h (LAY) / 6h (Under25) ou reativamente após falha.
- **Descartada hipótese de disputa de sessão entre os dois bots**: docs da Betfair confirmam que múltiplas sessões podem ficar ativas simultaneamente pra mesma conta — não é a causa.
- **Fix aplicado em `betfair_client.py` (LAY, `~/bot-prelive-betfair/`)**:
  - Nova função `keep_alive()` (POST em `/api/keepAlive`), chamada proativamente a cada `KEEP_ALIVE_INTERVALO_HORAS=4` via `renovar_token_se_necessario()`, evitando que a sessão chegue a expirar de verdade em uso normal.
  - Bug do `headers` estático corrigido em `chamar_api()`: dict agora é remontado a cada tentativa do retry loop, sempre lendo o `SESSION_TOKEN` global atual.
  - Circuit breaker em `login()`: após `LOGIN_CIRCUIT_BREAKER_LIMITE=3` falhas consecutivas de login real, ativa `CIRCUIT_BREAKER_ATIVO_ATE` (pausa de `LOGIN_CIRCUIT_BREAKER_COOLDOWN_SEGUNDOS=600`s = 10min) sem tentar mais logins nesse intervalo, e manda alerta via Telegram (`enviar_mensagem`). `chamar_api()` também respeita o circuit breaker (retorna `None`/`[]` cedo em vez de tentar).
  - Backup: `betfair_client.py.bak_keepalive_circuitbreaker`. Validado com `ast.parse` e `import betfair_client` sem erro.
- **Fix replicado no Under25 (`~/bot-under25/betfair_client.py`)**, adaptado pra essa versão mais simples do arquivo (sem `saude.py`, cooldown de login e timeout no `requests`/`urlopen` que não existiam antes):
  - Mesmo padrão de `keep_alive()`, circuit breaker e headers dinâmicos.
  - Bônus: `chamar_api()` do Under25 antes **não tratava `INVALID_SESSION` nem tinha timeout** — silenciosamente retornava `[]` em qualquer erro, podendo ficar "cego" por até 6h sem log de aviso. Agora trata sessão inválida explicitamente, tem timeout=15s e retry com backoff, igual ao LAY.
  - Backup: `betfair_client.py.bak_keepalive_circuitbreaker` na pasta do Under25.
- **Pendência de validação**: reiniciar os dois serviços e observar por alguns dias se o keep-alive elimina o ciclo de expiração perto das ~23h e se o circuit breaker nunca chega a disparar em uso normal (só deve disparar em cenário real de problema, não em operação saudável).
- **Pendência antiga que ficou mais urgente**: `betfair_client.py` segue duplicado entre os dois bots com histórico de divergir silenciosamente (Under25 estava numa versão bem mais antiga/frágil até este patch) — reforça a ideia já registrada de migrar pra um módulo compartilhado entre os dois bots.

## Atualização 14/08/2026 — Início da migração para módulo betfair_client compartilhado (EM ANDAMENTO)

- Motivação: pendência antiga de betfair_client.py duplicado entre os dois bots (com historico de divergir silenciosamente) resolvida via extracao pra pacote Python compartilhado em ~/shared/betfair_client/, instalavel via pip nos dois bots, mantendo o mesmo nome de modulo (import betfair_client continua funcionando sem editar bot_prelive.py/bot_under25.py).
- Pacote criado com pyproject.toml (setuptools>=64, PEP 660) + betfair_client/__init__.py (273 linhas, copia fiel da versao LAY -- mais completa, ja com saude.py e circuit breaker/keep-alive validados em 13/08). Adaptacoes: import de saude vira no-op se o modulo nao existir (cobre o caso do Under25, que nao tem saude.py), fallback de env vars legados (EMAIL/SENHA/APP_KEY do Under25, alem de BETFAIR_USERNAME/PASSWORD/APP_KEY do LAY), nova env var opcional BOT_NOME pras mensagens de circuit breaker no Telegram distinguirem LAY/Under25.
- Nenhum dos dois bots roda em venv -- ambos usam pip3/python3 do sistema (--user install), entao a instalacao do pacote fica automaticamente compartilhada entre os dois, sem precisar repetir por bot.
- Troubleshooting durante a instalacao: erro inicial "build backend missing build_editable hook" (pyproject pedia setuptools>=61, PEP 660 exige >=64 -- corrigido). Instalacao em modo editavel (-e) continuou falhando mesmo apos corrigir e atualizar o setuptools do sistema; contornado usando instalacao normal (sem -e). Primeira tentativa criou um pacote fantasma chamado "UNKNOWN" (nome do projeto nao foi lido do pyproject.toml), provavelmente por reaproveitar cache de build (pastas build/ e UNKNOWN.egg-info) de uma tentativa anterior ao fix do setuptools -- resolvido limpando esses diretorios e reinstalando com --no-cache-dir.
- Pendente: confirmar "import betfair_client" funcionando com o nome certo (nao mais "UNKNOWN") apos a limpeza de cache; depois disso, renomear os betfair_client.py locais de cada bot pra .local_desativado e reiniciar os dois servicos um de cada vez, conferindo login/keep-alive no journalctl antes de seguir pro segundo.
- Rollback disponivel: os betfair_client.py originais foram preservados como backup (.bak_shared_migration_*) antes de qualquer mudanca, nada foi apagado.

## Atualização 14/08/2026 (cont.) — Migração para módulo betfair_client compartilhado CONCLUÍDA

- Causa raiz do pacote instalando como "UNKNOWN": setuptools 84.0.0 chamava canonicalize_version(..., strip_trailing_zero=...), parâmetro novo não suportado pelo `packaging` desatualizado instalado no ambiente do usuário (aviso "Could not find an up-to-date installation of packaging" já aparecia antes e passou despercebido). Fix: pip3 install --user --upgrade "packaging>=24.2" (26.3 instalado). Após isso, pip3 install --user --no-cache-dir --no-build-isolation . instalou corretamente como betfair-client 0.1.0.
- Confirmado via `python3 -c "import betfair_client; print(betfair_client.__file__)"` fora de qualquer pasta de bot: resolve para ~/.local/lib/python3.10/site-packages/betfair_client/__init__.py.
- betfair_client.py local renomeado para .local_desativado nos dois bots (~/bot-prelive-betfair/ e ~/bot-under25/), forçando o uso do pacote compartilhado.
- Bot LAY (bot-betfair.service) reiniciado 01:23:34 UTC: login OK, busca de mercados OK (12 mercados CS), sem erros no journal.
- Bot Under25 (bot-under25.service) reiniciado 01:26:07 UTC: fallback de env vars legados (EMAIL/SENHA/APP_KEY) disparou corretamente (esperado, .env do Under25 não foi migrado pros nomes novos), login OK, busca de mercados ao vivo OK (7 mercados), sem erros no journal. Esse restart também foi o primeiro teste real em produção do timeout=15s + tratamento de INVALID_SESSION que o Under25 nunca teve antes da migração.
- Rollback disponível: betfair_client.py.local_desativado em cada pasta de bot, mais os .bak_shared_migration_* já existentes.
- Pendente: observar por alguns dias se o keep-alive (KEEP_ALIVE_INTERVALO_HORAS=4) elimina o ciclo de expiração de sessão perto das ~23h que causou o bloqueio de conta em 13/08, e se o circuit breaker nunca dispara em uso normal.

## Atualização 14/08/2026 (cont.) — RLS: brecha de escrita publica em apostas corrigida + modo sombra validado (volume ainda baixo)

- Verificacao completa via Supabase MCP: RLS ja estava ativo (rowsecurity=true) nas 12 tabelas do projeto, incluindo as 4 que estavam registradas como pendentes (apostas, metricas, historical_odds, resultados_reais).
- Achado: metricas, historical_odds e resultados_reais ja tinham politica correta (SELECT publico, sem escrita liberada). Mas apostas tinha uma politica "permitir tudo apostas" com cmd=ALL e qual=true para role public -- ou seja, qualquer chave anon podia ler, inserir, alterar ou apagar apostas livremente. Pior que a pendencia original registrada (nao era so "RLS desativado", era RLS ativo com policy totalmente aberta em escrita).
- Fix aplicado (migration restringe_escrita_publica_apostas via Supabase MCP): DROP da policy "permitir tudo apostas", criada policy "Leitura publica" (FOR SELECT USING true), mesmo padrao das outras 3 tabelas. Confirmado via curl com SUPABASE_SERVICE_KEY (HTTP 200 em GET /apostas) que a escrita/leitura do bot via service_role nao foi afetada (service_role sempre ignora RLS).
- Modo sombra (pendencia separada, checada na mesma sessao): mecanica confirmada funcionando desde o restart de 11/08 23:35 UTC (nao e bug -- os registros nulos encontrados eram todos anteriores ao restart, confirmado via query filtrando por analisado_em). Volume real pos-restart: so 4 analises com odd_favorito preenchido em 3 dias (55 aprovadas no total, mas a maioria reprova antes de chegar no calculo de odd_favorito). Nenhuma flag chega perto de N>=30 ainda -- continua cedo demais para avaliar_filtros_sombra.sql.

## Atualização 14/08/2026 (cont.) — Migração betfair_client compartilhado CONCLUÍDA + acesso Termius resolvido

- Causa raiz do pacote instalando como "UNKNOWN": setuptools 84.0.0 chamava canonicalize_version(..., strip_trailing_zero=...), parametro novo nao suportado pelo `packaging` desatualizado no ambiente do usuario. Fix: pip3 install --user --upgrade "packaging>=24.2" (26.3 instalado), depois pip3 install --user --no-cache-dir --no-build-isolation . instalou corretamente como betfair-client 0.1.0.
- betfair_client.py local renomeado para .local_desativado nos dois bots, forcando uso do pacote compartilhado (~/.local/lib/python3.10/site-packages/betfair_client/__init__.py). Confirmado com `python3 -c "import betfair_client; print(betfair_client.__file__)"` fora de qualquer pasta de bot.
- Bot LAY reiniciado 01:23:34 UTC: login OK, busca de mercados OK, sem erros.
- Bot Under25 reiniciado 01:26:07 UTC: fallback de env vars legados (EMAIL/SENHA/APP_KEY) disparou corretamente (esperado), login OK, mercados ao vivo OK, sem erros. Primeiro teste real em producao do timeout=15s + tratamento de INVALID_SESSION que o Under25 nunca teve antes.
- Rollback disponivel: betfair_client.py.local_desativado em cada pasta, mais os .bak_shared_migration_* ja existentes.
- Pendente: observar por alguns dias se o keep-alive elimina o ciclo de expiracao de sessao perto das ~23h (motivo original da migracao) e se o circuit breaker nunca dispara em uso normal.
- Acesso Termius quebrado (Permission denied publickey) resolvido: nao era problema de chave (chave publica estava correta no authorized_keys, so duplicada 3x, limpo com sort -u) nem de permissao de arquivo (700/600 corretos). Causa real: campo Username no Termius tinha espaco em branco antes de "ubuntu" (visivel no log como "Invalid user         ubuntu"), rejeitado pelo sshd. Fix: usuario redigitado manualmente sem colar, sem espaco. Diagnostico feito via Oracle Cloud Console (Compute > Instance > OS Management > Console connection > Cloud Shell), usado como acesso de emergencia quando nenhum terminal SSH estava disponivel.
- Nota de seguranca observada (nao endereçada ainda): auth.log mostra tentativas constantes de forca bruta de multiplos IPs (usuarios root, deploy, zzg, indra, toto, tomcat, minecraft, huake). Comum em VPS com IP publico exposto, mas sshd_config esta com PasswordAuthentication comentado (usando default do sistema, nao explicitamente "no"). Considerar endurecer explicitamente (PasswordAuthentication no) e/ou instalar fail2ban.

## Atualização 14/08/2026 (cont.) — Crash-loop do Under25 + shadowing do betfair_client local + rastreamento de sessão

- **Sintoma inicial**: `bot-under25.service` em crash-loop (restart counter subindo a cada ~30s) com `ModuleNotFoundError: No module named 'betfair_client'`. Investigação revelou que o pacote `betfair-client` instalado na migração de mais cedo (14/08) havia sumido do ambiente do usuário (`pip3 show betfair-client` → not found), causa raiz ainda não identificada.
- **Fix imediato**: pacote reinstalado com o mesmo procedimento de contorno já usado na migração original — `rm -rf build/ *.egg-info/`, `pip3 install --user --upgrade "packaging>=24.2"`, depois `pip3 install --user --no-cache-dir --no-build-isolation .` (modo editável `-e .` continua falhando, mesmo problema de antes). `import betfair_client` confirmado resolvendo para o site-packages.
- **Bug descoberto durante a validação — shadowing silencioso**: mesmo com o pacote reinstalado e funcional, `import betfair_client` de dentro de `~/bot-prelive-betfair/` continuava resolvendo para o `betfair_client.py` local da pasta (versão de 13/08, copiada de volta durante o troubleshooting do crash), porque o diretório de trabalho do processo entra no `sys.path` antes do site-packages `--user`. Isso fazia os bots rodarem uma versão desatualizada do client sem nenhum erro visível — o problema só foi percebido porque uma feature nova (rastreamento de sessão, ver abaixo) simplesmente não tinha efeito nenhum, sem log de erro.
  - Fix: `mv ~/bot-prelive-betfair/betfair_client.py ~/bot-prelive-betfair/betfair_client.py.local_desativado_v2`, forçando resolução para o pacote compartilhado de novo. Confirmado com `python3 -c "import betfair_client; print(betfair_client.__file__)"` apontando para `/home/ubuntu/.local/lib/python3.10/site-packages/betfair_client/__init__.py`.
  - **Lição**: qualquer arquivo `.py` solto com o mesmo nome do pacote, na `WorkingDirectory` de um serviço que usa `import` simples (sem path absoluto), sombreia o pacote instalado sem aviso nenhum. Reforça a necessidade de manter só o `.local_desativado` como backup nas pastas dos bots, nunca o nome ativo `betfair_client.py`, enquanto o pacote compartilhado estiver em uso.
- **Circuit breaker validado**: confirmado via journalctl que só disparou durante a instabilidade do cutover da migração original (madrugada de 14/08, ~02:56 LAY e ~03:34 Under25) e não repetiu depois — comportamento correto, contendo rajadas de login sem deixar escalar para bloqueio de conta como em 13/08.
- **Feature nova: rastreamento de sessão Betfair (`sessao_betfair`)** — motivada pela tentativa de confirmar se o keep-alive (editado nesta sessão, ver nota abaixo) está evitando a expiração perto das ~23h que causou o bloqueio de conta em 13/08.
  - Tabela `sessao_betfair` criada no Supabase via MCP (`id` fixo=1, `iniciada_em`, `atualizada_em`, `bot_origem`), RLS ativo com policy de leitura pública, mesmo padrão das outras tabelas.
  - `registrar_sessao_betfair(inicio)` em `supabase_integration.py`: grava/atualiza a linha única via upsert, incluindo `bot_origem` (lido de `os.getenv('SUPABASE_BOT_ID')`, que já é exportado corretamente por bot — `7449c515...` fixo no `.env` para o LAY, `4101d27c...` exportado explicitamente por `start_under25.sh` para o Under25).
  - `obter_sessao_betfair()` em `supabase_integration.py`: leitura simples da linha `id=1`.
  - No pacote compartilhado (`~/shared/betfair_client/betfair_client/__init__.py`), dentro de `login()`: quando `SESSAO_INICIADA_EM is None` (ou seja, sessão genuinamente nova, não uma renovação de token), chama `_sb.registrar_sessao_betfair(SESSAO_INICIADA_EM)` — reseta para `None` de novo em `logout()`.
  - Comando `/sessao` adicionado em `telegram_commands.py` (linha ~796): calcula horas decorridas desde `iniciada_em` e quanto falta para o limite de 23h, com emoji de status (verde >2h de folga, amarelo perto do limite, vermelho passou do limite).
  - Validado em produção: `POST /rest/v1/sessao_betfair` retornando 200/201 nos logs dos dois bots, tabela confirmada com dado real via query direta.
- **Nota separada — mudança no keep-alive**: usuário editou `KEEP_ALIVE_INTERVALO_HORAS` (ou lógica correlata) diretamente em `~/shared/betfair_client/betfair_client/__init__.py` durante o troubleshooting, buscando forçar reconexão mais cedo e "resetar a contagem" antes do limite de ~23h da Betfair. Como essa edição só existia no arquivo-fonte (nunca tinha sido reinstalada) e o shadowing do `betfair_client.py` local também mascarava qualquer versão do pacote, a mudança só entrou de fato em produção após a reinstalação do pacote + remoção do arquivo local nesta sessão. **Pendente**: observar nos próximos dias via `/sessao` se a mudança reduz/elimina o padrão de expiração perto das ~23h.
- **Limpeza**: `~/bot-under25/` (pasta antiga, não referenciada por nenhum unit file, cron ou script — os dois serviços rodam de `WorkingDirectory=/home/ubuntu/bot-prelive-betfair`) arquivada para `~/bot-under25.arquivado_20260814/` em vez de apagada, por segurança.
- **Pendências que seguem abertas**:
  - Causa raiz de por que o pacote `betfair-client` sumiu do ambiente `--user` em primeiro lugar — ainda não investigada.
  - Confirmar nos próximos dias, via `/sessao`, se a mudança no keep-alive evita a expiração perto das ~23h.
  - Scripts soltos em `~/` (`apply_retry_fix.py`, `apply_telegram_timeout.py`, `apply_timeout_fix.py`, `patch_event_id.py`, `patch_resultado_jogos.py`) — não investigados, possível limpeza futura.
  - Seguem em aberto de sessões anteriores: confirmar `gemini-flash-latest` vetando de verdade, medir consumo real de API Betfair do dia, rotacionar chaves expostas em chat, endurecer SSH (`PasswordAuthentication no`) / instalar fail2ban.

*Ultima atualizacao: 14/08/2026*

## Atualização 15/08/2026 00:59
- Bug crítico corrigido: apostas travadas em PENDENTE causadas por 'NoneType' object has no attribute 'replace' em resumo_resultados() (resultado_jogos.py:288, info.get('resultado_geral', '') não protegia contra None explícito); fix result = info.get('resultado_geral') or ''; validado em produção (9 apostas resolvidas). SSH endurecido: PasswordAuthentication no + fail2ban ativo na jail sshd. Pendente: reboot do VPS para aplicar kernel novo (sem urgência).

## Atualização 15/08/2026 01:20
- Melhorias dashboard (Timedina/betbots-dashboard): item 3 (Realtime) descartado por ora, exigiria trocar fetch() REST cru pela lib @supabase/supabase-js (Realtime usa WebSocket); polling 30s considerado suficiente. Item 5 (badges visuais no_limite/sombra_*) CONCLUÍDO: componente FlagBadges na coluna Status da aba Analises, badge âmbar 'No limite' + badge azul 'Sombra (N)' com tooltips; commit 0adf0eb, push feito, build validado. Item 4 (virtualização) pulado: tabela já limitada a 200 linhas via query, sem ganho real hoje. Próximo: item 6 (filtros persistidos na URL), depois item 7 (drill-down segmentação).

## Atualização 16/08/2026 04:35
- Backtest do filtro RAZAO_ODD_MAXIMA=1.7 + ODD_01_MINIMA=18.5: rejeitado. Subir a odd mínima de 18 pra 18,5 cortaria 5 apostas (todas vitórias, +27,55u) sem evitar nenhuma das 3 perdas do período — RAZAO_ODD_MAXIMA=1.7 e ODD_01_MINIMA=18 mantidos como estão.
- Varredura de correlação (189 apostas resolvidas do bot LAY, 13 perdas / 176 vitórias) pra testar hipótese de pontuação ponderada com peso em odd_over15: odd_over15, razão, odd_01, odd_favorito, odd_btts e liquidez_disponivel NÃO mostraram poder discriminante real (médias/win-rate por faixa praticamente idênticos entre vitória e perda) — descartado dar peso a essas variáveis.
- Único sinal real encontrado: `minuto=-10` (entrada pré-jogo, 10 min antes do kickoff) e `no_limite=true` (aprovação limítrofe nos filtros). Testado isoladamente e combinado:
  - Baseline (189 apostas): 93.1% win rate, PnL -273.26u
  - Excluir minuto=-10: 94.3%, PnL -35.26u
  - Excluir no_limite=true: 94.6%, PnL +46.58u
  - Excluir os dois: 95.9%, PnL +211.20u (n cai pra 122, -35% de volume)
- Implementado sistema de classificação de confiança (`confianca.py`, novo arquivo em `~/bot-prelive-betfair/`) com 4 grupos baseados em win rate histórico real (A=96% n=116, B=91% n=53, C=75% n=8 amostra pequena, D=83% n=6 amostra pequena). Função `classificar_confianca(minuto, no_limite)` retorna grupo/label/pct/n_amostra; `formatar_para_telegram()` formata a linha com emoji e aviso quando a amostra é pequena.
- Migration aplicada no Supabase (`add_confianca_columns_to_analises`): colunas `confianca_grupo` (text) e `confianca_pct` (integer) adicionadas em `analises`.
- Patches aplicados via Python script com anchor de segurança (aborta se anchor não encontrado ou duplicado), com backup automático antes de cada edição (`bot_prelive.py.bak_*`, `supabase_integration.py.bak_*`):
  - `bot_prelive.py` (linha ~1347): chama `classificar_confianca()` logo após `resultado['no_limite_detalhes']` ser definido, grava `resultado['confianca_grupo']` e `resultado['confianca_pct']`.
  - `supabase_integration.py` (linha ~127): grava os dois campos no insert de `analises`.
- `py_compile` validado sem erro nos dois arquivos. Serviço `bot-betfair.service` reiniciado às 07:31 UTC, log limpo (sem traceback, fila normal 264 aguardando).
- **Pendente**: confirmar via Supabase, após o próximo ciclo de análise (~04:55 local / 07:55 UTC), que `confianca_grupo`/`confianca_pct` estão sendo gravados corretamente nas novas análises.
- **Pendente futuro**: expor `confianca` na mensagem do Telegram (`formatar_para_telegram()` já pronta, falta plugar no ponto de envio de alerta de aposta) e criar badge no dashboard (Timedina/betbots-dashboard) similar ao `FlagBadges` existente.
- Nota: grupos C e D (minuto=-10) têm amostra pequena (n=8 e n=6) — reavaliar os percentuais quando a base tiver mais uns 50+ apostas novas resolvidas.


## Atualização 19/08/2026 — Confiança no Telegram (LAY) + bug critico de sessao_betfair (singleton) + causa raiz do bloqueio de conta ~23h

- **Confianca no alerta do Telegram (LAY)**: `formatar_para_telegram()` (ja existente em `confianca.py`) plugada em `formatar_alerta()` (`bot_prelive.py`). Import de `classificar_confianca`/`formatar_para_telegram` adicionado, chamada inserida logo apos `ia_str` (usa `minutos` e `info.get('no_limite')` ja disponiveis no dict, sem depender de campos extras gravados no Supabase), linha de confianca inserida no corpo do alerta entre `market_id_cs` e o rodape de monitoramento. Backup: `bot_prelive.py.bak_confianca_telegram_*`. Validado com `ast.parse`/`py_compile`, restart sem erro.
- **Decisao**: sistema de confianca (grupos A-D) fica exclusivo do bot LAY — os win rates foram calibrados sobre o historico dele; nao sera replicado para o Under25 sem recalibrar.
- **Confirmado via Supabase** (antes do plug no Telegram): `confianca_grupo`/`confianca_pct` gravando corretamente em 100% das analises aprovadas do LAY desde o restart de 16/08 (24/24). As ~4000 analises sem o campo preenchido no periodo sao todas reprovacoes (nunca chegam no ponto do calculo) ou aprovacoes do Under25 (bot que nao usa esse sistema, por decisao acima) — nao e bug.

- **Bug critico descoberto: `sessao_betfair` era tabela singleton (`id=1` fixo + `CHECK (id=1)`)**. LAY e Under25 sobrescreviam o registro de sessao um do outro a cada login, tornando o comando `/sessao` (e qualquer analise de duracao de sessao) nao confiavel havia dias — o dado mostrado podia ser de qualquer um dos dois bots, dependendo de quem logou por ultimo.
  - Fix em 2 migrations via Supabase MCP: (1) `sessao_betfair_por_bot` — dropada a constraint singleton e a PK antiga em `id`, nova PK em `bot_origem` (uma linha por bot agora), `NOTIFY pgrst reload schema`. (2) `sessao_betfair_fix_id_nullable` — a migration 1 deixou a coluna `id` orfa com `NOT NULL` sem `DEFAULT`, quebrando o insert do Under25 (`null value in column "id"`); corrigido tornando `id` nullable (coluna morta, mantida so por historico/nao quebrar leituras antigas).
  - Fix em `supabase_integration.py`: `registrar_sessao_betfair()`/`obter_sessao_betfair()` reescritas para upsert/select por `bot_origem` (`on_conflict='bot_origem'`) em vez de `id=1`. Backup: `supabase_integration.py.bak_sessao_por_bot_*`.
  - **Bug secundario no proprio patch**: primeira versao usava `os.getenv('SUPABASE_BOT_ID')` lido em runtime — retornou o ID do LAY mesmo rodando no processo do Under25 (confirmado: Under25 gravou a sessao com `bot_origem` do LAY). Causa: `supabase_integration.py` define `SUPABASE_BOT_ID` como variavel de MODULO, lida do `os.getenv()` uma unica vez no import; `bot_under25.py` sobrescreve essa variavel do modulo (`sb.SUPABASE_BOT_ID = "4101d27c..."`) logo no startup — padrao ja documentado e corrigido antes em outro ponto do codigo (comentario "FIX 13/08" na linha ~247), mas que eu reintroduzi por reler `os.getenv()` direto em vez de usar a variavel do modulo. Corrigido para `os.getenv('SUPABASE_BOT_ID_OVERRIDE', SUPABASE_BOT_ID)`, mesmo padrao da linha 247. Backup: `supabase_integration.py.bak_fix_bot_id_source_*`.
  - Validado apos o fix: tabela com 2 linhas separadas, `bot_origem` batendo corretamente com cada bot (LAY e Under25 logaram simultaneamente no restart de teste e cada um gravou sua propria linha).
  - **View de monitoramento criada** (`v_status_sessao_betfair`, via Supabase MCP): mostra `bot` (nome legivel), `horas_decorridas`, `horas_restantes_limite` (ate 23h) e `status` (OK/ATENCAO >=19h/CRITICO >=21h/VENCIDO >=23h) por bot, para acompanhar e comparar LAY x Under25 ao longo do dia.

- **Causa raiz provavel do bloqueio de conta perto das ~23h (recorrente, ja visto em 13/08)**: `bf.renovar_token_se_necessario()` (keep-alive proativo, `KEEP_ALIVE_INTERVALO_HORAS=4` no pacote compartilhado `betfair_client`) **nunca era chamado no loop principal do bot LAY** (`bot_prelive.py`) — so o Under25 chamava, a cada iteracao do `while True`. O LAY dependia 100% do relogin reativo (so ao detectar `INVALID_SESSION` em `chamar_api()`), reproduzindo o mesmo padrao de rajada de login perto do limite de sessao que gerou o bloqueio de conta original em 13/08 — o fix de keep-alive daquela data nunca chegou a proteger o LAY de verdade, so o Under25.
  - Fix: `bf.renovar_token_se_necessario()` adicionado como primeira chamada dentro do `while True:` de `rodar_bot()` em `bot_prelive.py`, mesmo padrao ja usado em `bot_under25.py`. Backup: `bot_prelive.py.bak_keepalive_lay_*`.
  - Validado: `ast.parse`/`py_compile` OK, `bot-betfair.service` reiniciado 23:36 UTC sem erro no journal.
  - **Nota de investigacao**: a suspeita inicial era o oposto (Under25 ficando conectado tempo demais) — na verdade era o LAY que estava desprotegido. A tabela `sessao_betfair` quebrada (ver acima) provavelmente mascarou isso por dias, ja que o `/sessao` podia estar mostrando o dado do bot errado.
  - **Pendente**: observar as proximas ~23h via `v_status_sessao_betfair` / `/sessao` para confirmar que o LAY nao bate mais em VENCIDO/bloqueio de conta com o keep-alive ativo nos dois bots agora.

- **Pendencia aberta, ainda nao testada** (arrastada desde 07/08): confirmar se `watchdog_bot.sh` (restart se journal mudo por `LIMITE_MUDO_MIN=5min`) religa o bot automaticamente durante uma pausa manual via `/pausar` — o script nao tem nenhuma logica hoje para diferenciar silencio por pausa intencional de travamento real.
- **Nao critico, decidir depois**: linha orfa em `sessao_betfair` com `bot_origem` do LAY mas timestamp do momento em que o Under25 tentou gravar (do periodo em que o bug de `os.getenv` ainda estava ativo) — foi sobrescrita pelo upsert correto depois do fix, nao precisa de limpeza manual.

*Ultima atualizacao: 19/08/2026*
