# 📦 Компактные данные для YandexGPT

## Проблема (БЫЛО)

### ❌ Передавали ВЕСЬ product_data:
```json
{
  "item_id": 751881208330,
  "title": "...",
  "main_imgs": [...],
  "price_info": {...},
  "product_props": [...],
  "delivery_info": {...},
  "shop_info": {...},
  "sku_props": [...],
  "skus": [
    {"skuid": "...", "sale_price": "...", ...},
    {"skuid": "...", "sale_price": "...", ...},
    ... // 312 элементов!!!
  ]
}
```

**Размер:** 50,000+ символов  
**Результат:** `400 Bad Request` от YandexGPT API

---

## Решение (СТАЛО)

### ✅ Передаем ТОЛЬКО нужное:
```json
{
  "title": "适用iphone17pro手机壳17promax酒红色...",
  "product_props": [
    {"品牌": "鳌虎"},
    {"型号": "磨砂硬壳肤感液态硅胶手机壳..."},
    {"流行元素": "磨砂"},
    {"适用手机型号": "iPhone 11 Pro Max iPhone 15..."},
    {"保护套质地": "亚克力"},
    {"颜色分类": "【酒红色】肤感磨砂硬壳★自带镜头膜 【暗夜紫】..."}
  ],
  "available_colors": [
    "【酒红色】肤感磨砂硬壳★自带镜头膜",
    "【暗夜紫】肤感磨砂硬壳★自带镜头膜",
    "【钛灰色】肤感磨砂硬壳★自带镜头膜",
    ...
  ],
  "available_sizes": [
    "iPhone 17",
    "iPhone Air",
    "iPhone 17 Pro",
    "iPhone 17 Pro Max",
    ...
  ]
}
```

**Размер:** 500-2000 символов  
**Результат:** ✅ Успешный запрос к YandexGPT

---

## Что исключили

❌ **skus** - сотни элементов (каждая комбинация цвет+размер)  
❌ **delivery_info** - не нужно для описания  
❌ **shop_info** - не нужно для описания  
❌ **main_imgs** - не используется в промпте  
❌ **price_info** - цену берем из skus отдельно

---

## Логика работы

### 1. Получение данных от TMAPI
```python
product_data = await self.tmapi_client.get_product_info(item_id)
# Полный JSON с сотнями SKU
```

### 2. Подготовка компактных данных
```python
compact_data = self._prepare_compact_data_for_llm(product_data)
# Только нужное для описания
```

### 3. Генерация контента
```python
llm_content = await self.yandex_gpt_client.generate_post_content(compact_data)
# YandexGPT получает компактный JSON
```

### 4. Получение цены
```python
price = self._get_max_price_from_skus(product_data)
# Берем из ПОЛНЫХ данных, не из компактных
```

---

## Метод `_prepare_compact_data_for_llm()`

```python
def _prepare_compact_data_for_llm(self, product_data: dict) -> dict:
    """
    Подготавливает компактные данные для отправки в LLM.
    Убирает огромный массив skus и другие лишние данные.
    """
    compact = {
        'title': product_data.get('title', ''),
        'product_props': product_data.get('product_props', [])
    }
    
    # Извлекаем уникальные цвета и размеры из sku_props
    sku_props = product_data.get('sku_props', [])
    if sku_props:
        for prop in sku_props:
            prop_name = prop.get('prop_name', '')
            
            # Цвета (максимум 20)
            if 'цвет' in prop_name.lower() or 'color' in prop_name.lower():
                colors = [v.get('name', '') for v in prop.get('values', [])]
                if colors:
                    compact['available_colors'] = colors[:20]
            
            # Размеры (максимум 30)
            if 'размер' in prop_name.lower() or 'size' in prop_name.lower():
                sizes = [v.get('name', '') for v in prop.get('values', [])]
                if sizes:
                    compact['available_sizes'] = sizes[:30]
    
    return compact
```

---

## Примеры

### До оптимизации (БЫЛО):
```
Отправка в YandexGPT: 52,487 символов
Результат: 400 Bad Request
```

### После оптимизации (СТАЛО):
```
Отправка в YandexGPT: 1,234 символа
Результат: ✅ Успех
```

**Уменьшение размера: ~40 раз!** 🚀

---

## Важно

1. ✅ **Компактные данные** используются ТОЛЬКО для LLM
2. ✅ **Полные данные** (`product_data`) используются для:
   - Получения цены из `skus`
   - Получения изображений из `main_imgs`
   - Другой обработки в Python

3. ✅ **LLM получает**:
   - Название товара
   - Характеристики (props)
   - Список доступных цветов
   - Список доступных размеров

4. ✅ **LLM НЕ получает**:
   - Сотни элементов SKU
   - Информацию о доставке
   - Информацию о магазине
   - Изображения

---

## Debug режим

```
[Scraper] Компактные данные для LLM подготовлены. Размер: ~1234 символов
[Scraper] Исключено 312 элементов из skus
```

---

## Результат

✅ Ошибка `400 Bad Request` устранена  
✅ Запросы к YandexGPT проходят успешно  
✅ Скорость обработки увеличилась  
✅ Размер промпта уменьшился в ~40 раз

---

**Дата создания:** 23 октября 2025  
**Статус:** Активно

