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
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path
import subprocess
import json
import re

import psycopg2
from pydantic import BaseModel, Field

from nexus.api.db_pool import get_connection

logger = logging.getLogger("nexus.api.chunk_workflow")

# Security: Valid database names (command injection prevention)
VALID_DATABASES = {"save_01", "save_02", "save_03", "save_04", "save_05"}

# Security: Valid model name pattern (alphanumeric, hyphens, dots, underscores only)
VALID_MODEL_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')


class ChunkState(str, Enum):
    """States for narrative chunk lifecycle."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"  # Storyteller text awaiting user decision
    FINALIZED = "finalized"  # User accepted, chunk is locked
    EMBEDDED = "embedded"  # Embeddings have been generated


class ChunkAcceptRequest(BaseModel):
    """Request to accept a Storyteller chunk."""

    chunk_id: int = Field(..., description="ID of the chunk to accept")
    session_id: str = Field(..., description="Session ID for context")


class ChunkAcceptResponse(BaseModel):
    """Response after accepting a chunk."""

    chunk_id: int
    state: ChunkState
    previous_chunk_embedded: bool
    embedding_job_id: Optional[str] = None


class ChunkRejectRequest(BaseModel):
    """Request to reject a Storyteller chunk."""

    chunk_id: int = Field(..., description="ID of the chunk to reject")
    session_id: str = Field(..., description="Session ID for context")
    action: str = Field(..., pattern="^(regenerate|edit_previous)$",
                       description="Action to take: regenerate or edit_previous")


class ChunkRejectResponse(BaseModel):
    """Response after rejecting a chunk."""

    chunk_id: int
    state: ChunkState
    action_taken: str
    regeneration_count: Optional[int] = None
    edit_enabled: bool = False


class EditPreviousRequest(BaseModel):
    """Request to edit the user's previous input."""

    chunk_id: int = Field(..., description="Current chunk ID")
    new_user_input: str = Field(..., min_length=1, description="New user input text")
    session_id: str = Field(..., description="Session ID for context")


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
                cur.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'narrative_chunks'
                    AND column_name IN ('state', 'finalized_at', 'embedding_generated_at', 'regeneration_count')
                """)
                existing_columns = {row[0] for row in cur.fetchall()}

                # Add missing columns
                if 'state' not in existing_columns:
                    cur.execute("""
                        ALTER TABLE narrative_chunks
                        ADD COLUMN state VARCHAR(20) DEFAULT 'draft'
                    """)
                    logger.info("Added state column to narrative_chunks")

                if 'finalized_at' not in existing_columns:
                    cur.execute("""
                        ALTER TABLE narrative_chunks
                        ADD COLUMN finalized_at TIMESTAMPTZ
                    """)
                    logger.info("Added finalized_at column to narrative_chunks")

                if 'embedding_generated_at' not in existing_columns:
                    cur.execute("""
                        ALTER TABLE narrative_chunks
                        ADD COLUMN embedding_generated_at TIMESTAMPTZ
                    """)
                    logger.info("Added embedding_generated_at column to narrative_chunks")

                if 'regeneration_count' not in existing_columns:
                    cur.execute("""
                        ALTER TABLE narrative_chunks
                        ADD COLUMN regeneration_count INTEGER DEFAULT 0
                    """)
                    logger.info("Added regeneration_count column to narrative_chunks")

    def accept_chunk(self, chunk_id: int, session_id: str) -> ChunkAcceptResponse:
        """
        Accept a Storyteller chunk, finalizing it and triggering embedding for the previous chunk.

        Args:
            chunk_id: The chunk to accept
            session_id: Session context

        Returns:
            Response with finalization status and embedding job info
        """
        with get_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Security: Atomic state transition to prevent race condition
                # Only finalize if currently pending_review (prevents double-finalization)
                cur.execute("""
                    UPDATE narrative_chunks
                    SET state = %s, finalized_at = %s
                    WHERE id = %s AND state = %s
                    RETURNING id
                """, (
                    ChunkState.FINALIZED.value,
                    datetime.now(timezone.utc),
                    chunk_id,
                    ChunkState.PENDING_REVIEW.value  # Only update if pending
                ))

                if not cur.fetchone():
                    # Check if chunk exists but wrong state
                    cur.execute("SELECT state FROM narrative_chunks WHERE id = %s", (chunk_id,))
                    result = cur.fetchone()
                    if not result:
                        raise ValueError(f"Chunk {chunk_id} not found")
                    else:
                        raise ValueError(
                            f"Chunk {chunk_id} cannot be accepted (current state: {result[0]})"
                        )

                # Get previous chunk (N-1) to trigger embedding
                cur.execute("""
                    SELECT id, state, raw_text
                    FROM narrative_chunks
                    WHERE id < %s
                    ORDER BY id DESC
                    LIMIT 1
                """, (chunk_id,))

                previous_chunk = cur.fetchone()
                embedding_triggered = False
                embedding_job_id = None

                if previous_chunk:
                    prev_id, prev_state, prev_text = previous_chunk

                    # Only generate embeddings if not already done
                    if prev_state == ChunkState.FINALIZED.value:
                        embedding_job_id = self._trigger_embedding_generation(prev_id)
                        embedding_triggered = True

                        # Mark as embedding in progress
                        cur.execute("""
                            UPDATE narrative_chunks
                            SET state = %s
                            WHERE id = %s
                        """, (ChunkState.EMBEDDED.value, prev_id))

                logger.info(f"Accepted chunk {chunk_id}, embedding triggered: {embedding_triggered}")

                return ChunkAcceptResponse(
                    chunk_id=chunk_id,
                    state=ChunkState.FINALIZED,
                    previous_chunk_embedded=embedding_triggered,
                    embedding_job_id=embedding_job_id
                )

    def reject_chunk(self, chunk_id: int, session_id: str, action: str) -> ChunkRejectResponse:
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
                cur.execute("""
                    SELECT state, regeneration_count
                    FROM narrative_chunks
                    WHERE id = %s
                """, (chunk_id,))

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
                    regeneration_count=regen_count
                )

                if action == "regenerate":
                    # Increment regeneration counter
                    cur.execute("""
                        UPDATE narrative_chunks
                        SET regeneration_count = regeneration_count + 1,
                            state = %s
                        WHERE id = %s
                        RETURNING regeneration_count
                    """, (ChunkState.PENDING_REVIEW.value, chunk_id))

                    new_count = cur.fetchone()[0]
                    response.regeneration_count = new_count
                    logger.info(f"Chunk {chunk_id} marked for regeneration (attempt {new_count})")

                elif action == "edit_previous":
                    # Enable editing of previous user input
                    response.edit_enabled = True
                    logger.info(f"Chunk {chunk_id} rejected, edit previous enabled")

                return response

    def edit_previous_input(self, chunk_id: int, new_user_input: str, session_id: str) -> EditPreviousResponse:
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
                cur.execute("""
                    SELECT id, state, raw_text
                    FROM narrative_chunks
                    WHERE id = %s
                """, (prev_chunk_id,))

                prev_chunk = cur.fetchone()
                if not prev_chunk:
                    raise ValueError(f"Previous chunk not found for chunk {chunk_id}")

                prev_id, prev_state, old_text = prev_chunk

                # Ensure previous chunk isn't finalized
                if prev_state == ChunkState.FINALIZED.value:
                    raise ValueError(f"Cannot edit finalized chunk {prev_id}")

                # Update the user's previous input
                cur.execute("""
                    UPDATE narrative_chunks
                    SET raw_text = %s,
                        state = %s
                    WHERE id = %s
                """, (new_user_input, ChunkState.DRAFT.value, prev_id))

                # Mark current Storyteller chunk for regeneration
                cur.execute("""
                    UPDATE narrative_chunks
                    SET state = %s,
                        regeneration_count = regeneration_count + 1
                    WHERE id = %s
                """, (ChunkState.PENDING_REVIEW.value, chunk_id))

                logger.info(f"Updated user input in chunk {prev_id}, triggering regeneration of {chunk_id}")

                return EditPreviousResponse(
                    previous_chunk_id=prev_id,
                    updated=True,
                    new_generation_triggered=True
                )

    def _trigger_embedding_generation(self, chunk_id: int) -> Optional[str]:
        """
        Trigger embedding generation for a finalized chunk.

        Args:
            chunk_id: The chunk to generate embeddings for

        Returns:
            Job ID if async, None if synchronous
        """
        try:
            # Load settings to get embedding configuration
            settings_path = Path(__file__).parent.parent.parent / "settings.json"
            with settings_path.open() as f:
                settings = json.load(f)

            # Get the appropriate embedding model from settings
            embedding_config = settings.get("Agent Settings", {}).get("MEMNON", {}).get("embedding", {})
            models = embedding_config.get("models", {})

            # Find active model
            active_model = None
            for model_name, model_config in models.items():
                if model_config.get("is_active", False):
                    active_model = model_name
                    break

            if not active_model:
                logger.warning("No active embedding model found in settings - using default")
                active_model = "inf-retriever-v1-1.5b"  # Best performing model from IR testing

            # Security: Validate inputs before subprocess call
            if not isinstance(chunk_id, int) or chunk_id <= 0:
                raise ValueError(f"Invalid chunk_id: {chunk_id}")

            if not VALID_MODEL_PATTERN.match(active_model):
                raise ValueError(
                    f"Invalid model name: {active_model}. "
                    f"Model names must contain only alphanumeric characters, hyphens, dots, and underscores."
                )

            # Security: dbname already validated in __init__

            # Run embedding generation script
            # TODO: Make async with FastAPI BackgroundTasks or Celery to avoid blocking
            result = subprocess.run([
                "python", "scripts/regenerate_embeddings.py",
                "--chunk", str(chunk_id),  # Safe: validated as positive int
                "--model", active_model,    # Safe: validated with regex
                "--database", self.dbname   # Safe: validated in __init__
            ], capture_output=True, text=True, timeout=300)  # 5 min timeout

            if result.returncode == 0:
                # Mark chunk as embedded
                with get_connection(self.dbname) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE narrative_chunks
                            SET embedding_generated_at = %s
                            WHERE id = %s
                        """, (datetime.now(timezone.utc), chunk_id))

                logger.info(f"Successfully generated embeddings for chunk {chunk_id}")
                return f"embed_{chunk_id}_{datetime.now().timestamp()}"
            else:
                logger.error(f"Embedding generation failed for chunk {chunk_id}: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Error triggering embedding generation: {e}")
            return None

    def get_chunk_states(self, start_chunk: int, end_chunk: int) -> List[Dict[str, Any]]:
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
                cur.execute("""
                    SELECT id, state, finalized_at, embedding_generated_at, regeneration_count
                    FROM narrative_chunks
                    WHERE id BETWEEN %s AND %s
                    ORDER BY id
                """, (start_chunk, end_chunk))

                return [dict(row) for row in cur.fetchall()]


# Create a singleton instance for the default database
default_workflow = ChunkWorkflow()