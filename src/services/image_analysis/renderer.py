"""
Утилиты для визуализации распознанных таблиц в виде изображений.
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path
from typing import Iterable, List

from PIL import Image, ImageDraw, ImageFont


def _wrap_cell_text(text: str, width: int = 28) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return "\n".join(textwrap.wrap(text, width=width)) or text


def render_table_image(
    rows: Iterable[Iterable[str]],
    *,
    output_dir: Path,
    source_url: str,
    table_index: int,
) -> Path:
    """
    Преобразует табличные данные в изображение и сохраняет на диск.

    Args:
        rows: Список строк таблицы (уже переведённых).
        output_dir: Каталог для сохранения изображения.
        source_url: URL оригинального изображения (для генерации уникального имени).
        table_index: Порядковый номер таблицы.

    Returns:
        Path: Путь к сохранённому файлу PNG.
    """

    normalized_rows: List[List[str]] = [list(r) for r in rows]
    if not normalized_rows:
        raise ValueError("Пустая таблица не может быть визуализирована.")

    max_columns = max(len(row) for row in normalized_rows)
    for row in normalized_rows:
        if len(row) < max_columns:
            row.extend([""] * (max_columns - len(row)))

    output_dir.mkdir(parents=True, exist_ok=True)

    font = ImageFont.load_default()
    dummy_img = Image.new("RGB", (10, 10), "white")
    dummy_draw = ImageDraw.Draw(dummy_img)

    cell_padding_x = 16
    cell_padding_y = 12
    line_spacing = 4

    wrapped_rows: List[List[str]] = []
    col_widths = [0] * max_columns
    row_heights: List[int] = []

    for row in normalized_rows:
        wrapped_row: List[str] = []
        max_height = 0
        for col_index, cell in enumerate(row):
            wrapped = _wrap_cell_text(cell)
            wrapped_row.append(wrapped)
            bbox = dummy_draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=line_spacing)
            width = (bbox[2] - bbox[0]) + cell_padding_x * 2
            height = (bbox[3] - bbox[1]) + cell_padding_y * 2
            col_widths[col_index] = max(col_widths[col_index], width)
            max_height = max(max_height, height)
        wrapped_rows.append(wrapped_row)
        row_heights.append(max_height)

    table_width = sum(col_widths) + (max_columns + 1)  # учёт линий
    table_height = sum(row_heights) + (len(row_heights) + 1)

    image = Image.new("RGB", (table_width, table_height), "white")
    draw = ImageDraw.Draw(image)

    current_y = 1
    for row_index, wrapped_row in enumerate(wrapped_rows):
        current_x = 1
        is_header = row_index == 0
        for col_index, cell_text in enumerate(wrapped_row):
            cell_width = col_widths[col_index]
            cell_height = row_heights[row_index]
            box = (current_x, current_y, current_x + cell_width, current_y + cell_height)
            background_color = "#eef3ff" if is_header else "#ffffff"
            draw.rectangle(box, fill=background_color, outline="#d0d7e9", width=1)

            text_bbox = draw.multiline_textbbox(
                (current_x, current_y),
                cell_text,
                font=font,
                spacing=line_spacing,
            )
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = current_x + (cell_width - text_width) / 2
            text_y = current_y + (cell_height - text_height) / 2
            draw.multiline_text(
                (text_x, text_y),
                cell_text,
                font=font,
                fill="#1a1a1a",
                spacing=line_spacing,
                align="center",
            )

            current_x += cell_width + 1
        current_y += row_heights[row_index] + 1

    hash_seed = f"{source_url}|{table_index}".encode("utf-8")
    filename = f"table_{table_index}_{hashlib.sha1(hash_seed).hexdigest()[:10]}.png"
    output_path = output_dir / filename
    image.save(output_path, format="PNG")
    return output_path

