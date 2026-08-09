"""Disposable-PostgreSQL prompt regressions for recent Orrery rulings."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from types import SimpleNamespace
from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.extras import Json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import (
    TurnCycleManager,
    _context_component_token_count,
)
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


@pytest.fixture()
def recent_rulings_db() -> Iterator[dict[str, Any]]:
    """Clone the template, seed genuine outcome ledgers, and always drop it."""

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

        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                chunk_ids: list[int] = []
                for index in range(1, 7):
                    cur.execute(
                        """
                        INSERT INTO narrative_chunks (raw_text, storyteller_text)
                        VALUES (%s, %s)
                        RETURNING id
                        """,
                        (f"Issue 685 raw {index}", f"Issue 685 prose {index}"),
                    )
                    chunk_ids.append(int(cur.fetchone()[0]))

                defer_delta = {"character.current_activity": "waiting in cover"}
                for tick_chunk_id in chunk_ids[3:6]:
                    cur.execute(
                        """
                        INSERT INTO orrery_adjudication_log (
                            tick_chunk_id, proposal_id, template_id,
                            binding_hash, action, adjudication_source,
                            original_state_delta, bindings
                        ) VALUES (
                            %s, 'hide:defer-streak', 'hide', 'defer-streak',
                            'defer', 'explicit', %s::jsonb, '{}'::jsonb
                        )
                        """,
                        (tick_chunk_id, Json(defer_delta)),
                    )

                cur.execute(
                    """
                    INSERT INTO orrery_adjudication_log (
                        tick_chunk_id, proposal_id, template_id, binding_hash,
                        action, adjudication_source, original_state_delta, bindings
                    ) VALUES (
                        %s, 'sleep:voided-no-note', 'sleep', 'voided-no-note',
                        'void', 'explicit',
                        '{"character.current_activity":"dozing"}'::jsonb,
                        '{}'::jsonb
                    )
                    """,
                    (chunk_ids[4],),
                )
                cur.execute(
                    """
                    INSERT INTO orrery_adjudication_log (
                        tick_chunk_id, proposal_id, template_id, binding_hash,
                        action, adjudication_source, skald_note,
                        original_state_delta, bindings
                    ) VALUES (
                        %s, 'sleep:voided', 'sleep', 'voided', 'void',
                        'explicit', 'Contradicts the witnessed departure',
                        '{"character.current_activity":"sleeping"}'::jsonb,
                        '{}'::jsonb
                    )
                    """,
                    (chunk_ids[5],),
                )
                cur.execute(
                    """
                    INSERT INTO orrery_resolutions (
                        tick_chunk_id, template_id, binding_hash,
                        priority, state_delta, brief, promotion_status
                    ) VALUES (
                        %s, 'surveil', 'ratified', 40,
                        '{"character.current_activity":"watching the quay"}'::jsonb,
                        'Mara watches the quay from a darkened window.', 'pending'
                    )
                    """,
                    (chunk_ids[5],),
                )

        engine = create_engine(
            f"postgresql://{os.environ.get('PGUSER', 'pythagor')}@"
            f"{os.environ.get('PGHOST', 'localhost')}:"
            f"{os.environ.get('PGPORT', '5432')}/{dbname}"
        )
        yield {
            "dbname": dbname,
            "Session": sessionmaker(bind=engine),
            "empty_anchor": chunk_ids[0],
            "outcome_anchor": chunk_ids[5],
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


def test_recent_rulings_render_all_outcomes_for_both_seats_and_count_budget(
    recent_rulings_db: dict[str, Any],
) -> None:
    """Real assembly renders every shape and carries it into Gaia's prompt."""

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
    """An anchor before every seeded outcome emits no header or payload key."""

    prompt, payload = _assemble_prompt(
        recent_rulings_db,
        anchor_chunk_id=recent_rulings_db["empty_anchor"],
        cap=5,
    )

    assert "orrery_recent_rulings_section" not in payload
    assert "=== RECENT ORRERY RULINGS ===" not in prompt
