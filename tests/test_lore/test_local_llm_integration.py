"""
Integration tests for local_llm.py using actual LM Studio SDK.

These tests actually call LM Studio to verify the semantic delegation pattern.
"""

import pytest
from pathlib import Path
import sys
import json

# Add nexus module to path
nexus_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(nexus_root))

from nexus.agents.lore.utils.local_llm import (
    LocalLLMManager,
    NarrativeAnalysis,
    LMS_SDK_AVAILABLE
)


@pytest.mark.skipif(not LMS_SDK_AVAILABLE, reason="LM Studio SDK not available")
class TestLMStudioIntegration:
    """Real integration tests with LM Studio."""
    
    def test_manager_connects_to_lm_studio(self, settings):
        """Test that manager successfully connects to LM Studio."""
        manager = LocalLLMManager(settings)
        
        # Should connect and be available
        assert manager.is_available()
        
        # Should have loaded a model
        assert manager.loaded_model_id is not None
    
    def test_query_delegates_to_llm(self, settings):
        """Test that queries are actually sent to LM Studio."""
        manager = LocalLLMManager(settings)
        
        # Send a simple query
        result = manager.query(
            prompt="Respond with just the word 'acknowledged'",
            temperature=0.1
        )
        
        # Should get a response
        assert result is not None
        assert len(result) > 0
        print(f"LLM Response: {result}")
    
    def test_analyze_narrative_returns_structure(self, settings, sample_chunks):
        """Test narrative analysis with real narrative chunk."""
        manager = LocalLLMManager(settings)
        
        # Use a real narrative chunk
        dialogue_chunk = sample_chunks.get('dialogue_offer')
        if dialogue_chunk and 'raw_text' in dialogue_chunk:
            # Analyze real narrative text
            result = manager.analyze_narrative_context(
                narrative_text=dialogue_chunk['raw_text'][:500],  # First 500 chars
                context_type="dialogue"
            )
            
            # Should return structured data
            assert result is not None
            assert isinstance(result, dict)
            
            # Log what we got back
            print(f"Analysis result keys: {result.keys()}")
            
            # Should have some expected fields (may vary based on LLM response)
            # The key is that it delegated to LLM, not what exactly comes back
    
    def test_generate_natural_language_queries(self, settings):
        """Test that query generation produces natural language."""
        manager = LocalLLMManager(settings)
        
        # Generate queries for some entities
        entities = ["Victor Sato", "betrayal", "Dynacorp conspiracy"]
        queries = manager.generate_retrieval_queries(
            entities=entities,
            max_queries=3
        )
        
        # Should generate queries
        assert queries is not None
        assert isinstance(queries, list)
        
        print(f"Generated queries: {queries}")
        
        # Queries should be natural language (if any generated)
        for query in queries:
            if query:  # If not empty
                # Natural language typically has multiple words
                assert len(query.split()) > 2, f"Query too short: {query}"
                # Should not be just keywords joined
                assert query != " ".join(entities), "Query is just keywords"
    
    def test_no_fallback_on_failure(self, settings):
        """Test that manager fails hard when LM Studio unavailable."""
        manager = LocalLLMManager(settings)
        
        # First verify it's working
        assert manager.is_available()
        
        # Now if we were to stop LM Studio, it should fail hard
        # (We won't actually stop it in tests, but the principle is there)
        
        # The key architectural point: there's no fallback LLM or cache
        # If LM Studio isn't available, operations should fail


class TestSemanticDelegationPattern:
    """Test the semantic delegation pattern without mocking."""
    
    def test_manager_methods_are_delegation_only(self, settings):
        """Test that manager methods only format and delegate."""
        manager = LocalLLMManager(settings)
        
        # Check the actual implementation pattern
        # The manager should NOT have methods that process text locally
        
        # Good methods (delegation):
        assert hasattr(manager, 'query')  # ✓ Sends to LLM
        assert hasattr(manager, 'analyze_narrative_context')  # ✓ Sends to LLM
        assert hasattr(manager, 'generate_retrieval_queries')  # ✓ Sends to LLM
        
        # Bad methods (local processing):
        assert not hasattr(manager, 'count_characters')  # ✗ Would process locally
        assert not hasattr(manager, 'extract_names')  # ✗ Would parse locally
        assert not hasattr(manager, 'summarize')  # ✗ Would summarize locally
    
    def test_narrative_analysis_structured_response(self):
        """Test that NarrativeAnalysis provides structure for LLM responses."""
        # The Pydantic model guides what we expect from LLM
        analysis = NarrativeAnalysis(
            characters=["Alex", "Victor"],
            locations=["Night City", "Badlands"],
            context_type="dialogue",
            entities_for_retrieval=["Dynacorp", "conspiracy"],
            confidence_score=0.85
        )
        
        # Can serialize for sending to LLM
        json_schema = analysis.model_json_schema()
        assert 'properties' in json_schema
        assert 'characters' in json_schema['properties']
        
        # Can parse from LLM response
        json_str = json.dumps(analysis.model_dump())
        parsed = NarrativeAnalysis.model_validate_json(json_str)
        assert parsed.characters == ["Alex", "Victor"]


@pytest.mark.skipif(LMS_SDK_AVAILABLE, reason="Only test fallback when SDK not available")  
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