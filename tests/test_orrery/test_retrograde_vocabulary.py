"""Tests for Retrograde seed-eligible vocabulary enumeration."""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel, Field, ValidationError

from nexus.agents.orrery import retrograde_vocabulary
from nexus.agents.orrery.retrograde_seed_candidates import (
    RetrogradeWireProjectIntent,
)
from nexus.agents.orrery.tag_library import TagLibraryEntry
from nexus.agents.orrery.retrograde_vocabulary import (
    ENTITY_REF_MAX_LENGTH,
    EntityRef,
    category_seed_policy,
    enumerate_seed_eligible_vocabulary,
    validate_bare_entity_ref,
)
from nexus.agents.orrery.status_family import STATUS_TAGS
from nexus.api.native_structured_output import (
    anthropic_json_schema,
    strict_json_schema,
    structured_output_error_text,
)


def test_seed_eligible_vocabulary_includes_template_primitives() -> None:
    """The enumerator reflects tags, events, places, and relations in templates."""

    vocabulary = enumerate_seed_eligible_vocabulary()

    assert {"character", "faction", "place"} <= set(vocabulary["entity_kinds"])
    assert {"actor", "target", "location"} <= set(vocabulary["slots"])
    assert "vendetta_holder" in vocabulary["single_entity_tag_anchors"]
    assert "grudge_active" in vocabulary["single_entity_tag_anchors"]
    assert "reputation_compromised" in vocabulary["single_entity_tag_anchors"]
    assert "retaliation_executed" in vocabulary["event_types"]
    assert "evade_pursuit" in vocabulary["event_types"]
    assert "dwelling" in vocabulary["place_classes"]
    assert "wilderness" in vocabulary["place_classes"]
    assert vocabulary["registered_single_entity_tags"] == []
    assert vocabulary["registered_tags_by_category"] == {}
    # Registry-backed like the registered_* sections: templates reference
    # event types by name only, so the template path carries no categories.
    assert vocabulary["event_type_categories"] == {}
    assert "family" in vocabulary["relationship_types"]
    assert "handler" in vocabulary["relationship_types"]


@pytest.mark.requires_postgres
def test_seed_eligible_vocabulary_can_include_live_tag_registry() -> None:
    """Passing a slot database folds post-migration registry rows into seeds."""

    vocabulary = enumerate_seed_eligible_vocabulary(dbname="save_02")

    assert "commerce" in vocabulary["single_entity_tag_anchors"]
    assert "grieving" in vocabulary["single_entity_tag_anchors"]
    assert "place_environment" in vocabulary["registered_tag_categories"]
    assert "place_function" in vocabulary["registered_tag_categories"]
    assert "state" in vocabulary["registered_tag_categories"]
    assert "commerce" in vocabulary["registered_tags_by_category"]["place_function"]
    assert (
        "wilderness" in vocabulary["registered_tags_by_category"]["place_environment"]
    )
    assert "grieving" in vocabulary["registered_tags_by_entity_kind"]["character"]
    assert "commerce" in vocabulary["registered_tags_by_entity_kind"]["place"]
    assert vocabulary["event_type_categories"]["upkeep_done"] == "routine"
    assert vocabulary["event_type_categories"]["slept"] == "physiological"
    policies = {
        item["category"]: item["policy"]
        for item in vocabulary["registered_category_seed_policies"]
    }
    assert policies["place_function"] == "stable_seed"
    assert policies["state"] == "event_anchored"

    for key in (
        "single_entity_tag_anchors",
        "registered_single_entity_tags",
        "registered_tag_categories",
    ):
        assert vocabulary[key] == sorted(vocabulary[key])
    for values in vocabulary["registered_tags_by_category"].values():
        assert values == sorted(values)
    for values in vocabulary["registered_tags_by_entity_kind"].values():
        assert values == sorted(values)


def test_seed_eligible_vocabulary_includes_pair_tag_kind_constraints() -> None:
    """Multi-entity tag families include subject/object polymorphism."""

    vocabulary = enumerate_seed_eligible_vocabulary()
    definitions = {
        item["tag"]: item for item in vocabulary["multi_entity_tag_definitions"]
    }

    assert "claims" in vocabulary["multi_entity_tag_families"]
    assert definitions["claims"]["subject_kinds"] == ["faction"]
    assert definitions["claims"]["object_kinds"] == ["place"]
    assert definitions["hunting"]["subject_kinds"] == ["character", "faction"]
    assert definitions["hunting"]["object_kinds"] == ["character"]
    assert definitions["hunting"]["is_ephemeral"] is True
    assert definitions["hunting"]["semantic_categories"] == ["adversarial"]
    assert STATUS_TAGS <= set(definitions)
    for tag in STATUS_TAGS:
        assert definitions[tag]["subject_kinds"] == ["character", "faction"]
        assert definitions[tag]["object_kinds"] == ["faction"]
        assert definitions[tag]["is_ephemeral"] is False
        assert definitions[tag]["semantic_categories"] == ["status"]


