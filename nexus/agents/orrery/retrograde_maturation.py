"""Runtime Retrograde stub maturation (spec decisions 9/10/12, Phase B-Lite).

Two halves, one durable queue:

1. **Commit side** — ``enqueue_declared_entity_maturations`` runs inside the
   chunk-commit transaction. It validates Skald's ``new_entities``
   declarations against the live tag/pair-tag registries (unregistered
   vocabulary is a hard error), creates stub rows for declared entities that
   do not exist yet, and enqueues one ``orrery_maturation_jobs`` row per
   declared entity whose name appears in the committed chunk (the
   conservative v1 engagement signal: declaration + commit IS the signal).

2. **Worker side** — ``drain_maturation_jobs_sync`` leases queued jobs and
   runs the scoped single-entity Retrograde pipeline per job: runtime packet
   -> R4/R5 seed generation (frontier) -> R6 expansion (frontier) ->
   persistence execute -> summary-chunk embedding. Event refs are namespaced
   per job so the per-slot ``payload.retrograde_event_ref`` idempotency keys
   never collide across jobs. The unique index on
   ``orrery_maturation_jobs.entity_id`` plus an already-connected guard make
   maturation idempotent per entity: a matured entity never re-matures.

Failures are loud and retryable: a failed job records ``last_error`` and
requeues with a delay until the attempt cap, then stays ``failed`` and
visible. A job whose manifest already records persisted rows resumes at the
embedding step instead of re-running generation.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

from nexus.agents.logon.apex_schema import NewEntityDeclaration
from nexus.agents.orrery.retrograde_vocabulary import SeedEligibleVocabulary
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import apply_tag_bestowal
from nexus.config import load_settings_as_dict
from nexus.config.settings_models import (
    OrreryRetrogradeMaturationSettings,
    OrreryRetrogradeRetrievalSettings,
)

logger = logging.getLogger("nexus.orrery.retrograde_maturation")

MATURATION_PACKET_SCHEMA_VERSION = "orrery_retrograde_maturation_packet.v0"
MATURATION_MANIFEST_SCHEMA_VERSION = "orrery_retrograde_maturation_manifest.v0"
MATURATION_EVENT_REF_PREFIX = "maturation_job"

_SUBTYPE_TABLES: Mapping[str, str] = {
    "character": "characters",
    "place": "places",
    "faction": "factions",
}


class RetrogradeMaturationVocabularyError(ValueError):
    """Raised when a declaration hint uses unregistered vocabulary."""


class MaturationEnqueueResult(BaseModel):
    """Summary of one commit-time declaration-processing pass."""

    declared: int = 0
    stubs_created: int = 0
    jobs_enqueued: int = 0
    jobs_already_present: int = 0
    signal_absent: int = 0
    skipped_disabled: int = 0


@dataclass
class _DeclaredEntityRecord:
    """Resolved subtype/global ids for one declared entity."""

    entity_kind: str
    subtype_id: int
    entity_id: int
    name: str
    created: bool


# ============================================================================
# Commit Side — Declaration Processing and Durable Enqueue
# ============================================================================


def enqueue_declared_entity_maturations(
    conn: Any,
    *,
    declarations: Sequence[Mapping[str, Any]],
    chunk_id: int,
    raw_text: str,
    slot: Optional[int] = None,
    settings: Optional[Mapping[str, Any]] = None,
) -> MaturationEnqueueResult:
    """Process Skald new-entity declarations inside the commit transaction.

    Must be called with the chunk-commit connection while its transaction is
    open so stub rows and job rows commit atomically with the chunk (the
    outbox pattern). Raises on unregistered tag/pair-tag hints and on
    ambiguous entity names; the commit fails loudly rather than persisting a
    declaration the registries reject.
    """

    result = MaturationEnqueueResult()
    if not declarations:
        return result

    parsed = [
        NewEntityDeclaration.model_validate(declaration) for declaration in declarations
    ]
    result.declared = len(parsed)

    settings_dict = dict(settings or load_settings_as_dict())
    cfg = _maturation_settings(settings_dict)
    if not cfg.enabled:
        result.skipped_disabled = len(parsed)
        logger.info(
            "Retrograde maturation disabled; ignoring %s declarations for " "chunk %s",
            len(parsed),
            chunk_id,
        )
        return result

    slot_label = _slot_label(slot)
    lowered_text = (raw_text or "").lower()

    with conn.cursor() as cur:
        for declaration in parsed:
            _validate_pair_tag_hints(cur, declaration)
            record = _resolve_or_create_stub(cur, declaration)
            if record.created:
                result.stubs_created += 1

            if declaration.name.lower() not in lowered_text:
                result.signal_absent += 1
                logger.info(
                    "Declared entity %r (%s) absent from committed chunk %s "
                    "text; stub %s, no maturation job (decision 12 v1 signal)",
                    declaration.name,
                    declaration.kind,
                    chunk_id,
                    "created" if record.created else "exists",
                )
                continue

            inserted = _enqueue_job(
                cur,
                record=record,
                declaration=declaration,
                chunk_id=chunk_id,
                slot_label=slot_label,
            )
            if inserted:
                result.jobs_enqueued += 1
            else:
                result.jobs_already_present += 1

    return result


def _validate_pair_tag_hints(cur: Any, declaration: NewEntityDeclaration) -> None:
    """Reject unregistered or kind-incompatible pair-tag hints loudly."""

    for hint in declaration.pair_tag_hints:
        cur.execute(
            """
            /* orrery:maturation:pair_tag_hint_lookup */
            SELECT subject_kinds, object_kinds, deprecated
            FROM pair_tags
            WHERE tag = %s
            """,
            (hint.tag,),
        )
        row = cur.fetchone()
        if row is None:
            raise RetrogradeMaturationVocabularyError(
                f"Declaration {declaration.name!r} uses unregistered pair-tag "
                f"hint {hint.tag!r}"
            )
        if _row_value(row, "deprecated", 2):
            raise RetrogradeMaturationVocabularyError(
                f"Declaration {declaration.name!r} uses deprecated pair-tag "
                f"hint {hint.tag!r}"
            )
        if hint.declared_entity_role == "subject":
            allowed = _row_value(row, "subject_kinds", 0)
        else:
            allowed = _row_value(row, "object_kinds", 1)
        if declaration.kind not in set(allowed or ()):
            raise RetrogradeMaturationVocabularyError(
                f"Pair-tag hint {hint.tag!r} does not allow "
                f"{declaration.kind!r} as {hint.declared_entity_role}"
            )


def _resolve_or_create_stub(
    cur: Any, declaration: NewEntityDeclaration
) -> _DeclaredEntityRecord:
    """Resolve a declared entity by exact name, creating a stub when absent.

    Single-entity tag hints are applied through ``apply_tag_bestowal`` which
    validates them against the live registry (unregistered, deprecated, or
    kind-incompatible names raise ``ValueError``).
    """

    table = _SUBTYPE_TABLES[declaration.kind]
    cur.execute(
        f"SELECT id, entity_id FROM {table} WHERE name = %s ORDER BY id",
        (declaration.name,),
    )
    rows = cur.fetchall()
    if len(rows) > 1:
        raise ValueError(
            f"Declared {declaration.kind} name {declaration.name!r} is "
            f"ambiguous: {len(rows)} existing rows match"
        )

    if rows:
        row = rows[0]
        record = _DeclaredEntityRecord(
            entity_kind=declaration.kind,
            subtype_id=int(_row_value(row, "id", 0)),
            entity_id=int(_row_value(row, "entity_id", 1)),
            name=declaration.name,
            created=False,
        )
    else:
        record = _insert_declared_stub(cur, declaration)
        logger.info(
            "Created %s stub %r (id=%s) from Skald declaration",
            declaration.kind,
            declaration.name,
            record.subtype_id,
        )

    if declaration.tag_hints:
        bestowal = OrreryTagBestowal(applied_tags=list(declaration.tag_hints))
        apply_tag_bestowal(
            cur,
            entity_id=record.entity_id,
            entity_kind=declaration.kind,
            bestowal=bestowal,
            source_kind="skald_inline",
        )

    return record


def _insert_declared_stub(
    cur: Any, declaration: NewEntityDeclaration
) -> _DeclaredEntityRecord:
    if declaration.kind == "character":
        _sync_id_sequence(cur, "characters")
        cur.execute(
            """
            INSERT INTO characters (name, summary)
            VALUES (%s, %s)
            RETURNING id, entity_id
            """,
            (declaration.name, declaration.summary),
        )
    elif declaration.kind == "place":
        _sync_id_sequence(cur, "places")
        cur.execute(
            """
            INSERT INTO places (name, type, summary)
            VALUES (%s, 'fixed_location', %s)
            RETURNING id, entity_id
            """,
            (declaration.name, declaration.summary),
        )
    else:
        cur.execute("LOCK TABLE factions IN SHARE ROW EXCLUSIVE MODE")
        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM factions")
        next_id = _row_value(cur.fetchone(), "next_id", 0)
        cur.execute(
            """
            INSERT INTO factions (id, name, summary)
            VALUES (%s, %s, %s)
            RETURNING id, entity_id
            """,
            (next_id, declaration.name, declaration.summary),
        )

    row = cur.fetchone()
    return _DeclaredEntityRecord(
        entity_kind=declaration.kind,
        subtype_id=int(_row_value(row, "id", 0)),
        entity_id=int(_row_value(row, "entity_id", 1)),
        name=declaration.name,
        created=True,
    )


def _sync_id_sequence(cur: Any, table: str) -> None:
    """Advance a table's id sequence to MAX(id) before a serial insert.

    Slot databases populated by data imports can carry id sequences far
    behind MAX(id); a serial insert then collides with existing rows. The
    sync is cheap and idempotent, and sequences never roll back, so doing it
    inside the commit transaction is safe.
    """

    if table not in _SUBTYPE_TABLES.values():
        raise ValueError(f"Unexpected table for id-sequence sync: {table!r}")
    cur.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{table}', 'id'),
            GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table}), 1)
        )
        """
    )


