# GAIA Utility Module Blueprint (World State Tracking)

## Overview

GAIA is a utility module called by LORE to monitor and maintain the state of the narrative world, including locations, factions, objects, and global conditions. It tracks changes to the world over time, understands causal relationships between world events, and ensures world-state consistency across the narrative.

## Key Responsibilities

1. **Entity State Tracking** - Monitor the status and properties of locations, factions, and objects
2. **Temporal State Management** - Track how world elements change over time
3. **Causal Relationship Tracking** - Understand how events in the world affect other world elements
4. **World Consistency Checking** - Detect and flag potential inconsistencies in world state
5. **Hidden State Maintenance** - Track "behind the scenes" world elements not directly visible in narrative
6. **World State Queries** - Answer questions about current or historical world states

## Technical Requirements

### Integration as Utility Module

- Implemented as a callable utility module
- Utilize Letta's memory system for world state storage
- Implement database schema extensions for world entities and states
- Leverage Letta's query system for world state retrieval

### Memory Management

- Create specialized memory blocks for different world entity types
- Define schema for entity relationships and state changes
- Implement versioning of world states for temporal queries
- Develop efficient state delta recording for compact storage

### World State Analysis

- Implement entity extraction for world elements from narrative text
- Define state change detection algorithms for tracking modifications
- Create world consistency validation functions
- Develop causal relationship tracking between events and states

### Query Interface

- Provide specialized query interface for world state information
- Support temporal queries about historical world states
- Enable location and faction-specific queries
- Implement "what if" hypothetical state change queries

## Pseudocode Implementation

