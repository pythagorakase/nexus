"""Real staging-to-audit presence coverage for issues #655 and #715."""

from __future__ import annotations

import asyncio
from collections import deque
import copy
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Deque, Dict, Iterator, cast
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

from nexus.agents.logon.apex_schema import StorytellerResponseBootstrap
from nexus.agents.logon.skald_wire import SkaldTurnWire
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.lore import LORE
from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.api import (
    commit_handler_sync,
    db_pool,
    narrative,
    presence_audit,
    slot_utils,
)
from nexus.api.narrative_generation import generate_narrative_async
from nexus.config import load_settings_as_dict
from nexus.util.log_safety import quote_log_value
from scripts import new_story_setup


pytestmark = pytest.mark.requires_postgres

KNOWN_CHARACTER = "Silas Wren"
PROTAGONIST = "Lucky Baptiste"
STARTING_PLACE = "The Blue Canary"
BOOTSTRAP_PAYLOAD = {
    "narrative": (
        "Rain needles the Blue Canary windows while Silas Wren waits beneath "
        "the unlit balcony."
    ),
    "choices": [
        "Ask Silas Wren why he came.",
        "Keep playing until the room empties.",
    ],
}
ORDINARY_PAYLOAD = {
    "narrative": (
        "The last chord fades, but Silas Wren remains beyond the locked door."
    ),
    "choices": [
        "Call to Silas Wren through the door.",
        "Leave by the kitchen stairs.",
    ],
    "letter": "Keep Wren off-scene until Lucky chooses whether to answer him.",
}
DECLARED_CHARACTER = "Keller"


def _declared_payload(*, listed_present: bool) -> dict[str, Any]:
    """Build one same-turn declaration, optionally authored as entering."""

    payload: dict[str, Any] = {
        "narrative": (
            "Keller waits beneath the club awning while the rain erases the street."
        ),
        "choices": [
            "Ask Keller what brought him to the Blue Canary.",
            "Watch him from behind the locked door.",
        ],
        "new_entities": [
            {
                "kind": "character",
                "name": DECLARED_CHARACTER,
                "summary": "A rain-soaked courier making his first appearance.",
            }
        ],
        "letter": "Keep Keller's purpose unresolved after his first appearance.",
    }
    if listed_present:
        payload["presence"] = {
            "enter": [{"kind": "character", "name": DECLARED_CHARACTER}]
        }
    return payload


