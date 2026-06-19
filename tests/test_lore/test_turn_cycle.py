"""Turn cycle plumbing tests for directive-free retrieval."""

from __future__ import annotations

import asyncio
import logging
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


@pytest.fixture()
def turn_manager() -> TurnCycleManager:
    return TurnCycleManager(DummyLore())


def _stub_baseline(
    manager: ContextMemoryManager,
    narrative: str,
    warm_slice: list[Dict[str, Any]],
    token_usage: Dict[str, int],
) -> ContextPackage:
    package = ContextPackage(
        baseline_chunks={chunk["chunk_id"] for chunk in warm_slice},
        baseline_entities={},
        baseline_themes=[],
        structured_passages=[],
        token_usage=token_usage,
    )
    transition = PassTransition(
        storyteller_output=narrative,
        expected_user_themes=[],
        assembled_context={},
        remaining_budget=token_usage.get("total_available", 0),
        structured_passages=[],
    )
    manager.context_state.store_baseline(package, transition, warm_slice)
    return package


def test_integrate_response_does_not_pass_authorial_directives(
    turn_manager: TurnCycleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = TurnContext(
        turn_id="turn_no_directives",
        user_input="Test input",
        start_time=time.time(),
    )
    ctx.warm_slice = [{"chunk_id": 999, "text": "Recent narrative."}]
    ctx.retrieved_passages = []
    ctx.token_counts = {
        "total_available": 1000,
        "warm_slice": 100,
        "structured": 0,
        "augmentation": 0,
    }

    captured: Dict[str, Any] = {}

    def fake_handle_storyteller_response(**kwargs: Any) -> ContextPackage:
        captured.update(kwargs)
        return _stub_baseline(
            turn_manager.lore.memory_manager,
            kwargs.get("narrative", ""),
            ctx.warm_slice,
            kwargs.get("token_usage", {}),
        )

    monkeypatch.setattr(
        turn_manager.lore.memory_manager,
        "handle_storyteller_response",
        fake_handle_storyteller_response,
    )

    asyncio.run(turn_manager.integrate_response(ctx, "Story chunk text"))

    assert "authorial_directives" not in captured
    assert "execute_authorial_directives" not in captured
    baseline_snapshot = ctx.memory_state["pass1"]
    assert "authorial_directives" not in baseline_snapshot
    assert baseline_snapshot["structured_passages"] == []


def test_warm_analysis_ignores_parent_authorial_directives(
    turn_manager: TurnCycleManager,
) -> None:
    class DummyMemnon:
        def get_chunk_by_id(self, chunk_id: int) -> Dict[str, Any]:
            return {
                "id": chunk_id,
                "text": "Parent scene.",
                "authorial_directives": ["Legacy directive should be ignored."],
            }

        def get_recent_chunks(self, limit: int) -> Dict[str, Any]:
            return {"results": []}

    turn_manager.lore.memnon = DummyMemnon()
    ctx = TurnContext(
        turn_id="turn_parent_no_directives",
        user_input="Continue.",
        start_time=time.time(),
        target_chunk_id=42,
    )

    asyncio.run(turn_manager.perform_warm_analysis(ctx))

    assert ctx.phase_states["warm_analysis"]["analysis"]["source"] == (
        "programmatic_warm_slice"
    )
    assert "authorial_directive_count" not in ctx.phase_states["warm_analysis"]
    assert (
        "authorial_directive_count" not in ctx.phase_states["warm_analysis"]["analysis"]
    )


def test_deep_queries_use_raw_chunk_only(turn_manager: TurnCycleManager) -> None:
    """Full chunk text should seed retrieval without successor directives."""

    class DummyMemnon:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def query_memory(
            self, query: str, k: int, use_hybrid: bool
        ) -> Dict[str, list[Dict[str, Any]]]:
            self.queries.append(query)
            return {
                "results": [
                    {
                        "id": len(self.queries),
                        "score": 1.0,
                        "text": f"Result for {query[:20]}",
                    }
                ]
            }

    memnon = DummyMemnon()
    turn_manager.lore.memnon = memnon

    ctx = TurnContext(
        turn_id="turn_deep_raw_chunk",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.warm_slice = [
        {
            "id": 10,
            "is_target": True,
            "full_text": "Full parent chunk text with all the messy narrative details.",
        }
    ]
    ctx.phase_states["warm_analysis"] = {"analysis": {"themes": ["testing"]}}

    asyncio.run(turn_manager.execute_deep_queries(ctx))

    assert memnon.queries == [
        "Full parent chunk text with all the messy narrative details."
    ]
    assert ctx.phase_states["deep_queries"]["query_sources"] == {
        "raw_chunk": 1,
        "llm_generated": 0,
    }


def test_deep_queries_can_skip_without_raw_text(
    turn_manager: TurnCycleManager,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Missing raw text should skip retrieval."""

    class DummyMemnon:
        def query_memory(
            self, query: str, k: int, use_hybrid: bool
        ) -> Dict[str, list[Dict[str, Any]]]:
            raise AssertionError("query_memory should not be called")

    turn_manager.lore.memnon = DummyMemnon()

    ctx = TurnContext(
        turn_id="turn_deep_no_queries",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.phase_states["warm_analysis"] = {
        "analysis": {"source": "programmatic_warm_slice"}
    }

    with caplog.at_level(logging.WARNING, logger="nexus.lore.turn_cycle"):
        asyncio.run(turn_manager.execute_deep_queries(ctx))

    assert ctx.retrieved_passages == []
    assert "No raw chunk text available for deep queries" in caplog.text
    assert ctx.phase_states["deep_queries"]["query_sources"] == {
        "raw_chunk": 0,
        "llm_generated": 0,
    }


def test_integrate_response_sorts_mixed_chunk_id_payloads(
    turn_manager: TurnCycleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass 1 snapshots should tolerate older string chunk IDs."""
    ctx = TurnContext(
        turn_id="turn_mixed_ids",
        user_input="Test input",
        start_time=time.time(),
    )
    ctx.warm_slice = []
    ctx.retrieved_passages = []
    ctx.token_counts = {"total_available": 1000}

    def fake_handle_storyteller_response(**kwargs: Any) -> ContextPackage:
        package = ContextPackage(
            baseline_chunks={3, "2", 1},
            baseline_entities={},
            baseline_themes=[],
            structured_passages=[],
            token_usage=kwargs.get("token_usage", {}),
        )
        transition = PassTransition(
            storyteller_output=kwargs.get("narrative", ""),
            remaining_budget=1000,
        )
        turn_manager.lore.memory_manager.context_state.store_baseline(
            package, transition
        )
        return package

    monkeypatch.setattr(
        turn_manager.lore.memory_manager,
        "handle_storyteller_response",
        fake_handle_storyteller_response,
    )

    asyncio.run(turn_manager.integrate_response(ctx, "Story chunk text"))

    assert ctx.memory_state["pass1"]["baseline_chunks"] == [1, "2", 3]
