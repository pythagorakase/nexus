# MEMNON - Narrative Memory and Vector Search for NEXUS

MEMNON is a specialized agent within the NEXUS ecosystem responsible for storing, indexing, and retrieving narrative content using advanced vector embeddings and natural language processing. It serves as the "memory" component of the system, allowing for intelligent semantic search and retrieval of narrative information through natural language queries.

## Latest Updates

- **LLM-Directed Search**: Added intelligent search planning using LLM to determine optimal search strategies
- **Multi-Strategy Search**: Implemented tiered search with structured data, vector search, and text search options
- **Relevance Validation**: Added automatic validation and result re-ranking based on query relevance
- **Improved Sullivan Search**: Fixed reliability issues with character references and improved retrieval
- **Letta Integration**: MEMNON is now fully integrated with the Letta framework
- **Natural Language Querying**: Added support for natural language queries with LLM-based analysis
- **Cross-Referenced Results**: Implemented unified querying across structured database and vector embeddings

## Features

- **Triple-Embedding Strategy**: Each narrative chunk is embedded using three different models:
  - BGE-Large: For general semantic understanding (1024 dimensions)
  - E5-Large: Optimized for question-answer matching (1024 dimensions)
  - BGE-Small-Custom: Fine-tuned model specific to the narrative domain (384 dimensions)

- **Hybrid Search**: Combines structured database queries with vector semantic search

- **Local LLM Integration**: Uses local LLM (via LM Studio) for query analysis and response synthesis

- **Cross-Referencing**: Relates narrative chunks to character and location entities

- **Configurable Query Types**: Specialized handling for different query types:
  - Character queries: "Tell me about Alex's motivations"
  - Location queries: "What happened at the warehouse district?"
  - Event queries: "What occurred when the power went out?"
  - Theme queries: "How does transhumanism appear in the narrative?"
  - Relationship queries: "Describe the relationship between Alex and Victor"

## Setup

### Prerequisites

- PostgreSQL with pgvector extension
- Python 3.9+
- Local LLM running via LM Studio (default port: 1234)
- Required Python packages:
  ```bash
  poetry install
  ```

### Installation

1. **Install pgvector extension**:
   ```bash
   cd /Users/pythagor/nexus
   ./scripts/install_pgvector.sh
   ```

2. **Configure Settings**:
   All MEMNON settings are stored in the central `settings.json` file under the `Agent Settings.MEMNON` section. These include:
   - Database connection settings
   - Embedding model configurations and paths
   - LLM parameters (model, temperature, API endpoints)
   - Import and query parameters
   - Retrieval settings (weights, boost factors)
   - Logging preferences

3. **Start Local LLM**:
   Launch LM Studio and start a local server with the model defined in settings.json (default: `llama-3.3-70b-instruct@q6_k`)

## Usage

### Running MEMNON Interactively

The MEMNON agent can be run interactively in one of two ways:

#### Option 1: Direct Mode (Recommended)

For the most reliable experience, use the standalone direct mode runner:

```bash
cd /Users/pythagor/nexus
poetry run python run_memnon.py
```

This bypasses the Letta framework integration and runs MEMNON in direct mode with a simple interactive interface. It supports:

- Natural language queries
- Raw vector search with `raw <query>` for faster results without LLM
- Status checks with `status`
- LLM API testing with `test_llm`

#### Option 2: Letta CLI Integration (Advanced)

For full Letta framework integration (requires more setup):

```bash
cd /Users/pythagor/nexus
poetry run python -m letta.cli cli --agent memnon --interactive
```

This launches MEMNON in interactive mode with full Letta framework integration, allowing you to query the narrative memory using natural language.

### Example Queries

You can ask MEMNON various types of questions:

```
> Tell me about Alex's character
> What happened in Season 2 Episode 3?
> Describe the relationship between Alex and Victor
> What are the major events at the Spire?
> How does the theme of betrayal manifest in Season 1?
```

MEMNON will:
1. Analyze the query to determine its type
2. Search the relevant memory tiers (database and/or vector)
3. Cross-reference results between entities and narrative chunks
4. Generate a synthesized response using the local LLM

