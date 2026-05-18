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

# Import NEXUS configuration loader
from nexus.config import load_settings_as_dict

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
from nexus.agents.lore.logon_utility import LogonUtility

from nexus.memory import ContextMemoryManager
from nexus.memory.user_confirmation import request_input

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
        dbname: Optional[str] = None,
        slot: Optional[int] = None,
    ):
        """
        Initialize LORE agent.

        Args:
            settings_path: Path to settings.json file
            debug: Enable debug logging
            enable_logon: Whether to enable LOGON utility
            dbname: Database name (save_01 through save_05).
                    If not provided, uses slot or NEXUS_SLOT env var.
            slot: Slot number (1-5). Alternative to dbname.
        """
        self.debug = debug
        self.dbname = dbname
        self.slot = slot
        self.settings = self._load_settings(settings_path)

        # Configure logging
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

        # Initialize components
        self.memnon = None
        self.logon: Optional[LogonUtility] = None
        self.enable_logon = enable_logon
        self._logon_initialized = False
        self.llm_manager = None
        self.token_manager = None
        self.turn_manager = None
        self.memory_manager = None

        # Load system prompt
        self.system_prompt = self._load_system_prompt()

        # Turn cycle state
        self.current_phase = TurnPhase.IDLE
        self.turn_context = None

        # Initialize utilities
        self._initialize_components()

        logger.info("LORE agent initialized successfully")

    def _load_settings(self, settings_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load and validate settings from nexus.toml (or legacy settings.json).

        Uses Pydantic models for validation and type safety.
        Falls back to settings.json for backward compatibility.
        """
        if not settings_path:
            # Try nexus.toml first, then fall back to settings.json
            config_dir = Path(__file__).parent.parent.parent.parent
            toml_path = config_dir / "nexus.toml"
            json_path = config_dir / "settings.json"

            settings_path = toml_path if toml_path.exists() else json_path

        self.settings_path = settings_path  # Store for later use

        try:
            settings = load_settings_as_dict(settings_path)
            logger.info(f"✓ Loaded and validated settings from {settings_path}")
            return settings
        except Exception as e:
            logger.error(f"Failed to load settings from {settings_path}: {e}")
            raise RuntimeError(
                f"Cannot initialize LORE without valid configuration: {e}\n"
                f"Tried: {settings_path}"
            ) from e

    def _load_system_prompt(self) -> str:
        """Load the LORE system prompt from file - asks user for path if not available"""
        system_prompt_path = Path(__file__).parent / "lore_system_prompt.md"

        try:
            with open(system_prompt_path, "r") as f:
                prompt = f.read()
                logger.info(
                    f"Loaded system prompt from {system_prompt_path} ({len(prompt)} bytes)"
                )
                return prompt
        except FileNotFoundError:
            logger.warning(
                f"System prompt file not found at default location: {system_prompt_path}"
            )

            # Ask user for alternative path
            user_path = request_input(
                f"System prompt not found at:\n  {system_prompt_path}\n\nPlease enter the path to lore_system_prompt.md",
                validation_func=lambda p: Path(p).exists() and Path(p).is_file(),
                hook_type="system_prompt_path",
            )

            if user_path:
                try:
                    with open(user_path, "r") as f:
                        prompt = f.read()
                        logger.info(
                            f"Loaded system prompt from user-provided path: {user_path} ({len(prompt)} bytes)"
                        )
                        return prompt
                except Exception as e:
                    logger.error(f"Failed to load system prompt from user path: {e}")
                    raise RuntimeError(
                        f"FATAL: Could not load system prompt from {user_path}: {e}"
                    )
            else:
                raise RuntimeError(
                    f"FATAL: System prompt required but not provided. LORE cannot operate without instructions."
                )
        except Exception as e:
            raise RuntimeError(
                f"FATAL: Failed to load system prompt: {e}! LORE cannot operate without instructions."
            )

    def _initialize_components(self):
        """Initialize all components and utilities - FAILS HARD if any component unavailable"""
        logger.info("Initializing LORE components...")

        # Initialize managers - all required
        self.token_manager = TokenBudgetManager(self.settings)
        self.turn_manager = TurnCycleManager(self)
        logger.info(
            "LORE turn cycle uses deterministic retrieval planning and direct "
            "MEMNON search."
        )

        # MEMNON is REQUIRED
        if not MEMNON_AVAILABLE:
            raise RuntimeError(
                "FATAL: MEMNON module not available! Cannot proceed without memory retrieval."
            )
        self._initialize_memnon()
        if not self.memnon:
            raise RuntimeError(
                "FATAL: MEMNON initialization failed! Check database connection."
            )

        # LOGON is initialized lazily on first use when enabled
        if self.enable_logon and not self._logon_initialized:
            apex_settings = self.settings.get("API Settings", {}).get("apex")
            if apex_settings is None:
                logger.warning(
                    "LOGON enabled but no explicit apex configuration found; using default provider settings"
                )
            logger.info(
                "LOGON lazy initialization enabled; provider will be created on first use"
            )

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
                def assistant_message(self, msg):
                    logger.info(f"MEMNON: {msg}")

                def error_message(self, msg):
                    logger.error(f"MEMNON Error: {msg}")

            # Get database URL - use slot-aware resolution
            # Priority: explicit dbname > slot > NEXUS_SLOT env var
            from nexus.api.slot_utils import get_slot_db_url

            db_url = get_slot_db_url(dbname=self.dbname, slot=self.slot)

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
                debug=self.debug,
            )
            logger.info("MEMNON utility initialized with database: %s", db_url)
        except Exception as e:
            logger.error(f"Failed to initialize MEMNON: {e}")
            self.memnon = None

    def _initialize_logon(self):
        """Initialize LOGON utility for API communication"""
        try:
            # Pass dbname for slot-aware database connections
            from nexus.api.slot_utils import require_slot_dbname

            db = require_slot_dbname(dbname=self.dbname, slot=self.slot)
            self.logon = LogonUtility(self.settings, dbname=db)
            self._logon_initialized = True
            logger.info("LOGON utility initialized on first use")
        except Exception as e:
            logger.error(f"Failed to initialize LOGON: {e}")
            self.logon = None
            self._logon_initialized = False
            raise RuntimeError("Failed to initialize LOGON") from e

    def ensure_logon(self) -> None:
        """Ensure LOGON is initialized before use."""
        if not self.enable_logon:
            logger.debug("LOGON disabled; skipping initialization request")
            return

        if self.logon is None:
            self._initialize_logon()

    async def process_turn(
        self,
        user_input: str,
        parent_chunk_id: Optional[int] = None,
        note: Optional[str] = None,
    ):
        """
        Process a complete turn cycle.

        Args:
            user_input: The user's input text
            parent_chunk_id: Optional chunk id that should be continued
            note: Optional soft author's note to nudge the storyteller (used by regenerate
                for meta-hints like "darker, plz" or continuity corrections; out-of-character).

        Returns:
            StoryTurnResponse with narrative and metadata, or string on error
        """
        logger.info(f"Starting turn cycle with input: {user_input[:100]}...")
        if note:
            logger.info(f"Author's note: {note[:200]}")

        # Initialize turn context
        self.turn_context = TurnContext(
            turn_id=f"turn_{int(time.time())}",
            user_input=user_input,
            start_time=time.time(),
            target_chunk_id=parent_chunk_id,
            note=note,
        )

        try:
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

            # Phase 4.5: Orrery dry-run resolution (optional; no canonical writes)
            self.current_phase = TurnPhase.ORRERY_RESOLVE
            await self.turn_manager.resolve_orrery(self.turn_context)

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
            failed_phase = self.current_phase
            logger.error(f"Error in turn cycle phase {failed_phase}: {e}")
            self.turn_context.error_log.append(f"{failed_phase}: {str(e)}")
            self.current_phase = TurnPhase.IDLE
            if failed_phase == TurnPhase.APEX_GENERATION:
                raise
            return f"Error processing turn: {str(e)}"

    async def retrieve_context(
        self,
        retrieval_directives: Union[str, List[str]],
        chunk_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process retrieval directives to assemble narrative context for a specific chunk.

        This legacy helper now performs direct MEMNON retrieval without local
        LLM query expansion or synthesis.

        Args:
            retrieval_directives: One or more continuity elements/context requests
                                  (e.g., ["Alex & Emilia's relationship history", "What happened to Victor?"])
            chunk_id: The narrative chunk this context is being assembled for

        Returns dict with:
        - retrieved_context: The assembled contextual information (dict keyed by directive)
        - sources: List of chunk IDs used
        - queries: The direct MEMNON queries executed
        - retrieval_reasoning: Deterministic retrieval metadata
        """
        # Normalize to list
        if isinstance(retrieval_directives, str):
            retrieval_directives = [retrieval_directives]

        qa_logger.info(
            f"Processing {len(retrieval_directives)} retrieval directive(s) for chunk {chunk_id}"
        )

        # Load the specific chunk text when this helper is anchoring retrieval to
        # a continuation point. The text is used as an additional direct query.
        target_chunk_text = ""
        if chunk_id:
            try:
                chunk_result = (
                    self.memnon.get_chunk_by_id(chunk_id) if self.memnon else None
                )
                if chunk_result:
                    target_chunk_text = chunk_result.get(
                        "full_text", chunk_result.get("text", "")
                    )
                    qa_logger.info(f"Loaded target chunk {chunk_id}")
                else:
                    qa_logger.warning(f"Could not find chunk {chunk_id}")
                    raise ValueError(f"Target chunk {chunk_id} not found in database")
            except Exception as e:
                qa_logger.error(f"Failed to retrieve chunk {chunk_id}: {e}")
                raise
        # Process each directive sequentially and aggregate results
        all_results = {
            "chunk_id": chunk_id,
            "directives": {},  # Store all per-directive data here
            "sources": [],  # Combined sources from all directives
            "queries": [],  # Combined queries from all directives
        }

        # Process each retrieval directive independently
        for directive in retrieval_directives:
            directive_result = await self._process_single_directive(
                directive, chunk_id, target_chunk_text
            )

            # Store per-directive results
            all_results["directives"][directive] = {
                "retrieved_context": directive_result["retrieved_context"],
                "reasoning": directive_result["reasoning"],
                "sql_attempts": directive_result.get("sql_attempts", []),
                "search_progress": directive_result.get("search_progress", []),
                "sources": directive_result["sources"],
            }

            # Also aggregate sources and queries for convenience
            all_results["sources"].extend(directive_result["sources"])
            all_results["queries"].extend(directive_result["queries"])

        # Deduplicate sources while preserving order
        all_results["sources"] = list(dict.fromkeys(all_results["sources"]))

        return all_results

    async def answer_question(self, question: str) -> Dict[str, Any]:
        """
        Backward compatibility wrapper for retrieve_context.
        Converts old-style question into a retrieval directive.
        """
        qa_logger.warning(
            "answer_question is deprecated. Use retrieve_context with directives instead."
        )
        return await self.retrieve_context([question], chunk_id=None)

    async def _process_single_directive(
        self,
        directive: str,
        chunk_id: Optional[int],
        target_chunk_text: str = "",
    ) -> Dict[str, Any]:
        """
        Process a single retrieval directive with direct MEMNON search.

        Args:
            directive: The specific continuity element to retrieve
            chunk_id: The narrative chunk this is for
            target_chunk_text: Text from the target chunk, when available

        Returns:
            Dict with retrieved_context, sources, queries, deterministic reasoning,
            and direct MEMNON search metadata for this directive.
        """
        qa_logger.info(f"Processing directive: {directive[:50]}...")
        max_query_text_chars = 500

        def sanitize_query(q: str) -> str:
            import re

            q = re.sub(r"[\n\r\t]+", " ", q)
            q = re.sub(r"[\"'()?:;<>\\]", " ", q)
            q = re.sub(r"\s+", " ", q).strip()
            return q

        raw_queries: List[str] = [directive]
        if target_chunk_text:
            raw_queries.append(target_chunk_text[:max_query_text_chars])
        queries: List[str] = [sanitize_query(q) for q in raw_queries if q and q.strip()]
        queries = list(dict.fromkeys(queries))  # Deduplicate

        # Execute queries via MEMNON
        aggregated_results: Dict[str, Dict[str, Any]] = {}
        search_progress: List[Dict[str, Any]] = []

        for q in queries:
            try:
                result = self.memnon.query_memory(q, filters=None, k=8, use_hybrid=True)
                search_progress.append(
                    {
                        "query": q,
                        "result_count": result.get("metadata", {}).get(
                            "result_count", 0
                        ),
                    }
                )
                for item in result.get("results", []):
                    result_chunk_id = str(item.get("chunk_id") or item.get("id"))
                    if not result_chunk_id:
                        continue
                    if result_chunk_id not in aggregated_results:
                        aggregated_results[result_chunk_id] = {
                            "chunk_id": result_chunk_id,
                            "text": item.get("text", ""),
                            "metadata": item.get("metadata", {}),
                            "score": float(item.get("score", 0.0)),
                        }
                    else:
                        aggregated_results[result_chunk_id]["score"] = max(
                            aggregated_results[result_chunk_id]["score"],
                            float(item.get("score", 0.0)),
                        )
            except Exception as e:
                qa_logger.error(f"Search error for query '{q}': {e}")

        # Sort results by score and prepare for synthesis
        sorted_results = sorted(
            aggregated_results.values(), key=lambda x: x["score"], reverse=True
        )[
            :10
        ]  # Top 10 results

        reasoning = {
            "mode": "direct_memnon_retrieval",
            "query_count": len(queries),
            "target_chunk_id": chunk_id,
        }

        if not sorted_results:
            return {
                "retrieved_context": f"No relevant information found for: {directive}",
                "sources": [],
                "queries": queries,
                "reasoning": reasoning,
                "sql_attempts": [],
                "search_progress": search_progress,
            }

        # Format direct source excerpts instead of asking a local model to synthesize.
        context_parts = []
        for i, result in enumerate(sorted_results, 1):
            context_parts.append(
                f"[Source {i}] Chunk {result['chunk_id']} "
                f"(score: {result['score']:.2f})\n{result['text'][:700]}"
            )

        retrieved_context = f"Retrieval directive: {directive}\n\n" + "\n\n".join(
            context_parts
        )
        if target_chunk_text:
            retrieved_context += "\n\nContinuation anchor:\n" + target_chunk_text[:1000]

        # Extract chunk IDs from results
        source_ids = [
            int(r["chunk_id"]) for r in sorted_results if r["chunk_id"].isdigit()
        ]

        return {
            "retrieved_context": retrieved_context,
            "sources": source_ids,
            "queries": queries,
            "reasoning": reasoning,
            "sql_attempts": [],
            "search_progress": search_progress,
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
            "token_utilization": self.turn_context.phase_states.get(
                "payload_assembly", {}
            ).get("utilization_percentage", 0),
            "errors": self.turn_context.error_log,
            "apex_tokens": self.turn_context.phase_states.get("apex_generation", {}),
            "components": {
                "memnon": "available" if self.memnon else "unavailable",
                "logon": "available" if self.logon else "unavailable",
                "retrieval": "direct_memnon",
            },
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current status of LORE and its components"""
        return {
            "current_phase": self.current_phase.value,
            "components": {
                "memnon": self.memnon is not None,
                "logon": self.logon is not None,
                "retrieval": "direct_memnon",
                "token_manager": self.token_manager is not None,
                "turn_manager": self.turn_manager is not None,
                "memory_manager": self.memory_manager is not None,
            },
            "settings_loaded": bool(self.settings),
            "debug_mode": self.debug,
            "memory": (
                self.memory_manager.get_memory_summary() if self.memory_manager else {}
            ),
        }


# Command-line interface for testing
async def main():
    """Main entry point for testing LORE"""
    import argparse

    parser = argparse.ArgumentParser(description="LORE Agent - NEXUS Orchestrator")
    parser.add_argument(
        "retrieval_directives",
        nargs="*",
        help="One or more retrieval directives/continuity elements to process",
    )
    parser.add_argument(
        "--chunk",
        type=int,
        required=False,
        help="Narrative chunk ID to build context for",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--settings", help="Path to settings.json")
    parser.add_argument("--test", action="store_true", help="Run test turn cycle")
    parser.add_argument("--status", action="store_true", help="Show component status")
    parser.add_argument("--qa", help="(Deprecated) Use positional argument instead")
    parser.add_argument(
        "--keep-model",
        action="store_true",
        help="Ignored; contextual retrieval no longer loads LM Studio",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize LORE
    lore = LORE(settings_path=args.settings, debug=args.debug)

    if args.status:
        # Show status
        status = lore.get_status()
        print("\n" + "=" * 60)
        print("LORE STATUS")
        print("=" * 60)
        print(json.dumps(status, indent=2))

    elif args.qa or args.retrieval_directives:
        # Contextual retrieval mode (formerly Q&A)
        directives = (
            args.retrieval_directives
            if args.retrieval_directives
            else [args.qa] if args.qa else []
        )

        if directives and not args.chunk:
            print(
                "Error: --chunk parameter is required when providing retrieval directives"
            )
            print(
                "Usage: python lore.py 'directive1' 'directive2' ... --chunk <chunk_id>"
            )
            return

        # Set keep-model flag BEFORE retrieval
        if args.keep_model:
            logger.info(
                "--keep-model ignored; contextual retrieval no longer loads LM Studio"
            )

        logger.info(
            f"Processing {len(directives)} retrieval directive(s) for chunk {args.chunk}"
        )
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
        total_sql = sum(
            len(d.get("sql_attempts", []))
            for d in result.get("directives", {}).values()
        )
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

        print("\n" + "=" * 60)
        print("LORE TEST RESULTS")
        print("=" * 60)
        print(f"\nUser Input: {test_input}")
        print(f"\nGenerated Response:\n{response}")
        print(f"\nTurn Summary:\n{json.dumps(lore.get_turn_summary(), indent=2)}")

    else:
        # Interactive mode
        print("\n" + "=" * 60)
        print("LORE AGENT - Interactive Mode")
        print("=" * 60)
        print("Commands: 'quit', 'status', 'summary'\n")

        while True:
            try:
                user_input = input("\n> ").strip()

                if user_input.lower() == "quit":
                    break
                elif user_input.lower() == "status":
                    print(json.dumps(lore.get_status(), indent=2))
                    continue
                elif user_input.lower() == "summary":
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
