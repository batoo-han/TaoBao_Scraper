# 🗄️ Настройка PostgreSQL и Redis

Руководство по установке и настройке PostgreSQL и Redis для Taobao Scraper Bot.

---

## 📋 Содержание

1. [Обзор](#обзор)
2. [Установка PostgreSQL](#установка-postgresql)
3. [Установка Redis](#установка-redis)
4. [Настройка через Docker Compose](#настройка-через-docker-compose)
5. [Миграция данных](#миграция-данных)
6. [Резервное копирование](#резервное-копирование)
7. [Устранение неполадок](#устранение-неполадок)

---

## 🎯 Обзор

Начиная с версии 3.0.0, бот использует:

- **PostgreSQL** - для хранения пользовательских настроек, списков доступа, лимитов запросов, административных настроек и статистики запросов
- **Redis** - для кэширования результатов запросов и ускорения повторных обработок

### Преимущества перехода на БД:

- ✅ **Надёжность** - транзакции, целостность данных
- ✅ **Масштабируемость** - поддержка множественных подключений
- ✅ **Аналитика** - статистика запросов в структурированном виде
- ✅ **Кэширование** - ускорение повторных запросов через Redis
- ✅ **Бэкапы** - стандартные инструменты PostgreSQL

---

## 🐘 Установка PostgreSQL

### Вариант 1: Docker (рекомендуется для разработки)

```bash
# Запуск PostgreSQL в Docker
docker run -d \
  --name postgres-taobao \
  -e POSTGRES_DB=taobao_bot \
  -e POSTGRES_USER=taobao_user \
  -e POSTGRES_PASSWORD=your_secure_password \
  -p 5432:5432 \
  -v postgres-data:/var/lib/postgresql/data \
  postgres:15-alpine

# Проверка работы
docker exec -it postgres-taobao psql -U taobao_user -d taobao_bot -c "SELECT version();"
```

### Вариант 2: Локальная установка (Ubuntu/Debian)

```bash
# Установка PostgreSQL
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# Запуск службы
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Создание пользователя и базы данных
sudo -u postgres psql <<EOF
CREATE USER taobao_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE taobao_bot OWNER taobao_user;
GRANT ALL PRIVILEGES ON DATABASE taobao_bot TO taobao_user;
\q
EOF

# Проверка подключения
psql -h localhost -U taobao_user -d taobao_bot -c "SELECT version();"
```

### Вариант 3: Локальная установка (Windows)

1. Скачайте установщик с [официального сайта](https://www.postgresql.org/download/windows/)
2. Запустите установщик и следуйте инструкциям
3. Во время установки укажите пароль для пользователя `postgres`
4. После установки откройте **pgAdmin** или **psql**
5. Создайте пользователя и базу данных:

```sql
CREATE USER taobao_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE taobao_bot OWNER taobao_user;
GRANT ALL PRIVILEGES ON DATABASE taobao_bot TO taobao_user;
```

---

## 🔴 Установка Redis

### Вариант 1: Docker (рекомендуется для разработки)

```bash
# Запуск Redis в Docker
docker run -d \
  --name redis-taobao \
  -p 6379:6379 \
  redis:7-alpine

# Или с паролем (рекомендуется для production):
docker run -d \
  --name redis-taobao \
  -p 6379:6379 \
  redis:7-alpine redis-server --requirepass your_secure_password
```

### Вариант 2: Локальная установка (Ubuntu/Debian)

```bash
# Установка Redis
sudo apt update
sudo apt install -y redis-server

# Настройка пароля (опционально, рекомендуется для production)
sudo nano /etc/redis/redis.conf
# Найдите строку: # requirepass foobared
# Раскомментируйте и замените: requirepass your_secure_password

# Запуск службы
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Проверка работы
redis-cli ping
# Должно вернуть: PONG
```

### Вариант 3: Локальная установка (Windows)

1. Скачайте Redis для Windows с [GitHub Releases](https://github.com/microsoftarchive/redis/releases) или используйте WSL
2. Запустите `redis-server.exe`
3. В другом терминале проверьте: `redis-cli.exe ping`

---

## 🐳 Настройка через Docker Compose

Рекомендуемый способ для production - использовать `docker-compose.yml`, который уже включает PostgreSQL и Redis:

```yaml
# docker-compose.yml (фрагмент)
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: taobao_bot
      POSTGRES_USER: taobao_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taobao_user"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  bot:
    # ... настройки бота
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

### Запуск:

```bash
# Создайте .env файл с паролями
echo "POSTGRES_PASSWORD=your_secure_password" >> .env
echo "REDIS_PASSWORD=your_secure_password" >> .env

# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps
```

---

## ⚙️ Настройка в .env

Добавьте следующие переменные в ваш `.env` файл:

```bash
# PostgreSQL
POSTGRES_HOST=localhost          # Для локальной БД: localhost, для Docker: postgres
POSTGRES_PORT=5432
POSTGRES_DB=taobao_bot
POSTGRES_USER=taobao_user
POSTGRES_PASSWORD=your_secure_password
# DATABASE_URL формируется автоматически, но можно указать явно:
# DATABASE_URL=postgresql+asyncpg://taobao_user:password@localhost:5432/taobao_bot
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# Redis
REDIS_URL=redis://:password@localhost:6379/0  # Для локальной БД без пароля: redis://:@localhost:6379/0
REDIS_PASSWORD=your_secure_password           # Оставьте пустым, если пароль не используется
REDIS_PORT=6379
REDIS_DB=0

# Кэширование
CACHE_ENABLED=True
CACHE_TTL_SECONDS=3600          # Время жизни кэша (1 час)
CACHE_PREFIX=cache:product
```

### Важные моменты:

- **Для локальной разработки** (PostgreSQL и Redis на localhost):
  - `POSTGRES_HOST=localhost`
  - `REDIS_URL=redis://:@localhost:6379/0` (если пароль не используется)
  - `REDIS_PASSWORD=` (оставьте пустым)

- **Для Docker Compose**:
  - `POSTGRES_HOST=postgres` (имя сервиса в docker-compose.yml)
  - `REDIS_URL=redis://:password@redis:6379/0` (имя сервиса: redis)
  - Укажите пароли в переменных окружения

---

## 📦 Миграция данных

Если вы обновляетесь с версии 2.x, нужно перенести данные из JSON файлов в PostgreSQL:

### 1. Запуск миграций Alembic

```bash
# Убедитесь, что PostgreSQL запущен и настройки в .env корректны

# Применение миграций (создание таблиц)
python scripts/migrate_db.py upgrade head

# Проверка текущей версии миграции
python scripts/migrate_db.py current
```

### 2. Импорт данных из JSON файлов

```bash
# Запуск скрипта миграции данных
python scripts/migrate_json_to_db.py

# Скрипт автоматически:
# - Импортирует пользовательские настройки из data/user_settings.json
# - Импортирует списки доступа из data/access_control.json
# - Импортирует лимиты из data/rate_limits.json
# - Импортирует административные настройки
```

### 3. Проверка миграции

```bash
# Проверка таблиц в БД
python scripts/check_tables.py

# Проверка данных (через psql)
psql -h localhost -U taobao_user -d taobao_bot -c "SELECT COUNT(*) FROM users;"
psql -h localhost -U taobao_user -d taobao_bot -c "SELECT COUNT(*) FROM access_control;"
```

---

## 💾 Резервное копирование

### PostgreSQL

```bash
# Создание бэкапа
pg_dump -h localhost -U taobao_user -d taobao_bot -F c -f backup_$(date +%Y%m%d_%H%M%S).dump

# Или через скрипт:
./scripts/backup_db.sh

# Восстановление из бэкапа
pg_restore -h localhost -U taobao_user -d taobao_bot backup_20250105_120000.dump

# Или через скрипт:
./scripts/restore_db.sh backup_20250105_120000.dump
```

### Redis

```bash
# Ручное сохранение (если включен persistence)
redis-cli --rdb /path/to/backup.rdb

# Или через Docker:
docker exec redis-taobao redis-cli --rdb /data/dump.rdb
docker cp redis-taobao:/data/dump.rdb ./backup.rdb
```

---

## 🔧 Устранение неполадок

### Проблема: "connection refused" для PostgreSQL

**Решение:**
```bash
# Проверьте, что PostgreSQL запущен
sudo systemctl status postgresql  # Linux
# или
docker ps | grep postgres         # Docker

# Проверьте настройки в .env:
# - POSTGRES_HOST (localhost для локальной БД, postgres для Docker)
# - POSTGRES_PORT (обычно 5432)
# - POSTGRES_PASSWORD
```

### Проблема: "authentication failed"

**Решение:**
```bash
# Проверьте пароль в .env
# Попробуйте подключиться вручную:
psql -h localhost -U taobao_user -d taobao_bot

# Если не получается, проверьте права пользователя:
sudo -u postgres psql -c "ALTER USER taobao_user WITH PASSWORD 'new_password';"
```

### Проблема: "Redis connection error"

**Решение:**
```bash
# Проверьте, что Redis запущен
redis-cli ping  # Должно вернуть PONG

# Проверьте настройки в .env:
# - REDIS_URL (формат: redis://:password@host:port/db)
# - REDIS_PASSWORD (если используется)

# Для Docker проверьте имя сервиса:
docker ps | grep redis
```

### Проблема: "relation does not exist" (таблицы не созданы)

**Решение:**
```bash
# Примените миграции Alembic:
python scripts/migrate_db.py upgrade head

# Проверьте текущую версию:
python scripts/migrate_db.py current

# Просмотрите историю миграций:
python scripts/migrate_db.py history
```

### Проблема: Кэширование не работает

**Решение:**
```bash
# Проверьте настройки в .env:
CACHE_ENABLED=True
CACHE_TTL_SECONDS=3600

# Проверьте подключение к Redis:
redis-cli ping

# Проверьте ключи в Redis:
redis-cli KEYS "cache:product:*"
```

---

## 📚 Дополнительные ресурсы

- [Документация PostgreSQL](https://www.postgresql.org/docs/)
- [Документация Redis](https://redis.io/docs/)
- [Alembic документация](https://alembic.sqlalchemy.org/)
- [SQLAlchemy документация](https://docs.sqlalchemy.org/)

---

## ✅ Чек-лист настройки

- [ ] PostgreSQL установлен и запущен
- [ ] База данных `taobao_bot` создана
- [ ] Пользователь `taobao_user` создан с правами доступа
- [ ] Redis установлен и запущен
- [ ] Настройки в `.env` файле заполнены корректно
- [ ] Миграции Alembic применены (`python scripts/migrate_db.py upgrade head`)
- [ ] Данные из JSON файлов импортированы (`python scripts/migrate_json_to_db.py`)
- [ ] Бот успешно подключается к PostgreSQL и Redis
- [ ] Кэширование работает (проверить логи после повторного запроса)

---

**Версия документа:** 3.0.0  
**Последнее обновление:** Январь 2025
