"""
LORE Agent - Central Orchestration Agent for NEXUS

LORE (Lore Operations & Retrieval Engine) is the sole intelligent agent in the NEXUS system.
It orchestrates all utility modules and assembles optimal context payloads for the Apex LLM.

Key Responsibilities:
1. Narrative State Analysis - Analyze current narrative moment for context needs
2. Utility Orchestration - Coordinate MEMNON, PSYCHE, NEMESIS, GAIA, and LOGON
3. Intelligent Context Assembly - Dynamically determine and balance information needs
4. Turn Cycle Management - Handle the complete turn sequence from user input to response

Usage Examples:
--------------
# Single retrieval directive for a specific chunk:
python -m nexus.agents.lore.lore "What happened to Victor?" --chunk 100

# Multiple retrieval directives for the same chunk:
python -m nexus.agents.lore.lore "Alex and Emilia relationship" "What happened to Victor?" "Information about The Silo" --chunk 100

# Debug mode to see SQL reasoning between queries:
python -m nexus.agents.lore.lore "Victor's current status" --chunk 888 --debug

# Keep model loaded after execution (for testing):
python -m nexus.agents.lore.lore "Eclipse Biotech corporate structure" --chunk 1247 --keep-model

# Debug mode with verbose logging:
python -m nexus.agents.lore.lore "Neural implant technology" --chunk 60 --debug

Note: The --chunk parameter is REQUIRED when providing retrieval directives.
Each directive gets 5 SQL queries by default (configurable via settings.json: Agent Settings > LORE > query_budget).
"""

import asyncio
import logging
import json
import time
from typing import Dict, Optional, Any, List, Union
from pathlib import Path

# Handle imports based on how the module is run
import sys
from pathlib import Path

# Add parent directories to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent.parent))

# Import utility modules
from utils.turn_context import TurnContext, TurnPhase
from utils.turn_cycle import TurnCycleManager
from utils.token_budget import TokenBudgetManager
from utils.local_llm import LocalLLMManager
from utils.model_manager import ModelManager
from logon_utility import LogonUtility

from nexus.memory import ContextMemoryManager

# Import MEMNON if available
try:
    from nexus.agents.memnon.memnon import MEMNON
    MEMNON_AVAILABLE = True
except ImportError:
    MEMNON_AVAILABLE = False
    logging.warning("MEMNON not available. Memory retrieval will be limited.")

# Configure logger
logger = logging.getLogger("nexus.lore")
qa_logger = logging.getLogger("nexus.lore.qa")


