"""Event-anchored claims and entity awareness for Orrery Epistemics v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import text


CLAIM_SCOPES = frozenset({"common", "bounded", "private"})
CLAIM_PROPAGATED_EVENT_TYPE = "claim_propagated"
EVENT_ROLES = frozenset({"actor", "target", "observer", "witness", "beneficiary"})
PARTICIPANT_ROLES = frozenset({"actor", "target", "beneficiary"})
WITNESS_ROLES = frozenset({"observer", "witness"})
SOURCE_TIERS = frozenset({"participant", "witness", "told", "granted"})


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
class ClaimKnowledge:
    """One hydrated claim-possession record consumed by package predicates."""

    claim_id: int
    world_event_id: int
    scope: str
    source_tier: str
    about_entity_ids: frozenset[int]
    channel: Optional[str] = None
    immediate_source_entity_id: Optional[int] = None


@dataclass(frozen=True, slots=True)
class EpistemicsHydration:
    """Complete claim projection plus the legacy recent-event lookup shapes."""

    claimed_event_scopes: Mapping[int, str]
    awareness_by_entity: Mapping[int, frozenset[int]]
    claim_knowledge_by_entity: Mapping[int, tuple[ClaimKnowledge, ...]]
    common_claim_knowledge: tuple[ClaimKnowledge, ...]
    possessed_claim_knowledge_by_entity: Mapping[int, tuple[ClaimKnowledge, ...]]


def coerce_epistemics_policy(raw: Any) -> EpistemicsPolicy:
    """Normalize a Pydantic model or mapping into strict runtime policy."""

    if raw is None:
        return EpistemicsPolicy()
    if isinstance(raw, EpistemicsPolicy):
        policy = raw
        if CLAIM_PROPAGATED_EVENT_TYPE in policy.claim_event_types:
            raise ValueError(
                "claim_propagated cannot appear in Epistemics claim_event_types"
            )
        return policy
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, Mapping):
        raise TypeError("Epistemics settings must be a mapping or Pydantic model")
    event_types = [str(value).strip() for value in raw.get("claim_event_types", ())]
    aware_roles = [str(value).strip() for value in raw.get("aware_roles", ())]
    if any(not value for value in event_types):
        raise ValueError("Epistemics claim_event_types entries must be non-empty")
    if CLAIM_PROPAGATED_EVENT_TYPE in event_types:
        raise ValueError(
            "claim_propagated cannot appear in Epistemics claim_event_types"
        )
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

    if event_type == CLAIM_PROPAGATED_EVENT_TYPE:
        return None
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
            world_event_id, account_label, summary, scope, source_chunk_id,
            source_resolution_id
        ) VALUES (%s, 'canonical', %s, 'bounded', %s, %s)
        ON CONFLICT (world_event_id, account_label)
            WHERE world_event_id IS NOT NULL DO NOTHING
        RETURNING id
        """,
        (world_event_id, clean_summary, source_chunk_id, source_resolution_id),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "SELECT id FROM claims "
            "WHERE world_event_id = %s AND account_label = 'canonical'",
            (world_event_id,),
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

    if event_type == CLAIM_PROPAGATED_EVENT_TYPE:
        return None
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
            world_event_id, account_label, summary, scope, source_chunk_id,
            source_resolution_id
        ) VALUES ($1, 'canonical', $2, 'bounded', $3, $4)
        ON CONFLICT (world_event_id, account_label)
            WHERE world_event_id IS NOT NULL DO NOTHING
        RETURNING id
        """,
        world_event_id,
        clean_summary,
        source_chunk_id,
        source_resolution_id,
    )
    if claim_id is None:
        claim_id = await conn.fetchval(
            "SELECT id FROM claims "
            "WHERE world_event_id = $1 AND account_label = 'canonical'",
            world_event_id,
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


def mint_account_variant_sync(
    cur: Any,
    *,
    source_claim_id: int,
    account_label: str,
    summary: str,
    source_chunk_id: Optional[int],
    account_payload: Optional[Mapping[str, Any]] = None,
    distorted_from_claim_id: Optional[int] = None,
) -> int:
    """Mint one non-awareness sibling account from an existing claim."""

    clean_label = account_label.strip()
    clean_summary = summary.strip()
    if not clean_label:
        raise ValueError("Account label must be non-empty")
    if not clean_summary:
        raise ValueError("Account variant summary must be non-empty")
    cur.execute(
        "SELECT world_event_id, scope FROM claims WHERE id = %s FOR SHARE",
        (source_claim_id,),
    )
    source = cur.fetchone()
    if source is None:
        raise ValueError(f"Source claim {source_claim_id} does not exist")
    source_event_id = int(_row_value(source, "world_event_id", 0))
    parent_claim_id = (
        source_claim_id if distorted_from_claim_id is None else distorted_from_claim_id
    )
    if distorted_from_claim_id is not None:
        cur.execute(
            "SELECT world_event_id FROM claims WHERE id = %s FOR SHARE",
            (distorted_from_claim_id,),
        )
        parent = cur.fetchone()
        if parent is None:
            raise ValueError(
                f"Lineage parent claim {distorted_from_claim_id} does not exist"
            )
        parent_event_id = int(_row_value(parent, "world_event_id", 0))
        if parent_event_id != source_event_id:
            raise ValueError(
                f"Lineage parent claim {distorted_from_claim_id} belongs to world "
                f"event {parent_event_id}; source claim {source_claim_id} belongs "
                f"to world event {source_event_id}"
            )
    payload_json = _account_payload_json(account_payload)
    cur.execute(
        """
        INSERT INTO claims (
            world_event_id, account_label, account_payload,
            distorted_from_claim_id, summary, scope, source_chunk_id
        ) VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            source_event_id,
            clean_label,
            payload_json,
            parent_claim_id,
            clean_summary,
            _row_value(source, "scope", 1),
            source_chunk_id,
        ),
    )
    inserted = cur.fetchone()
    if inserted is None:
        raise RuntimeError("Account variant INSERT returned no claim id")
    return int(_row_value(inserted, "id", 0))


