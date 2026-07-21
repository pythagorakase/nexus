"""Rollback-only commit-path coverage for relationship drift."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from itertools import count
from typing import Any, Iterator
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings
from nexus.config.settings_models import OrreryDriftSettings


pytestmark = pytest.mark.requires_postgres

_SCENES = count(100)
EPISTEMICS = {
    "enabled": True,
    "claim_event_types": ["relationship_drift_milestone"],
    "aware_roles": ["actor", "target"],
}


@pytest.fixture()
def live_conn() -> Iterator[Any]:
    """Open a slot-5 transaction and roll back every fixture mutation."""

    conn = psycopg2.connect(get_slot_db_url(slot=5), cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                           SELECT 1
                           FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'character_relationships'
                             AND column_name = 'valence_current'
                       ) AS valence_ready,
                       EXISTS (
                           SELECT 1
                           FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'world_events'
                             AND column_name = 'world_time'
                       ) AS event_clock_ready
                """
            )
            readiness = cur.fetchone()
            if not readiness["valence_ready"] or not readiness["event_clock_ready"]:
                pytest.skip("slot 5 requires applied migrations 083 and 088")
            cur.execute(
                """
                INSERT INTO event_types (type, category, severity, description)
                VALUES
                    (
                        'relationship_drift_milestone', 'emotional', 'minor',
                        'Rollback-only migration-089 milestone event seed.'
                    ),
                    (
                        'relationship_drift_drained', 'emotional', 'minor',
                        'Rollback-only migration-089 drain event seed.'
                    )
                ON CONFLICT (type) DO NOTHING
                """
            )
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _settings(*, enabled: bool = True, **overrides: object) -> OrreryDriftSettings:
    payload: dict[str, object] = {
        "enabled": enabled,
        "copresence_rate_per_hour": "0.001",
        "copresence_max_hours_per_tick": "12",
        "project_milestone_delta": "0.03",
        "hostile_events": {"threat_issued": "-0.2"},
        "cooperative_events": {"welfare_check": "0.02"},
    }
    payload.update(overrides)
    return OrreryDriftSettings.model_validate(payload)


def _insert_chunk(
    cur: Any, *, world_layer: str = "primary", time_delta: timedelta
) -> int:
    token = uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES (%s, 'Rollback-only relationship drift fixture.')
        RETURNING id
        """,
        (f"Relationship drift fixture {token}.",),
    )
    chunk_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date, slug
        ) VALUES (
            %s, 98, 98, %s, %s::world_layer_type, %s, now(), %s
        )
        """,
        (chunk_id, next(_SCENES), world_layer, time_delta, token[:10]),
    )
    return chunk_id


def _insert_character(cur: Any, label: str) -> tuple[int, int]:
    cur.execute(
        "INSERT INTO entities (kind, is_active) "
        "VALUES ('character', true) RETURNING id"
    )
    entity_id = int(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO characters (name, entity_id) VALUES (%s, %s) RETURNING id",
        (f"drift-{label}-{uuid4().hex[:10]}", entity_id),
    )
    return entity_id, int(cur.fetchone()["id"])


def _insert_edge(
    cur: Any,
    *,
    source_character_id: int,
    target_character_id: int,
    valence: Decimal = Decimal("0.1"),
) -> None:
    cur.execute(
        """
        INSERT INTO character_relationships (
            character1_id, character2_id, relationship_type,
            emotional_valence, valence_current, dynamic,
            recent_events, history
        ) VALUES (
            %s, %s, 'associate', '+1|favorable', %s,
            'Rollback-only drift edge.', 'None.', 'Fixture.'
        )
        """,
        (source_character_id, target_character_id, valence),
    )


