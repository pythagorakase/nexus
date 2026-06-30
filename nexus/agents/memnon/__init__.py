"""
MEMNON Agent - Unified Memory Access System

This module implements the MEMNON agent, which provides a unified interface
for memory management, embedding generation, and cross-reference retrieval
across both structured database storage and semantic vector search.
"""

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .memnon import MEMNON

__all__ = ["MEMNON"]


def __getattr__(name: str) -> Any:
    """Resolve package-level MEMNON export only when callers request it."""
    if name in __all__:
        from .memnon import MEMNON

        exports = {"MEMNON": MEMNON}
        globals().update(exports)
        return exports[name]
    raise AttributeError(f"module 'nexus.agents.memnon' has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return discoverable package exports without importing the agent stack."""
    return sorted({*globals(), *__all__})
