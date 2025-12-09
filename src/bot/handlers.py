import asyncio
import random
import logging
import re
import time
import uuid
import json
from collections import deque
from aiogram import Router, F
from aiogram.types import (
    Message,
    InputMediaPhoto,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import httpx
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatAction

from src.core.config import settings
from src.core.scraper import Scraper
import src.bot.error_handler as error_handler_module
from src.services.user_settings import get_user_settings_service
from src.services.access_control import (
    access_control_service,
    is_admin_user,
    parse_ids_and_usernames,
)

logger = logging.getLogger(__name__)


async def _safe_clear_markup(message: Message | None) -> None:
    """Безопасно убираем inline-клавиатуру, игнорируя ошибку 'message is not modified'."""
    if not message:
        return
    # Если клавиатура уже убрана — ничего не делаем
    if message.reply_markup is None:
        return
    try:
        await message.edit_reply_markup()
    except TelegramBadRequest as e:
        # Игнорируем стандартную ошибку Telegram, если разметка не изменилась
        if "message is not modified" in str(e):
            return
        raise


def _log_json(level: str, **payload):
    """Структурированное логирование в JSON."""
    msg = json.dumps(payload, ensure_ascii=False)
    getattr(logger, level, logger.info)(msg)

# Инициализация роутера для обработки сообщений
router = Router()
# Инициализация скрапера для получения информации о товарах
scraper = Scraper()
# Инициализация сервиса настроек пользователей
user_settings_service = get_user_settings_service()


class SettingsState(StatesGroup):
    """Состояния для меню настроек"""
    waiting_signature = State()
    waiting_exchange_rate = State()


class AccessState(StatesGroup):
    """Состояния для меню управления доступом (белый/чёрный список)"""
    choosing_action = State()
    editing_whitelist = State()
    editing_blacklist = State()


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Создаёт главное меню"""
    keyboard = [
        [KeyboardButton(text="📦 Запросить описание товара")],
        [KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def build_settings_menu_keyboard(user_id: int | None = None) -> ReplyKeyboardMarkup:
    """
    Создаёт меню настроек с кнопкой запуска Mimi App, если указана ссылка в настройках.
    Для пользователей с валютой RUB добавляет кнопку смены курса.
    """
    rows: list[list[KeyboardButton]] = []

    mini_app_url = (getattr(settings, "MINI_APP_URL", "") or "").strip()
    if mini_app_url:
        rows.append([KeyboardButton(text="🧩 Mimi App", web_app=WebAppInfo(url=mini_app_url))])

    rows.append([KeyboardButton(text="✍️ Изменить подпись")])
    rows.append([KeyboardButton(text="💱 Валюта"), KeyboardButton(text="ℹ️ Мои настройки")])

    try:
        if user_id is not None:
            settings_obj = user_settings_service.get_settings(user_id)
            if settings_obj.default_currency.lower() == "rub":
                rows.append([KeyboardButton(text="📈 Сменить курс")])
    except Exception:
        # В случае ошибки не блокируем построение клавиатуры
        pass

    rows.append([KeyboardButton(text="🔙 В главное меню")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def build_currency_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора валюты"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Юань (¥)", callback_data="currency:cny")],
            [InlineKeyboardButton(text="Рубль (₽)", callback_data="currency:rub")],
            [InlineKeyboardButton(text="Отмена", callback_data="currency:cancel")],
        ]
    )


def format_settings_summary(user_settings) -> str:
    """Форматирует сводку настроек пользователя"""
    currency = user_settings.default_currency.upper()
    signature = user_settings.signature or "—"
    rate = user_settings.exchange_rate
    rate_display = f"{float(rate):.4f} ₽ за 1 ¥" if rate else "не задан"
    return (
        "<b>Ваши настройки</b>\n"
        f"• подпись: <code>{signature}</code>\n"
        f"• валюта по умолчанию: <b>{currency}</b>\n"
        f"• курс для рубля: {rate_display}"
    ) 


async def ensure_access(message: Message) -> bool:
    """
    Проверяет, есть ли у пользователя доступ к боту.
    Администраторы всегда имеют доступ.
    При отказе отправляет пользователю понятное сообщение.
    """
    user = message.from_user
    user_id = user.id
    username = user.username or ""

    # Админы всегда имеют доступ, независимо от списков
    if is_admin_user(user_id, username):
        return True

    allowed, reason = access_control_service.is_allowed(user_id, username)
    if allowed:
        return True

    support_nick = (getattr(settings, "ACCESS_SUPPORT_USERNAME", "") or "").lstrip("@")
    support_suffix = f" @{support_nick}" if support_nick else ""

    text = (
        "⛔ Доступ к этому боту ограничен.\n\n"
        f"{reason or 'Вы сейчас не можете пользоваться ботом.'}\n\n"
        f"Если вы считаете, что это ошибка, обратитесь к администратору{support_suffix}."
    )
    await message.answer(text)
    return False


MAX_TEXT_CHUNK = 2000
CAPTION_TEXT_LIMIT = 1000  # Telegram captions <= 1024 символов
PUNCTUATION_BREAKS = ('.', '!', '?', ';', ':', ',', '…', '\n')
MIN_BREAK_RATIO = 0.4
HTML_SELF_CLOSING_TAGS = {"br", "hr"}
HTML_TAG_PATTERN = re.compile(r"<(/?)([a-zA-Z0-9]+)(?:\s[^<>]*)?>")


def split_text_chunks(text: str, limit: int) -> list[str]:
    """
    Делит текст на части, стараясь обрывать по знакам препинания, переносам строк или пробелам.
    Также следит, чтобы разбиение не приходилось на середину HTML-тегов.
    """
    if not text:
        return []

    cleaned = text.strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    idx = 0
    length = len(cleaned)
    min_break = max(int(limit * MIN_BREAK_RATIO), 120)

    while idx < length:
        target = min(idx + limit, length)
        candidate = cleaned[idx:target]

        break_idx = -1
        for pos in range(len(candidate) - 1, -1, -1):
            if candidate[pos] in PUNCTUATION_BREAKS:
                if pos >= min_break or target == length:
                    break_idx = pos + 1
                    break

        if break_idx == -1:
            space_idx = candidate.rfind(' ')
            if space_idx != -1 and (space_idx >= min_break or target == length):
                break_idx = space_idx + 1

        if break_idx > 0:
            target = idx + break_idx
            candidate = cleaned[idx:target]

        last_lt = candidate.rfind('<')
        last_gt = candidate.rfind('>')
        if last_lt > last_gt:
            closing = cleaned.find('>', target)
            if closing != -1:
                target = closing + 1
                candidate = cleaned[idx:target]
            else:
                candidate = candidate[:last_lt]
                target = idx + last_lt

        chunk = candidate.strip()
        if not chunk:
            chunk = cleaned[idx:target].strip()

        if not chunk:
            idx = target if target > idx else idx + 1
            continue

        fragment, adjusted_target = _extend_chunk_to_close_tags(cleaned, idx, target)
        fragment = fragment.strip()
        if not fragment:
            idx = adjusted_target if adjusted_target > idx else idx + 1
            continue

        chunks.append(fragment)
        idx = adjusted_target

    return chunks


def prepare_caption_and_queue(text: str) -> tuple[str, deque[str]]:
    """
    Возвращает текст подписи для первой медиагруппы и очередь оставшихся частей поста.
    """
    base_chunks = split_text_chunks(text, MAX_TEXT_CHUNK)
    if not base_chunks:
        return "", deque()

    remaining = deque(base_chunks[1:])
    caption_parts = split_text_chunks(base_chunks[0], CAPTION_TEXT_LIMIT)
    caption_text = caption_parts[0] if caption_parts else base_chunks[0]

    # Остаток от подписи возвращаем в очередь, чтобы не потерять текст
    for part in reversed(caption_parts[1:]):
        remaining.appendleft(part)

    return caption_text, remaining


async def send_text_sequence(message: Message, chunks: list[str]) -> None:
    """
    Отправляет список текстовых сообщений по очереди.
    """
    for chunk in chunks:
        if not chunk or not chunk.strip():
            continue
        await message.answer(chunk.strip(), parse_mode="HTML")


async def _send_single_photo(message: Message, url: str, caption: str | None) -> bool:
    """
    Отправляет одиночное фото с подписью. Возвращает True при успехе.
    """
    parse_mode = "HTML" if caption else None
    try:
        await message.answer_photo(url, caption=caption or None, parse_mode=parse_mode)
        return True
    except TelegramBadRequest:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                response = await client.get(url)
                if response.status_code == 200 and response.content:
                    buffer = BufferedInputFile(response.content, filename="photo.jpg")
                    await message.answer_photo(buffer, caption=caption or None, parse_mode=parse_mode)
                    return True
        except Exception:
            pass
    except Exception:
        pass
    return False


async def _send_media_group(message: Message, urls: list[str], caption: str | None) -> bool:
    """
    Отправляет медиагруппу (2-10 фото) с опциональной подписью на первом фото.
    """
    if not urls:
        return False

    media = []
    for idx, url in enumerate(urls):
        if idx == 0 and caption:
            media.append(InputMediaPhoto(media=url, caption=caption, parse_mode="HTML"))
        else:
            media.append(InputMediaPhoto(media=url))

    try:
        await message.answer_media_group(media=media)
        return True
    except TelegramBadRequest:
        pass
    except Exception:
        pass

    files: list[InputMediaPhoto] = []
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            for idx, url in enumerate(urls):
                try:
                    response = await client.get(url)
                    if response.status_code != 200 or not response.content:
                        continue
                    buffer = BufferedInputFile(response.content, filename=f"album_{idx+1}.jpg")
                    if not files and caption:
                        files.append(InputMediaPhoto(media=buffer, caption=caption, parse_mode="HTML"))
                    else:
                        files.append(InputMediaPhoto(media=buffer))
                except Exception:
                    continue
        if files:
            await message.answer_media_group(media=files)
            return True
    except TelegramBadRequest:
        pass
    except Exception:
        pass

    return False


async def send_media_block(message: Message, urls: list[str], caption: str | None) -> bool:
    """
    Универсальная отправка фотоблока: одиночное фото или альбом.
    """
    if not urls:
        return False
    if len(urls) == 1:
        return await _send_single_photo(message, urls[0], caption)
    return await _send_media_group(message, urls, caption)


def _normalize_broadcast_chat_id(raw: str | int | None) -> int | str | None:
    """
    Приводит идентификатор канала/группы к формату, который понимает Telegram Bot API.
    
    Правила нормализации:
    - @username остаётся как есть
    - Отрицательные числа (для групп/супергрупп) остаются как есть
    - Удаляет пробелы из числовых ID (например, "3 018 683 678" -> "3018683678")
    - Положительные числа > 1e9 считаются ID группы и преобразуются в отрицательные
    
    Возвращает None, если канал не указан.
    """
    if raw is None:
        return None
    value = str(raw).strip()
    # Удаляем пробелы из числовых ID (ID могут отображаться с пробелами в интерфейсе)
    value = value.replace(" ", "").replace("_", "")
    if not value:
        return None
    if value.startswith("@"):
        return value
    if value.lstrip("-").isdigit():
        try:
            num_value = int(value)
            return num_value
        except Exception:
            return value
    return value


def _get_chat_id_variants(raw_channel_id: str | int | None, normalized_chat_id: int | str | None) -> list[int | str]:
    """
    Генерирует список вариантов ID чата для попытки отправки.
    
    Telegram может использовать разные форматы ID в зависимости от типа группы:
    - Обычная группа: отрицательное число (-ID)
    - Супергруппа: -100 + ID (например, -1001234567890)
    
    Возвращает список вариантов ID, которые стоит попробовать.
    """
    variants: list[int | str] = []

    # 1) Если есть сырой ID (@username остаётся приоритетным)
    if isinstance(raw_channel_id, str):
        raw_clean = raw_channel_id.replace(" ", "").replace("_", "")
        if raw_clean.startswith("@"):
            variants.append(raw_clean)
        if raw_clean.lstrip("-").isdigit():
            try:
                raw_num = int(raw_clean)
                variants.append(raw_num)
                variants.append(-raw_num)
                variants.append(-int(f"100{abs(raw_num)}"))
            except Exception:
                variants.append(raw_clean)

    # 2) Варианты из нормализованного значения
    if isinstance(normalized_chat_id, str):
        norm_clean = normalized_chat_id.replace(" ", "").replace("_", "")
        if norm_clean.startswith("@"):
            variants.append(norm_clean)
        if norm_clean.lstrip("-").isdigit():
            try:
                norm_num = int(norm_clean)
                variants.append(norm_num)
                variants.append(-norm_num)
                variants.append(-int(f"100{abs(norm_num)}"))
            except Exception:
                variants.append(norm_clean)

    if isinstance(normalized_chat_id, int):
        variants.append(normalized_chat_id)
        variants.append(-normalized_chat_id)
        variants.append(-int(f"100{abs(normalized_chat_id)}"))
    
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)
    
    return unique_variants


async def _send_single_photo_to_chat(bot, chat_id: int | str, url: str, caption: str | None) -> bool:
    """
    Отправляет одиночное фото в указанный чат (канал) с fallback на загрузку файла.
    """
    parse_mode = "HTML" if caption else None
    try:
        await bot.send_photo(chat_id=chat_id, photo=url, caption=caption or None, parse_mode=parse_mode)
        return True
    except TelegramBadRequest:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                response = await client.get(url)
                if response.status_code == 200 and response.content:
                    buffer = BufferedInputFile(response.content, filename="photo.jpg")
                    await bot.send_photo(chat_id=chat_id, photo=buffer, caption=caption or None, parse_mode=parse_mode)
                    return True
        except Exception:
            pass
    except Exception:
        pass
    return False


async def _send_media_block_to_chat(bot, chat_id: int | str, urls: list[str], caption: str | None) -> bool:
    """
    Универсальная отправка фотоблока в указанный чат: одиночное фото или альбом.
    """
    if not urls:
        return False

    if len(urls) == 1:
        return await _send_single_photo_to_chat(bot, chat_id, urls[0], caption)

    media = []
    for idx, url in enumerate(urls):
        if idx == 0 and caption:
            media.append(InputMediaPhoto(media=url, caption=caption, parse_mode="HTML"))
        else:
            media.append(InputMediaPhoto(media=url))

    try:
        await bot.send_media_group(chat_id=chat_id, media=media)
        return True
    except TelegramBadRequest:
        pass
    except Exception:
        pass

    files: list[InputMediaPhoto] = []
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            for idx, url in enumerate(urls):
                try:
                    response = await client.get(url)
                    if response.status_code != 200 or not response.content:
                        continue
                    buffer = BufferedInputFile(response.content, filename=f"album_{idx+1}.jpg")
                    if not files and caption:
                        files.append(InputMediaPhoto(media=buffer, caption=caption, parse_mode="HTML"))
                    else:
                        files.append(InputMediaPhoto(media=buffer))
                except Exception:
                    continue
        if files:
            await bot.send_media_group(chat_id=chat_id, media=files)
            return True
    except TelegramBadRequest:
        pass
    except Exception:
        pass

    return False


async def _send_text_sequence_to_chat(bot, chat_id: int | str, chunks: list[str]) -> None:
    """
    Отправляет последовательность текстов в указанный чат (канал).
    """
    for chunk in chunks:
        if not chunk or not chunk.strip():
            continue
        await bot.send_message(chat_id=chat_id, text=chunk.strip(), parse_mode="HTML")


async def broadcast_post_to_channel(
    *,
    bot,
    channel_id: int | str | None,
    caption_text: str,
    text_chunks: list[str],
    image_urls: list[str] | None,
    request_id: str | None,
    user_id: int,
) -> None:
    """
    Дублирует готовый пост в дополнительный канал/группу, если он указан.
    
    Перед отправкой проверяет доступность чата и права бота.
    Пробует несколько вариантов форматов ID для групп (обычная группа, супергруппа).
    """
    normalized_chat = _normalize_broadcast_chat_id(channel_id)
    if not normalized_chat:
        return

    # Получаем варианты ID для попытки
    chat_id_variants = _get_chat_id_variants(channel_id, normalized_chat)
    
    # Проверяем доступность чата перед отправкой, пробуя разные варианты
    working_chat_id = None
    last_error = None
    
    for variant_id in chat_id_variants:
        try:
            chat = await bot.get_chat(variant_id)
            working_chat_id = variant_id
            _log_json(
                "info",
                event="broadcast_chat_check",
                request_id=request_id,
                user_id=user_id,
                channel_id=str(variant_id),
                original_id=str(channel_id),
                normalized_id=str(normalized_chat),
                chat_type=chat.type,
                chat_title=getattr(chat, "title", None),
            )
            break
        except TelegramBadRequest as e:
            last_error = str(e)
            # Пробуем следующий вариант
            continue
        except Exception as e:
            last_error = str(e)
            # Пробуем следующий вариант
            continue
    
    if not working_chat_id:
        logger.error(
            "Не удалось найти чат ни с одним из вариантов ID %s (исходный: %s). "
            "Попробованные варианты: %s. "
            "Последняя ошибка: %s. "
            "Убедитесь, что:\n"
            "1. Бот добавлен в группу/канал как администратор\n"
            "2. Бот имеет права на отправку сообщений\n"
            "3. ID указан правильно (попробуйте добавить бота @RawDataBot для получения точного ID)",
            normalized_chat,
            channel_id,
            [str(v) for v in chat_id_variants],
            last_error,
        )
        _log_json(
            "error",
            event="broadcast_chat_not_found",
            request_id=request_id,
            user_id=user_id,
            channel_id=str(normalized_chat),
            original_id=str(channel_id),
            tried_variants=[str(v) for v in chat_id_variants],
            error=last_error or "All variants failed",
        )
        return

    # Отправляем пост используя рабочий ID
    try:
        main_images = (image_urls or [])[:4]
        if main_images:
            album_sent = await _send_media_block_to_chat(bot, working_chat_id, main_images, caption_text)
            if not album_sent:
                await _send_text_sequence_to_chat(bot, working_chat_id, text_chunks)
                return

            remaining_text = text_chunks[1:] if len(text_chunks) > 1 else []
            if remaining_text:
                await _send_text_sequence_to_chat(bot, working_chat_id, remaining_text)

            remaining_images = (image_urls or [])[len(main_images):]
            for i in range(0, len(remaining_images), 10):
                batch = remaining_images[i:i + 10]
                sent = await _send_media_block_to_chat(bot, working_chat_id, batch, None)
                if not sent:
                    break
        else:
            await _send_text_sequence_to_chat(bot, working_chat_id, text_chunks)

        _log_json(
            "info",
            event="broadcast_success",
            request_id=request_id,
            user_id=user_id,
            channel_id=str(working_chat_id),
            original_id=str(channel_id),
            images=len(image_urls or []),
        )
    except TelegramBadRequest as exc:
        error_msg = str(exc)
        logger.error(
            "Не удалось отправить пост в чат %s (исходный ID: %s): %s\n"
            "Возможные причины:\n"
            "1. Бот не имеет прав на отправку сообщений/медиа\n"
            "2. Группа/канал ограничивает отправку сообщений ботами",
            working_chat_id,
            channel_id,
            error_msg,
        )
        _log_json(
            "error",
            event="broadcast_failed",
            request_id=request_id,
            user_id=user_id,
            channel_id=str(working_chat_id),
            original_id=str(channel_id),
            error=error_msg,
        )
    except Exception as exc:
        logger.warning("Не удалось отправить пост в канал %s: %s", working_chat_id, exc)
        _log_json(
            "error",
            event="broadcast_failed",
            request_id=request_id,
            user_id=user_id,
            channel_id=str(working_chat_id),
            original_id=str(channel_id),
            error=str(exc),
        )

def _extend_chunk_to_close_tags(text: str, start: int, end: int) -> tuple[str, int]:
    """
    Расширяет срез текста до тех пор, пока внутри него не останется незакрытых HTML-тегов.
    """
    end_pos = min(end, len(text))
    while True:
        fragment = text[start:end_pos]
        open_tags = _find_unclosed_html_tags(fragment)
        if not open_tags or end_pos >= len(text):
            return fragment, end_pos

        extended = False
        for tag in reversed(open_tags):
            closing_marker = f"</{tag}>"
            closing_idx = text.find(closing_marker, end_pos)
            if closing_idx != -1:
                end_pos = closing_idx + len(closing_marker)
                extended = True
                break
        if not extended:
            return fragment, end_pos


def _find_unclosed_html_tags(fragment: str) -> list[str]:
    """
    Возвращает стек незакрытых HTML-тегов внутри фрагмента.
    """
    stack: list[str] = []
    for match in HTML_TAG_PATTERN.finditer(fragment):
        full = match.group(0)
        closing = match.group(1) == '/'
        tag_name = match.group(2).lower()

        if full.endswith('/>') or tag_name in HTML_SELF_CLOSING_TAGS:
            continue

        if closing:
            if stack:
                for idx in range(len(stack) - 1, -1, -1):
                    if stack[idx] == tag_name:
                        stack = stack[:idx]
                        break
        else:
            stack.append(tag_name)
    return stack


async def send_typing_action(message: Message, stop_event: asyncio.Event):
    """
    Периодически отправляет индикатор "печатает" пока обрабатывается запрос.
    
    Args:
        message: Сообщение пользователя
        stop_event: Event для остановки отправки индикатора
    """
    while not stop_event.is_set():
        try:
            await message.bot.send_chat_action(
                chat_id=message.chat.id,
                action=ChatAction.TYPING
            )
            # Случайная задержка 3-5 секунд (typing action живёт 5 секунд)
            delay = random.uniform(3, 5)
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            break
        except Exception:
            # Игнорируем ошибки отправки typing action
            pass


@router.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение пользователю.
    """
    if not await ensure_access(message):
        return
    await state.clear()
    await message.answer(
        f"Привет, {message.from_user.full_name}! Отправь мне ссылку на товар с Taobao.",
        reply_markup=build_main_menu_keyboard()
    )

@router.message(F.text == "⚙️ Настройки")
async def open_settings_menu(message: Message, state: FSMContext) -> None:
    """Обработчик кнопки настроек"""
    await state.clear()
    user_id = message.from_user.id
    user_settings_service.get_settings(user_id)
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nВыберите действие:",
        reply_markup=build_settings_menu_keyboard(user_id),
        parse_mode="HTML"
    )


