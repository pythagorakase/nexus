"""Seeded native-path reproduction of tick-counted travel arrival (785-S1b).

Decision 785-Q1 accepts a seeded setup when it drives the real
resolve-and-commit path. Every turn here is staged by ``seed_accepted_turn``
(production staging through ``resolve_dry_run``) and accepted through the
production commit (``commit_orrery_tick_sync``); the test never calls the
resolver or the commit writer itself.

One story is played twice, on two disposable template clones routed under
slot 2, with identical seeding and identical turns. The only difference is
the configured ``mixed`` route speed, so the ETA stored at departure differs
by orders of magnitude while everything the resolver reads stays equal.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Any, NamedTuple

import pytest

from nexus.config.loader import settings_path_scope
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_accepted_turn,
    seed_character,
    seed_entity_tag,
    seed_place,
    seed_protagonist,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres

ROUTED_SLOT = 2
BASE_TIMESTAMP = "2073-08-01T12:00:00+00:00"
TRAVELER = "Repro Traveler"
PROTAGONIST = "Repro Player"
STANDING_SOCIALIZE_DEBT = 200
# Test values, not tunables: one run's ETA falls inside the first tick, the
# other's lies a day past every tick the story plays.
FAST_MIXED_KMH = 600.0
SLOW_MIXED_KMH = 0.05
DEPARTURE_BOUND = 8
ARRIVAL_BOUND = 24

# The first 32 primary continuation deltas (minutes) of the reference corpus,
# in chunk order, after its zero-minute bootstrap opening. Source (read-only,
# never connected to by this test):
#   SELECT extract(epoch FROM time_delta)/60 FROM chunk_metadata
#   WHERE world_layer = 'primary' ORDER BY chunk_id LIMIT 33
# on ref_codex_bakeoff_2026_07, dropping the leading 0.
CORPUS_DELTAS_MINUTES = (
    4, 3, 2, 3, 4, 4, 3, 4, 4, 4, 3, 6, 4, 7, 6, 1,
    4, 8, 6, 8, 3, 120, 7, 4, 4, 18, 6, 12, 8, 8, 4, 8,
)  # fmt: skip
TURN_CHOICES = (
    "Keep to the flat a while longer.",
    "Look out over the street.",
)


class Tick(NamedTuple):
    """One accepted turn as the traveler's committed state saw it."""

    turn: int
    chunk_id: int
    world_time: datetime
    status: str | None
    progress: float | None
    started_at: datetime | None
    eta: datetime | None
    resolutions: tuple[tuple[str, tuple[str, ...]], ...]
    traveler_events: tuple[str, ...]


class StoryRun(NamedTuple):
    """Seeded ids, every played tick, and the departure and arrival indexes."""

    seeded_ids: dict[str, int]
    ticks: list[Tick]
    departure_index: int
    arrival_index: int


def _travel_config(tmp_path: Path, speed_kmh_mixed: float) -> Path:
    """Write the real nexus.toml with only the mixed route speed replaced."""

    source = Path("nexus.toml").read_text()
    source, replaced = re.subn(
        r"(^\[orrery\.travel\.speed_kmh\]\n(?:[^\[\n].*\n)*?)mixed = .*$",
        rf"\g<1>mixed = {speed_kmh_mixed}",
        source,
        count=1,
        flags=re.MULTILINE,
    )
    assert replaced == 1
    config = tmp_path / f"nexus_mixed_{speed_kmh_mixed}.toml"
    config.write_text(source)
    return config


def _read_tick(cur: Any, *, index: int, chunk_id: int, traveler: int) -> Tick:
    """Read the tick chunk's clock, the traveler's row, and its resolutions."""

    cur.execute(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s", (chunk_id,)
    )
    (world_time,) = cur.fetchone()
    cur.execute(
        """
        SELECT status::text, progress_ratio, started_at_world_time, eta_world_time
        FROM character_travel_states
        WHERE character_entity_id = %s
        """,
        (traveler,),
    )
    travel = cur.fetchone()
    status, progress, started_at, eta = travel if travel else (None,) * 4
    cur.execute(
        """
        SELECT r.template_id,
               ARRAY(
                   SELECT e.event_type
                   FROM unnest(r.event_ids) WITH ORDINALITY AS u(event_id, ord)
                   JOIN world_events e ON e.id = u.event_id
                   ORDER BY u.ord
               )
        FROM orrery_resolutions r
        WHERE r.tick_chunk_id = %s AND r.actor_entity_id = %s
        ORDER BY r.id
        """,
        (chunk_id, traveler),
    )
    resolutions = tuple(
        (str(template_id), tuple(event_types))
        for template_id, event_types in cur.fetchall()
    )
    cur.execute(
        """
        SELECT event_type FROM world_events
        WHERE tick_chunk_id = %s AND actor_entity_id = %s
        ORDER BY id
        """,
        (chunk_id, traveler),
    )
    traveler_events = tuple(str(row[0]) for row in cur.fetchall())
    return Tick(
        turn=index,
        chunk_id=chunk_id,
        world_time=world_time,
        status=status,
        progress=None if progress is None else float(progress),
        started_at=started_at,
        eta=eta,
        resolutions=resolutions,
        traveler_events=traveler_events,
    )


