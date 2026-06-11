"""Tests for Skald-facing Retrograde R6 expansion validation."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from nexus.agents.orrery.retrograde_expansion import (
    RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
    RetrogradeExpansionValidationError,
    render_expansion_prompt,
    validate_expansion_plan,
)
from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
from nexus.agents.orrery.retrograde_seed_candidates import (
    SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    ENTITY_REF_MAX_LENGTH,
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)


def test_expansion_plan_accepts_row_shaped_dry_run_output() -> None:
    """A valid R6 plan can weave selected seeds into event/tag/relation plans."""

    vocabulary = _expansion_test_vocabulary()
    packet = _packet(vocabulary)
    seed_response = _seed_response(vocabulary)

    response = validate_expansion_plan(
        payload=_valid_expansion(vocabulary),
        packet=packet,
        seed_candidate_response=seed_response,
    )

    assert response.selected_seed_ids == ["seed_001"]
    assert response.commit_readiness.writes == "none"
    assert response.event_plan[0].event_type == vocabulary["event_types"][0]


def test_expansion_prompt_includes_selected_seeds_and_commit_blockers() -> None:
    """R6 prompt rendering names the dry-run boundary and selected seed surface."""

    vocabulary = _expansion_test_vocabulary()
    prompt = render_expansion_prompt(
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
    )

    assert "RETROGRADE_EXPANSION_REQUEST" in prompt
    assert "seed_001" in prompt
    assert "pre_game_tick_chunk_id" in prompt
    assert "relationship_plan currently supports only character->character" in prompt
    assert RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION in prompt


def test_expansion_plan_rejects_non_selected_event_seed() -> None:
    """Planned events can only weave seeds Skald selected in R5."""

    vocabulary = _expansion_test_vocabulary()
    payload = _valid_expansion(vocabulary)
    payload["event_plan"][0]["seed_ids"] = ["seed_999"]

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="non-selected seeds",
    ):
        validate_expansion_plan(
            payload=payload,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
        )


def test_expansion_plan_requires_event_for_event_anchored_tag() -> None:
    """Event-anchored final state tags need a planned source event."""

    vocabulary = _expansion_test_vocabulary()
    payload = _valid_expansion(vocabulary)
    payload["entity_tag_plan"][0].pop("source_event_ref")

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="requires source_event_ref",
    ):
        validate_expansion_plan(
            payload=payload,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
        )


def test_expansion_plan_validates_pair_tag_kinds() -> None:
    """R6 pair tags use the shared pair-tag registry constraints."""

    vocabulary = _expansion_test_vocabulary()
    payload = _valid_expansion(vocabulary)
    payload["pair_tag_plan"][0]["object_kind"] = "character"

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="does not allow object_kind",
    ):
        validate_expansion_plan(
            payload=payload,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
        )


def test_expansion_plan_rejects_cross_kind_relationships() -> None:
    """R6 relationship writes are limited to character-character rows."""

    vocabulary = _expansion_test_vocabulary()
    payload = _valid_expansion(vocabulary)
    payload["relationship_plan"][0]["subject_kind"] = "faction"

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="must be character->character",
    ):
        validate_expansion_plan(
            payload=payload,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
        )


def test_expansion_plan_requires_thread_for_each_selected_seed() -> None:
    """Every selected seed must be woven, deferred, or rejected in R6."""

    vocabulary = _expansion_test_vocabulary()
    seed_response = _seed_response(vocabulary)
    second_candidate = copy.deepcopy(seed_response["candidates"][0])
    second_candidate["seed_id"] = "seed_002"
    seed_response["candidates"].append(second_candidate)
    seed_response["selected_seed_ids"] = ["seed_001", "seed_002"]

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="thread_plan omits selected seeds",
    ):
        validate_expansion_plan(
            payload=_valid_expansion(vocabulary),
            packet=_packet(vocabulary),
            seed_candidate_response=seed_response,
        )


def test_expansion_plan_rejects_kind_incompatible_tag() -> None:
    """Plan tags must be registered for their entity kind, as in persistence."""

    vocabulary = _expansion_test_vocabulary()
    # Seed-stage hints ('grieving' on a character) stay legal, but the
    # expansion's 'scholar' tag on a character is no longer kind-registered.
    vocabulary["registered_tags_by_entity_kind"] = {
        "character": ["grieving", "untested_signal"],
        "faction": ["scholar"],
    }

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="not registered for entity_kind",
    ):
        validate_expansion_plan(
            payload=_valid_expansion(vocabulary),
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
        )


def test_expansion_plan_rejects_overlong_entity_ref() -> None:
    """Refs become canonical varchar(50) stub names; descriptions must fail."""

    vocabulary = _expansion_test_vocabulary()
    payload = _valid_expansion(vocabulary)
    payload["entity_tag_plan"][0][
        "entity_ref"
    ] = "the dockside chemist who first cut Mara's product behind Shutter Hall"

    with pytest.raises(
        ValidationError,
        match=f"at most {ENTITY_REF_MAX_LENGTH} characters",
    ):
        validate_expansion_plan(
            payload=payload,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
        )


def test_expansion_plan_rejects_overlong_location_ref() -> None:
    """location_ref obeys the same name bound as places.name varchar(50)."""

    vocabulary = _expansion_test_vocabulary()
    payload = _valid_expansion(vocabulary)
    payload["event_plan"][0][
        "location_ref"
    ] = "the flooded sub-basement of the old transit authority records annex"

    with pytest.raises(
        ValidationError,
        match=f"at most {ENTITY_REF_MAX_LENGTH} characters",
    ):
        validate_expansion_plan(
            payload=payload,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
        )


def test_expansion_prompt_states_entity_ref_name_contract() -> None:
    """The R6 prompt tells Skald refs are bounded proper names."""

    vocabulary = _expansion_test_vocabulary()
    prompt = render_expansion_prompt(
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
    )

    assert f"at most {ENTITY_REF_MAX_LENGTH} characters" in prompt


def test_expansion_plan_enforces_new_entity_budget() -> None:
    """Decision 8: refs beyond the first-class set respect the stub cap."""

    vocabulary = _expansion_test_vocabulary()
    packet = _packet(vocabulary)
    # The valid expansion references Vale and Shutter Hall beyond core Mara.
    packet["seed_generation_request"]["budget"]["max_new_entity_stubs"] = 1

    with pytest.raises(
        RetrogradeExpansionValidationError,
        match="max_new_entity_stubs",
    ):
        validate_expansion_plan(
            payload=_valid_expansion(vocabulary),
            packet=packet,
            seed_candidate_response=_seed_response(vocabulary),
        )


def test_expansion_plan_accepts_new_entities_within_budget() -> None:
    """New refs at or under the configured stub cap stay valid."""

    vocabulary = _expansion_test_vocabulary()
    packet = _packet(vocabulary)
    packet["seed_generation_request"]["budget"]["max_new_entity_stubs"] = 2

    response = validate_expansion_plan(
        payload=_valid_expansion(vocabulary),
        packet=packet,
        seed_candidate_response=_seed_response(vocabulary),
    )

    assert response.selected_seed_ids == ["seed_001"]


def test_expansion_prompt_surfaces_budget() -> None:
    """The R6 prompt shows the request budget, including the stub cap."""

    vocabulary = _expansion_test_vocabulary()
    packet = _packet(vocabulary)
    packet["seed_generation_request"]["budget"]["max_new_entity_stubs"] = 3

    prompt = render_expansion_prompt(
        packet=packet,
        seed_candidate_response=_seed_response(vocabulary),
    )

    assert '"max_new_entity_stubs": 3' in prompt


def _expansion_test_vocabulary() -> SeedEligibleVocabulary:
    vocabulary = enumerate_seed_eligible_vocabulary()
    vocabulary["registered_single_entity_tags"] = [
        "grieving",
        "scholar",
        "untested_signal",
    ]
    vocabulary["registered_tags_by_seed_policy"] = {
        "stable_seed": ["scholar"],
        "event_anchored": ["grieving"],
        "prompt_visible_only": ["untested_signal"],
    }
    return vocabulary


def _packet(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    return {
        "seed_generation_request": build_seed_generation_request(
            candidate_scaffolds={
                "core_entities": [
                    {
                        "kind": "character",
                        "role": "protagonist",
                        "name": "Mara",
                        "summary": "Debt tracker.",
                    }
                ],
                "named_seed_npcs": [],
                "pressure_axes": [],
                "trait_hooks": {},
            },
            vocabulary=vocabulary,
            weird={"level": "medium", "genre": "cyberpunk", "raw_midpoint": 0.5},
        ),
        "seed_eligible_vocabulary": vocabulary,
    }


def _seed_response(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    return {
        "schema_version": SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
        "candidates": [
            {
                "seed_id": "seed_001",
                "summary": "Mara inherited a debt from a dead handler.",
                "origin_friction": "medium",
                "present_leaf_anchor": "The debt returns in the opening hook.",
                "coverage_functions": ["hidden_truth", "unresolved_ledger"],
                "mechanical_hints": {
                    "events": [
                        {
                            "event_ref": "seed_event_001",
                            "event_type": vocabulary["event_types"][0],
                            "summary": "The handler died before clearing the debt.",
                            "participating_entities": ["Mara", "Vale"],
                        }
                    ],
                    "single_entity_tags": [
                        {
                            "entity_ref": "Mara",
                            "entity_kind": "character",
                            "tag": "grieving",
                            "supporting_event_ref": "seed_event_001",
                        }
                    ],
                    "pair_tags": [],
                    "relationships": [],
                },
                "defer_or_reject_if": [],
            }
        ],
        "selected_seed_ids": ["seed_001"],
        "rejected_seed_ids": [],
    }


def _valid_expansion(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    event_type = vocabulary["event_types"][0]
    relationship_type = vocabulary["relationship_types"][0]
    return {
        "schema_version": RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
        "selected_seed_ids": ["seed_001"],
        "event_plan": [
            {
                "event_ref": "retro_event_001",
                "seed_ids": ["seed_001"],
                "event_type": event_type,
                "summary": "The handler died before clearing Mara's inherited debt.",
                "chronology": "recent_past",
                "participants": [
                    {
                        "entity_ref": "Mara",
                        "entity_kind": "character",
                        "role": "beneficiary",
                    }
                ],
                "location_ref": "Shutter Hall",
                "changed_fields": ["world_events", "entity_tags"],
                "magnitude": 0.6,
                "payload": {"source": "retrograde_test"},
            }
        ],
        "entity_tag_plan": [
            {
                "entity_ref": "Mara",
                "entity_kind": "character",
                "tag": "grieving",
                "source_event_ref": "retro_event_001",
            },
            {
                "entity_ref": "Mara",
                "entity_kind": "character",
                "tag": "scholar",
            },
        ],
        "pair_tag_plan": [
            {
                "subject_ref": "Mara",
                "subject_kind": "character",
                "tag": "knows_location",
                "object_ref": "Shutter Hall",
                "object_kind": "place",
                "source_event_ref": "retro_event_001",
            }
        ],
        "relationship_plan": [
            {
                "subject_ref": "Mara",
                "subject_kind": "character",
                "relationship_type": relationship_type,
                "object_ref": "Vale",
                "object_kind": "character",
                "source_event_ref": "retro_event_001",
            }
        ],
        "thread_plan": [
            {
                "seed_id": "seed_001",
                "status": "woven",
                "event_refs": ["retro_event_001"],
                "present_leaf_anchor": "The inherited debt drives the opening hook.",
            }
        ],
        "coverage_notes": ["The seed keeps the unresolved ledger alive."],
        "commit_readiness": {
            "writes": "none",
            "planned_source": "retrograde",
            "blocked_by": [
                "pre_game_tick_chunk_id",
                "event_source_kind_retrograde",
            ],
            "explanation": "Dry-run plan only.",
        },
    }