@router.message(F.text == "🔙 В главное меню")
async def back_to_main_menu(message: Message, state: FSMContext) -> None:
    """Обработчик возврата в главное меню"""
    if not await ensure_access(message):
        return
    await state.clear()
    await message.answer(
        "Вы вернулись в главное меню.",
        reply_markup=build_main_menu_keyboard()
    )


@router.message(F.text == "✍️ Изменить подпись")
async def ask_for_signature(message: Message, state: FSMContext) -> None:
    """Запрашивает новую подпись у пользователя"""
    if not await ensure_access(message):
        return
    await state.set_state(SettingsState.waiting_signature)
    await message.answer(
        "Введите новую подпись (например @username или номер телефона).\n\n"
        "⚠️ <b>Важно:</b> Введите именно текст подписи. "
        "Если вы нажмёте кнопку меню, ввод будет отменён.\n\n"
        "Для отмены нажмите «🔙 В главное меню».",
        parse_mode="HTML"
    )


@router.message(SettingsState.waiting_signature)
async def update_signature(message: Message, state: FSMContext) -> None:
    """
    Обновляет подпись пользователя.
    Проверяет, что ввод не является нажатием кнопки меню.
    Если пользователь нажал кнопку вместо ввода текста, отменяет ввод и обрабатывает кнопку.
    """
    new_signature = (message.text or "").strip()
    
    # Список текстов кнопок, которые не должны обрабатываться как подпись
    # Ключ - текст кнопки, значение - функция для обработки
    menu_buttons = {
        "🧩 Mimi App": None,  # Web App обрабатывается отдельно
        "✍️ Изменить подпись": None,  # Уже в режиме ввода подписи
        "💱 Валюта": "choose_currency",
        "ℹ️ Мои настройки": "show_settings",
        "📈 Сменить курс": "ask_exchange_rate",
        "🔙 В главное меню": "back_to_main_menu",
        "📦 Запросить описание товара": "back_to_main_menu",
        "⚙️ Настройки": "open_settings_menu",
    }
    
    # Проверка: если введённый текст совпадает с кнопкой меню, отменяем ввод подписи
    if new_signature in menu_buttons:
        await state.clear()
        
        # Обрабатываем конкретные кнопки
        if new_signature == "ℹ️ Мои настройки":
            # Показываем настройки
            user_id = message.from_user.id
            user_settings = user_settings_service.get_settings(user_id)
            summary = format_settings_summary(user_settings)
            await message.answer(
                summary,
                reply_markup=build_settings_menu_keyboard(user_id),
                parse_mode="HTML"
            )
        elif new_signature == "💱 Валюта":
            # Показываем выбор валюты
            await message.answer(
                "Выберите валюту по умолчанию:",
                reply_markup=build_currency_keyboard(),
            )
        elif new_signature in ("🔙 В главное меню", "📦 Запросить описание товара"):
            # Возвращаемся в главное меню
            await message.answer(
                "Вы вернулись в главное меню.",
                reply_markup=build_main_menu_keyboard()
            )
        elif new_signature == "⚙️ Настройки":
            # Открываем меню настроек
            user_id = message.from_user.id
            user_settings_service.get_settings(user_id)
            await message.answer(
                "⚙️ <b>Настройки</b>\n\nВыберите действие:",
                reply_markup=build_settings_menu_keyboard(user_id),
                parse_mode="HTML"
            )
        elif new_signature == "📈 Сменить курс":
            # Запрашиваем новый курс обмена
            await state.set_state(SettingsState.waiting_exchange_rate)
            await message.answer(
                "Введите новый курс обмена (например: 12.5).\n\n"
                "⚠️ <b>Важно:</b> Введите именно число курса. "
                "Если вы нажмёте кнопку меню, ввод будет отменён.",
                parse_mode="HTML"
            )
        else:
            # Общее сообщение для других кнопок
            await message.answer(
                "❌ Ввод подписи отменён. Вы выбрали пункт меню вместо ввода подписи.\n\n"
                "Если хотите изменить подпись, используйте кнопку «✍️ Изменить подпись» и введите текст.",
                reply_markup=build_settings_menu_keyboard(message.from_user.id),
            )
        return
    
    # Проверка на пустую подпись
    if not new_signature:
        await message.answer(
            "❌ Подпись не должна быть пустой. Попробуйте снова или нажмите кнопку «🔙 В главное меню» для отмены."
        )
        return
    
    # Проверка длины подписи (максимум 64 символа, как в веб-приложении)
    if len(new_signature) > 64:
        await message.answer(
            f"❌ Подпись слишком длинная ({len(new_signature)} символов). "
            f"Максимальная длина — 64 символа. Попробуйте снова.",
        )
        return
    
    # Валидация пройдена, обновляем подпись
    user_id = message.from_user.id
    user_settings_service.update_signature(user_id, new_signature)

    await state.clear()
    await message.answer(
        f"✅ Подпись обновлена: <code>{new_signature}</code>",
        reply_markup=build_settings_menu_keyboard(message.from_user.id),
        parse_mode="HTML"
    )


