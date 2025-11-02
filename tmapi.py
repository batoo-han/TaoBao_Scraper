import httpx
import json
import logging
from config import settings
import certifi
import ssl
import asyncio

logger = logging.getLogger(__name__)


class TMAPISubscriptionError(Exception):
    """
    Специальное исключение для ошибки 439 TMAPI.
    Возникает когда срок подписки истёк или на счету недостаточно средств.
    """
    def __init__(self, message: str, status_code: int = 439):
        self.status_code = status_code
        super().__init__(message)

class TmapiClient:
    """
    Клиент для взаимодействия с API tmapi.top.
    Отвечает за получение информации о товарах по URL.
    В MOCK режиме читает данные из файлов вместо реальных API запросов.
    В DEBUG режиме выводит подробные логи.
    """
    def __init__(self):
        self.api_url = "http://api.tmapi.top/taobao/item_detail_by_url"  # URL API для получения данных о товаре
        self.item_desc_api_url = "http://api.tmapi.top/taobao/item_desc"  # URL API для получения описания товара
        self.api_token = settings.TMAPI_TOKEN  # API токен, загружаемый из настроек
        self.mock_mode = settings.MOCK_MODE  # Mock режим - использовать файлы вместо API
        self.debug_mode = settings.DEBUG_MODE  # Debug режим - показывать подробные логи
        # Увеличенные таймауты для медленного API
        self.timeout = httpx.Timeout(120.0, connect=20.0)  # 120 сек на запрос, 20 сек на соединение

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
            
            # Retry логика для таймаутов и HTTP ошибок
            max_retries = 2
            for attempt in range(1, max_retries + 1):
                try:
                    async with httpx.AsyncClient(verify=verify_ssl, timeout=self.timeout) as client:
                        # POST запрос с JSON телом
                        # Отключаем заголовок Expect: 100-continue чтобы избежать ошибки 417
                        headers = {"Expect": ""}
                        response = await client.post(
                            self.api_url, 
                            json=payload, 
                            params=querystring,
                            headers=headers
                        )
                        response.raise_for_status()  # Вызывает исключение для ошибок HTTP статуса
                        logger.debug(f"TMAPI response status: {response.status_code}")
                        logger.debug(f"TMAPI raw response: {response.text[:500]}...")  # Показываем первые 500 символов
                        return response.json()  # Возвращает JSON ответ
                except httpx.ReadTimeout as e:
                    if attempt < max_retries:
                        wait_time = attempt * 2  # 2, 4 секунды
                        logger.warning(f"[TMAPI] Таймаут при запросе (попытка {attempt}/{max_retries}). Ждём {wait_time} сек перед повтором...")
                        if self.debug_mode:
                            print(f"[TMAPI] ⏱️ Таймаут запроса, повтор через {wait_time} сек...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"[TMAPI] Таймаут после {max_retries} попыток. API tmapi.top не отвечает достаточно быстро.")
                        raise httpx.ReadTimeout(f"Таймаут при запросе к TMAPI после {max_retries} попыток. Возможно, API перегружен или недоступен.") from e
                except httpx.ConnectTimeout as e:
                    logger.error(f"[TMAPI] Таймаут соединения с API tmapi.top.")
                    raise httpx.ConnectTimeout(f"Не удалось подключиться к TMAPI. Проверьте интернет-соединение.") from e
                except httpx.HTTPStatusError as e:
                    # Обработка HTTP ошибок (4xx, 5xx) согласно документации TMAPI
                    # https://tmapi.top/docs/taobao-tmall/item-detail/get-item-detail-by-id/
                    status_code = e.response.status_code
                    error_response = e.response.text[:500] if e.response.text else "Нет текста ответа"
                    
                    # Для ошибки 417 - не удалось получить данные, пробуем повторить
                    if status_code == 417 and attempt < max_retries:
                        wait_time = attempt * 2
                        logger.warning(
                            f"[TMAPI] HTTP 417 - Не удалось получить данные (попытка {attempt}/{max_retries}). "
                            f"Пробуем повторить через {wait_time} сек...\n"
                            f"Ответ сервера: {error_response}"
                        )
                        if self.debug_mode:
                            print(f"[TMAPI] ⚠️ HTTP 417, повтор через {wait_time} сек...")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Для ошибки 499 - попробуйте ещё раз или увеличьте время ожидания до 60 секунд
                    if status_code == 499 and attempt < max_retries:
                        wait_time = min(5 + attempt * 3, 10)  # 5-8 секунд
                        logger.warning(
                            f"[TMAPI] HTTP 499 - Попробуйте ещё раз (попытка {attempt}/{max_retries}). "
                            f"Ждём {wait_time} сек...\n"
                            f"Ответ сервера: {error_response}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Для ошибки 500 - внутренняя ошибка сервера, пробуем повторить
                    if status_code == 500 and attempt < max_retries:
                        wait_time = attempt * 3  # 3, 6 секунд
                        logger.warning(
                            f"[TMAPI] HTTP 500 - Внутренняя ошибка сервера (попытка {attempt}/{max_retries}). "
                            f"Пробуем повторить через {wait_time} сек...\n"
                            f"Ответ сервера: {error_response}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Для ошибки 503 - превышен лимит одновременных запросов, пробуем повторить
                    if status_code == 503 and attempt < max_retries:
                        wait_time = attempt * 5  # 5, 10 секунд
                        logger.warning(
                            f"[TMAPI] HTTP 503 - Превышен лимит одновременных запросов (попытка {attempt}/{max_retries}). "
                            f"Ждём {wait_time} сек...\n"
                            f"Ответ сервера: {error_response}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Для ошибки 439 - специальное исключение для обработки отдельно
                    if status_code == 439:
                        error_msg = (
                            f"Срок действия подписки TMAPI истёк или на счету недостаточно средств. "
                            f"Ответ сервера: {error_response[:200]}"
                        )
                        logger.error(f"[TMAPI] HTTP 439: {error_msg}")
                        raise TMAPISubscriptionError(error_msg, status_code=439)
                    
                    # Для других HTTP ошибок логируем и пробрасываем
                    # Формируем понятное сообщение об ошибке согласно документации TMAPI
                    if status_code == 422:
                        error_msg = "TMAPI: Ошибка параметра. Проверьте формат запроса."
                    elif status_code == 439:
                        error_msg = "TMAPI: Срок действия подписки истёк или на счету недостаточно средств."
                    elif status_code == 417:
                        error_msg = "TMAPI: Не удалось получить данные. Пожалуйста, попробуйте ещё раз."
                    elif status_code == 499:
                        error_msg = "TMAPI: Попробуйте ещё раз или увеличьте время ожидания запроса до 60 секунд."
                    elif status_code == 500:
                        error_msg = "TMAPI: Произошла непредвиденная ошибка сервера. Попробуйте позже."
                    elif status_code == 503:
                        error_msg = "TMAPI: Превышен лимит одновременных запросов к API."
                    else:
                        error_msg = f"TMAPI: HTTP ошибка {status_code}."
                    
                    logger.error(
                        f"[TMAPI] HTTP ошибка {status_code} при запросе к {self.api_url}\n"
                        f"Описание: {error_msg}\n"
                        f"Ответ сервера: {error_response}\n"
                        f"Запрошенный URL: {url}"
                    )
                    
                    raise httpx.HTTPStatusError(
                        f"{error_msg}\nДетали: {error_response[:200]}",
                        request=e.request,
                        response=e.response
                    ) from e

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
            
            # Retry логика для таймаутов и HTTP ошибок
            max_retries = 2
            for attempt in range(1, max_retries + 1):
                try:
                    async with httpx.AsyncClient(verify=verify_ssl, timeout=self.timeout) as client:
                        # GET запрос для получения описания
                        # Отключаем заголовок Expect: 100-continue чтобы избежать ошибки 417
                        headers = {"Expect": ""}
                        response = await client.get(
                            self.item_desc_api_url, 
                            params=querystring,
                            headers=headers
                        )
                        
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
                except httpx.ReadTimeout as e:
                    if attempt < max_retries:
                        wait_time = attempt * 2
                        logger.warning(f"[TMAPI] Таймаут при запросе item_desc (попытка {attempt}/{max_retries}). Ждём {wait_time} сек...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"[TMAPI] Таймаут item_desc после {max_retries} попыток.")
                        raise httpx.ReadTimeout(f"Таймаут при запросе описания товара после {max_retries} попыток.") from e
                except httpx.ConnectTimeout as e:
                    logger.error(f"[TMAPI] Таймаут соединения при запросе item_desc.")
                    raise httpx.ConnectTimeout(f"Не удалось подключиться к TMAPI для получения описания.") from e
                except httpx.HTTPStatusError as e:
                    # Обработка HTTP ошибок (4xx, 5xx) согласно документации TMAPI
                    status_code = e.response.status_code
                    error_response = e.response.text[:500] if e.response.text else "Нет текста ответа"
                    
                    # Для ошибки 417 - не удалось получить данные, пробуем повторить
                    if status_code == 417 and attempt < max_retries:
                        wait_time = attempt * 2
                        logger.warning(
                            f"[TMAPI] HTTP 417 при запросе item_desc (попытка {attempt}/{max_retries}). "
                            f"Пробуем повторить через {wait_time} сек...\n"
                            f"Ответ сервера: {error_response}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Для ошибки 499 - попробуйте ещё раз
                    if status_code == 499 and attempt < max_retries:
                        wait_time = min(5 + attempt * 3, 10)
                        logger.warning(
                            f"[TMAPI] HTTP 499 при запросе item_desc (попытка {attempt}/{max_retries}). "
                            f"Ждём {wait_time} сек...\n"
                            f"Ответ сервера: {error_response}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Для ошибки 500 - внутренняя ошибка сервера, пробуем повторить
                    if status_code == 500 and attempt < max_retries:
                        wait_time = attempt * 3
                        logger.warning(
                            f"[TMAPI] HTTP 500 при запросе item_desc (попытка {attempt}/{max_retries}). "
                            f"Пробуем повторить через {wait_time} сек...\n"
                            f"Ответ сервера: {error_response}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Для ошибки 503 - превышен лимит, пробуем повторить
                    if status_code == 503 and attempt < max_retries:
                        wait_time = attempt * 5
                        logger.warning(
                            f"[TMAPI] HTTP 503 при запросе item_desc (попытка {attempt}/{max_retries}). "
                            f"Ждём {wait_time} сек...\n"
                            f"Ответ сервера: {error_response}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Для ошибки 439 - специальное исключение для обработки отдельно
                    if status_code == 439:
                        error_msg = (
                            f"Срок действия подписки TMAPI истёк или на счету недостаточно средств. "
                            f"Ответ сервера: {error_response[:200]}"
                        )
                        logger.error(f"[TMAPI] HTTP 439 при запросе item_desc: {error_msg}")
                        raise TMAPISubscriptionError(error_msg, status_code=439)
                    
                    # Для других HTTP ошибок логируем и пробрасываем
                    # Формируем понятное сообщение об ошибке согласно документации TMAPI
                    if status_code == 422:
                        error_msg = "TMAPI: Ошибка параметра при запросе описания."
                    elif status_code == 439:
                        error_msg = "TMAPI: Срок действия подписки истёк или на счету недостаточно средств."
                    elif status_code == 417:
                        error_msg = "TMAPI: Не удалось получить данные описания."
                    elif status_code == 499:
                        error_msg = "TMAPI: Попробуйте ещё раз или увеличьте время ожидания."
                    elif status_code == 500:
                        error_msg = "TMAPI: Произошла непредвиденная ошибка сервера."
                    elif status_code == 503:
                        error_msg = "TMAPI: Превышен лимит одновременных запросов к API."
                    else:
                        error_msg = f"TMAPI: HTTP ошибка {status_code} при запросе описания товара."
                    
                    logger.error(
                        f"[TMAPI] HTTP ошибка {status_code} при запросе item_desc для item_id={item_id}\n"
                        f"Описание: {error_msg}\n"
                        f"Ответ сервера: {error_response}"
                    )
                    
                    raise httpx.HTTPStatusError(
                        f"{error_msg}\nДетали: {error_response[:200]}",
                        request=e.request,
                        response=e.response
                    ) from e