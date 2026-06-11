"""Tests for wizard-time Retrograde orchestration."""

from __future__ import annotations

from typing import Any

import pytest

from nexus.agents.orrery.retrograde_orchestrator import (
    RetrogradeGenerationBundle,
    RetrogradePersistenceBlockedError,
    RetrogradeStageTiming,
    build_wizard_history_surface,
    generate_retrograde_history,
    get_retrograde_progress,
    persist_retrograde_history,
    record_retrograde_progress,
    reset_retrograde_progress,
)
from nexus.config import load_settings
from test_orrery.test_retrograde_persistence import (
    FakeRetrogradePersistenceCursor,
    _packet,
    _persistence_test_vocabulary,
    _seed_response,
    _valid_expansion,
)


def test_progress_registry_round_trip() -> None:
    """Progress entries accumulate per slot and reset cleanly."""

    reset_retrograde_progress(4)
    assert get_retrograde_progress(4) is None

    record_retrograde_progress(4, "packet", {})
    record_retrograde_progress(4, "seed_candidates", {"weird": "medium"})
    progress = get_retrograde_progress(4)
    assert progress is not None
    assert progress["stage"] == "seed_candidates"
    assert progress["detail"] == {"weird": "medium"}
    assert [item["stage"] for item in progress["stages"]] == [
        "packet",
        "seed_candidates",
    ]

    reset_retrograde_progress(4)
    assert get_retrograde_progress(4) is None


def test_progress_registry_rejects_unknown_stage() -> None:
    """Stage names outside the published vocabulary fail loudly."""

    with pytest.raises(ValueError, match="Unknown Retrograde wizard stage"):
        record_retrograde_progress(4, "weaving_intensifies", {})


def test_generate_retrograde_history_composes_stage_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generation pass composes packet, seed, and expansion stages."""

    vocabulary = _persistence_test_vocabulary()
    packet = {
        **_packet(vocabulary),
        "weird": {"level": "medium", "genre": "cyberpunk", "raw_midpoint": 0.5},
    }
    seed_response = _seed_response(vocabulary)
    expansion = _valid_expansion(vocabulary)

    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_vocabulary.enumerate_seed_eligible_vocabulary",
        lambda dbname=None: vocabulary,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_packet.build_retrograde_dry_run_packet",
        lambda **kwargs: packet,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_seed_candidates."
        "generate_seed_candidates_with_skald",
        lambda **kwargs: {
            "model": "test-model",
            "prompt_chars": 100,
            "seed_candidate_response": seed_response,
        },
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_expansion.generate_expansion_with_skald",
        lambda **kwargs: {
            "model": "test-model",
            "prompt_chars": 100,
            "retrograde_expansion_plan": expansion,
        },
    )

    stages: list[str] = []
    bundle = generate_retrograde_history(
        slot=5,
        dbname="save_05",
        cache=object(),
        settings=load_settings(),
        model_name="test-model",
        progress=lambda stage, detail: stages.append(stage),
    )

    assert stages == ["packet", "seed_candidates", "expansion"]
    assert bundle.slot == 5
    assert bundle.model == "test-model"
    assert bundle.weird["level"] == "medium"
    assert bundle.seed_candidate_response == seed_response
    assert bundle.expansion_plan == expansion
    assert [timing.stage for timing in bundle.timings] == [
        "packet",
        "seed_candidates",
        "expansion",
    ]


def test_persist_retrograde_history_executes_when_clear() -> None:
    """A clear plan executes canonical writes and returns the manifest."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    bundle = _bundle(vocabulary)

    manifest = persist_retrograde_history(
        cur,
        bundle=bundle,
        settings=load_settings(),
    )

    assert manifest["dry_run"] is False
    assert manifest["counters"]["events_inserted"] == 1
    assert manifest["counters"]["entity_tags_inserted"] == 2
    assert manifest["counters"]["pair_tags_inserted"] == 1
    assert manifest["counters"]["relationships_inserted"] == 1
    assert manifest["retrieval"]["embedding_pending_chunk_ids"]


def test_persist_retrograde_history_raises_on_blockers() -> None:
    """Execute blockers abort persistence before any canonical write."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        include_retrograde_sources=False,
    )
    bundle = _bundle(vocabulary)

    with pytest.raises(RetrogradePersistenceBlockedError) as exc_info:
        persist_retrograde_history(
            cur,
            bundle=bundle,
            settings=load_settings(),
        )

    assert exc_info.value.blockers
    assert not any("insert_world_event" in sql for sql in cur.statements)


def test_persist_retrograde_history_enforces_stub_cap() -> None:
    """The Decision 8 stub cap blocks over-budget expansions loudly."""

    vocabulary = _persistence_test_vocabulary()
    # Without Shutter Hall in the entity catalog, the place ref becomes a
    # minimum-viable stub candidate, which the zero cap then rejects.
    cur = FakeRetrogradePersistenceCursor(vocabulary, omit_place=True)
    bundle = _bundle(vocabulary)
    settings = load_settings().model_copy(deep=True)
    assert settings.orrery is not None
    settings.orrery.retrograde.wizard.max_new_entity_stubs = 0

    with pytest.raises(RetrogradePersistenceBlockedError) as exc_info:
        persist_retrograde_history(
            cur,
            bundle=bundle,
            settings=settings,
        )

    assert exc_info.value.blockers[0]["id"] == "entity_stub_budget_exceeded"
    assert not any("insert_world_event" in sql for sql in cur.statements)


def test_build_wizard_history_surface_splits_visible_and_hidden() -> None:
    """Decision 6: entities/relationships visible, event prose held back."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    bundle = _bundle(vocabulary)
    manifest = persist_retrograde_history(
        cur,
        bundle=bundle,
        settings=load_settings(),
    )

    surface = build_wizard_history_surface(bundle=bundle, manifest=manifest)

    visible = surface["visible"]
    assert {entity["name"] for entity in visible["entities"]} == {
        "Mara",
        "Vale",
        "Shutter Hall",
    }
    assert visible["relationships"] == [
        {
            "subject": "Mara",
            "object": "Vale",
            "relationship_type": bundle.expansion_plan["relationship_plan"][0][
                "relationship_type"
            ],
        }
    ]
    hidden = surface["hidden_counts"]
    assert hidden["world_events"] == 1
    assert hidden["entity_tags"] == 2
    assert hidden["pair_tags"] == 1
    assert hidden["woven_seeds"] == 1
    # The high-entropy long tail must not leak: no event prose in the surface.
    event_summary = bundle.expansion_plan["event_plan"][0]["summary"]
    assert event_summary not in repr(surface)


def _bundle(vocabulary: Any) -> RetrogradeGenerationBundle:
    packet = {
        **_packet(vocabulary),
        "weird": {"level": "medium", "genre": "cyberpunk", "raw_midpoint": 0.5},
    }
    return RetrogradeGenerationBundle(
        slot=5,
        dbname="save_05",
        model="test-model",
        weird=dict(packet["weird"]),
        packet=packet,
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan=_valid_expansion(vocabulary),
        timings=[RetrogradeStageTiming(stage="packet", seconds=0.0)],
    )
