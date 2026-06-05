"""Tests for Retrograde seed-eligible vocabulary enumeration."""

from __future__ import annotations

import pytest

from nexus.agents.orrery import retrograde_vocabulary
from nexus.agents.orrery.tag_library import TagLibraryEntry
from nexus.agents.orrery.retrograde_vocabulary import (
    enumerate_seed_eligible_vocabulary,
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
        "place_classes",
        "relationship_types",
    )

    for key in list_keys:
        assert vocabulary[key] == sorted(vocabulary[key])