def _enqueue_job(
    cur: Any,
    *,
    record: _DeclaredEntityRecord,
    declaration: NewEntityDeclaration,
    chunk_id: int,
    slot_label: str,
) -> bool:
    """Insert one durable maturation job; returns False when already present."""

    cur.execute(
        """
        /* orrery:maturation:enqueue */
        INSERT INTO orrery_maturation_jobs (
            entity_id, entity_kind, entity_subtype_id, entity_name,
            slot, requesting_chunk_id, declaration
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (entity_id) DO NOTHING
        RETURNING id
        """,
        (
            record.entity_id,
            record.entity_kind,
            record.subtype_id,
            record.name,
            slot_label,
            chunk_id,
            declaration.model_dump_json(),
        ),
    )
    row = cur.fetchone()
    if row is None:
        logger.info(
            "Maturation job for %s %r (entity_id=%s) already exists; "
            "idempotent enqueue skipped",
            record.entity_kind,
            record.name,
            record.entity_id,
        )
        return False
    logger.info(
        "Enqueued maturation job %s for %s %r (entity_id=%s, chunk %s)",
        _row_value(row, "id", 0),
        record.entity_kind,
        record.name,
        record.entity_id,
        chunk_id,
    )
    return True


# ============================================================================
# Worker Side — Drain and Scoped Pipeline
# ============================================================================


