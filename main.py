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
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    MenuButtonCommands,
)
from src.core.config import settings
from src.core.config_manager import config_manager
from src.core.logging_config import setup_logging
from src.bot.error_handler import init_error_handler
from src.bot.handlers import router

# Конфигурация логирования
setup_logging()


async def setup_bot_menu(bot: Bot) -> None:
    """
    Настраивает список команд бота, отображаемых в боковом меню Telegram.
    """
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="request", description="Запросить описание товара"),
        BotCommand(command="about", description="О сервисе"),
        BotCommand(command="faq", description="Часто задаваемые вопросы"),
        BotCommand(command="settings", description="Открыть настройки"),
        BotCommand(command="mysettings", description="Показать мои настройки"),
        BotCommand(command="subscription", description="Информация о подписке"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def main():
    """
    Основная асинхронная функция для запуска Telegram бота.
    
    Выполняет следующие шаги:
    1. Загружает настройки из БД (если доступны)
    2. Инициализирует бота с токеном из настроек
    3. Создаёт диспетчер для обработки сообщений
    4. Инициализирует систему обработки ошибок с уведомлениями админу
    5. Регистрирует обработчики сообщений (роутеры)
    6. Удаляет старые вебхуки (если были)
    7. Запускает long polling для получения обновлений
    
    Raises:
        Exception: Любые ошибки логируются и приводят к остановке бота
    """
    # Загружаем настройки из БД (с приоритетом над .env)
    try:
        await config_manager.load_from_db()
        logging.info("Настройки из БД загружены успешно")
    except Exception as e:
        logging.warning(f"Не удалось загрузить настройки из БД, используем .env: {e}")
    
    # Инициализация бота с токеном из настроек
    bot = Bot(token=settings.BOT_TOKEN)
    await setup_bot_menu(bot)
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
    try:
        await dp.start_polling(bot)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logging.info("Остановка бота по запросу пользователя…")
    finally:
        # Пытаемся закрыть storage если он есть
        try:
            if hasattr(dp, 'storage') and dp.storage:
                await dp.storage.close()
        except Exception:
            pass
        # Закрываем сессию бота
        try:
            await bot.session.close()
        except Exception:
            pass
        # Отменяем все оставшиеся задачи, чтобы убрать CancelledError в stdout
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in pending:
            task.cancel()
        if pending:
            try:
                await asyncio.gather(*pending, return_exceptions=True)
            except Exception:
                pass

if __name__ == "__main__":
    # Запуск основной функции
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Работа завершена по прерыванию.")