# 📦 Интеграция Pinduoduo

## Обзор

Бот теперь поддерживает парсинг товаров с платформы **Pinduoduo (拼多多)** в дополнение к Taobao и Tmall.

### Ключевые возможности

✅ **Автоматическое определение платформы** - бот сам понимает, с какой платформы ссылка  
✅ **Rate Limiting** - контроль частоты запросов к API (по умолчанию 5 запросов/сек)  
✅ **Унифицированный API** - один метод для всех платформ  
✅ **Поддержка Pinduoduo URL** - yangkeduo.com, pinduoduo.com, mobile.yangkeduo.com  

---

## Архитектура

### Компоненты

```
┌─────────────────────────────────────────┐
│         url_parser.py                   │
│  - Определение платформы                │
│  - Извлечение item_id                   │
└─────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│         tmapi.py                        │
│  - get_product_info_auto()              │
│  - get_pinduoduo_product()              │
│  - Rate limiting                        │
└─────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│         scraper.py                      │
│  - Обработка данных Pinduoduo           │
│  - Адаптация структуры                  │
└─────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│         bot_handler.py                  │
│  - Обработка Pinduoduo URLs             │
│  - Отправка результата                  │
└─────────────────────────────────────────┘
```

---

## Настройка

### 1. Получение API токена для Pinduoduo

1. Зайдите на [https://tmapi.top](https://tmapi.top)
2. Войдите в аккаунт (или зарегистрируйтесь)
3. Получите **отдельный токен** для Pinduoduo API
4. Скопируйте токен

### 2. Обновление `.env`

Добавьте новые переменные в `.env`:

```env
# Токен для Taobao/Tmall
TMAPI_TOKEN=your_taobao_token_here

# Токен для Pinduoduo (ВАЖНО: получите отдельный!)
TMAPI_PINDUODUO_TOKEN=your_pinduoduo_token_here

# Максимальное количество запросов в секунду (опционально, по умолчанию 5)
TMAPI_RATE_LIMIT=5
```

⚠️ **Важно:** Токены для Taobao/Tmall и Pinduoduo **разные**!

---

## Использование

### Поддерживаемые URL форматы

Бот автоматически распознаёт следующие форматы Pinduoduo:

```
https://mobile.yangkeduo.com/goods.html?goods_id=123456789
https://yangkeduo.com/goods.html?goods_id=123456789
https://pinduoduo.com/goods.html?goods_id=123456789
https://pdd.com/goods.html?goods_id=123456789
```

### Примеры

#### Отправка ссылки боту:

```
Пользователь: https://mobile.yangkeduo.com/goods.html?goods_id=99215544343
Бот: [Обрабатывает товар с Pinduoduo и отправляет пост с фото]
```

#### Автоматическое определение платформы:

```python
from url_parser import URLParser, Platform

url = "https://mobile.yangkeduo.com/goods.html?goods_id=123456"
platform, item_id = URLParser.parse_url(url)

print(platform)  # Output: "pinduoduo"
print(item_id)   # Output: "123456"
```

---

## Различия между платформами

| Параметр | Taobao/Tmall | Pinduoduo |
|----------|--------------|-----------|
| **API Endpoint** | `/taobao/item_detail_by_url` | `/pdd/item_detail` |
| **Входной параметр** | URL (полный) | `item_id` (только ID) |
| **Токен** | `TMAPI_TOKEN` | `TMAPI_PINDUODUO_TOKEN` |
| **Изображения** | `main_imgs` + `sku_props` | `main_imgs` + `detail_imgs` |
| **SKU структура** | `sku_props` (массив объектов) | `skus` (props_names в строке) |
| **Цена** | `price` (строка) | `price_info` (объект) |
| **Детальные изображения** | Второй запрос к `/item_desc` | В основном ответе |

---

## Структура данных Pinduoduo

### Основной ответ API

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "item_id": 99215544343,
    "title": "Название товара",
    "price": 211.5,
    "price_info": {
      "price": "211.5",
      "min_onsale_group_price": "211.5",
      "max_onsale_group_price": "312.7"
    },
    "product_props": [
      {"key": "品牌", "values": ["质造"]},
      {"key": "电源方式", "values": ["交流电"]}
    ],
    "main_imgs": [
      "https://img.pddpic.com/..."
    ],
    "detail_imgs": [
      "https://img.pddpic.com/..."
    ],
    "skus": [
      {
        "skuid": 1474323993683,
        "sale_price": "211.5",
        "props_names": "型号:经济款;套餐:礼包一",
        "stock": 100
      }
    ]
  }
}
```

### Извлечение вариантов товара

Для Pinduoduo варианты (цвета, размеры) хранятся в `skus`:

```python
# Формат props_names: "型号:经济款;套餐:礼包一"
# Парсинг:
for sku in skus:
    props_names = sku['props_names']  # "型号:经济款;套餐:礼包一"
    props_parts = props_names.split(';')  # ["型号:经济款", "套餐:礼包一"]
    
    for part in props_parts:
        key, value = part.split(':', 1)  # "型号", "经济款"
        # key - название свойства (型号 = модель)
        # value - значение (经济款 = эконом)
