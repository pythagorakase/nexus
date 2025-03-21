**NEXUS: Narrative Intelligence System**

# Vision Statement

We are building an intelligent, dynamic memory storage and retrieval system to augment AI-driven interactive/emergent storytelling. Apex-tier LLMs are capable of nuanced, elevated prose, but are limited by two critical weaknesses.
1. Inability to maintain continuity when length of narrative exceeds context window
2. Poor ability to plan for, or attend to, elements of the story that are not explicitly on screen:
	- activities of off-screen characters
	- changing states of other locations
	- internal states of characters (secrets, hidden agendas, etc.)

Our project aims to compensate for these weaknesses with a local-LLM-driven, modular, agentic collection of scripts that coordinate to:
1. Critically analyze new input from user & storyteller AI.
2. Dynamically and intelligently build an API payload to the apex-LLM that combines recent raw narrative, structured summaries of relevant character history and events, and excerpts from the historical narrative corpus curated for maximum relevance.
3. Incorporate the apex-LLMs response (newly-generated narrative + updates to hidden variables).

# User Design Notes

The system is intentionally and strictly turn-based. When it is the user's turn to contribute the next narrative passage, the system is paused and the narrative universe is frozen. Likewise, if connectivity is interrupted or the apex-LLM cannot be reached by API for any other reason, the system will enter an "offline mode".

**Implications for Coding Strategy**
1. Real-time functionality is neither needed or desired.
2. Latency is expected and acceptable.

# Current System Specifications
- **Model**: MacBook Pro M4 Max
- **CPU**: 16-core
	- 12 performance cores
	- 4 efficiency cores
- **GPU**: 40-core
- **Neural Engine**: 16-core
- **Unified Memory**: 128GB
- **Memory Bandwidth**: 546GB/s
- **Storage**: 2TB SSD

# Turn Flow
```
   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
   │     User        │   │      Warm       │   │      World      │
┌─►│     Input       │──►│    Analysis     │──►│      State      │
│  │                 │   │                 │   │     Report      │
│  └─────────────────┘   └─────────────────┘   └────────┬────────┘
│                                                       │
│                                                       ▼
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  │    Payload      │   │      Cold       │   │        Deep     │
│  │   Assembly      │◄──│  Distillation   │◄──│     Queries     │
│  │                 │   │                 │   │                 │
│  └───────┬─────────┘   └─────────────────┘   └─────────────────┘
│          │
│          ▼                  
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  │     Apex        │   │   [Potential]   │   │        Apex     │
│  │      API        │──►│     Offline     │──►│         API     │
│  │     Call        │   │      Mode       │   │    Response     │
│  └─────────────────┘   └─────────────────┘   └────────┬────────┘
│                                                       │
│                                                       ▼ 
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  │                 │   │                 │   │      World      │
└──│      Idle       │◄──│    Narrative    │◄──│      State      │
   │     State       │   │   Integration   │   │     Update      │
   └─────────────────┘   └─────────────────┘   └─────────────────┘
```

## 01 User Input
1. Simple chat-like interface within Terminal-based UI displays recent narrative in markdown format. (See `gui_mockup.rtf`)
2. User inputs next passage.
- [ ] UI displays X last chunks in order
- [ ] UI renders markdown
- [ ] enable input with parsing (narrative vs commands)
## 02 Warm Analysis
1. `LORE` cross-references "warm slice" against high-level summary information from SQLite database along two axes:
	   - characters
	   - events
2. For characters and events, `LORE` determines if they are known (i.e., if they already have database entries) or novel entities.
3. For relationships, `LORE` identifies
	   - which characters are directly interacting with each other
	   - any relationships that are off-screen but being referred to in dialog, etc.
4. Salience is determined along three axes, flagging entities for additional retrieval of structured information:
	   - characters: `PSYCHE` 
	   - relationships: `PSYCHE`
	   - events: `LORE`
