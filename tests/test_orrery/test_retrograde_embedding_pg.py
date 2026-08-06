"""PostgreSQL regressions for Retrograde summary embedding and repair.

Every test uses real configured MEMNON embedding models against one disposable
``NEXUS_template`` clone. No save-slot or template database is mutated.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator
import uuid

import psycopg2
from psycopg2 import sql
import pytest

from nexus import cli
from nexus.agents.memnon.utils.db_access import (
    _execute_retrograde_summary_vector_search,
)
from nexus.agents.memnon.utils.embedding_tables import (
    retrograde_summary_table_name_for_dimensions,
)
from nexus.agents.orrery.retrograde_embedding import (
    active_memnon_embedding_model_dimensions,
    embed_retrograde_summaries,
)
from nexus.api import db_pool, slot_utils


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    """Open a direct connection to the disposable issue-665 database."""
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@pytest.fixture(scope="module")
def disposable_db() -> Iterator[str]:
    """Yield a unique template clone and drop it after all regressions."""
    dbname = f"qa665_{uuid.uuid4().hex[:12]}"
    admin: Any = None
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
        yield dbname
    finally:
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


@pytest.fixture()
def route_disposable_db(
    disposable_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route slot-only production entry points to the disposable clone."""

    def require_disposable_db(
        dbname: str | None = None,
        slot: int | None = None,
    ) -> str:
        if dbname is not None and dbname != disposable_db:
            raise AssertionError(f"unexpected database target: {dbname}")
        if slot is not None and slot != 4:
            raise AssertionError(f"unexpected slot target: {slot}")
        return disposable_db

    monkeypatch.setattr(db_pool, "require_slot_dbname", require_disposable_db)
    monkeypatch.setattr(slot_utils, "slot_dbname", lambda slot: disposable_db)


def _insert_retrograde_summaries(
    dbname: str,
    summary_texts: list[str],
    *,
    stamped: bool = False,
) -> list[int]:
    """Insert canonical events and dedicated summaries for a regression."""
    conn = _connect(dbname)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO narrative_chunks (raw_text) VALUES (%s) RETURNING id",
                    ("Issue 665 disposable recording boundary",),
                )
                chunk_id = int(cur.fetchone()[0])
                cur.execute(
                    "SELECT type FROM event_types "
                    "WHERE type::text NOT LIKE '%project_started%' "
                    "ORDER BY type LIMIT 1"
                )
                event_type = cur.fetchone()[0]
                summary_ids: list[int] = []
                for index, summary_text in enumerate(summary_texts):
                    event_ref = f"qa665_{uuid.uuid4().hex}_{index}"
                    payload = {
                        "retrograde_event_ref": event_ref,
                        "summary": summary_text,
                        "chronology": "deep_past",
                    }
                    cur.execute(
                        """
                        INSERT INTO world_events (
                            event_type,
                            tick_chunk_id,
                            world_layer,
                            source,
                            changed_fields,
                            payload
                        ) VALUES (
                            %s, %s, 'primary', 'retrograde', '{}', %s::jsonb
                        )
                        RETURNING id
                        """,
                        (event_type, chunk_id, json.dumps(payload)),
                    )
                    world_event_id = int(cur.fetchone()[0])
                    cur.execute(
                        """
                        INSERT INTO retrograde_summaries (
                            world_event_id,
                            recorded_at_chunk_id,
                            chronology,
                            summary_text,
                            embedding_generated_at
                        ) VALUES (
                            %s, %s, 'deep_past', %s,
                            CASE WHEN %s
                                THEN '2000-01-01T00:00:00+00:00'::timestamptz
                                ELSE NULL
                            END
                        )
                        RETURNING id
                        """,
                        (world_event_id, chunk_id, summary_text, stamped),
                    )
                    summary_ids.append(int(cur.fetchone()[0]))
                return summary_ids
    finally:
        conn.close()


def _drop_active_summary_embedding_tables(dbname: str) -> None:
    """Remove lazily-created active-model tables inside the disposable DB."""
    dimensions = set(active_memnon_embedding_model_dimensions().values())
    conn = _connect(dbname)
    try:
        with conn:
            with conn.cursor() as cur:
                for dimension in dimensions:
                    table_name = retrograde_summary_table_name_for_dimensions(dimension)
                    cur.execute(
                        sql.SQL("DROP TABLE IF EXISTS {}").format(
                            sql.Identifier(table_name)
                        )
                    )
    finally:
        conn.close()


def _run_embed_history(slot: int, *, execute: bool) -> dict[str, Any]:
    """Parse and invoke the genuine public CLI-level embed-history function."""
    argv = ["--json", "retrograde-embed-history", "--slot", str(slot)]
    if execute:
        argv.append("--execute")
    args = cli.build_parser().parse_args(argv)
    return cli.run_retrograde_embed_history(args)


