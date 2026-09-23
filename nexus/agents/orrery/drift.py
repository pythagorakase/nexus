"""Deterministic relationship deltas from authored events and project milestones."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
import json
from typing import Any, Mapping, Optional, Sequence

from nexus.agents.orrery.db_rows import row_get as _row_get
from nexus.agents.orrery.relationship_provenance import (
    emit_relationship_milestones_sync,
    emit_relationship_milestones_async,
    relationship_producer,
    relationship_producer_async,
)
from nexus.config.settings_models import OrreryDriftSettings


RELATIONSHIP_DRIFT_EVENT_TYPE = "relationship_drift_milestone"
RELATIONSHIP_DRIFT_EVENT_TYPES = frozenset({RELATIONSHIP_DRIFT_EVENT_TYPE})
TWO_PARTY_PROJECT_TYPES = frozenset(
    {"recruit_ally", "pursue_romance", "court_patron", "seek_redemption"}
)
ZERO = Decimal("0")
ONE = Decimal("1")
RUNG_SCALE = Decimal("5.5")
VALENCE_QUANTUM = Decimal("1E-12")
MAX_VALENCE = ONE - VALENCE_QUANTUM
PLANNER_PRECISION = 40

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

    with localcontext() as context:
        context.prec = PLANNER_PRECISION
        bounded = _quantize_valence(valence)
        return int((bounded * RUNG_SCALE).quantize(ONE, rounding=ROUND_HALF_UP))


def _quantize_valence(valence: Decimal) -> Decimal:
    """Return the canonical fixed-scale representation for a valence write."""

    value = Decimal(valence)
    if abs(value) >= ONE:
        raise AssertionError(f"Relationship valence is outside (-1, +1): {value}")
    quantized = value.quantize(VALENCE_QUANTUM, rounding=ROUND_HALF_UP)
    return min(max(quantized, -MAX_VALENCE), MAX_VALENCE)


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
    settings: OrreryDriftSettings,
) -> RelationshipDriftPlan:
    """Plan all edge-local drift without database access or side effects."""

    with localcontext() as context:
        context.prec = PLANNER_PRECISION
        values = {
            edge: _quantize_valence(Decimal(value))
            for edge, value in relationships.items()
        }
        old_values = dict(values)
        applied: dict[EdgeKey, list[tuple[str, Decimal]]] = {}

        def apply(edge: EdgeKey, delta: Decimal, label: str) -> None:
            current = values.get(edge)
            if current is None:
                return
            next_value, effective = soft_clamp_step(current, delta)
            values[edge] = next_value
            applied.setdefault(edge, []).append((label, effective))

        for milestone in sorted(
            project_milestones, key=lambda item: item.resolution_id
        ):
            endpoints = (milestone.actor_entity_id, milestone.target_entity_id)
            label = f"project_milestone:{milestone.resolution_id}"
            for edge in _directed_edges(*endpoints):
                apply(edge, settings.project_milestone_delta, label)

        hostile = [
            event for event in events if event.event_type in settings.hostile_events
        ]
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

        write_values = {
            edge: _quantize_valence(value) for edge, value in values.items()
        }
        plans = tuple(
            PlannedEdgeDrift(
                source_entity_id=edge[0],
                target_entity_id=edge[1],
                old_valence=old_values[edge],
                new_valence=write_values[edge],
                producer_deltas=tuple(applied[edge]),
            )
            for edge in sorted(applied)
            if write_values[edge] != old_values[edge]
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
        if settings is None:
            return RelationshipDriftDrainResult()
        event_ids, claim_ids = emit_relationship_milestones_sync(
            cur,
            tick_chunk_id=tick_chunk_id,
            epistemics_settings=epistemics_settings,
        )
        return RelationshipDriftDrainResult((), event_ids, claim_ids)
    _require_migration_115_sync(cur)
    if _drain_recorded_sync(cur, tick_chunk_id):
        event_ids, claim_ids = emit_relationship_milestones_sync(
            cur,
            tick_chunk_id=tick_chunk_id,
            epistemics_settings=epistemics_settings,
        )
        return RelationshipDriftDrainResult((), event_ids, claim_ids)
    world_time, world_layer = _commit_clock_sync(cur, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return RelationshipDriftDrainResult()
    plan = plan_relationship_drift(
        relationships=_relationships_sync(cur),
        project_milestones=_project_milestones_sync(cur, tick_chunk_id),
        events=_drift_events_sync(cur, tick_chunk_id, config),
        settings=config,
    )
    result = _apply_plan_sync(
        cur,
        plan=plan,
        tick_chunk_id=tick_chunk_id,
        world_time=world_time,
        epistemics_settings=epistemics_settings,
    )
    _record_drain_sync(
        cur,
        tick_chunk_id=tick_chunk_id,
        world_time=world_time,
        result=result,
    )
    return result


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
        if settings is None:
            return RelationshipDriftDrainResult()
        event_ids, claim_ids = await emit_relationship_milestones_async(
            conn,
            tick_chunk_id=tick_chunk_id,
            epistemics_settings=epistemics_settings,
        )
        return RelationshipDriftDrainResult((), event_ids, claim_ids)
    await _require_migration_115_async(conn)
    if await _drain_recorded_async(conn, tick_chunk_id):
        event_ids, claim_ids = await emit_relationship_milestones_async(
            conn,
            tick_chunk_id=tick_chunk_id,
            epistemics_settings=epistemics_settings,
        )
        return RelationshipDriftDrainResult((), event_ids, claim_ids)
    world_time, world_layer = await _commit_clock_async(conn, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return RelationshipDriftDrainResult()
    plan = plan_relationship_drift(
        relationships=await _relationships_async(conn),
        project_milestones=await _project_milestones_async(conn, tick_chunk_id),
        events=await _drift_events_async(conn, tick_chunk_id, config),
        settings=config,
    )
    result = await _apply_plan_async(
        conn,
        plan=plan,
        tick_chunk_id=tick_chunk_id,
        world_time=world_time,
        epistemics_settings=epistemics_settings,
    )
    await _record_drain_async(
        conn,
        tick_chunk_id=tick_chunk_id,
        world_time=world_time,
        result=result,
    )
    return result


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


_MIGRATION_115_ERROR = (
    "Relationship drift requires migration 115; apply migration 115 before "
    "enabling [orrery.drift]."
)


def _require_migration_115_sync(cur: Any) -> None:
    cur.execute(
        """
        SELECT count(*) + (to_regclass('orrery_drift_drains') IS NOT NULL)::integer AS registered_count
        FROM event_types
        WHERE type = ANY(%s)
        """,
        (sorted(RELATIONSHIP_DRIFT_EVENT_TYPES),),
    )
    row = cur.fetchone()
    if row is None or int(_row_get(row, "registered_count", 0)) != 2:
        raise RuntimeError(_MIGRATION_115_ERROR)


async def _require_migration_115_async(conn: Any) -> None:
    registered_count = await conn.fetchval(
        """
        SELECT count(*) + (to_regclass('orrery_drift_drains') IS NOT NULL)::integer
        FROM event_types
        WHERE type = ANY($1::text[])
        """,
        sorted(RELATIONSHIP_DRIFT_EVENT_TYPES),
    )
    if int(registered_count or 0) != 2:
        raise RuntimeError(_MIGRATION_115_ERROR)


def _drain_recorded_sync(cur: Any, tick_chunk_id: int) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM orrery_drift_drains
            WHERE tick_chunk_id = %s
        ) AS recorded
        """,
        (tick_chunk_id,),
    )
    row = cur.fetchone()
    return row is not None and bool(_row_get(row, "recorded", 0))


