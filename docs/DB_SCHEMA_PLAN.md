# PostgreSQL Schema Plan (Personalized Bot Update)

## Overview

The new functionality introduces per-user personalization, centralized provider settings, audit requirements, and admin tooling.  
All persistent data will live in PostgreSQL. Below is the initial schema to unblock implementation.  
Migrations will be maintained with Alembic.

## Conventions

| Item                 | Rule / Notes                                  |
|----------------------|-----------------------------------------------|
| Primary keys         | `BIGSERIAL` (`id` column)                     |
| Foreign keys         | `ON DELETE CASCADE` unless noted              |
| Timestamps           | `TIMESTAMP WITH TIME ZONE`                    |
| Monetary fields      | `NUMERIC(14,2)` (convert raw floats at edges) |
| JSON payloads        | `JSONB`                                       |
| Soft delete          | not required for v1                           |

## Tables

### `users`
Stores Telegram users that interacted with the bot.

| Column            | Type                       | Notes                                               |
|-------------------|----------------------------|-----------------------------------------------------|
| id                | BIGSERIAL PK               | internal id                                         |
| telegram_id       | BIGINT UNIQUE NOT NULL     | Telegram user ID                                    |
| username          | TEXT                       | `@username` if available                            |
| first_name        | TEXT                       | optional                                            |
| last_name         | TEXT                       | optional                                            |
| language_code     | TEXT                       | e.g. `ru`, `en`                                     |
| is_admin          | BOOLEAN DEFAULT FALSE      | quick flag; detailed roles live in `admin_users`    |
| created_at        | TIMESTAMPTZ DEFAULT now()  |                                                     |
| updated_at        | TIMESTAMPTZ                | maintained via trigger                              |

### `user_settings`
Per-user personalization (1-1 with `users`).

| Column            | Type                       | Notes                                                       |
|-------------------|----------------------------|-------------------------------------------------------------|
| id                | BIGSERIAL PK               |                                                             |
| user_id           | BIGINT FK -> users(id)     | UNIQUE (one row per user)                                   |
| signature         | TEXT                       | default `@annabbox`                                         |
| default_currency  | TEXT NOT NULL              | `cny` or `rub` (enum later)                                 |
| exchange_rate     | NUMERIC(14,4)              | only relevant when currency = `rub`; nullable               |
| exchange_rate_at  | TIMESTAMPTZ                | when user last set rate                                     |
| preferences       | JSONB                      | reserved for future flags                                   |
| created_at        | TIMESTAMPTZ DEFAULT now()  |                                                             |
| updated_at        | TIMESTAMPTZ                | maintained via trigger                                      |

### `app_settings`
Global configuration controlled by admin (single row).

| Column            | Type                       | Notes                                   |
|-------------------|----------------------------|-----------------------------------------|
| id                | SMALLINT PK                | always `1`                              |
| active_llm_vendor | TEXT NOT NULL              | `yandex`, `openai`, `proxiapi`          |
| llm_config        | JSONB                      | provider-specific settings              |
| consent_text      | TEXT                       | full PD consent text (current revision) |
| updated_at        | TIMESTAMPTZ                |                                         |

### `llm_cache`
Cache responses to avoid redundant LLM calls.

| Column            | Type                       | Notes                                                       |
|-------------------|----------------------------|-------------------------------------------------------------|
| id                | BIGSERIAL PK               |                                                             |
| vendor            | TEXT NOT NULL              | `yandex`, `openai`, `proxiapi`                              |
| cache_key         | TEXT NOT NULL              | hashed/computed key (index unique)                          |
| request_payload   | JSONB                      | sanitized request                                           |
| response_payload  | JSONB                      | cached response                                             |
| created_at        | TIMESTAMPTZ DEFAULT now()  |                                                             |
| expires_at        | TIMESTAMPTZ                | nullable; admin-configurable TTL                            |

Indexes:
- `UNIQUE (vendor, cache_key)`
- TTL cleanup job can prune expired rows.

### `usage_stats`
Aggregated counters for analytics and dashboards.

| Column            | Type                       | Notes                                                       |
|-------------------|----------------------------|-------------------------------------------------------------|
| id                | BIGSERIAL PK               |                                                             |
| user_id           | BIGINT FK -> users(id)     | nullable (system-level metrics)                             |
| vendor            | TEXT                       |                                                             |
| total_requests    | INTEGER DEFAULT 0          |                                                             |
| total_tokens      | INTEGER DEFAULT 0          | optional if vendor supplies token usage                    |
| last_request_at   | TIMESTAMPTZ                |                                                             |

### `pd_audit_log`
Mandatory log for operations with personal data (ФЗ-152).

| Column            | Type                       | Notes                                                           |
|-------------------|----------------------------|-----------------------------------------------------------------|
| id                | BIGSERIAL PK               |                                                                 |
| actor_id          | BIGINT FK -> users(id)     | кто выполнял действие (для админов)                            |
| target_user_id    | BIGINT FK -> users(id)     | над кем выполняли действие                                     |
| action            | TEXT NOT NULL              | e.g. `view_profile`, `update_settings`, `export_data`           |
| details           | JSONB                      | что именно менялось/просматривалось                            |
| created_at        | TIMESTAMPTZ DEFAULT now()  |                                                                 |

### `admin_users`
Дополнительные параметры для админов (если нужна отдельная аутентификация).

| Column            | Type                       | Notes                                  |
|-------------------|----------------------------|----------------------------------------|
| id                | BIGSERIAL PK               |                                        |
| user_id           | BIGINT FK -> users(id)     |                                        |
| can_manage_keys   | BOOLEAN DEFAULT FALSE      |                                        |
| can_view_stats    | BOOLEAN DEFAULT TRUE       |                                        |
| can_manage_users  | BOOLEAN DEFAULT TRUE       |                                        |
| notes             | TEXT                       |                                        |
| created_at        | TIMESTAMPTZ DEFAULT now()  |                                        |

### `subscriptions` (future-proof)

| Column           | Type                       | Notes                                        |
|------------------|----------------------------|----------------------------------------------|
| id               | BIGSERIAL PK               |                                              |
| user_id          | BIGINT FK -> users(id)     |                                              |
| plan             | TEXT                       | `free`, `pro`, etc.                          |
| started_at       | TIMESTAMPTZ                |                                              |
| expires_at       | TIMESTAMPTZ                |                                              |
| status           | TEXT                       | `active`, `cancelled`, `expired`             |
| metadata         | JSONB                      | payment reference, gateway data              |

## Migrations

1. Initialize Alembic (`alembic init`).
2. Generate migration for the schema above.
3. Add triggers for automatic `updated_at`.
4. Seed `app_settings` row with default provider and consent text placeholder.

## Next Steps

- Implement repository/service layers to interact with the tables.
- Update bot handlers to read/write user settings.
- Wire up admin API endpoints to manage `app_settings`, `usage_stats`, `pd_audit_log`.
- Add periodic task to prune expired cache entries.


