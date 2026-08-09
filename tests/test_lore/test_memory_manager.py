"""Tests for the custom two-pass memory system that powers LORE."""

from __future__ import annotations

import copy
import logging
from typing import Dict, List

import pytest
from pydantic import ValidationError

from nexus.memory import ContextMemoryManager
from nexus.memory.context_state import Pass2BaselineV1
from nexus.memory.divergence import DivergenceResult
from nexus.memory.entity_detector import HighSpecificityEntityDetector


@pytest.fixture
def minimal_settings() -> Dict[str, object]:
    return {
        "Agent Settings": {
            "LORE": {
                "token_budget": {
                    "apex_context_window": 75_000,
                    "provider_overrides": {"local": 24_000},
                }
            }
        },
        "memory": {
            "pass2_budget_reserve": 0.25,
            "divergence_threshold": 0.4,
            "warm_slice_default": True,
            "max_sql_iterations": 3,
        },
    }


class DummyMemnon:
    """Simple stub that mimics the MEMNON retrieval surface area used in tests."""

    def __init__(self, gap_results: List[Dict[str, object]] | None = None) -> None:
        self._gap_results = gap_results or [
            {"chunk_id": 501, "text": "Data Shard logs confirm Dynacorp custody."}
        ]
        self._recent_results = [
            {"chunk_id": 610, "text": "Warm slice extension: fallout briefing."}
        ]
        self.queries: List[str] = []
        self.recent_calls: List[int] = []

    def query_memory(
        self, query: str, k: int = 5, use_hybrid: bool = True
    ) -> Dict[str, object]:
        self.queries.append(query)
        # Return a deep copy so downstream mutations don't affect subsequent checks
        return {"results": copy.deepcopy(self._gap_results)}

    def get_recent_chunks(self, limit: int = 5) -> Dict[str, object]:
        self.recent_calls.append(limit)
        return {"results": copy.deepcopy(self._recent_results)}


@pytest.fixture
def dummy_memnon() -> DummyMemnon:
    return DummyMemnon()


@pytest.fixture
def baseline_inputs() -> Dict[str, object]:
    narrative = (
        "Alex and Emilia secure the Crystal Orb inside the sealed vault while "
        "Pete monitors the perimeter."
    )
    warm_slice = [
        {"chunk_id": 101, "text": "Setup: extraction plan finalised."},
        {"chunk_id": 102, "text": "Alex briefs Emilia on the vault sequence."},
    ]
    retrieved = [{"id": 201, "text": "Intel dossier on Dynacorp vault design."}]
    token_usage = {
        "total_available": 1200,
        "warm_slice": 360,
        "structured": 180,
        "augmentation": 90,
    }
    return {
        "narrative": narrative,
        "warm_slice": warm_slice,
        "retrieved": retrieved,
        "token_usage": token_usage,
    }


@pytest.mark.parametrize(
    (
        "provider_wire_type",
        "provider_name",
        "expected_window",
        "expected_phase2_budget",
    ),
    [
        ("local", "local", 24_000, 2_400),
        ("openai", "openai", 75_000, 7_500),
        ("anthropic", "anthropic", 75_000, 7_500),
        # OpenAI-compatible remote providers share the "local" wire class but
        # have no override entry: they must keep the full frontier window.
        ("local", "openrouter", 75_000, 7_500),
    ],
)
def test_provider_override_resolves_at_memory_manager_seam(
    minimal_settings,
    caplog: pytest.LogCaptureFixture,
    provider_wire_type: str,
    provider_name: str,
    expected_window: int,
    expected_phase2_budget: int,
) -> None:
    """The turn-cycle seam resolves one provider-name budget for assembly."""
    manager = ContextMemoryManager(minimal_settings)

    with caplog.at_level(logging.DEBUG, logger="nexus.memory.manager"):
        effective_window = manager.configure_storyteller_budget(
            provider_wire_type, provider_name
        )

    assert effective_window == expected_window
    assert manager.phase2_budget == expected_phase2_budget
    override_logs = [
        record
        for record in caplog.records
        if "Storyteller payload budget override" in record.getMessage()
    ]
    assert len(override_logs) == (1 if provider_name == "local" else 0)
    if override_logs:
        assert "provider=local" in override_logs[0].getMessage()
        assert "effective=24000" in override_logs[0].getMessage()


def test_empty_provider_override_table_uses_base_budget(
    minimal_settings, caplog: pytest.LogCaptureFixture
) -> None:
    """An empty override table preserves pure base-window behavior."""
    settings = copy.deepcopy(minimal_settings)
    settings["Agent Settings"]["LORE"]["token_budget"]["provider_overrides"] = {}
    manager = ContextMemoryManager(settings)

    with caplog.at_level(logging.DEBUG, logger="nexus.memory.manager"):
        effective_window = manager.configure_storyteller_budget("local", "local")

    assert effective_window == 75_000
    assert manager.phase2_budget == 7_500
    assert "Storyteller payload budget override" not in caplog.text


