# PostgreSQL на Ubuntu Server — Полное руководство

> **Подробное руководство по установке, настройке, безопасности и администрированию PostgreSQL для проекта Taobao Scraper Bot на Ubuntu Server.**

---

## 📋 Содержание

1. [Установка PostgreSQL](#установка-postgresql)
2. [Первоначальная настройка](#первоначальная-настройка)
3. [Создание базы данных и пользователя](#создание-базы-данных-и-пользователя)
4. [Безопасность](#безопасность)
5. [Проверка конфигурации](#проверка-конфигурации)
6. [Администрирование](#администрирование)
7. [Резервное копирование и восстановление](#резервное-копирование-и-восстановление)
8. [Мониторинг и оптимизация](#мониторинг-и-оптимизация)
9. [Решение проблем](#решение-проблем)
10. [Интеграция с проектом](#интеграция-с-проектом)

---

## 🚀 Установка PostgreSQL

### Обновление системы

```bash
sudo apt update
sudo apt upgrade -y
```

### Установка PostgreSQL

**Для Ubuntu 22.04 LTS (рекомендуется):**

```bash
# Установка PostgreSQL 14 (стабильная версия)
sudo apt install postgresql postgresql-contrib -y

# Проверка версии
sudo -u postgres psql --version
```

**Для Ubuntu 24.04 LTS:**

```bash
# Установка PostgreSQL 16 (последняя версия)
sudo apt install postgresql postgresql-contrib -y

# Проверка версии
sudo -u postgres psql --version
```

### Проверка статуса службы

```bash
# Проверка статуса
sudo systemctl status postgresql

# Запуск службы (если не запущена)
sudo systemctl start postgresql

# Включение автозапуска
sudo systemctl enable postgresql
```

---

## ⚙️ Первоначальная настройка

### Настройка пароля для пользователя postgres

```bash
# Переключение на пользователя postgres
sudo -u postgres psql

# В psql консоли:
ALTER USER postgres PASSWORD 'ваш_надежный_пароль';
\q
```

### Настройка доступа (pg_hba.conf)

```bash
# Редактирование файла конфигурации
sudo nano /etc/postgresql/*/main/pg_hba.conf
```

**Рекомендуемые настройки для продакшена:**

```
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# Локальные подключения
local   all             postgres                                peer
local   all             all                                     md5

# IPv4 локальные подключения
host    all             all             127.0.0.1/32            md5

# IPv6 локальные подключения
host    all             all             ::1/128                 md5

# Удаленные подключения (только для доверенных IP)
host    all             all             10.0.0.0/8              md5
host    all             all             192.168.0.0/16          md5
```

**Важно:** Для продакшена **НЕ используйте** `trust` или `password` без SSL!

### Перезапуск PostgreSQL

```bash
sudo systemctl restart postgresql
```

---

## 🗄️ Создание базы данных и пользователя

### Создание базы данных

```bash
# Вход в psql от имени postgres
sudo -u postgres psql

# Создание базы данных
CREATE DATABASE taobao_scraper
    WITH 
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'ru_RU.UTF-8'
    LC_CTYPE = 'ru_RU.UTF-8'
    TEMPLATE = template0;

# Проверка создания
\l
```

### Создание пользователя для приложения

```bash
# В psql консоли:
CREATE USER taobao WITH PASSWORD 'taobao_scraper';

# Выдача прав на базу данных
GRANT ALL PRIVILEGES ON DATABASE taobao_scraper TO taobao;

# Подключение к базе данных
\c taobao_scraper

# Выдача прав на схему public
GRANT ALL ON SCHEMA public TO taobao;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO taobao;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO taobao;

# Выдача прав на будущие объекты
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO taobao;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO taobao;

# Выход
\q
```

### Проверка подключения

```bash
# Тест подключения от имени пользователя taobao
psql -U taobao -d taobao_scraper -h localhost

# Если запрашивает пароль, введите: taobao_scraper
```

---

## 🔒 Безопасность

### Настройка SSL (рекомендуется для продакшена)

#### Генерация самоподписанного сертификата

```bash
# Создание директории для сертификатов
sudo mkdir -p /etc/postgresql/ssl
sudo chmod 700 /etc/postgresql/ssl

# Генерация приватного ключа
sudo openssl genrsa -out /etc/postgresql/ssl/server.key 2048

# Генерация сертификата
sudo openssl req -new -x509 -key /etc/postgresql/ssl/server.key -days 365 -out /etc/postgresql/ssl/server.crt -subj "/CN=your-server-name"

# Установка прав
sudo chown postgres:postgres /etc/postgresql/ssl/server.key /etc/postgresql/ssl/server.crt
sudo chmod 600 /etc/postgresql/ssl/server.key
sudo chmod 644 /etc/postgresql/ssl/server.crt
```

#### Настройка postgresql.conf

```bash
sudo nano /etc/postgresql/*/main/postgresql.conf
```

**Добавьте/измените:**

```conf
# SSL настройки
ssl = on
ssl_cert_file = '/etc/postgresql/ssl/server.crt'
ssl_key_file = '/etc/postgresql/ssl/server.key'
ssl_ca_file = '/etc/postgresql/ssl/server.crt'

# Ограничение подключений
max_connections = 100
```

#### Перезапуск

```bash
sudo systemctl restart postgresql
```

### Ограничение доступа по IP

**Настройка firewall (ufw):**

```bash
# Разрешить только локальные подключения
sudo ufw allow from 127.0.0.1 to any port 5432

# Или разрешить доступ из определенной подсети
sudo ufw allow from 10.0.0.0/8 to any port 5432
```

### Отключение удаленного доступа (если не нужен)

```bash
sudo nano /etc/postgresql/*/main/postgresql.conf
```

**Измените:**

```conf
listen_addresses = 'localhost'
```

### Регулярная смена паролей

```bash
# В psql:
ALTER USER taobao WITH PASSWORD 'новый_надежный_пароль';
```

### Аудит подключений

```bash
# Включение логирования подключений
sudo nano /etc/postgresql/*/main/postgresql.conf
```

**Добавьте:**

```conf
log_connections = on
log_disconnections = on
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

---

## ✅ Проверка конфигурации

### Проверка версии PostgreSQL

```bash
sudo -u postgres psql -c "SELECT version();"
```

### Проверка статуса службы

```bash
sudo systemctl status postgresql
```

### Проверка подключений

```bash
# Количество активных подключений
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Список всех подключений
sudo -u postgres psql -c "SELECT pid, usename, datname, client_addr, state FROM pg_stat_activity;"
```

### Проверка прав пользователя

```bash
# В psql:
\c taobao_scraper
\du taobao
\dn+
```

### Проверка SSL

```bash
# Проверка SSL статуса
sudo -u postgres psql -c "SHOW ssl;"

# Тест SSL подключения
psql "host=localhost port=5432 dbname=taobao_scraper user=taobao sslmode=require"
```

### Проверка конфигурационных файлов

```bash
# Проверка синтаксиса postgresql.conf
sudo -u postgres postgres --check-config

# Проверка pg_hba.conf
sudo -u postgres postgres --check-config -D /var/lib/postgresql/*/main
```

---

## 🛠️ Администрирование

### Основные команды psql

```bash
# Вход в psql
sudo -u postgres psql

# Список баз данных
\l

# Подключение к базе
\c taobao_scraper

# Список таблиц
\dt

# Список пользователей
\du

# Список схем
\dn

# Описание таблицы
\d table_name

# Выход
\q
```

### Управление пользователями

```bash
# Создание пользователя
CREATE USER username WITH PASSWORD 'password';

# Изменение пароля
ALTER USER username WITH PASSWORD 'new_password';

# Выдача прав суперпользователя
ALTER USER username WITH SUPERUSER;

# Удаление пользователя
DROP USER username;
```

### Управление базами данных

```bash
# Создание базы данных
CREATE DATABASE dbname;

# Переименование базы данных
ALTER DATABASE old_name RENAME TO new_name;

# Удаление базы данных
DROP DATABASE dbname;

# Резервная копия
pg_dump -U taobao -d taobao_scraper > backup.sql

# Восстановление
psql -U taobao -d taobao_scraper < backup.sql
```

### Управление таблицами

```bash
# Создание таблицы
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

# Просмотр размера таблицы
SELECT pg_size_pretty(pg_total_relation_size('table_name'));

# Анализ таблицы (обновление статистики)
ANALYZE table_name;

# Переиндексация
REINDEX TABLE table_name;
```

### Очистка и обслуживание

```bash
# VACUUM (освобождение места)
VACUUM;

# VACUUM FULL (полная очистка, блокирует таблицу)
VACUUM FULL;

# VACUUM ANALYZE (очистка + обновление статистики)
VACUUM ANALYZE;

# Автоматический VACUUM (настроен по умолчанию)
# Проверка настроек:
SHOW autovacuum;
```

---

## 💾 Резервное копирование и восстановление

### Резервное копирование (pg_dump)

```bash
# Полная резервная копия базы данных
pg_dump -U taobao -d taobao_scraper -F c -f backup_$(date +%Y%m%d_%H%M%S).dump

# Резервная копия в SQL формат
pg_dump -U taobao -d taobao_scraper > backup_$(date +%Y%m%d_%H%M%S).sql

# Резервная копия только схемы (без данных)
pg_dump -U taobao -d taobao_scraper --schema-only > schema_backup.sql

# Резервная копия только данных
pg_dump -U taobao -d taobao_scraper --data-only > data_backup.sql
```

### Восстановление

```bash
# Восстановление из SQL файла
psql -U taobao -d taobao_scraper < backup.sql

# Восстановление из custom формата
pg_restore -U taobao -d taobao_scraper backup.dump

# Восстановление с заменой существующей базы
pg_restore -U taobao -d taobao_scraper --clean backup.dump
```

### Автоматическое резервное копирование (cron)

```bash
# Создание скрипта резервного копирования
sudo nano /usr/local/bin/pg_backup.sh
```

**Содержимое скрипта:**

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/postgresql"
DB_NAME="taobao_scraper"
DB_USER="taobao"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Резервная копия
pg_dump -U $DB_USER -d $DB_NAME -F c -f $BACKUP_DIR/${DB_NAME}_${DATE}.dump

# Удаление старых резервных копий (старше 7 дней)
find $BACKUP_DIR -name "${DB_NAME}_*.dump" -mtime +7 -delete

echo "Backup completed: ${DB_NAME}_${DATE}.dump"
```

**Установка прав и добавление в cron:**

```bash
sudo chmod +x /usr/local/bin/pg_backup.sh

# Добавление в crontab (ежедневно в 2:00)
sudo crontab -e
# Добавьте строку:
0 2 * * * /usr/local/bin/pg_backup.sh >> /var/log/pg_backup.log 2>&1
```

---

## 📊 Мониторинг и оптимизация

### Мониторинг производительности

```bash
# Активные запросы
SELECT pid, usename, datname, query, state, query_start 
FROM pg_stat_activity 
WHERE state != 'idle';

# Долгие запросы (> 1 минуты)
SELECT pid, now() - query_start AS duration, query 
FROM pg_stat_activity 
WHERE state = 'active' AND now() - query_start > interval '1 minute';

# Размер баз данных
SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size 
FROM pg_database 
ORDER BY pg_database_size(datname) DESC;

# Размер таблиц
SELECT schemaname, tablename, 
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Оптимизация конфигурации

**Основные параметры для настройки (postgresql.conf):**

```conf
# Память
shared_buffers = 256MB              # 25% от RAM для небольших серверов
effective_cache_size = 1GB          # 50-75% от RAM
work_mem = 16MB                     # Память для сортировки
maintenance_work_mem = 128MB        # Память для VACUUM, CREATE INDEX

# Подключения
max_connections = 100               # Максимальное количество подключений

# Логирование
log_min_duration_statement = 1000   # Логировать запросы > 1 сек
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '

# Автовакуум
autovacuum = on
autovacuum_max_workers = 3
```

**Применение изменений:**

```bash
sudo systemctl restart postgresql
```

### Проверка индексов

```bash
# Неиспользуемые индексы
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

# Размер индексов
SELECT schemaname, tablename, indexname, 
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
```

---

## 🔧 Решение проблем

### Проблема: PostgreSQL не запускается

```bash
# Проверка логов
sudo journalctl -u postgresql -n 50

# Проверка конфигурации
sudo -u postgres postgres --check-config

# Проверка прав на директорию данных
sudo ls -la /var/lib/postgresql/*/main
```

### Проблема: "permission denied for schema public"

```bash
# Выдача прав пользователю
sudo -u postgres psql -d taobao_scraper -c "
GRANT ALL ON SCHEMA public TO taobao;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO taobao;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO taobao;
"
```

### Проблема: "database does not exist"

```bash
# Проверка существующих баз данных
sudo -u postgres psql -l

# Создание базы данных (если отсутствует)
sudo -u postgres createdb taobao_scraper
```

### Проблема: "too many connections"

```bash
# Проверка текущих подключений
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Завершение долгих запросов
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'taobao_scraper' AND pid <> pg_backend_pid();

# Увеличение max_connections (если необходимо)
sudo nano /etc/postgresql/*/main/postgresql.conf
# Измените: max_connections = 200
sudo systemctl restart postgresql
```

### Проблема: Медленные запросы

```bash
# Включение pg_stat_statements (расширение для анализа запросов)
sudo -u postgres psql -d taobao_scraper -c "
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
"

# Топ медленных запросов
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### Проблема: Нехватка места на диске

```bash
# Проверка размера базы данных
sudo -u postgres psql -c "
SELECT pg_size_pretty(pg_database_size('taobao_scraper'));
"

# Очистка старых данных (VACUUM)
sudo -u postgres psql -d taobao_scraper -c "VACUUM FULL;"

# Удаление старых логов
sudo find /var/log/postgresql -name "*.log" -mtime +30 -delete
```

### Проблема: Ошибки подключения из приложения

```bash
# Проверка доступности порта
sudo netstat -tlnp | grep 5432

# Проверка firewall
sudo ufw status

# Проверка pg_hba.conf
sudo cat /etc/postgresql/*/main/pg_hba.conf | grep -v "^#"

# Тест подключения
psql -U taobao -d taobao_scraper -h localhost
```

---

## 🔗 Интеграция с проектом

### Настройка .env файла

```env
# PostgreSQL настройки
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=taobao_scraper
POSTGRES_USER=taobao
POSTGRES_PASSWORD=taobao_scraper
POSTGRES_SSLMODE=prefer
```

### Инициализация базы данных проекта

```bash
# Из корня проекта
python scripts/bootstrap_db.py
```

### Проверка подключения из Python

```python
# Тестовый скрипт
import asyncio
from src.db.session import get_async_session

async def test_connection():
    async with get_async_session() as session:
        result = await session.execute("SELECT version();")
        print(result.scalar())

asyncio.run(test_connection())
```

### Использование Alembic для миграций

```bash
# Создание миграции
alembic revision --autogenerate -m "Описание изменений"

# Применение миграций
alembic upgrade head

# Откат миграции
alembic downgrade -1
```

---

## 📚 Полезные ресурсы

- [Официальная документация PostgreSQL](https://www.postgresql.org/docs/)
- [PostgreSQL на Ubuntu](https://www.postgresql.org/download/linux/ubuntu/)
- [pgAdmin — веб-интерфейс для администрирования](https://www.pgadmin.org/)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)

---

## ✅ Чеклист безопасности

- [ ] Установлен надежный пароль для пользователя `postgres`
- [ ] Создан отдельный пользователь для приложения (не `postgres`)
- [ ] Настроен `pg_hba.conf` с использованием `md5` или `scram-sha-256`
- [ ] Включен SSL для удаленных подключений
- [ ] Настроен firewall для ограничения доступа
- [ ] Настроено автоматическое резервное копирование
- [ ] Включено логирование подключений и запросов
- [ ] Регулярно обновляется PostgreSQL
- [ ] Настроен мониторинг производительности
- [ ] Проверены права доступа пользователей

---

**Последнее обновление:** 2025-11-12  
**Версия документа:** 1.0

