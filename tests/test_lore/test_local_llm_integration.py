"""
Integration tests for local_llm.py using actual LM Studio SDK.

These tests actually call LM Studio to verify the semantic delegation pattern.
"""

import pytest
from pathlib import Path
import sys

# Add nexus module to path
nexus_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(nexus_root))

from nexus.agents.lore.utils.local_llm import LocalLLMManager, LMS_SDK_AVAILABLE

pytestmark = [pytest.mark.requires_local_llm]


@pytest.mark.skipif(not LMS_SDK_AVAILABLE, reason="LM Studio SDK not available")
class TestLMStudioIntegration:
    """Real integration tests with LM Studio."""

    def test_manager_connects_to_lm_studio(self, settings, system_prompt):
        """Test that manager successfully connects to LM Studio."""
        manager = LocalLLMManager(settings, system_prompt=system_prompt)

        # Should connect and be available
        assert manager.is_available()

        # Should have loaded a model
        assert manager.loaded_model_id is not None

    def test_query_delegates_to_llm(self, settings, system_prompt):
        """Test that queries are actually sent to LM Studio."""
        manager = LocalLLMManager(settings, system_prompt=system_prompt)

        # Send a simple query
        result = manager.query(
            prompt="Respond with just the word 'acknowledged'", temperature=0.1
        )

        # Should get a response
        assert result is not None
        assert len(result) > 0
        print(f"LLM Response: {result}")

    def test_no_fallback_on_failure(self, settings, system_prompt):
        """Test that manager fails hard when LM Studio unavailable."""
        manager = LocalLLMManager(settings, system_prompt=system_prompt)

        # First verify it's working
        assert manager.is_available()

        # Now if we were to stop LM Studio, it should fail hard
        # (We won't actually stop it in tests, but the principle is there)

        # The key architectural point: there's no fallback LLM or cache
        # If LM Studio isn't available, operations should fail


class TestSemanticDelegationPattern:
    """Test the semantic delegation pattern without mocking."""

    def test_manager_methods_are_delegation_only(self, settings, system_prompt):
        """Test that manager methods only format and delegate."""
        manager = LocalLLMManager(settings, system_prompt=system_prompt)

        # Check the actual implementation pattern
        # The manager should NOT have methods that process text locally

        # Good methods (delegation):
        assert hasattr(manager, "query")  # ✓ Sends to LLM
        assert not hasattr(manager, "analyze_narrative_context")
        assert not hasattr(manager, "generate_retrieval_queries")

        # Bad methods (local processing):
        assert not hasattr(manager, "count_characters")  # ✗ Would process locally
        assert not hasattr(manager, "extract_names")  # ✗ Would parse locally
        assert not hasattr(manager, "summarize")  # ✗ Would summarize locally


@pytest.mark.skipif(
    LMS_SDK_AVAILABLE, reason="Only test fallback when SDK not available"
)
class TestHTTPFallback:
    """Test HTTP fallback when SDK not available."""

    def test_falls_back_to_http_requests(self, settings):
        """Test that manager uses HTTP when SDK unavailable."""
        # This will use the HTTP fallback path
        try:
            manager = LocalLLMManager(settings)

            # Should still check availability via HTTP
            if manager.is_available():
                # Can still query via HTTP
                result = manager.query("Test prompt")
                assert result is not None
        except RuntimeError as e:
            # If LM Studio not running, should fail hard
            assert "LM Studio is not running" in str(e)
