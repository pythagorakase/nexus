"""Turn cycle plumbing tests for directive-free retrieval."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict

import pytest

from nexus.agents.lore.utils import turn_cycle as turn_cycle_module
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
        self.settings: Dict[str, Any] = {
            "Agent Settings": {
                "LORE": {
                    "token_budget": {
                        "apex_context_window": 75_000,
                        "prompt_overhead_tokens": 0,
                    }
                },
                "MEMNON": {
                    "retrieval": {"hybrid_search": {"presence_boost_enabled": False}}
                },
            },
            "memory": {},
        }
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
    ("apex_model", "provider_wire_type", "provider_name", "expected_window"),
    [
        ("nousresearch/hermes-4-70b", "local", "local", 32_000),
        (None, "openai", "openai", 75_000),
        ("claude-opus-4-8", "anthropic", "anthropic", 75_000),
        # Remote OpenAI-compatible providers share the local wire class but
        # keep the full frontier window (no provider_overrides entry).
        ("moonshotai/kimi-k2.5", "local", "openrouter", 75_000),
    ],
)
def test_process_user_input_uses_provider_profile_budget(
    apex_model: str | None,
    provider_wire_type: str,
    provider_name: str,
    expected_window: int,
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

        def resolve_storyteller_route(self) -> tuple[str, str, str]:
            return self.apex_model, provider_wire_type, provider_name

    lore = BudgetLore()
    manager = TurnCycleManager(lore)
    ctx = TurnContext(
        turn_id=f"provider-profile-{provider_name}",
        user_input="Continue.",
        start_time=time.time(),
    )

    asyncio.run(manager.process_user_input(ctx))

    assert ctx.apex_model == lore.apex_model
    assert ctx.provider_wire_type == provider_wire_type
    assert ctx.provider_name == provider_name
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


@pytest.mark.parametrize(
    (
        "enable_logon",
        "provider_wire_type",
        "expected_lookback",
        "expected_characters",
        "expected_locations",
        "expect_relationship_query",
    ),
    [
        (True, "local", 12, 12, 6, False),
        (False, None, 20, 25, 10, True),
    ],
)
def test_query_entity_states_passes_resolved_limits_to_fetch_boundary(
    monkeypatch: pytest.MonkeyPatch,
    enable_logon: bool,
    provider_wire_type: str | None,
    expected_lookback: int,
    expected_characters: int,
    expected_locations: int,
    expect_relationship_query: bool,
) -> None:
    """The real gather seam passes provider-resolved limits to DB fetches."""
    captured: Dict[str, Any] = {}
    statements: list[str] = []

    class EmptySession:
        def __enter__(self) -> "EmptySession":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def execute(
            self, statement: Any, parameters: Dict[str, Any] | None = None
        ) -> list[Any]:
            statements.append(str(statement))
            return []

    class EntityMemnon:
        Session = EmptySession

    class EntityLore:
        def __init__(self) -> None:
            self.settings = load_settings_as_dict()
            self.memnon = EntityMemnon()
            self.enable_logon = enable_logon

    def fake_characters(
        session: Any,
        featured_chunk_ids: list[int],
        *,
        max_featured_characters: int,
    ) -> Dict[str, list[Dict[str, Any]]]:
        captured["characters"] = (
            list(featured_chunk_ids),
            max_featured_characters,
        )
        return {
            "baseline": [],
            "featured": [
                {"id": 1, "current_location": 9_001},
                {"id": 2, "current_location": "Named Haven"},
            ],
        }

    def fake_place_ids_by_names(
        session: Any,
        place_names: set[str],
    ) -> set[int]:
        captured["place_names"] = set(place_names)
        return {9_002}

    def fake_places(
        session: Any,
        featured_chunk_ids: list[int],
        featured_place_ids: set[int],
        *,
        max_featured_places: int,
    ) -> Dict[str, list[Dict[str, Any]]]:
        captured["places"] = (
            list(featured_chunk_ids),
            set(featured_place_ids),
            max_featured_places,
        )
        warm_reference_ids = list(range(1_000, 1_000 + max_featured_places + 2))
        featured_ids = [
            *warm_reference_ids[:max_featured_places],
            *sorted(featured_place_ids),
        ]
        return {
            "baseline": [],
            "featured": [{"id": place_id} for place_id in featured_ids],
        }

    def fake_factions(
        session: Any,
        featured_chunk_ids: list[int],
    ) -> Dict[str, list[Dict[str, Any]]]:
        captured["factions"] = list(featured_chunk_ids)
        return {"baseline": [], "featured": []}

    monkeypatch.setattr(
        turn_cycle_module,
        "fetch_all_characters_with_references",
        fake_characters,
    )
    monkeypatch.setattr(
        turn_cycle_module,
        "fetch_all_places_with_references",
        fake_places,
    )
    monkeypatch.setattr(
        turn_cycle_module,
        "fetch_place_ids_by_names",
        fake_place_ids_by_names,
    )
    monkeypatch.setattr(
        turn_cycle_module,
        "fetch_all_factions_with_references",
        fake_factions,
    )

    manager = TurnCycleManager(EntityLore())
    ctx = TurnContext(
        turn_id="entity-provider-limits",
        user_input="Continue.",
        start_time=time.time(),
        provider_wire_type=provider_wire_type,
        provider_name=provider_wire_type,
        warm_slice=[
            {"chunk_id": chunk_id, "text": f"Chunk {chunk_id}."}
            for chunk_id in range(30, 5, -1)
        ],
    )

    asyncio.run(manager.query_entity_states(ctx))

    expected_chunk_ids = list(range(30, 30 - expected_lookback, -1))
    assert captured["characters"] == (expected_chunk_ids, expected_characters)
    assert captured["place_names"] == {"Named Haven"}
    assert captured["places"] == (
        expected_chunk_ids,
        {9_001, 9_002},
        expected_locations,
    )
    featured_location_ids = {
        place["id"] for place in ctx.entity_data["locations"]["featured"]
    }
    assert featured_location_ids == {
        *range(1_000, 1_000 + expected_locations),
        9_001,
        9_002,
    }
    assert captured["factions"] == expected_chunk_ids
    relationship_queried = any(
        "character_relationships" in statement for statement in statements
    )
    assert relationship_queried is expect_relationship_query


def test_query_entity_states_requires_wire_class_when_logon_is_active() -> None:
    """A missing Phase 1 route cannot silently fall back to base entity limits."""

    class EntityLore:
        def __init__(self) -> None:
            self.settings = load_settings_as_dict()
            self.memnon = object()
            self.enable_logon = True

    manager = TurnCycleManager(EntityLore())
    ctx = TurnContext(
        turn_id="entity-missing-wire-class",
        user_input="Continue.",
        start_time=time.time(),
        warm_slice=[{"chunk_id": 1, "text": "Parent."}],
    )

    with pytest.raises(RuntimeError, match="require.*wire class and provider name"):
        asyncio.run(manager.query_entity_states(ctx))


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

        def resolve_storyteller_route(self) -> tuple[str, str, str]:
            return "nousresearch/hermes-4-70b", "local", "local"

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
        {"chunk_id": 2, "text": "middle " * 7_000},
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

    assert phase_state["total_tokens_used"] <= phase_state["payload_ceiling"]
    assert ctx.token_counts["apex_window"] == 32_000
    assert phase_state["prompt_overhead_tokens"] == 4_000
    assert phase_state["payload_ceiling"] == (
        ctx.token_counts["total_available"] - 4_000
    )
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
    ctx.provider_name = "openai"
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
    """The overhead-reduced ceiling drops lowest-ranked retrievals first."""
    turn_manager.settings["Agent Settings"]["LORE"]["token_budget"][
        "prompt_overhead_tokens"
    ] = 400
    ctx = TurnContext(
        turn_id="retrieval-trim",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.provider_wire_type = "local"
    ctx.provider_name = "local"
    ctx.warm_slice = [{"chunk_id": 3, "text": "parent " * 600, "is_target": True}]
    ctx.retrieved_passages = [
        {"chunk_id": 1, "text": "first " * 250},
        {"chunk_id": 2, "text": "last " * 250},
    ]
    ctx.token_counts = {
        "total_available": 1_400,
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
    assert ctx.phase_states["payload_assembly"]["payload_ceiling"] == 1_000
    assert ctx.phase_states["payload_assembly"]["tokens_before_trimming"] <= 1_400
    assert ctx.phase_states["payload_assembly"]["tokens_before_trimming"] > 1_000


def test_trimmed_pass2_chunk_is_unregistered_refunded_and_retrievable() -> None:
    """Phase 5 reverses Pass-2 registration so a dropped chunk can resurface."""

    class RetrievalMemnon:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def query_memory(
            self, query: str, k: int = 5, use_hybrid: bool = True
        ) -> Dict[str, Any]:
            self.queries.append(query)
            return {
                "results": [
                    {
                        "chunk_id": 501,
                        "text": "retrieved " * 600,
                    }
                ]
            }

    class RetrievalLore:
        def __init__(self) -> None:
            self.settings = load_settings_as_dict()
            self.settings["orrery"]["enabled"] = False
            self.settings["Agent Settings"]["LORE"]["token_budget"][
                "prompt_overhead_tokens"
            ] = 500
            self.memnon = RetrievalMemnon()
            self.memory_manager = ContextMemoryManager(
                self.settings,
                memnon=self.memnon,
                provider_wire_type="openai",
                provider_name="openai",
            )
            self.token_manager = None

    lore = RetrievalLore()
    manager = TurnCycleManager(lore)
    parent = {"chunk_id": 100, "text": "Parent.", "is_target": True}
    lore.memory_manager.handle_storyteller_response(
        narrative="Prior storyteller response.",
        warm_slice=[parent],
        retrieved_passages=[],
        token_usage={
            "total_available": 2_000,
            "warm_slice": 100,
            "structured": 0,
            "augmentation": 0,
        },
    )
    initial_budget = lore.memory_manager.context_state.get_remaining_budget()

    first_turn = TurnContext(
        turn_id="pass2-first",
        user_input="Find the first missing memory.",
        start_time=time.time(),
    )
    asyncio.run(manager.process_user_input(first_turn))
    first_cost = first_turn.memory_state["pass2"]["tokens_used"]
    assert first_turn.memory_state["pass2"]["retrieved_chunk_ids"] == [501]
    assert lore.memory_manager.context_state.is_chunk_known(501)
    assert lore.memory_manager.context_state.get_remaining_budget() == (
        initial_budget - first_cost
    )

    first_turn.provider_wire_type = "openai"
    first_turn.provider_name = "openai"
    first_turn.warm_slice = lore.memory_manager.augment_warm_slice([parent])
    first_turn.token_counts = {
        "total_available": 1_000,
        "warm_slice": 100,
        "structured": 0,
        "augmentation": 0,
    }
    asyncio.run(manager.assemble_context_payload(first_turn))

    assert [
        chunk["chunk_id"]
        for chunk in first_turn.context_payload["warm_slice"]["chunks"]
    ] == [100]
    assert not lore.memory_manager.context_state.is_chunk_known(501)
    assert lore.memory_manager.context_state.get_remaining_budget() == initial_budget
    assert first_turn.memory_state["pass2"]["retrieved_chunk_ids"] == []
    assert first_turn.memory_state["pass2"]["tokens_used"] == 0
    assert (
        first_turn.phase_states["payload_assembly"]["memory_budget_refunded"]
        == first_cost
    )

    asyncio.run(manager.integrate_response(first_turn, "New storyteller response."))
    assert 501 not in lore.memory_manager.context_state.context.baseline_chunks
    next_turn_budget = lore.memory_manager.context_state.get_remaining_budget()

    second_turn = TurnContext(
        turn_id="pass2-second",
        user_input="Find that missing memory again.",
        start_time=time.time(),
    )
    asyncio.run(manager.process_user_input(second_turn))

    assert second_turn.memory_state["pass2"]["retrieved_chunk_ids"] == [501]
    assert lore.memory_manager.context_state.is_chunk_known(501)
    assert lore.memory_manager.context_state.get_remaining_budget() == (
        next_turn_budget - second_turn.memory_state["pass2"]["tokens_used"]
    )
    assert lore.memnon.queries == [
        "Find the first missing memory.",
        "Find that missing memory again.",
    ]


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
    ctx.provider_name = "local"
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
    ctx.context_payload = {
        "warm_slice": {"chunks": ctx.warm_slice},
        "retrieved_passages": {"results": ctx.retrieved_passages},
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


@pytest.mark.parametrize("presence_boost_enabled", [False, True])
def test_turn_phases_gate_and_thread_produced_presence_roster(
    monkeypatch: pytest.MonkeyPatch,
    presence_boost_enabled: bool,
) -> None:
    """The real entity phase produces the exact roster only for the enabled arm."""

    roster_query_count = 0

    class Row:
        def __init__(self, character_id: int) -> None:
            self.character_id = character_id

    class Result:
        def __init__(self, rows: list[Any] | None = None) -> None:
            self.rows = rows or []

        def fetchall(self) -> list[Any]:
            return self.rows

        def fetchone(self) -> Any | None:
            return self.rows[0] if self.rows else None

        def __iter__(self):
            return iter(self.rows)

    class ProductionSession:
        def __enter__(self) -> "ProductionSession":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(
            self, statement: Any, parameters: Dict[str, Any] | None = None
        ) -> Result:
            nonlocal roster_query_count
            sql = " ".join(str(statement).split())
            if (
                "SELECT character_id FROM chunk_character_references" in sql
                and "reference::text = 'present'" in sql
            ):
                if not presence_boost_enabled:
                    raise AssertionError("disabled arm executed the roster query")
                assert parameters == {"chunk_id": 42}
                roster_query_count += 1
                return Result([Row(9), Row(3)])
            return Result()

    class DummyMemnon:
        def __init__(self) -> None:
            self.threaded_present_ids: list[int] | None = None

        Session = ProductionSession

        def query_memory(
            self,
            query: str,
            k: int,
            use_hybrid: bool,
            **kwargs: Any,
        ) -> Dict[str, list[Dict[str, Any]]]:
            present_ids = kwargs.get("present_character_ids")
            self.threaded_present_ids = (
                list(present_ids) if present_ids is not None else None
            )
            return {"results": []}

    class PresenceLore:
        def __init__(self) -> None:
            self.settings = load_settings_as_dict()
            self.settings["Agent Settings"]["MEMNON"]["retrieval"]["hybrid_search"][
                "presence_boost_enabled"
            ] = presence_boost_enabled
            self.memnon = DummyMemnon()
            self.memory_manager = None
            self.token_manager = None
            self.enable_logon = True

    monkeypatch.setattr(
        turn_cycle_module,
        "fetch_all_characters_with_references",
        lambda *_args, **_kwargs: {"baseline": [], "featured": []},
    )
    monkeypatch.setattr(
        turn_cycle_module,
        "fetch_all_places_with_references",
        lambda *_args, **_kwargs: {"baseline": [], "featured": []},
    )
    monkeypatch.setattr(
        turn_cycle_module,
        "fetch_all_factions_with_references",
        lambda *_args, **_kwargs: {"baseline": [], "featured": []},
    )

    lore = PresenceLore()
    manager = TurnCycleManager(lore)
    ctx = TurnContext(
        turn_id="turn_presence_retrieval",
        user_input="Continue.",
        start_time=time.time(),
        target_chunk_id=42,
        provider_wire_type="local",
        provider_name="local",
        warm_slice=[
            {
                "chunk_id": 42,
                "is_target": True,
                "full_text": "Who is standing beside the protagonist?",
            }
        ],
    )

    asyncio.run(manager.query_entity_states(ctx))
    asyncio.run(manager.execute_deep_queries(ctx))

    if presence_boost_enabled:
        assert roster_query_count == 1
        assert ctx.present_character_ids == [3, 9]
        assert lore.memnon.threaded_present_ids == [3, 9]
    else:
        assert roster_query_count == 0
        assert ctx.present_character_ids == []
        assert lore.memnon.threaded_present_ids is None


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
    ctx.context_payload = {
        "warm_slice": {"chunks": ctx.warm_slice},
        "retrieved_passages": {"results": ctx.retrieved_passages},
    }

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


def test_payload_token_count_stringifies_database_values() -> None:
    """DB-sourced datetimes and Decimals must count, not crash enforcement."""
    from datetime import datetime
    from decimal import Decimal

    from nexus.agents.lore.utils.turn_cycle import _context_component_token_count

    payload = {
        "user_input": "ignored",
        "entity_data": {
            "world_time": datetime(2042, 8, 18, 8, 54),
            "valence": Decimal("0.25"),
        },
        "warm_slice": {"chunks": []},
        "retrieved_passages": {"results": []},
    }

    assert _context_component_token_count(payload) > 0
