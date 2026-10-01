"""Real resolver, commit, and migration proofs for exact event occurrence time."""

from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import asyncpg  # type: ignore[import-untyped]
import pytest

from nexus.agents.orrery.events import (
    OrreryWorldClockUnavailableError,
    coerce_signal_detection,
    commit_orrery_tick_async,
    commit_orrery_tick_sync,
)
from nexus.config import load_settings
from nexus.config.settings_models import OrrerySettings
from scripts import migrate
from tests.pg_fixtures import (
    _resolve_turn_orrery_proposal,
    asyncpg_kwargs,
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_accepted_turn,
    seed_character,
    seed_committed_chunk,
    seed_entity_tag,
    seed_place,
    seed_protagonist,
    seed_relationship,
    seed_story_clock,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres
BASE = datetime(2100, 1, 1, tzinfo=timezone.utc)
OLD_COMMENT = (
    "Exact diegetic occurrence time for system events whose schedule may precede "
    "their committing chunk; NULL legacy/resolver rows inherit the tick chunk "
    "world time."
)
COMMENT = (
    "Exact diegetic occurrence time, separate from database recording time. Resolver "
    "deeds and their detected signals use the tick chunk's canonical "
    "chunk_metadata.world_time unless the caller supplies an explicit instant. "
    "System events may retain a scheduled instant before their committing chunk. "
    "tick_chunk_id records ordering and replay, not occurrence time. Migration 142 "
    "fills only legacy NULL non-Retrograde rows from their tick chunk's canonical "
    "clock. Undated Retrograde history remains NULL pending its own chronology "
    "contract."
)


def orrery_settings() -> OrrerySettings:
    """Require and return the shipped resolver policy without changing it."""
    settings = load_settings().orrery
    assert settings is not None
    return settings


@pytest.fixture
def story(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, int, int, int]]:
    """Seed an eligible shipped vengeance branch and a detected accepting tick."""
    with disposable_slot_database("qa640_778s2a_time") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=3, dbname=dbname)
        seed_zone(
            dbname,
            name="Event Time Zone",
            min_longitude=-75,
            min_latitude=39,
            max_longitude=-72,
            max_latitude=42,
        )
        player_place, _ = seed_place(dbname, name="Player room")
        npc_place, _ = seed_place(dbname, name="Offscreen room")
        target_place, _ = seed_place(dbname, name="Quarry room")
        seed_protagonist(dbname, current_location=player_place)
        tick = seed_story_clock(dbname, world_time=BASE)
        actor_char, actor = seed_character(
            dbname, name="Avenger", current_location=npc_place
        )
        target_char, target = seed_character(
            dbname, name="Quarry", current_location=target_place
        )
        seed_entity_tag(dbname, entity_id=actor, tag="grudge_active")
        seed_entity_tag(dbname, entity_id=actor, tag="violent_history")
        seed_relationship(
            dbname,
            subject_character_id=actor_char,
            object_character_id=target_char,
            relationship_type="enemy",
            emotional_valence="-4|hostile",
        )
        policy = coerce_signal_detection(orrery_settings().ecology)
        # No events are committed while advancing: the real proposal stays eligible.
        for _ in range(100):
            resolved = proposal(dbname, tick)
            if (
                any(
                    draft["event_type"] == "hunt_declared"
                    and draft["bindings"] == {"actor": actor, "target": target}
                    for draft in resolved["resolutions"]
                )
                and policy.outcome(
                    template_id="extract_vengeance",
                    actor_entity_id=actor,
                    target_entity_id=target,
                    tick_chunk_id=tick + 1,
                    event_type="threat_issued",
                )["detected"]
            ):
                break
            tick = seed_committed_chunk(
                dbname, raw_text="Quiet passage.", scene=tick + 1
            )
        else:
            raise AssertionError("No shipped signal-bearing proposal and detected tick")
        yield dbname, tick, actor, target


