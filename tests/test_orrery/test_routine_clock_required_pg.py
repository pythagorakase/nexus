"""Real PostgreSQL clock refusals and override semantics for Orrery hydration.

Disposable qa640_783s6 clones exercise narrative_chunks, chunk_metadata,
characters, places, and character_routine_anchors. Damaged metadata cases
roll back; each clone is dropped by tests.pg_fixtures afterward.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.audit import explain_dry_run
from nexus.agents.orrery.resolver import hydrate_world_state, resolve_dry_run
from nexus.agents.orrery.substrate import Slot, routine_anchor_due
from nexus.api.orrery_dev_endpoints import _default_anchor_chunk_id
from nexus.config import load_settings
from tests.pg_fixtures import (
    disposable_slot_database,
    seed_character,
    seed_place,
    seed_routine_anchor,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres
STORY_WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)
ENTRY_POINTS = (hydrate_world_state, resolve_dry_run, explain_dry_run)


@pytest.fixture
def clock_clone() -> Iterator[str]:
    """Own an initially empty, TEST-pinned disposable template clone."""

    with disposable_slot_database("qa640_783s6") as dbname:
        yield dbname


@pytest.fixture
def clock_session(clock_clone: str) -> Iterator[Session]:
    """Use a real SQLAlchemy session on the disposable target."""

    engine = create_engine(sqlalchemy_url(clock_clone))
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _assert_refusal(entry_point: Any, session: Session, anchor: int | None) -> None:
    """Call each real entry point with no override and no resolver packages."""

    args = () if entry_point is hydrate_world_state else ((),)
    error = (
        "Cannot hydrate Orrery world state without world_time "
        f"(anchor_chunk_id={anchor!r})"
    )
    with pytest.raises(ValueError, match=f"^{re.escape(error)}$"):
        entry_point(session, *args, anchor_chunk_id=anchor, window_chunks=30)


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_clockless_entry_points_raise_on_empty_clone(
    entry_point: Any, clock_session: Session
) -> None:
    """No actors or packages are needed to trigger the shared refusal."""

    assert (
        clock_session.execute(
            text("SELECT count(*) FROM narrative_chunks")
        ).scalar_one()
        == 0
    )
    assert (
        clock_session.execute(
            text("SELECT count(*) FROM character_routine_anchors")
        ).scalar_one()
        == 0
    )
    _assert_refusal(entry_point, clock_session, None)


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
@pytest.mark.parametrize("damage", ["missing_metadata", "null_clock"])
def test_missing_anchor_metadata_and_null_clock_raise(
    entry_point: Any, damage: str, clock_clone: str, clock_session: Session
) -> None:
    """A real anchor id cannot substitute for its missing metadata clock."""

    anchor = seed_story_clock(clock_clone, world_time=STORY_WORLD_TIME)
    try:
        if damage == "missing_metadata":
            clock_session.execute(
                text("DELETE FROM chunk_metadata WHERE chunk_id = :anchor"),
                {"anchor": anchor},
            )
            assert (
                clock_session.execute(
                    text(
                        "SELECT count(*) FROM chunk_metadata WHERE chunk_id = :anchor"
                    ),
                    {"anchor": anchor},
                ).scalar_one()
                == 0
            )
        else:
            clock_session.execute(
                text(
                    "UPDATE chunk_metadata SET world_time = NULL "
                    "WHERE chunk_id = :anchor"
                ),
                {"anchor": anchor},
            )
            assert (
                clock_session.execute(
                    text(
                        "SELECT world_time FROM chunk_metadata WHERE chunk_id = :anchor"
                    ),
                    {"anchor": anchor},
                ).scalar_one()
                is None
            )
        _assert_refusal(entry_point, clock_session, anchor)
    finally:
        clock_session.rollback()
    assert (
        clock_session.execute(
            text("SELECT world_time FROM chunk_metadata WHERE chunk_id = :anchor"),
            {"anchor": anchor},
        ).scalar_one()
        == STORY_WORLD_TIME
    )


def test_stored_and_explicit_clocks_reach_real_routine_predicate(
    clock_clone: str, clock_session: Session
) -> None:
    """Stored and explicit clocks reach the public predicate without synthesis."""

    anchor = seed_story_clock(clock_clone, world_time=STORY_WORLD_TIME)
    seed_zone(
        clock_clone,
        name="Clock Zone",
        min_longitude=-74,
        min_latitude=40,
        max_longitude=-73,
        max_latitude=41,
    )
    place, _ = seed_place(clock_clone, name="Clock Workplace")
    _, actor = seed_character(clock_clone, name="Clock Worker", current_location=place)
    seed_routine_anchor(
        clock_clone,
        character_entity_id=actor,
        place_id=place,
        anchor_type="work",
        schedule={
            "weekdays": [STORY_WORLD_TIME.weekday()],
            "start": "09:00",
            "end": "17:00",
        },
    )
    state = hydrate_world_state(clock_session, anchor_chunk_id=anchor, window_chunks=30)
    assert state.world_time == STORY_WORLD_TIME
    assert routine_anchor_due("work")(state, {Slot.ACTOR: actor})
    end = STORY_WORLD_TIME.replace(hour=17)
    for selected_anchor in (anchor, None):
        state = hydrate_world_state(
            clock_session,
            anchor_chunk_id=selected_anchor,
            world_time_override=end,
            window_chunks=30,
        )
        assert state.world_time == end
        assert not routine_anchor_due("work")(state, {Slot.ACTOR: actor})


def test_turn_and_dev_anchor_selection_can_return_none(clock_session: Session) -> None:
    """Both empty-slot selectors return None, and both resolver paths refuse it."""

    manager = TurnCycleManager(SimpleNamespace(settings=load_settings()))
    context = TurnContext(turn_id="clock-selector", user_input="Begin.", start_time=0)
    turn_anchor = manager._orrery_anchor_chunk_id(clock_session, context)
    dev_anchor = _default_anchor_chunk_id(clock_session)
    assert turn_anchor is None
    assert dev_anchor is None
    _assert_refusal(resolve_dry_run, clock_session, turn_anchor)
    _assert_refusal(explain_dry_run, clock_session, dev_anchor)
