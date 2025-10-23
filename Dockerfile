# ==============================================================================
# TAOBAO SCRAPER BOT - DOCKERFILE
# ==============================================================================
# Легковесный Docker образ на базе Python 3.11
# ==============================================================================

FROM python:3.11-slim

# Метаданные образа
LABEL maintainer="your_email@example.com"
LABEL description="Taobao/Tmall Product Scraper Telegram Bot"
LABEL version="1.0.0"

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Копируем requirements и устанавливаем Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY *.py ./
COPY prompt/ ./prompt/

# Создаём non-root пользователя для безопасности
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Переключаемся на non-root пользователя
USER botuser

# Healthcheck (опционально)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#   CMD python -c "import sys; sys.exit(0)"

# Запускаем бота
CMD ["python", "-u", "autoparse.py"]
