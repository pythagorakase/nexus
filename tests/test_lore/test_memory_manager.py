"""Tests for the custom two-pass memory system that powers LORE."""

from __future__ import annotations

import copy
from typing import Dict, List

import pytest

from nexus.memory import ContextMemoryManager
from nexus.memory.divergence import DivergenceResult


@pytest.fixture
def minimal_settings() -> Dict[str, object]:
    return {
        "memory": {
            "pass2_budget_reserve": 0.25,
            "divergence_threshold": 0.4,
            "warm_slice_default": True,
            "max_sql_iterations": 3,
        }
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

    def query_memory(self, query: str, k: int = 5, use_hybrid: bool = True) -> Dict[str, object]:
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
        "Alex and Emilia secure the Crystal Orb inside the sealed vault while Pete monitors the perimeter."
    )
    warm_slice = [
        {"chunk_id": 101, "text": "Setup: extraction plan finalised."},
        {"chunk_id": 102, "text": "Alex briefs Emilia on the vault sequence."},
    ]
    retrieved = [
        {"id": 201, "text": "Intel dossier on Dynacorp vault design."}
    ]
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


def test_pass1_baseline_tracks_chunks_and_budget(minimal_settings, dummy_memnon, baseline_inputs):
    manager = ContextMemoryManager(minimal_settings, memnon=dummy_memnon)

    package = manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    # Baseline chunk ids combine warm slice and retrieved passages
    assert package.baseline_chunks == {101, 102, 201}
    assert package.token_usage["baseline_tokens"] == 630
    assert package.token_usage["reserved_for_pass2"] == 300
    assert package.token_usage["reserve_shortfall"] == 0
    assert package.authorial_directives == []
    assert package.structured_passages == []

    transition = manager.context_state.transition
    assert transition is not None
    assert transition.remaining_budget == 1200 - 630
    # Expected themes populated from narrative analysis
    assert "Alex" in transition.expected_user_themes
    assert "Emilia" in package.baseline_entities.get("characters", [])


def test_pass1_records_reserve_shortfall(minimal_settings, dummy_memnon, baseline_inputs):
    manager = ContextMemoryManager(minimal_settings, memnon=dummy_memnon)

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


def test_pass2_divergence_triggers_incremental_retrieval(minimal_settings, dummy_memnon, baseline_inputs):
    manager = ContextMemoryManager(minimal_settings, memnon=dummy_memnon)

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
    assert update.divergence.detected is True
    assert dummy_memnon.queries  # Retrieval happened
    assert update.retrieved_chunks, "Expected incremental retrieval results"
    assert manager.context_state.context is not None
    assert 501 in manager.context_state.context.additional_chunks
    post_budget = manager.context_state.get_remaining_budget()
    assert update.tokens_used > 0
    assert post_budget == max(0, pre_budget - update.tokens_used)
    assert manager.context_state.context.gap_analysis == update.divergence.gaps

    reserve = int(token_counts["total_available"] * minimal_settings["memory"]["pass2_budget_reserve"])
    assert manager.context_state.context.token_usage["reserved_for_pass2"] == reserve
    assert manager.context_state.context.token_usage["reserve_shortfall"] == max(0, reserve - post_budget)


def test_pass1_stores_authorial_directives(minimal_settings, dummy_memnon, baseline_inputs):
    manager = ContextMemoryManager(minimal_settings, memnon=dummy_memnon)

    directives = [
        "  Vault alarm subsystem overrides  ",
        "Dynacorp retaliation forecasts",
    ]

    package = manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
        authorial_directives=directives,
    )

    trimmed = [directive.strip() for directive in directives]
    assert package.authorial_directives == trimmed

    state_context = manager.context_state.context
    transition = manager.context_state.transition
    assert state_context is not None
    assert transition is not None
    assert state_context.authorial_directives == trimmed
    assert transition.authorial_directives == trimmed

    history = manager.query_memory.snapshot()
    for directive in trimmed:
        assert directive in history["pass1"]
    assert history["pass2"] == []


def test_pass1_separates_structured_passages(minimal_settings, dummy_memnon, baseline_inputs):
    manager = ContextMemoryManager(minimal_settings, memnon=dummy_memnon)

    structured = {
        "id": "character:alex",
        "name": "Alex Navarro",
        "summary": "Lead infiltrator, tracking The Ghost",
    }
    retrieved = baseline_inputs["retrieved"] + [structured, {"chunk_id": 305, "text": "Bridge diagnostics memo."}]

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


def test_pass2_warm_slice_expansion_without_divergence(minimal_settings, dummy_memnon, baseline_inputs):
    manager = ContextMemoryManager(minimal_settings, memnon=dummy_memnon)

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    # Force divergence detector to report no gap so we exercise warm slice expansion
    manager.divergence_detector.detect = lambda text, context, transition: DivergenceResult(
        detected=False,
        confidence=0.0,
        gaps={},
        unmatched_entities=set(),
        references_seen=set(),
    )

    token_counts = {
        "total_available": 1200,
        "warm_slice": 360,
        "structured": 180,
        "augmentation": 90,
    }

    update = manager.handle_user_input("Continue the vault briefing.", token_counts)

    assert update.divergence.detected is False
    assert not dummy_memnon.queries  # No gap-driven queries
    assert dummy_memnon.recent_calls == [5]  # Warm slice expansion call
    assert update.retrieved_chunks, "Warm slice expansion should contribute chunks"
    assert update.tokens_used > 0
    assert 610 in manager.context_state.context.additional_chunks


def test_augment_warm_slice_merges_incremental_additions(minimal_settings, dummy_memnon, baseline_inputs):
    manager = ContextMemoryManager(minimal_settings, memnon=dummy_memnon)

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    manager.divergence_detector.detect = lambda text, context, transition: DivergenceResult(
        detected=True,
        confidence=1.0,
        gaps={"Data Shard": "Reference not present"},
        unmatched_entities={"Data Shard"},
        references_seen={"Data Shard"},
    )

    manager.handle_user_input("Need the Data Shard briefing.")

    augmented = manager.augment_warm_slice([
        {"chunk_id": 101, "text": "Setup: extraction plan finalised."},
    ])

    chunk_ids = {chunk["chunk_id"] for chunk in augmented if "chunk_id" in chunk}
    assert {101, 501}.issubset(chunk_ids)


def test_get_memory_summary_reports_state(minimal_settings, dummy_memnon, baseline_inputs):
    manager = ContextMemoryManager(minimal_settings, memnon=dummy_memnon)

    manager.handle_storyteller_response(
        narrative=baseline_inputs["narrative"],
        warm_slice=baseline_inputs["warm_slice"],
        retrieved_passages=baseline_inputs["retrieved"],
        token_usage=baseline_inputs["token_usage"],
    )

    manager.divergence_detector.detect = lambda text, context, transition: DivergenceResult(
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
    assert summary["pass1"]["authorial_directives"] == []
    assert summary["pass1"]["structured_passages"] == []
    assert summary["pass2"]["divergence_detected"] is True
    assert summary["pass2"]["usage"]["remaining_budget"] >= 0
    assert summary["query_memory"]["history"]["pass2"], "Expected stored pass2 queries"
