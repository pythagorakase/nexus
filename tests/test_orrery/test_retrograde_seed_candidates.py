"""Tests for Skald-facing Retrograde seed candidate validation."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from nexus.agents.orrery.retrograde_junctions import resolve_junctions
from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
from nexus.agents.orrery.retrograde_seed_candidates import (
    SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
    RetrogradeSeedCandidateResponse,
    RetrogradeSeedCandidateValidationError,
    coerce_seed_candidate_response_payload,
    render_seed_generation_prompt,
    render_seed_selection_prompt,
    seed_candidate_wire_response_model,
    validate_seed_candidate_response,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    ENTITY_REF_MAX_LENGTH,
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)
from nexus.api.native_structured_output import anthropic_json_schema


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
    assert "registered_tags_by_entity_kind" in prompt
    assert "scholar" in prompt
    assert "knows_location" in prompt
    assert "single_entity_tag_refs" in prompt
    assert "character|scholar" in prompt


def test_seed_candidate_wire_schema_constrains_kind_tag_refs() -> None:
    """Native grammar sees legal kind/tag pairs as enum values."""

    vocabulary = _seed_test_vocabulary()
    schema_model = seed_candidate_wire_response_model(
        seed_generation_request=_seed_request(vocabulary),
        vocabulary=vocabulary,
    )
    schema = anthropic_json_schema(schema_model)
    enum_values = _schema_enum_values(schema)

    assert "character|scholar" in enum_values
    assert "character|grieving" in enum_values
    assert "faction|scholar" not in enum_values
    assert "character|place|knows_location" in enum_values


def test_seed_candidate_wire_payload_coerces_to_full_contract() -> None:
    """Provider-facing compact refs expand back into the app response model."""

    vocabulary = _seed_test_vocabulary()
    event_type = vocabulary["event_types"][0]
    relationship_type = vocabulary["relationship_types"][0]
    payload = {
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
                            "event_ref": "event_001",
                            "event_type": event_type,
                            "summary": "The handler died before clearing the debt.",
                            "participating_entities": ["Mara", "Vale"],
                        }
                    ],
                    "single_entity_tags": [
                        {
                            "entity_ref": "Mara",
                            "tag_ref": "character|grieving",
                            "supporting_event_ref": "event_001",
                            "rationale": "",
                        }
                    ],
                    "pair_tags": [
                        {
                            "subject_ref": "Mara",
                            "tag_ref": "character|place|knows_location",
                            "object_ref": "Shutter Hall",
                            "rationale": "",
                        }
                    ],
                    "relationships": [
                        {
                            "subject_ref": "Mara",
                            "relationship_ref": (
                                f"character|character|{relationship_type}"
                            ),
                            "object_ref": "Vale",
                            "rationale": "",
                        }
                    ],
                },
                "defer_or_reject_if": [],
            }
        ],
        "selected_seed_ids": ["seed_001"],
        "rejected_seed_ids": [],
        "selection_notes": "",
    }

    response = coerce_seed_candidate_response_payload(payload)

    hints = response.candidates[0].mechanical_hints
    assert hints.single_entity_tags[0].entity_kind == "character"
    assert hints.single_entity_tags[0].tag == "grieving"
    assert hints.single_entity_tags[0].rationale is None
    assert hints.pair_tags[0].subject_kind == "character"
    assert hints.pair_tags[0].object_kind == "place"
    assert hints.relationships[0].relationship_type == relationship_type
    assert response.selection_notes is None


def test_seed_candidate_wire_payload_rejects_malformed_ref() -> None:
    """Malformed compact refs stay retryable instead of becoming empty hints."""

    vocabulary = _seed_test_vocabulary()
    payload = _valid_response_payload(vocabulary)
    payload["candidates"][0]["mechanical_hints"]["single_entity_tags"][0] = {
        "entity_ref": "Mara",
        "tag_ref": "character",
        "supporting_event_ref": "event_001",
        "rationale": "",
    }

    with pytest.raises(ValueError, match="Malformed compact Retrograde ref"):
        coerce_seed_candidate_response_payload(payload)


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


def test_seed_candidate_response_rejects_overlong_entity_ref() -> None:
    """Hint refs feed R6 refs, which become varchar(50) stub names."""

    payload = _valid_response_payload(_seed_test_vocabulary())
    hints = payload["candidates"][0]["mechanical_hints"]
    hints["single_entity_tags"][0][
        "entity_ref"
    ] = "the handler's estranged sister who kept the original ledger pages"

    with pytest.raises(
        ValidationError,
        match=f"at most {ENTITY_REF_MAX_LENGTH} characters",
    ):
        RetrogradeSeedCandidateResponse.model_validate(payload)


def test_seed_candidate_prompt_states_entity_ref_name_contract() -> None:
    """The R4 prompt tells Skald refs are bounded proper names."""

    vocabulary = _seed_test_vocabulary()
    prompt = render_seed_generation_prompt(
        seed_generation_request=_seed_request(vocabulary),
        vocabulary=vocabulary,
    )

    assert f"at most {ENTITY_REF_MAX_LENGTH} characters" in prompt
    assert '"claimed_edges"' in prompt


def test_resolve_junctions_accepts_two_normalized_shared_entity_legs() -> None:
    """R3 legs resolve when distinct candidates name one canonical entity."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    payload["candidates"][0]["claimed_edges"][0]["open_endpoint_name"] = "The   Broker"
    payload["candidates"][1]["claimed_edges"][0]["open_endpoint_name"] = "the broker"

    resolved, issues = resolve_junctions(
        seed_generation_request=seed_request,
        candidates_payload=payload,
    )

    assert issues == []
    assert resolved == [
        {
            "junction_id": "junction_01",
            "edge_ids": ["edge_01", "edge_02"],
            "seed_ids": ["seed_001", "seed_002"],
            "entity_ref": "The   Broker",
            "normalized_entity_ref": "the broker",
            "entity_kind": "character",
        }
    ]


