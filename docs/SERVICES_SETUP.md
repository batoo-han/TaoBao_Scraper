# Настройка сервисов и получение API ключей 🔑

Полное руководство по регистрации и настройке всех необходимых сервисов для работы бота.

---

## 📱 1. Telegram Bot (обязательно)

### Создание бота

1. **Откройте Telegram** и найдите бота [@BotFather](https://t.me/BotFather)

2. **Отправьте команду** `/newbot`

3. **Введите название бота** (например: "My Taobao Parser")

4. **Введите username бота** (должен заканчиваться на `bot`, например: `my_taobao_bot`)

5. **Получите токен**
   - BotFather пришлёт вам сообщение с токеном
   - Формат: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
   - ⚠️ **ВАЖНО:** Никому не передавайте этот токен!

6. **Скопируйте токен** в `.env`:
   ```env
   BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

### Настройка бота (опционально)

- **Установить описание:** `/setdescription` → выберите бота → введите описание
- **Установить изображение:** `/setuserpic` → выберите бота → загрузите картинку
- **Установить команды:** `/setcommands` → выберите бота → введите:
  ```
  start - Запустить бота
  ```

---

## 🛍️ 2. TMAPI (обязательно)

### Регистрация

1. **Перейдите на сайт** [tmapi.top](https://tmapi.top)

2. **Зарегистрируйтесь:**
   - Email
   - Пароль
   - Подтвердите email

3. **Войдите в личный кабинет**

### Получение API токена

1. **В личном кабинете** найдите раздел "API Token" или "Keys"

2. **Создайте новый токен** или скопируйте существующий

3. **Формат токена:**
   ```
   eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

4. **Скопируйте токен** в `.env`:
   ```env
   TMAPI_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

### Тарифы

- **Бесплатный план:** 100 запросов/день
- **Платные планы:** для больших объёмов

### API Endpoint

Бот использует: `http://api.tmapi.top/taobao/item_detail_by_url`

---

## 🤖 3. Yandex Cloud (обязательно)

### Создание аккаунта

1. **Перейдите на** [cloud.yandex.ru](https://cloud.yandex.ru)

2. **Зарегистрируйтесь:**
   - Через Яндекс ID
   - Или создайте новый аккаунт

3. **Активируйте триальный период** (если доступен)
   - 3 месяца бесплатно
   - $50 на балансе

### Создание API ключа для YandexGPT

1. **В консоли Yandex Cloud:**
   - Перейдите в "Сервисные аккаунты"
   - Нажмите "Создать сервисный аккаунт"

2. **Настройте сервисный аккаунт:**
   - Имя: `taobao-bot-sa` (или любое другое)
   - Роли: `ai.languageModels.user`

3. **Создайте API ключ:**
   - Откройте созданный сервисный аккаунт
   - Перейдите в "API-ключи"
   - Нажмите "Создать API-ключ"
   - **Скопируйте ключ** (он показывается только один раз!)

4. **Получите Folder ID:**
   - В консоли Yandex Cloud откройте ваш каталог (folder)
   - ID каталога показан в верхней части страницы
   - Формат: `b1g...`

5. **Добавьте в `.env`:**
   ```env
   YANDEX_GPT_API_KEY=AQVNy_o0b5iuNtg7DcJqFlQy...
   YANDEX_FOLDER_ID=b1grlrtg9nq658eh2ir0
   YANDEX_GPT_MODEL=yandexgpt-lite
   ```

### Модели YandexGPT

- `yandexgpt-lite` - быстрая, дешевая (рекомендуется)
- `yandexgpt` - более продвинутая, дороже

### Цены (на момент написания)

- **YandexGPT Lite:** ~0.3₽ за 1000 токенов
- **Триальный период:** 3 месяца бесплатно ($50)

### Документация

- [Официальная документация YandexGPT](https://cloud.yandex.ru/docs/yandexgpt/)

---

## 💱 4. ExchangeRate-API (опционально)

Используется для конвертации CNY → RUB, если `CONVERT_CURRENCY=True`

### Регистрация

1. **Перейдите на** [exchangerate-api.com](https://www.exchangerate-api.com)

2. **Зарегистрируйтесь:**
   - Email
   - Подтвердите email

3. **Получите API ключ:**
   - После регистрации ключ сразу показывается
   - Также доступен в личном кабинете

4. **Скопируйте ключ** в `.env`:
   ```env
   EXCHANGE_RATE_API_KEY=b2119f68760e150f12041fb2
   ```

### Тарифы

- **Бесплатный план:** 1,500 запросов/месяц
- Для бота этого **более чем достаточно** (бот кэширует курс на сутки)

### Отключение конвертации

Если не хотите использовать конвертацию валют:
```env
CONVERT_CURRENCY=False
```

В этом случае API ключ не обязателен.

---

## ☁️ 5. Google Cloud (опционально)

Используется только если в коде есть интеграции с Google сервисами.

### Создание проекта

1. **Перейдите в** [console.cloud.google.com](https://console.cloud.google.com)

2. **Создайте новый проект:**
   - Нажмите "Select a project" → "New Project"
   - Введите название
   - Скопируйте Project ID

3. **Добавьте в `.env`:**
   ```env
   GOOGLE_CLOUD_PROJECT=your-project-id
   ```

⚠️ **Примечание:** В текущей версии бота Google Cloud не используется активно. Параметр оставлен для совместимости.

---

## ✅ Проверка настройки

После настройки всех сервисов ваш `.env` должен выглядеть так:

```env
# Обязательные
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TMAPI_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
YANDEX_GPT_API_KEY=AQVNy_o0b5iuNtg7DcJqFlQy...
YANDEX_FOLDER_ID=b1grlrtg9nq658eh2ir0

# Опциональные
EXCHANGE_RATE_API_KEY=b2119f68760e150f12041fb2
GOOGLE_CLOUD_PROJECT=your-project-id

# Настройки
YANDEX_GPT_MODEL=yandexgpt-lite
CONVERT_CURRENCY=False
DEBUG_MODE=False
DISABLE_SSL_VERIFY=False
```

---

## 🆘 Решение проблем

### Telegram Bot не отвечает
- Проверьте правильность токена
- Убедитесь что бот запущен
- Проверьте что бот не заблокирован

### TMAPI возвращает ошибки
- Проверьте квоту (100 запросов/день на бесплатном плане)
- Убедитесь что токен валиден
- Попробуйте `DEBUG_MODE=True` для тестирования без API

### YandexGPT ошибки
- Проверьте баланс в Yandex Cloud
- Убедитесь что API ключ и Folder ID правильные
- Проверьте роли сервисного аккаунта

### SSL ошибки
- Установите `DISABLE_SSL_VERIFY=True` (временно)
- Обновите `certifi`: `pip install --upgrade certifi`

---

## 📝 Дополнительные ресурсы

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [TMAPI Documentation](https://tmapi.top/docs)
- [Yandex Cloud Documentation](https://cloud.yandex.ru/docs)
- [ExchangeRate-API Docs](https://www.exchangerate-api.com/docs)

