import asyncio
import logging
<<<<<<< HEAD
from aiogram import Router, F
from aiogram.types import Message, InputMediaPhoto, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import httpx
from aiogram.filters import CommandStart, Command
=======
import random
from aiogram import F, Router
>>>>>>> ea50f5eeb9953ad571713ef3461bd36d187f61e9
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
import httpx

from src.bot.error_handler import error_handler
<<<<<<< HEAD
=======
from src.core.scraper import Scraper
from src.db.session import get_async_session
from src.services.llm import LLMProviderManager, UnsupportedProviderError
>>>>>>> ea50f5eeb9953ad571713ef3461bd36d187f61e9
from src.services.user_settings import UserSettingsService

logger = logging.getLogger(__name__)

router = Router()
<<<<<<< HEAD
# Инициализация скрапера для получения информации о товарах
scraper = Scraper()
# Инициализация сервиса настроек пользователей
user_settings_service = UserSettingsService()


class SettingsState(StatesGroup):
    """Состояния для меню настроек"""
    waiting_signature = State()
    waiting_exchange_rate = State()


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Создаёт главное меню"""
    keyboard = [
        [KeyboardButton(text="📦 Запросить описание товара")],
        [KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


SETTINGS_MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✍️ Изменить подпись")],
        [KeyboardButton(text="💱 Валюта"), KeyboardButton(text="ℹ️ Мои настройки")],
        [KeyboardButton(text="🔙 В главное меню")],
    ],
    resize_keyboard=True,
)


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
=======
scraper = Scraper()
>>>>>>> ea50f5eeb9953ad571713ef3461bd36d187f61e9


class SettingsState(StatesGroup):
    waiting_signature = State()
    waiting_exchange_rate = State()


def build_main_menu_keyboard(is_new_user: bool = False) -> ReplyKeyboardMarkup:
    """Создаёт главное меню. Кнопка /start показывается только новым пользователям."""
    keyboard = [
        [KeyboardButton(text="📦 Запросить описание товара")],
    ]
    # Кнопку /start показываем только новым пользователям
    if is_new_user:
        keyboard.append([KeyboardButton(text="/start")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

SETTINGS_MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✍️ Изменить подпись")],
        [KeyboardButton(text="💱 Валюта"), KeyboardButton(text="ℹ️ Мои настройки")],
        [KeyboardButton(text="🔙 В главное меню")],
    ],
    resize_keyboard=True,
)


def build_currency_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Юань (¥)", callback_data="currency:cny")],
            [InlineKeyboardButton(text="Рубль (₽)", callback_data="currency:rub")],
            [InlineKeyboardButton(text="Отмена", callback_data="currency:cancel")],
        ]
    )


def format_settings_summary(user_settings) -> str:
    currency = user_settings.default_currency.upper()
    signature = user_settings.signature or "—"
    rate = user_settings.exchange_rate
    rate_display = f"{float(rate):.4f} ₽ за 1 ¥" if rate else "не задан"
    return (
        "<b>Ваши настройки</b>\n"
        f"• Подпись: <code>{signature}</code>\n"
        f"• Валюта по умолчанию: <b>{currency}</b>\n"
        f"• Курс для рубля: {rate_display}"
    )


async def ensure_user_and_settings(message: Message, session) -> tuple:
    """
    Обеспечивает наличие пользователя и его настроек в БД.
    
    Returns:
        tuple: (user, settings_row, is_new_user) где is_new_user - True если пользователь только что создан
    """
    tg_user = message.from_user
    if tg_user is None:
        raise RuntimeError("Не удалось определить пользователя Telegram")

    user_service = UserSettingsService(session)
    
    # Проверяем, существует ли пользователь
    from sqlalchemy import select
    from src.db.models import User
    result = await session.execute(
        select(User).where(User.telegram_id == tg_user.id)
    )
    existing_user = result.scalar_one_or_none()
    is_new_user = existing_user is None
    
    user = await user_service.ensure_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        language_code=tg_user.language_code,
    )
    settings_row = await user_service.get_settings(user.id)
    return user, settings_row, is_new_user


async def send_typing_action(message: Message, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
            await asyncio.sleep(random.uniform(3, 5))
        except asyncio.CancelledError:
            break
        except Exception:
            pass


@router.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
<<<<<<< HEAD
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение пользователю.
    """
    await state.clear()
    await message.answer(
        f"Привет, {message.from_user.full_name}! Отправь мне ссылку на товар с Taobao, Tmall или Pinduoduo.",
        reply_markup=build_main_menu_keyboard()
    )

