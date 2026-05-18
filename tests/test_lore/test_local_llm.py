"""
Unit tests for local_llm.py

Tests the semantic delegation pattern where LORE formats requests
for the LLM but never attempts understanding itself.
"""

import pytest
from pathlib import Path
import sys
from unittest.mock import Mock, MagicMock, patch
import requests

# Add nexus module to path
nexus_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(nexus_root))

from nexus.agents.lore.utils.local_llm import (
    _parse_structured_json_text,
    LocalLLMManager,
    LMS_SDK_AVAILABLE,
)


class TestLocalLLMInitialization:
    """Test LLM manager initialization and configuration."""

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_initialization_basic(self, settings, system_prompt):
        """Test basic initialization with settings."""
        # Mock the connection check
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            manager = LocalLLMManager(settings, system_prompt=system_prompt)

            assert manager.settings == settings
            expected_base = (
                settings.get("Agent Settings", {})
                .get("LORE", {})
                .get("llm", {})
                .get("lmstudio_url", "http://localhost:1234/v1")
            )
            expected_model = (
                settings.get("Agent Settings", {})
                .get("LORE", {})
                .get("llm", {})
                .get("model_name", "local-model")
            )
            assert manager.base_url == expected_base
            assert manager.model_name == expected_model

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_hard_failure_no_lm_studio(self, settings, system_prompt):
        """Test HARD FAILURE when LM Studio is not available (NO FALLBACKS)."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            # Mock connection failure
            mock_get.side_effect = requests.exceptions.ConnectionError(
                "Connection refused"
            )

            # Should fail hard - no graceful fallback
            with pytest.raises(RuntimeError, match="Cannot connect to LM Studio API"):
                LocalLLMManager(settings, system_prompt=system_prompt)

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_is_available_method(self, settings, system_prompt):
        """Test the is_available method."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            manager = LocalLLMManager(settings, system_prompt=system_prompt)

            # Test availability check
            assert manager.is_available() == True


class TestStructuredParsing:
    """Test local-model response cleanup used by structured queries."""

    def test_parse_structured_json_text_uses_final_channel_json(self):
        """Structured fallback parsing should recover JSON from leaked transcripts."""
        raw = (
            "<|channel|>analysis<|message|>"
            "We need to decide whether to promote.\n"
            "<|channel|>final<|message|>"
            '{"promote": false}<|end|>'
        )

        assert _parse_structured_json_text(raw) == {"promote": False}


class TestSemanticDelegation:
    """Test that LORE never attempts semantic understanding itself."""

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_no_hardcoded_understanding(self, settings, system_prompt):
        """Test that the manager doesn't have hardcoded narrative understanding."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            manager = LocalLLMManager(settings, system_prompt=system_prompt)

            # Manager should not have methods that imply local understanding
            assert not hasattr(manager, "extract_characters")
            assert not hasattr(manager, "understand_plot")
            assert not hasattr(manager, "interpret_dialogue")
            assert not hasattr(manager, "calculate_sentiment")

            # Should have delegation methods
            assert hasattr(manager, "query")  # Generic LLM query
            assert not hasattr(manager, "analyze_narrative_context")
            assert not hasattr(manager, "generate_retrieval_queries")

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_query_method_is_generic(self, settings, system_prompt):
        """Test that the query method is generic delegation, not specific understanding."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            with patch("nexus.agents.lore.utils.local_llm.requests.post") as mock_post:
                # Mock connection check
                mock_get.return_value.status_code = 200

                # Mock LLM response
                mock_llm_response = MagicMock()
                mock_llm_response.status_code = 200
                mock_llm_response.json.return_value = {
                    "choices": [{"message": {"content": "LLM response"}}]
                }
                mock_post.return_value = mock_llm_response

                manager = LocalLLMManager(settings, system_prompt=system_prompt)

                # Query method should accept any prompt
                result = manager.query("Any semantic task", temperature=0.5)

                # Should delegate to LLM
                mock_post.assert_called()
                assert result is not None


class TestErrorHandling:
    """Test error handling and failure modes."""

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_connection_failure_hard_error(self, settings, system_prompt):
        """Test that connection failures cause hard errors (NO FALLBACKS)."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            # First call succeeds (initialization)
            # Second call fails (runtime)
            mock_get.side_effect = [
                MagicMock(status_code=200),
                requests.exceptions.ConnectionError("LM Studio disconnected"),
            ]

            manager = LocalLLMManager(settings, system_prompt=system_prompt)

            # Runtime connection failure should not be silently handled
            with pytest.raises(Exception):
                manager.is_available()
