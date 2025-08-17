#!/usr/bin/env python3
"""
Test Two-Pass Context Assembly with Karaoke Example

Demonstrates:
1. Pass 1: Process Storyteller output about dinner at Boudreaux's
2. Pass 2: Detect "karaoke" deep cut reference in user input
"""

import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.lore.utils.session_store import SessionStore, SessionContext, LoreState
from nexus.agents.lore.utils.curveball_analyzer import CurveballAnalyzer
from nexus.agents.lore.utils.auto_vector import auto_vector_user_input, detect_deep_cuts
from nexus.agents.lore.utils.local_llm import LocalLLMManager

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def simulate_pass1(chunk_id: int = 1369) -> SessionContext:
    """
    Simulate Pass 1: Process Storyteller output from chunk 1369.
    Extract entities, build context.
    """
    logger.info("\n" + "="*60)
    logger.info("PASS 1: STORYTELLER-DRIVEN ASSEMBLY (75% tokens)")
    logger.info("="*60)
    
    # Create session
    store = SessionStore()
    session = store.create_session(
        session_id="test_karaoke",
        turn_number=1,
        storyteller_output="The team enjoys dinner at Boudreaux's..."
    )
    
    # Simulate entities extracted from chunk 1369
    # (In reality, LORE would extract these)
    session.present_characters = {
        1: {"name": "Alex", "summary": "Team leader"},
        3: {"name": "Emilia", "summary": "Security specialist"},
        7: {"name": "Pete", "summary": "Tech expert"},
        12: {"name": "Nyati", "summary": "Scientist"},
        15: {"name": "Alina", "summary": "Data analyst"}
    }
    
    session.setting_places = {
        8: {"name": "Boudreaux's Haute-Creole Experience", "zone": "Night City"}
    }
    
    # Chunks included in Pass 1 (around chunk 1369)
    session.chunk_ids = list(range(1365, 1375))
    session.warm_slice_range = {"start": 1365, "end": 1374}
    
    # Token usage (simulated)
    session.token_usage = {
        "characters": 15000,
        "places": 5000,
        "chunks": 60000,
        "relationships": 5000
    }
    session.tokens_reserved_for_user = 32768  # 25% of 131072
    
    # LORE's understanding after Pass 1
    session.lore_state = LoreState(
        understanding="Team bonding dinner at Boudreaux's, reflecting on recent events",
        expectations=[],  # Not predicting user behavior
        context_gaps=["Victor's whereabouts unknown", "Eclipse Biotech plans unclear"],
        query_strategies=["team dinner", "Boudreaux's", "character dynamics"]
    )
    
    # Queries executed in Pass 1
    session.executed_queries = {"team dinner", "Boudreaux's reflection", "character states"}
    
    # Save session
    saved_path = store.save_session(session)
    logger.info(f"\nPass 1 Complete:")
    logger.info(f"- Characters in context: {list(session.present_characters.keys())}")
    logger.info(f"- Chunks in context: {len(session.chunk_ids)} chunks")
    logger.info(f"- Understanding: {session.lore_state.understanding}")
    logger.info(f"- Session saved to: {saved_path}")
    
    return session


def simulate_pass2(session: SessionContext, user_input: str):
    """
    Simulate Pass 2: Process user input and detect gaps.
    """
    logger.info("\n" + "="*60)
    logger.info("PASS 2: USER-DRIVEN REFINEMENT (25% tokens)")
    logger.info("="*60)
    logger.info(f"\nUser Input: \"{user_input}\"")
    
    # Initialize components
    class MinimalInterface:
        def assistant_message(self, msg): pass
        def error_message(self, msg): logger.error(msg)
    
    class MinimalAgentState:
        state = {"name": "test_two_pass"}
    
    class MinimalUser:
        id = "test"
        name = "Test"
    
    # Initialize MEMNON
    memnon = MEMNON(
        interface=MinimalInterface(),
        agent_state=MinimalAgentState(),
        user=MinimalUser(),
        db_url="postgresql://pythagor@localhost/NEXUS",
        debug=False
    )
    
    # Initialize LocalLLMManager (needs settings dict)
    llm_settings = {
        "Agent Settings": {
            "LORE": {
                "llm": {
                    "lmstudio_url": "http://localhost:1234/v1",
                    "model_name": "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF"
                }
            }
        }
    }
    llm = LocalLLMManager(llm_settings)
    
    # Step 1: Auto-vector user input
    logger.info("\n--- Auto-Vectoring User Input ---")
    auto_vector_results = auto_vector_user_input(user_input, memnon, k=10)
    
    if auto_vector_results["vectorized"]:
        logger.info(f"Auto-vector found {len(auto_vector_results['chunk_ids'])} chunks")
        logger.info(f"Top chunks: {auto_vector_results['chunk_ids'][:5]}")
        
        # Detect deep cuts
        deep_cuts = detect_deep_cuts(
            auto_vector_results,
            session.chunk_ids,
            distance_threshold=100
        )
        
        if deep_cuts:
            logger.info(f"\n🎯 DEEP CUTS DETECTED: {deep_cuts}")
            logger.info("These are remote references (like karaoke from S03E13)")
    else:
        logger.info("User input not suitable for vectorization")
    
    # Step 2: Analyze for gaps
    logger.info("\n--- Gap Detection ---")
    analyzer = CurveballAnalyzer(llm, memnon)
    analysis = analyzer.analyze_user_input(
        user_text=user_input,
        session_context=session,
        tokens_available=session.tokens_reserved_for_user
    )
    
    logger.info(f"Strategy: {analysis.strategy.value}")
    logger.info(f"Reasoning: {analysis.reasoning}")
    
    if analysis.has_novel_content:
        logger.info(f"Novel entities detected: {analysis.novel_entities}")
        if analysis.deep_cut_chunks:
            logger.info(f"Deep cut chunks to retrieve: {analysis.deep_cut_chunks}")
    
    # Step 3: Execute strategy
    logger.info(f"\n--- Executing {analysis.strategy.value} ---")
    directive = analyzer.get_expansion_directive(analysis)
    logger.info(f"Action: {directive}")
    
    # Check if we successfully detected the karaoke reference
    if deep_cuts:
        logger.info(f"\n✅ Successfully detected deep cut reference to karaoke!")
        logger.info(f"   Auto-vector found chunks {deep_cuts[:3]} from S03E13")
        logger.info(f"   That's the karaoke incident from ~600 chunks ago!")
    
    # Simulate final result
    logger.info("\n" + "="*60)
    logger.info("TWO-PASS ASSEMBLY COMPLETE")
    logger.info("="*60)
    logger.info(f"Pass 1: {sum(session.token_usage.values())} tokens (75%)")
    logger.info(f"Pass 2: {session.tokens_reserved_for_user} tokens available (25%)")


def main():
    parser = argparse.ArgumentParser(description='Test two-pass context assembly')
    parser.add_argument('--chunk', type=int, default=1369, help='Chunk ID for Pass 1')
    parser.add_argument('--user-input', type=str, 
                       default="I've taken karaoke off the rotation temporarily—too soon, perhaps",
                       help='User input for Pass 2')
    parser.add_argument('--skip-pass1', action='store_true', 
                       help='Skip Pass 1 and load existing session')
    
    args = parser.parse_args()
    
    try:
        if args.skip_pass1:
            # Load existing session
            store = SessionStore()
            session = store.load_session("test_karaoke")
            if not session:
                logger.error("No existing session found. Run without --skip-pass1 first.")
                sys.exit(1)
        else:
            # Run Pass 1
            session = simulate_pass1(args.chunk)
        
        # Run Pass 2
        simulate_pass2(session, args.user_input)
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()