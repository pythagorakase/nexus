"""Durable per-slot ownership for narrative generation pipelines.

Lock-order invariant
--------------------
Every transaction in this module locks or mutates
``narrative_generation_lease`` before touching
``narrative_generation_sessions``. Transactions that also touch embedding
claims use the order lease -> claims -> sessions. Acquisition takes an
explicit lease-table lock first because there may not yet be a singleton row;
that lock remains held while the new session and its foreign-keyed lease row
are inserted. Keeping this order uniform prevents stale takeover and terminal
completion from forming an ABBA deadlock.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from psycopg2.extras import RealDictCursor

logger = logging.getLogger("nexus.api.narrative_lease")


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
                cur.execute("DELETE FROM narrative_generation_lease WHERE id = TRUE")
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
    """Claim a parent, replacing only a terminal-error session's orphan."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT session_id
                FROM narrative_generation_lease
                WHERE id = TRUE
                  AND session_id = %s
                  AND parent_chunk_id = %s
                  AND expires_at > NOW()
                FOR UPDATE
                """,
                (session_id, parent_chunk_id),
            )
            if cur.fetchone() is None:
                raise RuntimeError(
                    f"Generation session {session_id} no longer owns parent "
                    f"{parent_chunk_id}."
                )
            cur.execute(
                """
                INSERT INTO narrative_parent_embedding_claims (
                    parent_chunk_id, session_id
                ) VALUES (%s, %s)
                ON CONFLICT (parent_chunk_id) DO UPDATE
                SET session_id = EXCLUDED.session_id,
                    claimed_at = NOW()
                WHERE EXISTS (
                    SELECT 1
                    FROM narrative_generation_sessions incumbent
                    WHERE incumbent.session_id =
                        narrative_parent_embedding_claims.session_id
                      AND incumbent.status = 'error'
                )
                """,
                (parent_chunk_id, session_id),
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
    """Persist monotonic terminal status and release only this session's lease."""
    _finish_generation(
        conn,
        session_id=session_id,
        status=status,
        chunk_id=chunk_id,
        error=error,
        release_embedding_claim=False,
    )


def _finish_generation(
    conn: Any,
    *,
    session_id: str,
    status: str,
    chunk_id: Optional[int],
    error: Optional[str],
    release_embedding_claim: bool,
) -> None:
    """Apply one terminal transition using lease -> claims -> session order."""
    if status not in {"complete", "error"}:
        raise ValueError(f"Unsupported terminal generation status: {status}")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                DELETE FROM narrative_generation_lease
                WHERE id = TRUE AND session_id = %s
                RETURNING session_id
                """,
                (session_id,),
            )
            released_lease = cur.fetchone() is not None
            if release_embedding_claim:
                cur.execute(
                    """
                    DELETE FROM narrative_parent_embedding_claims
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )

            cur.execute(
                """
                SELECT status, chunk_id
                FROM narrative_generation_sessions
                WHERE session_id = %s
                FOR UPDATE
                """,
                (session_id,),
            )
            session = cur.fetchone()
            if session is None:
                raise RuntimeError(
                    f"Generation session record {session_id} is missing."
                )

            current_status = str(session["status"])
            if current_status == "complete" and status == "error":
                logger.error(
                    "Refusing to downgrade completed generation session %s to error: %s",
                    session_id,
                    error,
                )
                raise RuntimeError(
                    f"Generation session {session_id} is already complete; "
                    "refusing error downgrade."
                )
            if not released_lease and current_status == "initiated":
                raise RuntimeError(
                    f"Generation session {session_id} does not own the slot lease."
                )
            if not released_lease and status == "complete":
                raise RuntimeError(
                    f"Generation session {session_id} lost its lease before completion."
                )

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
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def abandon_generation(conn: Any, *, session_id: str, error: str) -> None:
    """Fail a pre-scheduling route and release both its lease and parent claim."""
    _finish_generation(
        conn,
        session_id=session_id,
        status="error",
        chunk_id=None,
        error=error,
        release_embedding_claim=True,
    )
