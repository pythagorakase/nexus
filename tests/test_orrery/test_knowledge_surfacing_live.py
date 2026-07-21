"""Rollback-only live coverage for Storyteller knowledge surfacing."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import logging
from types import SimpleNamespace
from typing import Any, Iterator, cast
from uuid import uuid4

import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.knowledge_surfacing import build_knowledge_digest_sync
from nexus.api.slot_utils import get_slot_db_url
from tests.test_orrery.claim_accounts_test_support import (
    install_claim_accounts_shadow_sync,
)


pytestmark = pytest.mark.requires_postgres
LIVE_SLOT = 5


def _insert_chunk(session: Session, *, world_time: datetime, token: str) -> int:
    """Insert a playable narration-clock fixture chunk."""

    chunk_id = int(
        session.execute(
            text(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text)
                VALUES (:raw_text, 'Rollback-only knowledge fixture.')
                RETURNING id
                """
            ),
            {"raw_text": f"Knowledge fixture {token} at {world_time.isoformat()}."},
        ).scalar_one()
    )
    session.execute(
        text(
            """
            INSERT INTO chunk_metadata (chunk_id, world_time)
            VALUES (:chunk_id, :world_time)
            """
        ),
        {"chunk_id": chunk_id, "world_time": world_time},
    )
    session.execute(
        text(
            """
            UPDATE chunk_metadata
            SET world_time = :world_time
            WHERE chunk_id = :chunk_id
            """
        ),
        {"chunk_id": chunk_id, "world_time": world_time},
    )
    return chunk_id


def _insert_character(session: Session, *, label: str, token: str) -> tuple[int, int]:
    entity_id = int(
        session.execute(
            text(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('character', true)
                RETURNING id
                """
            )
        ).scalar_one()
    )
    name = f"knowledge-{label}-{token}"
    character_id = int(
        session.execute(
            text(
                """
                INSERT INTO characters (name, entity_id)
                VALUES (:name, :entity_id)
                RETURNING id
                """
            ),
            {"name": name, "entity_id": entity_id},
        ).scalar_one()
    )
    return entity_id, character_id


def _insert_claim(
    session: Session,
    *,
    anchor_chunk_id: int,
    summary: str,
    label: str = "canonical",
    event_id: int | None = None,
    account_payload: dict[str, Any] | None = None,
) -> tuple[int, int]:
    if event_id is None:
        event_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, world_layer, source,
                        changed_fields, payload
                    ) VALUES (
                        'threat_issued', :chunk_id, 'primary', 'resolver',
                        '{}', '{}'::jsonb
                    )
                    RETURNING id
                    """
                ),
                {"chunk_id": anchor_chunk_id},
            ).scalar_one()
        )
    claim_id = int(
        session.execute(
            text(
                """
                INSERT INTO claims (
                    world_event_id, summary, scope, source_chunk_id,
                    account_label, account_payload
                ) VALUES (
                    :event_id, :summary, 'bounded', :chunk_id,
                    :label, CAST(:account_payload AS jsonb)
                )
                RETURNING id
                """
            ),
            {
                "event_id": event_id,
                "summary": summary,
                "chunk_id": anchor_chunk_id,
                "label": label,
                "account_payload": json.dumps(account_payload),
            },
        ).scalar_one()
    )
    return claim_id, event_id


