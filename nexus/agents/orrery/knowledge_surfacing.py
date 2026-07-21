"""Spoiler-limited Storyteller context for knowledge held in the scene."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import logging
from typing import Any

from sqlalchemy import text

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.config.settings_models import OrreryKnowledgeSettings


logger = logging.getLogger("nexus.orrery.knowledge_surfacing")


class KnowledgeDigest(list[dict[str, Any]]):
    """List-compatible digest carrying private truncation metadata."""

    def __init__(
        self,
        entries: Sequence[dict[str, Any]] = (),
        *,
        truncated: bool = False,
    ) -> None:
        super().__init__(entries)
        self.truncated = truncated


def _coerce_settings(settings: Any) -> OrreryKnowledgeSettings:
    """Normalize a settings mapping or Pydantic model."""

    if isinstance(settings, OrreryKnowledgeSettings):
        return settings
    if hasattr(settings, "model_dump"):
        settings = settings.model_dump()
    if settings is None:
        settings = {}
    if isinstance(settings, Mapping):
        return OrreryKnowledgeSettings.model_validate(dict(settings))
    raise TypeError("Orrery knowledge settings must be a mapping or Pydantic model")


def _query_rows(
    session_or_cur: Any,
    *,
    present_entity_ids: Sequence[int],
    anchor_chunk_id: int,
    recent_reveal_window_chunks: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Load possessed delivered accounts through SQLAlchemy or a DB-API cursor."""

    recent_predicate = playable_narrative_predicate("recent_nc")
    sql = f"""
        /* orrery:world_knowledge */
        WITH recent_chunks AS (
            SELECT recent_nc.id
            FROM narrative_chunks recent_nc
            WHERE recent_nc.id <= {{anchor}}
              AND {recent_predicate}
            ORDER BY recent_nc.id DESC
            LIMIT {{window}}
        ),
        anchor_clock AS (
            SELECT world_time
            FROM chunk_metadata
            WHERE chunk_id = {{anchor}}
        )
        SELECT awareness.id AS awareness_id,
               awareness.knower_entity_id AS character_entity_id,
               present_character.name AS character_name,
               claim.id AS claim_id,
               claim.summary,
               awareness.source_tier,
               awareness.immediate_source_entity_id,
               COALESCE(
                   source_character.name,
                   source_faction.name,
                   source_place.name
               ) AS immediate_source_name,
               awareness.acquired_at_world_time,
               EXISTS (
                   SELECT 1
                   FROM world_events reveal
                   WHERE reveal.event_type = 'backstory_revealed'
                     AND reveal.tick_chunk_id IN (
                         SELECT id FROM recent_chunks
                     )
                     AND (reveal.payload ->> 'claim_id')::bigint = claim.id
                     AND (
                         reveal.actor_entity_id = awareness.knower_entity_id
                         OR EXISTS (
                             SELECT 1
                             FROM jsonb_array_elements_text(
                                 COALESCE(
                                     reveal.payload ->
                                         'revealed_participant_entity_ids',
                                     '[]'::jsonb
                                 )
                             ) participant(entity_id)
                             WHERE participant.entity_id::bigint =
                                   awareness.knower_entity_id
                         )
                     )
               ) AS freshly_revealed
        FROM claim_awareness awareness
        JOIN claims claim ON claim.id = awareness.claim_id
        JOIN characters present_character
          ON present_character.entity_id = awareness.knower_entity_id
        LEFT JOIN characters source_character
          ON source_character.entity_id = awareness.immediate_source_entity_id
        LEFT JOIN factions source_faction
          ON source_faction.entity_id = awareness.immediate_source_entity_id
        LEFT JOIN places source_place
          ON source_place.entity_id = awareness.immediate_source_entity_id
        WHERE awareness.knower_entity_id = ANY({{present_ids}})
          AND (
              awareness.source_chunk_id IS NULL
              OR awareness.source_chunk_id <= {{anchor}}
          )
          AND (
              awareness.acquired_at_world_time IS NULL
              OR awareness.acquired_at_world_time <= (
                  SELECT world_time FROM anchor_clock
              )
          )
          AND NOT EXISTS (
              SELECT 1
              FROM backstory_secrets secret
              WHERE secret.claim_id = claim.id
                AND secret.status = 'latent'
          )
        ORDER BY awareness.acquired_at_world_time DESC NULLS LAST,
                 awareness.claim_id DESC,
                 awareness.knower_entity_id DESC,
                 awareness.id DESC
        LIMIT {{limit}}
    """

    is_sqlalchemy = type(session_or_cur).__module__.startswith("sqlalchemy")
    if is_sqlalchemy:
        statement = text(
            sql.format(
                anchor=":anchor_chunk_id",
                window=":window_chunks",
                present_ids=":present_entity_ids",
                limit=":limit",
            )
        )
        result = session_or_cur.execute(
            statement,
            {
                "anchor_chunk_id": anchor_chunk_id,
                "window_chunks": recent_reveal_window_chunks,
                "present_entity_ids": list(present_entity_ids),
                "limit": limit,
            },
        )
        return [dict(row) for row in result.mappings()]

    statement = sql.format(
        anchor="%s",
        window="%s",
        present_ids="%s",
        limit="%s",
    )
    session_or_cur.execute(
        statement,
        (
            anchor_chunk_id,
            recent_reveal_window_chunks,
            anchor_chunk_id,
            list(present_entity_ids),
            anchor_chunk_id,
            limit,
        ),
    )
    rows = session_or_cur.fetchall()
    if rows and isinstance(rows[0], Mapping):
        return [dict(row) for row in rows]
    description = getattr(session_or_cur, "description", None)
    if description is None:
        raise TypeError(
            "session_or_cur must be a SQLAlchemy session/connection or DB-API cursor"
        )
    column_names = [column[0] for column in description]
    return [dict(zip(column_names, row, strict=True)) for row in rows]