def _connect(dbname: str) -> Any:
    """Open a psycopg2 connection to a disposable test database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def wizard_database() -> Iterator[str]:
    """Clone the template for one test and always drop the scratch database."""

    dbname = f"qa655_wizard_{uuid4().hex[:10]}"
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
        _seed_post_transition_world(dbname)
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


def _insert_entity(cur: Any, kind: str) -> int:
    """Insert one canonical entity row and return its id."""

    cur.execute("INSERT INTO entities (kind) VALUES (%s) RETURNING id", (kind,))
    return int(cur.fetchone()[0])


def _seed_post_transition_world(dbname: str) -> None:
    """Persist the world state that the wizard hands to opening generation."""

    setting = {
        "world_name": "QA655 New Orleans",
        "genre": "historical noir",
        "tone": "rain-soaked and tense",
        "story_seed": {
            "title": "The Black Songbook",
            "seed_type": "mystery",
            "situation": "A late set ends with a stranger waiting outside.",
            "hook": "The stranger knows which song Lucky refused to play.",
            "immediate_goal": "Decide whether to answer the locked door.",
            "stakes": "The club and its musicians may be exposed.",
            "tension_source": "A patient watcher outside the club.",
            "weather": "Hard midnight rain.",
            "key_npcs": [KNOWN_CHARACTER],
            "secrets": "The watcher has the missing ledger page.",
        },
    }
    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE TABLE
                    narrative_generation_lease,
                    narrative_generation_sessions,
                    incubator,
                    narrative_chunks,
                    global_variables,
                    layers,
                    entities
                RESTART IDENTITY CASCADE
                """
            )
            cur.execute("ALTER SEQUENCE narrative_chunks_id_seq RESTART WITH 1")
            cur.execute(
                """
                INSERT INTO global_variables (
                    id, base_timestamp, setting, new_story, model
                ) VALUES (TRUE, %s, %s::jsonb, FALSE, '@test.default')
                ON CONFLICT (id) DO UPDATE SET
                    base_timestamp = EXCLUDED.base_timestamp,
                    setting = EXCLUDED.setting,
                    new_story = EXCLUDED.new_story,
                    model = EXCLUDED.model,
                    user_character = NULL
                """,
                ("1927-08-13T23:47:00+00:00", json.dumps(setting)),
            )
            cur.execute(
                "INSERT INTO layers (name, type, description) "
                "VALUES (%s, 'planet', %s) RETURNING id",
                ("Earth", "The ordinary world of 1927."),
            )
            layer_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO zones (name, summary, layer) "
                "VALUES (%s, %s, %s) RETURNING id",
                ("New Orleans", "The river wards after midnight.", layer_id),
            )
            zone_id = int(cur.fetchone()[0])
            place_entity_id = _insert_entity(cur, "place")
            cur.execute(
                """
                INSERT INTO places (
                    name, type, zone, summary, history, current_status,
                    secrets, inhabitants, extra_data, entity_id
                ) VALUES (
                    %s, 'fixed_location', %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s
                ) RETURNING id
                """,
                (
                    STARTING_PLACE,
                    zone_id,
                    "A basement jazz club below the wet street.",
                    "A discreet meeting place for dockworkers and musicians.",
                    "Closed to strangers after the final set.",
                    "The songbook contains coded warnings.",
                    [PROTAGONIST],
                    json.dumps({"atmosphere": "red glass, rain, and burnt coffee"}),
                    place_entity_id,
                ),
            )
            place_id = int(cur.fetchone()[0])

            protagonist_entity_id = _insert_entity(cur, "character")
            cur.execute(
                """
                INSERT INTO characters (
                    name, summary, appearance, background, personality,
                    current_location, extra_data, entity_id
                ) VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, %s)
                RETURNING id
                """,
                (
                    PROTAGONIST,
                    "A pianist trusted with the club's coded songbook.",
                    "A dark blue dress and rain-polished shoes.",
                    "She learned every warning song played along the river.",
                    "Careful, observant, and slow to trust strangers.",
                    place_id,
                    protagonist_entity_id,
                ),
            )
            protagonist_id = int(cur.fetchone()[0])

            known_entity_id = _insert_entity(cur, "character")
            cur.execute(
                """
                INSERT INTO characters (
                    name, summary, appearance, background, personality,
                    extra_data, entity_id
                ) VALUES (%s, %s, %s, %s, %s, '{}'::jsonb, %s)
                """,
                (
                    KNOWN_CHARACTER,
                    "A patient fixer tied to the river syndicates.",
                    "A pale suit darkened at the shoulders by rain.",
                    "He has spent years collecting favors around Pier Nine.",
                    "Courteous, exacting, and difficult to surprise.",
                    known_entity_id,
                ),
            )
            cur.execute(
                "UPDATE global_variables SET user_character = %s WHERE id = TRUE",
                (protagonist_id,),
            )
            cur.execute(
                """
                INSERT INTO narrative_chunks (
                    raw_text, storyteller_text, authorial_directives
                ) VALUES (%s, %s, %s::jsonb)
                """,
                (
                    "Synthetic Retrograde prologue anchor.",
                    "Synthetic Retrograde prologue anchor.",
                    json.dumps([RETROGRADE_PROLOGUE_MARKER]),
                ),
            )


class _SchemaBoundaryProvider:
    """Deterministic external boundary beneath the real LOGON entry path."""

    model = "TEST"

    def __init__(
        self,
        payloads: Dict[type[BaseModel], Deque[dict[str, Any]]],
    ) -> None:
        self.payloads = payloads

    async def get_structured_completion_async(
        self,
        _prompt: str,
        schema_model: type[BaseModel],
        **_kwargs: Any,
    ) -> tuple[Any, object]:
        """Validate raw provider data through the schema LOGON selected."""

        queued = self.payloads.get(schema_model)
        if not queued:
            raise AssertionError(f"No provider payload queued for {schema_model}")
        return schema_model.model_validate(queued.popleft()), SimpleNamespace()


