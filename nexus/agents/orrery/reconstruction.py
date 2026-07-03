"""State checkpoints and delta logging for reconstruction sufficiency.

Implements the 7b/7c halves of the reconstruction bar
(docs/orrery_audit_dashboard_notes.md; decisions on issue #426): JSONB
checkpoints of the whole mutable state surface, auto-taken in the commit
path every ``[orrery.reconstruction] checkpoint_interval_chunks`` accepted
chunks, plus the Skald-side ``state_delta_log`` writer helpers.

Replay contract: world state at chunk T = the latest checkpoint at or before
T, plus ``orrery_resolutions.state_delta`` and ``state_delta_log`` rows in
chunk order up to T. Relationship pre-images live in
``relationship_versions`` (trigger-enforced, 7d).
"""

from __future__ import annotations

import json
from typing import Any, Optional

# Every mutable table the resolver's hydration or the Skald commit path can
# read or write. A checkpoint is one JSONB document with one array per entry.
# Order is presentation-only; each section is captured atomically inside the
# caller's transaction.
CHECKPOINT_SECTIONS: dict[str, str] = {
    "entity_tags": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM (SELECT * FROM entity_tags WHERE cleared_at IS NULL) t"
    ),
    "entity_pair_tags": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM (SELECT * FROM entity_pair_tags WHERE cleared_at IS NULL) t"
    ),
    "characters": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM (SELECT id, entity_id, current_location, current_activity, "
        "emotional_state FROM characters) t"
    ),
    "places": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM (SELECT id, entity_id, current_status FROM places) t"
    ),
    "character_relationships": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM character_relationships t"
    ),
    "faction_character_relationships": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM faction_character_relationships t"
    ),
    "faction_relationships": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM faction_relationships t"
    ),
    "character_need_states": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM character_need_states t"
    ),
    "character_travel_states": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM character_travel_states t"
    ),
    "character_routine_anchors": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM character_routine_anchors t"
    ),
}

CHECKPOINT_LABELS = ("genesis", "interval", "manual")


def _validate_label(label: str) -> None:
    if label not in CHECKPOINT_LABELS:
        raise ValueError(
            f"Unknown checkpoint label {label!r}; expected one of "
            f"{CHECKPOINT_LABELS}"
        )


def capture_state_checkpoint_sync(
    cur: Any,
    *,
    chunk_id: Optional[int],
    label: str,
) -> Optional[int]:
    """Snapshot the mutable state surface. Returns the checkpoint id, or
    ``None`` when a checkpoint for ``(chunk_id, label)`` already exists
    (idempotent re-commit)."""

    _validate_label(label)
    state: dict[str, Any] = {}
    for section, sql in CHECKPOINT_SECTIONS.items():
        cur.execute(sql)
        row = cur.fetchone()
        state[section] = row[0] if not hasattr(row, "keys") else list(row.values())[0]
    cur.execute(
        """
        INSERT INTO state_checkpoints (chunk_id, label, state)
        VALUES (%s, %s, %s::jsonb)
        ON CONFLICT (chunk_id, label) DO NOTHING
        RETURNING id
        """,
        (chunk_id, label, json.dumps(state)),
    )
    row = cur.fetchone()
    return row[0] if row else None


async def capture_state_checkpoint_async(
    conn: Any,
    *,
    chunk_id: Optional[int],
    label: str,
) -> Optional[int]:
    _validate_label(label)
    state: dict[str, Any] = {}
    for section, sql in CHECKPOINT_SECTIONS.items():
        value = await conn.fetchval(sql)
        state[section] = json.loads(value) if isinstance(value, str) else value
    return await conn.fetchval(
        """
        INSERT INTO state_checkpoints (chunk_id, label, state)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (chunk_id, label) DO NOTHING
        RETURNING id
        """,
        chunk_id,
        label,
        json.dumps(state),
    )


def log_state_delta_sync(
    cur: Any,
    *,
    source_chunk_id: int,
    writer: str,
    entity_id: Optional[int],
    field: str,
    new_value: Any,
    old_value: Any = None,
) -> None:
    """Append one Skald-side scalar write to the chunk-keyed delta ledger.

    Policy per issue #426: log everything, including writes that repeat the
    current value — the ledger's completeness is what makes replay honest.
    """

    cur.execute(
        """
        INSERT INTO state_delta_log (
            source_chunk_id, writer, entity_id, field, old_value, new_value
        ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (
            source_chunk_id,
            writer,
            entity_id,
            field,
            json.dumps(old_value) if old_value is not None else None,
            json.dumps(new_value),
        ),
    )


async def log_state_delta_async(
    conn: Any,
    *,
    source_chunk_id: int,
    writer: str,
    entity_id: Optional[int],
    field: str,
    new_value: Any,
    old_value: Any = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO state_delta_log (
            source_chunk_id, writer, entity_id, field, old_value, new_value
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
        """,
        source_chunk_id,
        writer,
        entity_id,
        field,
        json.dumps(old_value) if old_value is not None else None,
        json.dumps(new_value),
    )


def set_commit_chunk_attribution_sync(cur: Any, chunk_id: int) -> None:
    """Attribute this transaction's trigger-versioned writes to a chunk.

    The relationship-versioning triggers (migration 065) read the
    transaction-local ``nexus.source_chunk_id`` setting; rows written
    outside an attributed commit get NULL.
    """

    cur.execute(
        "SELECT set_config('nexus.source_chunk_id', %s, true)",
        (str(chunk_id),),
    )


async def set_commit_chunk_attribution_async(conn: Any, chunk_id: int) -> None:
    await conn.execute(
        "SELECT set_config('nexus.source_chunk_id', $1, true)",
        str(chunk_id),
    )
