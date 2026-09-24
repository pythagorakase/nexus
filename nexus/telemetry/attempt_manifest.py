"""Durable attempt references and hashes, scoped to a real generation owner."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
import hashlib
import json
from typing import Any

from pydantic_core import to_jsonable_python

from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor

from nexus.telemetry.prompt_window import PromptWindowRecord

_connection_factory: ContextVar[Callable[[], Any] | None] = ContextVar(
    "attempt_manifest_connection", default=None
)


def identity_hash(value: Any) -> str:
    """Hash canonical UTF-8 JSON without retaining its source payload."""
    return hashlib.sha256(
        json.dumps(
            to_jsonable_python(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


@contextmanager
def manifest_scope(factory: Callable[[], Any] | None) -> Iterator[None]:
    """Persist only attempts owned by the canonical durable generation task."""
    token = _connection_factory.set(factory)
    try:
        yield
    finally:
        _connection_factory.reset(token)


def start_attempt(
    record: PromptWindowRecord,
    *,
    blocks: list[dict[str, Any]],
    system_prompt: str,
    prompt: str,
    settings: dict[str, Any],
    wire_schema: dict[str, Any],
) -> None:
    """Insert the dispatch identity before generation, without copying canon."""
    factory = _connection_factory.get()
    if factory is None:
        return
    with closing(factory()) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT model, gaia_model, apex_context_window FROM global_variables WHERE id"
        )
        pin = cur.fetchone()
        if pin is None:
            raise RuntimeError("Attempt manifest requires story model pins")
        # The prompt record's trimming and validation data can contain free text;
        # persist only the declared numeric accounting fields.
        window = record.model_dump(
            include={
                "block_tokens",
                "input_tokens",
                "effective_ceiling",
                "policy_headroom",
                "headroom",
            }
        )
        # Serialize with terminal transitions so neither insertion order can
        # leave a late retry without the owning session's decision.
        cur.execute(
            "SELECT terminal_outcome FROM narrative_generation_sessions "
            "WHERE session_id=%s FOR UPDATE",
            (record.generation_session,),
        )
        session = cur.fetchone()
        if session is None:
            raise RuntimeError("Attempt manifest requires a generation session")
        cur.execute(
            """INSERT INTO generation_attempt_manifests (
                generation_session_id, seat, attempt, blocks, window_record,
                model_id, story_pin, config_sha256, wire_schema_sha256, prompt_sha256, outcome
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                record.generation_session,
                record.seat,
                record.attempt,
                Json(blocks),
                Json(window),
                record.model,
                Json(dict(zip(("model", "gaia_model", "apex_context_window"), pin))),
                identity_hash(settings),
                identity_hash(wire_schema),
                identity_hash({"system": system_prompt, "user": prompt}),
                session[0],
            ),
        )
        _refresh_references(cur, record)


def _refresh_references(cur: Any, record: PromptWindowRecord) -> None:
    cur.execute(
        """UPDATE generation_attempt_manifests SET
        retrieval_ids = ARRAY(SELECT id FROM retrieval_coverage_log
            WHERE turn_id=%s ORDER BY id),
        recall_ids = ARRAY(SELECT id FROM orrery_recall_trace
            WHERE turn_id=%s ORDER BY id)
        WHERE generation_session_id=%s AND seat=%s AND attempt=%s""",
        (
            record.generation_session,
            record.generation_session,
            record.generation_session,
            record.seat,
            record.attempt,
        ),
    )


def _validation_metadata(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metadata = []
    for note in notes:
        item: dict[str, Any] = {"sha256": identity_hash(note)}
        if note.get("repair") == "scene-reset-crossings":
            item.update(
                repair="scene-reset-crossings",
                moved_count=len(note.get("moved", [])),
                dropped_count=len(note.get("dropped", [])),
            )
        elif note.get("repair") == "active-extend-expiry":
            item["repair"] = "active-extend-expiry"
            if "entity_kind" in note and "entity_id" in note:
                item["entity_kind"] = note["entity_kind"]
                item["entity_id"] = note["entity_id"]
        elif note.get("rejection") == "wire-contract-violation":
            item["rejection"] = "wire-contract-violation"
        metadata.append(item)
    return metadata


def update_validation(record: PromptWindowRecord) -> None:
    """Store safe repair codes/counts and a hash of each original validation note."""
    factory = _connection_factory.get()
    if factory is None:
        return
    with closing(factory()) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE generation_attempt_manifests SET validation=%s, updated_at=now()
            WHERE generation_session_id=%s AND seat=%s AND attempt=%s""",
            (
                Json(_validation_metadata(record.validation_notes)),
                record.generation_session,
                record.seat,
                record.attempt,
            ),
        )
        if cur.rowcount != 1:
            raise RuntimeError("Validation has no durable attempt manifest")


def record_response(record: PromptWindowRecord, response: Any) -> None:
    """Hash the raw SDK envelope before output validation or repair mutates it."""
    factory = _connection_factory.get()
    if factory is None:
        return
    raw = response.model_dump(mode="json")

    # SDK-derived parsed objects are not part of the raw provider response.
    def raw_only(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: raw_only(item) for key, item in value.items() if key != "parsed"
            }
        if isinstance(value, list):
            return [raw_only(item) for item in value]
        return value

    with closing(factory()) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE generation_attempt_manifests SET response_sha256=%s, updated_at=now()
            WHERE generation_session_id=%s AND seat=%s AND attempt=%s""",
            (
                identity_hash(raw_only(raw)),
                record.generation_session,
                record.seat,
                record.attempt,
            ),
        )
        if cur.rowcount != 1:
            raise RuntimeError("Response has no durable attempt manifest")


