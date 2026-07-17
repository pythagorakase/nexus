"""Event-anchored claims and entity awareness for Orrery Epistemics v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import bindparam, text


CLAIM_SCOPES = frozenset({"common", "bounded", "private"})
EVENT_ROLES = frozenset({"actor", "target", "observer", "witness", "beneficiary"})
PARTICIPANT_ROLES = frozenset({"actor", "target", "beneficiary"})
WITNESS_ROLES = frozenset({"observer", "witness"})


@dataclass(frozen=True, slots=True)
class EpistemicsPolicy:
    """Normalized runtime view of ``[orrery.epistemics]``."""

    enabled: bool = False
    claim_event_types: frozenset[str] = frozenset()
    aware_roles: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ClaimParticipant:
    """One canonical event participant available to claim minting."""

    entity_id: int
    role: str
    name: str
    entity_kind: str = "character"


@dataclass(frozen=True, slots=True)
class MintResult:
    """Identifiers materialized or recovered by an idempotent claim mint."""

    claim_id: int
    awareness_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RevelationResult:
    """Outcome of an idempotent explicit awareness grant."""

    awareness_id: int
    source_tier: str
    inserted: bool


@dataclass(frozen=True, slots=True)
class AwarenessHydration:
    """Claim scopes and per-entity awareness for one recent-event window."""

    claimed_event_scopes: Mapping[int, str]
    awareness_by_entity: Mapping[int, frozenset[int]]


def coerce_epistemics_policy(raw: Any) -> EpistemicsPolicy:
    """Normalize a Pydantic model or mapping into strict runtime policy."""

    if raw is None:
        return EpistemicsPolicy()
    if isinstance(raw, EpistemicsPolicy):
        return raw
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, Mapping):
        raise TypeError("Epistemics settings must be a mapping or Pydantic model")
    event_types = [str(value).strip() for value in raw.get("claim_event_types", ())]
    aware_roles = [str(value).strip() for value in raw.get("aware_roles", ())]
    if any(not value for value in event_types):
        raise ValueError("Epistemics claim_event_types entries must be non-empty")
    unknown_roles = set(aware_roles) - EVENT_ROLES
    if unknown_roles:
        raise ValueError(f"Unknown Epistemics aware roles: {sorted(unknown_roles)}")
    return EpistemicsPolicy(
        enabled=bool(raw.get("enabled", True)),
        claim_event_types=frozenset(event_types),
        aware_roles=frozenset(aware_roles),
    )


def load_epistemics_policy() -> EpistemicsPolicy:
    """Load the canonical ``[orrery.epistemics]`` policy or fail loudly."""

    from nexus.config import load_settings

    settings = load_settings()
    if settings.orrery is None:
        raise ValueError("settings.orrery is required for Epistemics")
    return coerce_epistemics_policy(settings.orrery.epistemics)


def mechanical_claim_summary(
    event_type: str, participants: Iterable[ClaimParticipant | Mapping[str, Any]]
) -> str:
    """Build deterministic claim prose from event type, roles, and entity names."""

    normalized = _normalize_participants(participants)
    subject = event_type.replace("_", " ").strip()
    if not subject:
        raise ValueError("Claim event_type must be non-empty")
    if not normalized:
        raise ValueError("Claim summaries require at least one named participant")
    rendered = ", ".join(
        f"{participant.role} {participant.name}" for participant in normalized
    )
    return f"{subject.capitalize()}: {rendered}."


def mint_claim_for_event(
    cur: Any,
    *,
    world_event_id: int,
    event_type: str,
    summary: str,
    participants: Iterable[ClaimParticipant | Mapping[str, Any]],
    source_chunk_id: Optional[int],
    source_resolution_id: Optional[int],
    settings: Any,
) -> Optional[MintResult]:
    """Mint or recover one event claim and its configured awareness rows."""

    policy = coerce_epistemics_policy(settings)
    if not policy.enabled or event_type not in policy.claim_event_types:
        return None
    normalized = _normalize_participants(participants)
    clean_summary = summary.strip()
    if not clean_summary:
        raise ValueError("Claim summary must be non-empty")
    cur.execute(
        """
        INSERT INTO claims (
            world_event_id, summary, scope, source_chunk_id, source_resolution_id
        ) VALUES (%s, %s, 'bounded', %s, %s)
        ON CONFLICT (world_event_id) WHERE world_event_id IS NOT NULL DO NOTHING
        RETURNING id
        """,
        (world_event_id, clean_summary, source_chunk_id, source_resolution_id),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "SELECT id FROM claims WHERE world_event_id = %s", (world_event_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"Claim conflict for world event {world_event_id} had no existing row"
            )
    claim_id = int(_row_value(row, "id", 0))
    awareness_ids = _mint_awareness_sync(
        cur,
        claim_id=claim_id,
        participants=normalized,
        policy=policy,
        source_chunk_id=source_chunk_id,
    )
    return MintResult(claim_id=claim_id, awareness_ids=awareness_ids)


async def mint_claim_for_event_async(
    conn: Any,
    *,
    world_event_id: int,
    event_type: str,
    summary: str,
    participants: Iterable[ClaimParticipant | Mapping[str, Any]],
    source_chunk_id: Optional[int],
    source_resolution_id: Optional[int],
    settings: Any,
) -> Optional[MintResult]:
    """Async twin of :func:`mint_claim_for_event` for asyncpg appliers."""

    policy = coerce_epistemics_policy(settings)
    if not policy.enabled or event_type not in policy.claim_event_types:
        return None
    normalized = _normalize_participants(participants)
    clean_summary = summary.strip()
    if not clean_summary:
        raise ValueError("Claim summary must be non-empty")
    claim_id = await conn.fetchval(
        """
        INSERT INTO claims (
            world_event_id, summary, scope, source_chunk_id, source_resolution_id
        ) VALUES ($1, $2, 'bounded', $3, $4)
        ON CONFLICT (world_event_id) WHERE world_event_id IS NOT NULL DO NOTHING
        RETURNING id
        """,
        world_event_id,
        clean_summary,
        source_chunk_id,
        source_resolution_id,
    )
    if claim_id is None:
        claim_id = await conn.fetchval(
            "SELECT id FROM claims WHERE world_event_id = $1", world_event_id
        )
        if claim_id is None:
            raise RuntimeError(
                f"Claim conflict for world event {world_event_id} had no existing row"
            )
    awareness_ids = await _mint_awareness_async(
        conn,
        claim_id=int(claim_id),
        participants=normalized,
        policy=policy,
        source_chunk_id=source_chunk_id,
    )
    return MintResult(claim_id=int(claim_id), awareness_ids=awareness_ids)


def record_revelation(
    cur: Any,
    *,
    claim_id: int,
    knower_entity_id: int,
    source_entity_id: Optional[int] = None,
    channel: Optional[str] = None,
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
) -> RevelationResult:
    """Idempotently grant told or manual awareness of an existing claim."""

    source_tier = "told" if source_entity_id is not None else "granted"
    root_source_entity_id = None
    if source_entity_id is not None:
        cur.execute("SELECT scope FROM claims WHERE id = %s", (claim_id,))
        claim_row = cur.fetchone()
        if claim_row is None:
            raise ValueError(f"Claim {claim_id} does not exist")
        if str(_row_value(claim_row, "scope", 0)) == "common":
            root_source_entity_id = source_entity_id
        else:
            cur.execute(
                """
                SELECT root_source_entity_id
                FROM claim_awareness
                WHERE claim_id = %s AND knower_entity_id = %s
                """,
                (claim_id, source_entity_id),
            )
            source_awareness = cur.fetchone()
            if source_awareness is None:
                raise ValueError(
                    f"Entity {source_entity_id} cannot reveal claim {claim_id}: "
                    "the teller does not possess it"
                )
            inherited_root = _row_value(source_awareness, "root_source_entity_id", 0)
            root_source_entity_id = (
                int(inherited_root) if inherited_root is not None else source_entity_id
            )
    cur.execute(
        """
        INSERT INTO claim_awareness (
            claim_id, knower_entity_id, source_tier,
            immediate_source_entity_id, root_source_entity_id, channel,
            acquired_at_world_time, source_chunk_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (claim_id, knower_entity_id) DO NOTHING
        RETURNING id
        """,
        (
            claim_id,
            knower_entity_id,
            source_tier,
            source_entity_id,
            root_source_entity_id,
            channel,
            world_time,
            source_chunk_id,
        ),
    )
    row = cur.fetchone()
    inserted = row is not None
    if row is None:
        cur.execute(
            """
            SELECT id, source_tier FROM claim_awareness
            WHERE claim_id = %s AND knower_entity_id = %s
            """,
            (claim_id, knower_entity_id),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                "Awareness conflict did not resolve to an existing row for "
                f"claim {claim_id}, entity {knower_entity_id}"
            )
    return RevelationResult(
        awareness_id=int(_row_value(row, "id", 0)),
        source_tier=(
            source_tier if inserted else str(_row_value(row, "source_tier", 1))
        ),
        inserted=inserted,
    )


def promote_claim_scope(cur: Any, *, claim_id: int, new_scope: str) -> None:
    """Promote a common claim to bounded/private; reject every narrowing."""

    if new_scope not in CLAIM_SCOPES:
        raise ValueError(f"Unknown claim scope {new_scope!r}")
    cur.execute("SELECT scope FROM claims WHERE id = %s FOR UPDATE", (claim_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Claim {claim_id} does not exist")
    current_scope = str(_row_value(row, "scope", 0))
    if new_scope == current_scope:
        return
    if current_scope != "common" or new_scope == "common":
        raise ValueError(
            f"Illegal claim scope transition {current_scope!r} -> {new_scope!r}"
        )
    cur.execute("UPDATE claims SET scope = %s WHERE id = %s", (new_scope, claim_id))


def load_awareness_for_events(
    session: Any, *, world_event_ids: Sequence[int]
) -> AwarenessHydration:
    """Hydrate claim scopes and awareness in one query for selected events."""

    event_ids = sorted(set(int(event_id) for event_id in world_event_ids))
    if not event_ids:
        return AwarenessHydration({}, {})
    query = text(
        """
        /* orrery:epistemics_awareness */
        SELECT c.world_event_id, c.scope, ca.knower_entity_id
        FROM claims c
        LEFT JOIN claim_awareness ca ON ca.claim_id = c.id
        WHERE c.world_event_id IN :world_event_ids
        ORDER BY c.world_event_id, ca.knower_entity_id
        """
    ).bindparams(bindparam("world_event_ids", expanding=True))
    scopes: dict[int, str] = {}
    awareness: dict[int, set[int]] = {}
    for row in session.execute(query, {"world_event_ids": event_ids}).mappings():
        event_id = int(row["world_event_id"])
        scope = str(row["scope"])
        if scope not in CLAIM_SCOPES:
            raise ValueError(f"Claim on event {event_id} has unknown scope {scope!r}")
        scopes[event_id] = scope
        knower_entity_id = row["knower_entity_id"]
        if knower_entity_id is not None:
            awareness.setdefault(int(knower_entity_id), set()).add(event_id)
    return AwarenessHydration(
        claimed_event_scopes=scopes,
        awareness_by_entity={
            entity_id: frozenset(events) for entity_id, events in awareness.items()
        },
    )


def _normalize_participants(
    participants: Iterable[ClaimParticipant | Mapping[str, Any]],
) -> tuple[ClaimParticipant, ...]:
    normalized = []
    for raw in participants:
        if isinstance(raw, ClaimParticipant):
            participant = raw
        elif isinstance(raw, Mapping):
            participant = ClaimParticipant(
                entity_id=int(raw["entity_id"]),
                role=str(raw["role"]),
                name=str(raw["name"]),
                entity_kind=str(raw.get("entity_kind", "character")),
            )
        else:
            raise TypeError("Claim participants must be mappings or ClaimParticipant")
        if participant.role not in EVENT_ROLES:
            raise ValueError(f"Unknown event participant role {participant.role!r}")
        if not participant.name.strip():
            raise ValueError(
                f"Claim participant {participant.entity_id} has no entity name"
            )
        normalized.append(participant)
    return tuple(normalized)


def _tier_for_role(role: str) -> str:
    if role in PARTICIPANT_ROLES:
        return "participant"
    if role in WITNESS_ROLES:
        return "witness"
    raise ValueError(f"Unknown awareness role {role!r}")


def _aware_participants(
    participants: Sequence[ClaimParticipant], policy: EpistemicsPolicy
) -> tuple[tuple[int, str], ...]:
    by_entity: dict[int, str] = {}
    for participant in participants:
        if participant.role not in policy.aware_roles:
            continue
        tier = _tier_for_role(participant.role)
        current = by_entity.get(participant.entity_id)
        if current is None or (current == "witness" and tier == "participant"):
            by_entity[participant.entity_id] = tier
    return tuple(sorted(by_entity.items()))


def _mint_awareness_sync(
    cur: Any,
    *,
    claim_id: int,
    participants: Sequence[ClaimParticipant],
    policy: EpistemicsPolicy,
    source_chunk_id: Optional[int],
) -> tuple[int, ...]:
    awareness_ids = []
    world_time = _acquisition_world_time_sync(cur, source_chunk_id)
    for entity_id, tier in _aware_participants(participants, policy):
        cur.execute(
            """
            INSERT INTO claim_awareness (
                claim_id, knower_entity_id, source_tier, source_chunk_id,
                acquired_at_world_time
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (claim_id, knower_entity_id) DO NOTHING
            RETURNING id
            """,
            (claim_id, entity_id, tier, source_chunk_id, world_time),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                SELECT id FROM claim_awareness
                WHERE claim_id = %s AND knower_entity_id = %s
                """,
                (claim_id, entity_id),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(
                    f"Awareness conflict for claim {claim_id}, entity {entity_id} "
                    "had no existing row"
                )
        awareness_ids.append(int(_row_value(row, "id", 0)))
    return tuple(awareness_ids)


async def _mint_awareness_async(
    conn: Any,
    *,
    claim_id: int,
    participants: Sequence[ClaimParticipant],
    policy: EpistemicsPolicy,
    source_chunk_id: Optional[int],
) -> tuple[int, ...]:
    awareness_ids = []
    world_time = await _acquisition_world_time_async(conn, source_chunk_id)
    for entity_id, tier in _aware_participants(participants, policy):
        awareness_id = await conn.fetchval(
            """
            INSERT INTO claim_awareness (
                claim_id, knower_entity_id, source_tier, source_chunk_id,
                acquired_at_world_time
            ) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (claim_id, knower_entity_id) DO NOTHING
            RETURNING id
            """,
            claim_id,
            entity_id,
            tier,
            source_chunk_id,
            world_time,
        )
        if awareness_id is None:
            awareness_id = await conn.fetchval(
                """
                SELECT id FROM claim_awareness
                WHERE claim_id = $1 AND knower_entity_id = $2
                """,
                claim_id,
                entity_id,
            )
            if awareness_id is None:
                raise RuntimeError(
                    f"Awareness conflict for claim {claim_id}, entity {entity_id} "
                    "had no existing row"
                )
        awareness_ids.append(int(awareness_id))
    return tuple(awareness_ids)


def _acquisition_world_time_sync(
    cur: Any, source_chunk_id: Optional[int]
) -> Optional[datetime]:
    """Load the acquisition's diegetic clock without a wall-time fallback."""

    if source_chunk_id is not None:
        cur.execute(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
            (source_chunk_id,),
        )
    else:
        cur.execute("SELECT max(world_time) AS world_time FROM chunk_metadata")
    row = cur.fetchone()
    return _row_value(row, "world_time", 0) if row else None


async def _acquisition_world_time_async(
    conn: Any, source_chunk_id: Optional[int]
) -> Optional[datetime]:
    """Async twin of :func:`_acquisition_world_time_sync`."""

    if source_chunk_id is not None:
        return await conn.fetchval(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id = $1",
            source_chunk_id,
        )
    return await conn.fetchval("SELECT max(world_time) FROM chunk_metadata")


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    try:
        return row[index]
    except (KeyError, TypeError):
        return getattr(row, key)
