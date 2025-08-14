"""
Turn Cycle Phase Implementations for LORE

Handles the execution of individual turn cycle phases.
"""

import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

try:
    from .turn_context import TurnContext, TurnPhase
except ImportError:
    # If relative import fails, try absolute
    from nexus.agents.lore.utils.turn_context import TurnContext, TurnPhase

try:
    from nexus.agents.memnon.utils.query_analysis import QueryAnalyzer
    MEMNON_ANALYZER_AVAILABLE = True
except ImportError:
    MEMNON_ANALYZER_AVAILABLE = False
    logger.warning("MEMNON QueryAnalyzer not available - using fallback query generation")

logger = logging.getLogger("nexus.lore.turn_cycle")


class TurnCycleManager:
    """Manages the execution of turn cycle phases"""
    
    def __init__(self, lore_agent):
        """
        Initialize with reference to parent LORE agent.
        
        Args:
            lore_agent: Reference to the parent LORE instance
        """
        self.lore = lore_agent
        self.settings = lore_agent.settings
        
        # Initialize MEMNON's QueryAnalyzer if available
        self.query_analyzer = None
        if MEMNON_ANALYZER_AVAILABLE:
            memnon_settings = self.settings.get("Agent Settings", {}).get("MEMNON", {})
            self.query_analyzer = QueryAnalyzer(memnon_settings)
    
    async def process_user_input(self, turn_context: TurnContext):
        """
        Phase 1: Process and validate user input.
        
        Args:
            turn_context: Current turn context
        """
        logger.debug("Processing user input...")
        
        # Calculate token budget
        if self.lore.token_manager:
            turn_context.token_counts = self.lore.token_manager.calculate_budget(
                turn_context.user_input
            )
        
        # Store processed input
        turn_context.phase_states["user_input"] = {
            "processed": True,
            "token_count": turn_context.token_counts.get("user_input", 0)
        }
    
    async def perform_warm_analysis(self, turn_context: TurnContext):
        """
        Phase 2: Analyze recent narrative context.
        
        Args:
            turn_context: Current turn context
        """
        logger.debug("Performing warm analysis...")
        
        # Get recent narrative chunks from database if MEMNON available
        if self.lore.memnon:
            try:
                # Get chunk parameters from settings
                chunk_params = self.settings.get("Agent Settings", {}).get("LORE", {}).get("chunk_parameters", {})
                initial_chunks = chunk_params.get("warm_slice_initial", 10)
                
                # Get most recent chunks directly
                recent_chunks = self.lore.memnon.get_recent_chunks(limit=initial_chunks)
                turn_context.warm_slice = recent_chunks.get("results", [])
                
                logger.info(f"Retrieved {len(turn_context.warm_slice)} recent chunks for warm slice")
            except Exception as e:
                logger.error(f"Failed to retrieve warm slice: {e}")
                turn_context.warm_slice = []
        
        # Analyze with local LLM - REQUIRED for LORE to function
        if not self.lore.llm_manager or not self.lore.llm_manager.is_available():
            raise RuntimeError("FATAL: Local LLM is required for warm analysis. "
                             "LORE cannot function without semantic understanding. "
                             "Ensure LM Studio is running with a model loaded.")
        
        if not turn_context.warm_slice:
            raise RuntimeError("FATAL: No warm slice chunks retrieved. "
                             "Cannot analyze narrative context without recent chunks. "
                             "Check database connection and chunk retrieval.")
        
        analysis = self.lore.llm_manager.analyze_narrative_context(
            turn_context.warm_slice,
            turn_context.user_input
        )
        
        turn_context.phase_states["warm_analysis"] = {
            "analysis": analysis,
            "chunk_count": len(turn_context.warm_slice)
        }
    
    async def query_entity_states(self, turn_context: TurnContext):
        """
        Phase 3: Query for entity states.
        
        Args:
            turn_context: Current turn context
        """
        logger.debug("Querying entity states...")
        
        if not self.lore.memnon:
            logger.warning("MEMNON not available for entity queries")
            turn_context.entity_data = {"characters": [], "locations": []}
            return
        
        # Extract entity mentions from warm analysis
        analysis = turn_context.phase_states.get("warm_analysis", {}).get("analysis", {})
        
        # Query for specific characters if identified
        characters = []
        if isinstance(analysis, dict):
            for char_name in analysis.get("characters", [])[:3]:
                try:
                    char_data = self.lore.memnon._query_structured_data(
                        char_name, "characters", limit=1
                    )
                    if char_data:
                        characters.extend(char_data)
                except Exception as e:
                    logger.error(f"Failed to query character {char_name}: {e}")
        
        # Query for locations
        locations = []
        if isinstance(analysis, dict):
            for loc_name in analysis.get("locations", [])[:2]:
                try:
                    loc_data = self.lore.memnon._query_structured_data(
                        loc_name, "places", limit=1
                    )
                    if loc_data:
                        locations.extend(loc_data)
                except Exception as e:
                    logger.error(f"Failed to query location {loc_name}: {e}")
        
        turn_context.entity_data = {
            "characters": characters,
            "locations": locations
        }
        
        turn_context.phase_states["entity_state"] = {
            "characters_found": len(characters),
            "locations_found": len(locations)
        }
    
    async def execute_deep_queries(self, turn_context: TurnContext):
        """
        Phase 4: Execute deep memory queries.
        
        LLM generates retrieval queries based on narrative context,
        then MEMNON's QueryAnalyzer classifies them for optimal search.
        """
        logger.debug("Executing deep queries...")
        
        if not self.lore.memnon:
            logger.warning("MEMNON not available for deep queries")
            return
        
        # Step 1: LLM generates retrieval queries based on narrative analysis
        if not self.lore.llm_manager or not self.lore.llm_manager.is_available():
            raise RuntimeError("FATAL: LLM is required for deep query generation. "
                             "Cannot generate meaningful retrieval queries without semantic understanding.")
        
        analysis = turn_context.phase_states.get("warm_analysis", {}).get("analysis", {})
        if not isinstance(analysis, dict):
            raise RuntimeError("FATAL: Warm analysis failed or returned invalid data. "
                             "Cannot proceed with deep queries without narrative context analysis.")
        
        # LLM generates queries from scratch based on what information 
        # would help continue the narrative
        llm_queries = self.lore.llm_manager.generate_retrieval_queries(
            analysis,
            turn_context.user_input
        )
        
        if not llm_queries:
            raise RuntimeError("FATAL: LLM failed to generate any retrieval queries. "
                             "This should not happen - check LLM configuration.")
        
        # Step 2: Classify each generated query with MEMNON's QueryAnalyzer
        queries = []
        for q_text in llm_queries:
            query_type = "general"
            if self.query_analyzer:
                query_info = self.query_analyzer.analyze_query(q_text)
                query_type = query_info.get("type", "general")
                logger.debug(f"Query '{q_text[:50]}...' classified as '{query_type}'")
            
            queries.append({
                "text": q_text,
                "type": query_type,
                "source": "llm_generated"
            })
        
        # Step 3: Execute queries with proper SearchManager configuration
        all_results = []
        query_type_counts = {}
        
        for query_obj in queries[:5]:  # Limit to 5 queries
            try:
                # MEMNON's SearchManager uses the query type internally
                # to adjust vector/text weights for optimal results
                results = self.lore.memnon.query_memory(
                    query=query_obj["text"],
                    k=15,  # Get more results since we'll deduplicate
                    use_hybrid=True
                )
                
                # Track query types for logging
                query_type = query_obj["type"]
                query_type_counts[query_type] = query_type_counts.get(query_type, 0) + 1
                
                # Tag results with query metadata
                for result in results.get("results", []):
                    result["query_type"] = query_type
                    result["query_source"] = query_obj["source"]
                
                all_results.extend(results.get("results", []))
                
            except Exception as e:
                logger.error(f"Query failed for '{query_obj['text'][:50]}...': {e}")
        
        # Store unique results, preserving highest scores
        seen_ids = {}
        for result in all_results:
            chunk_id = result.get("id")
            if chunk_id:
                if chunk_id not in seen_ids or result.get("score", 0) > seen_ids[chunk_id].get("score", 0):
                    seen_ids[chunk_id] = result
        
        # Sort by score and take top results
        unique_results = sorted(
            seen_ids.values(),
            key=lambda x: x.get("score", 0),
            reverse=True
        )[:30]  # Keep top 30 for augmentation
        
        turn_context.retrieved_passages = unique_results
        turn_context.phase_states["deep_queries"] = {
            "queries_executed": len(queries),
            "query_types": query_type_counts,
            "results_retrieved": len(unique_results)
        }
        
        logger.info(f"Deep queries complete: {len(queries)} queries executed "
                   f"({query_type_counts}), {len(unique_results)} unique results retrieved")
    
    # DEPRECATED: Cold Distillation phase removed - cross-encoders handle reranking
    
    async def assemble_context_payload(self, turn_context: TurnContext):
        """
        Phase 5: Assemble final context payload.
        
        Args:
            turn_context: Current turn context
        """
        logger.debug("Assembling context payload...")
        
        # Build the context payload
        turn_context.context_payload = {
            "user_input": turn_context.user_input,
            "warm_slice": {
                "chunks": turn_context.warm_slice,
                "token_count": turn_context.token_counts.get("warm_slice", 0)
            },
            "entity_data": turn_context.entity_data,
            "retrieved_passages": {
                "results": turn_context.retrieved_passages,
                "token_count": turn_context.token_counts.get("augmentation", 0)
            },
            "metadata": {
                "turn_id": turn_context.turn_id,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # Calculate utilization
        if self.lore.token_manager:
            utilization = self.lore.token_manager.calculate_utilization(
                turn_context.token_counts
            )
        else:
            utilization = 0
        
        turn_context.phase_states["payload_assembly"] = {
            "total_tokens_used": sum([
                turn_context.token_counts.get("user_input", 0),
                turn_context.token_counts.get("warm_slice", 0),
                turn_context.token_counts.get("structured", 0),
                turn_context.token_counts.get("augmentation", 0)
            ]),
            "utilization_percentage": utilization
        }
        
        logger.info(f"Context payload assembled: {utilization:.1f}% budget utilization")
    
    async def call_apex_ai(self, turn_context: TurnContext) -> str:
        """
        Phase 6: Call Apex AI for narrative generation.
        
        Args:
            turn_context: Current turn context
            
        Returns:
            Generated narrative response
        """
        logger.debug("Calling Apex AI...")
        
        if not self.lore.logon:
            logger.error("LOGON not available for API calls")
            return "Error: API communication unavailable"
        
        try:
            response = self.lore.logon.generate_narrative(turn_context.context_payload)
            turn_context.apex_response = response.content
            
            turn_context.phase_states["apex_generation"] = {
                "success": True,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "model": response.model
            }
            
            return response.content
            
        except Exception as e:
            logger.error(f"Apex AI call failed: {e}")
            turn_context.phase_states["apex_generation"] = {
                "success": False,
                "error": str(e)
            }
            return f"Error generating narrative: {str(e)}"
    
    async def integrate_response(self, turn_context: TurnContext, response: str):
        """
        Phase 7: Integrate Apex response and update state.
        
        Args:
            turn_context: Current turn context
            response: Generated narrative response
        """
        logger.debug("Integrating response...")
        
        # In a full implementation, this would:
        # 1. Parse the response for state updates
        # 2. Update character states via PSYCHE
        # 3. Update world state via GAIA  
        # 4. Store the new narrative chunk in database
        
        # For now, just log the completion
        turn_context.phase_states["integration"] = {
            "response_length": len(response),
            "integration_complete": True
        }
        
        # Store narrative chunk if MEMNON available
        if self.lore.memnon and response:
            try:
                # This would normally use a proper method to store the chunk
                logger.info("Would store new narrative chunk to database")
            except Exception as e:
                logger.error(f"Failed to store narrative chunk: {e}")