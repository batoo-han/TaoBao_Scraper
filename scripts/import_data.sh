#!/bin/bash
# Скрипт для импорта данных бота на новый сервер
# Использование: ./scripts/import_data.sh [путь_к_архиву]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -z "$1" ]; then
    echo "📥 Импорт данных бота"
    echo ""
    echo "Использование: $0 <путь_к_архиву.tar.gz>"
    echo ""
    echo "Пример:"
    echo "  $0 backups/bot_backup_20240101_120000.tar.gz"
    echo "  $0 /path/to/bot_backup_20240101_120000.tar.gz"
    exit 1
fi

ARCHIVE_FILE="$1"

# Проверяем существование архива
if [ ! -f "$ARCHIVE_FILE" ]; then
    echo "❌ Ошибка: Архив не найден: $ARCHIVE_FILE"
    exit 1
fi

echo "📥 Импорт данных бота..."
echo "   Архив: $ARCHIVE_FILE"
echo ""

# Проверяем, что мы в правильной директории
if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo "⚠️  ВНИМАНИЕ: Не найдён main.py. Убедитесь, что вы в корне проекта."
    read -p "Продолжить? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Создаём резервную копию существующих файлов (если есть)
BACKUP_DIR="$PROJECT_DIR/backups/before_import_$(date +%Y%m%d_%H%M%S)"
if [ -f "$PROJECT_DIR/.env" ] || [ -d "$PROJECT_DIR/data" ]; then
    echo "💾 Создание резервной копии существующих файлов..."
    mkdir -p "$BACKUP_DIR"
    
    [ -f "$PROJECT_DIR/.env" ] && cp "$PROJECT_DIR/.env" "$BACKUP_DIR/" 2>/dev/null || true
    [ -d "$PROJECT_DIR/data" ] && cp -r "$PROJECT_DIR/data" "$BACKUP_DIR/" 2>/dev/null || true
    [ -d "$PROJECT_DIR/logs" ] && cp -r "$PROJECT_DIR/logs" "$BACKUP_DIR/" 2>/dev/null || true
    
    echo "   Резервная копия: $BACKUP_DIR"
    echo ""
fi

# Создаём необходимые директории
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/logs"

# Распаковываем архив
echo "📦 Распаковка архива..."
cd "$PROJECT_DIR"
tar -xzf "$ARCHIVE_FILE"

# Устанавливаем правильные права доступа
echo "🔒 Установка прав доступа..."
chmod 600 .env 2>/dev/null || true
chmod 644 data/*.json 2>/dev/null || true
chmod 755 data logs 2>/dev/null || true

# Проверяем валидность JSON файлов
echo "✅ Проверка JSON файлов..."
for json_file in data/*.json; do
    if [ -f "$json_file" ]; then
        if python3 -m json.tool "$json_file" > /dev/null 2>&1; then
            echo "   ✓ $json_file"
        else
            echo "   ✗ $json_file - ОШИБКА: невалидный JSON!"
        fi
    fi
done

echo ""
echo "✅ Импорт завершён!"
echo ""
echo "📋 Следующие шаги:"
echo "   1. Проверьте .env файл (обновите при необходимости)"
echo "   2. Запустите бота: docker-compose up -d"
echo "   3. Проверьте логи: docker-compose logs -f taobao-bot"
echo ""