def proposal(dbname: str, tick: int) -> dict[str, Any]:
    """Resolve the production proposal without substituting or patching drafts."""
    return _resolve_turn_orrery_proposal(
        dbname,
        anchor_chunk_id=tick,
        orrery_settings=orrery_settings().model_dump(by_alias=True),
    )


def event_rows(dbname: str) -> dict[int, dict[str, Any]]:
    """Snapshot complete rows, including provenance and payloads."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, to_jsonb(we) FROM world_events we ORDER BY id")
        return dict(cur.fetchall())


def migration_state(dbname: str) -> tuple[Any, Any, Any]:
    """Read all events, the occurrence comment, and the migration stamp."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT col_description('public.world_events'::regclass, attnum) "
            "FROM pg_attribute WHERE attrelid='public.world_events'::regclass "
            "AND attname='world_time'"
        )
        comment = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM schema_migrations WHERE version='142'")
        stamps = cur.fetchone()[0]
    return event_rows(dbname), comment, stamps


def pending_142(cur: Any, *, restore_comment: bool = False) -> None:
    """Make only 142 pending; restore its genuine pre-migration comment if needed."""
    cur.execute("DELETE FROM schema_migrations WHERE version='142'")
    assert cur.rowcount == 1
    if restore_comment:
        cur.execute(
            "COMMENT ON COLUMN public.world_events.world_time IS %s", (OLD_COMMENT,)
        )


def test_accepted_turn_stamps_resolver_and_signal_occurrence(
    story: tuple[str, int, int, int],
) -> None:
    """Acceptance stages its own production proposal and stamps both real emissions."""
    dbname, _, actor, target = story
    tick = seed_accepted_turn(
        dbname,
        slot=3,
        user_text="Wait quietly.",
        storyteller_text="The player waits while distant business continues.",
    )
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT we.event_type, we.world_time, cm.world_time, we.payload "
            "FROM world_events we JOIN chunk_metadata cm "
            "ON cm.chunk_id=we.tick_chunk_id "
            "WHERE we.source='resolver' AND we.tick_chunk_id=%s ORDER BY we.id",
            (tick,),
        )
        rows = cur.fetchall()
    assert rows and all(row[1] == row[2] for row in rows)
    deed = next(row for row in rows if row[0] == "hunt_declared")
    signal = next(row for row in rows if row[0] == "threat_issued")
    detection = deed[3]["signal_detection"]
    assert detection == coerce_signal_detection(orrery_settings().ecology).outcome(
        template_id="extract_vengeance",
        actor_entity_id=actor,
        target_entity_id=target,
        tick_chunk_id=tick,
        event_type="threat_issued",
    )
    assert (
        detection["threshold"]
        == orrery_settings().ecology.signal_detection["threat_issued"]
    )
    assert detection["roll"] < detection["threshold"]
    assert signal[3]["signal_detection"] == detection


