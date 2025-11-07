import asyncio
import random
import logging
from aiogram import Router, F
from aiogram.types import Message, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, BufferedInputFile
import httpx
from aiogram.filters import CommandStart
from aiogram.enums import ChatAction

from src.core.scraper import Scraper
from src.bot.error_handler import error_handler

logger = logging.getLogger(__name__)

# Инициализация роутера для обработки сообщений
router = Router()
# Инициализация скрапера для получения информации о товарах
scraper = Scraper() 


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
async def command_start_handler(message: Message) -> None:
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение пользователю.
    """
    await message.answer(f"Привет, {message.from_user.full_name}! Отправь мне ссылку на товар с Taobao, Tmall или Pinduoduo.")

@router.message(F.text.regexp(r"(https?://)?(www\.)?(m\.)?(e\.)?(detail\.tmall\.com|item\.taobao\.com|a\.m\.taobao\.com|market\.m\.taobao\.com|h5\.m\.taobao\.com|s\.click\.taobao\.com|uland\.taobao\.com|tb\.cn|mobile\.yangkeduo\.com|yangkeduo\.com|pinduoduo\.com|pdd\.com)/.*"))
async def handle_product_link(message: Message) -> None:
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
    
    product_url = message.text  # Определяем переменную до try блока
    try:
        logger.info(f"Обработка ссылки: {product_url}")
        # Скрапинг информации о товаре и генерация текста поста
        post_text, image_urls = await scraper.scrape_product(product_url)
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
async def echo_message(message: Message):
    """
    Обработчик для всех остальных сообщений, которые не были обработаны другими хэндлерами.
    """
    await message.answer("Пожалуйста, отправьте мне ссылку на товар Taobao/Tmall или используйте команду /start.")