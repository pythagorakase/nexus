"""Storyteller-time Bleed selector for narrated Orrery resolutions."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Mapping, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger("nexus.orrery.bleed")


class BleedCandidate(BaseModel):
    """One narrated off-screen resolution eligible for Storyteller-time Bleed."""

    resolution_id: int
    narration_id: int
    tick_chunk_id: int
    template_id: str
    event_type: Optional[str] = None
    actor_name: Optional[str] = None
    target_name: Optional[str] = None
    channel: Optional[str] = None
    summary: Optional[str] = None
    brief: Optional[str] = None
    text: str
    magnitude: Optional[float] = None

    def to_prompt_dict(self) -> dict[str, Any]:
        """Return the spoiler-limited shape injected into the Storyteller prompt."""

        return {
            "resolution_id": self.resolution_id,
            "template_id": self.template_id,
            "channel": self.channel,
            "summary": self.summary or self.brief,
            "actor_name": self.actor_name,
            "target_name": self.target_name,
            "magnitude": self.magnitude,
        }


class BleedSelectorResult(BaseModel):
    """Result of a Bleed selector pass."""

    candidates_considered: int = 0
    selected: list[BleedCandidate] = Field(default_factory=list)


def load_bleed_candidates(
    session: Any,
    *,
    anchor_chunk_id: int,
    limit: int,
) -> list[BleedCandidate]:
    """Load narrated Orrery candidates that are eligible before the anchor."""

    if limit <= 0:
        return []

    rows = session.execute(
        text(
            """
            /* orrery:bleed_candidates */
            SELECT
                r.id AS resolution_id,
                n.id AS narration_id,
                r.tick_chunk_id,
                r.template_id,
                r.brief,
                r.magnitude,
                n.text,
                n.perceptual_descriptor,
                actor.name AS actor_name,
                target.name AS target_name,
                we.event_type
            FROM orrery_resolutions r
            JOIN offscreen_narrations n ON n.id = r.narration_chunk_id
            LEFT JOIN entity_names_v actor ON actor.id = r.actor_entity_id
            LEFT JOIN LATERAL (
                SELECT event_type, target_entity_id
                FROM world_events
                WHERE resolution_id = r.id
                ORDER BY id
                LIMIT 1
            ) we ON TRUE
            LEFT JOIN entity_names_v target ON target.id = we.target_entity_id
            WHERE r.promotion_status = 'promoted'
              AND r.narration_status = 'succeeded'
              AND r.tick_chunk_id <= :anchor_chunk_id
              AND (
                    r.last_offered_chunk_id IS NULL
                 OR r.last_offered_chunk_id <> :anchor_chunk_id
              )
              AND r.offer_count < 3
            ORDER BY r.tick_chunk_id DESC,
                     r.magnitude DESC NULLS LAST,
                     r.priority DESC,
                     r.id DESC
            LIMIT :limit
            """
        ),
        {"anchor_chunk_id": anchor_chunk_id, "limit": limit},
    ).mappings()

    return [_candidate_from_row(row) for row in rows]


def select_bleed_menu(
    session: Any,
    *,
    anchor_chunk_id: int,
    max_candidates: int,
) -> BleedSelectorResult:
    """Select a deterministic ambient Bleed menu from eligible candidates."""

    if max_candidates <= 0:
        return BleedSelectorResult()

    candidate_pool = load_bleed_candidates(
        session,
        anchor_chunk_id=anchor_chunk_id,
        limit=max_candidates,
    )
    if not candidate_pool:
        return BleedSelectorResult()

    return BleedSelectorResult(
        candidates_considered=len(candidate_pool),
        selected=candidate_pool[:max_candidates],
    )


def record_bleed_offers(
    session: Any,
    candidates: list[BleedCandidate],
    *,
    anchor_chunk_id: int,
) -> None:
    """Update surfacing bookkeeping for candidates offered to the Storyteller."""

    resolution_ids = [candidate.resolution_id for candidate in candidates]
    if not resolution_ids:
        return

    session.execute(
        text(
            """
            /* orrery:record_bleed_offers */
            UPDATE orrery_resolutions
            SET first_surfaced_chunk_id = COALESCE(
                    first_surfaced_chunk_id,
                    :anchor_chunk_id
                ),
                last_offered_chunk_id = :anchor_chunk_id,
                offer_count = offer_count + 1
            WHERE id = ANY(:resolution_ids)
            """
        ),
        {
            "anchor_chunk_id": anchor_chunk_id,
            "resolution_ids": resolution_ids,
        },
    )
    session.commit()


def _candidate_from_row(row: Mapping[str, Any]) -> BleedCandidate:
    descriptor = _coerce_descriptor(row.get("perceptual_descriptor"))
    return BleedCandidate(
        resolution_id=int(row["resolution_id"]),
        narration_id=int(row["narration_id"]),
        tick_chunk_id=int(row["tick_chunk_id"]),
        template_id=str(row["template_id"]),
        event_type=row.get("event_type"),
        actor_name=row.get("actor_name"),
        target_name=row.get("target_name"),
        channel=descriptor.get("channel"),
        summary=descriptor.get("summary"),
        brief=row.get("brief") or descriptor.get("brief"),
        text=str(row.get("text") or ""),
        magnitude=_float_or_none(row.get("magnitude")),
    )


def _coerce_descriptor(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, Mapping):
        return dict(raw)
    raise TypeError(f"Unsupported perceptual_descriptor type: {type(raw).__name__}")


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)
