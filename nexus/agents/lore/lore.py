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

import logging
import json
import time
from typing import Dict, List, Optional, Any, Union, Tuple
from pathlib import Path
from enum import Enum

# Letta framework imports
from letta.agents.base_agent import BaseAgent
from letta.schemas.message import Message
from letta.schemas.letta_message import UserMessage
from letta.schemas.agent import AgentState
from letta.schemas.user import User
from letta.services.agent_manager import AgentManager
from letta.services.message_manager import MessageManager

# llama-cpp-python for local LLM
try:
    from llama_cpp import Llama
except ImportError:
    raise ImportError("llama-cpp-python not installed. Run: CMAKE_ARGS='-DLLAMA_METAL=on' pip install llama-cpp-python")

# Import utility modules
from ..memnon.memnon import MEMNON
# TODO: Import other utilities when converted from agents
# from ..psyche.psyche_utility import PsycheUtility
# from ..nemesis.nemesis_utility import NemesisUtility
# from ..gaia.gaia_utility import GaiaUtility
# from ..logon.logon_utility import LogonUtility

# Configure logger
logger = logging.getLogger("nexus.lore")


class TurnPhase(Enum):
    """Phases of the turn cycle"""
    USER_INPUT = "user_input"
    WARM_ANALYSIS = "warm_analysis"
    WORLD_STATE = "world_state"
    DEEP_QUERIES = "deep_queries"
    COLD_DISTILLATION = "cold_distillation"
    PAYLOAD_ASSEMBLY = "payload_assembly"
    APEX_GENERATION = "apex_generation"
    INTEGRATION = "integration"
    IDLE = "idle"


