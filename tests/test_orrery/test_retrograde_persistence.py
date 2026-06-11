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
    plan_retrograde_summary_chunks,
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
    assert plan["counters"]["relationships_would_insert"] == 1
    assert plan["event_rows"][0]["actor_entity_id"] == 101
    assert plan["event_rows"][0]["location_id"] == 2011
    assert plan["entity_tag_rows"][0]["source_kind"] == "retrograde"
    assert plan["relationship_rows"][0]["status"] == "would_insert"
    assert _blocker_ids(plan) == set()


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


def test_persistence_plan_can_stage_missing_entity_stubs() -> None:
    """Opt-in stub staging lets missing exact refs stop blocking dry-runs."""

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
        create_missing_entities=True,
    )

    assert plan["counters"]["entity_stubs_would_insert"] == 1
    assert plan["counters"]["events_would_insert"] == 1
    assert plan["counters"]["pair_tags_would_insert"] == 1
    assert {row["entity_ref"]: row["status"] for row in plan["entity_stub_rows"]} == {
        "Mara": "already_present",
        "Shutter Hall": "would_insert",
        "Vale": "already_present",
    }
    assert plan["event_rows"][0]["location"]["resolution"] == "stub_pending"
    assert plan["pair_tag_rows"][0]["object"]["resolution"] == "stub_pending"
    assert "unresolved_or_ambiguous_entity_refs" not in _blocker_ids(plan)
    assert _blocker_ids(plan) == set()


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


def test_persistence_plan_counts_vocabulary_blocked_events() -> None:
    """Dry-runs do not count vocabulary-invalid events as would-insert rows."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary, omit_first_event_type=True)

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
    assert plan["counters"]["events_would_insert"] == 0
    assert "missing_slot_vocabulary" in _blocker_ids(plan)


def test_persistence_plan_blocks_entity_kind_incompatible_tags() -> None:
    """Registered tag names still have to fit the target entity kind.

    The packet vocabulary deliberately claims place-applicability for
    "grieving" (simulating packet/registry drift) so the plan passes R6
    validation and the persistence-side applicability gate stays exercised
    as the second line of defense.
    """

    vocabulary = _persistence_test_vocabulary()
    vocabulary["registered_tags_by_entity_kind"] = {
        "character": ["grieving", "scholar", "untested_signal"],
        "place": ["grieving"],
        "faction": [],
    }
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    expansion = _valid_expansion(vocabulary)
    expansion["entity_tag_plan"][0] = {
        "entity_ref": "Shutter Hall",
        "entity_kind": "place",
        "tag": "grieving",
        "source_event_ref": "retro_event_001",
    }

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=expansion,
        slot=5,
        dbname="save_05",
        dry_run=True,
    )

    assert plan["counters"]["entity_tags_blocked"] == 1
    assert plan["counters"]["entity_tags_would_insert"] == 1
    assert "missing_slot_vocabulary" in _blocker_ids(plan)
    assert any(
        issue["value"] == "grieving"
        and issue["entity_kind"] == "place"
        and issue["reason"] == "tag category is not registered for this entity kind"
        for issue in plan["vocabulary_issues"]
    )


def test_persistence_execute_writes_canonical_rows() -> None:
    """Execute mode reaches the canonical write helpers when blockers are clear."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=_valid_expansion(vocabulary),
        slot=5,
        dbname="save_05",
        dry_run=False,
    )

    assert plan["prologue_anchor"]["status"] == "inserted"
    assert plan["counters"]["events_inserted"] == 1
    assert plan["counters"]["entity_tags_inserted"] == 2
    assert plan["counters"]["pair_tags_inserted"] == 1
    assert plan["counters"]["relationships_inserted"] == 1
    assert plan["counters"]["summary_chunks_inserted"] == 1
    assert any("insert_prologue_chunk" in sql for sql in cur.statements)
    assert any("insert_world_event" in sql for sql in cur.statements)
    assert any("insert_entity_tag" in sql for sql in cur.statements)
    assert any("insert_pair_tag" in sql for sql in cur.statements)
    assert any("insert_character_relationship" in sql for sql in cur.statements)
    assert any("insert_summary_chunk" in sql for sql in cur.statements)
    assert any("insert_summary_metadata" in sql for sql in cur.statements)
    assert any("link_summary_chunk" in sql for sql in cur.statements)
    summary_row = plan["summary_chunk_rows"][0]
    assert summary_row["status"] == "inserted"
    assert summary_row["chunk_id"] == 951
    assert summary_row["embedding_pending"] is True
    assert plan["retrieval"]["embedding_pending_chunk_ids"] == [951]


def test_persistence_dry_run_plans_summary_chunks() -> None:
    """Dry-run reports a retrieval summary chunk per planned event."""

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

    assert plan["counters"]["summary_chunks_would_insert"] == 1
    summary_row = plan["summary_chunk_rows"][0]
    assert summary_row["event_ref"] == "retro_event_001"
    assert summary_row["marker"] == "orrery:retrograde_event:retro_event_001"
    assert summary_row["status"] == "would_insert"
    assert summary_row["chunk_id"] is None
    assert summary_row["embedding_pending"] is True
    assert plan["retrieval"]["summary_chunks_enabled"] is True
    assert plan["retrieval"]["embedding_pending_chunk_ids"] == []
    assert not any("insert_summary_chunk" in sql for sql in cur.statements)


def test_persistence_summary_chunks_can_be_disabled() -> None:
    """The retrieval surface toggle suppresses summary chunk planning."""

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
        summary_chunks_enabled=False,
    )

    assert plan["summary_chunk_rows"] == []
    assert plan["counters"]["summary_chunks_would_insert"] == 0
    assert plan["retrieval"]["summary_chunks_enabled"] is False
    assert not any("summary_chunk_lookup" in sql for sql in cur.statements)