class _ProgressRecorder:
    """Record terminal states from the genuine narrative generator."""

    def __init__(self) -> None:
        self.statuses: list[str] = []

    async def send_progress(
        self,
        _session_id: str,
        status: str,
        _data: dict[str, Any] | None = None,
    ) -> None:
        """Capture one generator progress state."""

        self.statuses.append(status)


def _route_settings() -> dict[str, Any]:
    """Use the production settings with the ordinary control pinned single-pass."""

    settings = copy.deepcopy(load_settings_as_dict())
    settings["API Settings"]["apex"]["turn_pipeline"] = "single_pass"
    settings["apex"]["turn_pipeline"] = "single_pass"
    return settings


def _install_route_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dbname: str,
    payloads: Dict[type[BaseModel], Deque[dict[str, Any]]],
) -> list[tuple[int, list[dict[str, Any]]]]:
    """Point production DB/provider boundaries at the disposable test lane."""

    scratch_dbname = dbname
    audit_observations: list[tuple[int, list[dict[str, Any]]]] = []
    genuine_audit = presence_audit.audit_chunk_presence
    route_settings = _route_settings()

    def initialize_provider(
        utility: LogonUtility,
        is_bootstrap: bool | None = None,
        **_kwargs: Any,
    ) -> None:
        bootstrap_mode = (
            utility.bootstrap_mode if is_bootstrap is None else is_bootstrap
        )
        utility.provider = cast(Any, _SchemaBoundaryProvider(payloads))
        utility._provider_bootstrap_mode = bootstrap_mode
        utility._provider_wire_type = "openai"
        utility._provider_type_name = "openai"
        utility._validation_dbname = scratch_dbname

    def load_route_settings(
        lore: LORE,
        settings_path: str | None = None,
    ) -> dict[str, Any]:
        """Give the genuine LORE route the same validated test settings."""

        del settings_path
        lore.settings_path = Path("nexus.toml").resolve()
        return copy.deepcopy(route_settings)

    def require_scratch_dbname(
        dbname: str | None = None,
        slot: int | None = None,
    ) -> str:
        """Resolve every route-style slot lookup to the disposable database."""

        del slot
        return dbname or scratch_dbname

    def record_genuine_audit(
        conn: Any,
        chunk_id: int,
        prose: str,
        *,
        parent_chunk_id: int | None = None,
        detector: Any = None,
    ) -> list[dict[str, Any]]:
        """Run the real audit and retain its findings for a positive assertion."""

        findings = genuine_audit(
            conn,
            chunk_id,
            prose,
            parent_chunk_id=parent_chunk_id,
            detector=detector,
        )
        audit_observations.append((chunk_id, findings))
        return findings

    monkeypatch.setattr(
        slot_utils,
        "VALID_DBNAMES",
        {*slot_utils.VALID_DBNAMES, scratch_dbname},
    )
    monkeypatch.setattr(LogonUtility, "_initialize_provider", initialize_provider)
    monkeypatch.setattr(LORE, "_load_settings", load_route_settings)
    monkeypatch.setattr(
        slot_utils,
        "require_slot_dbname",
        require_scratch_dbname,
    )
    monkeypatch.setattr(
        narrative,
        "get_db_connection",
        lambda _slot=None: _connect(scratch_dbname),
    )
    monkeypatch.setattr(
        narrative,
        "_start_post_commit_orrery_work",
        lambda _slot: None,
    )
    monkeypatch.setattr(
        commit_handler_sync,
        "schedule_summary_generation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        presence_audit,
        "audit_chunk_presence",
        record_genuine_audit,
    )
    return audit_observations


