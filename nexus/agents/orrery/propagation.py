"""World-clock frontier draining for bounded Orrery claims.

The append-only ``claim_awareness`` projection is the only durable frontier.
This module derives every eligible transmission from that table plus the
current Stage 2b communication graph, then double-enters each new awareness
row as a ``claim_propagated`` world event.

The accepted-tick commit drains propagation before
:mod:`nexus.agents.orrery.reveal`. A reveal that promotes a private incident
to bounded during that same tick is therefore absent from this drain's
snapshot and first becomes propagatable on the next accepted tick. This pins
the scene boundary: the secret comes out now; gossip starts next scene.
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
from nexus.config.settings_models import (
    OrreryContagionSettings,
    OrreryDistortionSettings,
)


CLAIM_PROPAGATED_EVENT_TYPE = "claim_propagated"


@dataclass(frozen=True, slots=True)
class AwarenessState:
    """The frontier fields needed to schedule one knower's outbound hops."""

    claim_id: int
    incident_world_event_id: int
    knower_entity_id: int
    acquired_at_world_time: Optional[datetime]
    root_source_entity_id: Optional[int]
    depth: int


@dataclass(frozen=True, slots=True)
class PlannedPropagation:
    """One deterministic acquisition derived during a drain fixpoint."""

    claim_id: int
    delivered_claim_id: int
    incident_world_event_id: int
    knower_entity_id: int
    immediate_source_entity_id: int
    root_source_entity_id: int
    channel: str
    acquired_at_world_time: datetime
    latency_seconds: float
    depth: int


@dataclass(frozen=True, slots=True)
class ClaimAccount:
    """One authored sibling in a drain-start incident snapshot."""

    claim_id: int
    distortion_min_depth: Optional[int]
    propagation_eligible: bool


@dataclass(frozen=True, slots=True)
class IncidentSnapshot:
    """Sibling accounts and their shared canonical-event clock."""

    world_event_id: int
    birth_world_time: datetime
    accounts: tuple[ClaimAccount, ...]


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
    distortion_settings: Any = None,
) -> PropagationDrainResult:
    """Drain every eligible bounded-claim hop through a DB-API cursor."""

    config = _enabled_config(settings)
    if config is None:
        return PropagationDrainResult()
    _require_migration_083_sync(cur)
    world_time, world_layer = _commit_clock_sync(cur, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return PropagationDrainResult()
    incidents = _candidate_incidents_sync(cur, config)
    if not incidents:
        return PropagationDrainResult(policy_digest=contagion_policy_digest(config))
    graph = assemble_communication_graph(
        cur,
        settings=config,
        world_time=world_time,
    )
    frontier = _awareness_frontier_sync(cur, incidents)
    planned = _plan_propagations(
        incidents=incidents,
        frontier=frontier,
        graph=graph,
        world_time=world_time,
        settings=config,
        distortion_enabled=_distortion_enabled(distortion_settings),
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
    distortion_settings: Any = None,
) -> PropagationDrainResult:
    """Asyncpg twin of :func:`drain_claim_propagation_sync`."""

    config = _enabled_config(settings)
    if config is None:
        return PropagationDrainResult()
    await _require_migration_083_async(conn)
    world_time, world_layer = await _commit_clock_async(conn, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return PropagationDrainResult()
    incidents = await _candidate_incidents_async(conn, config)
    if not incidents:
        return PropagationDrainResult(policy_digest=contagion_policy_digest(config))
    graph = await assemble_communication_graph_async(
        conn,
        settings=config,
        world_time=world_time,
    )
    frontier = await _awareness_frontier_async(conn, incidents)
    planned = _plan_propagations(
        incidents=incidents,
        frontier=frontier,
        graph=graph,
        world_time=world_time,
        settings=config,
        distortion_enabled=_distortion_enabled(distortion_settings),
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


def _distortion_enabled(settings: Any) -> bool:
    if isinstance(settings, OrreryDistortionSettings):
        return settings.enabled
    return OrreryDistortionSettings.model_validate(settings or {}).enabled


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
               ) AS world_time_column,
               EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE (
                         table_schema = ANY(current_schemas(false))
                         OR table_schema = pg_my_temp_schema()::regnamespace::text
                     )
                     AND table_name = 'claims'
                     AND column_name = 'distortion_min_depth'
               ) AS distortion_depth_column
        """
    )
    row = cur.fetchone()
    if row is None or not bool(_row_get(row, "event_registered", 0)):
        raise RuntimeError(_MIGRATION_083_ERROR)
    if not bool(_row_get(row, "world_time_column", 1)):
        raise RuntimeError(_MIGRATION_083_ERROR)
    if not bool(_row_get(row, "distortion_depth_column", 2)):
        raise RuntimeError(
            "Claim propagation requires migration 092; apply migration 092 "
            "before draining incident-aware propagation."
        )


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
               ) AS world_time_column,
               EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE (
                         table_schema = ANY(current_schemas(false))
                         OR table_schema = pg_my_temp_schema()::regnamespace::text
                     )
                     AND table_name = 'claims'
                     AND column_name = 'distortion_min_depth'
               ) AS distortion_depth_column
        """
    )
    if row is None or not bool(row["event_registered"]):
        raise RuntimeError(_MIGRATION_083_ERROR)
    if not bool(row["world_time_column"]):
        raise RuntimeError(_MIGRATION_083_ERROR)
    if not bool(row["distortion_depth_column"]):
        raise RuntimeError(
            "Claim propagation requires migration 092; apply migration 092 "
            "before draining incident-aware propagation."
        )


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


