import asyncio
import inspect
import json
import logging
import re
from collections import Counter, OrderedDict, defaultdict

from src.api.tmapi import TmapiClient
from src.api.llm_provider import get_llm_client, get_translation_client, get_postprocess_client, get_hashtags_client
from src.api.exchange_rate import ExchangeRateClient
from src.api.proxyapi_client import ProxyAPIClient
from src.api.openai_client import OpenAIClient
from src.core.config import settings
from src.utils.url_parser import URLParser, Platform
from src.scrapers.pinduoduo_web import PinduoduoWebScraper
from src.api.tokens_stats import TokensUsage

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
        self.llm_client = get_llm_client()  # Унифицированный LLM клиент (YandexGPT или OpenAI/ProxyAPI)
        self.exchange_rate_client = ExchangeRateClient()  # Клиент для ExchangeRate-API
        self.translation_client = get_translation_client()  # Отдельный LLM для переводов/предобработки цен
        # Режим работы с ценами: simple — старый сценарий (только максимальная цена), advanced — перевод и сводка вариантов
        self.price_mode = (settings.PRICE_MODE or "simple").strip().lower()
        # Стратегия работы с OpenAI: legacy или single_pass
        openai_strategy_raw = (getattr(settings, "OPENAI_STRATEGY", "") or "single_pass").strip().lower()
        self.openai_strategy = openai_strategy_raw or "single_pass"
        # Флаг: используем ли однопроходный режим для OpenAI (без отдельного шага перевода)
        self.use_openai_single_pass = isinstance(self.llm_client, OpenAIClient) and self.openai_strategy in {
            "single_pass",
            "single",
            "one_pass",
        }
        # Для ProxyAPI отключаем режим структурированных (JSON) батч-переводов, чтобы не тратить лишний бюджет
        # и не получать нестабильные ответы через прокси.
        if isinstance(self.translation_client, ProxyAPIClient):
            self.translation_supports_structured = False
        else:
            self.translation_supports_structured = hasattr(self.translation_client, "generate_json_response")
        
        # Отдельный клиент для постобработки текста поста (может быть None, если отключено/не сконфигурировано)
        self.postprocess_client = get_postprocess_client()
        # Отдельный клиент для генерации хэштегов (может быть None, если отключено/не сконфигурировано)
        self.hashtags_client = get_hashtags_client()

        # Атрибут для сбора общей статистики токенов во время обработки запроса
        self._current_tokens_usage: TokensUsage | None = None
        # Атрибут для отдельного учёта токенов постобработки (чтобы показывать их отдельной строкой в статистике)
        self._postprocess_tokens_usage: TokensUsage | None = None
        # Атрибут для отдельного учёта токенов генерации хэштегов
        self._hashtags_tokens_usage: TokensUsage | None = None

    async def scrape_product(
        self, 
        url: str,
        user_signature: str = None,
        user_currency: str = None,
        exchange_rate: float = None,
        request_id: str | None = None,
        user_price_mode: str | None = None,
        is_admin: bool = False,
    ) -> tuple[str, list[str]] | tuple[str, list[str], TokensUsage]:
        """
        Собирает информацию о товаре по URL, генерирует структурированный контент
        и формирует финальный пост.

        Args:
            url (str): URL товара для скрапинга.
            user_signature (str, optional): Подпись пользователя для поста
            user_currency (str, optional): Валюта пользователя (cny или rub)
            exchange_rate (float, optional): Курс обмена для рубля
            user_price_mode (str, optional): Режим цен для пользователя (simple/advanced/None → использовать глобальный)
            is_admin (bool, optional): Является ли пользователь администратором (для детализированных ошибок)

        Returns:
            tuple: Кортеж, содержащий:
                - сгенерированный текст поста (str)
                - список URL изображений (list)
                - статистика токенов (TokensUsage) - опционально, если используется OpenAI/ProxyAPI
        """
        # Инициализируем общую статистику токенов для этого запроса
        self._current_tokens_usage = TokensUsage()
        # Инициализируем отдельную статистику токенов постобработки
        self._postprocess_tokens_usage = TokensUsage()
        # Используем подпись пользователя (может быть пустой)
        signature = user_signature or ""
        currency = (user_currency or settings.DEFAULT_CURRENCY).lower()
        # Режим цен: пользовательский override → глобальный → simple
        effective_price_mode = (user_price_mode or "").strip().lower() or self.price_mode or "simple"
        # Сохраняем переданный курс пользователя (если есть)
        user_exchange_rate = exchange_rate if exchange_rate is not None else None
        # Определяем платформу заранее, чтобы Pinduoduo обрабатывать веб-скрапингом
        platform, item_id = URLParser.parse_url(url)
        logger.info(f"Определена платформа: {platform} для URL: {url}")
        
        # Нормализуем URL для 1688: извлекаем ID и формируем правильный формат
        if platform == Platform.ALI1688:
            normalized_url = URLParser.normalize_1688_url(url)
            if normalized_url:
                logger.info(f"Нормализован URL 1688: {url} -> {normalized_url}")
                url = normalized_url
            else:
                logger.warning(f"Не удалось нормализовать URL 1688: {url}, используем исходный")
        
        if platform == Platform.PINDUODUO:
            logger.info("Обработка Pinduoduo через веб-скрапинг")
            pdd = PinduoduoWebScraper()
            api_response = await pdd.fetch_product(url)
            logger.info(f"Ответ от Pinduoduo скрейпера: code={api_response.get('code')}, msg={api_response.get('msg')}")
            api_response['_platform'] = Platform.PINDUODUO
        elif platform == Platform.SZWEGO:
            # Szwego: работаем через API (быстро, без браузера), используя заранее подготовленные cookies+UA.
            # Важно: cookies будут периодически протухать и их нужно обновлять вручную на сервере.
            logger.info("Обработка Szwego через API")
            from src.api.szwego_api import SzwegoApiClient
            szwego_client = SzwegoApiClient()
            api_response = await szwego_client.fetch_product(url)
            logger.info(
                "Ответ от Szwego API: code=%s, msg=%s",
                api_response.get("code"),
                api_response.get("msg"),
            )
            api_response["_platform"] = Platform.SZWEGO

            # ВАЖНО: если Szwego API вернул ошибку (например, URL не товарный / cookies протухли),
            # не продолжаем пайплайн и не вызываем LLM — иначе получаем пустой пост и тратим токены.
            try:
                code = api_response.get("code")
                has_data = isinstance(api_response.get("data"), dict) and bool(api_response.get("data"))
                if code != 200 or not has_data:
                    internal_msg = str(api_response.get("msg") or "").strip()
                    internal_low = internal_msg.lower()

                    # Для пользователя скрываем детали про cookies/token.
                    user_friendly = "Szwego временно недоступен. Попробуйте отправить запрос позже."

                    # 1) Если это похоже на проблему авторизации/токена — уведомляем админа (анти-спам внутри notify_admin_system)
                    # 2) Если это просто “ссылка не товарная” — возвращаем диагностическое сообщение пользователю
                    looks_like_auth_issue = bool(
                        code in {401, 403} or any(
                            k in internal_low
                            for k in ["токен", "token", "cookie", "cookies", "авторизац", "session", "login", "unauthor"]
                        )
                    )

                    if looks_like_auth_issue:
                        try:
                            import time as _time
                            from src.bot import error_handler as error_handler_module
                            from src.services.szwego_monitor import get_szwego_token_status

                            st = get_szwego_token_status()
                            await error_handler_module.notify_admin_system(
                                text=(
                                    "⚠️ <b>Szwego: запросы временно не работают</b>\n\n"
                                    f"<b>Причина:</b> <code>{internal_msg[:400] or 'unknown'}</code>\n"
                                    f"<b>Код:</b> <code>{code}</code>\n"
                                    f"<b>До expires:</b> <code>{st.seconds_left}</code> сек\n"
                                    f"<b>Файл cookies:</b> <code>{getattr(settings, 'SZWEGO_COOKIES_FILE', '')}</code>\n"
                                    f"<b>Время:</b> <code>{int(_time.time())}</code>\n"
                                ),
                                key="szwego_runtime",
                            )
                        except Exception:
                            pass
                        return user_friendly, []

                    # Если это не auth-проблема, а диагностический текст по URL — его можно показывать пользователю
                    if internal_msg:
                        return f"❌ {internal_msg}", []

                    return f"❌ {user_friendly}", []
            except Exception:
                # Если вдруг структура сломалась — безопасно выходим
                return "❌ Szwego временно недоступен. Попробуйте отправить запрос позже.", []
        else:
            # Получаем данные о товаре через tmapi.top (автоопределение платформы)
            logger.info("Обработка через TMAPI")
            api_response = await self.tmapi_client.get_product_info_auto(url, request_id=request_id)
        
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
                if is_admin:
                    user_msg = (
                        "❌ Не удалось получить данные товара с Pinduoduo.\n\n"
                        "⚠️ Отсутствует файл с cookies для авторизации.\n\n"
                        "Для работы с Pinduoduo необходимо:\n"
                        "1. Создать файл `src/pdd_cookies.json` на основе `src/pdd_cookies_example.json`\n"
                        "2. Заполнить файл реальными cookies из вашего браузера\n"
                        "3. Перезапустить бота\n\n"
                        "Подробнее см. в документации проекта."
                    )
                else:
                    user_msg = "⚠️ Работа с Pinduoduo временно недоступна. Попробуйте позже."
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
                    result = await self._translate_text_generic(raw_description, target_language="ru")
                    if isinstance(result, tuple):
                        translated, tokens_usage = result
                        if self._current_tokens_usage:
                            self._current_tokens_usage += tokens_usage
                    else:
                        translated = result
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

        # Для taobao/tmall/1688: запускаем получение detail_images параллельно с обработкой LLM
        # Это ускоряет общее время обработки, так как запрос к item_desc выполняется одновременно с подготовкой данных для LLM
        detail_images_task = None
        if platform in (Platform.TAOBAO, Platform.TMALL, Platform.ALI1688):
            item_id = product_data.get('item_id')
            if item_id:
                if settings.DEBUG_MODE:
                    print(f"[Scraper] Запускаем параллельную задачу для получения detail_images (item_id={item_id})")
                detail_images_task = asyncio.create_task(
                    self._get_filtered_detail_images(item_id, platform=platform, request_id=request_id)
                )
            else:
                if settings.DEBUG_MODE:
                    print(f"[Scraper] ⚠️ item_id отсутствует! Пропускаем параллельное получение detail изображений.")

        # В режиме расширенных цен:
        # - отключаем single_pass (он может раздувать ввод и усложнять отладку)
        # - НЕ форсим shared-промпт для генерации поста (используем OPENAI_PROMPT_VARIANT из .env),
        #   потому что shared сильно раздувает входные токены.
        force_legacy_openai = effective_price_mode in {"advanced", "adv", "full", "detailed"}
        original_strategy = getattr(settings, "OPENAI_STRATEGY", "single_pass")
        original_prompt_variant = getattr(settings, "OPENAI_PROMPT_VARIANT", "compact_v2")
        use_single_pass = self.use_openai_single_pass and not force_legacy_openai

        if force_legacy_openai and isinstance(self.llm_client, OpenAIClient):
            try:
                # Исторически в advanced режиме мы откатывались на legacy/shared,
                # но теперь ценовой пайплайн стабилизирован (1 запрос на перевод + локальная суммаризация),
                # поэтому shared больше не нужен.
                settings.OPENAI_STRATEGY = "legacy"
            except Exception:
                pass

        # Подготавливаем данные для LLM.
        # Для OpenAI в режиме single_pass отправляем сырые данные TMAPI (только нужные поля)
        # и перекладываем задачу перевода на саму модель.
        if use_single_pass:
            compact_data = self._prepare_openai_single_pass_payload(product_data)
            # В однопроходном режиме не тратим токены на отдельный перевод заголовка/описания.
            raw_title = product_data.get('title', '') or ''
            translated_title_hint = ""
            translated_description = ""
        else:
            # Старое поведение: компактные данные + отдельный перевод заголовка и описания.
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
            elif platform == Platform.SZWEGO:
                # Для Szwego: details = title, не переводим отдельно, чтобы не дублировать токены
                # Используем только переведённый title_hint для контекста цен
                raw_description = ''
            else:
                raw_description = (product_data.get('details') or '').strip()
            
            # Переводим описание (ограничиваем длину для скорости)
            translated_description = ''
            if raw_description:
                # Берём первые 500 символов описания для контекста
                description_sample = raw_description[:500]
                translated_description = await self._translate_text_generic(description_sample, target_language="ru")

        # Формируем контекст для перевода цен (даже в single_pass используем сырой заголовок)
        product_context = {
            'title': translated_title_hint or raw_title,
            'description': translated_description
        }

        price_lines: list[dict] = []
        # В simple-режиме возвращаемся к старому сценарию: только максимальная цена без перечисления вариантов
        if effective_price_mode in {"advanced", "adv", "full", "detailed"}:
            price_lines = await self._prepare_price_entries(product_data, product_context)
            if price_lines:
                compact_data["translated_sku_prices"] = price_lines
        
        # Генерируем структурированный контент с помощью выбранного LLM.
        # Важно: для OpenAI/ProxyAPI метод может вернуть (content, tokens_usage).
        result = None
        try:
            result = await self.llm_client.generate_post_content(compact_data)
        finally:
            # Возвращаем стратегию/промпт в исходное состояние, если временно форсировали legacy/shared.
            if force_legacy_openai and isinstance(self.llm_client, OpenAIClient):
                try:
                    settings.OPENAI_STRATEGY = original_strategy
                    settings.OPENAI_PROMPT_VARIANT = original_prompt_variant
                except Exception:
                    pass

        # Новая сигнатура: возвращает кортеж (content, tokens_usage) для OpenAI/ProxyAPI
        if isinstance(result, tuple):
            llm_content, tokens_usage = result
            if self._current_tokens_usage and tokens_usage:
                self._current_tokens_usage += tokens_usage
        else:
            # Обратная совместимость: YandexGPT возвращает только dict
            llm_content = result
        translated_title = llm_content.get('title') or translated_title_hint
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] LLM контент получен: {llm_content.get('title', 'N/A')}")
        
        # Пост-обработка: исправляем общие термины в ценах на конкретные из описания
        if price_lines and llm_content:
            price_lines = self._fix_price_labels_with_context(price_lines, llm_content)
        
        # Санитация ответа LLM: убираем выдуманные «Цвета», добавляем/фиксируем «Состав»
        try:
            if isinstance(llm_content, dict):
                # 0) Жёсткая защита от китайских иероглифов в ответе LLM.
                # Мы НЕ допускаем CJK-символы в title/description/характеристиках:
                # - если CJK встречается в значении, пытаемся убрать иероглифы;
                # - если после очистки остаётся «мусор» (почти нет букв), удаляем поле целиком.
                import re

                cjk_re = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")

                def _sanitize_text_no_cjk(val: str) -> tuple[str, bool]:
                    s = (val or "").strip()
                    had_cjk = bool(cjk_re.search(s))
                    if had_cjk:
                        s = cjk_re.sub("", s)
                    # Схлопываем лишние пробелы/слэши после удаления
                    s = re.sub(r"\s{2,}", " ", s).strip(" /-;:,").strip()
                    return s, had_cjk

                def _has_meaningful_letters(s: str) -> bool:
                    # Есть ли вообще буквы (кириллица/латиница), чтобы не оставлять пустую "кашу".
                    return any(("a" <= ch.lower() <= "z") or ("а" <= ch.lower() <= "я") or (ch.lower() == "ё") for ch in (s or ""))

                # title/description
                if isinstance(llm_content.get("title"), str):
                    t, _ = _sanitize_text_no_cjk(llm_content.get("title", ""))
                    llm_content["title"] = t or llm_content.get("title", "")
                if isinstance(llm_content.get("description"), str):
                    d, _ = _sanitize_text_no_cjk(llm_content.get("description", ""))
                    llm_content["description"] = d or llm_content.get("description", "")

                mc = llm_content.get('main_characteristics') or {}
                if not isinstance(mc, dict):
                    mc = {}

                # main_characteristics: чистим значения от CJK, убираем поля, которые после очистки теряют смысл
                cleaned_mc: dict = {}
                for k, v in mc.items():
                    key = str(k).strip()
                    if not key:
                        continue
                    # Если ключ сам содержит CJK — пропускаем (не должны быть китайские названия полей)
                    if cjk_re.search(key):
                        continue

                    if isinstance(v, str):
                        vv, had = _sanitize_text_no_cjk(v)
                        if had and (not vv or not _has_meaningful_letters(vv)):
                            # Был китайский, а после очистки смысла нет — выбрасываем поле
                            continue
                        cleaned_mc[key] = vv or v
                    elif isinstance(v, list):
                        out_items: list = []
                        for item in v:
                            if isinstance(item, str):
                                it, had = _sanitize_text_no_cjk(item)
                                if had and (not it or not _has_meaningful_letters(it)):
                                    continue
                                if it:
                                    out_items.append(it)
                            else:
                                out_items.append(item)
                        if out_items:
                            cleaned_mc[key] = out_items
                    else:
                        cleaned_mc[key] = v
                mc = cleaned_mc

                looks_like_apparel = self._is_apparel_product(translated_title or translated_title_hint, product_data)
                # 1) Удаляем цвета, если LLM выдумал вроде «Чистый цвет»/«Однотонный»
                colors = mc.get('Цвета') or mc.get('Цвет')
                if colors:
                    bad_markers = {'чистый цвет', 'однотон', 'однотонный', 'plain', 'solid'}
                    def _is_bad(val: str) -> bool:
                        s = (val or '').strip().lower()
                        return any(k in s for k in bad_markers)
                    def _looks_like_color_value(val: str) -> bool:
                        """
                        Грубая эвристика: оставляем только то, что действительно похоже на цвет/принт/паттерн.

                        Примеры, которые ДОЛЖНЫ пройти:
                        - "чёрно-красный", "бледно-розовый", "хаки", "бордовый"
                        - "осенний пейзаж" (как абстрактный «цветовой» дескриптор/принт)
                        - "камуфляж", "мраморный принт", "полоска", "клетка"

                        Примеры, которые ДОЛЖНЫ быть удалены:
                        - "корейская кукла" (скорее рисунок/сувенир/маркетинг, не цвет)
                        - "белый f0045", "d0004+f0045" (технические коды)
                        """
                        s = (val or "").strip().lower()
                        if not s:
                            return False

                        # 0) Если содержит технические коды типа f00xx, d00xx - не является цветом
                        import re
                        if re.search(r"\b[fFdD]0{2,3}\d{1,4}(?:\+[fFdD]0{2,3}\d{1,4})*\b", s):
                            return False

                        # 1) Если явно содержит известные цветовые слова — ок
                        try:
                            if self.COLOR_REGEX.search(s):
                                return True
                        except Exception:
                            pass

                        # 2) Разрешённые «паттерны»/принты/абстракции, которые часто используются как цветовой дескриптор
                        allowed_pattern_markers = (
                            "принт", "узор", "рисунок", "градиент",
                            "камуфляж", "леопард", "зебр", "питон",
                            "клетк", "полоск", "горош", "мрамор",
                            "пейзаж", "абстракц", "космос",
                        )
                        if any(m in s for m in allowed_pattern_markers):
                            return True

                        # 3) Явно запрещённые маркеры (часто это не цвет, а объект/упаковка/серия)
                        disallowed_markers = (
                            "кукла", "игрушк", "подарок", "сувенир",
                            "упаков", "короб", "пакет", "брелок",
                        )
                        if any(m in s for m in disallowed_markers):
                            return False

                        # 4) Если не похоже ни на цвет, ни на принт — удаляем
                        return False
                    def _clean_color_code(val: str) -> str:
                        """Очищает технические коды из названия цвета"""
                        import re
                        s = val.strip()
                        # Удаляем коды типа f00xx, d00xx и их комбинации
                        s = re.sub(r"\b[fFdD]0{2,3}\d{1,4}(?:\+[fFdD]0{2,3}\d{1,4})*\b", "", s)
                        # Удаляем оставшиеся фрагменты типа +f0045
                        s = re.sub(r"\s*\+\s*[fFdD]0{2,3}\d{1,4}\b", "", s)
                        s = re.sub(r"\s{2,}", " ", s).strip(" ,;:-").strip()
                        return s
                    
                    if isinstance(colors, list):
                        filtered = []
                        for c in colors:
                            if not isinstance(c, str):
                                continue
                            cleaned = _clean_color_code(c)
                            if cleaned and not _is_bad(cleaned) and _looks_like_color_value(cleaned):
                                filtered.append(cleaned)
                        if filtered:
                            mc['Цвета'] = filtered
                        else:
                            mc.pop('Цвета', None)
                    elif isinstance(colors, str):
                        cleaned = _clean_color_code(colors)
                        if not cleaned or _is_bad(cleaned) or not _looks_like_color_value(cleaned):
                            mc.pop('Цвета', None)
                        else:
                            mc['Цвета'] = cleaned
                # Раньше мы полностью выбрасывали «Цвета» для не-одежды, чтобы не было галлюцинаций.
                # Но для части товаров (подарки, кейсы, аксессуары) цвет — важный отличительный признак.
                # Поэтому оставляем цвета, если они явно присутствуют во входных данных (sku_props/product_props).
                if not looks_like_apparel:
                    try:
                        def _has_explicit_color_source(pd: dict) -> bool:
                            # 1) sku_props содержит цветовые измерения
                            sku_props_src = pd.get("sku_props") or []
                            if isinstance(sku_props_src, list):
                                for prop in sku_props_src:
                                    if not isinstance(prop, dict):
                                        continue
                                    pn = (prop.get("prop_name") or "").strip().lower()
                                    if any(tok in pn for tok in ("цвет", "color", "颜色")):
                                        return True
                            # 2) product_props содержит цветовую классификацию
                            props_src = pd.get("product_props") or []
                            if isinstance(props_src, list):
                                for item in props_src:
                                    if not isinstance(item, dict):
                                        continue
                                    for k in item.keys():
                                        kk = str(k).strip().lower()
                                        if any(tok in kk for tok in ("цвет", "color", "颜色")):
                                            return True
                            return False

                        if not _has_explicit_color_source(product_data):
                            mc.pop('Цвета', None)
                            mc.pop('Цвет', None)
                    except Exception:
                        mc.pop('Цвета', None)
                        mc.pop('Цвет', None)
                # 2) Удаляем лишние секции «Варианты наборов», «Комплектации» и т.п.
                forbidden_sections = ('вариант', 'комплектац', 'набор')
                for key in list(mc.keys()):
                    if any(token in key.lower() for token in forbidden_sections):
                        mc.pop(key, None)

                # 2.1) Удаляем заведомо лишнее для постов:
                # - гарантийные условия (пользователь не хочет видеть это в постах)
                # - указание источника/платформы/маркетплейса
                drop_markers = (
                    'гарант', 'срок служб', 'гарантий',
                    'источник', 'платформ', 'маркетплейс', 'source', 'platform',
                )
                for key in list(mc.keys()):
                    if any(marker in key.lower() for marker in drop_markers):
                        mc.pop(key, None)

                # 2.2) Исправляем типичную ошибку LLM: подставляет «Состав» как «инструменты/комплектацию».
                # Например: "Состав: кусачки для ногтей" — это не состав (материал), а предмет/инструмент.
                try:
                    comp_key = None
                    for k in list(mc.keys()):
                        if str(k).strip().lower() == "состав":
                            comp_key = k
                            break
                    if comp_key is not None:
                        v = mc.get(comp_key)
                        v_str = ""
                        if isinstance(v, str):
                            v_str = v.strip().lower()
                        elif isinstance(v, list):
                            v_str = " ".join(str(x) for x in v).strip().lower()

                        # Если похоже на материалы/состав ткани — оставляем как «Состав».
                        material_markers = (
                            "%", "хлоп", "шерст", "полиэстер", "вискоз", "нейлон", "акрил",
                            "кожа", "замш", "резин", "пластик", "металл", "сталь", "алюмин",
                            "дерев", "стекл", "керамик", "силикон",
                        )

                        # Если похоже на инструменты/предметы — переносим в «Инструменты».
                        tool_markers = (
                            "кусач", "щипц", "пилка", "ножниц", "пинцет", "триммер",
                            "отвёрт", "ключ", "дрель", "гайков", "перфорат", "шлиф",
                            "болгар", "пила", "цепн", "шурупов",
                        )

                        looks_like_material = any(m in v_str for m in material_markers)
                        looks_like_tools = any(t in v_str for t in tool_markers)

                        if (not looks_like_material) and looks_like_tools:
                            # Переносим в «Инструменты», стараясь не потерять существующее значение.
                            existing = mc.get("Инструменты")
                            if existing:
                                # Если уже есть — объединяем кратко
                                if isinstance(existing, list):
                                    merged = existing + ([v] if not isinstance(v, list) else v)
                                    mc["Инструменты"] = merged
                                elif isinstance(existing, str):
                                    mc["Инструменты"] = (existing + "; " + (v if isinstance(v, str) else str(v))).strip()
                            else:
                                mc["Инструменты"] = v
                            mc.pop(comp_key, None)
                except Exception:
                    pass
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
        
        # Формируем финальный пост из структурированных данных (без хэштегов)
        post_text = self._build_post_text(
            llm_content=llm_content,
            product_data=product_data,
            signature=signature,
            currency=currency,
            exchange_rate=exchange_rate,
            price_lines=price_lines,
            hashtags=None  # Хэштеги будут сгенерированы отдельно
        )

        # Шаг генерации хэштегов на основе готового поста (до постобработки).
        # ВАЖНО:
        # - Включается только при ENABLE_HASHTAGS=True.
        # - Использует отдельный LLM-клиент (если он успешно инициализировался).
        hashtags = []
        if getattr(settings, "ENABLE_HASHTAGS", False) and self.hashtags_client:
            try:
                hashtags_result = await self.hashtags_client.generate_hashtags(post_text)
                if isinstance(hashtags_result, tuple):
                    hashtags, tokens_usage_hashtags = hashtags_result
                else:
                    # Теоретически сюда попадём только если сигнатура изменится,
                    # но оставляем безопасный фолбэк.
                    hashtags = hashtags_result if isinstance(hashtags_result, list) else []
                    tokens_usage_hashtags = TokensUsage()

                # Сохраняем статистику токенов генерации хэштегов отдельно для показа в статистике.
                if tokens_usage_hashtags:
                    self._hashtags_tokens_usage = tokens_usage_hashtags
                    # Также добавляем в общую статистику для общего подсчёта стоимости.
                    if self._current_tokens_usage:
                        self._current_tokens_usage += tokens_usage_hashtags

                if settings.DEBUG_MODE:
                    try:
                        print(f"[Scraper] Генерация хэштегов выполнена через LLM. Хэштеги: {hashtags}, токены: {tokens_usage_hashtags.total_tokens} (вход: {tokens_usage_hashtags.prompt_tokens}, выход: {tokens_usage_hashtags.completion_tokens}), стоимость: ${tokens_usage_hashtags.total_cost:.6f}")
                    except Exception:
                        pass
                
                # Добавляем хэштеги в пост
                if hashtags:
                    post_text = self._add_hashtags_to_post(post_text, hashtags)
            except Exception as e:
                # Никогда не роняем основной сценарий из-за проблем генерации хэштегов.
                if settings.DEBUG_MODE:
                    try:
                        print(f"[Scraper] Ошибка LLM-генерации хэштегов: {e}")
                    except Exception:
                        pass

        # Шаг LLM-постобработки: аккуратное исправление языка без изменения структуры поста.
        # ВАЖНО:
        # - Включается только при ENABLE_POSTPROCESSING=True.
        # - Использует отдельный компактный OpenAI-клиент (если он успешно инициализировался).
        if getattr(settings, "ENABLE_POSTPROCESSING", False) and self.postprocess_client:
            try:
                result_pp = await self.postprocess_client.postprocess_post_text(post_text)
                if isinstance(result_pp, tuple):
                    post_text_processed, tokens_usage_pp = result_pp
                else:
                    # Теоретически сюда попадём только если сигнатура изменится,
                    # но оставляем безопасный фолбэк.
                    post_text_processed = result_pp
                    tokens_usage_pp = TokensUsage()

                # Если модель вернула ненулевой текст — используем его как финальный.
                if isinstance(post_text_processed, str) and post_text_processed.strip():
                    post_text = post_text_processed

                # Сохраняем статистику токенов постобработки отдельно для показа в статистике.
                if tokens_usage_pp:
                    self._postprocess_tokens_usage = tokens_usage_pp
                    # Также добавляем в общую статистику для общего подсчёта стоимости.
                    if self._current_tokens_usage:
                        self._current_tokens_usage += tokens_usage_pp

                if settings.DEBUG_MODE:
                    try:
                        print(f"[Scraper] Постобработка поста выполнена через LLM. Токены: {tokens_usage_pp.total_tokens} (вход: {tokens_usage_pp.prompt_tokens}, выход: {tokens_usage_pp.completion_tokens}), стоимость: ${tokens_usage_pp.total_cost:.6f}")
                    except Exception:
                        pass
            except Exception as e:
                # Никогда не роняем основной сценарий из-за проблем постобработки.
                if settings.DEBUG_MODE:
                    try:
                        print(f"[Scraper] Ошибка LLM-постобработки поста: {e}")
                    except Exception:
                        pass
        
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
            # Если задача была запущена параллельно - ждём её завершения, иначе получаем синхронно
            detail_images = []
            
            if detail_images_task:
                # Задача была запущена параллельно - ждём завершения
                try:
                    detail_images = await detail_images_task
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] Параллельная задача завершена: получено {len(detail_images)} detail изображений")
                except Exception as e:
                    logger.warning(f"Ошибка при получении detail_images в параллельной задаче: {e}")
                    if settings.DEBUG_MODE:
                        import traceback
                        print(f"[Scraper] ❌ Ошибка в параллельной задаче detail_images:")
                        traceback.print_exc()
                    detail_images = []
            else:
                # Для других платформ или если item_id отсутствовал - получаем синхронно (fallback)
                item_id = product_data.get('item_id')
                if item_id:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] Извлечен item_id: {item_id}, получаем detail_images синхронно")
                    detail_images = await self._get_filtered_detail_images(item_id, platform=platform, request_id=request_id)
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] Получено detail изображений: {len(detail_images)}")
                else:
                    if settings.DEBUG_MODE:
                        print(f"[Scraper] ⚠️ item_id отсутствует! Пропускаем получение detail изображений.")
        
        # Объединяем изображения: сначала из sku_props, потом из detail_html
        image_urls = sku_images + detail_images
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Итого изображений: {len(image_urls)} (sku: {len(sku_images)}, detail: {len(detail_images)})")

        # Возвращаем результат с статистикой токенов, если она есть
        total_tokens_usage = self._current_tokens_usage or TokensUsage()
        postprocess_tokens_usage = self._postprocess_tokens_usage or TokensUsage()
        
        # Если есть токены (основные или постобработки), возвращаем расширенную сигнатуру
        if total_tokens_usage.total_tokens > 0 or postprocess_tokens_usage.total_tokens > 0:
            # Возвращаем 4 элемента: текст, изображения, общие токены, токены постобработки
            # Если постобработка не выполнялась, postprocess_tokens_usage будет пустым TokensUsage()
            # Если основной провайдер - YandexGPT, total_tokens_usage может быть пустым, но postprocess_tokens_usage может быть заполнен
            return post_text, image_urls, total_tokens_usage, postprocess_tokens_usage
        return post_text, image_urls
    
    def _prepare_compact_data_for_llm(self, product_data: dict) -> dict:
        """
        Подготавливает компактные данные для отправки в LLM.
        Убирает огромный массив skus и другие лишние данные.
        Поддерживает как Taobao/Tmall, так и Pinduoduo, и Szwego.
        
        Args:
            product_data: Полные данные от TMAPI/Szwego API
            
        Returns:
            dict: Компактные данные только с нужной информацией
        """
        platform = product_data.get('_platform', 'unknown')
        
        # Для Szwego: оптимизация - ограничиваем длину title (часто это длинное описание)
        # и не передаём пустые product_props, чтобы не раздувать промпт
        if platform == Platform.SZWEGO:
            title = product_data.get('title', '').strip()
            # Ограничиваем длину title для Szwego (часто это многострочное описание)
            # Берём первые 300 символов, чтобы не раздувать промпт токенами
            if len(title) > 300:
                title = title[:300].rstrip() + "..."
            
            compact = {
                'title': title,
                # У Szwego нет product_props, не передаём пустой список
            }
            return compact
        
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

        # В режиме цен advanced пробрасываем цены в основной промпт,
        # чтобы OpenAI сразу видел ассортимент и не «выдумывал» варианты.
        if self.price_mode == "advanced":
            price_entries = self._get_unique_sku_price_items(product_data)
            if price_entries:
                compact["price_mode"] = "advanced"
                # Ограничиваем объём, чтобы не раздувать токены
                compact["price_entries"] = price_entries[:120]
        
        if settings.DEBUG_MODE:
            print(f"[Scraper] Компактные данные для LLM подготовлены. Размер: ~{len(str(compact))} символов")
            print(f"[Scraper] Исключено {len(product_data.get('skus', []))} элементов из skus")
        
        return compact
    
    def _prepare_openai_single_pass_payload(self, product_data: dict) -> dict:
        """
        Подготавливает полезную нагрузку для OpenAI в однопроходном режиме.
        
        В этом режиме:
        - мы не выполняем отдельный шаг перевода заголовка/описания;
        - передаём в модель только действительно нужные поля из ответа TMAPI;
        - оставляем перевод и формирование финального поста на саму модель OpenAI.
        
        На данном этапе используем фиксированный набор полей, но структура
        изначально спроектирована так, чтобы в будущем можно было различать
        платформы и настраивать список полей по платформам/стратегиям.
        """
        platform = product_data.get("_platform", "unknown")

        # Лимиты (защита от раздувания prompt токенами)
        max_skus = int(getattr(settings, "OPENAI_SINGLE_PASS_MAX_SKUS", 120) or 120)
        max_values_per_prop = int(getattr(settings, "OPENAI_SINGLE_PASS_MAX_SKU_VALUES", 60) or 60)
        max_prop_value_len = int(getattr(settings, "OPENAI_SINGLE_PASS_MAX_PROP_VALUE_LEN", 220) or 220)

        def _truncate_text(value: str) -> str:
            """
            Обрезает слишком длинные строковые значения, чтобы не тратить токены на «простыни».
            Важно: это касается только полей, где обычно дублируется то же самое из sku_props/skus
            (например, огромные строки вариантов цветов/комплектаций).
            """
            s = (value or "").strip()
            if not s:
                return ""
            if len(s) <= max_prop_value_len:
                return s
            return s[: max_prop_value_len - 1].rstrip() + "…"

        def _filter_product_props(props: object) -> list[dict]:
            """
            product_props обычно содержит «ключ → значение» (часто 1 ключ в dict).
            Тут выкидываем заведомо запрещённые/бесполезные вещи (пол/возраст и т.п.)
            и режем слишком длинные значения.
            """
            if not isinstance(props, list):
                return []

            forbidden_markers = (
                # Китайский (TMAPI)
                "适用性别", "性别", "适用年龄", "年龄",
                # Русский/английский (на случай других источников)
                "пол", "гендер", "возраст", "gender", "age",
                # Сезоны и времена года
                "季节", "season", "seasonality", "seasonal", "сезон", "сезонность", "сезонный",
                # Формат выпуска и заявления производителя
                "格式", "format", "release", "release format", "выпуск", "формат выпуска", "заявлен", "заявлен как",
            )

            cleaned: list[dict] = []
            for item in props:
                if not isinstance(item, dict) or not item:
                    continue
                out: dict = {}
                for k, v in item.items():
                    key = str(k)
                    key_l = key.lower()
                    if any(m.lower() in key_l for m in forbidden_markers):
                        continue

                    # Нормализуем значение
                    if isinstance(v, str):
                        vv = _truncate_text(v)
                        if vv:
                            out[key] = vv
                    elif isinstance(v, (int, float, bool)) or v is None:
                        out[key] = v
                    else:
                        # На всякий случай: сериализуем сложные типы в короткую строку
                        try:
                            out[key] = _truncate_text(str(v))
                        except Exception:
                            pass

                if out:
                    cleaned.append(out)
            return cleaned

        def _minify_sku_props(props: object) -> list[dict]:
            """
            sku_props содержит варианты по измерениям (цвет/размер/спецификация).
            В prompt отправляем только то, что нужно:
            - prop_name
            - values[].name (без vid/imageUrl и прочего)
            + лимитируем количество значений.
            """
            if not isinstance(props, list):
                return []

            result: list[dict] = []
            for prop in props:
                if not isinstance(prop, dict):
                    continue
                prop_name = (prop.get("prop_name") or "").strip()
                values = prop.get("values") or []
                if not prop_name or not isinstance(values, list):
                    continue

                names: list[str] = []
                seen = set()
                for v in values:
                    if not isinstance(v, dict):
                        continue
                    name = (v.get("name") or "").strip()
                    if not name:
                        continue
                    if name in seen:
                        continue
                    seen.add(name)
                    names.append(name)
                    if len(names) >= max_values_per_prop:
                        break

                if names:
                    result.append(
                        {
                            "prop_name": prop_name,
                            "values": [{"name": n} for n in names],
                        }
                    )
            return result

        def _minify_skus(skus: object) -> list[dict]:
            """
            skus часто содержит сотни/тысячи строк. Для LLM обычно достаточно:
            - props_names (человекочитаемый вариант)
            - sale_price (цена)
            Всё остальное выбрасываем. Делаем dedupe и лимит.
            """
            if not isinstance(skus, list):
                return []

            result: list[dict] = []
            seen = set()
            for sku in skus:
                if not isinstance(sku, dict):
                    continue
                props_names = (sku.get("props_names") or "").strip()
                sale_price = sku.get("sale_price")
                if not props_names and sale_price is None:
                    continue
                key = (props_names, str(sale_price))
                if key in seen:
                    continue
                seen.add(key)
                result.append({"props_names": props_names, "sale_price": sale_price})
                if len(result) >= max_skus:
                    break
            return result

        def _minify_price_info(pi: object) -> dict | None:
            """
            Для 1688 price_info может быть большим. Берём только полезное:
            price / price_min / price_max / origin_price_min / origin_price_max / discount_price
            """
            if not isinstance(pi, dict):
                return None
            keep_keys = (
                "price",
                "price_min",
                "price_max",
                "origin_price",
                "origin_price_min",
                "origin_price_max",
                "discount_price",
            )
            out = {k: pi.get(k) for k in keep_keys if k in pi}
            return out or None

        # Базовые поля, общие для всех поддерживаемых платформ (но содержимое «поджато»)
        payload: dict = {
            "platform": platform,
            "title": product_data.get("title", ""),
            "product_props": _filter_product_props(product_data.get("product_props", [])),
            "sku_props": _minify_sku_props(product_data.get("sku_props", [])),
            "skus": _minify_skus(product_data.get("skus", [])),
        }

        # Цена: пытаемся извлечь как унифицированное поле price,
        # но также прокидываем исходный блок price_info для 1688/других платформ.
        price_info_raw = product_data.get("price_info")
        price = product_data.get("price")
        if price is None and isinstance(price_info_raw, dict):
            price = price_info_raw.get("price") or price_info_raw.get("sale_price")

        if price is not None:
            payload["price"] = price
        price_info = _minify_price_info(price_info_raw)
        if price_info is not None:
            payload["price_info"] = price_info

        # При наличии уже подготовленных списков цветов/размеров тоже прокидываем их,
        # чтобы не терять совместимость с текущим промптом генерации поста.
        if "available_colors" in product_data:
            payload["available_colors"] = product_data.get("available_colors") or []
        if "available_sizes" in product_data:
            payload["available_sizes"] = product_data.get("available_sizes") or []

        # В режиме цен advanced отправляем LLM готовые позиции с ценами,
        # чтобы промпт compact_v2 сразу видел ассортимент (без выдумывания вариантов).
        if self.price_mode == "advanced":
            price_entries = self._get_unique_sku_price_items(product_data)
            if price_entries:
                payload["price_mode"] = "advanced"
                payload["price_entries"] = price_entries[:120]

        return payload
    
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
    
    async def _get_filtered_detail_images(self, item_id: int, platform: str = Platform.TAOBAO, request_id: str | None = None) -> list:
        """
        Получает дополнительные изображения из item_desc и фильтрует их по размерам.
        Убирает баннеры и изображения, которые сильно отличаются от основной группы.
        
        Args:
            item_id: ID товара
            platform: Платформа товара (taobao/tmall/1688)
            
        Returns:
            list: Отфильтрованный список URL изображений
        """
        try:
            if settings.DEBUG_MODE:
                print(f"[Scraper] Запрашиваем item_desc для item_id={item_id}")
            
            # Получаем описание товара
            desc_data = await self.tmapi_client.get_item_description(item_id, platform=platform, request_id=request_id)
            
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
        Обрабатывает по 15 изображений параллельно для ускорения обработки.
        
        Args:
            urls: Список URL изображений
            
        Returns:
            list: Список словарей с url, width, height
        """
        images_with_sizes = []
        
        # Обрабатываем порциями по 15 для ускорения (было 5)
        # Параллельная обработка позволяет увеличить размер батча без перегрузки
        batch_size = 15
        
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
            print("[Scraper] Используется fallback-ветка для обработки цен (без structured JSON задач)")
        return await self._prepare_price_entries_fallback(entries)

    async def _process_prices_with_llm(self, entries: list[dict], product_context: dict) -> list[dict]:
        """
        Использует translation LLM для перевода и сжатия списка цен.
        
        Args:
            entries: Список вариантов с ценами
            product_context: Контекст товара (title, description)
        
        Returns:
            list[dict]: Обработанный список цен
        """
        # Статистика токенов собирается внутри вызываемых методов через глобальную переменную
        # или через обновление total_tokens_usage в методе scrape_product
        try:
            # ВАЖНО: делаем ровно ОДИН LLM-запрос — массовый перевод позиций.
            # Дальше суммаризацию выполняем локально, чтобы:
            # - не тратить токены на огромный промпт;
            # - убрать ретраи/падения из-за невалидного JSON на этапе суммаризации.
            translated = await self._translate_price_entries_with_llm(entries, product_context)
            if not translated:
                return []
            return self._summarize_translated_prices_locally(translated)
        except Exception as e:
            if settings.DEBUG_MODE:
                print(f"[Scraper] Ошибка обработки цен через LLM: {e}")
            return []

    async def _translate_price_entries_with_llm(self, entries: list[dict], product_context: dict) -> list[dict]:
        # 1) Дедупликация и сжатие списка для экономии токенов
        uniq = []
        seen = set()
        for e in entries:
            name = (e.get("name") or "").strip()
            price = e.get("price")
            try:
                price_f = float(price)
            except (TypeError, ValueError):
                continue
            key = (name.lower(), price_f)
            if key in seen:
                continue
            seen.add(key)
            # Усечём слишком длинные названия, чтобы не раздувать промпт
            if len(name) > 160:
                name = name[:157].rstrip() + "…"
            # Добавляем id, чтобы жёстко требовать у модели вернуть ВСЕ элементы
            uniq.append({"id": len(uniq), "name": name, "price": price_f})
            if len(uniq) >= 50:  # жёсткий предел на список для перевода
                break

        if len(uniq) <= 1:
            return [{"label": uniq[0]["name"], "price": uniq[0]["price"]}] if uniq else []

        payload = json.dumps(uniq, ensure_ascii=False, separators=(",", ":"))
        
        if settings.DEBUG_MODE:
            logger.info(
                "[Prices][translate] Подготовлено уникальных позиций: %s, payload_len=%s",
                len(uniq),
                len(payload),
            )
        
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
        
        # Важно: Responses API у нас вызывается с text.format.type=json_object,
        # поэтому модель НЕ обязана возвращать "чистый массив". Чтобы избежать
        # обёрток вида {"0":[...]} и частичных ответов, требуем фиксированную форму:
        # {"items":[ ... ]} и жёстко проверяем полноту по id.
        user_prompt = (
            f"{context_hint}"
            "Дан JSON-массив объектов вида {\"id\": число, \"name\": \"оригинал\", \"price\": число}.\n"
            "Переведи поле name на русский, сохрани цену.\n\n"
            "КРИТИЧЕСКИ ВАЖНО:\n"
            "- Верни РОВНО столько же элементов, сколько во входном массиве.\n"
            "- Верни ВСЕ элементы, ничего не пропускай.\n"
            "- id должен совпадать с входным id.\n"
            "- price должен совпадать с входным price.\n"
            "- Если не можешь перевести — поставь исходный name в label.\n"
            "- label делай КОРОТКИМ: убери размеры/коды/служебные маркеры.\n"
            "  * УДАЛЯЙ размеры (XS/S/M/L/XL, 35-45, UK4/UK10 и т.п.)\n"
            "  * УДАЛЯЙ коды вида uk?10, u?k6 и похожие\n"
            "  * НЕ пиши «цвет на фото/изображённый цвет/图片色»\n"
            "  * Если остаются только варианты питания/комплекта — оставь это (например: «на батарейках», «аккумуляторный»)\n"
            "- Запрещены китайские иероглифы и английские слова в label.\n"
            "- Запрещены любые дополнительные поля, кроме items/id/label/price.\n\n"
            "ФОРМАТ ОТВЕТА (строго, без markdown):\n"
            "{\"items\":[{\"id\":0,\"label\":\"перевод\",\"price\":123.45}]}\n\n"
            f"{payload}"
        )
        max_cap = int(getattr(settings, "OPENAI_MAX_OUTPUT_TOKENS", 2400) or 2400)
        # Выход: JSON с items[].
        # Даём запас, чтобы модель не обрезала JSON на товарах с большим числом вариантов.
        token_limit = min(max_cap, max(900, len(uniq) * 45))
        last_error = None

        for attempt in range(2):
            try:
                if settings.DEBUG_MODE:
                    logger.debug(
                        "[Prices][translate] Попытка %s | token_limit=%s | uniq=%s",
                        attempt + 1,
                        token_limit,
                        len(uniq),
                    )
                result = await self._call_translation_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    token_limit=token_limit,
                    temperature=0.0,
                )
                if isinstance(result, tuple):
                    response_text, tokens_usage = result
                else:
                    response_text = result
                data = self._parse_json_response(response_text)

                # Нормализуем возможные «обёртки» и извлекаем items
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    items_iter = data["items"]
                elif isinstance(data, list):
                    items_iter = data
                elif isinstance(data, dict):
                    items_iter = [data]
                else:
                    items_iter = []

                translated_map: dict[int, dict] = {}
                for item in items_iter:
                    if not isinstance(item, dict):
                        continue
                    try:
                        idx = int(item.get("id"))
                    except Exception:
                        # Если id нет — пропускаем, это нарушает контракт
                        continue
                    label = str(item.get("label") or item.get("name") or "").strip()
                    price = item.get("price")
                    try:
                        price_value = float(price)
                    except (TypeError, ValueError):
                        continue
                    if label:
                        # Цена должна совпадать с входной. Если модель «перепутала» — игнорируем элемент.
                        try:
                            if abs(price_value - float(uniq[idx]["price"])) > 1e-6:
                                continue
                        except Exception:
                            pass
                        translated_map[idx] = {"label": label, "price": price_value}

                # Жёстко требуем полноту: если вернули не все элементы — retry
                if len(translated_map) != len(uniq):
                    last_error = ValueError(
                        f"LLM вернул неполный перевод цен: {len(translated_map)}/{len(uniq)} элементов"
                    )
                    logger.error(
                        "[Prices][translate] Неполный результат | got=%s expected=%s | response_sample=%s",
                        len(translated_map),
                        len(uniq),
                        response_text[:500],
                    )
                    continue

                normalized = [translated_map[i] for i in range(len(uniq))]

                if normalized:
                    if isinstance(result, tuple) and self._current_tokens_usage:
                        try:
                            self._current_tokens_usage += tokens_usage
                        except Exception:
                            pass
                    # Финальная дедупликация по (label, price)
                    deduped: list[dict] = []
                    seen_pairs = set()
                    for item in normalized:
                        key = (item["label"].lower(), item["price"])
                        if key in seen_pairs:
                            continue
                        seen_pairs.add(key)
                        deduped.append(item)
                    return deduped
                last_error = ValueError("LLM вернул пустой список после перевода цен.")
                logger.error(
                    "[Prices][translate] Пустой список после парса JSON | payload_len=%s | response_sample=%s",
                    len(payload),
                    response_text[:500],
                )
            except json.JSONDecodeError as exc:
                logger.error(
                    "[Prices][translate] JSONDecodeError: %s | payload_len=%s | response_sample=%s",
                    exc,
                    len(payload),
                    (response_text[:500] if 'response_text' in locals() else 'N/A'),
                )
                last_error = exc
                token_limit = int(token_limit * 1.5) + 500
                continue
            except Exception as exc:
                logger.error(
                    "[Prices][translate] Ошибка вызова LLM: %s | payload_len=%s",
                    exc,
                    len(payload),
                )
                last_error = exc
                continue

        if last_error:
            logger.error(
                "[Prices][translate] Ошибка LLM перевода цен: %s | payload_len=%s",
                last_error,
                len(payload),
            )
            # Fallback для тестов и устойчивости: вернём честный перевод через generic-переводчик
            # (без группировки и без претензий к JSON-формату).
            try:
                unique_names = list({e["name"] for e in entries if e.get("name")})[:20]
                translated = []
                for name in unique_names:
                    t = await self._translate_text_generic(name, target_language="ru")
                    translated.append(t or name)
                fallback = []
                for e in entries:
                    nm = e.get("name") or ""
                    pr = e.get("price")
                    if pr is None:
                        continue
                    try:
                        pr_f = float(pr)
                    except (TypeError, ValueError):
                        continue
                    tr = translated[unique_names.index(nm)] if nm in unique_names else nm
                    fallback.append({"label": tr, "price": pr_f})
                if fallback:
                    logger.warning("[Prices][translate] Использован fallback-перевод (generic).")
                    return fallback
            except Exception:
                pass
            raise last_error
        return []

    def _summarize_translated_prices_locally(self, items: list[dict]) -> list[dict]:
        """
        Локальная суммаризация переведённых позиций по ценам без LLM.

        Идея:
        - извлекаем тип товара из label через _extract_product_type();
        - группируем по (тип, цена);
        - если в группе несколько вариантов (обычно размеры/цвета) — не добавляем никаких пометок,
          оставляем только тип товара.

        Важно: это сознательно заменяет LLM-суммаризацию, чтобы сократить токены и убрать лишние запросы.
        """
        grouped: dict[tuple[float, str], int] = {}

        for it in items or []:
            label = str(it.get("label") or "").strip()
            price = it.get("price")
            if not label:
                continue
            try:
                price_f = float(price)
            except (TypeError, ValueError):
                continue

            product_type = self._extract_product_type(label)
            if not product_type or product_type == "__INVALID__":
                product_type = "вариант"

            key = (price_f, product_type)
            grouped[key] = grouped.get(key, 0) + 1

        result: list[dict] = []
        for (price_f, product_type), cnt in sorted(grouped.items(), key=lambda x: x[0][0]):
            # ВАЖНО: не добавляем никаких «ассортиментных» пометок — пользователю достаточно типа товара.
            result.append({"label": product_type, "price": price_f})

        # финальная дедупликация
        unique: list[dict] = []
        seen_pairs = set()
        for item in result:
            key = (str(item.get("label") or "").lower(), float(item.get("price")))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            unique.append(item)
        return unique

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
                    result = await self._call_translation_json(
                        system_prompt="Ты профессиональный переводчик. Всегда отвечай JSON.",
                        user_prompt=user_prompt,
                        token_limit=token_limit,
                        temperature=0.0,
                    )
                    if isinstance(result, tuple):
                        response_text, tokens_usage = result
                    else:
                        response_text = result
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
                        if isinstance(result, tuple) and self._current_tokens_usage:
                            try:
                                self._current_tokens_usage += tokens_usage
                            except Exception:
                                pass
                        return [translated_map[idx] for idx in range(len(names))]
                except json.JSONDecodeError as exc:
                    logger.error(
                        "[Prices][variants] JSONDecodeError: %s | response_sample=%s",
                        exc,
                        (response_text[:500] if 'response_text' in locals() else 'N/A'),
                    )
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
            # translated_block может быть (text, tokens_usage)
            text_only = translated_block[0] if isinstance(translated_block, tuple) else translated_block
            if isinstance(translated_block, tuple) and self._current_tokens_usage:
                try:
                    self._current_tokens_usage += translated_block[1]
                except Exception:
                    pass
            splitted = [line.strip() for line in str(text_only).split("\n")]
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
        # Важно: не смешиваем близкие, но разные типы (например, "пиджак" != "куртка"),
        # иначе локальная группировка по ценам будет давать неверные подписи.
        type_markers = {
            'майка': ['майка', 'футболка', 'длинная футболка', 'длинный рукав', 'топ', 'блуза'],
            'шорты': ['шорты', 'короткие штаны', 'короткие брюки'],
            'брюки': ['брюки', 'длинные штаны', 'длинные брюки', 'штаны'],
            'рубашка': ['рубашка', 'сорочка'],
            'пиджак': ['пиджак', 'жакет', 'блейзер'],
            'куртка': ['куртка'],
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
        4. Если варианты разных типов → перечисляет типы.
           ВАЖНО: не добавляем никаких «ассортиментных» пометок.
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
                # ВАЖНО: не добавляем никаких «ассортиментных» пометок.
                
                # Простая эвристика: если все оригинальные названия содержат тип товара и отличаются только префиксом
                all_contain_type = all(product_type in orig.lower() for orig in unique_originals)
                if all_contain_type:
                    # Все варианты содержат тип товара - скорее всего отличаются только размерами
                    result.append(product_type)
                else:
                    # Варианты отличаются не только размерами, но пользователю это не нужно в подписи.
                    # Оставляем просто тип товара.
                    result.append(product_type)
        
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
            # Штаны/термоштаны часто встречаются в детской одежде и должны попадать в apparel-ветку
            "штан",
            "обув", "ботин", "кроссов", "туфл", "кеды", "носк", "бель",
            "колгот", "пижам", "комбинез", "скинни", "sneaker", "coat", "hoodie",
            "靴", "衣", "裙", "裤", "衫"
        )
        return any(marker in text for marker in apparel_markers)

    def _is_footwear_product(self, translated_title: str | None, product_data: dict) -> bool:
        """
        Грубая эвристика определения обуви.

        Нужна для того, чтобы у одежды и обуви были разные названия поля:
        - одежда: "Состав"
        - обувь: "Материал"
        """
        text_parts = [
            translated_title or "",
            product_data.get('title') or "",
            " ".join(product_data.get('category_path') or []),
        ]
        text = " ".join(text_parts).lower()
        footwear_markers = (
            "обув", "ботин", "кроссов", "туфл", "кеды", "сапог", "босонож", "шлеп", "сандал",
            "shoe", "shoes", "sneaker", "boots",
            "靴",
        )
        return any(marker in text for marker in footwear_markers)

    def _normalize_apparel_characteristics(
        self,
        apparel_kind: str,
        main_characteristics: dict,
        platform: str | None = None,
    ) -> dict:
        """
        Нормализует и ОГРАНИЧИВАЕТ характеристики для одежды/обуви.

        ВАЖНО (по требованиям):
        - Для одежды/обуви в характеристиках допускаются:
          1) Состав/Материал (если есть)
          2) Цвета (если есть)
          3) Размеры (если есть)
          4) Уточнения по размерам (если есть) - ТОЛЬКО для платформы SZWEGO!
        - Порядок блоков при выводе фиксированный: Состав/Материал → Цвета → Размеры → Уточнения по размерам.
        """
        if not isinstance(main_characteristics, dict) or not main_characteristics:
            return {}

        kind = (apparel_kind or "").strip().lower()
        is_footwear = kind == "footwear"

        # 1) Извлекаем "Состав/Материал" из любых похожих ключей (ткань/содержание волокон/материал)
        material_value: str | None = None
        for k, v in list(main_characteristics.items()):
            key_l = str(k).strip().lower()
            if any(tok in key_l for tok in ("состав", "материал", "ткан", "волокон")):
                if isinstance(v, str) and v.strip():
                    material_value = v.strip()
                    break

        # 2) Извлекаем "Цвета"
        colors_value = None
        for k, v in list(main_characteristics.items()):
            key_l = str(k).strip().lower()
            if "цвет" in key_l or "color" in key_l:
                colors_value = v
                break

        # 3) Извлекаем "Размеры" (но НЕ "Уточнения по размерам")
        sizes_value: str | None = None
        for k, v in list(main_characteristics.items()):
            key_l = str(k).strip().lower()
            if ("размер" in key_l or "size" in key_l) and "уточнен" not in key_l:
                if isinstance(v, str) and v.strip():
                    sizes_value = v.strip()
                    break

        # 4) Извлекаем "Уточнения по размерам"
        size_details_value = None
        for k, v in list(main_characteristics.items()):
            key_l = str(k).strip().lower()
            if "уточнен" in key_l and "размер" in key_l:
                if v and (isinstance(v, list) and len(v) > 0 or isinstance(v, str) and v.strip()):
                    size_details_value = v
                    break

        normalized: dict = {}

        # Поле 1: Состав/Материал
        if material_value:
            key = "Материал" if is_footwear else "Состав"
            # Для одежды предпочитаем "Состав", даже если модель вернула "Материал"
            normalized[key] = material_value

        # Поле 2: Цвета (всегда список, если удаётся)
        if colors_value:
            def _sanitize_color_item(item: str) -> str | None:
                # Убираем упоминания пола/возраста и SKU-коды из "цветов".
                # Примеры, которые должны исчезнуть:
                # - "мужской-02", "женский-31"
                # Примеры, которые должны остаться:
                # - "светло-серый" (в т.ч. если было "мужской-16 (светло-серый)")
                s = (item or "").strip()
                if not s:
                    return None
                try:
                    import re

                    # 1) Если есть скобки с реальным цветом — берём содержимое скобок
                    m = re.search(r"\(([^)]+)\)", s)
                    if m:
                        inside = (m.group(1) or "").strip()
                        if inside and (self.COLOR_REGEX.search(inside.lower()) or any(x in inside.lower() for x in ("принт", "узор", "рисунок", "клетк", "полоск", "мрамор", "камуфляж"))):
                            s = inside

                    # 2) Удаляем гендер/возраст (и их производные) + англ. варианты
                    s = re.sub(
                        r"(?i)\b(мужск\w*|женск\w*|унисекс|для\s+мальчик\w*|для\s+девочк\w*|детск\w*|подрост\w*|kids?|child(?:ren)?|baby|boy(?:s)?|girl(?:s)?|men|women|male|female)\b",
                        "",
                        s,
                    )
                    # 3) Удаляем типичные SKU-хвосты: "-02", "_08", " 13" и т.п.
                    s = re.sub(r"(?i)[-_ ]?\d{1,4}\b", "", s)
                    # 4) Схлопываем мусор
                    s = re.sub(r"\s{2,}", " ", s).strip(" -_/;:,").strip()

                    # 5) Оставляем только если похоже на цвет/принт
                    low = s.lower()
                    if not low:
                        return None
                    if self.COLOR_REGEX.search(low):
                        return s
                    if any(mrk in low for mrk in ("принт", "узор", "рисунок", "клетк", "полоск", "мрамор", "камуфляж", "градиент")):
                        return s
                    return None
                except Exception:
                    # В случае ошибки — лучше выкинуть, чем протащить "мужской-02" в пост.
                    return None

            if isinstance(colors_value, str):
                cleaned = _sanitize_color_item(colors_value)
                if cleaned:
                    normalized["Цвета"] = [cleaned]
            elif isinstance(colors_value, list):
                out: list[str] = []
                for c in colors_value:
                    if not isinstance(c, str):
                        continue
                    cleaned = _sanitize_color_item(c)
                    if cleaned:
                        out.append(cleaned)
                if out:
                    # Убираем дубликаты, сохраняя порядок
                    seen = set()
                    uniq: list[str] = []
                    for x in out:
                        k = x.strip().lower()
                        if k and k not in seen:
                            seen.add(k)
                            uniq.append(x)
                    if uniq:
                        normalized["Цвета"] = uniq

        # Поле 3: Размеры (строка)
        if sizes_value:
            cleaned_sizes = self._sanitize_apparel_sizes(sizes_value)
            if cleaned_sizes:
                normalized["Размеры"] = self._format_size_range(cleaned_sizes)

        # Поле 4: Уточнения по размерам (список или строка) - ТОЛЬКО для платформы SZWEGO!
        if size_details_value and platform and platform.lower() == "szwego":
            # Сохраняем как есть (список или строка)
            # Проверяем, что значение не пустое
            if isinstance(size_details_value, list) and len(size_details_value) > 0:
                # Убираем пустые элементы из списка
                cleaned_list = [str(item).strip() for item in size_details_value if item and str(item).strip()]
                if cleaned_list:
                    normalized["Уточнения по размерам"] = cleaned_list
            elif isinstance(size_details_value, str) and size_details_value.strip():
                normalized["Уточнения по размерам"] = size_details_value.strip()

        return normalized

    def _sanitize_apparel_sizes(self, sizes_str: str) -> str | None:
        """
        Санитизация размера для одежды/обуви.

        Требования:
        - Если указан ТОЛЬКО "универсальный/one size/均码/единый размер" — поле "Размеры" НЕ выводим.
        - Если указано смешанно (например, "универсальный/42-48") — удаляем "универсальный" и оставляем только "42-48".

        Возвращает:
        - str: очищенная строка размеров
        - None: если после очистки значимых размеров не осталось
        """
        s = (sizes_str or "").strip()
        if not s:
            return None

        import re

        # Нормализуем разделители (/, |, ;, запятые) → запятая
        normalized = re.sub(r"[|/;]+", ",", s)
        normalized = normalized.replace("，", ",")
        # Иногда размеры приходят через пробелы
        normalized = re.sub(r"\s{2,}", " ", normalized).strip()

        raw_parts = [p.strip() for p in re.split(r"[,]+", normalized) if p.strip()]
        if not raw_parts:
            return None

        # Маркеры "универсального" размера, которые не несут ценности в посте
        universal_markers = (
            "универсальный", "универсал", "единый размер", "единственный размер",
            "one size", "onesize", "one-size", "free size", "freesize",
            "均码", "均一", "均",  # китайские варианты "единый размер"
        )

        def _is_universal(token: str) -> bool:
            t = (token or "").strip().lower()
            if not t:
                return False
            # Убираем скобки/лишние символы, чтобы "универсальный (one size)" тоже отфильтровался
            t = re.sub(r"[\[\](){}/\\|]+", " ", t)
            t = re.sub(r"\s{2,}", " ", t).strip()
            return any(m in t for m in universal_markers)

        # Разбиваем части дополнительно по пробелам, если вдруг пришло "универсальный 42-48"
        exploded: list[str] = []
        for part in raw_parts:
            if not part:
                continue
            # если есть явный диапазон/размеры вместе со словами — оставляем как отдельный токен, не режем по пробелам
            if re.search(r"\d", part) and any(sep in part for sep in ("-", "–", "—")):
                exploded.append(part)
                continue
            # иначе режем по пробелам, чтобы убрать "one size"
            for t in re.split(r"\s+", part):
                if t.strip():
                    exploded.append(t.strip())

        parts = [p for p in exploded if p and not _is_universal(p)]
        if not parts:
            return None

        # Возвращаем обратно в строку:
        # - Если остался один диапазон/размер — оставляем как есть
        # - Если несколько — через ", "
        return ", ".join(parts)

    def _sanitize_gender_age_from_title(self, text: str) -> str:
        """
        Убирает из заголовка любые упоминания пола/возраста (по требованиям).

        Примеры:
        - "брюки для детей" -> "брюки"
        - "женские кроссовки" -> "кроссовки"
        """
        s = (text or "").strip()
        if not s:
            return s
        try:
            import re
            # удаляем "для детей/мальчиков/девочек" целиком
            s = re.sub(r"(?i)\bдля\s+(детей|реб[её]нк\w*|мальчик\w*|девочк\w*)\b", "", s)
            # удаляем прилагательные/маркеры пола и возраста
            s = re.sub(r"(?i)\b(мужск\w*|женск\w*|унисекс|детск\w*|подрост\w*)\b", "", s)
            s = re.sub(r"\s{2,}", " ", s).strip(" -—,:;").strip()
            return s or (text or "").strip()
        except Exception:
            return (text or "").strip()

    def _remove_sizes_from_title(self, title: str) -> str:
        """
        Удаляет размеры из названия товара.
        Размеры могут быть в разных форматах: "35 × 24 × 17 см", "35x24x17", "35-24-17", "35 24 17" и т.п.
        
        Args:
            title: Название товара
            
        Returns:
            str: Название без размеров
        """
        if not title:
            return title
        
        try:
            import re
            
            # Паттерны для различных форматов размеров:
            # - "35 × 24 × 17 см", "35x24x17", "35-24-17", "35 24 17"
            # - "35×24×17см", "35 x 24 x 17 см"
            # - "35×24×17", "35 x 24 x 17"
            # - "35×24", "35 x 24"
            # - "35 см", "35см", "35cm"
            # - "35-40", "35/40", "S-M", "S, M, L"
            
            # Удаляем размеры в формате "число × число × число" (с единицами измерения или без)
            title = re.sub(r'\d+\s*[×xX]\s*\d+\s*[×xX]\s*\d+\s*(?:см|cm|mm|м|m)?', '', title, flags=re.IGNORECASE)
            
            # Удаляем размеры в формате "число × число" (с единицами измерения или без)
            title = re.sub(r'\d+\s*[×xX]\s*\d+\s*(?:см|cm|mm|м|m)?', '', title, flags=re.IGNORECASE)
            
            # Удаляем размеры в формате "число-число" или "число/число" (диапазоны)
            title = re.sub(r'\d+\s*[-/]\s*\d+\s*(?:см|cm|mm|м|m)?', '', title, flags=re.IGNORECASE)
            
            # Удаляем размеры в формате "число, число, число" (списки)
            title = re.sub(r'\d+\s*,\s*\d+\s*,\s*\d+\s*(?:см|cm|mm|м|m)?', '', title, flags=re.IGNORECASE)
            
            # Удаляем размеры в формате "число, число" (списки из двух)
            title = re.sub(r'\d+\s*,\s*\d+\s*(?:см|cm|mm|м|m)?', '', title, flags=re.IGNORECASE)
            
            # Удаляем одиночные размеры с единицами измерения в конце названия
            title = re.sub(r'\s+\d+\s*(?:см|cm|mm|м|m)\s*$', '', title, flags=re.IGNORECASE)
            
            # Удаляем размеры в формате "S-M", "S/M", "S, M, L" (буквенные размеры)
            # Но только если они в конце названия или после пробела
            title = re.sub(r'\s+[A-ZА-ЯЁ]\s*[-/]\s*[A-ZА-ЯЁ]\s*$', '', title)
            title = re.sub(r'\s+[A-ZА-ЯЁ]\s*,\s*[A-ZА-ЯЁ]\s*,\s*[A-ZА-ЯЁ]\s*$', '', title)
            
            # Очищаем множественные пробелы и пробелы в начале/конце
            title = re.sub(r'\s+', ' ', title).strip()
            
            return title
        except Exception:
            return (title or "").strip()

    def _strip_gender_age_sentences(self, text: str) -> str:
        """
        Для description: удаляем предложения, которые содержат упоминания пола/возраста.
        Это безопаснее, чем "вырезать слова" (чтобы не получить ломаный текст).
        """
        s = (text or "").strip()
        if not s:
            return s
        try:
            import re
            parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", s) if p.strip()]
            if not parts:
                return s
            bad = re.compile(
                r"(?i)\b(мужск\w*|женск\w*|унисекс|детск\w*|подрост\w*|для\s+(детей|реб[её]нк\w*|мальчик\w*|девочк\w*)|kids?|child(?:ren)?|baby|boy(?:s)?|girl(?:s)?|men|women|male|female)\b"
            )
            kept = [p for p in parts if not bad.search(p)]
            return " ".join(kept).strip() or s
        except Exception:
            return s

    def _remove_meta_comments_from_description(self, description: str) -> str:
        """
        Удаляет мета-комментарии о самом описании или источнике данных из description.
        Запрещены фразы типа: "В описании указаны...", "производитель указал", "в данных указано" и т.п.
        
        Args:
            description: Текст описания товара
            
        Returns:
            str: Описание без мета-комментариев
        """
        if not description:
            return description
        
        try:
            import re
            
            # Разбиваем на предложения для более точной фильтрации
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", description) if s.strip()]
            if not sentences:
                return description
            
            # Паттерны для мета-комментариев
            meta_patterns = [
                r"(?i)^в\s+описании\s+",  # "В описании указаны...", "В описании упомянуты..."
                r"(?i)\bв\s+описании\s+указан",  # "в описании указаны"
                r"(?i)\bв\s+описании\s+упомянут",  # "в описании упомянуты"
                r"(?i)\bпроизводитель\s+указал",  # "производитель указал"
                r"(?i)\bстрана\s+производства\s+указана",  # "страна производства указана"
                r"(?i)\bв\s+данных\s+указано",  # "в данных указано"
                r"(?i)\bв\s+характеристиках\s+указано",  # "в характеристиках указано"
                r"(?i)\bв\s+информации\s+указано",  # "в информации указано"
                r"(?i)\bв\s+спецификации\s+указано",  # "в спецификации указано"
                r"(?i)\bсогласно\s+описанию",  # "согласно описанию"
                r"(?i)\bпо\s+описанию",  # "по описанию"
                r"(?i)\bв\s+описании\s+есть",  # "в описании есть"
                r"(?i)\bв\s+описании\s+присутствует",  # "в описании присутствует"
            ]
            
            # Фильтруем предложения, содержащие мета-комментарии
            filtered_sentences = []
            for sentence in sentences:
                # Проверяем, содержит ли предложение мета-комментарий
                is_meta = False
                for pattern in meta_patterns:
                    if re.search(pattern, sentence):
                        is_meta = True
                        break
                
                # Если это не мета-комментарий, добавляем предложение
                if not is_meta:
                    filtered_sentences.append(sentence)
            
            # Собираем обратно в текст
            result = " ".join(filtered_sentences).strip()
            
            # Если после фильтрации осталась пустая строка, возвращаем исходную
            # (чтобы не потерять весь description из-за ошибки фильтрации)
            return result if result else description
        except Exception:
            # В случае ошибки возвращаем исходный текст
            return description

    def _remove_article_codes_from_title(self, title: str) -> str:
        """
        Удаляет артикулы, SKU, ID и коды товара из названия.
        
        Args:
            title: Название товара
            
        Returns:
            str: Название без артикулов и кодов
        """
        if not title:
            return title
        
        try:
            import re
            
            # Паттерны для артикулов и кодов:
            # - "Артикул: ABC123", "SKU: XYZ", "ID: 12345"
            # - "ABC123", "SKU-123", "ID-456"
            # - "Арт. ABC123", "Арт.ABC123"
            # - Коды в скобках: "(ABC123)", "[SKU-123]"
            # - Коды в конце: "Товар ABC123", "Товар SKU-123"
            
            # Удаляем артикулы и коды в формате "Артикул: ...", "SKU: ...", "ID: ..."
            title = re.sub(r"(?i)\b(артикул|sku|id|код)\s*:?\s*\S+", "", title)
            
            # Удаляем артикулы в формате "Арт. ..." или "Арт.ABC123"
            title = re.sub(r"(?i)\bарт\.?\s*\S+", "", title)
            
            # Удаляем коды в скобках: "(ABC123)", "[SKU-123]", "{ID-456}"
            title = re.sub(r"[\[\(]\s*(?:артикул|sku|id|код)\s*:?\s*\S+\s*[\]\)]", "", title, flags=re.IGNORECASE)
            title = re.sub(r"[\[\(]\s*[A-Z0-9\-_]+\s*[\]\)]", "", title)  # Простые коды в скобках
            
            # Удаляем коды в конце названия: "Товар ABC123", "Товар SKU-123"
            title = re.sub(r"\s+(?:артикул|sku|id|код)\s*:?\s*[A-Z0-9\-_]+$", "", title, flags=re.IGNORECASE)
            title = re.sub(r"\s+[A-Z]{2,}\d+[A-Z0-9\-_]*$", "", title)  # Коды типа "ABC123", "SKU-123"
            
            # Очищаем множественные пробелы и пробелы в начале/конце
            title = re.sub(r'\s+', ' ', title).strip()
            
            return title
        except Exception:
            return (title or "").strip()

    def _remove_color_words(self, text: str) -> str:
        if not text:
            return ""
        cleaned = self.COLOR_REGEX.sub("", text)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = cleaned.replace(" ,", ",").replace(" /", "/")
        return cleaned.strip(" ,./-")

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

    def _parse_json_response(self, text_or_tuple: str | tuple[str, TokensUsage]) -> dict | list:
        """
        Парсит JSON-ответ, обрабатывая как старую сигнатуру (str), так и новую (tuple[str, TokensUsage]).
        
        Args:
            text_or_tuple: Строка JSON или кортеж (строка, TokensUsage)
        
        Returns:
            dict | list: Распарсенный JSON
        """
        # Извлекаем текст из кортежа, если это новая сигнатура
        if isinstance(text_or_tuple, tuple):
            text, _ = text_or_tuple
        else:
            text = text_or_tuple
        
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
    ) -> str | tuple[str, TokensUsage]:
        """
        Вызывает метод generate_json_response для переводческого клиента.
        
        Returns:
            str: Текст ответа (старая сигнатура)
            tuple[str, TokensUsage]: Текст ответа и статистика токенов (новая сигнатура для OpenAI/ProxyAPI)
        """
        generator = getattr(self.translation_client, "generate_json_response", None)
        if not callable(generator):
            raise RuntimeError("Активный переводческий провайдер не поддерживает JSON-ответы.")

        # Централизованно ограничиваем max_output_tokens, чтобы не раздувать вызовы.
        max_tokens_cap = int(getattr(settings, "OPENAI_MAX_OUTPUT_TOKENS", 2400) or 2400)
        if max_tokens_cap > 0:
            token_limit = min(token_limit, max_tokens_cap)

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

        if settings.DEBUG_MODE:
            try:
                logger.debug(
                    "[Translation][request] max_tokens=%s, temperature=%s\n--- system ---\n%s\n--- user ---\n%s\n",
                    kwargs.get("max_output_tokens") or kwargs.get("max_tokens"),
                    kwargs.get("temperature"),
                    (system_prompt or "")[:1200],
                    (user_prompt or "")[:1200],
                )
            except Exception:
                pass

        result = await generator(**kwargs)
        # Новая сигнатура: возвращает кортеж (text, tokens_usage) для OpenAI/ProxyAPI
        if settings.DEBUG_MODE:
            try:
                if isinstance(result, tuple):
                    text_part = result[0]
                else:
                    text_part = result
                logger.debug(
                    "[Translation][response] len=%s | preview:\n%s",
                    len(text_part) if hasattr(text_part, "__len__") else "-",
                    str(text_part)[:1200],
                )
            except Exception:
                pass
        return result

    async def _translate_text_generic(
        self, text: str, target_language: str = "ru"
    ) -> str:
        """
        Универсальный переводчик: использует выбранный translation_client.
        
        Returns:
            str: Переведённый текст
        """
        if not text:
            return text

        translator = getattr(self.translation_client, "translate_text", None)
        if callable(translator):
            try:
                result = await translator(text, target_language=target_language)
                # Поддержка кортежа (text, tokens_usage)
                if isinstance(result, tuple):
                    translated, tokens_usage = result
                    if self._current_tokens_usage:
                        try:
                            self._current_tokens_usage += tokens_usage
                        except Exception:
                            pass
                else:
                    translated = result
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

        # Нормализация странных кодов размеров из некоторых источников (TMAPI):
        # "u?k4,u?k6,uk?8,uk?10,u?k12" -> "UK4 UK6 UK8 UK10 UK12"
        try:
            import re

            normalized = sizes_str
            normalized = re.sub(r"(?i)\bu\?k(\d+)\b", r"UK\1", normalized)
            normalized = re.sub(r"(?i)\buk\?(\d+)\b", r"UK\1", normalized)
            sizes_str = normalized
        except Exception:
            pass
            
        # Стандартные размеры одежды в порядке
        standard_sizes = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        
        # Разбиваем строку на части и очищаем
        sizes_raw = [s.strip() for s in sizes_str.replace(',', ' ').split() if s.strip()]

        # Обработка UK-размеров: UK4, UK6, UK8... -> UK4-UK12
        try:
            import re

            uk_nums: list[int] = []
            for token in sizes_raw:
                m = re.fullmatch(r"(?i)UK(\d{1,3})", token.strip())
                if not m:
                    uk_nums = []
                    break
                uk_nums.append(int(m.group(1)))
            if uk_nums:
                uk_sorted = sorted(set(uk_nums))
                if len(uk_sorted) >= 3:
                    # Если размеры идут с шагом 1 или 2 (UK часто чётные), показываем диапазон
                    step_ok = all((uk_sorted[i + 1] - uk_sorted[i]) in (1, 2) for i in range(len(uk_sorted) - 1))
                    if step_ok:
                        return f"UK{uk_sorted[0]}-UK{uk_sorted[-1]}"
                # Иначе перечисляем как есть в порядке
                return ", ".join(f"UK{n}" for n in uk_sorted)
        except Exception:
            pass
        
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

    def _ensure_lowercase_characteristic_value(self, key: str, value: str) -> str:
        """
        Гарантирует, что значение характеристики после двоеточия начинается со строчной буквы.

        ВАЖНО:
        - Для размеров (S, M, L, XL и т.п.) и размерных диапазонов не меняем регистр,
          чтобы не превратить "S, M, L" в "s, M, L".
        - Для бренда/марки не меняем регистр, чтобы не портить написание (например, "Lusimary").
        """
        s = (value or "").strip()
        if not s:
            return s

        key_l = (key or "").strip().lower()
        if "бренд" in key_l or "brand" in key_l:
            return s

        # Если значение начинается с цифры/символа — оставляем как есть (например, "30 мл")
        first_char = s[0]
        if first_char.isdigit() or first_char in "+-*/(":
            return s

        # Исключение: размеры/размерные ряды
        if "размер" in key_l or "size" in key_l:
            return s

        import re
        size_token = r"(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|XXXXL)"
        # "S, M, L" / "XS-XL" / "35-40" — не трогаем
        if re.fullmatch(rf"{size_token}(\s*,\s*{size_token})+", s):
            return s
        if re.fullmatch(rf"{size_token}\s*[-–]\s*{size_token}", s):
            return s

        # По умолчанию: делаем строчной первую букву
        return self._ensure_lowercase_bullet(s)

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
                # Запрещаем любые «ассортиментные» пометки в пользовательском тексте
                label_raw = str(entry.get("label") or "")
                try:
                    import re
                    label_raw = re.sub(r"(?i)\s*\(.*?в\s+ассортименте.*?\)\s*", " ", label_raw)
                    label_raw = re.sub(r"(?i)\bв\s+ассортименте\b", "", label_raw)
                    label_raw = re.sub(r"\s{2,}", " ", label_raw).strip(" ,;:-").strip()
                except Exception:
                    pass
                label = self._ensure_lowercase_bullet(label_raw)
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
        price_lines: list | None = None,
        hashtags: list[str] | None = None
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
        # Используем подпись пользователя (может быть пустой)
        user_signature = (signature or "").strip()
        # Извлекаем данные из LLM ответа
        title = llm_content.get('title', 'Товар')
        description = llm_content.get('description', '')
        main_characteristics = llm_content.get('main_characteristics', {})
        additional_info = llm_content.get('additional_info', {})
        # Хэштеги больше не извлекаются из llm_content, они передаются отдельным параметром
        emoji = llm_content.get('emoji', '')

        # По требованиям: запрещены любые упоминания пола/возраста и размеры в названии.
        # Чистим сразу, чтобы не протащить это в финальный пост даже при ошибке LLM.
        try:
            if isinstance(title, str):
                title = self._sanitize_gender_age_from_title(title)
                title = self._remove_sizes_from_title(title)
                title = self._remove_article_codes_from_title(title)
            if isinstance(description, str):
                description = self._strip_gender_age_sentences(description)
                description = self._remove_meta_comments_from_description(description)
            # Если LLM вдруг добавил "мужской/женский/детский" в названия характеристик — выкидываем такие поля.
            if isinstance(main_characteristics, dict) and main_characteristics:
                import re
                bad_key = re.compile(r"(?i)\b(мужск\w*|женск\w*|унисекс|детск\w*|подрост\w*)\b")
                for k in list(main_characteristics.keys()):
                    if bad_key.search(str(k)):
                        main_characteristics.pop(k, None)
                # Также запрещены гендерные/возрастные упоминания в ЗНАЧЕНИЯХ характеристик
                # (особенно в "Цвета", где модель иногда вставляет "для мальчиков/для девочек").
                bad_value = re.compile(r"(?i)\b(для\s+мальчик\w*|для\s+девочк\w*|мальчик\w*|девочк\w*|мужск\w*|женск\w*|унисекс)\b")
                for k in list(main_characteristics.keys()):
                    v = main_characteristics.get(k)
                    if isinstance(v, str):
                        if bad_value.search(v):
                            main_characteristics.pop(k, None)
                    elif isinstance(v, list):
                        cleaned_list = []
                        for item in v:
                            if not isinstance(item, str):
                                continue
                            if bad_value.search(item):
                                continue
                            cleaned_list.append(item)
                        if cleaned_list:
                            main_characteristics[k] = cleaned_list
                        else:
                            main_characteristics.pop(k, None)
                
                # Фильтруем характеристики, описывающие назначение или способ использования товара
                # Такие характеристики не нужны - пользователь сам решает, как использовать товар
                forbidden_characteristics = [
                    "назначение", "способ использования", "применение", "использование",
                    "для чего", "кому подходит", "варианты использования", "условия применения",
                    "сфера применения", "цель использования", "область применения",
                    "как использовать", "способ применения", "назначение товара"
                ]
                forbidden_key_pattern = re.compile(
                    r"(?i)\b(" + "|".join(forbidden_characteristics) + r")\b"
                )
                for k in list(main_characteristics.keys()):
                    if forbidden_key_pattern.search(str(k)):
                        main_characteristics.pop(k, None)
                
                # Также фильтруем "Конструкция", если она описывает способ использования
                # (например, "двухвариантное ношение", "сменная конструкция")
                if "Конструкция" in main_characteristics:
                    construction_value = str(main_characteristics.get("Конструкция", "")).lower()
                    usage_patterns = [
                        r"двухвариантн", r"сменн", r"вариант.*ношени", r"способ.*ношени",
                        r"ношени", r"использовани", r"применени"
                    ]
                    if any(re.search(pattern, construction_value) for pattern in usage_patterns):
                        main_characteristics.pop("Конструкция", None)
        except Exception:
            pass

        # Для одежды/обуви фиксируем строгий формат характеристик:
        # допускаются (и строго в этом порядке при выводе):
        # - Состав/Материал
        # - Цвета
        # - Размеры
        # - Уточнения по размерам (если есть) - ТОЛЬКО для платформы SZWEGO!
        #
        # Это делаем ДО санитации description, чтобы анти-дублирование работало корректно.
        try:
            looks_like_apparel = self._is_apparel_product(title, product_data)
            if looks_like_apparel:
                apparel_kind = "footwear" if self._is_footwear_product(title, product_data) else "clothing"
                # Получаем платформу из product_data для проверки, нужны ли "Уточнения по размерам"
                platform = product_data.get('_platform')
                main_characteristics = self._normalize_apparel_characteristics(apparel_kind, main_characteristics, platform)
                # Для одежды/обуви доп. секции в посте не используем (чтобы не уехал шаблон)
                additional_info = {}
        except Exception:
            pass
        
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
            # Санитация description: не допускаем цену и измеримые конкретики в описании.
            # Такие данные должны идти в характеристиках/ценовом блоке ниже.
            try:
                def _strip_bad_sentences(text: str) -> str:
                    import re

                    # Разделяем на предложения максимально простым способом
                    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
                    if not parts:
                        return text.strip()

                    bad_patterns = [
                        r"(?i)\bцена\b",
                        r"[¥₽$€]",
                        r"(?i)\b(руб|юан|cny|rmb|usd|eur)\b",
                        r"(?i)\b(объ[её]м|вес|размер|габарит|длина|ширина|высота|диаметр)\b",
                        r"(?i)\b(мм|см|м|л|мл|г|кг)\b",
                        r"(?i)\b(\d+(\.\d+)?)\b\s*(мм|см|м|л|мл|г|кг)\b",
                        # Запрещаем даты/время производства/сроки
                        r"(?i)\b(дата|время)\s+(изготовлен|изготовления|производств|выпуска)\b",
                        r"(?i)\bизготовлен(о|а|ы)?\b",
                        r"(?i)\bпроизведен(о|а|ы)?\b",
                        r"(?i)\b(партия|серия|batch)\b",
                        r"(?i)\b(год|месяц|срок)\b",
                        # Месяцы (любые склонения) — часто используются для «произведён в ноябре»
                        r"(?i)\b(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*\b",
                        # Явные форматы дат (21.10, 2024-11, 2024/11/03 и т.п.)
                        r"\b\d{1,2}[./-]\d{1,2}\b",
                        r"\b20\d{2}[./-]\d{1,2}([./-]\d{1,2})?\b",
                        # Запрещённые «рассуждения»/классификации
                        r"(?i)относит(ся|ься)\s+к\s+категор",
                        r"(?i)\bкатегори(я|и|ей)\b",
                        r"(?i)\bподходит\s+для\b",
                        r"(?i)\bдля\s+близких\b",
                        r"(?i)\bдля\s+родных\b",
                        r"(?i)\bтуристическ(ий|ая|ое)\b",
                        # Канцелярит и неестественные формулировки (встречались в compact_v2)
                        r"(?i)\bформат\s+исполнени[яе]\b",
                        r"(?i)\bпредставлен[ао]?\s+вариантами\b",
                        r"(?i)\bкак\s+по\s+отдельности\b",
                        r"(?i)\bреализует(ся|ься)\s+отдельно\b",
                        r"(?i)\bвариант(ы|ов)\s+отдельн(ых|ые)\s+позиц",
                    ]

                    filtered: list[str] = []
                    for p in parts:
                        p_stripped = p.strip()
                        if any(re.search(pat, p_stripped) for pat in bad_patterns):
                            # выкидываем предложение с ценой/единицами измерения
                            continue
                        # Дополнительный жёсткий фильтр: "Цена 14.5." даже без валюты
                        if re.search(r"(?i)^цена\s+\d", p_stripped):
                            continue
                        filtered.append(p_stripped)

                    return " ".join(filtered).strip() or text.strip()

                description = _strip_bad_sentences(description)
            except Exception:
                pass

            # Если в характеристиках есть «Цвета», то упоминания цветов в description считаем лишними
            # и стараемся убрать типичные фразы «в различных цветах», «доступны цвета: ...», «цвета: ...».
            try:
                import re
                mc_for_desc = main_characteristics if isinstance(main_characteristics, dict) else {}
                colors_val = mc_for_desc.get("Цвета") or mc_for_desc.get("Цвет")
                if colors_val:
                    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", description.strip()) if p.strip()]
                    cleaned_parts: list[str] = []
                    for p in parts:
                        p_l = p.lower()
                        # Удаляем предложения, где явно перечисляют/обсуждают цвета
                        if (
                            "цвет" in p_l
                            and ("доступ" in p_l or ":" in p or "переч" in p_l or "различн" in p_l)
                        ):
                            continue
                        cleaned_parts.append(p)
                    description = " ".join(cleaned_parts).strip() or description.strip()
            except Exception:
                pass

            # Анти-дублирование: если в характеристиках есть «Упаковка/Инструменты/Материал/Состав/Размер/Объём»,
            # то удаляем типовые предложения в description, которые повторяют эти факты.
            try:
                import re
                mc_for_desc = main_characteristics if isinstance(main_characteristics, dict) else {}
                keys = " ".join(str(k).lower() for k in mc_for_desc.keys())
                parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", description.strip()) if p.strip()]
                cleaned_parts: list[str] = []
                for p in parts:
                    p_l = p.lower()
                    # Упаковка/коробка/тюбик/мешок и т.п. — часто дублируется и даёт «воду»
                    if ("упаков" in keys or "упаков" in p_l) and any(w in p_l for w in ("упак", "короб", "пакет", "тюбик", "флакон", "бутыл", "мешок")):
                        # оставляем только если речь явно про необычный дизайн (матрёшка/футляр/кейс)
                        if not any(w in p_l for w in ("матр", "футляр", "кейс", "шкатул", "подарочн")):
                            continue
                    # Инструменты: не дублируем перечисления и не пишем «нет инструментов»
                    if ("инструмент" in keys or "инструмент" in p_l) and any(w in p_l for w in ("инструмент", "комплект", "набор включает")):
                        continue
                    # Материал/состав/объём/размер — тоже только в характеристиках
                    if any(w in keys for w in ("материал", "состав", "объём", "объем", "размер")) and any(w in p_l for w in ("материал", "состав", "объём", "объем", "размер")):
                        continue
                    cleaned_parts.append(p)
                description = " ".join(cleaned_parts).strip() or description.strip()
            except Exception:
                pass

            post_parts.append(f"<blockquote><i>{description}</i></blockquote>")
            post_parts.append("")
        
        # Основные характеристики
        if main_characteristics:
            # Список неопределенных/пустых значений для фильтрации
            invalid_values = [
                'другие материалы', 'прочие материалы', 'неизвестно', 
                'смешанные материалы', 'other materials', 'unknown', 
                'mixed', 'various', 'прочие', 'другие', 'не указано',
                'другое', 'иной', 'иное', 'другой', 'прочее',
                # Частые «мусорные» формулировки про ткань/материал, которые нельзя показывать пользователю
                'другая ткань', 'другие ткани', 'иная ткань', 'прочая ткань',
                # Слишком общие значения — это НЕ состав
                'ткань', 'материал', 'текстиль',
                'не указан', 'не указана', 'не указаны',
                'нет информации', 'нет данных', 'no information',
                'not specified', 'н/д', 'n/a', '', 'нет', 'none', 'null', 'не применимо', 'отсутствует'
            ]
            
            # Фильтруем и отображаем характеристики в правильном порядке
            # Порядок: Состав/Материал → Цвета → Размеры/Объём → Уточнения по размерам (только для SZWEGO) → Остальное
            ordered_keys = []
            
            # Сначала состав/материал (если есть и он конкретный)
            for key in main_characteristics.keys():
                if 'материал' in key.lower() or 'состав' in key.lower():
                    value = main_characteristics[key]
                    # Проверяем что значение не пустое и не из списка неопределенных
                    if value and isinstance(value, str) and value.strip():
                        v0 = value.lower().strip()
                        if v0 in invalid_values:
                            continue
                        # Дополнительная страховка: «другая/прочая/иная ткань/материал» в разных вариациях
                        try:
                            import re
                            if re.search(r"(?i)\b(друг\w*|проч\w*|ин\w*)\b.*\b(ткан|материал)\b", value):
                                continue
                            # «Состав: ткань/материал/текстиль» — слишком общее, пропускаем
                            if re.fullmatch(r"(?i)\s*(ткань|материал|текстиль)\s*", value):
                                continue
                        except Exception:
                            pass
                        ordered_keys.append(key)
            
            # Затем цвета
            for key in main_characteristics.keys():
                if 'цвет' in key.lower() or 'color' in key.lower():
                    value = main_characteristics[key]
                    # Проверяем что цвета не пустые
                    if value and (isinstance(value, list) and len(value) > 0 or isinstance(value, str) and value.strip()):
                        ordered_keys.append(key)
            
            # Затем размеры и объёмы (но НЕ "Уточнения по размерам")
            for key in main_characteristics.keys():
                key_lower = key.lower()
                if ('размер' in key_lower or 'size' in key_lower or 'объём' in key_lower or 'объем' in key_lower) and 'уточнен' not in key_lower:
                    value = main_characteristics[key]
                    # Проверяем что значение не пустое и не "не указан"
                    if value and isinstance(value, str) and value.strip() and value.lower().strip() not in invalid_values:
                        ordered_keys.append(key)
            
            # Затем "Уточнения по размерам" (после обычных размеров) - ТОЛЬКО для платформы SZWEGO!
            platform = product_data.get('_platform')
            if platform and platform.lower() == "szwego":
                for key in main_characteristics.keys():
                    if 'уточнен' in key.lower() and 'размер' in key.lower():
                        value = main_characteristics[key]
                        # Проверяем что значение не пустое (список или строка)
                        if value and (isinstance(value, list) and len(value) > 0 or isinstance(value, str) and value.strip()):
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
                # Убираем «Инструменты: нет/none» и подобные бессмысленные ответы
                try:
                    if "инструмент" in (key or "").strip().lower():
                        val = main_characteristics.get(key)
                        val_s = ""
                        if isinstance(val, str):
                            val_s = val.strip().lower()
                        if val_s in {"нет", "none", "no", "n/a", "не применимо", "отсутствует"}:
                            continue
                except Exception:
                    pass

                # Не показываем обычную товарную упаковку (коробка/пакет и т.п.) — это не ценная информация.
                try:
                    key_l = (key or "").strip().lower()
                    if "упаков" in key_l:
                        val = main_characteristics.get(key)
                        val_s = ""
                        if isinstance(val, str):
                            val_s = val.strip().lower()
                        if val_s in {"коробка", "картонная коробка", "пакет", "короб", "box", "carton", "bag"}:
                            continue
                        # Если значение слишком общее — тоже пропускаем
                        if val_s in {"коробочная упаковка", "в коробке", "в коробке/пакете"}:
                            continue
                except Exception:
                    pass

                # Доп. фильтр цветов на этапе рендера (страховка, если что-то проскочило в LLM)
                try:
                    key_lc = (key or "").strip().lower()
                    # Иногда модель/данные дают ключи "Цвет", "Цвета", "Цвета товара" и т.п.
                    if "цвет" in key_lc:
                        val = main_characteristics.get(key)
                        if isinstance(val, list):
                            filtered = []
                            for item in val:
                                if not isinstance(item, str):
                                    continue
                                s = item.strip().lower()
                                # Гендерные/возрастные маркеры в "Цвета" запрещены — это не цвет.
                                if any(
                                    g in s
                                    for g in (
                                        "для мальчиков",
                                        "для девочек",
                                        "мальчик",
                                        "мальчиков",
                                        "девочк",
                                        "девочек",
                                        "мужск",
                                        "женск",
                                        "унисекс",
                                        "для мужчин",
                                        "для женщин",
                                    )
                                ):
                                    continue
                                # Убираем «не-цветовые» слова и хвосты вроде «пиджак/брюки», «на фото» и т.п.
                                # Это частая ошибка LLM: "верблюжий пиджак" вместо "верблюжий".
                                bad_tokens = (
                                    "пиджак", "брюки", "штаны", "костюм", "жакет", "куртка", "рубашк",
                                    "цвет на фото", "на фото", "как на фото", "изображ", "图片色",
                                    "цвет", "подарок", "сувенир", "упаков", "игрушк", "кукла",
                                    # Гендерные/возрастные упоминания в "Цвета" запрещены
                                    "мальчик", "мальчиков", "для мальчиков", "девочк", "девочек", "для девочек",
                                    "мужск", "женск", "для мужчин", "для женщин", "унисекс",
                                )
                                # Убираем технические коды типа f00xx, d00xx и их комбинации
                                import re
                                # Удаляем коды типа f00xx, d00xx (f/d + 0 + 3-4 цифры)
                                # Также удаляем комбинации типа d0004+f0045
                                s = re.sub(r"\b[fFdD]0{2,3}\d{1,4}(?:\+[fFdD]0{2,3}\d{1,4})*\b", "", s)
                                # Удаляем оставшиеся фрагменты типа +f0045 в начале/середине строки
                                s = re.sub(r"\s*\+\s*[fFdD]0{2,3}\d{1,4}\b", "", s)
                                s = re.sub(r"\s{2,}", " ", s).strip(" ,;:-").strip()
                                
                                if any(x in s for x in bad_tokens):
                                    # Пробуем «аккуратно» вычистить тип товара/служебные слова,
                                    # а не просто выкинуть значение целиком.
                                    try:
                                        cleaned = s
                                        cleaned = re.sub(r"(?i)\b(цвет(а|ов)?|на фото|как на фото)\b", "", cleaned)
                                        cleaned = re.sub(r"(?i)\b(пиджак|брюки|штаны|костюм|жакет|куртка|рубашка)\b", "", cleaned)
                                        cleaned = re.sub(r"(?i)图片色", "", cleaned)
                                        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;:-").strip()
                                        if not cleaned:
                                            continue
                                        s = cleaned
                                    except Exception:
                                        continue
                                # После чистки всё ещё мусор — выкидываем
                                if any(x in s for x in ("кукла", "игрушк", "упаков", "подарок", "сувенир")):
                                    continue
                                if not s or s in {"цвет", "цвета"}:
                                    continue
                                # После всех чисток ещё раз гарантируем, что гендер не проскочил
                                if any(x in s for x in ("для мальчиков", "для девочек", "мальчик", "девочк", "мужск", "женск", "унисекс")):
                                    continue

                                # Возвращаем уже очищенное значение
                                filtered.append(s)
                            if filtered:
                                # Дедуп + порядок
                                seen = set()
                                uniq_colors = []
                                for c in filtered:
                                    c0 = str(c).strip().lower()
                                    if not c0 or c0 in seen:
                                        continue
                                    seen.add(c0)
                                    uniq_colors.append(c0)
                                main_characteristics[key] = uniq_colors
                            else:
                                continue
                except Exception:
                    pass
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
                
                # Форматируем размеры если это размеры (но НЕ "Уточнения по размерам")
                if 'размер' in key.lower() and 'уточнен' not in key.lower() and isinstance(value, str):
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
                    formatted_value = str(value).strip()
                    if formatted_value:
                        formatted_value = self._ensure_lowercase_characteristic_value(key, formatted_value)
                    post_parts.append(f"<i><b>{key}:</b> {formatted_value}</i>")
        
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
        
        # Подпись пользователя (если не пустая)
        if user_signature:
            post_parts.append(f"<i>{user_signature}</i>")
            post_parts.append("")
        
        # Хэштеги больше не добавляются здесь - они генерируются отдельно после создания поста
        # и добавляются через метод _add_hashtags_to_post()
        
        # Ссылка на товар
        if product_url:
            post_parts.append(f'<a href="{product_url}">Ссылка</a>')
        
        return "\n".join(post_parts)

    def _add_hashtags_to_post(self, post_text: str, hashtags: list[str]) -> str:
        """
        Добавляет хэштеги в конец поста перед ссылкой на товар.

        Args:
            post_text: Текст поста
            hashtags: Список хэштегов

        Returns:
            str: Текст поста с добавленными хэштегами
        """
        if not hashtags:
            return post_text
        
        # Очищаем хэштеги от пробелов
        cleaned_hashtags = [tag.strip().replace(" ", "").replace("#", "") for tag in hashtags if tag and tag.strip()]
        if not cleaned_hashtags:
            return post_text
        
        hashtag_text = " ".join([f"#{tag}" for tag in cleaned_hashtags if tag])
        
        # Ищем позицию ссылки на товар (если есть)
        link_pattern = r'<a href="[^"]+">Ссылка</a>'
        if link_match := __import__('re').search(link_pattern, post_text):
            # Вставляем хэштеги перед ссылкой
            link_pos = link_match.start()
            before_link = post_text[:link_pos].rstrip()
            after_link = post_text[link_pos:]
            return f"{before_link}\n\n<i>{hashtag_text}</i>\n\n{after_link}"
        else:
            # Если ссылки нет, добавляем хэштеги в конец
            return f"{post_text.rstrip()}\n\n<i>{hashtag_text}</i>"
