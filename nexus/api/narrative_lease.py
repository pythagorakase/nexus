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

from nexus.database import AmbiguousCommit, commit_transaction, transaction

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
                    SET status = 'error', terminal_outcome = 'error',
                        error_class = 'GenerationLeaseExpired',
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
        commit_transaction(conn)
        return None
    except AmbiguousCommit:
        raise
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
        commit_transaction(conn)
    except AmbiguousCommit:
        raise
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
        commit_transaction(conn)
        return claimed
    except AmbiguousCommit:
        raise
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
    error_class: Optional[str] = None,
) -> None:
    """Persist monotonic terminal status and release only this session's lease."""
    _finish_generation(
        conn,
        session_id=session_id,
        status=status,
        chunk_id=chunk_id,
        error=error,
        release_embedding_claim=False,
        error_class=error_class,
    )


def _finish_generation(
    conn: Any,
    *,
    session_id: str,
    status: str,
    chunk_id: Optional[int],
    error: Optional[str],
    release_embedding_claim: bool,
    error_class: Optional[str] = None,
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
                SELECT status, chunk_id, terminal_outcome
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

            if session["terminal_outcome"] in {"accepted", "superseded", "discarded"}:
                commit_transaction(conn)
                return
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
                    phase = CASE WHEN %s = 'complete' THEN 'complete' ELSE phase END,
                    terminal_outcome = CASE WHEN %s = 'error' THEN 'error' END,
                    error_class = %s,
                    error = %s,
                    updated_at = NOW()
                WHERE session_id = %s
                """,
                (
                    status,
                    chunk_id,
                    status,
                    status,
                    error_class or ("GenerationError" if status == "error" else None),
                    error,
                    session_id,
                ),
            )
        commit_transaction(conn)
        if released_lease:
            from nexus.jobs.scheduler import notify_generation_released

            notify_generation_released(conn.info.dbname)
    except AmbiguousCommit:
        raise
    except Exception:
        conn.rollback()
        raise


def abandon_generation(
    conn: Any, *, session_id: str, error: str, error_class: str = "GenerationError"
) -> None:
    """Fail a pre-scheduling route and release both its lease and parent claim."""
    _finish_generation(
        conn,
        session_id=session_id,
        status="error",
        chunk_id=None,
        error=error,
        release_embedding_claim=True,
        error_class=error_class,
    )


def heartbeat_generation(
    conn: Any, *, session_id: str, timeout_seconds: int, phase: Optional[str] = None
) -> None:
    """Renew a live owner and persist its actual phase in one transaction."""
    with transaction(conn):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE narrative_generation_lease "
                "SET expires_at = clock_timestamp() + make_interval(secs => %s) "
                "WHERE session_id = %s AND expires_at > clock_timestamp()",
                (timeout_seconds, session_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"Generation session {session_id} lost its lease")
            cur.execute(
                "UPDATE narrative_generation_sessions SET heartbeat_at = clock_timestamp(), "
                "phase = COALESCE(%s, phase), updated_at = clock_timestamp() "
                "WHERE session_id = %s AND status = 'initiated'",
                (phase, session_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"Generation session {session_id} is not active")


def read_generation_session(
    conn: Any, *, session_id: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Read the lease owner, or latest durable attempt, and reap crashed owners.

    A fresh reader must also discover a turn that finished while disconnected.
    The latest session remains discoverable after its lease has been released.
    """
    with transaction(conn):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT session_id FROM narrative_generation_lease "
                "WHERE expires_at <= clock_timestamp()"
            )
            if cur.fetchone() is not None:
                cur.execute(
                    "LOCK TABLE narrative_generation_lease IN SHARE ROW EXCLUSIVE MODE"
                )
                cur.execute(
                    "DELETE FROM narrative_generation_lease "
                    "WHERE expires_at <= clock_timestamp() RETURNING session_id"
                )
                expired = cur.fetchone()
                if expired:
                    cur.execute(
                        "UPDATE narrative_generation_sessions SET status = 'error', "
                        "terminal_outcome = 'error', error_class = 'GenerationLeaseExpired', "
                        "error = 'Generation lease expired before completion.', updated_at = NOW() "
                        "WHERE session_id = %s AND status = 'initiated'",
                        (expired["session_id"],),
                    )
            cur.execute(
                "SELECT gs.*, lease.expires_at FROM narrative_generation_sessions gs "
                "LEFT JOIN narrative_generation_lease lease USING (session_id) "
                "WHERE (%s IS NULL OR gs.session_id = %s) "
                "ORDER BY (lease.session_id IS NOT NULL) DESC, gs.created_at DESC LIMIT 1",
                (session_id, session_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            row = dict(row)
            row["session_id"] = str(row["session_id"])
            if row["replaced_by_session_id"] is not None:
                row["replaced_by_session_id"] = str(row["replaced_by_session_id"])
            return row


def discard_generation(cur: Any, session_id: str) -> None:
    """Record intentional draft removal in the same transaction as its delete."""
    cur.execute(
        "UPDATE narrative_generation_sessions SET status = 'complete', "
        "terminal_outcome = 'discarded', error_class = NULL, error = NULL, "
        "updated_at = NOW() WHERE session_id = %s AND terminal_outcome IS NULL",
        (session_id,),
    )
