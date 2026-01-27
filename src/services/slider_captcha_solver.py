"""
Локальный решатель слайдер-капчи (без внешних сервисов).

Важно: этот подход эвристический. Он может работать нестабильно,
если SZWEGO изменит вид капчи или применит антибот-меры.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageChops, ImageFilter, ImageOps


@dataclass
class SliderMatchResult:
    """
    Результат поиска позиции слайдера.

    - offset_x: найденное смещение (в пикселях) относительно левого края фона.
    - score: итоговая метрика (меньше — лучше).
    - confidence: эвристическая уверенность (0..1).
    """

    offset_x: int
    score: float
    confidence: float


def _to_edges(img: Image.Image) -> Image.Image:
    """
    Преобразует изображение в чёрно-белые контуры для более устойчивого сравнения.
    """
    gray = ImageOps.grayscale(img)
    return gray.filter(ImageFilter.FIND_EDGES)


def _calc_diff_score(
    bg_crop: Image.Image,
    piece_edges: Image.Image,
    mask: Optional[Image.Image],
) -> float:
    """
    Вычисляет «стоимость» совпадения для участка фона.

    Чем меньше сумма различий, тем лучше совпадение.
    """
    diff = ImageChops.difference(bg_crop, piece_edges)
    if mask is not None:
        # Маска позволяет учитывать только непрозрачную часть фрагмента.
        diff = ImageChops.multiply(diff, mask)
    hist = diff.histogram()
    # Гистограмма для L-изображения имеет 256 значений (0..255).
    # Взвешиваем интенсивность на количество пикселей.
    return sum(idx * count for idx, count in enumerate(hist))


def _calc_color_score(
    bg_crop: Image.Image,
    piece: Image.Image,
) -> float:
    """
    Дополнительная метрика «близости» по цвету/текстуре.

    - приводим оба изображения к одинаковому размеру фрагмента;
    - считаем среднее абсолютное отклонение по каналам RGB.

    Чем МЕНЬШЕ значение, тем лучше совпадение по цвету/текстуре.
    """
    # Работаем в RGB независимо от исходного режима.
    bg_rgb = bg_crop.convert("RGB")
    piece_rgb = piece.convert("RGB")

    if bg_rgb.size != piece_rgb.size:
        bg_rgb = bg_rgb.resize(piece_rgb.size)

    # Вычисляем поканальное различие и усредняем.
    diff = ImageChops.difference(bg_rgb, piece_rgb)
    hist = diff.histogram()
    # Гистограмма для RGB имеет 256*3 значений:
    # [R0..R255, G0..G255, B0..B255].
    total_pixels = diff.size[0] * diff.size[1]
    if total_pixels == 0:
        return float("inf")

    channel_scores: list[float] = []
    for ch in range(3):
        offset = ch * 256
        s = 0
        for i in range(256):
            count = hist[offset + i]
            if count:
                s += i * count
        channel_scores.append(s / total_pixels)

    # Усредняем по каналам.
    return sum(channel_scores) / len(channel_scores)


def find_slider_offset(
    background: Image.Image,
    piece: Image.Image,
    *,
    min_confidence: float = 0.15,
    min_x: int | None = None,
    max_x: int | None = None,
) -> Optional[SliderMatchResult]:
    """
    Ищет оптимальную позицию фрагмента на фоне.

    Возвращает None, если уверенность слишком низкая.
    """
    # Контуры дают устойчивое сравнение на шумных картинках.
    bg_edges = _to_edges(background)
    piece_edges = _to_edges(piece)

    # Маска для прозрачности (если есть альфа-канал).
    mask = None
    if piece.mode in {"RGBA", "LA"}:
        mask = piece.split()[-1]
        mask = ImageOps.grayscale(mask)

    bg_w, bg_h = bg_edges.size
    pw, ph = piece_edges.size
    if pw <= 0 or ph <= 0 or pw > bg_w or ph > bg_h:
        return None

    best_x = 0
    best_score = float("inf")
    second_score = float("inf")

    # Ограничиваем диапазон по X (можно задать минимальный/максимальный сдвиг,
    # например, не искать позиции левее стартовой точки ползунка).
    x_start = 0 if min_x is None else max(0, int(min_x))
    x_end = (bg_w - pw) if max_x is None else min(bg_w - pw, int(max_x))
    if x_start > x_end:
        return None

    # Полноценный 2D‑поиск: фрагменту нужно совпасть с «дыркой» не только по X, но и по Y.
    # Для оценки совпадения используем комбинированный скоринг:
    #  - разница по контурам
    #  - разница по цвету/текстуре (RGB)
    # Это даёт более устойчивый результат на картинках с неоднородным освещением.
    for y in range(0, bg_h - ph + 1):
        for x in range(x_start, x_end + 1):
            crop_edges = bg_edges.crop((x, y, x + pw, y + ph))
            # Основная метрика — различие по контурам.
            edge_score = _calc_diff_score(crop_edges, piece_edges, mask)

            # Дополнительная метрика — различие по цвету/текстуре на исходном фоне.
            crop_color = background.crop((x, y, x + pw, y + ph))
            color_score = _calc_color_score(crop_color, piece)

            # Итоговый скоринг: взвешенная сумма.
            # Вес по цвету можно будет подстроить при необходимости.
            score = edge_score * 0.7 + color_score * 0.3
            if score < best_score:
                second_score = best_score
                best_score = score
                best_x = x
            elif score < second_score:
                second_score = score

    # Эвристика уверенности: сравниваем лучшие значения между собой.
    if second_score <= 0:
        confidence = 1.0
    else:
        confidence = max(0.0, min(1.0, 1.0 - (best_score / second_score)))

    if confidence < min_confidence:
        # Fallback (важно для Tencent slider captcha):
        # На некоторых капчах фрагмент (piece) почти однотонный (белый),
        # а “дырка” на фоне (bg) выделяется тёмным контуром.
        # В этом случае edge-template matching может давать очень низкую уверенность.
        # Используем fallback по тёмной "дырке", но строго в том же диапазоне X.
        hole_x = _detect_hole_x(
            background,
            piece.size,
            min_x=min_x,
            max_x=max_x,
        )
        if hole_x is None:
            return None
        # Возвращаем “уверенность” как 0.2 (минимально приемлемую) — это эвристика.
        return SliderMatchResult(offset_x=hole_x, score=best_score, confidence=max(min_confidence, 0.2))

    return SliderMatchResult(offset_x=best_x, score=best_score, confidence=confidence)


def _detect_hole_x(
    background: Image.Image,
    piece_size: tuple[int, int],
    *,
    min_x: int | None = None,
    max_x: int | None = None,
) -> Optional[int]:
    """
    Fallback-детектор позиции “дырки” по тёмным пикселям на фоне.

    Для типичной Tencent slider captcha:
    - “дырка” визуально тёмная/контрастная
    - располагается правее стартовой позиции фрагмента

    Возвращает offset_x (относительно левого края background) так, чтобы
    целевая точка drag в `szwego_auth.py` пришлась примерно в центр дырки.
    """
    bg = ImageOps.grayscale(background)
    # Лёгкое сглаживание, чтобы убрать мелкий шум, но сохранить контраст отверстия.
    bg = bg.filter(ImageFilter.GaussianBlur(radius=1.5))

    w, h = bg.size
    pw, ph = piece_size
    if pw <= 0 or ph <= 0:
        return None

    # Берём центральную полосу по высоте — там обычно расположена дырка
    y0 = max(0, int(h * 0.2))
    y1 = min(h, int(h * 0.85))
    crop = bg.crop((0, y0, w, y1))

    # Бинаризация «тёмных» пикселей с адаптивным порогом: выбираем уровень яркости,
    # при котором примерно 30% пикселей попадают в категорию «тёмных».
    hist = crop.histogram()
    total = sum(hist)
    target = total * 0.3
    acc = 0
    thr = 128
    for i, c in enumerate(hist):
        acc += c
        if acc >= target:
            thr = i
            break
    bw = crop.point(lambda p: 255 if p < thr else 0, mode="L")

    # Ищем связные компоненты простым сканированием по столбцам:
    # считаем, сколько “тёмных” пикселей в каждом x
    col_sum = []
    for x in range(w):
        col = bw.crop((x, 0, x + 1, bw.size[1]))
        # histogram[255] — количество белых пикселей (тёмных на исходнике)
        hist = col.histogram()
        col_sum.append(hist[255])

    # Сглаживаем кол-во по окну, чтобы получить “горб” по дырке
    win = max(5, pw // 10)
    smooth = []
    for i in range(w):
        a = max(0, i - win)
        b = min(w, i + win + 1)
        smooth.append(sum(col_sum[a:b]) / (b - a))

    # Ограничиваем диапазон по X (аналогично основному поиску / стартовой позиции слайдера).
    # По факту "дырка" в текущих капчах SZWEGO всегда находится в правой трети фона,
    # поэтому дополнительно сдвигаем минимум к ~1/3 ширины. Если в будущем поведение
    # изменится — достаточно ослабить этот коэффициент.
    right_third_start = int(w * 0.33)
    base_min_x = 0 if min_x is None else max(0, int(min_x))
    x_start = max(base_min_x, right_third_start)
    x_end = w - 1 if max_x is None else min(w - 1, int(max_x))
    if x_start > x_end:
        return None

    # Ищем максимум тёмных столбцов в указанном диапазоне — там и должна быть «дырка».
    best_i = max(range(x_start, x_end + 1), key=lambda i: smooth[i])
    best_val = smooth[best_i]

    # Если максимум слишком мал — значит дырка не детектится
    if best_val < 5:
        return None

    # Возвращаем левую координату так, чтобы центр совпал с best_i
    hole_left = int(best_i - (pw / 2))
    hole_left = max(0, min(w - pw, hole_left))
    return hole_left
