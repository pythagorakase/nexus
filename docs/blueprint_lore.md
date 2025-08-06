# LORE Agent Blueprint (Revised) - Central Orchestration Agent

## Overview

LORE (Lore Operations & Retrieval Engine) has evolved from a Context Manager into the central orchestration agent for the NEXUS system. It is now the sole intelligent agent, responsible for analyzing narrative state, coordinating utility modules, and assembling optimal context payloads for the Apex LLM.

## Core Responsibilities

### 1. **Narrative State Analysis** (Original Role)
- Analyze current narrative moment for context needs
- Track plot progression and thematic elements
- Identify critical narrative dependencies

### 2. **Utility Orchestration** (New Role)
- Coordinate MEMNON for memory retrieval
- Call PSYCHE utilities for character state reports
- Interface with NEMESIS utilities for threat assessment
- Use GAIA utilities for world state queries
- Execute LOGON utilities for API communication

### 3. **Intelligent Context Assembly**
- Dynamically determine what information is needed
- Balance different context types based on narrative needs
- Optimize token allocation across components
- Generate explicit justifications for context decisions

### 4. **Turn Cycle Management** (New Role)
- Receive and parse user input
- Orchestrate the complete turn sequence
- Handle error recovery and fallbacks
- Manage system state between turns

## Technical Architecture

### Integration Points

```python
class LORE:
    def __init__(self):
        # Initialize utility modules
        self.memnon = MemnonUtility()  # Memory retrieval
        self.psyche = PsycheUtility()  # Character analysis
        self.nemesis = NemesisUtility()  # Threat tracking
        self.gaia = GaiaUtility()  # World state
        self.logon = LogonUtility()  # API communication
        
        # Initialize local LLM for reasoning
        self.local_llm = self._initialize_llm()
```

### Turn Cycle Flow

```
User Input → LORE Analysis → Utility Calls → Context Assembly → API Call → Response Processing
                ↑                                                              ↓
                └──────────────── State Updates ←─────────────────────────────┘
```

## Key Design Changes

### 1. **Decision Centralization**
All context assembly decisions now flow through LORE's local LLM reasoning:
- What character information is relevant?
- Which historical passages matter most?
- What threats should be emphasized?
- How should token budget be allocated?

### 2. **Utility Pattern**
Former agents become stateless utilities that LORE calls:
```python
# Instead of agent communication:
# psyche_response = await self.send_message_to_psyche(query)

# Direct utility calls:
character_state = self.psyche.get_character_state(character_id)
emotional_analysis = self.psyche.analyze_emotional_context(text)
```

### 3. **Reasoning-First Approach**
LORE uses its local LLM to reason about context needs before making utility calls:
```python
def analyze_context_needs(self, user_input, recent_narrative):
    # Use local LLM to determine what's needed
    reasoning = self.local_llm.analyze(f"""
    Given this user input: {user_input}
    And recent narrative: {recent_narrative}
    
    What context elements are most critical for generating the next narrative?
    Consider: character states, world conditions, active threats, thematic continuity
    """)
    
    return self._parse_context_needs(reasoning)
```

## Utility Module Specifications

### MEMNON (Memory Retrieval Utility)
- **Status**: Complete and operational
- **Interface**: Direct function calls for retrieval
- **Key Methods**:
  - `query_memory()` - Vector/hybrid search
  - `get_narrative_chunks()` - Retrieve specific chunks
  - `search_entities()` - Find character/location data

### PSYCHE (Character Psychology Utility)
- **Status**: Needs conversion from agent to utility
- **Interface**: Stateless analysis functions
- **Key Methods**:
  - `get_character_state()` - Current psychological profile
  - `analyze_relationships()` - Character dynamics
  - `generate_character_report()` - Formatted summary for context

### NEMESIS (Threat Management Utility)
- **Status**: Tables not yet populated
- **Interface**: Threat assessment and directive generation
- **Key Methods**:
  - `assess_active_threats()` - Current threat landscape
  - `generate_threat_directives()` - Guidance for Apex AI
  - `analyze_tension_needs()` - Narrative tension assessment

### GAIA (World State Utility)
- **Status**: Unclear role, needs definition
- **Proposed Interface**: Location and faction queries
- **Key Methods**:
  - `get_location_state()` - Current location conditions
  - `check_world_consistency()` - Validate world state
  - `get_faction_status()` - Political/power dynamics

### LOGON (API Communication Utility)
- **Status**: Needs simplification to API wrapper
- **Interface**: Apex LLM communication
- **Key Methods**:
  - `generate_narrative()` - Call Apex AI
  - `parse_response()` - Extract narrative and directives
  - `handle_api_errors()` - Fallback management

## Implementation Priority

1. **Phase 1**: Convert LORE to central orchestrator
   - Implement local LLM integration
   - Create utility interfaces
   - Build basic turn cycle

2. **Phase 2**: Integrate existing utilities
   - Wire up MEMNON (already complete)
   - Create simple PSYCHE utility from character tables
   - Build minimal LOGON wrapper

3. **Phase 3**: Advanced features
   - Implement NEMESIS when ready
   - Define GAIA's role if needed
   - Add sophisticated reasoning chains

## Local LLM Selection

### Recommended: Llama 3.3 70B Instruct (Q8_0)
**Rationale**:
- Proven instruction following for complex orchestration tasks
- Excellent context understanding for narrative analysis
- Good balance of capability and performance
- Strong at structured output generation

### Alternative: Mixtral 8Ex22B Instruct (Q4_K_M)
**Consider if**:
- You need faster inference speed
- You want MoE efficiency benefits
- You're doing lots of parallel reasoning tasks

### Testing Approach
Start with Llama 3.3 70B for initial development, but design LORE to easily swap LLMs:
```python
def _initialize_llm(self, model_config=None):
    # Configurable LLM initialization
    if not model_config:
        model_config = self.settings.get("lore_llm", {
            "model": "llama-3.3-70b-instruct",
            "quantization": "Q8_0"
        })
    return LLMInterface(model_config)
```