@router.message(F.text == "💱 Валюта")
async def choose_currency(message: Message, state: FSMContext) -> None:
    """Показывает выбор валюты"""
    if not await ensure_access(message):
        return
    await state.clear()
    await message.answer(
        "Выберите валюту по умолчанию:",
        reply_markup=build_currency_keyboard(),
    )


@router.callback_query(F.data.startswith("currency:"))
async def handle_currency_choice(callback: CallbackQuery, state: FSMContext) -> None:
    """Обрабатывает выбор валюты"""
    await state.clear()
    choice = callback.data.split(":", 1)[1]

    if choice == "cancel":
        await callback.answer("Выбор отменён")
        await _safe_clear_markup(callback.message)
        await callback.message.answer(
            "Настройки не изменены.",
            reply_markup=build_settings_menu_keyboard(callback.from_user.id),
        )
        return

    user_id = callback.from_user.id
    user_settings = user_settings_service.get_settings(user_id)

    if choice == "cny":
        user_settings_service.update_currency(user_id, "cny")
        await callback.answer("Валюта: юань")
        await _safe_clear_markup(callback.message)
        await callback.message.answer(
            "✅ Валюта по умолчанию: юань. Конвертация отключена.",
            reply_markup=build_settings_menu_keyboard(user_id),
        )
    elif choice == "rub":
        user_settings = user_settings_service.update_currency(user_id, "rub")
        await callback.answer("Валюта: рубль")
        await _safe_clear_markup(callback.message)

        if not user_settings.exchange_rate:
            await callback.message.answer(
                "Введите актуальный курс рубля (например 12.35)."
            )
            await state.set_state(SettingsState.waiting_exchange_rate)
        else:
            await callback.message.answer(
                f"✅ Валюта по умолчанию: рубль. Текущий курс: {float(user_settings.exchange_rate):.4f} ₽ за 1 ¥.",
                reply_markup=build_settings_menu_keyboard(callback.from_user.id),
            )
    else:
        await callback.answer("Неизвестный выбор", show_alert=True)


