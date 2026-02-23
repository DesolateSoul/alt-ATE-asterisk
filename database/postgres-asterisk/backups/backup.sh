#!/bin/bash
# Скрипт для автоматического бэкапа базы данных

# Загрузка переменных окружения
source ../.env

# Переменные
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/asterisk_db_$DATE.sql"
RETENTION_DAYS=7

# Создание бэкапа
docker exec postgres-asterisk-v2 pg_dump -U postgres asterisk_db > $BACKUP_FILE

# Сжатие
gzip $BACKUP_FILE

# Удаление старых бэкапов (старше 7 дней)
find $BACKUP_DIR -name "asterisk_db_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $BACKUP_FILE.gz"
