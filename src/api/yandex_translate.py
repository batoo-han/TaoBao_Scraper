import httpx
from src.core.config import settings

class YandexTranslateClient:
    """
    Клиент для взаимодействия с Yandex.Translate API.
    Отвечает за перевод текста.
    """
    def __init__(self):
        self.base_url = "https://translate.api.cloud.yandex.net/translate/v2/"  # Базовый URL Yandex.Translate API
        # Предполагается, что ключ Yandex GPT API может быть использован для Yandex.Translate
        self.api_key = settings.YANDEX_GPT_API_KEY  

    async def translate_text(self, text: str, target_language: str = "ru"):
        """
        Переводит заданный текст на указанный целевой язык.

        Args:
            text (str): Текст для перевода.
            target_language (str): Целевой язык (по умолчанию "ru").

        Returns:
            str: Переведенный текст.

        Raises:
            httpx.HTTPStatusError: Если запрос завершился с ошибкой (4xx или 5xx).
        """
        headers = {
            "Authorization": f"Api-Key {self.api_key}",  # Авторизационный заголовок
            "Content-Type": "application/json"
        }
        data = {
            "texts": [text],  # Список текстов для перевода
            "targetLanguageCode": target_language  # Код целевого языка
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}translate", headers=headers, json=data)
            response.raise_for_status()  # Вызывает исключение для ошибок HTTP статуса
            translated_text = response.json()["translations"][0]["text"]  # Извлекает переведенный текст
            return translated_text
