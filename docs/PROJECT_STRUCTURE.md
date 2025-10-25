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
│   │   ├── yandex_translate.py   # Yandex.Translate клиент
│   │   └── exchange_rate.py      # Курсы валют
│   ├── core/                     # 🧠 Бизнес-логика
│   │   ├── __init__.py
│   │   ├── scraper.py            # Основной оркестратор
│   │   └── config.py             # Настройки приложения
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

## 📦 Описание модулей

### `src/bot/` - Telegram бот

**Назначение:** Обработка взаимодействий с пользователями через Telegram

#### `handlers.py`
- Обработчики команд (`/start`)
- Обработчики сообщений (ссылки на товары)
- Router для aiogram
- Отправка typing action

**Зависимости:**
- `src.core.scraper` - для парсинга товаров
- `src.bot.error_handler` - для обработки ошибок

#### `error_handler.py`
- Централизованная обработка ошибок
- User-friendly сообщения для пользователей
- Уведомления админам
- Логирование в файл с ротацией

**Зависимости:**
- `src.core.config` - для настроек

---

### `src/api/` - Внешние API клиенты

**Назначение:** Взаимодействие с внешними сервисами

#### `tmapi.py`
- Клиент для TMAPI (tmapi.top)
- Поддержка Taobao, Tmall, Pinduoduo
- Автоматическое определение платформы
- Rate limiting (контроль частоты запросов)

**Методы:**
- `get_product_info_auto(url)` - универсальный метод с автоопределением платформы
- `get_product_info(url)` - Taobao/Tmall
- `get_pinduoduo_product(url)` - Pinduoduo
- `get_item_description(item_id)` - детальные изображения Taobao/Tmall

**Зависимости:**
- `src.core.config` - настройки (API токены, rate limit)
- `src.utils.url_parser` - определение платформы

#### `yandex_gpt.py`
- Клиент для YandexGPT (генерация постов)
- Формирование промптов
- Парсинг JSON ответов

**Зависимости:**
- `src.core.config` - API ключ, model, folder_id

#### `yandex_translate.py`
- Клиент для Yandex.Translate
- Перевод китайских названий на русский

**Зависимости:**
- `src.core.config` - API ключ

#### `exchange_rate.py`
- Клиент для ExchangeRate-API
- Получение курса CNY → RUB
- Кэширование (1 раз в день)

**Зависимости:**
- `src.core.config` - API ключ

---

### `src/core/` - Основная бизнес-логика

**Назначение:** Ключевая логика приложения

#### `scraper.py`
- **Главный оркестратор** - координирует работу всех модулей
- Парсинг товаров с разных платформ
- Обработка изображений (фильтрация, определение размеров)
- Генерация финального поста

**Workflow:**
```
1. Получение данных → tmapi.py
2. Генерация LLM контента → yandex_gpt.py
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
- Управление настройками через `.env`
- Использует `pydantic-settings` для валидации
- Экспортирует глобальный объект `settings`

**Настройки:**
- API токены (TMAPI, YandexGPT, ExchangeRate, etc.)
- Режимы работы (DEBUG_MODE, MOCK_MODE)
- Rate limiting
- Admin chat ID

**Зависимости:** Нет (leaf module)

---

### `src/utils/` - Вспомогательные утилиты

**Назначение:** Общие функции и хелперы

#### `url_parser.py`
- Определение платформы по URL (Taobao/Tmall/Pinduoduo)
- Извлечение item_id из URL Pinduoduo
- Класс `URLParser` с статическими методами
- Константы платформ (`Platform.TAOBAO`, `Platform.PINDUODUO`, etc.)

**Методы:**
- `detect_platform(url)` - определяет платформу
- `extract_pinduoduo_id(url)` - извлекает ID из Pinduoduo URL
- `parse_url(url)` - комплексный анализ (платформа + ID)

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
│ src/api/yandex_gpt.py             │
│ - Генерация title/description     │
│ - Извлечение характеристик        │
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
- Инициализация aiogram (Bot, Dispatcher)
- Настройка error handler
- Регистрация роутера
- Запуск long polling

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
- Легко добавлять новые модули без засорения корня
- Можно создавать подпапки (например, `src/api/clients/`, `src/bot/middlewares/`)

### ✅ Читаемость
- Сразу понятно назначение каждого модуля
- Логическая группировка по функциональности

### ✅ Maintainability
- Изменения в одном модуле не влияют на другие
- Легко находить нужный код

### ✅ Тестируемость
- Каждый модуль можно тестировать независимо
- Минимум зависимостей между модулями

### ✅ Стандартность
- Привычная структура для Python проектов
- Следует best practices (src/ layout)

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
- Импортируйте их напрямую: `from src.core.config import settings`

### 3. Держите `__init__.py` простыми
- Экспортируйте только основные классы
- Не добавляйте логику

### 4. Один модуль = одна ответственность
- Не смешивайте API клиенты с бизнес-логикой
- Не добавляйте обработчики бота в scraper

---

## 📚 Дополнительная документация

- `docs/PINDUODUO_INTEGRATION.md` - интеграция Pinduoduo
- `docs/ARCHITECTURE.md` - общая архитектура
- `docs/QUICK_START.md` - быстрый старт
- `README.md` - основная информация о проекте