@router.message(F.text == "📈 Сменить курс")
async def prompt_change_rate(message: Message, state: FSMContext) -> None:
    """Запрашивает новый курс, если валюта = рубль."""
    if not await ensure_access(message):
        return
    user_id = message.from_user.id
    user_settings = user_settings_service.get_settings(user_id)
    if user_settings.default_currency.lower() != "rub":
        await state.clear()
        await message.answer(
            "Сначала выберите валюту: рубль. Откройте «💱 Валюта» и установите рубль.",
            reply_markup=build_settings_menu_keyboard(user_id),
        )
        return

    await state.set_state(SettingsState.waiting_exchange_rate)
    await message.answer(
        "Введите новый курс рубля (например: 12.35).\n\n"
        "⚠️ <b>Важно:</b> Введите именно число курса. "
        "Если вы нажмёте кнопку меню, ввод будет отменён.\n\n"
        "Для отмены нажмите «🔙 В главное меню».",
        parse_mode="HTML"
    )


@router.message(SettingsState.waiting_exchange_rate)
async def set_exchange_rate(message: Message, state: FSMContext) -> None:
    """
    Устанавливает курс обмена.
    Проверяет, что ввод не является нажатием кнопки меню.
    """
    raw = (message.text or "").strip()
    
    # Список текстов кнопок, которые не должны обрабатываться как курс
    menu_buttons = {
        "🧩 Mimi App",
        "✍️ Изменить подпись",
        "💱 Валюта",
        "ℹ️ Мои настройки",
        "📈 Сменить курс",
        "🔙 В главное меню",
        "📦 Запросить описание товара",
        "⚙️ Настройки",
    }
    
    # Проверка: если введённый текст совпадает с кнопкой меню, отменяем ввод курса
    if raw in menu_buttons:
        await state.clear()
        await message.answer(
            "❌ Ввод курса отменён. Вы выбрали пункт меню вместо ввода курса.\n\n"
            "Если хотите изменить курс, используйте кнопку «📈 Сменить курс» и введите число.",
            reply_markup=build_settings_menu_keyboard(message.from_user.id),
        )
        return
    
    # Пытаемся преобразовать в число
    raw = raw.replace(",", ".")
    try:
        rate = float(raw)
        if rate <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Введите положительное число (например: 12.45).\n\n"
            "Или нажмите кнопку «🔙 В главное меню» для отмены."
        )
        return

    user_id = message.from_user.id
    user_settings_service.update_exchange_rate(user_id, rate)

    await state.clear()
    await message.answer(
        f"✅ Курс обновлён: 1 ¥ = {rate:.4f} ₽.",
        reply_markup=build_settings_menu_keyboard(message.from_user.id),
    )


