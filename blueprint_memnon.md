# MEMNON Agent Blueprint (Unified Memory Access System)

## Overview

MEMNON serves as a unified memory access system responsible for retrieving and managing narrative information across both structured database storage (PostgreSQL) and semantic vector storage. It provides a cohesive query interface, translates narrative queries into appropriate database operations, and synthesizes results from multiple sources into coherent responses.

## Key Responsibilities

1. **Unified Memory Access** - Provide a single query interface for all forms of memory (structured and vector)
2. **Memory Tier Integration** - Map specialized memory needs to Letta's two-tier memory architecture
3. **Multi-Model Embedding** - Utilize multiple embedding models to capture different semantic aspects
4. **Hybrid Search** - Combine structured database queries, semantic search, and keyword search
5. **Cross-Reference Management** - Maintain and utilize connections between structured and vector data
6. **Deep Query Processing** - Answer complex narrative queries requiring synthesis across multiple sources

## Technical Requirements

### Integration with Letta Framework

- Extend Letta's `Agent` class 
- Leverage Letta's memory system and PostgreSQL integration
- Utilize Letta's embedding system with extended functionality
- Implement custom memory retrieval workflows across storage types

### Memory Tier Adaptation

- Adapt to Letta's two-tier memory structure (Core and Archival)
- Implement specialized handling within Archival memory for:
  - Strategic narrative information (themes, arcs, global state)
  - Entity data (characters, locations, factions)
  - Detailed narrative chunks with rich metadata
- Create virtual memory tiers through metadata and query handling

### Cross-Storage Retrieval

- Develop unified query translation for different storage backends
- Create result synthesis mechanisms to combine structured and vector results
- Implement cross-referencing between database entities and narrative chunks
- Build relevance scoring across different storage types

### Query Interface

- Provide rich query language for complex information needs
- Support specialized narrative query types (character, event, theme, relationship)
- Enable aggregation and synthesis of information across storage types
- Create a coherent response format regardless of data source

## Pseudocode Implementation

