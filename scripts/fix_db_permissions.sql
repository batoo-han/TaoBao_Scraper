-- Скрипт для выдачи прав пользователю PostgreSQL
-- Выполните этот скрипт от имени суперпользователя (обычно postgres)

-- 1. Выдаём права на схему public
GRANT ALL ON SCHEMA public TO taobao;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO taobao;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO taobao;

-- 2. Выдаём права на создание таблиц в будущем
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO taobao;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO taobao;

-- 3. Если схема public не существует, создаём её
CREATE SCHEMA IF NOT EXISTS public;

-- 4. Выдаём права на использование схемы
GRANT USAGE ON SCHEMA public TO taobao;
GRANT CREATE ON SCHEMA public TO taobao;

