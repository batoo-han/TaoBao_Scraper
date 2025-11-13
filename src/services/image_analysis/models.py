"""
Модели данных для результатов анализа изображений.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class ImageTextBlock:
    """Распознанный текстовый фрагмент на изображении."""

    source_url: str
    original_text: str
    translated_text: str
    language: Optional[str] = None
    confidence: Optional[float] = None


@dataclass(slots=True)
class ImageTable:
    """Структурированная таблица, извлечённая с изображения."""

    source_url: str
    rows: List[List[str]]
    translated_rows: List[List[str]]
    classification: Optional[str] = None
    summary: Optional[str] = None
    image_path: Optional[str] = None
    confidence: Optional[float] = None


@dataclass(slots=True)
class ImageAnalysisResult:
    """Сводный результат анализа всех изображений товара."""

    text_blocks: List[ImageTextBlock] = field(default_factory=list)
    tables: List[ImageTable] = field(default_factory=list)
    aggregated_text: str = ""
    insights: Dict[str, Any] = field(default_factory=dict)
    table_image_paths: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Возвращает сериализованную структуру для сохранения в product_data."""
        return {
            "aggregated_text": self.aggregated_text,
            "insights": self.insights,
            "text_blocks": [
                {
                    "source_url": block.source_url,
                    "original_text": block.original_text,
                    "translated_text": block.translated_text,
                    "language": block.language,
                    "confidence": block.confidence,
                }
                for block in self.text_blocks
            ],
            "tables": [
                {
                    "source_url": table.source_url,
                    "rows": table.rows,
                    "translated_rows": table.translated_rows,
                    "classification": table.classification,
                    "summary": table.summary,
                    "image_path": table.image_path,
                    "confidence": table.confidence,
                }
                for table in self.tables
            ],
            "generated_images": list(self.table_image_paths),
        }

