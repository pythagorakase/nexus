# Letta-LORE Integration Plan

## Overview
Integration strategy for incorporating Letta v0.11.3's memory system into LORE's two-pass context assembly framework.

## Phase 1: Foundation Setup
1. **Create LettaMemoryBridge class** (`nexus/agents/lore/utils/letta_bridge.py`)
   - Initialize Letta client connection to local server
   - Create dedicated LORE agents with memgpt_v2_agent type
   - Map SessionStore operations to Letta agent state persistence

2. **Design Memory Schema Mapping**
   - Map LORE's SessionContext to Letta's Memory blocks
   - Store Pass 1 context in Letta's core memory (human/persona blocks)
   - Use archival memory for narrative chunks and entity data
   - Leverage recall memory for query history and patterns

## Phase 2: Custom Tool Development
3. **Create Letta Tools for LORE Utilities**
   - `memnon_search_tool`: Wrap MEMNON's vector/hybrid search
   - `logon_sql_tool`: Wrap LOGON's SQL query capabilities
   - `psyche_character_tool`: Wrap PSYCHE's character analysis
   - `gaia_location_tool`: Wrap GAIA's spatial queries

4. **Implement Tool Registration**
   - Register tools with Letta server using `client.tools.upsert_from_function()`
   - Configure tool rules for proper execution flow
   - Add tools to LORE agents dynamically based on context needs

## Phase 3: Memory Bridge Implementation
5. **Replace SessionStore with LettaMemoryBridge**
   - Migrate from JSON to Letta agent state persistence
   - Implement session create/load/save using Letta agents
   - Maintain backward compatibility with existing SessionStore API

6. **Two-Pass Memory Management**
   - Pass 1: Store Storyteller context in agent's core memory
   - Between passes: Persist state as Letta agent checkpoint
   - Pass 2: Restore agent, analyze user input, expand context
   - Use Letta's memory search for gap detection

## Phase 4: Integration Testing
7. **Create Test Harness**
   - Unit tests for LettaMemoryBridge operations
   - Integration tests with LORE's turn cycle
   - Test two-pass flow with karaoke example
   - Verify token budget management

8. **Performance Optimization**
   - Profile memory operations
   - Optimize agent creation/loading
   - Implement caching for frequently accessed agents

## Key Benefits
- **Persistent Memory**: Database-backed storage instead of JSON files
- **Scalable Architecture**: Letta server handles concurrent sessions
- **Rich Memory Search**: Leverage Letta's archival/recall memory capabilities
- **Tool Extensibility**: Easy to add new LORE utilities as Letta tools
- **Cross-Session Learning**: Letta agents can learn patterns across sessions

## Files to Create/Modify
- `nexus/agents/lore/utils/letta_bridge.py` (new)
- `nexus/agents/lore/utils/letta_tools.py` (new)
- `nexus/agents/lore/lore.py` (modify to use LettaMemoryBridge)
- `nexus/agents/lore/utils/session_store.py` (keep for fallback)
- `tests/test_letta_integration.py` (new)

## Notes
This integration preserves LORE's two-pass architecture while gaining Letta's powerful memory management, creating a best-of-both-worlds solution.