def _acquire_generation(session_id: str, *, parent_chunk_id: int) -> None:
    """Use the same durable ownership functions as the public continue route."""

    narrative._acquire_generation_owner(
        slot=5,
        session_id=session_id,
        operation="continue",
    )
    narrative._bind_generation_owner(
        slot=5,
        session_id=session_id,
        parent_chunk_id=parent_chunk_id,
        claim_embedding=False,
    )


def _accept_pending(session_id: str, chunk_id: int) -> int:
    """Accept through the public continue route's synchronous worker entry."""

    _choice, accepted_chunk_id, post_commit_thread = (
        narrative._resolve_and_approve_pending_sync(
            slot=5,
            session_id=session_id,
            chunk_id=chunk_id,
            user_text="",
            choice=1,
            accept_fate=False,
        )
    )
    assert post_commit_thread is None
    return accepted_chunk_id


def _assert_mentioned_row(dbname: str, chunk_id: int) -> None:
    """Assert the durable junction row names the known character as mentioned."""

    with _connect(dbname) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT c.name, ccr.reference::text AS reference
                FROM chunk_character_references AS ccr
                JOIN characters AS c ON c.id = ccr.character_id
                WHERE ccr.chunk_id = %s
                ORDER BY c.name
                """,
                (chunk_id,),
            )
            rows = list(cur.fetchall())
    assert {row["name"]: row["reference"] for row in rows} == {
        PROTAGONIST: "present",
        KNOWN_CHARACTER: "mentioned",
    }


def _assert_declared_row(
    dbname: str,
    chunk_id: int,
    *,
    expected_reference: str,
) -> None:
    """Require exactly one declared-character junction row with the given role."""

    with _connect(dbname) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT c.name, ccr.reference::text AS reference
                FROM chunk_character_references AS ccr
                JOIN characters AS c ON c.id = ccr.character_id
                WHERE ccr.chunk_id = %s AND c.name = %s
                """,
                (chunk_id, DECLARED_CHARACTER),
            )
            rows = [dict(row) for row in cur.fetchall()]
    assert rows == [{"name": DECLARED_CHARACTER, "reference": expected_reference}]


def _assert_clean_presence_audit(caplog: pytest.LogCaptureFixture) -> None:
    """Require normalization evidence and no post-commit audit tripwire."""

    messages = [record.getMessage() for record in caplog.records]
    assert f"presence prose mention normalized: {KNOWN_CHARACTER}" in messages
    assert not [
        message for message in messages if message.startswith("presence audit:")
    ]
    assert not [
        message
        for message in messages
        if message.startswith("presence audit failed for committed chunk")
    ]


def _assert_clean_declared_presence_audit(
    caplog: pytest.LogCaptureFixture,
    *,
    normalized: bool,
) -> None:
    """Assert the declared marker contract and a silent genuine audit."""

    messages = [record.getMessage() for record in caplog.records]
    marker = (
        "presence declared mention normalized: "
        f"{quote_log_value(DECLARED_CHARACTER)}"
    )
    assert (marker in messages) is normalized
    assert not [
        message for message in messages if message.startswith("presence audit:")
    ]
    assert not [
        message
        for message in messages
        if message.startswith("presence audit failed for committed chunk")
    ]


def _assert_audit_observation(
    audit_observations: list[tuple[int, list[dict[str, Any]]]],
    chunk_id: int,
) -> None:
    """Prove the real post-commit audit ran once and returned no findings."""

    assert audit_observations == [(chunk_id, [])]


def _stage_narrative(
    dbname: str,
    *,
    parent_chunk_id: int,
    settings: dict[str, Any],
) -> tuple[str, int]:
    """Drive the canonical generator through durable incubator staging."""

    session_id = str(uuid4())
    _acquire_generation(session_id, parent_chunk_id=parent_chunk_id)
    progress = _ProgressRecorder()

    async def generate() -> None:
        await generate_narrative_async(
            session_id,
            parent_chunk_id,
            "Begin the story." if parent_chunk_id == 0 else "Keep listening.",
            slot=5,
            get_db_connection=lambda _slot: _connect(dbname),
            load_settings=lambda: copy.deepcopy(settings),
            manager=progress,
            manage_generation_lease=True,
        )

    asyncio.run(generate())
    assert progress.statuses[-1] == "complete"
    return session_id, parent_chunk_id + 1


