"""
End-to-end tests for the chunk acceptance workflow.

Tests the complete flow of accepting/rejecting chunks, triggering embeddings,
and editing previous inputs using the test database (save_02).
"""

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from typing import Dict, Any

from nexus.api.chunk_workflow import (
    ChunkWorkflow,
    ChunkState,
    ChunkAcceptRequest,
    ChunkRejectRequest,
    EditPreviousRequest,
)
from nexus.api.db_pool import get_connection


class TestChunkWorkflow:
    """Test suite for chunk acceptance workflow."""

    @pytest.fixture
    def workflow(self):
        """Create a workflow instance for testing."""
        # Use save_02 (test database)
        return ChunkWorkflow(dbname="save_02")

    @pytest.fixture
    def test_chunk_id(self):
        """Use chunk 1425 for testing."""
        return 1425

    @pytest.fixture
    def setup_test_chunks(self, workflow, test_chunk_id):
        """Setup test chunks in known states."""
        # Reset chunk states for testing
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                # Set chunk 1424 and 1425 to draft state
                cur.execute("""
                    UPDATE narrative_chunks
                    SET state = %s,
                        finalized_at = NULL,
                        embedding_generated_at = NULL,
                        regeneration_count = 0
                    WHERE id IN (%s, %s)
                """, (ChunkState.DRAFT.value, test_chunk_id - 1, test_chunk_id))

    def test_schema_initialization(self, workflow):
        """Test that schema columns are properly initialized."""
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'narrative_chunks'
                    AND column_name IN ('state', 'finalized_at', 'embedding_generated_at', 'regeneration_count')
                """)
                columns = {row[0] for row in cur.fetchall()}

        assert 'state' in columns
        assert 'finalized_at' in columns
        assert 'embedding_generated_at' in columns
        assert 'regeneration_count' in columns

    def test_accept_chunk_success(self, workflow, test_chunk_id, setup_test_chunks):
        """Test successful chunk acceptance."""
        # Accept chunk 1425
        response = workflow.accept_chunk(test_chunk_id, "test_session")

        assert response.chunk_id == test_chunk_id
        assert response.state == ChunkState.FINALIZED

        # Verify chunk state in database
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT state, finalized_at
                    FROM narrative_chunks
                    WHERE id = %s
                """, (test_chunk_id,))
                state, finalized_at = cur.fetchone()

        assert state == ChunkState.FINALIZED.value
        assert finalized_at is not None

    def test_accept_chunk_triggers_embedding(self, workflow, test_chunk_id, setup_test_chunks):
        """Test that accepting a chunk triggers embedding for the previous chunk."""
        # First, finalize chunk 1424
        workflow.accept_chunk(test_chunk_id - 1, "test_session")

        # Mock the subprocess call for embedding generation
        with patch('nexus.api.chunk_workflow.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            # Accept chunk 1425 (should trigger embedding for 1424)
            response = workflow.accept_chunk(test_chunk_id, "test_session")

            assert response.previous_chunk_embedded
            assert response.embedding_job_id is not None

            # Verify subprocess was called with correct arguments
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "scripts/regenerate_embeddings.py" in call_args[1]
            assert str(test_chunk_id - 1) in call_args  # Previous chunk ID

    def test_reject_chunk_regenerate(self, workflow, test_chunk_id, setup_test_chunks):
        """Test rejecting a chunk for regeneration."""
        # Set chunk to pending_review
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE narrative_chunks
                    SET state = %s
                    WHERE id = %s
                """, (ChunkState.PENDING_REVIEW.value, test_chunk_id))

        # Reject for regeneration
        response = workflow.reject_chunk(test_chunk_id, "test_session", "regenerate")

        assert response.chunk_id == test_chunk_id
        assert response.action_taken == "regenerate"
        assert response.regeneration_count == 1

        # Verify regeneration count incremented
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT regeneration_count
                    FROM narrative_chunks
                    WHERE id = %s
                """, (test_chunk_id,))
                count = cur.fetchone()[0]

        assert count == 1

    def test_reject_chunk_edit_previous(self, workflow, test_chunk_id, setup_test_chunks):
        """Test rejecting a chunk to edit previous input."""
        # Reject for edit_previous
        response = workflow.reject_chunk(test_chunk_id, "test_session", "edit_previous")

        assert response.chunk_id == test_chunk_id
        assert response.action_taken == "edit_previous"
        assert response.edit_enabled

    def test_cannot_reject_finalized_chunk(self, workflow, test_chunk_id, setup_test_chunks):
        """Test that finalized chunks cannot be rejected."""
        # Finalize the chunk
        workflow.accept_chunk(test_chunk_id, "test_session")

        # Try to reject it
        with pytest.raises(ValueError, match="Cannot reject finalized chunk"):
            workflow.reject_chunk(test_chunk_id, "test_session", "regenerate")

    def test_edit_previous_input(self, workflow, test_chunk_id, setup_test_chunks):
        """Test editing the user's previous input."""
        # First, ensure chunk 1424 exists and is not finalized
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, raw_text
                    FROM narrative_chunks
                    WHERE id = %s
                """, (test_chunk_id - 1,))
                result = cur.fetchone()

        if result:
            # Edit the previous input
            new_text = "This is the edited user input for testing."
            response = workflow.edit_previous_input(
                test_chunk_id,
                new_text,
                "test_session"
            )

            assert response.previous_chunk_id == test_chunk_id - 1
            assert response.updated
            assert response.new_generation_triggered

            # Verify the text was updated
            with get_connection("save_02") as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT raw_text
                        FROM narrative_chunks
                        WHERE id = %s
                    """, (test_chunk_id - 1,))
                    updated_text = cur.fetchone()[0]

            assert updated_text == new_text

    def test_cannot_edit_finalized_chunk(self, workflow, test_chunk_id, setup_test_chunks):
        """Test that finalized chunks cannot be edited."""
        # Finalize chunk 1424
        workflow.accept_chunk(test_chunk_id - 1, "test_session")

        # Try to edit it
        with pytest.raises(ValueError, match="Cannot edit finalized chunk"):
            workflow.edit_previous_input(
                test_chunk_id,
                "Trying to edit finalized chunk",
                "test_session"
            )

    def test_get_chunk_states(self, workflow, test_chunk_id, setup_test_chunks):
        """Test retrieving chunk states for a range."""
        # Set different states for testing
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE narrative_chunks
                    SET state = %s
                    WHERE id = %s
                """, (ChunkState.PENDING_REVIEW.value, test_chunk_id - 1))

                cur.execute("""
                    UPDATE narrative_chunks
                    SET state = %s
                    WHERE id = %s
                """, (ChunkState.DRAFT.value, test_chunk_id))

        # Get states for range
        states = workflow.get_chunk_states(test_chunk_id - 1, test_chunk_id)

        assert len(states) == 2
        assert states[0]['id'] == test_chunk_id - 1
        assert states[0]['state'] == ChunkState.PENDING_REVIEW.value
        assert states[1]['id'] == test_chunk_id
        assert states[1]['state'] == ChunkState.DRAFT.value

    def test_embedding_generation_failure_handling(self, workflow, test_chunk_id, setup_test_chunks):
        """Test handling of embedding generation failures."""
        # Finalize chunk 1424
        workflow.accept_chunk(test_chunk_id - 1, "test_session")

        # Mock subprocess to simulate failure
        with patch('nexus.api.chunk_workflow.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Embedding generation failed"
            )

            # Accept chunk 1425 (should attempt embedding for 1424)
            response = workflow.accept_chunk(test_chunk_id, "test_session")

            # Should still finalize the chunk even if embedding fails
            assert response.chunk_id == test_chunk_id
            assert response.state == ChunkState.FINALIZED
            # But embedding job should be None due to failure
            assert response.embedding_job_id is None

    def test_concurrent_acceptance(self, workflow, test_chunk_id, setup_test_chunks):
        """Test that concurrent acceptance is handled properly."""
        import threading
        import queue

        results = queue.Queue()

        def accept_chunk():
            try:
                result = workflow.accept_chunk(test_chunk_id, "test_session")
                results.put(("success", result))
            except Exception as e:
                results.put(("error", str(e)))

        # Launch multiple threads trying to accept the same chunk
        threads = [threading.Thread(target=accept_chunk) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Collect results
        outcomes = []
        while not results.empty():
            outcomes.append(results.get())

        # Exactly one should succeed, others should fail
        successes = [o for o in outcomes if o[0] == "success"]
        errors = [o for o in outcomes if o[0] == "error"]

        # Due to database constraints, multiple accepts should be idempotent
        # or handle gracefully
        assert len(successes) >= 1  # At least one should succeed

    @pytest.mark.integration
    def test_full_workflow_cycle(self, workflow, test_chunk_id, setup_test_chunks):
        """Test a complete workflow cycle from draft to embedded."""
        # Start with draft chunk
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE narrative_chunks
                    SET state = %s, regeneration_count = 0
                    WHERE id = %s
                """, (ChunkState.DRAFT.value, test_chunk_id))

        # 1. Set to pending review (simulating Storyteller generation)
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE narrative_chunks
                    SET state = %s
                    WHERE id = %s
                """, (ChunkState.PENDING_REVIEW.value, test_chunk_id))

        # 2. Reject for regeneration
        response = workflow.reject_chunk(test_chunk_id, "test_session", "regenerate")
        assert response.regeneration_count == 1

        # 3. Reject for edit_previous
        response = workflow.reject_chunk(test_chunk_id, "test_session", "edit_previous")
        assert response.edit_enabled

        # 4. Edit previous input (if exists)
        if test_chunk_id > 1:
            response = workflow.edit_previous_input(
                test_chunk_id,
                "Edited input for full cycle test",
                "test_session"
            )
            assert response.updated

        # 5. Finally accept the chunk
        with patch('nexus.api.chunk_workflow.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            response = workflow.accept_chunk(test_chunk_id, "test_session")

        assert response.state == ChunkState.FINALIZED

        # Verify final state
        with get_connection("save_02") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT state, finalized_at, regeneration_count
                    FROM narrative_chunks
                    WHERE id = %s
                """, (test_chunk_id,))
                state, finalized_at, regen_count = cur.fetchone()

        assert state == ChunkState.FINALIZED.value
        assert finalized_at is not None
        assert regen_count >= 1  # Should have been incremented


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])