"""
==============================================================================
TAOBAO SCRAPER BOT - MAIN ENTRY POINT
==============================================================================
Главная точка входа приложения.
Инициализирует и запускает Telegram бота для парсинга товаров с Taobao/Tmall.

Author: Your Name
Version: 1.0.0
License: MIT
==============================================================================
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from src.core.config import settings
from src.bot.error_handler import init_error_handler
from src.bot.handlers import router

# Конфигурация базового логирования (детальное логирование в error_handler.py)
logging.basicConfig(level=logging.INFO)


async def main():
    """
    Основная асинхронная функция для запуска Telegram бота.
    
    Выполняет следующие шаги:
    1. Инициализирует бота с токеном из .env
    2. Создаёт диспетчер для обработки сообщений
    3. Инициализирует систему обработки ошибок с уведомлениями админу
    4. Регистрирует обработчики сообщений (роутеры)
    5. Удаляет старые вебхуки (если были)
    6. Запускает long polling для получения обновлений
    
    Raises:
        Exception: Любые ошибки логируются и приводят к остановке бота
    """
    # Инициализация бота с токеном из настроек
    bot = Bot(token=settings.BOT_TOKEN)
    # Инициализация диспетчера
    dp = Dispatcher()
    
    # Инициализация глобального обработчика ошибок
    admin_chat_id = settings.ADMIN_CHAT_ID if settings.ADMIN_CHAT_ID else None
    init_error_handler(bot, admin_chat_id)
    logging.info(f"Error handler initialized. Admin notifications: {'enabled' if admin_chat_id else 'disabled'}")
    
    # Включение роутера обработчиков сообщений
    dp.include_router(router)

    # Удаление вебхуков (если были) и запуск поллинга для получения обновлений
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot started successfully! 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запуск основной функции
    asyncio.run(main())