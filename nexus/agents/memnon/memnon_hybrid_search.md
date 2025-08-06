# AI Prompt: Implementing Hybrid Vector-BM25 Search in MEMNON

This prompt will guide you through integrating PostgreSQL's tsvector-based keyword search with your existing vector embeddings in MEMNON, creating a powerful hybrid search system.

## Create Database Extensions and Indexes

First, add the required SQL schema changes:

```python
def setup_hybrid_search(self):
    """Set up the database for hybrid search capabilities."""
    with self.engine.connect() as connection:
        # Create GIN index for text search if it doesn't exist
        connection.execute(text("""
        CREATE INDEX IF NOT EXISTS chunks_text_search_idx 
        ON chunks USING GIN (to_tsvector('english', text));
        """))
        
        # Create the hybrid search function
        connection.execute(text("""
        CREATE OR REPLACE FUNCTION hybrid_search(query_text TEXT, query_embedding VECTOR, k INTEGER) 
        RETURNS TABLE (
            id INTEGER,
            text TEXT,
            vector_score FLOAT,
            text_score FLOAT,
            combined_score FLOAT
        ) AS $$
        BEGIN
            RETURN QUERY
            WITH vector_results AS (
                -- Vector search (70% weight)
                SELECT c.id, c.text, 
                    1 - (query_embedding <=> e.embedding) AS raw_score,
                    (1 - (query_embedding <=> e.embedding)) * 0.7 AS vector_score
                FROM chunks c
                JOIN chunk_embeddings e ON c.id = e.chunk_id
                ORDER BY query_embedding <=> e.embedding
                LIMIT k * 2
            ),
            text_results AS (
                -- Text search (30% weight)
                SELECT c.id, c.text,
                    ts_rank(to_tsvector('english', c.text), 
                            plainto_tsquery('english', query_text)) AS raw_score,
                    ts_rank(to_tsvector('english', c.text), 
                            plainto_tsquery('english', query_text)) * 0.3 AS text_score
                FROM chunks c
                WHERE to_tsvector('english', c.text) @@ plainto_tsquery('english', query_text)
                LIMIT k * 2
            )
            SELECT 
                COALESCE(v.id, t.id) AS id,
                COALESCE(v.text, t.text) AS text,
                COALESCE(v.vector_score, 0) AS vector_score,
                COALESCE(t.text_score, 0) AS text_score,
                COALESCE(v.vector_score, 0) + COALESCE(t.text_score, 0) AS combined_score
            FROM vector_results v
            FULL OUTER JOIN text_results t ON v.id = t.id
            ORDER BY combined_score DESC
            LIMIT k;
        END;
        $$ LANGUAGE plpgsql;
        """))
        connection.commit()
```

## Add Hybrid Search Method to MEMNON

Implement the hybrid search method in your `memnon.py`:

```python
def hybrid_search(self, query_text, model_key='bge-large', vector_weight=0.7, 
                 text_weight=0.3, k=10, filters=None):
    """
    Perform hybrid search using both vector embeddings and text search.
    
    Args:
        query_text (str): The query text
        model_key (str): Which embedding model to use
        vector_weight (float): Weight to give vector search (0-1)
        text_weight (float): Weight to give text search (0-1)
        k (int): Number of results to return
        filters (dict): Optional filters to apply
        
    Returns:
        List[Dict]: Ranked search results
    """
    logger.info(f"Performing hybrid search for: {query_text}")
    
    # Generate embedding for vector part of search
    query_embedding = self.generate_embedding(query_text, model_key)
    
    # Prepare filter conditions if any
    filter_conditions = ""
    if filters:
        conditions = []
        for key, value in filters.items():
            if isinstance(value, (list, tuple)):
                conditions.append(f"metadata->>'%s' IN %s" % (key, tuple(value)))
            else:
                conditions.append(f"metadata->>'%s' = '%s'" % (key, value))
        if conditions:
            filter_conditions = "WHERE " + " AND ".join(conditions)
    
    # Call the database function
    query = text(f"""
    SELECT * FROM hybrid_search(:query_text, :query_embedding, :k)
    {filter_conditions}
    """)
    
    with self.engine.connect() as connection:
        result = connection.execute(
            query, 
            {
                "query_text": query_text,
                "query_embedding": query_embedding,
                "k": k
            }
        )
        
        # Process results
        results = []
        for row in result:
            results.append({
                "id": row.id,
                "text": row.text,
                "vector_score": float(row.vector_score),
                "text_score": float(row.text_score),
                "combined_score": float(row.combined_score),
                "score": float(row.combined_score),  # For compatibility with existing code
                "source": "hybrid_search"
            })
            
        return results
```

