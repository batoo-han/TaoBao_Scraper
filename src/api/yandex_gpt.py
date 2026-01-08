import json
import httpx

from src.core.config import settings
from src.api.prompts import POST_GENERATION_PROMPT, HASHTAGS_GENERATION_PROMPT


class YandexGPTClient:
    """
    Асинхронный клиент для YandexGPT.
    Используется как для генерации описаний, так и для произвольных JSON-ответов/переводов.
    """

    SYSTEM_PROMPT = (
        "Ты помощник для создания структурированного контента для постов в Telegram. "
        "КРИТИЧЕСКИ ВАЖНО: всё должно быть переведено на русский язык — названия цветов, бренды, "
        "любой текст. Не оставляй английские слова или китайские иероглифы. Всегда отвечай валидным JSON."
    )

    def __init__(self, model_name: str | None = None):
        self.base_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        self.api_key = settings.YANDEX_GPT_API_KEY
        self.headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }
        default_model = (settings.YANDEX_GPT_MODEL or "yandexgpt-lite").strip()
        self.model = (model_name or default_model) or "yandexgpt-lite"

    async def generate_post_content(self, product_data: dict) -> dict:
        """
        Генерирует структурированный JSON-контент для поста.
        """
        # Важно: используем компактный JSON, чтобы не тратить токены на пробелы/переносы строк
        product_info_str = json.dumps(product_data, ensure_ascii=False, separators=(",", ":"))
        prompt = POST_GENERATION_PROMPT.replace("{product_data}", product_info_str)

        if settings.DEBUG_MODE:
            print(f"[YandexGPT] Отправляем промпт ({self.model}):\n{prompt[:500]}...")

        text = await self.generate_json_response(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=2000,
            temperature=0.1,
        )

        try:
            return json.loads(self._cleanup_response(text))
        except json.JSONDecodeError as exc:
            if settings.DEBUG_MODE:
                print(f"[YandexGPT] Ошибка JSON: {exc}\nОтвет: {text}")
            raise ValueError(f"YandexGPT вернул невалидный JSON: {exc}") from exc

    async def generate_json_response(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> str:
        """
        Универсальный метод получения строкового ответа (часто JSON) от YandexGPT.
        """
        limit = max_tokens or max_output_tokens or 2000

        payload = {
            "modelUri": f"gpt://{settings.YANDEX_FOLDER_ID}/{self.model}",
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": str(limit),
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.base_url, headers=self.headers, json=payload)
            response.raise_for_status()

        result = response.json()["result"]["alternatives"][0]["message"]["text"]
        if settings.DEBUG_MODE:
            print(f"[YandexGPT] Получен ответ:\n{result}")
        return result

    async def translate_text(self, text: str, target_language: str = "ru") -> str:
        """
        Переводит одну строку средствами YandexGPT.
        """
        if not text:
            return text

        prompt = (
            f"Переведи следующий текст на {target_language}. "
            "Ответь только переводом без пояснений.\n\n"
            f"{text}"
        )
        translated = await self.generate_json_response(
            system_prompt="Ты профессиональный переводчик.",
            user_prompt=prompt,
            max_tokens=400,
            temperature=0.0,
        )
        return translated.strip()

    async def generate_hashtags(
        self,
        post_text: str,
    ) -> tuple[list[str], "TokensUsage"]:
        """
        Генерирует хэштеги на основе готового текста поста.

        Args:
            post_text: Готовый текст поста для Telegram

        Returns:
            tuple[list[str], TokensUsage]: Список хэштегов и статистика токенов
        """
        # Импортируем TokensUsage здесь, чтобы избежать циклических импортов
        from src.api.tokens_stats import TokensUsage
        
        if not post_text:
            # Если текста нет — возвращаем пустой список и нулевую статистику
            return [], TokensUsage()

        # Формируем промпт для генерации хэштегов
        user_prompt = HASHTAGS_GENERATION_PROMPT.replace("{post_text}", post_text)

        system_prompt = (
            "Ты опытный маркетолог, специализирующийся на работе с маркетплейсами. "
            "Твоя задача — по тексту поста товара дать один-два хэштега, которые отражают только суть товара."
        )

        if settings.DEBUG_MODE:
            print(f"[YandexGPT][hashtags] Отправляем промпт генерации хэштегов ({self.model}):\n{user_prompt[:500]}...")

        # Генерируем хэштеги
        text = await self.generate_json_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=200,
            temperature=0.1,
        )

        # Парсим JSON-ответ
        try:
            cleaned = self._cleanup_response(text)
            data = json.loads(cleaned)
            hashtags = data.get("hashtags", [])
            
            # Валидация: убеждаемся, что это список строк
            if not isinstance(hashtags, list):
                hashtags = []
            else:
                # Фильтруем и очищаем хэштеги
                hashtags = [
                    str(tag).strip().replace(" ", "").replace("#", "")
                    for tag in hashtags
                    if tag and str(tag).strip()
                ]
            
            if settings.DEBUG_MODE:
                print(f"[YandexGPT][hashtags] Сгенерированы хэштеги: {hashtags}")
            
            # YandexGPT не возвращает статистику токенов, создаём пустую
            return hashtags, TokensUsage()
        except (json.JSONDecodeError, KeyError, AttributeError) as exc:
            if settings.DEBUG_MODE:
                print(f"[YandexGPT][hashtags] Ошибка парсинга JSON: {exc}\nОтвет: {text}")
            # В случае ошибки возвращаем пустой список
            return [], TokensUsage()

    @staticmethod
    def _cleanup_response(raw_text: str) -> str:
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()
