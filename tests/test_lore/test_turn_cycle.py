"""Turn cycle plumbing tests for directive-free retrieval."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict

import pytest

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.token_budget import TokenBudgetManager
from nexus.config import load_settings_as_dict
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


@pytest.mark.parametrize(
    ("apex_model", "provider_wire_type", "expected_window"),
    [
        ("nousresearch/hermes-4-70b", "local", 24_000),
        (None, "openai", 75_000),
        ("claude-opus-4-8", "anthropic", 75_000),
    ],
)
def test_process_user_input_uses_provider_profile_budget(
    apex_model: str | None, provider_wire_type: str, expected_window: int
) -> None:
    """The real turn-cycle seam feeds one resolved window to both managers."""

    class BudgetLore:
        def __init__(self) -> None:
            self.settings = load_settings_as_dict()
            self.apex_model = (
                apex_model
                if apex_model is not None
                else self.settings["API Settings"]["apex"]["model"]
            )
            self.memnon = None
            self.memory_manager = ContextMemoryManager(self.settings)
            self.token_manager = TokenBudgetManager(self.settings)
            self.logon = self
            self.enable_logon = True

        def ensure_logon(self) -> None:
            return None

        def resolve_storyteller_route(self) -> tuple[str, str]:
            return self.apex_model, provider_wire_type

    lore = BudgetLore()
    manager = TurnCycleManager(lore)
    ctx = TurnContext(
        turn_id=f"provider-profile-{provider_wire_type}",
        user_input="Continue.",
        start_time=time.time(),
    )

    asyncio.run(manager.process_user_input(ctx))

    assert ctx.apex_model == lore.apex_model
    assert ctx.provider_wire_type == provider_wire_type
    assert ctx.token_counts["apex_window"] == expected_window
    assert lore.memory_manager.phase2_budget == expected_window // 10
    if apex_model is None:
        assert ctx.token_counts["reasoning_reserve"] == 30_000


def test_process_user_input_uses_base_budget_when_logon_is_disabled() -> None:
    """LOGON-disabled analysis uses an explicit base-window mode."""

    class DisabledLore:
        def __init__(self) -> None:
            self.settings = load_settings_as_dict()
            self.memnon = None
            self.memory_manager = ContextMemoryManager(self.settings)
            self.token_manager = TokenBudgetManager(self.settings)
            self.logon = None
            self.enable_logon = False

        def ensure_logon(self) -> None:
            raise AssertionError("LOGON-disabled turns must not resolve a route")

    lore = DisabledLore()
    manager = TurnCycleManager(lore)
    ctx = TurnContext(
        turn_id="logon-disabled-base-budget",
        user_input="Continue.",
        start_time=time.time(),
    )

    asyncio.run(manager.process_user_input(ctx))

    assert ctx.apex_model is None
    assert ctx.provider_wire_type is None
    assert ctx.token_counts["apex_window"] == 75_000
    assert ctx.token_counts["reasoning_reserve"] == 30_000
    assert lore.memory_manager.phase2_budget == 7_500


def test_slot_model_change_mid_turn_aborts_before_provider_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 6 must reject a route that differs from Phase 1's snapshot."""

    class RouteLore:
        def __init__(self) -> None:
            self.settings = load_settings_as_dict()
            self.memnon = None
            self.memory_manager = ContextMemoryManager(self.settings)
            self.token_manager = TokenBudgetManager(self.settings)
            self.enable_logon = True
            self.logon = LogonUtility(self.settings)

        def ensure_logon(self) -> None:
            return None

    lore = RouteLore()
    manager = TurnCycleManager(lore)
    ctx = TurnContext(
        turn_id="slot-change",
        user_input="Continue.",
        start_time=time.time(),
    )
    route_calls = {"count": 0}

    def resolve_route() -> tuple[str, str, None, str]:
        route_calls["count"] += 1
        if route_calls["count"] == 1:
            return ("gpt-5.5", "openai", None, "openai")
        return ("nousresearch/hermes-4-70b", "openai", None, "local")

    monkeypatch.setattr(lore.logon, "_resolve_storyteller_route", resolve_route)

    asyncio.run(manager.process_user_input(ctx))
    ctx.context_payload = {"user_input": ctx.user_input}

    with pytest.raises(
        RuntimeError, match="slot model changed mid-turn; aborting the turn"
    ):
        asyncio.run(manager.call_apex_ai(ctx))

    assert route_calls["count"] == 2
    assert lore.logon.provider is None


