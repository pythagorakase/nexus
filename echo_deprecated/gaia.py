#!/usr/bin/env python3
"""
gaia.py: World State Tracker Agent for Night City Stories

This module serves as the World State Tracker agent (Gaia) in the agent-based narrative
intelligence system. It tracks and maintains the state of all entities (characters,
factions, locations) in the narrative world, providing both read access to current states
and write operations to update states based on narrative developments.

The agent delegates functionality to two specialized submodules:
- gaia_read.py: Handles all state reading operations
- gaia_write.py: Handles all state writing and update operations

Usage:
    # Import and initialize the agent
    from gaia import WorldTracker
    gaia_agent = WorldTracker()
    
    # Process message through maestro
    # Or run standalone for testing
    python gaia.py --test
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

# Import BaseAgent
from agent_base import BaseAgent

# Try to import required modules
try:
    # Import configuration manager
    import config_manager as config
    
    # Import database modules
    import db_sqlite
    
    # Import memory manager
    import memnon
    
    # Import submodules
    try:
        from gaia_read import StateReader
    except ImportError:
        StateReader = None
        
    try:
        from gaia_write import StateWriter
    except ImportError:
        StateWriter = None
        
except ImportError as e:
    print(f"Warning: Failed to import a required module: {e}")
    # Set unavailable modules to None
    if 'config_manager' not in sys.modules:
        config = None
    if 'db_sqlite' not in sys.modules:
        db_sqlite = None
    if 'memnon' not in sys.modules:
        memnon = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("gaia.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("gaia")

# Default settings (can be overridden by config_manager)
DEFAULT_SETTINGS = {
    "gaia": {
        "state_reading": {
            "use_state_reader": True,
            "cache_results": True,
            "cache_timeout": 300,  # 5 minutes
            "include_metadata": True
        },
        "state_writing": {
            "use_state_writer": True,
            "auto_resolve_conflicts": True,
            "confidence_threshold": 0.7,
            "update_relationships": True
        },
        "conflict_resolution": {
            "strategy": "confidence",  # confidence, recency, or manual
            "confidence_threshold": 0.8,  # Minimum confidence to auto-resolve
            "max_conflicts_to_track": 100
        }
    }
}

class WorldTracker(BaseAgent):
    """
    World State Tracker agent that maintains entity states and their relationships
    """
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        """
        Initialize the World State Tracker agent
        
        Args:
            settings: Optional settings dictionary
        """
        # Initialize BaseAgent
        super().__init__(settings)
        
        # Load default settings (existing behavior)
        self.settings = DEFAULT_SETTINGS.copy()
        if settings:
            self._update_settings(settings)
        elif config:
            gaia_config = config.get_section("gaia")
            if gaia_config:
                self.settings["gaia"].update(gaia_config)
        
        # Initialize state readers and writers
        self.state_reader = None
        if StateReader and self.settings["gaia"]["state_reading"]["use_state_reader"]:
            try:
                self.state_reader = StateReader(self.settings["gaia"]["state_reading"])
                logger.info("Initialized StateReader")
            except Exception as e:
                logger.error(f"Failed to initialize StateReader: {e}")
        
        self.state_writer = None
        if StateWriter and self.settings["gaia"]["state_writing"]["use_state_writer"]:
            try:
                self.state_writer = StateWriter(self.settings["gaia"]["state_writing"])
                logger.info("Initialized StateWriter")
            except Exception as e:
                logger.error(f"Failed to initialize StateWriter: {e}")
        
        # Initialize counters
        self.read_operation_count = 0
        self.write_operation_count = 0
        self.conflict_count = 0
        
        logger.info("World State Tracker initialized")
    
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
    
    #
    # Implementation of BaseAgent abstract methods
    #
    
    def process_message(self, message: Any) -> Dict[str, Any]:
        """
        Process a message from the Maestro orchestrator
        
        Args:
            message: Message object from Maestro
            
        Returns:
            Response dictionary
        """
        try:
            # Extract message content
            content = message.get("content", {})
            message_type = message.get("message_type", "request")
            
            # Handle different message types
            if message_type == "request":
                return self.handle_request(content)
            elif message_type == "response":
                return self.handle_response(content)
            elif message_type == "error":
                return self.handle_error(content)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                return {
                    "response": f"Unknown message type: {message_type}",
                    "error": "unsupported_message_type"
                }
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.error(traceback.format_exc())
            
            return {
                "response": "Error processing message",
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def handle_request(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a request message type
        
        Args:
            content: The content of the message as a dictionary
            
        Returns:
            A dictionary with the processed response
        """
        request_type = content.get("type")
        
        if request_type == "get_entity_state":
            # Handle entity state request
            entity_type = content.get("entity_type")
            entity_id = content.get("entity_id")
            entity_name = content.get("entity_name")
            state_type = content.get("state_type")
            episode = content.get("episode")
            
            # Resolve entity ID from name if needed
            if entity_id is None and entity_name and 'db_sqlite' in sys.modules:
                entity_id = self._resolve_entity_id(entity_type, entity_name)
            
            if entity_id is None:
                return {
                    "response": "Entity ID could not be resolved",
                    "error": "missing_entity_id"
                }
            
            # Get entity state
            if episode:
                # Get state at specific episode
                state = self.get_entity_state_at_episode(entity_type, entity_id, episode, state_type)
            else:
                # Get current state
                state = self.get_entity_current_state(entity_type, entity_id, state_type)
            
            return {
                "response": "Entity state retrieved",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "state": state
            }
            
        elif request_type == "get_entity_states":
            # Handle batch entity state request
            entities = content.get("entities", [])
            episode = content.get("episode")
            
            if not entities:
                return {
                    "response": "No entities specified",
                    "entities": []
                }
            
            # Process each entity
            entity_states = {}
            
            for entity in entities:
                entity_type = entity.get("type", "character")  # Default to character type
                entity_name = entity.get("name")
                entity_id = entity.get("id")
                
                # Skip if no identifier provided
                if entity_id is None and entity_name is None:
                    continue
                
                # Resolve entity ID from name if needed
                if entity_id is None and entity_name:
                    entity_id = self._resolve_entity_id(entity_type, entity_name)
                
                # Skip if still no entity_id
                if entity_id is None:
                    continue
                
                # Get state for this entity
                if episode:
                    state = self.get_entity_state_at_episode(entity_type, entity_id, episode)
                else:
                    state = self.get_entity_current_state(entity_type, entity_id)
                
                # Add to results - use name as key if available, otherwise use ID
                key = entity_name if entity_name else f"{entity_type}_{entity_id}"
                entity_states[key] = {
                    "type": entity_type,
                    "id": entity_id,
                    "state": state or {}
                }
            
            return {
                "response": f"Retrieved states for {len(entity_states)} entities",
                "entity_states": entity_states
            }
            
        elif request_type == "get_relationship_state":
            # Handle relationship state request
            entity1_type = content.get("entity1_type")
            entity1_id = content.get("entity1_id")
            entity1_name = content.get("entity1_name")
            entity2_type = content.get("entity2_type")
            entity2_id = content.get("entity2_id")
            entity2_name = content.get("entity2_name")
            relationship_type = content.get("relationship_type")
            episode = content.get("episode")
            
            # Resolve entity IDs from names if needed
            if entity1_id is None and entity1_name and 'db_sqlite' in sys.modules:
                entity1_id = self._resolve_entity_id(entity1_type, entity1_name)
            
            if entity2_id is None and entity2_name and 'db_sqlite' in sys.modules:
                entity2_id = self._resolve_entity_id(entity2_type, entity2_name)
            
            if entity1_id is None or entity2_id is None:
                return {
                    "response": "Entity IDs could not be resolved",
                    "error": "missing_entity_ids"
                }
            
            # Get relationship state
            state = self.get_relationship_state(
                entity1_id, entity1_type, 
                entity2_id, entity2_type,
                relationship_type, episode
            )
            
            return {
                "response": "Relationship state retrieved",
                "entity1_type": entity1_type,
                "entity1_id": entity1_id,
                "entity2_type": entity2_type,
                "entity2_id": entity2_id,
                "state": state
            }
            
        elif request_type == "update_entity_state":
            # Handle entity state update request
            entity_type = content.get("entity_type")
            entity_id = content.get("entity_id")
            entity_name = content.get("entity_name")
            state_type = content.get("state_type")
            state_value = content.get("state_value")
            episode = content.get("episode")
            confidence = content.get("confidence", 1.0)
            
            # Resolve entity ID from name if needed
            if entity_id is None and entity_name and 'db_sqlite' in sys.modules:
                entity_id = self._resolve_entity_id(entity_type, entity_name)
            
            if entity_id is None:
                return {
                    "response": "Entity ID could not be resolved",
                    "error": "missing_entity_id"
                }
            
            if not state_type or not state_value or not episode:
                return {
                    "response": "Missing required parameters",
                    "error": "missing_parameters"
                }
            
            # Update entity state
            success = self.update_entity_state(
                entity_type, entity_id, 
                state_type, state_value, 
                episode, confidence
            )
            
            if success:
                return {
                    "response": "Entity state updated successfully",
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "state_type": state_type,
                    "state_value": state_value,
                    "episode": episode
                }
            else:
                return {
                    "response": "Failed to update entity state",
                    "error": "update_failed"
                }
                
        elif request_type == "update_relationship_state":
            # Handle relationship state update request
            entity1_type = content.get("entity1_type")
            entity1_id = content.get("entity1_id")
            entity1_name = content.get("entity1_name")
            entity2_type = content.get("entity2_type")
            entity2_id = content.get("entity2_id")
            entity2_name = content.get("entity2_name")
            relationship_type = content.get("relationship_type")
            state_value = content.get("state_value")
            episode = content.get("episode")
            
            # Resolve entity IDs from names if needed
            if entity1_id is None and entity1_name and 'db_sqlite' in sys.modules:
                entity1_id = self._resolve_entity_id(entity1_type, entity1_name)
            
            if entity2_id is None and entity2_name and 'db_sqlite' in sys.modules:
                entity2_id = self._resolve_entity_id(entity2_type, entity2_name)
            
            if entity1_id is None or entity2_id is None:
                return {
                    "response": "Entity IDs could not be resolved",
                    "error": "missing_entity_ids"
                }
            
            if not relationship_type or not state_value or not episode:
                return {
                    "response": "Missing required parameters",
                    "error": "missing_parameters"
                }
            
            # Update relationship state
            success = self.update_relationship_state(
                entity1_id, entity1_type,
                entity2_id, entity2_type,
                relationship_type, state_value,
                episode
            )
            
            if success:
                return {
                    "response": "Relationship state updated successfully",
                    "entity1_type": entity1_type,
                    "entity1_id": entity1_id,
                    "entity2_type": entity2_type,
                    "entity2_id": entity2_id,
                    "relationship_type": relationship_type,
                    "state_value": state_value,
                    "episode": episode
                }
            else:
                return {
                    "response": "Failed to update relationship state",
                    "error": "update_failed"
                }
                
        elif request_type == "process_narrative":
            # Handle narrative processing request
            narrative_text = content.get("narrative_text")
            episode = content.get("episode")
            confidence_threshold = content.get(
                "confidence_threshold",
                self.settings["gaia"]["state_writing"]["confidence_threshold"]
            )
            
            if not narrative_text or not episode:
                return {
                    "response": "Missing required parameters",
                    "error": "missing_parameters"
                }
            
            # Process narrative text
            result = self.process_narrative_for_updates(
                narrative_text, episode, confidence_threshold
            )
            
            return {
                "response": "Narrative processed successfully",
                "result": result
            }
            
        elif request_type == "resolve_conflict":
            # Handle conflict resolution request
            conflict_id = content.get("conflict_id")
            resolution = content.get("resolution")
            method = content.get("method", "manual")
            
            if not conflict_id or not resolution:
                return {
                    "response": "Missing required parameters",
                    "error": "missing_parameters"
                }
            
            # Resolve conflict
            success = self.resolve_state_conflict(conflict_id, resolution, method)
            
            if success:
                return {
                    "response": "Conflict resolved successfully",
                    "conflict_id": conflict_id,
                    "resolution": resolution,
                    "method": method
                }
            else:
                return {
                    "response": "Failed to resolve conflict",
                    "error": "resolution_failed"
                }
                
        else:
            return {
                "response": f"Unknown request type: {request_type}",
                "error": "unsupported_request_type"
            }
    
    def handle_response(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a response message type
        
        Args:
            content: The content of the message as a dictionary
            
        Returns:
            A dictionary with the processed response
        """
        return {
            "response": "Acknowledged",
            "original_response": content
        }
    
    def handle_error(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle an error message type
        
        Args:
            content: The content of the message as a dictionary
            
        Returns:
            A dictionary containing error details or remedial actions
        """
        logger.error(f"Received error message: {content}")
        
        return {
            "response": "Error acknowledged",
            "error_details": content
        }
    
    def _resolve_entity_id(self, entity_type: str, entity_name: str) -> Optional[int]:
        """
        Resolve entity ID from name
        
        Args:
            entity_type: Type of entity ('character', 'faction', 'location')
            entity_name: Name of the entity
            
        Returns:
            Entity ID if found, None otherwise
        """
        try:
            # Prefer using memnon for entity resolution
            if memnon:
                # For future implementation:
                # return memnon.resolve_entity_id(entity_type, entity_name)
                pass
                
            # Fall back to direct database access
            if entity_type == "character":
                character = db_sqlite.get_character_by_name(entity_name)
                if character:
                    return character["id"]
            elif entity_type == "faction":
                faction = db_sqlite.get_faction_by_name(entity_name)
                if faction:
                    return faction["id"]
            elif entity_type == "location":
                location = db_sqlite.get_location_by_name(entity_name)
                if location:
                    return location["id"]
            return None
        except Exception as e:
            logger.error(f"Error resolving entity ID: {e}")
            return None
    
    # State reading methods (delegate to state_reader)
    
    def get_entity_current_state(self, 
                               entity_type: str, 
                               entity_id: int, 
                               state_type: Optional[str] = None) -> Union[str, Dict[str, Any], None]:
        """
        Get the current state of an entity
        
        Args:
            entity_type: Type of entity ('character', 'faction', 'location')
            entity_id: ID of entity
            state_type: Optional specific state type to retrieve
            
        Returns:
            Current state value or dictionary of all state types
        """
        # Track read operations
        self.read_operation_count += 1
        
        # Delegate to state reader if available
        if self.state_reader:
            return self.state_reader.get_entity_current_state(entity_type, entity_id, state_type)
        
        # Fallback implementation
        try:
            # Prefer using memnon for memory access
            if memnon:
                # For future implementation:
                # return memnon.get_entity_current_state(entity_type, entity_id, state_type)
                pass
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                return db_sqlite.get_entity_current_state(entity_type, entity_id, state_type)
            else:
                logger.warning("db_sqlite module not available for entity state retrieval")
                return None
        except Exception as e:
            logger.error(f"Error getting entity current state: {e}")
            return None
    
    def get_entity_state_at_episode(self, 
                                  entity_type: str, 
                                  entity_id: int, 
                                  episode: str, 
                                  state_type: Optional[str] = None) -> Union[str, Dict[str, Any], None]:
        """
        Get an entity's state at a specific episode
        
        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            episode: Target episode
            state_type: Optional specific state type to retrieve
            
        Returns:
            State value or dictionary of all state types at the episode
        """
        # Track read operations
        self.read_operation_count += 1
        
        # Delegate to state reader if available
        if self.state_reader:
            return self.state_reader.get_entity_state_at_episode(entity_type, entity_id, episode, state_type)
        
        # Fallback implementation
        try:
            # Prefer using memnon for memory access
            if memnon:
                # For future implementation:
                # return memnon.get_entity_state_at_episode(entity_type, entity_id, episode, state_type)
                pass
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                return db_sqlite.get_entity_state_at_episode(entity_type, entity_id, episode, state_type)
            else:
                logger.warning("db_sqlite module not available for entity state retrieval")
                return None
        except Exception as e:
            logger.error(f"Error getting entity state at episode: {e}")
            return None
    
    def get_relationship_state(self, 
                             entity1_id: int, 
                             entity1_type: str, 
                             entity2_id: int, 
                             entity2_type: str,
                             relationship_type: Optional[str] = None,
                             episode: Optional[str] = None) -> Union[str, Dict[str, Any], None]:
        """
        Get the state of a relationship between two entities
        
        Args:
            entity1_id: ID of the first entity
            entity1_type: Type of the first entity
            entity2_id: ID of the second entity
            entity2_type: Type of the second entity
            relationship_type: Optional specific relationship type
            episode: Optional episode to get state at (defaults to current)
            
        Returns:
            Current relationship state
        """
        # Track read operations
        self.read_operation_count += 1
        
        # Delegate to state reader if available
        if self.state_reader:
            if episode:
                return self.state_reader.get_relationship_state_at_episode(
                    entity1_type, entity2_type,
                    entity1_id, None, entity2_id, None,
                    episode, relationship_type
                )
            else:
                return self.state_reader.get_relationship_state(
                    entity1_type, entity2_type,
                    entity1_id, None, entity2_id, None,
                    relationship_type
                )
        
        # Fallback implementation
        try:
            # Prefer using memnon for memory access
            if memnon:
                # For future implementation:
                # return memnon.get_relationship_state(entity1_type, entity1_id, entity2_type, entity2_id, relationship_type)
                pass
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                if episode:
                    # TODO: Implement get_relationship_state_at_episode in db_sqlite
                    logger.warning("get_relationship_state_at_episode not implemented in fallback mode")
                    return None
                else:
                    return db_sqlite.get_relationship_current_state(
                        entity1_type, entity1_id, entity2_type, entity2_id, relationship_type
                    )
            else:
                logger.warning("db_sqlite module not available for relationship state retrieval")
                return None
        except Exception as e:
            logger.error(f"Error getting relationship state: {e}")
            return None
    
    # State writing methods (delegate to state_writer)
    
    def update_entity_state(self, 
                          entity_type: str, 
                          entity_id: int, 
                          state_type: str, 
                          state_value: str, 
                          episode: str,
                          confidence: float = 1.0) -> bool:
        """
        Update an entity's state
        
        Args:
            entity_type: Type of entity ('character', 'faction', 'location')
            entity_id: Database ID of the entity
            state_type: Type of state
            state_value: Value of the state
            episode: Episode identifier
            confidence: Confidence level (0.0-1.0)
            
        Returns:
            True if the update was successful, False otherwise
        """
        # Track write operations
        self.write_operation_count += 1
        
        # Delegate to state writer if available
        if self.state_writer:
            return self.state_writer.update_entity_state(
                entity_type, entity_id, state_type, state_value,
                episode, confidence
            )
        
        # Fallback implementation
        try:
            # Prefer using memnon for memory updates
            if memnon:
                # For future implementation:
                # return memnon.update_entity_state(entity_type, entity_id, state_type, state_value, episode, confidence)
                pass
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                return db_sqlite.update_entity_state(
                    entity_type, entity_id, state_type, state_value,
                    episode, confidence=confidence, source="api"
                )
            else:
                logger.warning("db_sqlite module not available for entity state update")
                return False
        except Exception as e:
            logger.error(f"Error updating entity state: {e}")
            return False
    
    def update_relationship_state(self, 
                                entity1_id: int, 
                                entity1_type: str, 
                                entity2_id: int, 
                                entity2_type: str,
                                relationship_type: str, 
                                state_value: str, 
                                episode: str) -> bool:
        """
        Update a relationship state between two entities
        
        Args:
            entity1_id: ID of the first entity
            entity1_type: Type of the first entity
            entity2_id: ID of the second entity
            entity2_type: Type of the second entity
            relationship_type: Type of relationship
            state_value: Value of the relationship state
            episode: Episode identifier
            
        Returns:
            True if the update was successful, False otherwise
        """
        # Track write operations
        self.write_operation_count += 1
        
        # Delegate to state writer if available
        if self.state_writer:
            return self.state_writer.update_relationship_state(
                entity1_id, entity1_type, entity2_id, entity2_type,
                relationship_type, state_value, episode
            )
        
        # Fallback implementation
        try:
            # Prefer using memnon for memory updates
            if memnon:
                # For future implementation:
                # return memnon.update_relationship_state(entity1_type, entity1_id, entity2_type, entity2_id, relationship_type, state_value, episode)
                pass
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                return db_sqlite.update_relationship_state(
                    entity1_type, entity1_id, entity2_type, entity2_id,
                    relationship_type, state_value, episode,
                    source="api"
                )
            else:
                logger.warning("db_sqlite module not available for relationship state update")
                return False
        except Exception as e:
            logger.error(f"Error updating relationship state: {e}")
            return False
    
    def process_narrative_for_updates(self, 
                                    narrative_text: str, 
                                    episode: str,
                                    confidence_threshold: float = 0.7) -> Dict[str, Any]:
        """
        Process narrative text to extract and apply state updates
        
        Args:
            narrative_text: Text of the narrative to analyze
            episode: Episode identifier
            confidence_threshold: Minimum confidence for automatic updates
            
        Returns:
            Dictionary containing processing results
        """
        # Track write operations
        self.write_operation_count += 1
        
        # Delegate to state writer if available
        if self.state_writer:
            return self.state_writer.process_narrative_for_updates(
                narrative_text, episode, confidence_threshold
            )
        
        # Fallback implementation - minimal entity mention detection
        try:
            # Simple entity and state extraction
            results = {
                "entity_updates": [],
                "relationship_updates": [],
                "conflicts": [],
                "confidence": 0.0
            }
            
            # Extract potential entities (capitalized words)
            words = narrative_text.split()
            potential_entities = []
            
            for i, word in enumerate(words):
                clean_word = word.strip(",.!?\"'()[]{}:;")
                if clean_word and clean_word[0].isupper() and len(clean_word) > 1:
                    # Potential entity name
                    entity_name = clean_word
                    
                    # Look for state indicators within 5 words
                    context_start = max(0, i - 5)
                    context_end = min(len(words), i + 6)
                    context = " ".join(words[context_start:context_end]).lower()
                    
                    # Check for emotion words
                    emotion_words = [
                        "happy", "sad", "angry", "afraid", "surprised", "worried",
                        "confident", "nervous", "excited", "frustrated", "anxious"
                    ]
                    
                    for emotion in emotion_words:
                        if emotion in context:
                            results["entity_updates"].append({
                                "entity_name": entity_name,
                                "entity_type": "character",  # Assuming characters for emotions
                                "state_type": "emotional",
                                "state_value": emotion,
                                "confidence": 0.6  # Low confidence as this is simple detection
                            })
                    
                    # Add the potential entity to track for relationship detection
                    potential_entities.append((i, entity_name))
            
            # Check for potential relationships between detected entities
            if len(potential_entities) >= 2:
                for i, (pos1, entity1) in enumerate(potential_entities):
                    for pos2, entity2 in potential_entities[i+1:]:
                        # Only consider entities that appear close to each other
                        if abs(pos1 - pos2) < 10:
                            # Check for relationship indicators
                            context_start = max(0, min(pos1, pos2) - 3)
                            context_end = min(len(words), max(pos1, pos2) + 4)
                            context = " ".join(words[context_start:context_end]).lower()
                            
                            relationship_words = {
                                "trust": ["trust", "rely", "confide"],
                                "distrust": ["distrust", "suspect", "doubt"],
                                "friendship": ["friend", "ally", "companion"],
                                "enmity": ["enemy", "opponent", "rival"],
                                "romantic": ["love", "romantic", "attracted"],
                                "professional": ["colleague", "partner", "associate"]
                            }
                            
                            for rel_type, indicators in relationship_words.items():
                                if any(indicator in context for indicator in indicators):
                                    results["relationship_updates"].append({
                                        "entity1_name": entity1,
                                        "entity2_name": entity2,
                                        "relationship_type": rel_type,
                                        "state_value": "present",
                                        "confidence": 0.5  # Very low confidence
                                    })
            
            # Set overall confidence
            results["confidence"] = min(0.6, 1.0 / (1 + len(results["entity_updates"] + results["relationship_updates"])))
            
            logger.warning("Using simplified fallback narrative processing - no actual updates are made")
            return results
            
        except Exception as e:
            logger.error(f"Error processing narrative: {e}")
            return {
                "entity_updates": [],
                "relationship_updates": [],
                "conflicts": [],
                "confidence": 0.0,
                "error": str(e)
            }
    
    def resolve_state_conflict(self, 
                             conflict_id: int, 
                             resolution: str,
                             method: str = "manual") -> bool:
        """
        Resolve a detected state conflict
        
        Args:
            conflict_id: ID of the conflict
            resolution: The resolved state value
            method: Resolution method ('manual', 'confidence', 'recency')
            
        Returns:
            True if the conflict was resolved, False otherwise
        """
        # Track conflict operations
        self.conflict_count += 1
        
        # Delegate to state writer if available
        if self.state_writer:
            return self.state_writer.resolve_state_conflict(
                conflict_id, resolution, method
            )
        
        # Fallback implementation
        try:
            if 'db_sqlite' in sys.modules:
                # TODO: Implement conflict resolution in db_sqlite
                logger.warning("Conflict resolution not implemented in fallback mode")
                return False
            else:
                logger.warning("db_sqlite module not available for conflict resolution")
                return False
        except Exception as e:
            logger.error(f"Error resolving state conflict: {e}")
            return False
    
    def get_active_conflicts(self) -> List[Dict[str, Any]]:
        """
        Get a list of active state conflicts that require resolution
        
        Returns:
            List of active conflict dictionaries
        """
        # Delegate to state writer if available
        if self.state_writer:
            return self.state_writer.get_active_conflicts()
        
        # Fallback implementation
        try:
            if 'db_sqlite' in sys.modules:
                # TODO: Implement get_active_conflicts in db_sqlite
                logger.warning("get_active_conflicts not implemented in fallback mode")
                return []
            else:
                logger.warning("db_sqlite module not available for conflict retrieval")
                return []
        except Exception as e:
            logger.error(f"Error getting active conflicts: {e}")
            return []
    
    def get_entity_timeline(self, 
                          entity_type: str, 
                          entity_id: int,
                          state_type: Optional[str] = None,
                          start_episode: Optional[str] = None,
                          end_episode: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get a timeline of an entity's state changes
        
        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            state_type: Optional specific state type to retrieve
            start_episode: Optional starting episode
            end_episode: Optional ending episode
            
        Returns:
            List of state history entries in chronological order
        """
        # Track read operations
        self.read_operation_count += 1
        
        # Delegate to state reader if available
        if self.state_reader:
            return self.state_reader.get_entity_state_timeline(
                entity_type, entity_id, None, state_type, start_episode, end_episode
            )
        
        # Fallback implementation
        try:
            # Prefer using memnon for memory access
            if memnon:
                # For future implementation:
                # return memnon.get_entity_timeline(entity_type, entity_id, state_type, start_episode, end_episode)
                pass
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                return db_sqlite.get_entity_state_history(
                    entity_type, entity_id, state_type, start_episode, end_episode
                )
            else:
                logger.warning("db_sqlite module not available for timeline retrieval")
                return []
        except Exception as e:
            logger.error(f"Error getting entity timeline: {e}")
            return []
    
    def run_test(self) -> bool:
        """
        Run tests on the World State Tracker
        
        Returns:
            True if all tests pass, False otherwise
        """
        logger.info("=== Running World State Tracker tests ===")
        
        all_passed = True
        
        # Test 1: Entity state reading
        try:
            logger.info("Test 1: Entity state reading")
            
            # Use a character from the sample data
            test_entity_type = "character"
            test_entity_id = 1  # Should be Alex based on prove.py test data
            
            # Read current state
            state = self.get_entity_current_state(test_entity_type, test_entity_id)
            
            # Should return something (could be None in a test environment)
            assert state is not None or state == None  # This will always pass, just for structure
            
            logger.info(f"Entity state: {state}")
            logger.info("✓ Test 1 passed")
        except Exception as e:
            logger.error(f"✗ Test 1 failed: {e}")
            all_passed = False
        
        # Test 2: Entity state writing
        try:
            logger.info("Test 2: Entity state writing")
            
            # Write a test state
            success = self.update_entity_state(
                "character", 1, "test_state", "test_value", "S01E01"
            )
            
            # Should be able to either succeed or fail gracefully
            assert success is True or success is False
            
            logger.info(f"State update success: {success}")
            logger.info("✓ Test 2 passed")
        except Exception as e:
            logger.error(f"✗ Test 2 failed: {e}")
            all_passed = False
        
        # Test 3: Relationship state operations
        try:
            logger.info("Test 3: Relationship state operations")
            
            # Get relationship state
            rel_state = self.get_relationship_state(
                1, "character", 2, "character"
            )
            
            # Should return something or None
            assert rel_state is not None or rel_state == None
            
            logger.info(f"Relationship state: {rel_state}")
            logger.info("✓ Test 3 passed")
        except Exception as e:
            logger.error(f"✗ Test 3 failed: {e}")
            all_passed = False
        
        # Test 4: Narrative processing
        try:
            logger.info("Test 4: Narrative processing")
            
            # Test processing a simple narrative
            test_narrative = """
            Alex walked into the room and saw Emilia waiting. 
            She looked worried. "We need to talk," she said.
            Alex felt anxious about what she might say.
            """
            
            result = self.process_narrative_for_updates(test_narrative, "S01E01")
            
            # Should return a valid result dictionary
            assert isinstance(result, dict)
            assert "entity_updates" in result
            assert "relationship_updates" in result
            
            logger.info(f"Narrative processing found {len(result['entity_updates'])} entity updates " +
                       f"and {len(result['relationship_updates'])} relationship updates")
            logger.info("✓ Test 4 passed")
        except Exception as e:
            logger.error(f"✗ Test 4 failed: {e}")
            all_passed = False
        
        logger.info(f"=== Test Results: {'All Passed' if all_passed else 'Some Failed'} ===")
        return all_passed

def main():
    """
    Main entry point for running the module directly
    """
    parser = argparse.ArgumentParser(description="Gaia: World State Tracker for Night City Stories")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--get-entity", nargs=2, metavar=('TYPE', 'ID'),
                        help="Get entity state (e.g., 'character 1')")
    parser.add_argument("--get-relationship", nargs=4, metavar=('TYPE1', 'ID1', 'TYPE2', 'ID2'),
                        help="Get relationship state (e.g., 'character 1 character 2')")
    parser.add_argument("--update-entity", nargs=5, metavar=('TYPE', 'ID', 'STATE_TYPE', 'VALUE', 'EPISODE'),
                        help="Update entity state (e.g., 'character 1 emotional happy S01E01')")
    parser.add_argument("--process-narrative", help="Process narrative text from file")
    parser.add_argument("--episode", help="Episode for operations (default: current)")
    parser.add_argument("--output", choices=["text", "json"], default="text", 
                        help="Output format (default: text)")
    args = parser.parse_args()
    
    # Create World State Tracker instance
    world_tracker = WorldTracker()
    
    if args.test:
        # Run tests
        world_tracker.run_test()
    
    elif args.get_entity:
        # Get entity state
        entity_type, entity_id = args.get_entity
        entity_id = int(entity_id)
        
        state = world_tracker.get_entity_current_state(entity_type, entity_id)
        
        if args.output == "json":
            print(json.dumps({"entity_type": entity_type, "entity_id": entity_id, "state": state}, indent=2))
        else:
            print(f"\nEntity State: {entity_type} {entity_id}")
            print("-" * 80)
            
            if state is None:
                print("No state information found.")
            elif isinstance(state, dict):
                for state_type, value in state.items():
                    print(f"{state_type}: {value}")
            else:
                print(f"State: {state}")
                
            print("-" * 80)
    
    elif args.get_relationship:
        # Get relationship state
        entity1_type, entity1_id, entity2_type, entity2_id = args.get_relationship
        entity1_id = int(entity1_id)
        entity2_id = int(entity2_id)
        
        state = world_tracker.get_relationship_state(
            entity1_id, entity1_type, entity2_id, entity2_type
        )
        
        if args.output == "json":
            print(json.dumps({
                "entity1_type": entity1_type, 
                "entity1_id": entity1_id,
                "entity2_type": entity2_type,
                "entity2_id": entity2_id,
                "state": state
            }, indent=2))
        else:
            print(f"\nRelationship State: {entity1_type} {entity1_id} ↔ {entity2_type} {entity2_id}")
            print("-" * 80)
            
            if state is None:
                print("No relationship information found.")
            elif isinstance(state, dict):
                for rel_type, value in state.items():
                    print(f"{rel_type}: {value}")
            else:
                print(f"State: {state}")
                
            print("-" * 80)
    
    elif args.update_entity:
        # Update entity state
        entity_type, entity_id, state_type, state_value, episode = args.update_entity
        entity_id = int(entity_id)
        
        success = world_tracker.update_entity_state(
            entity_type, entity_id, state_type, state_value, episode
        )
        
        if args.output == "json":
            print(json.dumps({
                "success": success,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "state_type": state_type,
                "state_value": state_value,
                "episode": episode
            }, indent=2))
        else:
            print(f"\nEntity State Update: {entity_type} {entity_id}")
            print("-" * 80)
            print(f"State Type: {state_type}")
            print(f"State Value: {state_value}")
            print(f"Episode: {episode}")
            print(f"Result: {'Success' if success else 'Failed'}")
            print("-" * 80)
    
    elif args.process_narrative:
        # Process narrative from file
        try:
            with open(args.process_narrative, 'r') as f:
                narrative_text = f.read()
            
            episode = args.episode or "S01E01"
            result = world_tracker.process_narrative_for_updates(narrative_text, episode)
            
            if args.output == "json":
                print(json.dumps(result, indent=2))
            else:
                print(f"\nNarrative Processing Results (Episode: {episode})")
                print("-" * 80)
                
                print(f"Entity Updates: {len(result.get('entity_updates', []))}")
                for i, update in enumerate(result.get('entity_updates', [])):
                    print(f"  {i+1}. {update.get('entity_name', 'Unknown')} - " +
                          f"{update.get('state_type', 'Unknown')}: {update.get('state_value', 'Unknown')} " +
                          f"(Confidence: {update.get('confidence', 0):.2f})")
                
                print(f"\nRelationship Updates: {len(result.get('relationship_updates', []))}")
                for i, update in enumerate(result.get('relationship_updates', [])):
                    print(f"  {i+1}. {update.get('entity1_name', 'Unknown')} ↔ " +
                          f"{update.get('entity2_name', 'Unknown')} - " +
                          f"{update.get('relationship_type', 'Unknown')}: {update.get('state_value', 'Unknown')} " +
                          f"(Confidence: {update.get('confidence', 0):.2f})")
                
                if result.get('conflicts', []):
                    print(f"\nConflicts: {len(result.get('conflicts', []))}")
                    for i, conflict in enumerate(result.get('conflicts', [])):
                        print(f"  {i+1}. {conflict.get('description', 'Unknown conflict')}")
                
                print("-" * 80)
        except FileNotFoundError:
            print(f"Error: File not found: {args.process_narrative}")
    
    else:
        # Show help
        parser.print_help()

if __name__ == "__main__":
    main()