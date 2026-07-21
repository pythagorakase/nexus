"""Commit-time draining for template-gated durable backstory secrets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping, Optional, Sequence

from nexus.agents.orrery.db_rows import row_get as _row_get
from nexus.agents.orrery.epistemics import (
    promote_claim_scope,
    promote_claim_scope_async,
    record_revelation,
    record_revelation_async,
)
from nexus.agents.orrery.reveal_gates import REVEAL_GATES, SecretContext
from nexus.agents.orrery.substrate import TravelState, WorldState
from nexus.config.settings_models import OrreryRevealSettings


BACKSTORY_SECRET_AUTHORED_EVENT_TYPE = "backstory_secret_authored"
BACKSTORY_REVEALED_EVENT_TYPE = "backstory_revealed"
BACKSTORY_EVENT_TYPES = frozenset(
    {BACKSTORY_SECRET_AUTHORED_EVENT_TYPE, BACKSTORY_REVEALED_EVENT_TYPE}
)


@dataclass(frozen=True, slots=True)
class RevealDrainResult:
    """Secret, awareness, and event rows materialized by one reveal drain."""

    secret_ids: tuple[int, ...] = ()
    awareness_ids: tuple[int, ...] = ()
    event_ids: tuple[int, ...] = ()

    @property
    def revealed_count(self) -> int:
        """Return the number of latent secrets atomically revealed."""

        if len(self.secret_ids) != len(self.event_ids):
            raise RuntimeError("Backstory reveal status/event ledger counts diverged")
        return len(self.secret_ids)


@dataclass(frozen=True, slots=True)
class _LatentSecret:
    secret_id: int
    claim_id: int
    gate_template_id: str
    holder_entity_id: int
    world_event_id: int
    participant_entity_ids: tuple[int, ...]
    created_at: datetime

    def context(self) -> SecretContext:
        return SecretContext(
            secret_id=self.secret_id,
            claim_id=self.claim_id,
            holder_entity_id=self.holder_entity_id,
            world_event_id=self.world_event_id,
            participant_entity_ids=self.participant_entity_ids,
            created_at=self.created_at,
        )


def drain_backstory_reveals_sync(
    cur: Any,
    *,
    tick_chunk_id: int,
    settings: Any,
    state: Optional[WorldState] = None,
) -> RevealDrainResult:
    """Reveal every firing latent secret through a DB-API cursor."""

    config = _enabled_config(settings)
    if config is None:
        return RevealDrainResult()
    _require_migration_091_sync(cur)
    world_time, world_layer = _commit_clock_sync(cur, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return RevealDrainResult()
    secrets = _latent_secrets_sync(cur)
    if not secrets:
        return RevealDrainResult()
    effective_state = state or _hydrate_reveal_state_sync(cur, world_time)
    secret_ids: list[int] = []
    awareness_ids: list[int] = []
    event_ids: list[int] = []
    for secret in secrets:
        gate = REVEAL_GATES.get(secret.gate_template_id)
        if gate is None:
            raise RuntimeError(
                f"Unregistered reveal gate {secret.gate_template_id!r} on "
                f"latent secret {secret.secret_id}"
            )
        if not gate(effective_state, secret.context()):
            continue
        cur.execute(
            """
            UPDATE backstory_secrets
            SET status = 'revealed',
                revealed_at_world_time = %s,
                revealed_by_chunk_id = %s
            WHERE id = %s AND status = 'latent'
            RETURNING id
            """,
            (world_time, tick_chunk_id, secret.secret_id),
        )
        if cur.fetchone() is None:
            continue
        promote_claim_scope(cur, claim_id=secret.claim_id, new_scope="bounded")
        granted_entity_ids: list[int] = []
        for participant_id in _co_located_participants(effective_state, secret):
            grant = record_revelation(
                cur,
                claim_id=secret.claim_id,
                knower_entity_id=participant_id,
                source_entity_id=secret.holder_entity_id,
                channel="backstory_reveal",
                world_time=world_time,
                source_chunk_id=tick_chunk_id,
            )
            if grant.inserted:
                awareness_ids.append(grant.awareness_id)
                granted_entity_ids.append(participant_id)
        event_id = _emit_revealed_sync(
            cur,
            secret=secret,
            tick_chunk_id=tick_chunk_id,
            world_time=world_time,
            granted_entity_ids=granted_entity_ids,
        )
        secret_ids.append(secret.secret_id)
        event_ids.append(event_id)
    return RevealDrainResult(
        secret_ids=tuple(secret_ids),
        awareness_ids=tuple(awareness_ids),
        event_ids=tuple(event_ids),
    )


async def drain_backstory_reveals_async(
    conn: Any,
    *,
    tick_chunk_id: int,
    settings: Any,
    state: Optional[WorldState] = None,
) -> RevealDrainResult:
    """Asyncpg twin of :func:`drain_backstory_reveals_sync`."""

    config = _enabled_config(settings)
    if config is None:
        return RevealDrainResult()
    await _require_migration_091_async(conn)
    world_time, world_layer = await _commit_clock_async(conn, tick_chunk_id)
    if world_layer != "primary" or world_time is None:
        return RevealDrainResult()
    secrets = await _latent_secrets_async(conn)
    if not secrets:
        return RevealDrainResult()
    effective_state = state or await _hydrate_reveal_state_async(conn, world_time)
    secret_ids: list[int] = []
    awareness_ids: list[int] = []
    event_ids: list[int] = []
    for secret in secrets:
        gate = REVEAL_GATES.get(secret.gate_template_id)
        if gate is None:
            raise RuntimeError(
                f"Unregistered reveal gate {secret.gate_template_id!r} on "
                f"latent secret {secret.secret_id}"
            )
        if not gate(effective_state, secret.context()):
            continue
        updated_id = await conn.fetchval(
            """
            UPDATE backstory_secrets
            SET status = 'revealed',
                revealed_at_world_time = $1,
                revealed_by_chunk_id = $2
            WHERE id = $3 AND status = 'latent'
            RETURNING id
            """,
            world_time,
            tick_chunk_id,
            secret.secret_id,
        )
        if updated_id is None:
            continue
        await promote_claim_scope_async(
            conn, claim_id=secret.claim_id, new_scope="bounded"
        )
        granted_entity_ids: list[int] = []
        for participant_id in _co_located_participants(effective_state, secret):
            grant = await record_revelation_async(
                conn,
                claim_id=secret.claim_id,
                knower_entity_id=participant_id,
                source_entity_id=secret.holder_entity_id,
                channel="backstory_reveal",
                world_time=world_time,
                source_chunk_id=tick_chunk_id,
            )
            if grant.inserted:
                awareness_ids.append(grant.awareness_id)
                granted_entity_ids.append(participant_id)
        event_id = await _emit_revealed_async(
            conn,
            secret=secret,
            tick_chunk_id=tick_chunk_id,
            world_time=world_time,
            granted_entity_ids=granted_entity_ids,
        )
        secret_ids.append(secret.secret_id)
        event_ids.append(event_id)
    return RevealDrainResult(
        secret_ids=tuple(secret_ids),
        awareness_ids=tuple(awareness_ids),
        event_ids=tuple(event_ids),
    )


def _enabled_config(settings: Any) -> Optional[OrreryRevealSettings]:
    if settings is None:
        return None
    if isinstance(settings, OrreryRevealSettings):
        config = settings
    elif hasattr(settings, "model_dump"):
        config = OrreryRevealSettings.model_validate(settings.model_dump())
    elif isinstance(settings, Mapping):
        config = OrreryRevealSettings.model_validate(settings)
    else:
        raise TypeError("Orrery reveal settings must be a mapping or Pydantic model")
    return config if config.enabled else None


_MIGRATION_091_ERROR = (
    "Backstory reveals require migration 091; apply migration 091 before "
    "enabling [orrery.reveal]."
)


def _require_migration_091_sync(cur: Any) -> None:
    cur.execute(
        """
        SELECT count(*) AS registered_count,
               to_regclass('backstory_secrets') IS NOT NULL AS table_exists
        FROM event_types
        WHERE type = ANY(%s)
        """,
        (sorted(BACKSTORY_EVENT_TYPES),),
    )
    row = cur.fetchone()
    if (
        row is None
        or int(_row_get(row, "registered_count", 0)) != len(BACKSTORY_EVENT_TYPES)
        or not bool(_row_get(row, "table_exists", 1))
    ):
        raise RuntimeError(_MIGRATION_091_ERROR)


async def _require_migration_091_async(conn: Any) -> None:
    row = await conn.fetchrow(
        """
        SELECT count(*) AS registered_count,
               to_regclass('backstory_secrets') IS NOT NULL AS table_exists
        FROM event_types
        WHERE type = ANY($1::text[])
        """,
        sorted(BACKSTORY_EVENT_TYPES),
    )
    if (
        row is None
        or int(row["registered_count"]) != len(BACKSTORY_EVENT_TYPES)
        or not bool(row["table_exists"])
    ):
        raise RuntimeError(_MIGRATION_091_ERROR)


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
        raise ValueError(f"Backstory-reveal chunk {tick_chunk_id} has no metadata")
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
        raise ValueError(f"Backstory-reveal chunk {tick_chunk_id} has no metadata")
    return row["world_time"], row["world_layer"]


_LATENT_SECRETS_SQL = """
    SELECT secret.id AS secret_id,
           secret.claim_id,
           secret.gate_template_id,
           secret.holder_entity_id,
           claim.world_event_id,
           secret.created_at,
           COALESCE(
               ARRAY(
                   SELECT DISTINCT participant.entity_id
                   FROM world_event_entities participant
                   WHERE participant.event_id = claim.world_event_id
                     AND participant.role::text IN (
                         'actor', 'target', 'beneficiary'
                     )
                   ORDER BY participant.entity_id
               ),
               ARRAY[]::bigint[]
           ) AS participant_entity_ids
    FROM backstory_secrets secret
    JOIN claims claim ON claim.id = secret.claim_id
    WHERE secret.status = 'latent'
    ORDER BY secret.id
