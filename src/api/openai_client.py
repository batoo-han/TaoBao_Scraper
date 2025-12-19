import asyncio
import json
from typing import Iterable

from openai import AsyncOpenAI, OpenAIError

from src.core.config import settings
from src.api.prompts import POST_GENERATION_PROMPT


class OpenAIClient:
    """
    Клиент для взаимодействия с OpenAI.
    Используется как альтернатива YandexGPT и полностью повторяет формат ответов.
    """

    SYSTEM_PROMPT = (
        "Ты помощник для создания структурированного контента для постов в Telegram. "
        "КРИТИЧЕСКИ ВАЖНО: ВСЁ должно быть переведено на русский язык - названия цветов, бренды, "
        "любой текст. НЕ оставляй английские слова или китайские иероглифы. Всегда отвечай только валидным JSON."
    )

    # Константы для Responses API (отключено, используется только Chat Completions)
    RESPONSES_PREFIXES = ("gpt-5",)  # Не используется - Responses API отключён
    RESPONSES_JSON_TOKENS = 4500  # Не используется
    RESPONSES_TRANSLATE_TOKENS = 500  # Используется как max_tokens для переводов

    def __init__(self, model_name: str | None = None):
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY не задан. Укажите ключ в .env, чтобы использовать OpenAI."
            )

        source_model = model_name or settings.OPENAI_MODEL or "gpt-4o-mini"
        model_raw = source_model.strip()
        self.model = model_raw or "gpt-4o-mini"
        # Отключено использование Responses API - всегда используем Chat Completions API
        # Responses API слишком медленный из-за reasoning-запросов
        self.use_responses_api = False

        # Поддержка внешнего шлюза (OpenAI Gateway)
        base_url = (getattr(settings, "OPENAI_BASE_URL", "") or "").strip() or None
        extra_headers: dict[str, str] = {}
        gateway_token = (getattr(settings, "OPENAI_GATEWAY_TOKEN", "") or "").strip()
        if gateway_token:
            extra_headers["X-Gateway-Token"] = gateway_token

        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=base_url,
            default_headers=extra_headers or None,
        )
        # Для моделей gpt-5 не поддерживается temperature, используется max_completion_tokens вместо max_tokens
        is_gpt5 = self._requires_responses_api(self.model)
        self.supports_temperature = not is_gpt5
        self.supports_max_tokens = not is_gpt5  # Для gpt-5 используется max_completion_tokens

    @classmethod
    def _requires_responses_api(cls, model_name: str) -> bool:
        normalized = (model_name or "").strip().lower()
        return any(normalized.startswith(prefix) for prefix in cls.RESPONSES_PREFIXES)

    async def generate_post_content(self, product_data: dict) -> dict:
        """
        Генерация описания товара через OpenAI.
        """
        product_info_str = json.dumps(product_data, ensure_ascii=False, indent=2)
        prompt = POST_GENERATION_PROMPT.replace("{product_data}", product_info_str)

        if settings.DEBUG_MODE:
            print(f"[OpenAI] Отправляем промпт ({self.model}):\n{prompt[:500]}...")

        try:
            llm_response = await self.generate_json_response(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=prompt,
                max_output_tokens=self.RESPONSES_JSON_TOKENS
            )
        except OpenAIError as exc:
            raise RuntimeError(f"OpenAI вернул ошибку: {exc}") from exc

        if settings.DEBUG_MODE:
            print(f"[OpenAI] Получен ответ:\n{llm_response}")

        try:
            cleaned_response = llm_response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            return json.loads(cleaned_response)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenAI вернул невалидный JSON: {exc}") from exc

    async def generate_json_response(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int | None = None
    ) -> str:
        """
        Универсальный метод получения структурированного ответа (JSON) от модели.
        Всегда использует Chat Completions API для быстрой работы.
        """
        # Всегда используем Chat Completions API (быстрее, чем Responses API)
        text = await self._call_chat_completions(
            user_prompt,
            system_prompt=system_prompt,
            expect_json=True,
            max_tokens=max_output_tokens
        )
        if not text:
            raise ValueError("OpenAI вернул пустой ответ.")
        return text

    async def _call_chat_completions(
        self,
        prompt: str,
        system_prompt: str | None = None,
        expect_json: bool = True,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model_override: str | None = None,
    ) -> str:
        """
        Вызов Chat Completions API (gpt-4o, gpt-4o-mini, gpt-4.1-mini, gpt-5-mini и т.п.).
        
        Для моделей семейства gpt-5:
        - Используется max_completion_tokens вместо max_tokens
        - Параметр temperature не поддерживается
        """
        messages = [
            {"role": "system", "content": system_prompt or self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        model_name = model_override or self.model
        is_gpt5_model = self._requires_responses_api(model_name)  # Проверяем, является ли модель gpt-5
        
        kwargs = {
            "model": model_name,
            "messages": messages,
        }
        if expect_json:
            kwargs["response_format"] = {"type": "json_object"}
        
        # Для моделей gpt-5 не поддерживается temperature
        if not is_gpt5_model:
            temp_value = temperature if temperature is not None else (0.1 if self.supports_temperature else None)
            if temp_value is not None and self.supports_temperature:
                kwargs["temperature"] = temp_value
        
        # Для моделей gpt-5 используется max_completion_tokens вместо max_tokens
        max_value = max_tokens if max_tokens is not None else (2000 if self.supports_max_tokens else None)
        if max_value is not None:
            if is_gpt5_model:
                kwargs["max_completion_tokens"] = max_value
            elif self.supports_max_tokens:
                kwargs["max_tokens"] = max_value

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def _call_responses_api(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_output_tokens: int | None = None
    ) -> str:
        """
        Вызов Responses API (семейство gpt-5.x) с автоувеличением лимита токенов.
        
        ВНИМАНИЕ: Этот метод отключён и не используется.
        Responses API слишком медленный из-за reasoning-запросов.
        Всегда используется Chat Completions API вместо этого.
        """
        max_tokens = max_output_tokens or self.RESPONSES_JSON_TOKENS
        max_cap = 6000
        last_dump = ""

        for attempt in range(3):
            response = await self.client.responses.create(
                model=self.model,
                input=self._build_responses_input(system_prompt or self.SYSTEM_PROMPT, prompt),
                max_output_tokens=max_tokens,
                reasoning={"effort": "medium"},
            )
            text = self._extract_text_from_response(response)
            if text:
                return text

            try:
                last_dump = json.dumps(response.model_dump(), ensure_ascii=False, indent=2)[:1500]
            except Exception:
                last_dump = repr(response)

            details = getattr(response, "incomplete_details", None) or {}
            reason = getattr(details, "reason", None) or details.get("reason")

            if reason == "max_output_tokens" and max_tokens < max_cap:
                max_tokens = min(max_cap, int(max_tokens * 1.8))
                await asyncio.sleep(0.2)
                continue

            if attempt < 2:
                await asyncio.sleep(0.2)

        raise ValueError(
            "OpenAI вернул пустой ответ для Responses API. Raw fragment:\n"
            f"{last_dump}"
        )

    async def translate_text(self, text: str, target_language: str = "ru") -> str:
        """
        Переводит текст на указанный язык через выбранную модель OpenAI.
        """
        if not text:
            return text

        user_prompt = (
            f"Переведи следующий текст на {target_language}. "
            "Ответь только переводом без пояснений.\n\n"
            f"{text}"
        )

        # Всегда используем Chat Completions API для перевода (быстрее и надёжнее)
        # Для моделей gpt-5 temperature не передаётся (не поддерживается)
        translated = await self._call_chat_completions(
            user_prompt,
            system_prompt="Ты профессиональный переводчик.",
            expect_json=False,
            max_tokens=self.RESPONSES_TRANSLATE_TOKENS,
            temperature=0.1 if not self._requires_responses_api(self.model) else None,
        )

        return translated.strip() or text

    @staticmethod
    def _extract_text_from_response(response) -> str:
        """
        Собирает текст из Responses API (response.output[*].content[*].text)
        """
        chunks: list[str] = []
        output = getattr(response, "output", None) or []
        for item in output:
            content_list: Iterable = getattr(item, "content", None) or []
            for part in content_list:
                text_value = OpenAIClient._extract_text_from_part(part)
                if text_value:
                    chunks.append(text_value)
        if chunks:
            return "".join(chunks)

        # fallback: некоторые версии SDK предоставляют output_text
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text
        return ""

    @staticmethod
    def _extract_text_from_part(part) -> str:
        """
        Универсально вынимает текст из элемента ответа Responses API.
        """
        # dataclass с атрибутом text
        text_attr = getattr(part, "text", None)
        if text_attr:
            if isinstance(text_attr, str):
                return text_attr
            if isinstance(text_attr, list):
                pieces = []
                for segment in text_attr:
                    segment_text = getattr(segment, "text", None)
                    if segment_text:
                        pieces.append(segment_text)
                    elif isinstance(segment, dict):
                        value = segment.get("text")
                        if value:
                            pieces.append(value)
                if pieces:
                    return "".join(pieces)

        # Словарь
        if isinstance(part, dict):
            value = part.get("text")
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                pieces = [seg.get("text") for seg in value if isinstance(seg, dict) and seg.get("text")]
                return "".join(pieces)

        return ""

    @staticmethod
    def _build_responses_input(system_text: str, user_text: str) -> list[dict]:
        return [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_text}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_text}],
            },
        ]

