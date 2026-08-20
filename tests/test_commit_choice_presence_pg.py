"""PostgreSQL commit coverage for enacted-choice roster mentions."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterator
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import psycopg2
from psycopg2 import sql
import pytest

from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PresenceBaseline,
    PresenceDelta,
    SkaldTurnWire,
    hydrate_skald_turn,
)
from nexus.api import commit_handler, commit_handler_sync, db_pool, presence_audit
from nexus.api.lore_adapter import response_to_incubator
from nexus.api.presence_reconciliation import (
    CharacterRosterRows,
    reconcile_prose_mentions,
)
from nexus.memory.manager import empty_pass2_baseline
from scripts import new_story_setup


pytestmark = pytest.mark.requires_postgres

ROSTER_CHARACTER = "Len Aster"
ROSTER_ALIAS = "Lantern Fox"
SHORT_CHARACTER = "Ann"
LONG_CHARACTER = "Ann Lee"
TEST_BASELINE_PAYLOAD = empty_pass2_baseline({}).model_dump(mode="json")


def _connect(dbname: str) -> Any:
    """Open a psycopg2 connection to the disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


async def _connect_async(dbname: str) -> asyncpg.Connection:
    """Open an asyncpg connection with the application's JSON codecs."""

    conn = await asyncpg.connect(
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )
    for type_name in ("json", "jsonb"):
        await conn.set_type_codec(
            type_name,
            schema="pg_catalog",
            encoder=json.dumps,
            decoder=json.loads,
        )
    return conn


@pytest.fixture(scope="module")
def choice_presence_database() -> Iterator[str]:
    """Initialize one dump-based scratch database and drop it afterward."""

    dbname = f"qa_wt715_{uuid4().hex[:12]}"
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


def _reset_world(cur: Any, character_names: list[str]) -> dict[str, int]:
    """Reset disposable state and return IDs for a fresh roster."""

    cur.execute(
        "TRUNCATE incubator, narrative_chunks, characters " "RESTART IDENTITY CASCADE"
    )
    cur.execute(
        """
        INSERT INTO global_variables (
            id, base_timestamp, setting, new_story, model
        ) VALUES (TRUE, %s, '{}'::jsonb, FALSE, '@test.default')
        ON CONFLICT (id) DO UPDATE SET
            base_timestamp = EXCLUDED.base_timestamp,
            new_story = EXCLUDED.new_story,
            model = EXCLUDED.model,
            user_character = NULL
        """,
        ("2089-10-17T18:00:00+00:00",),
    )
    character_ids: dict[str, int] = {}
    for name in character_names:
        cur.execute(
            "INSERT INTO characters (name, summary) VALUES (%s, %s) RETURNING id",
            (name, f"A roster identity used by issue 715 QA: {name}."),
        )
        character_ids[name] = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO characters (name, summary) VALUES (%s, %s) RETURNING id",
        ("Test Protagonist", "The canonical player for commit-side work."),
    )
    protagonist_id = int(cur.fetchone()[0])
    cur.execute(
        "UPDATE global_variables SET user_character = %s WHERE id = TRUE",
        (protagonist_id,),
    )
    return character_ids


def _insert_staged_turn(
    cur: Any,
    *,
    session_id: str,
    parent_chunk_id: int,
    storyteller_text: str,
    choice_object: dict[str, Any] | None,
    choice_text: str | None,
    reference_updates: dict[str, Any],
    metadata_updates: dict[str, Any] | None = None,
    entity_updates: dict[str, Any] | None = None,
    new_entities: list[dict[str, Any]] | None = None,
) -> None:
    """Insert one fully shaped incubator row for the genuine commit readers."""

    cur.execute(
        """
        INSERT INTO incubator (
            id, chunk_id, parent_chunk_id, user_text, storyteller_text,
            generation_model, choice_object, choice_text,
            metadata_updates, entity_updates, reference_updates,
            orrery_proposal, orrery_adjudications, new_entities,
            lore_pass_baseline, session_id, llm_response_id, status
        ) VALUES (
            TRUE, %s, %s, 'Enact the selected response.', %s, 'TEST',
            %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, NULL,
            '[]'::jsonb, %s::jsonb, %s::jsonb, %s,
            'qa-wt715-response', 'provisional'
        )
        """,
        (
            parent_chunk_id + 1,
            parent_chunk_id,
            storyteller_text,
            json.dumps(choice_object) if choice_object is not None else None,
            choice_text,
            json.dumps(metadata_updates or {}),
            json.dumps(entity_updates) if entity_updates is not None else None,
            json.dumps(reference_updates),
            json.dumps(new_entities or []),
            json.dumps(TEST_BASELINE_PAYLOAD),
            session_id,
        ),
    )


