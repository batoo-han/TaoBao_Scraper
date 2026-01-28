# =============================================================================
# Dockerfile для админ-панели Taobao Bot
# 
# Multi-stage build:
# 1. frontend-build: Сборка React приложения
# 2. production: FastAPI бэкенд + статика фронтенда
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Сборка фронтенда
# -----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

# Копируем файлы зависимостей
COPY frontend/package.json frontend/package-lock.json* ./

# Устанавливаем зависимости
RUN npm ci --legacy-peer-deps

# Копируем исходники фронтенда
COPY frontend/ ./

# Собираем production билд
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Production образ
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS production

# Метаданные
LABEL maintainer="Taobao Bot Admin Panel"
LABEL version="1.0.0"

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Рабочая директория
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаём пользователя для безопасности (non-root)
RUN useradd --create-home --shell /bin/bash adminuser

# Копируем requirements и устанавливаем Python зависимости
COPY admin/requirements.txt ./admin/requirements.txt
RUN pip install --no-cache-dir -r admin/requirements.txt

# Копируем исходники бэкенда
COPY admin/backend ./admin/backend
COPY admin/__init__.py ./admin/__init__.py

# Копируем модели из основного проекта (нужны для работы с БД)
COPY src/db ./src/db
COPY src/__init__.py ./src/__init__.py

# Копируем собранный фронтенд
COPY --from=frontend-build /app/frontend/dist ./admin/frontend/dist

# Создаём директорию для логов
RUN mkdir -p /app/logs && chown -R adminuser:adminuser /app

# Переключаемся на non-root пользователя
USER adminuser

# Порт
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

# Команда запуска
CMD ["python", "-m", "uvicorn", "admin.backend.main:app", "--host", "0.0.0.0", "--port", "8082"]