def _assert_staged_mention(
    dbname: str,
    *,
    session_id: str,
    staged_chunk_id: int,
) -> None:
    """Prove reconciliation is durable before the accept/commit boundary."""

    with _connect(dbname) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT chunk_id, reference_updates
                FROM incubator
                WHERE session_id = %s
                """,
                (session_id,),
            )
            staged = cur.fetchone()
            cur.execute(
                "SELECT id FROM characters WHERE name = %s",
                (KNOWN_CHARACTER,),
            )
            known_character_id = int(cur.fetchone()["id"])
    assert staged is not None
    assert staged["chunk_id"] == staged_chunk_id
    character_updates = staged["reference_updates"]["characters"]
    assert any(
        update.get("character_name") == KNOWN_CHARACTER
        and update["character_id"] == known_character_id
        and update["reference_type"] == "mentioned"
        for update in character_updates
    )


def _assert_staged_declared_reference(
    dbname: str,
    *,
    session_id: str,
    expected_reference: str | None,
) -> None:
    """Prove the declaration and its pre-stub reference state are staged."""

    with _connect(dbname) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT new_entities, reference_updates
                FROM incubator
                WHERE session_id = %s
                """,
                (session_id,),
            )
            staged = cur.fetchone()
    assert staged is not None
    assert [declaration["name"] for declaration in staged["new_entities"]] == [
        DECLARED_CHARACTER
    ]
    declared_references = [
        reference
        for reference in staged["reference_updates"]["characters"]
        if reference.get("character_name") == DECLARED_CHARACTER
    ]
    if expected_reference is None:
        assert declared_references == []
    else:
        assert len(declared_references) == 1
        assert declared_references[0]["reference_type"] == expected_reference


def _assert_committed_prose_names_character(
    dbname: str,
    *,
    chunk_id: int,
    character_name: str = KNOWN_CHARACTER,
) -> None:
    """Require the audited committed prose to retain the named character."""

    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT raw_text FROM narrative_chunks WHERE id = %s",
                (chunk_id,),
            )
            row = cur.fetchone()
    assert row is not None
    assert character_name in row[0]


def _accept_opening(dbname: str, settings: dict[str, Any]) -> int:
    """Create the accepted ordinary-turn parent used by issue #715 controls."""

    session_id, staged_chunk_id = _stage_narrative(
        dbname,
        parent_chunk_id=0,
        settings=settings,
    )
    return _accept_pending(session_id, staged_chunk_id)