def _stage_choice_turn(
    dbname: str,
    *,
    choice_object: dict[str, Any] | None,
    choice_text: str | None,
    character_reference: str | None = None,
    alias: str | None = None,
) -> tuple[str, int]:
    """Reset the scratch state and stage one bootstrap turn for real commit."""

    session_id = str(uuid4())
    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            character_ids = _reset_world(cur, [ROSTER_CHARACTER])
            character_id = character_ids[ROSTER_CHARACTER]
            if alias is not None:
                cur.execute(
                    "INSERT INTO character_aliases (character_id, alias) "
                    "VALUES (%s, %s)",
                    (character_id, alias),
                )

            character_references = []
            if character_reference is not None:
                character_references.append(
                    {
                        "character_id": character_id,
                        "reference_type": character_reference,
                    }
                )
            _insert_staged_turn(
                cur,
                session_id=session_id,
                parent_chunk_id=0,
                storyteller_text="Rain closes over the empty platform.",
                choice_object=choice_object,
                choice_text=choice_text,
                reference_updates={
                    "characters": character_references,
                    "places": [],
                    "factions": [],
                },
            )
    return session_id, character_id


def _stage_authored_exit_turn(dbname: str) -> tuple[str, int, int]:
    """Stage the exact empty-reference shape produced by hydrated presence.exit."""

    session_id = str(uuid4())
    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            character_ids = _reset_world(cur, [ROSTER_CHARACTER])
            character_id = character_ids[ROSTER_CHARACTER]
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
                "VALUES (%s, %s) RETURNING id",
                (
                    "Len Aster waits on the platform.",
                    "Len Aster waits on the platform.",
                ),
            )
            parent_chunk_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO chunk_metadata (
                    chunk_id, season, episode, scene, world_layer, slug
                ) VALUES (%s, 1, 1, 1, 'primary', 'S01E01_001')
                """,
                (parent_chunk_id,),
            )
            cur.execute(
                """
                INSERT INTO chunk_character_references (
                    chunk_id, character_id, reference
                ) VALUES (%s, %s, 'present')
                """,
                (parent_chunk_id, character_id),
            )

            baseline = PresenceBaseline(
                present=[
                    CharacterRef(
                        kind="character",
                        name=ROSTER_CHARACTER,
                        id=character_id,
                    )
                ]
            )
            wire = SkaldTurnWire(
                narrative="Len Aster leaves the rain-dark platform behind.",
                choices=["Follow the departing train.", "Wait beneath the clock."],
                presence=PresenceDelta(
                    exit=[
                        CharacterRef(
                            kind="character",
                            name=ROSTER_CHARACTER,
                            id=character_id,
                        )
                    ]
                ),
                letter="Preserve Len Aster's authored departure.",
            )
            reconcile_prose_mentions(
                wire,
                presence_baseline=baseline,
                roster_rows=CharacterRosterRows(
                    characters=[
                        {
                            "id": character_id,
                            "name": ROSTER_CHARACTER,
                            "summary": None,
                        }
                    ],
                    aliases=[],
                ),
            )
            hydrated = hydrate_skald_turn(wire, presence_baseline=baseline)
            hydrated.generation_model = "TEST"
            payload = response_to_incubator(
                hydrated,
                parent_chunk_id=parent_chunk_id,
                user_text="Continue.",
                session_id=session_id,
                lore_pass_baseline=empty_pass2_baseline({}),
            )
            assert payload["reference_updates"]["characters"] == []
            _insert_staged_turn(
                cur,
                session_id=session_id,
                parent_chunk_id=parent_chunk_id,
                storyteller_text=payload["storyteller_text"],
                choice_object=payload["choice_object"],
                choice_text=payload["choice_text"],
                metadata_updates=payload["metadata_updates"],
                entity_updates=payload["entity_updates"],
                reference_updates=payload["reference_updates"],
                new_entities=payload["new_entities"],
            )
    return session_id, character_id, parent_chunk_id


def _stage_overlapping_choice_turn(
    dbname: str,
    *,
    choice_text: str,
) -> tuple[str, dict[str, int]]:
    """Stage choice prose against canonical overlapping roster names."""

    session_id = str(uuid4())
    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            character_ids = _reset_world(cur, [SHORT_CHARACTER, LONG_CHARACTER])
            _insert_staged_turn(
                cur,
                session_id=session_id,
                parent_chunk_id=0,
                storyteller_text="Rain closes over the empty platform.",
                choice_object=None,
                choice_text=choice_text,
                reference_updates={"characters": [], "places": [], "factions": []},
            )
    return session_id, character_ids


def _assert_reference_row(
    conn: Any,
    *,
    chunk_id: int,
    character_id: int,
    expected_reference: str,
) -> None:
    """Require one durable junction row with the expected precedence."""

    with conn.cursor() as cur:
        cur.execute(
            "SELECT reference::text FROM chunk_character_references "
            "WHERE chunk_id = %s AND character_id = %s",
            (chunk_id, character_id),
        )
        rows = cur.fetchall()
    assert rows == [(expected_reference,)]


def _assert_no_audit_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Require the read-only presence audit to stay silent."""

    messages = [record.getMessage() for record in caplog.records]
    assert not [
        message for message in messages if message.startswith("presence audit:")
    ]
    assert not [
        message
        for message in messages
        if message.startswith("presence audit failed for committed chunk")
    ]