async def mint_account_variant_async(
    conn: Any,
    *,
    source_claim_id: int,
    account_label: str,
    summary: str,
    source_chunk_id: Optional[int],
    account_payload: Optional[Mapping[str, Any]] = None,
    distorted_from_claim_id: Optional[int] = None,
) -> int:
    """Asyncpg twin of :func:`mint_account_variant_sync`."""

    clean_label = account_label.strip()
    clean_summary = summary.strip()
    if not clean_label:
        raise ValueError("Account label must be non-empty")
    if not clean_summary:
        raise ValueError("Account variant summary must be non-empty")
    source = await conn.fetchrow(
        "SELECT world_event_id, scope FROM claims WHERE id = $1 FOR SHARE",
        source_claim_id,
    )
    if source is None:
        raise ValueError(f"Source claim {source_claim_id} does not exist")
    source_event_id = int(source["world_event_id"])
    parent_claim_id = (
        source_claim_id if distorted_from_claim_id is None else distorted_from_claim_id
    )
    if distorted_from_claim_id is not None:
        parent_event_id = await conn.fetchval(
            "SELECT world_event_id FROM claims WHERE id = $1 FOR SHARE",
            distorted_from_claim_id,
        )
        if parent_event_id is None:
            raise ValueError(
                f"Lineage parent claim {distorted_from_claim_id} does not exist"
            )
        if int(parent_event_id) != source_event_id:
            raise ValueError(
                f"Lineage parent claim {distorted_from_claim_id} belongs to world "
                f"event {int(parent_event_id)}; source claim {source_claim_id} belongs "
                f"to world event {source_event_id}"
            )
    claim_id = await conn.fetchval(
        """
        INSERT INTO claims (
            world_event_id, account_label, account_payload,
            distorted_from_claim_id, summary, scope, source_chunk_id
        ) VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
        RETURNING id
        """,
        source_event_id,
        clean_label,
        _account_payload_json(account_payload),
        parent_claim_id,
        clean_summary,
        source["scope"],
        source_chunk_id,
    )
    if claim_id is None:
        raise RuntimeError("Account variant INSERT returned no claim id")
    return int(claim_id)