"""


def _latent_secrets_sync(cur: Any) -> tuple[_LatentSecret, ...]:
    cur.execute(_LATENT_SECRETS_SQL)
    return _coerce_latent_secrets(cur.fetchall())


async def _latent_secrets_async(conn: Any) -> tuple[_LatentSecret, ...]:
    return _coerce_latent_secrets(await conn.fetch(_LATENT_SECRETS_SQL))


def _coerce_latent_secrets(rows: Sequence[Any]) -> tuple[_LatentSecret, ...]:
    return tuple(
        _LatentSecret(
            secret_id=int(_row_get(row, "secret_id", 0)),
            claim_id=int(_row_get(row, "claim_id", 1)),
            gate_template_id=str(_row_get(row, "gate_template_id", 2)),
            holder_entity_id=int(_row_get(row, "holder_entity_id", 3)),
            world_event_id=int(_row_get(row, "world_event_id", 4)),
            created_at=_row_get(row, "created_at", 5),
            participant_entity_ids=tuple(
                int(value)
                for value in (_row_get(row, "participant_entity_ids", 6) or ())
            ),
        )
        for row in rows
    )


def _hydrate_reveal_state_sync(cur: Any, world_time: datetime) -> WorldState:
    cur.execute("SELECT id, is_active FROM entities ORDER BY id")
    activity = {
        int(_row_get(row, "id", 0)): bool(_row_get(row, "is_active", 1))
        for row in cur.fetchall()
    }
    cur.execute(
        """
        SELECT entity_id, current_location
        FROM characters
        WHERE entity_id IS NOT NULL AND current_location IS NOT NULL
        ORDER BY entity_id
        """
    )
    locations = {
        int(_row_get(row, "entity_id", 0)): int(_row_get(row, "current_location", 1))
        for row in cur.fetchall()
    }
    cur.execute(_TRUST_SQL)
    trust = _coerce_trust(cur.fetchall())
    cur.execute(_TRAVEL_SQL)
    travel_states = _coerce_travel_states(cur.fetchall())
    return WorldState(
        is_active=activity,
        locations=locations,
        trust=trust,
        travel_states=travel_states,
        world_time=world_time,
    )


async def _hydrate_reveal_state_async(conn: Any, world_time: datetime) -> WorldState:
    activity_rows = await conn.fetch("SELECT id, is_active FROM entities ORDER BY id")
    location_rows = await conn.fetch(
        """
        SELECT entity_id, current_location
        FROM characters
        WHERE entity_id IS NOT NULL AND current_location IS NOT NULL
        ORDER BY entity_id
        """
    )
    trust_rows = await conn.fetch(_TRUST_SQL)
    travel_rows = await conn.fetch(_TRAVEL_SQL)
    return WorldState(
        is_active={int(row["id"]): bool(row["is_active"]) for row in activity_rows},
        locations={
            int(row["entity_id"]): int(row["current_location"]) for row in location_rows
        },
        trust=_coerce_trust(trust_rows),
        travel_states=_coerce_travel_states(travel_rows),
        world_time=world_time,
    )


_TRUST_SQL = """
    SELECT source_entity_id, target_entity_id, valence_magnitude
    FROM entity_relationships_v
    WHERE relationship_scope = 'character'
      AND source_entity_id IS NOT NULL
      AND target_entity_id IS NOT NULL
      AND relationship_type IS NOT NULL
      AND valence_magnitude IS NOT NULL
    ORDER BY source_entity_id, target_entity_id