- [ ] develop structured local LLM prompt for rapidly identifying entities 
- [ ] develop lightweight message/query format to rapidly query whether identified entities are known vs novel
- [ ] develop structured local LLM prompt for parsing which entities are salient enough for queries
### 03 World State Report
1. `LORE` sends queries to `GAIA` for more detailed information:
	   - characters: detailed stored profiles for salient characters
	   - relationships: status and dynamics of salient relationships
	   - events: historical summary of already-known plot elements
2. `GAIA` answers queries, but also always appends a certain level of unsolicited information about "hidden"/off-screen variables, since this type of information is otherwise prone to being ignored or "forgotten" by LLMs.
	   - last known location & activity of off-screen characters
	   - last known status of significant locations
	   - last known status & activity of factions
- [ ] standardize and reorganize database structure
- [ ] standardize `LORE`-->`GAIA` query format for reliable retrieval
### 04 Deep Queries
1. Characters: `PSYCHE` selects one character for whom additional context/history would most benefit the Apex AI and formulates a query.
	   - "What is Alex's leadership style like?"
	   - "How has Emilia acted in similar situations before?"
2. Relationships: `PSYCHE` formulates a query for the most contextually important relationship.
	   - "How has Alex and Emilia's communication style changed over time?"
	   - "When did Alex and Emilia's relationship become romantic?"
	   - "How did Alina and Lansky interact during their first encounter?"
3. Events: `LORE`
	   - "When was the first time Alex entered The Bridge?"
	   - "What occurred immediately after the sabotage mission at the Dynacorp facility in season 1?"
4. Themes: `LORE` # having trouble thinking of good queries for this now
5. Queries are sent to `MEMNON`
- [ ] develop structured prompts for query formation
- [ ] decide whether to implement 4th category (themes/abstract)
- [ ] find balance between structured vs open-ended in query-forming prompts
### 05 Cold Distillation
1. For each query, `MEMNON` returns a broad pool of candidate chunks with permissive matching for keywords, semantic embedding, and deep metadata
2. A small, focused local LLM (such as Mixtral 8x7B, 4/5-bits) rapidly narrows the candidate chunk pool for each query to a "short list" suitable for deeper analysis and final selection
- [ ] use performance benchmarking to choose model/quantization with best balance of speed vs accuracy for intermediate filtering
- [ ] determine filtering limits at each stage (`top_k` vs maximum characters)
### 06 Payload Assembly
1. `LORE` dynamically determines percentage allotment for each component of API call within parameters. Example:
	   - system prompt & user settings: 4% (fixed)
	   - structured/summarized/hidden information: 15-30%
	   - contextual augmentation passages: 25-40%
	   - warm slice: 40-60%
2. `LORE` calculates absolute amounts of information to include for each category based on Apex AI model and corresponding TPM limit.
3. For contextual augmentation passages, `LORE` converts token budget into an overall character budget then makes final selections with the following logic:
	   - orders chunks from most relevant to least relevant
	   - removes the least relevant chunk and continues until the remainder is less than the character budget
	   - finally, reorders the final chunk selections chronologically (i.e., sort by chunk ID, "S03E07_003"), ensuring that all quoted passages are arranged in chronological order: historical context passages --> recent narrative --> last user input
4. For warm slice, `LORE` subtracts user input (a variable it cannot control) then, starting with the most recent chunk, goes backwards until this character budget is filled.
- [ ] develop prompt to encourage Apex AI to consider "hidden" variables and provide appropriate updates
### 07 Apex AI Generation
1. `LOGON` receives API payload from `LORE` and attempts to establish connection with Apex AI.
2. Checkpoint = Connectivity: If Apex API cannot be reached or fails to return valid response after a fixed amount of time, system enters offline mode. In this state, the narrative is frozen, but existing narrative history and character profiles may be browsed. `LOGON` continues to check for connectivity and retry API calls until a valid response is received.
3. Checkpoint = Quality Control: From API response, present user with new narrative passage and prompt user to (A) accept or (B) reject new content.
	   - If user rejects new content, provide option to (A) resend same API payload for regeneration, or (B) revise last user input and roll back to phase 02.
	   - If user accepts new content, proceed to next phase
