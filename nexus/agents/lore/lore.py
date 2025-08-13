"""
LORE Agent - Central Orchestration Agent for NEXUS

LORE (Lore Operations & Retrieval Engine) is the sole intelligent agent in the NEXUS system.
It orchestrates all utility modules and assembles optimal context payloads for the Apex LLM.

Key Responsibilities:
1. Narrative State Analysis - Analyze current narrative moment for context needs
2. Utility Orchestration - Coordinate MEMNON, PSYCHE, NEMESIS, GAIA, and LOGON
3. Intelligent Context Assembly - Dynamically determine and balance information needs
4. Turn Cycle Management - Handle the complete turn sequence from user input to response
"""

import asyncio
import logging
import json
import time
from typing import Dict, Optional, Any, List
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
        debug: bool = False
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
        self.llm_manager = None
        self.token_manager = None
        self.turn_manager = None
        
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
        
        # LOGON is REQUIRED
        self._initialize_logon()
        if not self.logon:
            raise RuntimeError("FATAL: LOGON initialization failed! Check API settings.")
        
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
            # Clean up resources after turn - good housekeeping!
            if self.llm_manager and self.settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {}).get("unload_after_turn", True):
                logger.debug("Unloading model after turn cycle to free resources")
                self.llm_manager.unload_model()

    async def answer_question(self, question: str) -> Dict[str, Any]:
        """
        Answer a direct question about the narrative without generating new story content.
        
        Returns dict with:
        - answer: The synthesized response
        - sources: List of chunk IDs used
        - queries: The generated retrieval queries
        - reasoning: LLM's reasoning trace
        """
        qa_logger.info(f"Processing question: {question[:50]}...")

        # Ensure the default LM Studio model is loaded (auto load/unload as needed)
        try:
            manager = ModelManager(self.settings_path if hasattr(self, 'settings_path') else None)
            ensured_model_id = manager.ensure_default_model()
            qa_logger.info(f"Ensured LM Studio model loaded: {ensured_model_id}")
            # Hint LocalLLMManager about the loaded model id
            if self.llm_manager:
                self.llm_manager.loaded_model_id = ensured_model_id
        except Exception as e:
            raise RuntimeError(f"FATAL: Cannot ensure default LM Studio model! {e}")

        # Fail hard if local LLM is not available after ensuring the model
        if not self.llm_manager or not self.llm_manager.is_available():
            raise RuntimeError("FATAL: LM Studio required for Q&A mode")

        # Acquire a small warm slice from recent chunks to guide query generation
        try:
            recent = self.memnon.get_recent_chunks(limit=5) if self.memnon else {"results": []}
            warm_slice = recent.get("results", [])
        except Exception as e:
            qa_logger.error(f"Failed to retrieve recent chunks: {e}")
            warm_slice = []

        # Analyze question in context of recent narrative
        context_analysis = self.llm_manager.analyze_narrative_context(warm_slice=warm_slice, user_input=question)

        # Generate retrieval queries (include the original question)
        raw_queries: List[str] = self.llm_manager.generate_retrieval_queries(context_analysis=context_analysis, user_input=question)
        
        # Sanitize queries for text search compatibility (avoid punctuation that breaks tsquery)
        def sanitize_query(q: str) -> str:
            # Keep alphanumerics and common separators; replace problematic chars with spaces
            import re
            q = re.sub(r"[\n\r\t]+", " ", q)
            q = re.sub(r"[\"'()?:;<>\\]", " ", q)
            q = re.sub(r"\s+", " ", q).strip()
            return q
        queries: List[str] = [sanitize_query(q) for q in raw_queries if q and q.strip()]
        # Deduplicate while preserving order
        queries = list(dict.fromkeys(queries))

        # Execute queries via MEMNON (hybrid search preferred) and also query structured data
        aggregated_results: Dict[str, Dict[str, Any]] = {}
        search_progress: List[Dict[str, Any]] = []
        structured_sources: List[Dict[str, Any]] = []
        for q in queries:
            try:
                result = self.memnon.query_memory(q, filters=None, k=8, use_hybrid=True)
                search_progress.append({"query": q, "result_count": result.get("metadata", {}).get("result_count", 0)})
                for item in result.get("results", []):
                    chunk_id = str(item.get("chunk_id") or item.get("id"))
                    if not chunk_id:
                        continue
                    if chunk_id not in aggregated_results:
                        aggregated_results[chunk_id] = {
                            "chunk_id": chunk_id,
                            "text": item.get("text", ""),
                            "metadata": item.get("metadata", {}),
                            "score": float(item.get("score", 0.0))
                        }
                    else:
                        # Keep the best score
                        aggregated_results[chunk_id]["score"] = max(
                            aggregated_results[chunk_id]["score"], float(item.get("score", 0.0))
                        )
            except Exception as e:
                qa_logger.error(f"Search error for query '{q}': {e}")

        # Structured lookup: try direct character/relationship info for names present in the question
        try:
            candidate_names: List[str] = []
            # Heuristic: extract capitalized tokens as potential names
            import re
            for token in re.findall(r"[A-Z][a-zA-Z]+", question):
                if token.lower() not in {"what", "who", "where", "when", "why", "how", "Is", "Are", "Dynacorp".lower()}:
                    candidate_names.append(token)
            # Always include first token if exact string present like Victor
            candidate_names = list(dict.fromkeys(candidate_names))[:2]
            for name in candidate_names:
                try:
                    # Query characters table via MEMNON structured path
                    structured = self.memnon._query_structured_data(name, table="characters", limit=3)
                    if structured:
                        # For structured results, create synthetic passages referencing character summaries if available
                        # Capture structured sources (characters table)
                        try:
                            char_ids = [int(rec.get("id")) for rec in structured if rec.get("id") is not None]
                            if char_ids:
                                structured_sources.append({"table": "characters", "ids": char_ids})
                        except Exception:
                            pass
                        # Attempt to enrich with character summary if needed (left for LLM synthesis input via SQL attempts)
                        search_progress.append({"query": f"structured:characters:{name}", "result_count": len(structured)})
                    # Also run plain memory search on the name to capture narrative mentions
                    try:
                        if name not in queries:
                            queries.append(name)
                        name_result = self.memnon.query_memory(name, filters=None, k=8, use_hybrid=True)
                        search_progress.append({"query": name, "result_count": name_result.get("metadata", {}).get("result_count", 0)})
                        for item in name_result.get("results", []):
                            chunk_id = str(item.get("chunk_id") or item.get("id"))
                            if not chunk_id:
                                continue
                            if chunk_id not in aggregated_results:
                                aggregated_results[chunk_id] = {
                                    "chunk_id": chunk_id,
                                    "text": item.get("text", ""),
                                    "metadata": item.get("metadata", {}),
                                    "score": float(item.get("score", 0.0))
                                }
                            else:
                                aggregated_results[chunk_id]["score"] = max(
                                    aggregated_results[chunk_id]["score"], float(item.get("score", 0.0))
                                )
                    except Exception as e:
                        qa_logger.debug(f"Name search failed for {name}: {e}")
                except Exception as e:
                    qa_logger.debug(f"Structured lookup failed for {name}: {e}")
        except Exception:
            pass

        # If nothing found, return an "I don't know" style answer
        if not aggregated_results:
            qa_logger.info("No results found across queries; returning insufficient-evidence response")
            return {
                "answer": "I don't know based on the available story data.",
                "sources": [],
                "queries": queries,
                "reasoning": "No relevant chunks were retrieved for the question."
            }

        # Select top passages (limit for concise synthesis)
        # Broaden synthesis pool: take top 10 by default and optionally expand around the best chunk (spot-reading)
        sorted_passages = sorted(aggregated_results.values(), key=lambda r: r.get("score", 0.0), reverse=True)
        top_passages = sorted_passages[:10]
        # Optional spot-reading: expand around single best chunk id by fetching neighbors n-1..n+1 for more context
        try:
            if top_passages:
                best_id_str = str(top_passages[0]["chunk_id"]) if top_passages[0].get("chunk_id") is not None else None
                if best_id_str and best_id_str.isdigit():
                    best_id = int(best_id_str)
                    neighbor_ids = [best_id - 1, best_id + 1]
                    for nid in neighbor_ids:
                        if nid > 0 and str(nid) not in aggregated_results:
                            neighbor = self.memnon._get_chunk_by_id(nid)
                            for item in neighbor.get("results", []) or []:
                                aggregated_results[str(item.get("id"))] = {
                                    "chunk_id": str(item.get("id")),
                                    "text": item.get("text", ""),
                                    "metadata": item.get("metadata", {}),
                                    "score": 0.01,  # low weight context
                                }
                    # Recompute top 10 including neighbors
                    top_passages = sorted(aggregated_results.values(), key=lambda r: r.get("score", 0.0), reverse=True)[:10]
        except Exception:
            pass

        # Build synthesis prompt with explicit chunk IDs and temporal metadata
        def fmt_meta(md: Dict[str, Any]) -> str:
            season = md.get("season")
            episode = md.get("episode")
            scene = md.get("scene_number")
            perspective = md.get("perspective")
            parts = []
            if season is not None and episode is not None:
                parts.append(f"S{season}E{episode}")
            if scene is not None:
                parts.append(f"Scene {scene}")
            if perspective:
                parts.append(f"Perspective: {perspective}")
            return ", ".join(parts)

        sources_block_lines: List[str] = []
        for p in top_passages:
            cid = p["chunk_id"]
            meta = fmt_meta(p.get("metadata", {}))
            txt = p.get("text", "").strip()
            # Keep each excerpt modest to control token use
            excerpt = txt if len(txt) <= 600 else txt[:600] + "..."
            sources_block_lines.append(f"- [chunk_id:{cid}] ({meta})\n{excerpt}")

        sources_block = "\n\n".join(sources_block_lines)

        system_prompt = (
            "You are LORE, an expert narrative analyst. Answer user questions about the existing story using only the provided sources. "
            "Be concise and strictly informational (no new prose). If evidence is insufficient, reply with 'I don't know'. "
            "Return a strict JSON object with keys: answer (string), reasoning (string), cited_chunk_ids (array of integers). "
            "Only include chunk IDs that appear in the provided sources."
        )

        user_prompt = (
            f"Question: {question}\n\n"
            f"Sources (each includes its chunk_id and metadata):\n\n{sources_block}\n\n"
            "Instructions: Using only these sources, produce JSON like:\n"
            "{\n  \"answer\": \"...\",\n  \"reasoning\": \"...\",\n  \"cited_chunk_ids\": [123, 456]\n}"
        )

        # Optional agentic SQL phase: let LLM propose up to N read-only SQL queries over whitelisted tables
        agentic_sql_enabled = bool(self.settings.get("Agent Settings", {}).get("LORE", {}).get("agentic_sql", False))
        sql_attempts: List[Dict[str, Any]] = []
        sql_context = ""
        if agentic_sql_enabled and self.memnon:
            # Load the system prompt which contains SQL guidance
            system_prompt_path = Path(__file__).parent / "lore_system_prompt.md"
            sql_section = ""
            try:
                with open(system_prompt_path, 'r') as f:
                    full_prompt = f.read()
                # Extract the Agentic SQL Mode section
                if "## Agentic SQL Mode" in full_prompt:
                    start = full_prompt.find("## Agentic SQL Mode")
                    end = full_prompt.find("### LOGON (API Interface)", start)
                    if end == -1:
                        end = full_prompt.find("## ", start + 1)
                    if end != -1:
                        sql_section = full_prompt[start:end].strip()
                    else:
                        sql_section = full_prompt[start:].strip()
            except Exception as e:
                qa_logger.warning(f"Could not load system prompt: {e}")
                sql_section = "Use SELECT queries with LIMIT. Respond with JSON: {\"action\": \"sql\"|\"final\", \"sql\": \"...\"}."
            
            # Get schema and construct prompt
            schema = self.memnon.get_schema_summary()
            planning_prompt = (
                f"Task: Answer the user's question by checking relevant facts via SQL.\n\n"
                f"Schema:\n{schema}\n\n"
                f"User question: {question}\n\n"
                f"{sql_section}\n\n"
                f"Return one JSON object per step and wait for results. Limit to 3 SQL steps."
            )
            # Simple loop: 3 steps max
            max_steps = 3
            executed_sql: set[str] = set()
            for _ in range(max_steps):
                # Prefer structured response for planning
                from nexus.agents.lore.utils.local_llm import SQLStep
                step_struct = self.llm_manager.structured_query(
                    planning_prompt,
                    response_model=SQLStep,
                    temperature=0.1,
                    max_tokens=200,
                    system_prompt="Propose exactly one Step JSON per turn."
                )
                try:
                    if hasattr(step_struct, "action"):
                        step = {"action": step_struct.action, "sql": getattr(step_struct, "sql", None)}
                    elif isinstance(step_struct, dict):
                        step = step_struct
                    else:
                        break
                except Exception:
                    break
                if not isinstance(step, dict):
                    break
                action = str(step.get("action", "")).lower()
                if action == "final":
                    break
                if action == "sql":
                    sql = str(step.get("sql", "")).strip()
                    
                    # Fix common SQL quote issues from LLM generation
                    import re
                    
                    # Only fix double-quoted strings (wrong SQL syntax)
                    # Convert "string" to 'string' and escape internal apostrophes
                    def fix_double_quotes(match):
                        keyword = match.group(1)  # ILIKE or =
                        content = match.group(2)
                        # Escape any apostrophes by doubling them
                        content = content.replace("'", "''")
                        return f"{keyword} '{content}'"
                    
                    # Only process double-quoted strings, leave single-quoted ones alone
                    sql = re.sub(r'(ILIKE|=)\s+"([^"]*)"', fix_double_quotes, sql, flags=re.IGNORECASE)
                    
                    # Guard against duplicate SQL proposals
                    if sql in executed_sql:
                        # Nudge planner to refine or finish
                        planning_prompt += "\nNote: The previous SQL was already executed; do not repeat identical SQL. Propose a refined query (different columns/table) or emit {\\\"action\\\": \\\"final\\\"}."
                        # Record skipped duplicate
                        sql_attempts.append({"sql": sql, "result": {"error": "duplicate_skipped"}})
                        continue
                    exec_result = self.memnon.execute_readonly_sql(sql)
                    executed_sql.add(sql)
                    sql_attempts.append({"sql": sql, "result": exec_result})
                    # Feed back result for next step
                    planning_prompt += f"\n\nResult for {sql!r}:\n{json.dumps(exec_result)[:1500]}"
                else:
                    break
            # Make any SQL-derived rows available to synthesis as an extra source block
            if sql_attempts:
                rows_snippets: List[str] = []
                for att in sql_attempts:
                    res = att.get("result", {})
                    if isinstance(res, dict) and res.get("rows"):
                        # Show first few rows compactly
                        preview = json.dumps(res.get("rows")[:3])
                        rows_snippets.append(f"SQL: {att.get('sql')}\nRows: {preview}")
                if rows_snippets:
                    user_prompt += "\n\nAdditional structured facts (from SQL):\n" + "\n\n".join(rows_snippets)

        # Prefer structured response via SDK when available
        structured = None
        try:
            structured = self.llm_manager.structured_query(
                prompt=user_prompt,
                response_model=__import__("nexus.agents.lore.utils.local_llm", fromlist=["QAResponse"]).QAResponse,
                temperature=0.2,
                max_tokens=800,
                system_prompt=system_prompt,
            )
        except Exception as e:
            qa_logger.debug(f"structured_query unavailable: {e}")

        if isinstance(structured, dict) or (hasattr(structured, "answer")):
            # Convert to unified dict form
            try:
                if isinstance(structured, dict):
                    answer = str(structured.get("answer", "")).strip()
                    reasoning = str(structured.get("reasoning", "")).strip()
                    cited_ids = structured.get("cited_chunk_ids", []) or []
                else:
                    answer = str(getattr(structured, "answer", "")).strip()
                    reasoning = str(getattr(structured, "reasoning", "")).strip()
                    cited_ids = list(getattr(structured, "cited_chunk_ids", []) or [])
            except Exception:
                answer = ""
                reasoning = ""
                cited_ids = []
        else:
            # Synthesize with low temperature for factuality
            raw_response = self.llm_manager.query(
                prompt=user_prompt,
                temperature=0.2,
                max_tokens=800,
                system_prompt=system_prompt,
            )

            qa_logger.debug(f"LLM raw synthesis response (truncated): {raw_response[:200]}...")

            # Parse JSON output
            answer: str = ""
            reasoning: str = ""
            cited_ids: List[int] = []
            try:
                # Strip channel markers if present
                cleaned = raw_response
                for marker in ["<|channel|>analysis<|message|>", "<|start|>assistant", "<|channel|>final<|message|>", "<|end|>"]:
                    cleaned = cleaned.replace(marker, "")
                cleaned = cleaned.strip()
                # Attempt to find the first JSON object in the response
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                candidate = cleaned[start:end+1] if start != -1 and end != -1 and end > start else cleaned
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    answer = str(parsed.get("answer", "")).strip()
                    reasoning = str(parsed.get("reasoning", "")).strip()
                    parsed_ids = parsed.get("cited_chunk_ids", []) or []
                    if isinstance(parsed_ids, list):
                        for v in parsed_ids:
                            try:
                                cited_ids.append(int(v))
                            except Exception:
                                continue
            except Exception as e:
                qa_logger.warning(f"Failed to parse JSON from LLM response: {e}; using fallback formatting")
                # Fallback: treat the whole response as the answer
                answer = raw_response.strip()
                reasoning = "Synthesis returned non-JSON; included raw content."

        # Validate cited IDs against retrieved sources
        available_ids = {int(p["chunk_id"]) for p in top_passages if str(p.get("chunk_id")).isdigit()}
        valid_cited = [cid for cid in cited_ids if cid in available_ids]
        if not valid_cited:
            # Fallback: cite the top 3 retrieved chunks
            valid_cited = list(available_ids)[:3]

        # Summarize SQL attempts for output transparency (avoid dumping full rows)
        summarized_sql_attempts: List[Dict[str, Any]] = []
        try:
            for att in sql_attempts:
                res = att.get("result", {}) if isinstance(att, dict) else {}
                summarized_sql_attempts.append({
                    "sql": att.get("sql"),
                    "row_count": res.get("row_count"),
                    "columns": res.get("columns")[:5] if isinstance(res.get("columns"), list) else None,
                })
        except Exception:
            pass

        return {
            "answer": answer or "I don't know based on the available story data.",
            "sources": valid_cited,
            "structured_sources": structured_sources,
            "queries": queries,
            "reasoning": reasoning,
            "search_progress": search_progress,
            "sql_attempts": summarized_sql_attempts,
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
                "turn_manager": self.turn_manager is not None
            },
            "settings_loaded": bool(self.settings),
            "debug_mode": self.debug
        }


# Command-line interface for testing
async def main():
    """Main entry point for testing LORE"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LORE Agent - NEXUS Orchestrator")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--settings", help="Path to settings.json")
    parser.add_argument("--test", action="store_true", help="Run test turn cycle")
    parser.add_argument("--status", action="store_true", help="Show component status")
    parser.add_argument("--qa", help="Run Q&A mode with the given question")
    parser.add_argument("--keep-model", action="store_true", help="Keep LM Studio model loaded after run")
    parser.add_argument("--agentic-sql", action="store_true", help="Enable agentic SQL mode for Q&A")
    
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
        
    elif args.qa:
        # Q&A mode
        if args.agentic_sql:
            # Override setting for this run
            lore.settings.setdefault("Agent Settings", {}).setdefault("LORE", {}).setdefault("agentic_sql", True)
        qa_logger.info(f"Running Q&A for question: {args.qa}")
        result = await lore.answer_question(args.qa)
        print(json.dumps(result, indent=2))
        if args.keep_model and lore.llm_manager:
            lore.llm_manager.unload_on_exit = False

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