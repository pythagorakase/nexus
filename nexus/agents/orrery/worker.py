"""Post-commit Orrery promotion and narration worker."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from typing import Any, Mapping, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field, ValidationError

from nexus.agents.lore.utils.local_llm import (
    LocalLLMManager,
    _parse_structured_json_text,
)
from nexus.config import load_settings_as_dict

logger = logging.getLogger("nexus.orrery.worker")


DEFAULT_NARRATION_MAX_ATTEMPTS = 3
DEFAULT_NARRATION_RETRY_DELAY_SECONDS = 300
DEFAULT_SEMANTIC_CLEARANCE_LIMIT = 20
DEFAULT_SEMANTIC_CLEARANCE_RECENT_CHUNKS = 10
DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_CHUNKS = 5
DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_EVENTS = 6

PROMOTION_SYSTEM_PROMPT = (
    "You are the Orrery promotion discriminator. Decide whether an off-screen "
    "resolution deserves durable prose. Promote only events that create future "
    "retrieval value, dramatic irony, concrete world change, or a perceivable "
    "ambient consequence. Do not promote routine maintenance."
)

NARRATION_SYSTEM_PROMPT = (
    "You write concise off-screen narrative records for NEXUS. The prose is "
    "canonical but not directly shown to the player. Keep it specific, sensory "
    "where useful, and free of second-person address."
)

SEMANTIC_CLEARANCE_SYSTEM_PROMPT = (
    "You are the Orrery semantic tag-clearance judge. Decide whether an "
    "ephemeral off-screen state tag is no longer active based only on the "
    "recent canonical narrative and Orrery events provided. Clear tags only "
    "when the evidence is concrete; uncertainty means keep the tag."
)


class PromotionVerdict(BaseModel):
    """Structured local-LLM promotion verdict for an Orrery resolution."""

    promote: bool
    reason: str = Field(min_length=1)
    perceptual_channel: Optional[str] = Field(
        default=None,
        description="Optional channel such as audio, visual, social, digital, or none.",
    )
    perceptual_summary: Optional[str] = Field(
        default=None,
        description="Short spoiler-safe cue a later Bleed selector could inspect.",
    )


class SemanticClearanceVerdict(BaseModel):
    """Structured local-LLM verdict for semantic ephemeral-tag clearance."""

    clear: bool
    reason: str = Field(min_length=1)


class OrreryWorkerResult(BaseModel):
    """Summary of one worker drain."""

    promoted: int = 0
    skipped: int = 0
    narrated: int = 0
    failed: int = 0
    semantically_cleared: int = 0


class OrreryStatus(BaseModel):
    """Operational snapshot for Orrery outbox and tag-clearance state."""

    pending_promotions: int = 0
    queued_narration_jobs: int = 0
    leased_narration_jobs: int = 0
    failed_narration_jobs: int = 0
    pending_offscreen_embeddings: int = 0
    failed_offscreen_embeddings: int = 0
    active_semantic_tags: int = 0
    recent_resolutions: int = 0
    recent_narrations: int = 0


def process_orrery_outbox_sync(
    slot: Optional[int] = None,
    *,
    promotion_limit: int = 20,
    narration_limit: int = 5,
    semantic_clearance_limit: int = DEFAULT_SEMANTIC_CLEARANCE_LIMIT,
    semantic_clearance_recent_chunks: int = DEFAULT_SEMANTIC_CLEARANCE_RECENT_CHUNKS,
    semantic_clearance_evidence_chunks: int = (
        DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_CHUNKS
    ),
    semantic_clearance_evidence_events: int = (
        DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_EVENTS
    ),
    settings: Optional[Mapping[str, Any]] = None,
    llm_manager: Optional[Any] = None,
    narration_provider: Optional[Any] = None,
) -> OrreryWorkerResult:
    """Promote, narrate, and clear pending Orrery background work."""

    promoted, skipped = promote_pending_resolutions_sync(
        slot,
        limit=promotion_limit,
        settings=settings,
        llm_manager=llm_manager,
    )
    narrated, failed = drain_narration_outbox_sync(
        slot,
        limit=narration_limit,
        settings=settings,
        narration_provider=narration_provider,
    )
    semantically_cleared = clear_semantic_tags_sync(
        slot,
        limit=semantic_clearance_limit,
        recent_chunk_window=semantic_clearance_recent_chunks,
        evidence_chunk_limit=semantic_clearance_evidence_chunks,
        evidence_event_limit=semantic_clearance_evidence_events,
        settings=settings,
        llm_manager=llm_manager,
    )
    return OrreryWorkerResult(
        promoted=promoted,
        skipped=skipped,
        narrated=narrated,
        failed=failed,
        semantically_cleared=semantically_cleared,
    )


def promote_pending_resolutions_sync(
    slot: Optional[int] = None,
    *,
    limit: int = 20,
    settings: Optional[Mapping[str, Any]] = None,
    llm_manager: Optional[Any] = None,
    conn: Optional[Any] = None,
) -> tuple[int, int]:
    """Use the local LLM to mark pending resolutions promoted or skipped."""

    owns_conn = conn is None
    conn = conn or _connect_for_slot(slot)
    settings_dict = dict(settings or load_settings_as_dict())
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        r.id,
                        r.tick_chunk_id,
                        r.template_id,
                        r.actor_entity_id,
                        r.priority,
                        r.magnitude,
                        r.state_delta,
                        r.brief,
                        r.event_ids,
                        n.name AS actor_name
                    FROM orrery_resolutions r
                    LEFT JOIN entity_names_v n ON n.id = r.actor_entity_id
                    WHERE r.promotion_status = 'pending'
                    ORDER BY r.tick_chunk_id, r.priority DESC, r.id
                    LIMIT %s
                    FOR UPDATE OF r SKIP LOCKED
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                if not rows:
                    return (0, 0)

                manager = llm_manager or LocalLLMManager(settings_dict)
                promoted = 0
                skipped = 0
                slot_label = _slot_label(slot)
                for row in rows:
                    verdict = _promotion_verdict(manager, row)
                    if verdict.promote:
                        _mark_promoted(cur, row, verdict, slot_label, settings_dict)
                        promoted += 1
                    else:
                        _mark_skipped(cur, row, verdict)
                        skipped += 1
                return (promoted, skipped)
    finally:
        if owns_conn:
            conn.close()


def drain_narration_outbox_sync(
    slot: Optional[int] = None,
    *,
    limit: int = 5,
    settings: Optional[Mapping[str, Any]] = None,
    narration_provider: Optional[Any] = None,
    conn: Optional[Any] = None,
) -> tuple[int, int]:
    """Generate off-screen narrations for queued Orrery jobs."""

    owns_conn = conn is None
    conn = conn or _connect_for_slot(slot)
    settings_dict = dict(settings or load_settings_as_dict())
    max_attempts, retry_delay_seconds = _narration_retry_settings(settings_dict)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        j.id AS job_id,
                        j.resolution_id,
                        j.slot,
                        j.attempts,
                        r.tick_chunk_id,
                        r.template_id,
                        r.actor_entity_id,
                        r.magnitude,
                        r.state_delta,
                        r.brief,
                        r.promotion_verdict,
                        r.event_ids,
                        cm.world_layer::text AS world_layer,
                        n.name AS actor_name
                    FROM orrery_narration_jobs j
                    JOIN orrery_resolutions r ON r.id = j.resolution_id
                    LEFT JOIN chunk_metadata cm ON cm.chunk_id = r.tick_chunk_id
                    LEFT JOIN entity_names_v n ON n.id = r.actor_entity_id
                    WHERE j.state = 'queued'
                      AND j.available_at <= now()
                    ORDER BY j.available_at, j.id
                    LIMIT %s
                    FOR UPDATE OF j SKIP LOCKED
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                if not rows:
                    return (0, 0)

                provider = narration_provider or _narration_provider(settings_dict)
                for row in rows:
                    cur.execute(
                        """
                        UPDATE orrery_narration_jobs
                        SET state = 'leased',
                            lease_until = now() + interval '5 minutes',
                            attempts = attempts + 1,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (row["job_id"],),
                    )
        narrated = 0
        failed = 0
        for row in rows:
            try:
                narration_text = _generate_narration(provider, row)
                descriptor = _perceptual_descriptor(row)
                with conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        _mark_narration_succeeded(
                            cur,
                            row=row,
                            narration_text=narration_text,
                            descriptor=descriptor,
                        )
                narrated += 1
            except Exception as exc:
                failed += 1
                with conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        _mark_narration_failed(
                            cur,
                            row=row,
                            error=str(exc),
                            max_attempts=max_attempts,
                            retry_delay_seconds=retry_delay_seconds,
                        )
                logger.exception("Failed to narrate Orrery job %s", row["job_id"])
        return (narrated, failed)
    finally:
        if owns_conn:
            conn.close()