@router.message(F.text == "⚙️ Настройки")
async def open_settings_menu(message: Message, state: FSMContext) -> None:
    """Обработчик кнопки настроек"""
    await state.clear()
    user_id = message.from_user.id
    user_settings = user_settings_service.get_settings(user_id)
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nВыберите действие:",
        reply_markup=SETTINGS_MENU_KEYBOARD,
        parse_mode="HTML"
    )


@router.message(F.text == "🔙 В главное меню")
async def back_to_main_menu(message: Message, state: FSMContext) -> None:
    """Обработчик возврата в главное меню"""
    await state.clear()
    await message.answer(
        "Вы вернулись в главное меню.",
        reply_markup=build_main_menu_keyboard()
    )


@router.message(F.text == "✍️ Изменить подпись")
async def ask_for_signature(message: Message, state: FSMContext) -> None:
    """Запрашивает новую подпись у пользователя"""
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
        reply_markup=SETTINGS_MENU_KEYBOARD,
        parse_mode="HTML"
    )


@router.message(F.text == "💱 Валюта")
async def choose_currency(message: Message, state: FSMContext) -> None:
    """Показывает выбор валюты"""
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
        await callback.message.edit_reply_markup()
        await callback.message.answer(
            "Настройки не изменены.",
            reply_markup=SETTINGS_MENU_KEYBOARD,
        )
        return

    user_id = callback.from_user.id
    user_settings = user_settings_service.get_settings(user_id)

    if choice == "cny":
        user_settings_service.update_currency(user_id, "cny")
        await callback.answer("Валюта: юань")
        await callback.message.edit_reply_markup()
        await callback.message.answer(
            "✅ Валюта по умолчанию: юань. Конвертация отключена.",
            reply_markup=SETTINGS_MENU_KEYBOARD,
        )
    elif choice == "rub":
        user_settings = user_settings_service.update_currency(user_id, "rub")
        await callback.answer("Валюта: рубль")
        await callback.message.edit_reply_markup()

        if not user_settings.exchange_rate:
            await callback.message.answer(
                "Введите актуальный курс рубля (например 12.35)."
            )
            await state.set_state(SettingsState.waiting_exchange_rate)
        else:
            await callback.message.answer(
                f"✅ Валюта по умолчанию: рубль. Текущий курс: {float(user_settings.exchange_rate):.4f} ₽ за 1 ¥.",
                reply_markup=SETTINGS_MENU_KEYBOARD,
            )
    else:
        await callback.answer("Неизвестный выбор", show_alert=True)


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
        reply_markup=SETTINGS_MENU_KEYBOARD,
    )


@router.message(F.text == "ℹ️ Мои настройки")
async def show_settings(message: Message, state: FSMContext) -> None:
    """Показывает текущие настройки пользователя"""
    await state.clear()
    user_id = message.from_user.id
    user_settings = user_settings_service.get_settings(user_id)
    summary = format_settings_summary(user_settings)
    await message.answer(
        summary,
        reply_markup=SETTINGS_MENU_KEYBOARD,
        parse_mode="HTML"
    )


@router.message(F.text.regexp(r"(https?://)?(www\.)?(m\.)?(e\.)?(detail\.tmall\.com|item\.taobao\.com|a\.m\.taobao\.com|market\.m\.taobao\.com|h5\.m\.taobao\.com|s\.click\.taobao\.com|uland\.taobao\.com|tb\.cn|mobile\.yangkeduo\.com|yangkeduo\.com|pinduoduo\.com|pdd\.com)/.*"))
async def handle_product_link(message: Message, state: FSMContext) -> None:
    """
    Обработчик сообщений, содержащих ссылки на товары Taobao/Tmall/Pinduoduo.
    Автоматически определяет платформу, извлекает информацию о товаре,
    генерирует пост и отправляет его пользователю.
    """
    # Отправляем начальное сообщение
    await message.answer("Обрабатываю вашу ссылку, пожалуйста, подождите...")
=======
    await state.clear()
    is_new_user = False
    if message.from_user:
        async with get_async_session() as session:
            _, _, is_new_user = await ensure_user_and_settings(message, session)
            await session.commit()
    
    greeting_name = message.from_user.full_name if message.from_user else "друг"
    await message.answer(
        f"Привет, {greeting_name}! Отправь ссылку на товар с Taobao, Tmall или Pinduoduo.",
        reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
    )