@router.message(F.text == "ℹ️ Мои настройки")
async def show_settings(message: Message, state: FSMContext) -> None:
    """Показывает текущие настройки пользователя"""
    if not await ensure_access(message):
        return
    await state.clear()
    user_id = message.from_user.id
    user_settings = user_settings_service.get_settings(user_id)
    summary = format_settings_summary(user_settings)
    await message.answer(
        summary,
        reply_markup=build_settings_menu_keyboard(user_id),
        parse_mode="HTML"
    )


@router.message(Command("access"))
async def access_menu_entry(message: Message, state: FSMContext) -> None:
    """
    Точка входа в меню управления доступом.
    Доступно только для админов (ADMIN_CHAT_ID и ADMIN_GROUP_BOT).
    """
    if not is_admin_user(message.from_user.id, message.from_user.username):
        return

    await state.set_state(AccessState.choosing_action)
    summary = access_control_service.get_summary()
    help_text = (
        "🔐 <b>Управление доступом к боту</b>\n\n"
        f"{summary}\n\n"
        "Доступные команды:\n"
        "• <code>white on</code> / <code>white off</code> — включить/выключить белый список\n"
        "• <code>black on</code> / <code>black off</code> — включить/выключить чёрный список\n"
        "• <code>add white</code> — добавить пользователей в белый список\n"
        "• <code>add black</code> — добавить пользователей в чёрный список\n"
        "• <code>del white</code> — удалить пользователей из белого списка\n"
        "• <code>del black</code> — удалить пользователей из чёрного списка\n"
        "• <code>show</code> — показать текущие списки\n\n"
        "После команды <code>add ...</code> или <code>del ...</code> бот попросит ввести "
        "ID и username через запятую, например:\n"
        "<code>123456, @user1, 987654321, user2</code>"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("dump_data"))
