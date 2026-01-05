#!/usr/bin/env bash
set -euo pipefail

# Быстрый деплой с минимальным простоем для long polling.
# Требования: Docker Compose v2, заранее сконфигурированный .env и собранный образ.
#
# Поведение:
# 1) Опционально тянем свежую базу (docker compose pull) — отключено по умолчанию (DO_PULL=1)
# 2) Собираем образ (если нужно) — можно отключить SKIP_BUILD=1
#    По умолчанию используется локальный образ (без --pull) для избежания проблем с сетью
#    Для принудительного обновления базового образа используйте DO_PULL=1
# 3) Перезапускаем только сервис бота (--no-deps) с уже собранным образом
# 4) Ждём healthcheck контейнера
#
# Простой = время пересоздания контейнера + прогрев, обычно 2–10 секунд при тёплой машине.
#
# Переменные окружения:
#   DO_PULL=1        - принудительно обновить базовый образ из Docker Hub (может вызвать проблемы с сетью)
#   SKIP_BUILD=1     - пропустить сборку образа (использовать уже готовый)
#   SERVICE          - имя сервиса (по умолчанию: taobao-bot)
#   COMPOSE_FILE     - путь к compose файлу (по умолчанию: docker-compose.yml)
#   HEALTH_TIMEOUT   - таймаут ожидания healthcheck в секундах (по умолчанию: 90)

SERVICE=${SERVICE:-taobao-bot}
COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.yml}
BUILD=${SKIP_BUILD:-0}
PULL=${DO_PULL:-0}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-90}  # секунд

echo "==> Сервис: ${SERVICE}"
echo "==> compose файл: ${COMPOSE_FILE}"

if [[ "${PULL}" == "1" ]]; then
  echo "==> docker compose pull"
  docker compose -f "${COMPOSE_FILE}" pull "${SERVICE}"
fi

if [[ "${BUILD}" != "1" ]]; then
  # Используем --pull только если явно указано DO_PULL=1
  # По умолчанию используем локальный образ для избежания проблем с сетью
  if [[ "${PULL}" == "1" ]]; then
    echo "==> docker compose build --pull ${SERVICE}"
    docker compose -f "${COMPOSE_FILE}" build --pull "${SERVICE}"
  else
    echo "==> docker compose build ${SERVICE} (без --pull, используем локальный образ)"
    docker compose -f "${COMPOSE_FILE}" build "${SERVICE}"
  fi
else
  echo "==> SKIP_BUILD=1 — пропускаем сборку (используем уже готовый образ)"
fi

# Применяем миграции БД перед запуском (если контейнеры уже запущены)
if docker compose -f "${COMPOSE_FILE}" ps postgres | grep -q "Up"; then
  echo "==> Применяем миграции БД..."
  docker compose -f "${COMPOSE_FILE}" exec -T taobao-bot python scripts/migrate_db.py upgrade head || {
    echo "⚠️  Предупреждение: не удалось применить миграции (возможно, контейнер ещё не запущен)"
  }
fi

echo "==> docker compose up -d --no-deps ${SERVICE}"
docker compose -f "${COMPOSE_FILE}" up -d --no-deps "${SERVICE}"

container_id=$(docker compose -f "${COMPOSE_FILE}" ps -q "${SERVICE}")
if [[ -z "${container_id}" ]]; then
  echo "!! Не удалось получить ID контейнера ${SERVICE}"
  exit 1
fi

echo "==> Ожидаем healthcheck (timeout=${HEALTH_TIMEOUT}s)"
deadline=$((SECONDS + HEALTH_TIMEOUT))
while true; do
  status=$(docker inspect --format='{{json .State.Health.Status}}' "${container_id}" 2>/dev/null | tr -d '"')
  if [[ "${status}" == "healthy" ]]; then
    echo "==> Контейнер ${SERVICE} здоров."
    break
  fi
  if (( SECONDS >= deadline )); then
    echo "!! Таймаут ожидания healthcheck, статус: ${status:-unknown}"
    docker compose -f "${COMPOSE_FILE}" logs --tail=50 "${SERVICE}" || true
    exit 1
  fi
  sleep 2
done

echo "==> Готово. Текущие логи (последние 50 строк):"
docker compose -f "${COMPOSE_FILE}" logs --tail=50 "${SERVICE}" || true

