#!/bin/bash
# ~/bot-prelive-betfair/watchdog_bot.sh
# Reinicia bot-betfair.service se detectar travamento (total ou silencioso)
# e avisa no Telegram sempre que reiniciar por travamento.
#
# 21/08: adicionado dedupe de alertas -- antes, se a fila de jogos ficasse
# vazia por muitas horas (ex: madrugada), o watchdog reiniciava E alertava
# a CADA ciclo de cron (5 em 5 min) enquanto a lacuna sem /analises seguia
# crescendo, gerando uma rajada de mensagens identicas no Telegram sem
# nenhum ganho real (reiniciar nao cria jogo novo pra analisar). Agora so
# reage de novo quando uma analise NOVA acontecer e DEPOIS ficar silencioso
# de novo (incidente genuinamente diferente), usando um arquivo de estado
# com o timestamp da ultima analise ja tratada.

SERVICE="bot-betfair.service"
LOG_FILE="/home/ubuntu/bot-prelive-betfair/watchdog.log"
ENV_FILE="/home/ubuntu/bot-prelive-betfair/.env"
STATE_FILE="/home/ubuntu/bot-prelive-betfair/.watchdog_silencioso_ts"

LIMITE_MUDO_MIN=5
LIMITE_SEM_ANALISE_MIN=180

# Carrega TELEGRAM_TOKEN/TELEGRAM_CHAT_ID do .env sem expor no processo
TELEGRAM_TOKEN=$(grep -E "^TELEGRAM_TOKEN=" "$ENV_FILE" | cut -d= -f2-)
TELEGRAM_CHAT_ID=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENV_FILE" | cut -d= -f2-)

agora=$(date +%s)
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"; }

alertar_telegram() {
    local msg="$1"
    if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s --max-time 10 -X POST \
            "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${msg}" \
            -d "parse_mode=Markdown" > /dev/null
    fi
}

ultima_linha_ts=$(journalctl -u "$SERVICE" -n 1 --no-pager -o short-unix 2>/dev/null | awk '{print $1}' | cut -d. -f1)

if [ -z "$ultima_linha_ts" ]; then
    log "ALERTA: não consegui ler journalctl — pulando ciclo"
    exit 1
fi

diff_mudo_min=$(( (agora - ultima_linha_ts) / 60 ))

if [ "$diff_mudo_min" -ge "$LIMITE_MUDO_MIN" ]; then
    log "TRAVAMENTO TOTAL detectado: sem nenhum log há ${diff_mudo_min}min. Reiniciando $SERVICE..."
    alertar_telegram "🐛 *Watchdog*: bot-betfair travado (mudo há ${diff_mudo_min}min). Reiniciando agora..."
    sudo systemctl restart "$SERVICE"
    sleep 5
    status=$(systemctl is-active $SERVICE)
    log "Restart executado. Status: $status"
    alertar_telegram "✅ *Watchdog*: restart concluído. Status: ${status}"
    exit 0
fi

ultima_analise_ts=$(journalctl -u "$SERVICE" --no-pager -o short-unix 2>/dev/null \
    | grep "rest/v1/analises" | tail -1 | awk '{print $1}' | cut -d. -f1)

if [ -z "$ultima_analise_ts" ]; then
    log "AVISO: nenhum POST /analises encontrado no journal disponível — sem baseline, pulando checagem 2"
    exit 0
fi

diff_analise_min=$(( (agora - ultima_analise_ts) / 60 ))

if [ "$diff_analise_min" -ge "$LIMITE_SEM_ANALISE_MIN" ]; then
    ts_ja_tratado=""
    if [ -f "$STATE_FILE" ]; then
        ts_ja_tratado=$(cat "$STATE_FILE" 2>/dev/null)
    fi

    if [ "$ts_ja_tratado" == "$ultima_analise_ts" ]; then
        log "TRAVAMENTO SILENCIOSO ja tratado (sem /analises há ${diff_analise_min}min, mesmo incidente -- ultima_analise_ts=${ultima_analise_ts}). Sem novo restart/alerta."
    else
        log "TRAVAMENTO SILENCIOSO detectado: sem POST /analises há ${diff_analise_min}min (processo ainda 'vivo'). Reiniciando $SERVICE..."
        alertar_telegram "🐛 *Watchdog*: bot-betfair sem gravar análises há ${diff_analise_min}min (travamento silencioso). Reiniciando agora..."
        sudo systemctl restart "$SERVICE"
        sleep 5
        status=$(systemctl is-active $SERVICE)
        log "Restart executado. Status: $status"
        alertar_telegram "✅ *Watchdog*: restart concluído. Status: ${status}"
        echo "$ultima_analise_ts" > "$STATE_FILE"
    fi
else
    log "OK — mudo há ${diff_mudo_min}min, sem análise há ${diff_analise_min}min (dentro do limite)"
    rm -f "$STATE_FILE"
fi
