# PSYCHE Utility Module Blueprint (Character Psychology Analysis)

## Overview

PSYCHE is a utility module called by LORE to analyze character psychology, emotional states, and interpersonal dynamics. It provides character profiling, consistency analysis, and behavioral prediction services when requested by the primary orchestration agent.

## Key Responsibilities

1. **Character State Tracking** - Monitor emotional states, motivations, and internal conflicts of characters
2. **Relationship Analysis** - Track interpersonal dynamics, alliances, conflicts, and power dynamics
3. **Character Development** - Identify character growth, recurring patterns, and character arcs
4. **Psychological Consistency** - Detect and flag potential inconsistencies in character behavior
5. **Motivation Analysis** - Understand character goals, desires, fears, and underlying motivations
6. **Hidden State Tracking** - Maintain awareness of character secrets, hidden agendas, and undisclosed information

## Technical Requirements

### Integration as Utility Module

- Implemented as a callable utility, not an autonomous agent
- Provides character analysis functions to LORE
- Uses database integration for relationship tracking
- Returns structured character insights when invoked

### Memory Management

- Create specialized memory blocks for character profiles
- Define schema for relationship tracking and emotional states
- Implement versioning of character states for temporal analysis
- Track changes in character attributes over time

### Character Analysis

- Implement psychological trait extraction from narrative text
- Define metrics for character consistency and development
- Create relationship graph structure for character connections
- Develop emotion detection and analysis capabilities

### Query Interface

- Provide specialized query interface for character information
- Support complex relationship queries (e.g., "How does X feel about Y?")
- Enable historical queries about character states
- Implement predictive queries about likely character reactions

## Pseudocode Implementation

