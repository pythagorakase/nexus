"""Occurrence-time horizon proofs using real migration-144 clocks and hydration.

Requires the current NEXUS_template schema. Only disposable qa640_778s3_horizon
clones are written: characters, narrative_chunks, chunk_metadata, world_events
and claims. No providers, owner slots or world-time restamping are used.
"""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from sqlalchemy import create_engine

from nexus.agents.orrery.resolver import hydrate_world_state
from nexus.agents.orrery.substrate import (
    Slot,
    WorldState,
    count_recent_events_within_hours_at_least,
    since_last_event_at_least,
    since_last_event_hours_at_least,
)
from nexus.config import load_settings
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_character,
    seed_committed_chunk,
    seed_protagonist,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres
BASE = datetime(2100, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Story:
    """Exact identities and chunks owned by one disposable proof."""

    dbname: str
    actor: int
    chunks: tuple[int, ...]
    early_events: tuple[int, int]
    floor_event: int
    undated_event: int


def _event(dbname: str, actor: int, chunk: int, *, undated: bool = False) -> int:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, world_layer,
                source, world_time, changed_fields, payload
            )
            SELECT %s, chunk_id, %s, 'primary', %s,
                   CASE WHEN %s THEN NULL ELSE world_time END, '{}', '{}'::jsonb
            FROM chunk_metadata WHERE chunk_id = %s
            RETURNING id
            """,
            (
                "threat_issued" if undated else "stroll_taken",
                actor,
                "retrograde" if undated else "resolver",
                undated,
                chunk,
            ),
        )
        return int(cur.fetchone()[0])


@pytest.fixture
def story(monkeypatch: pytest.MonkeyPatch) -> Iterator[Story]:
    """Forty committed chunks span exactly thirty-nine minutes of world time."""
    with disposable_slot_database("qa640_778s3_horizon") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        seed_protagonist(dbname, base_timestamp=BASE.isoformat())
        _, actor = seed_character(dbname, name="Horizon walker")
        chunks = tuple(
            seed_committed_chunk(
                dbname,
                raw_text=f"Horizon minute {i}",
                scene=i + 1,
                time_delta=None if i == 0 else timedelta(minutes=1),
            )
            for i in range(40)
        )
        early = (_event(dbname, actor, chunks[1]), _event(dbname, actor, chunks[4]))
        floor_event = _event(dbname, actor, chunks[9])
        undated = _event(dbname, actor, chunks[-1], undated=True)
        yield Story(dbname, actor, chunks, early, floor_event, undated)


def _hydrate(
    story: Story,
    *,
    anchor: int | None = None,
    horizon: float = 24.0,
    clock: datetime | None = None,
) -> WorldState:
    orrery = load_settings().orrery
    assert orrery is not None
    engine = create_engine(sqlalchemy_url(story.dbname))
    try:
        with engine.connect() as session:
            return hydrate_world_state(
                session,
                anchor_chunk_id=story.chunks[-1] if anchor is None else anchor,
                window_chunks=30,
                event_horizon_hours=horizon,
                world_time_override=clock,
                epistemics_settings=orrery.epistemics.model_copy(
                    update={"enabled": True}
                ),
            )
    finally:
        engine.dispose()


def test_horizon_sees_what_the_chunk_window_misses(story: Story) -> None:
    """The slow story clock preserves occurrences lost by the chunk window."""
    state = _hydrate(story)
    recent = {event.event_id for event in state.recent_events}
    horizon = {event.event_id for event in state.horizon_events}
    assert not set(story.early_events) & recent
    assert set(story.early_events) <= horizon
    assert story.undated_event in recent
    assert story.undated_event not in horizon
    bindings = {Slot.ACTOR: story.actor}
    assert since_last_event_at_least("stroll_taken", 45)(state, bindings)
    assert not since_last_event_hours_at_least("stroll_taken", 1.0)(state, bindings)
    assert count_recent_events_within_hours_at_least(
        "stroll_taken", within_hours=1.0, min_count=2
    )(state, bindings)


def test_horizon_floor_follows_world_time(story: Story) -> None:
    """The exact occurrence floor counts and a larger request is refused."""
    state = _hydrate(story, horizon=0.5)
    assert {event.event_id for event in state.horizon_events} == {story.floor_event}
    assert state.world_time == BASE + timedelta(minutes=39)
    with pytest.raises(ValueError, match="recent_event_horizon_hours"):
        since_last_event_hours_at_least("stroll_taken", 1.0)(
            state, {Slot.ACTOR: story.actor}
        )
    with pytest.raises(ValueError, match=f"anchor_chunk_id={story.chunks[-1]}"):
        _hydrate(story, clock=BASE.replace(tzinfo=None))


def test_hydration_is_anchor_bounded_and_replay_identical(story: Story) -> None:
    """Future tick insertions cannot change either historical event tuple."""
    before = _hydrate(story, anchor=story.chunks[19])
    assert set(story.early_events) <= {
        event.event_id for event in before.horizon_events
    }
    bindings = {Slot.ACTOR: story.actor}
    gates = (
        since_last_event_hours_at_least("stroll_taken", 1.0),
        count_recent_events_within_hours_at_least(
            "stroll_taken", within_hours=1.0, min_count=2
        ),
    )
    outcomes = tuple(gate(before, bindings) for gate in gates)
    for chunk in story.chunks[20:]:
        _event(story.dbname, story.actor, chunk)
    after = _hydrate(story, anchor=story.chunks[19])
    assert after.recent_events == before.recent_events
    assert after.horizon_events == before.horizon_events
    assert tuple(gate(after, bindings) for gate in gates) == outcomes


def test_epistemics_scopes_cover_horizon_events(story: Story) -> None:
    """Claims on occurrences outside the chunk window reach epistemic gates."""
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO claims (world_event_id, summary, scope, source_chunk_id) "
            "VALUES (%s, 'Old but recent occurrence', 'bounded', %s)",
            (story.early_events[0], story.chunks[1]),
        )
    state = _hydrate(story)
    assert story.early_events[0] not in {
        event.event_id for event in state.recent_events
    }
    assert state.claimed_event_scopes[story.early_events[0]] == "bounded"
