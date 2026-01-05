#!/bin/bash
# Скрипт для создания бэкапа PostgreSQL базы данных
# Использование: ./scripts/backup_db.sh [backup_dir]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${1:-$PROJECT_DIR/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

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

# Создаём директорию для бэкапов
mkdir -p "$BACKUP_DIR"

BACKUP_FILE="$BACKUP_DIR/db_backup_${TIMESTAMP}.sql.gz"

echo "📦 Создание бэкапа PostgreSQL..."
echo "   База данных: $POSTGRES_DB"
echo "   Файл: $BACKUP_FILE"

# Проверяем, работает ли PostgreSQL в Docker
if docker ps | grep -q taobao-scraper-postgres; then
    echo "   Используется Docker контейнер PostgreSQL"
    docker exec taobao-scraper-postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$BACKUP_FILE"
else
    echo "   Используется локальный PostgreSQL"
    export PGPASSWORD="$POSTGRES_PASSWORD"
    pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$BACKUP_FILE"
    unset PGPASSWORD
fi

if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "✅ Бэкап создан успешно: $BACKUP_FILE ($SIZE)"
    
    # Удаляем старые бэкапы (оставляем последние 30)
    echo "🧹 Очистка старых бэкапов (оставляем последние 30)..."
    ls -t "$BACKUP_DIR"/db_backup_*.sql.gz 2>/dev/null | tail -n +31 | xargs -r rm -f
    
    echo "✅ Готово"
else
    echo "❌ Ошибка при создании бэкапа"
    exit 1
fi
