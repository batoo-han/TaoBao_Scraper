"""
Клиент для взаимодействия с Yandex Vision: распознавание текста и таблиц на изображениях.
"""

from __future__ import annotations

import base64
from typing import Any, Dict

import httpx

from src.core.config import settings


class YandexVisionClient:
    """
    Минимальный клиент Yandex Vision для распознавания текста и табличных структур.
    """

    def __init__(self) -> None:
        self.endpoint = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"

    async def analyze_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Отправляет изображение на распознавание в Yandex Vision.

        Args:
            image_bytes: байтовое содержимое изображения.

        Returns:
            dict: Структура с результатами распознавания.
        """
        if not settings.YANDEX_VISION_API_KEY:
            raise RuntimeError("YANDEX_VISION_API_KEY не задан. Настройте ключ в .env или через админку.")

        headers = {
            "Authorization": f"Api-Key {settings.YANDEX_VISION_API_KEY}",
            "Content-Type": "application/json",
        }

        encoded = base64.b64encode(image_bytes).decode("ascii")

        request_payload: Dict[str, Any] = {
            "folderId": settings.YANDEX_FOLDER_ID,
            "analyzeSpecs": [
                {
                    "content": encoded,
                    "features": [
                        {
                            "type": "DOCUMENT_TEXT_DETECTION",
                            "textDetectionConfig": {
                                "model": settings.YANDEX_VISION_MODEL or "ocr",
                                "languageCodes": ["ru", "en"],
                            },
                        },
                        {
                            "type": "LAYOUT_DETECTION",
                        },
                    ],
                }
            ],
        }

        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(self.endpoint, headers=headers, json=request_payload)
            response.raise_for_status()
            payload = response.json()

        results = payload.get("results") or []
        if not results:
            return {}
        return results[0]

