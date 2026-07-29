"""Real-PostgreSQL regressions for accepted private correspondence."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.events import CommitOrreryTickResult
from nexus.api import commit_handler_sync
from nexus.api.narrative_generation import write_to_incubator
from nexus.memory.correspondence import (
    persist_staged_correspondence,
    plan_correspondence_compaction,
    read_accepted_correspondence,
)
from scripts.replay_state import _verify_correspondence_provenance


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str, *, dict_cursor: bool = False) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        cursor_factory=RealDictCursor if dict_cursor else None,
    )


@pytest.fixture()
def disposable_correspondence_db() -> Iterator[str]:
    """Clone NEXUS_template, apply 098/099, and drop the clone."""

    dbname = f"nexus_test_correspondence_{uuid.uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    Path("migrations/098_narrative_generation_lease.sql").read_text()
                )
                migration = Path(
                    "migrations/099_storyteller_correspondence.sql"
                ).read_text()
                cur.execute(migration)
                cur.execute(migration)
        yield dbname
    finally:
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


def _seed_chunks(cur: Any, count: int) -> list[int]:
    ids: list[int] = []
    for index in range(1, count + 1):
        cur.execute(
            """
            INSERT INTO narrative_chunks (raw_text, storyteller_text)
            VALUES (%s, %s)
            RETURNING id
            """,
            (f"public raw {index}", f"public prose {index}"),
        )
        chunk_id = int(cur.fetchone()[0])
        ids.append(chunk_id)
        cur.execute(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer, slug
            )
            VALUES (%s, 1, 1, %s, 'primary', %s)
            """,
            (chunk_id, index, f"S01E01_{index:03d}"),
        )
    return ids