"""

_TRAVEL_SQL = """
    SELECT cts.character_entity_id, cts.status::text AS status
    FROM character_travel_states cts
    JOIN entities entity ON entity.id = cts.character_entity_id
    WHERE entity.kind = 'character' AND entity.is_active = true
    ORDER BY cts.character_entity_id
"""


def _coerce_trust(rows: Sequence[Any]) -> dict[tuple[int, int], int]:
    trust: dict[tuple[int, int], int] = {}
    for row in rows:
        key = (
            int(_row_get(row, "source_entity_id", 0)),
            int(_row_get(row, "target_entity_id", 1)),
        )
        candidate = int(_row_get(row, "valence_magnitude", 2))
        current = trust.get(key)
        if (
            current is None
            or abs(candidate) > abs(current)
            or (abs(candidate) == abs(current) and candidate < current)
        ):
            trust[key] = candidate
    return trust


def _coerce_travel_states(rows: Sequence[Any]) -> dict[int, TravelState]:
    return {
        int(_row_get(row, "character_entity_id", 0)): TravelState(
            status=str(_row_get(row, "status", 1))
        )
        for row in rows
    }


def _co_located_participants(
    state: WorldState, secret: _LatentSecret
) -> tuple[int, ...]:
    holder_location = state.locations.get(secret.holder_entity_id)
    if holder_location is None or _in_transit(state, secret.holder_entity_id):
        return ()
    return tuple(
        participant_id
        for participant_id in secret.participant_entity_ids
        # The holder is trivially co-located with themselves; without this
        # exclusion the drain would record a self-revelation (both gate
        # functions apply the same filter before consuming this list).
        if participant_id != secret.holder_entity_id
        and state.locations.get(participant_id) == holder_location
        and not _in_transit(state, participant_id)
    )


def _in_transit(state: WorldState, entity_id: int) -> bool:
    travel_state = state.travel_states.get(entity_id)
    return bool(travel_state and travel_state.is_in_transit)


def _emit_revealed_sync(
    cur: Any,
    *,
    secret: _LatentSecret,
    tick_chunk_id: int,
    world_time: datetime,
    granted_entity_ids: Sequence[int],
) -> int:
    payload = _reveal_payload(secret, world_time, granted_entity_ids)
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, world_layer, source,
            changed_fields, payload, world_time
        ) VALUES (
            'backstory_revealed', %s, %s, 'primary', 'resolver',
            ARRAY[
                'backstory_secrets.status', 'claims.scope', 'claim_awareness'
            ]::text[],
            %s::jsonb, %s
        )
        RETURNING id
        """,
        (tick_chunk_id, secret.holder_entity_id, payload, world_time),
    )
    return int(_row_get(cur.fetchone(), "id", 0))


async def _emit_revealed_async(
    conn: Any,
    *,
    secret: _LatentSecret,
    tick_chunk_id: int,
    world_time: datetime,
    granted_entity_ids: Sequence[int],
) -> int:
    event_id = await conn.fetchval(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, world_layer, source,
            changed_fields, payload, world_time
        ) VALUES (
            'backstory_revealed', $1, $2, 'primary', 'resolver',
            ARRAY[
                'backstory_secrets.status', 'claims.scope', 'claim_awareness'
            ]::text[],
            $3::jsonb, $4
        )
        RETURNING id
        """,
        tick_chunk_id,
        secret.holder_entity_id,
        _reveal_payload(secret, world_time, granted_entity_ids),
        world_time,
    )
    return int(event_id)


def _reveal_payload(
    secret: _LatentSecret,
    world_time: datetime,
    granted_entity_ids: Sequence[int],
) -> str:
    return json.dumps(
        {
            "claim_id": secret.claim_id,
            "gate_template_id": secret.gate_template_id,
            "revealed_participant_entity_ids": list(granted_entity_ids),
            "secret_id": secret.secret_id,
            "world_time": world_time.isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
