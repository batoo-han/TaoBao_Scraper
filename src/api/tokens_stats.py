"""
Структура для хранения статистики использования токенов OpenAI.

Содержит информацию о количестве токенов и их стоимости для входных и выходных запросов.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokensUsage:
    """
    Статистика использования токенов и их стоимость.
    
    Attributes:
        prompt_tokens: Количество токенов во входящем промпте
        completion_tokens: Количество токенов в ответе модели
        total_tokens: Общее количество токенов
        prompt_cost: Стоимость входных токенов в долларах США
        completion_cost: Стоимость выходных токенов в долларах США
        total_cost: Общая стоимость запроса в долларах США
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0

    def __add__(self, other: "TokensUsage") -> "TokensUsage":
        """Сложение статистики токенов для агрегации."""
        return TokensUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            prompt_cost=self.prompt_cost + other.prompt_cost,
            completion_cost=self.completion_cost + other.completion_cost,
            total_cost=self.total_cost + other.total_cost,
        )

    def __iadd__(self, other: "TokensUsage") -> "TokensUsage":
        """Инкрементальное сложение статистики токенов."""
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.prompt_cost += other.prompt_cost
        self.completion_cost += other.completion_cost
        self.total_cost += other.total_cost
        return self


def calculate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    prompt_price_per_1m: float,
    completion_price_per_1m: float,
) -> TokensUsage:
    """
    Вычисляет стоимость использования токенов на основе цен.
    
    Args:
        prompt_tokens: Количество входных токенов
        completion_tokens: Количество выходных токенов
        prompt_price_per_1m: Цена за 1 000 000 входных токенов в USD
        completion_price_per_1m: Цена за 1 000 000 выходных токенов в USD
    
    Returns:
        TokensUsage объект с заполненной статистикой
    """
    prompt_cost = (prompt_tokens / 1_000_000.0) * prompt_price_per_1m
    completion_cost = (completion_tokens / 1_000_000.0) * completion_price_per_1m
    total_cost = prompt_cost + completion_cost
    
    return TokensUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        prompt_cost=prompt_cost,
        completion_cost=completion_cost,
        total_cost=total_cost,
    )

