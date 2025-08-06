# Hybrid Search in MEMNON

## Overview

The hybrid search feature combines vector-based semantic search with traditional text-based search to provide improved retrieval performance for narrative content. By integrating PostgreSQL's full-text search capabilities (GIN indexes and tsvector) with vector similarity search, MEMNON can now find relevant content more effectively, especially for queries that combine conceptual understanding with specific keywords.

## Key Features

- **Combined Scoring**: Results are scored using a weighted combination of vector similarity and text match relevance
- **Query-Type Aware**: Weight balance adapts automatically based on query type (character, event, theme, etc.)
- **Configurable Weights**: All weights can be adjusted in `settings.json`
- **Performance Optimized**: Uses PostgreSQL's native capabilities for efficient combined search

## Technical Implementation

Hybrid search is implemented through:

1. A PostgreSQL GIN index on narrative content using `to_tsvector('english', raw_text)`
2. A custom SQL function (`hybrid_search`) that performs both searches in parallel
3. Integration with MEMNON's existing search infrastructure

## Configuration

All hybrid search parameters are configurable in `settings.json`:

```json
"hybrid_search": {
    "enabled": true,
    "vector_weight_default": 0.7,
    "text_weight_default": 0.3,
    "weights_by_query_type": {
        "character": { "vector": 0.8, "text": 0.2 },
        "relationship": { "vector": 0.8, "text": 0.2 },
        "event": { "vector": 0.6, "text": 0.4 },
        "location": { "vector": 0.7, "text": 0.3 },
        "theme": { "vector": 0.75, "text": 0.25 },
        "general": { "vector": 0.7, "text": 0.3 }
    },
    "use_query_type_weights": true,
    "target_model": "inf-retriever-v1-1.5b"
}
```

### Configuration Parameters

- **enabled**: Enable or disable hybrid search (if disabled, falls back to vector search only)
- **vector_weight_default**: Default weight for vector similarity scores (0-1)
- **text_weight_default**: Default weight for text match scores (0-1)
- **weights_by_query_type**: Specific weights for different query types
- **use_query_type_weights**: Whether to use query-specific weights or just the defaults
- **target_model**: Which embedding model to use for the vector portion

## Usage

Hybrid search is automatically used when enabled - no special commands are required. The system will:

1. Determine query type using LLM analysis
2. Select appropriate weights based on query type
3. Run combined search and merge results
4. Sort by combined score

## Testing

You can test hybrid search performance with the command:

```
test hybrid search
```

This will run several test queries and compare results between hybrid search and standard vector search.

To specify your own test queries:

```
test hybrid search queries: ["Neural implant malfunction", "Meeting in corporate district"]
```

## Performance Considerations

The GIN index creation takes time for large databases but only needs to be done once. The hybrid search combines the strengths of both methods:

- Vector search excels at understanding conceptual meaning
- Text search excels at finding specific keywords and phrases

Together, they provide more robust and relevant results across a wider range of query types.

## Troubleshooting

If hybrid search is not working:

1. Check the status with the command: `status`
2. Verify PostgreSQL extensions and indexes are properly created
3. Check logs for any errors during initialization
4. Ensure `pgvector` extension is enabled in PostgreSQL 