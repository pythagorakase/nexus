"""Rollback-only PostgreSQL coverage for Stage 2a Epistemics repairs."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Iterator
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.agents.orrery.epistemics import (
    ClaimParticipant,
    mechanical_claim_summary,
    mint_claim_for_event,
    record_revelation,
)


pytestmark = pytest.mark.requires_postgres

LIVE_DATABASE = "NEXUS_template"
WORLD_TIME = datetime(2073, 8, 1, 15, 30, tzinfo=timezone.utc)
EPISTEMICS = {
    "enabled": True,
    "claim_event_types": ["threat_issued"],
    "aware_roles": ["actor", "target", "observer", "witness"],
}


@pytest.fixture()
def live_conn() -> Iterator[Any]:
    """Use the migrated template in a transaction rolled back after each test."""

    conn = psycopg2.connect(
        dbname=LIVE_DATABASE,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _insert_chunk(cur: Any) -> int:
    token = uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES (%s, %s)
        RETURNING id
        """,
        (f"Stage 2a Epistemics fixture {token}.", "Rollback-only fixture."),
    )
    chunk_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer,
            time_delta, generation_date, slug, world_time
        ) VALUES (%s, 1, 1, 1, 'primary', interval '0 seconds',
                  now(), %s, %s)
        """,
        (chunk_id, token[:10], WORLD_TIME),
    )
    return chunk_id


def _insert_entity(cur: Any, kind: str) -> int:
    cur.execute(
        "INSERT INTO entities (kind, is_active) VALUES (%s, true) RETURNING id",
        (kind,),
    )
    return int(cur.fetchone()["id"])


def _insert_event(
    cur: Any,
    *,
    chunk_id: int,
    actor_entity_id: int,
    target_entity_id: int | None = None,
) -> int:
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload
        ) VALUES (
            'threat_issued', %s, %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb
        )
        RETURNING id
        """,
        (chunk_id, actor_entity_id, target_entity_id),
    )
    return int(cur.fetchone()["id"])


def test_faction_participant_mints_awareness_at_source_chunk_world_time(
    live_conn: Any,
) -> None:
    """Faction knowers are legal and participant acquisition uses world time."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        chunk_id = _insert_chunk(cur)
        cur.execute(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
            (chunk_id,),
        )
        source_world_time = cur.fetchone()["world_time"]
        assert source_world_time is not None
        faction = _insert_entity(cur, "faction")
        target = _insert_entity(cur, "character")
        event_id = _insert_event(
            cur,
            chunk_id=chunk_id,
            actor_entity_id=faction,
            target_entity_id=target,
        )
        participants = (
            ClaimParticipant(faction, "actor", "The Fixture Assembly", "faction"),
            ClaimParticipant(target, "target", "Fixture Target", "character"),
        )
        minted = mint_claim_for_event(
            cur,
            world_event_id=event_id,
            event_type="threat_issued",
            summary=mechanical_claim_summary("threat_issued", participants),
            participants=participants,
            source_chunk_id=chunk_id,
            source_resolution_id=None,
            settings=EPISTEMICS,
        )
        assert minted is not None
        cur.execute(
            """
            SELECT knower_entity_id, source_tier, acquired_at_world_time,
                   immediate_source_entity_id, root_source_entity_id
            FROM claim_awareness
            WHERE claim_id = %s
            ORDER BY knower_entity_id
            """,
            (minted.claim_id,),
        )
        rows = cur.fetchall()

    assert {int(row["knower_entity_id"]): row["source_tier"] for row in rows} == {
        faction: "participant",
        target: "participant",
    }
    assert all(row["acquired_at_world_time"] == source_world_time for row in rows)
    assert all(
        row["immediate_source_entity_id"] is None
        and row["root_source_entity_id"] is None
        for row in rows
    )


def test_two_hop_revelation_threads_root_and_rejects_unpossessed_teller(
    live_conn: Any,
) -> None:
    """A→B→C retains A as root, while an unaware D cannot reveal."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        chunk_id = _insert_chunk(cur)
        source, middle, recipient, unpossessed = (
            _insert_entity(cur, "character") for _ in range(4)
        )
        event_id = _insert_event(
            cur,
            chunk_id=chunk_id,
            actor_entity_id=source,
        )
        participants = (
            ClaimParticipant(source, "actor", "Fixture Source", "character"),
        )
        minted = mint_claim_for_event(
            cur,
            world_event_id=event_id,
            event_type="threat_issued",
            summary=mechanical_claim_summary("threat_issued", participants),
            participants=participants,
            source_chunk_id=chunk_id,
            source_resolution_id=None,
            settings=EPISTEMICS,
        )
        assert minted is not None
        record_revelation(
            cur,
            claim_id=minted.claim_id,
            knower_entity_id=middle,
            source_entity_id=source,
            channel="conversation",
            world_time=WORLD_TIME,
            source_chunk_id=chunk_id,
        )
        second_hop = record_revelation(
            cur,
            claim_id=minted.claim_id,
            knower_entity_id=recipient,
            source_entity_id=middle,
            channel="conversation",
            world_time=WORLD_TIME,
            source_chunk_id=chunk_id,
        )
        cur.execute(
            """
            SELECT immediate_source_entity_id, root_source_entity_id
            FROM claim_awareness WHERE id = %s
            """,
            (second_hop.awareness_id,),
        )
        provenance = cur.fetchone()
        assert provenance == {
            "immediate_source_entity_id": middle,
            "root_source_entity_id": source,
        }
        with pytest.raises(ValueError, match="teller does not possess"):
            record_revelation(
                cur,
                claim_id=minted.claim_id,
                knower_entity_id=recipient,
                source_entity_id=unpossessed,
                channel="conversation",
                world_time=WORLD_TIME,
                source_chunk_id=chunk_id,
            )


def test_common_claim_can_be_revealed_without_teller_awareness_row(
    live_conn: Any,
) -> None:
    """Common claims are possessed implicitly, so a row-free teller is legal."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        chunk_id = _insert_chunk(cur)
        actor, teller, recipient = (_insert_entity(cur, "character") for _ in range(3))
        event_id = _insert_event(
            cur,
            chunk_id=chunk_id,
            actor_entity_id=actor,
        )
        minted = mint_claim_for_event(
            cur,
            world_event_id=event_id,
            event_type="threat_issued",
            summary="A common fixture claim.",
            participants=(
                ClaimParticipant(actor, "actor", "Fixture Actor", "character"),
            ),
            source_chunk_id=chunk_id,
            source_resolution_id=None,
            settings=EPISTEMICS,
        )
        assert minted is not None
        cur.execute(
            "UPDATE claims SET scope = 'common' WHERE id = %s",
            (minted.claim_id,),
        )
        cur.execute(
            """
            SELECT 1 FROM claim_awareness
            WHERE claim_id = %s AND knower_entity_id = %s
            """,
            (minted.claim_id, teller),
        )
        assert cur.fetchone() is None

        revelation = record_revelation(
            cur,
            claim_id=minted.claim_id,
            knower_entity_id=recipient,
            source_entity_id=teller,
            channel="conversation",
            world_time=WORLD_TIME,
            source_chunk_id=chunk_id,
        )
        cur.execute(
            """
            SELECT immediate_source_entity_id, root_source_entity_id
            FROM claim_awareness WHERE id = %s
            """,
            (revelation.awareness_id,),
        )
        provenance = cur.fetchone()

    assert provenance == {
        "immediate_source_entity_id": teller,
        "root_source_entity_id": teller,
    }
