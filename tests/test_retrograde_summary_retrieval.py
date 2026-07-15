"""Pure contract tests for the dedicated Retrograde summary corpus."""

from datetime import datetime, timezone

import pytest

from nexus.agents.memnon.utils.continuous_temporal_search import (
    result_temporal_anchor,
)
from nexus.agents.memnon.utils.db_access import (
    _retrograde_summaries_allowed,
    _retrograde_summary_result,
)
from nexus.agents.memnon.utils.embedding_tables import (
    parse_retrograde_summary_embedding_table_dimensions,
    retrograde_summary_table_name_for_dimensions,
)
from nexus.agents.orrery.retrograde_embedding import _normalized_summary_ids


def test_retrograde_summary_embedding_table_names_are_dimension_specific() -> None:
    """Summary vectors use their own dynamically named dimension tables."""
    assert (
        retrograde_summary_table_name_for_dimensions(2560)
        == "retrograde_summary_embeddings_2560d"
    )
    assert (
        parse_retrograde_summary_embedding_table_dimensions(
            "retrograde_summary_embeddings_0384d"
        )
        == 384
    )
    assert (
        parse_retrograde_summary_embedding_table_dimensions("chunk_embeddings_2560d")
        is None
    )


def test_retrograde_summary_result_keeps_typed_identity() -> None:
    """A summary result never masquerades as a narrative chunk."""
    created_at = datetime(2089, 4, 3, tzinfo=timezone.utc)
    result = _retrograde_summary_result(
        17,
        "The Saltline mirrors carried Orji's damaged case.",
        91,
        133,
        {"before": "crossing", "after": "relay"},
        created_at,
    )

    assert result["id"] == "retrograde_summary:17"
    assert result["memory_id"] == "retrograde_summary:17"
    assert result["summary_id"] == 17
    assert result["world_event_id"] == 91
    assert result["content_type"] == "retrograde_summary"
    assert "chunk_id" not in result
    assert result["metadata"]["recorded_at_chunk_id"] == 133
    assert result["metadata"]["created_at"] == created_at.isoformat()
    assert result_temporal_anchor(result) == 133


def test_summary_id_normalization_is_stable_and_strict() -> None:
    """Embedding requests deduplicate in order and reject invalid ids."""
    assert _normalized_summary_ids([9, 2, 9, 4]) == [9, 2, 4]
    with pytest.raises(ValueError, match="must be positive"):
        _normalized_summary_ids([0])


def test_narrative_metadata_filters_do_not_leak_to_summary_corpus() -> None:
    """Summary candidates are excluded when their rows cannot honor a filter."""
    assert _retrograde_summaries_allowed(None)
    assert _retrograde_summaries_allowed({"unrecognized_hint": "value"})
    assert not _retrograde_summaries_allowed({"season": 2})
    assert not _retrograde_summaries_allowed({"world_layer": "dream"})
