from aiogram import Router, F
from aiogram.types import Message, InputMediaPhoto
from aiogram.filters import CommandStart

from scraper import Scraper

# Инициализация роутера для обработки сообщений
router = Router()
# Инициализация скрапера для получения информации о товарах
scraper = Scraper() 

@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение пользователю.
    """
    await message.answer(f"Привет, {message.from_user.full_name}! Отправь мне ссылку на товар с Taobao или Tmall.")

@router.message(F.text.regexp(r"(https?://)?(www\.)?(m\.)?(e\.)?(detail\.tmall\.com|item\.taobao\.com|a\.m\.taobao\.com|market\.m\.taobao\.com|h5\.m\.taobao\.com|s\.click\.taobao\.com|uland\.taobao\.com|tb\.cn)/.*"))
async def handle_product_link(message: Message) -> None:
    """
    Обработчик сообщений, содержащих ссылки на товары Taobao/Tmall.
    Извлекает информацию о товаре, генерирует пост и отправляет его пользователю.
    """
    await message.answer("Обрабатываю вашу ссылку, пожалуйста, подождите...")
    try:
        product_url = message.text
        # Скрапинг информации о товаре и генерация текста поста
        post_text, image_urls = await scraper.scrape_product(product_url)

        if image_urls and len(image_urls) > 0:
            # Отправляем первые 4 фото с текстом поста
            media_main = []
            main_images = image_urls[:4]  # Первые 4 фото для основного сообщения
            
            for i, url in enumerate(main_images):
                if i == 0:
                    # Первое изображение с подписью (текстом поста)
                    media_main.append(InputMediaPhoto(media=url, caption=post_text, parse_mode="HTML"))
                else:
                    # Остальные изображения без подписи
                    media_main.append(InputMediaPhoto(media=url))
            
            await message.answer_media_group(media=media_main)
            
            # Если фото больше 4, отправляем оставшиеся отдельным сообщением
            if len(image_urls) > 4:
                remaining_images = image_urls[4:]  # Все фото после 4-го
                media_additional = []
                
                # Telegram позволяет до 10 фото в медиагруппе
                # Отправляем оставшиеся фото группами по 10
                for i in range(0, len(remaining_images), 10):
                    batch = remaining_images[i:i+10]
                    media_batch = [InputMediaPhoto(media=url) for url in batch]
                    await message.answer_media_group(media=media_batch)
        else:
            # Если изображений нет, отправляем только текст
            await message.answer(post_text, parse_mode="HTML")

    except Exception as e:
        # Обработка ошибок и отправка сообщения об ошибке пользователю
        error_message = f"Произошла ошибка при обработке ссылки: {str(e)}"
        print(f"[ERROR] {error_message}")
        await message.answer(error_message)

@router.message()
async def echo_message(message: Message):
    """
    Обработчик для всех остальных сообщений, которые не были обработаны другими хэндлерами.
    """
    await message.answer("Пожалуйста, отправьте мне ссылку на товар Taobao/Tmall или используйте команду /start.")