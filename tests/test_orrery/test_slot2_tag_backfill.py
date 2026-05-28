"""Tests for the reviewed slot 2 semantic tag applicator."""

from datetime import datetime, timezone

import pytest

from scripts.apply_slot2_semantic_tags import (
    Candidate,
    EntityDefinition,
    TagDefinition,
    _build_candidates,
    _insert_candidates,
)


def test_slot2_tag_backfill_filters_and_canonicalizes_proposals() -> None:
    """Only reviewed entity-kind-compatible tags become insert candidates."""

    manifest = {
        "per_entity": [
            {
                "entity_id": 1,
                "entity_kind": "character",
                "entity_name": "Alex",
                "registered_tag_proposals": [
                    {"tag": "safe_house", "confidence": "high"},
                    {"tag": "sleep_deprived_1_mild", "confidence": "high"},
                    {"tag": "low_confidence_anchor", "confidence": "low"},
                ],
                "unregistered_tag_candidates": [
                    {"tag": "found_family_anchor", "confidence": "high"},
                    {"tag": "bodyform:android", "confidence": "high"},
                    {"tag": "unknown_one_off", "confidence": "high"},
                ],
            },
            {
                "entity_id": 2,
                "entity_kind": "faction",
                "entity_name": "Dynacorp",
                "registered_tag_proposals": [],
                "unregistered_tag_candidates": [
                    {"tag": "militarized", "confidence": "medium"},
                    {"tag": "corporate_exile", "confidence": "high"},
                ],
            },
        ]
    }
    tags = {
        "low_confidence_anchor": TagDefinition(
            id=1, category="orrery_state", is_ephemeral=False
        ),
        "corporate_exile": TagDefinition(id=2, category="state", is_ephemeral=False),
        "extended_household": TagDefinition(id=3, category="role", is_ephemeral=False),
        "inorganic": TagDefinition(
            id=7, category="bodyform.lineage", is_ephemeral=False
        ),
        "militarized": TagDefinition(
            id=4, category="power_posture", is_ephemeral=False
        ),
        "safe_house": TagDefinition(
            id=5, category="place_affordance", is_ephemeral=False
        ),
        "sleep_deprived_1_mild": TagDefinition(
            id=6, category="orrery_need", is_ephemeral=False
        ),
    }
    entities = {
        1: EntityDefinition(kind="character", name="Alex"),
        2: EntityDefinition(kind="faction", name="Dynacorp"),
    }

    candidates, skipped = _build_candidates(
        manifest,
        tags=tags,
        allowed_categories={
            "character": {
                "bodyform.lineage",
                "orrery_need",
                "orrery_state",
                "role",
                "state",
            },
            "faction": {"power_posture"},
            "place": {"place_affordance"},
        },
        entities=entities,
        current=set(),
        min_confidence="medium",
    )

    assert [(candidate.entity_id, candidate.tag) for candidate in candidates] == [
        (1, "extended_household"),
        (1, "inorganic"),
        (1, "sleep_deprived_1_mild"),
        (2, "militarized"),
    ]
    assert skipped["below_confidence"] == 1
    assert skipped["incompatible_category:place_affordance"] == 1
    assert skipped["incompatible_category:state"] == 1
    assert skipped["unknown_tag"] == 1


def test_slot2_tag_backfill_skips_existing_and_missing_entities() -> None:
    """Current tags and missing entities are reported without insert candidates."""

    manifest = {
        "per_entity": [
            {
                "entity_id": 1,
                "entity_kind": "character",
                "entity_name": "Alex",
                "registered_tag_proposals": [
                    {"tag": "quiet_retreat", "confidence": "high"},
                ],
            },
            {
                "entity_id": 99,
                "entity_kind": "character",
                "entity_name": "Ghost",
                "registered_tag_proposals": [
                    {"tag": "quiet_retreat", "confidence": "high"},
                    {"tag": "off_grid", "confidence": "medium"},
                ],
            },
        ]
    }
    tags = {
        "quiet_retreat": TagDefinition(
            id=1, category="orrery_state", is_ephemeral=False
        ),
        "off_grid": TagDefinition(id=2, category="orrery_state", is_ephemeral=False),
    }
    entities = {1: EntityDefinition(kind="character", name="Alex")}

    candidates, skipped = _build_candidates(
        manifest,
        tags=tags,
        allowed_categories={"character": {"orrery_state"}},
        entities=entities,
        current={(1, 1)},
        min_confidence="medium",
    )

    assert candidates == []
    assert skipped["already_current"] == 1
    assert skipped["missing_entity"] == 2


def test_slot2_tag_backfill_rejects_manifest_entity_kind_mismatch() -> None:
    """Entity kind drift between the manifest and slot database fails loudly."""

    manifest = {
        "per_entity": [
            {
                "entity_id": 1,
                "entity_kind": "character",
                "entity_name": "Dynacorp",
                "registered_tag_proposals": [
                    {"tag": "quiet_retreat", "confidence": "high"},
                ],
            }
        ]
    }

    with pytest.raises(ValueError, match="does not match database kind"):
        _build_candidates(
            manifest,
            tags={
                "quiet_retreat": TagDefinition(
                    id=1, category="orrery_state", is_ephemeral=False
                )
            },
            allowed_categories={"character": {"orrery_state"}},
            entities={1: EntityDefinition(kind="faction", name="Dynacorp")},
            current=set(),
            min_confidence="medium",
        )


def test_slot2_tag_backfill_insert_counts_rows_without_mutating_current() -> None:
    """The insert helper counts DB rowcount and keeps caller state unchanged."""

    cursor = FakeInsertCursor(conflicting={(2, 20)})
    current = {(3, 30)}
    candidates = [
        _candidate(entity_id=1, tag_id=10),
        _candidate(entity_id=2, tag_id=20),
        _candidate(entity_id=3, tag_id=30),
    ]

    inserted = _insert_candidates(
        cursor,
        candidates,
        current=current,
        source_kind="llm_generated",
        world_time=datetime(2073, 10, 31, 9, 44, tzinfo=timezone.utc),
    )

    assert inserted == 1
    assert current == {(3, 30)}
    assert cursor.inserted == [(1, 10)]


def _candidate(*, entity_id: int, tag_id: int) -> Candidate:
    return Candidate(
        entity_id=entity_id,
        entity_kind="character",
        entity_name=f"entity-{entity_id}",
        proposed_tag=f"tag-{tag_id}",
        tag=f"tag-{tag_id}",
        tag_id=tag_id,
        category="state",
        confidence="high",
        proposal_source="registered",
        evidence="",
    )


class FakeInsertCursor:
    """Small cursor fake for the applicator's INSERT path."""

    def __init__(self, *, conflicting: set[tuple[int, int]]) -> None:
        self.conflicting = conflicting
        self.inserted: list[tuple[int, int]] = []
        self.rowcount = 0

    def execute(self, _sql: str, params: tuple[object, ...]) -> None:
        key = (int(params[0]), int(params[1]))
        if key in self.conflicting:
            self.rowcount = 0
            return
        self.inserted.append(key)
        self.rowcount = 1
