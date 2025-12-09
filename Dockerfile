# ==============================================================================
# TAOBAO SCRAPER BOT - DOCKERFILE
# ==============================================================================
# Легковесный Docker образ на базе Python 3.11
# ==============================================================================

FROM python:3.11-slim

# Метаданные образа
LABEL maintainer="batoo@ya.ru"
LABEL description="Taobao/Tmall Product Scraper Telegram Bot"
LABEL version="2.0.0"

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

# Создаём non-root пользователя для безопасности
RUN useradd -m -u 1000 botuser

# Копируем исходный код (новая структура)
COPY main.py ./
COPY src/ ./src/

# Меняем владельца файлов на botuser
RUN chown -R botuser:botuser /app

# Переключаемся на non-root пользователя
USER botuser

# Устанавливаем браузер Chromium для Playwright ОТ ПОЛЬЗОВАТЕЛЯ botuser
# Это важно, т.к. браузер устанавливается в домашнюю директорию пользователя
RUN python -m playwright install chromium || \
    (python -m playwright install chromium --with-deps || \
     (python -m playwright install chromium && python -m playwright install-deps chromium))

# Проверяем, что Chromium установлен (более гибкая проверка пути)
RUN if [ ! -d /home/botuser/.cache/ms-playwright ]; then \
        echo "ERROR: Playwright cache directory not found" && exit 1; \
    fi && \
    if ! find /home/botuser/.cache/ms-playwright -name "chrome" -type f 2>/dev/null | grep -q .; then \
        echo "ERROR: Chromium binary not found after installation" && \
        echo "Cache contents:" && ls -la /home/botuser/.cache/ms-playwright/ && exit 1; \
    fi && \
    echo "Chromium installation verified successfully"

# Healthcheck (опционально)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#   CMD python -c "import sys; sys.exit(0)"

# Примечание: pdd_cookies.json должен быть создан вручную на основе pdd_cookies_example.json
# Этот файл не копируется автоматически (в .gitignore), так как содержит чувствительные данные

# Запускаем бота (обновлённое название файла)
CMD ["python", "-u", "main.py"]
