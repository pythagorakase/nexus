"""PostgreSQL regressions for Retrograde summary embedding and repair.

Every test uses real configured MEMNON embedding models against one disposable
``NEXUS_template`` clone. No save-slot or template database is mutated.
"""

from __future__ import annotations

import json
from typing import Any, Iterator
import uuid

from psycopg2 import sql
import pytest

from nexus import cli
from nexus.agents.memnon.utils.db_access import (
    _execute_retrograde_summary_vector_search,
)
from nexus.agents.memnon.utils.embedding_tables import (
    retrograde_summary_table_name_for_dimensions,
)
from nexus.agents.memnon.utils.source_embeddings import (
    RETROGRADE_SUMMARY_SOURCE,
    count_stamped_without_vectors,
)
from nexus.agents.orrery.retrograde_embedding import (
    active_memnon_embedding_model_dimensions,
    embed_retrograde_summaries,
)
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
)


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    """Open a direct connection to the disposable issue-665 database."""
    return connect(dbname)


@pytest.fixture(scope="module")
def disposable_db() -> Iterator[str]:
    """Yield a template clone shared by every regression, dropped afterward."""
    with disposable_slot_database("qa665") as dbname:
        yield dbname


@pytest.fixture()
def route_disposable_db(
    disposable_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route slot 4, and only slot 4, to the disposable clone.

    The shared contract rebinds every loaded resolver and narrows
    ``VALID_DBNAMES`` to the clone, so a slot-only entry point reaches the
    clone and any other slot or database name raises.
    """
    route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=disposable_db)


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


def _stamped_without_vectors(dbname: str) -> int:
    """Run the read-only audit on a plain tuple cursor."""
    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            return count_stamped_without_vectors(
                cur,
                RETROGRADE_SUMMARY_SOURCE,
                active_memnon_embedding_model_dimensions(),
            )
    finally:
        conn.close()


def test_stamped_without_vector_audit_follows_damage_and_repair(
    disposable_db: str,
    route_disposable_db: None,
) -> None:
    """The audit counts stamped summaries missing any active vector (#848).

    ``tests/test_jobs_cli_pg.py`` covers the same audit through ``nexus jobs``.
    """
    baseline = _stamped_without_vectors(disposable_db)
    stamped_id = _insert_retrograde_summaries(
        disposable_db,
        ["The audited ferry log was stamped before any vector existed."],
        stamped=True,
    )[0]
    _insert_retrograde_summaries(
        disposable_db,
        ["An unstamped summary is pending work, not damage."],
    )

    assert _stamped_without_vectors(disposable_db) == baseline + 1

    embed_retrograde_summaries(disposable_db, [stamped_id])
    assert _stamped_without_vectors(disposable_db) == baseline

    model, dimensions = next(iter(active_memnon_embedding_model_dimensions().items()))
    conn = _connect(disposable_db)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "DELETE FROM {} WHERE summary_id = %s AND model = %s"
                    ).format(
                        sql.Identifier(
                            retrograde_summary_table_name_for_dimensions(dimensions)
                        )
                    ),
                    (stamped_id, model),
                )
    finally:
        conn.close()
    assert _stamped_without_vectors(disposable_db) == baseline + 1
