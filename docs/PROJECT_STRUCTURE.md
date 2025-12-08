# 📂 Структура проекта

## Обзор

Проект организован по модульному принципу с четким разделением ответственности.

```
TaoBao_Scraper_2/
├── main.py                       # 🚀 Точка входа приложения
├── src/                          # 📦 Исходный код
│   ├── __init__.py
│   ├── bot/                      # 🤖 Telegram бот
│   │   ├── __init__.py
│   │   ├── handlers.py           # Обработчики сообщений
│   │   └── error_handler.py      # Обработка ошибок
│   ├── api/                      # 🌐 Внешние API
│   │   ├── __init__.py
│   │   ├── tmapi.py              # TMAPI клиент (Taobao/Tmall/Pinduoduo)
│   │   ├── yandex_gpt.py         # YandexGPT клиент
│   │   ├── openai_client.py      # OpenAI клиент
│   │   ├── llm_provider.py       # Переключение провайдеров LLM
│   │   ├── prompts.py            # Общие промпты для генерации описаний
│   │   ├── yandex_translate.py   # Yandex.Translate клиент
│   │   └── exchange_rate.py      # Курсы валют
│   ├── core/                     # 🧠 Бизнес-логика
│   │   ├── __init__.py
│   │   ├── scraper.py            # Основной оркестратор
│   │   └── config.py             # Настройки приложения
│   ├── webapp/                   # 🧩 Mimi App (Mini App в Telegram)
│   │   ├── __init__.py
│   │   ├── auth.py               # Проверка подписи initData
│   │   ├── server.py             # aiohttp сервер и REST API
│   │   └── static/               # HTML/CSS/JS фронтенд для Mimi App
│   └── utils/                    # 🛠️ Утилиты
│       ├── __init__.py
│       └── url_parser.py         # Парсинг URL и определение платформы
├── docs/                         # 📚 Документация
├── other/                        # 📁 Вспомогательные файлы
├── requirements.txt              # 📋 Python зависимости
├── Dockerfile                    # 🐳 Docker конфигурация
├── docker-compose.yml
├── .env                          # 🔐 Переменные окружения
├── .gitignore
├── README.md
└── LICENSE
```

---

## ✍️ Стандарты оформления документации

- списки (включая вложенные и чек-листы) всегда начинаются со строчной буквы, даже внутри примеров и блоков кода
- после чекбоксов `- [ ]` текст также пишется со строчной буквы
- если элемент обязан начинаться с аббревиатуры, добавляем короткое пояснение перед ней в строчном виде (`- используется tmapi api ...`)
- исключения (например, официальные названия брендов) явно описываем примечанием рядом со списком

---

## 📦 Описание модулей

### `src/bot/` - Telegram бот

**Назначение:** Обработка взаимодействий с пользователями через Telegram

#### `handlers.py`
- обработчики команд (`/start`)
- обработчики сообщений (ссылки на товары)
- router для aiogram
- отправка typing action

**Зависимости:**
- `src.core.scraper` - для парсинга товаров
- `src.bot.error_handler` - для обработки ошибок

#### `error_handler.py`
- централизованная обработка ошибок
- user-friendly сообщения для пользователей
- уведомления админам
- логирование в файл с ротацией

**Зависимости:**
- `src.core.config` - для настроек

---

### `src/api/` - Внешние API клиенты

**Назначение:** Взаимодействие с внешними сервисами

#### `tmapi.py`
- клиент для tmapi.top
- поддержка Taobao, Tmall, 1688 и Pinduoduo
- автоматическое определение платформы
- rate limiting (контроль частоты запросов)

**Методы:**
- `get_product_info_auto(url)` - универсальный метод с автоопределением платформы
- `get_product_info(url)` - taobao/Tmall
- `get_ali_product_by_url(url)` - 1688 по url
- `get_ali_product_by_id(item_id)` - 1688 по id
- `get_pinduoduo_product(url)` - pinduoduo
- `get_item_description(item_id, platform)` - детальные изображения taobao/Tmall/1688

**Зависимости:**
- `src.core.config` - настройки (api токены, rate limit)
- `src.utils.url_parser` - определение платформы

#### `yandex_gpt.py`
- клиент для YandexGPT (генерация постов)
- формирование промптов
- парсинг JSON ответов

**Зависимости:**
- `src.core.config` - api ключ, model, folder_id

