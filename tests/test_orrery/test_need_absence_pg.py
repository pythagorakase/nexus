"""Real roster, resolver, and tick coverage for long world-clock absences."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Iterator

import asyncpg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.events import (
    _location_class_destination_async,
    _routine_zone_destination_async,
    commit_orrery_tick_async,
    commit_orrery_tick_sync,
)
from nexus.agents.orrery.needs import effective_debt_score, load_need_tuning
from nexus.agents.orrery.resolver import compose_actor_bindings, resolve_dry_run
from nexus.agents.orrery.substrate import Slot
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.presence.roster import read_roster
from tests.pg_fixtures import (
    asyncpg_kwargs,
    connect,
    disposable_slot_database,
    seed_protagonist,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def absence_db() -> Iterator[str]:
    """Own a schema-and-vocabulary clone; never mutate a player save."""
    with disposable_slot_database("qa640_need_absence") as dbname:
        yield dbname


def _chunk(dbname: str, at: datetime, character_id: int | None = None) -> int:
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
            "VALUES ('Absence probe', 'Absence probe') RETURNING id"
        )
        chunk_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO chunk_metadata (chunk_id, world_layer) VALUES (%s, 'primary')",
            (chunk_id,),
        )
        cur.execute(
            "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
            (at, chunk_id),
        )
        if character_id is not None:
            cur.execute(
                "INSERT INTO chunk_character_references "
                "(chunk_id, character_id, reference) VALUES (%s, %s, 'present')",
                (chunk_id, character_id),
            )
    return chunk_id


@pytest.mark.parametrize("absence_days", [30, 310122])
@pytest.mark.parametrize("async_writer", [False, True])
def test_long_absence_reappearance_and_offscreen_need_tick(
    absence_db: str, absence_days: int, async_writer: bool
) -> None:
    """A returning character has bounded pressure and can fulfill needs offscreen."""
    base = datetime(1347, 6, 11, 3, 21, tzinfo=timezone.utc)
    character_id, entity_id = seed_protagonist(
        absence_db, base_timestamp=base.isoformat()
    )
    _chunk(absence_db, base, character_id)
    absent_at = base + timedelta(days=absence_days)
    absent = _chunk(absence_db, absent_at)
    engine = create_engine(sqlalchemy_url(absence_db))
    try:
        with Session(engine) as session:
            old_ids = list(
                session.execute(
                    text(
                        "SELECT DISTINCT cer.entity_id FROM chunk_entity_references_v cer "
                        "JOIN entities e ON e.id = cer.entity_id "
                        "WHERE e.kind = 'character' AND e.is_active = true "
                        "AND cer.reference_type IS DISTINCT FROM 'present' "
                        "AND cer.chunk_id BETWEEN 0 AND :anchor"
                    ),
                    {"anchor": absent},
                ).scalars()
            )
            bindings = compose_actor_bindings(
                session, anchor_chunk_id=absent, window_chunks=30
            )
            assert old_ids == []
            assert bindings == ({Slot.ACTOR: entity_id},)
            print(f"historical selection: before={old_ids}, after={bindings}")
        with connect(absence_db) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT debt_score, last_evaluated_at, last_fulfilled_at "
                "FROM character_need_states WHERE character_entity_id = %s "
                "AND need_type = 'sleep'",
                (entity_id,),
            )
            stored, evaluated, fulfilled = cur.fetchone()
            assert stored == 0 and evaluated == base and fulfilled is None
            print(f"stored debt={stored}, evaluated={evaluated}, fulfilled={fulfilled}")
        returning = _chunk(absence_db, absent_at, character_id)
        with Session(engine) as session:
            assert read_roster(session, returning).present_entity_ids == {entity_id}
            assert (
                compose_actor_bindings(
                    session, anchor_chunk_id=returning, window_chunks=30
                )
                == ()
            )
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=returning,
                window_chunks=30,
                epistemics_settings={"enabled": False},
            )
            assert any(
                p.template_id == "sleep_need_pressure" for p in proposal.scene_pressures
            )
        with connect(absence_db) as conn:
            commit_orrery_tick_sync(conn, proposal, tick_chunk_id=returning, slot=4)
        departing = _chunk(absence_db, absent_at + timedelta(hours=1))
        with Session(engine) as session:
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=departing,
                window_chunks=30,
                epistemics_settings={"enabled": False},
            )
        assert any(d.template_id == "sleep" for d in proposal.resolutions)
        if async_writer:

            async def commit_async() -> None:
                conn = await asyncpg.connect(**asyncpg_kwargs(absence_db))
                try:
                    async with conn.transaction():
                        await commit_orrery_tick_async(
                            conn, proposal, tick_chunk_id=departing, slot=4
                        )
                finally:
                    await conn.close()

            asyncio.run(commit_async())
        with connect(absence_db) as conn:
            if not async_writer:
                commit_orrery_tick_sync(conn, proposal, tick_chunk_id=departing, slot=4)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT debt_score, last_evaluated_at, last_fulfilled_at, "
                    "last_evaluated_chunk_id, metadata FROM character_need_states "
                    "WHERE character_entity_id = %s AND need_type = 'sleep'",
                    (entity_id,),
                )
                debt, evaluated, fulfilled, source, metadata = cur.fetchone()
        print(
            f"anchor before={base.isoformat()}, after={evaluated.isoformat()}, debt={debt}"
        )
        assert 0 <= debt <= load_need_tuning().severity_thresholds["sleep"]["critical"]
        assert (
            effective_debt_score(
                "sleep",
                float(stored),
                last_evaluated_at=base,
                current_world_time=absent_at,
                tuning=load_need_tuning(),
            )
            == load_need_tuning().accrual_debt_caps["sleep"]
        )
        assert evaluated == fulfilled == absent_at + timedelta(hours=1)
        assert source == departing
        assert metadata["last_fulfillment"]["type"] == "sleep"
    finally:
        engine.dispose()


@pytest.mark.parametrize("clock", [None, "before_expiry", "at_expiry"])
def test_async_need_destination_tag_expiry(absence_db: str, clock: str | None) -> None:
    """Sibling destination queries type nullable clocks and honor tag expiry."""
    expiry = datetime(2100, 1, 2, tzinfo=timezone.utc)
    world_time = (
        None
        if clock is None
        else expiry - timedelta(hours=1) if clock == "before_expiry" else expiry
    )
    with connect(absence_db) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO layers DEFAULT VALUES RETURNING id")
        layer_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO zones (name, layer) VALUES ('Need destinations', %s) "
            "RETURNING id",
            (layer_id,),
        )
        zone_id = cur.fetchone()[0]
        place_ids = []
        for name in ("Origin", "Dwelling"):
            cur.execute(
                "INSERT INTO places (name, type, zone) "
                "VALUES (%s, 'fixed_location', %s) RETURNING id, entity_id",
                (name, zone_id),
            )
            place_id, entity_id = cur.fetchone()
            place_ids.append(place_id)
        cur.execute(
            "INSERT INTO entity_tags "
            "(entity_id, tag_id, source_kind, expires_at_world_time) "
            "SELECT %s, id, 'template', %s FROM tags WHERE tag = 'dwelling'",
            (entity_id, expiry),
        )
        assert cur.rowcount == 1

    async def resolve_destinations() -> None:
        conn = await asyncpg.connect(**asyncpg_kwargs(absence_db))
        try:
            active = clock != "at_expiry"
            assert await _routine_zone_destination_async(
                conn,
                zone_id=zone_id,
                anchor_type="home",
                current_world_time=world_time,
            ) == (place_ids[1] if active else place_ids[0])
            assert await _location_class_destination_async(
                conn,
                origin_place_id=place_ids[0],
                location_classes=("dwelling",),
                current_world_time=world_time,
            ) == (place_ids[1] if active else None)
        finally:
            await conn.close()

    asyncio.run(resolve_destinations())
