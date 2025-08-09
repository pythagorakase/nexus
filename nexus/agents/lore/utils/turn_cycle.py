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
        
        # Analyze with local LLM if available
        if self.lore.llm_manager and self.lore.llm_manager.is_available():
            if turn_context.warm_slice:
                analysis = self.lore.llm_manager.analyze_narrative_context(
                    turn_context.warm_slice,
                    turn_context.user_input
                )
                turn_context.phase_states["warm_analysis"] = {
                    "analysis": analysis,
                    "chunk_count": len(turn_context.warm_slice)
                }
            else:
                turn_context.phase_states["warm_analysis"] = {
                    "analysis": {"characters": [], "locations": [], "context_type": "unknown"},
                    "chunk_count": 0
                }
        else:
            turn_context.phase_states["warm_analysis"] = {
                "analysis": "Warm analysis unavailable",
                "chunk_count": 0
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
        
        Args:
            turn_context: Current turn context
        """
        logger.debug("Executing deep queries...")
        
        if not self.lore.memnon:
            logger.warning("MEMNON not available for deep queries")
            return
        
        # Generate queries based on context analysis
        queries = []
        
        # Use LLM to generate queries if available
        if self.lore.llm_manager and self.lore.llm_manager.is_available():
            analysis = turn_context.phase_states.get("warm_analysis", {}).get("analysis", {})
            if isinstance(analysis, dict):
                queries = self.lore.llm_manager.generate_retrieval_queries(
                    analysis,
                    turn_context.user_input
                )
        else:
            # Fallback: just use user input
            queries = [turn_context.user_input] if turn_context.user_input else []
        
        # Execute queries
        all_results = []
        for query in queries[:3]:  # Limit to 3 queries
            try:
                results = self.lore.memnon.query_memory(
                    query=query,
                    k=10,
                    use_hybrid=True
                )
                all_results.extend(results.get("results", []))
            except Exception as e:
                logger.error(f"Query failed for '{query}': {e}")
        
        # Store unique results
        seen_ids = set()
        unique_results = []
        for result in all_results:
            chunk_id = result.get("id")
            if chunk_id and chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                unique_results.append(result)
        
        turn_context.retrieved_passages = unique_results
        turn_context.phase_states["deep_queries"] = {
            "queries_executed": len(queries),
            "results_retrieved": len(unique_results)
        }
    
    async def perform_cold_distillation(self, turn_context: TurnContext):
        """
        Phase 5: Distill retrieved information.
        
        Args:
            turn_context: Current turn context
        """
        logger.debug("Performing cold distillation...")
        
        # Sort retrieved passages by relevance score
        if turn_context.retrieved_passages:
            turn_context.retrieved_passages.sort(
                key=lambda x: x.get("score", 0),
                reverse=True
            )
            
            # Keep top passages based on token budget
            max_passages = 10
            turn_context.retrieved_passages = turn_context.retrieved_passages[:max_passages]
        
        turn_context.phase_states["cold_distillation"] = {
            "passages_retained": len(turn_context.retrieved_passages)
        }
    
    async def assemble_context_payload(self, turn_context: TurnContext):
        """
        Phase 6: Assemble final context payload.
        
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
        Phase 7: Call Apex AI for narrative generation.
        
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
        Phase 8: Integrate Apex response and update state.
        
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