#### `openai_client.py`
- асинхронный клиент OpenAI (`AsyncOpenAI`)
- поддержка моделей `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-4o`, `o4-mini`
- строгий JSON-ответ через `response_format`

**Зависимости:**
- `src.core.config` - ключ и модель

#### `llm_provider.py`
- фабрика провайдеров (YandexGPT/OpenAI) с кэшированием
- читает `DEFAULT_LLM` и валидирует значение
- возвращает единый интерфейс `generate_post_content`

#### `prompts.py`
- хранит шаблоны промптов
- используется обоими провайдерами для полностью идентичного поведения

#### `yandex_translate.py`
- клиент для Yandex.Translate
- перевод китайских названий на русский

**Зависимости:**
- `src.core.config` - api ключ

#### `exchange_rate.py`
- клиент для ExchangeRate-API
- получение курса CNY → RUB
- кэширование (1 раз в день)

**Зависимости:**
- `src.core.config` - api ключ

---

### `src/core/` - Основная бизнес-логика

**Назначение:** Ключевая логика приложения

#### `scraper.py`
- **главный оркестратор** - координирует работу всех модулей
- парсинг товаров с разных платформ
- обработка изображений (фильтрация, определение размеров)
- генерация финального поста

**Workflow:**
```
1. Получение данных → tmapi.py
2. Генерация LLM контента → llm_provider.py → (yandex_gpt.py или openai_client.py)
3. Получение курса валют → exchange_rate.py
4. Получение detail изображений → tmapi.py
5. Фильтрация изображений → встроенная логика
6. Формирование поста → встроенная логика
7. Возврат (text, images)
```

**Зависимости:**
- `src.api.tmapi` - получение данных о товарах
- `src.api.yandex_gpt` - генерация контента
- `src.api.exchange_rate` - курсы валют
- `src.api.yandex_translate` - перевод
- `src.core.config` - настройки

#### `config.py`
- управление настройками через `.env`
- использует `pydantic-settings` для валидации
- экспортирует глобальный объект `settings`

**Настройки:**
- api токены (TMAPI, YandexGPT, ExchangeRate, etc.)
- режимы работы (DEBUG_MODE, MOCK_MODE)
- rate limiting
- admin chat ID

**Зависимости:** Нет (leaf module)

---

### `src/utils/` - Вспомогательные утилиты

**Назначение:** Общие функции и хелперы

#### `url_parser.py`
- определение платформы по URL (Taobao/Tmall/1688/Pinduoduo)
- извлечение item_id из URL Pinduoduo
- класс `URLParser` с статическими методами
- константы платформ (`Platform.TAOBAO`, `Platform.ALI1688`, `Platform.PINDUODUO`, etc.)

**Методы:**
- `detect_platform(url)` - определяет платформу
- `extract_pinduoduo_id(url)` - извлекает id из Pinduoduo URL
- `parse_url(url)` - комплексный анализ (платформа + id)

---

### `src/webapp/` - Mimi App для Telegram

**Назначение:** мини-приложение Telegram (WebApp), которое запускается из меню бота.

#### `server.py`
- `MiniAppServer` на `aiohttp`, обслуживает REST API, отдаёт статику и имеет healthcheck;
- маршруты `/mini-app/api/...` управляют пользовательскими и административными настройками;
- вшита проверка подписи `initData` и прав администратора.

#### `auth.py`
- функция `validate_init_data` реализует официальную схему валидации хэша Telegram;
- возвращает контекст пользователя с безопасным временем жизни.

#### `static/`
- `index.html`, `styles.css`, `app.js` — адаптивный интерфейс без сторонних фреймворков;
- `app.js` общается с API через Telegram WebApp SDK и показывает отдельные сценарии для пользователя/админа.

**Зависимости:** Нет (leaf module)

---

## 🔄 Поток данных

