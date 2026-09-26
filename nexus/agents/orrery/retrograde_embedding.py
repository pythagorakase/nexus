"""Embedding lifecycle for the dedicated Retrograde summary corpus.

The orchestration lives in :mod:`nexus.agents.memnon.utils.source_embeddings`;
this module keeps the summary corpus's public entry points.
"""

from __future__ import annotations

from typing import Any, Sequence

from nexus.agents.memnon.utils.source_embeddings import (
    RETROGRADE_SUMMARY_SOURCE,
    active_memnon_embedding_model_dimensions,
    embed_source_rows,
    normalized_source_ids,
)

__all__ = ["active_memnon_embedding_model_dimensions", "embed_retrograde_summaries"]


def _normalized_summary_ids(summary_ids: Sequence[int]) -> list[int]:
    """Return unique positive summary ids while preserving caller order."""
    return normalized_source_ids(RETROGRADE_SUMMARY_SOURCE, summary_ids)


def embed_retrograde_summaries(
    dbname: str,
    summary_ids: Sequence[int],
) -> list[dict[str, Any]]:
    """Embed summaries into their own dimension-specific corpus.

    All embeddings are generated before the write transaction begins. The
    transaction then creates any newly discovered dimension tables, upserts
    every active model's vector, and stamps ``embedding_generated_at``. If any
    model generation or database write fails, no requested summary receives
    the ironman stamp and the whole set remains retryable.

    Args:
        dbname: Valid slot database name (``save_01`` through ``save_05``).
        summary_ids: Dedicated ``retrograde_summaries.id`` values.

    Returns:
        One entry per summary, in caller order, describing stored models and
        dimensions.

    Raises:
        RuntimeError: If a summary is missing, no model is active, or any
            active model fails to generate an embedding.
        ValueError: If any summary id is not positive.
    """
    return embed_source_rows(dbname, RETROGRADE_SUMMARY_SOURCE, summary_ids)