def clear_semantic_tags_sync(
    slot: Optional[int] = None,
    *,
    limit: int = DEFAULT_SEMANTIC_CLEARANCE_LIMIT,
    recent_chunk_window: int = DEFAULT_SEMANTIC_CLEARANCE_RECENT_CHUNKS,
    evidence_chunk_limit: int = DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_CHUNKS,
    evidence_event_limit: int = DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_EVENTS,
    settings: Optional[Mapping[str, Any]] = None,
    llm_manager: Optional[Any] = None,
    conn: Optional[Any] = None,
) -> int:
    """Use the local LLM to clear stale semantic ephemeral tags."""

    if (
        limit <= 0
        or recent_chunk_window <= 0
        or evidence_chunk_limit <= 0
        or evidence_event_limit <= 0
    ):
        return 0

    owns_conn = conn is None
    conn = conn or _connect_for_slot(slot)
    settings_dict = dict(settings or load_settings_as_dict())
    try:
        rows = _semantic_clearance_candidates_sync(
            conn,
            limit=limit,
            recent_chunk_window=recent_chunk_window,
        )
        if not rows:
            return 0

        manager = llm_manager or LocalLLMManager(settings_dict)
        cleared = 0
        for row in rows:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    evidence = _semantic_clearance_evidence_sync(
                        cur,
                        entity_id=int(row["entity_id"]),
                        chunk_limit=evidence_chunk_limit,
                        event_limit=evidence_event_limit,
                    )
            verdict = _semantic_clearance_verdict(manager, row, evidence)
            if verdict.clear:
                did_clear = _mark_semantic_tag_cleared_sync(
                    conn,
                    row=row,
                    verdict=verdict,
                    source_chunk_id=_latest_evidence_chunk_id(evidence),
                )
                if did_clear:
                    cleared += 1
        return cleared
    finally:
        if owns_conn:
            conn.close()


