"""Turn cycle plumbing tests for authorial directives."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

import pytest

from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.memory import ContextMemoryManager
from nexus.memory.context_state import ContextPackage, PassTransition


class DummyLore:
    """Minimal LORE stub for exercising turn cycle logic."""

    def __init__(self) -> None:
        self.settings: Dict[str, Any] = {"memory": {}}
        self.memnon = None
        self.memory_manager = ContextMemoryManager(self.settings)
        self.token_manager = None
        self.llm_manager = None


@pytest.fixture()
def turn_manager() -> TurnCycleManager:
    return TurnCycleManager(DummyLore())


def _stub_baseline(
    manager: ContextMemoryManager,
    narrative: str,
    warm_slice: list[Dict[str, Any]],
    token_usage: Dict[str, int],
    directives: list[str],
) -> ContextPackage:
    package = ContextPackage(
        baseline_chunks={chunk["chunk_id"] for chunk in warm_slice},
        baseline_entities={},
        baseline_themes=[],
        authorial_directives=directives,
        structured_passages=[],
        token_usage=token_usage,
    )
    transition = PassTransition(
        storyteller_output=narrative,
        expected_user_themes=[],
        assembled_context={},
        remaining_budget=token_usage.get("total_available", 0),
        authorial_directives=directives,
        structured_passages=[],
    )
    manager.context_state.store_baseline(package, transition, warm_slice)
    return package


def test_integrate_response_passes_authorial_directives(turn_manager: TurnCycleManager, monkeypatch: pytest.MonkeyPatch):
    ctx = TurnContext(
        turn_id="turn_directive",
        user_input="Test input",
        start_time=time.time(),
    )
    ctx.authorial_directives = ["Directive A", "Directive B"]
    ctx.warm_slice = [{"chunk_id": 999, "text": "Recent narrative."}]
    ctx.retrieved_passages = []
    ctx.token_counts = {"total_available": 1000, "warm_slice": 100, "structured": 0, "augmentation": 0}

    captured: Dict[str, Any] = {}

    def fake_handle_storyteller_response(**kwargs):
        captured["authorial_directives"] = kwargs.get("authorial_directives")
        return _stub_baseline(
            turn_manager.lore.memory_manager,
            kwargs.get("narrative", ""),
            ctx.warm_slice,
            kwargs.get("token_usage", {}),
            kwargs.get("authorial_directives", []),
        )

    monkeypatch.setattr(
        turn_manager.lore.memory_manager,
        "handle_storyteller_response",
        fake_handle_storyteller_response,
    )

    asyncio.run(turn_manager.integrate_response(ctx, "Story chunk text"))

    assert captured["authorial_directives"] == ctx.authorial_directives
    baseline_snapshot = ctx.memory_state["pass1"]
    assert baseline_snapshot["authorial_directives"] == ctx.authorial_directives
    assert baseline_snapshot["structured_passages"] == []
