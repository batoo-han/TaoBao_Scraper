#!/bin/bash
# Скрипт для экспорта данных бота перед переносом на новый сервер
# Использование: ./scripts/export_data.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/bot_backup_$TIMESTAMP.tar.gz"

echo "📦 Экспорт данных бота..."
echo ""

# Создаём директорию для бэкапов
mkdir -p "$BACKUP_DIR"

# Проверяем наличие важных файлов
echo "🔍 Проверка файлов..."

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠️  ВНИМАНИЕ: .env файл не найден!"
    read -p "Продолжить без .env? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

FILES_TO_BACKUP=(
    ".env"
    "data/access_control.json"
    "data/access_control.backup.json"
    "data/user_settings.json"
    "data/rate_limits.json"
)

# Проверяем наличие файлов
MISSING_FILES=()
for file in "${FILES_TO_BACKUP[@]}"; do
    if [ ! -f "$PROJECT_DIR/$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo "⚠️  Отсутствующие файлы:"
    for file in "${MISSING_FILES[@]}"; do
        echo "   - $file"
    done
    read -p "Продолжить? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Добавляем логи (опционально)
if [ -f "$PROJECT_DIR/logs/bot_errors.log" ]; then
    FILES_TO_BACKUP+=("logs/bot_errors.log")
fi

# Создаём архив
echo "📦 Создание архива..."
cd "$PROJECT_DIR"
tar -czf "$BACKUP_FILE" "${FILES_TO_BACKUP[@]}" 2>/dev/null || {
    echo "❌ Ошибка при создании архива"
    exit 1
}

# Проверяем размер архива
ARCHIVE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "✅ Архив создан: $BACKUP_FILE"
echo "   Размер: $ARCHIVE_SIZE"

# Создаём файл с информацией о бэкапе
INFO_FILE="$BACKUP_DIR/bot_backup_$TIMESTAMP.info"
cat > "$INFO_FILE" << EOF
Дата создания: $(date)
Файл архива: bot_backup_$TIMESTAMP.tar.gz
Размер: $ARCHIVE_SIZE

Содержимое:
EOF

for file in "${FILES_TO_BACKUP[@]}"; do
    if [ -f "$PROJECT_DIR/$file" ]; then
        SIZE=$(du -h "$PROJECT_DIR/$file" | cut -f1)
        echo "  - $file ($SIZE)" >> "$INFO_FILE"
    fi
done

echo ""
echo "📋 Информация о бэкапе сохранена в: $INFO_FILE"
echo ""
echo "✅ Экспорт завершён!"
echo ""
echo "📤 Для копирования на новый сервер используйте:"
echo "   scp $BACKUP_FILE user@new-server:/path/to/destination/"
echo ""