def finish_attempt(record: PromptWindowRecord, outcome: str) -> None:
    """Finish a provider attempt independently of the later draft decision."""
    factory = _connection_factory.get()
    if factory is None:
        return
    with closing(factory()) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE generation_attempt_manifests SET provider_outcome=%s, updated_at=now()
            WHERE generation_session_id=%s AND seat=%s AND attempt=%s""",
            (outcome, record.generation_session, record.seat, record.attempt),
        )
        if cur.rowcount != 1:
            raise RuntimeError("Provider outcome has no durable attempt manifest")
        _refresh_references(cur, record)


def bind_exposures(cur: Any, session: str, chunk: int) -> None:
    """Bind accepted exposure references in the same transaction as the chunk."""
    cur.execute(
        """UPDATE generation_attempt_manifests SET exposure_ids=ARRAY(
        SELECT id FROM orrery_prompt_exposures WHERE tick_chunk_id=%s ORDER BY id
        ), updated_at=now() WHERE generation_session_id=%s""",
        (chunk, session),
    )


def prune_manifests(conn: Any, days: int) -> int:
    """Explicitly delete expired terminal manifests; retain live attempts."""
    if days < 1:
        raise ValueError("Manifest retention must be at least one day")
    with conn, conn.cursor() as cur:
        cur.execute(
            """DELETE FROM generation_attempt_manifests m
            USING narrative_generation_sessions s
            WHERE s.session_id=m.generation_session_id
              AND s.terminal_outcome IS NOT NULL
              AND m.created_at < now() - (%s * interval '1 day')""",
            (days,),
        )
        return cur.rowcount


JOB_TABLES = {
    "experience_render": "character_experience_jobs",
    "retrograde_maturation": "orrery_maturation_jobs",
    "correspondence_compaction": "correspondence_compaction_jobs",
    "narration": "orrery_narration_jobs",
}


def inspect_turn(
    conn: Any, *, session: str | None = None, chunk: int | None = None
) -> dict[str, Any]:
    """Read one causal chain under a database-enforced read-only snapshot."""
    if (session is None) == (chunk is None):
        raise ValueError("Specify exactly one session or accepted chunk")
    conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT session_id::text, operation, parent_chunk_id, phase,
                terminal_outcome, CASE WHEN terminal_outcome='accepted' THEN chunk_id END AS accepted_chunk_id,
                replaced_by_session_id::text, error_class
            FROM narrative_generation_sessions
            WHERE session_id=%s OR (chunk_id=%s AND terminal_outcome='accepted')""",
            (session, chunk),
        )
        sessions = cur.fetchall()
        if len(sessions) != 1:
            raise ValueError(f"Expected one generation session; found {len(sessions)}")
        summary = dict(sessions[0])
        session = summary["session_id"]
        cur.execute(
            "SELECT phase, recorded_at::text FROM generation_session_phases WHERE generation_session_id=%s ORDER BY id",
            (session,),
        )
        phases = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """SELECT m.*
            FROM generation_attempt_manifests m JOIN narrative_generation_sessions s
            ON s.session_id=m.generation_session_id
            WHERE m.generation_session_id=%s ORDER BY seat, attempt""",
            (session,),
        )
        manifests = [dict(row) for row in cur.fetchall()]
        for manifest in manifests:
            for key in ("generation_session_id", "created_at", "updated_at"):
                manifest[key] = str(manifest[key])
        jobs = []
        for queue, table in JOB_TABLES.items():
            cur.execute(
                sql.SQL(
                    "SELECT id, state::text, generation_session_id::text FROM {} WHERE generation_session_id=%s ORDER BY id"
                ).format(sql.Identifier(table)),
                (session,),
            )
            jobs.extend(dict(row, queue=queue) for row in cur.fetchall())
        cur.execute(
            """SELECT version_id AS id, CASE WHEN event_id IS NULL THEN 'pending'
                ELSE 'succeeded' END AS state, generation_session_id::text
            FROM relationship_milestone_queue WHERE generation_session_id=%s ORDER BY version_id""",
            (session,),
        )
        jobs.extend(dict(row, queue="relationship_milestone") for row in cur.fetchall())
        return {
            "session": summary,
            "phases": phases,
            "manifests": manifests,
            "jobs": jobs,
        }
