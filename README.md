# Detailed Roadmap for Building NEXUS on Letta Foundation

## 1. Initial Letta Setup and Environment Configuration

**Nature of work**: Integration, foundational setup
**Why necessary**: Establishes the base platform on which to build the narrative system
**Dependencies**: None

Letta provides a well-structured agent framework with built-in memory management, agent communication protocols, and database integration. Start by:

1. Set up the Letta server using Docker for proper PostgreSQL integration
2. Configure the environment variables for your preferred LLM backend (Claude 3.5 or GPT-4o)
3. Create a dedicated development environment for your narrative project
4. Configure Letta to use the embedding models you plan to use (BGE-Large, E5-Large, etc.)

## 2. Agent Role Mapping and Specialization

**Nature of work**: Adaptation, feature development
**Why necessary**: Maps your specialized agent roles to Letta's agent framework
**Dependencies**: Step 1

Letta provides a flexible agent framework that can be adapted to your specialized roles. Create specialized agent configurations for each of your proposed roles:

1. Configure a `LORE` agent based on Letta's BaseAgent for context analysis and management
2. Configure a `PSYCHE` agent for character psychology and relationship tracking
3. Configure a `GAIA` agent for world state tracking
4. Configure a `MEMNON` agent for memory retrieval
5. Configure a `LOGON` agent for narrative generation via Apex LLM

Each agent will be a customized implementation of Letta's Agent class with specialized prompts, tools, and memory configurations.

## 3. Memory Schema Adaptation

**Nature of work**: Adaptation, feature development
**Why necessary**: Maps your hierarchical memory architecture to Letta's memory system
**Dependencies**: Steps 1-2

Letta provides a flexible memory system with core memory blocks and archival memory, but needs to be adapted for your narrative metadata requirements:

1. Extend Letta's memory schemas to support your detailed narrative metadata scheme
2. Implement custom Block types for character profiles, relationship states, and world state information
3. Create a narrative-specific version of Memory with specialized memory integration logic
4. Adapt the in-context memory representation to support your three-tiered memory hierarchy
5. Develop custom memory templates that format memory for different narrative roles

## 4. Database Schema Extensions

**Nature of work**: New feature, adaptation
**Why necessary**: Enables storage of narrative-specific metadata and relationships
**Dependencies**: Step 3

Letta uses PostgreSQL with SQLAlchemy ORM that needs to be extended:

1. Design and implement extended database schemas for narrative-specific metadata
2. Create SQLAlchemy models for characters, relationships, locations, factions, and events
3. Develop specialized relationship tables to track character interactions and event connections
4. Design and implement the entity state tracking system for world state management
5. Add versioning support for tracking changes to character and world states over time

## 5. Embedding and Vector Search Enhancement

**Nature of work**: Adaptation, enhancement
**Why necessary**: Powers your advanced retrieval and context building capabilities
**Dependencies**: Steps 3-4

Letta already has embedding support, but needs to be enhanced for your narrative-specialized needs:

1. Implement custom embedders using your preferred models (BGE-Large, E5-Large, etc.)
2. Create specialized vector indexes for different types of narrative data (characters, events, themes)
3. Develop the multi-model embedding approach described in your README
4. Implement the hybrid search capability combining semantic, metadata, and keyword search
5. Create custom query generation logic for each agent role's specific information needs

## 6. Agent Communication Protocol Implementation

**Nature of work**: Adaptation, enhancement
**Why necessary**: Enables your specialized inter-agent workflows
**Dependencies**: Steps 2-3

Letta has a basic agent communication system that can be extended for your narrative workflow:

1. Implement the turn-based flow described in your README using Letta's messaging architecture
2. Create specialized message types for agent-to-agent communication
3. Develop the request/response patterns for each phase of your turn flow
4. Implement the query generation and response processing between agents
5. Create workflow orchestration for the full turn cycle

## 7. Narrative-Specific Tools and Functions

**Nature of work**: New feature
**Why necessary**: Provides the specialized tools your agents need for narrative tasks
**Dependencies**: Steps 2-6

Letta supports custom tools that you'll need to implement for narrative operations:

1. Develop specialized tools for character state management
2. Implement relationship analysis and tracking tools
3. Create world state update and query tools
4. Build narrative consistency checking tools
5. Implement payload assembly tools for context generation

## 8. Apex LLM Integration and API Management

**Nature of work**: Integration, adaptation
**Why necessary**: Connects your system to high-quality narrative generation
**Dependencies**: Steps 1-7

Letta has LLM integration that needs to be customized for your narrative generation needs:

1. Develop specialized prompt templates for narrative generation
2. Implement the dynamic payload assembly system described in your README
3. Create robust error handling and fallback mechanisms for API failures
4. Implement the offline mode functionality
5. Add quality control checkpoints for narrative output

## 9. Terminal-Based UI Implementation

**Nature of work**: New feature
**Why necessary**: Provides the user interface described in your README
**Dependencies**: Steps 1-8

Letta has a basic CLI, but you need a specialized narrative UI:

1. Implement the markdown-based narrative display
2. Create the command parsing system for distinguishing narrative vs commands
3. Develop the state monitoring display components
4. Implement the narrative browsing and history exploration features
5. Add the narrative quality control interface for accepting/rejecting/regenerating content

## 10. Consistency and Testing Framework

**Nature of work**: New feature
**Why necessary**: Ensures narrative consistency and system reliability
**Dependencies**: Steps 1-9

Build on Letta's testing structure to create narrative-specific testing:

1. Develop narrative consistency validation tools
2. Create character psychology consistency checkers
3. Implement world state consistency validation
4. Build automated test scenarios for narrative progression
5. Create performance benchmarking for payload optimization

## 11. Documentation and Deployment

**Nature of work**: Integration, documentation
**Why necessary**: Makes the system usable and maintainable
**Dependencies**: Steps 1-10

1. Create detailed documentation of the adapted architecture
2. Document the command system and user interface
3. Provide examples of narrative generation and interaction
4. Create deployment guides for different environments
5. Document the API for potential extensions

## Areas Where Letta Falls Short of Your Requirements

1. **Specialized Narrative Metadata**: Letta's memory system is more general-purpose and lacks the rich narrative metadata schema you've designed.

2. **Hierarchical Memory with Multiple Tiers**: Letta has core and archival memory but not the three-tiered approach you've designed.

3. **Turn-Based Flow**: Letta is more focused on continuous agent interaction than your strictly turn-based approach.

4. **Specialized Agent Roles**: Letta has general-purpose agents but not the specialized narrative roles you've designed.

5. **Narrative-Specific Payload Assembly**: Your dynamic context assembly system is more specialized than Letta's context management.

## Critical Elements to Port from Night City Stories Architecture

1. **Agent Role Specialization**: The distinct roles of LORE, PSYCHE, GAIA, MEMNON, and LOGON need to be recreated.

2. **Rich Metadata Schema**: Your detailed narrative metadata schema needs to be implemented on top of Letta.

3. **Turn Flow**: The strictly turn-based flow with distinct phases must be implemented.

4. **Dynamic Payload Assembly**: Your sophisticated system for balancing different types of context needs to be recreated.

5. **Offline Mode**: The ability to function during API outages needs to be implemented.