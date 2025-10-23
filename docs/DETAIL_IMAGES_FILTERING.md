# 📸 Фильтрация изображений из detail_html

## Общая логика

Теперь изображения берутся из **двух источников**:

1. **sku_props** - основные изображения вариантов товара (цвета, модели)
2. **detail_html** (item_desc API) - дополнительные детальные изображения

---

## Двухэтапный процесс

### Этап 1: Получение данных

```
1. GET /taobao/item_detail_by_url → получаем item_id
           ↓
2. GET /taobao/item_desc?item_id=XXX → получаем detail_html
```

### Этап 2: Объединение изображений

```
sku_images (из sku_props)
    +
detail_images (из detail_html, отфильтрованные)
    =
Итоговый список изображений
```

---

## Фильтрация изображений по размерам

### Проблема

В `detail_html` могут быть:
- **Баннеры**: 2480x184 (соотношение ~13:1)
- **Маленькие иконки**: 500x600
- **Нормальные фото**: 1500x1950, 1500x1912, 1400x1615, 1500x1808

### Решение

Фильтруем в **2 этапа**:

#### Шаг 1: Убираем баннеры

```python
aspect_ratio = width / height

# Убираем если:
if aspect_ratio > 5.0:  # Горизонтальный баннер
    exclude()
if aspect_ratio < 0.2:  # Вертикальный баннер
    exclude()

# Оставляем: 0.2 <= aspect_ratio <= 5.0
```

**Примеры:**
- ❌ 2480x184 → aspect = 13.48 → **ИСКЛЮЧЕН** (баннер)
- ✅ 1500x1950 → aspect = 0.77 → **ОСТАВЛЕН**
- ✅ 1400x1615 → aspect = 0.87 → **ОСТАВЛЕН**

#### Шаг 2: Убираем изображения с сильно отличающимися размерами

```python
# Находим медианную площадь
areas = [width * height for img in images]
median_area = statistics.median(areas)

# Проверяем каждое изображение
ratio = img_area / median_area

# Убираем если:
if ratio < 0.3:  # Слишком маленькое
    exclude()
if ratio > 3.0:  # Слишком большое
    exclude()

# Оставляем: 0.3 <= ratio <= 3.0
```

**Пример:**

Изображения: `2480x184`, `1500x1950`, `1500x1950`, `1500x1950`, `1500x1912`, `1400x1615`, `1500x1808`, `500x600`

**После фильтрации:**

1. Убираем баннер: `2480x184` (aspect = 13.48)
2. Оставшиеся: `1500x1950`, `1500x1950`, `1500x1950`, `1500x1912`, `1400x1615`, `1500x1808`, `500x600`
3. Медианная площадь: ~2,925,000 пикселей
4. Проверяем `500x600` = 300,000 пикселей → ratio = 0.10 → **ИСКЛЮЧЕН**
5. Финальный список: `1500x1950`, `1500x1950`, `1500x1950`, `1500x1912`, `1400x1615`, `1500x1808`

✅ **Результат:** Оставлены только похожие по размеру изображения!

---

## Структура данных detail_html

### Ответ API

```json
{
  "code": 200,
  "data": {
    "detail_imgs": ["url1", "url2", ...],
    "detail_html": "<img align=\"absmiddle\" size=\"2480x3840\" src=\"url1\" /><img align=\"absmiddle\" size=\"2480x184\" src=\"url2\" />..."
  }
}
```

### detail_html - это HTML строка!

**НЕ массив объектов**, а **HTML строка** с тегами `<img>`:

```html
<!-- Вариант 1: С атрибутом size -->
<img align="absmiddle" size="2480x3840" src="https://..." />
<img align="absmiddle" size="2480x184" src="https://..." />

<!-- Вариант 2: БЕЗ атрибута size (чаще!) -->
<img src="https://..." />
<img src="https://..." />
```

**Важно:**
- ⚠️ **Атрибут `size` присутствует НЕ ВСЕГДА!**
- В большинстве случаев теги `<img>` **БЕЗ** `size`
- Если `size` есть: формат `size="ШИРИНАxВЫСОТА"`

### Решение: Определяем размеры сами!

Когда атрибута `size` нет, мы:
1. Загружаем **только первые 4KB** изображения (HTTP Range запрос)
2. Используем библиотеку `imagesize` для определения размеров
3. Это **быстро** и **экономно** (не загружаем полное изображение)

---

## Код реализации

### 1. Новый метод в `tmapi.py`

```python
async def get_item_description(self, item_id: int):
    """
    Получает детальное описание товара с дополнительными изображениями.
    """
    querystring = {
        "apiToken": self.api_token,
        "item_id": item_id
    }
    
    response = await client.get(self.item_desc_api_url, params=querystring)
    return response.json()
```

### 2. Парсинг HTML в `scraper.py`

