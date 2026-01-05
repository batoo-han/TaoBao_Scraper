"""
Клиент Redis для работы с сессиями и временными данными.
"""

import json
from typing import Optional, Any
from redis.asyncio import Redis, ConnectionPool
from src.core.config import settings


class RedisClient:
    """Асинхронный клиент Redis"""
    
    def __init__(self):
        self.redis: Optional[Redis] = None
        self._pool: Optional[ConnectionPool] = None
    
    async def connect(self):
        """Подключение к Redis"""
        if self.redis is None:
            # Парсим URL Redis
            # Формат: redis://:password@host:port/db
            self._pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
            self.redis = Redis(connection_pool=self._pool)
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis:
            await self.redis.close()
            self.redis = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
    
    async def get(self, key: str) -> Optional[str]:
        """Получить значение по ключу"""
        if not self.redis:
            await self.connect()
        return await self.redis.get(key)
    
    async def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """
        Установить значение по ключу
        
        Args:
            key: Ключ
            value: Значение
            expire: Время жизни в секундах (опционально)
        
        Returns:
            bool: True если успешно
        """
        if not self.redis:
            await self.connect()
        return await self.redis.set(key, value, ex=expire)
    
    async def delete(self, key: str) -> int:
        """
        Удалить значение по ключу
        
        Args:
            key: Ключ
        
        Returns:
            int: Количество удаленных ключей
        """
        if not self.redis:
            await self.connect()
        return await self.redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Проверить существование ключа"""
        if not self.redis:
            await self.connect()
        return await self.redis.exists(key) > 0
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Установить время жизни ключа"""
        if not self.redis:
            await self.connect()
        return await self.redis.expire(key, seconds)
    
    async def get_json(self, key: str) -> Optional[Any]:
        """Получить JSON значение"""
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    
    async def set_json(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Установить JSON значение"""
        json_str = json.dumps(value, ensure_ascii=False)
        return await self.set(key, json_str, expire=expire)
    
    async def incr(self, key: str) -> int:
        """Увеличить значение на 1"""
        if not self.redis:
            await self.connect()
        return await self.redis.incr(key)
    
    async def decr(self, key: str) -> int:
        """Уменьшить значение на 1"""
        if not self.redis:
            await self.connect()
        return await self.redis.decr(key)


# Глобальный экземпляр клиента
_redis_client = RedisClient()

# Экспорт для совместимости
redis_client = _redis_client


def get_redis_client() -> RedisClient:
    """Получить глобальный экземпляр Redis клиента"""
    return _redis_client


async def init_redis():
    """Инициализация Redis (подключение)"""
    await _redis_client.connect()


async def close_redis():
    """Закрытие подключения к Redis"""
    await _redis_client.disconnect()
