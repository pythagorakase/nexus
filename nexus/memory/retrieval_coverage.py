"""Pass 2 retrieval coverage telemetry."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import text

from .context_state import is_retrograde_summary
from .entity_detector import EntityMatch

logger = logging.getLogger(__name__)


_REFERENCE_QUERY = text(
    """
    SELECT 'character' AS kind, character_id AS entity_id, chunk_id
    FROM chunk_character_references
    WHERE chunk_id = ANY(CAST(:kept_chunk_ids AS bigint[]))
    UNION ALL
    SELECT 'place' AS kind, place_id AS entity_id, chunk_id
    FROM place_chunk_references
    WHERE chunk_id = ANY(CAST(:kept_chunk_ids AS bigint[]))
    UNION ALL
    SELECT 'faction' AS kind, faction_id AS entity_id, chunk_id
    FROM chunk_faction_references
    WHERE chunk_id = ANY(CAST(:kept_chunk_ids AS bigint[]))
    """
)

_INSERT_QUERY = text(
    """
    INSERT INTO retrieval_coverage_log (
        turn_id,
        user_input,
        detected_entities,
        raw_result_count,
        kept_chunk_ids,
        kept_tokens,
        available_budget,
        coverage,
        gap_entities
    ) VALUES (
        :turn_id,
        :user_input,
        CAST(:detected_entities AS jsonb),
        :raw_result_count,
        CAST(:kept_chunk_ids AS bigint[]),
        :kept_tokens,
        :available_budget,
        CAST(:coverage AS jsonb),
        CAST(:gap_entities AS jsonb)
    )
    """
)


def _detected_entities(entity_match: EntityMatch) -> List[Dict[str, Any]]:
    detected: List[Dict[str, Any]] = []
    for kind, matches in (
        ("character", entity_match.characters),
        ("place", entity_match.places),
        ("faction", entity_match.factions),
    ):
        detected.extend(
            {
                "kind": kind,
                "id": int(match["id"]),
                "name": str(match["name"]),
            }
            for match in matches
        )
    return sorted(detected, key=lambda entity: (entity["kind"], entity["id"]))


def coerce_chunk_id(chunk: Dict[str, Any]) -> Optional[int]:
    """Return a real narrative chunk id for narrative-only consumers.

    A Retrograde summary may carry ``recorded_at_chunk_id`` as a chronology
    coordinate, but it never owns a narrative chunk identity and must not enter
    entity chunk-reference or retrieval-coverage queries.
    """

    if is_retrograde_summary(chunk):
        return None
    raw_id = chunk.get("chunk_id", chunk.get("id"))
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _chunk_ids(chunks: Iterable[Dict[str, Any]]) -> List[int]:
    chunk_ids: List[int] = []
    seen: set = set()
    for chunk in chunks:
        chunk_id = coerce_chunk_id(chunk)
        if chunk_id is None or chunk_id in seen:
            continue
        seen.add(chunk_id)
        chunk_ids.append(chunk_id)
    return chunk_ids


def _write_retrieval_coverage(
    connection: Any,
    *,
    entity_match: EntityMatch,
    turn_id: Optional[str],
    user_input: str,
    raw_result_count: int,
    kept_chunk_ids: List[int],
    kept_tokens: int,
    available_budget: int,
    error_context: Dict[str, Any],
) -> None:
    detected_entities = _detected_entities(entity_match)
    error_context["detected_entities"] = detected_entities

    references: Dict[tuple[str, int], set[int]] = {}
    if kept_chunk_ids:
        rows = connection.execute(
            _REFERENCE_QUERY,
            {"kept_chunk_ids": kept_chunk_ids},
        )
        for row in rows:
            key = (str(row.kind), int(row.entity_id))
            references.setdefault(key, set()).add(int(row.chunk_id))

    coverage: List[Dict[str, Any]] = []
    gap_entities: List[Dict[str, Any]] = []
    for entity in detected_entities:
        covering_chunk_ids = sorted(
            references.get((entity["kind"], entity["id"]), set())
        )
        coverage.append(
            {
                **entity,
                "covered": bool(covering_chunk_ids),
                "covering_chunk_ids": covering_chunk_ids,
            }
        )
        if not covering_chunk_ids:
            gap_entities.append(dict(entity))

    error_context["coverage"] = coverage
    error_context["gap_entities"] = gap_entities
    connection.execute(
        _INSERT_QUERY,
        {
            "turn_id": turn_id,
            "user_input": user_input,
            "detected_entities": json.dumps(detected_entities),
            "raw_result_count": raw_result_count,
            "kept_chunk_ids": kept_chunk_ids,
            "kept_tokens": kept_tokens,
            "available_budget": available_budget,
            "coverage": json.dumps(coverage),
            "gap_entities": json.dumps(gap_entities),
        },
    )


def audit_retrieval_coverage(
    *,
    incremental_retriever: Any,
    entity_match: EntityMatch,
    user_input: str,
    raw_result_count: int,
    kept_chunks: Iterable[Dict[str, Any]],
    kept_tokens: int,
    available_budget: int,
    turn_id: Optional[str] = None,
) -> None:
    """Write one best-effort retrieval coverage row for a Pass 2 turn.

    A fake or structurally incomplete MEMNON has no SQLAlchemy engine, so unit
    callers skip telemetry without attempting a connection. Once a database
    path exists, every failure is logged with the complete audit context and
    suppressed so telemetry cannot abort narrative generation.
    """

    memnon = getattr(incremental_retriever, "memnon", None)
    database_access = getattr(getattr(memnon, "db_manager", None), "engine", None)
    if database_access is None:
        return

    kept_chunk_ids = _chunk_ids(kept_chunks)
    error_context: Dict[str, Any] = {
        "turn_id": turn_id,
        "user_input": user_input,
        "raw_result_count": raw_result_count,
        "kept_chunk_ids": kept_chunk_ids,
        "kept_tokens": kept_tokens,
        "available_budget": available_budget,
    }

    try:
        if hasattr(database_access, "connect"):
            with database_access.begin() as connection:
                _write_retrieval_coverage(
                    connection,
                    entity_match=entity_match,
                    turn_id=turn_id,
                    user_input=user_input,
                    raw_result_count=raw_result_count,
                    kept_chunk_ids=kept_chunk_ids,
                    kept_tokens=kept_tokens,
                    available_budget=available_budget,
                    error_context=error_context,
                )
        else:
            _write_retrieval_coverage(
                database_access,
                entity_match=entity_match,
                turn_id=turn_id,
                user_input=user_input,
                raw_result_count=raw_result_count,
                kept_chunk_ids=kept_chunk_ids,
                kept_tokens=kept_tokens,
                available_budget=available_budget,
                error_context=error_context,
            )
    except Exception:
        logger.exception(
            "Retrieval coverage audit failed; narrative turn continues (context=%r)",
            error_context,
        )