def drain_maturation_jobs_sync(
    slot: Optional[int] = None,
    *,
    limit: Optional[int] = None,
    settings: Optional[Mapping[str, Any]] = None,
    conn: Optional[Any] = None,
) -> tuple[int, int]:
    """Lease and run queued maturation jobs; returns (matured, failed)."""

    settings_dict = dict(settings or load_settings_as_dict())
    cfg = _maturation_settings(settings_dict)
    if not cfg.enabled:
        return (0, 0)

    owns_conn = conn is None
    conn = conn or _connect_for_slot(slot)
    job_limit = limit if limit is not None else cfg.max_jobs_per_drain
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    /* orrery:maturation:lease */
                    SELECT
                        j.id AS job_id,
                        j.entity_id,
                        j.entity_kind,
                        j.entity_subtype_id,
                        j.entity_name,
                        j.slot,
                        j.requesting_chunk_id,
                        j.declaration,
                        j.attempts,
                        j.result_manifest
                    FROM orrery_maturation_jobs j
                    WHERE (j.state = 'queued' AND j.available_at <= now())
                       OR (
                            j.state = 'leased'
                            AND j.lease_until IS NOT NULL
                            AND j.lease_until < now()
                          )
                    ORDER BY j.available_at, j.id
                    LIMIT %s
                    FOR UPDATE OF j SKIP LOCKED
                    """,
                    (job_limit,),
                )
                rows = cur.fetchall()
                if not rows:
                    return (0, 0)
                for row in rows:
                    cur.execute(
                        """
                        UPDATE orrery_maturation_jobs
                        SET state = 'leased',
                            lease_until = now() + interval '15 minutes',
                            attempts = attempts + 1,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (row["job_id"],),
                    )

        matured = 0
        failed = 0
        for row in rows:
            try:
                _mature_one(
                    conn,
                    row=row,
                    cfg=cfg,
                    settings_dict=settings_dict,
                    slot=slot,
                )
                matured += 1
            except Exception as exc:
                failed += 1
                with conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        _mark_maturation_failed(
                            cur,
                            row=row,
                            error=str(exc),
                            max_attempts=cfg.max_attempts,
                            retry_delay_seconds=cfg.retry_delay_seconds,
                        )
                logger.exception(
                    "Maturation job %s for %s %r failed",
                    row["job_id"],
                    row["entity_kind"],
                    row["entity_name"],
                )
        return (matured, failed)
    finally:
        if owns_conn:
            conn.close()


