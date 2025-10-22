# Taobao Scraper Telegram Bot 🤖

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-brightgreen.svg)](Dockerfile)

Telegram-бот для автоматического парсинга товаров с Taobao/Tmall с использованием AI для генерации привлекательных постов.

<p align="center">
  <img src="other/5.png" alt="Пример поста" width="300"/>
</p>

---

## ✨ Основные возможности

- 🔍 **Автоматический парсинг** товаров с Taobao/Tmall
- 🤖 **AI-генерация контента** с использованием YandexGPT
- 📸 **Обработка изображений** - отправка до 10+ фото
- 💱 **Конвертация валют** CNY → RUB (опционально)
- 🎨 **Красивое форматирование** постов в HTML
- 📦 **Docker-ready** для быстрого развёртывания
- 🧪 **Режим отладки** для тестирования без API

---

## 🚀 Быстрый старт

### Локальное развёртывание

```bash
# Клонируйте репозиторий
git clone https://github.com/your-username/TaoBao_Scraper_2.git
cd TaoBao_Scraper_2

# Создайте виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Установите зависимости
pip install -r requirements.txt

# Настройте окружение
cp .env.example .env
# Отредактируйте .env и добавьте API ключи

# Запустите бота
python autoparse.py
```

### Docker развёртывание

```bash
# Клонируйте и настройте
git clone https://github.com/your-username/TaoBao_Scraper_2.git
cd TaoBao_Scraper_2
cp .env.example .env
# Отредактируйте .env

# Запустите с Docker Compose
docker-compose up -d

# Просмотр логов
docker-compose logs -f
```

---

## 📋 Требования

### API Ключи (обязательно):

- ✅ **Telegram Bot Token** - от [@BotFather](https://t.me/BotFather)
- ✅ **TMAPI Token** - от [tmapi.top](https://tmapi.top)
- ✅ **YandexGPT API Key** - от [Yandex Cloud](https://cloud.yandex.ru)

### Опционально:

- 💱 **ExchangeRate API Key** - для конвертации валют

📖 **Подробные инструкции:** [docs/SERVICES_SETUP.md](docs/SERVICES_SETUP.md)

---

## 🎯 Как это работает

1. **Пользователь отправляет ссылку** на товар с Taobao/Tmall
2. **TMAPI парсит данные** о товаре (название, цена, фото, характеристики)
3. **YandexGPT генерирует** структурированный контент на русском языке
4. **Бот формирует пост** с:
   - Эмодзи и привлекательным заголовком
   - Описанием в виде цитаты
   - Характеристиками товара
   - Ценой и ссылкой
5. **Отправляет медиагруппу** с 4+ фотографиями

### Пример сгенерированного поста:

```
👗 Уютный свитер

> Стильный и удобный свитер в европейском стиле для осени и зимы. 
> Идеально подходит для повседневной носки.

Цвета: Чёрный, белый, серый, кофейный, зелёный
Размеры: S-L
Сезон: Осень, зима

💰 Цена: 72.42 юаней + доставка

📝 Для заказа пишите @annabbox или в комментариях 🛍️

#свитер #одежда #осень

Ссылка
```

---

## 🛠️ Технологии

- **Python 3.11** - основной язык
- **aiogram** - Telegram Bot framework
- **httpx** - async HTTP клиент
- **YandexGPT** - генерация контента
- **TMAPI** - парсинг Taobao/Tmall
- **Docker** - контейнеризация

---

## 📁 Структура проекта

```
TaoBao_Scraper_2/
├── autoparse.py              # Точка входа
├── bot_handler.py            # Обработчики Telegram
├── scraper.py                # Оркестратор + формирование постов
├── tmapi.py                  # Клиент TMAPI
├── yandex_gpt.py             # Клиент YandexGPT
├── exchange_rate.py          # Курсы валют
├── config.py                 # Конфигурация
├── requirements.txt          # Зависимости
├── Dockerfile                # Docker образ
├── docker-compose.yml        # Docker Compose
├── .env.example              # Пример конфигурации
└── docs/                     # Документация
    ├── SERVICES_SETUP.md     # Настройка API сервисов
    ├── DEPLOYMENT.md         # Развёртывание
    └── ARCHITECTURE.md       # Архитектура
```

---

## ⚙️ Конфигурация

Все настройки в файле `.env`:

```env
# Обязательные API ключи
BOT_TOKEN=your_bot_token
TMAPI_TOKEN=your_tmapi_token
YANDEX_GPT_API_KEY=your_yandex_key
YANDEX_FOLDER_ID=your_folder_id

# Опции
CONVERT_CURRENCY=False    # Конвертация валют
DEBUG_MODE=False          # Режим отладки
DISABLE_SSL_VERIFY=False  # Отключить SSL проверку
```

**Полный список:** см. [.env.example](.env.example)

---

## 📖 Документация

| Документ | Описание |
|----------|----------|
| [SERVICES_SETUP.md](docs/SERVICES_SETUP.md) | Регистрация и настройка API сервисов |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Полное руководство по развёртыванию |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Архитектура и дизайн системы |
| [FAQ.md](docs/FAQ.md) | Часто задаваемые вопросы |

---

## 🧪 Режим отладки

Для тестирования без расхода API квоты:

```env
DEBUG_MODE=True
```

В этом режиме:
- ✅ Данные читаются из `result.txt`
- ✅ Не тратится квота TMAPI
- ✅ YandexGPT работает в реальном режиме

---

## 🤝 Вклад в проект

Приветствуются любые предложения и улучшения!

1. Fork репозитория
2. Создайте feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit изменения (`git commit -m 'Add some AmazingFeature'`)
4. Push в branch (`git push origin feature/AmazingFeature`)
5. Откройте Pull Request

---

## 📝 Лицензия

Распространяется под лицензией MIT. См. `LICENSE` для деталей.

---

## 🆘 Поддержка

Если у вас возникли проблемы:

1. Проверьте [FAQ](docs/FAQ.md)
2. Изучите [Issues](https://github.com/your-username/TaoBao_Scraper_2/issues)
3. Создайте новый Issue с подробным описанием

---

## 🙏 Благодарности

- [TMAPI](https://tmapi.top) - за API для парсинга Taobao
- [Yandex Cloud](https://cloud.yandex.ru) - за YandexGPT
- [aiogram](https://github.com/aiogram/aiogram) - за отличный Telegram framework

---

<p align="center">
  Сделано с ❤️ для упрощения работы с Taobao/Tmall
</p>