def test_seed_relationship_types_carry_semantic_and_valence_metadata() -> None:
    """Constraint classification is registered metadata, not string equality."""

    vocabulary = enumerate_seed_eligible_vocabulary()
    definitions = {
        item["relationship_type"]: item
        for item in vocabulary["relationship_type_definitions"]
    }

    for relationship_type in ("captor", "enemy", "rival"):
        assert "adversarial" in definitions[relationship_type]["semantic_categories"]
        assert definitions[relationship_type]["default_emotional_valence"].startswith(
            "-"
        )


def test_unclassified_seed_relationship_type_fails_loudly() -> None:
    """A new seed-eligible relation cannot silently bypass constraint classes."""

    with pytest.raises(ValueError, match="missing semantic and valence"):
        retrograde_vocabulary._load_relationship_type_definitions(
            ["unclassified_future_threat"]
        )


def test_seed_eligible_vocabulary_classifies_registered_categories(
    monkeypatch,
) -> None:
    """Retrograde distinguishes stable, event-anchored, and prompt-only tags."""

    monkeypatch.setattr(
        retrograde_vocabulary,
        "read_tag_library",
        lambda _dbname: [
            TagLibraryEntry(
                entity_kind="character",
                category="role.function",
                tag="scholar",
                is_ephemeral=False,
                description="",
                category_description="",
                prompt_order=10,
            ),
            TagLibraryEntry(
                entity_kind="character",
                category="state",
                tag="grieving",
                is_ephemeral=True,
                description="",
                category_description="",
                prompt_order=20,
            ),
            TagLibraryEntry(
                entity_kind="character",
                category="experimental_signal",
                tag="untested_signal",
                is_ephemeral=False,
                description="",
                category_description="",
                prompt_order=30,
            ),
        ],
    )
    monkeypatch.setattr(
        retrograde_vocabulary,
        "read_event_types",
        lambda _dbname: ["live_warning"],
    )
    monkeypatch.setattr(
        retrograde_vocabulary,
        "read_event_type_categories",
        lambda _dbname: {"live_warning": "interpersonal"},
    )

    vocabulary = enumerate_seed_eligible_vocabulary(dbname="save_05")
    policies = {
        item["category"]: item["policy"]
        for item in vocabulary["registered_category_seed_policies"]
    }

    assert policies == {
        "experimental_signal": "prompt_visible_only",
        "role.function": "stable_seed",
        "state": "event_anchored",
    }
    assert vocabulary["registered_tags_by_seed_policy"]["stable_seed"] == ["scholar"]
    assert vocabulary["registered_tags_by_seed_policy"]["event_anchored"] == [
        "grieving"
    ]
    assert vocabulary["registered_tags_by_seed_policy"]["prompt_visible_only"] == [
        "untested_signal"
    ]
    assert vocabulary["event_types"] == ["live_warning"]
    assert vocabulary["event_type_categories"] == {"live_warning": "interpersonal"}


def test_category_seed_policy_returns_complete_struct() -> None:
    """Direct callers get a complete category/entity policy, not a stub."""

    assert category_seed_policy("role.function", "character") == {
        "category": "role.function",
        "entity_kind": "character",
        "policy": "stable_seed",
        "reason": (
            "Stable identity, role, faction, or place affordance tags may "
            "be proposed as present-state seed outcomes."
        ),
    }


def test_category_seed_policy_settles_live_registry_split() -> None:
    """Issue #300 split: every live registry category classifies explicitly."""

    # Stable identity/role/affordance categories promoted in M4.
    for category, entity_kind in (
        ("bodyform", "character"),
        ("role", "character"),
        ("profession_lite", "character"),
        ("place_function", "place"),
        ("ideology_axis", "faction"),
        ("resource_class", "faction"),
        ("legitimacy_status", "faction"),
        ("operational_secrecy", "faction"),
        ("power_posture", "faction"),
        ("history_class", "faction"),
    ):
        assert (
            category_seed_policy(category, entity_kind)["policy"] == "stable_seed"
        ), category

    # Pressure/relational categories that require a causing event.
    for category, entity_kind in (
        ("hidden_agenda_class", "faction"),
        ("relationship_risk", "character"),
    ):
        assert (
            category_seed_policy(category, entity_kind)["policy"] == "event_anchored"
        ), category


def test_deprecated_place_affordance_is_not_seed_eligible() -> None:
    """Migration 043 deprecated place_affordance; Retrograde must not seed it."""

    policy = category_seed_policy("place_affordance", "place")
    assert policy["policy"] == "prompt_visible_only"


def test_category_seed_policy_pins_runtime_categories_prompt_only() -> None:
    """orrery_* runtime bookkeeping must never be seed-writeable."""

    policy = category_seed_policy("orrery_need", "character")
    assert policy["policy"] == "prompt_visible_only"
    assert "tick loop" in policy["reason"]
    assert (
        category_seed_policy("orrery_schedule", "character")["policy"]
        == "prompt_visible_only"
    )


