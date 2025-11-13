# Улучшения админ-панели

## Выполнено

### 1. Расширенная модель настроек
- Добавлены поля `app_config` и `platforms_config` в модель `AppSettings`
- Создана миграция `002_add_app_config_fields.py`
- Обновлен сервис `AppSettingsService` с методами для работы с новыми настройками

### 2. API Endpoints для настроек

#### Настройки приложения (`/api/admin/settings`)
- `GET /api/admin/settings` - получить все настройки
- `PUT /api/admin/settings/app-config` - обновить настройки приложения (BOT_TOKEN, API ключи и т.д.)
- `GET /api/admin/settings/llm-prompt` - получить настройки промпта
- `PUT /api/admin/settings/llm-prompt` - обновить промпт, температуру, макс. токенов
- `GET /api/admin/settings/platforms` - получить настройки платформ
- `PUT /api/admin/settings/platforms` - включить/выключить платформу

### 3. API для логов (`/api/admin/logs`)
- `GET /api/admin/logs` - получить последние строки логов (с фильтрацией по уровню и поиском)
- `GET /api/admin/logs/stream` - потоковая передача логов в реальном времени (SSE)
- `GET /api/admin/logs/download` - выгрузить логи в виде файла

### 4. Статистика по платформам
- `GET /api/admin/stats/platforms` - получить статистику по платформам (Taobao, Pinduoduo, Szwego, 1688)

## Что нужно сделать

### 1. Применить миграцию
```bash
python -m alembic upgrade head
```

### 2. Обновить веб-интерфейс

Нужно создать/обновить следующие разделы в `admin_web/`:

#### Настройки (`admin_web/settings.html`)
- Раздел "Основные настройки" (BOT_TOKEN, API ключи, база данных)
- Раздел "LLM настройки" (провайдер, промпт, температура, токены)
- Раздел "Платформы" (включение/выключение Taobao, Pinduoduo, Szwego, 1688)
- Раздел "Персональные данные" (включение/выключение ПД, текст согласия)
- Раздел "Системные настройки" (DEBUG_MODE, MOCK_MODE и т.д.)

#### Логи (`admin_web/logs.html`)
- Просмотр логов с фильтрацией
- Потоковая передача в реальном времени
- Выгрузка логов

#### Статистика (`admin_web/stats.html`)
- Общая статистика
- Статистика по пользователям
- Статистика по провайдерам
- Статистика по платформам

#### Документация (`admin_web/docs.html`)
- Документация для админов
- Документация для разработчиков
- Ссылки на документацию проекта

#### Биллинг (`admin_web/billing.html`)
- Мониторинг подписок
- История платежей (пока пусто, для будущего)

#### Дашборд (`admin_web/index.html`)
- Сделать иконки кликабельными
- Добавить ссылки на соответствующие разделы

### 3. Интеграция настроек из БД

Нужно обновить `src/core/config.py` для загрузки настроек из БД:
- При старте приложения загружать настройки из `app_config`
- Применять настройки налету (без перезагрузки)
- Сохранять изменения в БД при обновлении через админку

### 4. Система логирования

Настроить логирование в файл:
- Создать директорию `logs/`
- Настроить ротацию логов
- Интегрировать с существующей системой логирования

## Структура настроек в app_config

```json
{
  "BOT_TOKEN": "...",
  "YANDEX_GPT_API_KEY": "...",
  "YANDEX_FOLDER_ID": "...",
  "YANDEX_GPT_MODEL": "yandexgpt-lite",
  "OPENAI_API_KEY": "...",
  "OPENAI_MODEL": "gpt-4o-mini",
  "PROXIAPI_API_KEY": "...",
  "PROXIAPI_MODEL": "gpt-4o-mini",
  "TMAPI_TOKEN": "...",
  "EXCHANGE_RATE_API_KEY": "...",
  "POSTGRES_HOST": "localhost",
  "POSTGRES_PORT": 5432,
  "POSTGRES_DB": "taobao_scraper",
  "POSTGRES_USER": "taobao",
  "POSTGRES_PASSWORD": "...",
  "POSTGRES_SSLMODE": "prefer",
  "DEFAULT_SIGNATURE": "@annabbox",
  "DEFAULT_CURRENCY": "cny",
  "DEFAULT_LLM_VENDOR": "yandex",
  "LLM_CACHE_TTL_MINUTES": 240,
  "ADMIN_CHAT_ID": "...",
  "DEBUG_MODE": false,
  "MOCK_MODE": false,
  "DISABLE_SSL_VERIFY": false,
  "ADMIN_JWT_SECRET": "...",
  "ADMIN_PANEL_PORT": 8004,
  "PERSONAL_DATA_ENABLED": true
}
```

## Структура platforms_config

```json
{
  "taobao": {
    "enabled": true
  },
  "pinduoduo": {
    "enabled": true
  },
  "szwego": {
    "enabled": false
  },
  "1688": {
    "enabled": false
  }
}
```

