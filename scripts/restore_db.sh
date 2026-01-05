#!/bin/bash
# Скрипт для восстановления PostgreSQL базы данных из бэкапа
# Использование: ./scripts/restore_db.sh <backup_file>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -z "$1" ]; then
    echo "❌ Укажите файл бэкапа"
    echo "Использование: $0 <backup_file>"
    echo ""
    echo "Пример:"
    echo "  $0 backups/db_backup_20240101_120000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Файл бэкапа не найден: $BACKUP_FILE"
    exit 1
fi

# Загружаем переменные окружения
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(cat "$PROJECT_DIR/.env" | grep -v '^#' | xargs)
fi

# Параметры БД
POSTGRES_DB="${POSTGRES_DB:-taobao_bot}"
POSTGRES_USER="${POSTGRES_USER:-taobao_user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

echo "⚠️  ВНИМАНИЕ: Это действие перезапишет текущую базу данных!"
echo "   База данных: $POSTGRES_DB"
echo "   Файл бэкапа: $BACKUP_FILE"
echo ""
read -p "Продолжить? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Отменено"
    exit 0
fi

echo "📥 Восстановление базы данных..."

# Проверяем, работает ли PostgreSQL в Docker
if docker ps | grep -q taobao-scraper-postgres; then
    echo "   Используется Docker контейнер PostgreSQL"
    
    # Создаём временный файл в контейнере
    CONTAINER_TMP="/tmp/restore_$(basename $BACKUP_FILE)"
    docker cp "$BACKUP_FILE" "taobao-scraper-postgres:$CONTAINER_TMP"
    
    # Восстанавливаем
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        docker exec -i taobao-scraper-postgres bash -c "gunzip -c $CONTAINER_TMP | psql -U $POSTGRES_USER -d $POSTGRES_DB"
    else
        docker exec -i taobao-scraper-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$BACKUP_FILE"
    fi
    
    # Удаляем временный файл
    docker exec taobao-scraper-postgres rm -f "$CONTAINER_TMP"
else
    echo "   Используется локальный PostgreSQL"
    export PGPASSWORD="$POSTGRES_PASSWORD"
    
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        gunzip -c "$BACKUP_FILE" | psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB"
    else
        psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$BACKUP_FILE"
    fi
    
    unset PGPASSWORD
fi

if [ $? -eq 0 ]; then
    echo "✅ База данных восстановлена успешно"
else
    echo "❌ Ошибка при восстановлении базы данных"
    exit 1
fi