def _account_payload_json(
    account_payload: Optional[Mapping[str, Any]],
) -> Optional[str]:
    """Serialize structured account content deterministically or fail loudly."""

    if account_payload is None:
        return None
    return json.dumps(
        dict(account_payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def author_backstory_secret_sync(
    cur: Any,
    *,
    claim_id: int,
    gate_template_id: str,
    holder_entity_id: int,
    source_chunk_id: int,
) -> int:
    """Author one private claim as a durable template-gated secret."""

    from nexus.agents.orrery.reveal_gates import REVEAL_GATES

    cur.execute("SELECT scope FROM claims WHERE id = %s", (claim_id,))
    claim = cur.fetchone()
    if claim is None:
        raise ValueError(f"Claim {claim_id} does not exist")
    scope = str(_row_value(claim, "scope", 0))
    if scope != "private":
        raise ValueError(
            f"Backstory secret claim {claim_id} must be private, not {scope!r}"
        )
    if gate_template_id not in REVEAL_GATES:
        raise ValueError(f"Unregistered reveal gate {gate_template_id!r}")
    cur.execute("SELECT 1 FROM entities WHERE id = %s", (holder_entity_id,))
    if cur.fetchone() is None:
        raise ValueError(f"Secret holder entity {holder_entity_id} does not exist")
    cur.execute(
        """
        SELECT world_time, world_layer::text AS world_layer
        FROM chunk_metadata
        WHERE chunk_id = %s
        """,
        (source_chunk_id,),
    )
    clock = cur.fetchone()
    if clock is None:
        raise ValueError(f"Secret source chunk {source_chunk_id} has no metadata")
    cur.execute(
        """
        INSERT INTO backstory_secrets (
            claim_id, gate_template_id, holder_entity_id, source_chunk_id
        ) VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (claim_id, gate_template_id, holder_entity_id, source_chunk_id),
    )
    secret_id = int(_row_value(cur.fetchone(), "id", 0))
    record_revelation(
        cur,
        claim_id=claim_id,
        knower_entity_id=holder_entity_id,
        world_time=_row_value(clock, "world_time", 0),
        source_chunk_id=source_chunk_id,
    )
    payload = json.dumps(
        {
            "claim_id": claim_id,
            "gate_template_id": gate_template_id,
            "holder_entity_id": holder_entity_id,
            "secret_id": secret_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, world_layer, source,
            changed_fields, payload, world_time
        ) VALUES (
            'backstory_secret_authored', %s, %s, %s::world_layer_type,
            'authored', ARRAY['backstory_secrets']::text[], %s::jsonb, %s
        )
        """,
        (
            source_chunk_id,
            holder_entity_id,
            _row_value(clock, "world_layer", 1),
            payload,
            _row_value(clock, "world_time", 0),
        ),
    )
    return secret_id


async def author_backstory_secret_async(
    conn: Any,
    *,
    claim_id: int,
    gate_template_id: str,
    holder_entity_id: int,
    source_chunk_id: int,
) -> int:
    """Asyncpg twin of :func:`author_backstory_secret_sync`."""

    from nexus.agents.orrery.reveal_gates import REVEAL_GATES

    scope = await conn.fetchval("SELECT scope FROM claims WHERE id = $1", claim_id)
    if scope is None:
        raise ValueError(f"Claim {claim_id} does not exist")
    if str(scope) != "private":
        raise ValueError(
            f"Backstory secret claim {claim_id} must be private, not {str(scope)!r}"
        )
    if gate_template_id not in REVEAL_GATES:
        raise ValueError(f"Unregistered reveal gate {gate_template_id!r}")
    holder_exists = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM entities WHERE id = $1)", holder_entity_id
    )
    if not holder_exists:
        raise ValueError(f"Secret holder entity {holder_entity_id} does not exist")
    clock = await conn.fetchrow(
        """
        SELECT world_time, world_layer::text AS world_layer
        FROM chunk_metadata
        WHERE chunk_id = $1
        """,
        source_chunk_id,
    )
    if clock is None:
        raise ValueError(f"Secret source chunk {source_chunk_id} has no metadata")
    secret_id = await conn.fetchval(
        """
        INSERT INTO backstory_secrets (
            claim_id, gate_template_id, holder_entity_id, source_chunk_id
        ) VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        claim_id,
        gate_template_id,
        holder_entity_id,
        source_chunk_id,
    )
    await record_revelation_async(
        conn,
        claim_id=claim_id,
        knower_entity_id=holder_entity_id,
        world_time=clock["world_time"],
        source_chunk_id=source_chunk_id,
    )
    payload = json.dumps(
        {
            "claim_id": claim_id,
            "gate_template_id": gate_template_id,
            "holder_entity_id": holder_entity_id,
            "secret_id": int(secret_id),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    await conn.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, world_layer, source,
            changed_fields, payload, world_time
        ) VALUES (
            'backstory_secret_authored', $1, $2, $3::world_layer_type,
            'authored', ARRAY['backstory_secrets']::text[], $4::jsonb, $5
        )
        """,
        source_chunk_id,
        holder_entity_id,
        clock["world_layer"],
        payload,
        clock["world_time"],
    )
    return int(secret_id)


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


