"""Tests for Retrograde expansion persistence planning."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Optional

import pytest

from nexus.agents.orrery.retrograde_expansion import (
    RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
)
from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
from nexus.agents.orrery.retrograde_persistence import (
    build_retrograde_persistence_plan,
    plan_retrograde_summaries,
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
    assert plan["counters"]["summaries_inserted"] == 1
    assert any("insert_prologue_chunk" in sql for sql in cur.statements)
    assert any("insert_world_event" in sql for sql in cur.statements)
    assert any("insert_entity_tag" in sql for sql in cur.statements)
    assert any("insert_pair_tag" in sql for sql in cur.statements)
    assert any("insert_character_relationship" in sql for sql in cur.statements)
    assert any("insert_summary" in sql for sql in cur.statements)
    summary_row = plan["summary_rows"][0]
    assert summary_row["status"] == "inserted"
    assert summary_row["summary_id"] == 951
    assert summary_row["recorded_at_chunk_id"] == 900
    assert summary_row["embedding_pending"] is True
    assert plan["retrieval"]["embedding_pending_summary_ids"] == [951]


def test_persistence_dry_run_plans_summaries() -> None:
    """Dry-run reports a dedicated summary per planned event."""

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

    assert plan["counters"]["summaries_would_insert"] == 1
    summary_row = plan["summary_rows"][0]
    assert summary_row["event_ref"] == "retro_event_001"
    assert summary_row["status"] == "would_insert"
    assert summary_row["summary_id"] is None
    assert summary_row["embedding_pending"] is True
    assert plan["retrieval"]["summaries_enabled"] is True
    assert plan["retrieval"]["embedding_pending_summary_ids"] == []
    assert not any("insert_summary" in sql for sql in cur.statements)


def test_persistence_summaries_can_be_disabled() -> None:
    """The retrieval surface toggle suppresses summary planning."""

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
        summaries_enabled=False,
    )

    assert plan["summary_rows"] == []
    assert plan["counters"]["summaries_would_insert"] == 0
    assert plan["retrieval"]["summaries_enabled"] is False
    assert not any("summary_lookup" in sql for sql in cur.statements)


def test_persistence_summaries_idempotent_when_embedded() -> None:
    """Existing embedded summaries are reported without re-pending."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        existing_summaries=[
            {
                "id": 940,
                "recorded_at_chunk_id": 900,
                "chronology": "recent_past",
                "summary_text": (
                    "The handler died before clearing Mara's inherited debt."
                ),
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

    summary_row = plan["summary_rows"][0]
    assert summary_row["status"] == "already_present"
    assert summary_row["summary_id"] == 940
    assert summary_row["embedding_pending"] is False
    assert plan["retrieval"]["embedding_pending_summary_ids"] == []


def test_plan_summaries_from_persisted_events() -> None:
    """The DB-driven path backfills dedicated rows for persisted events."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        persisted_retrograde_events=[
            {
                "world_event_id": 107,
                "event_ref": "r6_e01_vale_debt_spliced",
                "summary": "A debt broker spliced Vale's escape account onto "
                "Mara's first safe alias.",
                "chronology": "deep_past",
                "existing_recorded_at_chunk_id": 88,
            }
        ],
    )

    rows = plan_retrograde_summaries(cur, dry_run=False)

    assert len(rows) == 1
    assert rows[0]["status"] == "inserted"
    assert rows[0]["summary_id"] == 951
    assert rows[0]["world_event_id"] == 107
    assert rows[0]["recorded_at_chunk_id"] == 88
    assert rows[0]["embedding_pending"] is True
    assert any("insert_summary" in sql for sql in cur.statements)


def test_plan_summaries_requires_summary_text() -> None:
    """Events without summary prose fail loudly instead of embedding stubs."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        persisted_retrograde_events=[
            {
                "world_event_id": 107,
                "event_ref": "r6_e01_vale_debt_spliced",
                "summary": "",
                "chronology": "deep_past",
                "existing_recorded_at_chunk_id": 88,
            }
        ],
    )

    with pytest.raises(ValueError, match="has no summary text"):
        plan_retrograde_summaries(cur, dry_run=False)


def test_plan_summaries_derives_content_from_canonical_world_event() -> None:
    """An id-only source writes the canonical event payload, never caller prose."""

    vocabulary = _persistence_test_vocabulary()
    canonical_summary = "Vale's canonical debt history survived the splice."
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        canonical_world_events=[
            {
                "world_event_id": 107,
                "source_kind": "retrograde",
                "event_ref": "r6_e01_vale_debt_spliced",
                "summary": canonical_summary,
                "chronology": "deep_past",
            }
        ],
    )

    rows = plan_retrograde_summaries(
        cur,
        dry_run=False,
        recorded_at_chunk_id=88,
        event_sources=[{"world_event_id": 107}],
    )

    assert rows[0]["event_ref"] == "r6_e01_vale_debt_spliced"
    assert rows[0]["status"] == "inserted"
    insert_params = [
        params
        for sql, params in zip(cur.statements, cur.params)
        if "orrery:retrograde:insert_summary" in sql
    ]
    assert insert_params == [(107, 88, "deep_past", canonical_summary)]