def _mature_one(
    conn: Any,
    *,
    row: Mapping[str, Any],
    cfg: OrreryRetrogradeMaturationSettings,
    settings_dict: Mapping[str, Any],
    slot: Optional[int],
) -> dict[str, Any]:
    """Run the scoped Retrograde pipeline for one leased job."""

    from nexus.api.slot_utils import require_slot_dbname

    started = time.monotonic()
    dbname = require_slot_dbname(slot=slot)
    retrieval = _retrieval_settings(settings_dict)

    prior_manifest = row.get("result_manifest") or {}
    if prior_manifest.get("persisted"):
        return _resume_embedding(
            conn,
            row=row,
            manifest=dict(prior_manifest),
            dbname=dbname,
            retrieval=retrieval,
        )

    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            connected_events = _entity_event_count(cur, int(row["entity_id"]))
            if connected_events:
                manifest = _base_manifest(row, cfg)
                manifest.update(
                    {
                        "persisted": False,
                        "skipped": "already_connected",
                        "existing_world_event_count": connected_events,
                    }
                )
                _mark_maturation_succeeded(cur, job_id=row["job_id"], manifest=manifest)
                logger.info(
                    "Maturation job %s skipped: entity %r already participates "
                    "in %s world events",
                    row["job_id"],
                    row["entity_name"],
                    connected_events,
                )
                return manifest
            context = _load_job_context(cur, row=row, cfg=cfg)

    from nexus.agents.orrery.retrograde_vocabulary import (
        enumerate_seed_eligible_vocabulary,
    )

    vocabulary = enumerate_seed_eligible_vocabulary(dbname)
    packet = build_runtime_maturation_packet(
        vocabulary=vocabulary,
        row=row,
        context=context,
        cfg=cfg,
        dbname=dbname,
    )

    from nexus.agents.orrery.retrograde_seed_candidates import (
        generate_seed_candidates_with_skald,
    )

    seed_started = time.monotonic()
    seed_result = generate_seed_candidates_with_skald(
        packet=packet,
        model_name=cfg.model_ref,
        max_tokens=cfg.max_tokens,
    )
    seed_elapsed = time.monotonic() - seed_started
    seed_response = seed_result["seed_candidate_response"]

    if not seed_response.get("selected_seed_ids"):
        manifest = _base_manifest(row, cfg)
        manifest.update(
            {
                "persisted": False,
                "skipped": "no_seeds_selected",
                "seed_model": seed_result["model"],
                "timings_seconds": {
                    "seed": round(seed_elapsed, 2),
                    "total": round(time.monotonic() - started, 2),
                },
            }
        )
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _mark_maturation_succeeded(cur, job_id=row["job_id"], manifest=manifest)
        logger.warning(
            "Maturation job %s: Skald selected no seeds for %r; entity stays "
            "a bare stub",
            row["job_id"],
            row["entity_name"],
        )
        return manifest

    from nexus.agents.orrery.retrograde_expansion import generate_expansion_with_skald

    expansion_started = time.monotonic()
    expansion_result = generate_expansion_with_skald(
        packet=packet,
        seed_candidate_response=seed_response,
        model_name=cfg.model_ref,
        max_tokens=cfg.max_tokens,
    )
    expansion_elapsed = time.monotonic() - expansion_started

    expansion_payload = namespace_expansion_event_refs(
        expansion_result["retrograde_expansion_plan"],
        prefix=f"{MATURATION_EVENT_REF_PREFIX}_{row['job_id']}",
    )

    from nexus.agents.orrery.retrograde_persistence import (
        build_retrograde_persistence_plan,
    )

    persistence_started = time.monotonic()
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            persistence = build_retrograde_persistence_plan(
                cur,
                packet=packet,
                seed_candidate_response=seed_response,
                expansion_plan_payload=expansion_payload,
                slot=_slot_int(slot, row.get("slot")),
                dbname=dbname,
                dry_run=False,
                create_missing_entities=True,
                summary_chunks_enabled=retrieval.summary_chunks,
            )
            persistence_elapsed = time.monotonic() - persistence_started
            total_elapsed = time.monotonic() - started
            manifest = _base_manifest(row, cfg)
            manifest.update(
                {
                    "persisted": True,
                    "seed_model": seed_result["model"],
                    "expansion_model": expansion_result["model"],
                    "counters": persistence["counters"],
                    "world_event_ids": persistence["commit_readiness"][
                        "event_ref_to_id"
                    ],
                    "embedding_pending_chunk_ids": list(
                        persistence["retrieval"]["embedding_pending_chunk_ids"]
                    ),
                    "embedding": {"status": "pending"},
                    "timings_seconds": {
                        "seed": round(seed_elapsed, 2),
                        "expansion": round(expansion_elapsed, 2),
                        "persistence": round(persistence_elapsed, 2),
                        "total": round(total_elapsed, 2),
                    },
                    "budget_exceeded": total_elapsed > cfg.budget_seconds,
                }
            )
            # Record the persisted manifest while the job stays leased so a
            # crash before embedding resumes at the embedding step instead of
            # regenerating (and duplicating) history.
            cur.execute(
                """
                UPDATE orrery_maturation_jobs
                SET result_manifest = %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                """,
                (json.dumps(manifest), row["job_id"]),
            )

    if manifest["budget_exceeded"]:
        logger.warning(
            "Maturation job %s exceeded budget: %.1fs > %.1fs",
            row["job_id"],
            manifest["timings_seconds"]["total"],
            cfg.budget_seconds,
        )

    return _finish_embedding(
        conn,
        row=row,
        manifest=manifest,
        dbname=dbname,
        retrieval=retrieval,
    )


