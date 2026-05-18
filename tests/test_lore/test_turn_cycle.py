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


class DummyLLMManager:
    """Local LLM stub with deterministic warm analysis and query generation."""

    def __init__(self) -> None:
        self.generated_query_calls = 0

    def is_available(self) -> bool:
        return True

    def analyze_narrative_context(
        self, warm_slice: list[Dict[str, Any]], user_input: str
    ) -> Dict[str, Any]:
        return {"themes": ["testing"], "user_input": user_input}

    def generate_retrieval_queries(
        self, analysis: Dict[str, Any], user_input: str
    ) -> list[str]:
        self.generated_query_calls += 1
        return ["Local query A", "Local query B", "Local query C"]


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


def test_integrate_response_passes_generated_authorial_directives(
    turn_manager: TurnCycleManager, monkeypatch: pytest.MonkeyPatch
):
    ctx = TurnContext(
        turn_id="turn_directive",
        user_input="Test input",
        start_time=time.time(),
    )
    ctx.authorial_directives = ["Incoming directive"]
    ctx.generated_authorial_directives = [
        "Generated directive A",
        "Generated directive B",
    ]
    ctx.warm_slice = [{"chunk_id": 999, "text": "Recent narrative."}]
    ctx.retrieved_passages = []
    ctx.token_counts = {
        "total_available": 1000,
        "warm_slice": 100,
        "structured": 0,
        "augmentation": 0,
    }

    captured: Dict[str, Any] = {}

    def fake_handle_storyteller_response(**kwargs):
        captured["authorial_directives"] = kwargs.get("authorial_directives")
        captured["execute_authorial_directives"] = kwargs.get(
            "execute_authorial_directives"
        )
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

    assert captured["authorial_directives"] == ctx.generated_authorial_directives
    assert captured["execute_authorial_directives"] is False
    baseline_snapshot = ctx.memory_state["pass1"]
    assert (
        baseline_snapshot["authorial_directives"] == ctx.generated_authorial_directives
    )
    assert baseline_snapshot["structured_passages"] == []


def test_warm_analysis_loads_parent_authorial_directives(
    turn_manager: TurnCycleManager,
):
    class DummyMemnon:
        def get_chunk_by_id(self, chunk_id: int) -> Dict[str, Any]:
            return {
                "id": chunk_id,
                "text": "Parent scene.",
                "authorial_directives": [
                    "Retrieve the missing ledger and ash-boiler escape route."
                ],
            }

        def get_recent_chunks(self, limit: int) -> Dict[str, Any]:
            return {"results": []}

    turn_manager.lore.memnon = DummyMemnon()
    turn_manager.lore.llm_manager = DummyLLMManager()
    ctx = TurnContext(
        turn_id="turn_parent_directives",
        user_input="Continue.",
        start_time=time.time(),
        target_chunk_id=42,
    )

    asyncio.run(turn_manager.perform_warm_analysis(ctx))

    assert ctx.authorial_directives == [
        "Retrieve the missing ledger and ash-boiler escape route."
    ]
    assert ctx.phase_states["warm_analysis"]["authorial_directive_count"] == 1


def test_deep_queries_use_authorial_directives_before_local_llm(
    turn_manager: TurnCycleManager,
):
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
                        "text": f"Result for {query}",
                    }
                ]
            }

    memnon = DummyMemnon()
    llm_manager = DummyLLMManager()
    turn_manager.lore.memnon = memnon
    turn_manager.lore.llm_manager = llm_manager

    ctx = TurnContext(
        turn_id="turn_deep_directives",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.authorial_directives = [
        "Directive query A",
        "Directive query B",
    ]
    ctx.phase_states["warm_analysis"] = {"analysis": {"themes": ["testing"]}}

    asyncio.run(turn_manager.execute_deep_queries(ctx))

    assert memnon.queries[:2] == ["Directive query A", "Directive query B"]
    assert memnon.queries[2:] == ["Local query A", "Local query B", "Local query C"]
    assert llm_manager.generated_query_calls == 1
    assert ctx.phase_states["deep_queries"]["query_sources"] == {
        "raw_chunk": 0,
        "authorial_directive": 2,
        "llm_generated": 3,
    }


def test_deep_queries_use_raw_chunk_before_targeted_queries(
    turn_manager: TurnCycleManager,
):
    """Full chunk text should seed retrieval before narrower query paths."""

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
    llm_manager = DummyLLMManager()
    turn_manager.lore.memnon = memnon
    turn_manager.lore.llm_manager = llm_manager

    ctx = TurnContext(
        turn_id="turn_deep_raw_chunk",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.warm_slice = [
        {
            "id": 10,
            "is_target": True,
            "text": "Full parent chunk text with all the messy narrative details.",
        }
    ]
    ctx.authorial_directives = [
        "Directive query A",
        "Directive query B",
    ]
    ctx.phase_states["warm_analysis"] = {"analysis": {"themes": ["testing"]}}

    asyncio.run(turn_manager.execute_deep_queries(ctx))

    assert memnon.queries == [
        "Full parent chunk text with all the messy narrative details.",
        "Directive query A",
        "Directive query B",
        "Local query A",
        "Local query B",
    ]
    assert ctx.phase_states["deep_queries"]["query_sources"] == {
        "raw_chunk": 1,
        "authorial_directive": 2,
        "llm_generated": 2,
    }


def test_deep_queries_obey_configured_query_budget(
    turn_manager: TurnCycleManager,
):
    """The deep-query budget should come from LORE retrieval settings."""

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
                        "text": f"Result for {query}",
                    }
                ]
            }

    memnon = DummyMemnon()
    llm_manager = DummyLLMManager()
    turn_manager.lore.memnon = memnon
    turn_manager.lore.llm_manager = llm_manager
    turn_manager.lore.settings["lore"] = {"retrieval": {"max_deep_queries": 3}}

    ctx = TurnContext(
        turn_id="turn_deep_budget",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.authorial_directives = [
        "Directive query A",
        "Directive query B",
    ]
    ctx.phase_states["warm_analysis"] = {"analysis": {"themes": ["testing"]}}

    asyncio.run(turn_manager.execute_deep_queries(ctx))

    assert memnon.queries == [
        "Directive query A",
        "Directive query B",
        "Local query A",
    ]
    assert ctx.phase_states["deep_queries"]["query_sources"] == {
        "raw_chunk": 0,
        "authorial_directive": 2,
        "llm_generated": 1,
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
            authorial_directives=[],
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