@router.message(Command("settings"))
async def open_settings_menu(message: Message, state: FSMContext) -> None:
    """Обработчик команды /settings (кнопка убрана из меню, доступна только через команду)."""
    await state.clear()
    async with get_async_session() as session:
        _, user_settings, _ = await ensure_user_and_settings(message, session)
        await session.commit()
    summary = format_settings_summary(user_settings)
    await message.answer(
        f"{summary}\n\nВыберите действие:",
        reply_markup=SETTINGS_MENU_KEYBOARD,
        parse_mode="HTML",
    )


@router.message(Command("mysettings"))
@router.message(F.text == "ℹ️ Мои настройки")
async def show_settings_summary(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with get_async_session() as session:
        _, user_settings, _ = await ensure_user_and_settings(message, session)
        await session.commit()
    summary = format_settings_summary(user_settings)
    await message.answer(
        f"{summary}\n\nВыберите действие:",
        reply_markup=SETTINGS_MENU_KEYBOARD,
        parse_mode="HTML",
    )


@router.message(Command("request"))
@router.message(F.text == "📦 Запросить описание товара")
async def prompt_create_post(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with get_async_session() as session:
        _, _, is_new_user = await ensure_user_and_settings(message, session)
        await session.commit()
    await message.answer(
        "Отправьте ссылку на товар, и я подготовлю описание.",
        reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
    )


@router.message(Command("about"))
async def about_service(message: Message, state: FSMContext) -> None:
    """Обработчик команды /about - информация о сервисе."""
    await state.clear()
    async with get_async_session() as session:
        _, _, is_new_user = await ensure_user_and_settings(message, session)
        await session.commit()
>>>>>>> ea50f5eeb9953ad571713ef3461bd36d187f61e9
    
    about_text = """🤖 *О сервисе*

Этот бот помогает быстро получать готовые описания товаров с китайских маркетплейсов на русском языке.

*Для чего это нужно?*
📦 Упрощает работу с товарами из Китая
🌐 Автоматически переводит и адаптирует описания
⚡ Экономит время на ручной обработке
📝 Создаёт готовые посты для продажи

*Что умеет бот:*
✅ Парсит товары с Taobao, Tmall и Pinduoduo
✅ Извлекает фотографии товара (до 4 основных + остальные)
✅ Переводит и адаптирует описания на русский язык
✅ Форматирует характеристики по типу товара
✅ Показывает цену с конвертацией валют
✅ Добавляет вашу персональную подпись

*Как начать:*
Просто отправьте ссылку на товар, и бот подготовит готовое описание! 🚀"""
    
    await message.answer(
        about_text,
        parse_mode="Markdown",
        reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
    )


@router.message(Command("faq"))
async def faq_handler(message: Message, state: FSMContext) -> None:
    """Обработчик команды /faq - часто задаваемые вопросы."""
    await state.clear()
    async with get_async_session() as session:
        _, _, is_new_user = await ensure_user_and_settings(message, session)
        await session.commit()
    
<<<<<<< HEAD
    # Проверяем, не находимся ли мы в процессе настройки
    current_state = await state.get_state()
    if current_state:
        await message.answer(
            "Сначала завершите настройку, затем отправьте ссылку.",
=======
    faq_text = """❓ *Часто задаваемые вопросы*

*Как это работает?*
1️⃣ Отправьте ссылку на товар с Taobao, Tmall или Pinduoduo
2️⃣ Бот автоматически извлекает данные о товаре
3️⃣ Описание переводится и адаптируется на русский язык
4️⃣ Вы получаете готовый пост с фотографиями и характеристиками

*Какие ссылки поддерживаются?*
✅ `item.taobao.com`
✅ `detail.tmall.com`
✅ `mobile.yangkeduo.com`
✅ Короткие ссылки `tb.cn` и `e.tb.cn`

*Как настроить валюту и подпись?*
Используйте команду `/settings` или кнопку "⚙️ Настройки" в меню.
Там можно:
• Изменить подпись для постов
• Выбрать валюту (юань или рубль)
• Установить курс обмена

*Куда обращаться за помощью?*
📧 Если возникли проблемы или вопросы, напишите администратору бота
💬 Используйте команду `/start` для возврата в главное меню

*Где смотреть статистику?*
Статистика использования доступна администратору. В будущем появится личный кабинет для просмотра вашей статистики.

*Технические детали:*
• Бот использует AI для перевода и адаптации текстов
• Фотографии фильтруются по размеру (минимум 500×500px)
• Поддерживается lazy-load для изображений
• Все данные обрабатываются безопасно"""
    
    await message.answer(
        faq_text,
        parse_mode="Markdown",
        reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
    )


@router.message(Command("subscription"))
async def subscription_info(message: Message, state: FSMContext) -> None:
    """Обработчик команды /subscription (кнопка убрана из меню, доступна только через команду)."""
    await state.clear()
    async with get_async_session() as session:
        _, _, is_new_user = await ensure_user_and_settings(message, session)
        await session.commit()
    await message.answer(
        "Подписки появятся позже. Сейчас все функции доступны бесплатно.",
        reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
    )


@router.message(F.text == "🔙 В главное меню")
async def back_to_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with get_async_session() as session:
        _, _, is_new_user = await ensure_user_and_settings(message, session)
        await session.commit()
    await message.answer(
        "Вы вернулись в главное меню.",
        reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
    )


@router.message(F.text == "✍️ Изменить подпись")
async def ask_for_signature(message: Message, state: FSMContext) -> None:
    await state.set_state(SettingsState.waiting_signature)
    await message.answer(
        "Введите новую подпись (например @username или номер телефона)."
    )


@router.message(SettingsState.waiting_signature)
async def update_signature(message: Message, state: FSMContext) -> None:
    new_signature = (message.text or "").strip()
    if not new_signature:
        await message.answer("Подпись не должна быть пустой. Попробуйте снова.")
        return

    async with get_async_session() as session:
        user_service = UserSettingsService(session)
        user, _, _ = await ensure_user_and_settings(message, session)
        await user_service.update_signature(user.id, new_signature)
        await session.commit()

    await state.clear()
    await message.answer(
        f"Подпись обновлена: {new_signature}",
        reply_markup=SETTINGS_MENU_KEYBOARD,
    )


@router.message(F.text == "💱 Валюта")
async def choose_currency(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Выберите валюту по умолчанию:",
        reply_markup=build_currency_keyboard(),
    )


@router.callback_query(F.data.startswith("currency:"))
async def handle_currency_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    choice = callback.data.split(":", 1)[1]

    if choice == "cancel":
        await callback.answer("Выбор отменён")
        await callback.message.edit_reply_markup()
        await callback.message.answer(
            "Настройки не изменены.",
>>>>>>> ea50f5eeb9953ad571713ef3461bd36d187f61e9
            reply_markup=SETTINGS_MENU_KEYBOARD,
        )
        return

<<<<<<< HEAD
    product_url = message.text  # Определяем переменную до try блока
    
    # Получаем настройки пользователя
    user_id = message.from_user.id
    user_settings = user_settings_service.get_settings(user_id)
    
    # Проверяем, что если валюта рубль, то курс установлен
    if user_settings.default_currency.lower() == "rub" and not user_settings.exchange_rate:
        await message.answer(
            "⚠️ Сначала укажите курс рубля в настройках.",
            reply_markup=SETTINGS_MENU_KEYBOARD,
        )
        return
    
    try:
        logger.info(f"Обработка ссылки: {product_url}")
        logger.info(f"Настройки пользователя: валюта={user_settings.default_currency}, курс={user_settings.exchange_rate}, подпись={user_settings.signature}")
        # Скрапинг информации о товаре и генерация текста поста с учётом настроек пользователя
        post_text, image_urls = await scraper.scrape_product(
            product_url,
            user_signature=user_settings.signature,
            user_currency=user_settings.default_currency,
            exchange_rate=user_settings.exchange_rate
        )
        logger.info(f"Скрапинг завершён. Длина текста: {len(post_text) if post_text else 0}, изображений: {len(image_urls) if image_urls else 0}")
        
        # Проверяем, что результат не пустой
        if not post_text:
            logger.warning("Получен пустой текст поста")
            await message.answer(
                "❌ Не удалось получить данные о товаре.\n\n"
                "Возможно, товар недоступен или ссылка неверна."
=======
    async with get_async_session() as session:
        user_service = UserSettingsService(session)
        user, settings_row, _ = await ensure_user_and_settings(callback.message, session)

        if choice == "cny":
            await user_service.update_currency(user.id, "cny")
            await session.commit()
            await callback.answer("Валюта: юань")
            await callback.message.edit_reply_markup()
            await callback.message.answer(
                "Валюта по умолчанию: юань. Конвертация отключена.",
                reply_markup=SETTINGS_MENU_KEYBOARD,
>>>>>>> ea50f5eeb9953ad571713ef3461bd36d187f61e9
            )
        elif choice == "rub":
            settings_row = await user_service.update_currency(user.id, "rub")
            await session.commit()
            await callback.answer("Валюта: рубль")
            await callback.message.edit_reply_markup()

            if not settings_row.exchange_rate:
                await callback.message.answer(
                    "Введите актуальный курс рубля (например 12.35)."
                )
                await state.set_state(SettingsState.waiting_exchange_rate)
            else:
                await callback.message.answer(
                    f"Валюта по умолчанию: рубль. Текущий курс: {float(settings_row.exchange_rate):.4f} ₽ за 1 ¥.",
                    reply_markup=SETTINGS_MENU_KEYBOARD,
                )
        else:
            await callback.answer("Неизвестный выбор", show_alert=True)


@router.message(SettingsState.waiting_exchange_rate)
async def set_exchange_rate(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        rate = float(raw)
        if rate <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное число, например 12.45.")
        return

    async with get_async_session() as session:
        user_service = UserSettingsService(session)
        user, _, _ = await ensure_user_and_settings(message, session)
        await user_service.update_exchange_rate(user.id, rate)
        await session.commit()

    await state.clear()
    await message.answer(
        f"Курс обновлён: 1 ¥ = {rate:.4f} ₽.",
        reply_markup=SETTINGS_MENU_KEYBOARD,
    )


@router.message(
    F.text.regexp(
        r"(https?://)?(www\.)?(m\.)?(e\.)?(detail\.tmall\.com|item\.taobao\.com|a\.m\.taobao\.com|market\.m\.taobao\.com|h5\.m\.taobao\.com|s\.click\.taobao\.com|uland\.taobao\.com|tb\.cn|mobile\.yangkeduo\.com|yangkeduo\.com|pinduoduo\.com|pdd\.com)/.*"
    )
)
async def handle_product_link(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        await message.answer(
            "Сначала завершите настройку, затем отправьте ссылку.",
            reply_markup=SETTINGS_MENU_KEYBOARD,
        )
        return

    async with get_async_session() as session:
        _, _, is_new_user = await ensure_user_and_settings(message, session)
        await session.commit()
    await message.answer(
        "Обрабатываю вашу ссылку, пожалуйста, подождите...",
        reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
    )

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(send_typing_action(message, stop_typing))
    product_url = (message.text or "").strip()

    post_text = ""
    image_urls: list[str] = []

    try:
        async with get_async_session() as session:
            user, user_settings, is_new_user = await ensure_user_and_settings(message, session)

            if user_settings.default_currency.lower() == "rub" and not user_settings.exchange_rate:
                await session.commit()
                await message.answer(
                    "⚠️ Сначала укажите курс рубля в настройках.",
                    reply_markup=SETTINGS_MENU_KEYBOARD,
                )
                return

            llm_manager = LLMProviderManager(session)

            post_text, image_urls = await scraper.scrape_product(
                product_url,
                llm_manager,
                user_settings=user_settings,
            )
            await session.commit()

    except UnsupportedProviderError:
        async with get_async_session() as session:
            _, _, is_new_user = await ensure_user_and_settings(message, session)
            await session.commit()
        await message.answer(
            "Провайдер генерации описаний не настроен. Свяжитесь с администратором.",
            reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
        )
        return
    except Exception as e:
        logger.error(f"Ошибка при обработке ссылки {product_url}: {e}", exc_info=True)
        if error_handler:
            error_type = error_handler.classify_error(e, context=f"scraping {product_url}")
            await error_handler.handle_error(
                error=e,
                user_message=message,
                context=f"Product URL: {product_url}",
                error_type=error_type,
            )
        else:
            logger.warning("error_handler не инициализирован, используем fallback")
            async with get_async_session() as session:
                _, _, is_new_user = await ensure_user_and_settings(message, session)
                await session.commit()
            await message.answer(
                "😔 Извините, произошла ошибка при обработке вашего запроса. "
                "Пожалуйста, попробуйте повторить через несколько минут.",
                reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
            )
        return
    finally:
        stop_typing.set()
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    if not post_text:
        async with get_async_session() as session:
            _, _, is_new_user = await ensure_user_and_settings(message, session)
            await session.commit()
        await message.answer(
            "❌ Не удалось получить данные о товаре.\n\n"
            "Возможно, товар недоступен или ссылка неверна.",
            reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
        )
        return

    if image_urls:
        main_images = image_urls[:4]

        if len(main_images) == 1:
            try:
                await message.answer_photo(
                    main_images[0],
                    caption=post_text,
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                        response = await client.get(main_images[0])
                        if response.status_code == 200 and response.content:
                            await message.answer_photo(
                                BufferedInputFile(response.content, filename="photo.jpg"),
                                caption=post_text,
                                parse_mode="HTML",
                            )
                        else:
                            async with get_async_session() as session:
                                _, _, is_new_user = await ensure_user_and_settings(message, session)
                                await session.commit()
                            await message.answer(post_text, parse_mode="HTML", reply_markup=build_main_menu_keyboard(is_new_user=is_new_user))
                except Exception:
                    async with get_async_session() as session:
                        _, _, is_new_user = await ensure_user_and_settings(message, session)
                        await session.commit()
                    await message.answer(post_text, parse_mode="HTML", reply_markup=build_main_menu_keyboard(is_new_user=is_new_user))
        else:
            media_main = []
            for i, url in enumerate(main_images):
                if i == 0:
                    media_main.append(InputMediaPhoto(media=url, caption=post_text, parse_mode="HTML"))
                else:
                    media_main.append(InputMediaPhoto(media=url))

            try:
                await message.answer_media_group(media=media_main)
            except TelegramBadRequest:
                try:
                    files: list[InputMediaPhoto] = []
                    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                        for i, url in enumerate(main_images):
                            try:
                                response = await client.get(url)
                                if response.status_code != 200 or not response.content:
                                    continue
                                buffer = BufferedInputFile(response.content, filename=f"photo_{i+1}.jpg")
                                if i == 0:
                                    files.append(InputMediaPhoto(media=buffer, caption=post_text, parse_mode="HTML"))
                                else:
                                    files.append(InputMediaPhoto(media=buffer))
                            except Exception:
                                continue
                    if files:
                        await message.answer_media_group(media=files)
                    else:
                        async with get_async_session() as session:
                            _, _, is_new_user = await ensure_user_and_settings(message, session)
                            await session.commit()
                        await message.answer(post_text, parse_mode="HTML", reply_markup=build_main_menu_keyboard(is_new_user=is_new_user))
                except Exception:
                    async with get_async_session() as session:
                        _, _, is_new_user = await ensure_user_and_settings(message, session)
                        await session.commit()
                    await message.answer(post_text, parse_mode="HTML", reply_markup=build_main_menu_keyboard(is_new_user=is_new_user))

            if len(image_urls) > len(main_images):
                remaining_images = image_urls[len(main_images):]
                for i in range(0, len(remaining_images), 10):
                    batch = remaining_images[i : i + 10]
                    media_batch = [InputMediaPhoto(media=url) for url in batch]
                    try:
                        await message.answer_media_group(media=media_batch)
                    except TelegramBadRequest:
                        try:
                            files: list[InputMediaPhoto] = []
                            async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                                for j, url in enumerate(batch):
                                    try:
                                        response = await client.get(url)
                                        if response.status_code != 200 or not response.content:
                                            continue
                                        files.append(
                                            InputMediaPhoto(
                                                media=BufferedInputFile(
                                                    response.content,
                                                    filename=f"photo_more_{i+j+1}.jpg",
                                                )
                                            )
                                        )
                                    except Exception:
                                        continue
                            if files:
                                await message.answer_media_group(media=files)
                        except Exception:
                            pass
    else:
        async with get_async_session() as session:
            _, _, is_new_user = await ensure_user_and_settings(message, session)
            await session.commit()
        await message.answer(post_text, parse_mode="HTML", reply_markup=build_main_menu_keyboard(is_new_user=is_new_user))


@router.message()
<<<<<<< HEAD
async def echo_message(message: Message, state: FSMContext):
    """
    Обработчик для всех остальных сообщений, которые не были обработаны другими хэндлерами.
    """
    await state.clear()
    await message.answer(
        "Пожалуйста, отправьте мне ссылку на товар Taobao/Tmall или используйте команду /start.",
        reply_markup=build_main_menu_keyboard()
    )
=======
async def fallback_message(message: Message):
    async with get_async_session() as session:
        _, _, is_new_user = await ensure_user_and_settings(message, session)
        await session.commit()
    await message.answer(
        "Пожалуйста, отправьте ссылку на товар или воспользуйтесь кнопками меню.",
        reply_markup=build_main_menu_keyboard(is_new_user=is_new_user),
    )


>>>>>>> ea50f5eeb9953ad571713ef3461bd36d187f61e9
