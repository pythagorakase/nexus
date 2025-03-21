# LORE Agent Blueprint (Context Manager)

## Overview

LORE (Context Manager) is responsible for analyzing the narrative context, understanding its meaning, and managing how it's presented to the Apex LLM. It maintains awareness of plot structure, themes, and causal relationships, ensuring narrative coherence through sophisticated context assembly and payload optimization.

## Key Responsibilities

1. **Deep Context Analysis** - Analyze retrieved narrative chunks to understand their significance to the current story moment
2. **Thematic Connection** - Identify recurring themes, motifs, and narrative patterns
3. **Plot Structure Awareness** - Recognize story beat progression, tension arcs, and narrative pacing
4. **Causal Tracking** - Understand how past events connect to present situations
5. **Metadata Enhancement** - Add contextual metadata to narrative chunks for improved retrieval
6. **Payload Assembly** - Construct balanced context payloads for the Apex LLM with dynamic allocation

## Technical Requirements

### Integration with Letta Framework

- Extend Letta's `Agent` class
- Utilize Letta's memory system via specialized block types
- Implement custom embedding workflows for narrative text
- Use Letta's existing database integration with custom schema extensions

### Memory Management

- Create specialized memory blocks for narrative metadata
- Define schema for thematic tracking, plot elements, and entity relationships
- Implement narrative-specific memory summarization
- Manage memory pressure through intelligent pruning of less relevant context

### Context Analysis

- Implement deep semantic analysis of narrative text
- Extract entities, relationships, and events
- Track plot development and story arcs
- Identify narrative inconsistencies

### Payload Assembly

- Create dynamic payload construction based on narrative needs
- Balance different types of context based on configurable allocation ranges:
  - Structured summaries: 10-25%
  - Contextual augmentation: 25-40%
  - Warm slice (recent narrative): 40-70%
- Optimize token usage for maximum context efficiency
- Prioritize critical narrative elements with explicit justification

### Two-Phase Distillation

- Implement two-phase context filtering:
  - Phase 1: Retrieve top 50 candidate chunks based on initial relevance
  - Phase 2: Use Mixtral 8x7B to narrow down to top 10 most contextually relevant chunks
  - Final selection: Balance relevance with chronological coherence

## Pseudocode Implementation