def test_batch_embedding_writes_every_summary_model_pair(
    disposable_db: str,
    route_disposable_db: None,
) -> None:
    """A genuine batch stores every requested summary under every active model."""
    summary_ids = _insert_retrograde_summaries(
        disposable_db,
        [
            "The brass archive inherited a debt before the first crossing.",
            "A winter courier hid the rival ledger beneath the empty observatory.",
        ],
    )
    active_models = active_memnon_embedding_model_dimensions()

    results = embed_retrograde_summaries(disposable_db, summary_ids)

    assert [result["summary_id"] for result in results] == summary_ids
    conn = _connect(disposable_db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, embedding_generated_at FROM retrograde_summaries "
                "WHERE id = ANY(%s) ORDER BY id",
                (summary_ids,),
            )
            stamp_rows = cur.fetchall()
            assert [row[0] for row in stamp_rows] == summary_ids
            assert all(row[1] is not None for row in stamp_rows)

            for model, dimensions in active_models.items():
                table_name = retrograde_summary_table_name_for_dimensions(dimensions)
                cur.execute(
                    sql.SQL(
                        "SELECT summary_id, model FROM {} "
                        "WHERE summary_id = ANY(%s) AND model = %s "
                        "ORDER BY summary_id"
                    ).format(sql.Identifier(table_name)),
                    (summary_ids, model),
                )
                assert cur.fetchall() == [
                    (summary_id, model) for summary_id in summary_ids
                ]
    finally:
        conn.close()


def test_cli_repairs_stamped_summary_when_vector_table_is_missing(
    disposable_db: str,
    route_disposable_db: None,
) -> None:
    """Dry-run detects old damage and execute recreates every active vector."""
    summary_id = _insert_retrograde_summaries(
        disposable_db,
        ["The stamped but vectorless treaty named the wrong surviving witness."],
        stamped=True,
    )[0]
    active_models = active_memnon_embedding_model_dimensions()
    _drop_active_summary_embedding_tables(disposable_db)
    conn = _connect(disposable_db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT embedding_generated_at FROM retrograde_summaries WHERE id = %s",
                (summary_id,),
            )
            old_stamp = cur.fetchone()[0]
    finally:
        conn.close()

    dry_run_payload = _run_embed_history(4, execute=False)

    assert dry_run_payload["success"] is True
    dry_run = dry_run_payload["retrograde_embed_history"]
    damaged_row = next(
        row for row in dry_run["summary_rows"] if row["summary_id"] == summary_id
    )
    assert damaged_row["status"] == "stamped_missing_vectors"
    assert damaged_row["embedding_pending"] is True
    assert damaged_row["missing_embedding_models"] == [
        {
            "model": model,
            "dimensions": dimensions,
            "table": retrograde_summary_table_name_for_dimensions(dimensions),
        }
        for model, dimensions in active_models.items()
    ]
    assert summary_id in dry_run["embedding_pending_summary_ids"]

    conn = _connect(disposable_db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT embedding_generated_at FROM retrograde_summaries WHERE id = %s",
                (summary_id,),
            )
            assert cur.fetchone()[0] == old_stamp
            for dimensions in set(active_models.values()):
                table_name = retrograde_summary_table_name_for_dimensions(dimensions)
                cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
                assert cur.fetchone()[0] is None
    finally:
        conn.close()

    execute_payload = _run_embed_history(4, execute=True)

    assert execute_payload["success"] is True
    execute = execute_payload["retrograde_embed_history"]
    assert summary_id in execute["embedding_pending_summary_ids"]
    assert summary_id in {
        result["summary_id"] for result in execute["embedding_results"]
    }
    conn = _connect(disposable_db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT embedding_generated_at FROM retrograde_summaries WHERE id = %s",
                (summary_id,),
            )
            assert cur.fetchone()[0] > old_stamp
            for model, dimensions in active_models.items():
                table_name = retrograde_summary_table_name_for_dimensions(dimensions)
                cur.execute(
                    sql.SQL(
                        "SELECT count(*) FROM {} WHERE summary_id = %s AND model = %s"
                    ).format(sql.Identifier(table_name)),
                    (summary_id, model),
                )
                assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_repaired_summary_participates_in_dedicated_vector_join(
    disposable_db: str,
    route_disposable_db: None,
) -> None:
    """CLI-repaired vectors are visible through MEMNON's dedicated join."""
    summary_text = (
        "The repaired eclipse account binds the glass navigator to the hidden quay."
    )
    summary_id = _insert_retrograde_summaries(
        disposable_db,
        [summary_text],
        stamped=True,
    )[0]
    active_models = active_memnon_embedding_model_dimensions()
    conn = _connect(disposable_db)
    try:
        with conn:
            with conn.cursor() as cur:
                for model, dimensions in active_models.items():
                    table_name = retrograde_summary_table_name_for_dimensions(
                        dimensions
                    )
                    cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
                    if cur.fetchone()[0] is not None:
                        cur.execute(
                            sql.SQL(
                                "DELETE FROM {} WHERE summary_id = %s AND model = %s"
                            ).format(sql.Identifier(table_name)),
                            (summary_id, model),
                        )
    finally:
        conn.close()

    execute_payload = _run_embed_history(4, execute=True)
    assert execute_payload["success"] is True
    assert (
        summary_id
        in execute_payload["retrograde_embed_history"]["embedding_pending_summary_ids"]
    )

    conn = _connect(disposable_db)
    try:
        with conn.cursor() as cur:
            for model, dimensions in active_models.items():
                table_name = retrograde_summary_table_name_for_dimensions(dimensions)
                cur.execute(
                    sql.SQL(
                        "SELECT embedding::text FROM {} "
                        "WHERE summary_id = %s AND model = %s"
                    ).format(sql.Identifier(table_name)),
                    (summary_id, model),
                )
                embedding_value = cur.fetchone()[0]
                results = _execute_retrograde_summary_vector_search(
                    cur,
                    dimensions,
                    embedding_value,
                    model,
                    10,
                )
                repaired = next(
                    result for result in results if result["summary_id"] == summary_id
                )
                assert repaired["text"] == summary_text
                assert repaired["source"] == "vector_search"
    finally:
        conn.close()
