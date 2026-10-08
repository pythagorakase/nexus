"""Routable destination gates, choosers and refusal at both travel boundaries.

Each case owns a routed disposable clone. The old same-zone/id ordering would
prefer the lower-id uncharted venue over its charted neighbor. Real psycopg2,
asyncpg and SQLAlchemy paths read these fixtures; both commit writers prove a
refusal rolls back the travel row and resolution/event writes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

import asyncpg  # type: ignore[import-untyped]
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery import events
from nexus.agents.orrery.evidence import resolve_evidence
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
    _draft_from_resolution,
    _project_destination,
    hydrate_world_state,
)
from nexus.agents.orrery.substrate import (
    ProjectPolicy,
    Resolution,
    Slot,
    WorldState,
    has_location_class_destination,
    route_known,
    routine_anchor_has_destination,
)
from tests.pg_fixtures import (
    asyncpg_kwargs,
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_character,
    seed_entity_tag,
    seed_place,
    seed_protagonist,
    seed_routine_anchor,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres
SLOT = 2
BASE = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)


class Story(NamedTuple):
    """The disposable story and its contrasting destination candidates."""

    dbname: str
    actor: int
    origin: int
    uncharted: int
    uncharted_entity: int
    charted: int
    charted_entity: int
    zone: int
    tick: int


@pytest.fixture
def story(monkeypatch: pytest.MonkeyPatch) -> Iterator[Story]:
    """Seed one story with two same-zone candidates in the adverse id order."""
    with disposable_slot_database("qa640_785s3d") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=SLOT, dbname=dbname)
        zone = seed_zone(
            dbname,
            name="Route Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        origin, _ = seed_place(dbname, name="Route Origin")
        uncharted, uncharted_entity = seed_place(dbname, name="Uncharted Venue")
        charted, charted_entity = seed_place(
            dbname,
            name="Charted Venue",
            latitude=40.7574,
        )
        seed_protagonist(
            dbname,
            base_timestamp=BASE.isoformat(),
            current_location=origin,
        )
        _, actor = seed_character(
            dbname,
            name="Route Traveler",
            current_location=origin,
        )
        seed_story_clock(dbname, world_time=BASE)
        tick = seed_story_clock(dbname, world_time=BASE + timedelta(hours=1), scene=2)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE places SET coordinates = NULL WHERE id = %s", (uncharted,)
            )
        assert uncharted < charted
        yield Story(
            dbname,
            actor,
            origin,
            uncharted,
            uncharted_entity,
            charted,
            charted_entity,
            zone,
            tick,
        )


def _tag_venues(story: Story, *, both: bool = True) -> None:
    """Make the uncharted venue, and optionally its neighbor, social venues."""
    seed_entity_tag(story.dbname, entity_id=story.uncharted_entity, tag="commerce")
    if both:
        seed_entity_tag(story.dbname, entity_id=story.charted_entity, tag="commerce")


def _state(story: Story) -> WorldState:
    """Hydrate the production read-side state on the disposable story."""
    engine = create_engine(sqlalchemy_url(story.dbname), future=True)
    try:
        with Session(engine) as session:
            return hydrate_world_state(
                session,
                anchor_chunk_id=story.tick,
                window_chunks=30,
                project_settings=ProjectPolicy(enabled=True),
            )
    finally:
        engine.dispose()


def _destinations(
    story: Story, *, anchor: str | None = None
) -> tuple[int | None, int | None]:
    """Read a class or routine-anchor destination through both SQL twins."""
    kwargs: dict[str, Any] = {
        "origin_place_id": story.origin,
        "current_world_time": BASE,
    }
    sync: Callable[..., int | None]
    asynchronous: Callable[..., Awaitable[int | None]]
    if anchor is None:
        kwargs["location_classes"] = ("commerce",)
        sync = events._location_class_destination_sync
        asynchronous = events._location_class_destination_async
    else:
        kwargs.update(actor_entity_id=story.actor, anchor_type=anchor)
        sync = events._routine_anchor_destination_sync
        asynchronous = events._routine_anchor_destination_async
    with closing(connect(story.dbname)) as conn, conn.cursor() as cur:
        sync_result = sync(cur, **kwargs)

    async def run() -> int | None:
        conn = await asyncpg.connect(**asyncpg_kwargs(story.dbname))
        try:
            return await asynchronous(conn, **kwargs)
        finally:
            await conn.close()

    return sync_result, asyncio.run(run())


def _proposal(story: Story, payload: dict[str, Any]) -> OrreryTickProposal:
    """Build the real commit writer's input around a travel.start request."""
    return OrreryTickProposal(
        anchor_chunk_id=story.tick,
        actor_count=1,
        resolutions=(
            OrreryResolutionDraft(
                template_id="travel",
                priority=21,
                binding_hash="routable-travel",
                bindings={"actor": story.actor},
                branch_label="Depart",
                narrative_stub="{actor} starts the journey.",
                state_delta={"travel.start": payload},
                event_type="travel_departed",
            ),
        ),
    )