_CANDIDATE_INCIDENTS_SQL = """
    WITH incident_accounts AS (
        SELECT claim.id AS claim_id,
               claim.world_event_id AS incident_world_event_id,
               claim.scope,
               claim.distortion_min_depth,
               COALESCE(event.world_time, metadata.world_time)
                   AS birth_world_time
        FROM claims claim
        JOIN world_events event ON event.id = claim.world_event_id
        LEFT JOIN chunk_metadata metadata
          ON metadata.chunk_id = event.tick_chunk_id
    ), eligible_incidents AS (
        SELECT DISTINCT account.incident_world_event_id
        FROM incident_accounts account
        JOIN claim_awareness awareness
          ON awareness.claim_id = account.claim_id
        WHERE account.scope = 'bounded'
          AND account.birth_world_time IS NOT NULL
          AND awareness.acquired_at_world_time IS NOT NULL
          AND awareness.acquired_at_world_time
              <= account.birth_world_time + {horizon_placeholder}
    )
    SELECT account.claim_id, account.incident_world_event_id,
           account.birth_world_time, account.distortion_min_depth,
           account.scope
    FROM incident_accounts account
    JOIN eligible_incidents eligible
      ON eligible.incident_world_event_id = account.incident_world_event_id
    ORDER BY account.incident_world_event_id, account.claim_id
"""


def _candidate_incidents_sync(
    cur: Any, settings: OrreryContagionSettings
) -> dict[int, IncidentSnapshot]:
    cur.execute(
        _CANDIDATE_INCIDENTS_SQL.format(horizon_placeholder="%s"),
        (settings.guards.age_horizon,),
    )
    return _incident_snapshots(cur.fetchall())


async def _candidate_incidents_async(
    conn: Any, settings: OrreryContagionSettings
) -> dict[int, IncidentSnapshot]:
    rows = await conn.fetch(
        _CANDIDATE_INCIDENTS_SQL.format(horizon_placeholder="$1"),
        settings.guards.age_horizon,
    )
    return _incident_snapshots(rows)


def _incident_snapshots(rows: Sequence[Any]) -> dict[int, IncidentSnapshot]:
    grouped: dict[int, tuple[datetime, list[ClaimAccount]]] = {}
    for row in rows:
        claim_id = int(_row_get(row, "claim_id", 0))
        incident_id = int(_row_get(row, "incident_world_event_id", 1))
        birth = _row_get(row, "birth_world_time", 2)
        if birth is None:
            continue
        raw_depth = _row_get(row, "distortion_min_depth", 3)
        scope = str(_row_get(row, "scope", 4))
        account = ClaimAccount(
            claim_id=claim_id,
            distortion_min_depth=(int(raw_depth) if raw_depth is not None else None),
            propagation_eligible=scope == "bounded",
        )
        existing = grouped.setdefault(incident_id, (birth, []))
        if existing[0] != birth:
            raise ValueError(
                f"Incident {incident_id} sibling claims disagree on birth time"
            )
        existing[1].append(account)
    return {
        incident_id: IncidentSnapshot(
            world_event_id=incident_id,
            birth_world_time=birth,
            accounts=tuple(accounts),
        )
        for incident_id, (birth, accounts) in grouped.items()
    }


def _awareness_frontier_sync(
    cur: Any, incidents: Mapping[int, IncidentSnapshot]
) -> tuple[AwarenessState, ...]:
    claim_incidents = _claim_incident_index(incidents)
    claim_ids = tuple(claim_incidents)
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
    return _build_frontier(
        awareness_rows,
        cur.fetchall(),
        claim_incidents=claim_incidents,
    )


