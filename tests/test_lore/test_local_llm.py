"""
Unit tests for local_llm.py

Tests the semantic delegation pattern where LORE formats requests
for the LLM but never attempts understanding itself.
"""

import pytest
from pathlib import Path
import sys
from unittest.mock import Mock, MagicMock, patch
import json
import requests

# Add nexus module to path
nexus_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(nexus_root))

from nexus.agents.lore.utils.local_llm import (
    _extract_final_channel_text,
    _has_complete_retrieval_query_set,
    _parse_structured_json_text,
    _sanitize_retrieval_queries,
    LocalLLMManager,
    NarrativeAnalysis,
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


class TestNarrativeAnalysis:
    """Test narrative analysis delegation to LLM."""

    def test_narrative_analysis_model_structure(self):
        """Test the NarrativeAnalysis Pydantic model."""
        analysis = NarrativeAnalysis(
            characters=["Alex", "Pete"],
            locations=["The Badlands"],
            context_type="action",
            entities_for_retrieval=["Wraith", "Rustborn"],
            confidence_score=0.85,
        )

        assert len(analysis.characters) == 2
        assert analysis.context_type == "action"
        assert analysis.confidence_score == 0.85

        # Test serialization
        json_data = analysis.model_dump()
        assert json_data["characters"] == ["Alex", "Pete"]

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_analyze_narrative_context_method_exists(self, settings, system_prompt):
        """Test that analyze_narrative_context method exists and delegates."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            manager = LocalLLMManager(settings, system_prompt=system_prompt)

            # Method should exist
            assert hasattr(manager, "analyze_narrative_context")
            assert callable(getattr(manager, "analyze_narrative_context"))

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_analyze_delegates_to_llm(self, settings, system_prompt):
        """Test that narrative analysis is delegated to LLM via HTTP."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            with patch("nexus.agents.lore.utils.local_llm.requests.post") as mock_post:
                # Mock connection check
                mock_get.return_value.status_code = 200

                # Mock LLM response
                mock_llm_response = MagicMock()
                mock_llm_response.status_code = 200
                mock_llm_response.json.return_value = {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "characters": ["Alex"],
                                        "locations": ["Night City"],
                                        "themes": ["betrayal"],
                                    }
                                )
                            }
                        }
                    ]
                }
                mock_post.return_value = mock_llm_response

                manager = LocalLLMManager(settings, system_prompt=system_prompt)

                # Call narrative analysis
                warm_slice = [{"id": 1, "text": "Alex walked through Night City"}]
                result = manager.analyze_narrative_context(
                    warm_slice, "What should Alex do next?"
                )

                # Should have called the LLM API
                mock_post.assert_called()

                # Should return parsed result
                assert isinstance(result, dict)


