"""Routine-anchor custody on real PostgreSQL (#783 S1a, migration 145).

Each test owns a disposable ``qa640_783s1a`` template clone, migrated through
145 by ``disposable_slot_database`` and dropped afterward. Custody runs both
twins (psycopg2 and asyncpg) in caller-owned transactions; no fleet database
is read or written.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import asyncpg  # type: ignore[import-untyped]
import psycopg2
import psycopg2.errors
import pytest
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.routine_anchors import (
    ROUTINE_ANCHOR_TYPES,
    ROUTINE_ANCHOR_WRITERS,
    ROUTINE_MOBILITY_POLICIES,
    RoutineAnchorChange,
    RoutineAnchorCustodyError,
    RoutineSchedule,
    apply_routine_anchor_changes_async,
    apply_routine_anchor_changes_sync,
)
from tests.pg_fixtures import (
    asyncpg_kwargs,
    connect,
    disposable_slot_database,
    seed_character,
    seed_committed_chunk,
    seed_place,
    seed_protagonist,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres

WRITER = "skald_state_update"


@dataclass(frozen=True)
class Seeded:
    """Ids seeded on one custody clone."""

    dbname: str
    chunk_1: int
    chunk_2: int
    bare_chunk: int
    zone: int
    home_place: int
    home_place_entity: int
    work_place: int
    mara: int
    dex: int
    event: int


def _seed(dbname: str) -> Seeded:
    """Seed a clock, two chunks, a zone, two places, two characters and an event."""

    seed_protagonist(dbname)
    chunk_1 = seed_committed_chunk(dbname, raw_text="Mara walks home.")
    chunk_2 = seed_committed_chunk(dbname, raw_text="Mara loses the job.", scene=2)
    zone = seed_zone(
        dbname,
        name="Harbor District",
        min_longitude=-75.0,
        min_latitude=40.0,
        max_longitude=-73.0,
        max_latitude=41.5,
    )
    home_place, home_place_entity = seed_place(dbname, name="Flat 4")
    work_place, _ = seed_place(dbname, name="Dock 9", longitude=-74.01, latitude=40.70)
    # Neither character stands at a place, and the event names no location,
    # so nothing but an anchor references either place.
    _, mara = seed_character(dbname, name="Mara Voss")
    _, dex = seed_character(dbname, name="Dex Halloran")
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
            "VALUES ('No metadata.', 'No metadata.') RETURNING id"
        )
        bare_chunk = int(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO world_events (event_type, tick_chunk_id, actor_entity_id, "
            "world_layer, source, changed_fields, payload) "
            "VALUES ('slept', %s, %s, 'primary', 'resolver', '{}', '{}') "
            "RETURNING id",
            (chunk_2, mara),
        )
        event = int(cur.fetchone()[0])
    return Seeded(
        dbname=dbname,
        chunk_1=chunk_1,
        chunk_2=chunk_2,
        bare_chunk=bare_chunk,
        zone=zone,
        home_place=home_place,
        home_place_entity=home_place_entity,
        work_place=work_place,
        mara=mara,
        dex=dex,
        event=event,
    )


@pytest.fixture
def seeded() -> Iterator[Seeded]:
    """Own one seeded, TEST-pinned custody clone."""

    with disposable_slot_database("qa640_783s1a") as dbname:
        yield _seed(dbname)


def _change(
    entity_id: int,
    anchor_type: str,
    mobility_policy: Optional[str] = None,
    *,
    place_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    schedule: Optional[dict[str, Any]] = None,
    clear: bool = False,
) -> RoutineAnchorChange:
    return RoutineAnchorChange(
        character_entity_id=entity_id,
        anchor_type=anchor_type,
        mobility_policy=mobility_policy,
        place_id=place_id,
        zone_id=zone_id,
        schedule=None if schedule is None else RoutineSchedule(**schedule),
        clear=clear,
    )


def _apply_sync(
    dbname: str, changes: list[RoutineAnchorChange], **kwargs: Any
) -> list[int]:
    """Apply through the psycopg2 twin in one transaction; commit on success."""

    with closing(connect(dbname)) as conn:
        with conn, conn.cursor() as cur:
            return apply_routine_anchor_changes_sync(cur, changes, **kwargs)


async def _apply_async_in_transaction(
    dbname: str, changes: list[RoutineAnchorChange], **kwargs: Any
) -> list[int]:
    conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
    try:
        async with conn.transaction():
            return await apply_routine_anchor_changes_async(conn, changes, **kwargs)
    finally:
        await conn.close()


def _apply_async(
    dbname: str, changes: list[RoutineAnchorChange], **kwargs: Any
) -> list[int]:
    """Apply through the asyncpg twin inside ``conn.transaction()``."""

    return asyncio.run(_apply_async_in_transaction(dbname, changes, **kwargs))


TWINS: dict[str, Callable[..., list[int]]] = {
    "sync": _apply_sync,
    "async": _apply_async,
}


def _fetch(dbname: str, query: str, params: tuple[Any, ...] = ()) -> list[dict]:
    with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def _anchors(dbname: str) -> list[dict]:
    return _fetch(
        dbname,
        """
        SELECT id, character_entity_id, anchor_type::text AS anchor_type,
               mobility_policy::text AS mobility_policy, place_id, zone_id,
               schedule, schedule IS NULL AS schedule_is_null, source,
               last_log_id, created_at, updated_at
        FROM character_routine_anchors
        ORDER BY character_entity_id, anchor_type
        """,
    )


def _ledger(dbname: str) -> list[dict]:
    return _fetch(
        dbname,
        """
        SELECT id, character_entity_id, anchor_type::text AS anchor_type,
               operation, writer_kind::text AS writer_kind, source_chunk_id,
               chunk_sequence, source_event_id, world_time, before_image,
               after_image, recorded_at
        FROM character_routine_anchor_log
        ORDER BY id
        """,
    )


def _counts(dbname: str) -> tuple[int, int]:
    row = _fetch(
        dbname,
        "SELECT (SELECT count(*) FROM character_routine_anchors) AS anchors, "
        "(SELECT count(*) FROM character_routine_anchor_log) AS ledger",
    )[0]
    return int(row["anchors"]), int(row["ledger"])


def _world_time(dbname: str, chunk_id: int) -> datetime:
    return _fetch(
        dbname,
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
        (chunk_id,),
    )[0]["world_time"]


def test_enum_labels_match_constants(seeded: Seeded) -> None:
    """The three enum label lists equal the module constants, in order."""

    labels = {
        row["typname"]: tuple(row["labels"])
        for row in _fetch(
            seeded.dbname,
            """
            SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)
                   AS labels
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            WHERE t.typname IN (
                'orrery_routine_anchor_type',
                'orrery_routine_mobility_policy',
                'orrery_routine_anchor_writer'
            )
            GROUP BY t.typname
            """,
        )
    }
    assert labels == {
        "orrery_routine_anchor_type": ROUTINE_ANCHOR_TYPES,
        "orrery_routine_mobility_policy": ROUTINE_MOBILITY_POLICIES,
        "orrery_routine_anchor_writer": ROUTINE_ANCHOR_WRITERS,
    }


WEEKDAY_EVENINGS = {"weekdays": [0, 1, 2, 3, 4], "start": "18:00", "end": "23:00"}
OFFICE_HOURS = {"start": "09:00", "end": "17:00"}

SCENARIOS: dict[str, Callable[[Seeded], list[RoutineAnchorChange]]] = {
    "fixed_place_home_weekdays": lambda s: [
        _change(
            s.mara,
            "home",
            "fixed_place",
            place_id=s.home_place,
            schedule=WEEKDAY_EVENINGS,
        )
    ],
    "zone_resolved_work": lambda s: [
        _change(s.mara, "work", "zone_resolved", zone_id=s.zone, schedule=OFFICE_HOURS)
    ],
    "works_from_home_with_fixed_home": lambda s: [
        _change(s.mara, "home", "fixed_place", place_id=s.home_place),
        _change(s.mara, "work", "works_from_home", schedule=OFFICE_HOURS),
    ],
    "nomadic_work": lambda s: [
        _change(s.dex, "work", "nomadic", schedule={"start": "06:00", "end": "14:00"})
    ],
    "explicit_none_home": lambda s: [_change(s.dex, "home", "none")],
    "overnight": lambda s: [
        _change(
            s.dex,
            "work",
            "fixed_place",
            place_id=s.work_place,
            schedule={"start": "22:00", "end": "06:00"},
        )
    ],
    "partial_weekend": lambda s: [
        _change(
            s.dex,
            "work",
            "fixed_place",
            place_id=s.work_place,
            schedule={"weekdays": [5, 6]},
        )
    ],
    "always": lambda s: [
        _change(
            s.mara,
            "home",
            "fixed_place",
            place_id=s.home_place,
            schedule={"always": True},
        )
    ],
    "unknown": lambda s: [_change(s.dex, "work", "fixed_place", place_id=s.work_place)],
}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_scenario_writes_row_and_ledger(seeded: Seeded, scenario: str) -> None:
    """After commit, every anchor row and its ledger row agree."""

    changes = SCENARIOS[scenario](seeded)
    log_ids = _apply_sync(
        seeded.dbname, changes, writer_kind=WRITER, source_chunk_id=seeded.chunk_1
    )

    anchors = {
        (row["character_entity_id"], row["anchor_type"]): row
        for row in _anchors(seeded.dbname)
    }
    ledger = {row["id"]: row for row in _ledger(seeded.dbname)}
    assert len(log_ids) == len(changes) == len(ledger) == len(anchors)
    world_time = _world_time(seeded.dbname, seeded.chunk_1)
    for sequence, (change, log_id) in enumerate(zip(changes, log_ids), start=1):
        row = anchors[(change.character_entity_id, change.anchor_type)]
        entry = ledger[log_id]
        stored_schedule = None if change.schedule is None else change.schedule.as_json()
        assert row["mobility_policy"] == change.mobility_policy
        assert (row["place_id"], row["zone_id"]) == (change.place_id, change.zone_id)
        assert row["schedule"] == stored_schedule
        assert row["schedule_is_null"] is (change.schedule is None)
        assert row["source"] == WRITER
        assert row["last_log_id"] == log_id
        assert entry["character_entity_id"] == change.character_entity_id
        assert entry["anchor_type"] == change.anchor_type
        assert entry["operation"] == "upsert"
        assert entry["writer_kind"] == WRITER
        assert entry["source_chunk_id"] == seeded.chunk_1
        assert entry["chunk_sequence"] == sequence
        assert entry["source_event_id"] is None
        assert entry["world_time"] == world_time
        assert entry["before_image"] is None
        assert entry["after_image"] == {
            "mobility_policy": row["mobility_policy"],
            "place_id": row["place_id"],
            "zone_id": row["zone_id"],
            "schedule": row["schedule"],
        }


def test_revise_and_clear(seeded: Seeded) -> None:
    """A revision and a clear keep the full history and the chunk sequence."""

    db = seeded.dbname
    [first_id] = _apply_sync(
        db,
        [
            _change(
                seeded.mara,
                "home",
                "fixed_place",
                place_id=seeded.home_place,
                schedule={"always": True},
            )
        ],
        writer_kind=WRITER,
        source_chunk_id=seeded.chunk_1,
    )
    [revision_id] = _apply_sync(
        db,
        [
            _change(
                seeded.mara,
                "home",
                "zone_resolved",
                zone_id=seeded.zone,
                schedule={"weekdays": [5, 6]},
            )
        ],
        writer_kind="relocation_arrival",
        source_chunk_id=seeded.chunk_2,
        source_event_id=seeded.event,
    )
    [revised] = _anchors(db)
    assert (revised["mobility_policy"], revised["zone_id"], revised["place_id"]) == (
        "zone_resolved",
        seeded.zone,
        None,
    )
    assert (revised["source"], revised["last_log_id"]) == (
        "relocation_arrival",
        revision_id,
    )
    [clear_id] = _apply_sync(
        db,
        [_change(seeded.mara, "home", clear=True)],
        writer_kind=WRITER,
        source_chunk_id=seeded.chunk_2,
    )

    assert _anchors(db) == []
    first, revision, clear = _ledger(db)
    assert [first["id"], revision["id"], clear["id"]] == [
        first_id,
        revision_id,
        clear_id,
    ]
    assert (first["source_chunk_id"], first["chunk_sequence"]) == (seeded.chunk_1, 1)
    assert [
        (row["source_chunk_id"], row["chunk_sequence"]) for row in (revision, clear)
    ] == [(seeded.chunk_2, 1), (seeded.chunk_2, 2)]
    assert revision["before_image"] == first["after_image"]
    assert revision["after_image"] == {
        "mobility_policy": "zone_resolved",
        "place_id": None,
        "zone_id": seeded.zone,
        "schedule": {"weekdays": [5, 6]},
    }
    assert (revision["source_event_id"], revision["writer_kind"]) == (
        seeded.event,
        "relocation_arrival",
    )
    assert clear["operation"] == "clear"
    assert clear["before_image"] == revision["after_image"]
    assert clear["after_image"] is None
    assert clear["source_event_id"] is None
    assert (
        clear["world_time"] == revision["world_time"] == _world_time(db, seeded.chunk_2)
    )
    assert first["world_time"] == _world_time(db, seeded.chunk_1)


@dataclass(frozen=True)
class RefusalCase:
    """One refused batch, with an optional committed setup batch first."""

    changes: Callable[[Seeded], list[RoutineAnchorChange]]
    message: str
    setup: Optional[Callable[[Seeded], list[RoutineAnchorChange]]] = None
    writer_kind: str = WRITER
    chunk: Callable[[Seeded], int] = lambda s: s.chunk_1


def _home_and_remote_work(s: Seeded) -> list[RoutineAnchorChange]:
    return [
        _change(s.mara, "home", "fixed_place", place_id=s.home_place),
        _change(s.mara, "work", "works_from_home"),
    ]


REFUSALS: dict[str, RefusalCase] = {
    "missing_place": RefusalCase(
        lambda s: [
            _change(s.mara, "home", "fixed_place", place_id=s.home_place + 100_000)
        ],
        "places.id=.* does not exist",
    ),
    "missing_zone": RefusalCase(
        lambda s: [_change(s.mara, "work", "zone_resolved", zone_id=s.zone + 100_000)],
        "zones.id=.* does not exist",
    ),
    "place_entity_as_character": RefusalCase(
        lambda s: [_change(s.home_place_entity, "home", "none")],
        "the entity is a place, not a character",
    ),
    "missing_entity": RefusalCase(
        lambda s: [_change(s.dex + 100_000, "home", "none")],
        "the entity does not exist",
    ),
    "chunk_without_metadata": RefusalCase(
        lambda s: [_change(s.mara, "home", "none")],
        "requires chunk_metadata.world_time for source_chunk_id=",
        chunk=lambda s: s.bare_chunk,
    ),
    "works_from_home_without_home": RefusalCase(
        lambda s: [_change(s.mara, "work", "works_from_home")],
        "a works_from_home work anchor needs a home anchor",
    ),
    "clear_home_under_works_from_home": RefusalCase(
        lambda s: [_change(s.mara, "home", clear=True)],
        "a works_from_home work anchor needs a home anchor",
        setup=_home_and_remote_work,
    ),
    "duplicate_pair": RefusalCase(
        lambda s: [_change(s.mara, "home", "none"), _change(s.mara, "home", "none")],
        "the batch already changes this anchor at change 0",
    ),
    "unknown_writer": RefusalCase(
        lambda s: [_change(s.mara, "home", "none")],
        "refuses writer_kind='gaia_freestyle'",
        writer_kind="gaia_freestyle",
    ),
    "clear_of_absent_anchor": RefusalCase(
        lambda s: [_change(s.mara, "work", clear=True)],
        "a clear needs an existing anchor",
    ),
}


@pytest.mark.parametrize("twin", list(TWINS))
@pytest.mark.parametrize("case", list(REFUSALS))
def test_refusals_change_nothing(seeded: Seeded, case: str, twin: str) -> None:
    """Each refusal raises in both twins and the rollback leaves both tables."""

    refusal = REFUSALS[case]
    if refusal.setup is not None:
        _apply_sync(
            seeded.dbname,
            refusal.setup(seeded),
            writer_kind=WRITER,
            source_chunk_id=seeded.chunk_1,
        )
    before = _counts(seeded.dbname)
    before_rows = (_anchors(seeded.dbname), _ledger(seeded.dbname))
    with pytest.raises(RoutineAnchorCustodyError, match=refusal.message):
        TWINS[twin](
            seeded.dbname,
            refusal.changes(seeded),
            writer_kind=refusal.writer_kind,
            source_chunk_id=refusal.chunk(seeded),
        )
    assert _counts(seeded.dbname) == before
    assert (_anchors(seeded.dbname), _ledger(seeded.dbname)) == before_rows


def _agreement_batches(s: Seeded) -> list[tuple[list[RoutineAnchorChange], dict]]:
    return [
        (
            [
                *_home_and_remote_work(s),
                _change(
                    s.dex,
                    "work",
                    "zone_resolved",
                    zone_id=s.zone,
                    schedule={"weekdays": [2, 0], "start": "22:00", "end": "06:00"},
                ),
            ],
            {"writer_kind": "retrograde_expansion", "source_chunk_id": s.chunk_1},
        ),
        (
            [
                _change(s.mara, "work", clear=True),
                _change(s.dex, "work", "nomadic"),
            ],
            {
                "writer_kind": WRITER,
                "source_chunk_id": s.chunk_2,
                "source_event_id": s.event,
            },
        ),
        (
            [
                _change(
                    s.mara,
                    "home",
                    "fixed_place",
                    place_id=s.home_place,
                    schedule={"always": True},
                ),
                _change(s.dex, "home", "none"),
            ],
            {"writer_kind": "retrograde_maturation", "source_chunk_id": s.chunk_2},
        ),
    ]


def _without_volatile(rows: list[dict]) -> list[dict]:
    return [
        {
            key: value
            for key, value in row.items()
            if key not in {"id", "recorded_at", "updated_at", "created_at"}
        }
        for row in rows
    ]


def test_sync_and_async_agree(seeded: Seeded) -> None:
    """One change sequence through each twin gives equal rows and ledgers."""

    with disposable_slot_database("qa640_783s1a") as other_db:
        other = _seed(other_db)
        assert (other.mara, other.dex, other.event, other.chunk_2) == (
            seeded.mara,
            seeded.dex,
            seeded.event,
            seeded.chunk_2,
        )
        sync_ids = [
            _apply_sync(seeded.dbname, changes, **kwargs)
            for changes, kwargs in _agreement_batches(seeded)
        ]
        async_ids = [
            _apply_async(other.dbname, changes, **kwargs)
            for changes, kwargs in _agreement_batches(other)
        ]
        assert sync_ids == async_ids
        assert _without_volatile(_anchors(seeded.dbname)) == _without_volatile(
            _anchors(other.dbname)
        )
        assert _without_volatile(_ledger(seeded.dbname)) == _without_volatile(
            _ledger(other.dbname)
        )
        assert len(_ledger(seeded.dbname)) == 7

    change = [_change(seeded.mara, "work", "nomadic")]
    with closing(connect(seeded.dbname)) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            with pytest.raises(RoutineAnchorCustodyError, match="autocommit"):
                apply_routine_anchor_changes_sync(
                    cur, change, writer_kind=WRITER, source_chunk_id=seeded.chunk_1
                )

    async def outside_transaction() -> None:
        conn = await asyncpg.connect(**asyncpg_kwargs(seeded.dbname))
        try:
            with pytest.raises(RoutineAnchorCustodyError, match="not in a transaction"):
                await apply_routine_anchor_changes_async(
                    conn, change, writer_kind=WRITER, source_chunk_id=seeded.chunk_1
                )
        finally:
            await conn.close()

    before = _counts(seeded.dbname)
    asyncio.run(outside_transaction())
    assert _counts(seeded.dbname) == before


def test_place_deletion_still_fails_loudly(seeded: Seeded) -> None:
    """Deleting a custody-written fixed_place anchor's place fails on the CHECK."""

    _apply_sync(
        seeded.dbname,
        [_change(seeded.mara, "home", "fixed_place", place_id=seeded.home_place)],
        writer_kind=WRITER,
        source_chunk_id=seeded.chunk_1,
    )
    ledger = _ledger(seeded.dbname)
    with closing(connect(seeded.dbname)) as conn:
        with pytest.raises(psycopg2.errors.CheckViolation) as caught:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM places WHERE id = %s", (seeded.home_place,))
    assert caught.value.diag.constraint_name == "character_routine_anchors_check"
    assert _ledger(seeded.dbname) == ledger
    [anchor] = _anchors(seeded.dbname)
    assert anchor["place_id"] == seeded.home_place


def test_schedule_column_is_nullable(seeded: Seeded) -> None:
    """Migration 145 makes schedule nullable with no default."""

    [column] = _fetch(
        seeded.dbname,
        """
        SELECT is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'character_routine_anchors'
          AND column_name = 'schedule'
        """,
    )
    assert column == {"is_nullable": "YES", "column_default": None}


def test_identical_upsert_still_writes_a_ledger_row(seeded: Seeded) -> None:
    """Re-asserting the same anchor records a second ledger row."""

    change = [
        _change(
            seeded.dex,
            "work",
            "fixed_place",
            place_id=seeded.work_place,
            schedule={"start": "09:00", "end": "17:00"},
        )
    ]
    [first_id] = _apply_sync(
        seeded.dbname, change, writer_kind=WRITER, source_chunk_id=seeded.chunk_1
    )
    [second_id] = _apply_sync(
        seeded.dbname, change, writer_kind=WRITER, source_chunk_id=seeded.chunk_2
    )
    first, second = _ledger(seeded.dbname)
    assert (first["id"], second["id"]) == (first_id, second_id)
    assert second["before_image"] == second["after_image"] == first["after_image"]
    [anchor] = _anchors(seeded.dbname)
    assert anchor["last_log_id"] == second_id