def load_orrery_status_sync(
    slot: Optional[int] = None,
    *,
    conn: Optional[Any] = None,
) -> OrreryStatus:
    """Return a compact operational snapshot for Orrery background work."""

    owns_conn = conn is None
    conn = conn or _connect_for_slot(slot)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                return OrreryStatus(
                    pending_promotions=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM orrery_resolutions
                        WHERE promotion_status = 'pending'
                        """,
                    ),
                    queued_narration_jobs=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM orrery_narration_jobs
                        WHERE state = 'queued'
                        """,
                    ),
                    leased_narration_jobs=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM orrery_narration_jobs
                        WHERE state = 'leased'
                        """,
                    ),
                    failed_narration_jobs=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM orrery_narration_jobs
                        WHERE state = 'failed'
                        """,
                    ),
                    pending_offscreen_embeddings=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM offscreen_narrations
                        WHERE embedding_status = 'pending'
                        """,
                    ),
                    failed_offscreen_embeddings=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM offscreen_narrations
                        WHERE embedding_status = 'failed'
                        """,
                    ),
                    active_semantic_tags=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM entity_tags et
                        JOIN tags t ON t.id = et.tag_id
                        WHERE et.cleared_at IS NULL
                          AND t.deprecated = false
                          AND t.is_ephemeral = true
                          AND t.clearance_kind = 'semantic'
                        """,
                    ),
                    recent_resolutions=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM orrery_resolutions
                        WHERE created_at >= now() - interval '24 hours'
                        """,
                    ),
                    recent_narrations=_count_sync(
                        cur,
                        """
                        SELECT count(*) AS count
                        FROM offscreen_narrations
                        WHERE created_at >= now() - interval '24 hours'
                        """,
                    ),
                )
    finally:
        if owns_conn:
            conn.close()


