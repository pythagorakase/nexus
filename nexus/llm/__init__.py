"""Pluggable LLM backends and routing utilities."""

from typing import TYPE_CHECKING

from .base import LLMBackend, LLMResponse
from .cloud import CloudBackend
from .local import LocalLMStudioBackend
from .remote import RemoteLMStudioBackend
from .router import LLMRouter

if TYPE_CHECKING:
    from .model_manager import ModelManager

__all__ = [
    "LLMBackend",
    "LLMResponse",
    "CloudBackend",
    "LocalLMStudioBackend",
    "RemoteLMStudioBackend",
    "LLMRouter",
    "ModelManager",
]


def __getattr__(name: str) -> object:
    if name == "ModelManager":
        from .model_manager import ModelManager

        return ModelManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
