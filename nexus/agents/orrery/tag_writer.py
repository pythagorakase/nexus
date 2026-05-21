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
``ON CONFLICT`` clause in ``_insert_entity_tag`` matches a unique index, and on
migration 037 seeding ``tag_category_registry`` so runtime bestowals know which
tag categories may be applied to each entity kind.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from nexus.agents.orrery.status_family import STATUS_TAGS, status_tag_for_level
from nexus.agents.orrery.tag_constants import CANONICAL_TAGS
from nexus.agents.orrery.tag_library import VALID_ENTITY_KINDS
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal


_DISALLOWED_SOURCE_KINDS = frozenset({"auto_" "registered"})


def apply_tag_bestowal(
    cur: Any,
    *,
    entity_id: int,
    entity_kind: str,
    bestowal: Optional[OrreryTagBestowal],
    source_kind: str = "skald_inline",
    world_time: Optional[datetime] = None,
) -> dict[str, int]:
    """Apply a closed-vocabulary tag bestowal to the database.

    Performs two operations in order:

    1. Apply registered tag names to the entity via ``entity_tags`` insert.
    2. Mark ``tags_to_clear`` entries cleared (UPDATE cleared_at = now()).

    Requires migration 037's ``tag_category_registry`` rows for the target
    ``entity_kind``; missing registry data is treated as a slot-migration error.
    Unknown, deprecated, or entity-kind-incompatible tags raise ``ValueError``.

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
        cur.execute("SELECT max(world_time) AS world_time FROM chunk_metadata")
        row = cur.fetchone()
        if row is not None:
            world_time = _row_value(row, "world_time", 0)

    tags_to_apply: list[int] = []
    for tag_name in bestowal.applied_tags:
        canonical_name, tag_row = _lookup_canonical_tag(cur, tag_name)
        category = _row_value(tag_row, "category", 1)
        _validate_allowed_category(
            category=category,
            allowed=allowed,
            tag_name=canonical_name,
            entity_kind=entity_kind,
        )
        tags_to_apply.append(_row_value(tag_row, "id", 0))

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
    for tag_id in tags_to_apply:
        applied = _insert_entity_tag(
            cur,
            entity_id=entity_id,
            tag_id=tag_id,
            source_kind=source_kind,
            world_time=world_time,
        )
        if applied:
            counters["applied"] += 1

    # 2. clear tags that no longer apply (update contexts only)
    for tag_id in tags_to_clear:
        if _clear_entity_tag(cur, entity_id=entity_id, tag_id=tag_id):
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
) -> bool:
    """Replace the active tag within a single-entity exclusive category.

    This is the write primitive for documented XOR categories such as
    ``role.fame`` and ``role.resources`` while the registry-level cardinality
    column is still schema-pending. The function clears all active sibling rows
    in the target tag's category for ``entity_id`` before inserting the new tag,
    all inside the caller-owned transaction.

    Returns ``True`` if the new tag row was inserted, ``False`` if it was
    already active. Sibling rows are cleared either way.
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

    if world_time is None:
        world_time = _load_world_time(cur)

    _clear_entity_tag_siblings(
        cur,
        entity_id=entity_id,
        category=category,
        keep_tag_id=tag_id,
    )
    return _insert_entity_tag(
        cur,
        entity_id=entity_id,
        tag_id=tag_id,
        source_kind=source_kind,
        world_time=world_time,
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


def _lookup_tag(cur: Any, tag_name: str) -> Optional[Any]:
    cur.execute(
        """
        SELECT id, category, is_ephemeral
        FROM tags
        WHERE tag = %s AND NOT deprecated AND synonym_for IS NULL
        """,
        (tag_name,),
    )
    return cur.fetchone()


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


def _insert_entity_tag(
    cur: Any,
    *,
    entity_id: int,
    tag_id: int,
    source_kind: str,
    world_time: Optional[datetime],
) -> bool:
    cur.execute(
        """
        INSERT INTO entity_tags (entity_id, tag_id, applied_at_world_time, source_kind)
        VALUES (%s, %s, %s, %s::entity_tag_source_kind)
        ON CONFLICT (entity_id, tag_id)
          WHERE cleared_at IS NULL
          DO NOTHING
        """,
        (entity_id, tag_id, world_time, source_kind),
    )
    return bool(cur.rowcount)


def _clear_entity_tag_siblings(
    cur: Any,
    *,
    entity_id: int,
    category: str,
    keep_tag_id: int,
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
        """,
        (entity_id, category, keep_tag_id),
    )
    return int(cur.rowcount)


def _clear_entity_tag(cur: Any, *, entity_id: int, tag_id: int) -> bool:
    cur.execute(
        """
        UPDATE entity_tags
        SET cleared_at = now()
        WHERE entity_id = %s AND tag_id = %s AND cleared_at IS NULL
        """,
        (entity_id, tag_id),
    )
    return bool(cur.rowcount)


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
        world_time = _load_world_time(cur)

    return _insert_pair_tag_row(
        cur,
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        pair_tag_id=pair_tag_id,
        source_kind=source_kind,
        world_time=world_time,
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
) -> bool:
    cur.execute(
        """
        INSERT INTO entity_pair_tags (
            subject_entity_id, object_entity_id, pair_tag_id,
            applied_at_world_time, source_kind
        )
        VALUES (%s, %s, %s, %s, %s::entity_tag_source_kind)
        ON CONFLICT (subject_entity_id, object_entity_id, pair_tag_id)
          WHERE cleared_at IS NULL
          DO NOTHING
        """,
        (subject_entity_id, object_entity_id, pair_tag_id, world_time, source_kind),
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
            f"got subject_entity_id == object_entity_id == {subject_entity_id}"
        )
    row = _lookup_pair_tag_row(cur, tag)
    pair_tag_id = _row_value(row, "id", 0)
    _validate_pair_tag_kinds(
        tag=tag,
        subject_kind=subject_kind,
        object_kind="faction",
        subject_kinds=_row_value(row, "subject_kinds", 1),
        object_kinds=_row_value(row, "object_kinds", 2),
    )
    if world_time is None:
        world_time = _load_world_time(cur)

    _clear_pair_tags_by_name(
        cur,
        subject_entity_id=subject_entity_id,
        object_entity_id=scope_faction_entity_id,
        tags=STATUS_TAGS - {tag},
    )
    return _insert_pair_tag_row(
        cur,
        subject_entity_id=subject_entity_id,
        object_entity_id=scope_faction_entity_id,
        pair_tag_id=pair_tag_id,
        source_kind=source_kind,
        world_time=world_time,
    )


def clear_pair_tag(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tag: str,
) -> bool:
    """Mark an active multi-entity tag as cleared (UPDATE cleared_at = now()).

    Used to retire ephemeral relations when their establishing context no
    longer holds (e.g., a `pursuing` relation when the pursuers give up).
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
        """,
        (tag, subject_entity_id, object_entity_id),
    )
    return bool(cur.rowcount)


def _clear_pair_tags_by_name(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tags: set[str],
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
        """,
        (subject_entity_id, object_entity_id, sorted(tags)),
    )
    return int(cur.rowcount)