def _mark_narration_succeeded(
    cur: Any,
    *,
    row: Mapping[str, Any],
    narration_text: str,
    descriptor: Mapping[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO offscreen_narrations (
            resolution_id, tick_chunk_id, world_layer,
            text, perceptual_descriptor
        ) VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        (
            row["resolution_id"],
            row["tick_chunk_id"],
            row["world_layer"],
            narration_text,
            json.dumps(descriptor),
        ),
    )
    narration_id = cur.fetchone()["id"]
    cur.execute(
        """
        UPDATE orrery_resolutions
        SET narration_status = 'succeeded',
            narration_chunk_id = %s
        WHERE id = %s
        """,
        (narration_id, row["resolution_id"]),
    )
    cur.execute(
        """
        UPDATE orrery_narration_jobs
        SET state = 'succeeded',
            lease_until = NULL,
            updated_at = now()
        WHERE id = %s
        """,
        (row["job_id"],),
    )


def _mark_narration_failed(
    cur: Any,
    *,
    row: Mapping[str, Any],
    error: str,
    max_attempts: int,
    retry_delay_seconds: int,
) -> None:
    attempt_count = int(row.get("attempts") or 0) + 1
    if attempt_count < max_attempts:
        cur.execute(
            """
            UPDATE orrery_narration_jobs
            SET state = 'queued',
                available_at = now() + (%s * interval '1 second'),
                lease_until = NULL,
                last_error = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (retry_delay_seconds, error, row["job_id"]),
        )
        cur.execute(
            """
            UPDATE orrery_resolutions
            SET narration_status = 'queued'
            WHERE id = %s
            """,
            (row["resolution_id"],),
        )
        return

    cur.execute(
        """
        UPDATE orrery_narration_jobs
        SET state = 'failed',
            lease_until = NULL,
            last_error = %s,
            updated_at = now()
        WHERE id = %s
        """,
        (error, row["job_id"]),
    )
    cur.execute(
        """
        UPDATE orrery_resolutions
        SET narration_status = 'failed'
        WHERE id = %s
        """,
        (row["resolution_id"],),
    )


def _promotion_verdict(manager: Any, row: Mapping[str, Any]) -> PromotionVerdict:
    prompt = (
        "Evaluate this off-screen resolution for durable narration.\n\n"
        f"Template: {row['template_id']}\n"
        f"Actor: {row.get('actor_name') or row.get('actor_entity_id')}\n"
        f"Priority: {row['priority']}\n"
        f"Magnitude: {row.get('magnitude')}\n"
        f"Brief: {row.get('brief')}\n"
        f"State delta: {json.dumps(row.get('state_delta') or {}, sort_keys=True)}\n\n"
        "Return promote=true only if this deserves off-screen prose."
    )
    raw = manager.structured_query(
        prompt,
        PromotionVerdict,
        temperature=0.1,
        max_tokens=512,
        system_prompt=PROMOTION_SYSTEM_PROMPT,
    )
    return _coerce_promotion_verdict(raw)


def _structured_payload_from_raw(raw: Any) -> Any:
    """Recover structured JSON when a local model leaks chat text wrappers."""
    if isinstance(raw, Mapping):
        answer = raw.get("answer")
        if isinstance(answer, str):
            parsed = _parse_structured_json_text(answer)
            if parsed is not None:
                return parsed
    elif isinstance(raw, str):
        parsed = _parse_structured_json_text(raw)
        if parsed is not None:
            return parsed
    return raw


def _markdown_bool_payload_from_raw(
    raw: Any, field_name: str
) -> Optional[dict[str, Any]]:
    """Recover simple markdown/text boolean verdicts from local LLM fallbacks."""
    text: Optional[str] = None
    reason: Optional[str] = None

    if isinstance(raw, Mapping):
        answer = raw.get("answer")
        if isinstance(answer, str):
            text = answer
        for reason_key in ("reason", "reasoning"):
            value = raw.get(reason_key)
            if isinstance(value, str) and value.strip():
                reason = value.strip()
                break
    elif isinstance(raw, str):
        text = raw

    if not text:
        return None

    verdict_match = re.search(
        rf"(?:\*\*)?\b{re.escape(field_name)}\b(?:\*\*)?\s*[:=]\s*(?:\*\*)?\s*(true|false)\b",
        text,
        re.IGNORECASE,
    )
    if not verdict_match:
        return None

    if reason is None:
        reason_match = re.search(
            r"(?:\*\*)?\breason\b(?:\*\*)?\s*[:=]\s*(.+)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if reason_match:
            reason = reason_match.group(1).strip()

    return {
        field_name: verdict_match.group(1).lower() == "true",
        "reason": reason or "Local model returned a text boolean verdict.",
    }


def _coerce_promotion_verdict(raw: Any) -> PromotionVerdict:
    """Return a conservative promotion verdict from noisy local-model output."""
    try:
        if isinstance(raw, PromotionVerdict):
            return raw
        payload = _structured_payload_from_raw(raw)
        payload = _markdown_bool_payload_from_raw(payload, "promote") or payload
        if isinstance(payload, Mapping) and "promote" in payload:
            payload = dict(payload)
            payload.setdefault(
                "reason", "Local model returned a bare promotion decision."
            )
        return PromotionVerdict.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Malformed Orrery promotion verdict; skipping conservatively: %s",
            raw,
            exc_info=True,
        )
        return PromotionVerdict(
            promote=False,
            reason="Malformed local promotion verdict; skipped conservatively.",
        )


def _mark_promoted(
    cur: Any,
    row: Mapping[str, Any],
    verdict: PromotionVerdict,
    slot_label: str,
    settings: Mapping[str, Any],
) -> None:
    narration_settings = (settings.get("orrery") or {}).get("narration") or {}
    provider = narration_settings.get("provider")
    model_ref = narration_settings.get("model_ref")
    cur.execute(
        """
        UPDATE orrery_resolutions
        SET promotion_status = 'promoted',
            promotion_verdict = %s::jsonb,
            narration_status = 'queued'
        WHERE id = %s
        """,
        (verdict.model_dump_json(), row["id"]),
    )
    cur.execute(
        """
        INSERT INTO orrery_narration_jobs (
            resolution_id, slot, provider, model_ref
        ) VALUES (%s, %s, %s, %s)
        """,
        (row["id"], slot_label, provider, model_ref),
    )


def _mark_skipped(cur: Any, row: Mapping[str, Any], verdict: PromotionVerdict) -> None:
    cur.execute(
        """
        UPDATE orrery_resolutions
        SET promotion_status = 'skipped',
            promotion_verdict = %s::jsonb,
            narration_status = 'none'
        WHERE id = %s
        """,
        (verdict.model_dump_json(), row["id"]),
    )


def _semantic_clearance_candidates_sync(
    conn: Any,
    *,
    limit: int,
    recent_chunk_window: int,
) -> list[Mapping[str, Any]]:
    """Load semantic tag candidates without holding row locks across inference."""

    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                WITH recent_ticks AS (
                    SELECT id
                    FROM narrative_chunks
                    ORDER BY id DESC
                    LIMIT %s
                )
                SELECT
                    et.id AS entity_tag_id,
                    et.entity_id,
                    et.applied_at,
                    et.applied_at_world_time,
                    et.template_id,
                    t.tag,
                    t.category,
                    t.description,
                    n.name AS entity_name
                FROM entity_tags et
                JOIN tags t ON t.id = et.tag_id
                LEFT JOIN entity_names_v n ON n.id = et.entity_id
                WHERE et.cleared_at IS NULL
                  AND t.deprecated = false
                  AND t.is_ephemeral = true
                  AND t.clearance_kind = 'semantic'
                  AND (
                      EXISTS (
                          SELECT 1
                          FROM chunk_entity_references_v cer
                          JOIN recent_ticks rt ON rt.id = cer.chunk_id
                          WHERE cer.entity_id = et.entity_id
                      )
                      OR EXISTS (
                          SELECT 1
                          FROM world_events we
                          JOIN recent_ticks rt ON rt.id = we.tick_chunk_id
                          WHERE we.actor_entity_id = et.entity_id
                             OR we.target_entity_id = et.entity_id
                             OR EXISTS (
                                  SELECT 1
                                  FROM world_event_entities wee
                                  WHERE wee.event_id = we.id
                                    AND wee.entity_id = et.entity_id
                             )
                      )
                  )
                ORDER BY et.applied_at, et.id
                LIMIT %s
                """,
                (recent_chunk_window, limit),
            )
            return list(cur.fetchall())


def _semantic_clearance_evidence_sync(
    cur: Any,
    *,
    entity_id: int,
    chunk_limit: int = DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_CHUNKS,
    event_limit: int = DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_EVENTS,
) -> dict[str, Any]:
    """Load bounded canonical evidence, not only the candidate trigger window."""

    cur.execute(
        """
        SELECT nc.id, left(nc.raw_text, 1200) AS text
        FROM chunk_entity_references_v cer
        JOIN narrative_chunks nc ON nc.id = cer.chunk_id
        WHERE cer.entity_id = %s
        ORDER BY nc.id DESC
        LIMIT %s
        """,
        (entity_id, chunk_limit),
    )
    chunks = [
        {"chunk_id": row["id"], "text": row.get("text")} for row in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT
            we.id,
            we.tick_chunk_id,
            we.event_type,
            we.changed_fields,
            we.magnitude,
            we.payload
        FROM world_events we
        WHERE we.actor_entity_id = %s
           OR we.target_entity_id = %s
           OR EXISTS (
                SELECT 1
                FROM world_event_entities wee
                WHERE wee.event_id = we.id
                  AND wee.entity_id = %s
           )
        ORDER BY we.tick_chunk_id DESC, we.id DESC
        LIMIT %s
        """,
        (entity_id, entity_id, entity_id, event_limit),
    )
    events = [
        {
            "event_id": row["id"],
            "tick_chunk_id": row["tick_chunk_id"],
            "event_type": row["event_type"],
            "changed_fields": list(row.get("changed_fields") or ()),
            "magnitude": _json_scalar(row.get("magnitude")),
            "payload": row.get("payload") or {},
        }
        for row in cur.fetchall()
    ]
    return {"recent_chunks": chunks, "recent_events": events}


def _semantic_clearance_verdict(
    manager: Any, row: Mapping[str, Any], evidence: Mapping[str, Any]
) -> SemanticClearanceVerdict:
    prompt = (
        "Evaluate whether this semantic ephemeral Orrery tag should be cleared.\n\n"
        f"Entity: {row.get('entity_name') or row['entity_id']}\n"
        f"Tag: {row['tag']}\n"
        f"Category: {row.get('category')}\n"
        f"Description: {row.get('description')}\n"
        f"Applied at: {row.get('applied_at')}\n"
        f"Applied world time: {row.get('applied_at_world_time')}\n"
        f"Template source: {row.get('template_id')}\n\n"
        "Evidence:\n"
        f"{json.dumps(evidence, sort_keys=True, default=str)}\n\n"
        "Return clear=true only if the tag is now stale, resolved, or no "
        "longer active. Return clear=false when evidence is missing, weak, "
        "ambiguous, or the state still plausibly applies."
    )
    raw = manager.structured_query(
        prompt,
        SemanticClearanceVerdict,
        temperature=0.1,
        max_tokens=512,
        system_prompt=SEMANTIC_CLEARANCE_SYSTEM_PROMPT,
    )
    return _coerce_semantic_clearance_verdict(raw)


def _coerce_semantic_clearance_verdict(raw: Any) -> SemanticClearanceVerdict:
    """Keep semantic tags when local clearance output is malformed."""
    try:
        if isinstance(raw, SemanticClearanceVerdict):
            return raw
        payload = _structured_payload_from_raw(raw)
        payload = _markdown_bool_payload_from_raw(payload, "clear") or payload
        if isinstance(payload, Mapping) and "clear" in payload:
            payload = dict(payload)
            payload.setdefault(
                "reason", "Local model returned a bare semantic-clearance decision."
            )
        return SemanticClearanceVerdict.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Malformed Orrery semantic clearance verdict; keeping tag: %s",
            raw,
            exc_info=True,
        )
        return SemanticClearanceVerdict(
            clear=False,
            reason="Malformed local semantic-clearance verdict; kept conservatively.",
        )


def _mark_semantic_tag_cleared_sync(
    conn: Any,
    *,
    row: Mapping[str, Any],
    verdict: SemanticClearanceVerdict,
    source_chunk_id: Optional[int],
) -> bool:
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE entity_tags et
                SET cleared_at = now()
                FROM tags t
                WHERE et.id = %s
                  AND t.id = et.tag_id
                  AND et.cleared_at IS NULL
                  AND t.deprecated = false
                  AND t.is_ephemeral = true
                  AND t.clearance_kind = 'semantic'
                RETURNING et.id
                """,
                (row["entity_tag_id"],),
            )
            updated = cur.fetchone()
            if not updated:
                return False
            cur.execute(
                """
                INSERT INTO tag_clearance_log (
                    entity_tag_id, mechanism, justification, source_chunk_id
                ) VALUES (%s, 'semantic', %s::jsonb, %s)
                """,
                (
                    row["entity_tag_id"],
                    json.dumps(
                        {
                            "tag": row["tag"],
                            "reason": verdict.reason,
                        }
                    ),
                    source_chunk_id,
                ),
            )
            return True


def _latest_evidence_chunk_id(evidence: Mapping[str, Any]) -> Optional[int]:
    chunk_ids: list[int] = []
    for chunk in evidence.get("recent_chunks") or ():
        chunk_id = chunk.get("chunk_id")
        if chunk_id is not None:
            chunk_ids.append(int(chunk_id))
    for event in evidence.get("recent_events") or ():
        chunk_id = event.get("tick_chunk_id")
        if chunk_id is not None:
            chunk_ids.append(int(chunk_id))
    return max(chunk_ids) if chunk_ids else None


def _count_sync(cur: Any, sql: str) -> int:
    cur.execute(sql)
    row = cur.fetchone()
    return int((row or {}).get("count") or 0)


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "as_tuple"):
        return float(value)
    return value


