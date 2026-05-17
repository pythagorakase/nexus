"""Tests for the reviewed slot 2 semantic tag applicator."""

from scripts.apply_slot2_semantic_tags import (
    EntityDefinition,
    TagDefinition,
    _build_candidates,
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
                    {"tag": "contacts_available", "confidence": "low"},
                ],
                "new_tag_proposals": [
                    {"tag": "found_family_anchor", "confidence": "high"},
                    {"tag": "unknown_one_off", "confidence": "high"},
                ],
            },
            {
                "entity_id": 2,
                "entity_kind": "faction",
                "entity_name": "Dynacorp",
                "registered_tag_proposals": [],
                "new_tag_proposals": [
                    {"tag": "militarized", "confidence": "medium"},
                    {"tag": "corporate_exile", "confidence": "high"},
                ],
            },
        ]
    }
    tags = {
        "contacts_available": TagDefinition(
            id=1, category="orrery_state", is_ephemeral=False
        ),
        "corporate_exile": TagDefinition(id=2, category="state", is_ephemeral=False),
        "extended_household": TagDefinition(id=3, category="role", is_ephemeral=False),
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
        entities=entities,
        current=set(),
        min_confidence="medium",
    )

    assert [(candidate.entity_id, candidate.tag) for candidate in candidates] == [
        (1, "extended_household"),
        (2, "militarized"),
    ]
    assert skipped["below_confidence"] == 1
    assert skipped["incompatible_category:orrery_need"] == 1
    assert skipped["incompatible_category:place_affordance"] == 1
    assert skipped["incompatible_category:state"] == 1
    assert skipped["unknown_tag"] == 1