@pytest.mark.parametrize(
    ("choice_object", "choice_text", "alias"),
    [
        (None, "I ask Len Aster to meet me after midnight.", None),
        (
            {
                "presented": [
                    "Send Len Aster a warning from the platform.",
                    "Wait beneath the station clock.",
                ],
                "selected": 1,
            },
            None,
            None,
        ),
        (None, "I leave the station ledger for Lantern Fox.", ROSTER_ALIAS),
    ],
    ids=["free-text", "structured", "alias"],
)
def test_sync_commit_reconciles_enacted_choice_roster_mentions(
    choice_presence_database: str,
    caplog: pytest.LogCaptureFixture,
    choice_object: dict[str, Any] | None,
    choice_text: str | None,
    alias: str | None,
) -> None:
    """The genuine sync commit persists canonical choice-only mentions."""

    session_id, character_id = _stage_choice_turn(
        choice_presence_database,
        choice_object=choice_object,
        choice_text=choice_text,
        alias=alias,
    )
    conn = _connect(choice_presence_database)
    try:
        with caplog.at_level(logging.WARNING):
            chunk_id = commit_handler_sync.commit_incubator_to_database_sync(
                conn,
                session_id,
                slot=None,
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT raw_text, storyteller_text "
                    "FROM narrative_chunks WHERE id = %s",
                    (chunk_id,),
                )
                raw_text, storyteller_text = (str(value) for value in cur.fetchone())
            named_form = alias or ROSTER_CHARACTER
            assert named_form in raw_text
            assert named_form not in storyteller_text
            findings = presence_audit.audit_chunk_presence(
                conn,
                chunk_id,
                raw_text,
                parent_chunk_id=0,
            )

        _assert_reference_row(
            conn,
            chunk_id=chunk_id,
            character_id=character_id,
            expected_reference="mentioned",
        )
        assert findings == []
        _assert_no_audit_warning(caplog)
    finally:
        conn.close()


