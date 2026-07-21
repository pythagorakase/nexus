"""Deterministic world-clock relationship-valence drift.

The planner applies producers in a fixed order: project milestones, hostile
events by event id, cooperative events by event id, then co-presence pairs by
their ordered entity ids.  Every calculation uses :class:`~decimal.Decimal`,
and the appliers write the final numeric value once per existing directed edge.

Co-presence is intentionally sampled only when this drain runs.  It compares
the current locations at the accepted tick with the preceding primary-layer
world time; it does not reconstruct arrivals, departures, or dwell intervals
inside that span.  The configured cap bounds the resulting sampling error on
large world-time jumps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Any, Mapping, Optional, Sequence

from nexus.agents.orrery.db_rows import row_get as _row_get
from nexus.agents.orrery.epistemics import (
    ClaimParticipant,
    mechanical_claim_summary,
    mint_claim_for_event,
    mint_claim_for_event_async,
)
from nexus.config.settings_models import OrreryDriftSettings


RELATIONSHIP_DRIFT_EVENT_TYPE = "relationship_drift_milestone"
TWO_PARTY_PROJECT_TYPES = frozenset(
    {"recruit_ally", "pursue_romance", "court_patron", "seek_redemption"}
)
ZERO = Decimal("0")
ONE = Decimal("1")
RUNG_SCALE = Decimal("5.5")

EdgeKey = tuple[int, int]


@dataclass(frozen=True, slots=True)
class ProjectMilestone:
    """One applied two-party project transition from the current tick."""

    resolution_id: int
    actor_entity_id: int
    target_entity_id: int


@dataclass(frozen=True, slots=True)
class DriftEvent:
    """One classified current-tick event with two character endpoints."""

    event_id: int
    event_type: str
    actor_entity_id: int
    target_entity_id: int


@dataclass(frozen=True, slots=True)
class CopresencePair:
    """One unordered pair of distinct, co-located, non-travelling characters."""

    first_entity_id: int
    second_entity_id: int

    def ordered(self) -> EdgeKey:
        """Return the canonical entity-id order for deterministic planning."""

        return (
            min(self.first_entity_id, self.second_entity_id),
            max(self.first_entity_id, self.second_entity_id),
        )


@dataclass(frozen=True, slots=True)
class PlannedEdgeDrift:
    """The complete one-drain mutation for one existing directed edge."""

    source_entity_id: int
    target_entity_id: int
    old_valence: Decimal
    new_valence: Decimal
    producer_deltas: tuple[tuple[str, Decimal], ...]

    @property
    def old_rung(self) -> int:
        """Return the Stage-1 derived rung at drain entry."""

        return derived_rung(self.old_valence)

    @property
    def new_rung(self) -> int:
        """Return the Stage-1 derived rung after all producers."""

        return derived_rung(self.new_valence)

    @property
    def is_milestone(self) -> bool:
        """Whether this drift crosses a derived-rung boundary."""

        return self.old_rung != self.new_rung


@dataclass(frozen=True, slots=True)
class RelationshipDriftPlan:
    """Pure deterministic output for one accepted tick."""

    edges: tuple[PlannedEdgeDrift, ...] = ()

    @property
    def milestones(self) -> tuple[PlannedEdgeDrift, ...]:
        """Return only edges whose Stage-1 derived rung changed."""

        return tuple(edge for edge in self.edges if edge.is_milestone)


@dataclass(frozen=True, slots=True)
class RelationshipDriftDrainResult:
    """Database rows materialized by one relationship-drift drain."""

    updated_edges: tuple[EdgeKey, ...] = ()
    milestone_event_ids: tuple[int, ...] = ()
    claim_ids: tuple[int, ...] = ()


def derived_rung(valence: Decimal) -> int:
    """Mirror PostgreSQL ``round(numeric * 5.5)`` exactly."""

    return int((valence * RUNG_SCALE).quantize(ONE, rounding=ROUND_HALF_UP))


def soft_clamp_step(valence: Decimal, delta: Decimal) -> tuple[Decimal, Decimal]:
    """Apply one asymptotic delta and return ``(new_value, effective_delta)``."""

    if abs(valence) >= ONE:
        raise AssertionError(f"Relationship valence is outside (-1, +1): {valence}")
    effective = delta * (ONE - abs(valence))
    new_valence = valence + effective
    if abs(new_valence) >= ONE:
        raise AssertionError(
            "Relationship drift escaped (-1, +1): "
            f"v={valence}, delta={delta}, effective={effective}, next={new_valence}"
        )
    return new_valence, effective


def plan_relationship_drift(
    *,
    relationships: Mapping[EdgeKey, Decimal],
    project_milestones: Sequence[ProjectMilestone],
    events: Sequence[DriftEvent],
    copresence_pairs: Sequence[CopresencePair],
    elapsed_hours: Decimal,
    settings: OrreryDriftSettings,
) -> RelationshipDriftPlan:
    """Plan all edge-local drift without database access or side effects."""

    values = {edge: Decimal(value) for edge, value in relationships.items()}
    old_values = dict(values)
    applied: dict[EdgeKey, list[tuple[str, Decimal]]] = {}

    def apply(edge: EdgeKey, delta: Decimal, label: str) -> None:
        current = values.get(edge)
        if current is None:
            return
        next_value, effective = soft_clamp_step(current, delta)
        values[edge] = next_value
        applied.setdefault(edge, []).append((label, effective))

    for milestone in sorted(project_milestones, key=lambda item: item.resolution_id):
        endpoints = (milestone.actor_entity_id, milestone.target_entity_id)
        label = f"project_milestone:{milestone.resolution_id}"
        for edge in _directed_edges(*endpoints):
            apply(edge, settings.project_milestone_delta, label)

    hostile = [event for event in events if event.event_type in settings.hostile_events]
    for event in sorted(hostile, key=lambda item: item.event_id):
        delta = settings.hostile_events[event.event_type]
        label = f"hostile:{event.event_id}:{event.event_type}"
        for edge in _directed_edges(event.actor_entity_id, event.target_entity_id):
            apply(edge, delta, label)

    cooperative = [
        event for event in events if event.event_type in settings.cooperative_events
    ]
    for event in sorted(cooperative, key=lambda item: item.event_id):
        delta = settings.cooperative_events[event.event_type]
        label = f"cooperative:{event.event_id}:{event.event_type}"
        for edge in _directed_edges(event.actor_entity_id, event.target_entity_id):
            apply(edge, delta, label)

    capped_hours = min(max(elapsed_hours, ZERO), settings.copresence_max_hours_per_tick)
    for pair in sorted(copresence_pairs, key=lambda item: item.ordered()):
        first, second = pair.ordered()
        for edge in ((first, second), (second, first)):
            current = values.get(edge)
            if current is None or current == ZERO or capped_hours == ZERO:
                continue
            direction = ONE if current > ZERO else -ONE
            delta = direction * settings.copresence_rate_per_hour * capped_hours
            apply(edge, delta, "copresence")

    plans = tuple(
        PlannedEdgeDrift(
            source_entity_id=edge[0],
            target_entity_id=edge[1],
            old_valence=old_values[edge],
            new_valence=values[edge],
            producer_deltas=tuple(applied[edge]),
        )
        for edge in sorted(applied)
        if values[edge] != old_values[edge]
    )
    return RelationshipDriftPlan(edges=plans)


def drain_relationship_drift_sync(
    cur: Any,
    *,
    tick_chunk_id: int,
    settings: Any,
    epistemics_settings: Any = None,
) -> RelationshipDriftDrainResult:
    """Plan and apply current-tick relationship drift through a DB-API cursor."""

    config = _enabled_config(settings)
    if config is None:
        return RelationshipDriftDrainResult()
    world_time, world_layer = _commit_clock_sync(cur, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return RelationshipDriftDrainResult()
    previous_world_time = _previous_primary_world_time_sync(
        cur, tick_chunk_id=tick_chunk_id
    )
    plan = plan_relationship_drift(
        relationships=_relationships_sync(cur),
        project_milestones=_project_milestones_sync(cur, tick_chunk_id),
        events=_drift_events_sync(cur, tick_chunk_id, config),
        copresence_pairs=_copresence_pairs_sync(cur),
        elapsed_hours=_elapsed_hours(previous_world_time, world_time),
        settings=config,
    )
    return _apply_plan_sync(
        cur,
        plan=plan,
        tick_chunk_id=tick_chunk_id,
        world_time=world_time,
        epistemics_settings=epistemics_settings,
    )


async def drain_relationship_drift_async(
    conn: Any,
    *,
    tick_chunk_id: int,
    settings: Any,
    epistemics_settings: Any = None,
) -> RelationshipDriftDrainResult:
    """Asyncpg twin of :func:`drain_relationship_drift_sync`."""

    config = _enabled_config(settings)
    if config is None:
        return RelationshipDriftDrainResult()
    world_time, world_layer = await _commit_clock_async(conn, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return RelationshipDriftDrainResult()
    previous_world_time = await _previous_primary_world_time_async(
        conn, tick_chunk_id=tick_chunk_id
    )
    plan = plan_relationship_drift(
        relationships=await _relationships_async(conn),
        project_milestones=await _project_milestones_async(conn, tick_chunk_id),
        events=await _drift_events_async(conn, tick_chunk_id, config),
        copresence_pairs=await _copresence_pairs_async(conn),
        elapsed_hours=_elapsed_hours(previous_world_time, world_time),
        settings=config,
    )
    return await _apply_plan_async(
        conn,
        plan=plan,
        tick_chunk_id=tick_chunk_id,
        world_time=world_time,
        epistemics_settings=epistemics_settings,
    )


def _enabled_config(settings: Any) -> Optional[OrreryDriftSettings]:
    if settings is None:
        return None
    if isinstance(settings, OrreryDriftSettings):
        config = settings
    elif hasattr(settings, "model_dump"):
        config = OrreryDriftSettings.model_validate(settings.model_dump())
    elif isinstance(settings, Mapping):
        config = OrreryDriftSettings.model_validate(settings)
    else:
        raise TypeError("Orrery drift settings must be a mapping or Pydantic model")
    return config if config.enabled else None


def _commit_clock_sync(cur: Any, tick_chunk_id: int) -> tuple[Any, Any]:
    cur.execute(
        """
        SELECT world_time, world_layer::text AS world_layer
        FROM chunk_metadata
        WHERE chunk_id = %s
        """,
        (tick_chunk_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Relationship-drift chunk {tick_chunk_id} has no metadata")
    return _row_get(row, "world_time", 0), _row_get(row, "world_layer", 1)


async def _commit_clock_async(conn: Any, tick_chunk_id: int) -> tuple[Any, Any]:
    row = await conn.fetchrow(
        """
        SELECT world_time, world_layer::text AS world_layer
        FROM chunk_metadata
        WHERE chunk_id = $1
        """,
        tick_chunk_id,
    )
    if row is None:
        raise ValueError(f"Relationship-drift chunk {tick_chunk_id} has no metadata")
    return row["world_time"], row["world_layer"]


def _previous_primary_world_time_sync(cur: Any, *, tick_chunk_id: int) -> Any:
    cur.execute(
        """
        SELECT world_time
        FROM chunk_metadata
        WHERE chunk_id < %s
          AND world_layer = 'primary'
          AND world_time IS NOT NULL
        ORDER BY chunk_id DESC
        LIMIT 1
        """,
        (tick_chunk_id,),
    )
    row = cur.fetchone()
    return _row_get(row, "world_time", 0) if row is not None else None


async def _previous_primary_world_time_async(conn: Any, *, tick_chunk_id: int) -> Any:
    return await conn.fetchval(
        """
        SELECT world_time
        FROM chunk_metadata
        WHERE chunk_id < $1
          AND world_layer = 'primary'
          AND world_time IS NOT NULL
        ORDER BY chunk_id DESC
        LIMIT 1
        """,
        tick_chunk_id,
    )


def _elapsed_hours(previous: Optional[datetime], current: datetime) -> Decimal:
    if previous is None:
        return ZERO
    elapsed = current - previous
    return _timedelta_seconds(elapsed) / Decimal("3600")


def _timedelta_seconds(value: timedelta) -> Decimal:
    return (
        Decimal(value.days) * Decimal("86400")
        + Decimal(value.seconds)
        + Decimal(value.microseconds) / Decimal("1000000")
    )


def _relationships_sync(cur: Any) -> dict[EdgeKey, Decimal]:
    cur.execute(
        """
        SELECT source.entity_id AS source_entity_id,
               target.entity_id AS target_entity_id,
               relation.valence_current
        FROM character_relationships relation
        JOIN characters source ON source.id = relation.character1_id
        JOIN characters target ON target.id = relation.character2_id
        ORDER BY source.entity_id, target.entity_id
        """
    )
    return {
        (
            int(_row_get(row, "source_entity_id", 0)),
            int(_row_get(row, "target_entity_id", 1)),
        ): Decimal(_row_get(row, "valence_current", 2))
        for row in cur.fetchall()
    }


async def _relationships_async(conn: Any) -> dict[EdgeKey, Decimal]:
    rows = await conn.fetch(
        """
        SELECT source.entity_id AS source_entity_id,
               target.entity_id AS target_entity_id,
               relation.valence_current
        FROM character_relationships relation
        JOIN characters source ON source.id = relation.character1_id
        JOIN characters target ON target.id = relation.character2_id
        ORDER BY source.entity_id, target.entity_id
        """
    )
    return {
        (int(row["source_entity_id"]), int(row["target_entity_id"])): Decimal(
            row["valence_current"]
        )
        for row in rows
    }


_PROJECT_MILESTONE_SQL = """
    SELECT resolution.id AS resolution_id,
           resolution.actor_entity_id,
           COALESCE(
               resolution.state_delta -> 'project.advance' -> 'applied',
               resolution.state_delta -> 'project.complete' -> 'applied'
           ) AS applied
    FROM orrery_resolutions resolution
    WHERE resolution.tick_chunk_id = {placeholder}
      AND (
          resolution.state_delta ? 'project.complete'
          OR (
              resolution.state_delta ? 'project.advance'
              AND COALESCE(
                  (resolution.state_delta -> 'project.advance'
                   ->> 'milestone')::boolean,
                  false
              )
          )
      )
    ORDER BY resolution.id
