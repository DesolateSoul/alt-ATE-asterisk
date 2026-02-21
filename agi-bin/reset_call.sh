#!/bin/bash

# AGI скрипт для сброса состояния вызова

send_command() {
    echo "$1"
}

log() {
    echo "$(date): $1" >> /tmp/agi_debug.log
}

main() {
    # Читаем переменные от Asterisk
    while read VAR && [ -n "$VAR" ]; do
        if [[ "$VAR" == *"agi_uniqueid"* ]]; then
            UNIQUEID=$(echo "$VAR" | cut -d':' -f2 | sed 's/^ //')
        fi
    done

    if [ -n "$UNIQUEID" ]; then
        # Отправляем запрос на сброс состояния
        curl -s -X POST http://10.7.35.3:8000/reset_call \
             -H "Content-Type: application/json" \
             -d "{\"unique_id\":\"$UNIQUEID\"}" \
             --connect-timeout 2 \
             --max-time 3 > /dev/null 2>&1
        
        log "Reset state for call $UNIQUEID"
    fi
    
    exit 0
}

main