```
┌─────────────────────────────────────────────────────┐
│  USER (Telegram)                                    │
│  Отправляет ссылку на товар                         │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  src/bot/handlers.py                                │
│  - Получает сообщение                               │
│  - Отправляет typing action                         │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  src/core/scraper.py                                │
│  Оркестрирует процесс парсинга                      │
└─────────────────────────────────────────────────────┘
                        ↓
        ┌───────────────┴───────────────┐
        ↓                               ↓
┌───────────────────┐         ┌────────────────────┐
│ src/api/tmapi.py  │         │ src/utils/         │
│ - Определение     │←────────│ url_parser.py      │
│   платформы       │         │ - Парсинг URL      │
│ - Получение       │         └────────────────────┘
│   данных          │
└───────────────────┘
        ↓
┌───────────────────────────────────┐
│ src/api/llm_provider.py           │
│ - Выбор YandexGPT/OpenAI          │
│ - Генерация title/description     │
│ - Валидация JSON                  │
└───────────────────────────────────┘
        ↓
┌───────────────────────────────────┐
│ src/api/exchange_rate.py          │
│ - Получение курса CNY → RUB       │
└───────────────────────────────────┘
        ↓
┌───────────────────────────────────┐
│ src/core/scraper.py               │
│ - Фильтрация изображений          │
│ - Формирование поста              │
└───────────────────────────────────┘
        ↓
┌───────────────────────────────────┐
│ src/bot/handlers.py               │
│ - Отправка поста с изображениями  │
└───────────────────────────────────┘
        ↓
┌───────────────────────────────────┐
│ USER (Telegram)                   │
│ Получает готовый пост             │
└───────────────────────────────────┘
```

---

## 🚀 Точка входа (main.py)

**Ответственность:**
- инициализация aiogram (Bot, Dispatcher)
- настройка error handler
- регистрация роутера
- запуск long polling

**Минималистичный дизайн:** всё остальное делегируется модулям

---

## 📝 Как добавить новую функциональность

### Добавление нового API клиента

1. Создайте файл `src/api/new_service.py`
2. Создайте класс клиента (например, `NewServiceClient`)
3. Добавьте в `src/api/__init__.py`:
```python
from .new_service import NewServiceClient
__all__ = [..., 'NewServiceClient']
```
4. Используйте в `scraper.py`:
```python
from src.api.new_service import NewServiceClient
```

### Добавление новой утилиты

1. Создайте файл `src/utils/new_util.py`
2. Добавьте функции или классы
3. Добавьте в `src/utils/__init__.py`:
```python
from .new_util import YourClass
__all__ = [..., 'YourClass']
```

### Добавление нового обработчика бота

1. В `src/bot/handlers.py` добавьте новый handler:
```python
@router.message(...)
async def new_handler(message: Message):
    ...
```

### Добавление новой настройки

1. В `src/core/config.py` добавьте поле в класс `Settings`:
```python
class Settings(BaseSettings):
    NEW_SETTING: str = "default_value"
```
2. Добавьте в `.env`:
```env
NEW_SETTING=your_value
```

---

## 🎯 Преимущества новой структуры

### ✅ Масштабируемость
- легко добавлять новые модули без засорения корня
- можно создавать подпапки (например, `src/api/clients/`, `src/bot/middlewares/`)

### ✅ Читаемость
- сразу понятно назначение каждого модуля
- логическая группировка по функциональности

### ✅ Maintainability
- изменения в одном модуле не влияют на другие
- легко находить нужный код

### ✅ Тестируемость
- каждый модуль можно тестировать независимо
- минимум зависимостей между модулями

### ✅ Стандартность
- привычная структура для Python проектов
- следует best practices (src/ layout)

---

## ⚠️ Важные правила

### 1. Избегайте циклических импортов
❌ **Неправильно:**
```python
# src/core/__init__.py
from .scraper import Scraper
from .config import settings

# src/api/tmapi.py
from src.core import settings  # ❌ Цикл!
```

✅ **Правильно:**
```python
# src/api/tmapi.py
from src.core.config import settings  # ✅ Прямой импорт
```

### 2. Используйте прямые импорты для leaf модулей
- `config.py` и `url_parser.py` - leaf модули (нет зависимостей)
- импортируйте их напрямую: `from src.core.config import settings`

### 3. Держите `__init__.py` простыми
- экспортируйте только основные классы
- не добавляйте логику

### 4. Один модуль = одна ответственность
- не смешивайте API клиенты с бизнес-логикой
- не добавляйте обработчики бота в scraper

---

## 📚 Дополнительная документация

- `docs/pinduoduo_INTEGRATION.md` - интеграция Pinduoduo
- `docs/architecture.md` - общая архитектура
- `docs/quick_START.md` - быстрый старт
- `readme.md` - основная информация о проекте
