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
import re
from typing import Any, Optional

from nexus.agents.orrery.db_rows import row_get
from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER


_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def playable_narrative_predicate(table_alias: str = "nc") -> str:
    """Return the canonical SQL predicate for player-played narrative rows.

    Retrograde's synthetic prologue remains in ``narrative_chunks`` because
    ``world_events.tick_chunk_id`` needs a real FK anchor.  It is not a scene
    the player can read or continue from.  All player-facing readers and
    accepted-chunk cadence calculations share this predicate so sparse raw
    chunk ids never leak back into story-order semantics.

    ``table_alias`` is interpolated as SQL syntax, so accept identifiers only.
    The marker itself is a trusted code constant and is encoded as JSON here.
    """

    if not _SQL_IDENTIFIER_RE.fullmatch(table_alias):
        raise ValueError(f"Unsafe narrative table alias: {table_alias!r}")
    marker_json = json.dumps([RETROGRADE_PROLOGUE_MARKER]).replace("'", "''")
    return (
        "NOT ("
        f"COALESCE({table_alias}.authorial_directives, '[]'::jsonb) "
        f"@> '{marker_json}'::jsonb"
        ")"
    )


def playable_narrative_ordinal_sync(cur: Any) -> int:
    """Count accepted player-played chunks in the current transaction."""

    cur.execute(
        "SELECT COUNT(*) FROM narrative_chunks nc WHERE "
        + playable_narrative_predicate()
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Playable narrative ordinal query returned no row")
    if hasattr(row, "keys"):
        return int(next(iter(row.values())))
    return int(row[0])


async def playable_narrative_ordinal_async(conn: Any) -> int:
    """Async equivalent of :func:`playable_narrative_ordinal_sync`."""

    value = await conn.fetchval(
        "SELECT COUNT(*) FROM narrative_chunks nc WHERE "
        + playable_narrative_predicate()
    )
    if value is None:
        raise RuntimeError("Playable narrative ordinal query returned no value")
    return int(value)


def interval_checkpoint_due(*, playable_ordinal: int, interval: int) -> bool:
    """Whether this accepted playable chunk reaches checkpoint cadence."""

    if interval <= 0:
        return False
    if playable_ordinal < 1:
        raise ValueError("playable_ordinal must be positive after chunk insertion")
    return playable_ordinal % interval == 0


# Every mutable table the resolver's hydration or the Skald commit path can
# read or write. A checkpoint is one JSONB document with one array per entry.
# Order is presentation-only; each section is captured atomically inside the
# caller's transaction.
CHECKPOINT_SECTIONS: dict[str, str] = {
    "entities": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM (SELECT id, is_active FROM entities) t"
    ),
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
    "character_project_states": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM character_project_states t"
    ),
    "character_routine_anchors": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM character_routine_anchors t"
    ),
    "claim_awareness": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) " "FROM claim_awareness t"
    ),
    "backstory_secrets": (
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) "
        "FROM backstory_secrets t"
    ),
}

_ADDITIVE_CHECKPOINT_TABLES = {"backstory_secrets": "backstory_secrets"}

# Control key (#552): the set of maturation-job ids whose expansion WRITES
# are visible inside the capture transaction. Underscore-prefixed and
# deliberately absent from CHECKPOINT_SECTIONS so verification never diffs it
# as state; replay uses target-minus-base membership as the exact applied-at
# boundary for asynchronously persisted maturation writes. MVCC gives the
# exactness: whatever this SELECT can see is precisely what the section
# snapshots in the same transaction saw.
#
# The predicate is result_manifest.persisted — recorded by the worker in the
# SAME transaction as the expansion writes — NOT state = 'succeeded', which
# flips in a later transaction after embedding and would open a race band
# where a capture sees the writes but not the membership.
MATURATION_JOBS_CONTROL_KEY = "_maturation_jobs_succeeded"
_MATURATION_JOBS_CONTROL_SQL = (
    "SELECT coalesce(jsonb_agg(id ORDER BY id), '[]'::jsonb) "
    "FROM orrery_maturation_jobs "
    "WHERE (result_manifest ->> 'persisted')::boolean"
)

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
        additive_table = _ADDITIVE_CHECKPOINT_TABLES.get(section)
        if additive_table is not None:
            cur.execute(
                "SELECT to_regclass(%s) AS checkpoint_table",
                (additive_table,),
            )
            if row_get(cur.fetchone(), "checkpoint_table", 0) is None:
                # A genuinely pre-migration schema produces a pre-migration
                # checkpoint document. Replay treats the absent key as the
                # explicit cross-era compatibility boundary.
                continue
        cur.execute(sql)
        row = cur.fetchone()
        state[section] = row[0] if not hasattr(row, "keys") else list(row.values())[0]
    cur.execute(_MATURATION_JOBS_CONTROL_SQL)
    control_row = cur.fetchone()
    state[MATURATION_JOBS_CONTROL_KEY] = (
        control_row[0]
        if not hasattr(control_row, "keys")
        else list(control_row.values())[0]
    )
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
    return row_get(row, "id", 0) if row else None


async def capture_state_checkpoint_async(
    conn: Any,
    *,
    chunk_id: Optional[int],
    label: str,
) -> Optional[int]:
    _validate_label(label)
    state: dict[str, Any] = {}
    for section, sql in CHECKPOINT_SECTIONS.items():
        additive_table = _ADDITIVE_CHECKPOINT_TABLES.get(section)
        if (
            additive_table is not None
            and await conn.fetchval("SELECT to_regclass($1)", additive_table) is None
        ):
            continue
        value = await conn.fetchval(sql)
        state[section] = json.loads(value) if isinstance(value, str) else value
    control_value = await conn.fetchval(_MATURATION_JOBS_CONTROL_SQL)
    state[MATURATION_JOBS_CONTROL_KEY] = (
        json.loads(control_value) if isinstance(control_value, str) else control_value
    )
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
