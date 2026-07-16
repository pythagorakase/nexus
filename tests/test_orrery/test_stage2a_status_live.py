"""Rollback-only PostgreSQL coverage for Stage 2a status producers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from nexus.agents.orrery.resolver import hydrate_world_state
from nexus.agents.orrery.retrograde_expansion import (
    RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
)
from nexus.agents.orrery.retrograde_maturation import (
    enqueue_declared_entity_maturations,
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
from nexus.agents.orrery.substrate import Slot, has_any_status_at_or_above
from nexus.agents.orrery.tag_writer import apply_status_pair_tag_bestowal
from nexus.api.slot_utils import get_slot_db_url, slot_dbname


pytestmark = pytest.mark.requires_postgres

LIVE_SLOT = 5
ENABLED_MATURATION = {"orrery": {"retrograde": {"maturation": {"enabled": True}}}}


@pytest.fixture()
def live_transaction() -> Iterator[tuple[Connection, Session, Any]]:
    """One real slot transaction shared by SQLAlchemy and psycopg2 calls."""

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    raw_connection = connection.connection.driver_connection
    try:
        yield connection, session, raw_connection
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _active_faction(session: Session) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                """
                SELECT f.id AS faction_id, f.entity_id, f.name
                FROM factions f
                JOIN entities e ON e.id = f.entity_id
                WHERE f.entity_id IS NOT NULL AND e.is_active
                ORDER BY f.id
                LIMIT 1
                """
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


def _insert_subject(session: Session, *, name: str) -> int:
    entity_id = int(
        session.execute(
            text(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('character', true)
                RETURNING id
                """
            )
        ).scalar_one()
    )
    session.execute(
        text(
            """
            INSERT INTO characters (name, entity_id)
            VALUES (:name, :entity_id)
            """
        ),
        {"name": name, "entity_id": entity_id},
    )
    return entity_id