```

---

## Rate Limiting

### Настройка

Ограничение частоты запросов настраивается через `.env`:

```env
# Максимум 5 запросов в секунду (по умолчанию)
TMAPI_RATE_LIMIT=5

# Для более медленной работы:
TMAPI_RATE_LIMIT=2

# Для более быстрой (если API позволяет):
TMAPI_RATE_LIMIT=10
```

### Как работает

1. Перед каждым запросом бот проверяет время с последнего запроса
2. Если прошло меньше `1/TMAPI_RATE_LIMIT` секунд - ждёт
3. Затем выполняет запрос
4. Сохраняет время запроса

**Пример:**
```
TMAPI_RATE_LIMIT=5 → минимум 200ms между запросами
TMAPI_RATE_LIMIT=2 → минимум 500ms между запросами
```

---

## Отладка

### Включение DEBUG логов

```env
DEBUG_MODE=True
```

### Примеры логов

```
[TMAPI] 🔍 Определена платформа: pinduoduo
[TMAPI] 🆔 Извлечён item_id: 99215544343
[TMAPI] ⏱️  Rate limiting: ждём 0.150 сек
[TMAPI] GET http://api.tmapi.top/pdd/item_detail
[TMAPI] Параметры: item_id=99215544343
[TMAPI] Статус ответа: 200
[Scraper] Платформа: pinduoduo
[Scraper] Pinduoduo: main_imgs=10, detail_imgs=16
```

---

## Обработка ошибок

### Неподдерживаемая платформа

```python
try:
    result = await tmapi_client.get_product_info_auto(url)
except ValueError as e:
    # Ошибка: "Неподдерживаемая платформа: http://example.com"
    print(e)
```

### Не удалось извлечь item_id

```python
try:
    result = await tmapi_client.get_pinduoduo_product(url)
except ValueError as e:
    # Ошибка: "Не удалось извлечь item_id из URL Pinduoduo"
    print(e)
```

### HTTP ошибки

```python
import httpx

try:
    result = await tmapi_client.get_product_info_auto(url)
except httpx.HTTPStatusError as e:
    # Обработка ошибок API (401, 403, 500 и т.д.)
    print(f"HTTP {e.response.status_code}: {e.response.text}")
```

---

## Тестирование

### Mock режим

Для тестирования без реальных API запросов:

```env
MOCK_MODE=True
DEBUG_MODE=True
```

В Mock режиме Pinduoduo возвращает заглушку:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "item_id": 123456,
    "title": "[MOCK] Pinduoduo товар",
    "price": 100.0
  }
}
```

### Ручное тестирование

```python
from tmapi import TmapiClient

client = TmapiClient()

# Тест 1: Определение платформы
url = "https://mobile.yangkeduo.com/goods.html?goods_id=99215544343"
result = await client.get_product_info_auto(url)
print(result['_platform'])  # "pinduoduo"

# Тест 2: Извлечение item_id
from url_parser import URLParser
platform, item_id = URLParser.parse_url(url)
print(item_id)  # "99215544343"
```

---

## Ограничения

⚠️ **TMAPI ограничения:**
- Максимум 5 запросов/сек (по умолчанию)
- Может измениться в будущем (настраивается через `TMAPI_RATE_LIMIT`)

⚠️ **Pinduoduo особенности:**
- ID товара должен быть в параметрах URL (`goods_id`, `id`, `item_id`)
- Если ID не найден - ошибка `ValueError`

---

## FAQ

### Q: Нужен ли отдельный токен для Pinduoduo?
**A:** Да, токены для Taobao/Tmall и Pinduoduo **разные**. Получите оба на tmapi.top.

### Q: Как изменить лимит запросов?
**A:** Измените `TMAPI_RATE_LIMIT` в `.env` (например, `TMAPI_RATE_LIMIT=10`).

### Q: Почему бот не парсит Pinduoduo?
**A:** Проверьте:
1. Добавлен ли `TMAPI_PINDUODUO_TOKEN` в `.env`?
2. Правильный ли формат URL (должен содержать `goods_id`)?
3. Включён ли `DEBUG_MODE` для просмотра логов?

### Q: Как узнать item_id из Pinduoduo URL?
**A:** Откройте URL в браузере, item_id обычно в параметре `goods_id`:
```
https://mobile.yangkeduo.com/goods.html?goods_id=99215544343
                                                 ↑ это item_id
```

---

## Roadmap

🔜 **Планируется:**
- [ ] Поддержка других китайских платформ (JD.com, 1688.com)
- [ ] Автоматическая коррекция неполных URL
- [ ] Кэширование результатов для одинаковых товаров
- [ ] Batch API запросы (несколько товаров за раз)

---

## Поддержка

Если возникли проблемы:
1. Проверьте логи (`DEBUG_MODE=True`)
2. Убедитесь что токены правильные
3. Проверьте формат URL
4. Откройте issue на GitHub