def _resume_embedding(
    conn: Any,
    *,
    row: Mapping[str, Any],
    manifest: dict[str, Any],
    dbname: str,
    retrieval: OrreryRetrogradeRetrievalSettings,
) -> dict[str, Any]:
    """Retry path for jobs that persisted history but failed at embedding."""

    logger.info(
        "Maturation job %s already persisted history; resuming at embedding",
        row["job_id"],
    )
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            pending = _pending_embedding_ids(
                cur, manifest.get("embedding_pending_chunk_ids") or []
            )
    manifest["embedding_pending_chunk_ids"] = pending
    return _finish_embedding(
        conn,
        row=row,
        manifest=manifest,
        dbname=dbname,
        retrieval=retrieval,
    )


def _finish_embedding(
    conn: Any,
    *,
    row: Mapping[str, Any],
    manifest: dict[str, Any],
    dbname: str,
    retrieval: OrreryRetrogradeRetrievalSettings,
) -> dict[str, Any]:
    """Embed pending summary chunks, then mark the job succeeded."""

    pending = list(manifest.get("embedding_pending_chunk_ids") or [])
    if pending and retrieval.embed_after_apply:
        from nexus.agents.orrery.retrograde_embedding import (
            embed_retrograde_summary_chunks,
        )

        results = embed_retrograde_summary_chunks(dbname, pending)
        manifest["embedding"] = {"status": "succeeded", "results": results}
    elif pending:
        manifest["embedding"] = {
            "status": "deferred",
            "reason": "orrery.retrograde.retrieval.embed_after_apply is false",
        }
    else:
        manifest["embedding"] = {"status": "none_pending"}

    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _mark_maturation_succeeded(cur, job_id=row["job_id"], manifest=manifest)
    logger.info(
        "Maturation job %s succeeded for %s %r",
        row["job_id"],
        row["entity_kind"],
        row["entity_name"],
    )
    return manifest


