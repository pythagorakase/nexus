"""Real-PostgreSQL tests for dedicated Retrograde summary persistence.

The fixture clones NEXUS_template into a uniquely named disposable database.
It never opens or mutates a save-slot database.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Iterator

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import pytest

from nexus.agents.orrery.retrograde_persistence import (
    _insert_character_stub,
    _insert_faction_stub,
    _insert_place_stub,
    plan_retrograde_summaries,
)


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def disposable_cursor() -> Iterator[Any]:
    """Yield a cursor on a temporary template clone, then drop the clone."""

    dbname = f"nexus_test_retrograde_storage_{uuid.uuid4().hex[:12]}"
    admin = None
    conn = None
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        conn = _connect(dbname)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT to_regclass('public.retrograde_summaries') AS name")
            if cur.fetchone()["name"] is None:
                pytest.skip("NEXUS_template has not applied migration 078")
            yield cur
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()
        if admin is not None:
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
            admin.close()


def test_summary_planning_is_idempotent_on_disposable_database(
    disposable_cursor: Any,
) -> None:
    """A persisted event gets one stable dedicated summary identity."""

    cur = disposable_cursor
    prologue_id = _insert_chunk(
        cur,
        raw_text="[Disposable Retrograde prologue.]",
        storyteller_text="Disposable Retrograde prologue.",
        directives=["orrery:retrograde_prologue_anchor"],
        scene=0,
        world_layer="retrograde",
    )
    cur.execute("SELECT type FROM event_types ORDER BY type LIMIT 1")
    event_type = cur.fetchone()["type"]
    event_ref = "disposable_wizard_event_001"
    summary_text = "A disposable test debt changed hands before the opening."
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, world_layer, source,
            changed_fields, payload
        ) VALUES (
            %s, %s, 'primary', 'retrograde', '{}', %s::jsonb
        )
        RETURNING id
        """,
        (
            event_type,
            prologue_id,
            json.dumps(
                {
                    "retrograde_event_ref": event_ref,
                    "summary": summary_text,
                    "chronology": "deep_past",
                }
            ),
        ),
    )
    world_event_id = int(cur.fetchone()["id"])

    first = plan_retrograde_summaries(cur, dry_run=False)
    second = plan_retrograde_summaries(cur, dry_run=False)

    assert len(first) == 1
    assert first[0]["status"] == "inserted"
    assert first[0]["recorded_at_chunk_id"] == prologue_id
    assert second[0]["status"] == "already_present"
    assert second[0]["summary_id"] == first[0]["summary_id"]
    cur.execute(
        """
        SELECT world_event_id, recorded_at_chunk_id, chronology, summary_text
        FROM retrograde_summaries
        WHERE id = %s
        """,
        (first[0]["summary_id"],),
    )
    assert cur.fetchone() == {
        "world_event_id": world_event_id,
        "recorded_at_chunk_id": prologue_id,
        "chronology": "deep_past",
        "summary_text": summary_text,
    }


def test_entity_stub_inserts_match_disposable_schema(disposable_cursor: Any) -> None:
    """Stub INSERT column lists stay aligned with the migrated template."""

    cur = disposable_cursor
    cur.execute("INSERT INTO layers DEFAULT VALUES RETURNING id")
    layer_id = cur.fetchone()["id"]
    cur.execute(
        "INSERT INTO zones (name, layer) VALUES ('Test Story Zone', %s) "
        "RETURNING id",
        (layer_id,),
    )
    zone_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO places (name, type, zone)
        VALUES ('Test Story Place', 'fixed_location', %s)
        RETURNING id
        """,
        (zone_id,),
    )
    place_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO characters (name, current_location)
        VALUES ('Test Protagonist', %s)
        RETURNING id
        """,
        (place_id,),
    )
    character_id = cur.fetchone()["id"]
    cur.execute(
        """
        INSERT INTO global_variables (id, user_character)
        VALUES (true, %s)
        ON CONFLICT (id) DO UPDATE
        SET user_character = EXCLUDED.user_character
        """,
        (character_id,),
    )
    suffix = uuid.uuid4().hex[:8]
    sources = [{"plan": "event_plan", "event_ref": suffix, "role": "actor"}]
    faction_name = f"Disposable Faction {suffix}"
    character_name = f"Disposable Character {suffix}"
    place_name = f"Disposable Place {suffix}"

    _insert_faction_stub(cur, entity_ref=faction_name, sources=sources)
    _insert_character_stub(cur, entity_ref=character_name, sources=sources)
    _insert_place_stub(cur, entity_ref=place_name, sources=sources)

    cur.execute(
        """
        SELECT name, entity_id FROM factions WHERE name = %s
        UNION ALL
        SELECT name, entity_id FROM characters WHERE name = %s
        UNION ALL
        SELECT name, entity_id FROM places WHERE name = %s
        """,
        (faction_name, character_name, place_name),
    )
    rows = cur.fetchall()
    assert {row["name"] for row in rows} == {
        faction_name,
        character_name,
        place_name,
    }
    assert all(row["entity_id"] is not None for row in rows)


def _insert_chunk(
    cur: Any,
    *,
    raw_text: str,
    storyteller_text: str,
    directives: list[str],
    scene: int,
    world_layer: str,
) -> int:
    cur.execute(
        """
        INSERT INTO narrative_chunks (
            raw_text, storyteller_text, authorial_directives,
            state, finalized_at
        ) VALUES (%s, %s, %s::jsonb, 'finalized', now())
        RETURNING id
        """,
        (raw_text, storyteller_text, json.dumps(directives)),
    )
    chunk_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer,
            time_delta, generation_date
        ) VALUES (%s, 0, 0, %s, %s::world_layer_type, interval '0 seconds', now())
        """,
        (chunk_id, scene, world_layer),
    )
    return chunk_id
