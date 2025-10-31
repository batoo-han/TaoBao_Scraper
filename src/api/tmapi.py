import httpx
import json
import logging
import asyncio
import time
from src.core.config import settings
from src.utils.url_parser import URLParser, Platform
import certifi
import ssl
# Интеграция RapidAPI для Pinduoduo удалена

logger = logging.getLogger(__name__)

class TmapiClient:
    """
    Клиент для взаимодействия с API tmapi.top.
    Поддерживает Taobao, Tmall и Pinduoduo.
    Автоматически определяет платформу по URL.
    Реализует rate limiting для контроля частоты запросов.
    В MOCK режиме читает данные из файлов вместо реальных API запросов.
    В DEBUG режиме выводит подробные логи.
    """
    def __init__(self):
        # URL API для Taobao/Tmall
        self.api_url = "http://api.tmapi.top/taobao/item_detail_by_url"
        self.item_desc_api_url = "http://api.tmapi.top/taobao/item_desc"
        
        # URL API для Pinduoduo
        self.pinduoduo_api_url = "http://api.tmapi.top/pdd/item_detail"
        
        # API токены
        self.api_token = settings.TMAPI_TOKEN  # Токен для Taobao/Tmall
        self.pinduoduo_token = settings.TMAPI_PINDUODUO_TOKEN  # Токен для Pinduoduo
        
        # Настройки режимов
        self.mock_mode = settings.MOCK_MODE
        self.debug_mode = settings.DEBUG_MODE
        
        # Rate limiting (количество запросов в секунду)
        self.rate_limit = settings.TMAPI_RATE_LIMIT
        self.last_request_time = 0
        self.request_lock = asyncio.Lock()  # Для синхронизации запросов
        # Для Pinduoduo используем веб-скрапинг (см. core.scraper)

    async def get_product_info(self, url: str):
        """
        Отправляет запрос к tmapi.top для получения информации о товаре.
        В MOCK режиме возвращает данные из result.txt.

        Args:
            url (str): URL товара (например, с Taobao или Tmall).

        Returns:
            dict: Словарь с информацией о товаре.

        Raises:
            httpx.HTTPStatusError: Если запрос завершился с ошибкой (4xx или 5xx) в реальном режиме.
        """
        if self.mock_mode:
            # Mock режим: читаем данные из локального файла вместо API
            logger.info(f"[MOCK MODE] Reading product info from result.txt for URL: {url}")
            if self.debug_mode:
                print(f"[TMAPI] 📁 MOCK MODE - читаем из result.txt")
            import os
            # Используем относительный путь от текущего файла
            current_dir = os.path.dirname(os.path.abspath(__file__))
            result_file = os.path.join(current_dir, "result.txt")
            
            with open(result_file, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"[MOCK MODE] Data loaded from {result_file}")
                # result.txt contains a JSON string, so we need to parse it
                return json.loads(content)
        else:
            logger.info(f"Fetching product info from TMAPI for URL: {url}")
            
            # Параметры запроса (API token в query string)
            querystring = {"apiToken": self.api_token}
            
            # Тело запроса (URL товара в JSON)
            payload = {"url": url}
            
            # Настраиваем SSL проверку
            if settings.DISABLE_SSL_VERIFY:
                # ВНИМАНИЕ: Отключение проверки SSL небезопасно! Используйте только при необходимости
                logger.warning("SSL verification is DISABLED. This is not recommended for production!")
                verify_ssl = False
            else:
                # Используем certifi для корректной работы сертификатов
                verify_ssl = ssl.create_default_context(cafile=certifi.where())
            
            async with httpx.AsyncClient(verify=verify_ssl) as client:
                # POST запрос с JSON телом
                response = await client.post(self.api_url, json=payload, params=querystring)
                response.raise_for_status()  # Вызывает исключение для ошибок HTTP статуса
                logger.debug(f"TMAPI response status: {response.status_code}")
                logger.debug(f"TMAPI raw response: {response.text[:500]}...")  # Показываем первые 500 символов
                return response.json()  # Возвращает JSON ответ

    async def get_item_description(self, item_id: int):
        """
        Получает детальное описание товара с дополнительными изображениями.
        
        Args:
            item_id (int): ID товара
            
        Returns:
            dict: Словарь с описанием товара, включая detail_html с изображениями
        """
        if self.mock_mode:
            logger.info(f"[MOCK MODE] Reading item description from result55.txt for item_id: {item_id}")
            if self.debug_mode:
                print(f"[TMAPI] 📁 MOCK MODE - читаем из result55.txt")
            import os
            import ast
            current_dir = os.path.dirname(os.path.abspath(__file__))
            result_file = os.path.join(current_dir, "result55.txt")
            
            with open(result_file, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"[MOCK MODE] Description data loaded from {result_file}")
                # result55.txt contains Python dict with single quotes, use ast.literal_eval
                return ast.literal_eval(content)
        else:
            logger.info(f"Fetching item description from TMAPI for item_id: {item_id}")
            
            # Параметры запроса
            querystring = {
                "apiToken": self.api_token,
                "item_id": item_id
            }
            
            if settings.DEBUG_MODE:
                print(f"[TMAPI] GET {self.item_desc_api_url}")
                print(f"[TMAPI] Параметры: item_id={item_id}")
            
            # Настраиваем SSL проверку
            if settings.DISABLE_SSL_VERIFY:
                logger.warning("SSL verification is DISABLED. This is not recommended for production!")
                verify_ssl = False
            else:
                verify_ssl = ssl.create_default_context(cafile=certifi.where())
            
            async with httpx.AsyncClient(verify=verify_ssl) as client:
                # GET запрос для получения описания
                response = await client.get(self.item_desc_api_url, params=querystring)
                
                if settings.DEBUG_MODE:
                    print(f"[TMAPI] Статус ответа: {response.status_code}")
                    print(f"[TMAPI] Первые 500 символов ответа: {response.text[:500]}")
                
                response.raise_for_status()
                logger.debug(f"TMAPI item_desc response status: {response.status_code}")
                
                result = response.json()
                
                if settings.DEBUG_MODE:
                    print(f"[TMAPI] JSON ответ: code={result.get('code')}, msg={result.get('msg')}")
                    if result.get('data'):
                        data_keys = list(result.get('data', {}).keys())
                        print(f"[TMAPI] Ключи в data: {data_keys}")
                
                return result
    
    async def _apply_rate_limit(self):
        """
        Применяет ограничение частоты запросов (rate limiting).
        Гарантирует, что запросы не превышают установленный лимит.
        """
        async with self.request_lock:
            current_time = time.time()
            time_since_last_request = current_time - self.last_request_time
            
            # Минимальный интервал между запросами (в секундах)
            min_interval = 1.0 / self.rate_limit
            
            # Если прошло меньше минимального интервала - ждём
            if time_since_last_request < min_interval:
                sleep_time = min_interval - time_since_last_request
                if self.debug_mode:
                    print(f"[TMAPI] ⏱️  Rate limiting: ждём {sleep_time:.3f} сек")
                await asyncio.sleep(sleep_time)
            
            # Обновляем время последнего запроса
            self.last_request_time = time.time()
    
    async def get_pinduoduo_product(self, url: str):
        """
        Pinduoduo через API отключён. Используйте веб-скрапинг (см. core.scraper).
        """
        raise NotImplementedError("Pinduoduo API отключён. Используйте веб-скрапинг.")

    async def _resolve_pdd_goods_id_from_url(self, url: str) -> None:
        return None
    
    async def get_product_info_auto(self, url: str):
        """
        Универсальный метод для получения информации о товаре.
        Автоматически определяет платформу (Taobao/Tmall/Pinduoduo) и вызывает нужный API.
        
        Args:
            url (str): URL товара с любой поддерживаемой платформы
            
        Returns:
            dict: Словарь с информацией о товаре и платформой
            
        Raises:
            ValueError: Если платформа не поддерживается
        """
        # Определяем платформу
        platform, item_id = URLParser.parse_url(url)
        
        if self.debug_mode:
            print(f"[TMAPI] 🔍 Определена платформа: {platform}")
            if item_id:
                print(f"[TMAPI] 🆔 Извлечён item_id: {item_id}")
        
        # Применяем rate limiting для всех запросов
        await self._apply_rate_limit()
        
        # Выбираем нужный метод API
        if platform == Platform.PINDUODUO:
            result = await self.get_pinduoduo_product(url)
            result['_platform'] = Platform.PINDUODUO  # Добавляем метку платформы
            return result
        
        elif platform in [Platform.TAOBAO, Platform.TMALL]:
            result = await self.get_product_info(url)
            result['_platform'] = platform  # Добавляем метку платформы
            return result
        
        else:
            error_msg = f"Неподдерживаемая платформа: {url}"
            logger.error(error_msg)
            raise ValueError(error_msg)