```python
def _parse_detail_html(self, detail_html: str) -> list:
    """
    Парсит HTML строку с тегами <img> и извлекает URL и размеры.
    """
    import re
    
    images_with_sizes = []
    
    # Находим все теги <img>
    img_tags = re.findall(r'<img[^>]*>', detail_html, re.IGNORECASE)
    
    for img_tag in img_tags:
        # Извлекаем src
        src_match = re.search(r'src="([^"]+)"', img_tag, re.IGNORECASE)
        if not src_match:
            continue
        
        url = src_match.group(1).strip()
        
        # Извлекаем size (если есть)
        size_match = re.search(r'size="(\d+)x(\d+)"', img_tag, re.IGNORECASE)
        
        if size_match:
            width = int(size_match.group(1))
            height = int(size_match.group(2))
            
            images_with_sizes.append({
                'url': url,
                'width': width,
                'height': height
            })
    
    return images_with_sizes
```

### 3. Фильтрация в `scraper.py`

```python
async def _get_filtered_detail_images(self, item_id: int) -> list:
    """
    Получает дополнительные изображения из item_desc и фильтрует их.
    """
    # 1. Получаем данные
    desc_data = await self.tmapi_client.get_item_description(item_id)
    detail_html = desc_data.get('data', {}).get('detail_html', '')  # ← STRING!
    
    # 2. Парсим HTML и извлекаем изображения с размерами
    images_with_sizes = self._parse_detail_html(detail_html)
    
    # 3. Фильтруем
    filtered_images = self._filter_images_by_size(images_with_sizes)
    
    return [img['url'] for img in filtered_images]
```

```python
def _filter_images_by_size(self, images_with_sizes: list) -> list:
    """
    Фильтрует изображения по размерам.
    """
    # Шаг 1: Убираем баннеры
    non_banners = [
        img for img in images_with_sizes
        if 0.2 <= (img['width'] / img['height']) <= 5.0
    ]
    
    # Шаг 2: Убираем изображения с сильно отличающимися размерами
    areas = [img['width'] * img['height'] for img in non_banners]
    median_area = statistics.median(areas)
    
    filtered = [
        img for img in non_banners
        if 0.3 <= (img['width'] * img['height'] / median_area) <= 3.0
    ]
    
    return filtered
```

---

## Объединение изображений

```python
# Получаем изображения из sku_props
sku_images = self._get_unique_images_from_sku_props(product_data)

# Получаем отфильтрованные изображения из detail_html
item_id = product_data.get('item_id')
detail_images = await self._get_filtered_detail_images(item_id)

# Объединяем: сначала варианты, потом детали
image_urls = sku_images + detail_images
```

**Порядок важен:**
1. Сначала показываем варианты товара (из sku_props)
2. Потом дополнительные детальные фото (из detail_html)

---

## DEBUG режим

```
[Scraper] Извлечено 13 уникальных изображений из sku_props
[Scraper] Detail изображений: 8 → 6 после фильтрации
[Scraper] Пропускаем баннер: 2480x184 (aspect: 13.48)
[Scraper] Пропускаем изображение 500x600 (площадь отличается в 0.10 раз от медианы)
[Scraper] Отфильтрованные размеры: 1500x1950, 1500x1950, 1500x1912, 1400x1615, 1500x1808, 1500x1950
[Scraper] Итого изображений: 19 (sku: 13, detail: 6)
```

---

## Параметры фильтрации

### Соотношение сторон (aspect ratio)

| Тип | Диапазон | Примеры |
|-----|----------|---------|
| ❌ Горизонтальный баннер | > 5.0 | 2480x184 (13.48) |
| ✅ Нормальное фото | 0.2 - 5.0 | 1500x1950 (0.77) |
| ❌ Вертикальный баннер | < 0.2 | 200x1500 (0.13) |

### Площадь изображения

| Отношение к медиане | Действие |
|---------------------|----------|
| < 0.3x | ❌ Исключить (слишком маленькое) |
| 0.3x - 3.0x | ✅ Оставить |
| > 3.0x | ❌ Исключить (слишком большое) |

---

## Преимущества

| До | После |
|----|-------|
| Только sku_props (~13 фото) | sku_props + detail_html (~19+ фото) |
| Могут быть баннеры | ✅ Баннеры отфильтрованы |
| Могут быть разного размера | ✅ Только похожие по размеру |
| - | ✅ Больше информации о товаре |

---

## Fallback механизм

1. Если `item_desc` API недоступен → используем только `sku_images`
2. Если `detail_html` пуст → используем только `sku_images`
3. Если все изображения отфильтрованы → возвращаем пустой список для detail
4. Если `sku_props` пуст → fallback на `main_imgs`

**Результат:** Бот ВСЕГДА получит хотя бы часть изображений!

---

## Итоговая логика

```
1. Получаем product_data (item_id)
           ↓
2. Параллельно:
   ├─ Извлекаем sku_images из sku_props
   └─ Получаем detail_html по item_id
           ↓
3. Фильтруем detail_html:
   ├─ Убираем баннеры (aspect ratio)
   └─ Убираем слишком отличающиеся (площадь)
           ↓
4. Объединяем: sku_images + filtered_detail_images
           ↓
5. Возвращаем итоговый список
```

---

**Дата создания:** 23 октября 2025  
**Статус:** Активно

