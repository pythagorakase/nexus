"""Template-backed live coverage for claim-awareness checkpoint verification."""

from __future__ import annotations

import os
from typing import Any, Iterator
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.agents.orrery.epistemics import ClaimParticipant, mint_claim_for_event
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import verify_checkpoints_sync


pytestmark = pytest.mark.requires_postgres

EPISTEMICS = {
    "enabled": True,
    "claim_event_types": ["threat_issued"],
    "aware_roles": ["actor", "target", "observer", "witness"],
}


@pytest.fixture()
def template_conn() -> Iterator[Any]:
    conn = psycopg2.connect(
        dbname="NEXUS_template",
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _insert_chunk(cur: Any) -> int:
    token = uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES (%s, 'Rollback-only awareness replay fixture.')
        RETURNING id
        """,
        (f"Awareness replay fixture {token}.",),
    )
    chunk_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date, slug
        ) VALUES (
            %s, 99, 99, %s, 'primary', interval '0 seconds', now(), %s
        )
        """,
        (chunk_id, chunk_id, token[:10]),
    )
    return chunk_id


def _insert_character_entity(cur: Any) -> int:
    cur.execute(
        "INSERT INTO entities (kind, is_active) "
        "VALUES ('character', true) RETURNING id"
    )
    return int(cur.fetchone()["id"])


def _mint_fixture_claim(cur: Any, *, chunk_id: int, source: int) -> int:
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, world_layer,
            source, changed_fields, payload
        ) VALUES (
            'threat_issued', %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb
        )
        RETURNING id
        """,
        (chunk_id, source),
    )
    event_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO world_event_entities (event_id, role, entity_id)
        VALUES (%s, 'actor', %s)
        """,
        (event_id, source),
    )
    minted = mint_claim_for_event(
        cur,
        world_event_id=event_id,
        event_type="threat_issued",
        summary="Awareness replay fixture claim.",
        participants=(
            ClaimParticipant(source, "actor", f"Replay source {source}", "character"),
        ),
        source_chunk_id=chunk_id,
        source_resolution_id=None,
        settings=EPISTEMICS,
    )
    assert minted is not None
    return minted.claim_id


def test_verify_reports_projection_only_awareness_drift(template_conn: Any) -> None:
    """A new checkpoint window catches awareness with no mint-event twin."""

    with template_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source = _insert_character_entity(cur)
        rogue = _insert_character_entity(cur)
        base_chunk = _insert_chunk(cur)
        claim_id = _mint_fixture_claim(cur, chunk_id=base_chunk, source=source)
        base_id = capture_state_checkpoint_sync(
            cur, chunk_id=base_chunk, label="manual"
        )
        assert base_id is not None

        target_chunk = _insert_chunk(cur)
        cur.execute(
            """
            INSERT INTO claim_awareness (
                claim_id, knower_entity_id, source_tier, source_chunk_id
            ) VALUES (%s, %s, 'participant', %s)
            RETURNING id
            """,
            (claim_id, rogue, target_chunk),
        )
        rogue_awareness_id = int(cur.fetchone()["id"])
        target_id = capture_state_checkpoint_sync(
            cur, chunk_id=target_chunk, label="manual"
        )
        assert target_id is not None
        with template_conn.cursor() as verify_cur:
            verdicts = verify_checkpoints_sync(verify_cur)

    verdict = next(
        item
        for item in verdicts
        if item.base_checkpoint_id == base_id and item.target_checkpoint_id == target_id
    )
    assert any(
        drift.section == "claim_awareness"
        and drift.row_key == str(rogue_awareness_id)
        and drift.kind == "missing_row"
        for drift in verdict.drifts
    )


def test_verify_skips_checkpoint_that_predates_awareness_section(
    template_conn: Any,
) -> None:
    """An old base document uses the missing-section skip contract."""

    with template_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source = _insert_character_entity(cur)
        base_chunk = _insert_chunk(cur)
        _mint_fixture_claim(cur, chunk_id=base_chunk, source=source)
        base_id = capture_state_checkpoint_sync(
            cur, chunk_id=base_chunk, label="manual"
        )
        assert base_id is not None
        cur.execute(
            "UPDATE state_checkpoints SET state = state - 'claim_awareness' "
            "WHERE id = %s",
            (base_id,),
        )
        target_chunk = _insert_chunk(cur)
        target_id = capture_state_checkpoint_sync(
            cur, chunk_id=target_chunk, label="manual"
        )
        assert target_id is not None
        with template_conn.cursor() as verify_cur:
            verdicts = verify_checkpoints_sync(verify_cur)

    verdict = next(
        item
        for item in verdicts
        if item.base_checkpoint_id == base_id and item.target_checkpoint_id == target_id
    )
    assert not [drift for drift in verdict.drifts if drift.section == "claim_awareness"]
    assert verdict.skipped_unreproducible >= 1
    assert any(
        "comparison skipped" in note
        for note in verdict.notes.get("claim_awareness", [])
    )