def build_runtime_maturation_packet(
    *,
    vocabulary: SeedEligibleVocabulary,
    row: Mapping[str, Any],
    context: Mapping[str, Any],
    cfg: OrreryRetrogradeMaturationSettings,
    dbname: str,
) -> dict[str, Any]:
    """Build a scoped single-entity packet for the runtime maturation pass.

    Reuses the wizard-time request builder and prompt renderer so the R4/R5
    validator sees an identical contract; only the scaffolds, budget, and an
    explicit maturation directive differ.
    """

    from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
    from nexus.agents.orrery.retrograde_seed_candidates import (
        render_seed_generation_prompt,
    )

    declaration = dict(row.get("declaration") or {})
    target_card = {
        "kind": row["entity_kind"],
        "role": "maturation_target",
        "name": row["entity_name"],
        "summary": declaration.get("summary") or context.get("entity_summary"),
        "details": {
            "declared_tag_hints": declaration.get("tag_hints") or [],
            "declared_pair_tag_hints": declaration.get("pair_tag_hints") or [],
        },
    }
    scaffolds = {
        "core_entities": [target_card, *context.get("scene_entities", [])],
        "named_seed_npcs": [],
        "pressure_axes": [
            {
                "kind": "declaration_summary",
                "text": declaration.get("summary"),
            },
            {
                "kind": "requesting_chunk_excerpt",
                "text": context.get("chunk_excerpt"),
            },
        ],
        "trait_hooks": {},
        "candidate_seed_contract": {
            "stage": "runtime single-entity maturation (R4 input)",
            "target_output": "candidate seeds for the maturation target only",
            "selection_required": True,
            "discard_cost": "inference only",
            "anchor_rule": (
                "Every surviving thread must connect the maturation target "
                "to present canon: the requesting scene, its participants, "
                "or established entities."
            ),
        },
    }

    weird = {
        "source": "maturation_default",
        "level": cfg.weird_level,
        "raw": None,
    }
    request = build_seed_generation_request(
        candidate_scaffolds=scaffolds,
        vocabulary=vocabulary,
        weird=weird,
    )
    request["stage"] = "runtime single-entity maturation (R4/R5)"
    request["budget"] = {
        "generate_candidates": cfg.generate_candidates,
        "select_target": cfg.select_target,
        "deferred_secret_cap": cfg.deferred_secret_cap,
        "overgenerate_multiplier": max(
            1, round(cfg.generate_candidates / cfg.select_target)
        ),
    }
    request["prompt_sections"] = list(request["prompt_sections"]) + [
        {
            "heading": "Maturation directive",
            "items": [
                (
                    f"Target entity: {row['entity_name']} "
                    f"({row['entity_kind']}). Generate shallow connected "
                    "backstory for this entity only."
                ),
                (
                    "This is a runtime pass with a tight budget; prefer few, "
                    "sharp seeds over breadth."
                ),
                (
                    "Implied entities get minimum viable mechanical weight "
                    "only; never recursive histories."
                ),
            ],
        }
    ]

    prompt = render_seed_generation_prompt(
        seed_generation_request=request,
        vocabulary=vocabulary,
    )

    return {
        "schema_version": MATURATION_PACKET_SCHEMA_VERSION,
        "kind": "runtime_stub_maturation",
        "dbname": dbname,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "maturation_target": target_card,
        "declaration": declaration,
        "requesting_chunk_id": int(row["requesting_chunk_id"]),
        "weird": weird,
        "seed_eligible_vocabulary": vocabulary,
        "seed_generation_request": request,
        "seed_generation_prompt": prompt,
    }


def namespace_expansion_event_refs(
    expansion_payload: Mapping[str, Any],
    *,
    prefix: str,
) -> dict[str, Any]:
    """Prefix expansion event refs so per-slot idempotency keys never collide.

    Retrograde persistence dedupes on ``payload.retrograde_event_ref`` and the
    per-event summary-chunk marker; two independent maturation jobs would both
    emit Skald-local refs like ``EV1`` without this rewrite.
    """

    payload = json.loads(json.dumps(dict(expansion_payload)))
    mapping = {
        str(event["event_ref"]): f"{prefix}_{event['event_ref']}"
        for event in payload.get("event_plan", [])
        if isinstance(event, dict) and event.get("event_ref")
    }

    for event in payload.get("event_plan", []):
        event["event_ref"] = mapping.get(
            str(event.get("event_ref")), event.get("event_ref")
        )
    for thread in payload.get("thread_plan", []):
        thread["event_refs"] = [
            mapping.get(str(ref), ref) for ref in thread.get("event_refs", [])
        ]
    for key in ("entity_tag_plan", "pair_tag_plan", "relationship_plan"):
        for plan_row in payload.get(key, []):
            source_ref = plan_row.get("source_event_ref")
            if source_ref is not None:
                plan_row["source_event_ref"] = mapping.get(str(source_ref), source_ref)
    return payload