"""


def _project_milestones_sync(
    cur: Any, tick_chunk_id: int
) -> tuple[ProjectMilestone, ...]:
    cur.execute(_PROJECT_MILESTONE_SQL.format(placeholder="%s"), (tick_chunk_id,))
    return _coerce_project_milestones(cur.fetchall())


async def _project_milestones_async(
    conn: Any, tick_chunk_id: int
) -> tuple[ProjectMilestone, ...]:
    rows = await conn.fetch(
        _PROJECT_MILESTONE_SQL.format(placeholder="$1"), tick_chunk_id
    )
    return _coerce_project_milestones(rows)


def _coerce_project_milestones(rows: Sequence[Any]) -> tuple[ProjectMilestone, ...]:
    milestones = []
    for row in rows:
        applied = _row_get(row, "applied", 2)
        if isinstance(applied, str):
            applied = json.loads(applied)
        if not isinstance(applied, Mapping):
            raise ValueError(
                f"Project resolution {_row_get(row, 'resolution_id', 0)} "
                "has no applied snapshot"
            )
        project_type = str(applied.get("project_type") or "")
        if project_type not in TWO_PARTY_PROJECT_TYPES:
            continue
        target = applied.get("target_character_entity_id")
        actor = _row_get(row, "actor_entity_id", 1)
        if actor is None or not isinstance(target, int):
            raise ValueError(
                f"Two-party project resolution {_row_get(row, 'resolution_id', 0)} "
                "has no actor/target entity pair"
            )
        milestones.append(
            ProjectMilestone(
                resolution_id=int(_row_get(row, "resolution_id", 0)),
                actor_entity_id=int(actor),
                target_entity_id=target,
            )
        )
    return tuple(milestones)


def _drift_events_sync(
    cur: Any, tick_chunk_id: int, settings: OrreryDriftSettings
) -> tuple[DriftEvent, ...]:
    event_types = sorted({*settings.hostile_events, *settings.cooperative_events})
    cur.execute(
        """
        SELECT id, event_type, actor_entity_id, target_entity_id
        FROM world_events
        WHERE tick_chunk_id = %s
          AND event_type = ANY(%s)
          AND actor_entity_id IS NOT NULL
          AND target_entity_id IS NOT NULL
        ORDER BY id
        """,
        (tick_chunk_id, event_types),
    )
    return _coerce_drift_events(cur.fetchall())


async def _drift_events_async(
    conn: Any, tick_chunk_id: int, settings: OrreryDriftSettings
) -> tuple[DriftEvent, ...]:
    event_types = sorted({*settings.hostile_events, *settings.cooperative_events})
    rows = await conn.fetch(
        """
        SELECT id, event_type, actor_entity_id, target_entity_id
        FROM world_events
        WHERE tick_chunk_id = $1
          AND event_type = ANY($2::text[])
          AND actor_entity_id IS NOT NULL
          AND target_entity_id IS NOT NULL
        ORDER BY id
        """,
        tick_chunk_id,
        event_types,
    )
    return _coerce_drift_events(rows)


def _coerce_drift_events(rows: Sequence[Any]) -> tuple[DriftEvent, ...]:
    return tuple(
        DriftEvent(
            event_id=int(_row_get(row, "id", 0)),
            event_type=str(_row_get(row, "event_type", 1)),
            actor_entity_id=int(_row_get(row, "actor_entity_id", 2)),
            target_entity_id=int(_row_get(row, "target_entity_id", 3)),
        )
        for row in rows
    )


_COPRESENCE_SQL = """
    SELECT first.entity_id AS first_entity_id,
           second.entity_id AS second_entity_id
    FROM characters first
    JOIN characters second
      ON second.current_location = first.current_location
     AND second.entity_id > first.entity_id
    WHERE first.current_location IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM character_travel_states travel
          WHERE travel.character_entity_id = first.entity_id
            AND travel.status = 'in_transit'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM character_travel_states travel
          WHERE travel.character_entity_id = second.entity_id
            AND travel.status = 'in_transit'
      )
    ORDER BY first.entity_id, second.entity_id
