"""Byte-identity of the shared MEMNON retrieval result builders (#848).

Each ``_legacy_*`` oracle below wraps the inline dict literal a search path
built before the builders existed, copied verbatim from ``db_access.py`` and
``search.py`` at ce1d9dea. The builders must reproduce those dicts exactly:
same keys, same key order, same value types, so JSON payloads, logs and the
cross-encoder's inputs are unchanged byte for byte.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

import pytest

from nexus.agents.memnon.utils.results import (
    narrative_metadata,
    narrative_result,
    retrograde_summary_memory_id,
    retrograde_summary_result,
)

WORLD_TIME = datetime(2073, 11, 2, 21, 15, tzinfo=timezone.utc)
CREATED_AT = datetime(2089, 4, 3, 8, 30, tzinfo=timezone.utc)
MODEL = "embedder-under-test"


def _assert_byte_identical(built: Dict[str, Any], legacy: Dict[str, Any]) -> None:
    """Equal values, identical key order and identical serialized bytes."""
    assert built == legacy
    assert repr(built) == repr(legacy)
    assert (
        json.dumps(built, default=str).encode()
        == json.dumps(legacy, default=str).encode()
    )


# Legacy oracles: dict literals verbatim from ce1d9dea.


def _legacy_retrograde_summary_result(
    summary_id: int,
    summary_text: str,
    world_event_id: int,
    recorded_at_chunk_id: Optional[int],
    chronology: Any,
    created_at: Any,
) -> Dict[str, Any]:
    memory_id = f"retrograde_summary:{int(summary_id)}"
    serialized_created_at = (
        created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
    )
    return {
        "id": memory_id,
        "memory_id": memory_id,
        "summary_id": int(summary_id),
        "world_event_id": int(world_event_id),
        "text": summary_text,
        "content_type": "retrograde_summary",
        "metadata": {
            "summary_id": int(summary_id),
            "world_event_id": int(world_event_id),
            "recorded_at_chunk_id": (
                int(recorded_at_chunk_id) if recorded_at_chunk_id is not None else None
            ),
            "chronology": chronology,
            "created_at": serialized_created_at,
        },
        "model_scores": {},
        "text_score": 0.0,
        "vector_score": 0.0,
    }


def _legacy_vector_search_narrative(row: tuple[Any, ...]) -> Dict[str, Any]:
    """db_access.execute_vector_search, narrative candidate."""
    (chunk_id, raw_text, season, episode, scene_number, world_time, score) = row
    chunk_id = str(chunk_id)
    return {
        "id": chunk_id,
        "chunk_id": chunk_id,
        "text": raw_text,
        "content_type": "narrative",
        "metadata": {
            "season": season,
            "episode": episode,
            "scene_number": scene_number,
            "world_time": world_time,
        },
        "model_scores": {},
        "score": float(score) if score is not None else 0.0,
        "source": "vector_search",
    }


def _legacy_hybrid_text_narrative(row: tuple[Any, ...]) -> Dict[str, Any]:
    """db_access.execute_multi_model_hybrid_search, first text pass."""
    (chunk_id, raw_text, season, episode, scene_number, world_time, text_score) = row
    text_score = float(text_score)
    chunk_id = str(chunk_id)
    return {
        "id": chunk_id,
        "chunk_id": chunk_id,
        "text": raw_text,
        "content_type": "narrative",
        "metadata": {
            "season": season,
            "episode": episode,
            "scene_number": scene_number,
            "world_time": world_time,
        },
        "model_scores": {},  # Will store scores for each model
        "text_score": 0.0,  # Will be normalized
        "vector_score": 0.0,  # Will be calculated as weighted average of model scores
        "raw_text_score": text_score,  # Keep raw score temporarily
    }


def _legacy_hybrid_like_narrative(row: tuple[Any, ...]) -> Dict[str, Any]:
    """db_access.execute_multi_model_hybrid_search, single-token ILIKE pass."""
    (chunk_id, raw_text, season, episode, scene_number, world_time) = row
    chunk_id = str(chunk_id)
    return {
        "id": chunk_id,
        "chunk_id": chunk_id,
        "text": raw_text,
        "content_type": "narrative",
        "metadata": {
            "season": season,
            "episode": episode,
            "scene_number": scene_number,
            "world_time": world_time,
        },
        "model_scores": {},
        "text_score": 0.05,
        "vector_score": 0.0,
    }


def _legacy_hybrid_vector_only_narrative(
    chunk_id: str,
    details: tuple[Any, ...],
    model_key: str,
    vector_score: float,
    normalized_text_score: float,
) -> Dict[str, Any]:
    """db_access.execute_multi_model_hybrid_search, vector-only candidate."""
    raw_text, season, episode, scene_number = details
    return {
        "id": chunk_id,
        "chunk_id": chunk_id,
        "text": raw_text,
        "content_type": "narrative",
        "metadata": {
            "season": season,
            "episode": episode,
            "scene_number": scene_number,
        },
        "model_scores": {model_key: vector_score},
        "text_score": float(normalized_text_score),
        "vector_score": 0.0,  # Will be calculated next
    }


def _legacy_text_search_narrative(row: tuple[Any, ...], source: str) -> Dict[str, Any]:
    """search.SearchManager.text_search, websearch and ILIKE passes."""
    chunk_id, raw_text, season, episode, scene_number, score, highlights = row
    return {
        "id": str(chunk_id),
        "chunk_id": str(chunk_id),
        "text": raw_text,
        "content_type": "narrative",
        "metadata": {
            "season": season,
            "episode": episode,
            "scene_number": scene_number,
            "highlights": highlights,
        },
        "score": float(score),
        "source": source,
    }


# Representative rows: int and str ids, NULL world_time and chunk anchors.

NARRATIVE_ROWS = [
    (1369, "Alex keeps the ledger dry.", 2, 7, 3, WORLD_TIME),
    (12, "A null clock scene.", 1, 1, 1, None),
]
SUMMARY_ROWS = [
    (17, "The Saltline mirrors carried Orji's case.", 91, 133, "deep_past", CREATED_AT),
    (18, "An unanchored rumor.", 92, None, "recent_past", "2089-04-03T08:30:00"),
]


@pytest.mark.parametrize("row", NARRATIVE_ROWS)
@pytest.mark.parametrize("score", [0.8123, None])
def test_vector_search_narrative_result_is_byte_identical(
    row: tuple[Any, ...], score: Optional[float]
) -> None:
    """execute_vector_search keeps model_scores, score and source in place."""
    chunk_id, raw_text, season, episode, scene_number, world_time = row
    built = narrative_result(
        str(chunk_id),
        raw_text,
        narrative_metadata(season, episode, scene_number, world_time=world_time),
        model_scores={},
        score=float(score) if score is not None else 0.0,
        source="vector_search",
    )
    _assert_byte_identical(built, _legacy_vector_search_narrative((*row, score)))


@pytest.mark.parametrize("row", NARRATIVE_ROWS)
def test_hybrid_text_pass_narrative_result_is_byte_identical(
    row: tuple[Any, ...],
) -> None:
    """The raw text score still lands after the three score fields."""
    chunk_id, raw_text, season, episode, scene_number, world_time = row
    built = narrative_result(
        str(chunk_id),
        raw_text,
        narrative_metadata(season, episode, scene_number, world_time=world_time),
        model_scores={},
        text_score=0.0,
        vector_score=0.0,
    )
    built["raw_text_score"] = 0.42
    _assert_byte_identical(built, _legacy_hybrid_text_narrative((*row, 0.42)))


@pytest.mark.parametrize("row", NARRATIVE_ROWS)
def test_hybrid_like_pass_narrative_result_is_byte_identical(
    row: tuple[Any, ...],
) -> None:
    """The single-token ILIKE pass keeps its fixed 0.05 text score."""
    chunk_id, raw_text, season, episode, scene_number, world_time = row
    built = narrative_result(
        str(chunk_id),
        raw_text,
        narrative_metadata(season, episode, scene_number, world_time=world_time),
        model_scores={},
        text_score=0.05,
        vector_score=0.0,
    )
    _assert_byte_identical(built, _legacy_hybrid_like_narrative(row))


def test_hybrid_vector_only_narrative_result_is_byte_identical() -> None:
    """A vector-only candidate has no world_time and one model score."""
    details = ("Only the vector found this.", 3, 2, 9)
    built = narrative_result(
        "404",
        details[0],
        narrative_metadata(*details[1:]),
        model_scores={MODEL: 0.61},
        text_score=float(0.25),
        vector_score=0.0,
    )
    _assert_byte_identical(
        built, _legacy_hybrid_vector_only_narrative("404", details, MODEL, 0.61, 0.25)
    )


@pytest.mark.parametrize("source", ["text_search", "text_search_like"])
@pytest.mark.parametrize("highlights", ["<b>ledger</b> dry", None])
def test_text_search_narrative_result_is_byte_identical(
    source: str, highlights: Optional[str]
) -> None:
    """SearchManager.text_search results carry no model_scores key."""
    row = (1369, "Alex keeps the ledger dry.", 2, 7, 3, 0.05, highlights)
    chunk_id, raw_text, season, episode, scene_number, score, _ = row
    built = narrative_result(
        chunk_id,
        raw_text,
        narrative_metadata(season, episode, scene_number, highlights=highlights),
        score=float(score),
        source=source,
    )
    assert "model_scores" not in built
    _assert_byte_identical(built, _legacy_text_search_narrative(row, source))


@pytest.mark.parametrize("row", SUMMARY_ROWS)
def test_plain_summary_result_is_byte_identical(row: tuple[Any, ...]) -> None:
    """The default summary shape matches the former private builder."""
    _assert_byte_identical(
        retrograde_summary_result(*row), _legacy_retrograde_summary_result(*row)
    )


@pytest.mark.parametrize("row", SUMMARY_ROWS)
def test_summary_vector_search_result_is_byte_identical(
    row: tuple[Any, ...],
) -> None:
    """_execute_retrograde_summary_vector_search's update() is folded in."""
    legacy = _legacy_retrograde_summary_result(*row)
    legacy.update(
        {"model_scores": {MODEL: 0.77}, "score": 0.77, "source": "vector_search"}
    )
    built = retrograde_summary_result(
        *row, model_scores={MODEL: 0.77}, score=0.77, source="vector_search"
    )
    _assert_byte_identical(built, legacy)


