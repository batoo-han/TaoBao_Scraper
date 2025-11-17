"""
Клиент для взаимодействия с OpenAI API.
Отвечает за генерацию текста поста на основе данных о товаре.
"""

import httpx
import json
from typing import Dict, Any

from src.core.config import settings
from src.api.llm.base import LLMProvider, LLMResult


class OpenAILLMProvider(LLMProvider):
    """
    Клиент для взаимодействия с OpenAI API.
    Отвечает за генерацию текста поста на основе данных о товаре.
    """
    vendor = "openai"

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        """
        Инициализация клиента OpenAI.

        Args:
            api_key: API ключ OpenAI (если не указан, берется из settings)
            model: Модель для использования (по умолчанию gpt-4o-mini)
        """
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def generate(self, product_data: Dict[str, Any]) -> LLMResult:
        """
        Генерирует структурированный контент для поста, используя OpenAI.

        Args:
            product_data: Словарь с информацией о товаре.

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
            print(f"[OpenAI] Отправляем промпт:\n{prompt[:500]}...")

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты редактор-рефразировщик: переписываешь русский текст товара кратко и нейтрально, без маркетинга, выдумок и англ./кит. слов. Всегда отвечай только валидным JSON указанной структуры."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.05,
            "max_tokens": 900,
            "response_format": {"type": "json_object"}  # Принудительный JSON режим (для gpt-4o и новее)
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.base_url, headers=self.headers, json=data)
            response.raise_for_status()

            response_json = response.json()
            llm_response = response_json["choices"][0]["message"]["content"]
            usage = response_json.get("usage", {})
            tokens_used = usage.get("total_tokens", None)

            cleaned_response = llm_response.strip()

            if settings.DEBUG_MODE:
                print(f"[OpenAI] Получен ответ:\n{llm_response}")

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
                return LLMResult(data=parsed_json, raw_text=llm_response, tokens_used=tokens_used)
            except json.JSONDecodeError as e:
                if settings.DEBUG_MODE:
                    print(f"[OpenAI] Ошибка парсинга JSON: {e}")
                    print(f"[OpenAI] Ответ LLM: {llm_response}")
                raise ValueError(f"OpenAI вернул невалидный JSON: {e}")

