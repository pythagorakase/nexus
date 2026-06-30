"""
LORE Agent Module

Central orchestration agent for the NEXUS narrative intelligence system.
"""

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .lore import LORE, TurnPhase

__all__ = ["LORE", "TurnPhase"]


def __getattr__(name: str) -> Any:
    """Resolve package-level LORE exports only when callers request them."""
    if name in __all__:
        from .lore import LORE, TurnPhase

        exports = {"LORE": LORE, "TurnPhase": TurnPhase}
        globals().update(exports)
        return exports[name]
    raise AttributeError(f"module 'nexus.agents.lore' has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return discoverable package exports without importing the agent stack."""
    return sorted({*globals(), *__all__})