def _tick_table(ticks: list[Tick]) -> str:
    """Render the per-tick outcomes for a failure message or the evidence."""

    lines = ["turn | world time | status | progress | ETA | resolutions | events"]
    for tick in ticks:
        lines.append(
            f"{tick.turn} | {tick.world_time.isoformat()} | {tick.status} | "
            f"{tick.progress} | "
            f"{tick.eta.isoformat() if tick.eta else None} | "
            f"{list(tick.resolutions)} | {list(tick.traveler_events)}"
        )
    return "\n".join(lines)


def _play_until_arrival(
    dbname: str, speed_kmh_mixed: float, tmp_path: Path
) -> StoryRun:
    """Seed the story on ``dbname`` and accept turns until the traveler arrives.

    Repro Origin is tagged ``urban_dense``, a live ``place_environment`` class
    that is public (``PUBLIC_PLACE_CLASSES``) and not a social venue. Without a
    public class an untagged fixed location never satisfies
    ``can_move_publicly(@actor)``, so both social departure branches stay
    blocked on every turn; the tag opens them and changes nothing else about
    the traveler, and it matches the real Midtown location of the origin.

    The traveler's ``socialize`` need row is seeded by the need-state trigger
    on ``characters`` (debt 0). The test overwrites that trigger-seeded row
    with a standing debt, because no production writer sets a standing debt
    without elapsed play; every later change to it comes from accepted turns.
    """

    with pytest.MonkeyPatch.context() as mp:
        route_slot_to_disposable(mp.setattr, slot=ROUTED_SLOT, dbname=dbname)
        with settings_path_scope(_travel_config(tmp_path, speed_kmh_mixed)):
            zone_id = seed_zone(
                dbname,
                name="Repro Zone",
                min_longitude=-74.1,
                min_latitude=40.6,
                max_longitude=-73.8,
                max_latitude=40.9,
            )
            origin_id, origin_entity = seed_place(
                dbname, name="Repro Origin", longitude=-73.9857, latitude=40.7484
            )
            venue_id, venue_entity = seed_place(
                dbname, name="Repro Venue", longitude=-73.9857, latitude=40.7574
            )
            flat_id, flat_entity = seed_place(
                dbname, name="Repro Flat", longitude=-73.9700, latitude=40.7600
            )
            venue_tag_id = seed_entity_tag(
                dbname, entity_id=venue_entity, tag="commerce"
            )
            origin_tag_id = seed_entity_tag(
                dbname, entity_id=origin_entity, tag="urban_dense"
            )
            player_id, player_entity = seed_protagonist(
                dbname,
                name=PROTAGONIST,
                base_timestamp=BASE_TIMESTAMP,
                current_location=flat_id,
            )
            traveler_id, traveler = seed_character(
                dbname,
                name=TRAVELER,
                summary=f"{TRAVELER} keeps to a quiet room at Repro Origin.",
                current_location=origin_id,
            )
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE character_need_states
                    SET debt_score = %s, last_evaluated_at = %s
                    WHERE character_entity_id = %s AND need_type = 'socialize'
                    """,
                    (STANDING_SOCIALIZE_DEBT, BASE_TIMESTAMP, traveler),
                )
                assert cur.rowcount == 1
            seeded_ids = {
                "zone": zone_id,
                "origin": origin_id,
                "origin_entity": origin_entity,
                "venue": venue_id,
                "venue_entity": venue_entity,
                "flat": flat_id,
                "flat_entity": flat_entity,
                "venue_tag": venue_tag_id,
                "origin_tag": origin_tag_id,
                "player": player_id,
                "player_entity": player_entity,
                "traveler": traveler_id,
                "traveler_entity": traveler,
            }
            references = {
                "characters": [
                    {
                        "character_id": player_id,
                        "character_name": PROTAGONIST,
                        "reference_type": "present",
                    },
                    {
                        "character_id": traveler_id,
                        "character_name": TRAVELER,
                        "reference_type": "mentioned",
                    },
                ],
                "places": [{"place_id": flat_id, "reference_type": "setting"}],
                "factions": [],
            }
            ticks: list[Tick] = []
            departure_index: int | None = None
            arrival_index: int | None = None
            user_text = "Begin the story."
            for index, delta in enumerate((0, *CORPUS_DELTAS_MINUTES)):
                chunk_id = seed_accepted_turn(
                    dbname,
                    user_text=user_text,
                    storyteller_text=(
                        f"Turn {index}: {PROTAGONIST} waits at Repro Flat. "
                        f"Across town, {TRAVELER} has gone too long without "
                        "company."
                    ),
                    choices=list(TURN_CHOICES),
                    choice_text=TURN_CHOICES[0],
                    time_delta=timedelta(minutes=delta),
                    reference_updates=references,
                    slot=ROUTED_SLOT,
                )
                user_text = TURN_CHOICES[0]
                with closing(connect(dbname)) as conn, conn.cursor() as cur:
                    tick = _read_tick(
                        cur, index=index, chunk_id=chunk_id, traveler=traveler
                    )
                    conn.rollback()
                ticks.append(tick)
                if departure_index is None:
                    if "social_travel_departed" in tick.traveler_events:
                        departure_index = index
                    elif index >= DEPARTURE_BOUND:
                        pytest.fail(
                            f"{dbname}: no social_travel_departed within "
                            f"{DEPARTURE_BOUND} continuations at seed_salt ''; "
                            "per-tick outcomes for the traveler:\n" + _tick_table(ticks)
                        )
                elif "travel_arrived" in tick.traveler_events:
                    arrival_index = index
                    break
                elif index - departure_index >= ARRIVAL_BOUND:
                    pytest.fail(
                        f"{dbname}: no travel_arrived within {ARRIVAL_BOUND} "
                        "continuations after departure at seed_salt ''; "
                        "per-tick outcomes for the traveler:\n" + _tick_table(ticks)
                    )
    assert departure_index is not None and arrival_index is not None, _tick_table(ticks)
    print(f"\n{dbname} (mixed {speed_kmh_mixed} km/h)\n{_tick_table(ticks)}")
    return StoryRun(seeded_ids, ticks, departure_index, arrival_index)


def _journey(
    run: StoryRun,
) -> list[tuple[int, tuple[tuple[str, tuple[str, ...]], ...]]]:
    """The traveler's committed resolutions from departure through arrival."""

    return [
        (tick.turn - run.departure_index, tick.resolutions)
        for tick in run.ticks[run.departure_index : run.arrival_index + 1]
    ]


