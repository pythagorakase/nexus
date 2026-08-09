"""Disposable-PostgreSQL prompt regressions for recent Orrery rulings."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2 import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import (
    TurnCycleManager,
    _context_component_token_count,
)
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
    resolve_dry_run,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.config import load_settings_as_dict
from nexus.memory import ContextMemoryManager

pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    """Open a direct connection to the disposable Issue 685 database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _insert_accepted_chunk_after_rollback_gap(dbname: str, index: int) -> int:
    """Consume one BIGSERIAL value, then insert the real accepted chunk."""

    gap_conn = _connect(dbname)
    try:
        with gap_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text)
                VALUES (%s, %s)
                RETURNING id
                """,
                (f"Rolled-back raw {index}", f"Rolled-back prose {index}"),
            )
            rolled_back_id = int(cur.fetchone()[0])
        gap_conn.rollback()
    finally:
        gap_conn.close()

    accepted_conn = _connect(dbname)
    try:
        with accepted_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text)
                VALUES (%s, %s)
                RETURNING id
                """,
                (f"Issue 685 raw {index}", f"Issue 685 prose {index}"),
            )
            accepted_id = int(cur.fetchone()[0])
        accepted_conn.commit()
    finally:
        accepted_conn.close()

    assert accepted_id > rolled_back_id
    return accepted_id


def _draft(
    *,
    template_id: str,
    binding_hash: str,
    actor_entity_id: int,
    narrative_stub: str,
    state_delta: dict[str, Any],
) -> OrreryResolutionDraft:
    """Build one controlled draft for the real adjudication/commit boundary."""

    return OrreryResolutionDraft(
        template_id=template_id,
        priority=40,
        binding_hash=binding_hash,
        bindings={"actor": actor_entity_id},
        branch_label=f"Issue 685 {template_id}",
        narrative_stub=narrative_stub,
        state_delta=state_delta,
        magnitude=0.2,
        promotable=False,
    )


def _resolve_then_commit(
    seeded: dict[str, Any],
    *,
    tick_chunk_id: int,
    drafts: tuple[OrreryResolutionDraft, ...],
    adjudications: list[dict[str, Any]],
) -> Any:
    """Exercise the live-cycle resolve then real adjudication/commit path."""

    settings = seeded["settings"]
    with seeded["Session"]() as session:
        resolved = resolve_dry_run(
            session,
            BUILTIN_TEMPLATES,
            anchor_chunk_id=tick_chunk_id,
            window_chunks=int(settings["orrery"]["binding"]["window_chunks"]),
            sunhelm_settings=settings["orrery"].get("sunhelm"),
        )
    assert resolved.anchor_chunk_id == tick_chunk_id

    proposal = OrreryTickProposal(
        anchor_chunk_id=tick_chunk_id,
        actor_count=max(1, resolved.actor_count),
        resolutions=drafts,
    )
    conn = _connect(seeded["dbname"])
    try:
        result = commit_orrery_tick_sync(
            conn,
            proposal,
            tick_chunk_id=tick_chunk_id,
            adjudications=adjudications,
            prompt_settings=settings["orrery"]["prompt"],
            sunhelm_settings=settings["orrery"].get("sunhelm"),
        )
        conn.commit()
        return result
    finally:
        conn.close()