def _snapshot(story: Story) -> tuple[list[Any], list[Any], list[Any]]:
    """Read travel and commit rows so refusal must leave every write undone."""
    with closing(connect(story.dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM character_travel_states ORDER BY character_entity_id"
        )
        travel = cur.fetchall()
        cur.execute("SELECT * FROM orrery_resolutions ORDER BY id")
        resolutions = cur.fetchall()
        cur.execute("SELECT * FROM world_events ORDER BY id")
        return travel, resolutions, cur.fetchall()


def test_location_class_chooser_skips_uncharted(story: Story) -> None:
    """Both choosers skip the lower id, and acceptance writes a concrete ETA."""
    _tag_venues(story)
    assert _destinations(story) == (story.charted, story.charted)
    with closing(connect(story.dbname)) as conn, conn:
        events.commit_orrery_tick_sync(
            conn,
            _proposal(story, {"destination_place_classes": ["commerce"]}),
            tick_chunk_id=story.tick,
            slot=SLOT,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT destination_place_id, eta_world_time "
                "FROM character_travel_states "
                "WHERE character_entity_id = %s",
                (story.actor,),
            )
            destination, eta = cur.fetchone()
    assert destination == story.charted
    assert eta is not None


def test_gate_and_evidence_ignore_uncharted(story: Story) -> None:
    """Hydration drives the same refusal in the gate and its explanation."""
    _tag_venues(story, both=False)
    condition = has_location_class_destination("commerce")
    bindings = {Slot.ACTOR: story.actor}
    state = _state(story)
    assert story.origin in state.charted_place_ids
    assert story.uncharted not in state.charted_place_ids
    assert not condition(state, bindings)
    evidence = resolve_evidence(condition.__name__, state, bindings)
    assert evidence["result"] is False
    assert evidence["observed"]["unroutable_destination_count"] == 1
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE places SET coordinates = "
            "(SELECT coordinates FROM places WHERE id = %s) WHERE id = %s",
            (story.charted, story.uncharted),
        )
    state = _state(story)
    assert condition(state, bindings)
    evidence = resolve_evidence(condition.__name__, state, bindings)
    assert evidence["result"] is True
    assert evidence["observed"]["unroutable_destination_count"] == 0


@pytest.mark.parametrize("reverse", [False, True])
def test_timed_authored_edge_routes_uncharted_place(
    story: Story, reverse: bool
) -> None:
    """Only timed authored edges qualify; reverse travel requires bidirectionality."""
    _tag_venues(story, both=False)
    seed_routine_anchor(
        story.dbname, character_entity_id=story.actor, place_id=story.uncharted
    )
    start, end = (
        (story.uncharted, story.origin) if reverse else (story.origin, story.uncharted)
    )
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO orrery_travel_edges "
            "(from_place_id, to_place_id, duration_minutes, bidirectional) "
            "VALUES (%s, %s, 10, %s)",
            (start, end, reverse),
        )
    condition = has_location_class_destination("commerce")
    assert condition(_state(story), {Slot.ACTOR: story.actor})
    assert _destinations(story) == (story.uncharted, story.uncharted)
    assert _destinations(story, anchor="home") == (
        story.uncharted,
        story.uncharted,
    )
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("UPDATE orrery_travel_edges SET duration_minutes = NULL")
    assert not condition(_state(story), {Slot.ACTOR: story.actor})
    assert _destinations(story) == (None, None)
    assert _destinations(story, anchor="home") == (None, None)
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE orrery_travel_edges SET duration_minutes = 10, "
            "route_method = 'osm_graph'"
        )
    assert not route_known(_state(story), story.origin, story.uncharted)
    assert _destinations(story) == (None, None)
    assert _destinations(story, anchor="home") == (None, None)
    if reverse:
        with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE orrery_travel_edges SET route_method = 'authored_edge', "
                "bidirectional = false"
            )
        assert not condition(_state(story), {Slot.ACTOR: story.actor})
        assert _destinations(story) == (None, None)
        assert _destinations(story, anchor="home") == (None, None)