"""


def _copresence_pairs_sync(cur: Any) -> tuple[CopresencePair, ...]:
    cur.execute(_COPRESENCE_SQL)
    return tuple(
        CopresencePair(
            int(_row_get(row, "first_entity_id", 0)),
            int(_row_get(row, "second_entity_id", 1)),
        )
        for row in cur.fetchall()
    )


async def _copresence_pairs_async(conn: Any) -> tuple[CopresencePair, ...]:
    rows = await conn.fetch(_COPRESENCE_SQL)
    return tuple(
        CopresencePair(int(row["first_entity_id"]), int(row["second_entity_id"]))
        for row in rows
    )


def _apply_plan_sync(
    cur: Any,
    *,
    plan: RelationshipDriftPlan,
    tick_chunk_id: int,
    world_time: datetime,
    epistemics_settings: Any,
) -> RelationshipDriftDrainResult:
    updated_edges = []
    event_ids = []
    claim_ids = []
    for edge in plan.edges:
        cur.execute(
            """
            UPDATE character_relationships relation
            SET valence_current = %s
            FROM characters source, characters target
            WHERE relation.character1_id = source.id
              AND relation.character2_id = target.id
              AND source.entity_id = %s
              AND target.entity_id = %s
            """,
            (edge.new_valence, edge.source_entity_id, edge.target_entity_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError(
                "Relationship edge disappeared during drift application: "
                f"{edge.source_entity_id}->{edge.target_entity_id}"
            )
        updated_edges.append((edge.source_entity_id, edge.target_entity_id))
        if not edge.is_milestone:
            continue
        event_id, claim_id = _emit_milestone_sync(
            cur,
            edge=edge,
            tick_chunk_id=tick_chunk_id,
            world_time=world_time,
            epistemics_settings=epistemics_settings,
        )
        event_ids.append(event_id)
        if claim_id is not None:
            claim_ids.append(claim_id)
    return RelationshipDriftDrainResult(
        updated_edges=tuple(updated_edges),
        milestone_event_ids=tuple(event_ids),
        claim_ids=tuple(claim_ids),
    )


async def _apply_plan_async(
    conn: Any,
    *,
    plan: RelationshipDriftPlan,
    tick_chunk_id: int,
    world_time: datetime,
    epistemics_settings: Any,
) -> RelationshipDriftDrainResult:
    updated_edges = []
    event_ids = []
    claim_ids = []
    for edge in plan.edges:
        status = await conn.execute(
            """
            UPDATE character_relationships relation
            SET valence_current = $1
            FROM characters source, characters target
            WHERE relation.character1_id = source.id
              AND relation.character2_id = target.id
              AND source.entity_id = $2
              AND target.entity_id = $3
            """,
            edge.new_valence,
            edge.source_entity_id,
            edge.target_entity_id,
        )
        if status != "UPDATE 1":
            raise RuntimeError(
                "Relationship edge disappeared during drift application: "
                f"{edge.source_entity_id}->{edge.target_entity_id}"
            )
        updated_edges.append((edge.source_entity_id, edge.target_entity_id))
        if not edge.is_milestone:
            continue
        event_id, claim_id = await _emit_milestone_async(
            conn,
            edge=edge,
            tick_chunk_id=tick_chunk_id,
            world_time=world_time,
            epistemics_settings=epistemics_settings,
        )
        event_ids.append(event_id)
        if claim_id is not None:
            claim_ids.append(claim_id)
    return RelationshipDriftDrainResult(
        updated_edges=tuple(updated_edges),
        milestone_event_ids=tuple(event_ids),
        claim_ids=tuple(claim_ids),
    )


_MILESTONE_PAYLOAD_SYNC = """
    jsonb_build_object(
        'old_rung', %s::integer,
        'new_rung', %s::integer,
        'old_valence', %s::numeric,
        'new_valence', %s::numeric,
        'producer_deltas', (
            SELECT COALESCE(jsonb_object_agg(label, delta), '{}'::jsonb)
            FROM unnest(%s::text[], %s::numeric[]) AS item(label, delta)
        )
    )
