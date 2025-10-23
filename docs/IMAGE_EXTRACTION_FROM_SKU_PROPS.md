# 📸 Извлечение изображений из sku_props

## Изменение логики

### ❌ БЫЛО (из main_imgs):
```python
image_urls = product_data.get('main_imgs', [])
```

**Проблема:**
- Общие фото товара
- Не привязаны к конкретным вариантам (цветам, моделям)
- Может не показывать все доступные варианты

---

### ✅ СТАЛО (из sku_props):
```python
image_urls = self._get_unique_images_from_sku_props(product_data)
```

**Преимущества:**
- ✅ Фото конкретных вариантов товара
- ✅ Привязаны к цветам/моделям
- ✅ Показывают все доступные варианты
- ✅ Только уникальные изображения (без дубликатов)
- ✅ Fallback на `main_imgs` если `sku_props` пусто

---

## Логика работы

### 1. Структура данных sku_props

```json
{
  "sku_props": [
    {
      "pid": "22041",
      "prop_name": "颜色分类",
      "values": [
        {
          "vid": "29040797540",
          "name": "【酒红色】肤感磨砂硬壳★自带镜头膜",
          "imageUrl": "https://img.alicdn.com/...jpg"
        },
        {
          "vid": "29096565807",
          "name": "【暗夜紫】肤感磨砂硬壳★自带镜头膜",
          "imageUrl": "https://img.alicdn.com/...jpg"
        }
      ]
    },
    {
      "pid": "23448",
      "prop_name": "适用手机型号",
      "values": [
        {
          "vid": "46556282",
          "name": "iPhone 17",
          "imageUrl": ""
        }
      ]
    }
  ]
}
```

### 2. Алгоритм извлечения

```python
def _get_unique_images_from_sku_props(self, product_data: dict) -> list:
    unique_images = []
    seen_urls = set()  # Для проверки уникальности
    
    sku_props = product_data.get('sku_props', [])
    
    # 1. Если sku_props отсутствует → fallback
    if not sku_props:
        return product_data.get('main_imgs', [])
    
    # 2. Проходим по всем свойствам
    for prop in sku_props:
        values = prop.get('values', [])
        
        # 3. Извлекаем imageUrl из каждого value
        for value in values:
            image_url = value.get('imageUrl', '').strip()
            
            # 4. Добавляем только уникальные и непустые
            if image_url and image_url not in seen_urls:
                seen_urls.add(image_url)
                unique_images.append(image_url)
    
    # 5. Если ничего не нашли → fallback
    if not unique_images:
        return product_data.get('main_imgs', [])
    
    return unique_images
```

---

## Пример (из result55.txt)

### Исходные данные:

**main_imgs:** 5 общих фото
```json
"main_imgs": [
  "https://img.alicdn.com/.../O1CN01R5FCFp21SGi59yENn_!!0-item_pic.jpg",
  "https://img.alicdn.com/.../O1CN01TCpNHf21SGd6Bi1Of_!!2212606996983.jpg",
  "https://img.alicdn.com/.../O1CN01Dsl42d21SGd8CReS5_!!2212606996983.jpg",
  "https://img.alicdn.com/.../O1CN010sLevv21SGd68SDYt_!!2212606996983.jpg",
  "https://img.alicdn.com/.../O1CN01EbBbgx21SGcxx90Xh_!!2212606996983.jpg"
]
```

**sku_props (颜色分类):** 13 вариантов цветов с фото
```json
"values": [
  {"name": "【酒红色】...", "imageUrl": "https://...jpg"},
  {"name": "【暗夜紫】...", "imageUrl": "https://...jpg"},
  {"name": "【钛灰色】...", "imageUrl": "https://...jpg"},
  {"name": "【少女粉】...", "imageUrl": "https://...jpg"},
  {"name": "【豆蔻绿】...", "imageUrl": "https://...jpg"},
  {"name": "【石墨灰】...", "imageUrl": "https://...jpg"},
  {"name": "【深海蓝】...", "imageUrl": "https://...jpg"},
  {"name": "【远峰蓝】...", "imageUrl": "https://...jpg"},
  {"name": "【爵士黑】...", "imageUrl": "https://...jpg"},
  {"name": "【咖啡色】...", "imageUrl": "https://...jpg"},
  {"name": "【苍岭绿】...", "imageUrl": "https://...jpg"},
  {"name": "【爱玛橙】...", "imageUrl": "https://...jpg"},
  {"name": "【纯白色】...", "imageUrl": "https://...jpg"}
]
```

### Результат:

✅ **Извлечено:** 13 уникальных изображений (по одному на каждый цвет)  
✅ **Показаны:** Все доступные варианты товара  
✅ **Без дубликатов:** Каждое фото уникально

---

## DEBUG режим

```
[Scraper] Извлечено 13 уникальных изображений из sku_props
```

Или в случае отсутствия:
```
[Scraper] sku_props отсутствует, используем main_imgs
[Scraper] Изображения в sku_props не найдены, используем main_imgs
```

---

## Fallback механизм

### Случай 1: sku_props отсутствует
```python
if not sku_props:
    return product_data.get('main_imgs', [])
```

### Случай 2: sku_props есть, но нет imageUrl
```python
if not unique_images:
    return product_data.get('main_imgs', [])
```

**Результат:** Бот ВСЕГДА получит изображения, даже если структура данных нестандартная.

---

## Преимущества

| Критерий | main_imgs | sku_props (NEW) |
|----------|-----------|-----------------|
| Привязка к вариантам | ❌ Нет | ✅ Да |
| Показ всех цветов | ❌ Может не показать | ✅ Все варианты |
| Уникальность | ⚠️ Могут быть дубли | ✅ Только уникальные |
| Количество фото | ~5 | ~13+ |
| Fallback | - | ✅ Есть |

---

## Интеграция с ботом

В `handlers.py` бот получает:
```python
post_text, image_urls = await scraper.scrape_product_data(item_id)

# image_urls теперь содержит уникальные фото из sku_props!
```

Бот отправляет все фото как медиа-группу:
```python
media = []
for idx, img_url in enumerate(image_urls):
    if idx == 0:
        media.append(InputMediaPhoto(media=img_url, caption=post_text))
    else:
        media.append(InputMediaPhoto(media=img_url))

await message.answer_media_group(media)
```

---

## Итоговая логика

```
1. Получаем product_data от TMAPI
           ↓
2. _get_unique_images_from_sku_props()
           ↓
3. Проверяем sku_props → есть?
   │
   ├─ Да → Извлекаем imageUrl из values
   │        ↓
   │   Проверяем уникальность (через set)
   │        ↓
   │   Возвращаем список уникальных URL
   │
   └─ Нет → Возвращаем main_imgs (fallback)
```

---

## Результат

✅ Больше фотографий товара  
✅ Фото привязаны к конкретным вариантам  
✅ Покупатель видит ВСЕ доступные цвета/модели  
✅ Нет дубликатов  
✅ Надежный fallback на main_imgs

---

**Дата обновления:** 23 октября 2025  
**Статус:** Активно

