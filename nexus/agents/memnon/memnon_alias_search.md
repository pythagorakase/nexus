# MEMNON Alias-Aware Vector Search Implementation

This document summarizes the implementation of alias-aware search in MEMNON that handles character equivalence, particularly for "You" and "Alex" second-person POV references.

## Overview

The implementation performs two key functions:

1. **Alias Detection**: Identifies when queries contain character references like "your" or "you" and expands these to include all character aliases
2. **Hybrid Search**: Combines vector search with text search, with special handling for queries containing character references

## Components

### 1. Alias Management

```python
def alias_terms(query: str, alias_lookup: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Extract character alias terms from a query."""
    # Special case for possessive forms like "your" -> "Alex"
    if any(term in lowered_query for term in ["your", "yours", "yourself"]):
        # Add Alex and all her aliases when "your" is detected
        if "alex" in alias_lookup:
            all_aliases.extend(alias_lookup["alex"])
    
    # Look for character names in the query
    for name, variants in alias_lookup.items():
        # Check for the name or any of its aliases in the query
        if re.search(name_pattern, lowered_query) or any(re.search(pattern, lowered_query) for pattern in variant_patterns):
            all_aliases.extend(variants)
```

### 2. Database Integration

The implementation loads character aliases from the PostgreSQL database:

```python
def load_aliases_from_db(conn) -> Dict[str, List[str]]:
    """Load character aliases from the database."""
    # Query all characters with aliases from the database
    result = conn.execute(text("""
        SELECT name, aliases 
        FROM characters 
        WHERE aliases IS NOT NULL AND array_length(aliases, 1) > 0
    """))
    
    # Special handling for Alex/You equivalence
    if "alex" in alias_lookup and "You" not in alias_lookup["alex"]:
        alias_lookup["alex"].append("You")
```

### 3. Hybrid Search SQL

The implementation uses a hybrid approach combining text search with vector search:

```sql
WITH text_search AS (
    -- Pre-filter with text search
    SELECT c.id,
           ts_rank_cd(to_tsvector('english', c.raw_text), plainto_tsquery('english', :raw_query)) AS text_score
    FROM narrative_chunks c
    WHERE to_tsvector('english', c.raw_text) @@ plainto_tsquery('english', :raw_query)
    ORDER BY text_score DESC
    LIMIT 500
)
SELECT c.id,
       c.raw_text,
       :model_name AS model,
       (ce.embedding <=> :query_vector) AS distance,
       ts.text_score,
       m.season, m.episode, m.scene, m.world_layer, 
       m.characters, m.place, m.atmosphere, m.time_delta
FROM chunk_embeddings_1024d ce
JOIN narrative_chunks c ON ce.chunk_id = c.id
JOIN text_search ts ON c.id = ts.id
LEFT JOIN chunk_metadata m ON c.id = m.chunk_id
WHERE ce.model = :model_name
ORDER BY (
    -- Combine vector distance and text score
    -- If any character in aliases appears in raw text, boost the score
    CASE WHEN c.raw_text ILIKE '%' || :alias_0 || '%' OR c.raw_text ILIKE '%' || :alias_1 || '%' ...
        THEN (ce.embedding <=> :query_vector) * 0.7 + ts.text_score * 0.3
        ELSE (ce.embedding <=> :query_vector) * 0.9 + ts.text_score * 0.1
    END
)
LIMIT :limit;
```

## Character Format Support

The implementation handles multiple character reference formats:

1. Direct text mentions: "You said something" finds chunks with "Alex said something"
2. Character metadata: Where characters are stored in the format "Alex:present" in the `chunk_metadata.characters` array
3. Possessive forms: "your thoughts" connects to "Alex's thoughts"

## Integration with MEMNON

To integrate with the main MEMNON agent, add these functions to the memnon.py file to enable alias-aware search by default when querying for information.

## Usage Example

```python
# Initialize MEMNON with alias-aware search
result = memnon.query_memory(
    "What did you say to Emilia about your gender?",
    use_alias_awareness=True
)

# This query will find chunks where:
# - Alex (not just "You") speaks to Emilia
# - Alex mentions gender transition
# - Possessive statements about Alex's identity
```

By leveraging alias awareness, MEMNON can now understand the equivalence between "Alex" and "You" in second-person narrative, improving retrieval accuracy for context-dependent queries about the protagonist.