def test_local_payload_trims_oldest_warm_chunks_and_keeps_parent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The real Phase 5 seam bounds a local payload without dropping its parent."""

    class LocalLore:
        def __init__(self) -> None:
            self.settings = load_settings_as_dict()
            self.settings["orrery"]["enabled"] = False
            self.memnon = None
            self.memory_manager = ContextMemoryManager(self.settings)
            self.token_manager = TokenBudgetManager(self.settings)
            self.logon = self
            self.enable_logon = True

        def ensure_logon(self) -> None:
            return None

        def resolve_storyteller_route(self) -> tuple[str, str]:
            return "nousresearch/hermes-4-70b", "local"

    lore = LocalLore()
    turn_manager = TurnCycleManager(lore)
    ctx = TurnContext(
        turn_id="local-payload-trim",
        user_input="Continue.",
        start_time=time.time(),
    )
    asyncio.run(turn_manager.process_user_input(ctx))
    ctx.warm_slice = [
        {"chunk_id": 1, "text": "oldest " * 10_000},
        {"chunk_id": 2, "text": "middle " * 10_000},
        {"chunk_id": 3, "text": "parent " * 2_000, "is_target": True},
    ]

    with caplog.at_level(logging.INFO, logger="nexus.lore.turn_cycle"):
        asyncio.run(turn_manager.assemble_context_payload(ctx))

    assembled_chunks = ctx.context_payload["warm_slice"]["chunks"]
    assembled_ids = [chunk["chunk_id"] for chunk in assembled_chunks]
    phase_state = ctx.phase_states["payload_assembly"]
    trim_logs = [
        record
        for record in caplog.records
        if "Storyteller payload trimmed" in record.getMessage()
    ]

    assert phase_state["total_tokens_used"] <= ctx.token_counts["total_available"]
    assert ctx.token_counts["apex_window"] == 24_000
    assert 1 not in assembled_ids
    assert assembled_ids[-1] == 3
    assert len(ctx.warm_slice) == 3
    assert len(trim_logs) == 1
    assert "wire_class=local" in trim_logs[0].getMessage()
    assert "warm_chunks_dropped=1" in trim_logs[0].getMessage()


def test_frontier_payload_below_ceiling_is_unchanged(
    turn_manager: TurnCycleManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Typical frontier assembly remains byte-for-byte equivalent in content."""
    ctx = TurnContext(
        turn_id="frontier-payload",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.provider_wire_type = "openai"
    ctx.warm_slice = [{"chunk_id": 10, "text": "Recent narrative.", "is_target": True}]
    ctx.entity_data = {"characters": [{"name": "Mara", "summary": "Alert."}]}
    ctx.retrieved_passages = [{"chunk_id": 2, "text": "Earlier context."}]
    ctx.memory_state = {"pass2": {"detected": False}}
    ctx.token_counts = {
        "total_available": 36_000,
        "warm_slice": 1_800,
        "structured": 3_600,
        "augmentation": 1_800,
    }

    with caplog.at_level(logging.INFO, logger="nexus.lore.turn_cycle"):
        asyncio.run(turn_manager.assemble_context_payload(ctx))

    timestamp = ctx.context_payload["metadata"]["timestamp"]
    expected_payload = {
        "user_input": "Continue.",
        "warm_slice": {"chunks": ctx.warm_slice, "token_count": 1_800},
        "entity_data": ctx.entity_data,
        "retrieved_passages": {
            "results": ctx.retrieved_passages,
            "token_count": 1_800,
        },
        "metadata": {"turn_id": "frontier-payload", "timestamp": timestamp},
        "memory_state": ctx.memory_state,
    }

    assembled_bytes = json.dumps(
        ctx.context_payload, ensure_ascii=False, separators=(",", ":")
    ).encode()
    expected_bytes = json.dumps(
        expected_payload, ensure_ascii=False, separators=(",", ":")
    ).encode()

    assert assembled_bytes == expected_bytes
    assert ctx.context_payload["warm_slice"]["chunks"] is ctx.warm_slice
    assert (
        ctx.context_payload["retrieved_passages"]["results"] is ctx.retrieved_passages
    )
    assert "Storyteller payload trimmed" not in caplog.text


def test_payload_trims_retrieved_passages_last_first(
    turn_manager: TurnCycleManager,
) -> None:
    """After warm trimming is exhausted, lowest-ranked retrievals go first."""
    ctx = TurnContext(
        turn_id="retrieval-trim",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.provider_wire_type = "local"
    ctx.warm_slice = [{"chunk_id": 3, "text": "parent " * 600, "is_target": True}]
    ctx.retrieved_passages = [
        {"chunk_id": 1, "text": "first " * 250},
        {"chunk_id": 2, "text": "last " * 250},
    ]
    ctx.token_counts = {
        "total_available": 1_000,
        "warm_slice": 600,
        "structured": 100,
        "augmentation": 300,
    }

    asyncio.run(turn_manager.assemble_context_payload(ctx))

    assert ctx.context_payload["retrieved_passages"]["results"] == [
        ctx.retrieved_passages[0]
    ]
    assert ctx.phase_states["payload_assembly"]["warm_chunks_dropped"] == 0
    assert ctx.phase_states["payload_assembly"]["retrieved_passages_dropped"] == 1


def test_structured_payload_overflow_raises(
    turn_manager: TurnCycleManager,
) -> None:
    """A structured core that cannot fit is a loud configuration error."""
    ctx = TurnContext(
        turn_id="structured-overflow",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.provider_wire_type = "local"
    ctx.warm_slice = [{"chunk_id": 3, "text": "Parent.", "is_target": True}]
    ctx.entity_data = {"characters": [{"summary": "structured " * 1_500}]}
    ctx.token_counts = {
        "total_available": 1_000,
        "warm_slice": 100,
        "structured": 800,
        "augmentation": 0,
    }

    with pytest.raises(ValueError, match="structured core is a configuration error"):
        asyncio.run(turn_manager.assemble_context_payload(ctx))


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
