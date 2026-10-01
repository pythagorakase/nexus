"""Crossed-boundary enumeration against real rows on disposable clones (issue 780).

Each module clone is seeded with ``seed_story_clock(T0)`` first. Characters,
places and the claim chain go through the shared seed helpers; only the rows
whose exact world-clock instant no production writer can set (a tag's
``expires_at_world_time``, project rows, an ``in_transit`` travel row) are
committed directly, after ``require_transaction_target``. Every enumeration
runs on a separate read-only connection from the QA family. Every expected
instant derives from this module's constants, never from ``nexus.toml``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any, NamedTuple

import psycopg2
import psycopg2.errors
from psycopg2.extras import RealDictCursor
import pytest

from nexus.agents.orrery.boundaries import (
    DEFAULT_PRODUCERS,
    BoundaryClass,
    BoundaryEnumeration,
    BoundaryWindow,
    enumerate_crossed_boundaries,
)
from nexus.agents.orrery.propagation import (
    drain_claim_propagation_sync,
    plan_due_propagations_sync,
)
from nexus.config import load_settings
from nexus.config.settings_models import OrreryProjectSettings, OrrerySettings
from scripts.qa_shift.boundary_catchup import (
    READ_ONLY_ERROR,
    measure_connection,
    open_read_only_connection,
)
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_character,
    seed_place,
    seed_story_clock,
    seed_zone,
)
from tests.test_orrery.claim_accounts_test_support import (
    _insert_chunk,
    _insert_claim,
    _settings,
    require_transaction_target,
    seed_chain,
)

pytestmark = pytest.mark.requires_postgres

T0 = datetime(2189, 10, 17, 22, 7, tzinfo=timezone.utc)
TRUSTING_LATENCY = timedelta(hours=1)
DEPTH_CAP = 4
ADVANCE_INTERVAL_HOURS = 24.0
STALL_ABANDON_THRESHOLD = 3
ABANDON_AFTER_HOURS = 168.0
ADVANCE_INTERVAL = timedelta(hours=ADVANCE_INTERVAL_HOURS)
ABANDON_AFTER = timedelta(hours=ABANDON_AFTER_HOURS)
TAG_TEXT = "off_grid"


def _orrery_settings() -> OrrerySettings:
    orrery = load_settings().orrery
    if orrery is None:
        raise RuntimeError("nexus.toml has no [orrery] settings")
    return orrery


settings = _orrery_settings().model_copy(
    update={
        "contagion": _settings(trusting="1h", depth_cap=DEPTH_CAP),
        "projects": OrreryProjectSettings(
            advance_interval_hours=ADVANCE_INTERVAL_HOURS,
            stall_abandon_threshold=STALL_ABANDON_THRESHOLD,
            abandon_after_stalled_world_hours=ABANDON_AFTER_HOURS,
        ),
    }
)

# The main clone's schedule.
TAG_A_AT = T0 + timedelta(minutes=30)
TAG_B_AT = T0 + timedelta(hours=48)
STALE_TAG_AT = T0 - timedelta(minutes=10)
# Applied before it expired: a tag that really lapsed at T0-10m, still uncleared.
STALE_TAG_APPLIED_AT = STALE_TAG_AT - timedelta(hours=1)
P1_DUE = T0 + timedelta(hours=2)
P2_DUE = T0 + timedelta(hours=5)
P2_STALLS = 3
TRAVEL_ETA = T0 + timedelta(hours=6)
CHAIN_LENGTH = 4
SKIPS = (0, 60, 4320)
TEN_DAYS = T0 + timedelta(days=10)

# The storm clone's schedule.
STORM_CHARACTERS = 50
STORM_TRAVELERS = 10
STORM_STALL_EVERY = 5
STORM_TAG_STEP = timedelta(minutes=30)
STORM_DUE_STEP = timedelta(hours=1)
STORM_ETA_STEP = timedelta(hours=6)
STORM_CHAINS = 5
STORM_CHAIN_LENGTH = 5
STORM_HORIZONS = (timedelta(days=7), timedelta(days=30))

DET = BoundaryClass.DETERMINISTIC
ADJ = BoundaryClass.ADJUDICABLE
PRODUCER_NAMES = tuple(producer.name for producer in DEFAULT_PRODUCERS)


class BoundaryClone(NamedTuple):
    """The main clone and the committed rows each test names."""

    dbname: str
    clock_chunk_id: int
    incident_id: int
    chain: list[int]
    tag_a: int
    tag_b: int
    p1: int
    p2: int
    traveler: int


def _insert_expiring_tag(
    cur: Any, entity_id: int, expires_at: datetime, applied_at: datetime = T0
) -> int:
    cur.execute(
        """
        INSERT INTO entity_tags (
            entity_id, tag_id, source_kind, applied_at_world_time,
            expires_at_world_time
        )
        SELECT %s, id, 'template', %s, %s
        FROM tags WHERE tag = %s AND NOT deprecated
        RETURNING id
        """,
        (entity_id, applied_at, expires_at, TAG_TEXT),
    )
    row = cur.fetchone()
    assert row is not None and cur.rowcount == 1
    return int(row["id"])


def _insert_project(
    cur: Any, entity_id: int, due: datetime, stall_count: int, chunk_id: int
) -> int:
    cur.execute(
        """
        INSERT INTO character_project_states (
            character_entity_id, project_type, status, stage, stall_count,
            next_eligible_at_world_time, source_chunk_id
        ) VALUES (
            %s, 'build_venture', 'active', 'laying_groundwork', %s, %s, %s
        )
        RETURNING id
        """,
        (entity_id, stall_count, due, chunk_id),
    )
    return int(cur.fetchone()["id"])


def _insert_transit(
    cur: Any, entity_id: int, origin: int, destination: int, eta: datetime
) -> None:
    cur.execute(
        """
        INSERT INTO character_travel_states (
            character_entity_id, status, anchor_place_id, origin_place_id,
            destination_place_id, estimated_duration_minutes,
            started_at_world_time, updated_at_world_time, eta_world_time
        ) VALUES (%s, 'in_transit', %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            entity_id,
            origin,
            origin,
            destination,
            (eta - T0).total_seconds() / 60,
            T0,
            T0,
            eta,
        ),
    )
    assert cur.rowcount == 1


