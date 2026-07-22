"""DB writer for Orrery tag bestowal.

Called by:

- ``nexus.api.new_story_db_mapper``: after the wizard inserts the protagonist
  and the starting location.
- ``nexus.api.commit_handler_sync``: after each per-chunk new-entity insert and
  state update.

The shared insert path stamps rows with the supplied ``source_kind`` (typically
``skald_inline`` for runtime bestowal; the offline slot 2 backfill uses
``llm_generated``). Operates within the caller's transaction — no commits here.

Depends on migration 036 making ``ix_entity_tags_current`` UNIQUE so the
``ON CONFLICT`` clause in ``_insert_entity_tag`` matches a unique index,
migration 037 seeding ``tag_category_registry`` so runtime bestowals know which
tag categories may be applied to each entity kind, and migration 049 adding the
scheduled-expiry column used by duration-bearing tags.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AbstractSet, Any, Literal, Optional, TypeAlias

from nexus.agents.orrery.status_family import STATUS_TAGS, status_tag_for_level
from nexus.agents.orrery.tag_constants import CANONICAL_TAGS
from nexus.agents.orrery.tag_library import VALID_ENTITY_KINDS
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal


# Split the retired source-kind literal so grep checks catch live usage sites.
_DISALLOWED_SOURCE_KINDS = frozenset({"auto_" "registered"})
_REAPPLICATION_POLICIES = frozenset({"new_row", "extend_expiry", "replace"})
ReapplicationPolicy: TypeAlias = Literal["new_row", "extend_expiry", "replace"]


@dataclass(frozen=True)
class _TagApplication:
    tag_id: int
    reapplication_policy: Optional[ReapplicationPolicy]


def apply_tag_bestowal(
    cur: Any,
    *,
    entity_id: int,
    entity_kind: str,
    bestowal: Optional[OrreryTagBestowal],
    source_kind: str = "skald_inline",
    world_time: Optional[datetime] = None,
    duration_override: Optional[timedelta] = None,
    source_chunk_id: Optional[int] = None,
) -> dict[str, int]:
    """Apply a closed-vocabulary tag bestowal to the database.

    Performs two operations in order:

    1. Apply registered tag names to the entity via ``entity_tags`` insert.
    2. Mark ``tags_to_clear`` entries cleared (UPDATE cleared_at = now()).

    Requires migration 037's ``tag_category_registry`` rows for the target
    ``entity_kind``; missing registry data is treated as a slot-migration error.
    Unknown, deprecated, or entity-kind-incompatible tags raise ``ValueError``.
    ``duration_override`` sets ``entity_tags.expires_at_world_time`` for
    duration-bearing applications and drives ``extend_expiry`` reapplications.

    Returns counter dict suitable for logging:
    ``{"applied", "cleared"}``.
    """

    counters = {
        "applied": 0,
        "cleared": 0,
    }

    if bestowal is None:
        return counters

    _validate_source_kind(source_kind)
    if entity_kind not in VALID_ENTITY_KINDS:
        raise ValueError(
            f"Unknown entity_kind={entity_kind!r}; expected one of "
            f"{sorted(VALID_ENTITY_KINDS)}"
        )

    allowed = _lookup_allowed_categories(cur, entity_kind)
    if not allowed:
        raise ValueError(
            f"No Orrery tag categories registered for entity_kind={entity_kind!r}"
        )

    if world_time is None:
        if source_chunk_id is not None:
            # Chunk-keyed rows take the bestowing chunk's clock or stay NULL —
            # never the global-max fallback, which would stamp an "exact" row
            # with a wrong world time when chunk metadata is missing.
            world_time = _chunk_world_time(cur, source_chunk_id)
        else:
            world_time = _load_world_time(cur)

    tags_to_apply: list[_TagApplication] = []
    for tag_name in bestowal.applied_tags:
        canonical_name, tag_row = _lookup_canonical_tag(cur, tag_name)
        category = _row_value(tag_row, "category", 1)
        _validate_allowed_category(
            category=category,
            allowed=allowed,
            tag_name=canonical_name,
            entity_kind=entity_kind,
        )
        tags_to_apply.append(
            _TagApplication(
                tag_id=_row_value(tag_row, "id", 0),
                reapplication_policy=_row_value(tag_row, "reapplication_policy", 3),
            )
        )

    tags_to_clear: list[int] = []
    for clear_name in bestowal.tags_to_clear:
        canonical_clear, tag_row = _lookup_canonical_tag(cur, clear_name)
        category = _row_value(tag_row, "category", 1)
        _validate_allowed_category(
            category=category,
            allowed=allowed,
            tag_name=canonical_clear,
            entity_kind=entity_kind,
        )
        tags_to_clear.append(_row_value(tag_row, "id", 0))

    # 1. apply registered tags to the entity
    for tag_application in tags_to_apply:
        applied = _insert_entity_tag(
            cur,
            entity_id=entity_id,
            tag_id=tag_application.tag_id,
            source_kind=source_kind,
            world_time=world_time,
            duration_override=duration_override,
            reapplication_policy=tag_application.reapplication_policy,
            source_chunk_id=source_chunk_id,
        )
        if applied:
            counters["applied"] += 1

    # 2. clear tags that no longer apply (update contexts only)
    for tag_id in tags_to_clear:
        if _clear_entity_tag(
            cur,
            entity_id=entity_id,
            tag_id=tag_id,
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason="bestowal.tags_to_clear",
        ):
            counters["cleared"] += 1

    return counters


def validate_tag_bestowal(
    cur: Any,
    *,
    entity_kind: str,
    bestowal: Optional[OrreryTagBestowal],
) -> list[str]:
    """Validate a bestowal against the live registry without writing.

    Returns issue strings for unknown, deprecated, or entity-kind-incompatible
    tag names. Used by wizard tools to reject bad bestowals at submission time
    (via ModelRetry) instead of exploding later inside the transition
    transaction.
    """

    if bestowal is None:
        return []
    if entity_kind not in VALID_ENTITY_KINDS:
        raise ValueError(
            f"Unknown entity_kind={entity_kind!r}; expected one of "
            f"{sorted(VALID_ENTITY_KINDS)}"
        )

    allowed = _lookup_allowed_categories(cur, entity_kind)
    if not allowed:
        raise ValueError(
            f"No Orrery tag categories registered for entity_kind={entity_kind!r}"
        )

    issues: list[str] = []
    for field_name in ("applied_tags", "tags_to_clear"):
        for tag_name in getattr(bestowal, field_name):
            try:
                canonical_name, tag_row = _lookup_canonical_tag(cur, tag_name)
                _validate_allowed_category(
                    category=_row_value(tag_row, "category", 1),
                    allowed=allowed,
                    tag_name=canonical_name,
                    entity_kind=entity_kind,
                )
            except ValueError as exc:
                issues.append(f"{field_name}: {exc}")
    return issues


async def apply_tag_bestowal_async(
    conn: Any,
    *,
    entity_id: int,
    entity_kind: str,
    bestowal: Optional[OrreryTagBestowal],
    source_kind: str = "skald_inline",
    world_time: Optional[datetime] = None,
    duration_override: Optional[timedelta] = None,
    source_chunk_id: Optional[int] = None,
) -> dict[str, int]:
    """Asyncpg equivalent of apply_tag_bestowal for async commit paths."""

    counters = {
        "applied": 0,
        "cleared": 0,
    }

    if bestowal is None:
        return counters

    _validate_source_kind(source_kind)
    if entity_kind not in VALID_ENTITY_KINDS:
        raise ValueError(
            f"Unknown entity_kind={entity_kind!r}; expected one of "
            f"{sorted(VALID_ENTITY_KINDS)}"
        )

    allowed = await _lookup_allowed_categories_async(conn, entity_kind)
    if not allowed:
        raise ValueError(
            f"No Orrery tag categories registered for entity_kind={entity_kind!r}"
        )

    if world_time is None:
        if source_chunk_id is not None:
            # Same rule as the sync twin: chunk clock or NULL, never global max.
            world_time = await _chunk_world_time_async(conn, source_chunk_id)
        else:
            world_time = await _load_world_time_async(conn)

    tags_to_apply: list[_TagApplication] = []
    for tag_name in bestowal.applied_tags:
        canonical_name, tag_row = await _lookup_canonical_tag_async(conn, tag_name)
        category = _row_value(tag_row, "category", 1)
        _validate_allowed_category(
            category=category,
            allowed=allowed,
            tag_name=canonical_name,
            entity_kind=entity_kind,
        )
        tags_to_apply.append(
            _TagApplication(
                tag_id=_row_value(tag_row, "id", 0),
                reapplication_policy=_row_value(tag_row, "reapplication_policy", 3),
            )
        )

    tags_to_clear: list[int] = []
    for clear_name in bestowal.tags_to_clear:
        canonical_clear, tag_row = await _lookup_canonical_tag_async(conn, clear_name)
        category = _row_value(tag_row, "category", 1)
        _validate_allowed_category(
            category=category,
            allowed=allowed,
            tag_name=canonical_clear,
            entity_kind=entity_kind,
        )
        tags_to_clear.append(_row_value(tag_row, "id", 0))

    for tag_application in tags_to_apply:
        applied = await _insert_entity_tag_async(
            conn,
            entity_id=entity_id,
            tag_id=tag_application.tag_id,
            source_kind=source_kind,
            world_time=world_time,
            duration_override=duration_override,
            reapplication_policy=tag_application.reapplication_policy,
            source_chunk_id=source_chunk_id,
        )
        if applied:
            counters["applied"] += 1

    for tag_id in tags_to_clear:
        if await _clear_entity_tag_async(
            conn,
            entity_id=entity_id,
            tag_id=tag_id,
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason="bestowal.tags_to_clear",
        ):
            counters["cleared"] += 1

    return counters


def apply_exclusive_tag_bestowal(
    cur: Any,
    *,
    entity_id: int,
    entity_kind: str,
    tag: str,
    source_kind: str = "skald_inline",
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
    duration_override: Optional[timedelta] = None,
) -> bool:
    """Replace the active tag within a single-entity exclusive category.

    This is the write primitive for documented XOR categories such as
    ``role.fame`` and ``role.resources`` while the registry-level cardinality
    column is still schema-pending. The function clears all active sibling rows
    in the target tag's category for ``entity_id`` before inserting the new tag,
    all inside the caller-owned transaction.

    Returns ``True`` if the new tag row was inserted, ``False`` if it was
    already active. Sibling rows are cleared either way.
    ``duration_override`` has the same meaning as in ``apply_tag_bestowal``.
    """

    _validate_source_kind(source_kind)
    if entity_kind not in VALID_ENTITY_KINDS:
        raise ValueError(
            f"Unknown entity_kind={entity_kind!r}; expected one of "
            f"{sorted(VALID_ENTITY_KINDS)}"
        )

    allowed = _lookup_allowed_categories(cur, entity_kind)
    if not allowed:
        raise ValueError(
            f"No Orrery tag categories registered for entity_kind={entity_kind!r}"
        )

    canonical_name, tag_row = _lookup_canonical_tag(cur, tag)
    category = _row_value(tag_row, "category", 1)
    _validate_allowed_category(
        category=category,
        allowed=allowed,
        tag_name=canonical_name,
        entity_kind=entity_kind,
    )
    tag_id = _row_value(tag_row, "id", 0)
    reapplication_policy = _row_value(tag_row, "reapplication_policy", 3)

    if world_time is None:
        if source_chunk_id is not None:
            # Chunk-keyed rows take the bestowing chunk's clock or stay NULL —
            # never the global-max fallback, which would stamp an "exact" row
            # with a wrong world time when chunk metadata is missing.
            world_time = _chunk_world_time(cur, source_chunk_id)
        else:
            world_time = _load_world_time(cur)

    _clear_entity_tag_siblings(
        cur,
        entity_id=entity_id,
        category=category,
        world_time=world_time,
        source_chunk_id=source_chunk_id,
        keep_tag_id=tag_id,
    )
    return _insert_entity_tag(
        cur,
        entity_id=entity_id,
        tag_id=tag_id,
        source_kind=source_kind,
        world_time=world_time,
        source_chunk_id=source_chunk_id,
        duration_override=duration_override,
        reapplication_policy=reapplication_policy,
    )


async def apply_exclusive_tag_bestowal_async(
    conn: Any,
    *,
    entity_id: int,
    entity_kind: str,
    tag: str,
    source_kind: str = "skald_inline",
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
    duration_override: Optional[timedelta] = None,
) -> bool:
    """Async twin of :func:`apply_exclusive_tag_bestowal`."""

    _validate_source_kind(source_kind)
    if entity_kind not in VALID_ENTITY_KINDS:
        raise ValueError(
            f"Unknown entity_kind={entity_kind!r}; expected one of "
            f"{sorted(VALID_ENTITY_KINDS)}"
        )

    allowed = await _lookup_allowed_categories_async(conn, entity_kind)
    if not allowed:
        raise ValueError(
            f"No Orrery tag categories registered for entity_kind={entity_kind!r}"
        )

    canonical_name, tag_row = await _lookup_canonical_tag_async(conn, tag)
    category = _row_value(tag_row, "category", 1)
    _validate_allowed_category(
        category=category,
        allowed=allowed,
        tag_name=canonical_name,
        entity_kind=entity_kind,
    )
    tag_id = _row_value(tag_row, "id", 0)
    reapplication_policy = _row_value(tag_row, "reapplication_policy", 3)

    if world_time is None:
        if source_chunk_id is not None:
            world_time = await _chunk_world_time_async(conn, source_chunk_id)
        else:
            world_time = await _load_world_time_async(conn)

    sibling_rows = await conn.fetch(
        """
        SELECT et.tag_id
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        WHERE et.entity_id = $1
          AND t.category = $2
          AND t.id <> $3
          AND et.cleared_at IS NULL
        ORDER BY et.id
        FOR UPDATE OF et
        """,
        entity_id,
        category,
        tag_id,
    )
    for row in sibling_rows:
        await _clear_entity_tag_async(
            conn,
            entity_id=entity_id,
            tag_id=_row_value(row, "tag_id", 0),
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason="exclusive_ladder_replace",
        )
    return await _insert_entity_tag_async(
        conn,
        entity_id=entity_id,
        tag_id=tag_id,
        source_kind=source_kind,
        world_time=world_time,
        source_chunk_id=source_chunk_id,
        duration_override=duration_override,
        reapplication_policy=reapplication_policy,
    )


def _lookup_allowed_categories(cur: Any, entity_kind: str) -> set[str]:
    cur.execute(
        """
        SELECT category
        FROM tag_category_registry
        WHERE entity_kind = %s::entity_kind
        """,
        (entity_kind,),
    )
    return {_row_value(row, "category", 0) for row in cur.fetchall()}


async def _lookup_allowed_categories_async(conn: Any, entity_kind: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT category
        FROM tag_category_registry
        WHERE entity_kind = $1::entity_kind
        """,
        entity_kind,
    )
    return {_row_value(row, "category", 0) for row in rows}


