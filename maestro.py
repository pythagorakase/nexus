#!/usr/bin/env python3
"""
maestro.py: Central Orchestrator for Night City Stories

This module serves as the central coordinator for the agent-based narrative intelligence system.
It manages the communication between specialized agents, maintains conversation state and history,
implements an event-based communication protocol, and handles error recovery.

Usage:
    import maestro
    
    # Initialize the orchestrator
    conductor = maestro.Maestro()
    
    # Process user input to generate narrative
    narrative = conductor.process_input("What happens next?")
    
    # Or run standalone for testing
    python maestro.py --test
"""

import os
import sys
import json
import logging
import argparse
import time
import traceback
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Set

# Try to import agent modules and config
try:
    # Import configuration manager
    import config_manager as config
    
    # Import database adapters
    import db_sqlite
    import db_chroma
    import memnon
    
    # Import agent modules - these should extend BaseAgent
    # Uncomment as they become available
    from agents.lore import ContextManager
    from agents.psyche import CharacterPsychologist
    from agents.gaia import WorldTracker
    from agents.logon import NarrativeGenerator
except ImportError as e:
    print(f"Warning: Failed to import a required module: {e}")
    # Set unavailable modules to None for optional dependency handling
    # This allows the maestro to initialize even if some agents aren't available
    if 'config_manager' not in sys.modules:
        config = None
    if 'db_sqlite' not in sys.modules:
        db_sqlite = None
    if 'db_chroma' not in sys.modules:
        db_chroma = None
    if 'memnon' not in sys.modules:
        memnon = None
    if 'agents.lore' not in sys.modules:
        ContextManager = None
    if 'agents.psyche' not in sys.modules:
        CharacterPsychologist = None
    if 'agents.gaia' not in sys.modules:
        WorldTracker = None
    if 'agents.logon' not in sys.modules:
        NarrativeGenerator = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("maestro.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("maestro")

# Default settings (can be overridden by config_manager)
DEFAULT_SETTINGS = {
    "agents": {
        "enable_all_agents": True,
        "lore": {
            "enabled": True,
            "model": "llama3-70b",
            "priority": 1
        },
        "psyche": {
            "enabled": True,
            "model": "phi3-medium",
            "priority": 2
        },
        "gaia": {
            "enabled": True,
            "model": "llama3-70b",
            "priority": 3
        },
        "logon": {
            "enabled": True,
            "model": "gpt-4o",
            "priority": 4
        }
    },
    "orchestration": {
        "max_iterations": 3,
        "timeout": 60,
        "parallel_execution": False,
        "communication_protocol": "json",
        "error_recovery": "fallback"
    },
    "state_management": {
        "save_state": True,
        "state_file": "narrative_state.json",
        "history_limit": 10,
        "compress_old_history": True
    }
}

class AgentMessage:
    """
    Message class for standardized communication between agents
    
    This class conforms to the BaseAgent protocol by providing a dictionary-like
    interface expected by the process_message method in BaseAgent.
    """
    
    def __init__(self, 
                sender: str,
                recipient: str,
                message_type: str,
                content: Dict[str, Any],
                timestamp: float = None):
        """
        Initialize an agent message
        
        Args:
            sender: Name of the sending agent
            recipient: Name of the receiving agent ('all' for broadcast)
            message_type: Type of message (e.g., 'request', 'response', 'error')
            content: Message content as a dictionary
            timestamp: Optional message timestamp (defaults to current time)
        """
        self.sender = sender
        self.recipient = recipient
        self.message_type = message_type
        self.content = content
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.id = f"{sender}_{recipient}_{message_type}_{int(self.timestamp)}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "content": self.content,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """Create message from dictionary"""
        return cls(
            sender=data["sender"],
            recipient=data["recipient"],
            message_type=data["message_type"],
            content=data["content"],
            timestamp=data.get("timestamp")
        )
    
    def __str__(self) -> str:
        """String representation of message"""
        return f"Message from {self.sender} to {self.recipient} ({self.message_type}): {json.dumps(self.content, indent=2)}"
    
    # For compatibility with BaseAgent protocol
    def get(self, key: str, default: Any = None) -> Any:
        """
        Dictionary-like access to message attributes
        
        Args:
            key: Attribute name to get
            default: Default value if the attribute doesn't exist
            
        Returns:
            Attribute value if it exists, default otherwise
        """
        if key == "content":
            return self.content
        elif key == "message_type":
            return self.message_type
        elif hasattr(self, key):
            return getattr(self, key)
        return default
    
    # For compatibility with dictionary access
    def __getitem__(self, key: str) -> Any:
        """
        Implement dict-like access with [] operator
        
        Args:
            key: Key to get
            
        Returns:
            Value for the key
            
        Raises:
            KeyError: If key doesn't exist
        """
        if key == "content":
            return self.content
        elif key == "message_type":
            return self.message_type
        elif hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

class AgentRegistry:
    """
    Registry for managing available agents
    """
    
    def __init__(self):
        """Initialize the agent registry"""
        self.agents = {}
        self.settings = {}
    
    def register_agent(self, name: str, agent_instance: Any, metadata: Dict[str, Any] = None) -> None:
        """
        Register an agent in the registry
        
        Args:
            name: Name of the agent
            agent_instance: Instance of the agent
            metadata: Optional metadata about the agent
        """
        if metadata is None:
            metadata = {}
        
        self.agents[name] = {
            "instance": agent_instance,
            "metadata": metadata,
            "enabled": metadata.get("enabled", True),
            "last_active": time.time()
        }
        
        logger.info(f"Registered agent: {name}")
    
    def connect_agents(self, maestro_instance: Any) -> None:
        """
        Connect all registered agents to maestro for inter-agent communication.
        
        This method sets a reference to the maestro instance in each agent,
        enabling them to use the registry for message routing.
        
        Args:
            maestro_instance: Reference to the maestro orchestrator
        """
        for name, agent_data in self.agents.items():
            agent_instance = agent_data["instance"]
            # Check if agent has the set_maestro method (implements BaseAgent)
            if hasattr(agent_instance, 'set_maestro') and callable(getattr(agent_instance, 'set_maestro')):
                try:
                    agent_instance.set_maestro(maestro_instance)
                    logger.debug(f"Connected agent '{name}' to maestro")
                except Exception as e:
                    logger.error(f"Failed to connect agent '{name}' to maestro: {str(e)}")
            else:
                logger.warning(f"Agent '{name}' does not implement set_maestro method, communication may be limited")
        
        logger.info(f"Connected {len(self.agents)} agents to maestro")
    
    def get_agent(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get an agent from the registry
        
        Args:
            name: Name of the agent
            
        Returns:
            Agent data dictionary if found, None otherwise
        """
        return self.agents.get(name)
    
    def is_agent_enabled(self, name: str) -> bool:
        """Check if an agent is enabled"""
        agent_data = self.agents.get(name)
        return agent_data is not None and agent_data["enabled"]
    
    def enable_agent(self, name: str) -> bool:
        """Enable an agent"""
        if name in self.agents:
            self.agents[name]["enabled"] = True
            logger.info(f"Enabled agent: {name}")
            return True
        return False
    
    def disable_agent(self, name: str) -> bool:
        """Disable an agent"""
        if name in self.agents:
            self.agents[name]["enabled"] = False
            logger.info(f"Disabled agent: {name}")
            return True
        return False
    
    def list_agents(self) -> List[Dict[str, Any]]:
        """Get a list of all registered agents with their status"""
        return [
            {
                "name": name,
                "enabled": data["enabled"],
                "last_active": data["last_active"],
                "metadata": data["metadata"]
            }
            for name, data in self.agents.items()
        ]
    
    def get_enabled_agents(self) -> List[str]:
        """Get a list of names of all enabled agents"""
        return [name for name, data in self.agents.items() if data["enabled"]]

class NarrativeState:
    """
    Maintains the current state of the narrative
    """
    
    def __init__(self, state_file: str = None):
        """
        Initialize narrative state
        
        Args:
            state_file: Optional path to save state
        """
        self.state_file = state_file
        self.current_episode = "S01E01"
        self.conversation_history = []
        self.entity_states = {}
        self.message_history = []
        self.metadata = {
            "created_at": time.time(),
            "updated_at": time.time()
        }
    
    def add_user_message(self, message: str) -> None:
        """Add a user message to the conversation history"""
        self.conversation_history.append({
            "role": "user",
            "content": message,
            "timestamp": time.time()
        })
        self.metadata["updated_at"] = time.time()
    
    def add_system_message(self, message: str) -> None:
        """Add a system message to the conversation history"""
        self.conversation_history.append({
            "role": "system",
            "content": message,
            "timestamp": time.time()
        })
        self.metadata["updated_at"] = time.time()
    
    def add_agent_message(self, message: AgentMessage) -> None:
        """Add an agent message to the message history"""
        self.message_history.append(message.to_dict())
        self.metadata["updated_at"] = time.time()
    
    def set_episode(self, episode: str) -> None:
        """Set the current episode"""
        self.current_episode = episode
        self.metadata["updated_at"] = time.time()
    
    def update_entity_state(self, entity_type: str, entity_id: str, state: Dict[str, Any]) -> None:
        """Update an entity's state"""
        if entity_type not in self.entity_states:
            self.entity_states[entity_type] = {}
        
        self.entity_states[entity_type][entity_id] = state
        self.metadata["updated_at"] = time.time()
    
    def get_recent_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get the most recent conversation history"""
        return self.conversation_history[-limit:] if limit > 0 else self.conversation_history
    
    def save(self) -> bool:
        """Save the state to a file"""
        if not self.state_file:
            return False
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump({
                    "current_episode": self.current_episode,
                    "conversation_history": self.conversation_history,
                    "entity_states": self.entity_states,
                    "metadata": self.metadata
                }, f, indent=2)
            
            logger.info(f"Saved narrative state to {self.state_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving narrative state: {e}")
            return False
    
    def load(self) -> bool:
        """Load the state from a file"""
        if not self.state_file or not os.path.exists(self.state_file):
            return False
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            
            self.current_episode = data.get("current_episode", "S01E01")
            self.conversation_history = data.get("conversation_history", [])
            self.entity_states = data.get("entity_states", {})
            self.metadata = data.get("metadata", {
                "created_at": time.time(),
                "updated_at": time.time()
            })
            
            logger.info(f"Loaded narrative state from {self.state_file}")
            return True
        except Exception as e:
            logger.error(f"Error loading narrative state: {e}")
            return False

class Maestro:
    """
    Central orchestrator for the agent-based narrative intelligence system
    """
    
    def __init__(self, settings: Dict[str, Any] = None):
        """
        Initialize the orchestrator
        
        Args:
            settings: Optional settings dictionary
        """
        # Load settings
        self.settings = DEFAULT_SETTINGS.copy()
        if settings:
            self._update_settings(settings)
        elif config:
            # Try to load from config_manager
            orchestration_config = config.get_section("orchestration")
            if orchestration_config:
                self.settings["orchestration"].update(orchestration_config)
            
            agents_config = config.get_section("agents")
            if agents_config:
                self.settings["agents"].update(agents_config)
            
            state_config = config.get_section("state_management")
            if state_config:
                self.settings["state_management"].update(state_config)
        
        # Initialize agent registry
        self.agent_registry = AgentRegistry()
        
        # Initialize narrative state
        state_file = self.settings["state_management"].get("state_file")
        self.state = NarrativeState(state_file)
        
        # Load existing state if available
        if state_file and self.settings["state_management"].get("save_state", True):
            self.state.load()
        
        # Initialize message queue for agent communication
        self.message_queue = []
        
        # Initialize agent instances
        self._initialize_agents()
        
        logger.info("Maestro initialized")
    
    def _update_settings(self, settings: Dict[str, Any]) -> None:
        """
        Update settings with user-provided values
        
        Args:
            settings: New settings to apply
        """
        # Recursive dictionary update
        def update_dict(target, source):
            for key, value in source.items():
                if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                    update_dict(target[key], value)
                else:
                    target[key] = value
        
        update_dict(self.settings, settings)
    
    def _initialize_agents(self) -> None:
        """
        Initialize and register all enabled agents
        
        Each agent should extend BaseAgent and implement the required methods:
        - process_message(message)
        - handle_request(content)
        - handle_response(content)
        - handle_error(content)
        """
        if not self.settings["agents"].get("enable_all_agents", True):
            logger.info("Agent initialization skipped (enable_all_agents is False)")
            return
        
        # Initialize Lore (Context Manager)
        if self.settings["agents"].get("lore", {}).get("enabled", True):
            try:
                if ContextManager:
                    # Initialize with settings
                    lore_settings = self.settings["agents"].get("lore", {})
                    lore_agent = ContextManager(lore_settings)
                    
                    self.agent_registry.register_agent(
                        name="lore",
                        agent_instance=lore_agent,
                        metadata=lore_settings
                    )
                    logger.info("Registered Lore agent (ContextManager)")
                else:
                    # Use placeholder implementation
                    from agent_base import BaseAgent
                    
                    class LorePlaceholder(BaseAgent):
                        def process_message(self, message):
                            message_type = message.get("message_type", "request")
                            content = message.get("content", {})
                            
                            if message_type == "request":
                                return self.handle_request(content)
                            elif message_type == "response":
                                return self.handle_response(content)
                            elif message_type == "error":
                                return self.handle_error(content)
                            else:
                                return {"error": f"Unknown message type: {message_type}"}
                        
                        def handle_request(self, content):
                            return {
                                "response": "Lore agent placeholder response",
                                "context_package": {
                                    "relevant_memories": [],
                                    "entity_mentions": []
                                }
                            }
                        
                        def handle_response(self, content):
                            return {"response": "Acknowledged response"}
                        
                        def handle_error(self, content):
                            return {"response": "Acknowledged error"}
                    
                    lore_settings = self.settings["agents"].get("lore", {})
                    lore_agent = LorePlaceholder(lore_settings)
                    
                    self.agent_registry.register_agent(
                        name="lore",
                        agent_instance=lore_agent,
                        metadata=lore_settings
                    )
                    logger.info("Registered Lore agent (placeholder implementation)")
            except Exception as e:
                logger.error(f"Failed to initialize Lore agent: {e}")
                logger.error(traceback.format_exc())
        
        # Initialize Psyche (Character Psychologist)
        if self.settings["agents"].get("psyche", {}).get("enabled", True):
            try:
                if CharacterPsychologist:
                    # Initialize with settings
                    psyche_settings = self.settings["agents"].get("psyche", {})
                    psyche_agent = CharacterPsychologist(psyche_settings)
                    
                    self.agent_registry.register_agent(
                        name="psyche",
                        agent_instance=psyche_agent,
                        metadata=psyche_settings
                    )
                    logger.info("Registered Psyche agent (CharacterPsychologist)")
                else:
                    # Use placeholder implementation
                    from agent_base import BaseAgent
                    
                    class PsychePlaceholder(BaseAgent):
                        def process_message(self, message):
                            message_type = message.get("message_type", "request")
                            content = message.get("content", {})
                            
                            if message_type == "request":
                                return self.handle_request(content)
                            elif message_type == "response":
                                return self.handle_response(content)
                            elif message_type == "error":
                                return self.handle_error(content)
                            else:
                                return {"error": f"Unknown message type: {message_type}"}
                        
                        def handle_request(self, content):
                            return {
                                "response": "Psyche agent placeholder response",
                                "character_insights": {
                                    "entities": []
                                }
                            }
                        
                        def handle_response(self, content):
                            return {"response": "Acknowledged response"}
                        
                        def handle_error(self, content):
                            return {"response": "Acknowledged error"}
                    
                    psyche_settings = self.settings["agents"].get("psyche", {})
                    psyche_agent = PsychePlaceholder(psyche_settings)
                    
                    self.agent_registry.register_agent(
                        name="psyche",
                        agent_instance=psyche_agent,
                        metadata=psyche_settings
                    )
                    logger.info("Registered Psyche agent (placeholder implementation)")
            except Exception as e:
                logger.error(f"Failed to initialize Psyche agent: {e}")
                logger.error(traceback.format_exc())
        
        # Initialize Gaia (World State Tracker)
        if self.settings["agents"].get("gaia", {}).get("enabled", True):
            try:
                if WorldTracker:
                    # Initialize with settings
                    gaia_settings = self.settings["agents"].get("gaia", {})
                    gaia_agent = WorldTracker(gaia_settings)
                    
                    self.agent_registry.register_agent(
                        name="gaia",
                        agent_instance=gaia_agent,
                        metadata=gaia_settings
                    )
                    logger.info("Registered Gaia agent (WorldTracker)")
                else:
                    # Use placeholder implementation
                    from agent_base import BaseAgent
                    
                    class GaiaPlaceholder(BaseAgent):
                        def process_message(self, message):
                            message_type = message.get("message_type", "request")
                            content = message.get("content", {})
                            
                            if message_type == "request":
                                return self.handle_request(content)
                            elif message_type == "response":
                                return self.handle_response(content)
                            elif message_type == "error":
                                return self.handle_error(content)
                            else:
                                return {"error": f"Unknown message type: {message_type}"}
                        
                        def handle_request(self, content):
                            return {
                                "response": "Gaia agent placeholder response",
                                "entity_states": {
                                    "entities": []
                                }
                            }
                        
                        def handle_response(self, content):
                            return {"response": "Acknowledged response"}
                        
                        def handle_error(self, content):
                            return {"response": "Acknowledged error"}
                    
                    gaia_settings = self.settings["agents"].get("gaia", {})
                    gaia_agent = GaiaPlaceholder(gaia_settings)
                    
                    self.agent_registry.register_agent(
                        name="gaia",
                        agent_instance=gaia_agent,
                        metadata=gaia_settings
                    )
                    logger.info("Registered Gaia agent (placeholder implementation)")
            except Exception as e:
                logger.error(f"Failed to initialize Gaia agent: {e}")
                logger.error(traceback.format_exc())
        
        # Initialize Logon (Narrative Generator)
        if self.settings["agents"].get("logon", {}).get("enabled", True):
            try:
                if NarrativeGenerator:
                    # Initialize with settings
                    logon_settings = self.settings["agents"].get("logon", {})
                    logon_agent = NarrativeGenerator(logon_settings)
                    
                    self.agent_registry.register_agent(
                        name="logon",
                        agent_instance=logon_agent,
                        metadata=logon_settings
                    )
                    logger.info("Registered Logon agent (NarrativeGenerator)")
                else:
                    # Use placeholder implementation
                    from agent_base import BaseAgent
                    
                    class LogonPlaceholder(BaseAgent):
                        def process_message(self, message):
                            message_type = message.get("message_type", "request")
                            content = message.get("content", {})
                            
                            if message_type == "request":
                                return self.handle_request(content)
                            elif message_type == "response":
                                return self.handle_response(content)
                            elif message_type == "error":
                                return self.handle_error(content)
                            else:
                                return {"error": f"Unknown message type: {message_type}"}
                        
                        def handle_request(self, content):
                            request_type = content.get("type", "unknown")
                            if request_type == "generate_narrative":
                                context_package = content.get("context_package", {})
                                # Simple placeholder narrative generation
                                user_input = context_package.get("user_input", "")
                                return {
                                    "response": f"This is a placeholder narrative response to: {user_input}",
                                    "narrative": f"This is a placeholder narrative response to: {user_input}"
                                }
                            return {"response": "Unknown request type"}
                        
                        def handle_response(self, content):
                            return {"response": "Acknowledged response"}
                        
                        def handle_error(self, content):
                            return {"response": "Acknowledged error"}
                    
                    logon_settings = self.settings["agents"].get("logon", {})
                    logon_agent = LogonPlaceholder(logon_settings)
                    
                    self.agent_registry.register_agent(
                        name="logon",
                        agent_instance=logon_agent,
                        metadata=logon_settings
                    )
                    logger.info("Registered Logon agent (placeholder implementation)")
            except Exception as e:
                logger.error(f"Failed to initialize Logon agent: {e}")
                logger.error(traceback.format_exc())
        
        # After all agents are registered, connect them to maestro
        self.agent_registry.connect_agents(self)
        logger.info("All agents connected to maestro for inter-agent communication")
    
    def send_message(self, message: AgentMessage) -> bool:
        """
        Send a message to an agent
        
        Args:
            message: The message to send
            
        Returns:
            True if the message was sent successfully, False otherwise
        """
        # Log the message for debugging
        logger.debug(f"Sending message: {message}")
        
        # Add to state history
        self.state.add_agent_message(message)
        
        # If recipient is 'all', broadcast to all enabled agents
        if message.recipient == "all":
            success = False
            for agent_name in self.agent_registry.get_enabled_agents():
                if agent_name != message.sender:  # Don't send to self
                    individual_message = AgentMessage(
                        sender=message.sender,
                        recipient=agent_name,
                        message_type=message.message_type,
                        content=message.content,
                        timestamp=message.timestamp
                    )
                    # Add to queue
                    self.message_queue.append(individual_message)
                    success = True
            return success
        
        # Check if the recipient agent is enabled
        if not self.agent_registry.is_agent_enabled(message.recipient):
            logger.warning(f"Cannot send message to disabled agent: {message.recipient}")
            return False
        
        # Add to queue
        self.message_queue.append(message)
        return True
    
    def process_message_queue(self) -> Dict[str, Any]:
        """
        Process all messages in the queue
        
        Returns:
            Dictionary with results from all agents
        """
        results = {}
        
        # Process messages with the configured execution style
        parallel = self.settings["orchestration"].get("parallel_execution", False)
        
        if parallel:
            # Parallel execution would be implemented here if needed
            # For now, just process sequentially
            pass
        
        # Process messages sequentially
        while self.message_queue:
            message = self.message_queue.pop(0)
            recipient = message.recipient
            
            try:
                # Get the recipient agent
                agent = self.agent_registry.get_agent(recipient)
                if not agent:
                    logger.warning(f"Agent not found or disabled: {recipient}")
                    continue
                
                # Process the message using the BaseAgent protocol
                # BaseAgent.process_message expects an object with message_type and content
                # attributes or dictionary-like access
                response = agent.process_message(message)
                
                # Store the result
                results[recipient] = response
                
                # Create response message if needed
                if isinstance(response, dict) and "response" in response:
                    # Create response message conforming to BaseAgent protocol
                    response_message = AgentMessage(
                        sender=recipient,
                        recipient=message.sender,
                        message_type="response",
                        content=response
                    )
                    self.message_queue.append(response_message)
                
            except Exception as e:
                logger.error(f"Error processing message for {recipient}: {e}")
                logger.error(traceback.format_exc())
                
                # Create error message conforming to BaseAgent protocol
                error_message = AgentMessage(
                    sender=recipient,
                    recipient=message.sender,
                    message_type="error",
                    content={"error": str(e), "traceback": traceback.format_exc()}
                )
                self.message_queue.append(error_message)
                
                # If using fallback error recovery, attempt to use a placeholder response
                if self.settings["orchestration"].get("error_recovery") == "fallback":
                    results[recipient] = {
                        "response": f"Error in {recipient} agent: {str(e)}",
                        "error": str(e),
                        "is_fallback": True
                    }
        
        return results
    
    def process_input(self, user_input: str) -> str:
        """
        Process user input to generate narrative
        
        Args:
            user_input: User's input text
            
        Returns:
            Generated narrative text
        """
        # Add user input to state
        self.state.add_user_message(user_input)
        
        try:
            # Create initial message to Lore agent
            initial_message = AgentMessage(
                sender="maestro",
                recipient="lore",
                message_type="request",
                content={
                    "type": "user_input",
                    "text": user_input,
                    "current_episode": self.state.current_episode
                }
            )
            
            # Send the message
            self.send_message(initial_message)
            
            # Process message queue to get context
            context_results = self.process_message_queue()
            
            # Extract context package from Lore's response
            lore_response = context_results.get("lore", {})
            context_package = lore_response.get("context_package", {})
            
            if not context_package and "content" in lore_response:
                # Try to extract from nested content if available
                context_package = lore_response["content"].get("context_package", {})
            
            # Get character insights from Psyche if needed
            character_insights = {}
            if self.agent_registry.is_agent_enabled("psyche"):
                # Extract entity mentions for focused analysis
                entity_mentions = self._extract_entity_mentions(user_input, context_package)
                
                # Create message to Psyche agent
                psyche_message = AgentMessage(
                    sender="maestro",
                    recipient="psyche",
                    message_type="request",
                    content={
                        "type": "narrative_analysis",
                        "text": user_input,
                        "episode": self.state.current_episode,
                        "entities": entity_mentions
                    }
                )
                
                self.send_message(psyche_message)
                psyche_results = self.process_message_queue()
                character_insights = psyche_results.get("psyche", {})
            
            # Get world state information from Gaia if needed
            world_state = {}
            if self.agent_registry.is_agent_enabled("gaia"):
                # Extract entity mentions for state queries
                entity_mentions = self._extract_entity_mentions(user_input, context_package)
                
                if entity_mentions:
                    # Create message to Gaia agent
                    gaia_message = AgentMessage(
                        sender="maestro",
                        recipient="gaia",
                        message_type="request",
                        content={
                            "type": "get_entity_states",
                            "entities": entity_mentions,
                            "episode": self.state.current_episode
                        }
                    )
                    
                    self.send_message(gaia_message)
                    gaia_results = self.process_message_queue()
                    world_state = gaia_results.get("gaia", {})
            
            # Combine information for narrative generation
            combined_context = {
                "user_input": user_input,
                "current_episode": self.state.current_episode,
                "recent_history": self.state.get_recent_history(),
                "context": context_package,
                "character_insights": character_insights,
                "world_state": world_state
            }
            
            # Send narrative generation request to Logon agent
            narrative_request = AgentMessage(
                sender="maestro",
                recipient="logon",
                message_type="request",
                content={
                    "type": "generate_narrative",
                    "context_package": combined_context
                }
            )
            
            self.send_message(narrative_request)
            
            # Process message queue to get narrative
            narrative_results = self.process_message_queue()
            
            # Extract narrative from response
            logon_response = narrative_results.get("logon", {})
            narrative = logon_response.get("narrative", 
                         logon_response.get("response", "No narrative generated."))
            
            # Add system message to state
            self.state.add_system_message(narrative)
            
            # Save state if configured
            if self.settings["state_management"].get("save_state", True):
                self.state.save()
            
            return narrative
            
        except Exception as e:
            error_msg = f"Error processing input: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return f"An error occurred while processing your input: {str(e)}"
    
    def _extract_entity_mentions(self, text: str, context_package: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract entity mentions from text and context
        
        Args:
            text: Input text to analyze
            context_package: Context information from Lore
            
        Returns:
            List of entity mention dictionaries with type and identifier
        """
        entities = []
        
        # Try to extract from context package first
        if isinstance(context_package, dict):
            # Look for entity mentions in various possible locations
            if "entity_mentions" in context_package:
                entities.extend(context_package["entity_mentions"])
            elif "entities" in context_package:
                entities.extend(context_package["entities"])
            elif "relevant_entities" in context_package:
                entities.extend(context_package["relevant_entities"])
        
        # If no entities were found in context package, try simple extraction
        if not entities:
            # Simple extraction of potential entity names from text
            # Just capitalize words that might be names
            # In a real implementation, this would use NER or other techniques
            words = text.split()
            for word in words:
                # Check for capitalized words that might be names
                clean_word = word.strip(",.!?\"'()[]{}:;")
                if clean_word and clean_word[0].isupper() and len(clean_word) > 1:
                    # Check if this entity is already in our list
                    if not any(e.get("name") == clean_word for e in entities):
                        entities.append({
                            "name": clean_word,
                            "type": "character"  # Default to character type
                        })
        
        return entities
    
    def get_agent_status(self) -> Dict[str, Any]:
        """
        Get status information about all registered agents
        
        Returns:
            Dictionary with agent status information
        """
        return {
            "registered_agents": self.agent_registry.list_agents(),
            "enabled_agents": self.agent_registry.get_enabled_agents(),
            "message_queue_size": len(self.message_queue)
        }
    
    def run_test(self) -> bool:
        """
        Run tests on the orchestrator
        
        Returns:
            True if all tests pass, False otherwise
        """
        logger.info("=== Running Maestro tests ===")
        
        all_passed = True
        
        # Test 1: Message sending
        try:
            logger.info("Test 1: Message sending")
            test_message = AgentMessage(
                sender="test",
                recipient="lore",
                message_type="test",
                content={"test": "test_content"}
            )
            success = self.send_message(test_message)
            assert success
            assert len(self.message_queue) > 0
            logger.info("✓ Test 1 passed")
        except AssertionError:
            logger.error("✗ Test 1 failed")
            all_passed = False
        
        # Test 2: State management
        try:
            logger.info("Test 2: State management")
            self.state.add_user_message("Test message")
            assert len(self.state.conversation_history) > 0
            assert self.state.conversation_history[-1]["role"] == "user"
            assert self.state.conversation_history[-1]["content"] == "Test message"
            logger.info("✓ Test 2 passed")
        except AssertionError:
            logger.error("✗ Test 2 failed")
            all_passed = False
        
        # Test 3: Agent registry
        try:
            logger.info("Test 3: Agent registry")
            # Get registered agents
            agents = self.agent_registry.list_agents()
            assert len(agents) > 0
            # Try to disable and re-enable the first agent
            if agents:
                first_agent = agents[0]["name"]
                self.agent_registry.disable_agent(first_agent)
                assert not self.agent_registry.is_agent_enabled(first_agent)
                self.agent_registry.enable_agent(first_agent)
                assert self.agent_registry.is_agent_enabled(first_agent)
            logger.info("✓ Test 3 passed")
        except AssertionError:
            logger.error("✗ Test 3 failed")
            all_passed = False
        
        # Test 4: Basic workflow
        try:
            logger.info("Test 4: Basic workflow")
            result = self.process_input("Test input")
            assert result is not None
            logger.info("✓ Test 4 passed")
        except AssertionError:
            logger.error("✗ Test 4 failed")
            all_passed = False
        except Exception as e:
            logger.error(f"✗ Test 4 failed with exception: {e}")
            logger.error(traceback.format_exc())
            all_passed = False
        
        logger.info(f"=== Test Results: {'All Passed' if all_passed else 'Some Failed'} ===")
        return all_passed

def main():
    """
    Main entry point for running the module directly
    """
    parser = argparse.ArgumentParser(description="Maestro: Central Orchestrator for Night City Stories")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--input", help="Process user input and print the result")
    parser.add_argument("--status", action="store_true", help="Show agent status")
    args = parser.parse_args()
    
    try:
        # Create Maestro instance
        maestro = Maestro()
        
        if args.test:
            # Run tests
            maestro.run_test()
        elif args.input:
            # Process input
            result = maestro.process_input(args.input)
            print("\nGenerated Narrative:")
            print("-" * 80)
            print(result)
            print("-" * 80)
        elif args.status:
            # Show agent status
            status = maestro.get_agent_status()
            print("\nAgent Status:")
            print("-" * 80)
            print(json.dumps(status, indent=2))
            print("-" * 80)
        else:
            # Show help
            parser.print_help()
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
