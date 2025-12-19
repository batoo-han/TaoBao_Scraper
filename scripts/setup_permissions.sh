#!/bin/bash
# Скрипт для настройки прав доступа к папкам data и logs
# Использование: ./scripts/setup_permissions.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔒 Настройка прав доступа для Docker контейнера..."
echo ""

# Определяем UID пользователя botuser в контейнере (обычно 1000)
BOT_USER_UID=${BOT_USER_UID:-1000}

# Создаём папки если их нет
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/logs"

# Проверяем, существует ли пользователь с таким UID
if id -u "$BOT_USER_UID" >/dev/null 2>&1; then
    BOT_USER=$(id -nu "$BOT_USER_UID")
    echo "✓ Найден пользователь: $BOT_USER (UID: $BOT_USER_UID)"
else
    # Если пользователя нет, создаём его или используем текущего
    if [ "$EUID" -eq 0 ]; then
        # Если запущено от root, создаём пользователя
        useradd -m -u "$BOT_USER_UID" botuser 2>/dev/null || true
        BOT_USER="botuser"
        echo "✓ Создан пользователь: $BOT_USER (UID: $BOT_USER_UID)"
    else
        # Используем текущего пользователя
        BOT_USER=$(whoami)
        BOT_USER_UID=$(id -u)
        echo "⚠️  Пользователь с UID $BOT_USER_UID не найден, используем текущего: $BOT_USER"
    fi
fi

# Устанавливаем владельца и права
echo ""
echo "📁 Настройка папки data/..."
if [ "$EUID" -eq 0 ]; then
    chown -R "$BOT_USER:$BOT_USER" "$PROJECT_DIR/data"
    chmod -R 755 "$PROJECT_DIR/data"
    # Для JSON файлов более строгие права
    find "$PROJECT_DIR/data" -type f -name "*.json" -exec chmod 644 {} \;
else
    # Если не root, используем sudo
    sudo chown -R "$BOT_USER:$BOT_USER" "$PROJECT_DIR/data" 2>/dev/null || \
        chown -R "$BOT_USER:$BOT_USER" "$PROJECT_DIR/data" || true
    sudo chmod -R 755 "$PROJECT_DIR/data" 2>/dev/null || \
        chmod -R 755 "$PROJECT_DIR/data" || true
    find "$PROJECT_DIR/data" -type f -name "*.json" -exec chmod 644 {} \; 2>/dev/null || true
fi

echo "📁 Настройка папки logs/..."
if [ "$EUID" -eq 0 ]; then
    chown -R "$BOT_USER:$BOT_USER" "$PROJECT_DIR/logs"
    chmod -R 755 "$PROJECT_DIR/logs"
else
    sudo chown -R "$BOT_USER:$BOT_USER" "$PROJECT_DIR/logs" 2>/dev/null || \
        chown -R "$BOT_USER:$BOT_USER" "$PROJECT_DIR/logs" || true
    sudo chmod -R 755 "$PROJECT_DIR/logs" 2>/dev/null || \
        chmod -R 755 "$PROJECT_DIR/logs" || true
fi

echo ""
echo "✅ Права доступа настроены!"
echo ""
echo "📋 Текущие права:"
ls -ld "$PROJECT_DIR/data" "$PROJECT_DIR/logs" 2>/dev/null || true
echo ""
echo "💡 Если контейнер всё ещё не может писать, проверьте:"
echo "   1. UID пользователя в контейнере: docker compose exec taobao-bot id"
echo "   2. Владельца папок: ls -ld data logs"
echo "   3. Запустите скрипт с sudo: sudo ./scripts/setup_permissions.sh"