def _lookup_tag(cur: Any, tag_name: str) -> Optional[Any]:
    cur.execute(
        """
        SELECT id, category, is_ephemeral, reapplication_policy
        FROM tags
        WHERE tag = %s AND NOT deprecated AND synonym_for IS NULL
        """,
        (tag_name,),
    )
    return cur.fetchone()


async def _lookup_tag_async(conn: Any, tag_name: str) -> Optional[Any]:
    return await conn.fetchrow(
        """
        SELECT id, category, is_ephemeral, reapplication_policy
        FROM tags
        WHERE tag = $1 AND NOT deprecated AND synonym_for IS NULL
        """,
        tag_name,
    )


def _lookup_canonical_tag(cur: Any, tag_name: str) -> tuple[str, Any]:
    canonical_name = CANONICAL_TAGS.get(tag_name, tag_name)
    tag_row = _lookup_tag(cur, canonical_name)
    if tag_row is None:
        if canonical_name == tag_name:
            raise ValueError(f"Unknown or deprecated Orrery tag {tag_name!r}")
        raise ValueError(
            f"Unknown or deprecated Orrery tag {tag_name!r} "
            f"(canonicalized to {canonical_name!r})"
        )
    return canonical_name, tag_row


async def _lookup_canonical_tag_async(conn: Any, tag_name: str) -> tuple[str, Any]:
    canonical_name = CANONICAL_TAGS.get(tag_name, tag_name)
    tag_row = await _lookup_tag_async(conn, canonical_name)
    if tag_row is None:
        if canonical_name == tag_name:
            raise ValueError(f"Unknown or deprecated Orrery tag {tag_name!r}")
        raise ValueError(
            f"Unknown or deprecated Orrery tag {tag_name!r} "
            f"(canonicalized to {canonical_name!r})"
        )
    return canonical_name, tag_row


