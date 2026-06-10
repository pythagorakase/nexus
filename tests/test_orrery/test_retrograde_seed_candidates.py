"""Tests for Skald-facing Retrograde seed candidate validation."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
from nexus.agents.orrery.retrograde_seed_candidates import (
    SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
    RetrogradeSeedCandidateResponse,
    RetrogradeSeedCandidateValidationError,
    render_seed_generation_prompt,
    validate_seed_candidate_response,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)


def test_seed_candidate_response_accepts_registered_mechanics() -> None:
    """A valid Skald response can use stable, event, pair, and relation hints."""

    vocabulary = _seed_test_vocabulary()
    seed_request = _seed_request(vocabulary)
    payload = _valid_response_payload(vocabulary)

    response = validate_seed_candidate_response(
        payload=payload,
        seed_generation_request=seed_request,
        vocabulary=vocabulary,
    )

    assert response.selected_seed_ids == ["seed_001"]
    assert response.candidates[0].mechanical_hints.single_entity_tags[1].tag == (
        "grieving"
    )


def test_seed_candidate_prompt_embeds_schema_and_allowed_vocabulary() -> None:
    """Prompt rendering gives Skald a concrete response schema and primitives."""

    vocabulary = _seed_test_vocabulary()
    seed_request = _seed_request(vocabulary)

    prompt = render_seed_generation_prompt(
        seed_generation_request=seed_request,
        vocabulary=vocabulary,
    )

    assert "Return JSON only" in prompt
    assert SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION in prompt
    assert "registered_tags_by_seed_policy" in prompt
    assert "scholar" in prompt
    assert "knows_location" in prompt


def test_seed_candidate_response_rejects_prompt_visible_mechanics() -> None:
    """Prompt-visible-only tags may guide prose but cannot become writes."""

    vocabulary = _seed_test_vocabulary()
    payload = _valid_response_payload(vocabulary)
    payload["candidates"][0]["mechanical_hints"]["single_entity_tags"].append(
        {
            "entity_ref": "Mara",
            "entity_kind": "character",
            "tag": "untested_signal",
        }
    )

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="prompt-visible-only",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=_seed_request(vocabulary),
            vocabulary=vocabulary,
        )


def test_seed_candidate_response_rejects_kind_incompatible_tag() -> None:
    """Tags must be registered for the hinted entity kind, as in persistence."""

    vocabulary = _seed_test_vocabulary()
    vocabulary["registered_tags_by_entity_kind"] = {
        "faction": ["scholar", "grieving", "untested_signal"],
    }
    payload = _valid_response_payload(vocabulary)

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="not registered for entity_kind",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=_seed_request(vocabulary),
            vocabulary=vocabulary,
        )


def test_seed_candidate_response_requires_event_for_event_anchored_tag() -> None:
    """Event-anchored current-state tags need an explicit supporting event."""

    vocabulary = _seed_test_vocabulary()
    payload = _valid_response_payload(vocabulary)
    payload["candidates"][0]["mechanical_hints"]["single_entity_tags"][1].pop(
        "supporting_event_ref"
    )

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="requires supporting_event_ref",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=_seed_request(vocabulary),
            vocabulary=vocabulary,
        )


def test_seed_candidate_response_validates_pair_tag_kinds() -> None:
    """Pair tags use the same kind constraints as the shared registry."""

    vocabulary = _seed_test_vocabulary()
    payload = _valid_response_payload(vocabulary)
    payload["candidates"][0]["mechanical_hints"]["pair_tags"][0][
        "object_kind"
    ] = "character"

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="does not allow object_kind",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=_seed_request(vocabulary),
            vocabulary=vocabulary,
        )


def test_seed_candidate_response_enforces_selection_budget() -> None:
    """The R5 selector cannot keep more seeds than the request target."""

    vocabulary = _seed_test_vocabulary()
    payload = _valid_response_payload(vocabulary)
    payload["candidates"].append(
        {
            **copy.deepcopy(payload["candidates"][0]),
            "seed_id": "seed_002",
            "summary": "A second selectable seed.",
        }
    )
    payload["selected_seed_ids"] = ["seed_001", "seed_002"]
    seed_request = _seed_request(vocabulary)
    seed_request["budget"]["select_target"] = 1

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="exceeding target 1",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=seed_request,
            vocabulary=vocabulary,
        )


def test_seed_candidate_response_schema_rejects_unknown_fields() -> None:
    """Skald cannot sneak non-contract fields into candidate responses."""

    payload = _valid_response_payload(_seed_test_vocabulary())
    payload["candidates"][0]["canonical_write_now"] = True

    with pytest.raises(ValidationError):
        RetrogradeSeedCandidateResponse.model_validate(payload)


def _seed_test_vocabulary() -> SeedEligibleVocabulary:
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
    vocabulary["registered_category_seed_policies"] = [
        {
            "category": "role.function",
            "entity_kind": "character",
            "policy": "stable_seed",
            "reason": "Stable role.",
        },
        {
            "category": "state",
            "entity_kind": "character",
            "policy": "event_anchored",
            "reason": "Current state needs an event.",
        },
        {
            "category": "experimental_signal",
            "entity_kind": "character",
            "policy": "prompt_visible_only",
            "reason": "Prompt only.",
        },
    ]
    return vocabulary


def _seed_request(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    return build_seed_generation_request(
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
    )


def _valid_response_payload(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    event_type = vocabulary["event_types"][0]
    relationship_type = vocabulary["relationship_types"][0]
    return {
        "schema_version": SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
        "candidates": [
            {
                "seed_id": "seed_001",
                "summary": "Mara inherited a debt from a dead handler.",
                "origin_friction": "medium",
                "present_leaf_anchor": (
                    "The handler's message reaches Mara in the opening hook."
                ),
                "coverage_functions": ["hidden_truth", "unresolved_ledger"],
                "mechanical_hints": {
                    "events": [
                        {
                            "event_ref": "event_001",
                            "event_type": event_type,
                            "summary": "The handler died before clearing the debt.",
                            "participating_entities": ["Mara", "Vale"],
                        }
                    ],
                    "single_entity_tags": [
                        {
                            "entity_ref": "Mara",
                            "entity_kind": "character",
                            "tag": "scholar",
                            "rationale": "She knows the old ledger system.",
                        },
                        {
                            "entity_ref": "Mara",
                            "entity_kind": "character",
                            "tag": "grieving",
                            "supporting_event_ref": "event_001",
                            "rationale": "The dead handler mattered to her.",
                        },
                    ],
                    "pair_tags": [
                        {
                            "subject_ref": "Mara",
                            "subject_kind": "character",
                            "tag": "knows_location",
                            "object_ref": "Shutter Hall",
                            "object_kind": "place",
                            "rationale": "The ledger exchange happened there.",
                        }
                    ],
                    "relationships": [
                        {
                            "subject_ref": "Mara",
                            "subject_kind": "character",
                            "relationship_type": relationship_type,
                            "object_ref": "Vale",
                            "object_kind": "character",
                            "rationale": "Vale can corroborate the debt.",
                        }
                    ],
                },
                "defer_or_reject_if": [
                    "Reject if the handler would need to appear on-screen first."
                ],
            }
        ],
        "selected_seed_ids": ["seed_001"],
        "rejected_seed_ids": [],
        "selection_notes": "The seed anchors the hook without forcing persistence.",
    }
