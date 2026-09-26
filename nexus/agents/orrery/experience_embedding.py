"""All-or-nothing embeddings for rendered character experiences.

The orchestration lives in :mod:`nexus.agents.memnon.utils.source_embeddings`;
this module keeps the actor-experience corpus's public entry point.
"""

from __future__ import annotations

from typing import Any, Sequence

from nexus.agents.memnon.utils.source_embeddings import (
    CHARACTER_EXPERIENCE_SOURCE,
    embed_source_rows,
)


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
