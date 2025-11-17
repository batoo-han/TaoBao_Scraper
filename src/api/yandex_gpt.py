import httpx
import json
from src.core.config import settings
from src.api.llm.base import LLMProvider, LLMResult

class YandexLLMProvider(LLMProvider):
    """
    Клиент для взаимодействия с YandexGPT API.
    Отвечает за генерацию текста поста на основе данных о товаре.
    """
    vendor = "yandex"

    def __init__(self):
        self.base_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"  # Базовый URL YandexGPT API
        self.api_key = settings.YANDEX_GPT_API_KEY  # API ключ, загружаемый из настроек
        self.headers = {
            "Authorization": f"Api-Key {self.api_key}",  # Авторизационный заголовок
            "Content-Type": "application/json"
        }

    async def generate(self, product_data: dict) -> LLMResult:
        """
        Генерирует структурированный контент для поста, используя YandexGPT.

        Args:
            product_data (dict): Словарь с информацией о товаре.

        Returns:
            LLMResult: Содержит распарсенный JSON и сырой ответ.

        Raises:
            httpx.HTTPStatusError: Если запрос завершился с ошибкой (4xx или 5xx).
        """
        prompt_template = """
Ты редактор. Твоя задача — кратко и грамотно пересказать уже переведённый на русский текст о товаре, сохранив смысл без маркетинговых украшений.

Требования:
- Никаких выдумок, только факты из данных.
- Естественный литературный русский, без канцелярита и «продающих» формулировок.
- Не указывать годы, сезоны, возраст. Пол можно, если явно указан.
- Не добавлять поля с пустыми значениями.
- Бренды и цвета — на русском; не оставляй английский/китайский.

Верни ТОЛЬКО валидный JSON такого вида:
{{
  "title": "краткое нейтральное название (до ~60 символов)",
  "description": "нейтральное пересказанное описание на русском (2–4 предложения)",
  "main_characteristics": {{
    "название_характеристики": "значение или список из данных"
  }},
  "additional_info": {{}},
  "hashtags": []
}}

Данные:
{product_data}
"""

        product_info_str = json.dumps(product_data, ensure_ascii=False, indent=2)
        prompt = prompt_template.format(product_data=product_info_str)

        if settings.DEBUG_MODE:
            print(f"[YandexGPT] Отправляем промпт:\n{prompt[:500]}...")

        data = {
            "modelUri": f"gpt://{settings.YANDEX_FOLDER_ID}/{settings.YANDEX_GPT_MODEL}", 
            "completionOptions": {
                "stream": False,
                "temperature": 0.05,
                "maxTokens": "900"
            },
            "messages": [
                {
                    "role": "system",
                    "text": "Ты редактор-рефразировщик: переписываешь русский текст товара кратко и нейтрально, без маркетинга, выдумок и англ./кит. слов. Всегда отвечай только валидным JSON указанной структуры."
                },
                {
                    "role": "user",
                    "text": prompt
                }
            ]
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.base_url, headers=self.headers, json=data)
            response.raise_for_status()

            llm_response = response.json()["result"]["alternatives"][0]["message"]["text"]
            cleaned_response = llm_response.strip()

            if settings.DEBUG_MODE:
                print(f"[YandexGPT] Получен ответ:\n{llm_response}")

            # Парсим JSON из ответа
            try:
                # Удаляем возможные markdown code blocks
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()

                parsed_json = json.loads(cleaned_response)
                return LLMResult(data=parsed_json, raw_text=llm_response, tokens_used=None)
            except json.JSONDecodeError as e:
                if settings.DEBUG_MODE:
                    print(f"[YandexGPT] Ошибка парсинга JSON: {e}")
                    print(f"[YandexGPT] Ответ LLM: {llm_response}")
                raise ValueError(f"YandexGPT вернул невалидный JSON: {e}")

    async def generate_post_content(self, product_data: dict):
        """
        Временный адаптер для существующего кода.
        """
        result = await self.generate(product_data)
        return result.data