### 08 Narrative Integration
1. `GAIA` processes any explicit changes to database information directed by Apex AI.
	   - "Change `location_status` of `Sullivan` from 'hiding under bed' to 'sleeping in laundry hamper'"
	   - "Change `internal_state` of `Pete` from 'resents being overlooked/underutilized' to 'determined to demonstrate he is invaluable and irreplaceable to team'"
	   - "Change `status` of `Pete_Silo` from 'abandoned' to 'occupied by squatters'"
	   - "Change "
2. `LORE` interprets new narrative for factual/event-based changes to databases.
3. `GAIA` interprets new narrative for character/relationship changes.
4. New chunk is embedded and enriched with metadata.
5. New chunk is added to user-viewable markdown-format chat interface. 
- [ ] determine whether narrative should be stored in two seprate formats (markdown + chunks)
### 09 Idle State
1. System notifies user that integration processing is complete.
2. System awaits next user input.


# Core System Architecture

This system uses the open-source Letta 

### `agents/`Agent Framework

#### `/agent_base.py` = `BaseAgent`
Base class defining the agent protocol, standard message format, and common utilities for all specialized agents.

#### `/lore.py` = `ContextManager`
- **Deep Context Analysis**: Analyzes retrieved narrative chunks to understand their significance to the current story moment.
- **Thematic Connection**: Identifies recurring themes, motifs, and narrative patterns.
- **Plot Structure Awareness**: Recognizes story beat progression, tension arcs, and narrative pacing.
- **Causal Tracking**: Understands how past events connect to present situations.
- **Metadata Enhancement**: Adds rich contextual metadata to narrative chunks for improved future retrieval.

#### `/psyche.py` = `CharacterPsychologist`
- Tracks psychological states and emotional arcs of characters
- Analyzes interpersonal dynamics between characters
- Predicts character reactions based on established personality traits
- Identifies psychological inconsistencies in narrative development
- Provides character-focused annotations for narrative generation

#### `/gaia.py` = `WorldTracker`
- Provides access to current entity states (character emotions, faction power levels, location conditions)
- Retrieves historical timelines of how entities have changed
- Tracks relationship dynamics between characters
- Answers questions like "How did Alex feel about Emilia during Episode 3?" or "Which factions controlled Downtown during Season 1?"
- Implements state changes explicitly ordered by AI after API call (e.g., updates to user-invisible variables)
- Analyzes narrative text to identify state changes
- Extracts entity mentions and their new conditions
- Writes these updated states to the database
- Records new relationships or modifications to existing ones
- Maintains database consistency and resolves conflicts

#### `/logon.py` = `NarrativeGenerator
- Model: API call to Claude 3.5 / GPT-4o
- Take the assembled context from the `ContextManager`
- Make the single API call to generate narrative text
- Handle API response parsing and error recovery

### `memory/` Shared Memory System
    - `VectorStorage`: ChromaDB integration for narrative chunks
    - `EntityRegistry`: PostgreSQL integration for structured data
    - `EventJournal`: Immutable record of all narrative events
	`/memnon.py`
		- Functions for accessing the hierarchical memory system
		- Handles coordination between SQLite and ChromaDB
		- Provides unified access methods for all memory levels
		- Extracts relevant functions from `hierarchical_memory.py`

### `adapters/` Database Adapters
- Thin wrappers around database access
- Consistent API for different storage backends
- Transaction management and error handling
	`/db_sqlite.py`: Adapter for SQLite database access handling entity data, relationships, and structured information (remains separate from ChromaDB adapter).
	`/db_chroma.py`: Adapter for vector database operations managing narrative chunks and semantic search (remains separate from SQLite adapter).

### Auxiliary Modules

#### `encode_chunks.py` Semantic Embedding
Models:
	- BGE-Large
	- E5-Large
	- BGE-Small (custom fine-tuned embedding model)
