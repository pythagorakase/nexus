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

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.database import AmbiguousCommit, commit_transaction, transaction

logger = logging.getLogger("nexus.api.narrative_lease")


@dataclass(frozen=True)
class GenerationLeaseConflict:
    """Describe the active owner that prevented lease acquisition."""

    active_session_id: str


class GenerationRetryConflict(ValueError):
    """The reviewed failure no longer describes a safe retry frontier."""


@dataclass(frozen=True)
class GenerationRetryContext:
    """The unchanged committed action captured while claiming the slot."""

    parent_chunk_id: int
    user_text: str


def _retry_context(cur: Any, expected_session_id: str) -> GenerationRetryContext:
    """Fence retry against durable state under the generation lease lock."""
    cur.execute(
        "SELECT session_id, status, terminal_outcome, parent_chunk_id, "
        "replaced_by_session_id FROM narrative_generation_sessions "
        "ORDER BY created_at DESC LIMIT 1 FOR UPDATE"
    )
    failed = cur.fetchone()
    if (
        failed is None
        or str(failed["session_id"]) != expected_session_id
        or failed["status"] != "error"
        or failed["terminal_outcome"] != "error"
        or failed["replaced_by_session_id"] is not None
        or failed["parent_chunk_id"] is None
    ):
        raise GenerationRetryConflict(
            "The failed generation changed. Reload the story."
        )
    cur.execute("SELECT 1 FROM incubator LIMIT 1")
    if cur.fetchone() is not None:
        raise GenerationRetryConflict("A pending narrative already exists.")
    cur.execute(
        "SELECT nc.id, nc.choice_text FROM narrative_chunks nc "
        f"WHERE {playable_narrative_predicate()} ORDER BY nc.id DESC LIMIT 1 "
        "FOR UPDATE"
    )
    parent = cur.fetchone()
    parent_id = int(failed["parent_chunk_id"])
    if parent_id == 0 and parent is None:
        return GenerationRetryContext(parent_chunk_id=0, user_text="")
    if (
        parent is None
        or int(parent["id"]) != parent_id
        or not (parent["choice_text"] or "").strip()
    ):
        raise GenerationRetryConflict("The committed action changed. Reload the story.")
    return GenerationRetryContext(
        parent_chunk_id=parent_id, user_text=parent["choice_text"]
    )


def acquire_generation_lease(
    conn: Any,
    *,
    session_id: str,
    operation: str,
    stale_timeout_seconds: int,
    expected_failed_session_id: Optional[str] = None,
) -> Optional[GenerationLeaseConflict | GenerationRetryContext]:
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

            retry = (
                _retry_context(cur, expected_failed_session_id)
                if expected_failed_session_id is not None
                else None
            )
            cur.execute(
                """
                INSERT INTO narrative_generation_sessions (
                    session_id, operation, status, parent_chunk_id
                ) VALUES (%s, %s, 'initiated', %s)
                ON CONFLICT (session_id) DO UPDATE
                SET operation = EXCLUDED.operation,
                    parent_chunk_id = NULL,
                    status = 'initiated',
                    chunk_id = NULL,
                    error = NULL,
                    updated_at = NOW()
                """,
                (session_id, operation, retry.parent_chunk_id if retry else None),
            )
            cur.execute(
                """
                INSERT INTO narrative_generation_lease (
                    id, session_id, operation, expires_at, parent_chunk_id
                ) VALUES (
                    TRUE, %s, %s,
                    NOW() + make_interval(secs => %s), %s
                )
                """,
                (
                    session_id,
                    operation,
                    stale_timeout_seconds,
                    retry.parent_chunk_id if retry else None,
                ),
            )
            if retry is not None:
                cur.execute(
                    "UPDATE narrative_generation_sessions "
                    "SET replaced_by_session_id = %s, updated_at = NOW() "
                    "WHERE session_id = %s",
                    (session_id, expected_failed_session_id),
                )
        commit_transaction(conn)
        return retry
    except AmbiguousCommit:
        raise
    except Exception:
        conn.rollback()
        raise


def associate_accepted_parent(
    cur: Any, *, session_id: str, parent_chunk_id: int
) -> None:
    """Bind a session to the chunk whose player action this transaction records.

    Runs inside the acceptance transaction so the binding commits atomically
    with the action. It requires no lease ownership: when the route has already
    abandoned the session (a post-commit exception, or a cancellation that
    outran the worker's commit), the failed row still gains its parent and the
    reviewed retry can resume the exact recorded action. A parent bound
    earlier is never overwritten.

    Lock order is lease -> session, the same order every other writer in this
    module uses (acquire, bind, heartbeat, finish). A concurrent abandon from a
    cancelled route holds the lease row while it waits for the session row;
    taking the session row first here would form an ABBA deadlock between the
    worker's commit and that cleanup.
    """
    cur.execute(
        """
        UPDATE narrative_generation_lease
        SET parent_chunk_id = %s
        WHERE id = TRUE AND session_id = %s AND parent_chunk_id IS NULL
        """,
        (parent_chunk_id, session_id),
    )
    cur.execute(
        """
        UPDATE narrative_generation_sessions
        SET parent_chunk_id = %s, updated_at = NOW()
        WHERE session_id = %s AND parent_chunk_id IS NULL
        """,
        (parent_chunk_id, session_id),
    )


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
            from nexus.jobs.embeddings import enqueue_locked_embeddings

            enqueue_locked_embeddings(cur, parent_chunk_id, session_id)
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
    accepted_parent_candidate: Optional[int] = None,
) -> None:
    """Apply one terminal transition using lease -> claims -> session order.

    ``accepted_parent_candidate`` names the frontier chunk a failed route acted
    on before it could bind its parent. The player's action is committed in its
    own transaction ahead of the bind, so the session is bound to that chunk
    here, in the same transaction that records the failure, if and only if the
    chunk durably holds a recorded action. A failure with no recorded action
    keeps a NULL parent and ordinary input stays open.
    """
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
            if accepted_parent_candidate is not None:
                cur.execute(
                    "SELECT choice_text FROM narrative_chunks WHERE id = %s",
                    (accepted_parent_candidate,),
                )
                candidate = cur.fetchone()
                if candidate and (candidate["choice_text"] or "").strip():
                    cur.execute(
                        """
                        UPDATE narrative_generation_sessions
                        SET parent_chunk_id = %s, updated_at = NOW()
                        WHERE session_id = %s AND parent_chunk_id IS NULL
                        """,
                        (accepted_parent_candidate, session_id),
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
    conn: Any,
    *,
    session_id: str,
    error: str,
    error_class: str = "GenerationError",
    accepted_parent_candidate: Optional[int] = None,
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
        accepted_parent_candidate=accepted_parent_candidate,
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
