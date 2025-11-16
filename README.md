# *NEXUS: Narrative Intelligence System*

# 1. Introduction

## 1.1 Purpose & Vision
We are building an intelligent, dynamic memory storage and retrieval system to augment AI-driven interactive/emergent storytelling. Apex-tier LLMs are capable of nuanced, elevated prose, but are limited by two critical weaknesses.
1. Inability to maintain continuity when length of narrative exceeds context window
2. Poor ability to plan for, or attend to, elements of the story that are not explicitly on screen:
	- activities of off-screen characters
	- changing states of other locations
	- internal states of characters (secrets, hidden agendas, etc.)

Our project aims to compensate for these weaknesses with a local-LLM-driven orchestration system that coordinates specialized utilities to:
1. Critically analyze new input from user & storyteller AI.
2. Dynamically and intelligently build an API payload to the apex-LLM that combines recent raw narrative, structured summaries of relevant character history and events, and excerpts from the historical narrative corpus curated for maximum relevance.
3. Incorporate the apex-LLMs response (newly-generated narrative + updates to hidden variables).

## 1.2 Scope & Limitations

### Limited Design "Team"
This is currently a passion project, driven by the user's desire to enjoy roleplaying and interactive storytelling with an AI beyond the constraints noted above. The development team is the user; you, the AI; and as many other AI instances as need be mustered by the user to see this project through, in whatever role is required: coding AI, project manager AI, debugging AI, etc. 

The user has limited somewhat technical knowledge, but is learning Python and SQL in order to better understand and guide the project.

### Vibe over Mechanics
The interactive, user-choice-driven flow has much in common with the kind of collaborative storytelling that can be found in tabletop RPG sessions with creative-minded people. However, incorporating similar rules systems is not currently a goal. When the user decides their character will attempt a difficult action, the result will be determined not by a "skill check" but rather by whatever the Apex AI determines is the best fit for the narrative. Similarly, there is no plan to design a "combat system".

There are already numerous rogue-like dungeon-crawlers with satisfyingly deep rules systems and tactics; instead of spending time and tokens trying to emulate them, our prime objective is to achieve unparalleled excellence in the roleplaying experience: richness of plot, depth of characters, a world that feels alive and engaging, and high-quality prose.

### Slow by Design
Real-time functionality is neither needed nor desired. The system is intentionally and strictly turn-based. In accordance with the overriding emphasis on quality latency is not just acceptable—it is expected.

## 1.3 Key Concepts
- **Apex AI**: Frontier LLM (Claude/GPT/Grok) that generates narrative content
- **Memory Tiers**: The three-part memory architecture (Strategic, Entity, Narrative)
- **Warm Slice**: Most recent narrative chunks plus new user input
- **Cold Distillation**: The process of retrieving and filtering narrative memory
- **Context Payload**: The assembled package of information sent to the Apex AI
- **Turn Cycle**: The step-by-step sequence from user input to new narrative
- **Entity State**: Character emotions, location conditions, faction status, etc.
- **Chunk**: A discrete piece of narrative text, typically a single scene or interaction

## 1.4 Local Development Servers

The `./iris` helper script now orchestrates every service required for UI work:

1. `cd /Users/pythagor/nexus && poetry install` (first run only).
2. `./iris`
   - Boots the Vite/Express dev server (default port 5001, respecting `PORT`).
   - Starts the Audition FastAPI app on `API_PORT` (default `8000`) and proxies it through `/api/audition`.
   - Starts the Core FastAPI model manager on `CORE_API_PORT` (default `8001`) and exposes it via `/api/models` + `/api/health`.

The Core API expects LM Studio plus the `lmstudio` Python SDK to be available locally so it can query `/api/models/status` and load/unload models. If you need to run components manually, start both FastAPI apps with `poetry run uvicorn nexus.api.apex_audition:app --reload --port 8000` and `poetry run uvicorn nexus.api.core:app --reload --port 8001`, then run `npm run dev` inside `ui/` with matching `API_PORT`/`CORE_API_PORT` environment variables so the proxies target the correct ports.