def _generate_narration(provider: Any, row: Mapping[str, Any]) -> str:
    prompt = (
        "Write one concise off-screen narration record.\n\n"
        f"Template: {row['template_id']}\n"
        f"Actor: {row.get('actor_name') or row.get('actor_entity_id')}\n"
        f"Brief: {row.get('brief')}\n"
        f"Promotion verdict: {json.dumps(row.get('promotion_verdict') or {}, sort_keys=True)}\n"
        f"State delta: {json.dumps(row.get('state_delta') or {}, sort_keys=True)}\n\n"
        "Length: 80-180 words. Do not address the player."
    )
    response = provider.get_completion(prompt)
    text = response.content.strip()
    if not text:
        raise ValueError("Orrery narration provider returned empty text")
    return text


def _perceptual_descriptor(row: Mapping[str, Any]) -> dict[str, Any]:
    verdict = row.get("promotion_verdict") or {}
    if isinstance(verdict, str):
        verdict = json.loads(verdict)
    return {
        "channel": verdict.get("perceptual_channel"),
        "summary": verdict.get("perceptual_summary"),
        "brief": row.get("brief"),
    }


def _narration_provider(settings: Mapping[str, Any]) -> Any:
    from nexus.config.loader import get_provider_for_model
    from scripts.api_anthropic import AnthropicProvider
    from scripts.api_openai import OpenAIProvider

    narration_settings = (settings.get("orrery") or {}).get("narration") or {}
    provider_name = narration_settings.get("provider")
    model = narration_settings.get("model_ref")
    provider_name = provider_name or get_provider_for_model(model)

    if provider_name in {"openai", "test"}:
        return OpenAIProvider(
            model=model,
            temperature=0.4,
            max_output_tokens=1200,
            system_prompt=NARRATION_SYSTEM_PROMPT,
        )
    if provider_name == "anthropic":
        return AnthropicProvider(
            model=model,
            temperature=0.4,
            max_tokens=1200,
            system_prompt=NARRATION_SYSTEM_PROMPT,
        )
    raise ValueError(f"Unsupported Orrery narration provider: {provider_name}")