@pytest.mark.parametrize("twin", ["sync", "async"])
@pytest.mark.parametrize("override", [False, True])
def test_sync_async_occurrence_time_parity(
    story: tuple[str, int, int, int], twin: str, override: bool
) -> None:
    """Both real commit entry points preserve bindings, tick and detection payload."""
    dbname, anchor, actor, target = story
    staged = proposal(dbname, anchor)
    tick = seed_committed_chunk(
        dbname, raw_text="Accept the next beat.", scene=anchor + 1
    )
    explicit = BASE - timedelta(hours=3) if override else None
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT world_time FROM chunk_metadata WHERE chunk_id=%s", (tick,))
        expected = explicit or cur.fetchone()[0]
    if twin == "sync":
        with closing(connect(dbname)) as conn, conn:
            result = commit_orrery_tick_sync(
                conn,
                staged,
                tick_chunk_id=tick,
                occurrence_time=explicit,
                ecology_settings=orrery_settings().ecology,
            )
            duplicate = commit_orrery_tick_sync(
                conn,
                staged,
                tick_chunk_id=tick,
                occurrence_time=explicit,
                ecology_settings=orrery_settings().ecology,
            )
    else:

        async def run() -> tuple[Any, Any]:
            conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
            try:
                async with conn.transaction():
                    result = await commit_orrery_tick_async(
                        conn,
                        staged,
                        tick_chunk_id=tick,
                        occurrence_time=explicit,
                        ecology_settings=orrery_settings().ecology,
                    )
                    duplicate = await commit_orrery_tick_async(
                        conn,
                        staged,
                        tick_chunk_id=tick,
                        occurrence_time=explicit,
                        ecology_settings=orrery_settings().ecology,
                    )
                    return result, duplicate
            finally:
                await conn.close()

        result, duplicate = asyncio.run(run())
    assert result.event_count > 0
    assert duplicate.event_count == 0 and duplicate.skipped_existing_count > 0
    rows = list(event_rows(dbname).values())
    assert rows and all(
        datetime.fromisoformat(row["world_time"]) == expected
        for row in rows
        if row["source"] == "resolver"
    )
    deed = next(row for row in rows if row["event_type"] == "hunt_declared")
    signal = next(row for row in rows if row["event_type"] == "threat_issued")
    expected_detection = coerce_signal_detection(orrery_settings().ecology).outcome(
        template_id="extract_vengeance",
        actor_entity_id=actor,
        target_entity_id=target,
        tick_chunk_id=tick,
        event_type="threat_issued",
    )
    for row in (deed, signal):
        assert row["tick_chunk_id"] == tick
        assert row["actor_entity_id"] == actor and row["target_entity_id"] == target
        assert row["payload"]["signal_detection"] == expected_detection
    assert signal["payload"]["signal_of"] == deed["event_type"]


@pytest.mark.parametrize("twin", ["sync", "async"])
@pytest.mark.parametrize("missing", [True, False])
def test_missing_tick_clock_raises_without_event_rows(
    story: tuple[str, int, int, int], twin: str, missing: bool
) -> None:
    """A valid other chunk cannot supply the missing event-local clock."""
    dbname, anchor, _, _ = story
    staged = proposal(dbname, anchor)
    tick = seed_committed_chunk(
        dbname, raw_text="Clockless accepting beat.", scene=anchor + 1
    )
    sql = (
        "DELETE FROM chunk_metadata WHERE chunk_id=%s"
        if missing
        else "UPDATE chunk_metadata SET world_time=NULL WHERE chunk_id=%s"
    )
    before = event_rows(dbname)
    if twin == "sync":
        with closing(connect(dbname)) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tick,))
                cur.execute(
                    "SELECT world_time FROM chunk_metadata WHERE chunk_id=%s", (anchor,)
                )
                assert cur.fetchone()[0] is not None
            with pytest.raises(
                OrreryWorldClockUnavailableError, match=f"tick chunk {tick}"
            ):
                commit_orrery_tick_sync(conn, staged, tick_chunk_id=tick)
            conn.rollback()
    else:

        async def run() -> None:
            conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
            tx = conn.transaction()
            await tx.start()
            try:
                await conn.execute(sql.replace("%s", "$1"), tick)
                assert (
                    await conn.fetchval(
                        "SELECT world_time FROM chunk_metadata WHERE chunk_id=$1",
                        anchor,
                    )
                    is not None
                )
                with pytest.raises(
                    OrreryWorldClockUnavailableError, match=f"tick chunk {tick}"
                ):
                    await commit_orrery_tick_async(conn, staged, tick_chunk_id=tick)
            finally:
                await tx.rollback()
                await conn.close()

        asyncio.run(run())
    assert event_rows(dbname) == before


