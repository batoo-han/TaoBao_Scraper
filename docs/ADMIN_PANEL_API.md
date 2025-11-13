# API документация административной панели

> **Версия API:** 1.0.0

---

## 🔐 Аутентификация

Все защищенные endpoints требуют JWT токен в заголовке:

```
Authorization: Bearer <your-jwt-token>
```

Токен получается через `/api/admin/auth/login` и действителен 24 часа.

---

## 📋 Endpoints

### Аутентификация

#### `POST /api/admin/auth/login`

Вход в админ-панель.

**Request:**
```json
{
  "username": "your_telegram_username",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "telegram_id": 123456789,
    "username": "admin",
    "first_name": "Admin",
    "can_manage_keys": true,
    "can_view_stats": true,
    "can_manage_users": true
  }
}
```

#### `GET /api/admin/auth/me`

Получить информацию о текущем администраторе.

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "id": 1,
  "telegram_id": 123456789,
  "username": "admin",
  "first_name": "Admin",
  "can_manage_keys": true,
  "can_view_stats": true,
  "can_manage_users": true
}
```

#### `POST /api/admin/auth/logout`

Выход из админ-панели (удаление токена на клиенте).

---

### Настройки приложения

#### `GET /api/admin/settings`

Получить текущие настройки приложения.

**Response:**
```json
{
  "active_llm_vendor": "yandex",
  "llm_config": {},
  "consent_text": "Текст согласия на обработку ПД...",
  "updated_at": "2025-11-12T10:00:00Z"
}
```

#### `PUT /api/admin/settings/llm-provider`

Изменить активного LLM провайдера.

**Требует права:** `can_manage_keys`

**Request:**
```json
{
  "vendor": "openai",
  "config": {}
}
```

**Response:** `AppSettingsResponse`

#### `PUT /api/admin/settings/consent-text`

Обновить текст согласия на обработку ПД (ФЗ-152).

**Требует права:** `can_manage_keys`

**Request:**
```json
{
  "text": "Новый текст согласия..."
}
```

---

### LLM Провайдеры

#### `GET /api/admin/providers`

Получить список всех доступных провайдеров.

**Response:**
```json
[
  {
    "vendor": "yandex",
    "name": "YandexGPT",
    "is_active": true,
    "config": {
      "api_key": "***",
      "folder_id": "b1g...",
      "model": "yandexgpt-lite"
    }
  },
  {
    "vendor": "openai",
    "name": "OpenAI",
    "is_active": false,
    "config": {
      "api_key": "***",
      "model": "gpt-4o-mini"
    }
  }
]
```

#### `GET /api/admin/providers/{vendor}/config`

Получить конфигурацию конкретного провайдера.

**Требует права:** `can_manage_keys`

**Response:**
```json
{
  "api_key": "***",
  "model": "gpt-4o-mini"
}
```

---

### Статистика

#### `GET /api/admin/stats/overview`

Получить общую статистику использования.

**Response:**
```json
{
  "total_users": 150,
  "active_users_30d": 45,
  "total_requests": 1250,
  "total_tokens": 125000,
  "active_provider": "yandex",
  "cache_hit_rate": 65.5,
  "requests_today": 25,
  "requests_this_week": 180,
  "requests_this_month": 450
}
```

#### `GET /api/admin/stats/users`

Получить статистику по пользователям.

**Query параметры:**
- `limit` (default: 100, max: 1000)
- `offset` (default: 0)

**Response:**
```json
[
  {
    "user_id": 1,
    "telegram_id": 123456789,
    "username": "user1",
    "first_name": "User",
    "total_requests": 50,
    "total_tokens": 5000,
    "last_request_at": "2025-11-12T10:00:00Z"
  }
]
```

#### `GET /api/admin/stats/providers`

Получить статистику по провайдерам.

**Response:**
```json
[
  {
    "vendor": "yandex",
    "total_requests": 1000,
    "total_tokens": 100000,
    "unique_users": 120,
    "cache_hits": 650,
    "cache_misses": 350
  }
]
```

---

### Пользователи

#### `GET /api/admin/users`

Получить список пользователей с пагинацией.

**Требует права:** `can_manage_users`

**Query параметры:**
- `page` (default: 1, min: 1)
- `page_size` (default: 20, min: 1, max: 100)
- `search` (optional) — поиск по username или first_name

**Response:**
```json
{
  "users": [...],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8
}
```

#### `GET /api/admin/users/{user_id}`

Получить детальную информацию о пользователе.

**Требует права:** `can_manage_users`

**Response:**
```json
{
  "id": 1,
  "telegram_id": 123456789,
  "username": "user1",
  "first_name": "User",
  "last_name": "Name",
  "language_code": "ru",
  "is_admin": false,
  "created_at": "2025-11-01T10:00:00Z",
  "updated_at": "2025-11-12T10:00:00Z",
  "settings": {
    "signature": "@annabbox",
    "default_currency": "cny",
    "exchange_rate": null,
    "exchange_rate_at": null
  }
}
```

#### `PUT /api/admin/users/{user_id}`

Обновить информацию о пользователе.

**Требует права:** `can_manage_users`

**Request:**
```json
{
  "first_name": "New Name",
  "last_name": "New Last Name",
  "is_admin": false
}
```

#### `POST /api/admin/users/{user_id}/make-admin`

Назначить пользователя администратором.

**Требует права:** `can_manage_users`

**Response:**
```json
{
  "message": "Пользователь user1 назначен администратором"
}
```

#### `DELETE /api/admin/users/{user_id}/revoke-admin`

Отозвать права администратора у пользователя.

**Требует права:** `can_manage_users`

---

### Аудит персональных данных

#### `GET /api/admin/audit`

Получить список записей аудита с фильтрацией.

**Query параметры:**
- `page` (default: 1)
- `page_size` (default: 50, max: 200)
- `action` (optional) — тип действия
- `user_id` (optional) — ID пользователя
- `date_from` (optional) — начало периода (ISO format)
- `date_to` (optional) — конец периода (ISO format)

**Response:**
```json
{
  "logs": [
    {
      "id": 1,
      "actor_id": 1,
      "actor_username": "admin",
      "target_user_id": 2,
      "target_username": "user1",
      "action": "view_profile",
      "details": {},
      "created_at": "2025-11-12T10:00:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 50,
  "total_pages": 2
}
```

#### `GET /api/admin/audit/{log_id}`

Получить детальную информацию о записи аудита.

#### `GET /api/admin/audit/export/csv`

Экспортировать записи аудита в CSV.

**Query параметры:**
- `date_from` (optional)
- `date_to` (optional)

**Response:** CSV файл

---

## 🔒 Права доступа

| Право | Описание | Endpoints |
|-------|----------|-----------|
| `can_manage_keys` | Управление ключами и настройками | `/settings/*`, `/providers/*` |
| `can_view_stats` | Просмотр статистики | `/stats/*` |
| `can_manage_users` | Управление пользователями | `/users/*` |

Все админы могут просматривать аудит (`/audit/*`).

---

## 📝 Коды ошибок

- `401 Unauthorized` — невалидный или отсутствующий токен
- `403 Forbidden` — недостаточно прав доступа
- `404 Not Found` — ресурс не найден
- `400 Bad Request` — невалидные данные запроса
- `500 Internal Server Error` — внутренняя ошибка сервера

---

**Последнее обновление:** 2025-11-12

