"""Base abstractions for LLM providers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict
from abc import ABC, abstractmethod


@dataclass(slots=True)
class LLMResult:
    """Normalized LLM response."""

    data: Dict[str, Any]
    raw_text: str
    tokens_used: int | None = None


class LLMProvider(ABC):
    """Interface for LLM providers."""

    vendor: str

    @abstractmethod
    async def generate(self, payload: Dict[str, Any]) -> LLMResult:
        """Produce content for the given payload."""

    def build_cache_key(self, payload: Dict[str, Any]) -> str:
        """Deterministic cache key from payload."""
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