def _incident_of(cur: Any, claim_id: int) -> int:
    cur.execute("SELECT world_event_id FROM claims WHERE id = %s", (claim_id,))
    return int(cur.fetchone()["world_event_id"])


def _seed_places(dbname: str, label: str) -> tuple[int, int]:
    seed_zone(
        dbname,
        name=f"{label} Zone",
        min_longitude=-75.0,
        min_latitude=40.0,
        max_longitude=-73.0,
        max_latitude=41.0,
    )
    origin, _ = seed_place(dbname, name=f"{label} Origin")
    destination, _ = seed_place(
        dbname, name=f"{label} Destination", longitude=-73.9, latitude=40.8
    )
    return origin, destination


@pytest.fixture(scope="module")
def boundary_clone() -> Iterator[BoundaryClone]:
    """Seed the clock, the claim chain, tags, two projects and one journey."""

    with disposable_slot_database("qa640_780_boundaries") as dbname:
        clock_chunk_id = seed_story_clock(dbname, world_time=T0)
        chain = seed_chain(dbname, "boundary-chain", CHAIN_LENGTH)
        origin, destination = _seed_places(dbname, "Boundary")
        entities = {
            role: seed_character(dbname, name=f"boundary-{role}")[1]
            for role in ("tag-a", "tag-b", "tag-stale", "p1", "p2", "traveler")
        }
        with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
            with conn, conn.cursor() as cur:
                claim_id = _insert_claim(
                    cur,
                    chunk_id=clock_chunk_id,
                    source_entity_id=chain[0],
                    birth_world_time=T0,
                )
                incident_id = _incident_of(cur, claim_id)
                require_transaction_target(cur)
                tag_a = _insert_expiring_tag(cur, entities["tag-a"], TAG_A_AT)
                tag_b = _insert_expiring_tag(cur, entities["tag-b"], TAG_B_AT)
                _insert_expiring_tag(
                    cur,
                    entities["tag-stale"],
                    STALE_TAG_AT,
                    applied_at=STALE_TAG_APPLIED_AT,
                )
                p1 = _insert_project(cur, entities["p1"], P1_DUE, 0, clock_chunk_id)
                p2 = _insert_project(
                    cur, entities["p2"], P2_DUE, P2_STALLS, clock_chunk_id
                )
                _insert_transit(
                    cur, entities["traveler"], origin, destination, TRAVEL_ETA
                )
        yield BoundaryClone(
            dbname=dbname,
            clock_chunk_id=clock_chunk_id,
            incident_id=incident_id,
            chain=chain,
            tag_a=tag_a,
            tag_b=tag_b,
            p1=p1,
            p2=p2,
            traveler=entities["traveler"],
        )


