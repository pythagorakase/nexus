# Time-Aware Embeddings for MEMNON

This module enhances MEMNON's retrieval capabilities by adding time-awareness to the search functionality. It helps improve results for queries that have temporal aspects like "first meeting", "earliest event", or "latest developments".

## Features

- **Temporal Query Classification**: Automatically detects if a query has temporal aspects related to early or recent events
- **Temporal Position Calculation**: Normalizes chunk positions in the narrative timeline
- **Score Adjustment**: Boosts search results based on temporal relevance to the query
- **Seamless Integration**: Works alongside existing vector and text search mechanisms

## Configuration

The temporal search functionality can be configured in `settings.json`:

```json
"hybrid_search": {
    "enabled": true,
    "vector_weight_default": 0.6,
    "text_weight_default": 0.4,
    "temporal_boost_factor": 0.5
}
```

The `temporal_boost_factor` controls how much influence temporal position has on the final score:
- 0.0: No temporal influence (falls back to standard hybrid search)
- 1.0: Maximum temporal influence (time position dominates the score)
- 0.5: Balanced approach (recommended starting point)

## How It Works

1. **Query Classification**:
   - Analyzes the query text for temporal patterns
   - Classifies queries as "early", "recent", or "non_temporal"
   - Early patterns: "first", "beginning", "initial", "start", etc.
   - Recent patterns: "latest", "current", "recent", "now", etc.

2. **Normalization**:
   - Converts chunk IDs into a normalized 0-1 temporal position
   - 0.0 represents the earliest chunk in the narrative
   - 1.0 represents the most recent chunk

3. **Temporal Boost**:
   - For "early" queries: Boosts chunks with lower temporal positions (earlier in the narrative)
   - For "recent" queries: Boosts chunks with higher temporal positions (later in the narrative)
   - Blends semantic/text relevance with temporal position using the temporal_boost_factor

4. **Result Reranking**:
   - Reranks search results based on adjusted scores
   - Returns the top results considering both semantic and temporal relevance

## Testing

You can test the temporal search functionality using the provided test script:

```bash
./test_temporal_search.sh
```

Options:
- `--boost-factor VALUE`: Set the temporal boost factor (default: 0.5)
- `--early-query QUERY`: Test with a specific early temporal query
- `--recent-query QUERY`: Test with a specific recent temporal query
- `--classification-only`: Only test the classification functionality

## Examples

### Early Temporal Queries

- "What was the first encounter between Alex and Emilia?"
- "How did the story begin?"
- "Tell me about the initial meeting with Dr. Nyati"
- "What are the origins of the cybernetics program?"

### Recent Temporal Queries

- "What's the current status of the project?"
- "What has Alex been doing recently?"
- "Tell me about the latest developments with Emilia"
- "What's happening now with the cybernetics program?"

## Future Improvements

Possible enhancements for the future:

1. **Learning-Based Classification**: Train a classifier to improve temporal query detection
2. **Adaptive Boost Factor**: Adjust temporal boost factor based on query confidence
3. **Middle-Period Queries**: Support queries targeting the middle of the narrative
4. **Explicit Time References**: Parse and handle specific time references (dates, episodes, etc.)
5. **User Feedback Integration**: Learn from user interactions to improve temporal boosts