"""World-clock frontier draining for bounded Orrery claims.

The append-only ``claim_awareness`` projection is the only durable frontier.
This module derives every eligible transmission from that table plus the
current Stage 2b communication graph, then double-enters each new awareness
row as a ``claim_propagated`` world event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import heapq
from itertools import count
import json
from typing import Any, Mapping, Optional, Sequence

from nexus.agents.orrery.communication import (
    CommunicationEdge,
    CommunicationGraph,
    assemble_communication_graph,
    assemble_communication_graph_async,
    coerce_contagion_settings,
)
from nexus.agents.orrery.db_rows import row_get as _row_get
from nexus.config.settings_models import OrreryContagionSettings


CLAIM_PROPAGATED_EVENT_TYPE = "claim_propagated"


@dataclass(frozen=True, slots=True)
class AwarenessState:
    """The frontier fields needed to schedule one knower's outbound hops."""

    claim_id: int
    knower_entity_id: int
    acquired_at_world_time: Optional[datetime]
    root_source_entity_id: Optional[int]
    depth: int


@dataclass(frozen=True, slots=True)
class PlannedPropagation:
    """One deterministic acquisition derived during a drain fixpoint."""

    claim_id: int
    knower_entity_id: int
    immediate_source_entity_id: int
    root_source_entity_id: int
    channel: str
    acquired_at_world_time: datetime
    latency_seconds: float
    depth: int


@dataclass(frozen=True, slots=True)
class PropagationDrainResult:
    """Rows and ledger events materialized by one accepted-chunk drain."""

    awareness_ids: tuple[int, ...] = ()
    event_ids: tuple[int, ...] = ()
    policy_digest: Optional[str] = None

    @property
    def minted_count(self) -> int:
        """Return the double-entry acquisition count."""

        if len(self.awareness_ids) != len(self.event_ids):
            raise RuntimeError("Propagation awareness/event ledger counts diverged")
        return len(self.awareness_ids)