def test_persistence_summary_chunks_idempotent_when_embedded() -> None:
    """Existing embedded summary chunks are reported without re-pending."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        existing_summary_chunks=[
            {
                "id": 940,
                "embedding_generated_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
            }
        ],
    )

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=_valid_expansion(vocabulary),
        slot=5,
        dbname="save_05",
        dry_run=True,
    )

    summary_row = plan["summary_chunk_rows"][0]
    assert summary_row["status"] == "already_present"
    assert summary_row["chunk_id"] == 940
    assert summary_row["embedding_pending"] is False
    assert plan["retrieval"]["embedding_pending_chunk_ids"] == []


def test_plan_summary_chunks_from_persisted_events() -> None:
    """The DB-driven path backfills chunks for already-persisted events."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        persisted_retrograde_events=[
            {
                "world_event_id": 107,
                "event_ref": "r6_e01_vale_debt_spliced",
                "summary": "A debt broker spliced Vale's escape account onto "
                "Mara's first safe alias.",
            }
        ],
    )

    rows = plan_retrograde_summary_chunks(cur, dry_run=False)

    assert len(rows) == 1
    assert rows[0]["status"] == "inserted"
    assert rows[0]["chunk_id"] == 951
    assert rows[0]["world_event_id"] == 107
    assert rows[0]["embedding_pending"] is True
    assert any("insert_summary_chunk" in sql for sql in cur.statements)
    assert any("link_summary_chunk" in sql for sql in cur.statements)
    link_params = [
        params
        for sql, params in zip(cur.statements, cur.params)
        if "link_summary_chunk" in sql
    ]
    assert link_params == [(951, 107)]


def test_plan_summary_chunks_requires_summary_text() -> None:
    """Events without summary prose fail loudly instead of embedding stubs."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        persisted_retrograde_events=[
            {
                "world_event_id": 107,
                "event_ref": "r6_e01_vale_debt_spliced",
                "summary": "",
            }
        ],
    )

    with pytest.raises(ValueError, match="has no summary text"):
        plan_retrograde_summary_chunks(cur, dry_run=False)


def test_persistence_execute_rejects_cross_kind_relationship_plan() -> None:
    """Cross-kind relationships are rejected before canonical writes begin."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    expansion = _valid_expansion(vocabulary)
    expansion["relationship_plan"][0] = {
        "subject_ref": "Rain Ledger",
        "subject_kind": "faction",
        "relationship_type": vocabulary["relationship_types"][0],
        "object_ref": "Mara",
        "object_kind": "character",
        "source_event_ref": "retro_event_001",
    }

    with pytest.raises(ValueError, match="must be character->character"):
        build_retrograde_persistence_plan(
            cur,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
            expansion_plan_payload=expansion,
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
        omit_first_event_type: bool = False,
        existing_summary_chunks: Optional[list[dict[str, Any]]] = None,
        persisted_retrograde_events: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.vocabulary = vocabulary
        self.omit_place = omit_place
        self.include_retrograde_sources = include_retrograde_sources
        self.omit_first_event_type = omit_first_event_type
        self.existing_summary_chunks = existing_summary_chunks or []
        self.persisted_retrograde_events = persisted_retrograde_events or []
        self.statements: list[str] = []
        self.params: list[Any] = []
        self._result: list[dict[str, Any]] = []
        self._summary_chunk_seq = 950

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
            event_types = self.vocabulary["event_types"]
            if self.omit_first_event_type:
                event_types = event_types[1:]
            self._result = [{"type": event_type} for event_type in event_types]
        elif "orrery:retrograde:single_entity_tags" in sql:
            self._result = [
                {
                    "id": 1,
                    "tag": "grieving",
                    "category": "state",
                    "entity_kind": "character",
                },
                {
                    "id": 2,
                    "tag": "scholar",
                    "category": "role.function",
                    "entity_kind": "character",
                },
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
        elif "orrery:retrograde:existing_character_relationship" in sql:
            self._result = []
        elif "orrery:retrograde:insert_prologue_chunk" in sql:
            self._result = [{"id": 900}]
        elif "orrery:retrograde:prologue_metadata_exists" in sql:
            self._result = []
        elif "orrery:retrograde:insert_prologue_metadata" in sql:
            self._result = []
        elif "orrery:retrograde:insert_world_event_entity" in sql:
            self._result = []
        elif "orrery:retrograde:insert_world_event" in sql:
            self._result = [{"id": 901}]
        elif "orrery:retrograde:insert_entity_tag" in sql:
            self._result = [{"id": 902}]
        elif "orrery:retrograde:insert_pair_tag" in sql:
            self._result = [{"id": 903}]
        elif "orrery:retrograde:insert_character_relationship" in sql:
            self._result = []
        elif "orrery:retrograde:summary_chunk_lookup" in sql:
            self._result = list(self.existing_summary_chunks)
        elif "orrery:retrograde:summary_scene_base" in sql:
            self._result = [{"next_scene": 1}]
        elif "orrery:retrograde:insert_summary_chunk" in sql:
            self._summary_chunk_seq += 1
            self._result = [{"id": self._summary_chunk_seq}]
        elif "orrery:retrograde:insert_summary_metadata" in sql:
            self._result = []
        elif "orrery:retrograde:link_summary_chunk" in sql:
            self._result = []
        elif "orrery:retrograde:persisted_retrograde_events" in sql:
            self._result = list(self.persisted_retrograde_events)
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
    vocabulary["registered_tags_by_entity_kind"] = {
        "character": ["grieving", "scholar", "untested_signal"],
        "place": [],
        "faction": [],
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
