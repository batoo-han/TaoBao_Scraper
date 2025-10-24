# Руководство по развёртыванию 🚀

Полное руководство по развёртыванию Taobao Scraper Bot локально и в Docker.

---

## 📋 Предварительные требования

### Обязательно:
- Python 3.11+
- Git
- Настроенные API ключи (см. [SERVICES_SETUP.md](SERVICES_SETUP.md))

### Для Docker:
- Docker 20.10+
- Docker Compose 2.0+

---

## 🏠 Локальное развёртывание

### 1. Клонирование репозитория

```bash
git clone https://github.com/your-username/TaoBao_Scraper_2.git
cd TaoBao_Scraper_2
```

### 2. Создание виртуального окружения

#### Windows:
```bash
python -m venv .venv
.venv\Scripts\activate
```

#### Linux/Mac:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Настройка окружения

1. **Скопируйте пример конфигурации:**
   ```bash
   cp .env.example .env
   ```

2. **Отредактируйте `.env`** и заполните все ключи API

3. **Проверьте настройки:**
   - `DEBUG_MODE=False` - для работы с реальными данными
   - `DEBUG_MODE=True` - для тестирования с заглушкой

### 5. Запуск бота

```bash
python autoparse.py
```

### 6. Проверка работы

1. Найдите вашего бота в Telegram
2. Отправьте команду `/start`
3. Отправьте ссылку на товар с Taobao/Tmall

---

## 🐳 Развёртывание в Docker

### Способ 1: Docker Compose (рекомендуется)

#### 1. Подготовка

```bash
# Клонируйте репозиторий
git clone https://github.com/your-username/TaoBao_Scraper_2.git
cd TaoBao_Scraper_2

# Создайте .env из примера
cp .env.example .env

# Отредактируйте .env файл
nano .env  # или используйте любой редактор
```

#### 2. Запуск

```bash
# Соберите и запустите контейнер
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down
```

#### 3. Обновление

```bash
# Остановите контейнер
docker-compose down

# Обновите код
git pull

# Пересоберите и запустите
docker-compose up -d --build
```

---

### Способ 2: Только Docker

#### 1. Сборка образа

```bash
docker build -t taobao-scraper-bot .
```

#### 2. Запуск контейнера

```bash
docker run -d \
  --name taobao-bot \
  --env-file .env \
  --restart unless-stopped \
  taobao-scraper-bot
```

#### 3. Просмотр логов

```bash
docker logs -f taobao-bot
```

#### 4. Остановка и удаление

```bash
docker stop taobao-bot
docker rm taobao-bot
```

---

## 🔧 Режимы работы

### Режим отладки (DEBUG_MODE=True)

**Использование:**
- Тестирование без траты API квоты
- Разработка и отладка
- Проверка форматирования постов

**Настройка:**
```env
DEBUG_MODE=True
```

**Как работает:**
- Читает данные из `result.txt`
- НЕ делает запросы к TMAPI
- YandexGPT работает в реальном режиме

---

### Продакшн режим (DEBUG_MODE=False)

**Использование:**
- Реальная работа бота
- Обработка реальных ссылок

**Настройка:**
```env
DEBUG_MODE=False
```

**Требования:**
- Валидный TMAPI_TOKEN
- Достаточная квота на TMAPI

---

## 📊 Мониторинг

### Просмотр логов

#### Docker Compose:
```bash
docker-compose logs -f taobao-bot
```

#### Docker:
```bash
docker logs -f taobao-bot
```

#### Локально:
Логи выводятся в консоль при запуске `python autoparse.py`

---

## 🔄 Обновление

> 📘 **Детальное руководство по обновлению:** [UPDATE_WORKFLOW.md](UPDATE_WORKFLOW.md)  
> Включает автоматизацию, скрипты, troubleshooting и оптимизированные команды.

### Локальное развёртывание

```bash
# Активируйте виртуальное окружение
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Обновите код
git pull

# Обновите зависимости (если изменились)
pip install --upgrade -r requirements.txt

# Перезапустите бота
python autoparse.py
```

### Docker (быстрое обновление)

```bash
# Остановите контейнер
docker-compose down

# Обновите код
git pull

# Пересоберите и запустите
docker-compose up -d --build

# Проверьте логи
docker-compose logs -f --tail=50
```

### Docker (одной командой)

```bash
cd ~/TaoBao_Scraper && \
git pull && \
sudo docker-compose up -d --build && \
sudo docker-compose logs -f --tail=50
```

---

## 🛠️ Решение проблем

### Бот не запускается

1. **Проверьте логи:**
   ```bash
   docker-compose logs taobao-bot
   ```

2. **Проверьте .env файл:**
   - Все ключи API заполнены?
   - Нет опечаток?

3. **Проверьте порты:**
   - Убедитесь что порты не заняты

### Бот не отвечает на сообщения

1. **Проверьте BOT_TOKEN:**
   - Получен от @BotFather?
   - Скопирован правильно?

2. **Проверьте логи:**
   - Есть ли ошибки?

3. **Перезапустите бота:**
   ```bash
   docker-compose restart
   ```

### TMAPI ошибки

1. **Проверьте квоту:**
   - Бесплатный план: 100 запросов/день
   - Превышена квота?

2. **Используйте DEBUG_MODE:**
   ```env
   DEBUG_MODE=True
   ```

3. **Проверьте токен:**
   - Валиден ли TMAPI_TOKEN?

### SSL ошибки

1. **Временное решение:**
   ```env
   DISABLE_SSL_VERIFY=True
   ```

2. **Постоянное решение:**
   - Обновите certifi: `pip install --upgrade certifi`
   - Пересоберите Docker образ

---

## 📝 Переменные окружения

### Обязательные:

| Переменная | Описание | Пример |
|------------|----------|--------|
| `BOT_TOKEN` | Токен Telegram бота | `1234:ABCdef...` |
| `TMAPI_TOKEN` | API токен TMAPI | `eyJhbG...` |
| `YANDEX_GPT_API_KEY` | API ключ YandexGPT | `AQVNy_o0...` |
| `YANDEX_FOLDER_ID` | ID каталога Yandex Cloud | `b1grlrtg...` |

### Опциональные:

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `YANDEX_GPT_MODEL` | Модель YandexGPT | `yandexgpt-lite` |
| `EXCHANGE_RATE_API_KEY` | Ключ API курсов валют | - |
| `CONVERT_CURRENCY` | Конвертация валют | `False` |
| `DEBUG_MODE` | Режим отладки | `False` |
| `DISABLE_SSL_VERIFY` | Отключить SSL | `False` |

---

## 🔐 Безопасность

### Важно:

1. **Никогда не коммитьте `.env` в Git**
   - Файл уже в `.gitignore`
   - Используйте `.env.example` для примера

2. **Храните ключи API в безопасности**
   - Не публикуйте в открытом доступе
   - Используйте секреты в CI/CD

3. **Регулярно обновляйте зависимости:**
   ```bash
   pip install --upgrade -r requirements.txt
   ```

4. **Используйте HTTPS/SSL в продакшене**
   - `DISABLE_SSL_VERIFY=False`

---

## 📚 Дополнительные ресурсы

- [Процесс обновления на сервере](UPDATE_WORKFLOW.md) - Детальное руководство по обновлению
- [Настройка сервисов](SERVICES_SETUP.md)
- [Архитектура проекта](ARCHITECTURE.md)
- [FAQ](FAQ.md)

