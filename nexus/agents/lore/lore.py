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
from typing import Dict, Optional, Any
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
            
            # Phase 5: Cold Distillation
            self.current_phase = TurnPhase.COLD_DISTILLATION
            await self.turn_manager.perform_cold_distillation(self.turn_context)
            
            # Phase 6: Payload Assembly
            self.current_phase = TurnPhase.PAYLOAD_ASSEMBLY
            await self.turn_manager.assemble_context_payload(self.turn_context)
            
            # Phase 7: Apex AI Generation
            self.current_phase = TurnPhase.APEX_GENERATION
            response = await self.turn_manager.call_apex_ai(self.turn_context)
            
            # Phase 8: Response Integration
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