# Contexto da sessão 13/08/2026 — Bug bot_id/odd_01=null no Under25 (RESOLVIDO)

## Sintoma original
Jogos aprovados do bot Under25 estavam sendo gravados na tabela `analises` com o
`bot_id` do bot LAY (7449c515-4a4e-4ad3-acda-32916034e9c1) em vez do próprio ID
(4101d27c-2130-4517-b596-3969cf06f049). Isso quebrava estatisticas/dashboard/PnL
por bot. Padrão: `motivos` no formato `["odd=X.XX", "min=N"]`, `odd_01=null`.

## Investigação (resumo)
Descartadas, uma a uma, com evidência:
- load_dotenv com override: não existe nenhum load_dotenv em bot_under25.py nem
  supabase_integration.py.
- Env do processo errado: `/proc/PID/environ` mostrou SUPABASE_BOT_ID correto
  (4101d27c...) no processo rodando, mesmo assim os inserts saíam com o ID do LAY.
- Cópia duplicada do projeto (`/home/ubuntu/bot-under25/`, versão antiga de 28/06,
  não usada pelo processo real — cwd/PWD confirmados como
  `/home/ubuntu/bot-prelive-betfair`).
- DEFAULT ou trigger na coluna `bot_id` da tabela `analises` no Postgres: nenhum
  dos dois existe.
- .pyc desatualizado em cache: mtime do .py e .pyc eram de 11-12/08, bem antes do
  processo iniciar em 13/08 05:00 — não é bytecode obsoleto.
- SUPABASE_BOT_ID_OVERRIDE: não existe no .env.

Causa raiz exata não ficou 100% confirmada (o comportamento contradizia o código
lido em disco), mas a hipótese mais provável é uma interação sutil entre a cadeia
de env vars (SUPABASE_BOT_ID_UNDER25 -> if SB_BOT_ID: -> sb.SUPABASE_BOT_ID) que
nunca disparava (a env var SUPABASE_BOT_ID_UNDER25 nunca existiu, só
SUPABASE_BOT_ID no .env compartilhado, que é do LAY) combinada com alguma leitura
indireta ainda não identificada.

## Fix aplicado (elimina o sintoma, independente da causa raiz)
1. bot_under25.py: substituída a lógica condicional por atribuição direta e
   incondicional:
   sb.SUPABASE_BOT_ID = "4101d27c-2130-4517-b596-3969cf06f049"
   print(f"[STARTUP] bot_id fixado: {sb.SUPABASE_BOT_ID}", flush=True)

2. supabase_integration.py, função carregar_filtros() (linha ~212): trocado
   bot_id_atual = os.getenv('SUPABASE_BOT_ID_OVERRIDE', os.getenv('SUPABASE_BOT_ID', SUPABASE_BOT_ID))
   por
   bot_id_atual = os.getenv('SUPABASE_BOT_ID_OVERRIDE', SUPABASE_BOT_ID)

   Isso corrigiu um bug secundário descoberto durante a investigação: o Under25
   estava carregando os filtros (odd mín/máx, liquidez mínima) do bot LAY em vez
   dos próprios. Confirmado no log: antes odd=1.8-2.1 liq=150.0 (do LAY), depois
   do fix odd=1.8-2.0 liq=100.0 (do Under25).

Backups: bot_under25.py.bak_13ago e supabase_integration.py.bak_13ago na pasta
do projeto.

## Estado após o fix
Processo reiniciado e confirmado rodando limpo (PID único), log mostra
[STARTUP] bot_id fixado: 4101d27c-... e a query de filtros já usando o bot_id
correto. Ainda não havia nenhum jogo aprovado/reprovado gerado desde o restart
no momento em que a sessão terminou (jogos ao vivo estavam todos fora da janela
de minutos aceita pelo filtro entrada<5min) — falta confirmar com um registro
real na tabela analises que o bot_id sai correto em produção.

## Pendente pra próxima sessão
- Confirmar no Supabase que o próximo aprovado do Under25 sai com
  bot_id=4101d27c-...
- Commitar e dar push nos dois patches (bot_under25.py, supabase_integration.py)
  junto com o que já estava pendente de antes (resultado_jogos.py, patches de
  shadow flags, deletar upabase_integration.py mal-nomeado).
- RLS ainda desligado em: apostas, metricas, historical_odds, resultados_reais.
  SQL de correção já pronto no CONTEXT.md original.
- Modo sombra: campos sombra_* quase não sendo preenchidos desde o deploy
  (11/08 23:35 UTC) — investigação não iniciada.

*Sessão em 13/08/2026*
