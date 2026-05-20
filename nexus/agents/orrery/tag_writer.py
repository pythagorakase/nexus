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

from nexus.agents.orrery.tag_constants import CANONICAL_TAGS
from nexus.agents.orrery.tag_library import VALID_ENTITY_KINDS
from nexus.agents.orrery.tag_schemas import NewTagProposal, OrreryTagBestowal


_SKALD_EPHEMERAL_CLEARANCE = "semantic"


def apply_tag_bestowal(
    cur: Any,
    *,
    entity_id: int,
    entity_kind: str,
    bestowal: Optional[OrreryTagBestowal],
    source_kind: str = "skald_inline",
    world_time: Optional[datetime] = None,
) -> dict[str, int]:
    """Apply a Skald-issued tag bestowal to the database.

    Performs three operations in order:

    1. Insert each new tag proposal into ``tags`` (idempotent via
       ``ON CONFLICT (tag) DO NOTHING``).
    2. Apply registered + just-proposed tag names to the entity via
       ``entity_tags`` insert.
    3. Mark ``tags_to_clear`` entries cleared (UPDATE cleared_at = now()).

    Requires migration 037's ``tag_category_registry`` rows for the target
    ``entity_kind``; missing registry data is treated as a slot-migration error.

    Returns counter dict suitable for logging:
    ``{"applied", "proposed", "cleared", "skipped_category", "skipped_unknown"}``.
    """

    counters = {
        "applied": 0,
        "proposed": 0,
        "cleared": 0,
        "skipped_category": 0,
        "skipped_unknown": 0,
    }

    if bestowal is None:
        return counters

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

    apply_names = list(bestowal.applied_tags)

    # 1. insert new tag proposals into the vocabulary
    for proposal in bestowal.new_tag_proposals:
        if proposal.category not in allowed:
            status = _category_registry_status(cur, proposal.category, entity_kind)
            if status == "unknown":
                _insert_category_registry_row(
                    cur, category=proposal.category, entity_kind=entity_kind
                )
                allowed.add(proposal.category)
            else:
                counters["skipped_category"] += 1
                continue
        _insert_new_tag(cur, proposal)
        counters["proposed"] += 1
        apply_names.append(proposal.tag)

    # 2. apply tags (registered + just-proposed) to the entity
    for proposed_name in apply_names:
        canonical_name = CANONICAL_TAGS.get(proposed_name, proposed_name)
        tag_row = _lookup_tag(cur, canonical_name)
        if tag_row is None:
            counters["skipped_unknown"] += 1
            continue
        category = _row_value(tag_row, "category", 1)
        if category not in allowed:
            counters["skipped_category"] += 1
            continue
        tag_id = _row_value(tag_row, "id", 0)
        applied = _insert_entity_tag(
            cur,
            entity_id=entity_id,
            tag_id=tag_id,
            source_kind=source_kind,
            world_time=world_time,
        )
        if applied:
            counters["applied"] += 1

    # 3. clear tags that no longer apply (update contexts only)
    for clear_name in bestowal.tags_to_clear:
        canonical_clear = CANONICAL_TAGS.get(clear_name, clear_name)
        tag_row = _lookup_tag(cur, canonical_clear)
        if tag_row is None:
            counters["skipped_unknown"] += 1
            continue
        tag_id = _row_value(tag_row, "id", 0)
        if _clear_entity_tag(cur, entity_id=entity_id, tag_id=tag_id):
            counters["cleared"] += 1

    return counters


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


def _category_registry_status(cur: Any, category: str, entity_kind: str) -> str:
    cur.execute(
        """
        SELECT entity_kind::text AS entity_kind
        FROM tag_category_registry
        WHERE category = %s
        """,
        (category,),
    )
    rows = cur.fetchall()
    if not rows:
        return "unknown"
    if any(_row_value(row, "entity_kind", 0) == entity_kind for row in rows):
        return "compatible"
    return "incompatible"


def _insert_category_registry_row(cur: Any, *, category: str, entity_kind: str) -> None:
    cur.execute(
        """
        INSERT INTO tag_category_registry (
            category, entity_kind, prompt_order, description
        ) VALUES (
            %s, %s::entity_kind, 1000, %s
        )
        ON CONFLICT (category, entity_kind) DO NOTHING
        """,
        (
            category,
            entity_kind,
            f"Skald-proposed {entity_kind} tag category.",
        ),
    )


def _insert_new_tag(cur: Any, proposal: NewTagProposal) -> None:
    """Insert proposal into ``tags``. Idempotent via ``ON CONFLICT (tag)``.

    Honors the ``is_ephemeral = (clearance_kind IS NOT NULL)`` check
    constraint by setting ``clearance_kind='semantic'`` for ephemerals and
    ``NULL`` for durables.
    """

    is_ephemeral = proposal.scope == "ephemeral"
    clearance_kind = _SKALD_EPHEMERAL_CLEARANCE if is_ephemeral else None
    description = f"[skald-proposed] {proposal.evidence}"
    cur.execute(
        """
        INSERT INTO tags (tag, category, is_ephemeral, clearance_kind, description)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (tag) DO NOTHING
        """,
        (proposal.tag, proposal.category, is_ephemeral, clearance_kind, description),
    )


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

    if subject_entity_id == object_entity_id:
        raise ValueError(
            f"pair_tag {tag!r} requires distinct subject and object; "
            f"got subject_entity_id == object_entity_id == {subject_entity_id}"
        )

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

    pair_tag_id = _row_value(row, "id", 0)
    subject_kinds = _row_value(row, "subject_kinds", 1)
    object_kinds = _row_value(row, "object_kinds", 2)

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

    if world_time is None:
        cur.execute("SELECT max(world_time) AS world_time FROM chunk_metadata")
        chunk_row = cur.fetchone()
        if chunk_row is not None:
            world_time = _row_value(chunk_row, "world_time", 0)

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