def test_arrival_tick_count_ignores_route_eta(tmp_path: Path) -> None:
    """Reproduce the defect: arrival counts ticks and ignores the stored ETA.

    The same seeded story, played through the production staging and
    acceptance path on two clones whose only difference is the configured
    ``mixed`` speed, departs on the same tick, commits the same journey, and
    arrives on the same tick offset, although one ETA passes before the
    second tick and the other lies a day past the arrival. 785-S3a inverts
    assertions (d) to (f): arrival then follows the crossed ETA.
    """

    with disposable_slot_database("qa640_785s1b_fast") as fast_db:
        fast = _play_until_arrival(fast_db, FAST_MIXED_KMH, tmp_path)
    with disposable_slot_database("qa640_785s1b_slow") as slow_db:
        slow = _play_until_arrival(slow_db, SLOW_MIXED_KMH, tmp_path)

    # (a) Both clones seeded the same ids, and played the same chunks.
    assert fast.seeded_ids == slow.seeded_ids
    assert [tick.chunk_id for tick in fast.ticks] == [
        tick.chunk_id for tick in slow.ticks
    ]

    # (b) Same departure tick; the speed override reached the commit.
    assert fast.departure_index == slow.departure_index
    fast_departure = fast.ticks[fast.departure_index]
    slow_departure = slow.ticks[slow.departure_index]
    for departure in (fast_departure, slow_departure):
        assert departure.status == "in_transit"
        assert departure.started_at == departure.world_time
    fast_eta, slow_eta = fast_departure.eta, slow_departure.eta
    assert fast_eta is not None and slow_eta is not None
    assert fast_eta - fast_departure.world_time < timedelta(minutes=1)
    assert slow_eta - slow_departure.world_time > timedelta(hours=24)

    # (c) The committed journey is identical in both runs.
    assert _journey(fast) == _journey(slow)

    # (d) Arrival lands on the same tick offset, which counts ticks.
    fast_offset = fast.arrival_index - fast.departure_index
    slow_offset = slow.arrival_index - slow.departure_index
    assert fast_offset == slow_offset
    assert fast_offset >= 4

    # (e) Fast run: the ETA passed on an earlier tick, which left the
    # traveler in transit.
    assert any(
        tick.world_time >= fast_eta and tick.status == "in_transit"
        for tick in fast.ticks[fast.departure_index : fast.arrival_index]
    )

    # (f) Slow run: arrival committed before the ETA recorded at departure.
    assert slow.ticks[slow.arrival_index].world_time < slow_eta
