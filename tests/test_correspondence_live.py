"""Gated live proof for one two-seat exchange and one compaction call.

Run only with NEXUS_RUN_LIVE_LLM=1, NEXUS_RUN_POSTGRES=1, and
NEXUS_CONSPIRACY_E2E=1. The test creates and drops a disposable
NEXUS_template clone; it never touches a numbered save database.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api.commit_handler_sync import compact_accepted_correspondence_sync
from nexus.api.slot_utils import VALID_DBNAMES
from nexus.config import load_settings_as_dict
from nexus.memory.correspondence import (
    correspondence_settings,
    load_accepted_correspondence,
    persist_staged_correspondence,
)


pytestmark = [
    pytest.mark.live,
    pytest.mark.live_llm,
    pytest.mark.requires_postgres,
    pytest.mark.skipif(
        os.environ.get("NEXUS_CONSPIRACY_E2E") != "1",
        reason="Set NEXUS_CONSPIRACY_E2E=1 for the live correspondence gate.",
    ),
]


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def disposable_live_correspondence_db() -> Iterator[str]:
    dbname = f"nexus_live_correspondence_{uuid.uuid4().hex[:12]}"
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
                cur.execute(
                    Path("migrations/099_storyteller_correspondence.sql").read_text()
                )
        VALID_DBNAMES.add(dbname)
        yield dbname
    finally:
        VALID_DBNAMES.discard(dbname)
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


def test_live_two_seat_exchange_and_compaction(
    disposable_live_correspondence_db: str,
) -> None:
    dbname = disposable_live_correspondence_db
    settings = load_settings_as_dict()
    config = correspondence_settings(settings)
    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE storyteller_correspondence_digest_versions,
                    storyteller_correspondence_letters, narrative_chunks
                RESTART IDENTITY CASCADE
                """
            )
            chunk_ids: list[int] = []
            for ordinal in range(1, 11):
                cur.execute(
                    """
                    INSERT INTO narrative_chunks (raw_text, storyteller_text)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (
                        f"Accepted public scene {ordinal}.",
                        f"Accepted public scene {ordinal}.",
                    ),
                )
                chunk_id = int(cur.fetchone()[0])
                chunk_ids.append(chunk_id)
                persist_staged_correspondence(
                    cur,
                    chunk_id=chunk_id,
                    writer_letter=f"Existing writer plan {ordinal}.",
                    gaia_letter=f"Existing Gaia answer {ordinal}.",
                )

    private_context = load_accepted_correspondence(
        dbname,
        max_tokens=int(config["max_rendered_tokens"]),
    )
    utility = LogonUtility(
        settings,
        dbname=dbname,
        model_override=str(settings["apex"]["model"]),
    )
    response = utility.generate_narrative(
        {
            "user_input": (
                "Continue with a quiet consequence of the locked archive; "
                "do not resolve who rang the drowned bell."
            ),
            "warm_slice": {
                "chunks": [{"text": "Accepted public scene 10.", "is_target": True}]
            },
            "entity_data": {},
            "retrieved_passages": {"results": []},
            "metadata": {"target_chunk_id": chunk_ids[-1]},
            "storyteller_correspondence": private_context,
        }
    )
    generated = utility.take_generated_correspondence()
    assert generated is not None
    assert generated.writer_letter.strip()
    assert generated.gaia_letter is not None and generated.gaia_letter.strip()
    public_dump = response.model_dump(mode="json")
    assert "letter" not in public_dump
    assert "correspondence" not in public_dump

    conn = _connect(dbname)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO narrative_chunks (raw_text, storyteller_text)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (response.narrative, response.narrative),
                )
                accepting_chunk_id = int(cur.fetchone()[0])
                persist_staged_correspondence(
                    cur,
                    chunk_id=accepting_chunk_id,
                    writer_letter=generated.writer_letter,
                    gaia_letter=generated.gaia_letter,
                )
        # Production hands compaction a free connection; it owns its own
        # transaction scope internally.
        assert compact_accepted_correspondence_sync(
            conn,
            accepting_chunk_id=accepting_chunk_id,
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT digest, compacted_through_chunk_id
                FROM storyteller_correspondence_digest_versions
                WHERE accepting_chunk_id = %s
                """,
                (accepting_chunk_id,),
            )
            digest = cur.fetchone()
            assert digest is not None
            assert str(digest["digest"]).strip()
            assert int(digest["compacted_through_chunk_id"]) == chunk_ids[4]
    finally:
        conn.close()