async def record_revelation_async(
    conn: Any,
    *,
    claim_id: int,
    knower_entity_id: int,
    source_entity_id: Optional[int] = None,
    channel: Optional[str] = None,
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
) -> RevelationResult:
    """Asyncpg twin of :func:`record_revelation`."""

    source_tier = "told" if source_entity_id is not None else "granted"
    root_source_entity_id = None
    if source_entity_id is not None:
        scope = await conn.fetchval("SELECT scope FROM claims WHERE id = $1", claim_id)
        if scope is None:
            raise ValueError(f"Claim {claim_id} does not exist")
        if str(scope) == "common":
            root_source_entity_id = source_entity_id
        else:
            source_awareness = await conn.fetchrow(
                """
                SELECT root_source_entity_id
                FROM claim_awareness
                WHERE claim_id = $1 AND knower_entity_id = $2
                """,
                claim_id,
                source_entity_id,
            )
            if source_awareness is None:
                raise ValueError(
                    f"Entity {source_entity_id} cannot reveal claim {claim_id}: "
                    "the teller does not possess it"
                )
            inherited_root = source_awareness["root_source_entity_id"]
            root_source_entity_id = (
                int(inherited_root) if inherited_root is not None else source_entity_id
            )
    row = await conn.fetchrow(
        """
        INSERT INTO claim_awareness (
            claim_id, knower_entity_id, source_tier,
            immediate_source_entity_id, root_source_entity_id, channel,
            acquired_at_world_time, source_chunk_id
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (claim_id, knower_entity_id) DO NOTHING
        RETURNING id, source_tier
        """,
        claim_id,
        knower_entity_id,
        source_tier,
        source_entity_id,
        root_source_entity_id,
        channel,
        world_time,
        source_chunk_id,
    )
    inserted = row is not None
    if row is None:
        row = await conn.fetchrow(
            """
            SELECT id, source_tier FROM claim_awareness
            WHERE claim_id = $1 AND knower_entity_id = $2
            """,
            claim_id,
            knower_entity_id,
        )
        if row is None:
            raise RuntimeError(
                "Awareness conflict did not resolve to an existing row for "
                f"claim {claim_id}, entity {knower_entity_id}"
            )
    return RevelationResult(
        awareness_id=int(row["id"]),
        source_tier=str(row["source_tier"]),
        inserted=inserted,
    )


def promote_claim_scope(cur: Any, *, claim_id: int, new_scope: str) -> None:
    """Move promotable sibling accounts into bounded spreadability."""

    if new_scope not in CLAIM_SCOPES:
        raise ValueError(f"Unknown claim scope {new_scope!r}")
    # Keep this latent-secret filter aligned with _merge_sibling_scope below:
    # hydration permits exactly the temporary divergence created here.
    cur.execute(
        """
        SELECT sibling.id, sibling.scope
        FROM claims target
        JOIN claims sibling
          ON sibling.world_event_id = target.world_event_id
        LEFT JOIN backstory_secrets latent_secret
          ON latent_secret.claim_id = sibling.id
         AND latent_secret.status = 'latent'
        WHERE target.id = %s
          AND latent_secret.id IS NULL
        ORDER BY sibling.id
        FOR UPDATE OF sibling
        """,
        (claim_id,),
    )
    siblings = cur.fetchall()
    if not siblings:
        raise ValueError(f"Claim {claim_id} does not exist")
    target = next(
        (row for row in siblings if int(_row_value(row, "id", 0)) == claim_id),
        None,
    )
    if target is None:
        raise RuntimeError(f"Claim {claim_id} disappeared during scope promotion")
    current_scope = str(_row_value(target, "scope", 1))
    if new_scope != current_scope and new_scope != "bounded":
        raise ValueError(
            f"Illegal claim scope transition {current_scope!r} -> {new_scope!r}"
        )
    cur.execute(
        """
        WITH promotable AS (
            SELECT sibling.id
            FROM claims target
            JOIN claims sibling
              ON sibling.world_event_id = target.world_event_id
            LEFT JOIN backstory_secrets latent_secret
              ON latent_secret.claim_id = sibling.id
             AND latent_secret.status = 'latent'
            WHERE target.id = %s
              AND latent_secret.id IS NULL
        )
        UPDATE claims promoted
        SET scope = %s
        FROM promotable
        WHERE promoted.id = promotable.id
        """,
        (claim_id, new_scope),
    )