@pytest.mark.parametrize("field", ["event_ref", "summary", "chronology"])
def test_plan_summaries_rejects_incoming_canonical_payload_divergence(
    field: str,
) -> None:
    """Supplied rerun content must exactly match the canonical event payload."""

    vocabulary = _persistence_test_vocabulary()
    canonical = {
        "world_event_id": 107,
        "source_kind": "retrograde",
        "event_ref": "r6_e01_vale_debt_spliced",
        "summary": "Vale's canonical debt history survived the splice.",
        "chronology": "deep_past",
    }
    incoming = {
        "world_event_id": 107,
        "event_ref": canonical["event_ref"],
        "summary": canonical["summary"],
        "chronology": canonical["chronology"],
    }
    incoming[field] = f"contradictory_{field}"
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        canonical_world_events=[canonical],
    )

    with pytest.raises(
        ValueError,
        match=rf"diverges from canonical world_events.payload fields: {field}",
    ):
        plan_retrograde_summaries(
            cur,
            dry_run=False,
            recorded_at_chunk_id=88,
            event_sources=[incoming],
        )

    assert not any("orrery:retrograde:insert_summary" in sql for sql in cur.statements)


def test_plan_summaries_rejects_non_retrograde_world_event_source() -> None:
    """A world-event id from another provenance cannot acquire a summary row."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        canonical_world_events=[
            {
                "world_event_id": 107,
                "source_kind": "resolver",
                "event_ref": "resolver_event_107",
                "summary": "A resolver-owned event.",
                "chronology": "recent_past",
            }
        ],
    )

    with pytest.raises(ValueError, match="source mismatch.*expected 'retrograde'"):
        plan_retrograde_summaries(
            cur,
            dry_run=False,
            recorded_at_chunk_id=88,
            event_sources=[{"world_event_id": 107}],
        )

    assert not any("orrery:retrograde:insert_summary" in sql for sql in cur.statements)


def test_existing_event_rerun_cannot_seed_summary_from_new_plan_content() -> None:
    """The high-level caller also rejects contradictory rerun summary prose."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(
        vocabulary,
        canonical_world_events=[
            {
                "world_event_id": 901,
                "source_kind": "retrograde",
                "event_ref": "retro_event_001",
                "summary": "The canonical handler history remains unchanged.",
                "chronology": "recent_past",
            }
        ],
    )

    with pytest.raises(
        ValueError,
        match="diverges from canonical world_events.payload fields: summary",
    ):
        build_retrograde_persistence_plan(
            cur,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
            expansion_plan_payload=_valid_expansion(vocabulary),
            slot=5,
            dbname="save_05",
            dry_run=True,
        )

    assert not any("orrery:retrograde:insert_summary" in sql for sql in cur.statements)


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


def test_persistence_death_of_preexisting_entity_blocks() -> None:
    """A death naming a live pre-existing entity is a blocker, never a write.

    Runtime maturation persists with dry_run=False; without this gate a
    Skald-emitted death could deactivate an entity currently on stage.
    """

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=_expansion_with_death(vocabulary),
        slot=5,
        dbname="save_05",
        dry_run=True,
    )

    assert plan["counters"]["deaths_blocked"] == 1
    assert plan["death_rows"][0]["status"] == "blocked"
    assert "death_targets_preexisting_entity" in _blocker_ids(plan)

    with pytest.raises(ValueError, match="not safe to execute"):
        build_retrograde_persistence_plan(
            cur,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
            expansion_plan_payload=_expansion_with_death(vocabulary),
            slot=5,
            dbname="save_05",
            dry_run=False,
        )
    assert cur.deactivated_entity_ids == []


def test_persistence_execute_deactivates_staged_stub() -> None:
    """Execute stages the backstory figure's stub, then flips it inactive."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=_expansion_with_death(vocabulary, dead_ref="Old Kessa"),
        slot=5,
        dbname="save_05",
        dry_run=False,
        create_missing_entities=True,
    )

    assert cur.inserted_character_stubs == ["Old Kessa"]
    assert plan["counters"]["deaths_deactivated"] == 1
    death_row = plan["death_rows"][0]
    assert death_row["status"] == "deactivated"
    assert death_row["cause_world_event_id"] == 901
    assert cur.deactivated_entity_ids == [300]
    assert cur.entity_activity_projections == [
        {
            "entity_id": 300,
            "source_chunk_id": 900,
            "world_event_id": 901,
        }
    ]


def test_persistence_death_already_inactive_is_idempotent() -> None:
    """Re-running a plan against a dead entity reports instead of rewriting."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary, inactive_entity_ids={102})

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=_expansion_with_death(vocabulary),
        slot=5,
        dbname="save_05",
        dry_run=False,
    )

    assert plan["counters"]["deaths_already_inactive"] == 1
    assert plan["death_rows"][0]["status"] == "already_inactive"
    assert cur.deactivated_entity_ids == []