@pytest.mark.parametrize("twin", ["sync", "async"])
def test_naive_occurrence_time_is_rejected(
    story: tuple[str, int, int, int], twin: str
) -> None:
    """The connection's UTC policy cannot invent an instant for a naive caller."""
    dbname, tick, _, _ = story
    staged = proposal(dbname, tick)
    before = event_rows(dbname)
    if twin == "sync":
        with closing(connect(dbname)) as conn:
            with pytest.raises(ValueError, match="timezone-aware"):
                commit_orrery_tick_sync(
                    conn,
                    staged,
                    tick_chunk_id=tick,
                    occurrence_time=BASE.replace(tzinfo=None),
                )
            conn.rollback()
    else:

        async def run() -> None:
            conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
            try:
                with pytest.raises(ValueError, match="timezone-aware"):
                    await commit_orrery_tick_async(
                        conn,
                        staged,
                        tick_chunk_id=tick,
                        occurrence_time=BASE.replace(tzinfo=None),
                    )
            finally:
                await conn.close()

        asyncio.run(run())
    assert event_rows(dbname) == before


def seed_event(
    cur: Any, tick: int, source: str, instant: datetime | None = None
) -> int:
    """Insert a legacy row on the clone, returning its actual generated id."""
    cur.execute(
        "INSERT INTO world_events (event_type, tick_chunk_id, source, world_time) "
        "VALUES ('retaliation_attempted', %s, %s, %s) RETURNING id",
        (tick, source, instant),
    )
    return int(cur.fetchone()[0])


def test_migration_142_backfills_only_eligible_null_rows(
    story: tuple[str, int, int, int],
) -> None:
    """Exact join, all non-Retrograde sources, Retrograde preservation and reruns."""
    dbname, tick, _, _ = story
    later_tick = seed_committed_chunk(
        dbname,
        raw_text="A different clock.",
        scene=tick + 1,
        time_delta=timedelta(hours=1),
    )
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        pending_142(cur)
        eligible = {
            seed_event(cur, tick, source)
            for source in ("resolver", "authored", "narrator", "apex", "bleed")
        }
        eligible.add(seed_event(cur, later_tick, "resolver"))
        seed_event(cur, tick, "retrograde")
        seed_event(cur, tick, "authored", BASE - timedelta(days=1))
        cur.execute("SELECT chunk_id, world_time FROM chunk_metadata")
        expected_clocks = dict(cur.fetchall())
        assert expected_clocks[tick] != expected_clocks[later_tick]
    before = event_rows(dbname)
    assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
    after, comment, stamps = migration_state(dbname)
    assert set(before) == set(after) and comment == COMMENT and stamps == 1
    for event_id, row in before.items():
        if event_id in eligible:
            changed = dict(after[event_id])
            assert (
                datetime.fromisoformat(changed.pop("world_time"))
                == expected_clocks[row["tick_chunk_id"]]
            )
            assert changed == {
                key: value for key, value in row.items() if key != "world_time"
            }
        else:
            assert after[event_id] == row
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        pending_142(cur)
    assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
    assert migration_state(dbname) == (after, comment, stamps)
    assert migrate.migrate_database(dbname, skip_locked=False) == (0, 0)
    assert migration_state(dbname) == (after, comment, stamps)


@pytest.mark.parametrize("missing", [True, False])
def test_migration_142_rejects_unresolved_tick_clock_atomically(
    story: tuple[str, int, int, int], missing: bool
) -> None:
    """Runner failure leaves all rows, the restored comment and pending stamp intact."""
    dbname, tick, _, _ = story
    unresolved = seed_committed_chunk(
        dbname, raw_text="Unresolved clock.", scene=tick + 1
    )
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        pending_142(cur, restore_comment=True)
        if missing:
            cur.execute("DELETE FROM chunk_metadata WHERE chunk_id=%s", (unresolved,))
        else:
            cur.execute(
                "UPDATE chunk_metadata SET world_time=NULL WHERE chunk_id=%s",
                (unresolved,),
            )
        seed_event(cur, tick, "resolver")
        seed_event(cur, unresolved, "resolver")
    before = migration_state(dbname)
    assert before[1:] == (OLD_COMMENT, 0)
    assert migrate.migrate_database(dbname, skip_locked=False) == (0, 1)
    assert migration_state(dbname) == before
