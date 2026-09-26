"""One retrieval result shape for MEMNON's narrative and summary corpora.

Narrative chunks and Retrograde summaries keep their own storage, identities
and chronology. What they share is the result dict every search path hands to
score fusion, cross-encoder reranking and LORE. The builders here are that
dict's only constructors, so the search paths cannot drift apart in key names,
key order or identity: a Retrograde summary never receives a ``chunk_id``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Required, TypedDict, Union, cast

NARRATIVE_CONTENT_TYPE = "narrative"
RETROGRADE_SUMMARY_CONTENT_TYPE = "retrograde_summary"


class RetrievalResult(TypedDict, total=False):
    """Shape of one MEMNON retrieval candidate.

    ``id``, ``text``, ``content_type`` and ``metadata`` are always present.
    Narrative results add ``chunk_id``; Retrograde summaries add ``memory_id``,
    ``summary_id`` and ``world_event_id`` and never carry a chunk id. Score
    fields follow in the order ``model_scores``, ``text_score``,
    ``vector_score``, ``score``, ``source`` when a path supplies them. Search
    pipelines attach ``raw_text_score`` and ``presence_boost`` afterwards, and
    rerankers add their own keys, so results travel onward as plain dicts.
    """

    id: Required[str]
    chunk_id: str
    memory_id: str
    summary_id: int
    world_event_id: int
    text: Required[str]
    content_type: Required[str]
    metadata: Required[Dict[str, Any]]
    model_scores: Dict[str, float]
    text_score: float
    vector_score: float
    score: float
    source: str


def retrograde_summary_memory_id(summary_id: int) -> str:
    """Return the typed public identity for a Retrograde summary."""
    return f"retrograde_summary:{int(summary_id)}"


def narrative_metadata(
    season: Any, episode: Any, scene_number: Any, **extra: Any
) -> Dict[str, Any]:
    """Return narrative chunk metadata, with any path-specific extras last.

    Args:
        season: ``chunk_metadata.season`` for the chunk.
        episode: ``chunk_metadata.episode`` for the chunk.
        scene_number: ``chunk_metadata.scene`` for the chunk.
        **extra: Path-specific fields such as ``world_time`` or
            ``highlights``, kept in the order given.
    """
    return {
        "season": season,
        "episode": episode,
        "scene_number": scene_number,
        **extra,
    }


def _attach_scores(
    result: RetrievalResult,
    *,
    model_scores: Optional[Dict[str, float]],
    text_score: Optional[float],
    vector_score: Optional[float],
    score: Optional[float],
    source: Optional[str],
) -> Dict[str, Any]:
    """Append supplied score fields in the canonical order."""
    if model_scores is not None:
        result["model_scores"] = model_scores
    if text_score is not None:
        result["text_score"] = text_score
    if vector_score is not None:
        result["vector_score"] = vector_score
    if score is not None:
        result["score"] = score
    if source is not None:
        result["source"] = source
    # A TypedDict is a plain dict at runtime; callers extend it with pipeline
    # keys (raw_text_score, presence_boost, rerank fields) the shape leaves open.
    return cast(Dict[str, Any], result)


def narrative_result(
    chunk_id: Union[int, str],
    text: str,
    metadata: Dict[str, Any],
    *,
    model_scores: Optional[Dict[str, float]] = None,
    text_score: Optional[float] = None,
    vector_score: Optional[float] = None,
    score: Optional[float] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a narrative chunk retrieval result.

    Args:
        chunk_id: ``narrative_chunks.id``; both ``id`` and ``chunk_id`` carry
            its string form.
        text: The chunk's ``raw_text``.
        metadata: Narrative metadata, normally from :func:`narrative_metadata`.
        model_scores: Per-model vector scores, included only when supplied.
        text_score: Normalized text score, included only when supplied.
        vector_score: Fused vector score, included only when supplied.
        score: Final ranking score, included only when supplied.
        source: Search path label, included only when supplied.

    Returns:
        The result dict, keys in :class:`RetrievalResult` order.
    """
    identity = str(chunk_id)
    result: RetrievalResult = {
        "id": identity,
        "chunk_id": identity,
        "text": text,
        "content_type": NARRATIVE_CONTENT_TYPE,
        "metadata": metadata,
    }
    return _attach_scores(
        result,
        model_scores=model_scores,
        text_score=text_score,
        vector_score=vector_score,
        score=score,
        source=source,
    )


def retrograde_summary_result(
    summary_id: int,
    summary_text: str,
    world_event_id: int,
    recorded_at_chunk_id: Optional[int],
    chronology: Any,
    created_at: Any,
    *,
    model_scores: Optional[Dict[str, float]] = None,
    text_score: float = 0.0,
    vector_score: float = 0.0,
    score: Optional[float] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a Retrograde summary retrieval result without a narrative chunk id.

    The six positional arguments match the column order every summary query
    selects, so callers may pass a fetched row directly.

    Args:
        summary_id: ``retrograde_summaries.id``.
        summary_text: The summary's text.
        world_event_id: The canonical world event the summary describes.
        recorded_at_chunk_id: Narrative boundary the summary was recorded at.
        chronology: The summary's chronology bucket.
        created_at: Row creation time; serialized to ISO 8601 when possible.
        model_scores: Per-model vector scores; an empty mapping by default.
        text_score: Normalized text score.
        vector_score: Fused vector score.
        score: Final ranking score, included only when supplied.
        source: Search path label, included only when supplied.

    Returns:
        The result dict, keys in :class:`RetrievalResult` order.
    """
    memory_id = retrograde_summary_memory_id(summary_id)
    serialized_created_at = (
        created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
    )
    result: RetrievalResult = {
        "id": memory_id,
        "memory_id": memory_id,
        "summary_id": int(summary_id),
        "world_event_id": int(world_event_id),
        "text": summary_text,
        "content_type": RETROGRADE_SUMMARY_CONTENT_TYPE,
        "metadata": {
            "summary_id": int(summary_id),
            "world_event_id": int(world_event_id),
            "recorded_at_chunk_id": (
                int(recorded_at_chunk_id) if recorded_at_chunk_id is not None else None
            ),
            "chronology": chronology,
            "created_at": serialized_created_at,
        },
    }
    return _attach_scores(
        result,
        model_scores={} if model_scores is None else model_scores,
        text_score=text_score,
        vector_score=vector_score,
        score=score,
        source=source,
    )