def test_resolve_junctions_rejects_edge_reused_across_junctions() -> None:
    """One sampled edge cannot serve two independent junction contracts."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    first_junction = seed_request["candidate_graph"]["junctions"][0]
    seed_request["candidate_graph"]["junctions"].append(
        {
            "junction_id": "junction_02",
            "edge_ids": list(first_junction["edge_ids"]),
            "open_endpoint_kind": "character",
            "resolution": "shared_entity",
        }
    )

    _resolved, issues = resolve_junctions(
        seed_generation_request=seed_request,
        candidates_payload=payload,
    )

    assert any("reuses edge_ids" in issue for issue in issues)


@pytest.mark.parametrize("junctions", [{}, "", 0])
def test_resolve_junctions_rejects_falsey_non_list_values(junctions: object) -> None:
    """Malformed falsey junction containers cannot disable enforcement."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    seed_request["candidate_graph"]["junctions"] = junctions

    resolved, issues = resolve_junctions(
        seed_generation_request=seed_request,
        candidates_payload=payload,
    )

    assert resolved == []
    assert issues == ["candidate_graph.junctions must be a list"]


def test_seed_candidate_generation_accepts_resolved_junction_before_selection() -> None:
    """R4 may return a valid pair while leaving both R5 lists empty."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    payload["selected_seed_ids"] = []
    payload["rejected_seed_ids"] = []

    response = validate_seed_candidate_response(
        payload=payload,
        seed_generation_request=seed_request,
        vocabulary=vocabulary,
    )

    assert response.selected_seed_ids == []
    assert response.rejected_seed_ids == []


def test_seed_candidate_response_rejects_unresolved_junction_name() -> None:
    """R4 cannot satisfy two junction legs with different entity names."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    payload["candidates"][1]["claimed_edges"][0][
        "open_endpoint_name"
    ] = "Another Broker"

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="same normalized entity name",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=seed_request,
            vocabulary=vocabulary,
        )


def test_seed_candidate_response_rejects_wrong_junction_endpoint_kind() -> None:
    """Both R4 claims must use the exact endpoint kind reserved by R3."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    payload["candidates"][1]["claimed_edges"][0]["open_endpoint_kind"] = "place"

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="resolves kind 'place'; expected 'character'",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=seed_request,
            vocabulary=vocabulary,
        )


def test_seed_candidate_response_rejects_same_candidate_on_both_junction_legs() -> None:
    """A braid needs two seeds; one candidate cannot consume both legs."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    second_claim = payload["candidates"][1]["claimed_edges"][0]
    payload["candidates"] = [payload["candidates"][0]]
    payload["candidates"][0]["claimed_edges"].append(second_claim)
    payload["selected_seed_ids"] = []
    payload["rejected_seed_ids"] = []

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="two distinct candidates",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=seed_request,
            vocabulary=vocabulary,
        )


def test_seed_candidate_response_rejects_junction_leg_claimed_twice() -> None:
    """Every mechanically sampled junction leg has exactly one owner."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    duplicate = copy.deepcopy(payload["candidates"][0])
    duplicate["seed_id"] = "seed_003"
    payload["candidates"].append(duplicate)
    payload["selected_seed_ids"] = []
    payload["rejected_seed_ids"] = []

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="must be claimed exactly once; found 2 claims",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=seed_request,
            vocabulary=vocabulary,
        )


def test_seed_candidate_claimed_endpoint_uses_canonical_name_length() -> None:
    """Claimed endpoints obey the same varchar(50) boundary as R6 refs."""

    vocabulary = _seed_test_vocabulary()
    _seed_request_payload, payload = _junction_case(vocabulary)
    payload["candidates"][0]["claimed_edges"][0]["open_endpoint_name"] = "x" * (
        ENTITY_REF_MAX_LENGTH + 1
    )

    with pytest.raises(ValidationError, match="at most 50 characters"):
        RetrogradeSeedCandidateResponse.model_validate(payload)


def test_seed_selection_requires_atomic_junction_pair() -> None:
    """R5 cannot select one junction leg while rejecting its partner."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    payload["selected_seed_ids"] = ["seed_001"]
    payload["rejected_seed_ids"] = ["seed_002"]

    with pytest.raises(
        RetrogradeSeedCandidateValidationError,
        match="must be selected or rejected together",
    ):
        validate_seed_candidate_response(
            payload=payload,
            seed_generation_request=seed_request,
            vocabulary=vocabulary,
        )