def _enumerate(dbname: str, window: BoundaryWindow) -> BoundaryEnumeration:
    with closing(open_read_only_connection(dbname)) as conn:
        with conn.cursor() as cur:
            enumeration = enumerate_crossed_boundaries(cur, window, settings=settings)
        conn.rollback()
    return enumeration


Row = tuple[str, tuple[Any, ...], datetime, BoundaryClass, int | None]


def _rows(enumeration: BoundaryEnumeration) -> list[Row]:
    return [
        (
            crossing.producer,
            crossing.subject_key,
            crossing.occurs_at_world_time,
            crossing.boundary_class,
            crossing.owner_issue,
        )
        for crossing in enumeration.crossings
    ]


def _hop(clone: BoundaryClone, depth: int) -> Row:
    return (
        "claim_propagation",
        ("claim_hop", clone.incident_id, clone.chain[depth]),
        T0 + depth * TRUSTING_LATENCY,
        DET,
        None,
    )


def _three_day_rows(clone: BoundaryClone) -> list[Row]:
    return [
        ("tag_expiry", ("entity_tag", clone.tag_a), TAG_A_AT, DET, None),
        _hop(clone, 1),
        _hop(clone, 2),
        ("project_due", ("project", clone.p1), P1_DUE, ADJ, None),
        _hop(clone, 3),
        ("project_due", ("project", clone.p2), P2_DUE, ADJ, None),
        ("project_abandon", ("project", clone.p2), P2_DUE, ADJ, None),
        ("travel_eta", ("travel", clone.traveler), TRAVEL_ETA, ADJ, 785),
        (
            "project_neglected",
            ("project", clone.p1),
            P1_DUE + ADVANCE_INTERVAL,
            ADJ,
            None,
        ),
        (
            "project_neglected",
            ("project", clone.p2),
            P2_DUE + ADVANCE_INTERVAL,
            ADJ,
            None,
        ),
        ("tag_expiry", ("entity_tag", clone.tag_b), TAG_B_AT, DET, None),
    ]


def _ten_day_rows(clone: BoundaryClone) -> list[Row]:
    return _three_day_rows(clone) + [
        ("project_abandon", ("project", clone.p1), P1_DUE + ABANDON_AFTER, ADJ, None)
    ]


def _counts(rows: Sequence[Row]) -> dict[str, int]:
    tally = Counter(row[0] for row in rows)
    return {name: tally[name] for name in PRODUCER_NAMES}


def _skip_window(minutes: int) -> BoundaryWindow:
    return BoundaryWindow.projected_child_clock(T0, timedelta(minutes=minutes))


def test_zero_time_turn_crosses_nothing(boundary_clone: BoundaryClone) -> None:
    enumeration = _enumerate(boundary_clone.dbname, _skip_window(0))

    assert enumeration.crossings == ()
    assert enumeration.at_or_before_previous["tag_expiry"] == 1
    assert dict(enumeration.at_or_before_previous) == {
        name: int(name == "tag_expiry") for name in PRODUCER_NAMES
    }
    assert dict(enumeration.counts) == {name: 0 for name in PRODUCER_NAMES}


def test_one_hour_skip(boundary_clone: BoundaryClone) -> None:
    enumeration = _enumerate(boundary_clone.dbname, _skip_window(60))

    assert _rows(enumeration) == [
        ("tag_expiry", ("entity_tag", boundary_clone.tag_a), TAG_A_AT, DET, None),
        _hop(boundary_clone, 1),
    ]


def test_three_day_skip_orders_by_instant_then_precedence(
    boundary_clone: BoundaryClone,
) -> None:
    enumeration = _enumerate(boundary_clone.dbname, _skip_window(4320))

    assert enumeration.window.source == "projected_child_clock"
    assert _rows(enumeration) == _three_day_rows(boundary_clone)
    assert dict(enumeration.counts) == _counts(_three_day_rows(boundary_clone))


