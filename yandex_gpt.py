import httpx
import json
from config import settings

class YandexGPTClient:
    """
    Клиент для взаимодействия с YandexGPT API.
    Отвечает за генерацию текста поста на основе данных о товаре.
    """
    def __init__(self):
        self.base_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"  # Базовый URL YandexGPT API
        self.api_key = settings.YANDEX_GPT_API_KEY  # API ключ, загружаемый из настроек
        self.headers = {
            "Authorization": f"Api-Key {self.api_key}",  # Авторизационный заголовок
            "Content-Type": "application/json"
        }

    async def generate_post_content(self, product_data: dict):
        """
        Генерирует структурированный контент для поста, используя YandexGPT.

        Args:
            product_data (dict): Словарь с информацией о товаре.

        Returns:
            dict: Словарь с ключами: title, description, characteristics, hashtags

        Raises:
            httpx.HTTPStatusError: Если запрос завершился с ошибкой (4xx или 5xx).
        """
        prompt_template = """
Ты — ассистент, который помогает создавать посты для Telegram-канала, продающего товары с Taobao/Tmall.

Твоя задача — проанализировать данные о товаре и создать структурированный контент на русском языке.

ОБЯЗАТЕЛЬНО верни ответ в виде JSON со следующей структурой:
{{
  "title": "Краткое привлекательное название товара на русском (не более 50 символов)",
  "description": "Краткое, привлекательное описание товара на русском (2-3 предложения, подчеркивающие основные преимущества)",
  "main_characteristics": {{
    "название_характеристики": "значение или список"
  }},
  "additional_info": {{
    "название_поля": "значение"
  }},
  "hashtags": ["хэштег1", "хэштег2"],
  "emoji": "подходящий эмодзи для товара"
}}

Требования:
1. **title**: Краткое, цепляющее название товара (переведи и адаптируй из данных)
2. **description**: 2-3 предложения, описывающие товар. Сделай текст привлекательным и продающим
3. **main_characteristics**: ТОЛЬКО самые важные характеристики (2-4 штуки):
   - Для одежды: Цвета (список), Размеры
   - Для обуви: Материал, Размеры, Цвета (список)
   - Для электроники: Основные характеристики, Цвет
   - НЕ указывай "Состав", если материал неопределенный (например: "Другие материалы", "Прочие", "Неизвестно")
   - Названия на русском, значения можно списком через запятую или массивом
4. **additional_info**: Дополнительная информация (ОПЦИОНАЛЬНО, можно оставить пустым {{}}):
   - Добавляй только если есть КОНКРЕТНАЯ полезная информация
   - НЕ добавляй общие/пустые значения типа: "Без бренда", "Нет информации", "Обычный"
   - Примеры ХОРОШИХ значений: "Сезон: Зима", "Материал подошвы: Резина"
   - Примеры ПЛОХИХ значений: "Бренд: Без бренда", "Стиль: Обычный"
   - НЕ дублируй информацию из main_characteristics
5. **hashtags**: 2-3 релевантных хэштега БЕЗ символа # (например: ["свитер", "женскаяодежда"])
6. **emoji**: Один подходящий эмодзи для данного типа товара (👗 для одежды, 👟 для обуви, 📱 для электроники и т.д.)

Исходные данные о товаре:
{product_data}

ВАЖНО: Ответь ТОЛЬКО валидным JSON, без дополнительного текста!
"""

        product_info_str = json.dumps(product_data, ensure_ascii=False, indent=2)
        prompt = prompt_template.format(product_data=product_info_str)

        if settings.DEBUG_MODE:
            print(f"[YandexGPT] Отправляем промпт:\n{prompt[:500]}...")

        data = {
            "modelUri": f"gpt://{settings.YANDEX_FOLDER_ID}/{settings.YANDEX_GPT_MODEL}", 
            "completionOptions": {
                "stream": False,
                "temperature": 0.3,
                "maxTokens": "2000"
            },
            "messages": [
                {
                    "role": "system",
                    "text": "Ты помощник для создания структурированного контента для постов в Telegram. Всегда отвечай только валидным JSON."
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
            
            if settings.DEBUG_MODE:
                print(f"[YandexGPT] Получен ответ:\n{llm_response}")
            
            # Парсим JSON из ответа
            try:
                # Удаляем возможные markdown code blocks
                cleaned_response = llm_response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()
                
                parsed_json = json.loads(cleaned_response)
                return parsed_json
            except json.JSONDecodeError as e:
                if settings.DEBUG_MODE:
                    print(f"[YandexGPT] Ошибка парсинга JSON: {e}")
                    print(f"[YandexGPT] Ответ LLM: {llm_response}")
                raise ValueError(f"YandexGPT вернул невалидный JSON: {e}")
