"""PostgreSQL coverage for the public maturation-jobs CLI readout."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from typing import Any, Iterator
import uuid

import psycopg2
from psycopg2 import sql
import pytest

from nexus import cli
from nexus.api import slot_utils


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    """Open a direct PostgreSQL connection to a disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@contextmanager
def _disposable_jobs_db() -> Iterator[str]:
    """Yield a unique NEXUS_template clone and always drop it afterward."""

    dbname = f"qa653_{uuid.uuid4().hex[:12]}"
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


def test_jobs_cli_reports_counts_and_non_terminal_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI reads all four states while diagnosing only queued and leased."""

    with _disposable_jobs_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO narrative_chunks (raw_text) VALUES (%s) "
                        "RETURNING id",
                        ("Issue 653 disposable chunk",),
                    )
                    chunk_id = int(cur.fetchone()[0])
                    cur.execute(
                        "INSERT INTO entities (kind) "
                        "SELECT 'character'::entity_kind "
                        "FROM generate_series(1, 4) RETURNING id"
                    )
                    entity_ids = [int(row[0]) for row in cur.fetchall()]
                    for index, (entity_id, state) in enumerate(
                        zip(
                            entity_ids,
                            ("queued", "leased", "succeeded", "failed"),
                            strict=True,
                        ),
                        start=1,
                    ):
                        cur.execute(
                            """
                            INSERT INTO orrery_maturation_jobs (
                                entity_id,
                                entity_kind,
                                entity_subtype_id,
                                entity_name,
                                slot,
                                requesting_chunk_id,
                                declaration,
                                state,
                                attempts,
                                available_at,
                                lease_until
                            ) VALUES (
                                %s, 'character', %s, %s, '4', %s,
                                '{}'::jsonb, %s::orrery_job_state, %s,
                                '2026-08-03T04:30:00+00:00'::timestamptz,
                                CASE WHEN %s = 'leased'
                                    THEN '2026-08-03T04:35:00+00:00'::timestamptz
                                    ELSE NULL
                                END
                            )
                            """,
                            (
                                entity_id,
                                index,
                                f"Entity {index}",
                                chunk_id,
                                state,
                                index - 1,
                                state,
                            ),
                        )
        finally:
            conn.close()

        monkeypatch.setattr(
            slot_utils,
            "require_slot_dbname",
            lambda *, slot: dbname,
        )
        parsed = cli.build_parser().parse_args(["jobs", "--slot", "4", "--json"])
        payload = cli.run_jobs(argparse.Namespace(slot=parsed.slot))

        assert payload["success"] is True
        assert payload["slot"] == 4
        assert payload["counts"] == {
            "queued": 1,
            "leased": 1,
            "succeeded": 1,
            "failed": 1,
        }
        assert [row["state"] for row in payload["non_terminal_jobs"]] == [
            "queued",
            "leased",
        ]
        assert [row["entity_name"] for row in payload["non_terminal_jobs"]] == [
            "Entity 1",
            "Entity 2",
        ]
        assert set(payload["non_terminal_jobs"][0]) == {
            "id",
            "state",
            "entity_kind",
            "entity_name",
            "requesting_chunk_id",
            "attempts",
            "available_at",
            "lease_until",
        }
        assert payload["non_terminal_jobs"][0]["lease_until"] is None
        assert payload["non_terminal_jobs"][1]["lease_until"] is not None