def test_seed_selection_accepts_selected_junction_pair() -> None:
    """Both members may consume ordinary R5 slots as one atomic decision."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)

    response = validate_seed_candidate_response(
        payload=payload,
        seed_generation_request=seed_request,
        vocabulary=vocabulary,
    )

    assert response.selected_seed_ids == ["seed_001", "seed_002"]


def test_seed_selection_accepts_rejected_pair_and_independent_seed() -> None:
    """A junction pair may be rejected while an ordinary seed survives."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)
    independent = copy.deepcopy(payload["candidates"][0])
    independent["seed_id"] = "seed_003"
    edge = seed_request["candidate_graph"]["dangling_edges"][2]
    independent["claimed_edges"] = [
        {
            "edge_id": edge["edge_id"],
            "open_endpoint_name": "Lark",
            "open_endpoint_kind": edge["open_endpoint_kind"],
        }
    ]
    payload["candidates"].append(independent)
    payload["selected_seed_ids"] = ["seed_003"]
    payload["rejected_seed_ids"] = ["seed_001", "seed_002"]

    response = validate_seed_candidate_response(
        payload=payload,
        seed_generation_request=seed_request,
        vocabulary=vocabulary,
    )

    assert response.selected_seed_ids == ["seed_003"]


def test_seed_selection_prompt_surfaces_resolved_atomic_junction() -> None:
    """The R5 judge sees the exact pair and its shared canonical endpoint."""

    vocabulary = _seed_test_vocabulary()
    seed_request, payload = _junction_case(vocabulary)

    prompt = render_seed_selection_prompt(
        seed_generation_request=seed_request,
        candidates_payload=payload,
    )

    assert '"junction_id": "junction_01"' in prompt
    assert '"normalized_entity_ref": "the broker"' in prompt
    assert "select both member seeds or reject both" in prompt


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
    vocabulary["registered_tags_by_entity_kind"] = {
        "character": ["scholar", "grieving", "untested_signal"],
        "place": [],
        "faction": [],
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


def _schema_enum_values(value: object) -> set[str]:
    values: set[str] = set()
    if isinstance(value, dict):
        enum = value.get("enum")
        if isinstance(enum, list):
            values.update(str(item) for item in enum)
        for item in value.values():
            values.update(_schema_enum_values(item))
    elif isinstance(value, list):
        for item in value:
            values.update(_schema_enum_values(item))
    return values


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


def _first_edge_claims(vocabulary: SeedEligibleVocabulary) -> list[dict[str, Any]]:
    """Claim the deterministic graph's first dangling edge.

    The R3 graph is seeded on the intentional core, so every request built
    by _seed_request over the same vocabulary yields identical edges — a
    fixture can claim edge one without seeing the request instance.
    """

    request = _seed_request(vocabulary)
    edge = request["candidate_graph"]["dangling_edges"][0]
    return [
        {
            "edge_id": edge["edge_id"],
            "open_endpoint_name": "The Salt Ledger",
            "open_endpoint_kind": edge["open_endpoint_kind"],
        }
    ]


def _junction_case(
    vocabulary: SeedEligibleVocabulary,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a two-candidate response satisfying one synthetic R3 junction."""

    request = _seed_request(vocabulary)
    edges = request["candidate_graph"]["dangling_edges"][:2]
    for edge in edges:
        edge["open_endpoint_kind"] = "character"
    request["candidate_graph"]["junctions"] = [
        {
            "junction_id": "junction_01",
            "edge_ids": [edge["edge_id"] for edge in edges],
            "open_endpoint_kind": "character",
            "resolution": "shared_entity",
        }
    ]

    payload = _valid_response_payload(vocabulary)
    first = payload["candidates"][0]
    first["claimed_edges"] = [
        {
            "edge_id": edges[0]["edge_id"],
            "open_endpoint_name": "The Broker",
            "open_endpoint_kind": "character",
        }
    ]
    second = copy.deepcopy(first)
    second["seed_id"] = "seed_002"
    second["summary"] = "The mentor betrayed the same broker Mara owes."
    second["claimed_edges"] = [
        {
            "edge_id": edges[1]["edge_id"],
            "open_endpoint_name": "the broker",
            "open_endpoint_kind": "character",
        }
    ]
    payload["candidates"].append(second)
    payload["selected_seed_ids"] = ["seed_001", "seed_002"]
    payload["rejected_seed_ids"] = []
    return request, payload


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
                "claimed_edges": _first_edge_claims(vocabulary),
            }
        ],
        "selected_seed_ids": ["seed_001"],
        "rejected_seed_ids": [],
        "selection_notes": "The seed anchors the hook without forcing persistence.",
    }
