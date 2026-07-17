"""Rollback-only slot-5 coverage for proximity-ranked Orrery Bleed.

Activated by ``NEXUS_RUN_POSTGRES=1``. Every fixture row and temporary update
is enclosed in one external SQLAlchemy transaction and rolled back.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from typing import Any, Iterator, cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.bleed import (
    load_bleed_anchor_entity_ids,
    load_bleed_candidates,
    select_bleed_menu,
)
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres

LIVE_SLOT = 5


def _insert_chunk(
    session: Session,
    *,
    label: str,
    token: str,
    world_time: datetime,
) -> int:
    """Insert an accepted chunk and restore its explicit fixture world time."""

    chunk_id = int(
        session.execute(
            text(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text)
                VALUES (:raw_text, :storyteller_text)
                RETURNING id
                """
            ),
            {
                "raw_text": f"Bleed proximity {label} fixture {token}.",
                "storyteller_text": "Rollback-only Bleed fixture.",
            },
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
    # The metadata trigger derives world_time during INSERT. A world-time-only
    # UPDATE does not retrigger it and keeps synthetic chunks chronologically
    # explicit, matching the repository's live-fixture discipline.
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


def _insert_character(
    session: Session,
    *,
    label: str,
    token: str,
) -> tuple[int, int]:
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
    character_id = int(
        session.execute(
            text(
                """
                INSERT INTO characters (name, entity_id)
                VALUES (:name, :entity_id)
                RETURNING id
                """
            ),
            {"name": f"bleed-{token}-{label}", "entity_id": entity_id},
        ).scalar_one()
    )
    return entity_id, character_id


