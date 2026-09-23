"""Transaction-scoped relationship provenance and all-producer milestones."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any, AsyncIterator, Iterator, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from nexus.agents.orrery.db_rows import row_get as _row_get
from nexus.agents.orrery.epistemics import (
    ClaimParticipant,
    mechanical_claim_summary,
    mint_claim_for_event,
    mint_claim_for_event_async,
    load_epistemics_policy,
)

RELATIONSHIP_DRIFT_EVENT_TYPE = "relationship_drift_milestone"
PRODUCERS = frozenset(
    {
        "gaia",
        "drift_event",
        "project_milestone",
        "package",
        "trait_compiler",
        "retrograde",
        "migration",
        "manual",
    }
)


def relationship_producer_sqlalchemy(
    connection_or_session: Connection | Session, producer: str
) -> None:
    """Stamp the caller's SQLAlchemy transaction until commit or rollback."""
    if producer not in PRODUCERS:
        raise ValueError(f"Unknown relationship producer: {producer}")
    connection_or_session.execute(
        text("SELECT set_config('nexus.write_producer', :producer, true)"),
        {"producer": producer},
    )


@contextmanager
def relationship_producer(
    cur: Any, producer: str, *, source_chunk_id: Optional[int] = None
) -> Iterator[None]:
    """Set a producer only for this writer, restoring any enclosing producer."""
    if producer not in PRODUCERS:
        raise ValueError(f"Unknown relationship producer: {producer}")
    cur.execute("SELECT current_setting('nexus.write_producer', true) AS producer")
    previous = _row_get(cur.fetchone(), "producer", 0) or ""
    if source_chunk_id is not None:
        cur.execute("SELECT current_setting('nexus.source_chunk_id', true) AS chunk")
        previous_chunk = _row_get(cur.fetchone(), "chunk", 0) or ""
        cur.execute(
            "SELECT set_config('nexus.source_chunk_id', %s, true)",
            (str(source_chunk_id),),
        )
    cur.execute(f"SET LOCAL nexus.write_producer = '{producer}'")
    try:
        yield
    except BaseException:
        # An aborted transaction cannot execute a restoration; rollback resets LOCAL.
        raise
    else:
        cur.execute("SELECT set_config('nexus.write_producer', %s, true)", (previous,))
        if source_chunk_id is not None:
            cur.execute(
                "SELECT set_config('nexus.source_chunk_id', %s, true)",
                (previous_chunk,),
            )


@asynccontextmanager
async def relationship_producer_async(
    conn: Any, producer: str, *, source_chunk_id: Optional[int] = None
) -> AsyncIterator[None]:
    """Asyncpg twin of relationship_producer; requires the caller transaction."""
    if producer not in PRODUCERS:
        raise ValueError(f"Unknown relationship producer: {producer}")
    previous = await conn.fetchval(
        "SELECT current_setting('nexus.write_producer', true)"
    )
    if source_chunk_id is not None:
        previous_chunk = await conn.fetchval(
            "SELECT current_setting('nexus.source_chunk_id', true)"
        )
        await conn.execute(
            "SELECT set_config('nexus.source_chunk_id', $1, true)", str(source_chunk_id)
        )
    await conn.execute(f"SET LOCAL nexus.write_producer = '{producer}'")
    try:
        yield
    except BaseException:
        raise
    else:
        await conn.execute(
            "SELECT set_config('nexus.write_producer', $1, true)", previous or ""
        )
        if source_chunk_id is not None:
            await conn.execute(
                "SELECT set_config('nexus.source_chunk_id', $1, true)",
                previous_chunk or "",
            )


@dataclass(frozen=True)
class RelationshipCrossing:
    """One trigger-detected crossing, retaining the exact database numerics."""

    source_entity_id: int
    target_entity_id: int
    old_valence: Decimal
    new_valence: Decimal
    producer: str

    @property
    def old_rung(self) -> int:
        """Return the pre-write canonical rung."""
        with localcontext() as context:
            context.prec = max(40, len(self.old_valence.as_tuple().digits) + 5)
            return int(
                (self.old_valence * Decimal("5.5")).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
            )

    @property
    def new_rung(self) -> int:
        """Return the post-write canonical rung."""
        with localcontext() as context:
            context.prec = max(40, len(self.new_valence.as_tuple().digits) + 5)
            return int(
                (self.new_valence * Decimal("5.5")).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
            )

    @property
    def producer_deltas(self) -> tuple[tuple[str, Decimal], ...]:
        """Preserve the existing payload shape alongside the closed producer name."""
        return ((self.producer, self.new_valence - self.old_valence),)