class TestQueryGeneration:
    """Test natural language query generation."""

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_generate_retrieval_queries_exists(self, settings, system_prompt):
        """Test that query generation method exists."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            manager = LocalLLMManager(settings, system_prompt=system_prompt)

            # Method should exist
            assert hasattr(manager, "generate_retrieval_queries")
            assert callable(getattr(manager, "generate_retrieval_queries"))

    def test_sanitize_retrieval_queries_rejects_model_chatter(self):
        """Meta reasoning and prompt echoes should not become MEMNON queries."""
        queries = _sanitize_retrieval_queries(
            [
                "<|channel|>analysis<|message|>The user wants retrieval queries",
                "We need to output exactly 3-5 lines.",
                "1. Mara Vey debt history with the Archivum",
                "- Past events at the Verdigris Scriptorium",
                "Query 3: Hollow Choir obligation conflict",
                "Mara Vey debt history with the Archivum",
            ]
        )

        assert queries == [
            "Mara Vey debt history with the Archivum",
            "Past events at the Verdigris Scriptorium",
            "Hollow Choir obligation conflict",
        ]

    def test_final_channel_text_feeds_query_sanitizer(self):
        """Leaked analysis-channel text should be discarded when final text exists."""
        raw = (
            "<|channel|>analysis<|message|>"
            "We need to generate 3-5 retrieval queries.\n"
            "<|channel|>final<|message|>\n"
            "1. Mara Vey debt history with the Archivum\n"
            "2. Past events at the Verdigris Scriptorium\n"
            "3. Hollow Choir obligation conflict"
        )
        final_text = _extract_final_channel_text(raw)
        queries = _sanitize_retrieval_queries(final_text.splitlines())

        assert queries == [
            "Mara Vey debt history with the Archivum",
            "Past events at the Verdigris Scriptorium",
            "Hollow Choir obligation conflict",
        ]

    def test_sanitize_retrieval_queries_rejects_structured_planner_leaks(self):
        """Structured SQL/planner leakage should not become a MEMNON query."""
        queries = _sanitize_retrieval_queries(
            [
                '{"action":"sql","sql":"SELECT * FROM events ..."}',
                "Character relationships and interactions",
                "Background info on key entities",
                "Lantern Court trapdoor history",
            ]
        )

        assert queries == ["Lantern Court trapdoor history"]

    def test_sanitize_retrieval_queries_rejects_instruction_and_quote_junk(self):
        """Live local models can leak instructions or malformed quote fragments."""
        queries = _sanitize_retrieval_queries(
            [
                "Make sure each line is a query phrase. No bullet points.",
                "We must output exactly 3-5 lines, no numbering or bullets. Let's produce 4 queries.",
                "But need 3-5 queries. Provide maybe four lines.",
                "We'll produce something like:",
                "So there is a scene where someone maybe climbs a dry pump throat.",
                "History of locations (maybe Mercy Flue, ledger, Archivum).",
                "Background information on key entities (Mercy Flue, ledger, Archivist).",
                "Past events at",
                "Past events at Lantern Lantern...",
                'Ganrow?" "stated*" "delay',
                'Sella" "clause splinter" history of location "Rema',
                'history of "Lantern Court" alliance with "Remainder Chamber"',
                "Sella sour bite Remainder Chamber poisoning",
                "Lantern Court healer living remainder",
                "East Span Crown wardline pursuit",
            ]
        )

        assert queries == [
            'history of "Lantern Court" alliance with "Remainder Chamber"',
            "Sella sour bite Remainder Chamber poisoning",
            "Lantern Court healer living remainder",
            "East Span Crown wardline pursuit",
        ]

    def test_sanitize_retrieval_queries_rejects_live_keyword_stutter(self):
        """Live local models can emit keyword stutter instead of useful queries."""
        queries = _sanitize_retrieval_queries(
            [
                "Character relationships and interactions among them.",
                "Thus we can propose queries like:",
                'Orrel "misdirect" inspectors inspector misdirection tactics',
                "front front the drains laundry?",
                "Orrel ledger ledgers ledgers",
                "Orrel misdirect inspectors through laundry chaos",
                "Lantern Court laundry crate inspector search",
                "Ledger concealment near the service hatch",
            ]
        )

        assert queries == [
            "Orrel misdirect inspectors through laundry chaos",
            "Lantern Court laundry crate inspector search",
            "Ledger concealment near the service hatch",
        ]

    def test_retrieval_query_set_requires_three_queries(self):
        """Structured output should fall back when too few valid queries survive."""
        assert not _has_complete_retrieval_query_set(["Sella sour bite"])
        assert _has_complete_retrieval_query_set(
            [
                "Sella sour bite Remainder Chamber poisoning",
                "Lantern Court healer living remainder",
                "East Span Crown wardline pursuit",
            ]
        )

    def test_sanitize_retrieval_queries_keeps_specific_generic_openers(self):
        """Specific entity/location queries should survive generic-looking openers."""
        queries = _sanitize_retrieval_queries(
            [
                "Background information on key entities involved in the Lantern Court conspiracy",
                "History of locations: Verdigris Scriptorium fire timeline",
                "History of locations around Lantern Court and Door Six",
            ]
        )

        assert queries == [
            "Background information on key entities involved in the Lantern Court conspiracy",
            "History of locations: Verdigris Scriptorium fire timeline",
            "History of locations around Lantern Court and Door Six",
        ]

    def test_parse_structured_json_text_uses_final_channel_json(self):
        """Structured fallback parsing should recover JSON from leaked transcripts."""
        raw = (
            "<|channel|>analysis<|message|>"
            "We need to decide whether to promote.\n"
            "<|channel|>final<|message|>"
            '{"promote": false}<|end|>'
        )

        assert _parse_structured_json_text(raw) == {"promote": False}

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_queries_are_natural_language(self, settings, system_prompt):
        """Test that queries are natural language, not keyword soup."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            with patch("nexus.agents.lore.utils.local_llm.requests.post") as mock_post:
                # Mock connection check
                mock_get.return_value.status_code = 200

                # Mock query generation response
                mock_llm_response = MagicMock()
                mock_llm_response.status_code = 200
                mock_llm_response.json.return_value = {
                    "choices": [
                        {
                            "message": {
                                "content": "What happened when Victor betrayed Alex?\nTell me about the Dynacorp conspiracy."
                            }
                        }
                    ]
                }
                mock_post.return_value = mock_llm_response

                manager = LocalLLMManager(settings, system_prompt=system_prompt)

                # Generate queries
                analysis = {
                    "characters": ["Victor"],
                    "locations": [],
                    "entities_for_retrieval": ["Dynacorp"],
                    "context_type": "dialogue",
                }
                queries = manager.generate_retrieval_queries(
                    analysis, "What happened with Victor?"
                )

                # Should call LLM
                mock_post.assert_called()

                # Should return natural language queries
                assert isinstance(queries, list)
                if len(queries) > 0:
                    # Queries should be sentences, not keywords
                    for query in queries:
                        assert isinstance(query, str)
                        # Natural language has multiple words
                        assert len(query.split()) > 2


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
            assert hasattr(manager, "analyze_narrative_context")  # Delegates to LLM
            assert hasattr(manager, "generate_retrieval_queries")  # Delegates to LLM

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

    @patch("nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE", False)
    def test_invalid_llm_response_handling(self, settings, system_prompt):
        """Test handling of malformed LLM responses."""
        with patch("nexus.agents.lore.utils.local_llm.requests.get") as mock_get:
            with patch("nexus.agents.lore.utils.local_llm.requests.post") as mock_post:
                # Mock connection check
                mock_get.return_value.status_code = 200

                # Mock invalid response
                mock_llm_response = MagicMock()
                mock_llm_response.status_code = 200
                mock_llm_response.json.return_value = {
                    "choices": [{"message": {"content": "Not valid JSON"}}]
                }
                mock_post.return_value = mock_llm_response

                manager = LocalLLMManager(settings, system_prompt=system_prompt)

                # Should handle invalid JSON gracefully
                warm_slice = [{"id": 1, "text": "Test narrative chunk"}]
                result = manager.analyze_narrative_context(
                    warm_slice, "Test user input"
                )

                # Should return some result (even if empty/default)
                assert result is not None
