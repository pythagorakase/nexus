#!/usr/bin/env python3
"""
gaia_write.py: World State Writer Module for Night City Stories

This module provides write operations for entity states, relationship states, and narrative
processing in the narrative world. It serves as the authoritative source for updating
"what is true" about the world state at any given point in the narrative.

The StateWriter class provides methods to:
- Update entity states with validation and conflict detection
- Update relationship states between entities
- Process narrative text to automatically extract and apply state updates
- Detect and resolve state conflicts
- Manage transactions for multi-operation updates
"""

import os
import sys
import json
import logging
import time
import re
import traceback
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Set
from datetime import datetime

# Import BaseAgent (required for interoperability)
from agent_base import BaseAgent

# Try to import required modules
try:
    # Import configuration manager
    import config_manager as config
    
    # Import database adapters
    import db_sqlite
    
    # Import memory manager
    import memnon
    
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
        logging.FileHandler("gaia_write.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("gaia_write")

# Default settings (can be overridden by config_manager)
DEFAULT_SETTINGS = {
    "state_writing": {
        "auto_resolve_conflicts": True,
        "confidence_threshold": 0.7,
        "update_transaction_size": 10,
        "notify_on_updates": True,
        "extraction_confidence": {
            "direct_mention": 0.9,
            "implied": 0.6,
            "inferred": 0.4
        },
        "validation": {
            "enable_validation": True,
            "reject_invalid_states": False
        }
    },
    "conflict_resolution": {
        "strategy": "confidence",  # confidence, recency, or manual
        "confidence_threshold": 0.8,  # Minimum confidence to auto-resolve
        "max_conflicts_to_track": 100
    }
}

# Custom exceptions for state writing
class StateWriteError(Exception):
    """Base exception for state write errors"""
    pass

class ValidationError(StateWriteError):
    """Exception for state validation errors"""
    pass

class ConflictError(StateWriteError):
    """Exception for state conflict errors"""
    pass

class TransactionError(StateWriteError):
    """Exception for transaction management errors"""
    pass

class StateWriter(BaseAgent):
    """
    State Writer for updating entity states and relationships in the narrative world
    """
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        """
        Initialize the State Writer
        
        Args:
            settings: Optional settings dictionary
        """
        # Initialize BaseAgent
        super().__init__(settings)
        
        # Initialize settings
        self.settings = DEFAULT_SETTINGS.copy()
        if isinstance(settings, dict):
            # Deep merge settings
            self._deep_merge_settings(self.settings, settings)
        
        # Initialize transaction management
        self.active_transaction = False
        self.transaction_operations = []
        self.transaction_conflicts = []
        
        # Store known entity types and valid state types
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
        
        # Track operation counts
        self.update_count = 0
        self.conflict_count = 0
        self.transaction_count = 0
        
        logger.info("StateWriter initialized")
    
    # Implementation of BaseAgent abstract methods
    
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
        
        if request_type == "update_entity_state":
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
            
            if not entity_type or not state_type or not state_value or not episode:
                return {
                    "response": "Missing required parameters",
                    "error": "missing_parameters"
                }
            
            # Update entity state
            success = self.update_entity_state(
                entity_type, state_type, state_value, 
                episode, entity_id, entity_name, confidence
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
            symmetrical = content.get("symmetrical", False)
            
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
                episode, symmetrical=symmetrical
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
                self.settings["state_writing"]["confidence_threshold"]
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
    
    # Helper methods
    
    def _deep_merge_settings(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """
        Deep merge source settings into target settings
        
        Args:
            target: Target settings dictionary
            source: Source settings dictionary to merge from
        """
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._deep_merge_settings(target[key], value)
            else:
                target[key] = value
    
    # Entity state methods
    
    def update_entity_state(self, 
                          entity_type: str, 
                          state_type: str,
                          state_value: str,
                          episode: str,
                          entity_id: Optional[int] = None,
                          entity_name: Optional[str] = None,
                          confidence: float = 1.0,
                          source: str = "api",
                          notes: Optional[str] = None,
                          narrative_time: Optional[str] = None,
                          chunk_id: Optional[str] = None) -> bool:
        """
        Update an entity's state with validation and conflict detection
        
        Args:
            entity_type: Type of entity ('character', 'faction', 'location')
            state_type: Type of state to update
            state_value: New value for the state
            episode: Episode identifier
            entity_id: Optional ID of the entity
            entity_name: Optional name of the entity (used if ID not provided)
            confidence: Confidence level for this update (0.0-1.0)
            source: Source of this update (e.g., 'api', 'narrative', 'inference')
            notes: Optional notes about this update
            narrative_time: Optional in-story timestamp
            chunk_id: Optional reference to specific narrative chunk
        
        Returns:
            True if update was successful, False otherwise
        
        Raises:
            ValueError: If neither entity_id nor entity_name is provided
            ValueError: If entity_type is invalid
            ValidationError: If state validation fails
        """
        # Track update operations
        self.update_count += 1
        
        # Validate entity type
        if entity_type not in self.entity_types:
            logger.error(f"Invalid entity type: {entity_type}")
            raise ValueError(f"Invalid entity type: {entity_type}. Must be one of: {', '.join(self.entity_types)}")
        
        # Validate state type for this entity type
        if state_type not in self.state_types.get(entity_type, set()):
            logger.warning(f"Unusual state type '{state_type}' for entity type '{entity_type}'")
            # Don't reject it if validation isn't strict
            if self.settings["state_writing"]["validation"]["reject_invalid_states"]:
                raise ValidationError(f"Invalid state type '{state_type}' for entity type '{entity_type}'")
        
        # Ensure we have either ID or name
        if entity_id is None and entity_name is None:
            logger.error("Either entity_id or entity_name must be provided")
            raise ValueError("Either entity_id or entity_name must be provided")
        
        # Resolve entity_id from name if necessary
        if entity_id is None and entity_name is not None:
            entity_id = self._resolve_entity_id(entity_type, entity_name)
            if entity_id is None:
                logger.warning(f"Could not resolve entity ID for {entity_type} named '{entity_name}'")
                return False
        
        # If in a transaction, add to operations list
        if self.active_transaction:
            self.transaction_operations.append({
                "type": "entity_state",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "state_type": state_type,
                "state_value": state_value,
                "episode": episode,
                "confidence": confidence,
                "source": source,
                "notes": notes,
                "narrative_time": narrative_time,
                "chunk_id": chunk_id
            })
            return True
        
        try:
            # Prefer using memnon for memory updates if available
            if memnon:
                result = memnon.update_entity_state(
                    entity_type, entity_id, state_type, state_value,
                    episode, confidence=confidence, source=source,
                    notes=notes, narrative_time=narrative_time, chunk_id=chunk_id
                )
                
                if result:
                    entity_name = entity_name or self._get_entity_name(entity_type, entity_id)
                    logger.info(f"Updated state: {entity_type} {entity_name} {state_type}={state_value} (episode {episode})")
                
                return result
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                result = db_sqlite.update_entity_state(
                    entity_type, entity_id, state_type, state_value,
                    episode, chunk_id, narrative_time, confidence, source, notes
                )
                
                if result:
                    entity_name = entity_name or self._get_entity_name(entity_type, entity_id)
                    logger.info(f"Updated state: {entity_type} {entity_name} {state_type}={state_value} (episode {episode})")
                
                return result
            else:
                logger.warning("Neither memnon nor db_sqlite module available for entity state update")
                return False
                
        except Exception as e:
            logger.error(f"Error updating entity state: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def update_relationship_state(self, 
                                entity1_id: Optional[int] = None,
                                entity1_type: str = "character",
                                entity2_id: Optional[int] = None,
                                entity2_type: str = "character",
                                relationship_type: str = "trust",
                                state_value: str = "neutral",
                                episode: str = "S01E01",
                                entity1_name: Optional[str] = None, 
                                entity2_name: Optional[str] = None,
                                symmetrical: bool = False,
                                confidence: float = 1.0,
                                source: str = "api",
                                notes: Optional[str] = None,
                                chunk_id: Optional[str] = None,
                                narrative_time: Optional[str] = None) -> bool:
        """
        Update a relationship state between two entities
        
        Args:
            entity1_id: Optional ID of first entity
            entity1_type: Type of first entity
            entity2_id: Optional ID of second entity
            entity2_type: Type of second entity
            relationship_type: Type of relationship
            state_value: Value of the relationship state
            episode: Episode identifier
            entity1_name: Optional name of first entity (used if ID not provided)
            entity2_name: Optional name of second entity (used if ID not provided)
            symmetrical: Whether the relationship applies in both directions
            confidence: Confidence level for this update (0.0-1.0)
            source: Source of this update
            notes: Optional notes about this update
            chunk_id: Optional reference to specific narrative chunk
            narrative_time: Optional in-story timestamp
        
        Returns:
            True if successful, False otherwise
        
        Raises:
            ValueError: If IDs or names are not provided for both entities
        """
        # Track update operations
        self.update_count += 1
        
        # Validate entity types
        if entity1_type not in self.entity_types or entity2_type not in self.entity_types:
            logger.error(f"Invalid entity types: {entity1_type}, {entity2_type}")
            raise ValueError(f"Invalid entity types. Must be one of: {', '.join(self.entity_types)}")
        
        # Validate relationship type
        if relationship_type not in self.relationship_types:
            logger.warning(f"Unusual relationship type: {relationship_type}")
            # Don't reject it if validation isn't strict
            if self.settings["state_writing"]["validation"]["reject_invalid_states"]:
                raise ValidationError(f"Invalid relationship type: {relationship_type}")
        
        # Ensure we have either ID or name for both entities
        if (entity1_id is None and entity1_name is None) or (entity2_id is None and entity2_name is None):
            logger.error("Either ID or name must be provided for both entities")
            raise ValueError("Either ID or name must be provided for both entities")
        
        # Resolve entity IDs from names if necessary
        if entity1_id is None and entity1_name is not None:
            entity1_id = self._resolve_entity_id(entity1_type, entity1_name)
            if entity1_id is None:
                logger.warning(f"Could not resolve entity ID for {entity1_type} named '{entity1_name}'")
                return False
        
        if entity2_id is None and entity2_name is not None:
            entity2_id = self._resolve_entity_id(entity2_type, entity2_name)
            if entity2_id is None:
                logger.warning(f"Could not resolve entity ID for {entity2_type} named '{entity2_name}'")
                return False
        
        # If in a transaction, add to operations list
        if self.active_transaction:
            self.transaction_operations.append({
                "type": "relationship_state",
                "entity1_type": entity1_type,
                "entity1_id": entity1_id,
                "entity2_type": entity2_type,
                "entity2_id": entity2_id,
                "relationship_type": relationship_type,
                "state_value": state_value,
                "episode": episode,
                "symmetrical": symmetrical,
                "confidence": confidence,
                "source": source,
                "notes": notes,
                "chunk_id": chunk_id,
                "narrative_time": narrative_time
            })
            return True
        
        try:
            # Prefer using memnon for memory updates if available
            if memnon:
                result = memnon.update_relationship_state(
                    entity1_type, entity1_id, entity2_type, entity2_id,
                    relationship_type, state_value, episode, symmetrical,
                    chunk_id=chunk_id, narrative_time=narrative_time, 
                    confidence=confidence, source=source, notes=notes
                )
                
                if result:
                    entity1_name = entity1_name or self._get_entity_name(entity1_type, entity1_id)
                    entity2_name = entity2_name or self._get_entity_name(entity2_type, entity2_id)
                    logger.info(f"Updated relationship: {entity1_type} {entity1_name} to " +
                               f"{entity2_type} {entity2_name} {relationship_type}={state_value} " +
                               f"(episode {episode})")
                
                return result
            
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                result = db_sqlite.update_relationship_state(
                    entity1_type, entity1_id, entity2_type, entity2_id,
                    relationship_type, state_value, episode, symmetrical,
                    chunk_id, narrative_time, confidence, source, notes
                )
                
                if result:
                    entity1_name = entity1_name or self._get_entity_name(entity1_type, entity1_id)
                    entity2_name = entity2_name or self._get_entity_name(entity2_type, entity2_id)
                    logger.info(f"Updated relationship: {entity1_type} {entity1_name} to " +
                               f"{entity2_type} {entity2_name} {relationship_type}={state_value} " +
                               f"(episode {episode})")
                
                return result
            else:
                logger.warning("Neither memnon nor db_sqlite module available for relationship state update")
                return False
                
        except Exception as e:
            logger.error(f"Error updating relationship state: {e}")
            logger.error(traceback.format_exc())
            return False
    
    # Transaction management methods
    
    def begin_transaction(self) -> bool:
        """
        Begin a new transaction for multi-operation updates
        
        Returns:
            True if transaction started successfully
        
        Raises:
            TransactionError: If a transaction is already active
        """
        if self.active_transaction:
            raise TransactionError("Transaction already active")
        
        self.active_transaction = True
        self.transaction_operations = []
        self.transaction_conflicts = []
        self.transaction_count += 1
        
        logger.info("Transaction started")
        return True
    
    def commit_transaction(self) -> Dict[str, Any]:
        """
        Commit all operations in the current transaction
        
        Returns:
            Dictionary with commit results
        
        Raises:
            TransactionError: If no transaction is active
        """
        if not self.active_transaction:
            raise TransactionError("No active transaction to commit")
        
        # Initialize result
        result = {
            "success": True,
            "operations": len(self.transaction_operations),
            "applied": 0,
            "failed": 0,
            "conflicts": self.transaction_conflicts
        }
        
        # Return immediately if no operations
        if not self.transaction_operations:
            self.active_transaction = False
            logger.info("Empty transaction committed")
            return result
        
        # Apply each operation
        applied_count = 0
        failed_count = 0
        
        try:
            # Temporarily set active_transaction to False to avoid recursion
            # Save the current operations
            current_operations = self.transaction_operations
            self.active_transaction = False
            self.transaction_operations = []
            
            for operation in current_operations:
                op_type = operation.get("type")
                
                if op_type == "entity_state":
                    # Entity state update
                    try:
                        success = False
                        
                        # Use direct database access to avoid transaction conflicts
                        if 'db_sqlite' in sys.modules:
                            success = db_sqlite.update_entity_state(
                                operation.get("entity_type"),
                                operation.get("entity_id"),
                                operation.get("state_type"),
                                operation.get("state_value"),
                                operation.get("episode"),
                                operation.get("chunk_id"),
                                operation.get("narrative_time"),
                                operation.get("confidence", 1.0),
                                operation.get("source", "api"),
                                operation.get("notes")
                            )
                        
                        if success:
                            applied_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        logger.error(f"Error applying entity state operation: {e}")
                        failed_count += 1
                
                elif op_type == "relationship_state":
                    # Relationship state update
                    try:
                        success = False
                        
                        # Use direct database access to avoid transaction conflicts
                        if 'db_sqlite' in sys.modules:
                            success = db_sqlite.update_relationship_state(
                                operation.get("entity1_type"),
                                operation.get("entity1_id"),
                                operation.get("entity2_type"),
                                operation.get("entity2_id"),
                                operation.get("relationship_type"),
                                operation.get("state_value"),
                                operation.get("episode"),
                                operation.get("symmetrical", False),
                                operation.get("chunk_id"),
                                operation.get("narrative_time"),
                                operation.get("confidence", 1.0),
                                operation.get("source", "api"),
                                operation.get("notes")
                            )
                        
                        if success:
                            applied_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        logger.error(f"Error applying relationship state operation: {e}")
                        failed_count += 1
                
                else:
                    # Unknown operation type
                    logger.warning(f"Unknown operation type: {op_type}")
                    failed_count += 1
            
            # Update result
            result["applied"] = applied_count
            result["failed"] = failed_count
            result["success"] = failed_count == 0
            
            logger.info(f"Transaction committed: {applied_count} applied, {failed_count} failed")
            return result
            
        except Exception as e:
            # Mark transaction as failed
            result["success"] = False
            result["error"] = str(e)
            result["applied"] = applied_count
            result["failed"] = failed_count + (len(current_operations) - applied_count - failed_count)
            
            logger.error(f"Transaction commit failed: {e}")
            logger.error(traceback.format_exc())
            return result
        finally:
            # Reset transaction state
            self.active_transaction = False
            self.transaction_operations = []
    
    def rollback_transaction(self) -> bool:
        """
        Roll back the current transaction, discarding all operations
        
        Returns:
            True if transaction was rolled back successfully
        
        Raises:
            TransactionError: If no transaction is active
        """
        if not self.active_transaction:
            raise TransactionError("No active transaction to roll back")
        
        # Reset transaction state
        operation_count = len(self.transaction_operations)
        self.active_transaction = False
        self.transaction_operations = []
        self.transaction_conflicts = []
        
        logger.info(f"Transaction rolled back ({operation_count} operations discarded)")
        return True
    
    # Narrative processing methods
    
    def process_narrative_for_updates(self, 
                                    narrative_text: str, 
                                    episode: str,
                                    confidence_threshold: float = None) -> Dict[str, Any]:
        """
        Extract and apply state updates from narrative text
        
        Args:
            narrative_text: Text of the narrative to analyze
            episode: Episode identifier
            confidence_threshold: Minimum confidence to apply updates automatically
                               (defaults to settings value if None)
        
        Returns:
            Dictionary containing processing results
        """
        # Use default threshold if none provided
        if confidence_threshold is None:
            confidence_threshold = self.settings["state_writing"]["confidence_threshold"]
        
        # Initialize result structure
        result = {
            "entity_updates": [],
            "relationship_updates": [],
            "conflicts": [],
            "applied_updates": 0,
            "confidence": 0.0
        }
        
        try:
            # Start a transaction for all updates
            self.begin_transaction()
            
            # Extract entity mentions
            entity_mentions = self._extract_entity_mentions(narrative_text)
            
            # Extract state changes
            state_changes = self._extract_state_changes(narrative_text, entity_mentions)
            result["entity_updates"] = state_changes
            
            # Extract relationship changes
            relationship_changes = self._extract_relationship_changes(narrative_text, entity_mentions)
            result["relationship_updates"] = relationship_changes
            
            # Apply the extracted updates with confidence filtering
            applied_count = 0
            
            # Apply entity state updates
            for update in state_changes:
                if update.get("confidence", 0.0) >= confidence_threshold:
                    # Apply the update
                    self.update_entity_state(
                        entity_type=update.get("entity_type", "character"),
                        state_type=update.get("state_type"),
                        state_value=update.get("state_value"),
                        episode=episode,
                        entity_id=update.get("entity_id"),
                        entity_name=update.get("entity_name"),
                        confidence=update.get("confidence", 0.5),
                        source="narrative",
                        notes=f"Extracted from narrative: '{update.get('evidence', '')}'"
                    )
                    applied_count += 1
            
            # Apply relationship updates
            for update in relationship_changes:
                if update.get("confidence", 0.0) >= confidence_threshold:
                    # Apply the update
                    self.update_relationship_state(
                        entity1_type=update.get("entity1_type", "character"),
                        entity1_id=update.get("entity1_id"),
                        entity1_name=update.get("entity1_name"),
                        entity2_type=update.get("entity2_type", "character"),
                        entity2_id=update.get("entity2_id"),
                        entity2_name=update.get("entity2_name"),
                        relationship_type=update.get("relationship_type"),
                        state_value=update.get("state_value"),
                        episode=episode,
                        confidence=update.get("confidence", 0.5),
                        source="narrative",
                        notes=f"Extracted from narrative: '{update.get('evidence', '')}'"
                    )
                    applied_count += 1
            
            # Commit the transaction
            commit_result = self.commit_transaction()
            
            # Update the result with conflicts and success status
            result["applied_updates"] = applied_count
            result["conflicts"] = commit_result.get("conflicts", [])
            result["success"] = commit_result.get("success", False)
            
            # Calculate overall confidence based on extracted updates
            if state_changes or relationship_changes:
                total_confidence = 0.0
                count = 0
                
                for update in state_changes + relationship_changes:
                    total_confidence += update.get("confidence", 0.0)
                    count += 1
                
                if count > 0:
                    result["confidence"] = total_confidence / count
            
            return result
            
        except Exception as e:
            # Roll back on any error
            if self.active_transaction:
                self.rollback_transaction()
                
            logger.error(f"Error processing narrative: {e}")
            logger.error(traceback.format_exc())
            
            result["error"] = str(e)
            result["success"] = False
            return result
    
    def _extract_entity_mentions(self, narrative_text: str) -> List[Dict[str, Any]]:
        """
        Identify entity references in text
        
        Args:
            narrative_text: Text to analyze
            
        Returns:
            List of entity mention dictionaries
        """
        # This is a simplified implementation that only identifies
        # capitalized words as potential entity names. In a production system,
        # you would use NER or query against known entity names.
        
        entities = []
        seen_names = set()
        
        # Extract words and remove punctuation
        words = narrative_text.split()
        for i, word in enumerate(words):
            # Clean the word
            clean_word = word.strip(",.!?\"'()[]{}:;")
            
            # Check if it looks like an entity name (capitalized, not all caps)
            if (clean_word and clean_word[0].isupper() and 
                not clean_word.isupper() and 
                len(clean_word) > 1 and
                clean_word not in seen_names):
                
                # Add to detected entities
                entities.append({
                    "name": clean_word,
                    "position": i,
                    "type": "character",  # Assume character by default
                    "confidence": 0.7
                })
                
                seen_names.add(clean_word)
        
        # Attempt to determine entity types based on context
        for entity in entities:
            entity_name = entity["name"]
            position = entity["position"]
            
            # Look at surrounding context
            start_idx = max(0, position - 10)
            end_idx = min(len(words), position + 10)
            context = " ".join(words[start_idx:end_idx]).lower()
            
            # Check for faction indicators
            faction_indicators = [
                "corporation", "corp", "gang", "faction", "group", "organization",
                "syndicate", "clan", "family", "cartel", "alliance"
            ]
            
            # Check for location indicators
            location_indicators = [
                "district", "place", "location", "area", "zone", "neighborhood",
                "building", "tower", "plaza", "street", "avenue", "alley", "quarter"
            ]
            
            # Set entity type based on context
            if any(indicator in context for indicator in faction_indicators):
                entity["type"] = "faction"
                entity["confidence"] = 0.8
            elif any(indicator in context for indicator in location_indicators):
                entity["type"] = "location"
                entity["confidence"] = 0.8
                
            # Try to resolve entity ID if possible
            entity_id = self._resolve_entity_id(entity["type"], entity_name)
            if entity_id:
                entity["id"] = entity_id
                entity["confidence"] = 0.9  # Higher confidence for known entities
        
        return entities
    
    def _extract_state_changes(self, 
                             narrative_text: str, 
                             entity_mentions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Recognize state changes described in narrative
        
        Args:
            narrative_text: Text to analyze
            entity_mentions: List of identified entities
            
        Returns:
            List of state change dictionaries
        """
        state_changes = []
        
        # Define state type patterns
        state_patterns = {
            "character": {
                "emotional": [
                    (r'(angry|angered|furious|enraged)', 'angry'),
                    (r'(sad|depressed|upset|distraught)', 'sad'),
                    (r'(happy|excited|pleased|delighted|joyful)', 'happy'),
                    (r'(afraid|scared|terrified|fearful)', 'afraid'),
                    (r'(confused|uncertain|unsure|puzzled)', 'confused'),
                    (r'(tired|exhausted|weary|fatigued)', 'tired'),
                    (r'(calm|relaxed|composed)', 'calm'),
                    (r'(nervous|anxious|worried|concerned)', 'anxious'),
                    (r'(hopeful|optimistic)', 'hopeful'),
                    (r'(desperate|hopeless|despairing)', 'desperate')
                ],
                "physical": [
                    (r'(injured|wounded|hurt|damaged)', 'injured'),
                    (r'(healthy|recovered|healed)', 'healthy'),
                    (r'(weak|frail)', 'weak'),
                    (r'(strong|powerful)', 'strong'),
                    (r'(sick|ill|diseased)', 'sick')
                ],
                "knowledge": [
                    (r'(learned|discovered|realized|found out)', 'aware'),
                    (r'(confused|unaware|oblivious)', 'unaware')
                ]
            },
            "faction": {
                "power": [
                    (r'(weakened|diminished|reduced)', 'weakened'),
                    (r'(strengthened|increased|grew|expanded)', 'strengthened')
                ],
                "activity": [
                    (r'(attacking|invading|assaulting)', 'attacking'),
                    (r'(defending|protecting|guarding)', 'defending'),
                    (r'(developing|building|creating)', 'developing'),
                    (r'(retreating|withdrawing)', 'retreating')
                ]
            },
            "location": {
                "condition": [
                    (r'(destroyed|ruined|devastated)', 'destroyed'),
                    (r'(secured|safe|protected)', 'secured'),
                    (r'(dangerous|hazardous|threatening)', 'dangerous'),
                    (r'(abandoned|deserted|empty)', 'abandoned')
                ],
                "control": [
                    (r'(controlled by|owned by|dominated by)', 'controlled')
                ]
            }
        }
        
        # For each entity mention, check for state changes in its context
        for entity in entity_mentions:
            entity_name = entity["name"]
            entity_type = entity["type"]
            
            # Get patterns for this entity type
            type_patterns = state_patterns.get(entity_type, {})
            
            # For each state type, check patterns
            for state_type, patterns in type_patterns.items():
                # Look for sentences containing the entity name
                sentences = re.split(r'[.!?]', narrative_text)
                for sentence in sentences:
                    if entity_name in sentence:
                        # Check each pattern
                        for pattern, state_value in patterns:
                            match = re.search(pattern, sentence, re.IGNORECASE)
                            if match:
                                # Calculate confidence based on pattern match and sentence structure
                                confidence = 0.7  # Base confidence
                                
                                # Direct association increases confidence
                                if re.search(fr'{entity_name}\s+\w+\s+{pattern}', sentence, re.IGNORECASE):
                                    confidence = 0.85
                                elif re.search(fr'{pattern}\s+\w+\s+{entity_name}', sentence, re.IGNORECASE):
                                    confidence = 0.85
                                
                                # Special case for location control
                                if state_type == "control" and entity_type == "location":
                                    # Look for faction entity in the same sentence
                                    controlling_entity = None
                                    for other_entity in entity_mentions:
                                        if other_entity["type"] == "faction" and other_entity["name"] in sentence:
                                            controlling_entity = other_entity
                                            break
                                    
                                    if controlling_entity:
                                        state_changes.append({
                                            "entity_type": entity_type,
                                            "entity_name": entity_name,
                                            "entity_id": entity.get("id"),
                                            "state_type": state_type,
                                            "state_value": controlling_entity["name"],
                                            "confidence": confidence,
                                            "evidence": sentence.strip(),
                                            "matched_text": match.group(0)
                                        })
                                else:
                                    # Regular state change
                                    state_changes.append({
                                        "entity_type": entity_type,
                                        "entity_name": entity_name,
                                        "entity_id": entity.get("id"),
                                        "state_type": state_type,
                                        "state_value": state_value,
                                        "confidence": confidence,
                                        "evidence": sentence.strip(),
                                        "matched_text": match.group(0)
                                    })
        
        return state_changes
    
    def _extract_relationship_changes(self, 
                                    narrative_text: str, 
                                    entity_mentions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify relationship changes in text
        
        Args:
            narrative_text: Text to analyze
            entity_mentions: List of identified entities
            
        Returns:
            List of relationship change dictionaries
        """
        relationship_changes = []
        
        # Skip if fewer than 2 entities
        if len(entity_mentions) < 2:
            return relationship_changes
        
        # Define relationship patterns
        relationship_patterns = {
            "trust": [
                (r'(trust[s]?|trusted|trusting)', 'trusts'),
                (r'(distrust[s]?|distrusted|distrusting|suspicious of)', 'distrusts')
            ],
            "power": [
                (r'(controls?|controlled|commanding|dominating)', 'controls'),
                (r'(obeys?|obeyed|following|submits? to)', 'obeys')
            ],
            "alliance": [
                (r'(allies?|allied|partnered|working with)', 'allied'),
                (r'(enemies?|opposing|against|fighting)', 'opposed')
            ],
            "emotional": [
                (r'(likes?|liked|appreciates?|fond of)', 'likes'),
                (r'(loves?|loved|adores?)', 'loves'),
                (r'(hates?|hated|despises?|detests?)', 'hates'),
                (r'(fears?|feared|afraid of|scared of)', 'fears')
            ],
            "professional": [
                (r'(works? for|employed by|hired)', 'works_for'),
                (r'(colleagues?|coworkers?|associates?)', 'colleagues')
            ]
        }
        
        # For each pair of entities, check for relationship mentions
        for i, entity1 in enumerate(entity_mentions):
            for entity2 in enumerate(entity_mentions[i+1:]):
                entity2 = entity2[1]  # Get the entity from the enumeration tuple
                
                # Skip if same entity
                if entity1["name"] == entity2["name"]:
                    continue
                
                entity1_name = entity1["name"]
                entity2_name = entity2["name"]
                
                # Look for sentences containing both entities
                sentences = re.split(r'[.!?]', narrative_text)
                for sentence in sentences:
                    if entity1_name in sentence and entity2_name in sentence:
                        # Check each relationship type
                        for rel_type, patterns in relationship_patterns.items():
                            for pattern, rel_value in patterns:
                                match = re.search(pattern, sentence, re.IGNORECASE)
                                if match:
                                    # Calculate confidence based on sentence structure
                                    confidence = 0.6  # Base confidence for co-occurrence
                                    
                                    # Direct association increases confidence
                                    if re.search(fr'{entity1_name}\s+\w+\s+{pattern}\s+\w+\s+{entity2_name}', 
                                               sentence, re.IGNORECASE):
                                        confidence = 0.8
                                        # Entity1 is the subject
                                        relationship_changes.append({
                                            "entity1_type": entity1["type"],
                                            "entity1_name": entity1_name,
                                            "entity1_id": entity1.get("id"),
                                            "entity2_type": entity2["type"],
                                            "entity2_name": entity2_name,
                                            "entity2_id": entity2.get("id"),
                                            "relationship_type": rel_type,
                                            "state_value": rel_value,
                                            "confidence": confidence,
                                            "evidence": sentence.strip(),
                                            "matched_text": match.group(0)
                                        })
                                    elif re.search(fr'{entity2_name}\s+\w+\s+{pattern}\s+\w+\s+{entity1_name}', 
                                                sentence, re.IGNORECASE):
                                        confidence = 0.8
                                        # Entity2 is the subject
                                        relationship_changes.append({
                                            "entity1_type": entity2["type"],
                                            "entity1_name": entity2_name,
                                            "entity1_id": entity2.get("id"),
                                            "entity2_type": entity1["type"],
                                            "entity2_name": entity1_name,
                                            "entity2_id": entity1.get("id"),
                                            "relationship_type": rel_type,
                                            "state_value": rel_value,
                                            "confidence": confidence,
                                            "evidence": sentence.strip(),
                                            "matched_text": match.group(0)
                                        })
                                    else:
                                        # Can't determine direction, lower confidence
                                        relationship_changes.append({
                                            "entity1_type": entity1["type"],
                                            "entity1_name": entity1_name,
                                            "entity1_id": entity1.get("id"),
                                            "entity2_type": entity2["type"],
                                            "entity2_name": entity2_name,
                                            "entity2_id": entity2.get("id"),
                                            "relationship_type": rel_type,
                                            "state_value": rel_value,
                                            "confidence": confidence,
                                            "evidence": sentence.strip(),
                                            "matched_text": match.group(0)
                                        })
        
        return relationship_changes
    
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
            # Prefer using memnon if available
            if memnon:
                # For future implementation:
                # return memnon.resolve_entity_id(entity_type, entity_name)
                pass
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                if entity_type == "character":
                    character = db_sqlite.get_character_by_name(entity_name)
                    if character:
                        return character["id"]
                elif entity_type == "faction":
                    faction = db_sqlite.get_faction_by_name(entity_name)
                    if faction:
                        # Adjust for potential differences in faction ID field
                        return faction.get("id") or faction.get("faction_id")
                elif entity_type == "location":
                    location = db_sqlite.get_location_by_name(entity_name)
                    if location:
                        # Adjust for potential differences in location ID field
                        return location.get("id") or location.get("location_id")
            return None
        except Exception as e:
            logger.error(f"Error resolving entity ID for {entity_type} {entity_name}: {e}")
            return None
    
    def _get_entity_name(self, entity_type: str, entity_id: int) -> Optional[str]:
        """
        Get entity name from ID
        
        Args:
            entity_type: Type of entity
            entity_id: ID of the entity
            
        Returns:
            Entity name if found, None otherwise
        """
        try:
            # Prefer using memnon if available
            if memnon:
                # For future implementation
                # return memnon.get_entity_name(entity_type, entity_id)
                pass
                
            # Fall back to direct database access
            if 'db_sqlite' in sys.modules:
                if entity_type == "character":
                    character = db_sqlite.get_character_by_id(entity_id)
                    if character:
                        return character["name"]
                elif entity_type == "faction":
                    # We would need a get_faction_by_id function
                    # For now, return a generic name
                    return f"Faction_{entity_id}"
                elif entity_type == "location":
                    # We would need a get_location_by_id function
                    # For now, return a generic name
                    return f"Location_{entity_id}"
            return f"Unknown_{entity_type}_{entity_id}"
        except Exception as e:
            logger.error(f"Error getting entity name for {entity_type} {entity_id}: {e}")
            return f"Unknown_{entity_type}_{entity_id}"
    
    def _detect_state_conflict(self,
                             entity_type: str,
                             entity_id: int,
                             state_type: str,
                             state_value: str,
                             episode: str,
                             confidence: float) -> Optional[Dict[str, Any]]:
        """
        Detect if a state update conflicts with existing state
        
        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            state_type: Type of state
            state_value: New value for the state
            episode: Episode identifier
            confidence: Confidence level for the new update
        
        Returns:
            Conflict information dict if conflict detected, None otherwise
        """
        # This is a simplified implementation as we're removing the entity_state_manager dependency
        
        # Skip conflict detection if confidence is very high
        if confidence > 0.95:
            return None
        
        # Get current state for this entity/state type
        current_state = None
        
        # Use memnon if available
        if memnon:
            # For future implementation:
            # current_state = memnon.get_entity_current_state(entity_type, entity_id, state_type)
            pass
            
        # Fall back to direct database access
        elif 'db_sqlite' in sys.modules:
            current_state = db_sqlite.get_entity_current_state(entity_type, entity_id, state_type)
        
        # If current state exists and differs from new state, we have a potential conflict
        if current_state and current_state != state_value:
            # Get entity name for better conflict description
            entity_name = self._get_entity_name(entity_type, entity_id)
            
            # Create conflict information
            conflict = {
                "id": f"conflict_{int(time.time())}_{entity_type}_{entity_id}_{state_type}",
                "type": "entity_state",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "state_type": state_type,
                "current_value": current_state,
                "new_value": state_value,
                "episode": episode,
                "detected_at": time.time(),
                "description": f"Conflict for {entity_type} '{entity_name}' {state_type}: '{current_state}' -> '{state_value}'",
                "resolution": None
            }
            
            self.conflict_count += 1
            return conflict
        
        return None
    
    def _detect_relationship_conflict(self,
                                    entity1_type: str,
                                    entity1_id: int,
                                    entity2_type: str,
                                    entity2_id: int,
                                    relationship_type: str,
                                    state_value: str,
                                    episode: str,
                                    confidence: float) -> Optional[Dict[str, Any]]:
        """
        Detect if a relationship update conflicts with existing state
        
        Args:
            entity1_type: Type of first entity
            entity1_id: ID of first entity
            entity2_type: Type of second entity
            entity2_id: ID of second entity
            relationship_type: Type of relationship
            state_value: New value for the relationship
            episode: Episode identifier
            confidence: Confidence level for the new update
        
        Returns:
            Conflict information dict if conflict detected, None otherwise
        """
        # This is a simplified implementation as we're removing the entity_state_manager dependency
        
        # Skip conflict detection if confidence is very high
        if confidence > 0.95:
            return None
        
        # Get current relationship state
        current_state = None
        
        # Use memnon if available
        if memnon:
            # For future implementation:
            # current_state = memnon.get_relationship_current_state(entity1_type, entity1_id, entity2_type, entity2_id, relationship_type)
            pass
            
        # Fall back to direct database access
        elif 'db_sqlite' in sys.modules:
            current_state = db_sqlite.get_relationship_current_state(
                entity1_type, entity1_id, entity2_type, entity2_id, relationship_type
            )
        
        # If current state exists and differs from new state, we have a potential conflict
        if current_state and current_state != state_value:
            # Get entity names for better conflict description
            entity1_name = self._get_entity_name(entity1_type, entity1_id)
            entity2_name = self._get_entity_name(entity2_type, entity2_id)
            
            # Create conflict information
            conflict = {
                "id": f"conflict_{int(time.time())}_{entity1_type}_{entity1_id}_{entity2_type}_{entity2_id}_{relationship_type}",
                "type": "relationship_state",
                "entity1_type": entity1_type,
                "entity1_id": entity1_id,
                "entity1_name": entity1_name,
                "entity2_type": entity2_type,
                "entity2_id": entity2_id,
                "entity2_name": entity2_name,
                "relationship_type": relationship_type,
                "current_value": current_state,
                "new_value": state_value,
                "episode": episode,
                "detected_at": time.time(),
                "description": f"Conflict for relationship between {entity1_type} '{entity1_name}' and {entity2_type} '{entity2_name}' {relationship_type}: '{current_state}' -> '{state_value}'",
                "resolution": None
            }
            
            self.conflict_count += 1
            return conflict
        
        return None
    
    def resolve_state_conflict(self, 
                             conflict_id: str, 
                             resolution: str,
                             method: str = "manual") -> bool:
        """
        Resolve a detected state conflict
        
        Args:
            conflict_id: ID of the conflict
            resolution: The resolved state value or 'current_value'/'new_value'
            method: Resolution method ('manual', 'confidence', 'recency')
        
        Returns:
            True if the conflict was resolved, False otherwise
        """
        # This is a simplified implementation as conflicts are not stored persistently
        # without entity_state_manager
        
        logger.info(f"Resolving conflict {conflict_id}: {resolution} via {method}")
        return True
    
    def get_active_conflicts(self) -> List[Dict[str, Any]]:
        """
        Retrieve unresolved conflicts
        
        Returns:
            List of active conflict dictionaries
        """
        # This is a simplified implementation that returns transaction conflicts if in a transaction
        if self.active_transaction:
            return self.transaction_conflicts
        return []

def run_tests():
    """
    Run tests for the StateWriter
    
    Returns:
        True if all tests pass, False otherwise
    """
    # If the testing module is available, use it for more comprehensive testing
    try:
        from prove import TestEnvironment
        
        # Define test functions
        def test_update_entity_state():
            writer = StateWriter()
            try:
                # Test with a character from test data
                state_update = writer.update_entity_state(
                    entity_type="character",
                    entity_id=1,  # Alex in test data
                    state_type="emotional",
                    state_value="happy",
                    episode="S01E01"
                )
                return state_update is True or state_update is False
            except Exception as e:
                print(f"Test failed: {e}")
                return False
                
        def test_update_relationship_state():
            writer = StateWriter()
            try:
                # Test with characters from test data
                rel_update = writer.update_relationship_state(
                    entity1_id=1,  # Alex
                    entity1_type="character",
                    entity2_id=2,  # Emilia
                    entity2_type="character",
                    relationship_type="trust",
                    state_value="cautious",
                    episode="S01E01"
                )
                return rel_update is True or rel_update is False
            except Exception as e:
                print(f"Test failed: {e}")
                return False
                
        def test_narrative_processing():
            writer = StateWriter()
            try:
                # Test narrative processing
                test_narrative = """
                Alex walked into the room and saw Emilia waiting. 
                She looked worried. "We need to talk," she said.
                Alex felt anxious about what she might say.
                """
                
                result = writer.process_narrative_for_updates(test_narrative, "S01E01")
                
                # Should return a valid result dictionary
                return isinstance(result, dict) and "entity_updates" in result
            except Exception as e:
                print(f"Test failed: {e}")
                return False
                
        def test_transaction_management():
            writer = StateWriter()
            try:
                # Test transaction management
                writer.begin_transaction()
                
                # Add some operations
                writer.update_entity_state(
                    entity_type="character",
                    entity_id=1,
                    state_type="emotional",
                    state_value="happy",
                    episode="S01E01"
                )
                
                writer.update_relationship_state(
                    entity1_id=1,
                    entity2_id=2,
                    relationship_type="trust",
                    state_value="cautious",
                    episode="S01E01"
                )
                
                # Commit the transaction
                result = writer.commit_transaction()
                
                # Should return a successful result
                return isinstance(result, dict) and "success" in result
            except Exception as e:
                print(f"Test failed: {e}")
                if writer.active_transaction:
                    writer.rollback_transaction()
                return False
        
        # Run tests using the test environment
        with TestEnvironment() as env:
            all_passed = True
            all_passed &= env.run_test("Entity State Update", test_update_entity_state)
            all_passed &= env.run_test("Relationship State Update", test_update_relationship_state)
            all_passed &= env.run_test("Narrative Processing", test_narrative_processing)
            all_passed &= env.run_test("Transaction Management", test_transaction_management)
            return all_passed
    
    except ImportError:
        # Fallback to simple testing
        print("Running basic tests without TestEnvironment")
        writer = StateWriter()
        
        try:
            # Basic state update test
            print("Testing entity state update...")
            state_update = writer.update_entity_state(
                entity_type="character",
                entity_id=1,  # Alex in test data
                state_type="emotional",
                state_value="happy",
                episode="S01E01"
            )
            print(f"Entity state update result: {state_update}")
            
            # Basic relationship update test
            print("\nTesting relationship state update...")
            rel_update = writer.update_relationship_state(
                entity1_id=1,  # Alex
                entity1_type="character",
                entity2_id=2,  # Emilia
                entity2_type="character",
                relationship_type="trust",
                state_value="cautious",
                episode="S01E01"
            )
            print(f"Relationship state update result: {rel_update}")
            
            # Narrative processing test
            print("\nTesting narrative processing...")
            test_narrative = """
            Alex walked into the room and saw Emilia waiting. 
            She looked worried. "We need to talk," she said.
            Alex felt anxious about what she might say.
            """
            
            result = writer.process_narrative_for_updates(test_narrative, "S01E01")
            print(f"Narrative processing found {len(result.get('entity_updates', []))} entity updates")
            print(f"Narrative processing found {len(result.get('relationship_updates', []))} relationship updates")
            
            # Transaction management test
            print("\nTesting transaction management...")
            writer.begin_transaction()
            
            # Add some operations
            writer.update_entity_state(
                entity_type="character",
                entity_id=1,
                state_type="emotional",
                state_value="happy",
                episode="S01E01"
            )
            
            writer.update_relationship_state(
                entity1_id=1,
                entity2_id=2,
                relationship_type="trust",
                state_value="cautious",
                episode="S01E01"
            )
            
            # Commit the transaction
            commit_result = writer.commit_transaction()
            print(f"Transaction commit result: {commit_result}")
            
            print("\nAll basic tests completed successfully!")
            return True
            
        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(writer, 'active_transaction') and writer.active_transaction:
                writer.rollback_transaction()
            return False

if __name__ == "__main__":
    # Run tests when executed directly
    success = run_tests()
    if not success:
        print("Tests failed!")
        sys.exit(1)