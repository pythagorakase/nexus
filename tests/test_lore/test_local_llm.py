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
    LocalLLMManager,
    NarrativeAnalysis,
    LMS_SDK_AVAILABLE
)


class TestLocalLLMInitialization:
    """Test LLM manager initialization and configuration."""
    
    def test_initialization_basic(self, settings):
        """Test basic initialization with settings."""
        # Mock the connection check
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            manager = LocalLLMManager(settings)
            
            assert manager.settings == settings
            assert manager.base_url == "http://localhost:1234/v1"
            assert manager.model_name == "local-model"
    
    @patch('nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE', False)
    def test_hard_failure_no_lm_studio(self, settings):
        """Test HARD FAILURE when LM Studio is not available (NO FALLBACKS)."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            # Mock connection failure
            mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
            
            # Should fail hard - no graceful fallback
            with pytest.raises(RuntimeError, match="LM Studio is not running"):
                LocalLLMManager(settings)
    
    def test_is_available_method(self, settings):
        """Test the is_available method."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            manager = LocalLLMManager(settings)
            
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
            confidence_score=0.85
        )
        
        assert len(analysis.characters) == 2
        assert analysis.context_type == "action"
        assert analysis.confidence_score == 0.85
        
        # Test serialization
        json_data = analysis.model_dump()
        assert json_data["characters"] == ["Alex", "Pete"]
    
    def test_analyze_narrative_context_method_exists(self, settings):
        """Test that analyze_narrative_context method exists and delegates."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            manager = LocalLLMManager(settings)
            
            # Method should exist
            assert hasattr(manager, 'analyze_narrative_context')
            assert callable(getattr(manager, 'analyze_narrative_context'))
    
    @patch('nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE', False)
    def test_analyze_delegates_to_llm(self, settings):
        """Test that narrative analysis is delegated to LLM via HTTP."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            with patch('nexus.agents.lore.utils.local_llm.requests.post') as mock_post:
                # Mock connection check
                mock_get.return_value.status_code = 200
                
                # Mock LLM response
                mock_llm_response = MagicMock()
                mock_llm_response.status_code = 200
                mock_llm_response.json.return_value = {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "characters": ["Alex"],
                                "locations": ["Night City"],
                                "themes": ["betrayal"]
                            })
                        }
                    }]
                }
                mock_post.return_value = mock_llm_response
                
                manager = LocalLLMManager(settings)
                
                # Call narrative analysis
                result = manager.analyze_narrative_context(
                    "Alex walked through Night City",
                    context_type="exploration"
                )
                
                # Should have called the LLM API
                mock_post.assert_called()
                
                # Should return parsed result
                assert isinstance(result, dict)


class TestQueryGeneration:
    """Test natural language query generation."""
    
    def test_generate_retrieval_queries_exists(self, settings):
        """Test that query generation method exists."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            manager = LocalLLMManager(settings)
            
            # Method should exist
            assert hasattr(manager, 'generate_retrieval_queries')
            assert callable(getattr(manager, 'generate_retrieval_queries'))
    
    @patch('nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE', False)
    def test_queries_are_natural_language(self, settings):
        """Test that queries are natural language, not keyword soup."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            with patch('nexus.agents.lore.utils.local_llm.requests.post') as mock_post:
                # Mock connection check
                mock_get.return_value.status_code = 200
                
                # Mock query generation response
                mock_llm_response = MagicMock()
                mock_llm_response.status_code = 200
                mock_llm_response.json.return_value = {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "queries": [
                                    "What happened when Victor betrayed Alex?",
                                    "Tell me about the Dynacorp conspiracy"
                                ]
                            })
                        }
                    }]
                }
                mock_post.return_value = mock_llm_response
                
                manager = LocalLLMManager(settings)
                
                # Generate queries
                entities = ["Victor", "betrayal", "Dynacorp"]
                queries = manager.generate_retrieval_queries(entities, max_queries=5)
                
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
    
    def test_no_hardcoded_understanding(self, settings):
        """Test that the manager doesn't have hardcoded narrative understanding."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            manager = LocalLLMManager(settings)
            
            # Manager should not have methods that imply local understanding
            assert not hasattr(manager, 'extract_characters')
            assert not hasattr(manager, 'understand_plot')
            assert not hasattr(manager, 'interpret_dialogue')
            assert not hasattr(manager, 'calculate_sentiment')
            
            # Should have delegation methods
            assert hasattr(manager, 'query')  # Generic LLM query
            assert hasattr(manager, 'analyze_narrative_context')  # Delegates to LLM
            assert hasattr(manager, 'generate_retrieval_queries')  # Delegates to LLM
    
    def test_query_method_is_generic(self, settings):
        """Test that the query method is generic delegation, not specific understanding."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            with patch('nexus.agents.lore.utils.local_llm.requests.post') as mock_post:
                # Mock connection check
                mock_get.return_value.status_code = 200
                
                # Mock LLM response
                mock_llm_response = MagicMock()
                mock_llm_response.status_code = 200
                mock_llm_response.json.return_value = {
                    "choices": [{
                        "message": {"content": "LLM response"}
                    }]
                }
                mock_post.return_value = mock_llm_response
                
                manager = LocalLLMManager(settings)
                
                # Query method should accept any prompt
                result = manager.query("Any semantic task", temperature=0.5)
                
                # Should delegate to LLM
                mock_post.assert_called()
                assert result is not None


class TestErrorHandling:
    """Test error handling and failure modes."""
    
    @patch('nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE', False)
    def test_connection_failure_hard_error(self, settings):
        """Test that connection failures cause hard errors (NO FALLBACKS)."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            # First call succeeds (initialization)
            # Second call fails (runtime)
            mock_get.side_effect = [
                MagicMock(status_code=200),
                requests.exceptions.ConnectionError("LM Studio disconnected")
            ]
            
            manager = LocalLLMManager(settings)
            
            # Runtime connection failure should not be silently handled
            with pytest.raises(Exception):
                manager.is_available()
    
    @patch('nexus.agents.lore.utils.local_llm.LMS_SDK_AVAILABLE', False)
    def test_invalid_llm_response_handling(self, settings):
        """Test handling of malformed LLM responses."""
        with patch('nexus.agents.lore.utils.local_llm.requests.get') as mock_get:
            with patch('nexus.agents.lore.utils.local_llm.requests.post') as mock_post:
                # Mock connection check
                mock_get.return_value.status_code = 200
                
                # Mock invalid response
                mock_llm_response = MagicMock()
                mock_llm_response.status_code = 200
                mock_llm_response.json.return_value = {
                    "choices": [{
                        "message": {"content": "Not valid JSON"}
                    }]
                }
                mock_post.return_value = mock_llm_response
                
                manager = LocalLLMManager(settings)
                
                # Should handle invalid JSON gracefully
                result = manager.analyze_narrative_context("Test")
                
                # Should return some result (even if empty/default)
                assert result is not None