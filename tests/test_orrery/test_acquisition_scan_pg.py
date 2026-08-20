"""PostgreSQL proofs for indexed acquisition-experience formation."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
from psycopg2 import sql  # type: ignore[import-untyped]
from psycopg2.extras import RealDictCursor
import pytest

from nexus.agents.orrery.experiences import (
    _ACQUISITION_CANDIDATES_SQL,
    seed_character_experiences_sync,
)
from nexus.api import db_pool
from nexus.config import load_settings_as_dict
from scripts import new_story_setup


pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "migrations" / "113_acquisition_formation_indexes.sql"


def _connect(dbname: str) -> Any:
    """Open a direct PostgreSQL connection to a disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@pytest.fixture(scope="module")
def acquisition_database() -> Iterator[str]:
    """Yield a dump-initialized database with migration 113 applied twice."""

    dbname = f"qa_wt723_{uuid4().hex[:12]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                migration_sql = MIGRATION.read_text()
                cur.execute(migration_sql)
                cur.execute(migration_sql)
                cur.execute(
                    "UPDATE global_variables SET base_timestamp = %s "
                    "WHERE id = true",
                    (datetime(2196, 7, 7, 0, 0, tzinfo=timezone.utc),),
                )
                assert cur.rowcount == 1
                cur.execute(
                    "INSERT INTO entities (kind) " "VALUES ('character') RETURNING id"
                )
                player_entity_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO characters (
                        name, entity_id, summary, background, personality
                    ) VALUES (
                        'Issue 723 Fixture Player', %s,
                        'The canonical fixture player.',
                        'Excluded from experience ownership.',
                        'Observant and reserved.'
                    ) RETURNING id
                    """,
                    (player_entity_id,),
                )
                player_character_id = int(cur.fetchone()[0])
                cur.execute(
                    "UPDATE global_variables SET user_character = %s WHERE id = true",
                    (player_character_id,),
                )
                assert cur.rowcount == 1
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
        pool = db_pool._pools.pop(dbname, None)
        if pool is not None:
            pool.closeall()
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


def _insert_chunk(
    cur: Any,
    *,
    label: str,
    world_layer: str,
    world_time: datetime,
) -> int:
    """Insert one accepted narrative chunk and its metadata."""

    cur.execute(
        """
        INSERT INTO narrative_chunks (
            raw_text, storyteller_text, state, finalized_at
        ) VALUES (%s, %s, 'accepted', %s)
        RETURNING id
        """,
        (label, label, world_time),
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, world_time
        ) VALUES (%s, 1, 1, %s, %s::world_layer_type, %s)
        """,
        (chunk_id, chunk_id, world_layer, world_time),
    )
    cur.execute(
        "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
        (world_time, chunk_id),
    )
    assert cur.rowcount == 1
    return chunk_id


def _insert_character(cur: Any, name: str) -> int:
    """Insert an eligible character and return its entity-spine id."""

    cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
    entity_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO characters (
            name, entity_id, summary, background, personality
        ) VALUES (
            %s, %s, 'A careful keeper of exact accounts.',
            'Maintains a complete private dossier.',
            'Precise and attentive.'
        )
        """,
        (name, entity_id),
    )
    return entity_id


def _insert_formed_event(
    cur: Any,
    *,
    chunk_id: int,
    actor_entity_id: int,
    payload: str = "{}",
    event_type: str = "discovered",
) -> int:
    """Insert an already-formed event and return its id."""

    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id,
            world_layer, source, changed_fields, payload,
            experiences_formed_at
        ) VALUES (
            %s, %s, %s, 'primary', 'resolver', '{}', %s::jsonb, now()
        ) RETURNING id
        """,
        (event_type, chunk_id, actor_entity_id, payload),
    )
    return int(cur.fetchone()[0])