def test_target_horizon_reaches_abandonment(boundary_clone: BoundaryClone) -> None:
    window = BoundaryWindow.target_horizon(T0, TEN_DAYS)
    enumeration = _enumerate(boundary_clone.dbname, window)

    assert enumeration.window.source == "target_horizon"
    assert _rows(enumeration) == _ten_day_rows(boundary_clone)


def test_planner_matches_drain(boundary_clone: BoundaryClone) -> None:
    horizon = T0 + (CHAIN_LENGTH - 1) * TRUSTING_LATENCY
    with closing(connect(boundary_clone.dbname, cursor_factory=RealDictCursor)) as conn:
        try:
            with conn.cursor() as cur:
                planned = plan_due_propagations_sync(
                    cur,
                    horizon_world_time=horizon,
                    settings=settings.contagion,
                    distortion_settings=settings.distortion,
                )
                chunk_id, stamped = _insert_chunk(cur, time_delta=horizon - T0)
                assert stamped == horizon
                result = drain_claim_propagation_sync(
                    cur,
                    tick_chunk_id=chunk_id,
                    settings=settings.contagion,
                    distortion_settings=settings.distortion,
                )
                cur.execute(
                    """
                    SELECT knower_entity_id, acquired_at_world_time
                    FROM claim_awareness
                    WHERE id = ANY(%s)
                    ORDER BY acquired_at_world_time, knower_entity_id
                    """,
                    (list(result.awareness_ids),),
                )
                minted = [
                    (int(row["knower_entity_id"]), row["acquired_at_world_time"])
                    for row in cur.fetchall()
                ]
        finally:
            conn.rollback()

    expected = [
        (boundary_clone.chain[depth], T0 + depth * TRUSTING_LATENCY)
        for depth in range(1, CHAIN_LENGTH)
    ]
    assert [(hop.knower_entity_id, hop.acquired_at_world_time) for hop in planned] == (
        expected
    )
    assert minted == expected
    assert result.minted_count == len(planned) == CHAIN_LENGTH - 1


def test_family_is_read_only(boundary_clone: BoundaryClone) -> None:
    with closing(open_read_only_connection(boundary_clone.dbname)) as conn:
        report = measure_connection(
            conn,
            parent_chunk_id=None,
            skip_minutes=SKIPS,
            target_world_time=TEN_DAYS,
            settings=settings,
        )
        with (
            conn.cursor() as cur,
            pytest.raises(psycopg2.errors.ReadOnlySqlTransaction),
        ):
            cur.execute("INSERT INTO seasons (id) VALUES (780)")
        conn.rollback()

    assert report["family"] == "boundary_catchup"
    assert report["database"] == boundary_clone.dbname
    assert report["transaction_read_only"] == "on"
    assert report["parent_chunk_id"] == boundary_clone.clock_chunk_id
    assert report["previous_world_time"] == T0.isoformat()
    one_hour = [
        ("tag_expiry", ("entity_tag", boundary_clone.tag_a), TAG_A_AT, DET, None),
        _hop(boundary_clone, 1),
    ]
    expected = [
        ([], 0),
        (one_hour, 60),
        (_three_day_rows(boundary_clone), 4320),
        (_ten_day_rows(boundary_clone), None),
    ]
    assert len(report["windows"]) == len(expected)
    for window, (rows, skip) in zip(report["windows"], expected):
        if skip is None:
            assert window["source"] == "target_horizon"
            assert window["target_world_time"] == TEN_DAYS.isoformat()
        else:
            assert window["source"] == "projected_child_clock"
            assert window["skip_minutes"] == skip
        assert window["counts"] == _counts(rows)
        assert window["total"] == len(rows)
        assert window["at_or_before_previous"]["tag_expiry"] == 1
        assert [
            (c["producer"], tuple(c["subject_key"]), c["occurs_at_world_time"])
            for c in window["crossings"]
        ] == [(row[0], row[1], row[2].isoformat()) for row in rows]

    with closing(connect(boundary_clone.dbname)) as writable:
        with pytest.raises(RuntimeError, match=READ_ONLY_ERROR):
            measure_connection(
                writable,
                parent_chunk_id=None,
                skip_minutes=SKIPS,
                target_world_time=None,
                settings=settings,
            )
        writable.rollback()


