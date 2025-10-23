"""
Модуль для обработки ошибок в production режиме.
Обеспечивает дружественные сообщения для пользователей и детальные уведомления для админов.
"""

import logging
import traceback
from datetime import datetime
from typing import Optional
from logging.handlers import RotatingFileHandler
from aiogram import Bot
from aiogram.types import Message

from config import settings

# Настройка логирования с ротацией
# Максимум 100 МБ на файл, храним 3 файла (итого ~300 МБ / ~3 месяца)
file_handler = RotatingFileHandler(
    'bot_errors.log',
    maxBytes=100 * 1024 * 1024,  # 100 МБ
    backupCount=2,  # Храним текущий + 2 старых файла
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Настраиваем root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Класс для централизованной обработки ошибок"""
    
    # Дружественные сообщения для пользователей
    USER_MESSAGES = {
        'api_error': (
            "😔 Извините, произошла ошибка при получении данных о товаре.\n\n"
            "Возможные причины:\n"
            "• Товар недоступен или удалён\n"
            "• Временные проблемы с сервисом\n\n"
            "Пожалуйста, попробуйте:\n"
            "1️⃣ Проверить, что ссылка ведёт на доступный товар\n"
            "2️⃣ Повторить попытку через несколько минут\n\n"
            "Наша команда уже уведомлена о проблеме и работает над её устранением. 🛠️"
        ),
        'network_error': (
            "😔 Извините, возникли проблемы с подключением к сервису.\n\n"
            "Пожалуйста, попробуйте повторить запрос через 1-2 минуты.\n\n"
            "Наша команда уже уведомлена о проблеме и работает над её устранением. 🛠️"
        ),
        'parsing_error': (
            "😔 Извините, не удалось обработать информацию о товаре.\n\n"
            "Возможные причины:\n"
            "• Нестандартная структура страницы товара\n"
            "• Неполные данные от продавца\n\n"
            "Пожалуйста, попробуйте другой товар или повторите попытку позже.\n\n"
            "Наша команда уже уведомлена о проблеме. 🛠️"
        ),
        'llm_error': (
            "😔 Извините, произошла ошибка при генерации описания товара.\n\n"
            "Это временная проблема с нашим сервисом генерации текстов.\n\n"
            "Пожалуйста, попробуйте повторить запрос через несколько минут.\n\n"
            "Наша команда уже уведомлена о проблеме и работает над её устранением. 🛠️"
        ),
        'telegram_error': (
            "😔 Извините, возникла проблема при отправке сообщения.\n\n"
            "Возможные причины:\n"
            "• Слишком большие изображения\n"
            "• Временные ограничения Telegram\n\n"
            "Попробуйте повторить запрос.\n\n"
            "Наша команда уже уведомлена о проблеме. 🛠️"
        ),
        'unknown_error': (
            "😔 Извините, произошла непредвиденная ошибка.\n\n"
            "Мы уже получили информацию о проблеме и работаем над её устранением.\n\n"
            "Пожалуйста, попробуйте:\n"
            "1️⃣ Повторить запрос через несколько минут\n"
            "2️⃣ Попробовать другой товар\n\n"
            "Приносим извинения за неудобства! 🙏"
        )
    }
    
    def __init__(self, bot: Bot, admin_chat_id: Optional[str] = None):
        """
        Инициализация обработчика ошибок.
        
        Args:
            bot: Экземпляр aiogram Bot для отправки уведомлений
            admin_chat_id: ID чата администратора для уведомлений об ошибках
        """
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        
    async def handle_error(
        self,
        error: Exception,
        user_message: Message,
        context: str = "",
        error_type: str = "unknown_error"
    ) -> None:
        """
        Обрабатывает ошибку: логирует, уведомляет админа, отправляет дружественное сообщение пользователю.
        
        Args:
            error: Исключение, которое произошло
            user_message: Сообщение пользователя, вызвавшее ошибку
            context: Дополнительный контекст (например, URL товара)
            error_type: Тип ошибки для выбора сообщения пользователю
        """
        # Получаем полный traceback
        tb = traceback.format_exc()
        
        # Формируем информацию об ошибке для логов
        error_info = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_message.from_user.id,
            'username': user_message.from_user.username,
            'chat_id': user_message.chat.id,
            'message_text': user_message.text,
            'error_type': error_type,
            'error_class': error.__class__.__name__,
            'error_message': str(error),
            'context': context,
            'traceback': tb
        }
        
        # Логируем ошибку
        logger.error(
            f"Error occurred: {error_type}\n"
            f"User: {user_message.from_user.id} (@{user_message.from_user.username})\n"
            f"Message: {user_message.text}\n"
            f"Context: {context}\n"
            f"Error: {error.__class__.__name__}: {str(error)}\n"
            f"Traceback:\n{tb}"
        )
        
        # Отправляем дружественное сообщение пользователю
        user_friendly_message = self.USER_MESSAGES.get(error_type, self.USER_MESSAGES['unknown_error'])
        try:
            await user_message.answer(user_friendly_message)
        except Exception as send_error:
            logger.error(f"Failed to send error message to user: {send_error}")
        
        # Уведомляем администратора
        await self._notify_admin(error_info)
    
    async def _notify_admin(self, error_info: dict) -> None:
        """
        Отправляет уведомление администратору о произошедшей ошибке.
        
        Args:
            error_info: Словарь с информацией об ошибке
        """
        if not self.admin_chat_id:
            logger.warning("Admin chat ID not configured, skipping admin notification")
            return
        
        # Формируем красивое сообщение для админа
        admin_message = (
            "🚨 <b>ОШИБКА В БОТЕ</b> 🚨\n\n"
            f"⏰ <b>Время:</b> {error_info['timestamp']}\n"
            f"👤 <b>Пользователь:</b> {error_info['user_id']} "
            f"(@{error_info['username'] or 'unknown'})\n"
            f"💬 <b>Чат:</b> {error_info['chat_id']}\n"
            f"📝 <b>Сообщение:</b> <code>{error_info['message_text'][:100]}</code>\n\n"
            f"❗ <b>Тип ошибки:</b> {error_info['error_type']}\n"
            f"🐛 <b>Класс:</b> <code>{error_info['error_class']}</code>\n"
            f"📄 <b>Описание:</b> <code>{error_info['error_message'][:200]}</code>\n"
        )
        
        if error_info['context']:
            admin_message += f"\n🔗 <b>Контекст:</b> <code>{error_info['context'][:100]}</code>\n"
        
        # Отправляем traceback отдельным сообщением (если не слишком длинный)
        traceback_preview = error_info['traceback'][:3000]
        
        try:
            await self.bot.send_message(
                chat_id=self.admin_chat_id,
                text=admin_message,
                parse_mode="HTML"
            )
            
            # Отправляем traceback
            await self.bot.send_message(
                chat_id=self.admin_chat_id,
                text=f"<b>Traceback:</b>\n<pre>{traceback_preview}</pre>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")
    
    @staticmethod
    def classify_error(error: Exception, context: str = "") -> str:
        """
        Классифицирует ошибку для выбора подходящего сообщения пользователю.
        
        Args:
            error: Исключение
            context: Контекст (например, где произошла ошибка)
            
        Returns:
            Тип ошибки (ключ для USER_MESSAGES)
        """
        error_class = error.__class__.__name__
        error_message = str(error).lower()
        
        # API ошибки
        if any(keyword in error_message for keyword in ['api', 'tmapi', '400', '401', '403', '404', '500', '502', '503']):
            return 'api_error'
        
        # Сетевые ошибки
        if any(keyword in error_class.lower() for keyword in ['timeout', 'connection', 'network', 'httpx']):
            return 'network_error'
        
        # Ошибки парсинга
        if any(keyword in error_class.lower() for keyword in ['parse', 'json', 'keyerror', 'valueerror', 'attributeerror']):
            return 'parsing_error'
        
        # Ошибки LLM
        if any(keyword in context.lower() for keyword in ['yandexgpt', 'llm', 'generation']):
            return 'llm_error'
        
        # Ошибки Telegram
        if any(keyword in error_class.lower() for keyword in ['telegram', 'aiogram', 'media']):
            return 'telegram_error'
        
        # Неизвестная ошибка
        return 'unknown_error'


# Глобальный обработчик (будет инициализирован в autoparse.py)
error_handler: Optional[ErrorHandler] = None


def init_error_handler(bot: Bot, admin_chat_id: Optional[str] = None) -> ErrorHandler:
    """
    Инициализирует глобальный обработчик ошибок.
    
    Args:
        bot: Экземпляр aiogram Bot
        admin_chat_id: ID чата администратора
        
    Returns:
        Экземпляр ErrorHandler
    """
    global error_handler
    error_handler = ErrorHandler(bot, admin_chat_id)
    return error_handler

