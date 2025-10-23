# 🤖 Taobao/Tmall Product Scraper Bot

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-green.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![Telegram](https://img.shields.io/badge/telegram-bot-blue.svg)

> **Профессиональный Telegram бот для парсинга товаров с Taobao и Tmall с автоматической генерацией красивых описаний на русском языке.**

---

## 📋 Содержание

- [Возможности](#возможности)
- [Быстрый старт](#быстрый-старт)
- [Установка](#установка)
- [Конфигурация](#конфигурация)
- [Использование](#использование)
- [Docker](#docker)
- [Документация](#документация)
- [Лицензия](#лицензия)

---

## ✨ Возможности

### 🎯 Основные функции
- ✅ **Парсинг товаров** с Taobao и Tmall по ссылке
- ✅ **Автоматическая генерация описаний** на русском через YandexGPT
- ✅ **Умная фильтрация изображений** (удаление баннеров, дубликатов)
- ✅ **Динамическое определение характеристик** товара
- ✅ **Извлечение цен** из вариантов товара
- ✅ **Профессиональная обработка ошибок** с уведомлениями администратора

### 🛠️ Технические особенности
- 🔄 **Индикатор "печатает"** во время обработки
- 📊 **Автоматическая ротация логов** (100 МБ × 3 файла)
- 🐳 **Docker-ready** с docker-compose
- 🔒 **Безопасность**: non-root пользователь, SSL сертификаты
- 📝 **Подробное логирование** всех ошибок
- ⚙️ **Гибкая конфигурация** через .env файл

### 🎨 Качество описаний
- 🌐 **Полный перевод** на русский (включая цвета и бренды)
- 🎯 **Динамический выбор** характеристик по типу товара
- 🚫 **Фильтрация** нерелевантной информации
- ❌ **Исключение** дат и возрастных ограничений
- 📐 **Умное форматирование** размеров (диапазоны, списки)

---

## 🚀 Быстрый старт

### Предварительные требования

- Python 3.11+ ИЛИ Docker
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- YandexGPT API Key ([Yandex Cloud](https://yandex.cloud))
- TMAPI Token ([tmapi.top](https://tmapi.top))

### Установка за 3 шага

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/yourusername/taobao-scraper-bot.git
cd taobao-scraper-bot

# 2. Настройте окружение
cp .env.example .env
# Отредактируйте .env и добавьте свои API ключи

# 3. Запустите через Docker
docker-compose up -d
```

**Готово!** 🎉 Бот запущен и готов к работе.

---

## 📦 Установка

### Вариант 1: Docker (рекомендуется)

```bash
# Клонируйте репозиторий
git clone https://github.com/yourusername/taobao-scraper-bot.git
cd taobao-scraper-bot

# Создайте .env из примера
cp .env.example .env
# Отредактируйте .env

# Соберите и запустите
docker-compose up -d

# Проверьте логи
docker-compose logs -f
```

### Вариант 2: Локальная установка

```bash
# Клонируйте репозиторий
git clone https://github.com/yourusername/taobao-scraper-bot.git
cd taobao-scraper-bot

# Создайте виртуальное окружение
python -m venv .venv

# Активируйте виртуальное окружение
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Создайте .env из примера
cp .env.example .env
# Отредактируйте .env

# Запустите бота
python autoparse.py
```

---

## ⚙️ Конфигурация

### Обязательные переменные

Отредактируйте `.env` файл:

```env
# Telegram Bot Token
BOT_TOKEN=your_telegram_bot_token

# YandexGPT
YANDEX_GPT_API_KEY=your_yandex_gpt_key
YANDEX_FOLDER_ID=your_folder_id
YANDEX_GPT_MODEL=yandexgpt-lite

# TMAPI
TMAPI_TOKEN=your_tmapi_token

# Exchange Rate API (опционально)
EXCHANGE_RATE_API_KEY=your_exchange_rate_key
```

### Опциональные переменные

```env
# ID админа для уведомлений об ошибках
ADMIN_CHAT_ID=123456789

# Режимы работы
DEBUG_MODE=False      # Подробные логи
MOCK_MODE=False       # Использовать mock данные

# Конвертация валют
CONVERT_CURRENCY=False
```

### Получение API ключей

| Сервис | Где получить | Документация |
|--------|--------------|--------------|
| Telegram Bot | [@BotFather](https://t.me/BotFather) | [Docs](https://core.telegram.org/bots) |
| YandexGPT | [Yandex Cloud Console](https://console.yandex.cloud) | [Docs](https://yandex.cloud/ru/docs/yandexgpt) |
| TMAPI | [tmapi.top](https://tmapi.top) | [Docs](https://tmapi.top/docs) |
| Exchange Rate | [exchangerate-api.com](https://www.exchangerate-api.com) | [Docs](https://www.exchangerate-api.com/docs) |

---

## 💬 Использование

### Основные команды

- `/start` — Запустить бота и получить приветствие
- Отправьте **ссылку на товар** — Получить полное описание

### Поддерживаемые ссылки

Бот поддерживает все типы ссылок Taobao/Tmall:

```
✅ https://item.taobao.com/item.htm?id=123456
✅ https://detail.tmall.com/item.htm?id=123456
✅ https://a.m.taobao.com/i123456.htm
✅ https://s.click.taobao.com/...
✅ https://e.tb.cn/h.xxx (короткие ссылки)
```

### Пример работы

1. **Отправьте ссылку:**
   ```
   https://item.taobao.com/item.htm?id=123456
   ```

2. **Бот показывает:**
   ```
   Обрабатываю вашу ссылку, пожалуйста, подождите...
   [индикатор "печатает..." вверху чата]
   ```

3. **Получаете результат:**
   - 📸 Фотографии товара (вариации + детальные)
   - 📝 Описание на русском
   - 💰 Цена (максимальная из доступных)
   - 🎨 Цвета (если есть)
   - 📏 Размеры (если есть)
   - 🧵 Состав (для одежды)

---

## 🐳 Docker

### Команды Docker Compose

```bash
# Запустить бота
docker-compose up -d

# Остановить бота
docker-compose down

# Перезапустить бота
docker-compose restart

# Посмотреть логи
docker-compose logs -f

# Пересобрать образ
docker-compose build --no-cache
docker-compose up -d
```

### Обновление кода

```bash
# Остановите контейнер
docker-compose down

# Получите новый код
git pull

# Пересоберите и запустите
docker-compose build
docker-compose up -d
```

---

## 📚 Документация

Подробная документация находится в папке [`docs/`](docs/):

### 🎯 Быстрый старт
- [**QUICK_START.md**](docs/QUICK_START.md) — Быстрое начало работы
- [**SERVICES_SETUP.md**](docs/SERVICES_SETUP.md) — Настройка API сервисов

### 🏗️ Архитектура
- [**ARCHITECTURE.md**](docs/ARCHITECTURE.md) — Архитектура проекта
- [**NEW_ARCHITECTURE.md**](docs/NEW_ARCHITECTURE.md) — Обновлённая архитектура

### 🔧 Конфигурация
- [**DEBUG_AND_MOCK_MODES.md**](docs/DEBUG_AND_MOCK_MODES.md) — Режимы отладки
- [**MODES_CHEATSHEET.md**](docs/MODES_CHEATSHEET.md) — Шпаргалка по режимам

### 📋 Функционал
- [**IMAGE_FILTERING_ENHANCED.md**](docs/IMAGE_FILTERING_ENHANCED.md) — Фильтрация изображений
- [**IMAGE_SIZE_DETECTION.md**](docs/IMAGE_SIZE_DETECTION.md) — Определение размеров изображений
- [**DYNAMIC_CHARACTERISTICS_GUIDE.md**](docs/DYNAMIC_CHARACTERISTICS_GUIDE.md) — Динамические характеристики
- [**MATERIAL_HANDLING_RULES.md**](docs/MATERIAL_HANDLING_RULES.md) — Правила обработки материалов

### 🐛 Отладка и ошибки
- [**ERROR_HANDLING.md**](docs/ERROR_HANDLING.md) — Система обработки ошибок
- [**ERROR_HANDLING_SETUP.md**](docs/ERROR_HANDLING_SETUP.md) — Настройка обработки ошибок
- [**DEBUG_INSTRUCTIONS.md**](docs/DEBUG_INSTRUCTIONS.md) — Инструкции по отладке
- [**FAQ.md**](docs/FAQ.md) — Частые вопросы

### 🚀 Deployment
- [**DEPLOYMENT.md**](docs/DEPLOYMENT.md) — Развёртывание в production
- [**CI_CD_SETUP.md**](docs/CI_CD_SETUP.md) — Настройка CI/CD
- [**GITHUB_SETUP.md**](docs/GITHUB_SETUP.md) — Настройка GitHub

---

## 🔧 Логирование

### Автоматическая ротация логов

Логи автоматически управляются:

- 📏 **Размер файла:** до 100 МБ
- 📂 **Количество:** 3 файла (текущий + 2 архивных)
- 💾 **Итого:** ~300 МБ истории (~3-6 месяцев)
- 🔄 **Ротация:** автоматическая при превышении

### Файлы логов

```
bot_errors.log       ← текущий
bot_errors.log.1     ← архив 1
bot_errors.log.2     ← архив 2
```

### Просмотр логов

```bash
# Последние 50 строк
tail -n 50 bot_errors.log

# В реальном времени
tail -f bot_errors.log
```

---

## 🛡️ Безопасность

- ✅ **Non-root пользователь** в Docker
- ✅ **SSL сертификаты** через certifi
- ✅ **Переменные окружения** через .env (не комитятся в Git)
- ✅ **Валидация входных данных** через Pydantic
- ✅ **Обработка ошибок** без утечки sensitive данных

---

## 📊 Статус проекта

- ✅ **Production Ready**
- ✅ **Docker Ready**
- ✅ **CI/CD Ready** (GitHub Actions)
- ✅ **Полная документация**
- ✅ **Обработка ошибок**
- ✅ **Автоматическое логирование**

---

## 🤝 Вклад в проект

Contributions приветствуются! Пожалуйста, ознакомьтесь с [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📝 Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE).

---

## 📞 Поддержка

Если у вас возникли проблемы:

1. Проверьте [FAQ](docs/FAQ.md)
2. Просмотрите [документацию](docs/)
3. Проверьте логи: `docker-compose logs -f`
4. Создайте [Issue](https://github.com/yourusername/taobao-scraper-bot/issues)

---

## 🙏 Благодарности

- [aiogram](https://github.com/aiogram/aiogram) — Telegram Bot Framework
- [YandexGPT](https://yandex.cloud/ru/services/yandexgpt) — AI для генерации описаний
- [TMAPI](https://tmapi.top) — API для Taobao/Tmall

---

<p align="center">
  Сделано с ❤️ для удобного парсинга Taobao/Tmall
</p>