def _insert_claim_awareness(
    cur: Any,
    *,
    incident_id: int,
    source_chunk_id: int,
    knower_entity_id: int,
    source_tier: str,
    account_label: str,
    summary: str,
    acquired_at_world_time: datetime | None,
) -> tuple[int, int]:
    """Insert one claim/account and its durable awareness row."""

    cur.execute(
        """
        INSERT INTO claims (
            world_event_id, summary, scope, source_chunk_id, account_label
        ) VALUES (%s, %s, 'bounded', %s, %s)
        RETURNING id
        """,
        (incident_id, summary, source_chunk_id, account_label),
    )
    claim_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO claim_awareness (
            claim_id, knower_entity_id, source_tier,
            immediate_source_entity_id, channel,
            acquired_at_world_time, source_chunk_id
        ) VALUES (%s, %s, %s, %s, 'dialogue', %s, %s)
        RETURNING id
        """,
        (
            claim_id,
            knower_entity_id,
            source_tier,
            knower_entity_id,
            acquired_at_world_time,
            source_chunk_id,
        ),
    )
    return claim_id, int(cur.fetchone()[0])


def _index_names(node: dict[str, Any]) -> set[str]:
    """Return every index name from a PostgreSQL JSON plan tree."""

    names = set()
    if node.get("Index Name") is not None:
        names.add(str(node["Index Name"]))
    for child in node.get("Plans", []):
        names.update(_index_names(child))
    return names


def test_acquisition_semantics_and_awareness_lock_are_preserved(
    acquisition_database: str,
) -> None:
    """Indexed formation preserves exact accounts, provenance, and row locks."""

    settings = load_settings_as_dict()
    told_time = datetime(2196, 7, 7, 1, 0, tzinfo=timezone.utc)
    granted_anchor_time = datetime(2196, 7, 7, 2, 0, tzinfo=timezone.utc)
    granted_acquired_time = datetime(2196, 7, 7, 2, 17, tzinfo=timezone.utc)
    existing_time = datetime(2196, 7, 7, 3, 0, tzinfo=timezone.utc)
    final_time = datetime(2196, 7, 7, 4, 0, tzinfo=timezone.utc)
    conn = _connect(acquisition_database)
    try:
        with conn:
            with conn.cursor() as cur:
                told_chunk_id = _insert_chunk(
                    cur,
                    label="Issue 723 told acquisition",
                    world_layer="flashback",
                    world_time=told_time,
                )
                granted_chunk_id = _insert_chunk(
                    cur,
                    label="Issue 723 granted acquisition",
                    world_layer="primary",
                    world_time=granted_anchor_time,
                )
                existing_chunk_id = _insert_chunk(
                    cur,
                    label="Issue 723 pre-existing acquisition",
                    world_layer="atemporal",
                    world_time=existing_time,
                )
                final_chunk_id = _insert_chunk(
                    cur,
                    label="Issue 723 acquisition sweep anchor",
                    world_layer="primary",
                    world_time=final_time,
                )
                cur.executemany(
                    "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
                    [
                        (told_time, told_chunk_id),
                        (granted_anchor_time, granted_chunk_id),
                        (existing_time, existing_chunk_id),
                        (final_time, final_chunk_id),
                    ],
                )
                told_owner_id = _insert_character(cur, "Talia Exact")
                granted_owner_id = _insert_character(cur, "Galen Exact")
                existing_owner_id = _insert_character(cur, "Priya Existing")
                incident_actor_id = _insert_character(cur, "Iris Incident")

                told_incident_id = _insert_formed_event(
                    cur,
                    chunk_id=told_chunk_id,
                    actor_entity_id=incident_actor_id,
                )
                told_claim_id, told_awareness_id = _insert_claim_awareness(
                    cur,
                    incident_id=told_incident_id,
                    source_chunk_id=told_chunk_id,
                    knower_entity_id=told_owner_id,
                    source_tier="told",
                    account_label="reported",
                    summary="The north gate opened before dawn.",
                    acquired_at_world_time=None,
                )

                granted_incident_id = _insert_formed_event(
                    cur,
                    chunk_id=granted_chunk_id,
                    actor_entity_id=incident_actor_id,
                )
                granted_claim_id, granted_awareness_id = _insert_claim_awareness(
                    cur,
                    incident_id=granted_incident_id,
                    source_chunk_id=granted_chunk_id,
                    knower_entity_id=granted_owner_id,
                    source_tier="granted",
                    account_label="sealed",
                    summary="The council ratified the winter compact.",
                    acquired_at_world_time=granted_acquired_time,
                )
                granted_delivery_id = _insert_formed_event(
                    cur,
                    chunk_id=granted_chunk_id,
                    actor_entity_id=told_owner_id,
                    payload=f'{{"awareness_id": {granted_awareness_id}}}',
                    event_type="claim_propagated",
                )

                existing_incident_id = _insert_formed_event(
                    cur,
                    chunk_id=existing_chunk_id,
                    actor_entity_id=incident_actor_id,
                )
                existing_claim_id, existing_awareness_id = _insert_claim_awareness(
                    cur,
                    incident_id=existing_incident_id,
                    source_chunk_id=existing_chunk_id,
                    knower_entity_id=existing_owner_id,
                    source_tier="told",
                    account_label="archived",
                    summary="The archive already contains this account.",
                    acquired_at_world_time=existing_time,
                )
                cur.execute(
                    """
                    INSERT INTO character_experiences (
                        character_entity_id, anchor_chunk_id, world_event_ids,
                        claim_id, claim_awareness_id, basis, world_time,
                        seed_summary, salience, source_digest, world_layer
                    ) VALUES (
                        %s, %s, ARRAY[%s]::bigint[], %s, %s, 'acquisition',
                        %s, 'Preserved pre-existing acquisition.', 0.2,
                        'qa-wt723-pre-existing', 'atemporal'
                    )
                    """,
                    (
                        existing_owner_id,
                        existing_chunk_id,
                        existing_incident_id,
                        existing_claim_id,
                        existing_awareness_id,
                        existing_time,
                    ),
                )

        assert (
            seed_character_experiences_sync(
                conn,
                anchor_chunk_id=final_chunk_id,
                settings=settings,
            )
            == 2
        )

        contender = _connect(acquisition_database)
        try:
            with contender.cursor() as cur:
                with pytest.raises(psycopg2.errors.LockNotAvailable):
                    cur.execute(
                        "SELECT id FROM claim_awareness WHERE id = %s "
                        "FOR UPDATE NOWAIT",
                        (told_awareness_id,),
                    )
            contender.rollback()
        finally:
            contender.close()

        assert (
            seed_character_experiences_sync(
                conn,
                anchor_chunk_id=final_chunk_id,
                settings=settings,
            )
            == 0
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT character_entity_id, anchor_chunk_id, world_event_ids,
                       claim_id, claim_awareness_id, basis::text AS basis,
                       world_time, seed_summary, world_layer::text AS world_layer
                FROM character_experiences
                WHERE claim_awareness_id = ANY(%s)
                ORDER BY claim_awareness_id
                """,
                ([told_awareness_id, granted_awareness_id, existing_awareness_id],),
            )
            rows = {int(row["claim_awareness_id"]): dict(row) for row in cur.fetchall()}

        assert set(rows) == {
            told_awareness_id,
            granted_awareness_id,
            existing_awareness_id,
        }
        told = rows[told_awareness_id]
        assert told["character_entity_id"] == told_owner_id
        assert told["anchor_chunk_id"] == told_chunk_id
        assert told["world_event_ids"] == [told_incident_id]
        assert told["claim_id"] == told_claim_id
        assert told["basis"] == "acquisition"
        assert told["world_time"] == told_time
        assert told["world_layer"] == "flashback"
        assert told["seed_summary"] == (
            "Talia Exact acquired the reported account by being told: "
            "The north gate opened before dawn."
        )

        granted = rows[granted_awareness_id]
        assert granted["character_entity_id"] == granted_owner_id
        assert granted["anchor_chunk_id"] == granted_chunk_id
        assert granted["world_event_ids"] == [
            granted_incident_id,
            granted_delivery_id,
        ]
        assert granted["claim_id"] == granted_claim_id
        assert granted["basis"] == "acquisition"
        assert granted["world_time"] == granted_acquired_time
        assert granted["world_layer"] == "primary"
        assert granted["seed_summary"] == (
            "Galen Exact acquired the sealed account by being granted: "
            "The council ratified the winter compact."
        )

        existing = rows[existing_awareness_id]
        assert existing["character_entity_id"] == existing_owner_id
        assert existing["world_event_ids"] == [existing_incident_id]
        assert existing["seed_summary"] == "Preserved pre-existing acquisition."
    finally:
        conn.rollback()
        conn.close()


