"""Durable per-slot ownership for narrative generation pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from psycopg2.extras import RealDictCursor


@dataclass(frozen=True)
class GenerationLeaseConflict:
    """Describe the active owner that prevented lease acquisition."""

    active_session_id: str


def acquire_generation_lease(
    conn: Any,
    *,
    session_id: str,
    operation: str,
    stale_timeout_seconds: int,
) -> Optional[GenerationLeaseConflict]:
    """Acquire the slot singleton, replacing only an expired owner."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Row locking cannot serialize the empty-table case. This table is
            # a one-row mutex, so a short transaction-level table lock closes
            # the first-acquisition race without blocking generation itself.
            cur.execute(
                """
                LOCK TABLE narrative_generation_lease
                IN SHARE ROW EXCLUSIVE MODE
                """
            )
            cur.execute(
                """
                SELECT session_id, expires_at <= NOW() AS is_stale
                FROM narrative_generation_lease
                WHERE id = TRUE
                FOR UPDATE
                """
            )
            incumbent = cur.fetchone()
            if incumbent and not incumbent["is_stale"]:
                conn.rollback()
                return GenerationLeaseConflict(
                    active_session_id=str(incumbent["session_id"])
                )

            if incumbent:
                stale_session_id = str(incumbent["session_id"])
                cur.execute(
                    """
                    UPDATE narrative_generation_sessions
                    SET status = 'error',
                        error = 'Generation lease expired before completion.',
                        updated_at = NOW()
                    WHERE session_id = %s
                    """,
                    (stale_session_id,),
                )
                cur.execute("DELETE FROM narrative_generation_lease WHERE id = TRUE")

            cur.execute(
                """
                INSERT INTO narrative_generation_sessions (
                    session_id, operation, status
                ) VALUES (%s, %s, 'initiated')
                ON CONFLICT (session_id) DO UPDATE
                SET operation = EXCLUDED.operation,
                    parent_chunk_id = NULL,
                    status = 'initiated',
                    chunk_id = NULL,
                    error = NULL,
                    updated_at = NOW()
                """,
                (session_id, operation),
            )
            cur.execute(
                """
                INSERT INTO narrative_generation_lease (
                    id, session_id, operation, expires_at
                ) VALUES (
                    TRUE, %s, %s,
                    NOW() + make_interval(secs => %s)
                )
                """,
                (session_id, operation, stale_timeout_seconds),
            )
        conn.commit()
        return None
    except Exception:
        conn.rollback()
        raise


def bind_generation_parent(conn: Any, *, session_id: str, parent_chunk_id: int) -> None:
    """Bind the active owner and its durable status to the resolved parent."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE narrative_generation_lease
                SET parent_chunk_id = %s
                WHERE id = TRUE
                  AND session_id = %s
                  AND expires_at > NOW()
                """,
                (parent_chunk_id, session_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError(
                    f"Generation session {session_id} no longer owns the slot lease."
                )
            cur.execute(
                """
                UPDATE narrative_generation_sessions
                SET parent_chunk_id = %s, updated_at = NOW()
                WHERE session_id = %s
                """,
                (parent_chunk_id, session_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError(
                    f"Generation session record {session_id} is missing."
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def claim_parent_embedding(conn: Any, *, session_id: str, parent_chunk_id: int) -> bool:
    """Claim the locked-chunk embedding trigger once for a parent."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO narrative_parent_embedding_claims (
                    parent_chunk_id, session_id
                )
                SELECT %s, %s
                FROM narrative_generation_lease
                WHERE id = TRUE
                  AND session_id = %s
                  AND parent_chunk_id = %s
                  AND expires_at > NOW()
                ON CONFLICT (parent_chunk_id) DO NOTHING
                """,
                (parent_chunk_id, session_id, session_id, parent_chunk_id),
            )
            claimed = cur.rowcount == 1
        conn.commit()
        return claimed
    except Exception:
        conn.rollback()
        raise


def finish_generation(
    conn: Any,
    *,
    session_id: str,
    status: str,
    chunk_id: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Persist terminal status and release only this session's lease."""
    if status not in {"complete", "error"}:
        raise ValueError(f"Unsupported terminal generation status: {status}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE narrative_generation_sessions
                SET status = %s,
                    chunk_id = %s,
                    error = %s,
                    updated_at = NOW()
                WHERE session_id = %s
                """,
                (status, chunk_id, error, session_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError(
                    f"Generation session record {session_id} is missing."
                )
            cur.execute(
                """
                DELETE FROM narrative_generation_lease
                WHERE id = TRUE AND session_id = %s
                """,
                (session_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def abandon_generation(conn: Any, *, session_id: str, error: str) -> None:
    """Fail and release a lease when the route aborts before scheduling."""
    finish_generation(
        conn,
        session_id=session_id,
        status="error",
        error=error,
    )