def _insert_hostile_event(
    cur: Any, *, chunk_id: int, actor_entity_id: int, target_entity_id: int
) -> int:
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload
        ) VALUES (
            'threat_issued', %s, %s, %s, 'primary', 'resolver', '{}', '{}'
        )
        RETURNING id
        """,
        (chunk_id, actor_entity_id, target_entity_id),
    )
    return int(cur.fetchone()["id"])


def _seed_tick(
    cur: Any,
    *,
    world_layer: str = "primary",
    valence: Decimal = Decimal("0.1"),
) -> tuple[int, int, int, int, int]:
    _insert_chunk(cur, time_delta=timedelta(0))
    tick_chunk_id = _insert_chunk(
        cur, world_layer=world_layer, time_delta=timedelta(hours=1)
    )
    actor_entity_id, actor_character_id = _insert_character(cur, "actor")
    target_entity_id, target_character_id = _insert_character(cur, "target")
    _insert_edge(
        cur,
        source_character_id=actor_character_id,
        target_character_id=target_character_id,
        valence=valence,
    )
    event_id = _insert_hostile_event(
        cur,
        chunk_id=tick_chunk_id,
        actor_entity_id=actor_entity_id,
        target_entity_id=target_entity_id,
    )
    cur.execute(
        "SELECT set_config('nexus.source_chunk_id', %s, true)",
        (str(tick_chunk_id),),
    )
    return (
        tick_chunk_id,
        actor_entity_id,
        target_entity_id,
        actor_character_id,
        event_id,
    )


def test_commit_drift_updates_versions_projects_literal_and_mints_claim(
    live_conn: Any,
) -> None:
    """A rung-crossing event is double-entered and known by both endpoints."""

    with live_conn.cursor() as cur:
        tick_chunk_id, actor_id, target_id, actor_character_id, _ = _seed_tick(cur)
        cur.execute(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
            (tick_chunk_id,),
        )
        tick_world_time = cur.fetchone()["world_time"]

    commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        drift_settings=_settings(),
        epistemics_settings=load_settings("nexus.toml").orrery.epistemics,
    )
    commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        drift_settings=_settings(),
        epistemics_settings=load_settings("nexus.toml").orrery.epistemics,
    )

    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT emotional_valence::text, valence_current
            FROM character_relationships
            WHERE character1_id = %s
            """,
            (actor_character_id,),
        )
        relationship = cur.fetchone()
        assert relationship == {
            "emotional_valence": "0|neutral",
            "valence_current": Decimal("-0.08"),
        }

        cur.execute(
            """
            SELECT count(*) AS count
            FROM relationship_versions
            WHERE relationship_table = 'character_relationships'
              AND source_chunk_id = %s
            """,
            (tick_chunk_id,),
        )
        assert cur.fetchone()["count"] == 1

        cur.execute(
            """
            SELECT payload
            FROM world_events
            WHERE tick_chunk_id = %s
              AND event_type = 'relationship_drift_drained'
            """,
            (tick_chunk_id,),
        )
        drain_marker = cur.fetchone()
        assert drain_marker is not None
        assert cur.fetchone() is None
        assert drain_marker["payload"] == {
            "edges_touched": 1,
            "milestone_count": 1,
        }

        cur.execute(
            """
            SELECT id, actor_entity_id, target_entity_id, changed_fields,
                   payload, world_time
            FROM world_events
            WHERE tick_chunk_id = %s
              AND event_type = 'relationship_drift_milestone'
            """,
            (tick_chunk_id,),
        )
        milestone = cur.fetchone()
        assert milestone is not None
        assert cur.fetchone() is None
        assert milestone["actor_entity_id"] == actor_id
        assert milestone["target_entity_id"] == target_id
        assert milestone["changed_fields"] == [
            "character_relationships.valence_current"
        ]
        assert milestone["world_time"] == tick_world_time
        assert milestone["payload"]["old_rung"] == 1
        assert milestone["payload"]["new_rung"] == 0
        assert Decimal(str(milestone["payload"]["old_valence"])) == Decimal("0.1")
        assert Decimal(str(milestone["payload"]["new_valence"])) == Decimal("-0.08")
        assert len(milestone["payload"]["producer_deltas"]) == 1
        producer_label = next(iter(milestone["payload"]["producer_deltas"]))
        assert producer_label.startswith("hostile:")
        assert Decimal(
            str(milestone["payload"]["producer_deltas"][producer_label])
        ) == Decimal("-0.18")

        cur.execute(
            """
            SELECT awareness.knower_entity_id
            FROM claims claim
            JOIN claim_awareness awareness ON awareness.claim_id = claim.id
            WHERE claim.world_event_id = %s
            ORDER BY awareness.knower_entity_id
            """,
            (milestone["id"],),
        )
        assert [row["knower_entity_id"] for row in cur.fetchall()] == sorted(
            [actor_id, target_id]
        )

        cur.execute(
            """
            SELECT role::text, entity_id
            FROM world_event_entities
            WHERE event_id = %s
            ORDER BY role
            """,
            (milestone["id"],),
        )
        assert {(row["role"], row["entity_id"]) for row in cur.fetchall()} == {
            ("actor", actor_id),
            ("target", target_id),
        }


