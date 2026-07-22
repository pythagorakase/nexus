"""Rollback-only live coverage for the sanctioned status.bestow delta."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterator

import psycopg2
import pytest

from nexus.agents.orrery.events import (
    REPLACEMENT_STATE_DELTA_ALIASES,
    SUPPORTED_STATE_DELTA_KEYS,
    _apply_state_delta_sync,
    _validate_proposal,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.replay import TAG_DELTA_KEYS
from nexus.agents.orrery.resolver import OrreryResolutionDraft, OrreryTickProposal
from nexus.agents.orrery.substrate import ProjectPolicy
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def status_delta_db() -> Iterator[dict[str, Any]]:
    conn = psycopg2.connect(get_slot_db_url(slot=5))
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('character', true), ('faction', true)
                RETURNING id
                """
            )
            actor, faction = (int(row[0]) for row in cur.fetchall())
            cur.execute(
                """
                SELECT chunk_id, world_time
                FROM chunk_metadata
                WHERE world_time IS NOT NULL
                ORDER BY chunk_id DESC
                LIMIT 1
                """
            )
            chunk, world_time = cur.fetchone()
        yield {
            "conn": conn,
            "actor": actor,
            "faction": faction,
            "chunk": int(chunk),
            "world_time": world_time,
        }
    finally:
        conn.rollback()
        conn.close()


def _draft(db: dict[str, Any], state_delta: dict[str, Any]) -> OrreryResolutionDraft:
    return OrreryResolutionDraft(
        template_id="status_bestow_live",
        priority=10,
        binding_hash="status-bestow-live",
        bindings={"actor": db["actor"], "faction": db["faction"]},
        branch_label="Bestow status",
        narrative_stub="The institution recognizes the actor.",
        state_delta=state_delta,
    )


def _apply(db: dict[str, Any], draft: OrreryResolutionDraft) -> int:
    with db["conn"].cursor() as cur:
        return _apply_state_delta_sync(
            cur,
            draft,
            resolution_id=0,
            actor_entity_id=db["actor"],
            target_entity_id=None,
            source_chunk_id=db["chunk"],
            need_tuning=load_need_tuning(),
            project_policy=ProjectPolicy(enabled=True),
        )


def _seed_status(db: dict[str, Any], level: str) -> None:
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_pair_tags (
                subject_entity_id, object_entity_id, pair_tag_id,
                source_kind, template_id
            )
            SELECT %s, %s, pt.id, 'template', 'status_bestow_seed'
            FROM pair_tags pt
            WHERE pt.tag = %s AND NOT pt.deprecated
            """,
            (db["actor"], db["faction"], f"status:{level}"),
        )


def _active_status(db: dict[str, Any]) -> str:
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            SELECT pt.tag
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.subject_entity_id = %s
              AND ept.object_entity_id = %s
              AND ept.cleared_at IS NULL
              AND pt.tag LIKE 'status:%%'
            """,
            (db["actor"], db["faction"]),
        )
        return str(cur.fetchone()[0])


def test_status_bestow_writes_exclusive_pair_tag_with_provenance(
    status_delta_db: dict[str, Any],
) -> None:
    db = status_delta_db
    draft = _draft(db, {"status.bestow": {"level": "junior"}})
    _validate_proposal(
        OrreryTickProposal(
            anchor_chunk_id=db["chunk"], actor_count=1, resolutions=(draft,)
        )
    )
    assert _apply(db, draft) == 1
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            SELECT pt.tag, ept.source_kind, ept.source_chunk_id,
                   ept.template_id, ept.applied_at_world_time
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.subject_entity_id = %s
              AND ept.object_entity_id = %s
              AND ept.cleared_at IS NULL
              AND pt.tag LIKE 'status:%%'
            """,
            (db["actor"], db["faction"]),
        )
        assert cur.fetchone() == (
            "status:junior",
            "template",
            db["chunk"],
            "status_bestow_live",
            db["world_time"],
        )
    assert "status.bestow" in SUPPORTED_STATE_DELTA_KEYS
    assert REPLACEMENT_STATE_DELTA_ALIASES["status_bestow"] == "status.bestow"
    assert "status.bestow" in TAG_DELTA_KEYS


def test_status_bestow_and_raw_status_fail_loudly(
    status_delta_db: dict[str, Any],
) -> None:
    db = status_delta_db
    with pytest.raises(ValueError, match="Unknown status level"):
        _apply(db, _draft(db, {"status.bestow": {"level": "archon"}}))

    missing_faction = _draft(db, {"status.bestow": {"level": "junior"}})
    missing_faction = replace(missing_faction, bindings={"actor": db["actor"]})
    with pytest.raises(ValueError, match="requires a FACTION binding"):
        _apply(db, missing_faction)

    raw = _draft(
        db,
        {"entity_pair_tags.add_outbound": ["status:junior"]},
    )
    raw = replace(
        raw,
        bindings={"actor": db["actor"], "target": db["faction"]},
    )
    with pytest.raises(ValueError, match="use status.bestow"):
        with db["conn"].cursor() as cur:
            _apply_state_delta_sync(
                cur,
                raw,
                resolution_id=0,
                actor_entity_id=db["actor"],
                target_entity_id=db["faction"],
                source_chunk_id=db["chunk"],
                need_tuning=load_need_tuning(),
                project_policy=ProjectPolicy(enabled=True),
            )


def test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways(
    status_delta_db: dict[str, Any],
) -> None:
    db = status_delta_db
    _seed_status(db, "respected")

    assert _apply(db, _draft(db, {"status.bestow": {"level": "junior"}})) == 0
    assert _active_status(db) == "status:respected"

    assert (
        _apply(
            db,
            _draft(
                db,
                {"status.bestow": {"level": "junior", "mode": "set"}},
            ),
        )
        == 1
    )
    assert _active_status(db) == "status:junior"

    assert (
        _apply(
            db,
            _draft(
                db,
                {"status.bestow": {"level": "respected", "mode": "set"}},
            ),
        )
        == 1
    )
    assert _active_status(db) == "status:respected"

    with pytest.raises(ValueError, match="Unknown status.bestow mode"):
        _apply(
            db,
            _draft(
                db,
                {"status.bestow": {"level": "junior", "mode": "lower"}},
            ),
        )
