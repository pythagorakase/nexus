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
- **Skald (Apex AI)**: Frontier LLM (Claude/GPT/Grok) that generates narrative content
- **Memory Tiers**: The three-part memory architecture (Strategic, Entity, Narrative)
- **Warm Slice**: Most recent narrative chunks plus new user input
- **Cold Distillation**: The process of retrieving and filtering narrative memory
- **Context Payload**: The assembled package of information sent to Skald
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
│  User   ├───────────────────────────────────┤  Skald  │
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
            │    MEMNON  │  LOGON       │
            └─────────────┬─────────────┘
                          │
       ┌──────────────────┴───────────────────┐
       │ vector     ¦    PSQL    ¦      chunk │
       │ embeddings ¦  database  ¦   metadata │
       └──────────────────────────────────────┘
```

### Agent & Utility Modules
- **LORE (Agent)**: Primary orchestration agent that coordinates utilities and manages the turn cycle
- **MEMNON (Utility)**: Headless information retrieval system with multi-strategy search and cross-encoder reranking
- **LOGON (Utility)**: Handles API traffic with Skald, delivers new narrative

### AI Role Summary
The system employs two tiers of AI:
**Skald** (Frontier LLM: Claude/GPT/Grok)
- Generates new narrative to continue from last user input
- Updates world state variables
- Updates hidden information
**LORE** (Local LLM: Llama)
- Agent reasoning and orchestration
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

### MEMNON (IR System)
`Memory Access & Retrieval System`

MEMNON is a headless information retrieval system that serves as LORE's primary interface to the narrative database. It implements advanced IR techniques specifically optimized for narrative intelligence.

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

### LOGON (Utility Module)
`API Communication Handler`
- Handles API calls to Claude / GPT models
- Takes the assembled context from LORE
- Makes the API call to generate narrative text
- Handles API response parsing and error recovery

## 2.3 Technical Dependencies

### Software
- **PostgreSQL with pgvector**: Powers the vectorized database for semantic search and embedding storage
- **SQLAlchemy + Alembic**: ORM for database interaction and migration management
- **Pydantic**: Data validation and settings management
- **Sentence-Transformers + Transformers**: Powers the triple-embedding strategy using models like BGE and E5
- **OpenAI / Anthropic APIs**: Interfaces for narrative generation with frontier LLMs
- **FastAPI + Uvicorn**: Web framework and ASGI server for API endpoints
- **LM Studio SDK**: Local LLM inference for LORE agent operations
- **llama-cpp-python**: Direct local model inference support
- **PyTorch + Accelerate**: ML framework for embedding models and cross-encoder reranking
- **Tiktoken**: Token counting for managing context window constraints
- **React + TypeScript**: Modern frontend UI framework

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

## 3.2 Embedding Strategy

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

Details: [Turn Flow Sequence](docs/turn_flow_sequence.md)

## 4.2 Context Assembly Process

LORE orchestrates context assembly through a two-pass memory system:

**Pass 1: Baseline Assembly** (triggered by Skald's narrative generation)
1. LORE calculates a context budget based on Skald token limits
2. Local LLM generates targeted retrieval queries based on narrative context
3. MEMNON executes multi-strategy search (vector + text + hybrid scoring)
4. Cross-encoder reranking refines results for semantic relevance
5. LORE assembles the baseline context package: warm slice, historical excerpts, entity state

**Pass 2: Divergence Detection** (triggered by user input)
1. When user completes a chunk with their input, LORE analyzes for divergence
2. LLM-based detector checks if user references entities/events NOT in the baseline
3. If divergence detected, additional targeted retrieval fills the gaps
4. Updated context ensures Skald has full awareness of user-referenced elements

This two-pass approach ensures continuity: Pass 1 provides context for generation, Pass 2 catches novel user references that need historical grounding.

## 4.3 Error Recovery

### API Failures
- **Temporary Outage**: Retry strategy with exponential backoff (3 attempts)
- **Content Moderation Rejection**: Alternative prompt formulation
- **Rate Limiting**: Queue system with delayed retry

### User Interaction
- **Narrative Rejection**: User can request regeneration with modifications
- **Rollback**: System can revert to previous stable state

# 5. Interface Design

## 5.1 User Interface

NEXUS features a modern React/TypeScript web interface built with Vite and shadcn/ui components.

**Main Navigation Tabs**:
- **Narrative**: Primary story view with markdown rendering, accept/reject controls for new generations, and command input
- **Map**: Geographic visualization of story locations
- **Characters**: Character profiles and relationship tracking
- **Audition**: Model comparison tool for evaluating different LLM outputs
- **Settings**: Configuration for models, themes, and system behavior

**Key Features**:
- **Theme System**: Multiple visual themes (Vector, Veil, Gilded) with consistent styling
- **New Story Wizard**: Conversational LLM-guided flow for creating new stories:
  - **Slot Selection**: Choose from save slots 2-5 (slot 1 protected)
  - **Setting Phase**: Genre, tech level, magic system, themes, diegetic artifact
  - **Character Phase**: Three sub-phases—concept definition, trait selection (3 of 10 options), wildcard trait
  - **Seed Phase**: Story opening type, location hierarchy, timestamp, secrets channel
- **Wizard Features**: "Accept Fate" button for autonomous Skald progression, structured choice system (2-4 options per response), interactive trait selector
- **Save Slot System**: 5-slot save system for managing multiple narrative sessions (slot 1 protected)
- **Status Bar**: Real-time display of model status, APEX connectivity, and generation state
- **Responsive Layout**: Adapts to different screen sizes with collapsible panels

## 5.2 Development Server

The `./iris` script orchestrates all services:
- Vite/Express dev server (default port 5001)
- Audition FastAPI app (port 8000, proxied via `/api/audition`)
- Core FastAPI model manager (port 8001, exposed via `/api/models` + `/api/health`)
