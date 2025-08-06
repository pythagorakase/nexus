#!/usr/bin/env python3
"""
Test the continuous temporal search implementation directly.
This script tests both the temporal intent analysis and the actual search functionality.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("temporal_test")

# Import the continuous temporal search module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nexus.agents.memnon.utils.continuous_temporal_search import analyze_temporal_intent, execute_time_aware_search

# Import other required utilities
from nexus.agents.memnon.utils.db_access import execute_hybrid_search
from sentence_transformers import SentenceTransformer

# Load settings
def load_settings() -> Dict[str, Any]:
    """Load settings from settings.json file."""
    try:
        settings_path = os.environ.get("NEXUS_SETTINGS_PATH", "settings.json")
        with open(settings_path, "r") as f:
            settings = json.load(f)
            logger.info(f"Loaded settings from {settings_path}")
            return settings
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return {}

# Global settings
SETTINGS = load_settings()
MEMNON_SETTINGS = SETTINGS.get("Agent Settings", {}).get("MEMNON", {})

# Database URL
DB_URL = MEMNON_SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")

def test_temporal_intent_analysis():
    """Test the continuous temporal intent analysis function with various queries."""
    test_queries = [
        # Early references
        "What happened at the beginning of the story?",
        "Tell me about Alex's first meeting with Dr. Nyati",
        "How did Alex initially react to the neural implant?",
        "What was the original plan for the mission?",
        "What happened before Alex met Emilia?",
        
        # Mid-narrative references
        "What happened while Alex was unconscious?",
        "During the raid on the corporate tower, what was Emilia doing?",
        "What was discussed at the meeting with Dr. Nyati?",
        "Following the incident at Neon Bay, how did the team regroup?",
        
        # Recent references
        "What's the current status of Alex's neural implant?",
        "How has Emilia's attitude changed recently?",
        "What was the outcome of the most recent mission?",
        "What are Alex's latest thoughts about Dr. Nyati?",
        "Tell me about the team's current plan",
        
        # Non-temporal references
        "Who is Dr. Nyati?",
        "Tell me about the Combat Zone",
        "What are neural implants?",
        "Describe Emilia's personality",
        "How does the neural network technology work?"
    ]
    
    print("\n=== TEMPORAL INTENT ANALYSIS ===")
    for query in test_queries:
        intent_score = analyze_temporal_intent(query)
        temporal_category = "Early" if intent_score < 0.4 else "Recent" if intent_score > 0.6 else "Neutral"
        print(f"{intent_score:.2f} ({temporal_category}):\t{query}")

def get_embedding_for_query(query_text: str, model_name: str) -> List[float]:
    """Generate an embedding for the query text using the specified model."""
    # Get model configuration
    model_configs = MEMNON_SETTINGS.get("models", {})
    if model_name not in model_configs:
        raise ValueError(f"Model {model_name} not found in settings")
    
    model_config = model_configs[model_name]
    local_path = model_config.get("local_path")
    remote_path = model_config.get("remote_path")
    
    model_path = local_path or remote_path
    if not model_path:
        raise ValueError(f"No path specified for model {model_name}")
    
    # Load model
    model = SentenceTransformer(model_path)
    
    # Generate embedding
    embedding = model.encode(query_text)
    
    # Convert to Python list (in case it's a numpy array)
    return embedding.tolist()

def test_hybrid_search_with_and_without_temporal():
    """Test hybrid search with and without temporal boosting."""
    # Test queries with temporal aspects
    test_queries = [
        "What happened at the beginning of Alex's journey?",
        "What's the most recent development with Emilia?",
        "How did Alex first meet Dr. Nyati?",
        "What is the current status of the team's mission?"
    ]
    
    # Get target model from settings
    hybrid_config = MEMNON_SETTINGS.get("retrieval", {}).get("hybrid_search", {})
    target_model = hybrid_config.get("target_model", "bge-large")
    
    # Set up boosting factors for testing
    boosting_factors = [0.0, 0.3, 0.7]
    
    # Test each query
    for query in test_queries:
        # Generate embedding for the query
        query_embedding = get_embedding_for_query(query, target_model)
        
        # Analyze temporal intent
        intent_score = analyze_temporal_intent(query)
        temporal_category = "Early" if intent_score < 0.4 else "Recent" if intent_score > 0.6 else "Neutral"
        
        print(f"\n=== TESTING QUERY: {query} ===")
        print(f"Temporal intent: {intent_score:.2f} ({temporal_category})")
        
        # Baseline: Standard hybrid search without temporal
        print("\n--- BASELINE: Standard Hybrid Search ---")
        baseline_results = execute_hybrid_search(
            db_url=DB_URL,
            query_text=query,
            query_embedding=query_embedding,
            model_key=target_model,
            vector_weight=0.6,
            text_weight=0.4,
            top_k=5
        )
        
        # Print top 5 results
        for i, result in enumerate(baseline_results[:5]):
            source = ', '.join([f"{k}: {v:.3f}" for k, v in result.items() if k in ['score', 'vector_score', 'text_score']])
            metadata = result.get('metadata', {})
            season = metadata.get('season', 'N/A')
            episode = metadata.get('episode', 'N/A')
            scene = metadata.get('scene_number', 'N/A')
            location = metadata.get('scene_id', '')
            text = result.get('text', '')[:100] + '...' if len(result.get('text', '')) > 100 else result.get('text', '')
            print(f"{i+1}. [S{season}E{episode}_{scene}] {source}\n   {text}")
        
        # Test with each boosting factor
        for factor in boosting_factors:
            print(f"\n--- TEMPORAL SEARCH (Boost Factor: {factor}) ---")
            
            temporal_results = execute_time_aware_search(
                db_url=DB_URL,
                query_text=query,
                query_embedding=query_embedding,
                model_key=target_model,
                vector_weight=0.6,
                text_weight=0.4,
                temporal_boost_factor=factor,
                top_k=5
            )
            
            # Print top 5 results
            for i, result in enumerate(temporal_results[:5]):
                source = ', '.join([f"{k}: {v:.3f}" for k, v in result.items() if k in ['score', 'original_score', 'vector_score', 'text_score']])
                metadata = result.get('metadata', {})
                season = metadata.get('season', 'N/A')
                episode = metadata.get('episode', 'N/A')
                scene = metadata.get('scene_number', 'N/A')
                position = result.get('temporal_position', 'N/A')
                text = result.get('text', '')[:100] + '...' if len(result.get('text', '')) > 100 else result.get('text', '')
                # Format position based on type
                if isinstance(position, float):
                    position_str = f"{position:.2f}"
                else:
                    position_str = str(position)
                    
                print(f"{i+1}. [S{season}E{episode}_{scene}] (Pos: {position_str}) {source}\n   {text}")
        
        print("=" * 80)

if __name__ == "__main__":
    print("Testing continuous temporal search implementation")
    
    # Test temporal intent analysis
    test_temporal_intent_analysis()
    
    # Test hybrid search with and without temporal boosting
    test_hybrid_search_with_and_without_temporal()