class LORE(BaseAgent):
    """
    Central orchestration agent for the NEXUS system.
    Manages the complete turn cycle and coordinates all utility modules.
    """
    
    def __init__(
        self,
        agent_id: str,
        agent_state: AgentState,
        user: User,
        message_manager: MessageManager,
        agent_manager: AgentManager,
        settings: Optional[Dict[str, Any]] = None,
        debug: bool = False
    ):
        """
        Initialize LORE agent.
        
        Args:
            agent_id: Unique identifier for this agent instance
            agent_state: Agent state from Letta framework
            user: User information
            message_manager: Message management service
            agent_manager: Agent management service
            settings: Configuration settings (loaded from settings.json)
            debug: Enable debug logging
        """
        # Initialize base agent
        super().__init__(
            agent_id=agent_id,
            openai_client=None,  # We'll use llama-cpp instead
            message_manager=message_manager,
            agent_manager=agent_manager,
            actor=user
        )
        
        self.agent_state = agent_state
        self.settings = settings or {}
        self.debug = debug
        
        # Configure logging
        if debug:
            logger.setLevel(logging.DEBUG)
        
        # Initialize local LLM
        self.llm = self._initialize_llm()
        
        # Initialize utility modules
        self._initialize_utilities()
        
        # Turn cycle state
        self.current_phase = TurnPhase.IDLE
        self.turn_context = {}
        
        logger.info(f"LORE agent initialized (id: {agent_id})")
    
    def _initialize_llm(self) -> Llama:
        """
        Initialize the local LLM using llama-cpp-python.
        
        Returns:
            Initialized Llama model instance
        """
        llm_config = self.settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {})
        
        # Get model path
        model_path = llm_config.get("model_path")
        if not model_path:
            raise ValueError("No model_path specified in LORE llm settings")
        
        # Resolve model path relative to project root
        model_path = Path(model_path)
        if not model_path.is_absolute():
            model_path = Path.cwd() / model_path
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        logger.info(f"Loading LLM from: {model_path}")
        
        # Initialize llama-cpp with configuration
        try:
            llm = Llama(
                model_path=str(model_path),
                n_ctx=llm_config.get("n_ctx", 32768),
                n_threads=llm_config.get("n_threads", 12),
                n_gpu_layers=llm_config.get("n_gpu_layers", -1),  # -1 = all layers on GPU
                seed=llm_config.get("seed", -1),
                f16_kv=llm_config.get("f16_kv", True),
                verbose=llm_config.get("verbose", False)
            )
            logger.info("LLM initialized successfully")
            return llm
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            raise
    
    def _initialize_utilities(self):
        """Initialize utility modules (MEMNON, PSYCHE, etc.)"""
        logger.info("Initializing utility modules...")
        
        # Initialize MEMNON (already exists as a utility)
        try:
            # MEMNON needs interface, agent_state, user, and db_url
            memnon_settings = self.settings.get("Agent Settings", {}).get("MEMNON", {})
            db_url = memnon_settings.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
            
            # Create a minimal interface for MEMNON
            from types import SimpleNamespace
            interface = SimpleNamespace(
                assistant_message=lambda x: logger.info(f"MEMNON: {x}"),
                error_message=lambda x: logger.error(f"MEMNON Error: {x}")
            )
            
            self.memnon = MEMNON(
                interface=interface,
                agent_state=self.agent_state,
                user=self.actor,
                db_url=db_url,
                debug=self.debug
            )
            logger.info("MEMNON utility initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MEMNON: {e}")
            self.memnon = None
        
        # Initialize placeholders for other utilities
        self.psyche = None  # TODO: Convert from agent to utility
        self.nemesis = None  # TODO: Convert from agent to utility
        self.gaia = None  # TODO: Convert from agent to utility
        self.logon = None  # TODO: Convert from agent to utility
        
        logger.info("Utility initialization complete")
    
    def _query_llm(self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        """
        Query the local LLM with a prompt.
        
        Args:
            prompt: The prompt to send to the LLM
            temperature: Optional temperature parameter
            max_tokens: Optional max tokens parameter
            
        Returns:
            LLM response as string
        """
        llm_config = self.settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {})
        
        # Use provided parameters or fall back to config
        temp = temperature if temperature is not None else llm_config.get("temperature", 0.7)
        max_tok = max_tokens if max_tokens is not None else llm_config.get("max_tokens", 2048)
        
        logger.debug(f"Querying LLM with temp={temp}, max_tokens={max_tok}")
        
        try:
            # Create completion using llama-cpp
            response = self.llm(
                prompt,
                max_tokens=max_tok,
                temperature=temp,
                top_p=llm_config.get("top_p", 0.9),
                top_k=llm_config.get("top_k", 40),
                repeat_penalty=llm_config.get("repeat_penalty", 1.1),
                echo=False  # Don't include prompt in response
            )
            
            # Extract text from response
            text = response['choices'][0]['text'].strip()
            logger.debug(f"LLM response length: {len(text)} chars")
            return text
            
        except Exception as e:
            logger.error(f"Error querying LLM: {e}")
            raise
    
    async def step(self, input_message: UserMessage) -> List[Message]:
        """
        Main execution loop for LORE agent.
        Orchestrates the complete turn cycle.
        
        Args:
            input_message: User input message
            
        Returns:
            List of messages generated during the turn
        """
        logger.info(f"Starting turn cycle with user input: {input_message.text[:100]}...")
        
        # Initialize turn context
        self.turn_context = {
            "user_input": input_message,
            "start_time": time.time(),
            "messages": []
        }
        
        try:
            # Phase 1: User Input Processing
            self.current_phase = TurnPhase.USER_INPUT
            await self._process_user_input(input_message)
            
            # Phase 2: Warm Analysis
            self.current_phase = TurnPhase.WARM_ANALYSIS
            await self._perform_warm_analysis()
            
            # Phase 3: World State Report
            self.current_phase = TurnPhase.WORLD_STATE
            await self._generate_world_state_report()
            
            # Phase 4: Deep Queries
            self.current_phase = TurnPhase.DEEP_QUERIES
            await self._execute_deep_queries()
            
            # Phase 5: Cold Distillation
            self.current_phase = TurnPhase.COLD_DISTILLATION
            await self._perform_cold_distillation()
            
            # Phase 6: Payload Assembly
            self.current_phase = TurnPhase.PAYLOAD_ASSEMBLY
            context_payload = await self._assemble_context_payload()
            
            # Phase 7: Apex AI Generation
            self.current_phase = TurnPhase.APEX_GENERATION
            apex_response = await self._call_apex_ai(context_payload)
            
            # Phase 8: Response Integration
            self.current_phase = TurnPhase.INTEGRATION
            messages = await self._integrate_response(apex_response)
            
            # Return to idle
            self.current_phase = TurnPhase.IDLE
            
            # Log turn completion
            elapsed = time.time() - self.turn_context["start_time"]
            logger.info(f"Turn cycle completed in {elapsed:.2f} seconds")
            
            return messages
            
        except Exception as e:
            logger.error(f"Error in turn cycle phase {self.current_phase}: {e}")
            self.current_phase = TurnPhase.IDLE
            raise
    
    async def step_stream(self, input_message: UserMessage):
        """
        Streaming version of step (not implemented yet).
        """
        raise NotImplementedError("Streaming not yet implemented for LORE")
    
    # Turn cycle phase implementations
    
    async def _process_user_input(self, input_message: UserMessage):
        """Phase 1: Process and validate user input"""
        logger.debug("Processing user input...")
        # TODO: Implement input processing
        pass
    
    async def _perform_warm_analysis(self):
        """Phase 2: Analyze recent narrative context"""
        logger.debug("Performing warm analysis...")
        # TODO: Implement warm analysis
        pass
    
    async def _generate_world_state_report(self):
        """Phase 3: Generate current world state report"""
        logger.debug("Generating world state report...")
        # TODO: Implement world state report generation
        pass
    
    async def _execute_deep_queries(self):
        """Phase 4: Execute deep memory queries"""
        logger.debug("Executing deep queries...")
        # TODO: Implement deep query execution
        pass
    
    async def _perform_cold_distillation(self):
        """Phase 5: Distill retrieved information"""
        logger.debug("Performing cold distillation...")
        # TODO: Implement cold distillation
        pass
    
    async def _assemble_context_payload(self) -> Dict[str, Any]:
        """Phase 6: Assemble final context payload"""
        logger.debug("Assembling context payload...")
        # TODO: Implement context assembly
        return {}
    
    async def _call_apex_ai(self, context_payload: Dict[str, Any]) -> str:
        """Phase 7: Call Apex AI for narrative generation"""
        logger.debug("Calling Apex AI...")
        # TODO: Implement Apex AI call
        return "Placeholder narrative response"
    
    async def _integrate_response(self, apex_response: str) -> List[Message]:
        """Phase 8: Integrate Apex response and update state"""
        logger.debug("Integrating response...")
        # TODO: Implement response integration
        return []