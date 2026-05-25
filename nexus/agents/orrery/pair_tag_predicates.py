"""DB-level read helpers for multi-entity (pair) tag predicates.

These helpers wrap the ``entity_pair_tags`` / ``pair_tags`` join pattern so
callers — the trait → tag compiler, idempotency checks, future predicates
that need to query the live edge set — don't have to repeat the JOIN-and-
filter-by-tag-name idiom.

These are *DB-level* helpers: they take a psycopg2-style cursor and execute
queries directly. They are NOT Condition-shape predicates over an
in-memory ``WorldState`` — that layer is a separate concern (will live in
``nexus.agents.orrery.substrate`` alongside the existing ``has_tag`` /
``lacks_tag`` / etc. predicates) and is added in a follow-up.

All helpers filter to currently-active rows (``cleared_at IS NULL``) and
deprecated pair_tag definitions are silently treated as absent — this
matches the discipline in ``apply_pair_tag_bestowal`` and downstream gates.
"""

from __future__ import annotations

from typing import Any


def _row_value(row: Any, key: str, index: int) -> Any:
    """Read a column from a row that may be a Mapping (RealDictCursor) or sequence.

    The Orrery codebase uses both RealDictCursor (worker paths) and tuple
    cursors (some tests and ad-hoc scripts). Indexing by integer crashes on
    mapping rows with a KeyError; indexing by string crashes on tuple rows
    with a TypeError. This helper handles both transparently.

    Mirrors ``nexus.agents.orrery.tag_writer._row_value``; duplicated here to
    keep the module independently usable rather than coupled to the writer's
    internal helpers.
    """

    if hasattr(row, "get"):
        return row[key]
    return row[index]


def pair_tag_exists(
    cur: Any,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tag: str,
) -> bool:
    """Return True if an active ``entity_pair_tags`` row exists for the triple.

    Useful for idempotency probes (does this relation already exist before
    inserting?), trait-compiler dispatch (should this trait still bestow this
    relation or is it already there?), and gate-condition primitives.

    Deprecated pair_tag definitions are treated as absent — same convention
    as ``apply_pair_tag_bestowal``.
    """

    cur.execute(
        """
        SELECT 1
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        WHERE ept.subject_entity_id = %s
          AND ept.object_entity_id = %s
          AND pt.tag = %s
          AND NOT pt.deprecated
          AND ept.cleared_at IS NULL
        LIMIT 1
        """,
        (subject_entity_id, object_entity_id, tag),
    )
    return cur.fetchone() is not None


def lookup_pair_tag_subjects(
    cur: Any,
    *,
    object_entity_id: int,
    tag: str,
) -> list[int]:
    """Return the entity IDs of all active subjects with relation ``tag`` to
    ``object_entity_id``.

    Inbound lookup: "who has this relation pointing AT me?" — used by gates
    like the targeted-detection-radius logic for ``hunting`` (issue #282)
    where the target entity needs to know who is hunting them.

    Results are returned in ascending subject_entity_id order for
    deterministic enumeration. Empty list if no active rows.
    """

    cur.execute(
        """
        SELECT ept.subject_entity_id AS subject_entity_id
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        WHERE ept.object_entity_id = %s
          AND pt.tag = %s
          AND NOT pt.deprecated
          AND ept.cleared_at IS NULL
        ORDER BY ept.subject_entity_id ASC
        """,
        (object_entity_id, tag),
    )
    return [_row_value(row, "subject_entity_id", 0) for row in cur.fetchall()]


def lookup_pair_tag_objects(
    cur: Any,
    *,
    subject_entity_id: int,
    tag: str,
) -> list[int]:
    """Return the entity IDs of all active objects that ``subject_entity_id``
    has relation ``tag`` to.

    Outbound lookup: "what does this entity have this relation with?" — used
    by the binding composer (a character's `mentors` outbound list = the set
    of students they should be paired with for MENTOR-flavored package
    bindings) and by the trait compiler when reconciling
    user-declared relations against existing rows.

    Results are returned in ascending object_entity_id order. Empty list if
    no active rows.
    """

    cur.execute(
        """
        SELECT ept.object_entity_id AS object_entity_id
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        WHERE ept.subject_entity_id = %s
          AND pt.tag = %s
          AND NOT pt.deprecated
          AND ept.cleared_at IS NULL
        ORDER BY ept.object_entity_id ASC
        """,
        (subject_entity_id, tag),
    )
    return [_row_value(row, "object_entity_id", 0) for row in cur.fetchall()]
