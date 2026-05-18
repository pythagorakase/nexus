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
``ON CONFLICT`` clause in ``_insert_entity_tag`` matches a unique index.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from nexus.agents.orrery.tag_constants import ALLOWED_CATEGORIES, CANONICAL_TAGS
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

    if entity_kind not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"Unknown entity_kind={entity_kind!r}; expected one of "
            f"{sorted(ALLOWED_CATEGORIES)}"
        )

    allowed = ALLOWED_CATEGORIES[entity_kind]

    if world_time is None:
        cur.execute("SELECT max(world_time) AS world_time FROM chunk_metadata")
        row = cur.fetchone()
        if row is not None:
            world_time = _row_value(row, "world_time", 0)

    # 1. insert new tag proposals into the vocabulary
    for proposal in bestowal.new_tag_proposals:
        _insert_new_tag(cur, proposal)
        counters["proposed"] += 1

    # 2. apply tags (registered + just-proposed) to the entity
    for proposed_name in _iter_apply_names(bestowal):
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


def _iter_apply_names(bestowal: OrreryTagBestowal) -> Iterable[str]:
    yield from bestowal.applied_tags
    yield from (p.tag for p in bestowal.new_tag_proposals)


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
