#!/usr/bin/env python3
"""
gaia_read.py: World State Reader Module for Night City Stories

This module provides read-only access to entity states, timelines, and relationships in the
narrative world. It serves as the authoritative source for querying "what is true" about
the world state at any given point in the narrative.

The StateReader class provides methods to:
- Query current and historical entity states (characters, factions, locations)
- Retrieve relationship information between entities
- Generate timelines of state changes
- Create world state snapshots for specific episodes
- Find entities matching specific state criteria

Usage:
    # Import and initialize
    from gaia_read import StateReader
    state_reader = StateReader()
    
    # Get current state of a character
    state = state_reader.get_entity_current_state("character", entity_name="Alex")
    
    # Get relationship between characters at a specific episode
    relationship = state_reader.get_relationship_state_at_episode(
        entity1_type="character", entity1_name="Alex",
        entity2_type="character", entity2_name="Emilia",
        episode="S01E05"
    )
"""

import os
import sys
import json
import logging
import time
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Set
from datetime import datetime
from functools import lru_cache

# Try to import required modules
try:
    # Import configuration manager
    import config_manager as config
    
    # Import database adapters
    import db_sqlite
    
    # Import memory manager
    import memnon
    
    # Import entity state manager
    try:
        from entity_state_manager import EntityStateManager, EntityType, StateType
    except ImportError:
        EntityStateManager = None
        