async def _drain_recorded_async(conn: Any, tick_chunk_id: int) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM orrery_drift_drains
                WHERE tick_chunk_id = $1
            )
            """,
            tick_chunk_id,
        )
    )


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
        ): _quantize_valence(Decimal(_row_get(row, "valence_current", 2)))
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
        (
            int(row["source_entity_id"]),
            int(row["target_entity_id"]),
        ): _quantize_valence(Decimal(row["valence_current"]))
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


def _apply_plan_sync(
    cur: Any,
    *,
    plan: RelationshipDriftPlan,
    tick_chunk_id: int,
    world_time: datetime,
    epistemics_settings: Any,
) -> RelationshipDriftDrainResult:
    updated_edges = []
    for edge in plan.edges:
        exact = edge.old_valence
        stored = edge.old_valence
        with localcontext() as context:
            context.prec = PLANNER_PRECISION
            for label, delta in edge.producer_deltas:
                exact += delta
                value = _quantize_valence(exact)
                if value == stored:
                    continue
                producer = (
                    "project_milestone"
                    if label.startswith("project_milestone:")
                    else "drift_event"
                )
                with relationship_producer(
                    cur, producer, source_chunk_id=tick_chunk_id
                ):
                    cur.execute(
                        """UPDATE character_relationships relation SET valence_current = %s
                    FROM characters source, characters target
                    WHERE relation.character1_id = source.id AND relation.character2_id = target.id
                      AND source.entity_id = %s AND target.entity_id = %s""",
                        (value, edge.source_entity_id, edge.target_entity_id),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError(
                            "Relationship edge disappeared during drift application"
                        )
                stored = value
                updated_edges.append((edge.source_entity_id, edge.target_entity_id))
    event_ids, claim_ids = emit_relationship_milestones_sync(
        cur,
        tick_chunk_id=tick_chunk_id,
        epistemics_settings=epistemics_settings,
    )
    return RelationshipDriftDrainResult(tuple(updated_edges), event_ids, claim_ids)


async def _apply_plan_async(
    conn: Any,
    *,
    plan: RelationshipDriftPlan,
    tick_chunk_id: int,
    world_time: datetime,
    epistemics_settings: Any,
) -> RelationshipDriftDrainResult:
    updated_edges = []
    for edge in plan.edges:
        exact = edge.old_valence
        stored = edge.old_valence
        with localcontext() as context:
            context.prec = PLANNER_PRECISION
            for label, delta in edge.producer_deltas:
                exact += delta
                value = _quantize_valence(exact)
                if value == stored:
                    continue
                producer = (
                    "project_milestone"
                    if label.startswith("project_milestone:")
                    else "drift_event"
                )
                async with relationship_producer_async(
                    conn, producer, source_chunk_id=tick_chunk_id
                ):
                    status = await conn.execute(
                        """UPDATE character_relationships relation SET valence_current = $1
                    FROM characters source, characters target
                    WHERE relation.character1_id = source.id AND relation.character2_id = target.id
                      AND source.entity_id = $2 AND target.entity_id = $3""",
                        value,
                        edge.source_entity_id,
                        edge.target_entity_id,
                    )
                    if status != "UPDATE 1":
                        raise RuntimeError(
                            "Relationship edge disappeared during drift application"
                        )
                stored = value
                updated_edges.append((edge.source_entity_id, edge.target_entity_id))
    event_ids, claim_ids = await emit_relationship_milestones_async(
        conn,
        tick_chunk_id=tick_chunk_id,
        epistemics_settings=epistemics_settings,
    )
    return RelationshipDriftDrainResult(tuple(updated_edges), event_ids, claim_ids)


def _record_drain_sync(
    cur: Any,
    *,
    tick_chunk_id: int,
    world_time: datetime,
    result: RelationshipDriftDrainResult,
) -> None:
    cur.execute(
        "INSERT INTO orrery_drift_drains (tick_chunk_id, applied_deltas) VALUES (%s, %s)",
        (tick_chunk_id, len(result.updated_edges)),
    )


async def _record_drain_async(
    conn: Any,
    *,
    tick_chunk_id: int,
    world_time: datetime,
    result: RelationshipDriftDrainResult,
) -> None:
    await conn.execute(
        "INSERT INTO orrery_drift_drains (tick_chunk_id, applied_deltas) VALUES ($1, $2)",
        tick_chunk_id,
        len(result.updated_edges),
    )


def _directed_edges(first: int, second: int) -> tuple[EdgeKey, EdgeKey]:
    forward = (first, second)
    reverse = (second, first)
    return (forward, reverse) if forward < reverse else (reverse, forward)