def _retrograde_inputs(
    *,
    subject_name: str,
    faction_name: str,
    status_tag: str,
    token: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    vocabulary: SeedEligibleVocabulary = enumerate_seed_eligible_vocabulary(
        slot_dbname(LIVE_SLOT)
    )
    request = build_seed_generation_request(
        candidate_scaffolds={
            "core_entities": [
                {
                    "kind": "character",
                    "role": "protagonist",
                    "name": subject_name,
                    "summary": "A rollback-only status fixture.",
                },
                {
                    "kind": "faction",
                    "role": "institution",
                    "name": faction_name,
                    "summary": "The scope faction for the fixture.",
                },
            ],
            "named_seed_npcs": [],
            "pressure_axes": [],
            "trait_hooks": {},
        },
        vocabulary=vocabulary,
        weird={"level": "medium", "genre": "test", "raw_midpoint": 0.5},
        rng_seed_material=f"stage2a-status-{token}",
    )
    edge = request["candidate_graph"]["dangling_edges"][0]
    event_type = (
        "threat_issued"
        if "threat_issued" in vocabulary["event_types"]
        else vocabulary["event_types"][0]
    )
    seed_response = {
        "schema_version": SEED_CANDIDATE_RESPONSE_SCHEMA_VERSION,
        "candidates": [
            {
                "seed_id": "seed_001",
                "summary": "The institution fixed the subject's standing.",
                "origin_friction": "medium",
                "present_leaf_anchor": "That standing remains in force.",
                "coverage_functions": ["hidden_truth"],
                "mechanical_hints": {
                    "events": [
                        {
                            "event_ref": "seed_event_001",
                            "event_type": event_type,
                            "summary": "The institution judged the subject.",
                            "participating_entities": [subject_name, faction_name],
                        }
                    ],
                    "single_entity_tags": [],
                    "pair_tags": [
                        {
                            "subject_ref": subject_name,
                            "subject_kind": "character",
                            "tag": status_tag,
                            "object_ref": faction_name,
                            "object_kind": "faction",
                        }
                    ],
                    "relationships": [],
                },
                "defer_or_reject_if": [],
                "claimed_edges": [
                    {
                        "edge_id": edge["edge_id"],
                        "open_endpoint_name": f"Fixture Edge {token[:8]}",
                        "open_endpoint_kind": edge["open_endpoint_kind"],
                    }
                ],
            }
        ],
        "selected_seed_ids": ["seed_001"],
        "rejected_seed_ids": [],
    }
    event_ref = f"maturation_job_991_status_{token}"
    expansion = {
        "schema_version": RETROGRADE_EXPANSION_RESPONSE_SCHEMA_VERSION,
        "selected_seed_ids": ["seed_001"],
        "event_plan": [
            {
                "event_ref": event_ref,
                "seed_ids": ["seed_001"],
                "event_type": event_type,
                "summary": "The institution fixed the subject's standing.",
                "chronology": "recent_past",
                "participants": [
                    {
                        "entity_ref": subject_name,
                        "entity_kind": "character",
                        "role": "actor",
                    },
                    {
                        "entity_ref": faction_name,
                        "entity_kind": "faction",
                        "role": "target",
                    },
                ],
                "location_ref": None,
                "changed_fields": ["entity_pair_tags"],
                "magnitude": 0.5,
                "payload": {"source": "stage2a_status_live"},
            }
        ],
        "entity_tag_plan": [],
        "pair_tag_plan": [
            {
                "subject_ref": subject_name,
                "subject_kind": "character",
                "tag": status_tag,
                "object_ref": faction_name,
                "object_kind": "faction",
                "source_event_ref": event_ref,
                "rationale": "The final institutional standing.",
            }
        ],
        "relationship_plan": [],
        "death_plan": [],
        "thread_plan": [
            {
                "seed_id": "seed_001",
                "status": "woven",
                "event_refs": [event_ref],
                "present_leaf_anchor": "That standing remains in force.",
            }
        ],
        "coverage_notes": ["Status fixture."],
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
    return (
        {"seed_generation_request": request, "seed_eligible_vocabulary": vocabulary},
        seed_response,
        expansion,
    )


def test_retrograde_institutional_standing_persists_status_edge(
    live_transaction: tuple[Connection, Session, Any],
) -> None:
    """The public Retrograde path writes status and complete provenance."""

    _connection, session, raw_connection = live_transaction
    token = uuid4().hex[:12]
    subject_name = f"stage2a-retrograde-{token}"
    subject_entity_id = _insert_subject(session, name=subject_name)
    faction = _active_faction(session)
    chunk_id = int(
        session.execute(text("SELECT max(id) FROM narrative_chunks")).scalar_one()
    )
    packet, seed_response, expansion = _retrograde_inputs(
        subject_name=subject_name,
        faction_name=str(faction["name"]),
        status_tag="status:pariah",
        token=token,
    )

    with raw_connection.cursor() as cur:
        dry_plan = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=expansion,
            slot=LIVE_SLOT,
            dbname=slot_dbname(LIVE_SLOT),
            dry_run=True,
            summaries_enabled=False,
            recorded_at_chunk_id=chunk_id,
        )
        assert dry_plan["pair_tag_rows"][0]["status"] == "would_insert"
        assert dry_plan["counters"]["pair_tags_would_insert"] == 1

        applied_plan = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=expansion,
            slot=LIVE_SLOT,
            dbname=slot_dbname(LIVE_SLOT),
            dry_run=False,
            summaries_enabled=False,
            recorded_at_chunk_id=chunk_id,
        )
        planned = applied_plan["pair_tag_rows"][0]
        assert planned["status"] == "inserted"
        assert applied_plan["counters"]["pair_tags_inserted"] == 1
        cur.execute(
            """
            SELECT ept.subject_entity_id, ept.object_entity_id, pt.tag,
                   ept.source_kind::text, ept.template_id, ept.source_chunk_id
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.id = %s
            """,
            (planned["entity_pair_tag_id"],),
        )
        row = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM tag_clearance_log WHERE entity_pair_tag_id = %s",
            (planned["entity_pair_tag_id"],),
        )
        assert cur.fetchone()[0] == 0

        assert apply_status_pair_tag_bestowal(
            cur,
            subject_entity_id=subject_entity_id,
            scope_faction_entity_id=int(faction["entity_id"]),
            subject_kind="character",
            level="senior",
            source_kind="retrograde",
            source_chunk_id=chunk_id,
        )
        cur.execute(
            """
            SELECT source_chunk_id
            FROM tag_clearance_log
            WHERE entity_pair_tag_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (planned["entity_pair_tag_id"],),
        )
        clearance_source_chunk_id = cur.fetchone()[0]

    assert row == (
        subject_entity_id,
        int(faction["entity_id"]),
        "status:pariah",
        "retrograde",
        f"retrograde:{expansion['event_plan'][0]['event_ref']}",
        chunk_id,
    )
    assert clearance_source_chunk_id == chunk_id


def test_retrograde_status_skips_existing_live_standing_with_dry_run_parity(
    live_transaction: tuple[Connection, Session, Any],
) -> None:
    """Backstory never clears or replaces an active present-day status."""

    _connection, session, raw_connection = live_transaction
    token = uuid4().hex[:12]
    subject_name = f"stage2a-existing-{token}"
    subject_entity_id = _insert_subject(session, name=subject_name)
    faction = _active_faction(session)
    chunk_id = int(
        session.execute(text("SELECT max(id) FROM narrative_chunks")).scalar_one()
    )
    packet, seed_response, expansion = _retrograde_inputs(
        subject_name=subject_name,
        faction_name=str(faction["name"]),
        status_tag="status:pariah",
        token=token,
    )

    with raw_connection.cursor() as cur:
        assert apply_status_pair_tag_bestowal(
            cur,
            subject_entity_id=subject_entity_id,
            scope_faction_entity_id=int(faction["entity_id"]),
            subject_kind="character",
            level="senior",
            source_chunk_id=chunk_id,
        )
        cur.execute("SELECT count(*) FROM tag_clearance_log")
        clearance_count_before = int(cur.fetchone()[0])
        dry_plan = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=expansion,
            slot=LIVE_SLOT,
            dbname=slot_dbname(LIVE_SLOT),
            dry_run=True,
            summaries_enabled=False,
            recorded_at_chunk_id=chunk_id,
        )
        applied_plan = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=expansion,
            slot=LIVE_SLOT,
            dbname=slot_dbname(LIVE_SLOT),
            dry_run=False,
            summaries_enabled=False,
            recorded_at_chunk_id=chunk_id,
        )
        cur.execute(
            """
            SELECT pt.tag
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.subject_entity_id = %s
              AND ept.object_entity_id = %s
              AND pt.tag LIKE 'status:%%'
              AND ept.cleared_at IS NULL
            """,
            (subject_entity_id, int(faction["entity_id"])),
        )
        active_tags = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT count(*) FROM tag_clearance_log")
        clearance_count_after = int(cur.fetchone()[0])

    assert dry_plan["pair_tag_rows"][0]["status"] == (
        "would_skip_existing_active_status"
    )
    assert applied_plan["pair_tag_rows"][0]["status"] == (
        "skipped_existing_active_status"
    )
    assert dry_plan["counters"]["pair_tags_would_skip_existing_active_status"] == 1
    assert applied_plan["counters"]["pair_tags_skipped_existing_active_status"] == 1
    assert active_tags == ["status:senior"]
    assert clearance_count_after == clearance_count_before


def test_wizard_time_retrograde_status_keeps_source_chunk_null(
    live_transaction: tuple[Connection, Session, Any],
) -> None:
    """Pre-ledger wizard history does not borrow the prologue anchor as source."""

    _connection, session, raw_connection = live_transaction
    token = uuid4().hex[:12]
    subject_name = f"stage2a-wizard-{token}"
    _insert_subject(session, name=subject_name)
    faction = _active_faction(session)
    packet, seed_response, expansion = _retrograde_inputs(
        subject_name=subject_name,
        faction_name=str(faction["name"]),
        status_tag="status:junior",
        token=token,
    )

    with raw_connection.cursor() as cur:
        plan = build_retrograde_persistence_plan(
            cur,
            packet=packet,
            seed_candidate_response=seed_response,
            expansion_plan_payload=expansion,
            slot=LIVE_SLOT,
            dbname=slot_dbname(LIVE_SLOT),
            dry_run=False,
            summaries_enabled=False,
            recorded_at_chunk_id=None,
        )
        row_id = int(plan["pair_tag_rows"][0]["entity_pair_tag_id"])
        cur.execute(
            "SELECT source_chunk_id FROM entity_pair_tags WHERE id = %s",
            (row_id,),
        )
        source_chunk_id = cur.fetchone()[0]

    assert plan["pair_tag_rows"][0]["status"] == "inserted"
    assert source_chunk_id is None


def test_declaration_status_hint_applies_and_hydrates_for_predicate(
    live_transaction: tuple[Connection, Session, Any],
) -> None:
    """A storyteller declaration hint becomes a hydrated status edge."""

    _connection, session, raw_connection = live_transaction
    faction = _active_faction(session)
    chunk_id = int(
        session.execute(text("SELECT max(id) FROM narrative_chunks")).scalar_one()
    )
    name = f"stage2a-declaration-{uuid4().hex[:12]}"
    result = enqueue_declared_entity_maturations(
        raw_connection,
        declarations=[
            {
                "kind": "character",
                "name": name,
                "summary": "A newly accepted junior of the institution.",
                "pair_tag_hints": [
                    {
                        "tag": "status:junior",
                        "other_entity_name": faction["name"],
                        "declared_entity_role": "subject",
                    }
                ],
            }
        ],
        chunk_id=chunk_id,
        raw_text=f"{name} presents their credentials.",
        slot=LIVE_SLOT,
        settings=ENABLED_MATURATION,
    )
    assert result.stubs_created == 1
    subject_entity_id = int(
        session.execute(
            text("SELECT entity_id FROM characters WHERE name = :name"),
            {"name": name},
        ).scalar_one()
    )
    edge = (
        session.execute(
            text(
                """
                SELECT ept.subject_entity_id, ept.object_entity_id,
                       pt.tag, ept.source_kind::text AS source_kind
                FROM entity_pair_tags ept
                JOIN pair_tags pt ON pt.id = ept.pair_tag_id
                WHERE ept.subject_entity_id = :subject
                  AND ept.object_entity_id = :object
                  AND pt.tag = 'status:junior'
                  AND ept.cleared_at IS NULL
                """
            ),
            {
                "subject": subject_entity_id,
                "object": int(faction["entity_id"]),
            },
        )
        .mappings()
        .one()
    )
    assert dict(edge) == {
        "subject_entity_id": subject_entity_id,
        "object_entity_id": int(faction["entity_id"]),
        "tag": "status:junior",
        "source_kind": "skald_inline",
    }

    state = hydrate_world_state(
        session,
        anchor_chunk_id=chunk_id,
        window_chunks=0,
        world_time_override=datetime(2073, 8, 1, tzinfo=timezone.utc),
        epistemics_settings={"enabled": False},
    )
    assert has_any_status_at_or_above("junior")(
        state,
        {Slot.ACTOR: subject_entity_id},
    )
