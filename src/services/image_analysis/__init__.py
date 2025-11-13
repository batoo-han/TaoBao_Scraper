"""
Подсистема анализа изображений: распознавание текста, обработка таблиц и генерация выводов.
"""

from .models import (
    ImageAnalysisResult,
    ImageTable,
    ImageTextBlock,
)
from .service import ImageTextAnalysisService

__all__ = [
    "ImageAnalysisResult",
    "ImageTable",
    "ImageTextBlock",
    "ImageTextAnalysisService",
]