async def dump_data_command(message: Message, state: FSMContext) -> None:
    """
    Команда для аварийного экспорта всех настроек пользователей и списков доступа.
    Доступно только для админов.
    Выводит JSON-дампы в чат для сохранения данных.
    """
    if not is_admin_user(message.from_user.id, message.from_user.username):
        await message.answer("❌ Эта команда доступна только администраторам.")
        return

    await state.clear()

    try:
        await message.answer("📦 Подготавливаю дамп данных...")

        # Дамп настроек пользователей
        user_settings_service = get_user_settings_service()
        user_data = {
            str(user_id): {
                "signature": settings_obj.signature,
                "default_currency": settings_obj.default_currency,
                "exchange_rate": settings_obj.exchange_rate,
            }
            for user_id, settings_obj in user_settings_service._settings_cache.items()
        }

        user_json = json.dumps(user_data, ensure_ascii=False, indent=2)
        user_info = (
            f"👥 <b>Настройки пользователей</b>\n"
            f"Всего пользователей: {len(user_data)}\n"
            f"Размер JSON: {len(user_json)} символов\n\n"
            f"<code>user_settings.json</code>:"
        )

        await message.answer(user_info, parse_mode="HTML")

        # Разбиваем большой JSON на части (лимит Telegram ~4000 символов, с запасом 3500)
        user_chunks = split_text_chunks(user_json, 3500)
        for i, chunk in enumerate(user_chunks, 1):
            header = f"<b>Часть {i}/{len(user_chunks)}:</b>\n\n" if len(user_chunks) > 1 else ""
            await message.answer(f"{header}<code>{chunk}</code>", parse_mode="HTML")
            # Небольшая задержка, чтобы не превысить rate limits
            await asyncio.sleep(0.5)

        # Дамп списков доступа
        from dataclasses import asdict
        access_data = asdict(access_control_service._config)
        access_json = json.dumps(access_data, ensure_ascii=False, indent=2)

        access_info = (
            f"\n🔐 <b>Списки доступа</b>\n"
            f"Размер JSON: {len(access_json)} символов\n\n"
            f"<code>access_control.json</code>:"
        )

        await message.answer(access_info, parse_mode="HTML")

        access_chunks = split_text_chunks(access_json, 3500)
        for i, chunk in enumerate(access_chunks, 1):
            header = f"<b>Часть {i}/{len(access_chunks)}:</b>\n\n" if len(access_chunks) > 1 else ""
            await message.answer(f"{header}<code>{chunk}</code>", parse_mode="HTML")
            await asyncio.sleep(0.5)

        summary_msg = (
            f"\n✅ <b>Дамп завершён</b>\n\n"
            f"• Настроек пользователей: {len(user_data)}\n"
            f"• Белый список: {len(access_data.get('whitelist_ids', []))} ID, "
            f"{len(access_data.get('whitelist_usernames', []))} username\n"
            f"• Чёрный список: {len(access_data.get('blacklist_ids', []))} ID, "
            f"{len(access_data.get('blacklist_usernames', []))} username\n\n"
            f"Скопируйте JSON данные и сохраните их в файлы для восстановления."
        )
        await message.answer(summary_msg, parse_mode="HTML")

        _log_json(
            "info",
            event="admin_dump_data",
            user_id=message.from_user.id,
            username=message.from_user.username,
            users_count=len(user_data),
        )

    except Exception as e:
        logger.error(f"Ошибка при создании дампа данных: {e}", exc_info=True)
        await message.answer(
            f"❌ Ошибка при создании дампа данных:\n<code>{str(e)}</code>",
            parse_mode="HTML",
        )