def test_relocation_scout_and_anchors_skip_uncharted(story: Story) -> None:
    """Scouts and fixed/zone anchor twins all use the same duration rule."""
    _tag_venues(story)
    seed_routine_anchor(
        story.dbname, character_entity_id=story.actor, place_id=story.uncharted
    )
    state = _state(story)
    assert (
        _project_destination(
            state,
            actor_entity_id=story.actor,
            location_classes=("commerce",),
        )
        == story.charted
    )
    condition = routine_anchor_has_destination("home")
    assert not condition(state, {Slot.ACTOR: story.actor})
    assert _destinations(story, anchor="home") == (None, None)
    with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE character_routine_anchors SET mobility_policy = 'zone_resolved', "
            "place_id = NULL, zone_id = %s WHERE character_entity_id = %s",
            (story.zone, story.actor),
        )
    assert condition(_state(story), {Slot.ACTOR: story.actor})
    assert _destinations(story, anchor="home") == (story.charted, story.charted)


@pytest.mark.parametrize(
    "journey",
    ["planned", "project", "explicit", "explicit_with_class", "explicit_with_anchor"],
)
def test_unroutable_explicit_journey_refused_before_acceptance(
    story: Story, journey: str
) -> None:
    """Planned travel, project handoffs and explicit ids fail before a draft exists."""
    if journey == "project":
        with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO character_project_states "
                "(character_entity_id, project_type, status, stage, target_place_id) "
                "VALUES (%s, 'plan_relocation', 'active', 'committing', %s)",
                (story.actor, story.uncharted),
            )
        delta: dict[str, Any] = {"project.complete": {}}
    else:
        with closing(connect(story.dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO character_travel_states "
                "(character_entity_id, status, destination_place_id) "
                "VALUES (%s, 'planned', %s) ON CONFLICT (character_entity_id) "
                "DO UPDATE SET status = 'planned', "
                "destination_place_id = EXCLUDED.destination_place_id",
                (story.actor, story.uncharted),
            )
        payload: dict[str, Any] = {}
        if journey != "planned":
            payload["destination_place_id"] = story.uncharted
        if journey == "explicit_with_class":
            payload["destination_place_classes"] = ["commerce"]
        if journey == "explicit_with_anchor":
            payload["destination_anchor"] = "home"
        delta = {"travel.start": payload}
    before = _snapshot(story)
    resolution = Resolution(
        template_id="travel",
        priority=21,
        binding_hash="refuse-before-acceptance",
        bindings={Slot.ACTOR: story.actor},
        passes=True,
        branch_label="Depart",
        narrative_stub="{actor} starts the journey.",
        state_delta=delta,
    )
    with pytest.raises(
        ValueError,
        match=(
            "has no routable duration; an unroutable journey is refused "
            "before acceptance"
        ),
    ):
        _draft_from_resolution(resolution, state=_state(story))
    assert _snapshot(story) == before


@pytest.mark.parametrize("twin", ["sync", "async"])
def test_commit_refuses_route_without_duration(story: Story, twin: str) -> None:
    """Both commit paths recheck duration and roll back every pending write."""
    proposal = _proposal(story, {"destination_place_id": story.uncharted})
    before = _snapshot(story)
    message = "has no route duration .*; no ETA exists"
    if twin == "sync":
        with closing(connect(story.dbname)) as conn:
            try:
                with pytest.raises(ValueError, match=message):
                    events.commit_orrery_tick_sync(
                        conn,
                        proposal,
                        tick_chunk_id=story.tick,
                        slot=SLOT,
                    )
            finally:
                conn.rollback()
    else:

        async def run() -> None:
            conn = await asyncpg.connect(**asyncpg_kwargs(story.dbname))
            tx = conn.transaction()
            await tx.start()
            try:
                with pytest.raises(ValueError, match=message):
                    await events.commit_orrery_tick_async(
                        conn,
                        proposal,
                        tick_chunk_id=story.tick,
                        slot=SLOT,
                    )
            finally:
                await tx.rollback()
                await conn.close()

        asyncio.run(run())
    assert _snapshot(story) == before