@pytest.fixture()
def recent_rulings_db() -> Iterator[dict[str, Any]]:
    """Create real outcomes through resolve/adjudicate/commit, then drop the DB."""

    dbname = f"nexus_test_i685_{uuid.uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    engine = None
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )

        engine = create_engine(
            f"postgresql://{os.environ.get('PGUSER', 'pythagor')}@"
            f"{os.environ.get('PGHOST', 'localhost')}:"
            f"{os.environ.get('PGPORT', '5432')}/{dbname}"
        )
        settings = load_settings_as_dict()
        seeded = {
            "dbname": dbname,
            "Session": sessionmaker(bind=engine),
            "settings": settings,
        }
        actor_conn = _connect(dbname)
        try:
            with actor_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO global_variables (id, new_story, base_timestamp)
                    VALUES (true, true, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET base_timestamp = EXCLUDED.base_timestamp
                    """,
                    (datetime(2042, 8, 18, 8, 54, tzinfo=timezone.utc),),
                )
                cur.execute(
                    "INSERT INTO entities (kind, is_active) "
                    "VALUES ('character', true) RETURNING id"
                )
                actor_entity_id = int(cur.fetchone()[0])
                cur.execute(
                    "INSERT INTO characters (name, summary, entity_id) "
                    "VALUES ('Mara', 'Issue 685 production-path actor.', %s)",
                    (actor_entity_id,),
                )
            actor_conn.commit()
        finally:
            actor_conn.close()

        chunk_ids = [
            _insert_accepted_chunk_after_rollback_gap(dbname, index)
            for index in range(1, 5)
        ]
        assert all(
            later - earlier > 1 for earlier, later in zip(chunk_ids, chunk_ids[1:])
        ), "fixture must prove sparse BIGSERIAL chronology"

        defer_draft = _draft(
            template_id="hide",
            binding_hash="defer-streak",
            actor_entity_id=actor_entity_id,
            narrative_stub="The watcher remains hidden.",
            state_delta={"character.current_activity": "waiting in cover"},
        )
        void_no_note = _draft(
            template_id="sleep",
            binding_hash="voided-no-note",
            actor_entity_id=actor_entity_id,
            narrative_stub="The watcher dozes.",
            state_delta={"character.current_activity": "dozing"},
        )
        void_with_note = _draft(
            template_id="sleep",
            binding_hash="voided",
            actor_entity_id=actor_entity_id,
            narrative_stub="The watcher sleeps.",
            state_delta={"character.current_activity": "sleeping"},
        )
        ratified = _draft(
            template_id="surveil",
            binding_hash="ratified",
            actor_entity_id=actor_entity_id,
            narrative_stub="Mara watches the quay from a darkened window.",
            state_delta={},
        )

        first = _resolve_then_commit(
            seeded,
            tick_chunk_id=chunk_ids[1],
            drafts=(defer_draft,),
            adjudications=[{"proposal_id": defer_draft.proposal_id, "action": "defer"}],
        )
        assert first.deferred_count == 1

        second = _resolve_then_commit(
            seeded,
            tick_chunk_id=chunk_ids[2],
            drafts=(defer_draft, void_no_note),
            adjudications=[
                {"proposal_id": defer_draft.proposal_id, "action": "defer"},
                {"proposal_id": void_no_note.proposal_id, "action": "void"},
            ],
        )
        assert second.deferred_count == 1
        assert second.voided_count == 1

        third = _resolve_then_commit(
            seeded,
            tick_chunk_id=chunk_ids[3],
            drafts=(defer_draft, void_with_note, ratified),
            adjudications=[
                {"proposal_id": defer_draft.proposal_id, "action": "defer"},
                {
                    "proposal_id": void_with_note.proposal_id,
                    "action": "void",
                    "note": "Contradicts the witnessed departure",
                },
            ],
        )
        assert third.deferred_count == 1
        assert third.voided_count == 1
        assert third.resolution_count == 1

        yield {
            **seeded,
            "empty_anchor": chunk_ids[0],
            "outcome_anchor": chunk_ids[3],
        }
    finally:
        if engine is not None:
            engine.dispose()
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


def _assemble_prompt(
    seeded: dict[str, Any],
    *,
    anchor_chunk_id: int,
    cap: int,
) -> tuple[str, dict[str, Any]]:
    settings = load_settings_as_dict()
    settings["orrery"]["knowledge"]["enabled"] = False
    settings["orrery"]["bleed"]["max_candidates"] = 0
    settings["orrery"]["bleed"]["reserved_remote_slots"] = 0
    settings["orrery"]["prompt"]["max_rendered_recent_rulings"] = cap

    lore = SimpleNamespace(
        settings=settings,
        memnon=SimpleNamespace(Session=seeded["Session"]),
        memory_manager=ContextMemoryManager(settings),
        token_manager=None,
        enable_logon=False,
    )
    manager = TurnCycleManager(lore)
    context = TurnContext(
        turn_id="issue-685",
        user_input="Continue.",
        start_time=time.time(),
        target_chunk_id=anchor_chunk_id,
        token_counts={"total_available": 75_000},
    )

    asyncio.run(manager.assemble_context_payload(context))
    prompt = LogonUtility(settings)._format_context_prompt(context.context_payload)
    return prompt, context.context_payload


def test_recent_rulings_render_real_outcomes_across_sparse_chunk_ids(
    recent_rulings_db: dict[str, Any],
) -> None:
    """Production writes render by accepted order, then reach both seats."""

    prompt, payload = _assemble_prompt(
        recent_rulings_db,
        anchor_chunk_id=recent_rulings_db["outcome_anchor"],
        cap=5,
    )

    assert prompt.count("=== RECENT ORRERY RULINGS ===") == 1
    assert (
        "[RATIFIED] Mara watches the quay from a darkened window. (turn N-1)" in prompt
    )
    assert (
        "[DEFERRED] hide: state_delta="
        '{"character.current_activity":"waiting in cover"} '
        "(turn N-1) — 3rd consecutive deferral" in prompt
    )
    assert (
        "[VOIDED — Contradicts the witnessed departure] sleep: state_delta="
        '{"character.current_activity":"sleeping"} (turn N-1)' in prompt
    )
    assert (
        "[VOIDED — no note] sleep: state_delta="
        '{"character.current_activity":"dozing"} (turn N-2)' in prompt
    )

    writer = SimpleNamespace(
        narrative="The scene continues.",
        choices=[],
        scene=None,
        presence=None,
        operations=None,
        letter="The outcome ledger informed the scene.",
    )
    gaia_prompt = LogonUtility._format_gaia_user_prompt(prompt, writer)
    assert "=== RECENT ORRERY RULINGS ===" in gaia_prompt
    assert "3rd consecutive deferral" in gaia_prompt

    without_rulings = dict(payload)
    without_rulings.pop("orrery_recent_rulings_section")
    assert _context_component_token_count(payload) > _context_component_token_count(
        without_rulings
    )


def test_recent_rulings_respect_configured_cap(
    recent_rulings_db: dict[str, Any],
) -> None:
    """The configured cap bounds outcomes before prompt-budget measurement."""

    prompt, payload = _assemble_prompt(
        recent_rulings_db,
        anchor_chunk_id=recent_rulings_db["outcome_anchor"],
        cap=2,
    )

    section = payload["orrery_recent_rulings_section"]
    assert len(section) == 3
    assert prompt.count("[RATIFIED]") == 1
    assert prompt.count("[VOIDED —") == 1
    assert "[DEFERRED]" not in prompt


def test_recent_rulings_omit_empty_section(
    recent_rulings_db: dict[str, Any],
) -> None:
    """An anchor before every outcome emits no header or payload key."""

    prompt, payload = _assemble_prompt(
        recent_rulings_db,
        anchor_chunk_id=recent_rulings_db["empty_anchor"],
        cap=5,
    )

    assert "orrery_recent_rulings_section" not in payload
    assert "=== RECENT ORRERY RULINGS ===" not in prompt
