# ==============================================================================
# TAOBAO SCRAPER BOT - DOCKERFILE
# ==============================================================================
# Легковесный Docker образ на базе Python 3.11
# ==============================================================================

FROM python:3.11-slim

# Метаданные образа
LABEL maintainer="batoo@ya.ru"
LABEL description="Taobao/Tmall Product Scraper Telegram Bot"
LABEL version="1.0.0"

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости для Playwright
RUN apt-get update && apt-get install -y \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Копируем requirements и устанавливаем Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузер Chromium для Playwright
RUN playwright install chromium --with-deps || \
    (playwright install chromium && playwright install-deps chromium)

# Копируем исходный код (новая структура)
COPY main.py ./
COPY src/ ./src/

# Примечание: pdd_cookies.json должен быть создан вручную на основе pdd_cookies_example.json
# Этот файл не копируется автоматически (в .gitignore), так как содержит чувствительные данные

# Создаём non-root пользователя для безопасности
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Переключаемся на non-root пользователя
USER botuser

# Healthcheck (опционально)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#   CMD python -c "import sys; sys.exit(0)"

# Запускаем бота (обновлённое название файла)
CMD ["python", "-u", "main.py"]
