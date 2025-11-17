import asyncio
import random
import logging
from aiogram import Router, F
from aiogram.types import Message, InputMediaPhoto, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import httpx
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatAction

from src.core.scraper import Scraper
from src.bot.error_handler import error_handler
from src.services.user_settings import UserSettingsService

logger = logging.getLogger(__name__)

# Инициализация роутера для обработки сообщений
router = Router()
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
    
    # Создаём событие для остановки typing action
    stop_typing = asyncio.Event()
    
    # Запускаем фоновую задачу для индикатора "печатает"
    typing_task = asyncio.create_task(send_typing_action(message, stop_typing))
    
    # Проверяем, не находимся ли мы в процессе настройки
    current_state = await state.get_state()
    if current_state:
        await message.answer(
            "Сначала завершите настройку, затем отправьте ссылку.",
            reply_markup=SETTINGS_MENU_KEYBOARD,
        )
        return

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
            )
            return
        
        if image_urls and len(image_urls) > 0:
            # Готовим первые изображения для первого сообщения
            # Основной пост ограничиваем 4 фото (Taobao/Tmall/PDD)
            main_images = image_urls[:4]

            # Если только одно изображение — отправляем как одиночное фото (альбом требует ≥2)
            if len(main_images) == 1:
                try:
                    await message.answer_photo(main_images[0], caption=post_text, parse_mode="HTML")
                except TelegramBadRequest:
                    # Фолбэк: скачать и отправить как файл
                    try:
                        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                            r = await client.get(main_images[0])
                            if r.status_code == 200 and r.content:
                                fname = "photo.jpg"
                                await message.answer_photo(BufferedInputFile(r.content, filename=fname), caption=post_text, parse_mode="HTML")
                            else:
                                await message.answer(post_text, parse_mode="HTML")
                    except Exception:
                        await message.answer(post_text, parse_mode="HTML")
            else:
                # Собираем медиагруппу (первая с подписью)
                media_main = []
                for i, url in enumerate(main_images):
                    if i == 0:
                        media_main.append(InputMediaPhoto(media=url, caption=post_text, parse_mode="HTML"))
                    else:
                        media_main.append(InputMediaPhoto(media=url))

                try:
                    await message.answer_media_group(media=media_main)
                except TelegramBadRequest:
                    # Фолбэк: предварительно скачиваем и отправляем как файлы (альбом)
                    try:
                        files: list[InputMediaPhoto] = []
                        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                            for i, url in enumerate(main_images):
                                try:
                                    r = await client.get(url)
                                    if r.status_code != 200 or not r.content:
                                        continue
                                    fname = f"photo_{i+1}.jpg"
                                    buf = BufferedInputFile(r.content, filename=fname)
                                    if i == 0:
                                        files.append(InputMediaPhoto(media=buf, caption=post_text, parse_mode="HTML"))
                                    else:
                                        files.append(InputMediaPhoto(media=buf))
                                except Exception:
                                    continue
                        if files:
                            await message.answer_media_group(media=files)
                        else:
                            await message.answer(post_text, parse_mode="HTML")
                    except Exception:
                        await message.answer(post_text, parse_mode="HTML")

                # Дополнительные фото после первых 10 (если есть)
                if len(image_urls) > len(main_images):
                    remaining_images = image_urls[len(main_images):]
                    for i in range(0, len(remaining_images), 10):
                        batch = remaining_images[i:i+10]
                        media_batch = [InputMediaPhoto(media=url) for url in batch]
                        try:
                            await message.answer_media_group(media=media_batch)
                        except TelegramBadRequest:
                            # Фолбэк: скачиваем и отправляем файлы
                            try:
                                files: list[InputMediaPhoto] = []
                                async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                                    for j, url in enumerate(batch):
                                        try:
                                            r = await client.get(url)
                                            if r.status_code != 200 or not r.content:
                                                continue
                                            fname = f"photo_more_{i+j+1}.jpg"
                                            files.append(InputMediaPhoto(media=BufferedInputFile(r.content, filename=fname)))
                                        except Exception:
                                            continue
                                if files:
                                    await message.answer_media_group(media=files)
                            except Exception:
                                pass
        else:
            # Если изображений нет, отправляем только текст
            await message.answer(post_text, parse_mode="HTML")

    except Exception as e:
        # Логируем ошибку перед обработкой
        logger.error(f"Ошибка при обработке ссылки {product_url}: {e}", exc_info=True)
        # Профессиональная обработка ошибок
        if error_handler:
            # Определяем тип ошибки и контекст
            error_type = error_handler.classify_error(e, context=f"scraping {product_url}")
            await error_handler.handle_error(
                error=e,
                user_message=message,
                context=f"Product URL: {product_url}",
                error_type=error_type
            )
        else:
            # Fallback на случай если error_handler не инициализирован
            logger.warning("error_handler не инициализирован, используем fallback")
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
    await state.clear()
    await message.answer(
        "Пожалуйста, отправьте мне ссылку на товар Taobao/Tmall или используйте команду /start.",
        reply_markup=build_main_menu_keyboard()
    )