def test_sync_commit_preserves_present_precedence_for_choice_mention(
    choice_presence_database: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A staged present row is neither duplicated nor downgraded by choice prose."""

    session_id, character_id = _stage_choice_turn(
        choice_presence_database,
        choice_object=None,
        choice_text="I ask Len Aster to wait beyond the platform gate.",
        character_reference="present",
    )
    conn = _connect(choice_presence_database)
    try:
        with caplog.at_level(logging.WARNING):
            chunk_id = commit_handler_sync.commit_incubator_to_database_sync(
                conn,
                session_id,
                slot=None,
            )
        _assert_reference_row(
            conn,
            chunk_id=chunk_id,
            character_id=character_id,
            expected_reference="present",
        )
        assert f"presence prose mention normalized: {ROSTER_CHARACTER}" not in [
            record.getMessage() for record in caplog.records
        ]
    finally:
        conn.close()


def test_sync_commit_preserves_hydrated_authored_exit(
    choice_presence_database: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A hydrated authored exit stays rowless and audit-accounted on sync commit."""

    session_id, character_id, parent_chunk_id = _stage_authored_exit_turn(
        choice_presence_database
    )
    conn = _connect(choice_presence_database)
    try:
        with caplog.at_level(logging.WARNING):
            chunk_id = commit_handler_sync.commit_incubator_to_database_sync(
                conn,
                session_id,
                slot=None,
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT raw_text FROM narrative_chunks WHERE id = %s",
                    (chunk_id,),
                )
                raw_text = str(cur.fetchone()[0])
                cur.execute(
                    "SELECT reference::text FROM chunk_character_references "
                    "WHERE chunk_id = %s AND character_id = %s",
                    (chunk_id, character_id),
                )
                rows = cur.fetchall()
            findings = presence_audit.audit_chunk_presence(
                conn,
                chunk_id,
                raw_text,
                parent_chunk_id=parent_chunk_id,
            )

        assert ROSTER_CHARACTER in raw_text
        assert rows == []
        assert findings == []
        _assert_no_audit_warning(caplog)
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("choice_text", "expected_character"),
    [
        ("I ask Ann Lee to wait beneath the clock.", LONG_CHARACTER),
        ("I ask Ann to wait beneath the clock.", SHORT_CHARACTER),
    ],
    ids=["longest-match", "shorter-name-only"],
)
def test_sync_commit_suppresses_only_contained_shorter_name(
    choice_presence_database: str,
    caplog: pytest.LogCaptureFixture,
    choice_text: str,
    expected_character: str,
) -> None:
    """Sync choice reconciliation keeps only the longest matched span."""

    session_id, character_ids = _stage_overlapping_choice_turn(
        choice_presence_database,
        choice_text=choice_text,
    )
    conn = _connect(choice_presence_database)
    try:
        with caplog.at_level(logging.WARNING):
            chunk_id = commit_handler_sync.commit_incubator_to_database_sync(
                conn,
                session_id,
                slot=None,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.name, ccr.reference::text
                    FROM chunk_character_references AS ccr
                    JOIN characters AS c ON c.id = ccr.character_id
                    WHERE ccr.chunk_id = %s AND c.id IN (%s, %s)
                    ORDER BY c.id
                    """,
                    (
                        chunk_id,
                        character_ids[SHORT_CHARACTER],
                        character_ids[LONG_CHARACTER],
                    ),
                )
                rows = cur.fetchall()
                cur.execute(
                    "SELECT raw_text FROM narrative_chunks WHERE id = %s",
                    (chunk_id,),
                )
                raw_text = str(cur.fetchone()[0])
            findings = presence_audit.audit_chunk_presence(
                conn,
                chunk_id,
                raw_text,
                parent_chunk_id=0,
            )

        assert rows == [(expected_character, "mentioned")]
        assert findings == []
        _assert_no_audit_warning(caplog)
    finally:
        conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("choice_object", "choice_text"),
    [
        (None, "I ask Len Aster to meet me after midnight."),
        (
            {
                "presented": [
                    "Send Len Aster a warning from the platform.",
                    "Wait beneath the station clock.",
                ],
                "selected": 1,
            },
            None,
        ),
    ],
    ids=["free-text", "structured"],
)
async def test_async_commit_reconciles_enacted_choice_roster_mentions(
    choice_presence_database: str,
    caplog: pytest.LogCaptureFixture,
    choice_object: dict[str, Any] | None,
    choice_text: str | None,
) -> None:
    """The genuine async commit mirrors free-text and structured reconciliation."""

    session_id, character_id = _stage_choice_turn(
        choice_presence_database,
        choice_object=choice_object,
        choice_text=choice_text,
    )
    conn = await _connect_async(choice_presence_database)
    try:
        with caplog.at_level(logging.WARNING):
            chunk_id = await commit_handler.commit_incubator_to_database(
                conn,
                session_id,
                slot=None,
            )
            raw_text = await conn.fetchval(
                "SELECT raw_text FROM narrative_chunks WHERE id = $1",
                chunk_id,
            )
            storyteller_text = await conn.fetchval(
                "SELECT storyteller_text FROM narrative_chunks WHERE id = $1",
                chunk_id,
            )
            assert ROSTER_CHARACTER in str(raw_text)
            assert ROSTER_CHARACTER not in str(storyteller_text)
            findings = await presence_audit.audit_chunk_presence_async(
                conn,
                chunk_id,
                str(raw_text),
                parent_chunk_id=0,
            )
        rows = await conn.fetch(
            "SELECT reference::text AS reference "
            "FROM chunk_character_references "
            "WHERE chunk_id = $1 AND character_id = $2",
            chunk_id,
            character_id,
        )
        assert [row["reference"] for row in rows] == ["mentioned"]
        assert findings == []
        _assert_no_audit_warning(caplog)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_async_commit_preserves_hydrated_authored_exit(
    choice_presence_database: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A hydrated authored exit stays rowless and audit-accounted asynchronously."""

    session_id, character_id, parent_chunk_id = _stage_authored_exit_turn(
        choice_presence_database
    )
    conn = await _connect_async(choice_presence_database)
    try:
        with caplog.at_level(logging.WARNING):
            chunk_id = await commit_handler.commit_incubator_to_database(
                conn,
                session_id,
                slot=None,
            )
            raw_text = str(
                await conn.fetchval(
                    "SELECT raw_text FROM narrative_chunks WHERE id = $1",
                    chunk_id,
                )
            )
            rows = await conn.fetch(
                "SELECT reference::text AS reference "
                "FROM chunk_character_references "
                "WHERE chunk_id = $1 AND character_id = $2",
                chunk_id,
                character_id,
            )
            findings = await presence_audit.audit_chunk_presence_async(
                conn,
                chunk_id,
                raw_text,
                parent_chunk_id=parent_chunk_id,
            )

        assert ROSTER_CHARACTER in raw_text
        assert rows == []
        assert findings == []
        _assert_no_audit_warning(caplog)
    finally:
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("choice_text", "expected_character"),
    [
        ("I ask Ann Lee to wait beneath the clock.", LONG_CHARACTER),
        ("I ask Ann to wait beneath the clock.", SHORT_CHARACTER),
    ],
    ids=["longest-match", "shorter-name-only"],
)
async def test_async_commit_suppresses_only_contained_shorter_name(
    choice_presence_database: str,
    caplog: pytest.LogCaptureFixture,
    choice_text: str,
    expected_character: str,
) -> None:
    """Async choice reconciliation keeps only the longest matched span."""

    session_id, character_ids = _stage_overlapping_choice_turn(
        choice_presence_database,
        choice_text=choice_text,
    )
    conn = await _connect_async(choice_presence_database)
    try:
        with caplog.at_level(logging.WARNING):
            chunk_id = await commit_handler.commit_incubator_to_database(
                conn,
                session_id,
                slot=None,
            )
            rows = await conn.fetch(
                """
                SELECT c.name, ccr.reference::text AS reference
                FROM chunk_character_references AS ccr
                JOIN characters AS c ON c.id = ccr.character_id
                WHERE ccr.chunk_id = $1 AND c.id = ANY($2::bigint[])
                ORDER BY c.id
                """,
                chunk_id,
                [
                    character_ids[SHORT_CHARACTER],
                    character_ids[LONG_CHARACTER],
                ],
            )
            raw_text = str(
                await conn.fetchval(
                    "SELECT raw_text FROM narrative_chunks WHERE id = $1",
                    chunk_id,
                )
            )
            findings = await presence_audit.audit_chunk_presence_async(
                conn,
                chunk_id,
                raw_text,
                parent_chunk_id=0,
            )

        assert [(row["name"], row["reference"]) for row in rows] == [
            (expected_character, "mentioned")
        ]
        assert findings == []
        _assert_no_audit_warning(caplog)
    finally:
        await conn.close()
