"""Tests for Retrograde seed-eligible vocabulary enumeration."""

from __future__ import annotations

from nexus.agents.orrery import retrograde_vocabulary as module
from nexus.agents.orrery.retrograde_vocabulary import (
    enumerate_seed_eligible_vocabulary,
)
from nexus.agents.orrery.tag_library import TagLibraryEntry


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
    assert "home" in vocabulary["place_affordances"]
    assert "wilderness" in vocabulary["place_affordances"]
    assert vocabulary["registered_single_entity_tags"] == []
    assert vocabulary["registered_tags_by_category"] == {}
    assert "family" in vocabulary["relationship_types"]
    assert "handler" in vocabulary["relationship_types"]


def test_seed_eligible_vocabulary_can_include_live_tag_registry(monkeypatch) -> None:
    """Passing a slot database folds post-migration registry rows into seeds."""

    entries = [
        TagLibraryEntry(
            entity_kind="place",
            category="place_function",
            tag="commerce",
            is_ephemeral=False,
            description="",
            category_description="",
            prompt_order=60,
        ),
        TagLibraryEntry(
            entity_kind="place",
            category="place_environment",
            tag="wilderness",
            is_ephemeral=False,
            description="",
            category_description="",
            prompt_order=63,
        ),
        TagLibraryEntry(
            entity_kind="character",
            category="state",
            tag="grieving",
            is_ephemeral=True,
            description="",
            category_description="",
            prompt_order=50,
        ),
    ]

    def fake_read_tag_library(dbname: str):
        assert dbname == "save_02"
        return entries

    monkeypatch.setattr(module, "read_tag_library", fake_read_tag_library)

    vocabulary = enumerate_seed_eligible_vocabulary(dbname="save_02")

    assert "commerce" in vocabulary["single_entity_tag_anchors"]
    assert "grieving" in vocabulary["single_entity_tag_anchors"]
    assert vocabulary["registered_tag_categories"] == [
        "place_environment",
        "place_function",
        "state",
    ]
    assert vocabulary["registered_tags_by_category"]["place_function"] == ["commerce"]
    assert vocabulary["registered_tags_by_category"]["place_environment"] == [
        "wilderness"
    ]
    assert vocabulary["registered_tags_by_entity_kind"]["character"] == ["grieving"]
    assert vocabulary["registered_tags_by_entity_kind"]["place"] == [
        "commerce",
        "wilderness",
    ]


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


def test_seed_eligible_pair_tags_are_sorted() -> None:
    """Stable ordering keeps snapshots and future prompt generation deterministic."""

    vocabulary = enumerate_seed_eligible_vocabulary()
    list_keys = (
        "entity_kinds",
        "slots",
        "single_entity_tag_anchors",
        "durable_tags",
        "ephemeral_tags",
        "current_tags",
        "applied_tags",
        "registered_single_entity_tags",
        "registered_tag_categories",
        "multi_entity_tag_families",
        "event_types",
        "place_affordances",
        "relationship_types",
    )

    for key in list_keys:
        assert vocabulary[key] == sorted(vocabulary[key])