_PENDING_SQL = """
    SELECT queue.version_id, source.entity_id AS source_entity_id,
           target.entity_id AS target_entity_id,
           (version.old_row->>'valence_current')::numeric AS old_valence,
           version.valence_after, version.producer,
           coalesce(version.source_chunk_id, {tick}) AS tick_chunk_id,
           metadata.world_time, metadata.world_layer::text AS world_layer
    FROM relationship_milestone_queue queue
    JOIN relationship_versions version ON version.id = queue.version_id
    JOIN characters source ON source.id = (version.old_row->>'character1_id')::bigint
    JOIN characters target ON target.id = (version.old_row->>'character2_id')::bigint
    JOIN chunk_metadata metadata ON metadata.chunk_id = coalesce(version.source_chunk_id, {tick})
    WHERE queue.event_id IS NULL
      AND (version.source_chunk_id = {tick} OR version.source_chunk_id IS NULL)
    ORDER BY queue.version_id
    FOR UPDATE OF queue
"""


def _crossing(row: Any) -> RelationshipCrossing:
    return RelationshipCrossing(
        int(_row_get(row, "source_entity_id", 1)),
        int(_row_get(row, "target_entity_id", 2)),
        Decimal(_row_get(row, "old_valence", 3)),
        Decimal(_row_get(row, "valence_after", 4)),
        str(_row_get(row, "producer", 5)),
    )


def emit_relationship_milestones_sync(
    cur: Any,
    *,
    tick_chunk_id: int,
    epistemics_settings: Any = None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Consume queued crossings atomically, regardless of their producer."""
    policy = (
        load_epistemics_policy() if epistemics_settings is None else epistemics_settings
    )
    cur.execute(_PENDING_SQL.format(tick="%s"), (tick_chunk_id,) * 3)
    rows = cur.fetchall()
    event_ids, claim_ids = [], []
    for row in rows:
        event_id, claim_id = _emit_milestone_sync(
            cur,
            edge=_crossing(row),
            tick_chunk_id=int(_row_get(row, "tick_chunk_id", 6)),
            world_time=_row_get(row, "world_time", 7),
            world_layer=_row_get(row, "world_layer", 8),
            epistemics_settings=policy,
        )
        cur.execute(
            "UPDATE relationship_milestone_queue SET event_id = %s WHERE version_id = %s",
            (event_id, _row_get(row, "version_id", 0)),
        )
        event_ids.append(event_id)
        if claim_id is not None:
            claim_ids.append(claim_id)
    return tuple(event_ids), tuple(claim_ids)


async def emit_relationship_milestones_async(
    conn: Any,
    *,
    tick_chunk_id: int,
    epistemics_settings: Any = None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Asyncpg twin of emit_relationship_milestones_sync."""
    policy = (
        load_epistemics_policy() if epistemics_settings is None else epistemics_settings
    )
    rows = await conn.fetch(_PENDING_SQL.format(tick="$1"), tick_chunk_id)
    event_ids, claim_ids = [], []
    for row in rows:
        event_id, claim_id = await _emit_milestone_async(
            conn,
            edge=_crossing(row),
            tick_chunk_id=int(row["tick_chunk_id"]),
            world_time=row["world_time"],
            world_layer=row["world_layer"],
            epistemics_settings=policy,
        )
        await conn.execute(
            "UPDATE relationship_milestone_queue SET event_id = $1 WHERE version_id = $2",
            event_id,
            row["version_id"],
        )
        event_ids.append(event_id)
        if claim_id is not None:
            claim_ids.append(claim_id)
    return tuple(event_ids), tuple(claim_ids)


_MILESTONE_PAYLOAD_SYNC = """
    jsonb_build_object(
        'producer', %s::text,
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
        'producer', $12::text,
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
    edge: RelationshipCrossing,
    tick_chunk_id: int,
    world_time: datetime,
    world_layer: str,
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
            %s, %s, %s, %s, %s::world_layer_type, 'resolver',
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
            world_layer,
            edge.producer,
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
    edge: RelationshipCrossing,
    tick_chunk_id: int,
    world_time: datetime,
    world_layer: str,
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
            $1, $2, $3, $4, $13::world_layer_type, 'resolver',
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
        edge.producer,
        world_layer,
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
    cur: Any, *, event_id: int, edge: RelationshipCrossing
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
    conn: Any, *, event_id: int, edge: RelationshipCrossing
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
    cur: Any, edge: RelationshipCrossing
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
    conn: Any, edge: RelationshipCrossing
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
    rows: Sequence[Any], edge: RelationshipCrossing
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