async def promote_claim_scope_async(
    conn: Any, *, claim_id: int, new_scope: str
) -> None:
    """Asyncpg twin of :func:`promote_claim_scope`."""

    if new_scope not in CLAIM_SCOPES:
        raise ValueError(f"Unknown claim scope {new_scope!r}")
    # Async parity for the promotion/hydration contract documented above.
    siblings = await conn.fetch(
        """
        SELECT sibling.id, sibling.scope
        FROM claims target
        JOIN claims sibling
          ON sibling.world_event_id = target.world_event_id
        LEFT JOIN backstory_secrets latent_secret
          ON latent_secret.claim_id = sibling.id
         AND latent_secret.status = 'latent'
        WHERE target.id = $1
          AND latent_secret.id IS NULL
        ORDER BY sibling.id
        FOR UPDATE OF sibling
        """,
        claim_id,
    )
    if not siblings:
        raise ValueError(f"Claim {claim_id} does not exist")
    target = next((row for row in siblings if int(row["id"]) == claim_id), None)
    if target is None:
        raise RuntimeError(f"Claim {claim_id} disappeared during scope promotion")
    current_scope = str(target["scope"])
    if new_scope != current_scope and new_scope != "bounded":
        raise ValueError(
            f"Illegal claim scope transition {current_scope!r} -> {new_scope!r}"
        )
    await conn.execute(
        """
        WITH promotable AS (
            SELECT sibling.id
            FROM claims target
            JOIN claims sibling
              ON sibling.world_event_id = target.world_event_id
            LEFT JOIN backstory_secrets latent_secret
              ON latent_secret.claim_id = sibling.id
             AND latent_secret.status = 'latent'
            WHERE target.id = $1
              AND latent_secret.id IS NULL
        )
        UPDATE claims promoted
        SET scope = $2
        FROM promotable
        WHERE promoted.id = promotable.id
        """,
        claim_id,
        new_scope,
    )


def _merge_sibling_scope(
    *,
    event_id: int,
    rows: list[tuple[str, bool]],
) -> str:
    """Validate one incident's sibling scopes and return its shared scope."""

    scopes = {scope for scope, _is_latent_secret in rows}
    if len(scopes) == 1:
        return next(iter(scopes))

    # Keep this exact exemption aligned with promote_claim_scope above: that
    # writer skips private claims bound to latent backstory secrets so one
    # reveal cannot expose a sibling whose own gate has not fired.
    exempt_private = scopes == {"bounded", "private"} and all(
        is_latent_secret for scope, is_latent_secret in rows if scope == "private"
    )
    if exempt_private:
        return "bounded"
    raise ValueError(
        "Sibling claims on event "
        f"{event_id} have divergent scopes {sorted(scopes)!r}; only a private "
        "claim bound to a latent backstory secret may coexist with bounded "
        "siblings"
    )