class LORE:
    """
    Central orchestration agent for the NEXUS system.
    Manages the complete turn cycle and coordinates all utility modules.
    """
    
    def __init__(
        self,
        settings_path: Optional[str] = None,
        debug: bool = False,
        enable_logon: bool = True,
    ):
        """
        Initialize LORE agent.
        
        Args:
            settings_path: Path to settings.json file
            debug: Enable debug logging
        """
        self.debug = debug
        self.settings = self._load_settings(settings_path)
        
        # Configure logging
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        
        # Initialize components
        self.memnon = None
        self.logon = None
        self.enable_logon = enable_logon
        self.llm_manager = None
        self.token_manager = None
        self.turn_manager = None
        self.memory_manager = None
        
        # Turn cycle state
        self.current_phase = TurnPhase.IDLE
        self.turn_context = None
        
        # Initialize utilities
        self._initialize_components()
        
        logger.info("LORE agent initialized successfully")
    
    def _load_settings(self, settings_path: Optional[str] = None) -> Dict[str, Any]:
        """Load settings from JSON file"""
        if not settings_path:
            settings_path = Path(__file__).parent.parent.parent.parent / "settings.json"
        
        self.settings_path = settings_path  # Store for later use
        
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                logger.info(f"Loaded settings from {settings_path}")
                return settings
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            # Return minimal default settings
            return {
                "Agent Settings": {
                    "LORE": {
                        "debug": True,
                        "llm": {
                            "lmstudio_url": "http://localhost:1234/v1",
                            "model_name": "local-model"
                        },
                        "token_budget": {
                            "apex_context_window": 200000,
                            "system_prompt_tokens": 5000,
                            "reserved_response_tokens": 4000
                        }
                    }
                },
                "API Settings": {
                    "apex": {
                        "provider": "openai",
                        "model": "gpt-4o"
                    }
                }
            }
    
    def _initialize_components(self):
        """Initialize all components and utilities - FAILS HARD if any component unavailable"""
        logger.info("Initializing LORE components...")
        
        # Initialize managers - all required
        self.token_manager = TokenBudgetManager(self.settings)
        settings_path = self.settings_path if hasattr(self, 'settings_path') else None
        self.llm_manager = LocalLLMManager(self.settings, settings_path)  # Will fail hard if LM Studio not available
        self.turn_manager = TurnCycleManager(self)
        
        # MEMNON is REQUIRED
        if not MEMNON_AVAILABLE:
            raise RuntimeError("FATAL: MEMNON module not available! Cannot proceed without memory retrieval.")
        self._initialize_memnon()
        if not self.memnon:
            raise RuntimeError("FATAL: MEMNON initialization failed! Check database connection.")
        
        # LOGON is required unless explicitly disabled (e.g., offline tests)
        if self.enable_logon:
            self._initialize_logon()
            if not self.logon:
                raise RuntimeError("FATAL: LOGON initialization failed! Check API settings.")
        
        # Memory manager orchestrates Pass 1/Pass 2 state
        self.memory_manager = ContextMemoryManager(
            self.settings,
            memnon=self.memnon,
            llm_manager=self.llm_manager,
            token_manager=self.token_manager,
        )

        logger.info("Component initialization complete")
    
    def _initialize_memnon(self):
        """Initialize MEMNON utility for memory retrieval"""
        try:
            # Create a minimal interface for MEMNON
            class MinimalInterface:
                def assistant_message(self, msg): logger.info(f"MEMNON: {msg}")
                def error_message(self, msg): logger.error(f"MEMNON Error: {msg}")
            
            # Get database URL from settings
            memnon_settings = self.settings.get("Agent Settings", {}).get("MEMNON", {})
            db_url = memnon_settings.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
            
            # Create minimal agent state and user objects
            class MinimalAgentState:
                state = {"name": "LORE"}
            
            class MinimalUser:
                id = "lore_system"
                name = "LORE"
            
            self.memnon = MEMNON(
                interface=MinimalInterface(),
                agent_state=MinimalAgentState(),
                user=MinimalUser(),
                db_url=db_url,
                debug=self.debug
            )
            logger.info("MEMNON utility initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MEMNON: {e}")
            self.memnon = None
    
    def _initialize_logon(self):
        """Initialize LOGON utility for API communication"""
        try:
            self.logon = LogonUtility(self.settings)
            logger.info("LOGON utility initialized")
        except Exception as e:
            logger.error(f"Failed to initialize LOGON: {e}")
            self.logon = None
    
    async def process_turn(self, user_input: str) -> str:
        """
        Process a complete turn cycle.
        
        Args:
            user_input: The user's input text
            
        Returns:
            Generated narrative response
        """
        logger.info(f"Starting turn cycle with input: {user_input[:100]}...")
        
        # Initialize turn context
        self.turn_context = TurnContext(
            turn_id=f"turn_{int(time.time())}",
            user_input=user_input,
            start_time=time.time()
        )
        
        try:
            # Ensure the required model is loaded
            if self.llm_manager:
                self.llm_manager.ensure_model_loaded()
            
            # Phase 1: User Input Processing
            self.current_phase = TurnPhase.USER_INPUT
            await self.turn_manager.process_user_input(self.turn_context)
            
            # Phase 2: Warm Analysis
            self.current_phase = TurnPhase.WARM_ANALYSIS
            await self.turn_manager.perform_warm_analysis(self.turn_context)
            
            # Phase 3: Entity State Queries
            self.current_phase = TurnPhase.ENTITY_STATE
            await self.turn_manager.query_entity_states(self.turn_context)
            
            # Phase 4: Deep Queries
            self.current_phase = TurnPhase.DEEP_QUERIES
            await self.turn_manager.execute_deep_queries(self.turn_context)
            
            # Phase 5: Payload Assembly
            self.current_phase = TurnPhase.PAYLOAD_ASSEMBLY
            await self.turn_manager.assemble_context_payload(self.turn_context)
            
            # Phase 6: Apex AI Generation
            self.current_phase = TurnPhase.APEX_GENERATION
            response = await self.turn_manager.call_apex_ai(self.turn_context)
            
            # Phase 7: Response Integration
            self.current_phase = TurnPhase.INTEGRATION
            await self.turn_manager.integrate_response(self.turn_context, response)
            
            # Return to idle
            self.current_phase = TurnPhase.IDLE
            
            # Log completion
            elapsed = time.time() - self.turn_context.start_time
            logger.info(f"Turn cycle completed in {elapsed:.2f} seconds")
            
            return response
            
        except Exception as e:
            logger.error(f"Error in turn cycle phase {self.current_phase}: {e}")
            self.turn_context.error_log.append(f"{self.current_phase}: {str(e)}")
            self.current_phase = TurnPhase.IDLE
            return f"Error processing turn: {str(e)}"
        
        finally:
            # Clean up resources after turn - honor runtime keep-model override and settings
            if (
                self.llm_manager
                and self.llm_manager.unload_on_exit  # allow --keep-model to disable
                and self.settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {}).get("unload_after_turn", True)
            ):
                logger.debug("Unloading model after turn cycle to free resources")
                self.llm_manager.unload_model()

    async def retrieve_context(self, retrieval_directives: Union[str, List[str]], chunk_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Process retrieval directives to assemble narrative context for a specific chunk.
        
        This is LORE's core function: understanding what contextual elements are needed
        for narrative generation and assembling them from the database.
        
        Args:
            retrieval_directives: One or more continuity elements/context requests 
                                  (e.g., ["Alex & Emilia's relationship history", "What happened to Victor?"])
            chunk_id: The narrative chunk this context is being assembled for
            
        Returns dict with:
        - retrieved_context: The assembled contextual information (dict keyed by directive)
        - sources: List of chunk IDs used
        - queries: The generated retrieval queries
        - retrieval_reasoning: LORE's reasoning about what to retrieve
        """
        # Normalize to list
        if isinstance(retrieval_directives, str):
            retrieval_directives = [retrieval_directives]
        
        qa_logger.info(f"Processing {len(retrieval_directives)} retrieval directive(s) for chunk {chunk_id}")

        # Ensure the default LM Studio model is loaded (auto load/unload as needed)
        try:
            manager = ModelManager(
                self.settings_path if hasattr(self, 'settings_path') else None,
                unload_on_exit=self.llm_manager.unload_on_exit
            )
            ensured_model_id = manager.ensure_default_model()
            qa_logger.info(f"Ensured LM Studio model loaded: {ensured_model_id}")
            # Hint LocalLLMManager about the loaded model id
            if self.llm_manager:
                self.llm_manager.loaded_model_id = ensured_model_id
        except Exception as e:
            raise RuntimeError(f"FATAL: Cannot ensure default LM Studio model! {e}")

        # Fail hard if local LLM is not available after ensuring the model
        if not self.llm_manager or not self.llm_manager.is_available():
            raise RuntimeError("FATAL: LM Studio required for contextual retrieval")

        # Load the specific chunk and surrounding context if chunk_id provided
        warm_slice = []
        chunk_context = None
        target_chunk_text = ""
        if chunk_id:
            try:
                # Get the specific chunk - this is our continuation point
                chunk_result = self.memnon.get_chunk_by_id(chunk_id) if self.memnon else None
                if chunk_result:
                    chunk_context = chunk_result
                    # Store the full text with header for later use
                    target_chunk_text = f"📍 TARGET CHUNK (continuation point):\n{chunk_result.get('full_text', chunk_result.get('text', ''))}"
                    
                    # Add it to warm slice with a clear marker
                    warm_slice.append({
                        "id": chunk_id,
                        "text": target_chunk_text,
                        "is_target": True
                    })
                    qa_logger.info(f"Loaded target chunk {chunk_id}")
                else:
                    qa_logger.warning(f"Could not find chunk {chunk_id}")
                    raise ValueError(f"Target chunk {chunk_id} not found in database")
            except Exception as e:
                qa_logger.error(f"Failed to retrieve chunk {chunk_id}: {e}")
                raise
        
        if not warm_slice:
            # Fallback to recent chunks if no specific chunk
            try:
                recent = self.memnon.get_recent_chunks(limit=5) if self.memnon else {"results": []}
                warm_slice = recent.get("results", [])
            except Exception as e:
                qa_logger.error(f"Failed to retrieve recent chunks: {e}")
                warm_slice = []

        # Process each directive sequentially and aggregate results
        all_results = {
            "chunk_id": chunk_id,
            "directives": {},  # Store all per-directive data here
            "sources": [],     # Combined sources from all directives
            "queries": []      # Combined queries from all directives
        }
        
        # Process each retrieval directive independently
        for directive in retrieval_directives:
            directive_result = await self._process_single_directive(directive, chunk_id, warm_slice, target_chunk_text)
            
            # Store per-directive results
            all_results["directives"][directive] = {
                "retrieved_context": directive_result["retrieved_context"],
                "reasoning": directive_result["reasoning"],
                "sql_attempts": directive_result.get("sql_attempts", []),
                "search_progress": directive_result.get("search_progress", []),
                "sources": directive_result["sources"]
            }
            
            # Also aggregate sources and queries for convenience
            all_results["sources"].extend(directive_result["sources"])
            all_results["queries"].extend(directive_result["queries"])
        
        # Deduplicate sources while preserving order
        all_results["sources"] = list(dict.fromkeys(all_results["sources"]))
        
        # If model was loaded for this operation, optionally unload it
        # Honor both settings.json keep_model_loaded and runtime overrides (unload_on_exit=False)
        try:
            unload_after = not self.settings.get("Agent Settings", {}).get("LORE", {}).get("keep_model_loaded", False)
            if self.llm_manager:
                # If caller wants to keep the model, they should set unload_on_exit=False before calling
                if self.llm_manager.unload_on_exit and unload_after:
                    self.llm_manager.unload_model()
                    qa_logger.info("Unloaded LM Studio model after retrieval")
        except Exception as e:
            qa_logger.warning(f"Model unload decision failed: {e}")
        
        return all_results
    
    async def answer_question(self, question: str) -> Dict[str, Any]:
        """
        Backward compatibility wrapper for retrieve_context.
        Converts old-style question into a retrieval directive.
        """
        qa_logger.warning("answer_question is deprecated. Use retrieve_context with directives instead.")
        return await self.retrieve_context([question], chunk_id=None)

    async def _process_single_directive(self, directive: str, chunk_id: Optional[int], warm_slice: List[Dict], target_chunk_text: str = "") -> Dict[str, Any]:
        """
        Process a single retrieval directive with full iterative capability.
        
        Args:
            directive: The specific continuity element to retrieve
            chunk_id: The narrative chunk this is for
            warm_slice: Context chunks to use for analysis
            
        Returns:
            Dict with retrieved_context, sources, queries, and reasoning for this directive
        """
        qa_logger.info(f"Processing directive: {directive[:50]}...")
        
        # Analyze directive in context of the specific chunk
        context_analysis = self.llm_manager.analyze_narrative_context(
            warm_slice=warm_slice, 
            user_input=f"For chunk {chunk_id}: {directive}" if chunk_id else directive
        )
        
        # Generate retrieval queries for this directive
        raw_queries: List[str] = self.llm_manager.generate_retrieval_queries(
            context_analysis=context_analysis, 
            user_input=directive
        )
        
        # Sanitize queries for text search compatibility
        def sanitize_query(q: str) -> str:
            import re
            q = re.sub(r"[\n\r\t]+", " ", q)
            q = re.sub(r"[\"'()?:;<>\\]", " ", q)
            q = re.sub(r"\s+", " ", q).strip()
            return q
        
        queries: List[str] = [sanitize_query(q) for q in raw_queries if q and q.strip()]
        queries = list(dict.fromkeys(queries))  # Deduplicate
        
        # Execute queries via MEMNON
        aggregated_results: Dict[str, Dict[str, Any]] = {}
        search_progress: List[Dict[str, Any]] = []
        
        for q in queries:
            try:
                result = self.memnon.query_memory(q, filters=None, k=8, use_hybrid=True)
                search_progress.append({"query": q, "result_count": result.get("metadata", {}).get("result_count", 0)})
                for item in result.get("results", []):
                    result_chunk_id = str(item.get("chunk_id") or item.get("id"))
                    if not result_chunk_id:
                        continue
                    if result_chunk_id not in aggregated_results:
                        aggregated_results[result_chunk_id] = {
                            "chunk_id": result_chunk_id,
                            "text": item.get("text", ""),
                            "metadata": item.get("metadata", {}),
                            "score": float(item.get("score", 0.0))
                        }
                    else:
                        aggregated_results[result_chunk_id]["score"] = max(
                            aggregated_results[result_chunk_id]["score"], 
                            float(item.get("score", 0.0))
                        )
            except Exception as e:
                qa_logger.error(f"Search error for query '{q}': {e}")
        
        # Optional agentic SQL phase for this directive
        sql_attempts: List[Dict[str, Any]] = []
        sql_context = ""
        
        agentic_sql_enabled = bool(self.settings.get("Agent Settings", {}).get("LORE", {}).get("agentic_sql", False))
        if agentic_sql_enabled and self.memnon:
            # Load SQL guidance from system prompt
            system_prompt_path = Path(__file__).parent / "lore_system_prompt.md"
            sql_section = ""
            try:
                with open(system_prompt_path, 'r') as f:
                    full_prompt = f.read()
                if "## Agentic SQL Mode" in full_prompt:
                    start = full_prompt.find("## Agentic SQL Mode")
                    end = full_prompt.find("### LOGON (API Interface)", start)
                    if end == -1:
                        end = full_prompt.find("## ", start + 1)
                    sql_section = full_prompt[start:end if end != -1 else None].strip()
            except Exception as e:
                qa_logger.warning(f"Could not load system prompt: {e}")
                sql_section = "Use SELECT queries with LIMIT. Respond with JSON: {\"action\": \"sql\"|\"final\", \"sql\": \"...\"}."
            
            # Get schema and construct prompt
            schema = self.memnon.get_schema_summary()
            query_budget = self.settings.get("Agent Settings", {}).get("LORE", {}).get("query_budget", 5)
            
            planning_prompt = (
                f"Task: Retrieve contextual information for this continuity element via SQL.\n\n"
                f"Schema:\n{schema}\n\n"
                f"Retrieval directive: {directive}\n" +
                (f"Context: This is for narrative chunk {chunk_id}\n\n" if chunk_id else "\n\n") +
                f"{sql_section}\n\n"
                f"Return one JSON object per step and wait for results. Limit to {query_budget} SQL steps."
            )
            
            # Iterative SQL refinement loop
            executed_sql: set[str] = set()
            for step_num in range(query_budget):
                from nexus.agents.lore.utils.local_llm import SQLStep
                
                # Debug: Log what the LLM is seeing
                if step_num > 0:
                    qa_logger.info(f"SQL Step {step_num + 1} - Building on previous results...")
                    qa_logger.debug(f"Prompt includes {len(executed_sql)} previous queries and results")
                
                # Get the LLM's reasoning AND the SQL step
                step_prompt = planning_prompt + (
                    f"\n\nStep {step_num + 1}: Based on the results so far, what should the next query be?\n"
                    "First explain your reasoning, then provide the JSON step."
                )
                
                # Get both reasoning and structured output
                # Use settings from settings.json - no fallbacks!
                llm_settings = self.settings.get("Agent Settings", {}).get("global", {}).get("llm", {})
                if not llm_settings:
                    raise RuntimeError("FATAL: LLM settings not found in settings.json")
                
                raw_response = self.llm_manager.query(
                    step_prompt,
                    system_prompt=llm_settings["system_prompt"] + " When iterating on SQL queries, explain your reasoning then provide JSON.",
                    temperature=llm_settings["temperature"],
                    max_tokens=llm_settings["max_tokens"]
                )
                
                # Log full model output at debug level to avoid duplicating terminal prints
                qa_logger.debug(f"Step {step_num + 1} raw response: {raw_response}")
                
                # Output reasoning in real-time - extract ONLY the first analysis channel
                if '<|channel|>analysis<|message|>' in raw_response:
                    # Extract just the analysis part, not the final/JSON part
                    analysis_part = raw_response.split('<|channel|>analysis<|message|>', 1)[1]
                    # Prefer to stop at <|end|>, otherwise stop at the next channel marker if present
                    if '<|end|>' in analysis_part:
                        analysis_part = analysis_part.split('<|end|>', 1)[0]
                    elif '<|channel|>' in analysis_part:
                        analysis_part = analysis_part.split('<|channel|>', 1)[0]
                    analysis_part = analysis_part.strip()
                    if analysis_part:
                        print("\nReasoning:")
                        print(analysis_part)
                
                # Extract the JSON from the response
                import re
                json_match = re.search(r'\{[^}]*"action"[^}]*\}', raw_response)
                if not json_match:
                    qa_logger.warning(f"No JSON found in response: {raw_response}")
                    continue
                
                try:
                    step = json.loads(json_match.group())
                except json.JSONDecodeError as e:
                    qa_logger.warning(f"Failed to parse JSON: {e}")
                    continue
                
                # Check if we're done
                if step.get("action") == "final":
                    qa_logger.info(f"SQL agent finished after {step_num + 1} steps")
                    break
                
                # Execute the SQL query
                if step.get("action") == "sql" and step.get("sql"):
                    sql_query = step["sql"]
                    if sql_query not in executed_sql:
                        executed_sql.add(sql_query)
                        
                        # Output query in real-time
                        print("\nQuery:")
                        print(sql_query)
                        
                        try:
                            result = self.memnon.execute_readonly_sql(sql_query)
                            # Store for later use
                            sql_attempts.append({"sql": sql_query, "result": result, "reasoning": raw_response})
                            
                            # Output result in real-time
                            print("\nResult:")
                            if result.get("row_count", 0) == 0:
                                print("No rows returned")
                            else:
                                print(f"{result.get('row_count')} rows returned")
                                # Show sample of results
                                if result.get("rows"):
                                    sample = result["rows"][:3]  # Show first 3 rows
                                    for row in sample:
                                        print(f"  {str(row)[:150]}..." if len(str(row)) > 150 else f"  {row}")
                                    if result.get("row_count", 0) > 3:
                                        print(f"  ... and {result['row_count'] - 3} more rows")
                            
                            # Add result to prompt for next iteration - don't truncate!
                            planning_prompt += f"\n\nStep {step_num + 1} SQL: {sql_query}\n"
                            # Show full results for proper iteration
                            result_str = json.dumps(result, indent=2)
                            if len(result_str) > 2000:  # Only truncate if truly massive
                                planning_prompt += f"Result (truncated to first 10 rows):\n"
                                truncated_result = {
                                    "row_count": result.get("row_count"),
                                    "columns": result.get("columns"),
                                    "rows": result.get("rows", [])[:10]
                                }
                                planning_prompt += json.dumps(truncated_result, indent=2) + "\n"
                            else:
                                planning_prompt += f"Result: {result_str}\n"
                            
                            # Add clear guidance for next iteration
                            remaining = query_budget - (step_num + 1)
                            if remaining > 0:
                                planning_prompt += f"\n🔄 Next query for '{directive[:50]}...'\n"
                                planning_prompt += f"Queries remaining: {remaining}/{query_budget}\n"
                                planning_prompt += "Based on these results, what should the next query be? Or respond with {\"action\": \"final\"} if done.\n"
                            
                            # Extract SQL context for synthesis
                            if result.get("rows"):
                                sql_context += f"\nSQL Query: {sql_query}\n"
                                sql_context += f"Result ({len(result['rows'])} rows):\n"
                                sql_context += json.dumps(result["rows"][:3], indent=2)[:1000] + "\n"
                        except Exception as e:
                            qa_logger.warning(f"SQL execution failed: {e}")
                            sql_attempts.append({"sql": sql_query, "error": str(e)})
                            
                            # Output error in real-time
                            print("\nResult:")
                            print(f"Error: {e}")
        
        # Sort results by score and prepare for synthesis
        sorted_results = sorted(
            aggregated_results.values(), 
            key=lambda x: x["score"], 
            reverse=True
        )[:10]  # Top 10 results
        
        # Synthesize the retrieved context for this directive
        if not sorted_results and not sql_context:
            return {
                "retrieved_context": f"No relevant information found for: {directive}",
                "sources": [],
                "queries": queries,
                "reasoning": "No results from text search or SQL queries",
                "sql_attempts": sql_attempts
            }
        
        # Format sources for synthesis
        sources_text = ""
        for i, result in enumerate(sorted_results, 1):
            sources_text += f"\n[Source {i}] Chunk {result['chunk_id']} (score: {result['score']:.2f}):\n"
            sources_text += result["text"][:500] + "...\n"
        
        # Add SQL context if available
        if sql_context:
            sources_text = f"SQL Results:\n{sql_context}\n\nText Search Results:\n{sources_text}"
        
        # Generate synthesis with final reminder about the target chunk
        synthesis_prompt = (
            f"Retrieval directive: {directive}\n\n"
            f"Available sources:\n{sources_text}\n\n"
        )
        
        # Add the target chunk reminder at the end as per OpenAI's guidance
        if target_chunk_text:
            synthesis_prompt += (
                f"\n{'='*50}\n"
                f"REMINDER - This context is being assembled to continue the story from:\n"
                f"{target_chunk_text}\n"
                f"{'='*50}\n\n"
            )
        
        synthesis_prompt += (
            "Synthesize the relevant contextual information that addresses the retrieval directive. "
            "This context will enable the Storyteller AI to continue the narrative from the target chunk shown above. "
            "Be specific and include relevant details that inform the continuation."
        )
        
        try:
            # Use proper settings from settings.json
            llm_settings = self.settings.get("Agent Settings", {}).get("global", {}).get("llm", {})
            raw_synthesis = self.llm_manager.query(
                synthesis_prompt,
                system_prompt=llm_settings.get("system_prompt", "You are a narrative intelligence system"),
                temperature=llm_settings.get("temperature", 0.8),
                max_tokens=llm_settings.get("max_tokens", 2048)
            )
            # Prefer content from final channel if present
            synthesis = raw_synthesis
            if '<|channel|>final<|message|>' in raw_synthesis:
                synthesis = raw_synthesis.split('<|channel|>final<|message|>', 1)[1].strip()
            # Clean trailing control tokens
            for marker in ("<|end|>",):
                if marker in synthesis:
                    synthesis = synthesis.split(marker, 1)[0].strip()
        except Exception as e:
            qa_logger.error(f"Synthesis failed: {e}")
            synthesis = sources_text[:1000]
        
        # Extract chunk IDs from results
        source_ids = [int(r["chunk_id"]) for r in sorted_results if r["chunk_id"].isdigit()]
        
        return {
            "retrieved_context": synthesis,
            "sources": source_ids,
            "queries": queries,
            "reasoning": context_analysis,
            "sql_attempts": sql_attempts,
            "search_progress": search_progress
        }
    
    def get_turn_summary(self) -> Dict[str, Any]:
        """Get a summary of the last turn cycle"""
        if not self.turn_context:
            return {"status": "No turn processed yet"}
        
        elapsed = time.time() - self.turn_context.start_time
        
        return {
            "turn_id": self.turn_context.turn_id,
            "elapsed_time": f"{elapsed:.2f} seconds",
            "phases_completed": list(self.turn_context.phase_states.keys()),
            "token_utilization": self.turn_context.phase_states.get("payload_assembly", {}).get("utilization_percentage", 0),
            "errors": self.turn_context.error_log,
            "apex_tokens": self.turn_context.phase_states.get("apex_generation", {}),
            "components": {
                "memnon": "available" if self.memnon else "unavailable",
                "logon": "available" if self.logon else "unavailable",
                "llm": "available" if self.llm_manager.is_available() else "unavailable"
            }
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of LORE and its components"""
        return {
            "current_phase": self.current_phase.value,
            "components": {
                "memnon": self.memnon is not None,
                "logon": self.logon is not None,
                "local_llm": self.llm_manager.is_available() if self.llm_manager else False,
                "token_manager": self.token_manager is not None,
                "turn_manager": self.turn_manager is not None,
                "memory_manager": self.memory_manager is not None
            },
            "settings_loaded": bool(self.settings),
            "debug_mode": self.debug,
            "memory": self.memory_manager.get_memory_summary() if self.memory_manager else {}
        }


# Command-line interface for testing
async def main():
    """Main entry point for testing LORE"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LORE Agent - NEXUS Orchestrator")
    parser.add_argument("retrieval_directives", nargs="*", help="One or more retrieval directives/continuity elements to process")
    parser.add_argument("--chunk", type=int, required=False, help="Narrative chunk ID to build context for")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--settings", help="Path to settings.json")
    parser.add_argument("--test", action="store_true", help="Run test turn cycle")
    parser.add_argument("--status", action="store_true", help="Show component status")
    parser.add_argument("--qa", help="(Deprecated) Use positional argument instead")
    parser.add_argument("--keep-model", action="store_true", help="Keep LM Studio model loaded after run")
    parser.add_argument("--agentic-sql", action="store_true", help="Enable agentic SQL mode for retrieval")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Initialize LORE
    lore = LORE(settings_path=args.settings, debug=args.debug)
    
    if args.status:
        # Show status
        status = lore.get_status()
        print("\n" + "="*60)
        print("LORE STATUS")
        print("="*60)
        print(json.dumps(status, indent=2))
        
    elif args.qa or args.retrieval_directives:
        # Contextual retrieval mode (formerly Q&A)
        directives = args.retrieval_directives if args.retrieval_directives else [args.qa] if args.qa else []
        
        if directives and not args.chunk:
            print("Error: --chunk parameter is required when providing retrieval directives")
            print("Usage: python lore.py 'directive1' 'directive2' ... --chunk <chunk_id>")
            return
        
        if args.agentic_sql:
            # Override setting for this run
            lore.settings.setdefault("Agent Settings", {}).setdefault("LORE", {}).setdefault("agentic_sql", True)
        
        # Set keep-model flag BEFORE retrieval
        if args.keep_model and lore.llm_manager:
            lore.llm_manager.unload_on_exit = False
            logger.info("Model will be kept loaded after retrieval (--keep-model)")
        
        logger.info(f"Processing {len(directives)} retrieval directive(s) for chunk {args.chunk}")
        result = await lore.retrieve_context(directives, chunk_id=args.chunk)
        
        # Format output to follow the actual reasoning flow
        print(f"\n{'='*60}")
        print(f"CONTEXTUAL RETRIEVAL FOR CHUNK {args.chunk}")
        print(f"{'='*60}\n")
        
        # For each directive, show only the final synthesis (queries were output in real-time)
        for directive, directive_data in result.get("directives", {}).items():
            print(f"\n🎯 DIRECTIVE: {directive}")
            print("=" * 50)
            
            # The SQL queries and reasoning have already been output in real-time
            # during the _process_single_directive() function
            # Just show the final synthesis here
            
            print(f"\nFinal Synthesis:")
            print("-" * 40)
            
            # Just output the synthesis as-is - TUI will handle formatting
            synthesis = directive_data.get("retrieved_context", "No context retrieved")
            print("\nResponse:")
            print(synthesis)
            print()
        
        # Summary statistics
        print(f"📊 Summary:")
        if result.get("sources"):
            print(f"   Total chunks used: {len(result['sources'])}")
        
        # Count SQL queries across all directives
        total_sql = sum(len(d.get("sql_attempts", [])) for d in result.get("directives", {}).values())
        if total_sql:
            print(f"   SQL queries executed: {total_sql}")
        
        # Count text search results across all directives  
        total_search = sum(
            sum(sp.get("result_count", 0) for sp in d.get("search_progress", []))
            for d in result.get("directives", {}).values()
        )
        if total_search:
            print(f"   Text search results: {total_search}")
        
        print(f"\n{'='*60}\n")
        
        # Optionally save full JSON if requested
        if args.debug:
            print("Full JSON response (debug mode):")
            print(json.dumps(result, indent=2))

    elif args.test:
        # Run a test turn
        test_input = "I examine the neural implant carefully, looking for any markings."
        logger.info(f"Running test turn with input: {test_input}")
        
        response = await lore.process_turn(test_input)
        
        print("\n" + "="*60)
        print("LORE TEST RESULTS")
        print("="*60)
        print(f"\nUser Input: {test_input}")
        print(f"\nGenerated Response:\n{response}")
        print(f"\nTurn Summary:\n{json.dumps(lore.get_turn_summary(), indent=2)}")
        
    else:
        # Interactive mode
        print("\n" + "="*60)
        print("LORE AGENT - Interactive Mode")
        print("="*60)
        print("Commands: 'quit', 'status', 'summary'\n")
        
        while True:
            try:
                user_input = input("\n> ").strip()
                
                if user_input.lower() == 'quit':
                    break
                elif user_input.lower() == 'status':
                    print(json.dumps(lore.get_status(), indent=2))
                    continue
                elif user_input.lower() == 'summary':
                    print(json.dumps(lore.get_turn_summary(), indent=2))
                    continue
                elif not user_input:
                    continue
                
                response = await lore.process_turn(user_input)
                print(f"\nLORE: {response}")
                
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