def test_retrograde_world_layer_does_not_drift(live_conn: Any) -> None:
    """The two-clocks gate rejects non-primary chunks silently."""

    with live_conn.cursor() as cur:
        tick_chunk_id, _actor, _target, actor_character_id, _event = _seed_tick(
            cur, world_layer="retrograde"
        )

    commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        drift_settings=_settings(),
        epistemics_settings=EPISTEMICS,
    )

    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT valence_current FROM character_relationships "
            "WHERE character1_id = %s",
            (actor_character_id,),
        )
        assert cur.fetchone()["valence_current"] == Decimal("0.1")


def test_disabled_config_does_not_drift(live_conn: Any) -> None:
    """The config gate is silent and performs no relationship write."""

    with live_conn.cursor() as cur:
        tick_chunk_id, _actor, _target, actor_character_id, _event = _seed_tick(cur)

    commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        drift_settings=_settings(enabled=False),
        epistemics_settings=EPISTEMICS,
    )

    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT valence_current FROM character_relationships "
            "WHERE character1_id = %s",
            (actor_character_id,),
        )
        assert cur.fetchone()["valence_current"] == Decimal("0.1")


def test_zero_edge_tick_still_records_drain_marker(live_conn: Any) -> None:
    """A completed empty drain is durable and idempotent too."""

    with live_conn.cursor() as cur:
        _insert_chunk(cur, time_delta=timedelta(0))
        tick_chunk_id = _insert_chunk(cur, time_delta=timedelta(0))

    commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        drift_settings=_settings(),
        epistemics_settings=EPISTEMICS,
    )

    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT payload
            FROM world_events
            WHERE tick_chunk_id = %s
              AND event_type = 'relationship_drift_drained'
            """,
            (tick_chunk_id,),
        )
        assert cur.fetchone()["payload"] == {
            "edges_touched": 0,
            "milestone_count": 0,
        }


def test_resolution_free_copresence_crossing_mints_canonical_claim(
    live_conn: Any,
) -> None:
    """Canonical epistemics reaches drift when no Orrery proposal exists."""

    with live_conn.cursor() as cur:
        tick_chunk_id, actor_id, target_id, _character_id, _event = _seed_tick(
            cur, valence=Decimal("0.08")
        )
        cur.execute("SELECT id FROM places ORDER BY id LIMIT 1")
        place_id = cur.fetchone()["id"]
        cur.execute(
            """
            UPDATE characters
            SET current_location = %s
            WHERE entity_id = ANY(%s)
            """,
            (place_id, [actor_id, target_id]),
        )

    commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        drift_settings=_settings(
            copresence_rate_per_hour="0.2",
            copresence_max_hours_per_tick="1",
            hostile_events={},
            cooperative_events={},
        ),
        epistemics_settings=load_settings("nexus.toml").orrery.epistemics,
    )

    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT claim.id
            FROM world_events event
            JOIN claims claim ON claim.world_event_id = event.id
            WHERE event.tick_chunk_id = %s
              AND event.event_type = 'relationship_drift_milestone'
              AND event.actor_entity_id = %s
              AND event.target_entity_id = %s
            """,
            (tick_chunk_id, actor_id, target_id),
        )
        assert cur.fetchone() is not None


def test_long_scale_valence_uses_same_rung_as_postgres(live_conn: Any) -> None:
    """Defensive read quantization cannot disagree with SQL rung derivation."""

    long_valence = Decimal("-0.4545454545454545454545454545454545454545")
    with live_conn.cursor() as cur:
        tick_chunk_id, _actor, _target, actor_character_id, _event = _seed_tick(
            cur, valence=long_valence
        )
        cur.execute(
            """
            SELECT round(valence_current * 5.5)::integer AS sql_rung
            FROM character_relationships
            WHERE character1_id = %s
            """,
            (actor_character_id,),
        )
        sql_rung = cur.fetchone()["sql_rung"]

    commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        drift_settings=_settings(),
        epistemics_settings=EPISTEMICS,
    )

    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT (payload ->> 'old_rung')::integer AS python_rung
            FROM world_events
            WHERE tick_chunk_id = %s
              AND event_type = 'relationship_drift_milestone'
            """,
            (tick_chunk_id,),
        )
        assert cur.fetchone()["python_rung"] == sql_rung