def _validate_allowed_category(
    *,
    category: str,
    allowed: set[str],
    tag_name: str,
    entity_kind: str,
) -> None:
    if category not in allowed:
        raise ValueError(
            f"Orrery tag {tag_name!r} has category {category!r}, which is not "
            f"registered for entity_kind={entity_kind!r}"
        )


def _validate_source_kind(source_kind: str) -> None:
    if source_kind in _DISALLOWED_SOURCE_KINDS:
        raise ValueError(
            f"source_kind={source_kind!r} is not accepted by Orrery writers; "
            "closed-vocabulary bestowals must not auto-register tags"
        )


def _load_world_time(cur: Any) -> Optional[datetime]:
    cur.execute("SELECT max(world_time) AS world_time FROM chunk_metadata")
    row = cur.fetchone()
    if row is None:
        return None
    return _row_value(row, "world_time", 0)


async def _load_world_time_async(conn: Any) -> Optional[datetime]:
    row = await conn.fetchrow(
        "SELECT max(world_time) AS world_time FROM chunk_metadata"
    )
    if row is None:
        return None
    return _row_value(row, "world_time", 0)


def _log_entity_tag_clearance(
    cur: Any,
    *,
    entity_tag_id: int,
    world_time: Optional[datetime],
    source_chunk_id: Optional[int],
    reason: str,
) -> None:
    """Record one single-entity tag clearance (mechanism 'authored').

    Before migration 064 every tag_writer clear was silent; as-of
    reconstruction needs the log row even when world_time/chunk id are
    unknown (they stay NULL — honest, not fabricated).
    """

    cur.execute(
        """
        INSERT INTO tag_clearance_log (
            entity_tag_id, mechanism, cleared_at_world_time,
            justification, source_chunk_id
        ) VALUES (%s, 'authored', %s, %s::jsonb, %s)
        """,
        (entity_tag_id, world_time, json.dumps({"reason": reason}), source_chunk_id),
    )