def test_missing_provider_wire_type_is_programming_error(minimal_settings) -> None:
    """Budget resolution cannot silently assume a frontier provider."""
    manager = ContextMemoryManager(minimal_settings)

    with pytest.raises(RuntimeError, match="valid active provider wire class"):
        manager.configure_storyteller_budget(None, "openai")  # type: ignore[arg-type]


def test_missing_provider_name_is_programming_error(minimal_settings) -> None:
    """The override lookup key cannot be silently absent or blank."""
    manager = ContextMemoryManager(minimal_settings)

    with pytest.raises(RuntimeError, match="registry provider name"):
        manager.configure_storyteller_budget("local", None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="registry provider name"):
        manager.configure_storyteller_budget("local", "  ")


def test_explicit_base_budget_mode_configures_phase2(minimal_settings) -> None:
    """LOGON-disabled callers can deliberately select the base window."""
    manager = ContextMemoryManager(minimal_settings)

    effective_window = manager.configure_base_storyteller_budget()

    assert effective_window == 75_000
    assert manager.provider_wire_type is None
    assert manager.phase2_budget == 7_500
    assert manager._compute_available_phase2_budget({"total_available": 7_500}) == 7_500


def test_pass1_baseline_tracks_chunks_and_budget(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )

    package = manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage={
            **baseline_inputs["token_usage"],
            "using_reasoning_model": False,
        },
    )

    # Baseline chunk ids combine warm slice and retrieved passages
    assert package.baseline_chunks == {101, 102, 201}
    assert package.token_usage["baseline_tokens"] == 630
    assert package.token_usage["reserved_for_pass2"] == 300
    assert package.token_usage["reserve_shortfall"] == 0
    assert package.structured_passages == []

    transition = manager.context_state.transition
    assert transition is not None
    assert transition.remaining_budget == 1200 - 630
    # Expected themes populated from narrative analysis
    assert "Alex" in transition.expected_user_themes
    assert "Emilia" in package.baseline_entities.get("characters", [])

    exported = manager.export_pass2_baseline()
    assert exported.parent_chunk_id is None
    assert exported.memory_identities == [101, 102, 201]
    assert exported.prior_token_accounting == {
        name: value
        for name, value in package.token_usage.items()
        if name != "using_reasoning_model"
    }
    assert exported.remaining_budget == transition.remaining_budget
    dumped = exported.model_dump(mode="json")
    assert "storyteller_output" not in dumped
    assert "assembled_context" not in dumped
    assert "baseline_entities" not in dumped


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"schema_version": 2}, "Input should be 1"),
        ({"memory_identities": [True]}, "valid integer"),
        ({"memory_identities": [0]}, "must be positive"),
        ({"prior_token_accounting": {"warm_slice": -1}}, "greater than or equal"),
        ({"remaining_budget": -1}, "greater than or equal"),
    ],
)
def test_pass2_baseline_rejects_unsupported_or_invalid_state(
    update: Dict[str, object], message: str
) -> None:
    """The durable wire fails closed on versions, identities, and budgets."""

    payload: Dict[str, object] = {
        "schema_version": 1,
        "producer": "nexus.memory.context_memory_manager",
        "config_fingerprint": "0" * 64,
        "parent_chunk_id": None,
        "memory_identities": [1, "retrograde_summary:2"],
        "prior_token_accounting": {"warm_slice": 1},
        "remaining_budget": 10,
    }
    payload.update(update)
    with pytest.raises(ValidationError, match=message):
        Pass2BaselineV1.model_validate(payload)


def test_pass1_records_reserve_shortfall(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )

    tight_tokens = {
        "total_available": 1000,
        "warm_slice": 600,
        "structured": 220,
        "augmentation": 120,
    }

    package = manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=tight_tokens,
    )

    assert package.token_usage["baseline_tokens"] == 940
    assert package.token_usage["reserved_for_pass2"] == 250
    assert package.token_usage["reserve_shortfall"] == 250 - (1000 - 940)

    transition = manager.context_state.transition
    assert transition is not None
    assert transition.remaining_budget == max(0, 1000 - 940)


