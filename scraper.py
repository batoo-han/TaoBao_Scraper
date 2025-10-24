from tmapi import TmapiClient
from yandex_gpt import YandexGPTClient
from exchange_rate import ExchangeRateClient
from yandex_translate import YandexTranslateClient
from config import settings

class Scraper:
    """
    Класс-оркестратор для сбора информации о товаре, его обработки и генерации поста.
    """
    def __init__(self):
        self.tmapi_client = TmapiClient()  # Клиент для tmapi.top
        self.yandex_gpt_client = YandexGPTClient()  # Клиент для YandexGPT
        self.exchange_rate_client = ExchangeRateClient()  # Клиент для ExchangeRate-API
        self.yandex_translate_client = YandexTranslateClient()  # Клиент для Yandex.Translate

    async def scrape_product(self, url: str):
        """
        Собирает информацию о товаре по URL, генерирует структурированный контент
        и формирует финальный пост.

        Args:
            url (str): URL товара для скрапинга.

        Returns:
            tuple: Кортеж, содержащий сгенерированный текст поста (str) и список URL изображений (list).
        """
        # Получаем данные о товаре через tmapi.top
        api_response = await self.tmapi_client.get_product_info(url)
        
        # TMAPI возвращает структуру: {"code": 200, "msg": "success", "data": {...}}
        # Извлекаем данные о товаре из поля "data"
        if isinstance(api_response, dict) and 'data' in api_response:
            product_data = api_response['data']
        else:
            product_data = api_response
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Данные товара получены: {product_data.get('title', 'N/A')[:50]}...")
        
        exchange_rate = None
        # Если включена конвертация валют, получаем курс
        if settings.CONVERT_CURRENCY:
            exchange_rate = await self.exchange_rate_client.get_exchange_rate()

        # Подготавливаем компактные данные для LLM (без огромного массива skus!)
        compact_data = self._prepare_compact_data_for_llm(product_data)
        
        # Генерируем структурированный контент с помощью YandexGPT
        # LLM вернет JSON с: title, description, characteristics, hashtags
        llm_content = await self.yandex_gpt_client.generate_post_content(compact_data)
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] LLM контент получен: {llm_content.get('title', 'N/A')}")
        
        # Формируем финальный пост из структурированных данных
        post_text = self._build_post_text(
            llm_content=llm_content,
            product_data=product_data,
            exchange_rate=exchange_rate
        )
        
        # Получаем уникальные изображения из sku_props (только доступные варианты)
        sku_images = self._get_unique_images_from_sku_props(product_data)
        
        # Получаем дополнительные изображения из item_desc
        item_id = product_data.get('item_id')
        detail_images = []
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Извлечен item_id: {item_id}")
        
        if item_id:
            detail_images = await self._get_filtered_detail_images(item_id)
            if settings.DEBUG_MODE:
                print(f"[Scraper] Получено detail изображений: {len(detail_images)}")
        else:
            if settings.DEBUG_MODE:
                print(f"[Scraper] ⚠️ item_id отсутствует! Пропускаем получение detail изображений.")
        
        # Объединяем изображения: сначала из sku_props, потом из detail_html
        image_urls = sku_images + detail_images
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Итого изображений: {len(image_urls)} (sku: {len(sku_images)}, detail: {len(detail_images)})")

        return post_text, image_urls
    
    def _prepare_compact_data_for_llm(self, product_data: dict) -> dict:
        """
        Подготавливает компактные данные для отправки в LLM.
        Убирает огромный массив skus и другие лишние данные.
        
        Args:
            product_data: Полные данные от TMAPI
            
        Returns:
            dict: Компактные данные только с нужной информацией
        """
        compact = {
            'title': product_data.get('title', ''),
            'product_props': product_data.get('product_props', [])
        }
        
        # Добавляем уникальные значения цветов и размеров из sku_props (НЕ из skus!)
        sku_props = product_data.get('sku_props', [])
        if sku_props:
            for prop in sku_props:
                prop_name = prop.get('prop_name', '')
                
                # Извлекаем цвета
                if 'цвет' in prop_name.lower() or 'color' in prop_name.lower():
                    colors = [v.get('name', '') for v in prop.get('values', [])]
                    if colors:
                        compact['available_colors'] = colors[:20]  # Максимум 20 цветов
                
                # Извлекаем размеры
                if 'размер' in prop_name.lower() or 'size' in prop_name.lower() or '尺码' in prop_name:
                    sizes = [v.get('name', '') for v in prop.get('values', [])]
                    if sizes:
                        compact['available_sizes'] = sizes[:30]  # Максимум 30 размеров
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Компактные данные для LLM подготовлены. Размер: ~{len(str(compact))} символов")
            print(f"[Scraper] Исключено {len(product_data.get('skus', []))} элементов из skus")
        
        return compact
    
    def _get_unique_images_from_sku_props(self, product_data: dict) -> list:
        """
        Извлекает уникальные URL изображений из sku_props.
        Берет только изображения вариантов товара (цвета, модели).
        
        Args:
            product_data: Данные товара от TMAPI
            
        Returns:
            list: Список уникальных URL изображений
        """
        unique_images = []
        seen_urls = set()
        
        sku_props = product_data.get('sku_props', [])
        
        if not sku_props:
            # Fallback на main_imgs если нет sku_props
            if settings.DEBUG_MODE:
                print(f"[Scraper] sku_props отсутствует, используем main_imgs")
            return product_data.get('main_imgs', [])
        
        # Проходим по всем свойствам SKU
        for prop in sku_props:
            prop_name = prop.get('prop_name', '')
            
            # Берем изображения из вариантов (обычно цвета имеют картинки)
            # Можно взять из любого prop, но обычно цвета самые информативные
            values = prop.get('values', [])
            
            for value in values:
                image_url = value.get('imageUrl', '').strip()
                
                # Добавляем только уникальные и непустые URL
                if image_url and image_url not in seen_urls:
                    seen_urls.add(image_url)
                    unique_images.append(image_url)
        
        # Если не нашли изображения в sku_props, берем из main_imgs
        if not unique_images:
            if settings.DEBUG_MODE:
                print(f"[Scraper] Изображения в sku_props не найдены, используем main_imgs")
            return product_data.get('main_imgs', [])
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Извлечено {len(unique_images)} уникальных изображений из sku_props")
        
        return unique_images
    
    async def _get_filtered_detail_images(self, item_id: int) -> list:
        """
        Получает дополнительные изображения из item_desc и фильтрует их по размерам.
        Убирает баннеры и изображения, которые сильно отличаются от основной группы.
        
        Args:
            item_id: ID товара
            
        Returns:
            list: Отфильтрованный список URL изображений
        """
        try:
            if settings.DEBUG_MODE:
                print(f"[Scraper] Запрашиваем item_desc для item_id={item_id}")
            
            # Получаем описание товара
            desc_data = await self.tmapi_client.get_item_description(item_id)
            
            if settings.DEBUG_MODE:
                print(f"[Scraper] item_desc ответ: code={desc_data.get('code')}, data keys={list(desc_data.get('data', {}).keys()) if desc_data.get('data') else 'None'}")
            
            if not desc_data or desc_data.get('code') != 200:
                if settings.DEBUG_MODE:
                    print(f"[Scraper] ⚠️ Не удалось получить item_desc. Код: {desc_data.get('code') if desc_data else 'None'}")
                    print(f"[Scraper] Ответ API: {desc_data}")
                return []
            
            detail_html = desc_data.get('data', {}).get('detail_html', '')
            
            if settings.DEBUG_MODE:
                html_len = len(detail_html) if detail_html else 0
                print(f"[Scraper] detail_html длина: {html_len} символов")
                if html_len > 0:
                    print(f"[Scraper] detail_html начало: {detail_html[:200]}...")
            
            if not detail_html:
                if settings.DEBUG_MODE:
                    print(f"[Scraper] ⚠️ detail_html пуст!")
                return []
            
            # Парсим HTML строку и извлекаем изображения
            images_with_sizes, images_urls_only = self._parse_detail_html(detail_html)
            
            # Если есть URL без размеров - определяем размеры
            if images_urls_only:
                if settings.DEBUG_MODE:
                    print(f"[Scraper] Определяем размеры для {len(images_urls_only)} изображений...")
                
                images_from_urls = await self._get_image_sizes_from_urls(images_urls_only)
                images_with_sizes.extend(images_from_urls)
            
            if not images_with_sizes:
                if settings.DEBUG_MODE:
                    print(f"[Scraper] ⚠️ Не удалось получить изображения с размерами")
                return []
            
            if settings.DEBUG_MODE:
                print(f"[Scraper] Всего изображений с размерами: {len(images_with_sizes)}")
            
            # Фильтруем изображения
            filtered_images = self._filter_images_by_size(images_with_sizes)
            
            if settings.DEBUG_MODE:
                print(f"[Scraper] Detail изображений: {len(images_with_sizes)} → {len(filtered_images)} после фильтрации")
            
            return [img['url'] for img in filtered_images]
            
        except Exception as e:
            if settings.DEBUG_MODE:
                import traceback
                print(f"[Scraper] ❌ ОШИБКА при получении detail изображений:")
                print(f"[Scraper] Тип ошибки: {type(e).__name__}")
                print(f"[Scraper] Сообщение: {e}")
                print(f"[Scraper] Traceback:")
                traceback.print_exc()
            return []
    
    def _parse_detail_html(self, detail_html: str) -> list:
        """
        Парсит HTML строку с тегами <img> и извлекает URL.
        Если атрибут size присутствует - использует его, иначе получает размеры по URL.
        
        Args:
            detail_html: HTML строка с тегами <img>
            
        Returns:
            list: Список словарей с url, width, height
        """
        import re
        
        images_with_sizes = []
        images_urls_only = []
        
        # Находим все теги <img>
        img_tags = re.findall(r'<img[^>]*>', detail_html, re.IGNORECASE)
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Найдено {len(img_tags)} тегов <img> в HTML")
        
        for img_tag in img_tags:
            # Извлекаем src
            src_match = re.search(r'src="([^"]+)"', img_tag, re.IGNORECASE)
            if not src_match:
                continue
            
            url = src_match.group(1).strip()
            
            # Пытаемся извлечь size (если есть)
            size_match = re.search(r'size="(\d+)x(\d+)"', img_tag, re.IGNORECASE)
            
            if size_match:
                try:
                    width = int(size_match.group(1))
                    height = int(size_match.group(2))
                    
                    if width > 0 and height > 0:
                        images_with_sizes.append({
                            'url': url,
                            'width': width,
                            'height': height
                        })
                except ValueError:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] Не удалось распарсить size: {size_match.group(1)}x{size_match.group(2)}")
            else:
                # Нет атрибута size - сохраняем URL для определения размера
                images_urls_only.append(url)
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] С атрибутом size: {len(images_with_sizes)}")
            print(f"[Scraper] Без атрибута size: {len(images_urls_only)}")
        
        # Возвращаем оба списка для дальнейшей обработки
        return images_with_sizes, images_urls_only
    
    async def _get_image_sizes_from_urls(self, urls: list) -> list:
        """
        Определяет размеры изображений по URL.
        Обрабатывает по 5 изображений параллельно для предотвращения перегрузки.
        
        Args:
            urls: Список URL изображений
            
        Returns:
            list: Список словарей с url, width, height
        """
        import asyncio
        
        images_with_sizes = []
        
        # Обрабатываем порциями по 5 для предотвращения перегрузки
        batch_size = 5
        
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i+batch_size]
            
            if settings.DEBUG_MODE:
                print(f"[Scraper] Обрабатываем порцию {i//batch_size + 1}/{(len(urls) + batch_size - 1)//batch_size} ({len(batch)} изображений)...")
                print(f"[Scraper] URLs в этой порции:")
                for idx, url in enumerate(batch):
                    print(f"[Scraper]   {idx+1}. {url[:100]}...")
            
            # Создаем задачи для текущей порции
            tasks = [self._get_single_image_size(url) for url in batch]
            
            if settings.DEBUG_MODE:
                print(f"[Scraper] Создано {len(tasks)} задач, запускаем asyncio.gather()...")
            
            # Запускаем параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            if settings.DEBUG_MODE:
                print(f"[Scraper] asyncio.gather() завершён, получено {len(results)} результатов")
                print(f"[Scraper] Типы результатов: {[type(r).__name__ for r in results]}")
            
            # Собираем успешные результаты
            for idx, result in enumerate(results):
                if isinstance(result, dict) and 'url' in result:
                    images_with_sizes.append(result)
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ✅ Результат {idx+1}: {result['width']}x{result['height']}")
                elif isinstance(result, Exception):
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ❌ Результат {idx+1}: Exception - {type(result).__name__}: {result}")
                elif result is None:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ⚠️ Результат {idx+1}: None")
                else:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ⚠️ Результат {idx+1}: {type(result).__name__} = {result}")
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] ✅ Успешно определены размеры для {len(images_with_sizes)} из {len(urls)} изображений")
        
        return images_with_sizes
    
    async def _get_single_image_size(self, url: str) -> dict:
        """
        Определяет размер одного изображения по URL.
        Сначала пытается Range запрос (4KB), если не работает - загружает полностью (с лимитом).
        
        Args:
            url: URL изображения
            
        Returns:
            dict: Словарь с url, width, height или None при ошибке
        """
        if settings.DEBUG_MODE:
            print(f"[Scraper] >>> Начинаем обработку: {url[:80]}...")
        
        import httpx
        import imagesize
        from io import BytesIO
        
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                # Попытка 1: Range запрос (экономия трафика)
                headers = {'Range': 'bytes=0-4095'}
                
                try:
                    response = await client.get(url, headers=headers)
                    
                    if settings.DEBUG_MODE:
                        content_range = response.headers.get('Content-Range', 'нет')
                        print(f"[Scraper] 🔍 Range запрос: HTTP {response.status_code}, размер: {len(response.content)} байт, Content-Range: {content_range}")
                    
                    if response.status_code in (200, 206):  # 200 = полный файл, 206 = часть
                        data = BytesIO(response.content)
                        width, height = imagesize.get(data)
                        
                        if width > 0 and height > 0:
                            # Для Range запроса file_size берём из Content-Range (формат: "bytes 0-4095/150000")
                            file_size = 0
                            content_range = response.headers.get('Content-Range', '')
                            if content_range:
                                # Парсим "bytes 0-4095/150000" -> берём 150000
                                parts = content_range.split('/')
                                if len(parts) == 2:
                                    try:
                                        file_size = int(parts[1])
                                    except ValueError:
                                        pass
                            
                            if settings.DEBUG_MODE:
                                if file_size > 0:
                                    print(f"[Scraper] ✅ Range запрос успешен: {width}x{height}, полный размер: {file_size/1024:.1f}KB")
                                else:
                                    print(f"[Scraper] ✅ Range запрос успешен: {width}x{height} (размер файла неизвестен)")
                            return {
                                'url': url,
                                'width': width,
                                'height': height,
                                'file_size': file_size
                            }
                        else:
                            if settings.DEBUG_MODE:
                                print(f"[Scraper] ⚠️ Range запрос: imagesize вернул {width}x{height}")
                    
                except Exception as range_error:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ⚠️ Range запрос не сработал: {type(range_error).__name__}: {range_error}")
                
                # Попытка 2: Полная загрузка (с лимитом 200KB для безопасности)
                if settings.DEBUG_MODE:
                    print(f"[Scraper] 🔄 Пробуем полную загрузку...")
                
                response = await client.get(url)
                
                # Ограничение: не более 200KB
                if len(response.content) > 200 * 1024:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ⚠️ Изображение слишком большое: {len(response.content)} байт")
                    # Но всё равно пробуем определить размер из первых байтов
                    data = BytesIO(response.content[:4096])
                else:
                    data = BytesIO(response.content)
                
                width, height = imagesize.get(data)
                
                if width > 0 and height > 0:
                    file_size = len(response.content)
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ✅ Полная загрузка успешна: {width}x{height}, размер: {file_size/1024:.1f}KB")
                    return {
                        'url': url,
                        'width': width,
                        'height': height,
                        'file_size': file_size
                    }
                else:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ❌ imagesize вернул {width}x{height}")
                    return None
                    
        except Exception as e:
            if settings.DEBUG_MODE:
                print(f"[Scraper] ❌ Ошибка при получении размера:")
                print(f"[Scraper]    URL: {url[:100]}...")
                print(f"[Scraper]    Тип: {type(e).__name__}")
                print(f"[Scraper]    Сообщение: {e}")
            return None
    
    def _filter_images_by_size(self, images_with_sizes: list) -> list:
        """
        Фильтрует изображения по размерам.
        Убирает баннеры, иконки/кнопки и изображения, которые сильно отличаются от большинства.
        
        Args:
            images_with_sizes: Список словарей с url, width, height, file_size (опционально)
            
        Returns:
            list: Отфильтрованный список изображений
        """
        import statistics
        
        if not images_with_sizes:
            return []
        
        # Шаг 1: Убираем слишком маленькие изображения (иконки, кнопки)
        min_dimension = 400  # Минимум 400x400
        large_enough = []
        
        for img in images_with_sizes:
            width = img['width']
            height = img['height']
            
            if width >= min_dimension and height >= min_dimension:
                large_enough.append(img)
            elif settings.DEBUG_MODE:
                print(f"[Scraper] Пропускаем слишком маленькое: {width}x{height} (минимум {min_dimension}x{min_dimension})")
        
        if not large_enough:
            if settings.DEBUG_MODE:
                print(f"[Scraper] ⚠️ Все изображения слишком маленькие")
            return []
        
        # Шаг 2: Убираем по размеру файла (если доступно)
        min_file_size = 20 * 1024  # Минимум 20KB
        size_filtered = []
        
        for img in large_enough:
            file_size = img.get('file_size', 0)
            
            if file_size == 0:
                # Размер файла неизвестен - оставляем (сервер не вернул Content-Range)
                size_filtered.append(img)
                if settings.DEBUG_MODE:
                    print(f"[Scraper] Пропускаем проверку веса для {img['width']}x{img['height']} (размер неизвестен)")
            elif file_size >= min_file_size:
                size_filtered.append(img)
            else:
                if settings.DEBUG_MODE:
                    print(f"[Scraper] Пропускаем слишком лёгкое: {img['width']}x{img['height']} ({file_size/1024:.1f}KB < {min_file_size/1024:.0f}KB)")
        
        if not size_filtered:
            if settings.DEBUG_MODE:
                print(f"[Scraper] ⚠️ Все изображения слишком лёгкие")
            return []
        
        # Шаг 3: Убираем явные баннеры (соотношение сторон > 5:1 или < 1:5)
        non_banners = []
        for img in size_filtered:
            width = img['width']
            height = img['height']
            aspect_ratio = width / height if height > 0 else 0
            
            # Если соотношение от 0.2 до 5.0 - это НЕ баннер
            if 0.2 <= aspect_ratio <= 5.0:
                non_banners.append(img)
            elif settings.DEBUG_MODE:
                print(f"[Scraper] Пропускаем баннер: {width}x{height} (aspect: {aspect_ratio:.2f})")
        
        if not non_banners:
            if settings.DEBUG_MODE:
                print(f"[Scraper] ⚠️ Все изображения - баннеры")
            return []
        
        # Шаг 4: Находим медианный размер (площадь)
        areas = [img['width'] * img['height'] for img in non_banners]
        median_area = statistics.median(areas)
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Медианная площадь: {median_area:,.0f} пикселей")
        
        # Шаг 5: Убираем изображения, которые сильно отличаются от медианы по площади
        # УЖЕСТОЧЕННЫЙ допуск: изображение должно быть в пределах 0.6x - 1.7x от медианы
        area_filtered = []
        for img in non_banners:
            area = img['width'] * img['height']
            ratio = area / median_area if median_area > 0 else 0
            
            if 0.6 <= ratio <= 1.7:
                area_filtered.append(img)
            elif settings.DEBUG_MODE:
                print(f"[Scraper] Пропускаем изображение {img['width']}x{img['height']} (площадь отличается в {ratio:.2f}x от медианы)")
        
        if not area_filtered:
            if settings.DEBUG_MODE:
                print(f"[Scraper] ⚠️ Все изображения отличаются по площади")
            return []
        
        # Шаг 6: Проверяем однородность aspect ratio (чтобы отсеять горизонтальные среди вертикальных и наоборот)
        aspect_ratios = [img['width'] / img['height'] if img['height'] > 0 else 0 for img in area_filtered]
        median_aspect = statistics.median(aspect_ratios)
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Медианный aspect ratio: {median_aspect:.2f}")
        
        filtered = []
        for img in area_filtered:
            aspect = img['width'] / img['height'] if img['height'] > 0 else 0
            # Если медианный aspect ~0.77 (вертикальные), то допускаем 0.5-1.5
            # Если медианный aspect ~1.0 (квадратные), то допускаем 0.7-1.4
            # Если медианный aspect ~1.5 (горизонтальные), то допускаем 1.0-2.0
            # Используем адаптивный диапазон: ±40% от медианы
            min_aspect = median_aspect * 0.6
            max_aspect = median_aspect * 1.4
            
            if min_aspect <= aspect <= max_aspect:
                filtered.append(img)
            elif settings.DEBUG_MODE:
                print(f"[Scraper] Пропускаем изображение {img['width']}x{img['height']} (aspect {aspect:.2f} не в диапазоне {min_aspect:.2f}-{max_aspect:.2f})")
        
        if settings.DEBUG_MODE and filtered:
            sizes = [f"{img['width']}x{img['height']}" for img in filtered]
            print(f"[Scraper] ✅ Прошли фильтр: {', '.join(sizes)}")
        
        return filtered
    
    def _get_max_price_from_skus(self, product_data: dict) -> str:
        """
        Извлекает максимальную цену из skus где stock > 0.
        
        Args:
            product_data: Данные товара от TMAPI
            
        Returns:
            str: Максимальная цена или цена из price_info
        """
        skus = product_data.get('skus', [])
        
        if not skus:
            # Если skus нет, берем из price_info
            return product_data.get('price_info', {}).get('price', 'N/A')
        
        # Фильтруем skus с stock > 0
        available_skus = [sku for sku in skus if sku.get('stock', 0) > 0]
        
        if not available_skus:
            # Если нет доступных, берем из price_info
            return product_data.get('price_info', {}).get('price', 'N/A')
        
        # Ищем максимальную sale_price
        max_price = None
        for sku in available_skus:
            sale_price = sku.get('sale_price')
            if sale_price is not None:
                try:
                    price_value = float(sale_price)
                    if max_price is None or price_value > max_price:
                        max_price = price_value
                except (ValueError, TypeError):
                    continue
        
        if max_price is not None:
            if settings.DEBUG_MODE:
                print(f"[Scraper] Максимальная цена из skus: {max_price}")
            return str(max_price)
        
        # Fallback на price_info
        return product_data.get('price_info', {}).get('price', 'N/A')
    
    def _format_size_range(self, sizes_str: str) -> str:
        """
        Форматирует размерный ряд. Если размеры последовательные, возвращает диапазон.
        
        Args:
            sizes_str: Строка с размерами (например "S, M, L" или "35, 36, 37, 38")
        
        Returns:
            str: Отформатированная строка размеров
        """
        if not sizes_str or not sizes_str.strip():
            return sizes_str
            
        # Стандартные размеры одежды в порядке
        standard_sizes = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        
        # Разбиваем строку на части и очищаем
        sizes_raw = [s.strip() for s in sizes_str.replace(',', ' ').split() if s.strip()]
        
        # Попытка обработать числовые размеры (обувь)
        try:
            numeric_sizes = [float(s) for s in sizes_raw]
            # Проверяем последовательность для числовых размеров
            if len(numeric_sizes) > 2:
                sorted_sizes = sorted(numeric_sizes)
                # Проверяем что это последовательность с шагом 1
                is_sequential = all(
                    sorted_sizes[i+1] - sorted_sizes[i] == 1.0 
                    for i in range(len(sorted_sizes)-1)
                )
                if is_sequential:
                    # Форматируем как целые числа если они целые
                    first = int(sorted_sizes[0]) if sorted_sizes[0].is_integer() else sorted_sizes[0]
                    last = int(sorted_sizes[-1]) if sorted_sizes[-1].is_integer() else sorted_sizes[-1]
                    return f"{first}-{last}"
            # Если не последовательность, возвращаем через запятую
            return ", ".join(str(int(s) if s.is_integer() else s) for s in numeric_sizes)
        except (ValueError, AttributeError):
            # Не числовые размеры, обрабатываем как буквенные
            pass
        
        # Обработка буквенных размеров (одежда)
        sizes = [s.upper() for s in sizes_raw]
        
        # Проверяем, все ли размеры стандартные
        if all(s in standard_sizes for s in sizes):
            # Получаем индексы
            indices = [standard_sizes.index(s) for s in sizes]
            
            # Проверяем последовательность (без пропусков)
            if len(indices) > 1 and indices == list(range(min(indices), max(indices) + 1)):
                # Возвращаем диапазон
                return f"{sizes[0]}-{sizes[-1]}"
        
        # Возвращаем как есть (через запятую)
        return ", ".join(sizes_raw)
    
    def _build_post_text(self, llm_content: dict, product_data: dict, exchange_rate: float = None) -> str:
        """
        Формирует финальный текст поста из структурированных данных LLM и данных API.
        Использует HTML разметку для Telegram.

        Args:
            llm_content (dict): Структурированный контент от YandexGPT
            product_data (dict): Данные о товаре от TMAPI
            exchange_rate (float, optional): Курс обмена CNY в RUB

        Returns:
            str: Отформатированный текст поста в HTML
        """
        # Извлекаем данные из LLM ответа
        title = llm_content.get('title', 'Товар')
        description = llm_content.get('description', '')
        main_characteristics = llm_content.get('main_characteristics', {})
        additional_info = llm_content.get('additional_info', {})
        hashtags = llm_content.get('hashtags', [])
        emoji = llm_content.get('emoji', '')
        
        # Извлекаем цену из skus (максимальная sale_price где stock > 0)
        price = self._get_max_price_from_skus(product_data)
        
        if settings.DEBUG_MODE:
            price_info = product_data.get('price_info', {})
            print(f"[Scraper] Итоговая цена: {price}")
            print(f"[Scraper] Цена из price_info: {price_info.get('price', 'N/A')}")
            if 'origin_price' in price_info:
                print(f"[Scraper] Origin price: {price_info.get('origin_price')}")
        
        product_url = product_data.get('product_url', '')
        
        # Начинаем формировать пост
        post_parts = []
        
        # Заголовок с эмодзи (жирным шрифтом)
        title_line = f"{emoji} " if emoji else ""
        title_line += f"<b>{title}</b>"
        post_parts.append(title_line)
        post_parts.append("")
        
        # Описание в виде цитаты (курсивом)
        if description:
            post_parts.append(f"<blockquote><i>{description}</i></blockquote>")
            post_parts.append("")
        
        # Основные характеристики
        if main_characteristics:
            # Список неопределенных/пустых значений для фильтрации
            invalid_values = [
                'другие материалы', 'прочие материалы', 'неизвестно', 
                'смешанные материалы', 'other materials', 'unknown', 
                'mixed', 'various', 'прочие', 'другие', 'не указано',
                'не указан', 'не указана', 'не указаны',
                'нет информации', 'нет данных', 'no information',
                'not specified', 'н/д', 'n/a', ''
            ]
            
            # Фильтруем и отображаем характеристики в правильном порядке
            # Порядок: Состав/Материал → Цвета → Размеры/Объём → Остальное
            ordered_keys = []
            
            # Сначала состав/материал (если есть и он конкретный)
            for key in main_characteristics.keys():
                if 'материал' in key.lower() or 'состав' in key.lower():
                    value = main_characteristics[key]
                    # Проверяем что значение не пустое и не из списка неопределенных
                    if value and isinstance(value, str) and value.strip() and value.lower().strip() not in invalid_values:
                        ordered_keys.append(key)
            
            # Затем цвета
            for key in main_characteristics.keys():
                if 'цвет' in key.lower() or 'color' in key.lower():
                    value = main_characteristics[key]
                    # Проверяем что цвета не пустые
                    if value and (isinstance(value, list) and len(value) > 0 or isinstance(value, str) and value.strip()):
                        ordered_keys.append(key)
            
            # Затем размеры и объёмы
            for key in main_characteristics.keys():
                if 'размер' in key.lower() or 'size' in key.lower() or 'объём' in key.lower() or 'объем' in key.lower():
                    value = main_characteristics[key]
                    # Проверяем что значение не пустое и не "не указан"
                    if value and isinstance(value, str) and value.strip() and value.lower().strip() not in invalid_values:
                        ordered_keys.append(key)
            
            # Остальные характеристики (если есть значимые)
            for key in main_characteristics.keys():
                if key not in ordered_keys:
                    value = main_characteristics[key]
                    # Добавляем только если значение не пустое
                    if value and (isinstance(value, list) and len(value) > 0 or isinstance(value, str) and value.strip()):
                        ordered_keys.append(key)
            
            # Отображаем характеристики в правильном порядке
            for key in ordered_keys:
                value = main_characteristics[key]
                
                # Дополнительная проверка: пропускаем неопределенные значения
                if isinstance(value, str) and value.lower().strip() in invalid_values:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] Фильтруем неопределенное значение '{key}': '{value}'")
                    continue
                
                # Пропускаем пустые значения
                if not value:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                if isinstance(value, list) and len(value) == 0:
                    continue
                
                # Форматируем размеры если это размеры
                if 'размер' in key.lower() and isinstance(value, str):
                    value = self._format_size_range(value)
                
                if isinstance(value, list):
                    # Если значение - список (например, цвета)
                    post_parts.append(f"<i><b>{key}:</b></i>")
                    for item in value:
                        post_parts.append(f"<i>  • {item}</i>")
                    post_parts.append("")
                else:
                    # Если значение - строка
                    post_parts.append(f"<i><b>{key}:</b> {value}</i>")
        
        # Дополнительная информация (только если есть)
        if additional_info:
            for key, value in additional_info.items():
                # Пропускаем пустые значения
                if value and str(value).strip():
                    post_parts.append(f"<i><b>{key}:</b> {value}</i>")
            
            # Добавляем пустую строку только если были доп. данные
            if any(v and str(v).strip() for v in additional_info.values()):
                post_parts.append("")
        
        # Если были характеристики, добавляем отступ перед ценой
        if main_characteristics or additional_info:
            if not post_parts[-1] == "":
                post_parts.append("")
        
        # Цена с эмодзи (курсивом)
        price_text = f"<i>💰 <b>Цена:</b> {price} юаней"
        if exchange_rate and settings.CONVERT_CURRENCY:
            try:
                rub_price = float(price) * exchange_rate
                price_text += f" (~{rub_price:.2f} ₽)"
            except (ValueError, TypeError):
                pass
        price_text += " + доставка</i>"
        post_parts.append(price_text)
        post_parts.append("")
        
        # Призыв к действию (курсивом)
        post_parts.append("<i>📝 Для заказа пишите @annabbox или в комментариях 🛍️</i>")
        post_parts.append("")
        
        # Хэштеги (курсивом)
        if hashtags:
            hashtag_text = " ".join([f"#{tag}" for tag in hashtags])
            post_parts.append(f"<i>{hashtag_text}</i>")
            post_parts.append("")
        
        # Ссылка на товар
        if product_url:
            post_parts.append(f'<a href="{product_url}">Ссылка</a>')
        
        return "\n".join(post_parts)
