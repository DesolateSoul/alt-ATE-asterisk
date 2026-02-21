#!/bin/bash

# AGI скрипт для проверки распознанного текста

# Функция для отправки команд в Asterisk
send_command() {
    echo "$1"
    echo "$1" >> /tmp/agi_commands.log
}

# Функция для логирования
log() {
    echo "$(date): $1" >> /tmp/agi_debug.log
}

# Функция для парсинга ответа от Docker
parse_response() {
    local response="$1"
    local key="$2"
    
    # Пробуем извлечь значение с помощью grep и sed
    echo "$response" | grep -o "\"$key\":[^,}]*" | cut -d':' -f2 | tr -d '" ' || echo ""
}

# Основная логика
main() {
    log "=== НАЧАЛО ОБРАБОТКИ ==="

    # Читаем переменные от Asterisk
    UNIQUEID=""
    while read VAR && [ -n "$VAR" ]; do
        log "GOT: $VAR"
        if [[ "$VAR" == *"agi_uniqueid"* ]]; then
            UNIQUEID=$(echo "$VAR" | cut -d':' -f2 | sed 's/^ //')
        fi
    done

    # Получаем текущий этап проверки
    send_command "GET VARIABLE CHECK_STAGE"
    read STAGE_RESPONSE
    CHECK_STAGE=$(echo "$STAGE_RESPONSE" | cut -d'=' -f2 | sed 's/^200 result=//' | sed 's/^ //' | sed 's/ $//')
    
    # Получаем номер текущей попытки
    if [ "$CHECK_STAGE" = "INN" ]; then
        send_command "GET VARIABLE INN_ATTEMPT_COUNT"
    else
        send_command "GET VARIABLE CODEWORD_ATTEMPT_COUNT"
    fi
    read ATTEMPT_RESPONSE
    ATTEMPT_COUNT=$(echo "$ATTEMPT_RESPONSE" | cut -d'=' -f2 | sed 's/^200 result=//' | sed 's/^ //' | sed 's/ $//')
    
    log "Current stage: '$CHECK_STAGE', attempt: $ATTEMPT_COUNT"

    # Получаем распознанный текст
    send_command "GET VARIABLE SPEECH_TEXT(0)"
    read RESPONSE
    TEXT=$(echo "$RESPONSE" | cut -d'=' -f2 | sed 's/^200 result=//' | sed 's/^ //' | sed 's/ $//')

    log "Raw response: $RESPONSE"
    log "Extracted text: '$TEXT'"

    # Проверяем, что текст не пустой
    if [ -z "$TEXT" ]; then
        log "Текст пустой"
        send_command "SET VARIABLE RECOGNITION_RESULT EMPTY"
        send_command "SET VARIABLE RETRY_SPEECH 1"
        exit 0
    fi

    # Приводим к нижнему регистру и убираем пробелы
    CLEAN_TEXT=$(echo "$TEXT" | tr '[:upper:]' '[:lower:]' | xargs)

    log "Cleaned text: '$CLEAN_TEXT'"

    # Отправляем в Docker для валидации
    JSON="{\"text\":\"$TEXT\",\"clean_text\":\"$CLEAN_TEXT\",\"unique_id\":\"$UNIQUEID\",\"stage\":\"$CHECK_STAGE\",\"attempt\":$ATTEMPT_COUNT}"
    
    log "Sending to Docker: $JSON"
    
    # Отправляем запрос и получаем ответ от Docker
    RESPONSE=$(curl -s -X POST http://10.7.35.3:8000/check_text \
         -H "Content-Type: application/json" \
         -d "$JSON" \
         --connect-timeout 2 \
         --max-time 5)
    
    CURL_EXIT=$?
    
    if [ $CURL_EXIT -eq 0 ] && [ -n "$RESPONSE" ]; then
        log "Docker response: $RESPONSE"
        
        # Парсим ответ
        IS_VALID=$(parse_response "$RESPONSE" "is_valid")
        MESSAGE=$(parse_response "$RESPONSE" "message")
        
        log "Parsed - is_valid: '$IS_VALID', message: '$MESSAGE'"
        
        if [ "$IS_VALID" = "true" ]; then
            log "ТЕКСТ ПРОШЕЛ ВАЛИДАЦИЮ!"
            send_command "SET VARIABLE RECOGNITION_RESULT SUCCESS"
            
            if [ "$CHECK_STAGE" = "INN" ]; then
                send_command "SET VARIABLE INN_VALID SUCCESS"
                send_command "VERBOSE \"ИНН успешно распознан: $CLEAN_TEXT\""
            elif [ "$CHECK_STAGE" = "CODEWORD" ]; then
                send_command "SET VARIABLE CODEWORD_VALID SUCCESS"
                send_command "VERBOSE \"Кодовое слово успешно распознано: $CLEAN_TEXT\""
            fi
        else
            log "ТЕКСТ НЕ ПРОШЕЛ ВАЛИДАЦИЮ!"
            send_command "SET VARIABLE RECOGNITION_RESULT FAILED"
            
            # Проверяем, не превышено ли максимальное количество попыток
            MAX_ATTEMPTS_REACHED=$(parse_response "$RESPONSE" "max_attempts_reached")
            
            if [ "$CHECK_STAGE" = "INN" ]; then
                send_command "SET VARIABLE INN_VALID FAILED"
                send_command "VERBOSE \"Неверный ИНН: $CLEAN_TEXT\""
            elif [ "$CHECK_STAGE" = "CODEWORD" ]; then
                send_command "SET VARIABLE CODEWORD_VALID FAILED"
                send_command "VERBOSE \"Неверное кодовое слово: $CLEAN_TEXT\""
                
                if [ "$MAX_ATTEMPTS_REACHED" = "true" ]; then
                    send_command "SET VARIABLE MAX_ATTEMPTS_REACHED 1"
                fi
            fi
        fi
    else
        log "Ошибка подключения к Docker серверу (curl exit: $CURL_EXIT)"
        send_command "SET VARIABLE RECOGNITION_RESULT FAILED"
        send_command "VERBOSE \"Ошибка подключения к серверу валидации\""
        
        # В случае ошибки сервера, лучше дать пользователю еще одну попытку
        send_command "SET VARIABLE RETRY_SPEECH 1"
    fi

    log "=== ОБРАБОТКА ЗАВЕРШЕНА ==="
}

# Запускаем основную функцию
main

exit 0
