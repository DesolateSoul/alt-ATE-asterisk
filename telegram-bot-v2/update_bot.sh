#!/bin/bash
echo "📝 Копирую bot.py в контейнер..."
docker cp ./bot.py asterisk-telegram-bot:/app/bot.py

echo "🔄 Перезапускаю контейнер..."
docker restart asterisk-telegram-bot

echo "📋 Последние логи:"
sleep 2
docker logs asterisk-telegram-bot --tail 20
