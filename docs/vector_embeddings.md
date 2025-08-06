# Vector Embeddings in NEXUS

This document describes the vector embedding strategy used in the NEXUS system for semantic search and similarity matching.

## Embedding Models

NEXUS uses a multi-model ensemble approach with weighted combinations of different embedding models:

1. **Extra-Large Model (1536 dimensions)**
   - **inf-retriever-v1-1.5b** (Infly/inf-retriever-v1-1.5b)
   - Weight: 0.5
   - Highest dimensional representation for maximum semantic capture

2. **Large Models (1024 dimensions)**
   - **E5-Large-V2** (intfloat/e5-large-v2) - Weight: 0.3
   - **BGE-Large-EN** (BAAI/bge-large-en) - Weight: 0.2

## Database Storage Strategy

To handle different vector dimensions efficiently, we use a **dimension-specific tables approach**:

1. **chunk_embeddings_1536d**
   - Table for 1536-dimensional vectors (inf-retriever-v1-1.5b)
   - Column type: `embedding Vector(1536)`

2. **chunk_embeddings_1024d**
   - Table for 1024-dimensional vectors (E5-Large-V2, BGE-Large-EN)
   - Column type: `embedding Vector(1024)`

This approach was chosen because pgvector requires fixed dimensions at table creation time, and mixing vectors of different dimensions in the same table would require significant padding and dimensionality management.

## Query Routing System

The `embedding_utils.py` utility provides functions that automatically route queries to the correct table based on the model name:

```python
from scripts.utils.embedding_utils import get_table_for_model

# Will return "chunk_embeddings_1536d"
table = get_table_for_model("inf-retriever-v1-1.5b") 

# Will return "chunk_embeddings_1024d"
table = get_table_for_model("e5-large-v2") 
table = get_table_for_model("bge-large-en")
```

## Implementation Details

### Key Functions

1. `get_model_dimensions(model_name)`: Returns the dimension (1024 or 1536) for a given model
2. `get_table_for_model(model_name)`: Returns the appropriate table name based on dimensions
3. `construct_vector_search_sql(model_name, filter_conditions, limit)`: Builds SQL with the correct table
4. `normalize_vector(vector)`: Normalizes vectors to unit length for better comparison

### Search Process

1. Generate embedding for the query using the specified model
2. Determine the appropriate table based on the model name
3. Execute a similarity search using pgvector's `<=>` operator
4. Return the most similar chunks

## Usage Example

Here's a simple example of performing a semantic search:

```python
from nexus.agents.memnon.memnon import Memnon

# Initialize Memnon (the memory utility)
memnon = Memnon()

# Search using the multi-model ensemble approach
results = memnon.hybrid_search(
    "Alex discovers the artifact",
    limit=5
)

# Or search with a specific model
inf_results = memnon.vector_search(
    "Alex discovers the artifact",
    model="inf-retriever-v1-1.5b",
    limit=5
)

e5_results = memnon.vector_search(
    "Alex discovers the artifact", 
    model="e5-large-v2",
    limit=5
)
```

## Validation Tools

Use the `validate_embeddings.py` script to verify that both tables are functioning correctly:

```bash
python scripts/validate_embeddings.py
```

This will:
1. Count embeddings in each table by model
2. Perform a simple vector similarity search with each model type
3. Validate that the appropriate table is being used for each model

## Testing

The `test_embedding_utils.py` script allows testing the table selection logic:

```bash
python scripts/test_embedding_utils.py
```

## Hybrid Search Capabilities

MEMNON implements sophisticated hybrid search combining:
- **Multi-model vector similarity**: Weighted ensemble of inf-retriever-v1-1.5b, E5-Large-V2, and BGE-Large-EN
- **PostgreSQL full-text search**: For keyword matching
- **Cross-encoder reranking**: Using Naver TREC-DL22 model for final result refinement
- **Temporal boosting**: Time-aware search for queries with temporal context
- **Query-type-specific weighting**: Different strategies for different query types

## Future Considerations

The current multi-model ensemble approach provides excellent semantic coverage. Potential enhancements include:

1. **Dynamic model weighting**: Adjusting weights based on query characteristics
2. **Additional specialized models**: Task-specific embeddings for different narrative aspects
3. **Hybrid dimensionality reduction**: Combining models at different dimensional scales

The dimension-specific tables approach provides optimal performance while maintaining flexibility for future model additions.