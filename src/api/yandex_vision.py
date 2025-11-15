"""
Клиент для взаимодействия с Yandex Vision: распознавание текста и таблиц на изображениях.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


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

        folder_id = settings.YANDEX_VISION_FOLDER_ID or settings.YANDEX_FOLDER_ID
        if not folder_id:
            raise RuntimeError(
                "Не указан идентификатор каталога для Yandex Vision. "
                "Заполните YANDEX_VISION_FOLDER_ID или общий YANDEX_FOLDER_ID."
            )

        request_payload: Dict[str, Any] = {
            "folderId": folder_id,
            "analyzeSpecs": [
                {
                    "content": encoded,
                    "features": [
                        {
                            "type": "TEXT_DETECTION",
                            "textDetectionConfig": {
                                # Доступные модели: page, page-column-sort, handwritten, table, markdown, math-markdown
                                # page - по умолчанию, для текста в одну колонку
                                "model": settings.YANDEX_VISION_MODEL or "page",
                                "languageCodes": ["ru", "en", "zh"],
                            },
                        },
                    ],
                    #"mimeType": "image/png",
                    #"signature": "content",
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                response = await client.post(self.endpoint, headers=headers, json=request_payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as http_err:
            body = http_err.response.text
            logger.error(
                "Yandex Vision HTTP %s: %s",
                http_err.response.status_code,
                body[:2000],
            )
            raise
        except httpx.RequestError as req_err:
            logger.error("Yandex Vision request error: %s", req_err)
            raise

        payload = response.json()
        results = payload.get("results") or []
        if not results:
            return {}
        return results[0]

