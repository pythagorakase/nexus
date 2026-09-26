"""All-or-nothing embeddings for rendered character experiences.

The orchestration lives in :mod:`nexus.agents.memnon.utils.source_embeddings`;
this module keeps the actor-experience corpus's public entry point and the
deferred-work drain that embeds recollections after their render commits.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from nexus.agents.memnon.utils.source_embeddings import (
    CHARACTER_EXPERIENCE_SOURCE,
    embed_source_rows,
)
from nexus.agents.orrery.experiences import experience_settings

UNEMBEDDED_RENDERED_EXPERIENCE_PREDICATE = (
    "experience_text IS NOT NULL"
    " AND embedding_generated_at IS NULL"
    " AND invalidation_status = 'valid'"
)
"""Rows the embedding drain owes vectors: rendered, valid and unstamped."""


def _first_value(row: Any, key: str) -> Any:
    """Read one column from a dict-style or tuple-style cursor row."""
    return row[key] if isinstance(row, Mapping) else row[0]


def embed_character_experiences(
    dbname: str,
    experience_ids: Sequence[int],
) -> list[dict[str, Any]]:
    """Embed rendered recollections and stamp only after every vector upsert.

    Every active-model embedding is generated before the write transaction.
    Dimension tables, all model vectors, and every ironman timestamp then land
    in one transaction. A generation or write failure leaves the entire input
    set unstamped and retryable. Only valid, rendered experiences embed.
    """
    return embed_source_rows(dbname, CHARACTER_EXPERIENCE_SOURCE, experience_ids)


def unembedded_rendered_experience_ids(cur: Any, limit: int) -> list[int]:
    """Return up to ``limit`` of the oldest experiences still owed vectors.

    Args:
        cur: Open DBAPI cursor, dict-style or tuple-style.
        limit: Maximum ids to return; must be positive.

    Raises:
        ValueError: If ``limit`` is not positive.
    """
    if limit < 1:
        raise ValueError(f"Experience embedding limit must be positive, got {limit}")
    cur.execute(
        f"""
        SELECT id FROM character_experiences
        WHERE {UNEMBEDDED_RENDERED_EXPERIENCE_PREDICATE}
        ORDER BY id
        LIMIT %s
        """,
        (limit,),
    )
    return [int(_first_value(row, "id")) for row in cur.fetchall()]


def count_unembedded_rendered_experiences(cur: Any) -> int:
    """Count rendered, valid experiences whose vectors are not yet stamped."""
    cur.execute(
        f"""
        SELECT count(*) AS unembedded
        FROM character_experiences
        WHERE {UNEMBEDDED_RENDERED_EXPERIENCE_PREDICATE}
        """
    )
    return int(_first_value(cur.fetchone(), "unembedded"))


def drain_experience_embeddings_sync(
    conn: Any,
    *,
    dbname: str,
    settings: Mapping[str, Any],
    limit: int,
) -> int:
    """Embed the oldest rendered, unembedded experiences, all or nothing.

    Selection reads through ``conn``; embedding and the ironman stamp run
    through :func:`embed_character_experiences` on ``dbname``. A failure
    raises with every selected row still unstamped, so the next drain
    retries it.

    Args:
        conn: Open DBAPI connection to the slot database named by ``dbname``.
        dbname: Slot database whose experiences are embedded.
        settings: Full settings mapping; a disabled ``[orrery.experiences]``
            drains nothing.
        limit: Maximum experiences to embed in this call; must be positive.

    Returns:
        The number of experiences embedded and stamped.
    """
    if not experience_settings(settings).enabled:
        return 0
    with conn, conn.cursor() as cur:
        experience_ids = unembedded_rendered_experience_ids(cur, limit)
    if not experience_ids:
        return 0
    return len(embed_character_experiences(dbname, experience_ids))
