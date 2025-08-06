# Vector Embedding Management in NEXUS

## Overview

This document describes the implementation details of how we manage multiple vector dimensions in our embedding system. 

## Approach Summary

After investigation, we decided to keep the vector embeddings in separate tables based on their dimensions:

1. **chunk_embeddings**: Table for 1024-dimensional vectors (BGE-Large, E5-Large)
2. **chunk_embeddings_small**: Table for 384-dimensional vectors (BGE-Small-Custom)

This approach works better with PostgreSQL's pgvector extension, which requires fixed dimensions at table creation time.

## Key Components

### 1. Embedding Utility Functions (`embedding_utils.py`)

A set of utility functions that automatically select the correct table based on the model name:

```python
def get_model_dimensions(model_name: str) -> int:
    """Get vector dimensions for a model (384 or 1024)"""
    
def get_table_for_model(model_name: str) -> str:
    """Get appropriate database table for a model"""
    
def construct_vector_search_sql(model_name: str, filter_conditions: str = None, limit: int = 10) -> Tuple[str, str]:
    """Build SQL query for vector search with the right table"""
    
def normalize_vector(vector: Union[List[float], np.ndarray]) -> np.ndarray:
    """Normalize vector to unit length for better comparison"""
```

### 2. Updated Query Script (`query_narratives_vector.py`)

Modified to use the utility functions for routing searches to the correct table:

```python
# Use embedding utilities to select the correct table
if EMBEDDING_UTILS_AVAILABLE:
    embedding_table = get_table_for_model(model)
    dimensions = get_model_dimensions(model)
else:
    # Fallback logic if utilities aren't available
    if model.startswith("bge-small"):
        embedding_table = "chunk_embeddings_small"
        dimensions = 384
    else:
        embedding_table = "chunk_embeddings"
        dimensions = 1024
```

### 3. Validation Scripts

Two scripts to test and validate the embedding system:

- `validate_embeddings.py`: Checks both tables are correctly storing embeddings
- `test_embedding_utils.py`: Tests the table selection and routing logic 
- `test_vector_search.py`: Runs test queries with different models

## Usage Examples

### Basic Semantic Search

```python
from scripts.query_narratives_vector import NarrativeSearcher

# Initialize the searcher
searcher = NarrativeSearcher()

# Search with large model (will use chunk_embeddings table)
large_results = searcher.semantic_search(
    "What did Alex discover in the temple?",
    model="bge-large",
    limit=5
)

# Search with small model (will use chunk_embeddings_small table)
small_results = searcher.semantic_search(
    "What did Alex discover in the temple?",
    model="bge-small-custom",
    limit=5
)
```

### Directly Using Utility Functions

```python
from scripts.utils.embedding_utils import get_table_for_model, construct_vector_search_sql

# Get table name
table = get_table_for_model("bge-small-custom")  # Returns "chunk_embeddings_small"

# Build SQL query
sql, used_table = construct_vector_search_sql(
    model_name="bge-large",
    filter_conditions="metadata.characters LIKE '%Alex%'",
    limit=10
)
```

## Testing

Run the test scripts to verify the system is working:

```bash
# Test embedding utility functions
python scripts/test_embedding_utils.py

# Validate embedding tables
python scripts/validate_embeddings.py

# Run test queries
python scripts/test_vector_search.py --query "How did Alex react to the discovery?"
```

## Documentation

See `docs/vector_embeddings.md` for detailed documentation on the embedding strategy.