def test_persistence_death_of_unresolved_entity_blocks_execute() -> None:
    """A death naming an unknown entity is a blocker, never a silent skip."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    expansion = _expansion_with_death(
        vocabulary,
        dead_ref="Ghost Stranger",
    )

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=expansion,
        slot=5,
        dbname="save_05",
        dry_run=True,
    )

    assert plan["counters"]["deaths_blocked"] == 1
    assert "unresolved_or_ambiguous_entity_refs" in _blocker_ids(plan)

    with pytest.raises(ValueError, match="not safe to execute"):
        build_retrograde_persistence_plan(
            cur,
            packet=_packet(vocabulary),
            seed_candidate_response=_seed_response(vocabulary),
            expansion_plan_payload=expansion,
            slot=5,
            dbname="save_05",
            dry_run=False,
        )
    assert cur.deactivated_entity_ids == []


def test_persistence_death_of_staged_stub_plans_deactivation() -> None:
    """A dead entity created by this very plan still gets its kill switch."""

    vocabulary = _persistence_test_vocabulary()
    cur = FakeRetrogradePersistenceCursor(vocabulary)
    expansion = _expansion_with_death(
        vocabulary,
        dead_ref="Old Kessa",
    )

    plan = build_retrograde_persistence_plan(
        cur,
        packet=_packet(vocabulary),
        seed_candidate_response=_seed_response(vocabulary),
        expansion_plan_payload=expansion,
        slot=5,
        dbname="save_05",
        dry_run=True,
        create_missing_entities=True,
    )

    assert plan["counters"]["deaths_would_deactivate"] == 1
    death_row = plan["death_rows"][0]
    assert death_row["status"] == "would_deactivate"
    assert death_row["entity"]["resolution"] == "stub_pending"
    assert "unresolved_or_ambiguous_entity_refs" not in _blocker_ids(plan)


class FakeRetrogradePersistenceCursor:
    """Minimal DB cursor double for Retrograde persistence dry-runs."""

    def __init__(
        self,
        vocabulary: SeedEligibleVocabulary,
        *,
        omit_place: bool = False,
        include_retrograde_sources: bool = True,
        omit_first_event_type: bool = False,
        existing_summaries: Optional[list[dict[str, Any]]] = None,
        persisted_retrograde_events: Optional[list[dict[str, Any]]] = None,
        canonical_world_events: Optional[list[dict[str, Any]]] = None,
        inactive_entity_ids: Optional[set[int]] = None,
    ) -> None:
        self.vocabulary = vocabulary
        self.omit_place = omit_place
        self.include_retrograde_sources = include_retrograde_sources
        self.omit_first_event_type = omit_first_event_type
        self.existing_summaries = existing_summaries or []
        self.persisted_retrograde_events = persisted_retrograde_events or []
        canonical_rows = [
            {
                "world_event_id": row["world_event_id"],
                "source_kind": row.get("source_kind", "retrograde"),
                "event_ref": row.get("event_ref"),
                "summary": row.get("summary"),
                "chronology": row.get("chronology"),
            }
            for row in self.persisted_retrograde_events
        ]
        canonical_rows.extend(canonical_world_events or [])
        if self.existing_summaries and not canonical_rows:
            canonical_rows.append(
                {
                    "world_event_id": 901,
                    "source_kind": "retrograde",
                    "event_ref": "retro_event_001",
                    "summary": (
                        "The handler died before clearing Mara's inherited debt."
                    ),
                    "chronology": "recent_past",
                }
            )
        self.canonical_world_events = {
            int(row["world_event_id"]): dict(row) for row in canonical_rows
        }
        self.inactive_entity_ids = set(inactive_entity_ids or set())
        self.deactivated_entity_ids: list[int] = []
        self.entity_activity_projections: list[dict[str, int]] = []
        self.inserted_character_stubs: list[str] = []
        self.statements: list[str] = []
        self.params: list[Any] = []
        self._result: list[dict[str, Any]] = []
        self._summary_seq = 950

    def execute(self, sql: str, params: Optional[Any] = None) -> None:
        self.statements.append(sql)
        self.params.append(params)
        if "orrery:retrograde:genesis_invariant" in sql:
            self._result = []
        elif "orrery:retrograde:prologue_chunk" in sql:
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
            for offset, name in enumerate(self.inserted_character_stubs):
                rows.append(
                    {
                        "entity_id": 300 + offset,
                        "entity_kind": "character",
                        "name": name,
                        "character_id": 30 + offset,
                        "faction_id": None,
                        "place_id": None,
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
            assert params is not None
            event_ref = str(params[0])
            matching_ids = [
                world_event_id
                for world_event_id, row in self.canonical_world_events.items()
                if row["source_kind"] == "retrograde" and row["event_ref"] == event_ref
            ]
            self._result = [{"id": min(matching_ids)}] if matching_ids else []
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
            assert params is not None
            payload = json.loads(str(params[7]))
            self.canonical_world_events[901] = {
                "world_event_id": 901,
                "source_kind": "retrograde",
                "event_ref": payload["retrograde_event_ref"],
                "summary": payload["summary"],
                "chronology": payload["chronology"],
            }
            self._result = [{"id": 901}]
        elif "orrery:retrograde:insert_entity_tag" in sql:
            self._result = [{"id": 902}]
        elif "orrery:retrograde:insert_pair_tag" in sql:
            self._result = [{"id": 903}]
        elif "orrery:retrograde:insert_character_relationship" in sql:
            self._result = []
        elif "orrery:retrograde:canonical_world_event_source" in sql:
            assert params is not None
            row = self.canonical_world_events.get(int(params[0]))
            self._result = [row] if row is not None else []
        elif "orrery:retrograde:summary_lookup" in sql:
            self._result = list(self.existing_summaries)
        elif "orrery:retrograde:insert_summary" in sql:
            self._summary_seq += 1
            self._result = [{"id": self._summary_seq}]
        elif "orrery:retrograde:persisted_retrograde_events" in sql:
            self._result = list(self.persisted_retrograde_events)
        elif "orrery:retrograde:insert_character_stub" in sql:
            assert params is not None
            self.inserted_character_stubs.append(str(params[0]))
            self._result = []
        elif "orrery:retrograde:entity_is_active" in sql:
            assert params is not None
            entity_id = int(params[0])
            self._result = [{"is_active": entity_id not in self.inactive_entity_ids}]
        elif "orrery:retrograde:deactivate_entity" in sql:
            assert params is not None
            entity_id = int(params[0])
            self.deactivated_entity_ids.append(entity_id)
            self.inactive_entity_ids.add(entity_id)
            self._result = []
        elif "orrery:retrograde:record_entity_activity" in sql:
            assert params is not None
            self.entity_activity_projections.append(
                {
                    "entity_id": int(params[0]),
                    "source_chunk_id": int(params[1]),
                    "world_event_id": int(params[2]),
                }
            )
            self._result = [{"id": int(params[2])}]
        elif "SELECT to_regclass" in sql:
            self._result = [{"checkpoint_table": "backstory_secrets"}]
        elif "jsonb_agg(to_jsonb(t))" in sql:
            self._result = [{"state": []}]
        elif "INSERT INTO state_checkpoints" in sql:
            self._result = [{"id": 904}]
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


def _first_edge_claims(vocabulary: SeedEligibleVocabulary) -> list[dict[str, Any]]:
    request = _packet(vocabulary)["seed_generation_request"]
    edge = request["candidate_graph"]["dangling_edges"][0]
    return [
        {
            "edge_id": edge["edge_id"],
            "open_endpoint_name": "The Salt Ledger",
            "open_endpoint_kind": edge["open_endpoint_kind"],
        }
    ]


def _seed_response(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
    response = _seed_response_base(vocabulary)
    claims = _first_edge_claims(vocabulary)
    for candidate in response.get("candidates", []):
        candidate.setdefault("claimed_edges", claims)
    return response


def _seed_response_base(vocabulary: SeedEligibleVocabulary) -> dict[str, Any]:
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


def _expansion_with_death(
    vocabulary: SeedEligibleVocabulary,
    *,
    dead_ref: str = "Vale",
) -> dict[str, Any]:
    expansion = _valid_expansion(vocabulary)
    participants = expansion["event_plan"][0]["participants"]
    if not any(p["entity_ref"] == dead_ref for p in participants):
        participants.append(
            {"entity_ref": dead_ref, "entity_kind": "character", "role": "target"}
        )
    expansion["death_plan"] = [
        {
            "entity_ref": dead_ref,
            "entity_kind": "character",
            "cause_event_ref": "retro_event_001",
        }
    ]
    return expansion


def _blocker_ids(plan: dict[str, Any]) -> set[str]:
    return {blocker["id"] for blocker in plan["execute_blockers"]}