def load_maturation_status_sync(cur: Any) -> dict[str, int]:
    """Return compact maturation queue counts for status snapshots."""

    cur.execute(
        """
        SELECT state::text AS state, count(*) AS count
        FROM orrery_maturation_jobs
        GROUP BY state
        """
    )
    counts = {"queued": 0, "leased": 0, "succeeded": 0, "failed": 0}
    for row in cur.fetchall():
        counts[str(_row_value(row, "state", 0))] = int(_row_value(row, "count", 1))
    return counts


# ============================================================================
# Internal Helpers
# ============================================================================


def _load_job_context(
    cur: Any,
    *,
    row: Mapping[str, Any],
    cfg: OrreryRetrogradeMaturationSettings,
) -> dict[str, Any]:
    """Load scoped prompt material: entity summary, chunk excerpt, anchors."""

    table = _SUBTYPE_TABLES[str(row["entity_kind"])]
    cur.execute(
        f"SELECT summary FROM {table} WHERE id = %s",
        (row["entity_subtype_id"],),
    )
    entity_row = cur.fetchone()
    if entity_row is None:
        raise ValueError(
            f"Maturation job {row['job_id']} references missing "
            f"{row['entity_kind']} id {row['entity_subtype_id']}"
        )
    entity_summary = _row_value(entity_row, "summary", 0)

    cur.execute(
        "SELECT raw_text FROM narrative_chunks WHERE id = %s",
        (row["requesting_chunk_id"],),
    )
    chunk_row = cur.fetchone()
    if chunk_row is None:
        raise ValueError(
            f"Maturation job {row['job_id']} references missing chunk "
            f"{row['requesting_chunk_id']}"
        )
    raw_text = str(_row_value(chunk_row, "raw_text", 0) or "")
    excerpt = _excerpt_around_name(
        raw_text,
        name=str(row["entity_name"]),
        max_chars=cfg.chunk_excerpt_chars,
    )

    scene_entities: list[dict[str, Any]] = []
    for kind, sql in (
        (
            "character",
            """
            SELECT c.name, c.summary
            FROM chunk_character_references r
            JOIN characters c ON c.id = r.character_id
            WHERE r.chunk_id = %s
            ORDER BY c.id
            LIMIT 6
            """,
        ),
        (
            "place",
            """
            SELECT p.name, p.summary
            FROM place_chunk_references r
            JOIN places p ON p.id = r.place_id
            WHERE r.chunk_id = %s
            ORDER BY p.id
            LIMIT 6
            """,
        ),
        (
            "faction",
            """
            SELECT f.name, f.summary
            FROM chunk_faction_references r
            JOIN factions f ON f.id = r.faction_id
            WHERE r.chunk_id = %s
            ORDER BY f.id
            LIMIT 6
            """,
        ),
    ):
        cur.execute(sql, (row["requesting_chunk_id"],))
        for entity in cur.fetchall():
            name = _row_value(entity, "name", 0)
            if name == row["entity_name"]:
                continue
            scene_entities.append(
                {
                    "kind": kind,
                    "role": "scene_anchor",
                    "name": name,
                    "summary": _row_value(entity, "summary", 1),
                    "details": {},
                }
            )

    return {
        "entity_summary": entity_summary,
        "chunk_excerpt": excerpt,
        "scene_entities": scene_entities,
    }


def _excerpt_around_name(raw_text: str, *, name: str, max_chars: int) -> str:
    """Return a window of chunk text centered on the entity's first mention."""

    if len(raw_text) <= max_chars:
        return raw_text
    index = raw_text.lower().find(name.lower())
    if index < 0:
        return raw_text[:max_chars]
    half = max_chars // 2
    start = max(0, index - half)
    return raw_text[start : start + max_chars]


