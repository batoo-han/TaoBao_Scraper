import inspect
import json
import logging
import re
from collections import Counter, OrderedDict, defaultdict

from src.api.tmapi import TmapiClient
from src.api.llm_provider import get_llm_client, get_translation_client
from src.api.exchange_rate import ExchangeRateClient
from src.api.proxyapi_client import ProxyAPIClient
from src.core.config import settings
from src.utils.url_parser import URLParser, Platform
from src.scrapers.pinduoduo_web import PinduoduoWebScraper

logger = logging.getLogger(__name__)

class Scraper:
    """
    Класс-оркестратор для сбора информации о товаре, его обработки и генерации поста.
    """
    
    COLOR_KEYWORDS = {
        "белый", "белая", "белые", "черный", "черная", "черные", "чёрный", "чёрная", "чёрные",
        "красный", "красная", "красные", "розовый", "розовая", "розовые",
        "синий", "синяя", "синие", "голубой", "голубая",
        "зелёный", "зелёная", "зелёные", "зеленый", "зеленая", "зеленые",
        "жёлтый", "жёлтая", "жёлтые", "желтый", "желтая", "желтые",
        "фиолетовый", "фиолетовая", "фиолетовые",
        "серый", "серая", "серые", "серебряный", "серебристый",
        "золотой", "золотая",
        "коричневый", "коричневая",
        "бежевый", "бежевые",
        "хаки", "бордовый", "мятный", "пудровый", "бирюзовый",
        "разноцветный", "многоцветный", "пёстрый", "пестрый"
    }
    COLOR_REGEX = re.compile(
        r"\b(" + "|".join(sorted(re.escape(word) for word in COLOR_KEYWORDS)) + r")\b",
        re.IGNORECASE
    )

    GENERIC_STOPWORDS = {
        "вариант", "варианты", "комплект", "комплекты", "набор", "наборы",
        "версии", "версия", "тип", "типы", "модель", "модели",
        "для", "из", "от", "без", "под", "на", "по", "и", "или", "с", "со",
        "в", "во", "это", "этот", "эта", "эти", "новый", "новая", "новые",
        "размер", "размеры", "цвет", "цвета"
    }

    BATTERY_KEYWORDS = ("батар", "battery", "power")
    CHARGE_KEYWORDS = ("заряд", "заряжа", "аккум", "recharge", "charging")
    def __init__(self):
        self.tmapi_client = TmapiClient()  # Клиент для tmapi.top
        self.llm_client = get_llm_client()  # Унифицированный LLM клиент (YandexGPT или OpenAI)
        self.exchange_rate_client = ExchangeRateClient()  # Клиент для ExchangeRate-API
        self.translation_client = get_translation_client()  # Отдельный LLM для переводов/предобработки цен
        # Для ProxyAPI отключаем режим структурированных (JSON) батч-переводов, чтобы не тратить лишний бюджет
        # и не получать нестабильные ответы через прокси.
        if isinstance(self.translation_client, ProxyAPIClient):
            self.translation_supports_structured = False
        else:
            self.translation_supports_structured = hasattr(self.translation_client, "generate_json_response")

    async def scrape_product(
        self, 
        url: str,
        user_signature: str = None,
        user_currency: str = None,
        exchange_rate: float = None
    ):
        """
        Собирает информацию о товаре по URL, генерирует структурированный контент
        и формирует финальный пост.

        Args:
            url (str): URL товара для скрапинга.
            user_signature (str, optional): Подпись пользователя для поста
            user_currency (str, optional): Валюта пользователя (cny или rub)
            exchange_rate (float, optional): Курс обмена для рубля

        Returns:
            tuple: Кортеж, содержащий сгенерированный текст поста (str) и список URL изображений (list).
        """
        # Используем настройки пользователя или значения по умолчанию
        signature = user_signature or settings.DEFAULT_SIGNATURE
        currency = (user_currency or settings.DEFAULT_CURRENCY).lower()
        # Сохраняем переданный курс пользователя (если есть)
        user_exchange_rate = exchange_rate if exchange_rate is not None else None
        # Определяем платформу заранее, чтобы Pinduoduo обрабатывать веб-скрапингом
        platform, _ = URLParser.parse_url(url)
        logger.info(f"Определена платформа: {platform} для URL: {url}")
        
        if platform == Platform.PINDUODUO:
            logger.info("Обработка Pinduoduo через веб-скрапинг")
            pdd = PinduoduoWebScraper()
            api_response = await pdd.fetch_product(url)
            logger.info(f"Ответ от Pinduoduo скрейпера: code={api_response.get('code')}, msg={api_response.get('msg')}")
            api_response['_platform'] = Platform.PINDUODUO
        else:
            # Получаем данные о товаре через tmapi.top (автоопределение платформы)
            logger.info("Обработка через TMAPI")
            api_response = await self.tmapi_client.get_product_info_auto(url)
        
        # Извлекаем платформу (добавлено методом get_product_info_auto)
        platform = api_response.get('_platform', 'unknown')
        
        # TMAPI возвращает структуру: {"code": 200, "msg": "success", "data": {...}}
        # Извлекаем данные о товаре из поля "data"
        if isinstance(api_response, dict) and 'data' in api_response:
            product_data = api_response['data']
        else:
            product_data = api_response
        
        # Сохраняем платформу в product_data для дальнейшего использования
        product_data['_platform'] = platform

        # Нормализуем URL товара для поста: используем короткий URL, если доступен
        try:
            if platform == Platform.PINDUODUO:
                # pinduoduo_web кладёт короткий URL в data.url
                short_url = product_data.get('url') or product_data.get('pdd_minimal', {}).get('url')
                if short_url:
                    product_data['product_url'] = short_url
        except Exception:
            pass
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Платформа: {platform}")
            print(f"[Scraper] Данные товара получены: {product_data.get('title', 'N/A')[:50]}...")
        
        # Ранняя проверка: если Pinduoduo и ошибка авторизации (401) — сообщаем пользователю
        if platform == 'pinduoduo':
            logger.info(f"Проверка ответа Pinduoduo: code={api_response.get('code') if isinstance(api_response, dict) else 'N/A'}")
            # Проверяем ошибку авторизации
            if isinstance(api_response, dict) and api_response.get('code') == 401:
                logger.warning("Ошибка 401: отсутствуют cookies для Pinduoduo")
                user_msg = (
                    "❌ Не удалось получить данные товара с Pinduoduo.\n\n"
                    "⚠️ Отсутствует файл с cookies для авторизации.\n\n"
                    "Для работы с Pinduoduo необходимо:\n"
                    "1. Создать файл `src/pdd_cookies.json` на основе `src/pdd_cookies_example.json`\n"
                    "2. Заполнить файл реальными cookies из вашего браузера\n"
                    "3. Перезапустить бота\n\n"
                    "Подробнее см. в документации проекта."
                )
                return user_msg, []
            # Ранняя проверка: если Pinduoduo и совсем пусто — прерываем цепочку до LLM
            no_images = not product_data.get('main_imgs') and not product_data.get('detail_imgs')
            no_text = not (product_data.get('details') or product_data.get('title'))
            logger.info(f"Проверка данных Pinduoduo: images={not no_images}, text={not no_text}")
            if no_images and no_text:
                logger.warning("Пустой результат от Pinduoduo: нет фото и описания")
                if settings.DEBUG_MODE:
                    print("[Scraper][Pinduoduo] Пустой результат: нет фото и описания. Прерываем цепочку.")
                    print(f"[Scraper][Pinduoduo] product_data keys: {list(product_data.keys())}")
                user_msg = (
                    "Не удалось получить данные товара с Pinduoduo.\n\n"
                    "Возможно, устарели cookies / User-Agent, страница требует капчу/логин или доступ ограничен.\n"
                    "Проверьте настройки авторизации и обновите cookies."
                )
                return user_msg, []
            # Переводим описание на русский через Yandex Translate перед LLM
            try:
                pdd_min = product_data.get('pdd_minimal', {}) if isinstance(product_data, dict) else {}
                raw_description = (
                    (pdd_min.get('description') or '').strip() or
                    (product_data.get('details') or '').strip() or
                    (product_data.get('title') or '').strip()
                )
                if raw_description:
                    translated = await self._translate_text_generic(raw_description, target_language="ru")
                    if translated and translated != raw_description:
                        product_data['details'] = translated
                        if settings.DEBUG_MODE:
                            print(f"[Scraper][Pinduoduo] Перевод описания выполнен, длина: {len(translated)}")
            except Exception as e:
                if settings.DEBUG_MODE:
                    print(f"[Scraper][Pinduoduo] Ошибка перевода описания: {e}")
        
        # Используем курс пользователя, если он передан, иначе получаем из API (если включено)
        exchange_rate = user_exchange_rate
        if exchange_rate is None and settings.CONVERT_CURRENCY:
            exchange_rate = await self.exchange_rate_client.get_exchange_rate()

        # Подготавливаем компактные данные для LLM (без огромного массива skus!)
        compact_data = self._prepare_compact_data_for_llm(product_data)

        # Заготавливаем переведённый заголовок и описание для контекста цен
        raw_title = product_data.get('title', '') or ''
        translated_title_hint = await self._translate_text_generic(raw_title, target_language="ru")
        if translated_title_hint:
            compact_data["title_hint"] = translated_title_hint
        
        # Извлекаем и переводим описание товара для контекста
        raw_description = ''
        platform = product_data.get('_platform')
        if platform == 'pinduoduo':
            pdd_min = product_data.get('pdd_minimal', {}) if isinstance(product_data, dict) else {}
            raw_description = (
                (pdd_min.get('description') or '').strip() or
                (product_data.get('details') or '').strip()
            )
        else:
            raw_description = (product_data.get('details') or '').strip()
        
        # Переводим описание (ограничиваем длину для скорости)
        translated_description = ''
        if raw_description:
            # Берём первые 500 символов описания для контекста
            description_sample = raw_description[:500]
            translated_description = await self._translate_text_generic(description_sample, target_language="ru")
        
        # Формируем контекст для перевода цен
        product_context = {
            'title': translated_title_hint or raw_title,
            'description': translated_description
        }

        price_lines = await self._prepare_price_entries(product_data, product_context)
        if price_lines:
            compact_data["translated_sku_prices"] = price_lines
        
        # Генерируем структурированный контент с помощью выбранного LLM
        # LLM вернет JSON с: title, description, characteristics, hashtags
        llm_content = await self.llm_client.generate_post_content(compact_data)
        translated_title = llm_content.get('title') or translated_title_hint
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] LLM контент получен: {llm_content.get('title', 'N/A')}")
        
        # Пост-обработка: исправляем общие термины в ценах на конкретные из описания
        if price_lines and llm_content:
            price_lines = self._fix_price_labels_with_context(price_lines, llm_content)
        
        # Санитация ответа LLM: убираем выдуманные «Цвета», добавляем/фиксируем «Состав»
        try:
            if isinstance(llm_content, dict):
                mc = llm_content.get('main_characteristics') or {}
                if not isinstance(mc, dict):
                    mc = {}
                looks_like_apparel = self._is_apparel_product(translated_title or translated_title_hint, product_data)
                # 1) Удаляем цвета, если LLM выдумал вроде «Чистый цвет»/«Однотонный»
                colors = mc.get('Цвета') or mc.get('Цвет')
                if colors:
                    bad_markers = {'чистый цвет', 'однотон', 'однотонный', 'plain', 'solid'}
                    def _is_bad(val: str) -> bool:
                        s = (val or '').strip().lower()
                        return any(k in s for k in bad_markers)
                    if isinstance(colors, list):
                        filtered = [c for c in colors if isinstance(c, str) and not _is_bad(c)]
                        if filtered:
                            mc['Цвета'] = filtered
                        else:
                            mc.pop('Цвета', None)
                    elif isinstance(colors, str) and _is_bad(colors):
                        mc.pop('Цвета', None)
                if not looks_like_apparel:
                    mc.pop('Цвета', None)
                    mc.pop('Цвет', None)
                # 2) Удаляем лишние секции «Варианты наборов», «Комплектации» и т.п.
                forbidden_sections = ('вариант', 'комплектац', 'набор')
                for key in list(mc.keys()):
                    if any(token in key.lower() for token in forbidden_sections):
                        mc.pop(key, None)
                # 3) Гарантируем «Состав», если он явным образом указан в описании
                platform = product_data.get('_platform')
                if platform == 'pinduoduo':
                    import re
                    desc_text = (product_data.get('details') or '')
                    comp = None
                    # Ищем «Ткань/материал», «Содержание волокон», «Состав»
                    for pat in [r"(?i)Состав[:：]\s*([^\n]+)", r"(?i)Ткань\s*/?\s*материал[:：]\s*([^\n]+)", r"(?i)Содержание волокон[:：]\s*([^\n]+)"]:
                        m = re.search(pat, desc_text)
                        if m:
                            comp = m.group(1).strip()
                            break
                    if comp:
                        if not str(mc.get('Состав') or '').strip():
                            mc['Состав'] = comp
                llm_content['main_characteristics'] = mc
        except Exception:
            pass
        
        # Формируем финальный пост из структурированных данных
        post_text = self._build_post_text(
            llm_content=llm_content,
            product_data=product_data,
            signature=signature,
            currency=currency,
            exchange_rate=exchange_rate,
            price_lines=price_lines
        )
        
        # Получаем изображения в зависимости от платформы
        if platform == 'pinduoduo':
            # Для Pinduoduo: main_imgs + detail_imgs (нет sku_props)
            sku_images = product_data.get('main_imgs', [])
            
            # У Pinduoduo detail_imgs уже есть в основном ответе
            detail_images = product_data.get('detail_imgs', [])
            
            if settings.DEBUG_MODE:
                print(f"[Scraper] Pinduoduo: main_imgs={len(sku_images)}, detail_imgs={len(detail_images)}")
        else:
            # Для Taobao/Tmall: сравниваем main_imgs и sku_props
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
        Поддерживает как Taobao/Tmall, так и Pinduoduo.
        
        Args:
            product_data: Полные данные от TMAPI
            
        Returns:
            dict: Компактные данные только с нужной информацией
        """
        platform = product_data.get('_platform', 'unknown')
        
        compact = {
            'title': product_data.get('title', ''),
            'product_props': product_data.get('product_props', [])
        }
        
        # Обработка в зависимости от платформы
        if platform == 'pinduoduo':
            # Для Pinduoduo: извлекаем варианты из skus (props_names)
            skus = product_data.get('skus', [])
            colors = set()
            sizes = set()
            
            for sku in skus[:50]:  # Ограничиваем 50 SKU
                props_names = sku.get('props_names', '')
                # Формат: "型号:经济款;套餐:礼包一"
                if props_names:
                    props_parts = props_names.split(';')
                    for part in props_parts:
                        if ':' in part:
                            key, value = part.split(':', 1)
                            # Определяем цвет или размер по ключу
                            if '颜色' in key or 'color' in key.lower() or '色' in key:
                                colors.add(value)
                            elif '尺码' in key or 'size' in key.lower() or '型号' in key:
                                sizes.add(value)
            
            if colors:
                compact['available_colors'] = list(colors)[:20]
            if sizes:
                compact['available_sizes'] = list(sizes)[:30]
        else:
            # Для Taobao/Tmall: используем sku_props
            sku_props = product_data.get('sku_props', [])
            if sku_props:
                for prop in sku_props:
                    prop_name = prop.get('prop_name', '')
                    
                    # Извлекаем цвета
                    if 'цвет' in prop_name.lower() or 'color' in prop_name.lower():
                        colors = [v.get('name', '') for v in prop.get('values', [])]
                        if colors:
                            compact['available_colors'] = colors[:20]
                    
                    # Извлекаем размеры
                    if 'размер' in prop_name.lower() or 'size' in prop_name.lower() or '尺码' in prop_name:
                        sizes = [v.get('name', '') for v in prop.get('values', [])]
                        if sizes:
                            compact['available_sizes'] = sizes[:30]
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Компактные данные для LLM подготовлены. Размер: ~{len(str(compact))} символов")
            print(f"[Scraper] Исключено {len(product_data.get('skus', []))} элементов из skus")
        
        return compact
    
    def _get_unique_images_from_sku_props(self, product_data: dict) -> list:
        """
        Извлекает уникальные URL изображений, выбирая лучший источник.
        Сравнивает количество изображений в main_imgs и sku_props.
        Берет откуда больше. Если равно - берет из main_imgs.
        
        Args:
            product_data: Данные товара от TMAPI
            
        Returns:
            list: Список уникальных URL изображений из лучшего источника
        """
        # Получаем изображения из main_imgs
        main_imgs = product_data.get('main_imgs', [])
        main_imgs_count = len(main_imgs) if main_imgs else 0
        
        # Получаем sku_props
        sku_props = product_data.get('sku_props', [])
        
        if not sku_props:
            # Если нет sku_props, используем main_imgs
            if settings.DEBUG_MODE:
                print(f"[Scraper] sku_props отсутствует, используем main_imgs ({main_imgs_count} изображений)")
            return main_imgs
        
        # Собираем уникальные изображения из sku_props
        sku_unique_images = []
        seen_urls = set()
        
        for prop in sku_props:
            values = prop.get('values', [])
            
            for value in values:
                image_url = value.get('imageUrl', '').strip()
                
                # Добавляем только уникальные и непустые URL
                if image_url and image_url not in seen_urls:
                    seen_urls.add(image_url)
                    sku_unique_images.append(image_url)
        
        sku_props_count = len(sku_unique_images)
        
        # Сравниваем количество и выбираем лучший источник
        if sku_props_count > main_imgs_count:
            # В sku_props больше изображений
            if settings.DEBUG_MODE:
                print(f"[Scraper] sku_props: {sku_props_count} изображений > main_imgs: {main_imgs_count} → используем sku_props")
            return sku_unique_images
        elif main_imgs_count > sku_props_count:
            # В main_imgs больше изображений
            if settings.DEBUG_MODE:
                print(f"[Scraper] main_imgs: {main_imgs_count} изображений > sku_props: {sku_props_count} → используем main_imgs")
            return main_imgs
        else:
            # Равное количество - приоритет main_imgs
            if settings.DEBUG_MODE:
                print(f"[Scraper] main_imgs: {main_imgs_count} = sku_props: {sku_props_count} → используем main_imgs (приоритет)")
            return main_imgs if main_imgs else sku_unique_images
    
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
        from PIL import Image
        from io import BytesIO
        
        try:
            # Заголовки для обхода блокировки Alibaba CDN (HTTP 420)
            browser_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://item.taobao.com/',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
            }
            
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=browser_headers) as client:
                # Попытка 1: Range запрос (экономия трафика)
                # Увеличиваем до 64KB для более надёжного определения размеров JPEG/PNG
                headers = {'Range': 'bytes=0-65535'}  # 64KB достаточно для определения размеров большинства изображений
                
                try:
                    response = await client.get(url, headers=headers)
                    
                    if settings.DEBUG_MODE:
                        content_range = response.headers.get('Content-Range', 'нет')
                        print(f"[Scraper] 🔍 Range запрос: HTTP {response.status_code}, размер: {len(response.content)} байт, Content-Range: {content_range}")
                    
                    if response.status_code in (200, 206):  # 200 = полный файл, 206 = часть
                        try:
                            # Используем PIL для определения размеров
                            img = Image.open(BytesIO(response.content))
                            width, height = img.size
                            
                            if width > 0 and height > 0:
                                # Для Range запроса file_size берём из Content-Range (формат: "bytes 0-65535/150000")
                                file_size = 0
                                content_range = response.headers.get('Content-Range', '')
                                if content_range:
                                    # Парсим "bytes 0-65535/150000" -> берём 150000
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
                        except Exception as pil_error:
                            if settings.DEBUG_MODE:
                                print(f"[Scraper] ⚠️ Range запрос: PIL не смог открыть изображение: {type(pil_error).__name__}")
                    
                except Exception as range_error:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ⚠️ Range запрос не сработал: {type(range_error).__name__}: {range_error}")
                
                # Попытка 2: Полная загрузка (с лимитом 2MB для определения размеров)
                # Увеличиваем лимит, так как многие изображения Taobao имеют размер 500-700KB
                if settings.DEBUG_MODE:
                    print(f"[Scraper] 🔄 Пробуем полную загрузку...")
                
                response = await client.get(url)
                
                # Ограничение: не более 2MB (для определения размеров это нормально)
                # Большие изображения (>2MB) обычно являются баннерами или некачественными
                if len(response.content) > 2 * 1024 * 1024:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ⚠️ Изображение слишком большое: {len(response.content)/1024:.1f}KB (лимит 2MB)")
                    return None
                
                try:
                    # Используем PIL для определения размеров
                    img = Image.open(BytesIO(response.content))
                    width, height = img.size
                    
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
                            print(f"[Scraper] ❌ PIL вернул {width}x{height}")
                        return None
                except Exception as pil_error:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ❌ PIL не смог открыть изображение: {type(pil_error).__name__}: {pil_error}")
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
        min_dimension = 150  # Минимум 150x150
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

    def _fix_price_labels_with_context(self, price_lines: list[dict], llm_content: dict) -> list[dict]:
        """
        Исправляет общие термины в названиях цен на конкретные типы товаров из описания LLM.
        
        Например, заменяет "верхняя одежда" на "рубашка", если в описании упоминается "рубашка".
        """
        if not price_lines or not llm_content:
            return price_lines
        
        # Извлекаем текст описания и заголовок
        description = llm_content.get('description', '')
        title = llm_content.get('title', '')
        context_text = f"{title} {description}".lower()
        
        # Список общих терминов, которые нужно заменить на конкретные
        generic_terms = {
            'верхняя одежда': ['рубашка', 'куртка', 'свитер', 'кофта', 'пиджак', 'жилет', 'худи', 'толстовка'],
            'одежда': ['рубашка', 'брюки', 'куртка', 'свитер', 'футболка', 'платье', 'юбка'],
            'изделие': ['рубашка', 'брюки', 'куртка', 'свитер', 'футболка', 'платье', 'юбка'],
            'нижнее белье': ['трусы', 'майка', 'бюстгальтер'],
            'обувь': ['кроссовки', 'ботинки', 'туфли', 'сапоги', 'босоножки'],
        }
        
        # Извлекаем названия из price_lines
        price_labels = [item['label'].lower() for item in price_lines]
        
        # Для каждого общего термина в ценах ищем конкретный в описании
        fixed_lines = []
        for item in price_lines:
            label = item['label']
            label_lower = label.lower()
            
            # Проверяем, является ли это общим термином
            replacement = None
            for generic, concrete_options in generic_terms.items():
                if generic in label_lower:
                    # Ищем конкретные типы товаров в описании
                    for concrete in concrete_options:
                        # Проверяем, что:
                        # 1. Конкретный тип упоминается в описании
                        # 2. Этот конкретный тип ещё не используется в других ценах
                        if concrete in context_text and concrete not in price_labels:
                            replacement = label_lower.replace(generic, concrete)
                            break
                    if replacement:
                        break
            
            if replacement:
                fixed_lines.append({"label": replacement, "price": item['price']})
            else:
                fixed_lines.append(item)
        
        return fixed_lines
    
    async def _prepare_price_entries(self, product_data: dict, product_context: dict | str | None) -> list[dict]:
        """
        Готовит список цен по уникальным SKU для отображения в посте.
        Возвращает только если найдено несколько ценовых групп.
        
        Args:
            product_data: Данные о товаре
            product_context: Контекст товара (dict с title и description) или просто title (str) для обратной совместимости
        """
        entries = self._get_unique_sku_price_items(product_data)
        if len(entries) <= 1:
            return []
        
        # Обеспечиваем обратную совместимость: если передана строка, преобразуем в dict
        if isinstance(product_context, str):
            product_context = {'title': product_context, 'description': ''}
        elif not product_context:
            product_context = {'title': '', 'description': ''}

        if self._translation_supports_structured_tasks():
            if settings.DEBUG_MODE:
                print("[Scraper] Используется LLM-ветка для обработки цен")
            structured = await self._process_prices_with_llm(entries, product_context)
            if structured:
                return structured

        if settings.DEBUG_MODE:
            print("[Scraper] Используется fallback-ветка для обработки цен (без LLM)")
        return await self._prepare_price_entries_fallback(entries)

    async def _process_prices_with_llm(self, entries: list[dict], product_context: dict) -> list[dict]:
        """
        Использует translation LLM для перевода и сжатия списка цен.
        
        Args:
            entries: Список вариантов с ценами
            product_context: Контекст товара (title, description)
        """
        try:
            translated = await self._translate_price_entries_with_llm(entries, product_context)
            if not translated:
                return []
            summarized = await self._summarize_price_entries_with_llm(product_context, translated)
            return summarized
        except Exception as e:
            if settings.DEBUG_MODE:
                print(f"[Scraper] Ошибка обработки цен через LLM: {e}")
            return []

    async def _translate_price_entries_with_llm(self, entries: list[dict], product_context: dict) -> list[dict]:
        payload = json.dumps(entries, ensure_ascii=False, indent=2)
        
        # Извлекаем контекст
        title = product_context.get('title', '')
        description = product_context.get('description', '')
        
        system_prompt = (
            "Ты профессиональный переводчик и эксперт по товарным каталогам маркетплейсов. "
            "Переводи товарные позиции на русский язык максимально кратко и точно, "
            "используя контекст описания товара для определения КОНКРЕТНЫХ типов товара."
        )
        
        # Формируем контекст товара для промпта
        context_lines = []
        if title:
            context_lines.append(f"Название товара: {title}")
        if description:
            context_lines.append(f"Описание товара: {description}")
        
        context_hint = "\n".join(context_lines) + "\n\n" if context_lines else ""
        
        user_prompt = (
            f"{context_hint}"
            "Ниже передан JSON-массив позиций с оригинальными названиями и ценами в юанях.\n"
            "Переведи каждое название на русский язык ЧЕСТНО и ПОЛНОСТЬЮ, сохраняя всю информацию.\n"
            "Верни JSON-массив вида: [{\"label\": \"переведённое название\", \"price\": число}].\n\n"
            "⚠️ КРИТИЧЕСКИ ВАЖНО - ЧЕСТНЫЙ ПОЛНЫЙ ПЕРЕВОД:\n\n"
            "1. СОХРАНЯЙ структуру: [ТИП ТОВАРА], [описание цвета/принта]\n"
            "   - 'XS, 长袖套装, MARBLE MUSHROOM PRINT' → 'майка, принт мраморный грибной'\n"
            "   - 'M, 短裤, BLACK' → 'шорты, чёрные'\n"
            "   - 'L, 长裤, RED PRINT' → 'брюки, принт красный'\n\n"
            "2. ОПРЕДЕЛИ ТИП товара из китайских слов:\n"
            "   - '长袖' / '长袖套装' → 'майка' или 'футболка' (длинный рукав)\n"
            "   - '短裤' → 'шорты' (короткие штаны)\n"
            "   - '长裤' → 'брюки' (длинные штаны)\n"
            "   - '衬衫' → 'рубашка'\n"
            "   - '裤子' → 'брюки'\n\n"
            "3. ПЕРЕВОДИ принты/цвета, но ставь ИХ ПОСЛЕ типа товара:\n"
            "   - 'MARBLE MUSHROOM PRINT, 甜奶油红蘑菇, 长袖' → 'майка, принт мраморный грибной'\n"
            "   - 'CARAMEL GINGERBREAD PRINT, 焦糖小人儿姜饼干, 短裤' → 'шорты, принт карамельный имбирный пряник'\n"
            "   - 'BLACK, 黑色, 长裤' → 'брюки, чёрные'\n\n"
            "4. ИСПОЛЬЗУЙ контекст описания для УТОЧНЕНИЯ типа:\n"
            "   - Если в описании: 'Комплект: майка, шорты, брюки'\n"
            "   - И в варианте: '长袖' → переводи как 'майка' (из контекста)\n"
            "   - И в варианте: '短裤' → переводи как 'шорты' (из контекста)\n\n"
            "5. НЕ УДАЛЯЙ информацию:\n"
            "   - Переводи ВСЁ: размеры, принты, цвета (суммаризация будет позже)\n"
            "   - Формат: 'ТИП ТОВАРА, атрибуты'\n"
            "   - Пример: 'майка, принт мраморный грибной' (НЕ просто 'майка')\n\n"
            "ПРИМЕРЫ:\n\n"
            "Вход: {\"name\": \"XS, 长袖套装, MARBLE MUSHROOM PRINT 甜奶油红蘑菇\", \"price\": 158}\n"
            "Выход: {\"label\": \"майка, принт мраморный грибной\", \"price\": 158}\n\n"
            "Вход: {\"name\": \"M, 短裤, WASHED ONYX SKI PRINT 水洗黑\", \"price\": 118}\n"
            "Выход: {\"label\": \"шорты, принт стираный чёрный лыжный\", \"price\": 118}\n\n"
            "Вход: {\"name\": \"L, 长裤, CARAMEL GINGERBREAD\", \"price\": 188}\n"
            "Выход: {\"label\": \"брюки, принт карамельный имбирный пряник\", \"price\": 188}\n\n"
            "Цены НЕ изменяй. Переводи ЧЕСТНО и ПОЛНОСТЬЮ.\n\n"
            f"Исходный JSON:\n{payload}"
        )
        token_limit = max(2000, len(entries) * 80)
        last_error = None

        for attempt in range(2):
            try:
                response_text = await self._call_translation_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    token_limit=token_limit,
                    temperature=0.0,
                )
                data = self._parse_json_response(response_text)
                normalized = []
                for item in data if isinstance(data, list) else []:
                    label = str(item.get('label') or item.get('name') or "").strip()
                    price = item.get('price')
                    try:
                        price_value = float(price)
                    except (TypeError, ValueError):
                        continue
                    if label:
                        normalized.append({"label": label, "price": price_value})
                if normalized:
                    return normalized
                last_error = ValueError("LLM вернул пустой список после перевода цен.")
            except json.JSONDecodeError as exc:
                last_error = exc
                token_limit = int(token_limit * 1.5) + 500
                continue

        if last_error:
            raise last_error
        return []

    async def _summarize_price_entries_with_llm(self, product_context: dict, items: list[dict]) -> list[dict]:
        if not items:
            return []
        
        payload = json.dumps(items, ensure_ascii=False, indent=2)
        
        # Извлекаем контекст
        title = product_context.get('title', '')
        description = product_context.get('description', '')
        
        system_prompt = (
            "Ты эксперт по товарным каталогам маркетплейсов. Создавай краткие и точные описания цен, "
            "как на Wildberries или Ozon. Обобщай вариации, если различия несущественны (размер, цвет, принт). "
            "Если различия влияют на тип товара или комплектность - оставляй отдельно."
        )
        
        # Формируем контекст
        context_lines = []
        if title:
            context_lines.append(f"Название товара: {title}")
        if description:
            context_lines.append(f"Описание: {description}")
        
        context_hint = "\n".join(context_lines) + "\n\n" if context_lines else ""
        
        user_prompt = (
            f"{context_hint}"
            "Ниже приведён JSON-массив позиций с переводами и ценами:\n"
            f"{payload}\n\n"
            "⚠️ КРИТИЧЕСКИ ВАЖНО - ГРУППИРОВКА ПО ТИПУ ТОВАРА, НЕ ПО ПРИНТУ!\n\n"
            "ПРАВИЛА СУММАРИЗАЦИИ (стиль маркетплейса Wildberries/Ozon):\n\n"
            "1. ОПРЕДЕЛИ ТИП ТОВАРА из названия (майка, футболка, шорты, брюки, штаны, рубашка и т.д.)\n"
            "   - 'длинная футболка, принт X' → ТИП = 'футболка' или 'майка'\n"
            "   - 'короткие штаны, цвет Y' → ТИП = 'шорты'\n"
            "   - 'длинные штаны, принт Z' → ТИП = 'брюки'\n"
            "   - 'рубашка с пайетками' → ТИП = 'рубашка'\n\n"
            "2. ГРУППИРУЙ по ТИПУ товара + ЦЕНЕ (игнорируй принты, цвета, размеры!):\n"
            "   - Все 'футболка [любой принт]' с ценой 158 ¥ → 'майка с принтом в ассортименте'\n"
            "   - Все 'короткие штаны [любой цвет]' с ценой 118 ¥ → 'шорты в ассортименте'\n"
            "   - НЕ группируй по принтам! 'марморный принт' - НЕ тип товара!\n\n"
            "3. НОРМАЛИЗУЙ названия типов товара:\n"
            "   - 'длинная футболка' / 'длинный рукав' → 'майка'\n"
            "   - 'короткие штаны' / 'короткие брюки' → 'шорты'\n"
            "   - 'длинные штаны' / 'длинные брюки' → 'брюки'\n"
            "   - 'футболка' / 'топ' → 'футболка'\n\n"
            "4. ФОРМАТ описания (2-4 слова):\n"
            "   - Если разные принты: 'майка с принтом в ассортименте'\n"
            "   - Если один цвет: 'шорты чёрные'\n"
            "   - Если один тип без вариаций: 'брюки'\n\n"
            "⚠️⚠️⚠️ ПРИМЕРЫ С ПРИНТАМИ (как в вашем случае) ⚠️⚠️⚠️\n\n"
            "Пример 1 - ПРАВИЛЬНАЯ группировка комплекта с принтами SKIMS:\n"
            "Вход: [\n"
            "  {\"label\": \"Принт MARBLE MUSHROOM, цвет нежно-розовый с красным грибком, длинная футболка\", \"price\": 158},\n"
            "  {\"label\": \"Принт CARAMEL GINGERBREAD, цвет карамельный имбирный пряник, длинная футболка\", \"price\": 158},\n"
            "  {\"label\": \"Принт WASHED ONYX SKI, цвет вымытый чёрный, длинная футболка\", \"price\": 158},\n"
            "  {\"label\": \"Принт MARBLE MUSHROOM, цвет нежно-розовый с красным грибком, короткие штаны\", \"price\": 118},\n"
            "  {\"label\": \"Принт WASHED ONYX SKI, цвет вымытый чёрный, короткие штаны\", \"price\": 118},\n"
            "  {\"label\": \"Принт CARAMEL GINGERBREAD, цвет карамельный, короткие штаны\", \"price\": 118},\n"
            "  {\"label\": \"Принт MARBLE MUSHROOM, цвет нежно-розовый, длинные штаны\", \"price\": 188},\n"
            "  {\"label\": \"Принт WASHED ONYX SKI, длинные штаны\", \"price\": 188}\n"
            "]\n"
            "Выход: [\n"
            "  {\"label\": \"майка с принтом в ассортименте\", \"price\": 158},\n"
            "  {\"label\": \"шорты с принтом в ассортименте\", \"price\": 118},\n"
            "  {\"label\": \"брюки с принтом в ассортименте\", \"price\": 188}\n"
            "]\n"
            "Логика: Группировка по ТИПУ товара (майка, шорты, брюки), НЕ по принту!\n\n"
            "Пример 2 - НЕПРАВИЛЬНАЯ группировка (так делать НЕЛЬЗЯ):\n"
            "Выход НЕПРАВИЛЬНЫЙ: [\n"
            "  {\"label\": \"марморный грибной принт\", \"price\": 158},  ← ОШИБКА! Принт - не тип товара!\n"
            "  {\"label\": \"карамельный имбирный печенье\", \"price\": 158},  ← ОШИБКА!\n"
            "  {\"label\": \"принт ски оникса в ассортименте\", \"price\": 118}  ← ОШИБКА!\n"
            "]\n\n"
            "Пример 3 - Рубашка и брюки:\n"
            "Вход: [\n"
            "  {\"label\": \"XS брюки чёрные\", \"price\": 128},\n"
            "  {\"label\": \"S брюки чёрные\", \"price\": 128},\n"
            "  {\"label\": \"XS рубашка с пайетками белая\", \"price\": 148},\n"
            "  {\"label\": \"S рубашка с пайетками белая\", \"price\": 148}\n"
            "]\n"
            "Выход: [\n"
            "  {\"label\": \"брюки\", \"price\": 128},\n"
            "  {\"label\": \"рубашка с пайетками\", \"price\": 148}\n"
            "]\n\n"
            "АЛГОРИТМ:\n"
            "Шаг 1: Для каждого элемента извлеки ТИП товара (майка/шорты/брюки/рубашка)\n"
            "Шаг 2: Сгруппируй по (ТИП товара, ЦЕНА)\n"
            "Шаг 3: Для каждой группы создай краткое описание БЕЗ принтов/цветов/размеров\n"
            "Шаг 4: Если в группе >1 вариант с разными принтами/цветами → добавь 'в ассортименте'\n\n"
            "Верни JSON-массив [{\"label\": \"описание\", \"price\": число}]. "
            "Описание: 2-4 слова, ТИП товара + (опционально) 'с принтом в ассортименте'. "
            "Группируй ТОЛЬКО по типу товара и цене!"
        )
        token_limit = max(2000, len(items) * 40)
        last_error = None

        for attempt in range(2):
            try:
                response_text = await self._call_translation_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    token_limit=token_limit,
                    temperature=0.0,
                )
                data = self._parse_json_response(response_text)
                result = []
                seen = set()
                for item in data if isinstance(data, list) else []:
                    label = str(item.get('label') or "").strip()
                    price = item.get('price')
                    try:
                        price_value = float(price)
                    except (TypeError, ValueError):
                        continue
                    if not label:
                        continue
                    key = (label, price_value)
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append({"label": label, "price": price_value})

                if result:
                    price_groups: OrderedDict[float, list[str]] = OrderedDict()
                    for entry in sorted(result, key=lambda e: e['price']):
                        price_groups.setdefault(entry['price'], []).append(entry['label'])

                    merged: list[dict] = []
                    for price_value, labels in price_groups.items():
                        if not labels:
                            continue
                        merged_label = self._merge_price_labels(labels)
                        if isinstance(merged_label, list):
                            for lbl in merged_label:
                                cleaned = (lbl or "").strip()
                                if cleaned:
                                    merged.append({"label": cleaned, "price": price_value})
                        else:
                            cleaned = (merged_label or "").strip()
                            if cleaned:
                                merged.append({"label": cleaned, "price": price_value})

                    return merged
                last_error = ValueError("LLM вернул пустой список после суммаризации цен.")
            except json.JSONDecodeError as exc:
                last_error = exc
                token_limit = int(token_limit * 1.5) + 500
                continue

        if last_error:
            raise last_error
        return []

    async def _prepare_price_entries_fallback(self, entries: list[dict]) -> list[dict]:
        grouped: OrderedDict[float, list[str]] = OrderedDict()
        for entry in entries:
            grouped.setdefault(entry['price'], []).append(entry['name'])

        if len(grouped) <= 1:
            return []

        all_names = [name for names in grouped.values() for name in names]
        translated_names = await self._translate_variant_names(all_names)

        idx = 0
        summarized_lines = []
        for price_value, names in grouped.items():
            translated_group = []
            for _ in names:
                translated = translated_names[idx] if idx < len(translated_names) else _
                idx += 1
                translated_group.append(translated.strip() or _)
            summaries = self._summarize_price_group(translated_group)
            for label in summaries:
                cleaned_label = (label or "").strip()
                # Фильтруем маркеры невалидных товаров
                if cleaned_label and "__INVALID__" not in cleaned_label.upper():
                    summarized_lines.append({"label": cleaned_label, "price": price_value})

        # Фильтруем невалидные варианты: если для одной цены есть несколько вариантов,
        # и один из них выглядит как мусор - удаляем мусорный
        price_groups: dict[float, list[dict]] = {}
        for item in summarized_lines:
            price = item['price']
            if price not in price_groups:
                price_groups[price] = []
            price_groups[price].append(item)
        
        filtered_lines = []
        for price, items in price_groups.items():
            if len(items) > 1:
                # Есть несколько вариантов с одинаковой ценой
                # Фильтруем подозрительные (очень короткие или содержащие мусорные слова)
                valid_items = []
                suspicious_keywords = ['товар', 'отправляется', 'доставка', 'без']
                
                for item in items:
                    label_lower = item['label'].lower()
                    # Проверяем, не является ли это мусором
                    is_suspicious = (
                        len(item['label']) < 5 or  # Слишком короткое название
                        sum(1 for kw in suspicious_keywords if kw in label_lower) >= 2  # Много мусорных слов
                    )
                    if not is_suspicious:
                        valid_items.append(item)
                
                # Если после фильтрации остались валидные - используем их, иначе - все
                filtered_lines.extend(valid_items if valid_items else items)
            else:
                # Один вариант с этой ценой - оставляем как есть
                filtered_lines.extend(items)

        unique = []
        seen = set()
        for item in filtered_lines:
            key = (item['label'], item['price'])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _get_unique_sku_price_items(self, product_data: dict) -> list[dict]:
        """
        Собирает уникальные комбинации (название варианта + цена).
        """
        items = []
        seen = set()
        for sku in product_data.get('skus', []) or []:
            price_str = sku.get('sale_price') or sku.get('origin_price')
            try:
                price_value = float(str(price_str).replace(',', '.'))
            except (TypeError, ValueError):
                continue

            name = self._normalize_sku_prop_name(sku.get('props_names') or '')
            if not name:
                continue

            key = (name.lower(), price_value)
            if key in seen:
                continue
            seen.add(key)
            items.append({'name': name, 'price': price_value})
        return items

    def _normalize_sku_prop_name(self, props_names: str) -> str:
        """
        Приводит props_names к удобочитаемому виду без ключей.
        """
        if not props_names:
            return ""

        parts = []
        for part in props_names.split(';'):
            part = part.strip()
            if not part:
                continue
            if ':' in part:
                _, value = part.split(':', 1)
            else:
                value = part
            value = value.strip()
            if value:
                parts.append(value)
        return ", ".join(parts) if parts else props_names.strip()

    async def _translate_variant_names(self, names: list[str]) -> list[str]:
        """
        Переводит список названий вариантов на русский язык.
        """
        if not names:
            return names

        if self.translation_supports_structured:
            payload = [{"id": idx, "label": name} for idx, name in enumerate(names)]
            token_limit = max(800, len(names) * 40)
            user_prompt = (
                "Ниже передан JSON-массив объектов с полями id и label. "
                "Переведи поле label на русский язык, сохранив тот же id. "
                "Верни массив в формате [{\"id\": 0, \"label\": \"перевод\"}]. "
                "Не добавляй новых элементов и не меняй порядок.\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            )
            for attempt in range(2):
                try:
                    response_text = await self._call_translation_json(
                        system_prompt="Ты профессиональный переводчик. Всегда отвечай JSON.",
                        user_prompt=user_prompt,
                        token_limit=token_limit,
                        temperature=0.0,
                    )
                    data = self._parse_json_response(response_text)
                    translated_map: dict[int, str] = {}
                    if isinstance(data, list):
                        for item in data:
                            try:
                                idx = int(item.get("id"))
                            except Exception:
                                continue
                            label = (item.get("label") or item.get("text") or "").strip()
                            if label:
                                translated_map[idx] = label
                    if len(translated_map) == len(names):
                        return [translated_map[idx] for idx in range(len(names))]
                except json.JSONDecodeError as exc:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] Ошибка группового перевода вариантов: {exc}")
                    token_limit = int(token_limit * 1.5) + 200
                    continue
                except Exception as exc:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] Ошибка группового перевода вариантов: {exc}")
                    break


        translator = getattr(self.translation_client, "translate_text", None)
        if not callable(translator):
            return names

        batch_text = "\n".join(names)
        translated_block = None
        try:
            translated_block = await translator(batch_text, target_language="ru")
        except Exception as exc:
            if settings.DEBUG_MODE:
                print(f"[Scraper] Ошибка группового перевода вариантов: {exc}")

        if translated_block:
            splitted = [line.strip() for line in translated_block.split("\n")]
            if len(splitted) == len(names):
                return [segment or original for segment, original in zip(splitted, names)]

        results = []
        for name in names:
            try:
                translated = await translator(name, target_language="ru")
            except Exception:
                translated = None
            results.append((translated or name).strip() or name)
        return results

    def _extract_product_type(self, name: str) -> str:
        """
        Извлекает тип товара из названия, убирая размеры, цвета, принты и другие описательные слова.
        Возвращает нормализованное название типа товара.
        
        Фокусируется на извлечении ТИПА одежды (майка, шорты, брюки), игнорируя принты и цвета.
        """
        if not name:
            return ""
        
        name_lower = name.lower()
        
        # Список "мусорных" фраз, которые НЕ являются типами товара
        garbage_phrases = [
            'товар отправляется',
            'товар отправляется без',
            'без фирменного лейбла',
            'без брендовой маркировки',
            'без бренда',
            'отправка без',
            'доставка',
            'в наличии',
            'под заказ',
            'предзаказ',
            'новинка',
            'распродажа',
            'скидка',
            'акция',
        ]
        
        # Проверяем на мусорные фразы
        for garbage in garbage_phrases:
            if garbage in name_lower:
                # Если название содержит мусорную фразу и не содержит явного типа товара - возвращаем маркер
                # Проверим ниже, есть ли явный тип
                has_product_type = False
                for markers in [
                    ['майка', 'футболка', 'топ', 'блуза'],
                    ['шорты', 'брюки', 'штаны'],
                    ['рубашка', 'сорочка'],
                    ['куртка', 'пиджак'],
                    ['свитер', 'джемпер', 'кофта', 'худи'],
                    ['платье', 'юбка'],
                ]:
                    if any(marker in name_lower for marker in markers):
                        has_product_type = True
                        break
                
                if not has_product_type:
                    # Мусорная фраза без явного типа товара - помечаем как невалидный
                    return "__INVALID__"
        
        # Словарь маркеров типов товара (важнее всего!)
        type_markers = {
            'майка': ['майка', 'футболка', 'длинная футболка', 'длинный рукав', 'топ', 'блуза'],
            'шорты': ['шорты', 'короткие штаны', 'короткие брюки'],
            'брюки': ['брюки', 'длинные штаны', 'длинные брюки', 'штаны'],
            'рубашка': ['рубашка', 'сорочка'],
            'куртка': ['куртка', 'пиджак', 'жакет'],
            'свитер': ['свитер', 'джемпер', 'кофта', 'худи', 'толстовка'],
            'платье': ['платье'],
            'юбка': ['юбка'],
        }
        
        # Ищем тип товара в названии
        for product_type, markers in type_markers.items():
            for marker in markers:
                if marker in name_lower:
                    return product_type
        
        # Если не нашли явного маркера типа товара - используем fallback-логику
        # Но помним, что результат должен быть валидирован в конце
        # Список размеров для удаления (регистронезависимо)
        size_patterns = [
            r'\b(xs|s|m|l|xl|xxl|xxxl)\b',  # Буквенные размеры
            r'\b(\d{1,3})\b',  # Числовые размеры (35, 36, 37, ...)
            r'\b(one\s*size|free\s*size|универсальный)\b',  # Универсальный размер
        ]
        
        # Убираем размеры из названия
        cleaned = name_lower
        for pattern in size_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Убираем слова, связанные с принтами и цветами
        print_keywords = ['принт', 'print', 'рисунок', 'узор', 'pattern']
        for keyword in print_keywords:
            # Убираем фразы типа "принт мраморный", "print marble"
            cleaned = re.sub(rf'\b{keyword}\b[^,\.]*', '', cleaned, flags=re.IGNORECASE)
        
        # Убираем запятые и лишние пробелы
        cleaned = re.sub(r'^[,\s]+', '', cleaned)
        cleaned = re.sub(r'[,\s]+$', '', cleaned)
        cleaned = re.sub(r'\s*,\s*', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Убираем цвета
        cleaned = self._remove_color_words(cleaned)
        
        # Убираем стоп-слова
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё]+", cleaned.lower())
        filtered = [
            token for token in tokens
            if token not in self.GENERIC_STOPWORDS
            and len(token) > 2
        ]
        
        # Возвращаем первые значимые слова как тип товара
        if filtered:
            candidate = " ".join(filtered[:2])
            
            # Проверяем, не является ли это просто цветом/принтом без типа товара
            # Список прилагательных, которые обычно описывают цвет/принт, но не тип товара
            color_adjectives = [
                'карамельный', 'мраморный', 'имбирный', 'стираный', 'вымытый',
                'чёрный', 'белый', 'красный', 'синий', 'зелёный', 'жёлтый',
                'коричневый', 'серый', 'розовый', 'фиолетовый', 'оранжевый',
                'нежный', 'яркий', 'тёмный', 'светлый', 'пастельный',
                'печенье', 'пряник', 'грибной', 'лыжный', 'оникс'
            ]
            
            # Если результат состоит только из цветовых прилагательных - это не тип товара
            candidate_words = candidate.lower().split()
            all_colors = all(word in color_adjectives for word in candidate_words)
            
            if all_colors:
                # Это цвет/принт, а не тип товара - помечаем как невалидный
                return "__INVALID__"
            
            return candidate
        
        # Если ничего не осталось после фильтрации - проверяем исходное название
        # Если оно содержит только цвета/принты без типа - невалидный
        final_candidate = cleaned.strip() or name.strip()
        
        # Проверяем, что это не просто цвет/принт
        if final_candidate and len(final_candidate) > 0:
            # Если название слишком короткое или содержит только прилагательные - невалидно
            words = final_candidate.lower().split()
            if len(words) <= 2 and all(
                any(color_word in word for color_word in ['карамель', 'мрамор', 'имбир', 'принт', 'print'])
                for word in words
            ):
                return "__INVALID__"
        
        # ФИНАЛЬНАЯ ВАЛИДАЦИЯ: проверяем, является ли результат известным типом товара
        # Список всех известных типов товара
        known_types = {
            'майка', 'футболка', 'топ', 'блуза',
            'шорты', 'брюки', 'штаны',
            'рубашка', 'сорочка',
            'куртка', 'пиджак', 'жакет',
            'свитер', 'джемпер', 'кофта', 'худи', 'толстовка',
            'платье', 'юбка',
            'носки', 'колготки', 'гольфы',
            'трусы', 'белье',
            'пижама', 'халат',
            'комбинезон',
        }
        
        # Если результат НЕ содержит ни одного известного типа - это не товар
        if final_candidate:
            final_lower = final_candidate.lower()
            has_known_type = any(known_type in final_lower for known_type in known_types)
            if not has_known_type:
                # Результат не содержит известных типов товара - это мусор (цвет/принт)
                return "__INVALID__"
        
        return final_candidate
    
    def _summarize_price_group(self, names: list[str]) -> list[str]:
        """
        Сокращает список названий позиций, чтобы избежать повторов в посте.
        
        Логика:
        1. Удаляет размеры из всех названий
        2. Группирует по типу товара
        3. Если все варианты одного типа (только размеры/цвета отличаются) → возвращает один тип товара
        4. Если варианты разных типов → перечисляет типы, для повторяющихся типов → "в ассортименте"
        """
        if not names:
            return []
        
        # Шаг 1: Удаляем размеры и цвета из всех названий, получаем тип товара
        type_to_originals: dict[str, list[str]] = {}
        for name in names:
            name = name.strip()
            if not name:
                continue
            
            product_type = self._extract_product_type(name)
            
            # Пропускаем невалидные типы
            if product_type == "__INVALID__":
                continue
            
            if not product_type:
                # Если не удалось определить тип, используем оригинальное название
                product_type = name
            
            if product_type not in type_to_originals:
                type_to_originals[product_type] = []
            type_to_originals[product_type].append(name)
        
        if not type_to_originals:
            return []
        
        # Шаг 2: Если все варианты одного типа - возвращаем один элемент
        if len(type_to_originals) == 1:
            product_type = list(type_to_originals.keys())[0]
            originals = type_to_originals[product_type]
            
            # Если это действительно разные варианты (а не просто дубликаты)
            unique_originals = list(dict.fromkeys(originals))
            if len(unique_originals) > 1:
                # Проверяем, отличаются ли они только размерами
                # Если да - возвращаем просто тип товара
                return [product_type]
            else:
                # Один вариант - возвращаем как есть
                return unique_originals
        
        # Шаг 3: Несколько типов товаров - обрабатываем каждый
        result = []
        for product_type, originals in type_to_originals.items():
            unique_originals = list(dict.fromkeys(originals))
            
            if len(unique_originals) == 1:
                # Один вариант этого типа - возвращаем тип товара
                result.append(product_type)
            else:
                # Несколько вариантов одного типа (разные размеры/цвета)
                # Проверяем, отличаются ли они только размерами
                # Если варианты отличаются только размерами - указываем тип товара
                # Если отличаются цветами/другими характеристиками - указываем "в ассортименте"
                
                # Простая эвристика: если все оригинальные названия содержат тип товара и отличаются только префиксом
                all_contain_type = all(product_type in orig.lower() for orig in unique_originals)
                if all_contain_type:
                    # Все варианты содержат тип товара - скорее всего отличаются только размерами
                    result.append(product_type)
                else:
                    # Варианты отличаются не только размерами
                    result.append(f"{product_type} в ассортименте")
        
        # Убираем дубликаты, сохраняя порядок
        unique_result = []
        seen = set()
        for item in result:
            item_lower = item.lower()
            if item_lower not in seen:
                seen.add(item_lower)
                unique_result.append(item)
        
        return unique_result

    def _extract_keywords(self, names: list[str]) -> list[str]:
        counter = Counter()
        for name in names:
            tokens = re.findall(r"[A-Za-zА-Яа-яЁё]+", name.lower())
            filtered = [
                token for token in tokens
                if token not in self.COLOR_KEYWORDS
                and token not in self.GENERIC_STOPWORDS
                and len(token) > 2
            ]
            counter.update(filtered)

        keywords = []
        for token, _ in counter.most_common():
            if token not in keywords:
                keywords.append(token)
            if len(keywords) >= 5:
                break
        return keywords

    def _extract_shared_descriptor(self, names: list[str]) -> str:
        normalized = [name.lower() for name in names]
        if normalized and all(self._contains_keyword(name, self.BATTERY_KEYWORDS) for name in normalized):
            return "на батарейках"
        if normalized and all(self._contains_keyword(name, self.CHARGE_KEYWORDS) for name in normalized):
            return "перезаряжаемые"
        return ""

    @staticmethod
    def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
        text = text.lower()
        return any(keyword in text for keyword in keywords)

    def _is_apparel_product(self, translated_title: str | None, product_data: dict) -> bool:
        text_parts = [
            translated_title or "",
            product_data.get('title') or "",
            product_data.get('product_props') or "",
            " ".join(product_data.get('category_path') or []),
        ]
        text = " ".join(text_parts).lower()
        apparel_markers = (
            "плать", "юбк", "джинс", "брюк", "рубаш", "футболк", "толстов",
            "худи", "костюм", "жилет", "куртк", "пальт", "шорт", "леггинс",
            "обув", "ботин", "кроссов", "туфл", "кеды", "носк", "бель",
            "колгот", "пижам", "комбинез", "скинни", "sneaker", "coat", "hoodie",
            "靴", "衣", "裙", "裤", "衫"
        )
        return any(marker in text for marker in apparel_markers)

    @staticmethod
    def _common_prefix(lhs: str, rhs: str) -> str:
        limit = min(len(lhs), len(rhs))
        idx = 0
        while idx < limit and lhs[idx] == rhs[idx]:
            idx += 1
        return lhs[:idx]

    def _remove_color_words(self, text: str) -> str:
        if not text:
            return ""
        cleaned = self.COLOR_REGEX.sub("", text)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = cleaned.replace(" ,", ",").replace(" /", "/")
        return cleaned.strip(" ,./-")

    def _merge_price_labels(self, labels: list[str]) -> str | list[str]:
        if not labels:
            return []
        if len(labels) == 1:
            return labels[0]

        prefix = labels[0]
        for lbl in labels[1:]:
            prefix = self._common_prefix(prefix, lbl)
            if not prefix:
                break

        prefix = prefix.rstrip(" -—:,()/").strip()
        if prefix and len(prefix) >= 12:
            suffixes = []
            for lbl in labels:
                suffix = lbl[len(prefix):].lstrip(" -—:,()").strip()
                suffix = self._remove_color_words(suffix)
                if not suffix:
                    suffix = "вариант"
                suffixes.append(suffix)
            unique_suffixes = []
            seen = set()
            for suf in suffixes:
                normalized = suf.lower()
                if normalized not in seen:
                    seen.add(normalized)
                    unique_suffixes.append(suf)
            if unique_suffixes:
                joined = ", ".join(unique_suffixes[:6])
                if len(unique_suffixes) > 6:
                    joined += ", и др."
                return f"{prefix} (в ассортименте: {joined})"
            return prefix

        # Нет общего префикса — оставляем элементы отдельно
        return labels

    def _translation_supports_structured_tasks(self) -> bool:
        """
        Проверяет, поддерживает ли активный переводческий провайдер
        сложные JSON-задачи (перевод и агрегация цен через LLM).

        Для ProxyAPI мы сознательно отключаем этот режим, чтобы:
        - избежать цепочек медленных запросов при работе с моделями gpt-5.x;
        - использовать ProxyAPI только как быстрый переводчик через chat.completions.
        """
        try:
            from src.api.proxyapi_client import ProxyAPIClient  # локальный импорт, чтобы избежать циклов

            if isinstance(self.translation_client, ProxyAPIClient):
                return False
        except Exception:
            # если по какой-то причине импорт не удался, не ломаемся
            pass

        return hasattr(self.translation_client, "generate_json_response")

    def _parse_json_response(self, text: str):
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        return json.loads(cleaned)

    async def _call_translation_json(
        self,
        system_prompt: str,
        user_prompt: str,
        token_limit: int = 1500,
        temperature: float = 0.0,
    ) -> str:
        generator = getattr(self.translation_client, "generate_json_response", None)
        if not callable(generator):
            raise RuntimeError("Активный переводческий провайдер не поддерживает JSON-ответы.")

        kwargs = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }

        try:
            sig = inspect.signature(generator)
            if "max_output_tokens" in sig.parameters:
                kwargs["max_output_tokens"] = token_limit
            elif "max_tokens" in sig.parameters:
                kwargs["max_tokens"] = token_limit
            if "temperature" in sig.parameters:
                kwargs["temperature"] = temperature
        except (TypeError, ValueError):
            kwargs["max_tokens"] = token_limit

        return await generator(**kwargs)

    async def _translate_text_generic(self, text: str, target_language: str = "ru") -> str:
        """
        Универсальный переводчик: использует выбранный translation_client.
        """
        if not text:
            return text

        translator = getattr(self.translation_client, "translate_text", None)
        if callable(translator):
            try:
                translated = await translator(text, target_language=target_language)
                if translated:
                    return translated
            except Exception as e:
                if settings.DEBUG_MODE:
                    print(f"[Scraper] Ошибка перевода: {e}")
        return text
    
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

    def _ensure_lowercase_bullet(self, text: str) -> str:
        """
        Гарантирует, что первый алфавитный символ в пункте списка — строчный.
        """
        if not text:
            return text
        chars = list(text)
        for idx, ch in enumerate(chars):
            if ch.isalpha():
                chars[idx] = ch.lower()
                return "".join(chars)
        return text

    def _render_price_section(
        self,
        price_lines: list[dict],
        fallback_price: str,
        currency: str,
        exchange_rate: float | None
    ) -> str:
        """
        Формирует текстовую секцию с ценами.
        """
        if price_lines:
            unique_prices = {entry['price'] for entry in price_lines}
            if len(unique_prices) == 1:
                price_value = unique_prices.pop()
                amount = self._format_price_amount(price_value, currency, exchange_rate)
                return f"<i>💰 <b>Цена:</b> {amount}</i>"

            lines = ["<i>💰 <b>Цены:</b></i>"]
            for entry in price_lines:
                amount = self._format_price_amount(entry['price'], currency, exchange_rate)
                label = self._ensure_lowercase_bullet(entry['label'])
                lines.append(f"<i>  • {label} - {amount}</i>")
            return "\n".join(lines)

        amount = self._format_price_value_string(fallback_price, currency, exchange_rate)
        if not amount:
            return ""
        return f"<i>💰 <b>Цена:</b> {amount}</i>"

    def _format_price_amount(self, price_value: float, currency: str, exchange_rate: float | None) -> str:
        """
        Форматирует числовое значение цены с учётом валюты.
        """
        try:
            numeric = float(price_value)
        except (TypeError, ValueError):
            numeric = None

        if currency == "rub" and exchange_rate and numeric is not None:
            rub_price = numeric * float(exchange_rate)
            rub_price_rounded = round(rub_price / 10) * 10
            return f"{int(rub_price_rounded)} ₽ + доставка"

        if numeric is not None:
            return f"{self._format_number(numeric)} ¥ + доставка"

        return "N/A"

    @staticmethod
    def _format_number(value: float) -> str:
        """
        Убирает лишние нули у числовых значений.
        """
        if float(value).is_integer():
            return f"{int(value)}"
        return f"{value:.2f}".rstrip('0').rstrip('.')

    def _format_price_value_string(
        self,
        price_value: str,
        currency: str,
        exchange_rate: float | None
    ) -> str:
        """
        Форматирует цену, если она доступна только в текстовом виде.
        """
        if not price_value:
            return ""
        try:
            numeric = float(str(price_value).replace(',', '.'))
            return self._format_price_amount(numeric, currency, exchange_rate)
        except (ValueError, TypeError):
            suffix = "₽" if currency == "rub" and exchange_rate else "¥"
            return f"{price_value} {suffix} + доставка"
    
    def _build_post_text(
        self, 
        llm_content: dict, 
        product_data: dict, 
        signature: str = None,
        currency: str = "cny",
        exchange_rate: float = None,
        price_lines: list | None = None
    ) -> str:
        """
        Формирует финальный текст поста из структурированных данных LLM и данных API.
        Использует HTML разметку для Telegram.

        Args:
            llm_content (dict): Структурированный контент от YandexGPT
            product_data (dict): Данные о товаре от TMAPI
            signature (str, optional): Подпись пользователя для поста
            currency (str): Валюта пользователя (cny или rub)
            exchange_rate (float, optional): Курс обмена CNY в RUB

        Returns:
            str: Отформатированный текст поста в HTML
        """
        # Используем подпись пользователя или значение по умолчанию
        user_signature = signature or settings.DEFAULT_SIGNATURE
        # Извлекаем данные из LLM ответа
        title = llm_content.get('title', 'Товар')
        description = llm_content.get('description', '')
        main_characteristics = llm_content.get('main_characteristics', {})
        additional_info = llm_content.get('additional_info', {})
        hashtags = llm_content.get('hashtags', [])
        emoji = llm_content.get('emoji', '')
        
        # Извлекаем цену (первично из skus), далее — надёжные фолбэки
        price = self._get_max_price_from_skus(product_data)
        if not price:
            price = str((product_data.get('price_info') or {}).get('price') or '').strip()
        if not price:
            price = str(product_data.get('price') or '').strip()
        if not price:
            price = str((product_data.get('pdd_minimal') or {}).get('price') or '').strip()
        
        # Санитация названия/описания от выдуманных фасонов и годов
        try:
            src_text = ((product_data.get('details') or '') + ' ' + (product_data.get('title') or '')).lower()
            def _neutralize_underwear(text: str) -> str:
                t = text
                # Если в исходном тексте нет "бокс", но есть "трусы" — заменяем "боксёры" на "трусы"
                if 'трусы' in src_text and 'бокс' not in src_text:
                    t = t.replace('трусы-боксёры', 'трусы')
                    t = t.replace('боксёры', 'трусы')
                return t
            def _remove_years(text: str) -> str:
                import re
                return re.sub(r"\b(20\d{2})\b", "", text).replace('  ', ' ').strip()
            title = _remove_years(_neutralize_underwear(title))
            description = _remove_years(_neutralize_underwear(description))
        except Exception:
            pass

        if settings.DEBUG_MODE:
            price_info = product_data.get('price_info', {})
            print(f"[Scraper] Итоговая цена: {price}")
            print(f"[Scraper] Цена из price_info: {price_info.get('price', 'N/A')}")
            if 'origin_price' in price_info:
                print(f"[Scraper] Origin price: {price_info.get('origin_price')}")
        
        product_url = product_data.get('product_url', '')
        
        # Начинаем формировать пост
        post_parts = []
        
        # Заголовок с эмодзи (жирным курсивом)
        title_line = f"{emoji} " if emoji else ""
        title_line += f"<i><b>{title}</b></i>"
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
                        # После маркера слово должно начинаться со строчной буквы
                        formatted_item = str(item).strip()
                        if formatted_item:
                            formatted_item = self._ensure_lowercase_bullet(formatted_item)
                        post_parts.append(f"<i>  • {formatted_item}</i>")
                    post_parts.append("")
                else:
                    # Если значение - строка
                    post_parts.append(f"<i><b>{key}:</b> {value}</i>")
        
        # Для Pinduoduo (и схожих): извлечём важные характеристики из переведённого описания
        try:
            platform = product_data.get('_platform')
            if platform == 'pinduoduo':
                import re
                desc_text = (product_data.get('details') or '')
                if desc_text:
                    extracted: dict = {}
                    m = re.search(r"(?i)Материал[:：]\s*([^\n]+)", desc_text)
                    if m:
                        extracted.setdefault('Материал', m.group(1).strip())
                    m = re.search(r"(?i)Подкладка[:：]\s*([^\n]+)", desc_text)
                    if m:
                        extracted.setdefault('Подкладка', m.group(1).strip())
                    m = re.search(r"(?i)(Тип застёжки|Застёжка)[:：]\s*([^\n]+)", desc_text)
                    if m:
                        extracted.setdefault('Тип застёжки', m.group(2).strip())
                    # Сливаем в main_characteristics, не перезаписывая существующие
                    for k, v in extracted.items():
                        if not v:
                            continue
                        if k not in main_characteristics or not str(main_characteristics.get(k) or '').strip():
                            main_characteristics[k] = v
        except Exception:
            pass

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
        
        # Цена с учётом пользовательской валюты
        currency_lower = (currency or "cny").lower()
        
        # Проверяем, что exchange_rate не None и не 0
        has_exchange_rate = exchange_rate is not None and float(exchange_rate) > 0
        
        price_block = self._render_price_section(
            price_lines=price_lines or [],
            fallback_price=price,
            currency=currency_lower,
            exchange_rate=exchange_rate if has_exchange_rate else None
        )
        if price_block:
            post_parts.append(price_block)
            post_parts.append("")
        
        # Призыв к действию (курсивом) с подписью пользователя
        contact = user_signature.strip() if user_signature.strip() else settings.DEFAULT_SIGNATURE
        post_parts.append(f"<i>📝 Для заказа пишите {contact} или в комментариях 🛍️</i>")
        post_parts.append("")
        
        # Хэштеги (курсивом)
        # Очищаем хэштеги от пробелов (программная проверка на случай, если LLM добавил пробелы)
        # Удаляем все пробелы из хэштегов, включая пробелы в начале и конце
        if hashtags:
            cleaned_hashtags = [tag.strip().replace(" ", "") for tag in hashtags if tag and tag.strip()]
            hashtag_text = " ".join([f"#{tag}" for tag in cleaned_hashtags if tag])
            if hashtag_text:  # Добавляем только если есть хотя бы один хэштег
                post_parts.append(f"<i>{hashtag_text}</i>")
                post_parts.append("")
        
        # Ссылка на товар
        if product_url:
            post_parts.append(f'<a href="{product_url}">Ссылка</a>')
        
        return "\n".join(post_parts)
