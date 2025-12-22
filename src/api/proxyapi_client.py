"""
Клиент для взаимодействия с ProxyAPI в режиме OpenAI-совместимого API.

Документация:
- Универсальный OpenAI-совместимый API: https://proxyapi.ru/docs/openai-compatible-api
- Оригинальный OpenAI API через ProxyAPI: https://proxyapi.ru/docs/openai-text-generation

В данном проекте мы используем OpenAI API через ProxyAPI:
BASE_URL = https://api.proxyapi.ru/openai/v1
"""

import json
from typing import Iterable, Optional

from openai import AsyncOpenAI, OpenAIError

from src.core.config import settings
from src.api.prompts import POST_GENERATION_PROMPT
from src.api.tokens_stats import TokensUsage, calculate_cost
from src.api.openai_pricing import get_effective_pricing


class ProxyAPIClient:
    """
    Клиент ProxyAPI, полностью совместимый по интерфейсу с OpenAIClient.
    Используется как ещё один провайдер LLM наряду с YandexGPT и OpenAI.
    """

    SYSTEM_PROMPT = (
        "Ты помощник для создания структурированного контента для постов в Telegram. "
        "КРИТИЧЕСКИ ВАЖНО: ВСЁ должно быть переведено на русский язык - названия цветов, бренды, "
        "любой текст. НЕ оставляй английские слова или китайские иероглифы. Всегда отвечай только валидным JSON."
    )

    RESPONSES_PREFIXES = ("gpt-5",)
    RESPONSES_JSON_TOKENS = 4500
    RESPONSES_TRANSLATE_TOKENS = 500

    def __init__(self, model_name: str | None = None) -> None:
        if not settings.PROXYAPI_API_KEY:
            raise ValueError(
                "PROXYAPI_API_KEY не задан. Укажите ключ ProxyAPI в .env, чтобы использовать провайдера proxyapi."
            )

        source_model = model_name or settings.OPENAI_MODEL or "gpt-4o-mini"
        model_raw = source_model.strip()
        self.model = model_raw or "gpt-4o-mini"
        # Для ProxyAPI намеренно не используем Responses API, чтобы избежать долгих reasoning-запросов.
        # Всегда работаем через /v1/chat/completions с JSON-форматом ответа.
        self.use_responses_api = False

        base_url = (getattr(settings, "PROXYAPI_BASE_URL", "") or "").strip() or None
        self.client = AsyncOpenAI(
            api_key=settings.PROXYAPI_API_KEY,
            base_url=base_url,
        )

    @classmethod
    def _requires_responses_api(cls, model_name: str) -> bool:
        normalized = (model_name or "").strip().lower()
        return any(normalized.startswith(prefix) for prefix in cls.RESPONSES_PREFIXES)

    async def generate_post_content(
        self, product_data: dict
    ) -> dict | tuple[dict, TokensUsage]:
        """
        Генерация описания товара через ProxyAPI (OpenAI-совместимое API).
        
        Returns:
            dict: JSON с содержимым поста
            tuple[dict, TokensUsage]: JSON с содержимым и статистика токенов (если используется новая сигнатура)
        """
        # Важно: используем компактный JSON, чтобы не тратить токены на пробелы/переносы строк
        product_info_str = json.dumps(product_data, ensure_ascii=False, separators=(",", ":"))
        prompt = POST_GENERATION_PROMPT.replace("{product_data}", product_info_str)

        try:
            result = await self.generate_json_response(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=prompt,
                max_output_tokens=self.RESPONSES_JSON_TOKENS,
            )
            # Новая сигнатура: возвращает кортеж (text, tokens_usage)
            if isinstance(result, tuple):
                llm_response, tokens_usage = result
            else:
                # Обратная совместимость
                llm_response = result
                tokens_usage = TokensUsage()
        except OpenAIError as exc:
            raise RuntimeError(f"ProxyAPI (OpenAI) вернул ошибку: {exc}") from exc

        try:
            cleaned_response = llm_response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            parsed_content = json.loads(cleaned_response)
            # Возвращаем кортеж для совместимости с новой сигнатурой
            return parsed_content, tokens_usage
        except json.JSONDecodeError as exc:
            raise ValueError(f"ProxyAPI (OpenAI) вернул невалидный JSON: {exc}") from exc

    async def generate_json_response(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int | None = None,
    ) -> str | tuple[str, TokensUsage]:
        """
        Универсальный метод получения структурированного ответа (JSON) от модели.
        
        Returns:
            str: Текст ответа (старая сигнатура для обратной совместимости)
            tuple[str, TokensUsage]: Текст ответа и статистика токенов (новая сигнатура)
        """
        result = await self._call_chat_completions(
            user_prompt,
            system_prompt=system_prompt,
            expect_json=True,
            max_tokens=max_output_tokens,
        )
        
        # Новая сигнатура: возвращает кортеж (text, tokens_usage)
        if isinstance(result, tuple):
            text, tokens_usage = result
        else:
            text = result
            tokens_usage = TokensUsage()
        
        if not text:
            raise ValueError("ProxyAPI (OpenAI) вернул пустой ответ.")
        
        return text, tokens_usage

    async def _call_chat_completions(
        self,
        prompt: str,
        system_prompt: str | None = None,
        expect_json: bool = True,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str | tuple[str, TokensUsage]:
        """
        Вызов Chat Completions API через ProxyAPI.
        
        Returns:
            str: Текст ответа (старая сигнатура)
            tuple[str, TokensUsage]: Текст ответа и статистика токенов (новая сигнатура)
        """
        messages = [
            {"role": "system", "content": system_prompt or self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        # Для моделей семейства gpt-5.x ProxyAPI (как и оригинальный OpenAI)
        # может не поддерживать параметры max_tokens/temperature в chat.completions
        # и ожидает max_completion_tokens при работе через Responses API.
        # Поэтому для таких моделей не передаём max_tokens/temperature в chat.completions.
        normalized = (self.model or "").strip().lower()
        supports_control_params = not normalized.startswith("gpt-5")

        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if expect_json:
            kwargs["response_format"] = {"type": "json_object"}
        if supports_control_params:
            if temperature is not None:
                kwargs["temperature"] = temperature
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

        response = await self.client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        
        # Извлекаем статистику токенов из response.usage
        # Согласно документации OpenAI/ProxyAPI, response.usage содержит:
        # - prompt_tokens: количество токенов во входном промпте
        # - completion_tokens: количество токенов в ответе
        # - total_tokens: общее количество токенов
        tokens_usage = TokensUsage()
        if hasattr(response, "usage") and response.usage is not None:
            usage = response.usage
            # Прямой доступ к атрибутам согласно документации OpenAI
            try:
                prompt_tokens = usage.prompt_tokens if hasattr(usage, "prompt_tokens") else 0
                completion_tokens = usage.completion_tokens if hasattr(usage, "completion_tokens") else 0
                # total_tokens может быть не указан, тогда вычисляем его
                if hasattr(usage, "total_tokens") and usage.total_tokens is not None:
                    total_tokens = usage.total_tokens
                else:
                    total_tokens = prompt_tokens + completion_tokens
                
                # Получаем цены токенов для ProxyAPI (за 1M токенов)
                prompt_price, completion_price = get_effective_pricing(
                    model_name=self.model,
                    prompt_price_override=getattr(settings, "PROXYAPI_PROMPT_PRICE_PER_1M", 0.0),
                    completion_price_override=getattr(settings, "PROXYAPI_COMPLETION_PRICE_PER_1M", 0.0),
                )
                
                # Если цены доступны, вычисляем стоимость
                if prompt_price > 0 or completion_price > 0:
                    tokens_usage = calculate_cost(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        prompt_price_per_1m=prompt_price if prompt_price > 0 else 0.0,
                        completion_price_per_1m=completion_price if completion_price > 0 else 0.0,
                    )
                else:
                    # Сохраняем только количество токенов без стоимости
                    tokens_usage = TokensUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )
            except (AttributeError, TypeError) as e:
                # Если возникла ошибка при доступе к атрибутам, логируем и продолжаем
                if settings.DEBUG_MODE:
                    print(f"[ProxyAPI] Ошибка при извлечении статистики токенов: {e}")
        
        return text, tokens_usage

    async def _call_responses_api(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """
        Вызов Responses API через ProxyAPI.

        ProxyAPI по документации полностью поддерживает эндпоинт /v1/responses,
        поэтому логика аналогична OpenAI.
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
                continue

        raise ValueError(
            "ProxyAPI (OpenAI) вернул пустой ответ для Responses API. Raw fragment:\n"
            f"{last_dump}"
        )

    async def translate_text(
        self, text: str, target_language: str = "ru"
    ) -> str | tuple[str, TokensUsage]:
        """
        Переводит текст на указанный язык через ProxyAPI.
        
        Returns:
            str: Переведённый текст (старая сигнатура)
            tuple[str, TokensUsage]: Переведённый текст и статистика токенов (новая сигнатура)
        """
        if not text:
            return text, TokensUsage()

        user_prompt = (
            f"Переведи следующий текст на {target_language}. "
            "Ответь только переводом без пояснений.\n\n"
            f"{text}"
        )

        result = await self._call_chat_completions(
            user_prompt,
            system_prompt="Ты профессиональный переводчик.",
            expect_json=False,
            max_tokens=self.RESPONSES_TRANSLATE_TOKENS,
            temperature=0.1,
        )
        
        # Новая сигнатура: возвращает кортеж (text, tokens_usage)
        if isinstance(result, tuple):
            translated, tokens_usage = result
        else:
            translated = result
            tokens_usage = TokensUsage()

        return (translated.strip() or text), tokens_usage

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
                text_value = ProxyAPIClient._extract_text_from_part(part)
                if text_value:
                    chunks.append(text_value)
        if chunks:
            return "".join(chunks)

        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text
        return ""

    @staticmethod
    def _extract_text_from_part(part) -> str:
        """
        Универсально вынимает текст из элемента ответа Responses API.
        """
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
                if pieces:
                    return "".join(pieces)

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