async def _log_entity_tag_clearance_async(
    conn: Any,
    *,
    entity_tag_id: int,
    world_time: Optional[datetime],
    source_chunk_id: Optional[int],
    reason: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO tag_clearance_log (
            entity_tag_id, mechanism, cleared_at_world_time,
            justification, source_chunk_id
        ) VALUES ($1, 'authored', $2, $3::jsonb, $4)
        """,
        entity_tag_id,
        world_time,
        json.dumps({"reason": reason}),
        source_chunk_id,
    )


def _log_pair_tag_clearance(
    cur: Any,
    *,
    entity_pair_tag_id: int,
    world_time: Optional[datetime],
    source_chunk_id: Optional[int],
    reason: str,
) -> None:
    """Record one pair-tag clearance (loggable since migration 064)."""

    cur.execute(
        """
        INSERT INTO tag_clearance_log (
            entity_pair_tag_id, mechanism, cleared_at_world_time,
            justification, source_chunk_id
        ) VALUES (%s, 'authored', %s, %s::jsonb, %s)
        """,
        (
            entity_pair_tag_id,
            world_time,
            json.dumps({"reason": reason}),
            source_chunk_id,
        ),
    )


def _chunk_world_time(cur: Any, source_chunk_id: int) -> Optional[datetime]:
    """The bestowing chunk's in-world time, or None (never wall clock)."""

    cur.execute(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
        (source_chunk_id,),
    )
    row = cur.fetchone()
    return _row_value(row, "world_time", 0) if row else None


async def _chunk_world_time_async(
    conn: Any, source_chunk_id: int
) -> Optional[datetime]:
    return await conn.fetchval(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = $1",
        source_chunk_id,
    )


def _insert_entity_tag(
    cur: Any,
    *,
    entity_id: int,
    tag_id: int,
    source_kind: str,
    world_time: Optional[datetime],
    duration_override: Optional[timedelta],
    reapplication_policy: Optional[ReapplicationPolicy],
    source_chunk_id: Optional[int] = None,
) -> bool:
    reapplication_policy = reapplication_policy or "new_row"
    if reapplication_policy not in _REAPPLICATION_POLICIES:
        raise ValueError(
            f"Unsupported entity tag reapplication_policy={reapplication_policy!r}"
        )
    if reapplication_policy == "extend_expiry" and duration_override is None:
        raise ValueError(
            "reapplication_policy='extend_expiry' requires duration_override"
        )

    expires_at_world_time = _compute_expires_at_world_time(
        world_time=world_time,
        duration_override=duration_override,
    )

    if reapplication_policy == "replace":
        cur.execute(
            """
            INSERT INTO entity_tags (
                entity_id, tag_id, applied_at_world_time,
                expires_at_world_time, source_kind, source_chunk_id
            )
            VALUES (%s, %s, %s, %s, %s::entity_tag_source_kind, %s)
            ON CONFLICT (entity_id, tag_id)
              WHERE cleared_at IS NULL
              DO UPDATE SET
                applied_at = now(),
                applied_at_world_time = EXCLUDED.applied_at_world_time,
                expires_at_world_time = EXCLUDED.expires_at_world_time,
                source_kind = EXCLUDED.source_kind,
                source_chunk_id = EXCLUDED.source_chunk_id
            """,
            (
                entity_id,
                tag_id,
                world_time,
                expires_at_world_time,
                source_kind,
                source_chunk_id,
            ),
        )
        return bool(cur.rowcount)

    if reapplication_policy == "extend_expiry":
        cur.execute(
            """
            INSERT INTO entity_tags (
                entity_id, tag_id, applied_at_world_time,
                expires_at_world_time, source_kind, source_chunk_id
            )
            VALUES (%s, %s, %s, %s, %s::entity_tag_source_kind, %s)
            ON CONFLICT (entity_id, tag_id)
              WHERE cleared_at IS NULL
              DO UPDATE SET
                applied_at = now(),
                applied_at_world_time = EXCLUDED.applied_at_world_time,
                expires_at_world_time = GREATEST(
                    COALESCE(
                        entity_tags.expires_at_world_time,
                        EXCLUDED.applied_at_world_time
                    ),
                    EXCLUDED.applied_at_world_time
                ) + %s,
                source_kind = EXCLUDED.source_kind,
                source_chunk_id = EXCLUDED.source_chunk_id
            """,
            (
                entity_id,
                tag_id,
                world_time,
                expires_at_world_time,
                source_kind,
                source_chunk_id,
                duration_override,
            ),
        )
        # A truthy result means the active row changed: either inserted fresh or
        # conflict-updated. For replace/extend, "applied" is broader than insert.
        return bool(cur.rowcount)

    cur.execute(
        """
        INSERT INTO entity_tags (
            entity_id, tag_id, applied_at_world_time,
            expires_at_world_time, source_kind, source_chunk_id
        )
        VALUES (%s, %s, %s, %s, %s::entity_tag_source_kind, %s)
        ON CONFLICT (entity_id, tag_id)
          WHERE cleared_at IS NULL
          DO NOTHING
        """,
        (
            entity_id,
            tag_id,
            world_time,
            expires_at_world_time,
            source_kind,
            source_chunk_id,
        ),
    )
    return bool(cur.rowcount)


async def _insert_entity_tag_async(
    conn: Any,
    *,
    entity_id: int,
    tag_id: int,
    source_kind: str,
    world_time: Optional[datetime],
    duration_override: Optional[timedelta],
    reapplication_policy: Optional[ReapplicationPolicy],
    source_chunk_id: Optional[int] = None,
) -> bool:
    reapplication_policy = reapplication_policy or "new_row"
    if reapplication_policy not in _REAPPLICATION_POLICIES:
        raise ValueError(
            f"Unsupported entity tag reapplication_policy={reapplication_policy!r}"
        )
    if reapplication_policy == "extend_expiry" and duration_override is None:
        raise ValueError(
            "reapplication_policy='extend_expiry' requires duration_override"
        )

    expires_at_world_time = _compute_expires_at_world_time(
        world_time=world_time,
        duration_override=duration_override,
    )

    if reapplication_policy == "replace":
        result = await conn.execute(
            """
            INSERT INTO entity_tags (
                entity_id, tag_id, applied_at_world_time,
                expires_at_world_time, source_kind, source_chunk_id
            )
            VALUES ($1, $2, $3, $4, $5::entity_tag_source_kind, $6)
            ON CONFLICT (entity_id, tag_id)
              WHERE cleared_at IS NULL
              DO UPDATE SET
                applied_at = now(),
                applied_at_world_time = EXCLUDED.applied_at_world_time,
                expires_at_world_time = EXCLUDED.expires_at_world_time,
                source_kind = EXCLUDED.source_kind,
                source_chunk_id = EXCLUDED.source_chunk_id
            """,
            entity_id,
            tag_id,
            world_time,
            expires_at_world_time,
            source_kind,
            source_chunk_id,
        )
        return _asyncpg_status_changed(result)

    if reapplication_policy == "extend_expiry":
        result = await conn.execute(
            """
            INSERT INTO entity_tags (
                entity_id, tag_id, applied_at_world_time,
                expires_at_world_time, source_kind, source_chunk_id
            )
            VALUES ($1, $2, $3, $4, $5::entity_tag_source_kind, $6)
            ON CONFLICT (entity_id, tag_id)
              WHERE cleared_at IS NULL
              DO UPDATE SET
                applied_at = now(),
                applied_at_world_time = EXCLUDED.applied_at_world_time,
                expires_at_world_time = GREATEST(
                    COALESCE(
                        entity_tags.expires_at_world_time,
                        EXCLUDED.applied_at_world_time
                    ),
                    EXCLUDED.applied_at_world_time
                ) + $7,
                source_kind = EXCLUDED.source_kind,
                source_chunk_id = EXCLUDED.source_chunk_id
            """,
            entity_id,
            tag_id,
            world_time,
            expires_at_world_time,
            source_kind,
            source_chunk_id,
            duration_override,
        )
        return _asyncpg_status_changed(result)

    result = await conn.execute(
        """
        INSERT INTO entity_tags (
            entity_id, tag_id, applied_at_world_time,
            expires_at_world_time, source_kind, source_chunk_id
        )
        VALUES ($1, $2, $3, $4, $5::entity_tag_source_kind, $6)
        ON CONFLICT (entity_id, tag_id)
          WHERE cleared_at IS NULL
          DO NOTHING
        """,
        entity_id,
        tag_id,
        world_time,
        expires_at_world_time,
        source_kind,
        source_chunk_id,
    )
    return _asyncpg_status_changed(result)


def _compute_expires_at_world_time(
    *,
    world_time: Optional[datetime],
    duration_override: Optional[timedelta],
) -> Optional[datetime]:
    if duration_override is None:
        return None
    if world_time is None:
        raise ValueError("duration_override requires a known Orrery world_time")
    return world_time + duration_override


def _clear_entity_tag_siblings(
    cur: Any,
    *,
    entity_id: int,
    category: str,
    keep_tag_id: int,
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
) -> int:
    cur.execute(
        """
        UPDATE entity_tags et
        SET cleared_at = now()
        FROM tags t
        WHERE et.tag_id = t.id
          AND et.entity_id = %s
          AND t.category = %s
          AND t.id <> %s
          AND et.cleared_at IS NULL
        RETURNING et.id
        """,
        (entity_id, category, keep_tag_id),
    )
    cleared_ids = [_row_value(row, "id", 0) for row in cur.fetchall()]
    for entity_tag_id in cleared_ids:
        _log_entity_tag_clearance(
            cur,
            entity_tag_id=entity_tag_id,
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason="exclusive_ladder_replace",
        )
    return len(cleared_ids)


def clear_entity_tag(
    cur: Any,
    *,
    entity_id: int,
    tag: str,
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
) -> bool:
    """Mark an active single-entity tag as cleared (UPDATE cleared_at = now()).

    Returns ``True`` if a row was cleared, ``False`` if no active row existed for
    ``(entity_id, tag)``.

    Note: unknown or deprecated ``tag`` names silently return ``False`` rather
    than raising — this is the inverse of ``apply_tag_bestowal``, which raises
    ``ValueError`` for unknown tags. The asymmetry matches ``clear_pair_tag``:
    clearing a tag that doesn't exist is a no-op, so an unknown tag is
    indistinguishable from a missing row. Alias names in ``CANONICAL_TAGS``
    resolve to their canonical tag before clearing. Deprecated registry rows
    are intentionally treated as absent; clearing pre-deprecation active rows is
    a data-cleanup concern for a migration or id-based maintenance helper.
    """

    canonical_name = CANONICAL_TAGS.get(tag, tag)
    cur.execute(
        """
        UPDATE entity_tags et
        SET cleared_at = now()
        FROM tags t
        WHERE et.tag_id = t.id
          AND et.entity_id = %s
          AND t.tag = %s
          AND NOT t.deprecated
          AND t.synonym_for IS NULL
          AND et.cleared_at IS NULL
        RETURNING et.id
        """,
        (entity_id, canonical_name),
    )
    cleared_ids = [_row_value(row, "id", 0) for row in cur.fetchall()]
    for entity_tag_id in cleared_ids:
        _log_entity_tag_clearance(
            cur,
            entity_tag_id=entity_tag_id,
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason="clear_entity_tag",
        )
    return bool(cleared_ids)


def _clear_entity_tag(
    cur: Any,
    *,
    entity_id: int,
    tag_id: int,
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
    reason: str = "tag_writer.clear",
) -> bool:
    cur.execute(
        """
        UPDATE entity_tags
        SET cleared_at = now()
        WHERE entity_id = %s AND tag_id = %s AND cleared_at IS NULL
        RETURNING id
        """,
        (entity_id, tag_id),
    )
    cleared_ids = [_row_value(row, "id", 0) for row in cur.fetchall()]
    for entity_tag_id in cleared_ids:
        _log_entity_tag_clearance(
            cur,
            entity_tag_id=entity_tag_id,
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason=reason,
        )
    return bool(cleared_ids)


async def _clear_entity_tag_async(
    conn: Any,
    *,
    entity_id: int,
    tag_id: int,
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
    reason: str = "tag_writer.clear",
) -> bool:
    rows = await conn.fetch(
        """
        UPDATE entity_tags
        SET cleared_at = now()
        WHERE entity_id = $1 AND tag_id = $2 AND cleared_at IS NULL
        RETURNING id
        """,
        entity_id,
        tag_id,
    )
    for row in rows:
        await _log_entity_tag_clearance_async(
            conn,
            entity_tag_id=_row_value(row, "id", 0),
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason=reason,
        )
    return bool(rows)


def _asyncpg_status_changed(status: str) -> bool:
    try:
        return int(status.rsplit(" ", 1)[-1]) > 0
    except (TypeError, ValueError):
        return False


def _row_value(row: Any, key: str, index: int) -> Any:
    """Read a column from a row that may be a Mapping (DictCursor) or sequence."""
    if hasattr(row, "get"):
        return row[key]
    return row[index]


# ---------------------------------------------------------------------------
# Multi-entity (pair) tag writer
# ---------------------------------------------------------------------------
#
# `entity_pair_tags` is the application table for directed binary relations
# between entities; `pair_tags` is the corresponding vocabulary registry (see
# migration 042). This section adds writer helpers analogous to the single-
# entity tag writer above: `apply_pair_tag_bestowal` for inserts (idempotent
# against the unique partial index on active rows) and `clear_pair_tag` for
# retiring an ephemeral relation.
#
# Predicates (`has_pair_tag`, inbound/outbound subject lookups) and the
# binding-composer extension live in a separate module to keep the writer
# focused on writes.


def apply_pair_tag_bestowal(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    subject_kind: str,
    object_kind: str,
    tag: str,
    source_kind: str = "skald_inline",
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
) -> bool:
    """Apply a directed multi-entity tag (relation) from subject to object.

    Looks up the pair_tag by name, validates that ``subject_kind`` /
    ``object_kind`` are members of the relation's allowed-kinds arrays, and
    inserts a row into ``entity_pair_tags``. Idempotent via ``ON CONFLICT``
    against ``ix_entity_pair_tags_current`` (the unique partial index covering
    active rows).

    Caller owns the transaction; no commits here.

    Returns ``True`` if a new active row was inserted, ``False`` if an active
    row for ``(subject, object, pair_tag)`` already existed (silently
    suppressed).

    Raises ``ValueError`` for:
    - subject_entity_id == object_entity_id (self-loop)
    - unknown / deprecated ``tag``
    - ``subject_kind`` not in the tag's allowed subject_kinds
    - ``object_kind`` not in the tag's allowed object_kinds

    Note: ``subject_kind`` / ``object_kind`` are validated against the
    pair_tag's allowed-kinds arrays only — they are NOT cross-checked against
    the actual ``entities.kind`` values of the supplied entity IDs. Callers
    must ensure ``subject_kind`` and ``object_kind`` correctly describe the
    underlying entities; passing mismatched kind labels is undefined behavior
    that this function will silently accept.
    """

    _validate_source_kind(source_kind)
    if tag.startswith("status:"):
        raise ValueError(
            f"pair_tag {tag!r} belongs to the exclusive status ladder; "
            "use apply_status_pair_tag_bestowal"
        )
    if subject_entity_id == object_entity_id:
        raise ValueError(
            f"pair_tag {tag!r} requires distinct subject and object; "
            f"got subject_entity_id == object_entity_id == {subject_entity_id}"
        )

    row = _lookup_pair_tag_row(cur, tag)
    pair_tag_id = _row_value(row, "id", 0)
    subject_kinds = _row_value(row, "subject_kinds", 1)
    object_kinds = _row_value(row, "object_kinds", 2)
    _validate_pair_tag_kinds(
        tag=tag,
        subject_kind=subject_kind,
        object_kind=object_kind,
        subject_kinds=subject_kinds,
        object_kinds=object_kinds,
    )

    if world_time is None:
        if source_chunk_id is not None:
            # Chunk-keyed rows take the bestowing chunk's clock or stay NULL —
            # never the global-max fallback, which would stamp an "exact" row
            # with a wrong world time when chunk metadata is missing.
            world_time = _chunk_world_time(cur, source_chunk_id)
        else:
            world_time = _load_world_time(cur)

    return _insert_pair_tag_row(
        cur,
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        pair_tag_id=pair_tag_id,
        source_kind=source_kind,
        world_time=world_time,
        source_chunk_id=source_chunk_id,
    )


def _lookup_pair_tag_row(cur: Any, tag: str) -> Any:
    cur.execute(
        """
        SELECT id, subject_kinds, object_kinds
        FROM pair_tags
        WHERE tag = %s AND NOT deprecated
        """,
        (tag,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Unknown or deprecated pair_tag {tag!r}")
    return row


def validate_pair_tag_endpoint(
    cur: Any,
    *,
    tag: str,
    entity_kind: str,
    role: Literal["subject", "object"],
) -> None:
    """Validate one known endpoint of a registered directed pair tag.

    Declaration hints name the other endpoint but do not resolve it yet, so
    generation and commit can only validate the declared entity's side of the
    relation.  The registry lookup and kind rules intentionally share the same
    primitives as :func:`apply_pair_tag_bestowal`.
    """

    if entity_kind not in VALID_ENTITY_KINDS:
        raise ValueError(
            f"Unknown entity_kind={entity_kind!r}; expected one of "
            f"{sorted(VALID_ENTITY_KINDS)}"
        )

    row = _lookup_pair_tag_row(cur, tag)
    allowed_index = 1 if role == "subject" else 2
    allowed_key = "subject_kinds" if role == "subject" else "object_kinds"
    allowed = _row_value(row, allowed_key, allowed_index) or []
    if entity_kind not in allowed:
        raise ValueError(
            f"pair_tag {tag!r} does not allow {role}_kind={entity_kind!r}; "
            f"allowed: {sorted(allowed)}"
        )


def _validate_pair_tag_kinds(
    *,
    tag: str,
    subject_kind: str,
    object_kind: str,
    subject_kinds: list[str],
    object_kinds: list[str],
) -> None:
    if subject_kind not in subject_kinds:
        raise ValueError(
            f"pair_tag {tag!r} does not allow subject_kind={subject_kind!r}; "
            f"allowed: {sorted(subject_kinds)}"
        )
    if object_kind not in object_kinds:
        raise ValueError(
            f"pair_tag {tag!r} does not allow object_kind={object_kind!r}; "
            f"allowed: {sorted(object_kinds)}"
        )


def _insert_pair_tag_row(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    pair_tag_id: int,
    source_kind: str,
    world_time: Optional[datetime],
    source_chunk_id: Optional[int] = None,
    template_id: Optional[str] = None,
) -> bool:
    cur.execute(
        """
        INSERT INTO entity_pair_tags (
            subject_entity_id, object_entity_id, pair_tag_id,
            applied_at_world_time, source_kind, source_chunk_id, template_id
        )
        VALUES (%s, %s, %s, %s, %s::entity_tag_source_kind, %s, %s)
        ON CONFLICT (subject_entity_id, object_entity_id, pair_tag_id)
          WHERE cleared_at IS NULL
          DO NOTHING
        """,
        (
            subject_entity_id,
            object_entity_id,
            pair_tag_id,
            world_time,
            source_kind,
            source_chunk_id,
            template_id,
        ),
    )
    return bool(cur.rowcount)


def apply_status_pair_tag_bestowal(
    cur: Any,
    *,
    subject_entity_id: int,
    scope_faction_entity_id: int,
    subject_kind: str,
    level: str,
    source_kind: str = "skald_inline",
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
    template_id: Optional[str] = None,
) -> bool:
    """Replace the active ``status:*`` level for one subject→faction edge.

    Status is multi-valued across different scope factions, but exclusive within
    a single ``(subject, scope_faction)`` edge. This helper clears active
    sibling ``status:*`` rows for that edge before applying ``status:<level>``.
    """

    tag = status_tag_for_level(level)
    _validate_source_kind(source_kind)
    if subject_entity_id == scope_faction_entity_id:
        raise ValueError(
            f"pair_tag {tag!r} requires distinct subject and object; "
            "got subject_entity_id == scope_faction_entity_id == "
            f"{subject_entity_id}"
        )
    row = _lookup_pair_tag_row(cur, tag)
    pair_tag_id = _row_value(row, "id", 0)
    cur.execute(
        "SELECT kind::text AS kind FROM entities WHERE id = %s",
        (scope_faction_entity_id,),
    )
    scope_row = cur.fetchone()
    if scope_row is None:
        raise ValueError(
            "Status scope_faction_entity_id="
            f"{scope_faction_entity_id} does not resolve on the entities spine"
        )
    actual_scope_kind = str(_row_value(scope_row, "kind", 0))
    if actual_scope_kind != "faction":
        raise ValueError(
            "Status scope_faction_entity_id="
            f"{scope_faction_entity_id} has actual kind {actual_scope_kind!r}; "
            "expected 'faction'"
        )
    _validate_pair_tag_kinds(
        tag=tag,
        subject_kind=subject_kind,
        object_kind="faction",
        subject_kinds=_row_value(row, "subject_kinds", 1),
        object_kinds=_row_value(row, "object_kinds", 2),
    )
    if world_time is None:
        if source_chunk_id is not None:
            # Chunk-keyed rows take the bestowing chunk's clock or stay NULL —
            # never the global-max fallback, which would stamp an "exact" row
            # with a wrong world time when chunk metadata is missing.
            world_time = _chunk_world_time(cur, source_chunk_id)
        else:
            world_time = _load_world_time(cur)

    _clear_pair_tags_by_name(
        cur,
        subject_entity_id=subject_entity_id,
        object_entity_id=scope_faction_entity_id,
        tags=STATUS_TAGS - {tag},
        world_time=world_time,
        source_chunk_id=source_chunk_id,
        reason="status_ladder_replace",
    )
    return _insert_pair_tag_row(
        cur,
        subject_entity_id=subject_entity_id,
        object_entity_id=scope_faction_entity_id,
        pair_tag_id=pair_tag_id,
        source_kind=source_kind,
        world_time=world_time,
        source_chunk_id=source_chunk_id,
        template_id=template_id,
    )


def clear_pair_tag(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tag: str,
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
) -> bool:
    """Mark an active multi-entity tag as cleared (UPDATE cleared_at = now()).

    Used to retire ephemeral relations when their establishing context no
    longer holds (e.g., a `hunting` relation when the hunters give up).
    Durable relations can also be cleared if narrative or substrate updates
    require it.

    Returns ``True`` if a row was cleared, ``False`` if no active row existed
    for ``(subject, object, pair_tag)``.

    Note: unknown or deprecated ``tag`` names silently return ``False``
    rather than raising — this is the inverse of ``apply_pair_tag_bestowal``,
    which raises ``ValueError`` for unknown tags. The asymmetry is deliberate:
    clearing a relation that doesn't exist is a no-op, so an unknown tag is
    indistinguishable from a missing row. Callers should not interpret
    ``False`` as "previously cleared" versus "tag doesn't exist."
    """

    cur.execute(
        """
        UPDATE entity_pair_tags ept
        SET cleared_at = now()
        FROM pair_tags pt
        WHERE ept.pair_tag_id = pt.id
          AND pt.tag = %s
          AND ept.subject_entity_id = %s
          AND ept.object_entity_id = %s
          AND ept.cleared_at IS NULL
        RETURNING ept.id
        """,
        (tag, subject_entity_id, object_entity_id),
    )
    cleared_ids = [_row_value(row, "id", 0) for row in cur.fetchall()]
    for pair_tag_row_id in cleared_ids:
        _log_pair_tag_clearance(
            cur,
            entity_pair_tag_id=pair_tag_row_id,
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason="clear_pair_tag",
        )
    return bool(cleared_ids)


def _clear_pair_tags_by_name(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tags: AbstractSet[str],
    world_time: Optional[datetime] = None,
    source_chunk_id: Optional[int] = None,
    reason: str = "clear_pair_tags_by_name",
) -> int:
    if not tags:
        return 0
    cur.execute(
        """
        UPDATE entity_pair_tags ept
        SET cleared_at = now()
        FROM pair_tags pt
        WHERE ept.pair_tag_id = pt.id
          AND ept.subject_entity_id = %s
          AND ept.object_entity_id = %s
          AND pt.tag = ANY(%s)
          AND ept.cleared_at IS NULL
        RETURNING ept.id
        """,
        (subject_entity_id, object_entity_id, sorted(tags)),
    )
    cleared_ids = [_row_value(row, "id", 0) for row in cur.fetchall()]
    for pair_tag_row_id in cleared_ids:
        _log_pair_tag_clearance(
            cur,
            entity_pair_tag_id=pair_tag_row_id,
            world_time=world_time,
            source_chunk_id=source_chunk_id,
            reason=reason,
        )
    return len(cleared_ids)
