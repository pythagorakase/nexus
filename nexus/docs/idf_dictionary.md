# IDF Dictionary for Enhanced Text Search

## Overview

The IDF (Inverse Document Frequency) Dictionary enhances MEMNON's text search capabilities by weighting terms based on their rarity across the document collection. This enables rare terms like "gender" to have higher importance than common terms like character names when searching.

## How It Works

1. **Term Frequency Analysis**: The system analyzes all narrative chunks to count how often each term appears
2. **IDF Calculation**: For each term, calculates IDF score using the formula: `log(total_documents / documents_containing_term)`
3. **Weight Classification**: Terms are assigned weight classes (A-D) based on their IDF values:
   - Class A (IDF > 2.5): Very rare terms
   - Class B (IDF > 2.0): Rare terms
   - Class C (IDF > 1.0): Uncommon terms
   - Class D (IDF ≤ 1.0): Common terms
4. **Weighted Queries**: Search queries are transformed into weighted PostgreSQL queries using these classifications

## Key Benefits

1. **Improved Relevance**: Rare but important terms have higher impact on search results
2. **Better Context Understanding**: Terms related to narrative themes and events are prioritized over common names
3. **Reduced Noise**: Common terms (like frequently mentioned character names) don't overwhelm search results

## Implementation Details

The IDF Dictionary is implemented as a standalone module with caching for performance:

1. On initialization, the system either:
   - Loads the dictionary from cache if less than 24 hours old
   - Rebuilds the dictionary from the database if cache is stale or missing
   
2. For queries, the system:
   - Processes each term in the query
   - Assigns weight classes (A-D) to each term
   - Constructs a weighted tsquery string (e.g., "gender:A & alex:D")
   - Uses this weighted query with PostgreSQL's text search

3. Performance considerations:
   - Dictionary is cached to disk and only rebuilt when necessary
   - Only executed once during initialization
   - Minimal memory footprint with efficient key-value storage

## Example

For a query "gender identity neural implant alex":

```
Original query: "gender identity neural implant alex"
Weighted query: "gender:A & identity:B & neural:B & implant:B & alex:D"
```

The PostgreSQL text search engine will now give higher weight to matches containing the rare terms "gender", "identity", "neural", and "implant" than to matches containing just the common character name "alex".

## Testing

You can test the IDF dictionary with the provided test script:

```bash
python test_idf_dictionary.py --query "gender identity neural implant alex" --terms gender alex
```

This will show the IDF values for specific terms and demonstrate the query weighting process.

## Integration with Hybrid Search

The IDF dictionary seamlessly integrates with MEMNON's hybrid search system:

1. During MEMNON initialization, the IDF dictionary is created and loaded
2. When performing hybrid searches, the dictionary is passed to the search function
3. The search function uses the weighted query format when available
4. Both text search and vector similarity scores are combined for final ranking

With this feature, MEMNON's search capabilities are significantly enhanced for narrative contexts where rare terms often carry more meaningful information than frequently mentioned names or common words.

---

## Note for ClaudeCode

The IDF Dictionary implementation has been completed with the following files:

1. `nexus/agents/memnon/utils/idf_dictionary.py` - The core implementation
2. `nexus/agents/memnon/test_idf_dictionary.py` - Test script for validation
3. Updates to `memnon.py` and `db_access.py` for integration

The implementation uses PostgreSQL's `ts_stat` function to efficiently calculate term frequencies across all narrative chunks. The dictionary is cached to a file (in `~/.cache/nexus/` by default) to avoid recalculation on every startup.

Key implementation decisions:
- Using weight classes (A-D) to leverage PostgreSQL's built-in weighting system
- Using `&` (AND) operator in weighted queries for precision instead of `|` (OR)
- Smart fallback to standard OR-based search when IDF dictionary isn't available
- Cache refreshes after 24 hours to account for corpus changes

Potential improvements:
1. Add stemming to normalize similar terms (using a library like NLTK or Snowball)
2. Tune weight class thresholds based on corpus statistics
3. Add specialized domain-specific stopwords list
4. Consider query expansion for rare terms with few results
5. Add option to preserve the original query structure (AND/OR logic)

Let me know if you have any feedback on the implementation! 