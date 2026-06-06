"""Tests for Retrograde expansion persistence planning."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from nexus.agents.orrery.retrograde_expansion import (
    RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
)
from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
from nexus.agents.orrery.retrograde_persistence import (
    build_retrograde_persistence_plan,
)
from nexus.agents.orrery.retrograde_seed_candidates import (
    SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)


def test_persistence_plan_resolves_row_shaped_dry_run() -> None:
    """Resolved plans produce dry-run world event, tag, and pair-tag rows."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=_valid_expansion(vocabulary),
        slot=5,
        dbname="save_05",
        dry_run=True,
    )

    assert plan["prologue_anchor"]["status"] == "would_insert"
    assert plan["counters"]["events_would_insert"] == 1
    assert plan["counters"]["entity_tags_would_insert"] == 2
    assert plan["counters"]["pair_tags_would_insert"] == 1
    assert plan["counters"]["relationships_planned_only"] == 1
    assert plan["event_rows"][0]["actor_entity_id"] == 101
    assert plan["event_rows"][0]["location_id"] == 2011
    assert plan["entity_tag_rows"][0]["source_kind"] == "retrograde"
    assert _blocker_ids(plan) == {"relationship_writer_not_available"}


def test_persistence_plan_reports_unresolved_refs() -> None:
    """Prompt-local refs are reported instead of guessed from partial matches."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary, omit_place=True)

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=_valid_expansion(vocabulary),
        slot=5,
        dbname="save_05",
        dry_run=True,
    )

    assert plan["counters"]["events_blocked"] == 1
    assert plan["counters"]["pair_tags_blocked"] == 1
    assert any(
        issue["entity_ref"] == "Shutter Hall" and issue["resolution"] == "unresolved"
        for issue in plan["reference_issues"]
    )
    assert "unresolved_or_ambiguous_entity_refs" in _blocker_ids(plan)


def test_persistence_plan_reports_missing_source_enum_values() -> None:
    """Pre-migration slots dry-run cleanly and surface missing provenance enums."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary, include_retrograde_sources=False)

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=_valid_expansion(vocabulary),
        slot=5,
        dbname="save_05",
        dry_run=True,
    )

    assert {
        "event_source_kind_retrograde",
        "entity_tag_source_kind_retrograde",
    } <= _blocker_ids(plan)


def test_persistence_execute_blocks_relationship_plan_without_writer() -> None:
    """Execution refuses partial canonical writes while relationships are pending."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)

    with pytest.raises(ValueError, match="relationship_plan contains rows"):
        build_retrograde_persistence_plan(
            cur,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
            expansion_plan_payload=_valid_expansion(vocabulary),
            slot=5,
            dbname="save_05",
            dry_run=False,
        )

    assert not any("insert_prologue_chunk" in sql for sql in cur.statements)


class FakeRetrogradePersistenceCursor:
    """Minimal DB cursor double for Retrograde persistence dry-runs."""

    def __init__(
        self,
        vocabulary: SeedEligibleVocabulary,
        *,
        omit_place: bool = False,
        include_retrograde_sources: bool = True,
    ) -> None:
        self.vocabulary = vocabulary
        self.omit_place = omit_place
        self.include_retrograde_sources = include_retrograde_sources
        self.statements: list[str] = []
        self.params: list[Any] = []
        self._result: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Optional[Any] = None) -> None:
        self.statements.append(sql)
        self.params.append(params)
        if "orrery:retrograde:prologue_chunk" in sql:
            self._result = []
        elif "orrery:retrograde:entity_catalog" in sql:
            rows = [
                {
                    "entity_id": 101,
                    "entity_kind": "character",
                    "name": "Mara",
                    "character_id": 11,
                    "faction_id": None,
                    "place_id": None,
                },
                {
                    "entity_id": 102,
                    "entity_kind": "character",
                    "name": "Vale",
                    "character_id": 12,
                    "faction_id": None,
                    "place_id": None,
                },
            ]
            if not self.omit_place:
                rows.append(
                    {
                        "entity_id": 201,
                        "entity_kind": "place",
                        "name": "Shutter Hall",
                        "character_id": None,
                        "faction_id": None,
                        "place_id": 2011,
                    }
                )
            self._result = rows
        elif "orrery:retrograde:event_types" in sql:
            self._result = [
                {"type": event_type} for event_type in self.vocabulary["event_types"]
            ]
        elif "orrery:retrograde:single_entity_tags" in sql:
            self._result = [
                {"id": 1, "tag": "grieving"},
                {"id": 2, "tag": "scholar"},
            ]
        elif "orrery:retrograde:pair_tags" in sql:
            self._result = [{"id": 3, "tag": "knows_location"}]
        elif "orrery:retrograde:enum_values" in sql:
            assert params is not None
            type_name = str(params[0])
            values = {
                "event_source_kind": ["apex", "resolver", "authored"],
                "entity_tag_source_kind": ["authored", "llm_generated", "system"],
            }[type_name]
            if self.include_retrograde_sources:
                values = [*values, "retrograde"]
            self._result = [{"enumlabel": value} for value in values]
        elif "orrery:retrograde:world_time" in sql:
            self._result = [{"world_time": datetime(2026, 1, 1, tzinfo=timezone.utc)}]
        elif "orrery:retrograde:existing_world_event" in sql:
            self._result = []
        elif "orrery:retrograde:active_entity_tag" in sql:
            self._result = []
        elif "orrery:retrograde:active_pair_tag" in sql:
            self._result = []
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._result)

    def fetchone(self) -> Optional[dict[str, Any]]:
        if not self._result:
            return None
        return self._result[0]


def _persistence_test_vocabulary() -> SeedEligibleVocabulary:
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
    return {
        "schema_version": RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
        "selected_seed_ids": ["seed_001"],
        "event_plan": [
            {
                "event_ref": "retro_event_001",
                "seed_ids": ["seed_001"],
                "event_type": vocabulary["event_types"][0],
                "summary": "The handler died before clearing Mara's inherited debt.",
                "chronology": "recent_past",
                "participants": [
                    {
                        "entity_ref": "Mara",
                        "entity_kind": "character",
                        "role": "actor",
                    },
                    {
                        "entity_ref": "Vale",
                        "entity_kind": "character",
                        "role": "target",
                    },
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
                "relationship_type": vocabulary["relationship_types"][0],
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


def _blocker_ids(plan: dict[str, Any]) -> set[str]:
    return {blocker["id"] for blocker in plan["execute_blockers"]}