### Special Commands

MEMNON in direct mode supports these commands:

```
> status
```
Displays status information including database statistics, loaded embedding models, etc.

```
> raw What happened at the warehouse?
```
Performs a query without using the LLM for response synthesis. This is much faster, especially if the LLM is still loading.

```
> test_llm
```
Tests the connection to the LLM API to verify model availability and loading status.

```
> process_files pattern=ALEX_*.md
```
Processes narrative files matching the specified pattern, extracting chunks and generating embeddings.

### Performance Tips

For best performance with MEMNON:

1. **LLM Loading Time**: The first query will take longer as the LLM loads into memory (can be 5+ minutes for 70B models).

2. **Use Raw Queries First**: While the LLM is loading, use `raw <query>` to get immediate results.

3. **Check LLM Status**: Use `test_llm` to verify when the LLM is fully loaded and ready.

4. **Timeout Settings**: The system waits up to 3 minutes for LLM responses. If queries time out, try again later when the model is fully loaded.

5. **Monitor LM Studio**: Keep the LM Studio application open to see loading progress and errors.

## Database Schema

MEMNON uses the following database tables:

1. **narrative_chunks**: Stores the raw text content of each narrative chunk
   - `id`: BigInteger primary key
   - `raw_text`: The full text content of the chunk
   - `created_at`: Timestamp

2. **chunk_embeddings**: Stores embeddings for all models
   - `id`: BigInteger primary key
   - `chunk_id`: Foreign key to narrative_chunks.id
   - `model`: Name of the embedding model
   - `embedding`: Vector representation
   - `dimensions`: Size of the embedding vector (1024 or 384)
   - `created_at`: Timestamp

3. **chunk_metadata**: Stores structured metadata about each narrative chunk
   - Many fields including season, episode, world_layer, time_delta, etc.
   - JSON fields for characters, thematic_elements, etc.

4. **characters**: Stores character information
   - Character attributes like name, aliases, background, etc.

5. **places**: Stores location information
   - Location attributes like name, type, description, etc.

## Implementation Details

### Multi-Tier Memory Architecture

MEMNON implements a multi-tier memory architecture:
- **Strategic Tier**: Database tables for themes, events, and global state
- **Entity Tier**: Database tables for characters, places, factions, and relationships
- **Narrative Tier**: Vector embeddings for narrative chunks

### LLM-Directed Search

MEMNON now uses an LLM to intelligently plan the search strategy for each query:

1. **Query Analysis**: Extracts entities, keywords, and determines query type
2. **Search Planning**: Uses the LLM to generate a customized search plan based on query characteristics
3. **Execution Strategy**: Decides which search methods to use and in what order:
   - Structured data lookup (database tables)
   - Vector similarity search (semantic meaning)
   - Direct text search (keyword matching)
4. **Result Validation**: Validates and re-ranks results based on relevance to the query

The search planning prompt asks the LLM to consider:
- Which data sources are most likely to contain the requested information
- What order of operations would be most efficient
- Whether simpler searches should be tried before more complex ones
- How to combine results from different search methods

The result is a dynamic JSON-formatted search plan that tailors the search approach to each specific query.

### Unified Query Interface

The `query_memory` method provides a unified interface for querying all memory tiers:
```python
results = memnon.query_memory(
    query="What happened when Alex confronted Victor?",
    query_type="event",  # Optional - will be determined automatically if not provided
    filters={"season": 2},  # Optional filters
    k=10  # Number of results to return
)
```

The returned results include search metadata:
```python
{
    "query": "original query",
    "query_type": "detected query type",
    "results": [...],  # List of matching items
    "metadata": {
        "search_plan": "LLM-generated search plan explanation",
        "search_stats": {
            "strategies_executed": ["structured_data", "vector_search", "text_search"],
            "strategy_stats": {...},  # Performance stats for each strategy
            "total_time": 1.25,  # Total search time in seconds
            "total_results": 12  # Number of results found
        }
    }
}
```

### Query Analysis