def _entity_event_count(cur: Any, entity_id: int) -> int:
    """Count world events the entity already participates in."""

    cur.execute(
        """
        /* orrery:maturation:already_connected */
        SELECT count(*) AS count FROM (
            SELECT id FROM world_events
            WHERE actor_entity_id = %s OR target_entity_id = %s
            UNION
            SELECT event_id FROM world_event_entities WHERE entity_id = %s
        ) participation
        """,
        (entity_id, entity_id, entity_id),
    )
    return int(_row_value(cur.fetchone(), "count", 0))


def _pending_embedding_ids(cur: Any, chunk_ids: Sequence[Any]) -> list[int]:
    ids = [int(chunk_id) for chunk_id in chunk_ids]
    if not ids:
        return []
    cur.execute(
        """
        SELECT id FROM narrative_chunks
        WHERE id = ANY(%s) AND embedding_generated_at IS NULL
        ORDER BY id
        """,
        (ids,),
    )
    return [int(_row_value(row, "id", 0)) for row in cur.fetchall()]


def _mark_maturation_succeeded(
    cur: Any, *, job_id: int, manifest: Mapping[str, Any]
) -> None:
    cur.execute(
        """
        UPDATE orrery_maturation_jobs
        SET state = 'succeeded',
            lease_until = NULL,
            result_manifest = %s::jsonb,
            updated_at = now()
        WHERE id = %s
        """,
        (json.dumps(manifest), job_id),
    )


def _mark_maturation_failed(
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
            UPDATE orrery_maturation_jobs
            SET state = 'queued',
                available_at = now() + (%s * interval '1 second'),
                lease_until = NULL,
                last_error = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (retry_delay_seconds, error, row["job_id"]),
        )
        return
    cur.execute(
        """
        UPDATE orrery_maturation_jobs
        SET state = 'failed',
            lease_until = NULL,
            last_error = %s,
            updated_at = now()
        WHERE id = %s
        """,
        (error, row["job_id"]),
    )


def _base_manifest(
    row: Mapping[str, Any], cfg: OrreryRetrogradeMaturationSettings
) -> dict[str, Any]:
    return {
        "schema_version": MATURATION_MANIFEST_SCHEMA_VERSION,
        "job_id": int(row["job_id"]),
        "entity": {
            "kind": row["entity_kind"],
            "name": row["entity_name"],
            "entity_id": int(row["entity_id"]),
            "subtype_id": int(row["entity_subtype_id"]),
        },
        "requesting_chunk_id": int(row["requesting_chunk_id"]),
        "budget_seconds": cfg.budget_seconds,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _maturation_settings(
    settings: Mapping[str, Any],
) -> OrreryRetrogradeMaturationSettings:
    raw = ((settings.get("orrery") or {}).get("retrograde") or {}).get(
        "maturation"
    ) or {}
    if isinstance(raw, OrreryRetrogradeMaturationSettings):
        return raw
    return OrreryRetrogradeMaturationSettings.model_validate(raw)


def _retrieval_settings(
    settings: Mapping[str, Any],
) -> OrreryRetrogradeRetrievalSettings:
    raw = ((settings.get("orrery") or {}).get("retrograde") or {}).get(
        "retrieval"
    ) or {}
    if isinstance(raw, OrreryRetrogradeRetrievalSettings):
        return raw
    return OrreryRetrogradeRetrievalSettings.model_validate(raw)


def _slot_int(slot: Optional[int], slot_label: Any) -> int:
    if slot is not None:
        return int(slot)
    try:
        return int(slot_label)
    except (TypeError, ValueError):
        from nexus.api.slot_utils import get_active_slot

        return int(get_active_slot())


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
    """Resolve the slot label stored on a maturation job row.

    Unlike the narration outbox's bookkeeping label, this value routes the
    drain worker's database connection, so an unresolvable slot must fail
    loudly at enqueue time instead of producing a permanently
    unprocessable job. ``get_active_slot`` raises when ``NEXUS_SLOT`` is
    unset or invalid.
    """

    if slot is not None:
        return str(slot)
    from nexus.api.slot_utils import get_active_slot

    return str(get_active_slot())


def _row_value(row: Any, key: str, index: int) -> Any:
    """Read a column from either a RealDict row or a tuple row."""

    if isinstance(row, Mapping):
        return row[key]
    return row[index]