def _narration_retry_settings(settings: Mapping[str, Any]) -> tuple[int, int]:
    narration_settings = (settings.get("orrery") or {}).get("narration") or {}
    max_attempts = int(
        narration_settings.get("max_attempts", DEFAULT_NARRATION_MAX_ATTEMPTS)
    )
    retry_delay_seconds = int(
        narration_settings.get(
            "retry_delay_seconds", DEFAULT_NARRATION_RETRY_DELAY_SECONDS
        )
    )
    return max(1, max_attempts), max(0, retry_delay_seconds)


def _connect_for_slot(slot: Optional[int]) -> Any:
    from nexus.api.slot_utils import require_slot_dbname

    dbname = require_slot_dbname(slot=slot)
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _slot_label(slot: Optional[int]) -> str:
    if slot is not None:
        return str(slot)
    value = os.environ.get("NEXUS_SLOT")
    if value:
        return value
    return "default"


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for Orrery worker catch-up and status checks."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, default=None, help="Save slot to inspect.")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print an Orrery background-work status snapshot instead of draining.",
    )
    parser.add_argument(
        "--promotion-limit",
        type=int,
        default=20,
        help="Maximum pending resolutions to promote in this run.",
    )
    parser.add_argument(
        "--narration-limit",
        type=int,
        default=5,
        help="Maximum queued narration jobs to drain in this run.",
    )
    parser.add_argument(
        "--semantic-clearance-limit",
        type=int,
        default=DEFAULT_SEMANTIC_CLEARANCE_LIMIT,
        help="Maximum semantic ephemeral tags to evaluate in this run.",
    )
    parser.add_argument(
        "--semantic-clearance-recent-chunks",
        type=int,
        default=DEFAULT_SEMANTIC_CLEARANCE_RECENT_CHUNKS,
        help="Recent chunk window used to find relevant semantic tag evidence.",
    )
    parser.add_argument(
        "--semantic-clearance-evidence-chunks",
        type=int,
        default=DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_CHUNKS,
        help="Maximum recent narrative chunks included per semantic tag verdict.",
    )
    parser.add_argument(
        "--semantic-clearance-evidence-events",
        type=int,
        default=DEFAULT_SEMANTIC_CLEARANCE_EVIDENCE_EVENTS,
        help="Maximum recent Orrery events included per semantic tag verdict.",
    )
    args = parser.parse_args(argv)

    if args.status:
        payload = load_orrery_status_sync(args.slot).model_dump()
    else:
        payload = process_orrery_outbox_sync(
            args.slot,
            promotion_limit=args.promotion_limit,
            narration_limit=args.narration_limit,
            semantic_clearance_limit=args.semantic_clearance_limit,
            semantic_clearance_recent_chunks=args.semantic_clearance_recent_chunks,
            semantic_clearance_evidence_chunks=args.semantic_clearance_evidence_chunks,
            semantic_clearance_evidence_events=args.semantic_clearance_evidence_events,
        ).model_dump()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