except ImportError as e:
    print(f"Warning: Failed to import a required module: {e}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("gaia_read.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("gaia_read")

# Default settings (can be overridden by config_manager)
DEFAULT_SETTINGS = {
    "state_reading": {
        "cache_results": True,
        "cache_timeout": 300,  # 5 minutes
        "cache_max_size": 1000,  # Maximum number of cached results
        "include_metadata": True,
        "default_episode": "S01E01",
        "use_direct_db_access": False  # Whether to use direct DB access or go through memnon
    }
}

class StateReader:
    """
    State Reader for querying entity states and relationships in the narrative world
    """
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        """
        Initialize the State Reader
        
        Args:
            settings: Optional settings dictionary
        """
        # Initialize settings
        self.settings = DEFAULT_SETTINGS["state_reading"].copy()
        if settings:
            self.settings.update(settings)
        
        # Initialize entity state manager if available
        self.entity_state_manager = None
        if EntityStateManager:
            try:
                self.entity_state_manager = EntityStateManager()
                logger.info("Initialized EntityStateManager")
            except Exception as e:
                logger.error(f"Failed to initialize EntityStateManager: {e}")
        
        # Initialize cache
        self._cache = {}
        self._cache_timestamps = {}
        
        # Store known entity types
        self.entity_types = {
            "character", "faction", "location"
        }
        
        # State types by entity type
        self.state_types = {
            "character": {
                "physical", "emotional", "knowledge", "motivation", "relationship", "location"
            },
            "faction": {
                "power", "activity", "agenda", "alliance"
            },
            "location": {
                "condition", "control", "atmosphere", "accessibility"
            }
        }
        
        # Relationship types
        self.relationship_types = {
            "trust", "power", "alliance", "knowledge", "emotional", "professional"
        }

        logger.info("StateReader initialized")
    
    # --- Entity state methods ---
    
    def get_entity_current_state(self, entity_type: str, 
                               entity_id: Optional[int] = None, 
                               entity_name: Optional[str] = None, 
                               state_type: Optional[str] = None) -> Union[str, Dict[str, Any], None]:
        """
        Get the current state of an entity by ID or name.
        
        Args:
            entity_type: Type of entity ('character', 'faction', 'location')
            entity_id: Optional ID of the entity
            entity_name: Optional name of the entity (used if ID not provided)
            state_type: Optional specific state type to retrieve
            
        Returns:
            If state_type specified: the current value for that state
            If state_type None: dictionary of all current states
            None if entity not found
            
        Raises:
            ValueError: If neither entity_id nor entity_name is provided
            ValueError: If entity_type is invalid
        """
        # Validate entity type
        if entity_type not in self.entity_types:
            logger.error(f"Invalid entity type: {entity_type}")
            raise ValueError(f"Invalid entity type: {entity_type}. Must be one of: {', '.join(self.entity_types)}")
        
        # Ensure we have either ID or name
        if entity_id is None and entity_name is None:
            logger.error("Either entity_id or entity_name must be provided")
            raise ValueError("Either entity_id or entity_name must be provided")
        
        # Resolve entity_id from name if necessary
        if entity_id is None and entity_name is not None:
            entity_id = self._resolve_entity_id(entity_type, entity_name)
            if entity_id is None:
                logger.warning(f"Could not resolve entity ID for {entity_type} named '{entity_name}'")
                return None
        
        # Check cache
        cache_key = f"current_state_{entity_type}_{entity_id}_{state_type}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Use entity state manager if available
        if self.entity_state_manager:
            result = self.entity_state_manager.get_entity_current_state(entity_type, entity_id, state_type)
            self._add_to_cache(cache_key, result)
            return result
        
        # Fall back to direct database access
        try:
            if 'db_sqlite' in sys.modules:
                result = db_sqlite.get_entity_current_state(entity_type, entity_id, state_type)
                self._add_to_cache(cache_key, result)
                return result
            else:
                logger.warning("db_sqlite module not available for entity state retrieval")
                return None
        except Exception as e:
            logger.error(f"Error getting current state for {entity_type} {entity_id}: {e}")
            return None
    
    def get_entity_state_at_episode(self, entity_type: str, 
                                  entity_id: Optional[int] = None,
                                  entity_name: Optional[str] = None, 
                                  episode: str = "S01E01", 
                                  state_type: Optional[str] = None) -> Union[str, Dict[str, Any], None]:
        """
        Get an entity's state at a specific episode.
        
        Args:
            entity_type: Type of entity ('character', 'faction', 'location')
            entity_id: Optional ID of the entity
            entity_name: Optional name of the entity (used if ID not provided)
            episode: Episode identifier (e.g., 'S01E05')
            state_type: Optional specific state type to retrieve
            
        Returns:
            If state_type specified: the value for that state at the episode
            If state_type None: dictionary of all states at the episode
            None if entity not found
            
        Raises:
            ValueError: If neither entity_id nor entity_name is provided
            ValueError: If entity_type is invalid
        """
        # Validate entity type
        if entity_type not in self.entity_types:
            logger.error(f"Invalid entity type: {entity_type}")
            raise ValueError(f"Invalid entity type: {entity_type}. Must be one of: {', '.join(self.entity_types)}")
        
        # Ensure we have either ID or name
        if entity_id is None and entity_name is None:
            logger.error("Either entity_id or entity_name must be provided")
            raise ValueError("Either entity_id or entity_name must be provided")
        
        # Resolve entity_id from name if necessary
        if entity_id is None and entity_name is not None:
            entity_id = self._resolve_entity_id(entity_type, entity_name)
            if entity_id is None:
                logger.warning(f"Could not resolve entity ID for {entity_type} named '{entity_name}'")
                return None
        
        # Check cache
        cache_key = f"episode_state_{entity_type}_{entity_id}_{episode}_{state_type}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Use entity state manager if available
        if self.entity_state_manager:
            result = self.entity_state_manager.get_entity_state_at_episode(entity_type, entity_id, episode, state_type)
            self._add_to_cache(cache_key, result)
            return result
        
        # Fall back to direct database access
        try:
            if 'db_sqlite' in sys.modules:
                result = db_sqlite.get_entity_state_at_episode(entity_type, entity_id, episode, state_type)
                self._add_to_cache(cache_key, result)
                return result
            else:
                logger.warning("db_sqlite module not available for entity state retrieval")
                return None
        except Exception as e:
            logger.error(f"Error getting state at episode {episode} for {entity_type} {entity_id}: {e}")
            return None
    
    def get_entity_state_timeline(self, entity_type: str, 
                                entity_id: Optional[int] = None,
                                entity_name: Optional[str] = None, 
                                state_type: Optional[str] = None,
                                start_episode: Optional[str] = None, 
                                end_episode: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get a timeline of state changes for an entity.
        
        Args:
            entity_type: Type of entity ('character', 'faction', 'location')
            entity_id: Optional ID of the entity
            entity_name: Optional name of the entity (used if ID not provided)
            state_type: Optional specific state type to retrieve
            start_episode: Optional starting episode for timeline
            end_episode: Optional ending episode for timeline
            
        Returns:
            List of state records in chronological order
            
        Raises:
            ValueError: If neither entity_id nor entity_name is provided
            ValueError: If entity_type is invalid
        """
        # Validate entity type
        if entity_type not in self.entity_types:
            logger.error(f"Invalid entity type: {entity_type}")
            raise ValueError(f"Invalid entity type: {entity_type}. Must be one of: {', '.join(self.entity_types)}")
        
        # Ensure we have either ID or name
        if entity_id is None and entity_name is None:
            logger.error("Either entity_id or entity_name must be provided")
            raise ValueError("Either entity_id or entity_name must be provided")
        
        # Resolve entity_id from name if necessary
        if entity_id is None and entity_name is not None:
            entity_id = self._resolve_entity_id(entity_type, entity_name)
            if entity_id is None:
                logger.warning(f"Could not resolve entity ID for {entity_type} named '{entity_name}'")
                return []
        
        # Check cache
        cache_key = f"timeline_{entity_type}_{entity_id}_{state_type}_{start_episode}_{end_episode}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Use entity state manager if available
        if self.entity_state_manager:
            result = self.entity_state_manager.get_entity_state_history(
                entity_type, entity_id, state_type, start_episode, end_episode
            )
            self._add_to_cache(cache_key, result)
            return result
        
        # Fall back to direct database access
        try:
            if 'db_sqlite' in sys.modules:
                result = db_sqlite.get_entity_state_history(
                    entity_type, entity_id, state_type, start_episode, end_episode
                )
                self._add_to_cache(cache_key, result)
                return result
            else:
                logger.warning("db_sqlite module not available for entity timeline retrieval")
                return []
        except Exception as e:
            logger.error(f"Error getting state timeline for {entity_type} {entity_id}: {e}")
            return []
    
    def get_entities_with_state(self, entity_type: str, 
                              state_type: str, 
                              state_value: str, 
                              at_episode: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find all entities of a given type with a specific state.
        
        Args:
            entity_type: Type of entity to search for
            state_type: Type of state to match
            state_value: Value of state to match
            at_episode: Optional episode to check states at (defaults to current)
            
        Returns:
            List of entity data matching the criteria
            
        Raises:
            ValueError: If entity_type is invalid
            ValueError: If state_type is invalid for the entity type
        """
        # Validate entity type
        if entity_type not in self.entity_types:
            logger.error(f"Invalid entity type: {entity_type}")
            raise ValueError(f"Invalid entity type: {entity_type}. Must be one of: {', '.join(self.entity_types)}")
        
        # Validate state type for this entity type
        if state_type not in self.state_types.get(entity_type, set()):
            logger.error(f"Invalid state type '{state_type}' for entity type '{entity_type}'")
            raise ValueError(f"Invalid state type for {entity_type}: {state_type}")
        
        # Check cache
        cache_key = f"entities_with_state_{entity_type}_{state_type}_{state_value}_{at_episode}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Use entity state manager if available
        if self.entity_state_manager:
            result = self.entity_state_manager.get_entities_with_state(
                entity_type, state_type, state_value, at_episode
            )
            self._add_to_cache(cache_key, result)
            return result
        
        # Fall back to direct database access
        try:
            # This requires custom implementation as db_sqlite doesn't have a direct equivalent
            if 'db_sqlite' in sys.modules:
                results = []
                
                # First, get all entities of this type
                if entity_type == "character":
                    entities = db_sqlite.get_characters()
                    for entity in entities:
                        entity_id = entity.get("id")
                        # Check if this entity has the specified state
                        if at_episode:
                            state = db_sqlite.get_entity_state_at_episode(
                                entity_type, entity_id, at_episode, state_type
                            )
                        else:
                            state = db_sqlite.get_entity_current_state(
                                entity_type, entity_id, state_type
                            )
                        
                        if state == state_value:
                            results.append({
                                "entity_id": entity_id,
                                "entity_name": entity.get("name"),
                                "entity_type": entity_type,
                                "state_type": state_type,
                                "state_value": state_value
                            })
                
                # Add similar logic for other entity types if needed
                
                self._add_to_cache(cache_key, results)
                return results
            else:
                logger.warning("db_sqlite module not available for entity state filtering")
                return []
        except Exception as e:
            logger.error(f"Error finding entities with state {state_type}={state_value}: {e}")
            return []
    
    # --- Relationship state methods ---
    
    def get_relationship_state(self, 
                             entity1_type: str, 
                             entity2_type: str,
                             entity1_id: Optional[int] = None,
                             entity1_name: Optional[str] = None, 
                             entity2_id: Optional[int] = None, 
                             entity2_name: Optional[str] = None,
                             relationship_type: Optional[str] = None) -> Union[str, Dict[str, Any], None]:
        """
        Get the current state of a relationship between two entities.
        
        Args:
            entity1_type: Type of first entity
            entity2_type: Type of second entity
            entity1_id: Optional ID of first entity
            entity1_name: Optional name of first entity
            entity2_id: Optional ID of second entity
            entity2_name: Optional name of second entity
            relationship_type: Optional specific relationship type
            
        Returns:
            If relationship_type specified: the current value for that relationship
            If relationship_type None: dictionary of all relationship types and values
            None if entities not found
            
        Raises:
            ValueError: If neither ID nor name is provided for either entity
            ValueError: If entity types are invalid
        """
        # Validate entity types
        if entity1_type not in self.entity_types or entity2_type not in self.entity_types:
            logger.error(f"Invalid entity types: {entity1_type}, {entity2_type}")
            raise ValueError(f"Invalid entity types. Must be one of: {', '.join(self.entity_types)}")
        
        # Ensure we have either ID or name for both entities
        if (entity1_id is None and entity1_name is None) or (entity2_id is None and entity2_name is None):
            logger.error("Either ID or name must be provided for both entities")
            raise ValueError("Either ID or name must be provided for both entities")
        
        # Resolve entity IDs from names if necessary
        if entity1_id is None and entity1_name is not None:
            entity1_id = self._resolve_entity_id(entity1_type, entity1_name)
            if entity1_id is None:
                logger.warning(f"Could not resolve entity ID for {entity1_type} named '{entity1_name}'")
                return None
        
        if entity2_id is None and entity2_name is not None:
            entity2_id = self._resolve_entity_id(entity2_type, entity2_name)
            if entity2_id is None:
                logger.warning(f"Could not resolve entity ID for {entity2_type} named '{entity2_name}'")
                return None
        
        # Check cache
        cache_key = f"relationship_{entity1_type}_{entity1_id}_{entity2_type}_{entity2_id}_{relationship_type}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Use entity state manager if available
        if self.entity_state_manager:
            result = self.entity_state_manager.get_relationship_current_state(
                entity1_type, entity1_id, entity2_type, entity2_id, relationship_type
            )
            self._add_to_cache(cache_key, result)
            return result
        
        # Fall back to direct database access
        try:
            if 'db_sqlite' in sys.modules:
                result = db_sqlite.get_relationship_current_state(
                    entity1_type, entity1_id, entity2_type, entity2_id, relationship_type
                )
                self._add_to_cache(cache_key, result)
                return result
            else:
                logger.warning("db_sqlite module not available for relationship state retrieval")
                return None
        except Exception as e:
            logger.error(f"Error getting relationship state between {entity1_type} {entity1_id} and {entity2_type} {entity2_id}: {e}")
            return None
    
    def get_relationship_state_at_episode(self, 
                                        entity1_type: str,
                                        entity2_type: str,
                                        entity1_id: Optional[int] = None,
                                        entity1_name: Optional[str] = None,
                                        entity2_id: Optional[int] = None,
                                        entity2_name: Optional[str] = None,
                                        episode: str = "S01E01",
                                        relationship_type: Optional[str] = None) -> Union[str, Dict[str, Any], None]:
        """
        Get the state of a relationship at a specific episode.
        
        Args:
            entity1_type: Type of first entity
            entity2_type: Type of second entity
            entity1_id: Optional ID of first entity
            entity1_name: Optional name of first entity
            entity2_id: Optional ID of second entity
            entity2_name: Optional name of second entity
            episode: Episode identifier
            relationship_type: Optional specific relationship type
            
        Returns:
            If relationship_type specified: the value for that relationship at the episode
            If relationship_type None: dictionary of all relationship types and values at the episode
            None if entities not found
            
        Raises:
            ValueError: If neither ID nor name is provided for either entity
            ValueError: If entity types are invalid
        """
        # Validate entity types
        if entity1_type not in self.entity_types or entity2_type not in self.entity_types:
            logger.error(f"Invalid entity types: {entity1_type}, {entity2_type}")
            raise ValueError(f"Invalid entity types. Must be one of: {', '.join(self.entity_types)}")
        
        # Ensure we have either ID or name for both entities
        if (entity1_id is None and entity1_name is None) or (entity2_id is None and entity2_name is None):
            logger.error("Either ID or name must be provided for both entities")
            raise ValueError("Either ID or name must be provided for both entities")
        
        # Resolve entity IDs from names if necessary
        if entity1_id is None and entity1_name is not None:
            entity1_id = self._resolve_entity_id(entity1_type, entity1_name)
            if entity1_id is None:
                logger.warning(f"Could not resolve entity ID for {entity1_type} named '{entity1_name}'")
                return None
        
        if entity2_id is None and entity2_name is not None:
            entity2_id = self._resolve_entity_id(entity2_type, entity2_name)
            if entity2_id is None:
                logger.warning(f"Could not resolve entity ID for {entity2_type} named '{entity2_name}'")
                return None
        
        # Check cache
        cache_key = f"relationship_episode_{entity1_type}_{entity1_id}_{entity2_type}_{entity2_id}_{episode}_{relationship_type}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Get relationship history
        try:
            # Note: This implementation requires us to get relationship history and filter
            # since entity_state_manager doesn't have a direct method for this
            
            # First, get current state (as a fallback)
            current_state = None
            if self.entity_state_manager:
                current_state = self.entity_state_manager.get_relationship_current_state(
                    entity1_type, entity1_id, entity2_type, entity2_id, relationship_type
                )
            elif 'db_sqlite' in sys.modules:
                current_state = db_sqlite.get_relationship_current_state(
                    entity1_type, entity1_id, entity2_type, entity2_id, relationship_type
                )
            
            # Then, try to find state at the specified episode
            # This would require implementing a custom query or using existing relationship
            # history methods if available - for now, we'll just return the current state
            # with a warning
            
            logger.warning(f"Relationship state history not directly accessible. Using current state for {episode}")
            self._add_to_cache(cache_key, current_state)
            return current_state
            
        except Exception as e:
            logger.error(f"Error getting relationship state at episode {episode}: {e}")
            return None
    
    def get_relationship_network(self, entity_type: str,
                               entity_id: Optional[int] = None,
                               entity_name: Optional[str] = None,
                               depth: int = 1,
                               at_episode: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the network of relationships for an entity.
        
        Args:
            entity_type: Type of entity
            entity_id: Optional ID of entity
            entity_name: Optional name of entity
            depth: How many degrees of separation to include (1 = direct connections only)
            at_episode: Optional episode to check relationships at (defaults to current)
            
        Returns:
            Dictionary containing relationship network information
            
        Raises:
            ValueError: If neither entity_id nor entity_name is provided
            ValueError: If entity_type is invalid
        """
        # Validate entity type
        if entity_type not in self.entity_types:
            logger.error(f"Invalid entity type: {entity_type}")
            raise ValueError(f"Invalid entity type: {entity_type}. Must be one of: {', '.join(self.entity_types)}")
        
        # Ensure we have either ID or name
        if entity_id is None and entity_name is None:
            logger.error("Either entity_id or entity_name must be provided")
            raise ValueError("Either entity_id or entity_name must be provided")
        
        # Resolve entity_id from name if necessary
        if entity_id is None and entity_name is not None:
            entity_id = self._resolve_entity_id(entity_type, entity_name)
            if entity_id is None:
                logger.warning(f"Could not resolve entity ID for {entity_type} named '{entity_name}'")
                return {
                    "entity_type": entity_type,
                    "entity_name": entity_name,
                    "relationships": []
                }
        
        # Check cache
        cache_key = f"network_{entity_type}_{entity_id}_{depth}_{at_episode}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Use entity state manager if available
        if self.entity_state_manager:
            # Get entity name if we only have ID
            if entity_name is None:
                entity_name = self._get_entity_name(entity_type, entity_id)
            
            # Get relationships for this entity
            if at_episode:
                relationships = self.entity_state_manager.get_relationships_for_entity(
                    entity_type, entity_id, at_episode
                )
            else:
                relationships = self.entity_state_manager.get_relationships_for_entity(
                    entity_type, entity_id
                )
            
            # Format result
            result = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "relationships": relationships
            }
            
            # If depth > 1, recursively get relationship networks for connected entities
            if depth > 1:
                for relationship in relationships:
                    related_entity_type = relationship.get("entity_type")
                    related_entity_id = relationship.get("entity_id")
                    
                    # Skip if missing info
                    if not related_entity_type or not related_entity_id:
                        continue
                    
                    # Recursively get network (depth - 1)
                    related_network = self.get_relationship_network(
                        related_entity_type, related_entity_id, None, depth - 1, at_episode
                    )
                    
                    # Add to relationship
                    relationship["network"] = related_network
            
            self._add_to_cache(cache_key, result)
            return result
        
        # Fall back to direct database access
        try:
            if 'db_sqlite' in sys.modules and entity_type == "character":
                # Character relationships are handled differently
                relationships = db_sqlite.get_character_relationships_for_character(entity_id)
                
                # Get entity name if we only have ID
                if entity_name is None:
                    character = db_sqlite.get_character_by_id(entity_id)
                    if character:
                        entity_name = character.get("name")
                
                # Format result
                result = {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "relationships": relationships
                }
                
                self._add_to_cache(cache_key, result)
                return result
            else:
                logger.warning("db_sqlite module not available or entity type not supported")
                return {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "relationships": []
                }
        except Exception as e:
            logger.error(f"Error getting relationship network for {entity_type} {entity_id}: {e}")
            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "relationships": []
            }
    
    # --- Location and faction specific methods ---
    
    def get_faction_territories(self, faction_id: Optional[int] = None, 
                              faction_name: Optional[str] = None,
                              at_episode: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get territories controlled by a faction at a specific point in time.
        
        Args:
            faction_id: Optional ID of the faction
            faction_name: Optional name of the faction
            at_episode: Optional episode to check control at (defaults to current)
            
        Returns:
            List of locations under faction control
            
        Raises:
            ValueError: If neither faction_id nor faction_name is provided
        """
        # Ensure we have either ID or name
        if faction_id is None and faction_name is None:
            logger.error("Either faction_id or faction_name must be provided")
            raise ValueError("Either faction_id or faction_name must be provided")
        
        # Resolve faction_id from name if necessary
        if faction_id is None and faction_name is not None:
            faction_id = self._resolve_entity_id("faction", faction_name)
            if faction_id is None:
                logger.warning(f"Could not resolve entity ID for faction named '{faction_name}'")
                return []
        
        # Check cache
        cache_key = f"territories_faction_{faction_id}_{at_episode}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Initialize result
        territories = []
        
        # Get faction name if we only have ID
        if faction_name is None:
            faction_name = self._get_entity_name("faction", faction_id)
        
        try:
            # Get all locations
            if 'db_sqlite' in sys.modules:
                locations = db_sqlite.get_locations()
                
                # For each location, check if it's controlled by this faction
                for location_name, location_data in locations.items():
                    # Get location control state
                    location_id = location_data.get("id")  # This might need adjustment based on actual db schema
                    
                    # Get control state
                    control_state = None
                    if at_episode:
                        control_state = self.get_entity_state_at_episode(
                            "location", location_id, at_episode, "control"
                        )
                    else:
                        control_state = self.get_entity_current_state(
                            "location", location_id, "control"
                        )
                    
                    # Check if this faction controls the location
                    if control_state and (control_state == faction_name or str(control_state) == str(faction_id)):
                        territories.append({
                            "location_id": location_id,
                            "location_name": location_name,
                            "status": location_data.get("status"),
                            "description": location_data.get("description")
                        })
            
            self._add_to_cache(cache_key, territories)
            return territories
            
        except Exception as e:
            logger.error(f"Error getting faction territories for {faction_name}: {e}")
            return []
    
    def get_location_state(self, location_id: Optional[int] = None,
                         location_name: Optional[str] = None,
                         at_episode: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the state of a location at a specific point in time.
        
        Args:
            location_id: Optional ID of the location
            location_name: Optional name of the location
            at_episode: Optional episode to check state at (defaults to current)
            
        Returns:
            Dictionary with location state information
            
        Raises:
            ValueError: If neither location_id nor location_name is provided
        """
        # Ensure we have either ID or name
        if location_id is None and location_name is None:
            logger.error("Either location_id or location_name must be provided")
            raise ValueError("Either location_id or location_name must be provided")
        
        # Resolve location_id from name if necessary
        if location_id is None and location_name is not None:
            location_id = self._resolve_entity_id("location", location_name)
            if location_id is None:
                logger.warning(f"Could not resolve entity ID for location named '{location_name}'")
                return {}
        
        # Get location name if we only have ID
        if location_name is None:
            location_name = self._get_entity_name("location", location_id)
        
        # Check cache
        cache_key = f"location_state_{location_id}_{at_episode}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            # Get location data
            location_data = {}
            if 'db_sqlite' in sys.modules:
                location = db_sqlite.get_location_by_name(location_name)
                if location:
                    location_data = location
            
            # Get location state
            if at_episode:
                state = self.get_entity_state_at_episode("location", location_id, at_episode)
            else:
                state = self.get_entity_current_state("location", location_id)
            
            # Combine location data and state
            result = {
                "location_id": location_id,
                "location_name": location_name,
                "description": location_data.get("description", ""),
                "historical_significance": location_data.get("historical_significance", ""),
                "status": location_data.get("status", ""),
                "state": state or {}
            }
            
            self._add_to_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error getting location state for {location_name}: {e}")
            return {
                "location_id": location_id,
                "location_name": location_name,
                "state": {}
            }
    
    def get_characters_at_location(self, location_id: Optional[int] = None,
                                 location_name: Optional[str] = None,
                                 at_episode: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all characters currently at a specific location.
        
        Args:
            location_id: Optional ID of the location
            location_name: Optional name of the location
            at_episode: Optional episode to check (defaults to current)
            
        Returns:
            List of characters at the location
            
        Raises:
            ValueError: If neither location_id nor location_name is provided
        """
        # Ensure we have either ID or name
        if location_id is None and location_name is None:
            logger.error("Either location_id or location_name must be provided")
            raise ValueError("Either location_id or location_name must be provided")
        
        # Resolve location_id from name if necessary
        if location_id is None and location_name is not None:
            location_id = self._resolve_entity_id("location", location_name)
            if location_id is None:
                logger.warning(f"Could not resolve entity ID for location named '{location_name}'")
                return []
        
        # Get location name if we only have ID
        if location_name is None:
            location_name = self._get_entity_name("location", location_id)
        
        # Check cache
        cache_key = f"characters_at_location_{location_id}_{at_episode}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            characters = []
            
            # Get all characters
            if 'db_sqlite' in sys.modules:
                char_list = db_sqlite.get_characters()
                
                # For each character, check if they're at this location
                for character in char_list:
                    char_id = character.get("id")
                    
                    # Get location state
                    location_state = None
                    if at_episode:
                        location_state = self.get_entity_state_at_episode(
                            "character", char_id, at_episode, "location"
                        )
                    else:
                        location_state = self.get_entity_current_state(
                            "character", char_id, "location"
                        )
                    
                    # Check if character is at this location
                    if location_state and (location_state == location_name or str(location_state) == str(location_id)):
                        characters.append({
                            "character_id": char_id,
                            "character_name": character.get("name"),
                            "description": character.get("description", "")
                        })
            
            self._add_to_cache(cache_key, characters)
            return characters
            
        except Exception as e:
            logger.error(f"Error getting characters at location {location_name}: {e}")
            return []
    
    # --- World state snapshot methods ---
    
    def get_world_state_snapshot(self, episode: str) -> Dict[str, Any]:
        """
        Get a comprehensive snapshot of the world state at a specific episode.
        
        Args:
            episode: Episode identifier
            
        Returns:
            Dictionary containing state information for key entities and relationships
        """
        # Check cache
        cache_key = f"world_snapshot_{episode}"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            # Initialize snapshot structure
            snapshot = {
                "episode": episode,
                "timestamp": time.time(),
                "characters": {},
                "factions": {},
                "locations": {},
                "key_relationships": []
            }
            
            # Get all characters, factions, and locations
            if 'db_sqlite' in sys.modules:
                # Get characters
                characters = db_sqlite.get_characters()
                for character in characters:
                    char_id = character.get("id")
                    char_name = character.get("name")
                    
                    # Get character state at this episode
                    state = self.get_entity_state_at_episode("character", char_id, episode)
                    
                    snapshot["characters"][char_name] = {
                        "id": char_id,
                        "description": character.get("description", ""),
                        "state": state or {}
                    }
                
                # Get factions
                factions = db_sqlite.get_factions()
                for faction_name, faction_data in factions.items():
                    faction_id = faction_data.get("id")  # This might need adjustment
                    
                    # Get faction state at this episode
                    state = self.get_entity_state_at_episode("faction", faction_id, episode)
                    
                    # Get territories
                    territories = self.get_faction_territories(faction_id, None, episode)
                    
                    snapshot["factions"][faction_name] = {
                        "id": faction_id,
                        "ideology": faction_data.get("ideology", ""),
                        "state": state or {},
                        "territories": territories
                    }
                
                # Get locations
                locations = db_sqlite.get_locations()
                for location_name, location_data in locations.items():
                    location_id = location_data.get("id")  # This might need adjustment
                    
                    # Get location state at this episode
                    state = self.get_entity_state_at_episode("location", location_id, episode)
                    
                    # Get characters at this location
                    characters_at_location = self.get_characters_at_location(location_id, None, episode)
                    
                    snapshot["locations"][location_name] = {
                        "id": location_id,
                        "description": location_data.get("description", ""),
                        "state": state or {},
                        "characters": characters_at_location
                    }
                
                # Get important relationships
                # This is simplified - in a full implementation, you'd have logic to
                # determine which relationships are important enough to include
                for char_name, char_data in snapshot["characters"].items():
                    char_id = char_data.get("id")
                    
                    # Get this character's relationships
                    network = self.get_relationship_network("character", char_id, None, 1, episode)
                    
                    for relationship in network.get("relationships", []):
                        other_name = relationship.get("entity_name")
                        if not other_name:
                            continue
                            
                        # Add to key relationships if it seems important
                        # This is a simplified heuristic - in reality, you'd have more nuanced logic
                        rel_type = relationship.get("relationship_type", "")
                        if rel_type in ["alliance", "trust", "power"]:
                            snapshot["key_relationships"].append({
                                "entity1_name": char_name,
                                "entity2_name": other_name,
                                "relationship_type": rel_type,
                                "state_value": relationship.get("state_value", "")
                            })
            
            self._add_to_cache(cache_key, snapshot)
            return snapshot
            
        except Exception as e:
            logger.error(f"Error generating world state snapshot for episode {episode}: {e}")
            return {
                "episode": episode,
                "timestamp": time.time(),
                "error": str(e),
                "characters": {},
                "factions": {},
                "locations": {}
            }
    
    def get_entity_conflicts(self) -> List[Dict[str, Any]]:
        """
        Get all unresolved entity state conflicts.
        
        Returns:
            List of unresolved state conflicts
        """
        # Check cache
        cache_key = "unresolved_conflicts"
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Use entity state manager if available
        if self.entity_state_manager:
            result = self.entity_state_manager.get_unresolved_conflicts()
            self._add_to_cache(cache_key, result)
            return result
        
        # Fall back to direct database access
        try:
            if 'db_sqlite' in sys.modules:
                # This would need db_sqlite to implement a get_unresolved_conflicts function
                # For now, return an empty list with a warning
                logger.warning("get_unresolved_conflicts not implemented in db_sqlite")
                return []
            else:
                logger.warning("db_sqlite module not available for conflict retrieval")
                return []
        except Exception as e:
            logger.error(f"Error getting unresolved conflicts: {e}")
            return []
    
    # --- Helper methods ---
    
    def _resolve_entity_id(self, entity_type: str, entity_name: str) -> Optional[int]:
        """
        Resolve entity ID from name.
        
        Args:
            entity_type: Type of entity
            entity_name: Name of the entity
            
        Returns:
            Entity ID if found, None otherwise
        """
        try:
            if 'db_sqlite' in sys.modules:
                if entity_type == "character":
                    character = db_sqlite.get_character_by_name(entity_name)
                    return character["id"] if character else None
                elif entity_type == "faction":
                    faction = db_sqlite.get_faction_by_name(entity_name)
                    # The ID field might be different for factions - adjust as needed
                    return faction["id"] if faction else None
                elif entity_type == "location":
                    location = db_sqlite.get_location_by_name(entity_name)
                    # The ID field might be different for locations - adjust as needed
                    return location["id"] if location else None
            return None
        except Exception as e:
            logger.error(f"Error resolving entity ID for {entity_type} {entity_name}: {e}")
            return None
    
    def _get_entity_name(self, entity_type: str, entity_id: int) -> Optional[str]:
        """
        Get entity name from ID.
        
        Args:
            entity_type: Type of entity
            entity_id: ID of the entity
            
        Returns:
            Entity name if found, None otherwise
        """
        try:
            if 'db_sqlite' in sys.modules:
                if entity_type == "character":
                    character = db_sqlite.get_character_by_id(entity_id)
                    return character["name"] if character else None
                elif entity_type == "faction":
                    # This would need a get_faction_by_id method in db_sqlite
                    # For now, return a default name with a warning
                    logger.warning("get_faction_by_id not implemented in db_sqlite")
                    return f"Faction_{entity_id}"
                elif entity_type == "location":
                    # This would need a get_location_by_id method in db_sqlite
                    # For now, return a default name with a warning
                    logger.warning("get_location_by_id not implemented in db_sqlite")
                    return f"Location_{entity_id}"
            return None
        except Exception as e:
            logger.error(f"Error getting entity name for {entity_type} {entity_id}: {e}")
            return None
    
    # --- Cache management methods ---
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache if it exists and is not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value if found and not expired, None otherwise
        """
        if not self.settings.get("cache_results", True):
            return None
        
        if key in self._cache and key in self._cache_timestamps:
            # Check if cache entry is expired
            cache_age = time.time() - self._cache_timestamps[key]
            if cache_age < self.settings.get("cache_timeout", 300):
                return self._cache[key]
            else:
                # Remove expired cache entry
                del self._cache[key]
                del self._cache_timestamps[key]
        
        return None
    
    def _add_to_cache(self, key: str, value: Any) -> None:
        """
        Add a value to the cache.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        if not self.settings.get("cache_results", True):
            return
        
        # Check cache size limit
        cache_max_size = self.settings.get("cache_max_size", 1000)
        if len(self._cache) >= cache_max_size:
            # Remove oldest entries
            oldest_keys = sorted(self._cache_timestamps.keys(), key=lambda k: self._cache_timestamps[k])
            # Remove about 10% of the oldest entries
            for old_key in oldest_keys[:max(1, cache_max_size // 10)]:
                del self._cache[old_key]
                del self._cache_timestamps[old_key]
        
        # Add to cache
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()
    
    def clear_cache(self) -> None:
        """Clear the entire cache."""
        self._cache = {}
        self._cache_timestamps = {}
        logger.info("Cache cleared")
    
    def invalidate_cache_for_entity(self, entity_type: str, entity_id: int) -> None:
        """
        Invalidate all cache entries for a specific entity.
        
        Args:
            entity_type: Type of entity
            entity_id: ID of the entity
        """
        keys_to_remove = []
        entity_prefix = f"{entity_type}_{entity_id}"
        
        # Find all keys related to this entity
        for key in self._cache.keys():
            if entity_prefix in key:
                keys_to_remove.append(key)
        
        # Remove the keys
        for key in keys_to_remove:
            del self._cache[key]
            if key in self._cache_timestamps:
                del self._cache_timestamps[key]
        
        logger.info(f"Invalidated {len(keys_to_remove)} cache entries for {entity_type} {entity_id}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "size": len(self._cache),
            "max_size": self.settings.get("cache_max_size", 1000),
            "timeout": self.settings.get("cache_timeout", 300),
            "enabled": self.settings.get("cache_results", True),
            "hit_ratio": 0.0,  # Would need to track hits/misses to calculate
            "oldest_entry_age": 0,
            "newest_entry_age": 0
        }
        
        if self._cache_timestamps:
            current_time = time.time()
            oldest = min(self._cache_timestamps.values())
            newest = max(self._cache_timestamps.values())
            stats["oldest_entry_age"] = round(current_time - oldest)
            stats["newest_entry_age"] = round(current_time - newest)
        
        return stats

def run_tests():
    """
    Run tests for the StateReader
    
    Returns:
        True if all tests pass, False otherwise
    """
    # If the testing module is available, use it for more comprehensive testing
    try:
        from prove import TestEnvironment
        
        # Define test functions
        def test_entity_current_state():
            reader = StateReader()
            try:
                # Test with a character from test data
                state = reader.get_entity_current_state("character", entity_id=1)
                return True
            except Exception as e:
                print(f"Test failed: {e}")
                return False
                
        def test_relationship_state():
            reader = StateReader()
            try:
                # Test with characters from test data
                state = reader.get_relationship_state(
                    entity1_type="character", entity2_type="character",
                    entity1_id=1, entity2_id=2
                )
                return True
            except Exception as e:
                print(f"Test failed: {e}")
                return False
        
        # Run tests using the test environment
        with TestEnvironment() as env:
            all_passed = True
            all_passed &= env.run_test("Entity Current State", test_entity_current_state)
            all_passed &= env.run_test("Relationship State", test_relationship_state)
            return all_passed
    
    except ImportError:
        # Fallback to simple testing
        print("Running basic tests without TestEnvironment")
        reader = StateReader()
        
        try:
            # Basic test - entity state access
            state = reader.get_entity_current_state("character", entity_id=1)
            print(f"Character state: {state}")
            
            # Relationship state access
            rel_state = reader.get_relationship_state(
                entity1_type="character", entity2_type="character",
                entity1_id=1, entity2_id=2
            )
            print(f"Relationship state: {rel_state}")
            
            return True
        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    # Run tests when executed directly
    result = run_tests()
    if result:
        print("All tests passed!")
    else:
        print("Tests failed.")
        sys.exit(1)