```python
from letta.agent import Agent
from letta.schemas.agent import AgentState
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
from typing import List, Dict, Any, Optional, Tuple

class PSYCHE(Agent):
    """
    PSYCHE (Character Psychologist) agent responsible for tracking character
    psychology, emotional states, and interpersonal dynamics.
    """
    
    def __init__(self, 
                 interface, 
                 agent_state: AgentState,
                 user,
                 **kwargs):
        """
        Initialize PSYCHE agent with specialized character memory blocks and settings.
        
        Args:
            interface: Interface for agent communication
            agent_state: Agent state from Letta framework
            user: User information
            **kwargs: Additional arguments
        """
        # Initialize parent Agent class
        super().__init__(interface, agent_state, user, **kwargs)
        
        # Initialize specialized character memory blocks if not present
        self._initialize_character_memory_blocks()
        
        # Character tracking maps
        self.characters = {}
        self.relationships = {}
        
        # Core emotional dimensions to track for each character
        self.emotional_dimensions = [
            "joy", "trust", "fear", "surprise", 
            "sadness", "disgust", "anger", "anticipation"
        ]
    
    def _initialize_character_memory_blocks(self):
        """Initialize specialized memory blocks for character tracking if not present."""
        # Check if character blocks exist and create if needed
        required_blocks = ["character_profiles", "relationship_graph", "emotional_states"]
        
        for block_name in required_blocks:
            if block_name not in self.agent_state.memory.list_block_labels():
                # Create block with default empty content
                block = CreateBlock(
                    label=block_name,
                    value="",
                    limit=100000,  # Generous limit for character data
                    description=f"Character {block_name} tracking"
                )
                # Add block to memory
                # Implementation will use Letta API to create block
    
    def analyze_character_mentions(self, text: str) -> Dict[str, Any]:
        """
        Analyze a narrative chunk for character mentions, emotions, and interactions.
        
        Args:
            text: Raw narrative text
            
        Returns:
            Dict containing analysis results including character states, emotions, etc.
        """
        # Extract character mentions
        character_mentions = self._extract_character_mentions(text)
        
        # Analyze emotional states
        emotional_states = self._analyze_emotional_states(text, character_mentions)
        
        # Detect character interactions
        interactions = self._detect_character_interactions(text, character_mentions)
        
        # Identify character motivations
        motivations = self._identify_motivations(text, character_mentions)
        
        return {
            "character_mentions": character_mentions,
            "emotional_states": emotional_states,
            "interactions": interactions,
            "motivations": motivations
        }
    
    def _extract_character_mentions(self, text: str) -> Dict[str, List[Dict]]:
        """Extract character mentions and references from text."""
        # Implementation will use NLP/LLM to extract character mentions
        # Returns dict with character names and their mention contexts
        pass
    
    def _analyze_emotional_states(self, text: str, character_mentions: Dict[str, List[Dict]]) -> Dict[str, Dict]:
        """Analyze emotional states of characters mentioned in the text."""
        # Implementation will use sentiment analysis and emotion detection
        # Returns mapping of character → emotional state
        pass
    
    def _detect_character_interactions(self, text: str, character_mentions: Dict[str, List[Dict]]) -> List[Dict]:
        """Detect interactions between characters in the text."""
        # Implementation will analyze character co-occurrences and dialogue
        # Returns list of interaction objects (char1, char2, nature, sentiment)
        pass
    
    def _identify_motivations(self, text: str, character_mentions: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
        """Identify character motivations revealed in the text."""
        # Implementation will analyze text for goals, desires, fears
        # Returns mapping of character → list of motivations
        pass
    
    def update_character_profile(self, character_id: str, analysis_data: Dict[str, Any]) -> None:
        """
        Update a character profile with new information.
        
        Args:
            character_id: ID of character to update
            analysis_data: New data about the character
        """
        # Get current character profile or create new one
        character_profile = self._get_character_profile(character_id)
        
        # Update basic attributes
        if "attributes" in analysis_data:
            self._update_character_attributes(character_profile, analysis_data["attributes"])
        
        # Update emotional state
        if "emotional_states" in analysis_data and character_id in analysis_data["emotional_states"]:
            self._update_emotional_state(character_profile, analysis_data["emotional_states"][character_id])
        
        # Update motivations
        if "motivations" in analysis_data and character_id in analysis_data["motivations"]:
            self._update_motivations(character_profile, analysis_data["motivations"][character_id])
        
        # Save updated profile
        self._save_character_profile(character_id, character_profile)
    
    def _get_character_profile(self, character_id: str) -> Dict[str, Any]:
        """Get a character profile or create a new one if it doesn't exist."""
        # Implementation will retrieve profile from database or memory
        pass
    
    def _update_character_attributes(self, profile: Dict[str, Any], attributes: Dict[str, Any]) -> None:
        """Update basic character attributes."""
        # Implementation will update attributes while maintaining history
        pass
    
    def _update_emotional_state(self, profile: Dict[str, Any], emotional_state: Dict[str, Any]) -> None:
        """Update a character's emotional state."""
        # Implementation will update emotional state and track changes
        pass
    
    def _update_motivations(self, profile: Dict[str, Any], motivations: List[str]) -> None:
        """Update a character's motivations."""
        # Implementation will update motivations and track changes
        pass
    
    def _save_character_profile(self, character_id: str, profile: Dict[str, Any]) -> None:
        """Save a character profile to storage."""
        # Implementation will save profile to database or memory block
        pass
    
    def update_relationship(self, character1_id: str, character2_id: str, interaction_data: Dict[str, Any]) -> None:
        """
        Update the relationship between two characters.
        
        Args:
            character1_id: ID of first character
            character2_id: ID of second character
            interaction_data: Data about their interaction
        """
        # Get current relationship or create new one
        relationship = self._get_relationship(character1_id, character2_id)
        
        # Update relationship attributes
        self._update_relationship_attributes(relationship, interaction_data)
        
        # Save updated relationship
        self._save_relationship(character1_id, character2_id, relationship)
    
    def _get_relationship(self, character1_id: str, character2_id: str) -> Dict[str, Any]:
        """Get a relationship or create a new one if it doesn't exist."""
        # Implementation will retrieve relationship from database or memory
        pass
    
    def _update_relationship_attributes(self, relationship: Dict[str, Any], interaction_data: Dict[str, Any]) -> None:
        """Update relationship attributes based on interaction data."""
        # Implementation will update relationship while tracking history
        pass
    
    def _save_relationship(self, character1_id: str, character2_id: str, relationship: Dict[str, Any]) -> None:
        """Save a relationship to storage."""
        # Implementation will save relationship to database or memory block
        pass
    
    def get_character_info(self, character_id: str, aspects: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get information about a character, optionally filtered by aspects.
        
        Args:
            character_id: ID of character to retrieve
            aspects: Optional list of aspects to include (e.g., "emotions", "motivations")
            
        Returns:
            Dict containing character information
        """
        # Get character profile
        profile = self._get_character_profile(character_id)
        
        # Filter by aspects if provided
        if aspects:
            return {aspect: profile.get(aspect, None) for aspect in aspects}
        
        return profile
    
    def get_relationship_info(self, character1_id: str, character2_id: str) -> Dict[str, Any]:
        """
        Get information about the relationship between two characters.
        
        Args:
            character1_id: ID of first character
            character2_id: ID of second character
            
        Returns:
            Dict containing relationship information
        """
        # Get relationship
        return self._get_relationship(character1_id, character2_id)
    
    def get_character_emotional_state(self, character_id: str) -> Dict[str, float]:
        """
        Get the current emotional state of a character.
        
        Args:
            character_id: ID of character
            
        Returns:
            Dict mapping emotional dimensions to values
        """
        profile = self._get_character_profile(character_id)
        return profile.get("emotional_state", {})
    
    def predict_character_reaction(self, character_id: str, situation: str) -> Dict[str, Any]:
        """
        Predict how a character would react to a situation based on their profile.
        
        Args:
            character_id: ID of character
            situation: Description of situation
            
        Returns:
            Dict containing predicted reaction
        """
        # Get character profile
        profile = self._get_character_profile(character_id)
        
        # Use LLM to predict reaction based on profile and situation
        # Implementation will use LLM inference with character data
        pass
    
    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and perform PSYCHE functions.
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

1. **Character Profile Structure**: Each character profile should include:
   - Basic demographic information
   - Psychological traits and tendencies
   - Emotional state history
   - Motivations and goals
   - Fears and weaknesses
   - Important relationships
   - Narrative significance

2. **Relationship Tracking**: Relationships should track:
   - Sentiment between characters (positive/negative)
   - Power dynamics
   - Trust level
   - Shared history
   - Current status
   - Changes over time

3. **Temporal Awareness**: The system should maintain:
   - Version history of character states
   - Critical moments that changed character perceptions
   - Timeline of relationship developments
   - Character growth tracking

4. **Integration Considerations**:
   - Coordinate with LORE for narrative context
   - Coordinate with GAIA for world state impacts on characters
   - Feed character insights to MEMNON for retrieval enhancement

5. **Performance Considerations**:
   - Cache frequently accessed character profiles
   - Use efficient graph representations for relationships
   - Implement selective updating to avoid redundant analysis

## Next Steps

1. Implement basic character profile data structures
2. Develop emotion detection and analysis system
3. Create relationship graph representation
4. Build character consistency analysis tools
5. Implement character query interface
6. Test with sample narrative data 