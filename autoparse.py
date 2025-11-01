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
from config import settings
from error_handler import init_error_handler

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
    error_handler = init_error_handler(bot, admin_chat_id)
    logging.info(f"Error handler initialized. Admin notifications: {'enabled' if admin_chat_id else 'disabled'}")
    
    # Проверяем доступность чата админа при старте (если задан)
    if error_handler.admin_chat_id:
        try:
            from error_handler import _test_admin_chat
            test_result = await _test_admin_chat(bot, error_handler.admin_chat_id)
            if test_result:
                logging.info(f"✅ Admin chat доступен. Уведомления будут отправляться в chat_id: {error_handler.admin_chat_id}")
            else:
                logging.warning(f"⚠️ Не удалось проверить доступность admin chat. Уведомления могут не работать.")
        except Exception as e:
            logging.warning(f"⚠️ Ошибка при проверке admin chat: {e}")
    
    # Импорт и включение роутера обработчиков сообщений
    from bot_handler import router as bot_router
    dp.include_router(bot_router)

    # Удаление вебхуков (если были) и запуск поллинга для получения обновлений
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot started successfully! 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запуск основной функции
    asyncio.run(main())