```python
from letta.agent import Agent
from letta.schemas.agent import AgentState
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
from typing import List, Dict, Any, Optional, Tuple
import json

class LORE(Agent):
    """
    LORE (Context Manager) agent responsible for context analysis, thematic connections, 
    and payload assembly for narrative generation.
    """
    
    def __init__(self, 
                 interface, 
                 agent_state: AgentState,
                 user,
                 **kwargs):
        """
        Initialize LORE agent with specialized narrative memory blocks and settings.
        
        Args:
            interface: Interface for agent communication
            agent_state: Agent state from Letta framework
            user: User information
            **kwargs: Additional arguments
        """
        # Initialize parent Agent class
        super().__init__(interface, agent_state, user, **kwargs)
        
        # Initialize specialized narrative memory blocks if not present
        self._initialize_narrative_memory_blocks()
        
        # Set up thematic trackers
        self.thematic_trackers = {}
        
        # Configure context allocation settings
        self.context_allocation = {
            "structured_summaries": {
                "min": 0.10,  # 10%
                "max": 0.25,  # 25%
                "default": 0.20  # 20%
            },
            "contextual_augmentation": {
                "min": 0.25,  # 25%
                "max": 0.40,  # 40%
                "default": 0.30  # 30%
            },
            "warm_slice": {
                "min": 0.40,  # 40%
                "max": 0.70,  # 70%
                "default": 0.50  # 50%
            }
        }
        
        # Configure distillation settings
        self.distillation_settings = {
            "phase1_top_k": 50,  # Initial retrieval count
            "phase2_top_k": 10,  # Final filtered count
            "intermediate_llm": "Mixtral 8x7B"  # Model for phase 2 filtering
        }
        
        # Configure API models
        self.local_llm = self._initialize_local_llm()
        self.intermediate_llm = self._initialize_intermediate_llm()
    
    def _initialize_narrative_memory_blocks(self):
        """Initialize specialized memory blocks for narrative if not present."""
        # Check if narrative blocks exist and create if needed
        required_blocks = ["themes", "plot_arcs", "narrative_state", "world_state_summary", "context_decisions"]
        
        for block_name in required_blocks:
            if block_name not in self.agent_state.memory.list_block_labels():
                # Create block with default empty content
                block = CreateBlock(
                    label=block_name,
                    value="",
                    limit=50000,  # Generous limit for narrative data
                    description=f"Narrative {block_name} tracking"
                )
                # Add block to memory
                # Implementation will use Letta API to create block
    
    def _initialize_local_llm(self):
        """Initialize local LLM for basic context analysis."""
        # Implementation will initialize local LLM client
        pass
    
    def _initialize_intermediate_llm(self):
        """Initialize intermediate LLM (Mixtral) for phase 2 filtering."""
        # Implementation will initialize Mixtral client
        pass
    
    def analyze_narrative_chunk(self, text: str) -> Dict[str, Any]:
        """
        Analyze a narrative chunk for entities, themes, plot developments.
        
        Args:
            text: Raw narrative text
            
        Returns:
            Dict containing analysis results including entities, themes, etc.
        """
        # Extract entities from text (characters, locations, objects)
        entities = self._extract_entities(text)
        
        # Identify themes and motifs
        themes = self._identify_themes(text)
        
        # Analyze plot progression
        plot_elements = self._analyze_plot_elements(text)
        
        # Track narrative pace and tension
        narrative_metrics = self._measure_narrative_metrics(text)
        
        return {
            "entities": entities,
            "themes": themes,
            "plot_elements": plot_elements,
            "narrative_metrics": narrative_metrics
        }
    
    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract entities from text including characters, locations, objects."""
        # Implementation will use LLM to extract entities
        # Returns dict with categories like "characters", "locations", etc.
        pass
    
    def _identify_themes(self, text: str) -> List[Dict[str, Any]]:
        """Identify themes and motifs in the narrative text."""
        # Implementation will use LLM to identify themes
        # Returns list of theme objects with name, confidence, evidence
        pass
    
    def _analyze_plot_elements(self, text: str) -> Dict[str, Any]:
        """Analyze plot developments and story beats."""
        # Implementation will analyze plot progression
        # Returns plot information like conflict, resolution, stakes
        pass
    
    def _measure_narrative_metrics(self, text: str) -> Dict[str, float]:
        """Measure narrative pace, tension, and other metrics."""
        # Implementation will analyze narrative metrics
        # Returns metrics like pace, tension, character focus
        pass
    
    def enrich_chunk_metadata(self, chunk_id: str, analysis: Dict[str, Any]) -> None:
        """
        Add rich metadata to a narrative chunk based on analysis.
        
        Args:
            chunk_id: ID of chunk to enrich
            analysis: Analysis results from analyze_narrative_chunk
        """
        # Implementation will add metadata to chunk in database
        pass
    
    def two_phase_context_retrieval(self, 
                                   query: str,
                                   narrative_state: Dict[str, Any],
                                   filter_criteria: Optional[Dict] = None) -> List[Dict]:
        """
        Perform two-phase context retrieval with intermediate filtering.
        
        Args:
            query: Query text for retrieval
            narrative_state: Current narrative state for context
            filter_criteria: Optional filters (time, characters, etc.)
            
        Returns:
            List of filtered, highly relevant narrative chunks
        """
        # Phase 1: Initial broad retrieval
        candidate_chunks = self._retrieve_candidate_chunks(
            query, 
            k=self.distillation_settings["phase1_top_k"], 
            filter_criteria=filter_criteria
        )
        
        # Format chunks for intermediate LLM
        formatted_chunks = self._format_chunks_for_filtering(candidate_chunks, narrative_state)
        
        # Phase 2: Intermediate filtering with Mixtral
        filtered_chunks = self._filter_chunks_with_mixtral(
            formatted_chunks, 
            query, 
            narrative_state,
            k=self.distillation_settings["phase2_top_k"]
        )
        
        # Reorder chronologically for narrative coherence
        chronological_chunks = self._reorder_chronologically(filtered_chunks)
        
        return chronological_chunks
    
    def _retrieve_candidate_chunks(self, 
                                 query: str, 
                                 k: int = 50,
                                 filter_criteria: Optional[Dict] = None) -> List[Dict]:
        """Retrieve initial candidate chunks based on query."""
        # Implementation will use MEMNON to retrieve candidate chunks
        pass
    
    def _format_chunks_for_filtering(self, 
                                   chunks: List[Dict], 
                                   narrative_state: Dict[str, Any]) -> str:
        """Format chunks for intermediate LLM filtering."""
        # Implementation will format chunks with context for filtering
        pass
    
    def _filter_chunks_with_mixtral(self, 
                                  formatted_chunks: str, 
                                  query: str, 
                                  narrative_state: Dict[str, Any],
                                  k: int = 10) -> List[Dict]:
        """Use Mixtral to filter and rank chunks by relevance."""
        # Implementation will call Mixtral to filter chunks
        # Will parse Mixtral's response to extract ranked chunks
        pass
    
    def _reorder_chronologically(self, chunks: List[Dict]) -> List[Dict]:
        """Reorder chunks chronologically for narrative coherence."""
        # Implementation will sort chunks by timestamp/ID
        pass
    
    def construct_narrative_context(self, 
                                   recent_chunks: List[Dict],
                                   narrative_state: Dict[str, Any],
                                   query: Optional[str] = None,
                                   token_limit: int = 8000) -> Dict[str, Any]:
        """
        Construct a narrative context payload with dynamic allocation.
        
        Args:
            recent_chunks: Recent narrative chunks (warm slice)
            narrative_state: Current narrative state info
            query: Optional query for contextual retrieval
            token_limit: Maximum tokens allowed
            
        Returns:
            Dict containing assembled context payload and allocation metadata
        """
        # Analyze narrative state to determine optimal allocation
        allocation = self._determine_optimal_allocation(
            narrative_state, 
            recent_chunks, 
            token_limit
        )
        
        # Calculate token budgets based on allocation
        token_budgets = self._calculate_token_budgets(token_limit, allocation)
        
        # Retrieve structured summaries
        structured_info = self._get_structured_info(
            narrative_state, 
            token_budgets["structured_summaries"]
        )
        
        # Retrieve contextual augmentation with two-phase filtering
        contextual_passages = self._get_contextual_passages(
            query, 
            narrative_state,
            token_budgets["contextual_augmentation"]
        )
        
        # Format warm slice (recent narrative)
        warm_slice = self._format_warm_slice(
            recent_chunks, 
            token_budgets["warm_slice"]
        )
        
        # Combine all components into context payload
        payload = self._assemble_context_payload(
            structured_info, 
            contextual_passages, 
            warm_slice
        )
        
        # Generate allocation justification
        justification = self._generate_allocation_justification(
            allocation, 
            narrative_state,
            structured_info,
            contextual_passages,
            warm_slice
        )
        
        # Record decision for future reference
        self._record_context_decision(
            allocation, 
            justification, 
            token_budgets
        )
        
        return {
            "payload": payload,
            "allocation": allocation,
            "justification": justification,
            "token_budgets": token_budgets
        }
    
    def _determine_optimal_allocation(self, 
                                    narrative_state: Dict[str, Any], 
                                    recent_chunks: List[Dict],
                                    token_limit: int) -> Dict[str, float]:
        """Determine optimal allocation percentages for context components."""
        # Implementation will analyze narrative state and adapt allocation
        # Returns dict of component name -> allocation percentage
        pass
    
    def _calculate_token_budgets(self, 
                               total_tokens: int, 
                               allocation: Dict[str, float]) -> Dict[str, int]:
        """Calculate token budgets for different context components."""
        # Implementation will calculate absolute token counts from percentages
        # Returns dict of component name -> token count
        pass
    
    def _get_structured_info(self, 
                           narrative_state: Dict[str, Any], 
                           token_budget: int) -> Dict[str, str]:
        """
        Get structured information about characters, world state, etc.
        
        Selection criteria:
        - Characters actively participating in current scene
        - Locations currently featured or referenced
        - Key plot points directly relevant to current action
        """
        # Implementation will query GAIA and PSYCHE and format response
        pass
    
    def _get_contextual_passages(self, 
                              query: str, 
                              narrative_state: Dict[str, Any],
                              token_budget: int) -> List[Dict[str, Any]]:
        """
        Get contextual passages from memory retrieval.
        
        Selection criteria:
        - Thematic relevance to current scene
        - Character development milestones
        - Prior events directly referenced or implied
        """
        # Implementation will use two-phase retrieval for relevant historical passages
        # Will format and trim to fit budget
        pass
    
    def _format_warm_slice(self, 
                         recent_chunks: List[Dict], 
                         token_budget: int) -> str:
        """
        Format warm slice (recent narrative) text.
        
        Selection criteria:
        - Start from most recent and work backward
        - Identify optimal cut points at narrative transitions
        - Balance recent action with story arc context
        """
        # Implementation will format recent narrative chunks
        # Will trim to fit budget
        pass
    
    def _assemble_context_payload(self,
                                structured_info: Dict[str, str],
                                contextual_passages: List[Dict[str, Any]],
                                warm_slice: str) -> str:
        """Assemble full context payload with all components."""
        # Implementation will combine all components in standardized format
        pass
    
    def _generate_allocation_justification(self,
                                         allocation: Dict[str, float],
                                         narrative_state: Dict[str, Any],
                                         structured_info: Dict[str, str],
                                         contextual_passages: List[Dict[str, Any]],
                                         warm_slice: str) -> str:
        """Generate explicit justification for allocation decisions."""
        # Implementation will explain allocation decisions and tradeoffs
        # Will justify selection of specific historical passages
        # Will explain warm slice extent
        pass
    
    def _record_context_decision(self,
                               allocation: Dict[str, float],
                               justification: str,
                               token_budgets: Dict[str, int]) -> None:
        """Record context allocation decision for future reference."""
        # Implementation will store decision in memory block
        pass
    
    def update_narrative_state(self, new_narrative: str) -> None:
        """
        Update narrative state based on new narrative content.
        
        Args:
            new_narrative: New narrative text
        """
        # Analyze new narrative
        analysis = self.analyze_narrative_chunk(new_narrative)
        
        # Update theme trackers
        self._update_theme_trackers(analysis["themes"])
        
        # Update plot arc tracking
        self._update_plot_arcs(analysis["plot_elements"])
        
        # Update narrative state memory block
        self._update_narrative_state_block(analysis)
    
    def _update_theme_trackers(self, themes: List[Dict[str, Any]]) -> None:
        """Update theme trackers with new theme information."""
        # Implementation will update theme tracking in memory blocks
        pass
    
    def _update_plot_arcs(self, plot_elements: Dict[str, Any]) -> None:
        """Update plot arc tracking with new plot developments."""
        # Implementation will update plot tracking in memory blocks
        pass
    
    def _update_narrative_state_block(self, analysis: Dict[str, Any]) -> None:
        """Update the narrative state memory block with latest analysis."""
        # Implementation will update narrative state in memory blocks
        pass
    
    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and perform LORE functions.
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

1. **Two-Phase Distillation Process**: LORE implements a sophisticated two-phase distillation process:
   - **Initial Retrieval**: Retrieve top 50 candidate chunks based on relevance
   - **Intermediate Filtering**: Use Mixtral 8x7B to refine selection to top 10 chunks
   - **Final Ordering**: Reorder selected chunks chronologically for narrative coherence

2. **Dynamic Allocation Strategy**: Context payload is constructed with dynamic allocation:
   - **Structured Summaries**: Character profiles, location details, plot state (10-25%)
   - **Contextual Augmentation**: Historical passages with thematic significance (25-40%)
   - **Warm Slice**: Recent narrative for immediate continuity (40-70%)
   - **Allocation Decisions**: Explicitly justified based on narrative needs

3. **Component Selection Logic**:
   - **Structured Summaries**: Focus on active characters, current locations, and immediately relevant plot points
   - **Historical Passages**: Selected for thematic relevance, character development milestones, and directly referenced prior events
   - **Warm Slice**: Begins with most recent chunks, working backward to optimal narrative break points

4. **Explicit Reasoning Process**:
   - Each context assembly generates explicit justification for allocation decisions
   - Decisions are recorded for future reference and optimization
   - Tradeoffs between different components are documented

5. **Agent Communication**:
   - LORE coordinates with other agents to build comprehensive context:
     - Query GAIA for world state information
     - Query PSYCHE for character state information
     - Use MEMNON for unified memory access (both vector and structured)
     - Prepare final payload for LOGON

## Next Steps

1. Implement the two-phase distillation process with Mixtral integration
2. Develop dynamic allocation logic with explicit justification
3. Create the component selection algorithms with specialized criteria
4. Build integration points with other agents (PSYCHE, GAIA, MEMNON)
5. Test with sample narrative data
6. Fine-tune context assembly algorithms based on performance 