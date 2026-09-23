"""Real writer and consumer regressions on a migrated disposable corpus clone."""

from decimal import Decimal
from typing import Any

import asyncpg
import pytest
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.logon.apex_schema import StateUpdates
from nexus.agents.orrery.drift import (
    DriftEvent,
    ProjectMilestone,
    _apply_plan_async,
    _apply_plan_sync,
    plan_relationship_drift,
)
from nexus.agents.orrery.resolver import _load_recent_events
from nexus.api.commit_handler import apply_state_updates
from nexus.api.commit_handler_sync import apply_state_updates_sync
from scripts.relationship_analyst import (
    CharacterRelationshipPair,
    save_relationship_data,
)
from tests.pg_fixtures import asyncpg_kwargs, connect, sqlalchemy_url
from tests.test_orrery.test_drift_live import (
    EPISTEMICS,
    _insert_character,
    _seed_tick,
    _settings,
    drift_database,
    live_conn,
)

pytestmark = pytest.mark.requires_postgres


def test_analyst_save_stamps_insert_and_replacement(drift_database: str) -> None:
    """The SQLAlchemy save path commits both directions, including replacement."""
    with connect(drift_database) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _, first = _insert_character(cur, "analyst-first")
            _, second = _insert_character(cur, "analyst-second")
    conn.close()
    extra = {
        "schema_type": "liminal_relationship",
        "impressions": {
            "first_impression": "Quiet",
            "current_assessment": "Kind",
            "points_of_interest": [],
        },
        "interaction_history": {"contexts": ["Fixture"], "quality": "positive"},
        "potential_directions": [],
        "information_gaps": [],
        "intuition_notes": "Fixture",
    }

    def direction(source: int, target: int) -> dict[str, Any]:
        return dict(
            character1_id=source,
            character2_id=target,
            relationship_type="acquaintance",
            emotional_valence="+1|favorable",
            dynamic="Fixture",
            recent_events="Fixture",
            history="Fixture",
            extra_data=extra,
        )

    pair = CharacterRelationshipPair(
        rel_1_to_2=direction(first, second), rel_2_to_1=direction(second, first)
    )
    engine = create_engine(sqlalchemy_url(drift_database))
    try:
        assert save_relationship_data(engine, pair) == (first, second)
        assert save_relationship_data(engine, pair) == (first, second)
        with engine.connect() as connection:
            versions = connection.execute(
                text(
                    """
                SELECT operation, producer FROM relationship_versions
                WHERE relationship_table = 'character_relationships'
                  AND (old_row->>'character1_id')::bigint IN (:first, :second)
                ORDER BY id
            """
                ),
                {"first": first, "second": second},
            ).all()
            assert versions == [
                ("insert", "manual"),
                ("insert", "manual"),
                ("delete", "manual"),
                ("delete", "manual"),
                ("insert", "manual"),
                ("insert", "manual"),
            ]
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM character_relationships WHERE character1_id IN (:first, :second)"
                    ),
                    {"first": first, "second": second},
                ).scalar_one()
                == 2
            )
            assert not connection.execute(
                text("SELECT current_setting('nexus.write_producer', true)")
            ).scalar_one()
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("world_layer", ["primary", "flashback", "atemporal"])
@pytest.mark.parametrize("writer", ["sync", "async"])
async def test_gaia_milestone_retains_layer_and_resolver_filter(
    drift_database: str, live_conn: Any, world_layer: str, writer: str
) -> None:
    """Accepted non-primary crossings and claims stay outside current events."""
    with live_conn.cursor() as cur:
        tick, actor, target, first, hostile = _seed_tick(cur, world_layer=world_layer)
        cur.execute("SELECT id FROM characters WHERE entity_id = %s", (target,))
        second = cur.fetchone()["id"]
        cur.execute("DELETE FROM world_events WHERE id = %s", (hostile,))
    live_conn.commit()
    updates = StateUpdates(
        relationships=[
            {
                "character1_id": first,
                "character2_id": second,
                "emotional_valence": "-3|resentful",
            }
        ]
    )
    if writer == "sync":
        apply_state_updates_sync(live_conn, updates, source_chunk_id=tick)
        live_conn.commit()
    else:
        conn = await asyncpg.connect(**asyncpg_kwargs(drift_database))
        try:
            async with conn.transaction():
                await apply_state_updates(conn, updates, source_chunk_id=tick)
        finally:
            await conn.close()
    engine = create_engine(sqlalchemy_url(drift_database))
    try:
        with Session(engine) as session:
            row = session.execute(
                text(
                    """
                SELECT event.id, event.world_layer::text, claim.source_chunk_id,
                       metadata.world_layer::text AS claim_layer
                FROM world_events event
                JOIN claims claim ON claim.world_event_id = event.id
                JOIN chunk_metadata metadata ON metadata.chunk_id = claim.source_chunk_id
                WHERE event.tick_chunk_id = :tick
                  AND event.event_type = 'relationship_drift_milestone'
            """
                ),
                {"tick": tick},
            ).one()
            assert (row.world_layer, row.source_chunk_id, row.claim_layer) == (
                world_layer,
                tick,
                world_layer,
            )
            events = _load_recent_events(session, anchor_chunk_id=tick, window_chunks=1)
            assert (row.id in {event.event_id for event in events}) == (
                world_layer == "primary"
            )
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", ["sync", "async"])
async def test_canceling_producers_retain_versions_and_crossings(
    drift_database: str, live_conn: Any, writer: str
) -> None:
    """The real planner keeps 0 -> .2 -> 0 and both attributed rung crossings."""
    with live_conn.cursor() as cur:
        tick, actor, target, first, hostile = _seed_tick(cur, valence=Decimal("0"))
        cur.execute(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s", (tick,)
        )
        world_time = cur.fetchone()["world_time"]
    live_conn.commit()
    plan = plan_relationship_drift(
        relationships={(actor, target): Decimal("0")},
        project_milestones=[ProjectMilestone(1, actor, target)],
        events=[DriftEvent(hostile, "threat_issued", actor, target)],
        settings=_settings(
            project_milestone_delta="0.2", hostile_events={"threat_issued": "-0.25"}
        ),
    )
    assert len(plan.edges) == 1
    assert plan.edges[0].old_valence == plan.edges[0].new_valence == 0
    assert [delta for _, delta in plan.edges[0].producer_deltas] == [
        Decimal("0.2"),
        Decimal("-0.2"),
    ]
    kwargs = dict(
        plan=plan,
        tick_chunk_id=tick,
        world_time=world_time,
        epistemics_settings=EPISTEMICS,
    )
    if writer == "sync":
        with live_conn.cursor() as cur:
            result = _apply_plan_sync(cur, **kwargs)
        live_conn.commit()
    else:
        conn = await asyncpg.connect(**asyncpg_kwargs(drift_database))
        try:
            async with conn.transaction():
                result = await _apply_plan_async(conn, **kwargs)
        finally:
            await conn.close()
    assert len(result.milestone_event_ids) == len(result.claim_ids) == 2
    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT producer, delta, valence_after FROM relationship_versions
            WHERE source_chunk_id = %s AND operation = 'update' ORDER BY id
        """,
            (tick,),
        )
        assert [tuple(row.values()) for row in cur.fetchall()] == [
            ("project_milestone", Decimal("0.2"), Decimal("0.2")),
            ("drift_event", Decimal("-0.2"), Decimal("0")),
        ]
        cur.execute(
            """
            SELECT payload FROM world_events WHERE id = ANY(%s) ORDER BY id
        """,
            (list(result.milestone_event_ids),),
        )
        assert [
            (
                row["payload"]["producer"],
                row["payload"]["old_rung"],
                row["payload"]["new_rung"],
            )
            for row in cur.fetchall()
        ] == [("project_milestone", 0, 1), ("drift_event", 1, 0)]
        cur.execute(
            "SELECT valence_current FROM character_relationships WHERE character1_id = %s",
            (first,),
        )
        assert cur.fetchone()["valence_current"] == 0
