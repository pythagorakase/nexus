"""Real-PostgreSQL coverage for migration 078 on a disposable database.

Run with ``NEXUS_RUN_POSTGRES=1``. The fixture clones ``NEXUS_template`` into
a uniquely named database, never opens a save-slot database, and drops the
clone even when the migration fails.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import uuid
from typing import Any, Iterator

import psycopg2
from psycopg2 import sql
import pytest

import scripts.migrate as migrate


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@pytest.fixture()
def disposable_retrograde_db() -> Iterator[Any]:
    """Yield a template clone whose name cannot collide with a save slot."""

    dbname = f"nexus_test_retrograde_078_{uuid.uuid4().hex[:12]}"
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
        yield conn
    finally:
        if conn is not None:
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


def test_migration_078_moves_ids_embeddings_manifests_and_rolls_back(
    disposable_retrograde_db: Any,
) -> None:
    """078 preserves identities and remains wholly transaction-rollback safe."""

    conn = disposable_retrograde_db
    migration = migrate._load_python_migration(
        Path(__file__).parents[2] / "migrations" / "078_retrograde_summary_storage.py"
    )
    _drop_migration_targets(conn)

    seeded = _seed_legacy_runtime_summary(conn)
    migration.run(conn)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, world_event_id, recorded_at_chunk_id, chronology,
                   summary_text, embedding_generated_at, created_at
            FROM retrograde_summaries
            ORDER BY world_event_id
            """
        )
        summaries = cur.fetchall()
        assert len(summaries) == 3
        assert summaries[0] == (
            seeded["summary_id"],
            seeded["world_event_id"],
            seeded["requesting_chunk_id"],
            "recent_past",
            seeded["summary_text"],
            seeded["embedded_at"],
            seeded["legacy_created_at"],
        )
        assert summaries[1] == (
            seeded["summary_id"] + 1,
            seeded["runtime_backfill_event_id"],
            seeded["requesting_chunk_id"],
            "opening_pressure",
            seeded["runtime_backfill_summary"],
            None,
            seeded["runtime_backfill_created_at"],
        )
        assert summaries[2] == (
            seeded["summary_id"] + 2,
            seeded["wizard_backfill_event_id"],
            seeded["prologue_id"],
            "deep_past",
            seeded["wizard_backfill_summary"],
            None,
            seeded["wizard_backfill_created_at"],
        )
        cur.execute("SELECT summary_id, model FROM retrograde_summary_embeddings_0004d")
        assert cur.fetchall() == [(seeded["summary_id"], "migration-test")]
        cur.execute(
            "SELECT count(*) FROM narrative_chunks WHERE id = %s",
            (seeded["summary_id"],),
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT payload, result_manifest FROM world_events, "
            "orrery_maturation_jobs WHERE world_events.id = %s "
            "AND orrery_maturation_jobs.id = %s",
            (seeded["world_event_id"], seeded["job_id"]),
        )
        payload, manifest = cur.fetchone()
        assert "retrograde_summary_chunk_id" not in payload
        assert manifest["schema_version"] == "orrery_retrograde_maturation_manifest.v1"
        assert manifest["embedding_pending_summary_ids"] == [seeded["summary_id"]]
        assert "embedding_pending_chunk_ids" not in manifest
        assert manifest["embedding"]["results"][0]["summary_id"] == seeded["summary_id"]
        assert "chunk_id" not in manifest["embedding"]["results"][0]
        cur.execute(
            """
            SELECT tgenabled
            FROM pg_trigger
            WHERE tgrelid = 'orrery_maturation_jobs'::regclass
              AND tgname = 'trg_orrery_maturation_jobs_require_manifest_v1'
              AND NOT tgisinternal
            """
        )
        assert cur.fetchone() == ("O",)

        cur.execute("SAVEPOINT reject_legacy_chunk")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                UPDATE narrative_chunks
                SET authorial_directives = %s::jsonb
                WHERE id = %s
                """,
                (
                    json.dumps(["orrery:retrograde_event_summary"]),
                    seeded["requesting_chunk_id"],
                ),
            )
        cur.execute("ROLLBACK TO SAVEPOINT reject_legacy_chunk")

        cur.execute("SAVEPOINT reject_legacy_link")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                UPDATE world_events
                SET payload = payload || %s::jsonb
                WHERE id = %s
                """,
                (
                    json.dumps({"retrograde_summary_chunk_id": 999999}),
                    seeded["world_event_id"],
                ),
            )
        cur.execute("ROLLBACK TO SAVEPOINT reject_legacy_link")

        invalid_manifests = (
            {
                "schema_version": "orrery_retrograde_maturation_manifest.v0",
                "persisted": True,
            },
            {
                "schema_version": "orrery_retrograde_maturation_manifest.v1",
                "embedding_pending_chunk_ids": [seeded["summary_id"]],
            },
            {
                "schema_version": "orrery_retrograde_maturation_manifest.v1",
                "embedding": {
                    "results": [{"chunk_id": seeded["summary_id"]}],
                },
            },
        )
        for invalid_manifest in invalid_manifests:
            _assert_manifest_update_rejected(
                cur,
                job_id=seeded["job_id"],
                manifest=invalid_manifest,
            )

        allowed_manifests = (
            {},
            {
                "schema_version": "orrery_retrograde_maturation_manifest.v1",
                "embedding_pending_summary_ids": [seeded["summary_id"]],
                "embedding": {
                    "results": [{"summary_id": seeded["summary_id"]}],
                },
            },
        )
        for allowed_manifest in allowed_manifests:
            cur.execute(
                "UPDATE orrery_maturation_jobs SET result_manifest = %s::jsonb "
                "WHERE id = %s RETURNING result_manifest",
                (json.dumps(allowed_manifest), seeded["job_id"]),
            )
            assert cur.fetchone()[0] == allowed_manifest

        # Fresh queue rows intentionally leave result_manifest NULL until the
        # worker records a result. The post-078 guard must preserve that path.
        cur.execute(
            "DELETE FROM orrery_maturation_jobs WHERE id = %s",
            (seeded["job_id"],),
        )
        cur.execute(
            """
            INSERT INTO orrery_maturation_jobs (
                entity_id, entity_kind, entity_subtype_id, entity_name, slot,
                requesting_chunk_id, declaration, state
            ) VALUES (
                %s, 'character', %s, %s, 'disposable_078', %s,
                '{}'::jsonb, 'queued'
            )
            RETURNING result_manifest
            """,
            (
                seeded["entity_id"],
                seeded["character_id"],
                "Migration Courier",
                seeded["requesting_chunk_id"],
            ),
        )
        assert cur.fetchone()[0] is None

    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.retrograde_summaries')")
        assert cur.fetchone()[0] is None
        cur.execute(
            "SELECT count(*) FROM narrative_chunks WHERE id = %s",
            (seeded["summary_id"],),
        )
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT result_manifest FROM orrery_maturation_jobs WHERE id = %s",
            (seeded["job_id"],),
        )
        manifest = cur.fetchone()[0]
        assert manifest["schema_version"] == "orrery_retrograde_maturation_manifest.v0"
        assert manifest["embedding_pending_chunk_ids"] == [seeded["summary_id"]]
        assert "embedding_pending_summary_ids" not in manifest
        cur.execute(
            """
            SELECT count(*)
            FROM pg_trigger
            WHERE tgrelid = 'orrery_maturation_jobs'::regclass
              AND tgname = 'trg_orrery_maturation_jobs_require_manifest_v1'
              AND NOT tgisinternal
            """
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT to_regprocedure("
            "'public.nexus_require_retrograde_maturation_manifest_v1()'"
            ")"
        )
        assert cur.fetchone()[0] is None


def test_migration_078_rejects_stamped_summary_without_vector_coverage(
    disposable_retrograde_db: Any,
) -> None:
    """An ironman stamp without a copyable vector must stop the migration."""

    conn = disposable_retrograde_db
    migration = migrate._load_python_migration(
        Path(__file__).parents[2] / "migrations" / "078_retrograde_summary_storage.py"
    )
    _drop_migration_targets(conn)
    seeded = _seed_legacy_runtime_summary(conn)
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM chunk_embeddings_0004d WHERE chunk_id = %s",
            (seeded["summary_id"],),
        )
    conn.commit()

    with pytest.raises(RuntimeError, match="non-null embedding stamps"):
        migration.run(conn)
    conn.rollback()

    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.retrograde_summaries')")
        assert cur.fetchone()[0] is None
        cur.execute(
            "SELECT count(*) FROM narrative_chunks WHERE id = %s",
            (seeded["summary_id"],),
        )
        assert cur.fetchone()[0] == 1