"""

_MILESTONE_PAYLOAD_ASYNC = """
    jsonb_build_object(
        'old_rung', $5::integer,
        'new_rung', $6::integer,
        'old_valence', $7::numeric,
        'new_valence', $8::numeric,
        'producer_deltas', (
            SELECT COALESCE(jsonb_object_agg(label, delta), '{}'::jsonb)
            FROM unnest($9::text[], $10::numeric[]) AS item(label, delta)
        )
    )
"""


def _emit_milestone_sync(
    cur: Any,
    *,
    edge: PlannedEdgeDrift,
    tick_chunk_id: int,
    world_time: datetime,
    epistemics_settings: Any,
) -> tuple[int, Optional[int]]:
    labels = [label for label, _delta in edge.producer_deltas]
    deltas = [delta for _label, delta in edge.producer_deltas]
    cur.execute(
        f"""
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload, world_time
        ) VALUES (
            %s, %s, %s, %s, 'primary', 'resolver',
            ARRAY['character_relationships.valence_current']::text[],
            {_MILESTONE_PAYLOAD_SYNC}, %s
        )
        RETURNING id
        """,
        (
            RELATIONSHIP_DRIFT_EVENT_TYPE,
            tick_chunk_id,
            edge.source_entity_id,
            edge.target_entity_id,
            edge.old_rung,
            edge.new_rung,
            edge.old_valence,
            edge.new_valence,
            labels,
            deltas,
            world_time,
        ),
    )
    event_id = int(_row_get(cur.fetchone(), "id", 0))
    _insert_event_entities_sync(cur, event_id=event_id, edge=edge)
    participants = _claim_participants_sync(cur, edge)
    mint_result = mint_claim_for_event(
        cur,
        world_event_id=event_id,
        event_type=RELATIONSHIP_DRIFT_EVENT_TYPE,
        summary=mechanical_claim_summary(RELATIONSHIP_DRIFT_EVENT_TYPE, participants),
        participants=participants,
        source_chunk_id=tick_chunk_id,
        source_resolution_id=None,
        settings=epistemics_settings,
    )
    return event_id, mint_result.claim_id if mint_result is not None else None


async def _emit_milestone_async(
    conn: Any,
    *,
    edge: PlannedEdgeDrift,
    tick_chunk_id: int,
    world_time: datetime,
    epistemics_settings: Any,
) -> tuple[int, Optional[int]]:
    labels = [label for label, _delta in edge.producer_deltas]
    deltas = [delta for _label, delta in edge.producer_deltas]
    event_id = await conn.fetchval(
        f"""
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload, world_time
        ) VALUES (
            $1, $2, $3, $4, 'primary', 'resolver',
            ARRAY['character_relationships.valence_current']::text[],
            {_MILESTONE_PAYLOAD_ASYNC}, $11
        )
        RETURNING id
        """,
        RELATIONSHIP_DRIFT_EVENT_TYPE,
        tick_chunk_id,
        edge.source_entity_id,
        edge.target_entity_id,
        edge.old_rung,
        edge.new_rung,
        edge.old_valence,
        edge.new_valence,
        labels,
        deltas,
        world_time,
    )
    await _insert_event_entities_async(conn, event_id=int(event_id), edge=edge)
    participants = await _claim_participants_async(conn, edge)
    mint_result = await mint_claim_for_event_async(
        conn,
        world_event_id=int(event_id),
        event_type=RELATIONSHIP_DRIFT_EVENT_TYPE,
        summary=mechanical_claim_summary(RELATIONSHIP_DRIFT_EVENT_TYPE, participants),
        participants=participants,
        source_chunk_id=tick_chunk_id,
        source_resolution_id=None,
        settings=epistemics_settings,
    )
    return int(event_id), mint_result.claim_id if mint_result is not None else None


def _insert_event_entities_sync(
    cur: Any, *, event_id: int, edge: PlannedEdgeDrift
) -> None:
    cur.execute(
        """
        INSERT INTO world_event_entities (event_id, role, entity_id)
        VALUES (%s, 'actor', %s), (%s, 'target', %s)
        ON CONFLICT DO NOTHING
        """,
        (event_id, edge.source_entity_id, event_id, edge.target_entity_id),
    )


async def _insert_event_entities_async(
    conn: Any, *, event_id: int, edge: PlannedEdgeDrift
) -> None:
    await conn.execute(
        """
        INSERT INTO world_event_entities (event_id, role, entity_id)
        VALUES ($1, 'actor', $2), ($1, 'target', $3)
        ON CONFLICT DO NOTHING
        """,
        event_id,
        edge.source_entity_id,
        edge.target_entity_id,
    )


def _claim_participants_sync(
    cur: Any, edge: PlannedEdgeDrift
) -> tuple[ClaimParticipant, ...]:
    cur.execute(
        """
        SELECT names.id, names.name, entities.kind::text AS entity_kind
        FROM entity_names_v names
        JOIN entities ON entities.id = names.id
        WHERE names.id = ANY(%s)
        """,
        ([edge.source_entity_id, edge.target_entity_id],),
    )
    return _claim_participants_from_rows(cur.fetchall(), edge)


async def _claim_participants_async(
    conn: Any, edge: PlannedEdgeDrift
) -> tuple[ClaimParticipant, ...]:
    rows = await conn.fetch(
        """
        SELECT names.id, names.name, entities.kind::text AS entity_kind
        FROM entity_names_v names
        JOIN entities ON entities.id = names.id
        WHERE names.id = ANY($1::bigint[])
        """,
        [edge.source_entity_id, edge.target_entity_id],
    )
    return _claim_participants_from_rows(rows, edge)


def _claim_participants_from_rows(
    rows: Sequence[Any], edge: PlannedEdgeDrift
) -> tuple[ClaimParticipant, ...]:
    details = {
        int(_row_get(row, "id", 0)): (
            str(_row_get(row, "name", 1)),
            str(_row_get(row, "entity_kind", 2)),
        )
        for row in rows
    }
    participants = []
    for entity_id, role in (
        (edge.source_entity_id, "actor"),
        (edge.target_entity_id, "target"),
    ):
        if entity_id not in details:
            raise ValueError(
                f"Drift milestone cannot mint awareness for unnamed entity {entity_id}"
            )
        name, kind = details[entity_id]
        participants.append(ClaimParticipant(entity_id, role, name, kind))
    return tuple(participants)


def _directed_edges(first: int, second: int) -> tuple[EdgeKey, EdgeKey]:
    forward = (first, second)
    reverse = (second, first)
    return (forward, reverse) if forward < reverse else (reverse, forward)