async def _awareness_frontier_async(
    conn: Any, incidents: Mapping[int, IncidentSnapshot]
) -> tuple[AwarenessState, ...]:
    claim_incidents = _claim_incident_index(incidents)
    claim_ids = tuple(claim_incidents)
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
    return _build_frontier(
        awareness_rows,
        event_rows,
        claim_incidents=claim_incidents,
    )


def _claim_incident_index(
    incidents: Mapping[int, IncidentSnapshot],
) -> dict[int, int]:
    return {
        account.claim_id: incident.world_event_id
        for incident in incidents.values()
        for account in incident.accounts
    }


def _build_frontier(
    awareness_rows: Sequence[Any],
    event_rows: Sequence[Any],
    *,
    claim_incidents: Mapping[int, int],
) -> tuple[AwarenessState, ...]:
    depths: dict[tuple[int, int], int] = {}
    for row in event_rows:
        event_id = int(_row_get(row, "id", 0))
        payload = _json_object(_row_get(row, "payload", 1), event_id=event_id)
        scheduling_claim_id, delivered_claim_id, incident_id = (
            _propagation_claim_identity(payload, event_id=event_id)
        )
        scheduling_incident = claim_incidents.get(scheduling_claim_id)
        delivered_incident = claim_incidents.get(delivered_claim_id)
        if scheduling_incident is None or delivered_incident is None:
            raise ValueError(
                f"claim_propagated event {event_id} names a claim outside its "
                "incident snapshot"
            )
        if scheduling_incident != delivered_incident:
            raise ValueError(
                f"claim_propagated event {event_id} crosses incident boundaries"
            )
        if incident_id is not None and incident_id != scheduling_incident:
            raise ValueError(
                f"claim_propagated event {event_id} has incident "
                f"{incident_id}, expected {scheduling_incident}"
            )
        key = (
            delivered_claim_id,
            _payload_int(payload, "knower_entity_id", event_id),
        )
        depth = _payload_int(payload, "depth", event_id)
        if depth < 1:
            raise ValueError(
                f"claim_propagated event {event_id} has invalid depth {depth}"
            )
        if key in depths:
            raise ValueError(
                "Duplicate claim_propagated ledger entries for delivered "
                f"claim/knower {key}"
            )
        depths[key] = depth

    frontier = []
    awareness_keys: set[tuple[int, int]] = set()
    for row in awareness_rows:
        claim_id = int(_row_get(row, "claim_id", 1))
        knower = int(_row_get(row, "knower_entity_id", 2))
        acquired = _row_get(row, "acquired_at_world_time", 4)
        root = _row_get(row, "root_source_entity_id", 3)
        key = (claim_id, knower)
        awareness_keys.add(key)
        incident_id = claim_incidents.get(claim_id)
        if incident_id is None:
            raise ValueError(f"Awareness row names unknown incident claim {claim_id}")
        frontier.append(
            AwarenessState(
                claim_id=claim_id,
                incident_world_event_id=incident_id,
                knower_entity_id=knower,
                acquired_at_world_time=acquired,
                root_source_entity_id=int(root) if root is not None else None,
                depth=depths.get(key, 0),
            )
        )
    orphaned = sorted(set(depths) - awareness_keys)
    if orphaned:
        raise ValueError(
            "claim_propagated delivered claim/knower entries have no awareness "
            "projection: "
            f"{orphaned}"
        )
    return tuple(frontier)