def _grant_awareness(
    session: Session,
    *,
    claim_id: int,
    knower_entity_id: int,
    source_tier: str,
    source_entity_id: int | None,
    acquired_at: datetime,
    source_chunk_id: int,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO claim_awareness (
                claim_id, knower_entity_id, source_tier,
                immediate_source_entity_id, acquired_at_world_time,
                source_chunk_id
            ) VALUES (
                :claim_id, :knower_id, :source_tier,
                :source_id, :acquired_at, :source_chunk_id
            )
            """
        ),
        {
            "claim_id": claim_id,
            "knower_id": knower_entity_id,
            "source_tier": source_tier,
            "source_id": source_entity_id,
            "acquired_at": acquired_at,
            "source_chunk_id": source_chunk_id,
        },
    )


def _insert_reveal(
    session: Session,
    *,
    chunk_id: int,
    claim_id: int,
    holder_entity_id: int,
    participant_entity_ids: list[int],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, world_layer,
                source, changed_fields, payload
            ) VALUES (
                'backstory_revealed', :chunk_id, :holder_id, 'primary',
                'resolver', '{}', CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "chunk_id": chunk_id,
            "holder_id": holder_entity_id,
            "payload": json.dumps(
                {
                    "claim_id": claim_id,
                    "revealed_participant_entity_ids": participant_entity_ids,
                }
            ),
        },
    )


@pytest.fixture()
def knowledge_db() -> Iterator[dict[str, Any]]:
    """Build an isolated Stage A-D fixture in one slot-5 transaction."""

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    raw_connection = connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        install_claim_accounts_shadow_sync(cur)
    session = Session(bind=connection)
    try:
        token = uuid4().hex[:10]
        latest = session.execute(
            text("SELECT max(world_time) FROM chunk_metadata")
        ).scalar_one()
        base_time = latest or datetime(2073, 8, 1, tzinfo=timezone.utc)
        chunks = [
            _insert_chunk(
                session,
                world_time=base_time + timedelta(hours=index + 1),
                token=f"{token}-{index}",
            )
            for index in range(7)
        ]
        alpha, alpha_character = _insert_character(session, label="alpha", token=token)
        beta, beta_character = _insert_character(session, label="beta", token=token)
        source, _source_character = _insert_character(
            session, label="source", token=token
        )
        session.execute(
            text(
                """
                INSERT INTO chunk_character_references (
                    chunk_id, character_id, reference
                ) VALUES
                    (:chunk_id, :alpha_character, 'present'),
                    (:chunk_id, :beta_character, 'present')
                """
            ),
            {
                "chunk_id": chunks[-1],
                "alpha_character": alpha_character,
                "beta_character": beta_character,
            },
        )

        claims: dict[str, int] = {}

        claims["participant"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[0],
            summary="Alpha saw the first exchange.",
        )
        _grant_awareness(
            session,
            claim_id=claims["participant"],
            knower_entity_id=alpha,
            source_tier="participant",
            source_entity_id=None,
            acquired_at=base_time + timedelta(hours=1),
            source_chunk_id=chunks[0],
        )

        claims["witness"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[1],
            summary="Beta witnessed the second exchange.",
        )
        _grant_awareness(
            session,
            claim_id=claims["witness"],
            knower_entity_id=beta,
            source_tier="witness",
            source_entity_id=None,
            acquired_at=base_time + timedelta(hours=2),
            source_chunk_id=chunks[1],
        )

        canonical_id, sibling_event = _insert_claim(
            session,
            anchor_chunk_id=chunks[2],
            summary="Unpossessed canonical answer key.",
            account_payload={"truth_marker": True},
        )
        claims["canonical_unpossessed"] = canonical_id
        claims["variant"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[2],
            event_id=sibling_event,
            label="dockside-rumor",
            summary="The dockside rumor gives a different culprit.",
            account_payload={"truth_marker": False, "culprit": "classified"},
        )
        _grant_awareness(
            session,
            claim_id=claims["variant"],
            knower_entity_id=alpha,
            source_tier="told",
            source_entity_id=source,
            acquired_at=base_time + timedelta(hours=3),
            source_chunk_id=chunks[2],
        )

        claims["granted"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[3],
            summary="Beta received an unattributed briefing.",
        )
        _grant_awareness(
            session,
            claim_id=claims["granted"],
            knower_entity_id=beta,
            source_tier="granted",
            source_entity_id=None,
            acquired_at=base_time + timedelta(hours=4),
            source_chunk_id=chunks[3],
        )

        claims["granted_with_source"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[4],
            summary="Alpha received a sourced special grant.",
        )
        _grant_awareness(
            session,
            claim_id=claims["granted_with_source"],
            knower_entity_id=alpha,
            source_tier="granted",
            source_entity_id=source,
            acquired_at=base_time + timedelta(hours=5),
            source_chunk_id=chunks[4],
        )

        claims["fresh_holder"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[5],
            summary="Alpha's secret surfaced one beat ago.",
        )
        _grant_awareness(
            session,
            claim_id=claims["fresh_holder"],
            knower_entity_id=alpha,
            source_tier="participant",
            source_entity_id=None,
            acquired_at=base_time + timedelta(hours=6),
            source_chunk_id=chunks[5],
        )
        _insert_reveal(
            session,
            chunk_id=chunks[5],
            claim_id=claims["fresh_holder"],
            holder_entity_id=alpha,
            participant_entity_ids=[],
        )

        claims["fresh_participant"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[5],
            summary="Beta was granted the freshly surfaced secret.",
        )
        _grant_awareness(
            session,
            claim_id=claims["fresh_participant"],
            knower_entity_id=beta,
            source_tier="told",
            source_entity_id=alpha,
            acquired_at=base_time + timedelta(hours=6, minutes=30),
            source_chunk_id=chunks[5],
        )
        _insert_reveal(
            session,
            chunk_id=chunks[5],
            claim_id=claims["fresh_participant"],
            holder_entity_id=alpha,
            participant_entity_ids=[beta],
        )

        claims["stale_reveal"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[1],
            summary="Beta remembers an older revelation.",
        )
        _grant_awareness(
            session,
            claim_id=claims["stale_reveal"],
            knower_entity_id=beta,
            source_tier="participant",
            source_entity_id=None,
            acquired_at=base_time + timedelta(hours=2, minutes=30),
            source_chunk_id=chunks[1],
        )
        _insert_reveal(
            session,
            chunk_id=chunks[1],
            claim_id=claims["stale_reveal"],
            holder_entity_id=beta,
            participant_entity_ids=[],
        )

        claims["latent"], _ = _insert_claim(
            session,
            anchor_chunk_id=chunks[6],
            summary="Latent secret that must never cross the boundary.",
            account_payload={"secret": "answer"},
        )
        _grant_awareness(
            session,
            claim_id=claims["latent"],
            knower_entity_id=alpha,
            source_tier="participant",
            source_entity_id=None,
            acquired_at=base_time + timedelta(hours=7),
            source_chunk_id=chunks[6],
        )
        session.execute(
            text(
                """
                INSERT INTO backstory_secrets (claim_id, status)
                VALUES (:claim_id, 'latent')
                """
            ),
            {"claim_id": claims["latent"]},
        )
        session.flush()
        yield {
            "session": session,
            "raw_connection": raw_connection,
            "anchor": chunks[-1],
            "present": (alpha, beta),
            "source": source,
            "claims": claims,
        }
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _settings(*, enabled: bool = True, max_entries: int = 12) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "max_entries": max_entries,
        "recent_reveal_window_chunks": 3,
    }


def test_digest_surfaces_only_possessed_safe_accounts(
    knowledge_db: dict[str, Any],
) -> None:
    """Possession, acquisition, variants, freshness, and spoilers stay bounded."""

    db = knowledge_db
    digest = build_knowledge_digest_sync(
        db["session"],
        present_entity_ids=db["present"],
        anchor_chunk_id=db["anchor"],
        settings=_settings(),
    )
    by_claim = {entry["claim_id"]: entry for entry in digest}
    claims = db["claims"]

    assert by_claim[claims["participant"]]["acquisition"] == {"kind": "firsthand"}
    assert by_claim[claims["witness"]]["acquisition"] == {"kind": "firsthand"}
    told = by_claim[claims["variant"]]["acquisition"]
    assert told["kind"] == "told"
    assert told["source_entity_id"] == db["source"]
    assert told["source_name"].startswith("knowledge-source-")
    assert by_claim[claims["granted"]]["acquisition"] == {"kind": "granted"}
    assert by_claim[claims["granted_with_source"]]["acquisition"]["kind"] == ("told")
    assert by_claim[claims["variant"]]["account_label"] == "dockside-rumor"
    assert "account_label" not in by_claim[claims["participant"]]

    assert claims["canonical_unpossessed"] not in by_claim
    assert claims["latent"] not in by_claim
    assert all("account_payload" not in entry for entry in digest)
    assert all("truth_marker" not in json.dumps(entry) for entry in digest)
    assert all("classified" not in json.dumps(entry) for entry in digest)

    assert by_claim[claims["fresh_holder"]]["freshly_revealed"] is True
    assert by_claim[claims["fresh_participant"]]["freshly_revealed"] is True
    assert "freshly_revealed" not in by_claim[claims["stale_reveal"]]

    order = [
        (
            entry["character_entity_id"],
            entry["acquired_at_world_time"],
            entry["claim_id"],
        )
        for entry in digest
    ]
    assert order == sorted(order)

    with db["raw_connection"].cursor(cursor_factory=RealDictCursor) as cur:
        cursor_digest = build_knowledge_digest_sync(
            cur,
            present_entity_ids=db["present"],
            anchor_chunk_id=db["anchor"],
            settings=_settings(),
        )
    assert cursor_digest == digest


def test_digest_cap_drops_oldest_and_reports_truncation(
    knowledge_db: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """The global cap retains newest acquisitions and emits debug telemetry."""

    caplog.set_level(logging.DEBUG, logger="nexus.orrery.knowledge_surfacing")
    digest = build_knowledge_digest_sync(
        knowledge_db["session"],
        present_entity_ids=knowledge_db["present"],
        anchor_chunk_id=knowledge_db["anchor"],
        settings=_settings(max_entries=2),
    )

    assert len(digest) == 2
    assert getattr(digest, "truncated") is True
    assert knowledge_db["claims"]["participant"] not in {
        entry["claim_id"] for entry in digest
    }
    assert "dropping oldest acquisitions" in caplog.text


class _LiveMemnonHarness:
    def __init__(self, session: Session) -> None:
        self.session = session

    @contextmanager
    def Session(self) -> Iterator[Session]:
        yield self.session


class _LiveLoreHarness:
    token_manager = None

    def __init__(self, session: Session, *, enabled: bool) -> None:
        self.settings = {
            "orrery": {
                "enabled": True,
                "bleed": {"max_candidates": 0},
                "knowledge": _settings(enabled=enabled),
            }
        }
        self.memnon = _LiveMemnonHarness(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_turn_payload_conditionally_attaches_world_knowledge(
    knowledge_db: dict[str, Any], enabled: bool
) -> None:
    """Turn assembly attaches only a non-empty, enabled live digest."""

    db = knowledge_db
    manager = TurnCycleManager(_LiveLoreHarness(db["session"], enabled=enabled))
    context = TurnContext(
        turn_id="knowledge-live",
        user_input="Continue.",
        start_time=0,
    )
    context.orrery_proposal = cast(
        Any,
        SimpleNamespace(
            anchor_chunk_id=db["anchor"],
            pressure_count=0,
            resolution_count=0,
            joint_beats=(),
        ),
    )

    await manager.assemble_context_payload(context)

    if enabled:
        assert context.context_payload["world_knowledge"]
        assert context.context_payload["world_knowledge_truncated"] is False
        assert context.phase_states["world_knowledge"]["entry_count"] > 0
    else:
        assert "world_knowledge" not in context.context_payload
        assert "world_knowledge_truncated" not in context.context_payload