def contagion_policy_digest(settings: Any) -> str:
    """Hash canonical JSON for the effective ``[orrery.contagion]`` policy."""

    config = coerce_contagion_settings(settings)
    canonical = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def drain_claim_propagation_sync(
    cur: Any,
    *,
    tick_chunk_id: int,
    settings: Any,
) -> PropagationDrainResult:
    """Drain every eligible bounded-claim hop through a DB-API cursor."""

    config = _enabled_config(settings)
    if config is None:
        return PropagationDrainResult()
    _require_migration_083_sync(cur)
    world_time, world_layer = _commit_clock_sync(cur, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return PropagationDrainResult()
    claim_births = _candidate_claim_births_sync(cur, config)
    if not claim_births:
        return PropagationDrainResult(policy_digest=contagion_policy_digest(config))
    graph = assemble_communication_graph(
        cur,
        settings=config,
        world_time=world_time,
    )
    frontier = _awareness_frontier_sync(cur, tuple(claim_births))
    planned = _plan_propagations(
        claim_births=claim_births,
        frontier=frontier,
        graph=graph,
        world_time=world_time,
        settings=config,
    )
    digest = contagion_policy_digest(config)
    awareness_ids: list[int] = []
    event_ids: list[int] = []
    for acquisition in planned:
        inserted = _insert_propagation_sync(
            cur,
            acquisition=acquisition,
            tick_chunk_id=tick_chunk_id,
            world_layer=world_layer,
            policy_digest=digest,
        )
        if inserted is None:
            continue
        awareness_id, event_id = inserted
        awareness_ids.append(awareness_id)
        event_ids.append(event_id)
    return PropagationDrainResult(
        awareness_ids=tuple(awareness_ids),
        event_ids=tuple(event_ids),
        policy_digest=digest,
    )


async def drain_claim_propagation_async(
    conn: Any,
    *,
    tick_chunk_id: int,
    settings: Any,
) -> PropagationDrainResult:
    """Asyncpg twin of :func:`drain_claim_propagation_sync`."""

    config = _enabled_config(settings)
    if config is None:
        return PropagationDrainResult()
    await _require_migration_083_async(conn)
    world_time, world_layer = await _commit_clock_async(conn, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return PropagationDrainResult()
    claim_births = await _candidate_claim_births_async(conn, config)
    if not claim_births:
        return PropagationDrainResult(policy_digest=contagion_policy_digest(config))
    graph = await assemble_communication_graph_async(
        conn,
        settings=config,
        world_time=world_time,
    )
    frontier = await _awareness_frontier_async(conn, tuple(claim_births))
    planned = _plan_propagations(
        claim_births=claim_births,
        frontier=frontier,
        graph=graph,
        world_time=world_time,
        settings=config,
    )
    digest = contagion_policy_digest(config)
    awareness_ids: list[int] = []
    event_ids: list[int] = []
    for acquisition in planned:
        inserted = await _insert_propagation_async(
            conn,
            acquisition=acquisition,
            tick_chunk_id=tick_chunk_id,
            world_layer=world_layer,
            policy_digest=digest,
        )
        if inserted is None:
            continue
        awareness_id, event_id = inserted
        awareness_ids.append(awareness_id)
        event_ids.append(event_id)
    return PropagationDrainResult(
        awareness_ids=tuple(awareness_ids),
        event_ids=tuple(event_ids),
        policy_digest=digest,
    )


def _enabled_config(settings: Any) -> Optional[OrreryContagionSettings]:
    if settings is None:
        return None
    config = coerce_contagion_settings(settings)
    return config if config.enabled else None


_MIGRATION_083_ERROR = (
    "Claim propagation requires migration 083; apply migration 083 before "
    "enabling [orrery.contagion]."
)


def _require_migration_083_sync(cur: Any) -> None:
    cur.execute(
        """
        SELECT EXISTS (
                   SELECT 1 FROM event_types
                   WHERE type = 'claim_propagated'
               ) AS event_registered,
               EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = ANY(current_schemas(false))
                     AND table_name = 'world_events'
                     AND column_name = 'world_time'
               ) AS world_time_column
        """
    )
    row = cur.fetchone()
    if row is None or not bool(_row_get(row, "event_registered", 0)):
        raise RuntimeError(_MIGRATION_083_ERROR)
    if not bool(_row_get(row, "world_time_column", 1)):
        raise RuntimeError(_MIGRATION_083_ERROR)


async def _require_migration_083_async(conn: Any) -> None:
    row = await conn.fetchrow(
        """
        SELECT EXISTS (
                   SELECT 1 FROM event_types
                   WHERE type = 'claim_propagated'
               ) AS event_registered,
               EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = ANY(current_schemas(false))
                     AND table_name = 'world_events'
                     AND column_name = 'world_time'
               ) AS world_time_column
        """
    )
    if row is None or not bool(row["event_registered"]):
        raise RuntimeError(_MIGRATION_083_ERROR)
    if not bool(row["world_time_column"]):
        raise RuntimeError(_MIGRATION_083_ERROR)


def _commit_clock_sync(cur: Any, tick_chunk_id: int) -> tuple[Optional[datetime], Any]:
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
        raise ValueError(f"Propagation chunk {tick_chunk_id} has no metadata")
    world_time = _row_get(row, "world_time", 0)
    return world_time, _row_get(row, "world_layer", 1)


async def _commit_clock_async(
    conn: Any, tick_chunk_id: int
) -> tuple[Optional[datetime], Any]:
    row = await conn.fetchrow(
        """
        SELECT world_time, world_layer::text AS world_layer
        FROM chunk_metadata
        WHERE chunk_id = $1
        """,
        tick_chunk_id,
    )
    if row is None:
        raise ValueError(f"Propagation chunk {tick_chunk_id} has no metadata")
    world_time = row["world_time"]
    return world_time, row["world_layer"]


_CANDIDATE_CLAIMS_SQL = """
    WITH bounded_claims AS (
        SELECT c.id AS claim_id,
               COALESCE(we.world_time, cm.world_time) AS birth_world_time
        FROM claims c
        JOIN world_events we ON we.id = c.world_event_id
        LEFT JOIN chunk_metadata cm ON cm.chunk_id = we.tick_chunk_id
        WHERE c.scope = 'bounded'
    )
    SELECT candidate.claim_id, candidate.birth_world_time
    FROM bounded_claims candidate
    WHERE candidate.birth_world_time IS NOT NULL
      AND EXISTS (
          SELECT 1
          FROM claim_awareness awareness
          WHERE awareness.claim_id = candidate.claim_id
            AND awareness.acquired_at_world_time IS NOT NULL
            AND awareness.acquired_at_world_time
                <= candidate.birth_world_time + {horizon_placeholder}
      )
    ORDER BY candidate.claim_id
"""


def _candidate_claim_births_sync(
    cur: Any, settings: OrreryContagionSettings
) -> dict[int, datetime]:
    cur.execute(
        _CANDIDATE_CLAIMS_SQL.format(horizon_placeholder="%s"),
        (settings.guards.age_horizon,),
    )
    return _claim_births(cur.fetchall())


async def _candidate_claim_births_async(
    conn: Any, settings: OrreryContagionSettings
) -> dict[int, datetime]:
    rows = await conn.fetch(
        _CANDIDATE_CLAIMS_SQL.format(horizon_placeholder="$1"),
        settings.guards.age_horizon,
    )
    return _claim_births(rows)


def _claim_births(rows: Sequence[Any]) -> dict[int, datetime]:
    births = {}
    for row in rows:
        claim_id = int(_row_get(row, "claim_id", 0))
        birth = _row_get(row, "birth_world_time", 1)
        if birth is None:
            continue
        births[claim_id] = birth
    return births


def _awareness_frontier_sync(
    cur: Any, claim_ids: Sequence[int]
) -> tuple[AwarenessState, ...]:
    cur.execute(
        """
        SELECT id, claim_id, knower_entity_id, root_source_entity_id,
               acquired_at_world_time
        FROM claim_awareness
        WHERE claim_id = ANY(%s)
        ORDER BY claim_id, acquired_at_world_time, knower_entity_id, id
        """,
        (list(claim_ids),),
    )
    awareness_rows = cur.fetchall()
    cur.execute(
        """
        SELECT id, payload
        FROM world_events
        WHERE event_type = 'claim_propagated'
          AND (payload ->> 'claim_id')::bigint = ANY(%s)
        ORDER BY id
        """,
        (list(claim_ids),),
    )
    return _build_frontier(awareness_rows, cur.fetchall())


async def _awareness_frontier_async(
    conn: Any, claim_ids: Sequence[int]
) -> tuple[AwarenessState, ...]:
    awareness_rows = await conn.fetch(
        """
        SELECT id, claim_id, knower_entity_id, root_source_entity_id,
               acquired_at_world_time
        FROM claim_awareness
        WHERE claim_id = ANY($1::bigint[])
        ORDER BY claim_id, acquired_at_world_time, knower_entity_id, id
        """,
        list(claim_ids),
    )
    event_rows = await conn.fetch(
        """
        SELECT id, payload
        FROM world_events
        WHERE event_type = 'claim_propagated'
          AND (payload ->> 'claim_id')::bigint = ANY($1::bigint[])
        ORDER BY id
        """,
        list(claim_ids),
    )
    return _build_frontier(awareness_rows, event_rows)


def _build_frontier(
    awareness_rows: Sequence[Any], event_rows: Sequence[Any]
) -> tuple[AwarenessState, ...]:
    depths: dict[tuple[int, int], int] = {}
    for row in event_rows:
        event_id = int(_row_get(row, "id", 0))
        payload = _json_object(_row_get(row, "payload", 1), event_id=event_id)
        key = (
            _payload_int(payload, "claim_id", event_id),
            _payload_int(payload, "knower_entity_id", event_id),
        )
        depth = _payload_int(payload, "depth", event_id)
        if depth < 1:
            raise ValueError(
                f"claim_propagated event {event_id} has invalid depth {depth}"
            )
        if key in depths:
            raise ValueError(
                "Duplicate claim_propagated ledger entries for claim/knower " f"{key}"
            )
        depths[key] = depth

    frontier = []
    awareness_keys: set[tuple[int, int]] = set()
    for row in awareness_rows:
        claim_id = int(_row_get(row, "claim_id", 1))
        knower = int(_row_get(row, "knower_entity_id", 2))
        acquired = _row_get(row, "acquired_at_world_time", 4)
        root = _row_get(row, "root_source_entity_id", 3)
        # NOTE(#479 Stage C): accounts remain independent claim-id frontiers.
        # Do not skip this account because the knower possesses a sibling;
        # cross-account exclusion belongs to the later distortion policy.
        key = (claim_id, knower)
        awareness_keys.add(key)
        frontier.append(
            AwarenessState(
                claim_id=claim_id,
                knower_entity_id=knower,
                acquired_at_world_time=acquired,
                root_source_entity_id=int(root) if root is not None else None,
                depth=depths.get(key, 0),
            )
        )
    orphaned = sorted(set(depths) - awareness_keys)
    if orphaned:
        raise ValueError(
            "claim_propagated ledger entries have no awareness projection: "
            f"{orphaned}"
        )
    return tuple(frontier)


def _plan_propagations(
    *,
    claim_births: Mapping[int, datetime],
    frontier: Sequence[AwarenessState],
    graph: CommunicationGraph,
    world_time: datetime,
    settings: OrreryContagionSettings,
) -> tuple[PlannedPropagation, ...]:
    by_claim: dict[int, list[AwarenessState]] = {
        claim_id: [] for claim_id in claim_births
    }
    for awareness in frontier:
        by_claim.setdefault(awareness.claim_id, []).append(awareness)

    outbound = _fan_out_edges(graph, settings.guards.fan_out_cap)
    planned: list[PlannedPropagation] = []
    sequence = count()
    for claim_id, birth_world_time in claim_births.items():
        possessed = {
            awareness.knower_entity_id: awareness
            for awareness in by_claim.get(claim_id, ())
        }
        pending: list[tuple[Any, ...]] = []

        def offer(source: AwarenessState) -> None:
            if (
                source.acquired_at_world_time is None
                or source.depth >= settings.guards.depth_cap
            ):
                return
            for edge in outbound.get(source.knower_entity_id, ()):
                scheduled = source.acquired_at_world_time + edge.latency
                if (
                    scheduled > world_time
                    or scheduled > birth_world_time + settings.guards.age_horizon
                ):
                    continue
                heapq.heappush(
                    pending,
                    (
                        scheduled,
                        source.depth + 1,
                        edge.listener_entity_id,
                        source.knower_entity_id,
                        edge.kind,
                        edge.label,
                        next(sequence),
                        edge,
                        source,
                    ),
                )

        for awareness in sorted(
            possessed.values(),
            key=lambda item: (
                item.acquired_at_world_time is None,
                item.acquired_at_world_time or world_time,
                item.depth,
                item.knower_entity_id,
            ),
        ):
            offer(awareness)

        while pending:
            (
                scheduled,
                depth,
                listener,
                source_id,
                _kind,
                _label,
                _sequence,
                edge,
                source,
            ) = heapq.heappop(pending)
            if listener in possessed:
                continue
            root = source.root_source_entity_id or source_id
            acquisition = PlannedPropagation(
                claim_id=claim_id,
                knower_entity_id=listener,
                immediate_source_entity_id=source_id,
                root_source_entity_id=root,
                channel=f"{edge.kind}:{edge.label}",
                acquired_at_world_time=scheduled,
                latency_seconds=edge.latency.total_seconds(),
                depth=depth,
            )
            planned.append(acquisition)
            minted = AwarenessState(
                claim_id=claim_id,
                knower_entity_id=listener,
                acquired_at_world_time=scheduled,
                root_source_entity_id=root,
                depth=depth,
            )
            possessed[listener] = minted
            offer(minted)
    return tuple(planned)


def _fan_out_edges(
    graph: CommunicationGraph, fan_out_cap: int
) -> dict[int, tuple[CommunicationEdge, ...]]:
    by_teller: dict[int, list[CommunicationEdge]] = {}
    for edge in graph.edges:
        by_teller.setdefault(edge.teller_entity_id, []).append(edge)
    return {
        teller: tuple(
            sorted(
                edges,
                key=lambda edge: (edge.latency, edge.listener_entity_id),
            )[:fan_out_cap]
        )
        for teller, edges in by_teller.items()
    }


def _insert_propagation_sync(
    cur: Any,
    *,
    acquisition: PlannedPropagation,
    tick_chunk_id: int,
    world_layer: Any,
    policy_digest: str,
) -> Optional[tuple[int, int]]:
    cur.execute(
        """
        INSERT INTO claim_awareness (
            claim_id, knower_entity_id, source_tier,
            immediate_source_entity_id, root_source_entity_id, channel,
            acquired_at_world_time, source_chunk_id
        ) VALUES (%s, %s, 'told', %s, %s, %s, %s, %s)
        ON CONFLICT (claim_id, knower_entity_id) DO NOTHING
        RETURNING id
        """,
        (
            acquisition.claim_id,
            acquisition.knower_entity_id,
            acquisition.immediate_source_entity_id,
            acquisition.root_source_entity_id,
            acquisition.channel,
            acquisition.acquired_at_world_time,
            tick_chunk_id,
        ),
    )
    awareness_row = cur.fetchone()
    if awareness_row is None:
        return None
    awareness_id = int(_row_get(awareness_row, "id", 0))
    payload = _event_payload(acquisition, awareness_id, policy_digest)
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload, world_time
        ) VALUES (
            'claim_propagated', %s, NULL, NULL, %s::world_layer_type,
            'resolver', ARRAY['claim_awareness']::text[], %s::jsonb, %s
        )
        RETURNING id
        """,
        (
            tick_chunk_id,
            world_layer,
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            acquisition.acquired_at_world_time,
        ),
    )
    event_id = int(_row_get(cur.fetchone(), "id", 0))
    return awareness_id, event_id


async def _insert_propagation_async(
    conn: Any,
    *,
    acquisition: PlannedPropagation,
    tick_chunk_id: int,
    world_layer: Any,
    policy_digest: str,
) -> Optional[tuple[int, int]]:
    awareness_id = await conn.fetchval(
        """
        INSERT INTO claim_awareness (
            claim_id, knower_entity_id, source_tier,
            immediate_source_entity_id, root_source_entity_id, channel,
            acquired_at_world_time, source_chunk_id
        ) VALUES ($1, $2, 'told', $3, $4, $5, $6, $7)
        ON CONFLICT (claim_id, knower_entity_id) DO NOTHING
        RETURNING id
        """,
        acquisition.claim_id,
        acquisition.knower_entity_id,
        acquisition.immediate_source_entity_id,
        acquisition.root_source_entity_id,
        acquisition.channel,
        acquisition.acquired_at_world_time,
        tick_chunk_id,
    )
    if awareness_id is None:
        return None
    payload = _event_payload(acquisition, int(awareness_id), policy_digest)
    event_id = await conn.fetchval(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload, world_time
        ) VALUES (
            'claim_propagated', $1, NULL, NULL, $2::world_layer_type,
            'resolver', ARRAY['claim_awareness']::text[], $3::jsonb, $4
        )
        RETURNING id
        """,
        tick_chunk_id,
        world_layer,
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
        acquisition.acquired_at_world_time,
    )
    return int(awareness_id), int(event_id)


def _event_payload(
    acquisition: PlannedPropagation, awareness_id: int, policy_digest: str
) -> dict[str, Any]:
    return {
        "awareness_id": awareness_id,
        "claim_id": acquisition.claim_id,
        "knower_entity_id": acquisition.knower_entity_id,
        "immediate_source_entity_id": acquisition.immediate_source_entity_id,
        "root_source_entity_id": acquisition.root_source_entity_id,
        "channel": acquisition.channel,
        "latency_seconds": acquisition.latency_seconds,
        "depth": acquisition.depth,
        "policy_digest": policy_digest,
    }


def _json_object(raw: Any, *, event_id: int) -> Mapping[str, Any]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, Mapping):
        raise ValueError(f"claim_propagated event {event_id} payload is not an object")
    return raw


def _payload_int(payload: Mapping[str, Any], key: str, event_id: int) -> int:
    try:
        return int(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"claim_propagated event {event_id} has invalid {key!r}"
        ) from exc