```python
from letta.agent import Agent
from letta.schemas.agent import AgentState
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
from typing import List, Dict, Any, Optional, Tuple, Union
import datetime

class GAIA(Agent):
    """
    GAIA (World Tracker) agent responsible for monitoring world state,
    including locations, factions, and objects.
    """
    
    def __init__(self, 
                 interface, 
                 agent_state: AgentState,
                 user,
                 **kwargs):
        """
        Initialize GAIA agent with specialized world memory blocks and settings.
        
        Args:
            interface: Interface for agent communication
            agent_state: Agent state from Letta framework
            user: User information
            **kwargs: Additional arguments
        """
        # Initialize parent Agent class
        super().__init__(interface, agent_state, user, **kwargs)
        
        # Initialize specialized world memory blocks if not present
        self._initialize_world_memory_blocks()
        
        # Entity tracking maps
        self.locations = {}
        self.factions = {}
        self.objects = {}
        self.global_states = {}
        
        # Entity types and their attributes
        self.entity_schemas = {
            "location": ["name", "description", "condition", "occupants", "security_level", "owner", "status"],
            "faction": ["name", "description", "power_level", "territory", "assets", "allies", "enemies", "goals"],
            "object": ["name", "description", "location", "owner", "condition", "significance", "capabilities"],
            "global": ["weather", "time", "date", "major_events", "political_climate", "economic_state"]
        }
    
    def _initialize_world_memory_blocks(self):
        """Initialize specialized memory blocks for world tracking if not present."""
        # Check if world blocks exist and create if needed
        required_blocks = ["locations", "factions", "objects", "global_state", "timeline"]
        
        for block_name in required_blocks:
            if block_name not in self.agent_state.memory.list_block_labels():
                # Create block with default empty content
                block = CreateBlock(
                    label=block_name,
                    value="",
                    limit=100000,  # Generous limit for world data
                    description=f"World {block_name} tracking"
                )
                # Add block to memory
                # Implementation will use Letta API to create block
    
    def analyze_world_mentions(self, text: str) -> Dict[str, Any]:
        """
        Analyze a narrative chunk for world entity mentions and state changes.
        
        Args:
            text: Raw narrative text
            
        Returns:
            Dict containing analysis results including entity mentions and state changes
        """
        # Extract entity mentions
        entity_mentions = self._extract_entity_mentions(text)
        
        # Detect state changes
        state_changes = self._detect_state_changes(text, entity_mentions)
        
        # Identify causal relationships
        causal_relationships = self._identify_causal_relationships(text, state_changes)
        
        # Detect inconsistencies
        inconsistencies = self._detect_inconsistencies(entity_mentions, state_changes)
        
        return {
            "entity_mentions": entity_mentions,
            "state_changes": state_changes,
            "causal_relationships": causal_relationships,
            "inconsistencies": inconsistencies
        }
    
    def _extract_entity_mentions(self, text: str) -> Dict[str, List[Dict]]:
        """Extract world entity mentions from text."""
        # Implementation will use NLP/LLM to extract entity mentions
        # Returns dict with entity types and their mentions
        pass
    
    def _detect_state_changes(self, text: str, entity_mentions: Dict[str, List[Dict]]) -> List[Dict]:
        """Detect state changes for world entities."""
        # Implementation will analyze text for entity state changes
        # Returns list of state change events
        pass
    
    def _identify_causal_relationships(self, text: str, state_changes: List[Dict]) -> List[Dict]:
        """Identify causal relationships between events and state changes."""
        # Implementation will analyze text for causality
        # Returns list of cause-effect relationships
        pass
    
    def _detect_inconsistencies(self, entity_mentions: Dict[str, List[Dict]], state_changes: List[Dict]) -> List[Dict]:
        """Detect potential inconsistencies in world state."""
        # Implementation will check for contradictions and conflicts
        # Returns list of potential inconsistencies
        pass
    
    def get_entity(self, 
                  entity_type: str, 
                  entity_id: str, 
                  timestamp: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        """
        Get an entity by type and ID, optionally at a specific point in time.
        
        Args:
            entity_type: Type of entity ("location", "faction", "object", "global")
            entity_id: ID of entity to retrieve
            timestamp: Optional timestamp for historical state
            
        Returns:
            Dict containing entity state
        """
        # Load entity from appropriate store
        if entity_type == "location":
            entity_store = self.locations
        elif entity_type == "faction":
            entity_store = self.factions
        elif entity_type == "object":
            entity_store = self.objects
        elif entity_type == "global":
            entity_store = self.global_states
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")
        
        # Get current state or historical state based on timestamp
        if timestamp is None:
            return self._get_current_entity_state(entity_store, entity_id)
        else:
            return self._get_historical_entity_state(entity_store, entity_id, timestamp)
    
    def _get_current_entity_state(self, entity_store: Dict, entity_id: str) -> Dict[str, Any]:
        """Get current state of an entity."""
        # Implementation will retrieve entity from database or memory
        pass
    
    def _get_historical_entity_state(self, 
                                     entity_store: Dict, 
                                     entity_id: str, 
                                     timestamp: datetime.datetime) -> Dict[str, Any]:
        """Get historical state of an entity at a specific timestamp."""
        # Implementation will retrieve historical state from version history
        pass
    
    def update_entity_state(self, 
                           entity_type: str, 
                           entity_id: str,
                           state_changes: Dict[str, Any],
                           timestamp: Optional[datetime.datetime] = None,
                           cause: Optional[str] = None) -> None:
        """
        Update the state of a world entity.
        
        Args:
            entity_type: Type of entity ("location", "faction", "object", "global")
            entity_id: ID of entity to update
            state_changes: Dict of attributes to update
            timestamp: Optional timestamp for when change occurred
            cause: Optional cause of the state change
        """
        # Select appropriate entity store
        if entity_type == "location":
            entity_store = self.locations
        elif entity_type == "faction":
            entity_store = self.factions
        elif entity_type == "object":
            entity_store = self.objects
        elif entity_type == "global":
            entity_store = self.global_states
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")
        
        # Get current entity state
        entity = self._get_current_entity_state(entity_store, entity_id)
        
        # Apply updates
        self._apply_state_changes(entity, state_changes)
        
        # Record state change with timestamp and cause
        self._record_state_change(entity_type, entity_id, state_changes, timestamp, cause)
        
        # Save updated entity
        self._save_entity(entity_store, entity_id, entity)
    
    def _apply_state_changes(self, entity: Dict[str, Any], state_changes: Dict[str, Any]) -> None:
        """Apply state changes to an entity."""
        # Implementation will update entity state while validating changes
        pass
    
    def _record_state_change(self, 
                            entity_type: str, 
                            entity_id: str, 
                            state_changes: Dict[str, Any],
                            timestamp: Optional[datetime.datetime],
                            cause: Optional[str]) -> None:
        """Record a state change in the timeline."""
        # Implementation will add state change to timeline for historical tracking
        pass
    
    def _save_entity(self, entity_store: Dict, entity_id: str, entity: Dict[str, Any]) -> None:
        """Save an entity to storage."""
        # Implementation will save entity to database or memory block
        pass
    
    def create_entity(self, 
                     entity_type: str, 
                     entity_data: Dict[str, Any],
                     cause: Optional[str] = None) -> str:
        """
        Create a new world entity.
        
        Args:
            entity_type: Type of entity ("location", "faction", "object", "global")
            entity_data: Initial state data for entity
            cause: Optional cause of entity creation
            
        Returns:
            ID of newly created entity
        """
        # Validate entity data against schema
        self._validate_entity_data(entity_type, entity_data)
        
        # Generate entity ID
        entity_id = self._generate_entity_id(entity_type, entity_data)
        
        # Initialize entity with schema defaults and provided data
        entity = self._initialize_entity(entity_type, entity_data)
        
        # Save entity to appropriate store
        if entity_type == "location":
            entity_store = self.locations
        elif entity_type == "faction":
            entity_store = self.factions
        elif entity_type == "object":
            entity_store = self.objects
        elif entity_type == "global":
            entity_store = self.global_states
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")
        
        # Save new entity
        self._save_entity(entity_store, entity_id, entity)
        
        # Record creation event
        self._record_entity_creation(entity_type, entity_id, entity, cause)
        
        return entity_id
    
    def _validate_entity_data(self, entity_type: str, entity_data: Dict[str, Any]) -> None:
        """Validate entity data against schema."""
        # Implementation will check required fields and data types
        pass
    
    def _generate_entity_id(self, entity_type: str, entity_data: Dict[str, Any]) -> str:
        """Generate a unique ID for a new entity."""
        # Implementation will create a unique identifier
        pass
    
    def _initialize_entity(self, entity_type: str, entity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize an entity with default values and provided data."""
        # Implementation will create entity with schema defaults
        pass
    
    def _record_entity_creation(self, 
                               entity_type: str, 
                               entity_id: str, 
                               entity: Dict[str, Any],
                               cause: Optional[str]) -> None:
        """Record entity creation in the timeline."""
        # Implementation will add creation event to timeline
        pass
    
    def query_entities(self, 
                      entity_type: str,
                      query: Dict[str, Any],
                      timestamp: Optional[datetime.datetime] = None) -> List[Dict[str, Any]]:
        """
        Query entities by type and filter criteria.
        
        Args:
            entity_type: Type of entity to query
            query: Filter criteria
            timestamp: Optional timestamp for historical query
            
        Returns:
            List of matching entities
        """
        # Implementation will search entities based on criteria
        pass
    
    def get_entities_at_location(self, 
                                location_id: str,
                                entity_types: Optional[List[str]] = None,
                                timestamp: Optional[datetime.datetime] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all entities at a specific location.
        
        Args:
            location_id: ID of location to query
            entity_types: Optional filter for entity types
            timestamp: Optional timestamp for historical query
            
        Returns:
            Dict mapping entity types to lists of entities
        """
        # Implementation will find all entities at location
        pass
    
    def get_faction_territory(self, 
                             faction_id: str,
                             timestamp: Optional[datetime.datetime] = None) -> List[str]:
        """
        Get all locations controlled by a faction.
        
        Args:
            faction_id: ID of faction to query
            timestamp: Optional timestamp for historical query
            
        Returns:
            List of location IDs controlled by faction
        """
        # Implementation will find all locations owned by faction
        pass
    
    def get_world_timeline(self, 
                          start_time: Optional[datetime.datetime] = None,
                          end_time: Optional[datetime.datetime] = None,
                          entity_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get timeline of world state changes.
        
        Args:
            start_time: Optional start time for timeline
            end_time: Optional end time for timeline
            entity_filter: Optional filter for specific entities
            
        Returns:
            List of timeline events matching criteria
        """
        # Implementation will retrieve filtered timeline events
        pass
    
    def check_world_consistency(self) -> List[Dict[str, Any]]:
        """
        Check world state for inconsistencies.
        
        Returns:
            List of detected inconsistencies
        """
        # Implementation will perform consistency checks
        pass
    
    def simulate_state_change(self, 
                             entity_type: str, 
                             entity_id: str,
                             state_changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate a state change without applying it permanently.
        
        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            state_changes: Proposed state changes
            
        Returns:
            Dict with simulated impact and potential issues
        """
        # Implementation will simulate state change impacts
        pass
    
    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and perform GAIA functions.
        This is the main entry point required by Letta Agent framework.
        
        Args:
            messages: Incoming messages to process
            
        Returns:
            Agent response
        """
        # Implementation will handle different message types and commands
        # Will delegate to appropriate methods based on content
        pass
```

## Implementation Notes

1. **Entity Schema Design**: Entity schemas should be flexible but provide strong typing:
   - Core required fields for each entity type
   - Optional fields for specialized entity subtypes
   - Validation rules to ensure data integrity
   - Support for custom attributes per entity

2. **State Change Tracking**: State changes should be recorded with:
   - Timestamps for temporal querying
   - Causality information (what caused the change)
   - Delta recording (only store what changed)
   - Version history for rollback capability

3. **Spatial Relationships**: The system should maintain:
   - Hierarchical location structure (regions contain locations)
   - Adjacency relationships between locations
   - Entity containment (what entities are in which locations)
   - Territory control (which factions control which locations)

4. **Integration Considerations**:
   - Coordinate with LORE for narrative impact of world events
   - Coordinate with PSYCHE for character location tracking
   - Provide world state context to MEMNON for retrieval enhancement

5. **Performance Considerations**:
   - Implement lazy loading for entity details
   - Use efficient spatial indexing for location queries
   - Cache frequently accessed entities
   - Use delta compression for state history

## Next Steps

1. Implement basic entity data structures
2. Develop entity state tracking system
3. Create timeline and historical state retrieval
4. Build world consistency validation tools
5. Implement spatial relationship tracking
6. Test with sample narrative data 