def test_pass2_divergence_triggers_incremental_retrieval(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    pre_budget = manager.context_state.get_remaining_budget()

    user_input = "Did we ever recover the Data Shard from Dynacorp's safehouse?"
    token_counts = {
        "total_available": 1200,
        "warm_slice": 360,
        "structured": 180,
        "augmentation": 90,
    }

    update = manager.handle_user_input(user_input, token_counts)

    assert update.baseline_available is True
    assert update.divergence.detected is False
    assert dummy_memnon.queries  # Retrieval happened
    assert update.retrieved_chunks, "Expected incremental retrieval results"
    assert manager.context_state.context is not None
    assert 501 in manager.context_state.context.additional_chunks
    post_budget = manager.context_state.get_remaining_budget()
    assert update.tokens_used > 0
    assert post_budget == max(0, pre_budget - update.tokens_used)
    assert manager.context_state.context.gap_analysis == update.divergence.gaps

    reserve = int(
        token_counts["total_available"]
        * minimal_settings["memory"]["pass2_budget_reserve"]
    )
    assert manager.context_state.context.token_usage["reserved_for_pass2"] == reserve
    assert manager.context_state.context.token_usage["reserve_shortfall"] == max(
        0, reserve - post_budget
    )


def test_pass2_preserves_entity_detection_when_character_is_in_baseline(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )
    manager.entity_detector.character_lookup = {
        "emilia": {"id": 2, "name": "Emilia", "summary": None}
    }

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    update = manager.handle_user_input("Ask Emilia about the vault.")

    assert update.divergence.detected is True
    assert update.divergence.gaps == {"character_2": "Character 'Emilia' mentioned"}
    assert update.divergence.references_seen == {"user_input"}


def test_pass2_marks_matched_entities_outside_baseline(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )
    manager.entity_detector.character_lookup = {
        "victor": {"id": 99, "name": "Victor", "summary": None}
    }

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    update = manager.handle_user_input("Ask Victor about the vault.")

    assert update.divergence.detected is True
    assert update.divergence.gaps == {"character_99": "Character 'Victor' mentioned"}


def test_entity_detector_raises_when_database_load_fails():
    class BrokenDB:
        def execute(self, _query):
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="Failed to load entities"):
        HighSpecificityEntityDetector(BrokenDB())


def test_pass1_separates_structured_passages(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )

    structured = {
        "id": "character:alex",
        "name": "Alex Navarro",
        "summary": "Lead infiltrator, tracking The Ghost",
    }
    retrieved = baseline_inputs["retrieved"] + [
        structured,
        {"chunk_id": 305, "text": "Bridge diagnostics memo."},
    ]

    package = manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=retrieved,
        token_usage=baseline_inputs["token_usage"],
    )

    assert 305 in package.baseline_chunks
    assert structured in package.structured_passages
    assert structured in manager.context_state.get_structured_passages()

    chunk_details = manager.context_state.get_all_chunks()
    chunk_ids = {chunk.get("chunk_id") for chunk in chunk_details}
    assert 305 in chunk_ids
    assert all(entry.get("chunk_id") is not None for entry in chunk_details)


def test_pass2_warm_slice_expansion_without_divergence(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    token_counts = {
        "total_available": 1200,
        "warm_slice": 360,
        "structured": 180,
        "augmentation": 90,
    }

    update = manager.handle_user_input("Continue the vault briefing.", token_counts)

    assert update.divergence.detected is False
    assert dummy_memnon.queries  # Raw input retrieval still runs
    assert not dummy_memnon.recent_calls  # Warm slice expansion no longer used in pass2
    assert update.retrieved_chunks, "Raw input retrieval should contribute chunks"
    assert update.tokens_used > 0
    assert 501 in manager.context_state.context.additional_chunks


def test_augment_warm_slice_merges_incremental_additions(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    manager._detect_divergence = lambda *args, **kwargs: DivergenceResult(
        detected=True,
        confidence=1.0,
        gaps={"Data Shard": "Reference not present"},
        unmatched_entities={"Data Shard"},
        references_seen={"Data Shard"},
    )

    manager.handle_user_input("Need the Data Shard briefing.")

    augmented = manager.augment_warm_slice(
        [
            {"chunk_id": 101, "text": "Setup: extraction plan finalised."},
        ]
    )

    chunk_ids = {chunk["chunk_id"] for chunk in augmented if "chunk_id" in chunk}
    assert {101, 501}.issubset(chunk_ids)


def test_get_memory_summary_reports_state(
    minimal_settings, dummy_memnon, baseline_inputs
):
    manager = ContextMemoryManager(
        minimal_settings,
        memnon=dummy_memnon,
        provider_wire_type="openai",
        provider_name="openai",
    )

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    manager._detect_divergence = lambda *args, **kwargs: DivergenceResult(
        detected=True,
        confidence=0.9,
        gaps={"Dynacorp": "Reference not present"},
        unmatched_entities={"Dynacorp"},
        references_seen={"Dynacorp"},
    )
    manager.handle_user_input("What did Dynacorp do with the orb?")

    summary = manager.get_memory_summary()

    assert summary["pass1"]["baseline_chunks"] == 3
    assert summary["pass1"]["token_usage"]["baseline_tokens"] == 630
    assert summary["pass1"]["structured_passages"] == []
    assert summary["pass2"]["divergence_detected"] is True
    assert summary["pass2"]["usage"]["remaining_budget"] >= 0
    assert summary["query_memory"]["history"]["pass2"], "Expected stored pass2 queries"
