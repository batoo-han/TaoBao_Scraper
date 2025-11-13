"""
Высокоуровневый сервис для анализа изображений товара:
- загрузка и распознавание текста (OCR);
- извлечение таблиц, их перевод и визуализация;
- генерация структурированных инсайтов через LLM.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from src.api.yandex_translate import YandexTranslateClient
from src.api.yandex_vision import YandexVisionClient
from src.core.config import settings
from src.core.config_manager import config_manager
from .models import ImageAnalysisResult, ImageTable, ImageTextBlock
from .renderer import render_table_image

logger = logging.getLogger(__name__)


class ImageTextAnalysisService:
    """
    Оркестратор анализа изображений. Предназначен для запуска из Scraper.
    """

    def __init__(self, *, translate_client: Optional[YandexTranslateClient] = None) -> None:
        self.translate_client = translate_client or YandexTranslateClient()
        self.vision_client = YandexVisionClient()
        self.output_dir = Path(settings.IMAGE_TEXT_OUTPUT_DIR)
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://item.taobao.com/",
        }
        self._max_download_bytes = 8 * 1024 * 1024  # 8 MB
        self._semaphore = asyncio.Semaphore(3)

    async def analyze_product_images(
        self,
        *,
        product_data: Dict[str, Any],
        sku_images: Iterable[str],
        detail_images: Iterable[Dict[str, Any]],
    ) -> ImageAnalysisResult:
        """
        Основной метод анализа: скачивает изображения, распознаёт текст/таблицы,
        переводит и готовит данные для дальнейшей обработки.
        """
        runtime_config = config_manager.get_runtime_cache()
        if not runtime_config.get("ENABLE_IMAGE_TEXT_ANALYSIS", settings.ENABLE_IMAGE_TEXT_ANALYSIS):
            return ImageAnalysisResult()

        ocr_provider = (
            runtime_config.get("IMAGE_TEXT_OCR_PROVIDER", settings.IMAGE_TEXT_OCR_PROVIDER) or "yandex"
        ).lower()
        if ocr_provider != "yandex":
            logger.warning("Image OCR: провайдер '%s' пока не поддерживается", ocr_provider)
            return ImageAnalysisResult()

        output_dir_value = runtime_config.get("IMAGE_TEXT_OUTPUT_DIR", settings.IMAGE_TEXT_OUTPUT_DIR) or (
            settings.IMAGE_TEXT_OUTPUT_DIR
        )
        self.output_dir = Path(output_dir_value)

        image_entries = self._collect_unique_images(sku_images, detail_images)
        if not image_entries:
            return ImageAnalysisResult()

        raw_results: List[Optional[Dict[str, Any]]] = []
        tasks = [self._process_single_image(entry) for entry in image_entries]
        for result in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(result, Exception):
                logger.debug("Image OCR: исключение %s", result)
                continue
            if result:
                raw_results.append(result)

        if not raw_results:
            return ImageAnalysisResult()

        target_language = (
            runtime_config.get("IMAGE_TEXT_TRANSLATE_LANGUAGE", settings.IMAGE_TEXT_TRANSLATE_LANGUAGE) or "ru"
        )
        translation_cache: Dict[str, str] = {}

        analysis = ImageAnalysisResult()
        aggregated_parts: List[str] = []

        for idx, record in enumerate(raw_results, start=1):
            source_url = record["source_url"]
            for block in record.get("text_blocks", []):
                original_text = block.get("text", "").strip()
                if not original_text:
                    continue
                translated = await self._translate_text(original_text, target_language, translation_cache)
                analysis.text_blocks.append(
                    ImageTextBlock(
                        source_url=source_url,
                        original_text=original_text,
                        translated_text=translated,
                        language=block.get("language"),
                        confidence=block.get("confidence"),
                    )
                )
                aggregated_parts.append(translated.strip())

            for table_idx, table in enumerate(record.get("tables", []), start=1):
                rows = table.get("rows", [])
                if not rows:
                    continue

                translated_rows: List[List[str]] = []
                for row in rows:
                    translated_row = []
                    for cell in row:
                        translated_cell = await self._translate_text(cell, target_language, translation_cache)
                        translated_row.append(translated_cell)
                    translated_rows.append(translated_row)

                try:
                    image_path = render_table_image(
                        translated_rows,
                        output_dir=self.output_dir,
                        source_url=source_url,
                        table_index=idx * 10 + table_idx,
                    ).resolve()
                except Exception as render_err:
                    logger.debug("Image OCR: не удалось визуализировать таблицу: %s", render_err)
                    image_path = None

                table_result = ImageTable(
                    source_url=source_url,
                    rows=rows,
                    translated_rows=translated_rows,
                    image_path=str(image_path) if image_path else None,
                    confidence=table.get("confidence"),
                )
                analysis.tables.append(table_result)
                if image_path:
                    analysis.table_image_paths.append(str(image_path))

        aggregated_text = "\n".join(part for part in aggregated_parts if part).strip()
        if len(aggregated_text) > 6000:
            aggregated_text = aggregated_text[:6000]
        analysis.aggregated_text = aggregated_text

        try:
            insights = await self._generate_insights(analysis, runtime_config)
            analysis.insights = insights
            self._apply_table_insights(analysis, insights)
        except Exception as llm_error:
            logger.warning("Image OCR: не удалось получить инсайты из LLM: %s", llm_error)

        return analysis

    async def _process_single_image(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = entry["url"]
        try:
            async with self._semaphore:
                image_bytes = await self._download_image(url)
                if not image_bytes:
                    return None
                vision_payload = await self.vision_client.analyze_image(image_bytes)
        except Exception as exc:
            logger.debug("Image OCR: ошибка обработки %s: %s", url, exc)
            return None

        text_blocks, tables = self._parse_vision_result(vision_payload)
        if not text_blocks and not tables:
            return None

        return {
            "source_url": url,
            "text_blocks": text_blocks,
            "tables": tables,
        }

    async def _download_image(self, url: str) -> Optional[bytes]:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=self._headers) as client:
            response = await client.get(url)
            if response.status_code != 200 or not response.content:
                return None
            if len(response.content) > self._max_download_bytes:
                logger.debug("Image OCR: изображение %s превышает лимит %s байт", url, self._max_download_bytes)
                return None
            return response.content

    def _collect_unique_images(
        self,
        sku_images: Iterable[str],
        detail_images: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for url in sku_images:
            if url and url not in seen:
                seen.add(url)
                entries.append({"url": url, "source": "sku"})

        for info in detail_images:
            url = (info or {}).get("url")
            if url and url not in seen:
                seen.add(url)
                entries.append({"url": url, "source": "detail"})

        return entries

    def _parse_vision_result(self, payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        text_blocks: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []

        results = payload.get("results") or []
        for result in results:
            inner_results = result.get("results") or []
            for inner in inner_results:
                text_annotation = inner.get("textAnnotation") or {}
                if text_annotation:
                    blocks = self._extract_blocks_from_pages(text_annotation.get("pages") or [])
                    text_blocks.extend(blocks["text"])
                    tables.extend(blocks["tables"])

                layout = inner.get("layout") or {}
                if layout:
                    layout_blocks = self._extract_blocks_from_pages(layout.get("pages") or [], layout_key="blockType")
                    text_blocks.extend(layout_blocks["text"])
                    tables.extend(layout_blocks["tables"])

        # Fallback на полный текст
        if not text_blocks:
            full_text = self._extract_full_text(payload)
            if full_text:
                text_blocks.append({"text": full_text, "language": None, "confidence": None})

        return text_blocks, tables

    def _extract_blocks_from_pages(
        self,
        pages: Iterable[Dict[str, Any]],
        *,
        layout_key: str = "type",
    ) -> Dict[str, List[Dict[str, Any]]]:
        text_blocks: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []

        for page in pages:
            blocks = page.get("blocks") or []
            for block in blocks:
                block_type = block.get(layout_key)
                confidence = block.get("confidence")
                if block_type == "TEXT":
                    text = self._extract_text_from_block(block)
                    if text:
                        language = None
                        props = block.get("properties") or {}
                        langs = props.get("detectedLanguages") or []
                        if langs:
                            language = langs[0].get("languageCode")
                        text_blocks.append(
                            {
                                "text": text,
                                "language": language,
                                "confidence": confidence,
                            }
                        )
                elif block_type == "TABLE":
                    table = self._extract_table_from_block(block)
                    if table:
                        tables.append({"rows": table, "confidence": confidence})
        return {"text": text_blocks, "tables": tables}

    def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        lines = block.get("lines") or []
        collected_lines: List[str] = []
        for line in lines:
            words = line.get("words") or []
            word_values = [word.get("text") for word in words if word.get("text")]
            if word_values:
                collected_lines.append(" ".join(word_values))
        text = "\n".join(collected_lines).strip()
        if text:
            return text

        # запасной вариант
        text_obj = block.get("text") or {}
        if isinstance(text_obj, dict):
            return text_obj.get("text", "").strip()
        if isinstance(text_obj, str):
            return text_obj.strip()
        return ""

    def _extract_table_from_block(self, block: Dict[str, Any]) -> List[List[str]]:
        table = block.get("table") or block
        rows_data = table.get("rows") or []
        extracted: List[List[str]] = []
        for row in rows_data:
            row_cells = row.get("cells") or []
            row_values: List[str] = []
            for cell in row_cells:
                cell_text = cell.get("text")
                if isinstance(cell_text, dict):
                    value = cell_text.get("text", "")
                elif isinstance(cell_text, str):
                    value = cell_text
                else:
                    value = ""
                    lines = cell.get("lines") or []
                    for line in lines:
                        words = [w.get("text") for w in line.get("words", []) if w.get("text")]
                        if words:
                            value += (" " + " ".join(words))
                row_values.append(value.strip())
            extracted.append(row_values)
        return extracted

    def _extract_full_text(self, payload: Dict[str, Any]) -> str:
        try:
            results = payload.get("results") or []
            for result in results:
                inner = result.get("results") or []
                for block in inner:
                    text_annotation = block.get("textAnnotation") or {}
                    text = text_annotation.get("fullText") or text_annotation.get("text")
                    if text:
                        return str(text).strip()
        except Exception:
            pass
        return ""

    async def _translate_text(
        self,
        text: str,
        target_language: str,
        cache: Dict[str, str],
    ) -> str:
        normalized = text.strip()
        if not normalized:
            return ""
        cache_key = (normalized, target_language)
        if cache_key in cache:
            return cache[cache_key]
        try:
            translated = await self.translate_client.translate_text(normalized, target_language=target_language)
        except Exception as exc:
            logger.debug("Image OCR: не удалось перевести текст '%s': %s", normalized[:60], exc)
            translated = normalized
        cache[cache_key] = translated
        return translated

    async def _generate_insights(
        self,
        analysis: ImageAnalysisResult,
        runtime_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not analysis.text_blocks and not analysis.tables:
            return {}

        prompt_template = runtime_config.get("IMAGE_TEXT_SUMMARY_PROMPT") or settings.IMAGE_TEXT_SUMMARY_PROMPT
        temperature = 0.1
        max_tokens = 700

        text_section = ""
        if analysis.text_blocks:
            parts = []
            for idx, block in enumerate(analysis.text_blocks, start=1):
                snippet = block.translated_text.strip()
                if snippet:
                    parts.append(f"{idx}. {snippet}")
            text_section = "\n".join(parts)

        tables_section = ""
        if analysis.tables:
            parts = []
            for idx, table in enumerate(analysis.tables, start=1):
                formatted_rows = [" | ".join(row) for row in table.translated_rows]
                table_text = "\n".join(formatted_rows)
                parts.append(f"Таблица {idx}:\n{table_text}")
            tables_section = "\n\n".join(parts)

        final_prompt = (
            f"{prompt_template}\n\n"
            f"### Текстовые фрагменты:\n{text_section or '—'}\n\n"
            f"### Таблицы:\n{tables_section or '—'}"
        )

        raw = await self._call_yandex_llm(
            prompt=final_prompt,
            model=settings.YANDEX_GPT_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if not cleaned:
                return {}
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Image OCR: LLM вернул невалидный JSON: %s", exc)
            logger.debug("Image OCR: сырой ответ LLM:\n%s", raw)
            return {}

    async def _call_yandex_llm(self, *, prompt: str, model: str, temperature: float, max_tokens: int) -> str:
        headers = {
            "Authorization": f"Api-Key {settings.YANDEX_GPT_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "modelUri": f"gpt://{settings.YANDEX_FOLDER_ID}/{model}",
            "completionOptions": {
                "stream": False,
                "temperature": max(0.0, min(1.0, temperature)),
                "maxTokens": str(max_tokens),
            },
            "messages": [
                {
                    "role": "system",
                    "text": (
                        "Ты аналитик характеристик товаров. Отвечай строго валидным JSON без комментариев "
                        "и Markdown. Не выдумывай данные."
                    ),
                },
                {
                    "role": "user",
                    "text": prompt,
                },
            ],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            payload = response.json()

        alternatives = (
            payload.get("result", {})
            .get("alternatives", [])
        )
        if not alternatives:
            raise RuntimeError("Пустой ответ YandexGPT для анализа изображений.")

        return alternatives[0].get("message", {}).get("text", "")

    def _apply_table_insights(self, analysis: ImageAnalysisResult, insights: Dict[str, Any]) -> None:
        tables_info = insights.get("tables")
        if not isinstance(tables_info, list):
            return

        mapping = {}
        for item in tables_info:
            try:
                index = int(item.get("index"))
            except Exception:
                continue
            mapping[index] = item

        for idx, table in enumerate(analysis.tables, start=1):
            info = mapping.get(idx)
            if not info:
                continue
            classification = info.get("title") or info.get("type")
            summary = info.get("summary") or info.get("notes")
            if classification:
                table.classification = classification
            if summary:
                table.summary = summary