1. **Semantic Understanding**: Converting narrative text into high-dimensional vector representations that capture meaning
2. **Similarity Calculation**: Determining semantic relatedness between queries and stored narrative chunks
3. **Multi-faceted Retrieval**: Supporting different types of information needs (factual, thematic, character-focused)
4. **Domain Adaptation**: Understanding cyberpunk-specific terminology and concepts
5. **Hybrid Search Support**: Integrating with keyword and metadata-based search for comprehensive retrieval


#### `config_manager.py` 
Enables user to adjust variables likely to change often, such as preference settings and system prompts, without touching code.

#### `prove.py` Testing Suite
Contains shared utilities that can be called by other modules for testing and validation.

#### `narrative_learner.py` Learning Engine
For future implementation. Would allow for user feedback to train LLMs for better contextual retrievals.

## AI Role Summary
- **Most Core Functions & Agents**: LLama 3 70B 4-6 bit
- **Intermediate Context Retrieval Filtering**: Mixtral 8x7B 4-bit
- **New Non-User Narrative Generation**: Claude 3.5 or GPT-4o

# Processing Pipeline Stages

#### 1. Data Preparation
- BGE & E-5 export narrative chunks from local ChromaDB
- Maintain chronological organization
- Create comprehensive metadata manifest
- Mixtral performs intermediate relevancy filtering to reduce load on Llama

#### 2. Multi-Stage Analysis
- **First Pass**: Entity and Relationship Mapping
- **Second Pass**: Character Psychological Profiling
- **Third Pass**: Thematic and Narrative Function Analysis
- **Final Pass**: Hierarchical Relationship Construction

#### 3. Metadata Enrichment Schema

##### Metadata Scheme
- **Narrative Functions**: Tagging whether a chunk contains exposition, character development, plot advancement, foreshadowing, etc.
- **Emotional Valence**: Recording the emotional tone and intensity of a scene (e.g., "high tension," "emotional breakthrough," "contemplative")
- **Character Development Milestones**: Identifying significant evolution points for characters (e.g., "Emilia's first betrayal," "Alex confronts past trauma")
- **Thematic Tags**: Recognizing recurring themes like "identity," "corporate exploitation," or "transhumanism"
- **Plot Arc Position**: Categorizing where chunks fall in various narrative arcs (e.g., "inciting incident," "rising action," "climax")
- **Causal Chain Identifiers**: Linking events in cause-effect relationships (e.g., "cause of faction war," "consequence of heist")
- **Narrative Weight**: Scoring the relative importance of a chunk to the overall narrative (allowing for prioritization)

##### New Narrative: Context Manager
- After each narrative generation cycle, the Narrative Context Manager would analyze the new content
- It would process the most recent narrative chunks and identify these deeper narrative properties
- The system would then update ChromaDB with these additional metadata fields for each chunk
- Over time, your ChromaDB collection would accumulate rich narrative metadata beyond the basic episode/chunk identifiers it currently has

## Architectural Synchronization Strategy
**Hierarchical Memory Mapping**

The LLM-driven agent modules will interact with the three-tiered memory system in a specialized, layered approach:

1. **Top-Level Memory (Strategic Narrative Understanding)**
    - **Narrative Context Manager serves as the primary strategist
    - Responsibilities:
        - Maintain overarching story arcs
        - Track major character trajectories
        - Generate periodic high-level narrative summaries
        - Make strategic decisions about narrative direction
2. **Mid-Level Memory (Entity and Relationship Tracking)**
    - **Character Psychologist focuses on interpersonal dynamics
        - Uses `gaia.py` to track nuanced character states
        - Maintains psychological profiles
        - Tracks relationship evolutions
    - **World State Tracker ("Gaia")** manages broader world context
        - Monitors faction dynamics
        - Tracks location changes and global narrative implications
        - Ensures world-building consistency
3. **Chunk-Level Memory (Detailed Narrative Segments)**
    - **Embedding Team** continues semantic retrieval optimization
        - Leverages multiple embedding models (BGE-Large, E5-Large, BGE-Small)
        - Provides multi-perspective semantic understanding
    - **Event/Entity/Emotion Detection** adds metadata enrichment
        - Tags narrative chunks with additional contextual information
        - Supports more granular retrieval and analysis