```python
from letta.agent import Agent
from letta.schemas.agent import AgentState
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
from letta.embeddings import EmbeddingEndpoint
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import json
import sqlalchemy

class MEMNON(Agent):
    """
    MEMNON (Unified Memory Access System) agent responsible for accessing and 
    retrieving narrative information across all memory types.
    """
    
    def __init__(self, 
                 interface, 
                 agent_state: AgentState,
                 user,
                 **kwargs):
        """
        Initialize MEMNON agent with unified memory access capabilities.
        
        Args:
            interface: Interface for agent communication
            agent_state: Agent state from Letta framework
            user: User information
            **kwargs: Additional arguments
        """
        # Initialize parent Agent class
        super().__init__(interface, agent_state, user, **kwargs)
        
        # Initialize specialized memory blocks if not present
        self._initialize_memory_blocks()
        
        # Set up database connections
        self.db_engine = self._initialize_database_connection()
        
        # Set up embedding models
        self.embedding_models = self._initialize_embedding_models()
        
        # Configure retrieval settings
        self.retrieval_settings = {
            "default_top_k": 20,
            "max_query_results": 50,
            "relevance_threshold": 0.75,
            "entity_boost_factor": 1.2,
            "recency_boost_factor": 1.1,
            "db_vector_balance": 0.6,  # 60% weight to database, 40% to vector
            "model_weights": {
                "bge-large": 0.4,
                "e5-large": 0.4,
                "bge-small-custom": 0.2
            }
        }
        
        # Memory type registry - maps virtual memory tier to actual storage
        self.memory_tiers = {
            "strategic": {"type": "database", "tables": ["themes", "plot_arcs", "global_state"]},
            "entity": {"type": "database", "tables": ["characters", "locations", "factions", "relationships"]},
            "narrative": {"type": "vector", "collections": ["narrative_chunks"]},
        }
    
    def _initialize_memory_blocks(self):
        """Initialize specialized memory blocks if not present."""
        # Check if memory blocks exist and create if needed
        required_blocks = ["memory_index", "query_templates", "retrieval_stats", "db_schema"]
        
        for block_name in required_blocks:
            if block_name not in self.agent_state.memory.list_block_labels():
                # Create block with default empty content
                block = CreateBlock(
                    label=block_name,
                    value="",
                    limit=50000,  # Generous limit for memory data
                    description=f"Memory {block_name} block"
                )
                # Add block to memory
                # Implementation will use Letta API to create block
    
    def _initialize_database_connection(self) -> sqlalchemy.engine.Engine:
        """Initialize connection to PostgreSQL database."""
        # Implementation will use Letta's database connection utilities
        # Returns database engine
        pass
    
    def _initialize_embedding_models(self) -> Dict[str, Any]:
        """Initialize embedding models for semantic retrieval."""
        # Implementation will set up embedding models using Letta framework
        # Returns dict of model name -> model instance
        pass
    
    def query_memory(self, 
                   query: str, 
                   query_type: Optional[str] = None,
                   memory_tiers: Optional[List[str]] = None,
                   filters: Optional[Dict[str, Any]] = None,
                   k: int = 10) -> Dict[str, Any]:
        """
        Unified memory query interface for retrieving narrative information.
        
        Args:
            query: The narrative query
            query_type: Optional type of query (character, event, theme, relationship)
            memory_tiers: Optional specific memory tiers to query
            filters: Optional filters to apply (time, characters, locations, etc.)
            k: Number of results to return
            
        Returns:
            Dict containing query results and metadata
        """
        # Process query to understand information need
        query_info = self._analyze_query(query, query_type)
        
        # Determine which memory tiers to access if not specified
        if not memory_tiers:
            memory_tiers = self._determine_relevant_memory_tiers(query_info)
        
        # Initialize results container
        all_results = {}
        
        # Query each relevant memory tier
        for tier in memory_tiers:
            tier_info = self.memory_tiers.get(tier)
            if not tier_info:
                continue
                
            if tier_info["type"] == "database":
                # Query structured database
                tier_results = self._query_database(
                    query_info, tier_info["tables"], filters, k)
            elif tier_info["type"] == "vector":
                # Query vector store
                tier_results = self._query_vector_store(
                    query_info, tier_info["collections"], filters, k)
            
            all_results[tier] = tier_results
        
        # Cross-reference and synthesize results
        synthesized_results = self._synthesize_results(all_results, query_info)
        
        # Format final response
        response = {
            "query": query,
            "query_type": query_info["type"],
            "results": synthesized_results,
            "metadata": {
                "sources": memory_tiers,
                "result_count": len(synthesized_results),
                "filters_applied": filters
            }
        }
        
        return response
    
    def _analyze_query(self, query: str, query_type: Optional[str]) -> Dict[str, Any]:
        """Analyze query to understand information need and type."""
        # Implementation will analyze query semantics
        # If query_type not provided, attempt to detect it
        # Returns query info including type, focus, entities, and keywords
        pass
    
    def _determine_relevant_memory_tiers(self, query_info: Dict[str, Any]) -> List[str]:
        """Determine which memory tiers are most relevant for a query."""
        # Implementation will select appropriate tiers based on query type
        # Returns list of relevant tier names
        pass
    
    def _query_database(self, 
                      query_info: Dict[str, Any], 
                      tables: List[str],
                      filters: Optional[Dict[str, Any]],
                      k: int) -> List[Dict[str, Any]]:
        """Query structured database for narrative information."""
        # Implementation will translate narrative query to SQL
        # Execute queries against specified tables
        # Apply any filters
        # Return structured results
        pass
    
    def _query_vector_store(self, 
                          query_info: Dict[str, Any], 
                          collections: List[str],
                          filters: Optional[Dict[str, Any]],
                          k: int) -> List[Dict[str, Any]]:
        """Query vector store for semantically relevant information."""
        # Generate embeddings for query
        query_embeddings = self._generate_embeddings(query_info["query_text"])
        
        # Perform vector search with metadata filtering
        results = self._vector_search(
            query_embeddings, collections, filters, k)
        
        return results
    
    def _vector_search(self,
                     query_embeddings: Dict[str, List[float]],
                     collections: List[str],
                     filters: Optional[Dict[str, Any]],
                     k: int) -> List[Dict[str, Any]]:
        """Perform vector search with metadata filtering."""
        # Implementation will perform vector search across collections
        # Apply metadata filters
        # Return semantic search results
        pass
    
    def _generate_embeddings(self, text: str, models: Optional[List[str]] = None) -> Dict[str, List[float]]:
        """Generate embeddings using multiple models."""
        # Implementation will create embeddings for each specified model
        # Returns dict of model name -> embedding vector
        pass
    
    def _synthesize_results(self, 
                          all_results: Dict[str, List[Dict[str, Any]]], 
                          query_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Synthesize results from multiple sources into unified response."""
        # Implementation will combine and rank results from different tiers
        # Resolve conflicts and duplicates
        # Cross-reference entities with narrative chunks
        # Return unified list of results with source information
        pass
    
    def store_narrative_chunk(self, 
                             chunk_text: str, 
                             metadata: Dict[str, Any]) -> str:
        """
        Store a narrative chunk with embeddings and metadata.
        
        Args:
            chunk_text: The text content of the chunk
            metadata: Associated metadata (characters, locations, time, etc.)
            
        Returns:
            ID of the stored chunk
        """
        # Generate unique ID for chunk
        chunk_id = self._generate_chunk_id(chunk_text, metadata)
        
        # Process text content (clean, format)
        processed_text = self._preprocess_text(chunk_text)
        
        # Generate embeddings using all available models
        embeddings = self._generate_embeddings(processed_text)
        
        # Store chunk in vector database with text, embeddings, and metadata
        self._store_vector_chunk(chunk_id, processed_text, embeddings, metadata)
        
        # Extract and store structured information to PostgreSQL
        self._extract_and_store_structured_data(chunk_id, processed_text, metadata)
        
        return chunk_id
    
    def _generate_chunk_id(self, text: str, metadata: Dict[str, Any]) -> str:
        """Generate a unique ID for a chunk based on content and metadata."""
        # Implementation will create a unique identifier
        pass
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for embedding and storage."""
        # Implementation will clean and format text
        pass
    
    def _store_vector_chunk(self, 
                          chunk_id: str, 
                          text: str, 
                          embeddings: Dict[str, List[float]], 
                          metadata: Dict[str, Any]) -> None:
        """Store a chunk in the vector database with all associated data."""
        # Implementation will store chunk in vector database
        pass
    
    def _extract_and_store_structured_data(self, 
                                        chunk_id: str, 
                                        text: str, 
                                        metadata: Dict[str, Any]) -> None:
        """Extract structured information and store in PostgreSQL."""
        # Implementation will extract entities, relationships, etc.
        # Store extracted data in appropriate database tables
        # Create cross-references between structured data and chunk ID
        pass
    
    def process_deep_query(self, query: str, query_type: str) -> Dict[str, Any]:
        """
        Process a deep narrative query requiring synthesis across multiple sources.
        
        Args:
            query: The narrative query to process
            query_type: Type of query (character, event, theme, relationship)
            
        Returns:
            Dict containing synthesized response and supporting evidence
        """
        # Determine specialized query strategy based on query_type
        query_strategy = self._get_query_strategy(query_type)
        
        # Generate query expansion for more comprehensive results
        expanded_query = self._expand_query(query, query_type)
        
        # Extract relevant entities and keywords from query
        query_info = self._analyze_query(expanded_query, query_type)
        
        # Determine memory tiers to query based on query type
        memory_tiers = query_strategy.get("memory_tiers", 
                                           self._determine_relevant_memory_tiers(query_info))
        
        # Build specialized filters based on query type and extracted info
        filters = self._build_specialized_filters(query_info, query_type)
        
        # Query each tier with specialized parameters
        raw_results = self.query_memory(
            expanded_query, 
            query_type=query_type,
            memory_tiers=memory_tiers,
            filters=filters,
            k=query_strategy.get("k", 20)
        )
        
        # Perform specialized post-processing based on query type
        processed_results = self._post_process_by_query_type(
            raw_results, query_type, query_info)
        
        # Generate synthesized response using LLM with retrieved evidence
        synthesized_response = self._synthesize_response(
            query, processed_results, query_type)
        
        return {
            "query": query,
            "query_type": query_type,
            "response": synthesized_response,
            "supporting_evidence": processed_results["results"][:5],  # Top 5 for brevity
            "metadata": processed_results["metadata"]
        }
    
    def _get_query_strategy(self, query_type: str) -> Dict[str, Any]:
        """Get specialized query strategy for query type."""
        # Implementation will return search parameters for query type
        pass
    
    def _expand_query(self, query: str, query_type: str) -> str:
        """Expand query with additional related terms based on query type."""
        # Implementation will use LLM to expand query
        pass
    
    def _build_specialized_filters(self, query_info: Dict[str, Any], query_type: str) -> Dict[str, Any]:
        """Build specialized filters based on query type and extracted info."""
        # Implementation will create filters appropriate for query type
        pass
    
    def _post_process_by_query_type(self, 
                                  results: Dict[str, Any], 
                                  query_type: str,
                                  query_info: Dict[str, Any]) -> Dict[str, Any]:
        """Apply specialized post-processing based on query type."""
        # Implementation will apply query-specific processing
        pass
    
    def _synthesize_response(self, 
                           query: str, 
                           results: Dict[str, Any],
                           query_type: str) -> str:
        """Generate synthesized narrative response using LLM."""
        # Implementation will use LLM to synthesize coherent response
        pass
    
    def update_entity(self, 
                    entity_type: str, 
                    entity_id: str, 
                    updates: Dict[str, Any]) -> bool:
        """
        Update entity information in structured database.
        
        Args:
            entity_type: Type of entity (character, location, faction, etc.)
            entity_id: ID of entity to update
            updates: Attribute updates to apply
            
        Returns:
            True if update successful, False otherwise
        """
        # Implementation will update entity in database
        # Update any cross-references or indices
        pass
    
    def update_chunk_metadata(self, chunk_id: str, metadata_updates: Dict[str, Any]) -> bool:
        """
        Update metadata for a specific chunk in vector storage.
        
        Args:
            chunk_id: ID of chunk to update
            metadata_updates: Metadata fields and values to update
            
        Returns:
            True if update successful, False otherwise
        """
        # Implementation will update chunk metadata in vector database
        # Update any related structured data if necessary
        pass
    
    def get_memory_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about memory usage across all storage types.
        
        Returns:
            Dict with memory statistics
        """
        # Implementation will collect and return memory statistics
        # Include database and vector storage stats
        # Include usage patterns and performance metrics
        pass
    
    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and perform MEMNON functions.
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

1. **Memory Tier Adaptation**: While maintaining Letta's two-tier approach (Core and Archival), MEMNON implements virtual memory tiers through:
   - Strategic Memory: Implemented as structured database tables for themes, plot arcs, and global state
   - Entity Memory: Implemented as structured database tables for characters, locations, factions, and relationships
   - Chunk Memory: Implemented as vector storage for detailed narrative segments

2. **Unified Access Layer**: MEMNON serves as a single entry point for all memory, handling:
   - Translation between narrative queries and specific database/vector operations
   - Cross-referencing between structured and vector data
   - Result synthesis from multiple storage types
   - Coherent response formatting regardless of source

3. **Multi-Model Embedding Strategy**: For vector storage, the system continues to use multiple embedding models:
   - BGE-Large: Strong general semantic understanding
   - E5-Large: Excels at matching answers to questions
   - BGE-Small (fine-tuned): Domain-specific embeddings for narrative context

4. **Cross-Storage Referencing**: The system maintains explicit connections between:
   - Character profiles in database ↔ Character mentions in narrative chunks
   - Location information in database ↔ Location descriptions in narrative chunks
   - Theme tracking in database ↔ Theme manifestations in narrative chunks

5. **Integration with Other Agents**:
   - Provide unified memory access to LORE for context construction
   - Support PSYCHE with character history and relationship queries
   - Help GAIA with world state and historical entity queries
   - Retrieve relevant context for LOGON through LORE

## Next Steps

1. Implement database schema for structured narrative information
2. Develop unified query interface across storage types
3. Build cross-referencing between structured and vector data
4. Create specialized query processors for different information needs
5. Implement result synthesis mechanisms
6. Test with sample narrative data across storage types 