import httpx
import json
import logging
from config import settings
import certifi
import ssl

logger = logging.getLogger(__name__)

class TmapiClient:
    """
    Клиент для взаимодействия с API tmapi.top.
    Отвечает за получение информации о товарах по URL.
    В режиме отладки читает данные из файла result.txt.
    """
    def __init__(self):
        self.api_url = "http://api.tmapi.top/taobao/item_detail_by_url"  # URL API для получения данных о товаре
        self.api_token = settings.TMAPI_TOKEN  # API токен, загружаемый из настроек
        self.debug_mode = settings.DEBUG_MODE  # Включаем режим отладки из настроек

    async def get_product_info(self, url: str):
        """
        Отправляет запрос к tmapi.top для получения информации о товаре.
        В режиме отладки возвращает данные из result.txt.

        Args:
            url (str): URL товара (например, с Taobao или Tmall).

        Returns:
            dict: Словарь с информацией о товаре.

        Raises:
            httpx.HTTPStatusError: Если запрос завершился с ошибкой (4xx или 5xx) в реальном режиме.
        """
        if self.debug_mode:
            # Режим отладки: читаем данные из локального файла вместо API
            logger.info(f"[DEBUG MODE] Reading product info from result.txt for URL: {url}")
            import os
            # Используем относительный путь от текущего файла
            current_dir = os.path.dirname(os.path.abspath(__file__))
            result_file = os.path.join(current_dir, "result.txt")
            
            with open(result_file, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"[DEBUG MODE] Data loaded from {result_file}")
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