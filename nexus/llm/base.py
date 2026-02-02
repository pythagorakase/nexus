"""Base interfaces for pluggable LLM backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Dict, Any


@dataclass
class LLMResponse:
    """Standard response payload from an LLM backend."""

    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None


class LLMBackend(ABC):
    """Abstract interface for async LLM backends."""

    @abstractmethod
    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Return a full completion for the prompt."""

    @abstractmethod
    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """Stream completion tokens for the prompt."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the backend can currently serve requests."""