def test_representative_plan_uses_both_acquisition_indexes(
    acquisition_database: str,
) -> None:
    """A representative corpus uses both migration-113 indexes."""

    chunk_count = 300
    awareness_count = 30_000
    knower_count = 60
    chunk_base = 1_000_000
    entity_base = 2_000_000
    incident_base = 3_000_000
    delivery_base = 3_100_000
    claim_base = 4_000_000
    awareness_base = 5_000_000
    conn = _connect(acquisition_database)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO narrative_chunks (
                    id, raw_text, state, finalized_at
                )
                SELECT %s + ordinal,
                       'Issue 723 plan chunk ' || ordinal,
                       'accepted', now()
                FROM generate_series(1, %s) AS ordinal
                """,
                (chunk_base, chunk_count),
            )
            cur.execute(
                """
                INSERT INTO chunk_metadata (
                    chunk_id, season, episode, scene, world_layer, world_time
                )
                SELECT %s + ordinal,
                       7,
                       2 + ((ordinal - 1) / 100),
                       1 + ((ordinal - 1) %% 100),
                       'primary',
                       TIMESTAMPTZ '2196-07-08 00:00:00+00'
                           + ordinal * INTERVAL '1 minute'
                FROM generate_series(1, %s) AS ordinal
                """,
                (chunk_base, chunk_count),
            )
            cur.execute(
                """
                INSERT INTO entities (id, kind)
                SELECT %s + ordinal, 'character'::entity_kind
                FROM generate_series(1, %s) AS ordinal
                """,
                (entity_base, knower_count),
            )
            cur.execute(
                """
                INSERT INTO characters (
                    name, entity_id, summary, background, personality
                )
                SELECT 'Issue 723 Plan Character ' || ordinal,
                       %s + ordinal,
                       'A representative benchmark character.',
                       'A complete benchmark background.',
                       'Methodical.'
                FROM generate_series(1, %s) AS ordinal
                """,
                (entity_base, knower_count),
            )
            cur.execute(
                """
                INSERT INTO world_events (
                    id, event_type, tick_chunk_id, actor_entity_id,
                    world_layer, source, changed_fields, payload,
                    experiences_formed_at
                )
                SELECT %s + ordinal,
                       'discovered',
                       %s + 1 + (((ordinal - 1) / 100) %% %s),
                       %s + 1 + ((ordinal - 1) %% %s),
                       'primary', 'resolver',
                       ARRAY['benchmark_incident'],
                       jsonb_build_object('fixture_kind', 'incident'),
                       now()
                FROM generate_series(1, %s) AS ordinal
                """,
                (
                    incident_base,
                    chunk_base,
                    chunk_count,
                    entity_base,
                    knower_count,
                    awareness_count,
                ),
            )
            cur.execute(
                """
                INSERT INTO claims (
                    id, world_event_id, summary, scope,
                    source_chunk_id, account_label
                )
                SELECT %s + ordinal,
                       %s + ordinal,
                       'Issue 723 plan account ' || ordinal,
                       'bounded',
                       %s + 1 + (((ordinal - 1) / 100) %% %s),
                       'canonical'
                FROM generate_series(1, %s) AS ordinal
                """,
                (
                    claim_base,
                    incident_base,
                    chunk_base,
                    chunk_count,
                    awareness_count,
                ),
            )
            cur.execute(
                """
                INSERT INTO claim_awareness (
                    id, claim_id, knower_entity_id, source_tier,
                    acquired_at_world_time, source_chunk_id
                )
                SELECT %s + ordinal,
                       %s + ordinal,
                       %s + 1 + ((ordinal - 1) %% %s),
                       CASE ordinal %% 20
                           WHEN 0 THEN 'told'
                           WHEN 1 THEN 'granted'
                           WHEN 2 THEN 'witness'
                           ELSE 'participant'
                       END,
                       TIMESTAMPTZ '2196-07-08 00:00:00+00'
                           + (1 + (((ordinal - 1) / 100) %% %s))
                               * INTERVAL '1 minute',
                       %s + 1 + (((ordinal - 1) / 100) %% %s)
                FROM generate_series(1, %s) AS ordinal
                """,
                (
                    awareness_base,
                    claim_base,
                    entity_base,
                    knower_count,
                    chunk_count,
                    chunk_base,
                    chunk_count,
                    awareness_count,
                ),
            )
            cur.execute(
                """
                INSERT INTO world_events (
                    id, event_type, tick_chunk_id, actor_entity_id,
                    world_layer, source, changed_fields, payload,
                    experiences_formed_at
                )
                SELECT %s + ordinal,
                       'claim_propagated',
                       %s + 1 + (((ordinal - 1) / 100) %% %s),
                       %s + 1 + ((ordinal - 1) %% %s),
                       'primary', 'resolver', ARRAY['claim_awareness'],
                       jsonb_build_object(
                           'awareness_id',
                           CASE WHEN ((ordinal - 1) / 20) %% 4 IN (0, 1)
                                THEN %s + ordinal
                                ELSE %s + ordinal + 1000000
                           END
                       ),
                       now()
                FROM generate_series(1, %s) AS ordinal
                """,
                (
                    delivery_base,
                    chunk_base,
                    chunk_count,
                    entity_base,
                    knower_count,
                    awareness_base,
                    awareness_base,
                    awareness_count,
                ),
            )
            cur.execute(
                """
                INSERT INTO character_experiences (
                    character_entity_id, anchor_chunk_id, world_event_ids,
                    claim_id, claim_awareness_id, basis, world_time,
                    seed_summary, salience, source_digest, world_layer
                )
                SELECT ca.knower_entity_id,
                       ca.source_chunk_id,
                       ARRAY[c.world_event_id]::bigint[],
                       ca.claim_id,
                       ca.id,
                       'acquisition',
                       ca.acquired_at_world_time,
                       'Issue 723 pre-existing plan acquisition ' || ca.id,
                       0.2,
                       md5('qa-wt723-plan-' || ca.id),
                       'primary'
                FROM claim_awareness ca
                JOIN claims c ON c.id = ca.claim_id
                WHERE ca.id BETWEEN %s + 1 AND %s + %s
                  AND ca.source_tier IN ('told', 'granted')
                  AND (((ca.id - %s - 1) / 20) %% 4) IN (0, 3)
                """,
                (
                    awareness_base,
                    awareness_base,
                    awareness_count,
                    awareness_base,
                ),
            )
            for table in (
                "claim_awareness",
                "character_experiences",
                "claims",
                "characters",
                "chunk_metadata",
                "world_events",
            ):
                cur.execute(sql.SQL("ANALYZE {}").format(sql.Identifier(table)))
            representative_anchor = chunk_base + 150
            cur.execute(
                "EXPLAIN (FORMAT JSON) " + _ACQUISITION_CANDIDATES_SQL,
                (representative_anchor,),
            )
            plan = cur.fetchone()[0][0]["Plan"]
            index_names = _index_names(plan)
            assert "ix_claim_awareness_acquisition_sweep" in index_names
            assert "ix_world_events_awareness_delivery" in index_names
            cur.execute(
                """
                SELECT obj_description(
                           'ix_claim_awareness_acquisition_sweep'::regclass
                       ),
                       obj_description(
                           'ix_world_events_awareness_delivery'::regclass
                       )
                """
            )
            comments = cur.fetchone()
            assert "anchor-bounded told/granted" in comments[0]
            assert "source chunk and durable claim-awareness" in comments[1]
            cur.execute(
                """
                SELECT pg_get_expr(index.indpred, index.indrelid)
                FROM pg_index index
                WHERE index.indexrelid =
                    'ix_world_events_awareness_delivery'::regclass
                """
            )
            predicate = str(cur.fetchone()[0])
            assert "payload ->> 'awareness_id'" in predicate
            assert "IS NOT NULL" in predicate
    finally:
        conn.rollback()
        conn.close()