For longer debugging sessions you can now supervise every service with the included `Procfile.dev`. Install either [Honcho](https://honcho.readthedocs.io/en/latest/) (`pip install honcho`) or Foreman (`brew install foreman`), then run:

```
honcho start -f Procfile.dev
```

The Procfile respects the same `PORT`, `API_PORT`, and `CORE_API_PORT` variables as `./iris`, so you can override any of them before launching if a port is already in use.
If `DATABASE_URL` is unset, it automatically falls back to the local `postgresql://pythagor@localhost:5432/NEXUS`, mirroring the `iris` defaults.

# 2. System Architecture

## 2.1 Architectural Overview
NEXUS is built on a single-agent orchestration architecture implemented entirely within this repository. At its core, the system uses LORE as the primary intelligent agent that coordinates specialized utility modules in a turn-based cycle.

```
┌─────────┐                                   ┌─────────┐
│  User   ├───────────────────────────────────┤ Apex AI │
└─────────┘                                   └─────────┘
                          │
                     ┌────┴────┐ 
                     │  LORE   │
                     │ (Agent) │
                     └────┬────┘
                          │
            ┌─────────────┴─────────────┐
            │      Utility Modules      │
            ├───────────────────────────┤
            │ PSYCHE │ GAIA │ MEMNON   │
            │ NEMESIS│ LOGON│           │
            └─────────────┬─────────────┘
                          │                          
       ┌──────────────────┴───────────────────┐
       │ vector     ¦    PSQL    ¦      chunk │ 
       │ embeddings ¦  database  ¦   metadata │ 
       └──────────────────────────────────────┘
```

### Agent & Utility Modules
- **LORE (Agent)**: Primary orchestration agent that coordinates all utilities and manages the turn cycle
- **LOGON (Utility)**: Handles all API traffic with Apex AI, delivers new narrative
- **PSYCHE (Utility)**: Profiles/analyzes characters and relationships
- **GAIA (Utility)**: Tracks/updates world state
- **MEMNON (Utility)**: Provides unified access for queries to system memory, memory management
- **NEMESIS (Utility)**: Analyzes threats and narrative tension

### AI Role Summary
The system employs two tiers of AI:
**Frontier LLMs** ("Apex AI" = GPT/Claude/Grok)
- Generate new narrative to continue from last user input
- Updates to world state variables
- Update hidden information
**Local LLMs** (Llama)
- LORE agent reasoning and orchestration
- Utility functions (analysis, retrieval, coordination)
- Preparation for new narrative
- Post-generation processing and integration

### PostgreSQL
Data flows through a unified PostgreSQL database with vector extensions that stores:
- Complete narrative history with vector embeddings
- Structured character and world state information
- Cross-referenced connections between entities and narrative moments
- Rich metadata for context-aware retrieval 

## 2.2 System Components
### LORE (Primary Agent)
`Orchestration & Context Management`
- Deep Context Analysis: Analyzes retrieved narrative chunks to understand their significance to the current story moment.
- Thematic Connection: Identifies recurring themes, motifs, and narrative patterns.
- Plot Structure Awareness: Recognizes story beat progression, tension arcs, and narrative pacing.
- Causal Tracking: Understands how past events connect to present situations.
- Metadata Enhancement: Adds rich contextual metadata to narrative chunks for improved future retrieval.

Module Specifications:
[[blueprint_lore]]

### PSYCHE (Utility Module)
`Character Psychology Analysis`
- Tracks psychological states and emotional arcs of characters
- Analyzes interpersonal dynamics between characters
- Predicts character reactions based on established personality traits
- Identifies psychological inconsistencies in narrative development
- Provides character-focused annotations for narrative generation

Module Specifications:
[[blueprint_psyche]]

### GAIA (Utility Module)
`World State Tracking`
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

Module Specifications:
[[blueprint_gaia]]

### NEMESIS (Utility Module)
`Threat Analysis & Narrative Tension`
- Identifies both explicit and potential threats across multiple domains: physical, interpersonal, and environmental.
- Assesses identified threats along axes of probability and magnitude of impact.
- For each threat, identifies potential user courses of action that could escalate or deescalate them.
- Generates per-turn threat assessment report for Apex AI.

Module Specifications:
[[blueprint_nemesis]]

### LOGON (Utility Module)
`API Communication Handler`
- Model: API call to Claude 3.5 / GPT-4o
- Take the assembled context from the `ContextManager`
- Make the single API call to generate narrative text
- Handle API response parsing and error recovery

Module Specifications:
[[blueprint_logon]]

### MEMNON (Utility Module - Fully Operational)
`Memory Access & Retrieval System`

**Production-Ready Implementation**:
MEMNON is a sophisticated, fully operational information retrieval system that serves as LORE's primary interface to the narrative database. It implements advanced IR techniques specifically optimized for narrative intelligence.

**Multi-Model Embedding Architecture**:
- Manages 3 active embedding models with weighted fusion:
  - inf-retriever-v1-1.5b (1536d, weight 0.5)
  - E5-Large-V2 (1024d, weight 0.3)
  - BGE-Large-EN (1024d, weight 0.2)
- Dimension-specific PostgreSQL tables with pgvector
- Automatic model routing and result fusion

**Advanced Search Capabilities**:
- **Hybrid Search**: Configurable vector + text search with query-type-specific weights ([detailed documentation](docs/hybrid_search.md))
- **Temporal Search**: Continuous temporal intent analysis with narrative-aware boosting
- **Cross-Encoder Reranking**: Sliding window approach for semantic similarity refinement
- **Query Classification**: Automatic categorization (character, event, location, theme, etc.)
- **IDF-Weighted Text Search**: PostgreSQL full-text search with term relevance weighting
- **Character Alias Resolution**: Handles perspective shifts and character references

**Performance Features**:
- Batch processing for embeddings and reranking
- Model caching and session management
- 8-bit quantization support for memory efficiency
- Comprehensive logging and error handling

Implementation: `nexus/agents/memnon/`

### Auxiliary Modules

#### Agent Runtime Helpers
Lightweight utilities inside `nexus/agents/` provide agent lifecycle hooks, message formatting, and shared services without relying on external frameworks.

#### `narrative_learner.py` Learning Engine
For future implementation. Would allow for user feedback to train LLMs for better contextual retrievals.

## 2.3 Agent Runtime Evolution
NEXUS originally launched on top of the open-source Letta project (formerly MemGPT), but the dependency created coordination overhead and brittle local paths. The current architecture ships with a custom, embedded agent runtime that preserves the same high-level abstractions—turn cycles, tool execution, and structured memory—but is purpose-built for the narrative intelligence stack. This eliminates submodules, stabilizes packaging, and keeps all execution-critical code under first-party control.


## 2.4 Technical Dependencies

### Software
- **PostgreSQL with pgvector**: Powers the vectorized database for semantic search and embedding storage
- **SQLAlchemy**: Object-relational mapper for database interaction and query building
- **Alembic**: Database migration tool for versioning and evolving the database schema
- **Pydantic**: Data validation and settings management library
- **Sentence-Transformers**: Powers the triple-embedding strategy using models like BGE and E5
- **Transformers**: Hugging Face's transformers library for accessing and using embedding models
- **pgvector**: PostgreSQL extension enabling vector similarity operations for semantic search
- **OpenAI API**: Interface for new narrative generation with frontier LLMs
- **Anthropic API**: Alternative interface for narrative generation with Claude models
- **FastAPI and Uvicorn**: Web framework and ASGI server for potential API endpoints
- **NumPy**: Scientific computing library for array operations and embedding manipulation
- **Tiktoken**: Token counting library for managing context window constraints
- **Requests**: HTTP library for API interactions

### Hardware
Performance quality and latency will depend on the user's ability to run a capable local LLM.

Development Hardware:
	- **Model**: MacBook Pro M4 Max
	- **CPU**: 16-core
		- 12 performance cores
		- 4 efficiency cores
	- **GPU**: 40-core
	- **Neural Engine**: 16-core
	- **Unified Memory**: 128GB
	- **Memory Bandwidth**: 546GB/s
	- **Storage**: 2TB SSD

# 3. Data Design

## 3.1 Memory Architecture
1. **Strategic Memory** (high-level narrative understanding):
    - Implemented as structured tables with explicit schemas
    - Accessed through direct SQL queries
    - Contains synthesized information about plot, themes, character arcs
2. **Entity Memory** (character/location tracking):
    - Implemented as structured tables with relationships
    - Accessed through entity-specific queries
    - Contains detailed state information for characters, locations, etc.
3. **Narrative Memory** (detailed text chunks):
    - Implemented as vector-enabled tables
    - Accessed through similarity search
    - Contains the actual narrative text with rich metadata

## 3.2 Database Schema
See `NEXUS_schema.sql`

## 3.3 Embedding Strategy

### Semantic Embedding
Models:
	- inf-retriever-v1-1.5b (1536 dimensions, weight 0.5)
	- E5-Large-V2 (1024 dimensions, weight 0.3)
	- BGE-Large-EN (1024 dimensions, weight 0.2)

#### Database Storage Strategy
The system uses separate tables for different vector dimensions:
- **chunk_embeddings_1536d**: Table for 1536-dimensional vectors (inf-retriever-v1-1.5b)
- **chunk_embeddings_1024d**: Table for 1024-dimensional vectors (E5-Large-V2, BGE-Large-EN)

This separation maintains efficient storage and query performance in PostgreSQL with pgvector, which requires fixed dimensions at table creation time.

#### Automatic Table Selection
The system includes utilities that automatically route queries to the correct table based on the model name, allowing for transparent usage of multiple vector dimensions in the same codebase.

#### Search Capabilities
1. **Semantic Understanding**: Converting narrative text into high-dimensional vector representations that capture meaning
2. **Similarity Calculation**: Determining semantic relatedness between queries and stored narrative chunks
3. **Multi-faceted Retrieval**: Supporting different types of information needs (factual, thematic, character-focused)
4. **Triple-Embedding Strategy**: Using multiple models to capture different semantic aspects
5. **Domain Adaptation**: Understanding narrative-specific terminology and concepts
6. **Hybrid Search Support**: Integrating with keyword and metadata-based search for comprehensive retrieval
7. **Cross-Encoder Reranking**: Using Naver TREC-DL22 model for final result refinement

See the detailed documentation in [docs/vector_embeddings.md](docs/vector_embeddings.md) for more information.

### Metadata Tagging
See:
`narrative_metadata_schema_2.json`
and
`batch_metadata_processing.py`

## 3.4 Cross-Reference System
- Entity-to-Narrative
	- character profile --> every scene where they appear
	- location --> descriptions and local events
	- objects/items --> passages where used or mentioned
- Entity Relationships
	- character <--> character
	- character <--> location
	- faction <--> territory
- Temporal Cross-References
	- story clock --> events occurring then
	- narrative order --> place in story progression
	- character timeline = person-specific chronology
- Thematic Links
	- themes (e.g., "transhumanism") --> scenes exploring this theme
	- motifs --> each appearance of motif
	- emotional tones --> passages with specific moods

# 4. Core Workflows
## 4.1 Turn Cycle Sequence

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

Details:
[[turn_flow_sequence]]

## 4.2 Context Assembly Process
1. `LORE` dynamically calculates a context budget based on Apex AI TPM limits, assigning percentage shares for warm slice, historical passage quotes, and structured information.
2. Local LLM generates 3-5 targeted retrieval queries based on narrative context analysis (replacing PSYCHE query formulation).
3. Programmatic entity queries retrieve characters, locations, relationships, active events, and threats from the database based on `entity_inclusion` settings (warm slice chunk references, status filters, configurable limits).
4. `LORE` uses `MEMNON` utility to retrieve broad pool of candidate chunks using multi-model embeddings, with intermediate filtering and cross-encoder reranking for final selections.

## 4.3 Query Framework
The Query Framework serves as the communication backbone of NEXUS, enabling structured information exchange between LORE and its utility modules. It expands the native MEMNON query stack with narrative-specific enhancements tailored to our schema and retrieval strategies.

- **Specialized Query Types**: Purpose-built queries for different narrative needs:
    - Character queries (psychology, relationships, development)
    - World state queries (locations, factions, objects, conditions)
    - Narrative context queries (themes, plot continuity, motifs)
    - Multi-domain synthesis queries (complex historical analysis)
- **Two-Phase Retrieval Process**:
    - Phase 1: Broad retrieval across memory types using multi-model embeddings
    - Phase 2: Cross-encoder reranking for final result refinement
- **Cross-Reference System**: Core innovation that connects:
    - Entity-to-narrative links (characters/locations → relevant passages)
    - Temporal indexing (story time + narrative order)
    - Thematic tagging (themes, motifs, emotional tones)
    - State change tracking (entity changes linked to causal moments)

This framework enables LORE to coordinate its utilities to access precisely the right information at the right time, ensuring narrative coherence across unlimited storytelling length and maintaining consistent character and world development even for off-screen elements.

Detailed:
[[query_framework]]

## 4.4 Error Recovery

### API Failures
- **Temporary Outage**: Retry strategy with exponential backoff (3 attempts)
- **Content Moderation Rejection**: Alternative prompt formulation
- **Rate Limiting**: Queue system with delayed retry

### Narrative Consistency Issues
- **Character Inconsistency**: `PSYCHE` flags contradictions for correction
- **World State Conflict**: `GAIA` resolves conflicts using confidence scoring
- **Timeline Paradox**: System enforces chronological consistency

### User Interaction
- **Narrative Rejection**: User can request regeneration with modifications
- **Rollback**: System can revert to previous stable state

# 5. Interface Design

## 5.1 User Interface
NEXUS is textual, from front-end to back-end. The UI will serve the centrality and primacy of engaging with high-quality text by presenting a simple, retro terminal-based experience.

Readability will be enhanced by markdown formatting, and a simple retro color scheme.

Design Details:
[[ui_design]]

## 5.2 Command System
- simple parsing with either numbered options or standardized commands for (default) user narrative input, accepting/rejecting new AI-generated content, adjusting settings, etc

# 6 Development Roadmap

## 6.1 Current Status
User is taking Python and SQL courses in order to better understand and guide the development process and its products.

## 6.2 Next Steps

### General
- [x] import legacy SQLite database and develop PSQL schema

### Per Turn Sequence
#### 01 User Input
- [ ] UI displays X last chunks in order
- [ ] UI renders markdown
- [ ] enable input with parsing (narrative vs commands)
#### 02 Warm Analysis
- [ ] develop structured local LLM prompt for rapidly identifying entities 
- [ ] develop lightweight message/query format to rapidly query whether identified entities are known vs novel
- [ ] develop structured local LLM prompt for parsing which entities are salient enough for queries
#### 03 World State Report

#### 04 Deep Queries
- [ ] develop structured prompts for query formation
- [ ] find balance between structured vs open-ended in query-forming prompts

#### 05 Cold Distillation
- [ ] use performance benchmarking to choose model/quantization with best balance of speed vs accuracy for intermediate filtering
- [ ] determine filtering limits at each stage (`top_k` vs maximum characters)
#### 06 Payload Assembly
- [ ] finesse local AI prompt to encourage spending as much as possible under token limits, rather than being "frugal"
- [ ] develop prompt to encourage Apex AI to consider "hidden" variables and provide appropriate updates

#### 07 Apex AI Generation


#### 08 Narrative Integration
- [ ] develop design for time tracking

#### 09 Idle State


## 6.3 Future Extensions
- [x] World Clock: stored and validated by `GAIA` as a database value, updated by soliciting `time_delta` from Apex AI during narrative generation (accounting for in-scene times as well as skips for sleeping, travel, montages)
- [ ] Chronological Non-Linearity: timestamp independent of narrative order tag could allow for flashbacks without breaking system (maybe?)
- [ ] Add system prompts for starting a saga in other genres
- [ ] Limited (1-2 slots) save system
