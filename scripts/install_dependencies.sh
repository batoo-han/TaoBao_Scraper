#!/bin/bash
# ==============================================================================
# СКРИПТ УСТАНОВКИ ЗАВИСИМОСТЕЙ С УВЕЛИЧЕННЫМ ТАЙМАУТОМ
# ==============================================================================
# Используется для решения проблем с таймаутом при установке пакетов из PyPI
# ==============================================================================

echo "========================================"
echo "Установка зависимостей проекта"
echo "========================================"
echo ""

# Проверка наличия виртуального окружения
if [ ! -d ".venv" ]; then
    echo "ОШИБКА: Виртуальное окружение .venv не найдено!"
    echo "Создайте его командой: python -m venv .venv"
    exit 1
fi

# Активация виртуального окружения
echo "Активация виртуального окружения..."
source .venv/bin/activate

# Обновление pip
echo ""
echo "Обновление pip..."
python -m pip install --upgrade pip --default-timeout=300

# Установка зависимостей с увеличенным таймаутом
echo ""
echo "Установка зависимостей из requirements.txt..."
echo "Таймаут установлен: 300 секунд (5 минут)"
echo ""

# Попытка установки с увеличенным таймаутом
MAX_RETRIES=3
RETRY_COUNT=0
SUCCESS=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ "$SUCCESS" = false ]; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Попытка $RETRY_COUNT из $MAX_RETRIES..."
    
    if python -m pip install -r requirements.txt --default-timeout=300 --retries=5; then
        SUCCESS=true
        echo ""
        echo "✓ Установка завершена успешно!"
    else
        echo ""
        echo "✗ Ошибка при установке (попытка $RETRY_COUNT из $MAX_RETRIES)"
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo "Повторная попытка через 5 секунд..."
            sleep 5
        fi
    fi
done

if [ "$SUCCESS" = false ]; then
    echo ""
    echo "========================================"
    echo "УСТАНОВКА НЕ УДАЛАСЬ"
    echo "========================================"
    echo ""
    echo "Альтернативные варианты:"
    echo "1. Использовать зеркало PyPI (для России):"
    echo "   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=300"
    echo ""
    echo "2. Установить пакеты по одному:"
    echo "   pip install aiogram>=3.0.0 --default-timeout=300"
    echo "   pip install httpx>=0.24.0 --default-timeout=300"
    echo "   ... и т.д."
    echo ""
    echo "3. Проверить интернет-соединение и повторить попытку"
    exit 1
fi

echo ""
echo "========================================"
echo "ВСЕ ЗАВИСИМОСТИ УСТАНОВЛЕНЫ"
echo "========================================"

