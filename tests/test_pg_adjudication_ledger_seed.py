"""``seed_adjudication_ledger`` commits a Skald ruling ledger on a clone.

The helper gives the adjudication history a ledger to read without the
owner's saves, which hold no rulings. These tests read back what it committed
on a disposable template clone: every promotion status with its narration
status, a defer streak of every outcome, scene pressures and prompt exposures
on every tick, and the history payload built from them. They also pin its
refusals: fewer than two ticks, and a save that already holds a pending
resolution.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery.history import adjudication_history
from tests.pg_fixtures import (
    AdjudicationLedgerSeed,
    connect,
    disposable_slot_database,
    seed_adjudication_ledger,
    seed_character,
    seed_place,
    seed_protagonist,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres

WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)


class LedgerStory(NamedTuple):
    """A clone with a located player, an actor, and three clocked ticks."""

    dbname: str
    actor_entity_id: int
    ticks: tuple[int, int, int]


@pytest.fixture()
def ledger_story() -> Iterator[LedgerStory]:
    """Seed the story the ledger needs, in need-clock anchor order."""

    with disposable_slot_database("qa885_ledger_seed") as dbname:
        seed_zone(
            dbname,
            name="Ledger Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        place_id, _ = seed_place(dbname, name="Ledger Plaza")
        seed_protagonist(
            dbname,
            base_timestamp=WORLD_TIME.isoformat(),
            current_location=place_id,
        )
        first = seed_story_clock(dbname, world_time=WORLD_TIME)
        _, actor_entity_id = seed_character(
            dbname, name="Ledger Actor", current_location=place_id
        )
        second = seed_story_clock(
            dbname, world_time=WORLD_TIME + timedelta(hours=1), scene=2
        )
        third = seed_story_clock(
            dbname, world_time=WORLD_TIME + timedelta(hours=2), scene=3
        )
        yield LedgerStory(dbname, actor_entity_id, (first, second, third))


def test_ledger_commits_every_status_and_streak_outcome(
    ledger_story: LedgerStory,
) -> None:
    """The committed rows and the history payload both show the full ledger."""

    ledger = seed_adjudication_ledger(
        ledger_story.dbname,
        actor_entity_id=ledger_story.actor_entity_id,
        ticks=ledger_story.ticks,
    )
    assert isinstance(ledger, AdjudicationLedgerSeed)
    assert ledger.tick_chunk_ids == ledger_story.ticks
    assert sorted(ledger.resolutions.values()) == [
        ("pending", "none"),
        ("pending", "none"),
        ("promoted", "succeeded"),
        ("skipped", "none"),
    ]
    assert sorted(ledger.streaks.values()) == [
        ("open", 3),
        ("ratified", 1),
        ("replace", 1),
        ("void", 1),
    ]
    assert len(ledger.scene_pressure_ids) == 3
    assert ledger.prompt_exposure_ids

    with closing(connect(ledger_story.dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, promotion_status::text, narration_status::text, "
            "actor_entity_id FROM orrery_resolutions ORDER BY id"
        )
        assert cur.fetchall() == [
            (row_id, promotion, narration, ledger_story.actor_entity_id)
            for row_id, (promotion, narration) in sorted(ledger.resolutions.items())
        ]
        cur.execute("SELECT id, actor_entity_id FROM orrery_adjudication_log")
        log_rows = cur.fetchall()
        assert sorted(row[0] for row in log_rows) == sorted(ledger.adjudication_log_ids)
        assert {row[1] for row in log_rows} == {ledger_story.actor_entity_id}
        cur.execute(
            "SELECT DISTINCT tick_chunk_id FROM orrery_scene_pressures "
            "ORDER BY tick_chunk_id"
        )
        assert tuple(row[0] for row in cur.fetchall()) == ledger_story.ticks
        cur.execute(
            "SELECT count(*) FROM orrery_narration_jobs WHERE state = 'succeeded'"
        )
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM offscreen_narrations")
        assert cur.fetchone()[0] == 1

    engine = create_engine(sqlalchemy_url(ledger_story.dbname))
    try:
        with Session(engine) as session:
            payload = adjudication_history(session)
    finally:
        engine.dispose()
    streaks = {
        streak["proposal_id"]: (streak["outcome"], streak["length"])
        for streak in payload["defer_streaks"]
    }
    assert streaks == dict(ledger.streaks)
    assert payload["totals"]["actions"] == {"defer": 6, "replace": 1, "void": 1}
    assert payload["totals"]["committed_resolutions"] == 4
    funnel = {
        key: sum(entry[key] for entry in payload["templates"].values())
        for key in ("promoted", "promotion_skipped", "promotion_pending", "narrated")
    }
    assert funnel == {
        "promoted": 1,
        "promotion_skipped": 1,
        "promotion_pending": 2,
        "narrated": 1,
    }
    assert payload["scene_pressures"]["rows"] == 3
    assert payload["exposures"]["resolution"]["rows"] > 0
    assert payload["exposures"]["scene_pressure"]["rows"] > 0


def test_ledger_refuses_fewer_than_two_ticks(ledger_story: LedgerStory) -> None:
    """A single tick cannot hold a deferral and its outcome."""

    with pytest.raises(ValueError, match="two or more distinct ascending"):
        seed_adjudication_ledger(
            ledger_story.dbname,
            actor_entity_id=ledger_story.actor_entity_id,
            ticks=ledger_story.ticks[:1],
        )
    with pytest.raises(ValueError, match="two or more distinct ascending"):
        seed_adjudication_ledger(
            ledger_story.dbname,
            actor_entity_id=ledger_story.actor_entity_id,
            ticks=(ledger_story.ticks[1], ledger_story.ticks[0]),
        )


def test_ledger_refuses_a_save_with_pending_resolutions(
    ledger_story: LedgerStory,
) -> None:
    """A second ledger would let promotion decide the first ledger's rows."""

    seed_adjudication_ledger(
        ledger_story.dbname,
        actor_entity_id=ledger_story.actor_entity_id,
        ticks=ledger_story.ticks[:2],
    )
    with pytest.raises(AssertionError, match="no pending resolution"):
        seed_adjudication_ledger(
            ledger_story.dbname,
            actor_entity_id=ledger_story.actor_entity_id,
            ticks=ledger_story.ticks[1:],
        )
    with closing(connect(ledger_story.dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM orrery_resolutions")
        assert cur.fetchone()[0] == 4