def _plan_propagations(
    *,
    incidents: Mapping[int, IncidentSnapshot],
    frontier: Sequence[AwarenessState],
    graph: CommunicationGraph,
    world_time: datetime,
    settings: OrreryContagionSettings,
    distortion_enabled: bool,
) -> tuple[PlannedPropagation, ...]:
    by_incident: dict[int, list[AwarenessState]] = {
        incident_id: [] for incident_id in incidents
    }
    for awareness in frontier:
        by_incident.setdefault(awareness.incident_world_event_id, []).append(awareness)

    outbound = _fan_out_edges(graph, settings.guards.fan_out_cap)
    planned: list[PlannedPropagation] = []
    sequence = count()
    for incident_id in sorted(incidents):
        incident = incidents[incident_id]
        birth_world_time = incident.birth_world_time
        eligible_claim_ids = {
            account.claim_id
            for account in incident.accounts
            if account.propagation_eligible
        }
        # Ledger integrity remains keyed by delivered claim/knower, while this
        # possession frontier is deliberately incident/knower: hearing any
        # sibling account suppresses every later propagated account.
        possessed: dict[int, AwarenessState] = {}
        for awareness in sorted(
            by_incident.get(incident_id, ()),
            key=_awareness_source_sort_key,
        ):
            possessed.setdefault(awareness.knower_entity_id, awareness)
        pending: list[tuple[Any, ...]] = []

        def offer(source: AwarenessState) -> None:
            if (
                source.claim_id not in eligible_claim_ids
                or source.acquired_at_world_time is None
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
                        source.claim_id,
                        next(sequence),
                        edge,
                        source,
                    ),
                )

        for awareness in sorted(possessed.values(), key=_awareness_source_sort_key):
            offer(awareness)

        while pending:
            (
                scheduled,
                depth,
                listener,
                source_id,
                _kind,
                _label,
                _scheduling_claim_id,
                _sequence,
                edge,
                source,
            ) = heapq.heappop(pending)
            if listener in possessed:
                continue
            root = source.root_source_entity_id or source_id
            delivered_claim_id = _select_delivered_claim(
                incident,
                scheduling_claim_id=source.claim_id,
                depth=depth,
                distortion_enabled=distortion_enabled,
            )
            acquisition = PlannedPropagation(
                claim_id=source.claim_id,
                delivered_claim_id=delivered_claim_id,
                incident_world_event_id=incident_id,
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
                claim_id=delivered_claim_id,
                incident_world_event_id=incident_id,
                knower_entity_id=listener,
                acquired_at_world_time=scheduled,
                root_source_entity_id=root,
                depth=depth,
            )
            possessed[listener] = minted
            offer(minted)
    return tuple(planned)


def _awareness_source_sort_key(awareness: AwarenessState) -> tuple[Any, ...]:
    return (
        awareness.acquired_at_world_time is None,
        awareness.acquired_at_world_time or datetime.max,
        awareness.depth,
        awareness.knower_entity_id,
        awareness.claim_id,
    )


def _select_delivered_claim(
    incident: IncidentSnapshot,
    *,
    scheduling_claim_id: int,
    depth: int,
    distortion_enabled: bool,
) -> int:
    """Select from the fixed authored sibling set by total birth-hop depth.

    Variants do not compound through lineage. Each onward hop consults the
    original drain-start incident snapshot, and the deepest qualifying authored
    account wins directly.
    """

    if not distortion_enabled:
        return scheduling_claim_id
    qualifying = [
        account
        for account in incident.accounts
        if account.propagation_eligible
        and account.distortion_min_depth is not None
        and account.distortion_min_depth <= depth
    ]
    if not qualifying:
        return scheduling_claim_id
    return min(
        qualifying,
        key=lambda account: (-int(account.distortion_min_depth or 0), account.claim_id),
    ).claim_id


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
            acquisition.delivered_claim_id,
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
        acquisition.delivered_claim_id,
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
        "delivered_claim_id": acquisition.delivered_claim_id,
        "incident_world_event_id": acquisition.incident_world_event_id,
        "distortion_applied": (acquisition.delivered_claim_id != acquisition.claim_id),
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


def _propagation_claim_identity(
    payload: Mapping[str, Any], *, event_id: int
) -> tuple[int, int, Optional[int]]:
    """Validate Stage C identity keys with a pre-092 absent-key fallback."""

    stage_c_keys = {
        "delivered_claim_id",
        "incident_world_event_id",
        "distortion_applied",
    }
    present = stage_c_keys & set(payload)
    if present and present != stage_c_keys:
        missing = sorted(stage_c_keys - present)
        raise ValueError(
            f"claim_propagated event {event_id} lacks Stage C payload fields "
            f"{missing}"
        )
    scheduling_claim_id = _payload_int(payload, "claim_id", event_id)
    if not present:
        return scheduling_claim_id, scheduling_claim_id, None
    delivered_claim_id = _payload_int(payload, "delivered_claim_id", event_id)
    incident_id = _payload_int(payload, "incident_world_event_id", event_id)
    distortion_applied = payload["distortion_applied"]
    if not isinstance(distortion_applied, bool):
        raise ValueError(
            f"claim_propagated event {event_id} has invalid " "'distortion_applied'"
        )
    expected = delivered_claim_id != scheduling_claim_id
    if distortion_applied != expected:
        raise ValueError(
            f"claim_propagated event {event_id} distortion_applied disagrees "
            "with its scheduling and delivered claims"
        )
    return scheduling_claim_id, delivered_claim_id, incident_id


def _payload_int(payload: Mapping[str, Any], key: str, event_id: int) -> int:
    try:
        return int(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"claim_propagated event {event_id} has invalid {key!r}"
        ) from exc