@router.message(AccessState.choosing_action)
async def access_choose_action(message: Message, state: FSMContext) -> None:
    """
    Обрабатывает базовые команды управления списками в состоянии выбора действия.
    """
    if not is_admin_user(message.from_user.id, message.from_user.username):
        await state.clear()
        return

    raw = (message.text or "").strip().lower()

    if raw in {"white on", "white off", "black on", "black off"}:
        enable = raw.endswith("on")
        if raw.startswith("white"):
            access_control_service.set_whitelist_enabled(enable)
            await message.answer(
                f"✅ Белый список {'включён' if enable else 'выключен'}.",
                parse_mode="HTML",
            )
        else:
            access_control_service.set_blacklist_enabled(enable)
            await message.answer(
                f"✅ Чёрный список {'включён' if enable else 'выключен'}.",
                parse_mode="HTML",
            )
        # остаёмся в режиме выбора действия
        summary = access_control_service.get_summary()
        await message.answer(summary)
        return

    if raw == "show":
        dump = access_control_service.dump_lists()
        await message.answer(dump, parse_mode="HTML")
        return

    if raw in {"add white", "add black"}:
        await state.update_data(mode=raw.replace("add ", ""), op="add")
        await state.set_state(AccessState.editing_whitelist if "white" in raw else AccessState.editing_blacklist)
        await message.answer(
            "Отправьте список пользователей для добавления в формате:\n"
            "<code>123456, @user1, 987654321, user2</code>",
            parse_mode="HTML",
        )
        return

    if raw in {"del white", "del white ", "del black", "del black "}:
        await state.update_data(mode=raw.replace("del ", "").strip(), op="del")
        await state.set_state(AccessState.editing_whitelist if "white" in raw else AccessState.editing_blacklist)
        await message.answer(
            "Отправьте список пользователей для удаления в формате:\n"
            "<code>123456, @user1, 987654321, user2</code>",
            parse_mode="HTML",
        )
        return

    await message.answer(
        "Неизвестная команда. Используйте:\n"
        "<code>white on</code>, <code>white off</code>, <code>black on</code>, <code>black off</code>,\n"
        "<code>add white</code>, <code>add black</code>, <code>del white</code>, <code>del black</code>,\n"
        "или <code>show</code>.",
        parse_mode="HTML",
    )


@router.message(AccessState.editing_whitelist)
async def access_edit_whitelist(message: Message, state: FSMContext) -> None:
    """
    Добавление/удаление пользователей из белого списка.
    """
    if not is_admin_user(message.from_user.id, message.from_user.username):
        await state.clear()
        return

    data = await state.get_data()
    op = data.get("op", "add")

    ids, names = parse_ids_and_usernames(message.text or "")
    if not ids and not names:
        await message.answer("Не удалось распознать ни один ID или username. Попробуйте ещё раз.")
        return

    if op == "add":
        access_control_service.add_to_whitelist(ids, names)
        await message.answer("✅ Пользователи добавлены в белый список.")
    else:
        access_control_service.remove_from_whitelist(ids, names)
        await message.answer("✅ Пользователи удалены из белого списка (если были).")

    await state.set_state(AccessState.choosing_action)
    summary = access_control_service.get_summary()
    await message.answer(summary)


@router.message(AccessState.editing_blacklist)
async def access_edit_blacklist(message: Message, state: FSMContext) -> None:
    """
    Добавление/удаление пользователей из чёрного списка.
    """
    if not is_admin_user(message.from_user.id, message.from_user.username):
        await state.clear()
        return

    data = await state.get_data()
    op = data.get("op", "add")

    ids, names = parse_ids_and_usernames(message.text or "")
    if not ids and not names:
        await message.answer("Не удалось распознать ни один ID или username. Попробуйте ещё раз.")
        return

    if op == "add":
        access_control_service.add_to_blacklist(ids, names)
        await message.answer("✅ Пользователи добавлены в чёрный список.")
    else:
        access_control_service.remove_from_blacklist(ids, names)
        await message.answer("✅ Пользователи удалены из чёрного списка (если были).")

    await state.set_state(AccessState.choosing_action)
    summary = access_control_service.get_summary()
    await message.answer(summary)


