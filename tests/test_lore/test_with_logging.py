#!/usr/bin/env python
"""
Test LORE with comprehensive logging to capture all reasoning traces.

This test captures:
1. The exact prompts sent to the LLM
2. The full LLM responses (including reasoning traces)
3. Token counts and budget calculations
4. All intermediate processing steps
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add nexus to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexus.agents.lore.utils.local_llm import LocalLLMManager
from nexus.agents.lore.utils.token_budget import TokenBudgetManager
from nexus.agents.lore.utils.chunk_operations import calculate_chunk_tokens


def setup_logging():
    """Configure comprehensive logging to file and console."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(__file__).parent / f"lore_test_log_{timestamp}.txt"
    
    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    # Set specific loggers to appropriate levels
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("AsyncWebsocketHandler").setLevel(logging.INFO)
    
    return log_file


def test_narrative_analysis(manager, logger):
    """Test narrative analysis with full logging."""
    logger.info("="*60)
    logger.info("TEST: NARRATIVE CONTEXT ANALYSIS")
    logger.info("="*60)
    
    logger.info(f"LM Studio connected: {manager.is_available()}")
    logger.info(f"Loaded model: {manager.loaded_model_id}")
    
    # Test narrative chunk (from corpus)
    warm_slice = [{
        'id': 114,
        'raw_text': """Victor's hand trembled as he reached for the neural interface. 
"Alex, I'm sorry," he whispered, his voice barely audible over the hum of the 
Dynacorp machinery. "They have my daughter. I had no choice." The betrayal hung 
between them like a blade, sharper than any physical weapon. Alex's augmented 
eyes flickered with data streams, processing the magnitude of this deception.""",
        'world_time': '2073-10-15T22:30:00',
        'episode': 'S01E08',
        'scene': 114
    }]
    
    user_input = "What led to Victor betraying Alex? Tell me about their relationship."
    
    logger.info(f"\nUSER INPUT: {user_input}")
    logger.info(f"WARM SLICE: Chunk {warm_slice[0]['id']} ({len(warm_slice[0]['raw_text'])} chars)")
    logger.info(f"NARRATIVE EXCERPT: {warm_slice[0]['raw_text'][:200]}...")
    
    # Analyze narrative context
    logger.info("\n--- Calling analyze_narrative_context ---")
    analysis = manager.analyze_narrative_context(warm_slice, user_input)
    
    logger.info("\nANALYSIS RESULT:")
    logger.info(json.dumps(analysis, indent=2))
    
    return analysis


def test_query_generation(manager, analysis, user_input, logger):
    """Test natural language query generation."""
    logger.info("\n" + "="*60)
    logger.info("TEST: NATURAL LANGUAGE QUERY GENERATION")
    logger.info("="*60)
    
    logger.info(f"\nCONTEXT ANALYSIS INPUT:")
    logger.info(f"  Characters: {analysis.get('characters', [])}")
    logger.info(f"  Entities: {analysis.get('entities_for_retrieval', [])}")
    logger.info(f"  Context Type: {analysis.get('context_type', 'unknown')}")
    
    # Generate retrieval queries
    logger.info("\n--- Calling generate_retrieval_queries ---")
    queries = manager.generate_retrieval_queries(analysis, user_input)
    
    logger.info(f"\nGENERATED QUERIES ({len(queries)} total):")
    for i, query in enumerate(queries, 1):
        logger.info(f"  {i}. {query}")
    
    return queries