def test_wizard_opening_stage_and_accept_reconcile_known_character(
    wizard_database: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The first staged opening persists its missing prose mention before audit."""

    payloads: Dict[type[BaseModel], Deque[dict[str, Any]]] = {
        StorytellerResponseBootstrap: deque([BOOTSTRAP_PAYLOAD.copy()]),
    }
    audit_observations = _install_route_boundaries(
        monkeypatch,
        dbname=wizard_database,
        payloads=payloads,
    )
    with caplog.at_level(logging.WARNING):
        session_id, staged_chunk_id = _stage_narrative(
            wizard_database,
            parent_chunk_id=0,
            settings=_route_settings(),
        )
        _assert_staged_mention(
            wizard_database,
            session_id=session_id,
            staged_chunk_id=staged_chunk_id,
        )
        chunk_id = _accept_pending(session_id, staged_chunk_id)

    assert chunk_id == 2
    _assert_mentioned_row(wizard_database, chunk_id)
    _assert_committed_prose_names_character(wizard_database, chunk_id=chunk_id)
    _assert_audit_observation(audit_observations, chunk_id)
    _assert_clean_presence_audit(caplog)


def test_declared_character_named_without_presence_commits_mentioned_row(
    wizard_database: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A transaction-visible same-turn stub is reconciled before junction writes."""

    payloads: Dict[type[BaseModel], Deque[dict[str, Any]]] = {
        StorytellerResponseBootstrap: deque([BOOTSTRAP_PAYLOAD.copy()]),
        SkaldTurnWire: deque([_declared_payload(listed_present=False)]),
    }
    audit_observations = _install_route_boundaries(
        monkeypatch,
        dbname=wizard_database,
        payloads=payloads,
    )
    settings = _route_settings()
    opening_chunk_id = _accept_opening(wizard_database, settings)
    audit_observations.clear()
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        session_id, staged_chunk_id = _stage_narrative(
            wizard_database,
            parent_chunk_id=opening_chunk_id,
            settings=settings,
        )
        _assert_staged_declared_reference(
            wizard_database,
            session_id=session_id,
            expected_reference=None,
        )
        chunk_id = _accept_pending(session_id, staged_chunk_id)

    assert chunk_id == 3
    _assert_declared_row(
        wizard_database,
        chunk_id,
        expected_reference="mentioned",
    )
    _assert_committed_prose_names_character(
        wizard_database,
        chunk_id=chunk_id,
        character_name=DECLARED_CHARACTER,
    )
    _assert_audit_observation(audit_observations, chunk_id)
    _assert_clean_declared_presence_audit(caplog, normalized=True)


def test_declared_character_already_listed_present_has_one_present_row(
    wizard_database: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An authored same-turn entry is accounted and never gains a duplicate mention."""

    payloads: Dict[type[BaseModel], Deque[dict[str, Any]]] = {
        StorytellerResponseBootstrap: deque([BOOTSTRAP_PAYLOAD.copy()]),
        SkaldTurnWire: deque([_declared_payload(listed_present=True)]),
    }
    audit_observations = _install_route_boundaries(
        monkeypatch,
        dbname=wizard_database,
        payloads=payloads,
    )
    settings = _route_settings()
    opening_chunk_id = _accept_opening(wizard_database, settings)
    audit_observations.clear()
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        session_id, staged_chunk_id = _stage_narrative(
            wizard_database,
            parent_chunk_id=opening_chunk_id,
            settings=settings,
        )
        _assert_staged_declared_reference(
            wizard_database,
            session_id=session_id,
            expected_reference="present",
        )
        chunk_id = _accept_pending(session_id, staged_chunk_id)

    assert chunk_id == 3
    _assert_declared_row(
        wizard_database,
        chunk_id,
        expected_reference="present",
    )
    _assert_audit_observation(audit_observations, chunk_id)
    _assert_clean_declared_presence_audit(caplog, normalized=False)


def test_ordinary_turn_control_still_normalizes_before_commit(
    wizard_database: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An ordinary child turn retains PR #663's pre-hydration behavior."""

    payloads: Dict[type[BaseModel], Deque[dict[str, Any]]] = {
        StorytellerResponseBootstrap: deque([BOOTSTRAP_PAYLOAD.copy()]),
        SkaldTurnWire: deque([ORDINARY_PAYLOAD.copy()]),
    }
    audit_observations = _install_route_boundaries(
        monkeypatch,
        dbname=wizard_database,
        payloads=payloads,
    )
    settings = _route_settings()
    opening_session_id, opening_staged_id = _stage_narrative(
        wizard_database,
        parent_chunk_id=0,
        settings=settings,
    )
    opening_chunk_id = _accept_pending(opening_session_id, opening_staged_id)
    audit_observations.clear()
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        session_id, staged_chunk_id = _stage_narrative(
            wizard_database,
            parent_chunk_id=opening_chunk_id,
            settings=settings,
        )
        _assert_staged_mention(
            wizard_database,
            session_id=session_id,
            staged_chunk_id=staged_chunk_id,
        )
        chunk_id = _accept_pending(session_id, staged_chunk_id)

    assert chunk_id == 3
    _assert_mentioned_row(wizard_database, chunk_id)
    _assert_committed_prose_names_character(wizard_database, chunk_id=chunk_id)
    _assert_audit_observation(audit_observations, chunk_id)
    _assert_clean_presence_audit(caplog)
