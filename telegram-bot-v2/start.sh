#!/bin/bash
echo "========================================="
echo "🚀 ЗАПУСК TELEGRAM БОТА И NOTIFIER"
echo "========================================="
date

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Запускаем notifier в фоне
log "Запуск notifier.py..."
python /app/notifier.py &
NOTIFIER_PID=$!
log "✓ Notifier запущен с PID: $NOTIFIER_PID"

# Даем notifier время на инициализацию
sleep 2

# Проверяем, что notifier работает
if kill -0 $NOTIFIER_PID 2>/dev/null; then
    log "✓ Notifier работает (PID: $NOTIFIER_PID)"
else
    log "❌ ОШИБКА: Notifier не запустился!"
    # Выводим последние строки лога для диагностики
    tail -20 /app/logs/notifier.log 2>/dev/null || echo "Лог notifier не найден"
fi

# Запускаем бота
log "Запуск bot.py..."
python /app/bot.py &
BOT_PID=$!
log "✓ Bot запущен с PID: $BOT_PID"

log "✅ Все процессы запущены"
log "PID Bot: $BOT_PID, PID Notifier: $NOTIFIER_PID"

# Функция обработки сигналов
cleanup() {
    log "Получен сигнал завершения, останавливаем процессы..."
    kill -TERM $BOT_PID 2>/dev/null
    kill -TERM $NOTIFIER_PID 2>/dev/null
    wait $BOT_PID 2>/dev/null
    wait $NOTIFIER_PID 2>/dev/null
    log "✅ Все процессы остановлены"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Мониторинг процессов
while true; do
    if ! kill -0 $BOT_PID 2>/dev/null; then
        log "❌ Bot (PID $BOT_PID) не работает!"
    fi
    if ! kill -0 $NOTIFIER_PID 2>/dev/null; then
        log "❌ Notifier (PID $NOTIFIER_PID) не работает!"
        log "Попытка перезапуска notifier..."
        python /app/notifier.py &
        NOTIFIER_PID=$!
        log "✓ Notifier перезапущен с новым PID: $NOTIFIER_PID"
    fi
    sleep 30
done &

# Ждем завершения основных процессов
wait $BOT_PID
wait $NOTIFIER_PID

