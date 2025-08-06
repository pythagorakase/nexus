The Query Framework in NEXUS builds upon Letta's existing database abstraction and search capabilities while implementing significant extensions to support narrative intelligence needs. This system serves as the communication backbone between agents and enables sophisticated information retrieval across memory types.

# Letta Foundation and NEXUS Extensions

**Letta's Existing Capabilities:**

- SQLAlchemy-based ORM with unified interface for text and vector search
- Conversation history retrieval with direct text matching
- Archival memory with semantic (embedding-based) search
- Support for multiple embedding models
- Basic filtering, pagination, and sorting

**NEXUS Extensions:**

- Cross-reference system connecting structured and vector data
- Enhanced metadata tagging for narrative elements
- Narrative-specific query types and patterns
- Multi-model embedding combination for improved semantic understanding
- Temporal awareness for narrative chronology
- Entity relationship modeling and traversal
- Information synthesis across memory types

# Query Types and Specialized Handlers

NEXUS implements specialized query types handled by dedicated agents:

**Character Queries (PSYCHE)**

- Psychological state tracking: "What's Alex's current emotional state?"
- Relationship analysis: "How has Emilia's trust in Alex evolved?"
- Motivation tracking: "What are Dr. Nyati's current goals?"
- Character development: "How has Pete changed since the incident in S01E05?"

**World State Queries (GAIA)**

- Location status: "What's the current condition of The Combat Zone?"
- Faction control: "Which groups are competing for influence in Neon Bay?"
- Object tracking: "Where is the prototype cybernetic implant?"
- Global conditions: "What's the current political climate in Night City?"

**Narrative Context Queries (LORE)**

- Thematic retrieval: "Find passages exploring the theme of transhumanism"
- Plot continuity: "Retrieve scenes setting up the current conflict"
- Motif tracking: "Show instances where the 'neon rain' motif appears"
- Scene reconstruction: "What happened the last time Alex visited The Underbelly?"

**Multi-domain Synthesis Queries (MEMNON)**

- Complex historical analysis: "How has the power dynamic between factions shifted since Season 1?"
- Character-world interactions: "How have events in The Combat Zone affected Emilia's psychological state?"
- Causal chains: "What sequence of events led to the current tension between Alex and Dr. Nyati?"

# Multi-Tier Retrieval Process

All complex queries follow a two-phase distillation process:

**Phase 1: Initial Retrieval**

- Translate narrative query to appropriate database operations
- Apply metadata filters (time period, characters, locations)
- Perform combined retrieval across appropriate memory types:
    - Strategic memory (SQL tables for themes, plot)
    - Entity memory (character/world state tables)
    - Narrative memory (vector search in text corpus)
- Return top 50 candidate results based on relevance scoring

**Phase 2: Refined Selection**

- Apply cross-encoder reranking for semantic similarity scoring
- Evaluate each candidate for narrative relevance
- Apply intelligent reranking based on:
    - Direct relevance to query
    - Narrative significance
    - Chronological position
    - Character/plot importance
- Return top 10 filtered results ordered for optimal coherence

# Cross-Reference System

A core innovation in NEXUS is the cross-reference system implemented by MEMNON:

- **Entity-to-Narrative Links**: Each character, location, and object maintains links to relevant narrative passages where they appear
- **Temporal Indexing**: All data is indexed by both story time (in-universe) and narrative order (episode/scene)
- **Relationship Graph**: Character and faction relationships are modeled as a graph database layer for traversal
- **Thematic Tagging**: Narrative chunks are tagged with themes, motifs, and emotional tones
- **State Change Tracking**: Entity state changes are linked to their causal narrative moments

# Implementation Architecture

The Query Framework is implemented as follows:

1. **Query Interface Layer**:
    - Extends Letta's `Agent.step()` method for specialized query handling
    - Implements standardized query message format
    - Routes queries to appropriate handler agents
2. **Semantic Layer**:
    - Enhances Letta's embedding system with multi-model approach
    - Implements domain-specific embedding fine-tuning
    - Provides weighted combination of different embedding models
3. **Storage Access Layer**:
    - Extends Letta's SQLAlchemy implementation
    - Adds specialized joins between entity and narrative tables
    - Implements temporal retrieval patterns
    - Manages hybrid SQL/vector queries
4. **Synthesis Layer**:
    - New component not present in Letta
    - Uses local LLMs to combine and process query results
    - Implements result formatting based on requesting agent's needs
    - Resolves conflicts and contradictions in retrieved data

By extending Letta's foundation with these specialized capabilities, NEXUS achieves a significantly more sophisticated query system optimized for narrative intelligence, enabling the creation of coherent, contextually-aware interactive storytelling.