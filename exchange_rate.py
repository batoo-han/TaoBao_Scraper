import httpx
from config import settings
import datetime

class ExchangeRateClient:
    """
    Клиент для получения курса валют с ExchangeRate-API и его кэширования.
    """
    def __init__(self):
        self.base_url = "https://v6.exchangerate-api.com/v6/"  # Базовый URL ExchangeRate-API
        self.api_key = settings.EXCHANGE_RATE_API_KEY  # API ключ, загружаемый из настроек
        # Кэш для хранения курсов валют: { (базовая_валюта, целевая_валюта): { "rate": курс, "expiry": время_истечения } }
        self.cache = {}  

    async def get_exchange_rate(self, base_currency: str = "CNY", target_currency: str = "RUB"):
        """
        Получает курс обмена между двумя валютами, используя кэширование.

        Args:
            base_currency (str): Базовая валюта (по умолчанию "CNY").
            target_currency (str): Целевая валюта (по умолчанию "RUB").

        Returns:
            float: Курс обмена.

        Raises:
            httpx.HTTPStatusError: Если запрос завершился с ошибкой (4xx или 5xx).
        """
        cache_key = (base_currency, target_currency)
        # Проверяем наличие курса в кэше и его актуальность
        if cache_key in self.cache:
            if self.cache[cache_key]["expiry"] > datetime.datetime.now():
                return self.cache[cache_key]["rate"]

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}{self.api_key}/latest/{base_currency}")
            response.raise_for_status()  # Вызывает исключение для ошибок HTTP статуса
            data = response.json()
            
            rate = data["conversion_rates"][target_currency]
            
            # API возвращает время следующего обновления, которое используется как время истечения кэша
            time_next_update_utc_str = data["time_next_update_utc"]
            # Парсим строку времени в объект datetime
            expiry_datetime = datetime.datetime.strptime(time_next_update_utc_str, "%a, %d %b %Y %H:%M:%S %z")

            # Сохраняем курс и время истечения в кэш
            self.cache[cache_key] = {
                "rate": rate,
                "expiry": expiry_datetime
            }
            return rate