def test_accept_reject_hysteresis_and_digest_undo(
    disposable_correspondence_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dbname = disposable_correspondence_db
    monkeypatch.setattr(
        commit_handler_sync,
        "commit_orrery_tick_sync",
        lambda *_args, **_kwargs: CommitOrreryTickResult(),
    )
    monkeypatch.setattr(
        commit_handler_sync,
        "_orrery_checkpoint_interval",
        lambda: 0,
    )
    compaction_triggers: list[int] = []
    monkeypatch.setattr(
        commit_handler_sync,
        "compact_accepted_correspondence_sync",
        lambda _conn, *, accepting_chunk_id: (
            compaction_triggers.append(accepting_chunk_id) or False
        ),
    )
    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled",
        lambda: False,
    )

    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE incubator, storyteller_correspondence_digest_versions,
                    storyteller_correspondence_letters,
                    narrative_generation_lease,
                    narrative_parent_embedding_claims,
                    narrative_generation_sessions, narrative_chunks
                RESTART IDENTITY CASCADE
                """
            )
            chunk_ids = _seed_chunks(cur, 10)

            # A rejected provisional pair dies with the singleton and never
            # reaches the accepted journal.
            session_id = "00000000-0000-0000-0000-000000000617"
            cur.execute(
                """
                INSERT INTO narrative_generation_sessions (
                    session_id, operation, parent_chunk_id, status
                )
                VALUES (%s, 'continue', %s, 'initiated')
                """,
                (session_id, chunk_ids[-1]),
            )
            cur.execute(
                """
                INSERT INTO narrative_generation_lease (
                    id, session_id, parent_chunk_id, operation, expires_at
                )
                VALUES (TRUE, %s, %s, 'continue', NOW() + INTERVAL '5 minutes')
                """,
                (session_id, chunk_ids[-1]),
            )
            conn.commit()
            asyncio.run(
                write_to_incubator(
                    conn,
                    {
                        "chunk_id": 12,
                        "parent_chunk_id": chunk_ids[-1],
                        "user_text": "continue",
                        "storyteller_text": "public draft",
                        "generation_model": "TEST",
                        "choice_object": None,
                        "choice_text": None,
                        "metadata_updates": {},
                        "entity_updates": {},
                        "reference_updates": {},
                        "orrery_proposal": None,
                        "orrery_adjudications": [],
                        "new_entities": [],
                        "correspondence_writer_letter": "rejected writer secret",
                        "correspondence_gaia_letter": "rejected gaia secret",
                        "session_id": session_id,
                        "llm_response_id": "response-617",
                        "status": "provisional",
                    },
                )
            )
            cur.execute(
                """
                SELECT correspondence_writer_letter, correspondence_gaia_letter
                FROM incubator
                WHERE id = TRUE
                """
            )
            assert cur.fetchone() == (
                "rejected writer secret",
                "rejected gaia secret",
            )
            cur.execute("DELETE FROM incubator WHERE id = TRUE")
            cur.execute("SELECT count(*) FROM storyteller_correspondence_letters")
            assert cur.fetchone()[0] == 0

            # Historical setup reaches the exact ceiling. The exchange under
            # test below is never inserted by this fixture helper.
            for ordinal, chunk_id in enumerate(chunk_ids[:10], start=1):
                persist_staged_correspondence(
                    cur,
                    chunk_id=chunk_id,
                    writer_letter=f"writer secret {ordinal}",
                    gaia_letter=f"gaia secret {ordinal}",
                )

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            context_at_ten = read_accepted_correspondence(cur)
            assert len(context_at_ten.exchanges) == 10
            assert (
                plan_correspondence_compaction(
                    cur,
                    accepting_chunk_id=chunk_ids[9],
                    floor_turns=5,
                    ceiling_turns=10,
                )
                is None
            )

        # Stage the eleventh exchange through the lease-guarded production
        # writer, then accept it through the genuine production commit path.
        asyncio.run(
            write_to_incubator(
                conn,
                {
                    "chunk_id": 11,
                    "parent_chunk_id": chunk_ids[-1],
                    "user_text": "continue",
                    "storyteller_text": "public accepted scene 11",
                    "generation_model": "TEST",
                    "choice_object": None,
                    "choice_text": None,
                    "metadata_updates": {},
                    "entity_updates": {},
                    "reference_updates": {},
                    "orrery_proposal": None,
                    "orrery_adjudications": [],
                    "new_entities": [],
                    "correspondence_writer_letter": "writer secret 11",
                    "correspondence_gaia_letter": "gaia secret 11",
                    "session_id": session_id,
                    "llm_response_id": "response-accepted-617",
                    "status": "provisional",
                },
            )
        )
        accept_conn = _connect(dbname)
        try:
            accepting_chunk_id = commit_handler_sync.commit_incubator_to_database_sync(
                accept_conn,
                session_id,
                slot=None,
            )
        finally:
            accept_conn.close()
        assert compaction_triggers == [accepting_chunk_id]

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT raw_text, storyteller_text
                FROM narrative_chunks
                WHERE id = %s
                """,
                (accepting_chunk_id,),
            )
            public = cur.fetchone()
            assert public is not None
            assert "secret" not in public["raw_text"]
            assert "secret" not in public["storyteller_text"]

            cur.execute(
                """
                SELECT seat, body
                FROM storyteller_correspondence_letters
                WHERE chunk_id = %s
                ORDER BY CASE seat WHEN 'writer' THEN 1 ELSE 2 END
                """,
                (accepting_chunk_id,),
            )
            assert cur.fetchall() == [
                {"seat": "writer", "body": "writer secret 11"},
                {"seat": "gaia", "body": "gaia secret 11"},
            ]

            plan = plan_correspondence_compaction(
                cur,
                accepting_chunk_id=accepting_chunk_id,
                floor_turns=5,
                ceiling_turns=10,
            )
            assert plan is not None
            assert len(plan.aging_exchanges) == 5
            assert len(plan.recent_exchanges) == 6
            assert all(len(exchange.letters) == 2 for exchange in plan.aging_exchanges)

            # Two immutable versions make chunk undo observable: deleting the
            # accepting chunk cascades its letters/current digest, revealing
            # the prior digest as current.
            cur.execute(
                """
                INSERT INTO storyteller_correspondence_digest_versions (
                    accepting_chunk_id, compacted_through_chunk_id, digest
                )
                VALUES (%s, %s, 'prior digest'), (%s, %s, 'current digest')
                """,
                (
                    chunk_ids[9],
                    chunk_ids[3],
                    accepting_chunk_id,
                    chunk_ids[4],
                ),
            )
            assert read_accepted_correspondence(cur).digest == "current digest"
            cur.execute(
                "DELETE FROM narrative_chunks WHERE id = %s",
                (accepting_chunk_id,),
            )
            restored = read_accepted_correspondence(cur)
            assert restored.digest == "prior digest"
            assert all(
                exchange.chunk_id != accepting_chunk_id
                for exchange in restored.exchanges
            )
            with conn.cursor() as replay_cur:
                assert _verify_correspondence_provenance(replay_cur) == []
