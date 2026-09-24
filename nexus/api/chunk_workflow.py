"""
Chunk acceptance and embedding workflow management.

This module handles the finalization of narrative chunks, including:
- User acceptance/rejection of Storyteller text
- Automatic embedding generation triggers
- Edit-previous-input functionality
- Regeneration tracking
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import psycopg2
from pydantic import BaseModel

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.api.db_pool import get_connection

logger = logging.getLogger("nexus.api.chunk_workflow")

# Security: Valid database names (command injection prevention)
VALID_DATABASES = {"save_01", "save_02", "save_03", "save_04", "save_05"}

EmbeddingScheduler = Callable[[int], Optional[str]]


def build_embedding_scheduler(
    workflow: "ChunkWorkflow", add_task: Callable[..., Any]
) -> EmbeddingScheduler:
    """Return the durable enqueue entry point for legacy route callers."""
    return workflow.trigger_embedding_generation


class ChunkState(str, Enum):
    """States for narrative chunk lifecycle.

    The authoritative "has been embedded" predicate is
    narrative_chunks.embedding_generated_at IS NOT NULL — that timestamp is
    the single source of truth for ironman status. Earlier versions also
    carried a redundant 'embedded' state value; retired in migration 021.
    """

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"  # Storyteller text awaiting user decision
    FINALIZED = "finalized"  # User accepted, chunk is locked


class ChunkAcceptResponse(BaseModel):
    """Response after accepting a chunk."""

    chunk_id: int
    state: ChunkState
    previous_chunk_embedded: bool
    embedding_job_id: Optional[str] = None


class ChunkRejectResponse(BaseModel):
    """Response after rejecting a chunk."""

    chunk_id: int
    state: ChunkState
    action_taken: str
    regeneration_count: Optional[int] = None
    edit_enabled: bool = False


class EditPreviousResponse(BaseModel):
    """Response after editing previous input."""

    previous_chunk_id: int
    updated: bool
    new_generation_triggered: bool


class ChunkWorkflow:
    """Manages chunk acceptance workflow and embedding triggers."""

    def __init__(self, dbname: Optional[str] = None):
        dbname = dbname or "save_01"

        # Security: Validate database name to prevent command injection
        if dbname not in VALID_DATABASES:
            raise ValueError(
                f"Invalid database name: {dbname}. "
                f"Must be one of: {', '.join(sorted(VALID_DATABASES))}"
            )

        self.dbname = dbname
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensure the necessary columns exist in narrative_chunks table."""
        with get_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Check if columns exist, add if not
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'narrative_chunks'
                    AND column_name IN ('state', 'finalized_at', 'embedding_generated_at', 'regeneration_count')
                """
                )
                existing_columns = {row[0] for row in cur.fetchall()}

                # Add missing columns
                if "state" not in existing_columns:
                    cur.execute(
                        """
                        ALTER TABLE narrative_chunks
                        ADD COLUMN state VARCHAR(20) DEFAULT 'draft'
                    """
                    )
                    logger.info("Added state column to narrative_chunks")

                if "finalized_at" not in existing_columns:
                    cur.execute(
                        """
                        ALTER TABLE narrative_chunks
                        ADD COLUMN finalized_at TIMESTAMPTZ
                    """
                    )
                    logger.info("Added finalized_at column to narrative_chunks")

                if "embedding_generated_at" not in existing_columns:
                    cur.execute(
                        """
                        ALTER TABLE narrative_chunks
                        ADD COLUMN embedding_generated_at TIMESTAMPTZ
                    """
                    )
                    logger.info(
                        "Added embedding_generated_at column to narrative_chunks"
                    )

                if "regeneration_count" not in existing_columns:
                    cur.execute(
                        """
                        ALTER TABLE narrative_chunks
                        ADD COLUMN regeneration_count INTEGER DEFAULT 0
                    """
                    )
                    logger.info("Added regeneration_count column to narrative_chunks")

    def accept_chunk(
        self,
        chunk_id: int,
        session_id: str,
        embedding_scheduler: Optional[EmbeddingScheduler] = None,
    ) -> ChunkAcceptResponse:
        """
        Accept a Storyteller chunk, finalizing it and triggering embedding for the previous chunk.

        Args:
            chunk_id: The chunk to accept
            session_id: Session context
            embedding_scheduler: Optional scheduler for async embedding generation

        Returns:
            Response with finalization status and embedding job info
        """
        with get_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Security: Atomic state transition to prevent race condition
                # Only finalize if currently pending_review (prevents double-finalization)
                cur.execute(
                    """
                    UPDATE narrative_chunks
                    SET state = %s, finalized_at = %s
                    WHERE id = %s AND state = %s
                    RETURNING id
                """,
                    (
                        ChunkState.FINALIZED.value,
                        datetime.now(timezone.utc),
                        chunk_id,
                        ChunkState.PENDING_REVIEW.value,  # Only update if pending
                    ),
                )

                if not cur.fetchone():
                    # Check if chunk exists but wrong state
                    cur.execute(
                        "SELECT state FROM narrative_chunks WHERE id = %s", (chunk_id,)
                    )
                    result = cur.fetchone()
                    if not result:
                        raise ValueError(f"Chunk {chunk_id} not found")
                    else:
                        raise ValueError(
                            f"Chunk {chunk_id} cannot be accepted (current state: {result[0]})"
                        )

                # Get the previous player-played chunk to trigger embedding.
                # Sparse ids and Retrograde's synthetic prologue mean this
                # is not necessarily the row with the immediately preceding
                # id.
                cur.execute(
                    f"""
                    SELECT nc.id, nc.embedding_generated_at
                    FROM narrative_chunks nc
                    WHERE nc.id < %s
                      AND {playable_narrative_predicate("nc")}
                    ORDER BY nc.id DESC
                    LIMIT 1
                """,
                    (chunk_id,),
                )

                previous_chunk = cur.fetchone()
                embedding_triggered = False
                embedding_job_id = None

                if previous_chunk:
                    prev_id, prev_embedded_at = previous_chunk

                    # Fire embedding on the previous chunk only if it hasn't
                    # been embedded yet. embedding_generated_at IS NULL is the
                    # authoritative "not yet ironman" predicate; the old
                    # state=='embedded' value was a redundant proxy for this
                    # same signal and has been retired.
                    if prev_embedded_at is None:
                        from nexus.jobs.embeddings import enqueue_embedding

                        embedding_job_id = enqueue_embedding(cur, prev_id)
                        embedding_triggered = embedding_job_id is not None

                logger.info(
                    f"Accepted chunk {chunk_id}, embedding triggered: {embedding_triggered}"
                )

                return ChunkAcceptResponse(
                    chunk_id=chunk_id,
                    state=ChunkState.FINALIZED,
                    previous_chunk_embedded=embedding_triggered,
                    embedding_job_id=embedding_job_id,
                )

    def reject_chunk(
        self, chunk_id: int, session_id: str, action: str
    ) -> ChunkRejectResponse:
        """
        Reject a Storyteller chunk with specified action.

        Args:
            chunk_id: The chunk to reject
            session_id: Session context
            action: Either 'regenerate' or 'edit_previous'

        Returns:
            Response with rejection status and available actions
        """
        with get_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Get current chunk info
                cur.execute(
                    """
                    SELECT state, regeneration_count
                    FROM narrative_chunks
                    WHERE id = %s
                """,
                    (chunk_id,),
                )

                result = cur.fetchone()
                if not result:
                    raise ValueError(f"Chunk {chunk_id} not found")

                current_state, regen_count = result

                if current_state == ChunkState.FINALIZED.value:
                    raise ValueError(f"Cannot reject finalized chunk {chunk_id}")

                response = ChunkRejectResponse(
                    chunk_id=chunk_id,
                    state=ChunkState.PENDING_REVIEW,
                    action_taken=action,
                    regeneration_count=regen_count,
                )

                if action == "regenerate":
                    # Increment regeneration counter
                    cur.execute(
                        """
                        UPDATE narrative_chunks
                        SET regeneration_count = regeneration_count + 1,
                            state = %s
                        WHERE id = %s
                        RETURNING regeneration_count
                    """,
                        (ChunkState.PENDING_REVIEW.value, chunk_id),
                    )

                    new_count = cur.fetchone()[0]
                    response.regeneration_count = new_count
                    logger.info(
                        f"Chunk {chunk_id} marked for regeneration (attempt {new_count})"
                    )

                elif action == "edit_previous":
                    # Enable editing of previous user input
                    response.edit_enabled = True
                    logger.info(f"Chunk {chunk_id} rejected, edit previous enabled")

                return response

    def edit_previous_input(
        self, chunk_id: int, new_user_input: str, session_id: str
    ) -> EditPreviousResponse:
        """
        Edit the user's input from the previous chunk.

        Args:
            chunk_id: Current chunk ID (rejected Storyteller text)
            new_user_input: New text for the user's previous input
            session_id: Session context

        Returns:
            Response indicating success and new generation trigger
        """
        with get_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Security: Compute arithmetic in Python, not SQL (prevents injection)
                prev_chunk_id = chunk_id - 1

                # Find the previous user chunk (should be user input)
                cur.execute(
                    """
                    SELECT id, state, raw_text
                    FROM narrative_chunks
                    WHERE id = %s
                """,
                    (prev_chunk_id,),
                )

                prev_chunk = cur.fetchone()
                if not prev_chunk:
                    raise ValueError(f"Previous chunk not found for chunk {chunk_id}")

                prev_id, prev_state, old_text = prev_chunk

                # Ensure previous chunk isn't finalized
                if prev_state == ChunkState.FINALIZED.value:
                    raise ValueError(f"Cannot edit finalized chunk {prev_id}")

                # Update the user's previous input
                cur.execute(
                    """
                    UPDATE narrative_chunks
                    SET raw_text = %s,
                        state = %s
                    WHERE id = %s
                """,
                    (new_user_input, ChunkState.DRAFT.value, prev_id),
                )

                # Mark current Storyteller chunk for regeneration
                cur.execute(
                    """
                    UPDATE narrative_chunks
                    SET state = %s,
                        regeneration_count = regeneration_count + 1
                    WHERE id = %s
                """,
                    (ChunkState.PENDING_REVIEW.value, chunk_id),
                )

                logger.info(
                    f"Updated user input in chunk {prev_id}, triggering regeneration of {chunk_id}"
                )

                return EditPreviousResponse(
                    previous_chunk_id=prev_id,
                    updated=True,
                    new_generation_triggered=True,
                )

    def revert_pending_choice(self, cur, parent_chunk_id: int) -> None:
        """Clear a recastable parent selection in the caller's undo transaction."""
        from nexus.api.choice_recovery import clear_parent_choice

        clear_parent_choice(cur, parent_chunk_id)

    def trigger_embedding_generation(
        self, chunk_id: int, job_id: Optional[str] = None
    ) -> str:
        """Persist a plan for the slot scheduler; never execute a model here."""
        from nexus.jobs.embeddings import enqueue_embedding

        with get_connection(self.dbname) as conn, conn.cursor() as cur:
            return enqueue_embedding(cur, chunk_id)

    def get_chunk_states(
        self, start_chunk: int, end_chunk: int
    ) -> List[Dict[str, Any]]:
        """
        Get the states of chunks in a range.

        Args:
            start_chunk: Starting chunk ID
            end_chunk: Ending chunk ID

        Returns:
            List of chunk state information
        """
        with get_connection(self.dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, state, finalized_at, embedding_generated_at, regeneration_count
                    FROM narrative_chunks
                    WHERE id BETWEEN %s AND %s
                    ORDER BY id
                """,
                    (start_chunk, end_chunk),
                )

                return [dict(row) for row in cur.fetchall()]


# Lazily constructed singleton for the default database. Building the
# workflow eagerly at import time opened a Postgres pool and ran
# _ensure_schema() before any caller asked for a DB-backed action, which
# coupled every `nexus.api` import to database availability (issue #369).
_default_workflow: Optional[ChunkWorkflow] = None
_default_workflow_lock = threading.Lock()


def get_default_workflow() -> ChunkWorkflow:
    """Return the default-database ChunkWorkflow, constructing it on first use.

    The first call opens the connection pool and runs schema validation;
    subsequent calls return the cached instance.
    """
    global _default_workflow
    if _default_workflow is None:
        with _default_workflow_lock:
            if _default_workflow is None:
                _default_workflow = ChunkWorkflow()
    return _default_workflow