@router.message(F.text.regexp(r"(https?://)?(www\.)?(m\.)?(e\.)?(detail\.tmall\.com|item\.taobao\.com|a\.m\.taobao\.com|market\.m\.taobao\.com|h5\.m\.taobao\.com|s\.click\.taobao\.com|uland\.taobao\.com|tb\.cn|detail\.1688\.com|1688\.com|m\.1688\.com|winport\.m\.1688\.com|mobile\.yangkeduo\.com|yangkeduo\.com|pinduoduo\.com|pdd\.com)/.*"))
async def handle_product_link(message: Message, state: FSMContext) -> None:
    """
    Обработчик сообщений, содержащих ссылки на товары Taobao/Tmall/1688/Pinduoduo.
    Автоматически определяет платформу, извлекает информацию о товаре,
    генерирует пост и отправляет его пользователю.
    """
    # Проверяем право доступа
    if not await ensure_access(message):
        return

    request_id = str(uuid.uuid4())
    started_at = time.monotonic()
    broadcast_task: asyncio.Task | None = None
    forward_channel_id = (getattr(settings, "FORWARD_CHANNEL_ID", "") or "").strip()

    # Отправляем начальное сообщение
    await message.answer("Обрабатываю вашу ссылку, пожалуйста, подождите...")
    
    # Создаём событие для остановки typing action
    stop_typing = asyncio.Event()
    
    # Запускаем фоновую задачу для индикатора "печатает"
    typing_task = asyncio.create_task(send_typing_action(message, stop_typing))
    
    # Проверяем, не находимся ли мы в процессе настройки
    current_state = await state.get_state()
    if current_state:
        await message.answer(
            "Сначала завершите настройку, затем отправьте ссылку.",
            reply_markup=build_settings_menu_keyboard(message.from_user.id),
        )
        return

    product_url = message.text  # Определяем переменную до try блока
    
    # Получаем настройки пользователя
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user_settings = user_settings_service.get_settings(user_id)
    
    # Проверяем, что если валюта рубль, то курс установлен
    if user_settings.default_currency.lower() == "rub" and not user_settings.exchange_rate:
        await message.answer(
            "⚠️ Сначала укажите курс рубля в настройках.",
            reply_markup=build_settings_menu_keyboard(user_id),
        )
        return
    
    try:
        _log_json(
            "info",
            event="scrape_start",
            request_id=request_id,
            chat_id=message.chat.id,
            user_id=user_id,
            username=username or "unknown",
            url=product_url,
        )
        _log_json(
            "info",
            event="user_settings",
            request_id=request_id,
            chat_id=message.chat.id,
            user_id=user_id,
            username=username or "unknown",
            currency=user_settings.default_currency,
            exchange_rate=user_settings.exchange_rate,
            signature=user_settings.signature,
        )
        # Скрапинг информации о товаре и генерация текста поста с учётом настроек пользователя
        post_text, image_urls = await scraper.scrape_product(
            product_url,
            user_signature=user_settings.signature,
            user_currency=user_settings.default_currency,
            exchange_rate=user_settings.exchange_rate,
            request_id=request_id,
        )
        duration_ms = int((time.monotonic() - started_at) * 1000)
        _log_json(
            "info",
            event="scrape_done",
            request_id=request_id,
            chat_id=message.chat.id,
            user_id=user_id,
            username=username or "unknown",
            text_len=len(post_text) if post_text else 0,
            images=len(image_urls) if image_urls else 0,
            duration_ms=duration_ms,
        )
        _log_json(
            "info",
            event="metric_scrape",
            status="success",
            request_id=request_id,
            chat_id=message.chat.id,
            user_id=user_id,
            username=username or "unknown",
            duration_ms=duration_ms,
            url=product_url,
        )
        
        # Проверяем, что результат не пустой
        if not post_text:
            logger.warning("Получен пустой текст поста")
            await message.answer(
                "❌ Не удалось получить данные о товаре.\n\n"
                "Возможно, товар недоступен или ссылка неверна."
            )
            return
        
        caption_text, caption_queue = prepare_caption_and_queue(post_text)
        if not caption_text:
            caption_text = post_text.strip()
            caption_queue = deque()
        full_text_chunks = [caption_text] + list(caption_queue)
        broadcast_text_chunks = list(full_text_chunks)

        if image_urls:
            main_images = image_urls[:4]
            album_sent = await send_media_block(message, main_images, caption_text)
            if not album_sent:
                await send_text_sequence(message, full_text_chunks)
            else:
                if caption_queue:
                    await send_text_sequence(message, list(caption_queue))
                    caption_queue.clear()

                remaining_images = image_urls[len(main_images):]
                for i in range(0, len(remaining_images), 10):
                    batch = remaining_images[i:i+10]
                    sent = await send_media_block(message, batch, None)
                    if not sent:
                        break
        else:
            await send_text_sequence(message, full_text_chunks)

        if forward_channel_id:
            broadcast_task = asyncio.create_task(
                broadcast_post_to_channel(
                    bot=message.bot,
                    channel_id=forward_channel_id,
                    caption_text=caption_text,
                    text_chunks=broadcast_text_chunks,
                    image_urls=image_urls,
                    request_id=request_id,
                    user_id=user_id,
                )
            )

    except Exception as e:
        # Логируем ошибку перед обработкой
        _log_json(
            "error",
            event="scrape_error",
            request_id=request_id,
            chat_id=message.chat.id,
            user_id=user_id,
            username=username or "unknown",
            url=product_url,
            error=str(e),
        )
        duration_ms = int((time.monotonic() - started_at) * 1000)
        _log_json(
            "info",
            event="metric_scrape",
            status="error",
            request_id=request_id,
            chat_id=message.chat.id,
            user_id=user_id,
            username=username or "unknown",
            duration_ms=duration_ms,
            url=product_url,
        )
        # Профессиональная обработка ошибок (с защитой на случай, если error_handler ещё не успел инициализироваться)
        try:
            handler = getattr(error_handler_module, "error_handler", None)
            if handler is not None:
                # Определяем тип ошибки и контекст
                error_type = handler.classify_error(e, context=f"scraping {product_url}")
                await handler.handle_error(
                    error=e,
                    user_message=message,
                    context=f"Product URL: {product_url}, request_id={request_id}",
                    error_type=error_type,
                    request_id=request_id,
                )
                return
        except Exception as handler_exc:  # защита от падения внутри самого обработчика
            _log_json(
                "error",
                event="error_handler_failure",
                request_id=request_id,
                chat_id=message.chat.id,
                user_id=user_id,
                username=username or "unknown",
                url=product_url,
                error=str(handler_exc),
            )

        # Fallback на случай если error_handler не инициализирован или сломался
        logger.warning("error_handler недоступен, используем fallback-поведение")
        await message.answer(
            "😔 Извините, произошла ошибка при обработке вашего запроса. "
            "Пожалуйста, попробуйте повторить через несколько минут."
        )
    finally:
        # Останавливаем индикатор "печатает"
        stop_typing.set()
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

@router.message()
async def echo_message(message: Message, state: FSMContext):
    """
    Обработчик для всех остальных сообщений, которые не были обработаны другими хэндлерами.
    """
    if not await ensure_access(message):
        return
    await state.clear()
    await message.answer(
        "Пожалуйста, отправьте мне ссылку на товар Taobao/Tmall или используйте команду /start.",
        reply_markup=build_main_menu_keyboard()
    )