def _insert_relationship(
    session: Session,
    *,
    source_character_id: int,
    target_character_id: int,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, dynamic, recent_events, history
            ) VALUES (
                :source_id, :target_id, 'associate', '-5|fixture',
                'Rollback-only Bleed fixture.', 'No persistent events.',
                'Created for issue 477 Stage 3 live coverage.'
            )
            """
        ),
        {"source_id": source_character_id, "target_id": target_character_id},
    )


def _insert_hunting_edge(
    session: Session,
    *,
    actor_entity_id: int,
    faction_entity_id: int,
) -> None:
    result = session.execute(
        text(
            """
            INSERT INTO entity_pair_tags (
                subject_entity_id, object_entity_id, pair_tag_id,
                source_kind, template_id
            )
            SELECT :actor_id, :faction_id, pt.id,
                   'template', 'test_bleed_proximity_live'
            FROM pair_tags pt
            WHERE pt.tag = 'hunting' AND NOT pt.deprecated
            RETURNING id
            """
        ),
        {"actor_id": actor_entity_id, "faction_id": faction_entity_id},
    ).scalar_one_or_none()
    assert result is not None, "slot 5 must register the hunting pair tag"


def _insert_candidate(
    session: Session,
    *,
    chunk_id: int,
    actor_entity_id: int,
    label: str,
    token: str,
    magnitude: float,
) -> int:
    resolution_id = int(
        session.execute(
            text(
                """
                INSERT INTO orrery_resolutions (
                    tick_chunk_id, template_id, binding_hash,
                    actor_entity_id, priority, magnitude, state_delta,
                    brief, promotion_status
                ) VALUES (
                    :chunk_id, :template_id, :binding_hash,
                    :actor_id, 50, :magnitude, '{}'::jsonb,
                    :brief, 'promoted'
                )
                RETURNING id
                """
            ),
            {
                "chunk_id": chunk_id,
                "template_id": f"bleed_{label}",
                "binding_hash": f"bleed-{token}-{label}",
                "actor_id": actor_entity_id,
                "magnitude": magnitude,
                "brief": f"Rollback-only {label} candidate.",
            },
        ).scalar_one()
    )
    narration_id = int(
        session.execute(
            text(
                """
                INSERT INTO offscreen_narrations (
                    resolution_id, tick_chunk_id, world_layer,
                    text, perceptual_descriptor
                ) VALUES (
                    :resolution_id, :chunk_id, 'primary',
                    :narration, CAST(:descriptor AS jsonb)
                )
                RETURNING id
                """
            ),
            {
                "resolution_id": resolution_id,
                "chunk_id": chunk_id,
                "narration": f"Rollback-only narration for {label}.",
                "descriptor": json.dumps(
                    {"channel": "visual", "summary": f"{label} resolves"}
                ),
            },
        ).scalar_one()
    )
    session.execute(
        text(
            """
            UPDATE orrery_resolutions
            SET narration_status = 'succeeded',
                narration_chunk_id = :narration_id
            WHERE id = :resolution_id
            """
        ),
        {"narration_id": narration_id, "resolution_id": resolution_id},
    )
    return resolution_id


@pytest.fixture()
def bleed_proximity_db() -> Iterator[dict[str, Any]]:
    """Build an isolated candidate pool and purpose-specific graph in slot 5."""

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        token = uuid4().hex[:12]
        # Exclude ambient live candidates for this transaction only so every
        # backfill assertion operates on a closed, deterministic fixture pool.
        session.execute(
            text(
                """
                UPDATE orrery_resolutions
                SET offer_count = 3
                WHERE offer_count < 3
                """
            )
        )
        faction = (
            session.execute(
                text(
                    """
                    SELECT f.id AS faction_id, f.entity_id
                    FROM factions f
                    JOIN entities e ON e.id = f.entity_id
                    WHERE e.is_active = true
                    ORDER BY f.entity_id
                    LIMIT 1
                    """
                )
            )
            .mappings()
            .one_or_none()
        )
        if faction is None:
            pytest.skip("save_05 needs one active faction for Bleed coverage")

        latest_world_time = session.execute(
            text("SELECT max(world_time) FROM chunk_metadata")
        ).scalar_one()
        base_world_time = latest_world_time or datetime(2073, 8, 1, tzinfo=timezone.utc)
        mixed_anchor_chunk = _insert_chunk(
            session,
            label="mixed-anchor",
            token=token,
            world_time=base_world_time + timedelta(hours=1),
        )
        faction_anchor_chunk = _insert_chunk(
            session,
            label="faction-anchor",
            token=token,
            world_time=base_world_time + timedelta(hours=2),
        )
        empty_anchor_chunk = _insert_chunk(
            session,
            label="empty-anchor",
            token=token,
            world_time=base_world_time + timedelta(hours=3),
        )

        characters = {
            label: _insert_character(session, label=label, token=token)
            for label in ("anchor", "near_one", "near_two", "remote", "faction_near")
        }
        anchor_entity_id, anchor_character_id = characters["anchor"]
        session.execute(
            text(
                """
                INSERT INTO chunk_character_references (
                    chunk_id, character_id, reference
                ) VALUES (:chunk_id, :character_id, 'present')
                """
            ),
            {
                "chunk_id": mixed_anchor_chunk,
                "character_id": anchor_character_id,
            },
        )
        session.execute(
            text(
                """
                INSERT INTO chunk_faction_references (chunk_id, faction_id)
                VALUES (:chunk_id, :faction_id)
                """
            ),
            {
                "chunk_id": faction_anchor_chunk,
                "faction_id": int(faction["faction_id"]),
            },
        )

        for label in ("near_one", "near_two"):
            _insert_relationship(
                session,
                source_character_id=anchor_character_id,
                target_character_id=characters[label][1],
            )
        _insert_hunting_edge(
            session,
            actor_entity_id=characters["faction_near"][0],
            faction_entity_id=int(faction["entity_id"]),
        )

        candidate_ids = {
            label: _insert_candidate(
                session,
                chunk_id=mixed_anchor_chunk,
                actor_entity_id=characters[label][0],
                label=label,
                token=token,
                magnitude=magnitude,
            )
            for label, magnitude in (
                ("remote", 0.99),
                ("near_one", 0.10),
                ("near_two", 0.09),
                ("faction_near", 0.08),
            )
        }
        session.flush()
        yield {
            "session": session,
            "chunks": {
                "mixed": mixed_anchor_chunk,
                "faction": faction_anchor_chunk,
                "empty": empty_anchor_chunk,
            },
            "entities": {label: pair[0] for label, pair in characters.items()},
            "faction_entity_id": int(faction["entity_id"]),
            "candidates": candidate_ids,
        }
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _select(
    db: dict[str, Any],
    *,
    anchor_chunk: str,
    anchor_entity_ids: tuple[int, ...],
    max_candidates: int,
    near_distance_max: int = 2,
    reserved_remote_slots: int = 1,
):
    return select_bleed_menu(
        db["session"],
        anchor_chunk_id=int(db["chunks"][anchor_chunk]),
        anchor_entity_ids=anchor_entity_ids,
        max_candidates=max_candidates,
        near_distance_max=near_distance_max,
        reserved_remote_slots=reserved_remote_slots,
    )


def test_live_boundary_reservation_and_configured_starvation(
    bleed_proximity_db: dict[str, Any],
) -> None:
    """Near leads, remote is reserved, and zero can intentionally starve it."""

    db = bleed_proximity_db
    anchor_ids = load_bleed_anchor_entity_ids(
        db["session"], anchor_chunk_id=db["chunks"]["mixed"]
    )

    reserved = _select(
        db,
        anchor_chunk="mixed",
        anchor_entity_ids=anchor_ids,
        max_candidates=2,
    )
    no_reservation = _select(
        db,
        anchor_chunk="mixed",
        anchor_entity_ids=anchor_ids,
        max_candidates=2,
        reserved_remote_slots=0,
    )

    assert [candidate.resolution_id for candidate in reserved.selected] == [
        db["candidates"]["near_one"],
        db["candidates"]["remote"],
    ]
    assert [candidate.distance for candidate in reserved.selected] == [1, None]
    assert [candidate.resolution_id for candidate in no_reservation.selected] == [
        db["candidates"]["near_one"],
        db["candidates"]["near_two"],
    ]


def test_live_faction_anchor_and_empty_anchor_fallback(
    bleed_proximity_db: dict[str, Any],
) -> None:
    """Hunting reaches a faction anchor; empty anchors preserve old bytes."""

    db = bleed_proximity_db
    faction_ids = load_bleed_anchor_entity_ids(
        db["session"], anchor_chunk_id=db["chunks"]["faction"]
    )
    assert faction_ids == (db["faction_entity_id"],)
    faction_result = _select(
        db,
        anchor_chunk="faction",
        anchor_entity_ids=faction_ids,
        max_candidates=2,
    )
    faction_candidate = next(
        candidate
        for candidate in faction_result.selected
        if candidate.resolution_id == db["candidates"]["faction_near"]
    )
    assert faction_candidate.distance == 1

    assert (
        load_bleed_anchor_entity_ids(
            db["session"], anchor_chunk_id=db["chunks"]["empty"]
        )
        == ()
    )
    old_order = load_bleed_candidates(
        db["session"],
        anchor_chunk_id=db["chunks"]["empty"],
        limit=3,
    )
    fallback = _select(
        db,
        anchor_chunk="empty",
        anchor_entity_ids=(),
        max_candidates=3,
    )
    assert [candidate.model_dump_json() for candidate in fallback.selected] == [
        candidate.model_dump_json() for candidate in old_order
    ]


def test_live_backfill_and_determinism(
    bleed_proximity_db: dict[str, Any],
) -> None:
    """Short partitions backfill fully and identical state yields one menu."""

    db = bleed_proximity_db
    entities = db["entities"]
    near_short = _select(
        db,
        anchor_chunk="mixed",
        anchor_entity_ids=(entities["near_one"],),
        max_candidates=3,
        near_distance_max=0,
    )
    assert len(near_short.selected) == 3
    assert (near_short.near_count, near_short.remote_count) == (1, 2)

    all_candidate_actors = tuple(
        entities[label] for label in ("remote", "near_one", "near_two", "faction_near")
    )
    remote_short = _select(
        db,
        anchor_chunk="mixed",
        anchor_entity_ids=all_candidate_actors,
        max_candidates=3,
    )
    assert len(remote_short.selected) == 3
    assert (remote_short.near_count, remote_short.remote_count) == (3, 0)

    anchor_ids = (entities["anchor"],)
    first = _select(
        db,
        anchor_chunk="mixed",
        anchor_entity_ids=anchor_ids,
        max_candidates=2,
    )
    second = _select(
        db,
        anchor_chunk="mixed",
        anchor_entity_ids=anchor_ids,
        max_candidates=2,
    )
    assert first == second


class _FixtureMemnon:
    def __init__(self, session: Session):
        self._session = session

    @contextmanager
    def Session(self) -> Iterator[Session]:
        yield self._session


class _FixtureLore:
    def __init__(self, session: Session):
        self.settings = {
            "orrery": {
                "enabled": True,
                "bleed": {
                    "max_candidates": 2,
                    "near_distance_max": 2,
                    "reserved_remote_slots": 1,
                },
            }
        }
        self.memnon = _FixtureMemnon(session)


@pytest.mark.asyncio
async def test_live_phase_state_reports_distance_class_counts(
    bleed_proximity_db: dict[str, Any],
) -> None:
    """Turn-cycle telemetry exposes selected near and remote counts."""

    db = bleed_proximity_db
    manager = TurnCycleManager(_FixtureLore(db["session"]))
    context = TurnContext(turn_id="bleed-live", user_input="Continue.", start_time=0)
    context.orrery_proposal = cast(
        Any,
        SimpleNamespace(
            anchor_chunk_id=db["chunks"]["mixed"],
            pressure_count=0,
        ),
    )

    await manager.select_orrery_bleed(context)

    assert [candidate.distance for candidate in context.bleed_menu] == [1, None]
    assert context.phase_states["orrery_bleed"] == {
        "enabled": True,
        "anchor_chunk_id": db["chunks"]["mixed"],
        "candidate_count": 4,
        "selected_count": 2,
        "near_count": 1,
        "remote_count": 1,
        "offers_recorded": 0,
    }