def test_token_budget(settings, logger):
    """Test token budget calculation."""
    logger.info("\n" + "="*60)
    logger.info("TEST: TOKEN BUDGET MANAGEMENT")
    logger.info("="*60)
    
    budget_manager = TokenBudgetManager(settings)
    
    user_input = "What led to Victor betraying Alex? Tell me about their relationship."
    
    # Calculate tokens
    user_tokens = calculate_chunk_tokens(user_input)
    logger.info(f"\nUSER INPUT TOKENS: {user_tokens}")
    logger.info(f"USER INPUT: '{user_input}'")
    
    # Calculate budget
    budget = budget_manager.calculate_budget(user_input, apex_model="gpt-4o")
    
    logger.info("\nTOKEN BUDGET ALLOCATION:")
    logger.info(f"  Apex Window: {budget['apex_window']:,} tokens")
    logger.info(f"  System Prompt: {budget['system_prompt']:,} tokens")
    logger.info(f"  User Input: {budget['user_input']:,} tokens")
    logger.info(f"  Total Available: {budget['total_available']:,} tokens")
    logger.info(f"\nCONTEXT ALLOCATIONS:")
    logger.info(f"  Warm Slice: {budget['warm_slice']:,} tokens")
    logger.info(f"  Structured: {budget['structured']:,} tokens")
    logger.info(f"  Augmentation: {budget['augmentation']:,} tokens")
    
    # Calculate percentages
    total_context = budget['warm_slice'] + budget['structured'] + budget['augmentation']
    if total_context > 0:
        logger.info(f"\nPERCENTAGE BREAKDOWN:")
        logger.info(f"  Warm Slice: {budget['warm_slice']/total_context*100:.1f}%")
        logger.info(f"  Structured: {budget['structured']/total_context*100:.1f}%")
        logger.info(f"  Augmentation: {budget['augmentation']/total_context*100:.1f}%")
    
    return budget


def test_semantic_delegation(manager, logger):
    """Test pure semantic delegation pattern."""
    logger.info("\n" + "="*60)
    logger.info("TEST: SEMANTIC DELEGATION PATTERN")
    logger.info("="*60)
    
    # Complex semantic task that LORE delegates entirely to LLM
    prompt = """
You are analyzing a cyberpunk narrative. The user asks: "What are the implications 
of Victor's betrayal for the power dynamics in Night City?"

Based on the following narrative context:
- Victor betrayed Alex to protect his daughter, who was held by Dynacorp
- Alex has neural augmentations and data-streaming eyes
- The scene takes place amidst Dynacorp machinery

Provide:
1. Key themes to explore (betrayal, family, corporate control)
2. Power dynamics at play
3. Character motivations
4. Suggested narrative directions

Respond in natural language with your analysis.
"""
    
    logger.info(f"\nSEMANTIC PROMPT SENT TO LLM:")
    logger.info(prompt)
    
    logger.info("\n--- Calling LLM with semantic task ---")
    response = manager.query(prompt, temperature=0.7, max_tokens=800)
    
    logger.info(f"\nLLM SEMANTIC RESPONSE:")
    logger.info(response)
    
    return response


def main():
    """Run all tests with comprehensive logging."""
    # Setup logging
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("="*60)
    logger.info("LORE COMPREHENSIVE TEST WITH LOGGING")
    logger.info(f"Log file: {log_file}")
    logger.info("="*60)
    
    # Load settings
    settings_path = Path(__file__).parent / "lore_test_settings.json"
    with open(settings_path) as f:
        settings = json.load(f)
    
    try:
        # Initialize manager once (SDK singleton)
        manager = LocalLLMManager(settings)
        logger.info(f"Manager initialized with model: {manager.loaded_model_id}")
        
        # Run tests
        analysis = test_narrative_analysis(manager, logger)
        user_input = "What led to Victor betraying Alex?"
        queries = test_query_generation(manager, analysis, user_input, logger)
        budget = test_token_budget(settings, logger)
        semantic_response = test_semantic_delegation(manager, logger)
        
        logger.info("\n" + "="*60)
        logger.info("ALL TESTS COMPLETED SUCCESSFULLY")
        logger.info(f"Full log saved to: {log_file}")
        logger.info("="*60)
        
        print(f"\n✅ Test log saved to: {log_file}")
        print(f"   View with: cat {log_file}")
        
    except Exception as e:
        logger.error(f"TEST FAILED: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()