def _storm_counts(horizon: timedelta) -> dict[str, int]:
    """Closed-form crossings per producer for a window of length ``horizon``."""

    def steps(span: timedelta, step: timedelta, cap: int) -> int:
        return 0 if span < timedelta(0) else min(cap, span // step)

    stalled = STORM_CHARACTERS // STORM_STALL_EVERY
    unstalled_reach = steps(horizon - ABANDON_AFTER, STORM_DUE_STEP, STORM_CHARACTERS)
    return {
        "tag_expiry": steps(horizon, STORM_TAG_STEP, STORM_CHARACTERS),
        "claim_propagation": STORM_CHAINS
        * steps(horizon, TRUSTING_LATENCY, STORM_CHAIN_LENGTH - 1),
        "travel_eta": steps(horizon, STORM_ETA_STEP, STORM_TRAVELERS),
        "project_due": steps(horizon, STORM_DUE_STEP, STORM_CHARACTERS),
        "project_neglected": steps(
            horizon - ADVANCE_INTERVAL, STORM_DUE_STEP, STORM_CHARACTERS
        ),
        "project_abandon": steps(horizon, STORM_DUE_STEP * STORM_STALL_EVERY, stalled)
        + unstalled_reach
        - unstalled_reach // STORM_STALL_EVERY,
    }


def test_synthetic_storm_calibration() -> None:
    with disposable_slot_database("qa640_780_storm") as dbname:
        clock_chunk_id = seed_story_clock(dbname, world_time=T0)
        origin, destination = _seed_places(dbname, "Storm")
        storm = [
            seed_character(dbname, name=f"storm-{k}")[1]
            for k in range(1, STORM_CHARACTERS + 1)
        ]
        chains = [
            seed_chain(dbname, f"storm-chain-{index}", STORM_CHAIN_LENGTH)
            for index in range(STORM_CHAINS)
        ]
        with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
            with conn, conn.cursor() as cur:
                for chain in chains:
                    _insert_claim(
                        cur,
                        chunk_id=clock_chunk_id,
                        source_entity_id=chain[0],
                        birth_world_time=T0,
                    )
                require_transaction_target(cur)
                for k, entity_id in enumerate(storm, start=1):
                    _insert_expiring_tag(cur, entity_id, T0 + k * STORM_TAG_STEP)
                    _insert_project(
                        cur,
                        entity_id,
                        T0 + k * STORM_DUE_STEP,
                        STALL_ABANDON_THRESHOLD if k % STORM_STALL_EVERY == 0 else 0,
                        clock_chunk_id,
                    )
                    if k <= STORM_TRAVELERS:
                        _insert_transit(
                            cur, entity_id, origin, destination, T0 + k * STORM_ETA_STEP
                        )

        windows = [(f"skip_{minutes}m", _skip_window(minutes)) for minutes in SKIPS] + [
            (
                f"target_{horizon.days}d",
                BoundaryWindow.target_horizon(T0, T0 + horizon),
            )
            for horizon in STORM_HORIZONS
        ]
        calibration = []
        with closing(open_read_only_connection(dbname)) as conn:
            with conn.cursor() as cur:
                for label, window in windows:
                    started = time.perf_counter()
                    enumeration = enumerate_crossed_boundaries(
                        cur, window, settings=settings
                    )
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    span = window.target_world_time - window.previous_world_time
                    assert dict(enumeration.counts) == _storm_counts(span), label
                    assert dict(enumeration.at_or_before_previous) == {
                        name: 0 for name in PRODUCER_NAMES
                    }
                    per_subject = Counter(c.subject_key for c in enumeration.crossings)
                    calibration.append(
                        {
                            "window": label,
                            "source": window.source,
                            "counts": dict(enumeration.counts),
                            "total": enumeration.total,
                            "max_crossings_per_subject": max(
                                per_subject.values(), default=0
                            ),
                            "wall_clock_ms": round(elapsed_ms, 1),
                        }
                    )
            conn.rollback()

    print("BOUNDARY_CALIBRATION " + json.dumps({"windows": calibration}))