## Modify the Main Query Function 

Update MEMNON's main query function to use hybrid search by default:

```python
def query_memory(self, query: str, query_type: Optional[str] = None, 
                filters: Optional[Dict[str, Any]] = None, 
                k: int = None, use_hybrid=True) -> Dict[str, Any]:
    """
    Query the memory system with enhanced hybrid search capability.
    
    Args:
        query (str): The query string
        query_type (Optional[str]): Type of query for specialized handling
        filters (Optional[Dict]): Metadata filters to apply
        k (int): Number of results to return
        use_hybrid (bool): Whether to use hybrid search
        
    Returns:
        Dict[str, Any]: Query results with metadata
    """
    if k is None:
        k = self.settings.query.default_limit
    
    start_time = time.time()
    
    # Analyze query to determine if it's character-focused, theme-focused, etc.
    query_analysis = self._analyze_query(query, query_type)
    
    # Determine weights based on query analysis
    vector_weight = 0.7  # Default
    text_weight = 0.3    # Default
    
    if query_analysis.get("query_category") == "character":
        # Character-focused queries benefit more from vector search
        vector_weight = 0.8
        text_weight = 0.2
    elif query_analysis.get("query_category") == "event":
        # Event-focused queries benefit more from keyword search
        vector_weight = 0.6
        text_weight = 0.4
    
    # Use different search strategies based on configuration
    if use_hybrid:
        results = self.hybrid_search(
            query_text=query,
            vector_weight=vector_weight,
            text_weight=text_weight,
            k=k,
            filters=filters
        )
    else:
        # Fall back to standard vector search
        results = self._query_vector_search(query, k=k, filters=filters)
    
    # Apply any post-processing
    self._enhance_results_with_metadata(results)
    
    elapsed = time.time() - start_time
    
    return {
        "query": query,
        "results": results,
        "elapsed_time": elapsed,
        "query_analysis": query_analysis
    }
```

## Add Configuration Options

Update your settings.json to include hybrid search parameters:

```python
def update_settings(self):
    """Update settings.json with hybrid search configuration."""
    # Load existing settings
    with open('settings.json', 'r') as f:
        settings = json.load(f)
    
    # Add hybrid search settings if they don't exist
    if "retrieval" not in settings["Agent Settings"]["MEMNON"]:
        settings["Agent Settings"]["MEMNON"]["retrieval"] = {}
        
    settings["Agent Settings"]["MEMNON"]["retrieval"]["hybrid_search"] = {
        "enabled": True,
        "vector_weight_default": 0.7,
        "text_weight_default": 0.3,
        "character_query_vector_weight": 0.8,
        "event_query_vector_weight": 0.6,
        "use_custom_weights": True
    }
    
    # Save updated settings
    with open('settings.json', 'w') as f:
        json.dump(settings, f, indent=4)
```

## Tests and Example Usage

```python
def test_hybrid_search():
    """Test the hybrid search functionality."""
    memnon = MEMNON()  # Initialize your MEMNON instance
    
    # Set up the database for hybrid search
    memnon.setup_hybrid_search()
    
    # Example queries to test
    test_queries = [
        "What happened when Alex and Emilia were in the corporate district?",
        "Alex's neural implant malfunction",
        "Emilia's feelings about the mission"
    ]
    
    # Test each query
    for query in test_queries:
        print(f"\nQuery: {query}")
        results = memnon.query_memory(query, use_hybrid=True)
        
        print(f"Found {len(results['results'])} results in {results['elapsed_time']:.2f}s")
        print(f"Analysis: {results['query_analysis']}")
        
        # Print top 3 results
        for i, result in enumerate(results['results'][:3]):
            print(f"\nResult {i+1}: Score {result['combined_score']:.4f}")
            print(f"  Vector: {result['vector_score']:.4f}, Text: {result['text_score']:.4f}")
            print(f"  {result['text'][:100]}...")
```

This implementation gives you a powerful hybrid search system that combines the semantic understanding of vector embeddings with the precision of BM25-style keyword search, all within your existing PostgreSQL database.

The system automatically adjusts weights based on query type, giving you the best of both worlds without requiring any additional services beyond what you already have.