def _acquisition(row: Mapping[str, Any]) -> dict[str, Any]:
    """Translate storage provenance into Storyteller-facing acquisition shape."""

    source_tier = str(row["source_tier"])
    source_id = row["immediate_source_entity_id"]
    if source_tier in {"participant", "witness"}:
        return {"kind": "firsthand"}
    if source_id is not None:
        source_name = row["immediate_source_name"]
        if not source_name:
            raise ValueError(
                "Told knowledge has no display name for immediate source entity "
                f"{source_id}"
            )
        return {
            "kind": "told",
            "source_entity_id": int(source_id),
            "source_name": str(source_name),
        }
    return {"kind": "granted"}


def _entry(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project one safe row without account payload or sibling expansion."""

    acquired = row["acquired_at_world_time"]
    entry: dict[str, Any] = {
        "character_entity_id": int(row["character_entity_id"]),
        "character_name": str(row["character_name"]),
        "claim_id": int(row["claim_id"]),
        "summary": str(row["summary"]),
        "acquisition": _acquisition(row),
        "acquired_at_world_time": (
            acquired.isoformat() if isinstance(acquired, datetime) else None
        ),
    }
    if bool(row["freshly_revealed"]):
        entry["freshly_revealed"] = True
    return entry


def _final_order(entry: Mapping[str, Any]) -> tuple[Any, ...]:
    """Sort by character, acquisition world time, and claim id."""

    acquired = entry["acquired_at_world_time"]
    return (
        int(entry["character_entity_id"]),
        acquired is not None,
        acquired or "",
        int(entry["claim_id"]),
    )


def build_knowledge_digest_sync(
    session_or_cur: Any,
    *,
    present_entity_ids: Sequence[int],
    anchor_chunk_id: int,
    settings: Any,
) -> list[dict[str, Any]]:
    """Build the bounded knowledge digest for characters present at an anchor.

    SPOILER DISCIPLINE -- THIS IS THE GOVERNING CONSTRAINT:
    ONLY the summary of the exact delivered claim named by a present character's
    awareness row may cross this boundary. NEVER select or expose account_payload,
    unpossessed sibling accounts, an unpossessed canonical account, or a latent
    backstory secret. This is the scene's knowledge landscape, not the answer key.
    """

    config = _coerce_settings(settings)
    if not config.enabled:
        return KnowledgeDigest()

    present_ids = tuple(sorted({int(entity_id) for entity_id in present_entity_ids}))
    if not present_ids:
        return KnowledgeDigest()

    rows = _query_rows(
        session_or_cur,
        present_entity_ids=present_ids,
        anchor_chunk_id=int(anchor_chunk_id),
        recent_reveal_window_chunks=config.recent_reveal_window_chunks,
        limit=config.max_entries + 1,
    )
    truncated = len(rows) > config.max_entries
    if truncated:
        logger.debug(
            "World knowledge capped at %d entries; dropping oldest acquisitions",
            config.max_entries,
        )
        rows = rows[: config.max_entries]

    entries = sorted((_entry(row) for row in rows), key=_final_order)
    return KnowledgeDigest(entries, truncated=truncated)