def load_epistemics_hydration(
    session: Any,
    *,
    entity_ids: Iterable[int],
    recent_event_ids: Iterable[int],
    anchor_chunk_id: Optional[int],
) -> EpistemicsHydration:
    """Hydrate anchor-visible claim possession for an explicit entity universe.

    ``knows_recent_event`` receives scope existence for every recent event,
    independent of whether its participants remain active. Claim predicates
    additionally need time-unbounded possession and every entity involved in
    the minting event. A non-common claim is relevant when either an active
    knower or an about-entity intersects ``entity_ids``; common claims are
    relevant only through their about-entities. Claim subjects and awareness
    are loaded on separate axes, so neither can multiply the other. No
    predicate performs follow-up SQL. ``None`` retains the unbounded
    current-table view for direct callers without a historical anchor.
    """

    universe = tuple(sorted({int(entity_id) for entity_id in entity_ids}))
    recent_events = tuple(sorted({int(event_id) for event_id in recent_event_ids}))
    if not universe and not recent_events:
        return EpistemicsHydration(
            claimed_event_scopes={},
            awareness_by_entity={},
            claim_knowledge_by_entity={},
            common_claim_knowledge=(),
            possessed_claim_knowledge_by_entity={},
        )

    availability = (
        session.execute(
            text(
                """
                /* orrery:epistemics_hydration:backstory_availability */
                SELECT to_regclass('backstory_secrets') IS NOT NULL AS available
                """
            )
        )
        .mappings()
        .first()
    )
    backstory_available = bool(availability and availability["available"])
    # A pre-091 schema cannot contain latent backstory bindings. Rendering a
    # literal false keeps all divergence shapes loud until the table exists.
    latent_secret_flag = (
        """
        EXISTS (
            SELECT 1
            FROM backstory_secrets latent_secret
            WHERE latent_secret.claim_id = c.id
              AND latent_secret.status = 'latent'
        )
        """
        if backstory_available
        else "false"
    )

    scopes: dict[int, str] = {}
    if recent_events:
        scope_query = text(
            f"""
            /* orrery:epistemics_hydration:recent_event_scopes */
            SELECT c.id AS claim_id,
                   c.world_event_id,
                   c.scope,
                   {latent_secret_flag} AS is_latent_backstory_secret
            FROM claims c
            JOIN world_events we ON we.id = c.world_event_id
            WHERE c.world_event_id = ANY(:recent_event_ids)
              AND (:anchor_chunk_id IS NULL
                   OR we.tick_chunk_id <= :anchor_chunk_id)
            ORDER BY c.world_event_id, c.id
            """
        )
        scope_rows_by_event: dict[int, list[tuple[str, bool]]] = {}
        for row in session.execute(
            scope_query,
            {
                "recent_event_ids": list(recent_events),
                "anchor_chunk_id": anchor_chunk_id,
            },
        ).mappings():
            event_id = int(row["world_event_id"])
            scope = str(row["scope"])
            if scope not in CLAIM_SCOPES:
                raise ValueError(
                    f"Claim on event {event_id} has unknown scope {scope!r}"
                )
            scope_rows_by_event.setdefault(event_id, []).append(
                (scope, bool(row.get("is_latent_backstory_secret", False)))
            )
        for event_id, sibling_rows in scope_rows_by_event.items():
            # Legacy recent-event predicates are incident-level: possession
            # of any sibling account admits the shared event. Account-aware
            # predicates remain claim-id keyed below.
            scopes[event_id] = _merge_sibling_scope(
                event_id=event_id,
                rows=sibling_rows,
            )

    if not universe:
        return EpistemicsHydration(
            claimed_event_scopes=scopes,
            awareness_by_entity={},
            claim_knowledge_by_entity={},
            common_claim_knowledge=(),
            possessed_claim_knowledge_by_entity={},
        )

    claims_query = text(
        f"""
        /* orrery:epistemics_hydration:claims */
        WITH anchor AS (
            SELECT created_at
            FROM narrative_chunks
            WHERE id = :anchor_chunk_id
        ),
        relevant_claim_ids AS (
            SELECT c.id AS claim_id
            FROM claims c
            JOIN world_events we ON we.id = c.world_event_id
            WHERE (:anchor_chunk_id IS NULL
                   OR we.tick_chunk_id <= :anchor_chunk_id)
              AND (we.actor_entity_id = ANY(:entity_ids)
                   OR we.target_entity_id = ANY(:entity_ids))
            UNION
            SELECT c.id AS claim_id
            FROM claims c
            JOIN world_event_entities wee ON wee.event_id = c.world_event_id
            JOIN world_events we ON we.id = c.world_event_id
            WHERE (:anchor_chunk_id IS NULL
                   OR we.tick_chunk_id <= :anchor_chunk_id)
              AND wee.entity_id = ANY(:entity_ids)
            UNION
            SELECT ca.claim_id
            FROM claim_awareness ca
            JOIN claims c ON c.id = ca.claim_id
            JOIN world_events we ON we.id = c.world_event_id
            WHERE c.scope <> 'common'
              AND ca.knower_entity_id = ANY(:entity_ids)
              AND (:anchor_chunk_id IS NULL
                   OR we.tick_chunk_id <= :anchor_chunk_id)
              -- Mirror replay.py's claim-awareness readmission visibility.
              AND (
                  :anchor_chunk_id IS NULL
                  OR (ca.source_chunk_id IS NOT NULL
                      AND ca.source_chunk_id <= :anchor_chunk_id)
                  OR (ca.source_chunk_id IS NULL
                      AND ca.created_at <= (SELECT created_at FROM anchor))
              )
        ),
        claim_entities AS (
            SELECT relevant.claim_id, subjects.entity_id
            FROM relevant_claim_ids relevant
            JOIN claims c ON c.id = relevant.claim_id
            JOIN world_events we ON we.id = c.world_event_id
            JOIN LATERAL (
                SELECT we.actor_entity_id AS entity_id
                WHERE we.actor_entity_id IS NOT NULL
                UNION
                SELECT we.target_entity_id AS entity_id
                WHERE we.target_entity_id IS NOT NULL
                UNION
                SELECT wee.entity_id
                FROM world_event_entities wee
                WHERE wee.event_id = we.id
            ) subjects ON true
        ),
        about_by_claim AS (
            SELECT claim_id,
                   array_agg(entity_id ORDER BY entity_id) AS about_entity_ids
            FROM claim_entities
            GROUP BY claim_id
        )
        SELECT c.id AS claim_id,
               c.world_event_id,
               c.scope,
               {latent_secret_flag} AS is_latent_backstory_secret,
               COALESCE(
                   about.about_entity_ids,
                   ARRAY[]::bigint[]
               ) AS about_entity_ids
        FROM relevant_claim_ids relevant
        JOIN claims c ON c.id = relevant.claim_id
        LEFT JOIN about_by_claim about ON about.claim_id = c.id
        WHERE c.scope <> 'common'
           OR COALESCE(about.about_entity_ids, ARRAY[]::bigint[])
              && CAST(:entity_ids AS bigint[])
        ORDER BY c.id
        """
    )
    claims: dict[int, dict[str, Any]] = {}
    hydrated_scope_rows: dict[int, list[tuple[str, bool]]] = {}
    for row in session.execute(
        claims_query,
        {
            "entity_ids": list(universe),
            "anchor_chunk_id": anchor_chunk_id,
        },
    ).mappings():
        claim_id = int(row["claim_id"])
        event_id = int(row["world_event_id"])
        scope = str(row["scope"])
        if scope not in CLAIM_SCOPES:
            raise ValueError(f"Claim on event {event_id} has unknown scope {scope!r}")
        hydrated_scope_rows.setdefault(event_id, []).append(
            (scope, bool(row.get("is_latent_backstory_secret", False)))
        )
        claims[claim_id] = {
            "world_event_id": event_id,
            "scope": scope,
            "about_entity_ids": frozenset(
                int(entity_id) for entity_id in (row["about_entity_ids"] or ())
            ),
        }
    for event_id, sibling_rows in hydrated_scope_rows.items():
        _merge_sibling_scope(event_id=event_id, rows=sibling_rows)

    awareness: dict[int, set[int]] = {}
    awareness_rows: dict[tuple[int, int], dict[str, Any]] = {}
    if claims:
        awareness_query = text(
            """
            /* orrery:epistemics_hydration:awareness */
            WITH anchor AS (
                SELECT created_at
                FROM narrative_chunks
                WHERE id = :anchor_chunk_id
            )
            SELECT ca.claim_id,
                   ca.knower_entity_id,
                   ca.source_tier,
                   ca.channel,
                   ca.immediate_source_entity_id
            FROM claim_awareness ca
            WHERE ca.claim_id = ANY(:claim_ids)
              AND ca.knower_entity_id = ANY(:entity_ids)
              -- Mirror replay.py's claim-awareness readmission visibility.
              AND (
                  :anchor_chunk_id IS NULL
                  OR (ca.source_chunk_id IS NOT NULL
                      AND ca.source_chunk_id <= :anchor_chunk_id)
                  OR (ca.source_chunk_id IS NULL
                      AND ca.created_at <= (SELECT created_at FROM anchor))
              )
            ORDER BY ca.claim_id, ca.knower_entity_id
            """
        )
        awareness_results = session.execute(
            awareness_query,
            {
                "claim_ids": sorted(claims),
                "entity_ids": list(universe),
                "anchor_chunk_id": anchor_chunk_id,
            },
        ).mappings()
    else:
        awareness_results = ()

    for row in awareness_results:
        claim_id = int(row["claim_id"])
        event_id = int(claims[claim_id]["world_event_id"])
        knower_entity_id = row["knower_entity_id"]
        knower_id = int(knower_entity_id)
        source_tier = str(row["source_tier"])
        if source_tier not in SOURCE_TIERS:
            raise ValueError(
                f"Claim {claim_id} has unknown awareness tier {source_tier!r}"
            )
        # Event-level knowledge intentionally collapses sibling possession;
        # claim_knowledge below preserves the exact possessed account id.
        awareness.setdefault(knower_id, set()).add(event_id)
        awareness_rows.setdefault(
            (claim_id, knower_id),
            {
                "source_tier": source_tier,
                "channel": row["channel"],
                "immediate_source_entity_id": row["immediate_source_entity_id"],
            },
        )

    claim_knowledge: dict[int, list[ClaimKnowledge]] = {}
    for (claim_id, knower_id), row in sorted(awareness_rows.items()):
        claim = claims[claim_id]
        immediate_source = row["immediate_source_entity_id"]
        claim_knowledge.setdefault(knower_id, []).append(
            ClaimKnowledge(
                claim_id=claim_id,
                world_event_id=int(claim["world_event_id"]),
                scope=str(claim["scope"]),
                source_tier=str(row["source_tier"]),
                about_entity_ids=frozenset(claim["about_entity_ids"]),
                channel=(str(row["channel"]) if row["channel"] is not None else None),
                immediate_source_entity_id=(
                    int(immediate_source) if immediate_source is not None else None
                ),
            )
        )

    common_claims = tuple(
        ClaimKnowledge(
            claim_id=claim_id,
            world_event_id=int(claim["world_event_id"]),
            scope="common",
            source_tier="common",
            about_entity_ids=frozenset(claim["about_entity_ids"]),
        )
        for claim_id, claim in sorted(claims.items())
        if claim["scope"] == "common"
    )
    explicit_claims = {
        entity_id: tuple(records) for entity_id, records in claim_knowledge.items()
    }
    return EpistemicsHydration(
        claimed_event_scopes=scopes,
        awareness_by_entity={
            entity_id: frozenset(events) for entity_id, events in awareness.items()
        },
        claim_knowledge_by_entity=explicit_claims,
        common_claim_knowledge=common_claims,
        possessed_claim_knowledge_by_entity=_merge_possessed_claim_knowledge(
            universe,
            explicit_claims=explicit_claims,
            common_claims=common_claims,
        ),
    )


def _merge_possessed_claim_knowledge(
    entity_ids: Iterable[int],
    *,
    explicit_claims: Mapping[int, tuple[ClaimKnowledge, ...]],
    common_claims: tuple[ClaimKnowledge, ...],
) -> dict[int, tuple[ClaimKnowledge, ...]]:
    """Precompute deterministic universal-plus-explicit possession by entity."""

    common_by_claim_id = {record.claim_id: record for record in common_claims}
    possessed: dict[int, tuple[ClaimKnowledge, ...]] = {}
    for entity_id in sorted({int(value) for value in entity_ids}):
        by_claim_id = dict(common_by_claim_id)
        by_claim_id.update(
            {record.claim_id: record for record in explicit_claims.get(entity_id, ())}
        )
        possessed[entity_id] = tuple(
            by_claim_id[claim_id] for claim_id in sorted(by_claim_id)
        )
    return possessed


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
        return current_world_time_sync(cur)
    row = cur.fetchone()
    return _row_value(row, "world_time", 0) if row else None


def current_world_time_sync(cur: Any) -> Optional[datetime]:
    """Return the current diegetic clock, or ``None`` in a clockless world."""

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
