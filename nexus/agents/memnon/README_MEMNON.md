# MEMNON Agent Documentation

## Overview

The MEMNON agent serves as the Unified Memory Access System within the NEXUS narrative intelligence framework. Its primary responsibility is **high-quality information retrieval**. It does **not** perform narrative synthesis or generate creative text; that role belongs to other agents like LORE.

MEMNON focuses on:

*   **Storing Narrative Data:** Ingesting narrative text (e.g., from scripts), chunking it based on scene breaks, generating embeddings using multiple configured models, and storing chunks, metadata (season, episode, scene, etc.), and embeddings in a PostgreSQL database.
*   **Storing Structured Data:** Managing database tables for structured entities like Characters and Places.
*   **Multi-Strategy Retrieval:** Accepting natural language queries and executing a combination of search strategies to find relevant information:
    *   **Vector Search:** Comparing query embeddings against chunk embeddings using pgvector.
    *   **Text Search:** Performing keyword-based searches (SQL `ILIKE`) on chunk text.
    *   **Structured Data Search:** Querying specific database tables (e.g., `characters`, `places`) based on entities identified in the query.
*   **Score Normalization & Weighting:** Adjusting raw scores from different retrieval sources (vector, text, structured) and embedding models based on configurable normalization rules and weights to produce a unified relevance ranking.
*   **Embedding Management:** Using the `EmbeddingManager` utility to handle interactions with various embedding models (local or API-based).

## Key Components & Logic

*   **Modular Architecture:** MEMNON has been refactored into a modular architecture with specialized utility classes:
    *   **EmbeddingManager:** Handles embedding model lifecycle and vector generation
    *   **SearchManager:** Coordinates different search strategies across data sources
    *   **QueryAnalyzer:** Analyzes user queries to determine optimal search approach
    *   **DatabaseManager:** Provides database connection and schema management
    *   **ContentProcessor:** Manages content chunking, processing, and storage
*   **Database Schema:** Uses SQLAlchemy ORM models (`NarrativeChunk`, `ChunkEmbedding`, `ChunkMetadata`, `Character`, `Place`) to interact with the PostgreSQL database.
*   **`settings.json`:** Configuration for database connection, embedding models (endpoints, weights), logging, import parameters (file patterns, chunking regex), and retrieval settings (result limits, thresholds, weights) are loaded from the main `settings.json` file under `Agent Settings -> MEMNON`.
*   **Content Processing:** The `ContentProcessor` class handles reading a file, identifying chunks via regex, generating embeddings for each configured model, and storing the chunk, metadata, and embeddings in the database.
*   **Query Analysis:** The `QueryAnalyzer` class performs analysis of incoming queries to determine the likely query type (e.g., character, location, event) and extract keywords and potential entities (characters, places) by matching against database entries.
*   **Search Strategies:** The `SearchManager` class implements and orchestrates different search strategies including vector search, text search, and structured data queries.
*   **`query_memory()`:** The main entry point for retrieval. It orchestrates the query analysis, strategy selection, execution of individual search methods, score normalization/weighting, deduplication, and final ranking.
*   **`step()`:** The standard agent interface method. It parses incoming user messages, checks for simple commands (`process files`, `status`), and otherwise passes the message text to `query_memory()` for retrieval. It returns a dictionary containing the results and metadata.

## Usage

### Initialization

MEMNON can be initialized like other Letta agents or directly:

```python
from nexus.agents.memnon.memnon import MEMNON
# Assuming an interface object 'interface' exists
# Direct Mode (e.g., for scripting or testing)
memnon_agent = MEMNON(interface=interface, direct_mode=True) 

# Letta Framework Mode (agent_state provided)
# memnon_agent = MEMNON(interface=interface, agent_state=agent_state_object) 
```

### Processing Narrative Files

Use the `process_all_narrative_files()` method or the `process files` command via the `step()` method:

```python
# Method call (direct mode example)
total_chunks = memnon_agent.process_all_narrative_files(glob_pattern="path/to/your/narrative/*.md", limit=10)
print(f"Processed {total_chunks} chunks.")

# Command via step() (Letta mode example, assuming 'messages' list)
messages.append(Message(role="user", content="process files pattern **/scripts/*.md"))
response = memnon_agent.step(messages) 
print(response) # Output: {'status': 'Processing initiated...'} 
```

### Querying Memory

Use the `query_memory()` method or send a query message via the `step()` method:

```python
# Method call (direct mode example)
query = "What happened to Alex in the old warehouse?"
results_dict = memnon_agent.query_memory(query=query, k=5)
print(json.dumps(results_dict, indent=2))

# Query via step() (Letta mode example)
messages.append(Message(role="user", content="Tell me about the character named Silas."))
response = memnon_agent.step(messages)
print(json.dumps(response, indent=2)) # Returns results dictionary
```

### Checking Status

Use the `_get_status()` method or the `status` command via the `step()` method:

```python
# Method call (direct mode example)
status_string = memnon_agent._get_status()
print(status_string)

# Command via step() (Letta mode example)
messages.append(Message(role="user", content="status"))
response = memnon_agent.step(messages)
print(response) # Output: {'status': 'MEMNON Status:\n...'}
```

### Interactive Mode (Command Line)

The script can be run with an `--interactive` flag for rapid querying:

```bash
python nexus/agents/memnon/memnon.py --interactive
```

This will start a loop prompting for queries. Type your query and press Enter. The results dictionary will be printed. Type `quit` to exit. 