def test_category_seed_policy_defaults_unknown_to_prompt_only() -> None:
    """Unclassified future categories ship locked (conservative direction)."""

    policy = category_seed_policy("experimental_new_axis", "character")
    assert policy["policy"] == "prompt_visible_only"


def test_seed_eligible_pair_tags_are_sorted() -> None:
    """Stable ordering keeps snapshots and future prompt generation deterministic."""

    vocabulary = enumerate_seed_eligible_vocabulary()
    sorted_buckets = (
        vocabulary["entity_kinds"],
        vocabulary["slots"],
        vocabulary["single_entity_tag_anchors"],
        vocabulary["durable_tags"],
        vocabulary["ephemeral_tags"],
        vocabulary["current_tags"],
        vocabulary["applied_tags"],
        vocabulary["registered_single_entity_tags"],
        vocabulary["registered_tag_categories"],
        vocabulary["multi_entity_tag_families"],
        vocabulary["event_types"],
        vocabulary["place_classes"],
        vocabulary["relationship_types"],
    )

    for values in sorted_buckets:
        assert values == sorted(values)


@pytest.mark.parametrize(
    "value",
    [
        "Vale",
        "Sister Orla",
        "Placeholder: X",
        "Vale: the Younger",
        "Low Quarter",
        "Upper Reach",
        "N" * ENTITY_REF_MAX_LENGTH,
    ],
)
def test_bare_entity_ref_accepts_proper_names(value: str) -> None:
    """A bare name passes unchanged, even when it contains a colon (#1007)."""

    assert validate_bare_entity_ref(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "character:Sentinel1007",
        "Character: Sentinel1007",
        "PLACE|Sentinel1007",
        "faction : Sentinel1007",
    ],
)
def test_bare_entity_ref_rejects_kind_prefix_without_echoing_value(
    value: str,
) -> None:
    """A kind-prefixed ref fails with a fixed message that omits the input."""

    with pytest.raises(ValueError, match="entity-kind prefix") as exc_info:
        validate_bare_entity_ref(value)

    assert "Sentinel1007" not in str(exc_info.value)


@pytest.mark.parametrize("identifier", ["zone:Low Quarter", "layer:Upper Reach"])
def test_graph_zone_and_layer_identifiers_are_rejected_as_refs(
    identifier: str,
) -> None:
    """Zone and layer graph identifiers fail like entity-kind prefixes.

    The packet puts the starting zone and layer into core_entities, so the
    candidate graph shows the model ``zone:`` and ``layer:`` identifiers. A
    seed target_ref shaped like one would freeze a target that the bare-name
    expansion plan can never match (#1007 review).
    """

    with pytest.raises(ValueError, match="entity-kind prefix"):
        validate_bare_entity_ref(identifier)

    with pytest.raises(ValidationError, match="entity-kind prefix"):
        RetrogradeWireProjectIntent.model_validate(
            {
                "project_type": "plan_relocation",
                "target_ref": identifier,
                "rationale": "The ledger trail leads somewhere quieter.",
            }
        )


def test_wire_target_ref_rejects_prefix_without_echoing_value() -> None:
    """The wire boundary error text stays free of the offending value."""

    with pytest.raises(ValidationError) as exc_info:
        RetrogradeWireProjectIntent.model_validate(
            {
                "project_type": "court_patron",
                "target_ref": "character:Sentinel1007",
                "rationale": "The old debt can become patronage.",
            }
        )

    rendered = structured_output_error_text(exc_info.value)
    assert "entity-kind prefix" in rendered
    assert "Sentinel1007" not in rendered
    assert "Sentinel1007" not in str(exc_info.value.errors(include_input=False))


def test_wire_target_ref_validates_after_whitespace_strip() -> None:
    """A padded prefix is stripped first, then rejected (never mode="before")."""

    with pytest.raises(ValidationError, match="entity-kind prefix"):
        RetrogradeWireProjectIntent.model_validate(
            {
                "project_type": "court_patron",
                "target_ref": "  character:Vale",
                "rationale": "The old debt can become patronage.",
            }
        )


def test_entity_ref_validator_adds_nothing_to_json_schema() -> None:
    """The AfterValidator leaves provider grammars byte-identical."""

    class PlainRefs(BaseModel):
        ref: Annotated[str, Field(min_length=1, max_length=ENTITY_REF_MAX_LENGTH)]
        wire_ref: str = Field(default="", max_length=ENTITY_REF_MAX_LENGTH)

    class ValidatedRefs(BaseModel):
        ref: EntityRef
        wire_ref: retrograde_vocabulary.OptionalWireEntityRef = Field(
            default="", max_length=ENTITY_REF_MAX_LENGTH
        )

    for render in (strict_json_schema, anthropic_json_schema):
        plain = render(PlainRefs)
        validated = render(ValidatedRefs)
        assert validated["properties"] == plain["properties"]
        for field in ("ref", "wire_ref"):
            assert set(validated["properties"][field]) == set(
                plain["properties"][field]
            )
