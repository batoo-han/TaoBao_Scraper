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
        "Введите новую подпись (например @username или номер телефона)."
    )


@router.message(SettingsState.waiting_signature)
async def update_signature(message: Message, state: FSMContext) -> None:
    """Обновляет подпись пользователя"""
    new_signature = (message.text or "").strip()
    if not new_signature:
        await message.answer("Подпись не должна быть пустой. Попробуйте снова.")
        return

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
    await message.answer("Введите новый курс рубля (например 12.35).")


@router.message(SettingsState.waiting_exchange_rate)
async def set_exchange_rate(message: Message, state: FSMContext) -> None:
    """Устанавливает курс обмена"""
    raw = (message.text or "").strip().replace(",", ".")
    try:
        rate = float(raw)
        if rate <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное число, например 12.45.")
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

        if image_urls:
            main_images = image_urls[:4]
            album_sent = await send_media_block(message, main_images, caption_text)
            if not album_sent:
                await send_text_sequence(message, full_text_chunks)
                return

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