def _drop_migration_targets(conn: Any) -> None:
    """Remove prior 078 artifacts in dependency-safe deterministic order."""

    with conn.cursor() as cur:
        cur.execute(
            "DROP TRIGGER IF EXISTS "
            "trg_narrative_chunks_reject_retrograde_summary "
            "ON narrative_chunks"
        )
        cur.execute(
            "DROP TRIGGER IF EXISTS "
            "trg_world_events_reject_retrograde_summary_link "
            "ON world_events"
        )
        cur.execute(
            "DROP TRIGGER IF EXISTS "
            "trg_orrery_maturation_jobs_require_manifest_v1 "
            "ON orrery_maturation_jobs"
        )
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND (
                  table_name = 'retrograde_summaries'
                  OR table_name ~ '^retrograde_summary_embeddings_[0-9]+d$'
              )
            ORDER BY
                CASE WHEN table_name = 'retrograde_summaries' THEN 1 ELSE 0 END,
                table_name
            """
        )
        for (table_name,) in cur.fetchall():
            cur.execute(
                sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(table_name)
                )
            )
        cur.execute(
            "DROP FUNCTION IF EXISTS " "nexus_reject_legacy_retrograde_summary_chunk()"
        )
        cur.execute(
            "DROP FUNCTION IF EXISTS " "nexus_reject_legacy_retrograde_summary_link()"
        )
        cur.execute(
            "DROP FUNCTION IF EXISTS "
            "nexus_require_retrograde_maturation_manifest_v1()"
        )
    conn.commit()


def _assert_manifest_update_rejected(
    cur: Any,
    *,
    job_id: int,
    manifest: dict[str, Any],
) -> None:
    cur.execute("SAVEPOINT reject_legacy_manifest")
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "UPDATE orrery_maturation_jobs SET result_manifest = %s::jsonb "
            "WHERE id = %s",
            (json.dumps(manifest), job_id),
        )
    cur.execute("ROLLBACK TO SAVEPOINT reject_legacy_manifest")
    cur.execute("RELEASE SAVEPOINT reject_legacy_manifest")


def _seed_legacy_runtime_summary(conn: Any) -> dict[str, Any]:
    summary_text = "A test courier hid a debt ledger before the opening pressure."
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO narrative_chunks (
                raw_text, storyteller_text, authorial_directives,
                state, finalized_at
            )
            VALUES (%s, %s, %s::jsonb, 'finalized', now())
            RETURNING id
            """,
            (
                "[Retrograde prologue anchor for migration test.]",
                "Synthetic prologue anchor for migration test.",
                json.dumps(["orrery:retrograde_prologue_anchor"]),
            ),
        )
        prologue_id = int(cur.fetchone()[0])
        _insert_metadata(cur, prologue_id, scene=0, world_layer="retrograde")

        cur.execute(
            """
            INSERT INTO narrative_chunks (
                raw_text, storyteller_text, authorial_directives,
                state, finalized_at
            )
            VALUES (%s, %s, '[]'::jsonb, 'finalized', now())
            RETURNING id
            """,
            ("The player accepts a migration-test turn.",) * 2,
        )
        requesting_chunk_id = int(cur.fetchone()[0])
        _insert_metadata(cur, requesting_chunk_id, scene=1, world_layer="primary")

        cur.execute(
            """
            INSERT INTO characters (
                name, summary, background, current_activity, extra_data
            ) VALUES (%s, %s, %s, %s, '{}'::jsonb)
            RETURNING id, entity_id
            """,
            (
                f"Migration Courier {uuid.uuid4().hex[:8]}",
                "Disposable migration-test character.",
                "Created only inside a disposable database.",
                "Testing migration 078.",
            ),
        )
        character_id, entity_id = map(int, cur.fetchone())
        cur.execute(
            """
            INSERT INTO orrery_maturation_jobs (
                entity_id, entity_kind, entity_subtype_id, entity_name, slot,
                requesting_chunk_id, declaration, state, result_manifest
            ) VALUES (
                %s, 'character', %s, %s, 'disposable_078', %s,
                '{}'::jsonb, 'succeeded', '{}'::jsonb
            )
            RETURNING id
            """,
            (entity_id, character_id, "Migration Courier", requesting_chunk_id),
        )
        job_id = int(cur.fetchone()[0])
        event_ref = f"maturation_job_{job_id}_event_001"

        cur.execute(
            """
            INSERT INTO narrative_chunks (
                raw_text, storyteller_text, authorial_directives,
                state, finalized_at, embedding_generated_at
            )
            VALUES (%s, %s, %s::jsonb, 'finalized', now(), now())
            RETURNING id, embedding_generated_at, created_at
            """,
            (
                summary_text,
                summary_text,
                json.dumps(
                    [
                        "orrery:retrograde_event_summary",
                        f"orrery:retrograde_event:{event_ref}",
                    ]
                ),
            ),
        )
        summary_id, embedded_at, legacy_created_at = cur.fetchone()
        summary_id = int(summary_id)
        _insert_metadata(cur, summary_id, scene=2, world_layer="retrograde")

        cur.execute("SELECT type FROM event_types ORDER BY type LIMIT 1")
        event_type = cur.fetchone()[0]
        payload = {
            "retrograde_event_ref": event_ref,
            "retrograde_summary_chunk_id": summary_id,
            "summary": summary_text,
            "chronology": "recent_past",
        }
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
            (event_type, prologue_id, json.dumps(payload)),
        )
        world_event_id = int(cur.fetchone()[0])

        runtime_backfill_summary = (
            "The courier's hidden route became a pressure point at opening."
        )
        runtime_backfill_payload = {
            "retrograde_event_ref": f"maturation_job_{job_id}_event_002",
            "summary": runtime_backfill_summary,
            "chronology": "opening_pressure",
        }
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, world_layer, source,
                changed_fields, payload
            ) VALUES (
                %s, %s, 'primary', 'retrograde', '{}', %s::jsonb
            )
            RETURNING id, created_at
            """,
            (event_type, prologue_id, json.dumps(runtime_backfill_payload)),
        )
        runtime_backfill_event_id, runtime_backfill_created_at = cur.fetchone()
        runtime_backfill_event_id = int(runtime_backfill_event_id)

        wizard_backfill_summary = (
            "Long before play, a ceremonial debt established the district custom."
        )
        wizard_backfill_payload = {
            "retrograde_event_ref": f"wizard_event_{uuid.uuid4().hex[:8]}",
            "summary": wizard_backfill_summary,
            "chronology": "deep_past",
        }
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, world_layer, source,
                changed_fields, payload
            ) VALUES (
                %s, %s, 'primary', 'retrograde', '{}', %s::jsonb
            )
            RETURNING id, created_at
            """,
            (event_type, prologue_id, json.dumps(wizard_backfill_payload)),
        )
        wizard_backfill_event_id, wizard_backfill_created_at = cur.fetchone()
        wizard_backfill_event_id = int(wizard_backfill_event_id)

        manifest = {
            "schema_version": "orrery_retrograde_maturation_manifest.v0",
            "persisted": True,
            "embedding_pending_chunk_ids": [summary_id],
            "embedding": {
                "status": "succeeded",
                "results": [{"chunk_id": summary_id, "job_id": "legacy-test"}],
            },
        }
        cur.execute(
            "UPDATE orrery_maturation_jobs SET result_manifest = %s::jsonb "
            "WHERE id = %s",
            (json.dumps(manifest), job_id),
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chunk_embeddings_0004d (
                chunk_id bigint NOT NULL
                    REFERENCES narrative_chunks(id) ON DELETE CASCADE,
                model text NOT NULL,
                embedding vector(4) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (chunk_id, model)
            )
            """
        )
        cur.execute(
            "INSERT INTO chunk_embeddings_0004d "
            "(chunk_id, model, embedding) VALUES (%s, %s, %s::vector)",
            (summary_id, "migration-test", "[0,0,0,0]"),
        )
    conn.commit()
    return {
        "summary_id": summary_id,
        "world_event_id": world_event_id,
        "requesting_chunk_id": requesting_chunk_id,
        "character_id": character_id,
        "entity_id": entity_id,
        "job_id": job_id,
        "summary_text": summary_text,
        "embedded_at": embedded_at,
        "legacy_created_at": legacy_created_at,
        "prologue_id": prologue_id,
        "runtime_backfill_event_id": runtime_backfill_event_id,
        "runtime_backfill_summary": runtime_backfill_summary,
        "runtime_backfill_created_at": runtime_backfill_created_at,
        "wizard_backfill_event_id": wizard_backfill_event_id,
        "wizard_backfill_summary": wizard_backfill_summary,
        "wizard_backfill_created_at": wizard_backfill_created_at,
    }


def _insert_metadata(cur: Any, chunk_id: int, *, scene: int, world_layer: str) -> None:
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer,
            time_delta, generation_date
        ) VALUES (%s, 0, 0, %s, %s::world_layer_type, interval '0 seconds', now())
        """,
        (chunk_id, scene, world_layer),
    )
