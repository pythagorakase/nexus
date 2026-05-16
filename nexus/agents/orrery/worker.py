"""Post-commit Orrery promotion and narration worker."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field, ValidationError

from nexus.agents.lore.utils.local_llm import LocalLLMManager
from nexus.config import load_settings_as_dict

logger = logging.getLogger("nexus.orrery.worker")


DEFAULT_NARRATION_MAX_ATTEMPTS = 3
DEFAULT_NARRATION_RETRY_DELAY_SECONDS = 300

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


class OrreryWorkerResult(BaseModel):
    """Summary of one worker drain."""

    promoted: int = 0
    skipped: int = 0
    narrated: int = 0
    failed: int = 0


def process_orrery_outbox_sync(
    slot: Optional[int] = None,
    *,
    promotion_limit: int = 20,
    narration_limit: int = 5,
    settings: Optional[Mapping[str, Any]] = None,
    llm_manager: Optional[Any] = None,
    narration_provider: Optional[Any] = None,
) -> OrreryWorkerResult:
    """Promote pending resolutions, then drain queued narration jobs."""

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
    return OrreryWorkerResult(
        promoted=promoted,
        skipped=skipped,
        narrated=narrated,
        failed=failed,
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
    try:
        if isinstance(raw, PromotionVerdict):
            return raw
        return PromotionVerdict.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Malformed Orrery promotion verdict: {raw}") from exc


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