@pytest.mark.parametrize("row", SUMMARY_ROWS)
def test_summary_hybrid_paths_are_byte_identical(row: tuple[Any, ...]) -> None:
    """Text-pass, ILIKE and vector-only summary results keep their shapes."""
    text_pass = _legacy_retrograde_summary_result(*row)
    text_pass["raw_text_score"] = 0.3
    built_text_pass = retrograde_summary_result(*row)
    built_text_pass["raw_text_score"] = 0.3
    _assert_byte_identical(built_text_pass, text_pass)

    like = _legacy_retrograde_summary_result(*row)
    like["text_score"] = 0.05
    _assert_byte_identical(retrograde_summary_result(*row, text_score=0.05), like)

    vector_only = _legacy_retrograde_summary_result(*row)
    vector_only.update({"model_scores": {MODEL: 0.5}, "text_score": float(0.2)})
    _assert_byte_identical(
        retrograde_summary_result(*row, model_scores={MODEL: 0.5}, text_score=0.2),
        vector_only,
    )


@pytest.mark.parametrize(
    "source,score", [("text_search", 0.33), ("text_search_like", 0.05)]
)
def test_summary_text_search_results_are_byte_identical(
    source: str, score: float
) -> None:
    """SearchManager.text_search summary results, highlights included."""
    row = SUMMARY_ROWS[0]
    legacy = _legacy_retrograde_summary_result(*row)
    built = retrograde_summary_result(*row, score=score, source=source)
    if source == "text_search":
        legacy["metadata"]["highlights"] = "<b>Saltline</b>"
        built["metadata"]["highlights"] = "<b>Saltline</b>"
    legacy.update({"score": score, "source": source})
    _assert_byte_identical(built, legacy)


def test_summary_identity_never_masquerades_as_a_chunk() -> None:
    """Typed summary identities and narrative identities stay disjoint."""
    summary = retrograde_summary_result(*SUMMARY_ROWS[0])
    narrative = narrative_result(17, "Chunk seventeen.", narrative_metadata(1, 1, 1))

    assert summary["id"] == retrograde_summary_memory_id(17) == "retrograde_summary:17"
    assert "chunk_id" not in summary
    assert narrative["id"] == narrative["chunk_id"] == "17"
    assert "memory_id" not in narrative


def test_default_summary_model_scores_are_not_shared() -> None:
    """Each summary result owns a fresh model_scores mapping."""
    first = retrograde_summary_result(*SUMMARY_ROWS[0])
    second = retrograde_summary_result(*SUMMARY_ROWS[0])
    first["model_scores"][MODEL] = 0.9

    assert second["model_scores"] == {}