MEMNON uses both pattern matching and LLM-based analysis to understand queries:
1. Detects query type (character, location, event, theme, relationship)
2. Extracts relevant entities (characters, places, time references)
3. Determines which memory tiers to search
4. Applies appropriate filters and boost factors

### Cross-Referencing

Results from different memory tiers are cross-referenced to create a coherent response:
- Characters mentioned in narrative chunks
- Places described in narrative scenes
- Events involving specific characters
- Relationships depicted in interactions

### LLM Integration

MEMNON uses a local LLM for:
1. Query classification and understanding
2. Response synthesis and generation
3. Natural language explanation of complex results

## Configuring MEMNON

Key configuration sections in `settings.json`:

```json
"MEMNON": {
    "debug": true,
    "database": {
        "url": "postgresql://user@localhost/NEXUS"
    },
    "models": {
        "bge-large": {
            "local_path": "/path/to/model",
            "weight": 0.4
        },
        "e5-large": {
            "local_path": "/path/to/model",
            "weight": 0.4
        },
        "bge-small-custom": {
            "local_path": "/path/to/model",
            "weight": 0.2
        }
    },
    "llm": {
        "api_base": "http://localhost:1234",
        "temperature": 0.2,
        "system_prompt": "You are MEMNON..."
    },
    "retrieval": {
        "entity_boost_factor": 1.2,
        "recency_boost_factor": 1.1
    }
}
```

## Troubleshooting

### LLM Connection Issues

If you encounter LLM connection issues:
1. Ensure LM Studio is running with the API server enabled
2. Verify the API endpoint in settings.json (default: http://localhost:1234)
3. Check that the model specified in settings.json is loaded in LM Studio 
4. For large models (70B), allow 5-10 minutes for full model loading
5. Use `test_llm` command to check connection status
6. Try using `raw <query>` while the model is still loading
7. If LM Studio shows the model is loaded but queries timeout, restart LM Studio

### Embedding Model Issues

If embedding models fail to load:
1. Check the paths in settings.json to ensure they point to valid model directories
2. Verify the models have been downloaded or installed correctly
3. Run with debug enabled to see detailed error messages

### Database Issues

For database connection issues:
1. Verify your PostgreSQL credentials and database name (NEXUS, not nexus)
2. Ensure pgvector extension is installed
3. Check if tables exist with `\dt` command in psql

## Next Steps

1. Add advanced entity extraction using Named Entity Recognition (NER)
2. Implement hierarchical memory compression for long-term storage
3. Add specialized query templates for complex narrative analysis
4. Develop continuous learning capabilities to improve over time
5. Implement collaborative multi-agent memory sharing

## Implementation Status (April 2025)

1. ✅ **Database Integration**: Successfully connected to PostgreSQL with pgvector extension
2. ✅ **Triple-Model Embedding**: Implemented BGE-large, E5-large, and BGE-small-custom models
3. ✅ **Letta Integration**: Core functionality integrated with Letta framework
4. ✅ **Direct Mode**: Added standalone mode that bypasses Letta initialization
5. ✅ **Local LLM Support**: Added integration with LM Studio for local LLM inference
6. ✅ **Unified Query Interface**: Combined structured and vector retrieval with cross-referencing
7. ✅ **Run Scripts**: Created `run_memnon.py` and `run_memnon_debug.py` for interactive usage and testing
8. ✅ **Natural Language Querying**: Implemented query analysis and natural language responses
9. ✅ **LLM-Directed Search**: Added intelligent search planning using LLM reasoning
10. ✅ **Multi-Strategy Search**: Implemented structured data, vector, and text search capabilities
11. ✅ **Result Validation**: Added automatic result validation and relevance scoring
12. ✅ **Sullivan Search Fix**: Resolved search issues for specific character references
13. ✅ **Documentation**: Updated README_MEMNON.md with usage instructions and troubleshooting

Known Limitations:
- Long loading times for large LLMs (70B+)
- Limited NER capabilities for entity extraction
- LLM search planning adds latency to queries (1-2 seconds)
- High memory usage when all three embedding models are loaded concurrently