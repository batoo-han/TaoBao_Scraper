import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import settings

# Конфигурация логирования
logging.basicConfig(level=logging.INFO)

async def main():
    """
    Основная функция для запуска Telegram бота.
    Инициализирует бота и диспетчер, регистрирует обработчики и запускает поллинг.
    """
    # Инициализация бота с токеном из настроек
    bot = Bot(token=settings.BOT_TOKEN)
    # Инициализация диспетчера
    dp = Dispatcher()
    
    # Импорт и включение роутера обработчиков сообщений
    from bot_handler import router as bot_router
    dp.include_router(bot_router)

    # Удаление вебхуков (если были) и запуск поллинга для получения обновлений
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запуск основной функции
    asyncio.run(main())