"""
Утилита для отслеживания статистики использования Redis кэша.
"""

from dataclasses import dataclass


@dataclass
class CacheStats:
    """
    Статистика использования кэша для одного запроса.
    
    Attributes:
        hits: Количество попаданий в кэш (cache hits)
        misses: Количество промахов кэша (cache misses)
        saved_tokens: Сэкономлено токенов благодаря кэшу
        saved_cost: Сэкономлено денег благодаря кэшу (USD)
        saved_time_ms: Сэкономлено времени благодаря кэшу (мс)
    """
    hits: int = 0  # Количество попаданий в кэш
    misses: int = 0  # Количество промахов кэша
    saved_tokens: int = 0  # Сэкономлено токенов
    saved_cost: float = 0.0  # Сэкономлено денег (USD)
    saved_time_ms: int = 0  # Сэкономлено времени (мс)
    
    def add_hit(self, saved_tokens: int = 0, saved_cost: float = 0.0, saved_time_ms: int = 0):
        """
        Добавить попадание в кэш.
        
        Args:
            saved_tokens: Количество сэкономленных токенов
            saved_cost: Сэкономленная сумма в долларах
            saved_time_ms: Сэкономленное время в миллисекундах
        """
        self.hits += 1
        self.saved_tokens += saved_tokens
        self.saved_cost += saved_cost
        self.saved_time_ms += saved_time_ms
    
    def add_miss(self):
        """Добавить промах кэша."""
        self.misses += 1
    
    def total_requests(self) -> int:
        """Общее количество запросов к кэшу."""
        return self.hits + self.misses
    
    def hit_rate(self) -> float:
        """
        Процент попаданий в кэш (0.0 - 1.0).
        
        Returns:
            float: Процент попаданий от 0.0 до 1.0
        """
        total = self.total_requests()
        if total == 0:
            return 0.0
        return self.hits / total
