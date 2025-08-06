# Implementing a Custom IDF Dictionary for Enhanced Text Search

## Overview

Create a custom Inverse Document Frequency (IDF) dictionary to improve text search by giving rare terms like "gender" higher weight than common terms like "Alex" in your narrative retrieval system.

## Key Concepts

- **TF-IDF**: Term Frequency (how often a word appears in a document) × Inverse Document Frequency (how rare a word is across all documents)
- **Why it matters**: A term appearing 4 times in all existing 1425 chunks should have higher importance than one appearing in 3500 times across the same chunk span.
- **Implementation goal**: Pre-calculate term frequencies, store in a dictionary, and use to weight search terms

## Implementation Plan

### 1. Create IDF Dictionary Module (new file: `idf_dictionary.py`)

```python
# In nexus/agents/memnon/utils/idf_dictionary.py
import math
import logging
import psycopg2
import pickle
from pathlib import Path
import time
from typing import Dict, Any

logger = logging.getLogger("nexus.memnon.idf_dictionary")

class IDFDictionary:
    """Manages inverse document frequency calculations for text search."""
    
    def __init__(self, db_url: str, cache_path: str = None):
        self.db_url = db_url
        self.cache_path = cache_path or Path("idf_cache.pkl")
        self.idf_dict = {}
        self.total_docs = 0
        self.last_updated = 0
        
    def build_dictionary(self, force_rebuild: bool = False) -> Dict[str, float]:
        """Build or load the IDF dictionary."""
        # Check for cached dictionary
        if not force_rebuild and self._load_from_cache():
            return self.idf_dict
            
        logger.info("Building IDF dictionary from database...")
        try:
            with psycopg2.connect(self.db_url) as conn:
                with conn.cursor() as cursor:
                    # Get total document count
                    cursor.execute("SELECT COUNT(*) FROM narrative_chunks")
                    self.total_docs = cursor.fetchone()[0]
                    
                    # Get term frequencies
                    cursor.execute("""
                    SELECT word, ndoc FROM ts_stat(
                        'SELECT to_tsvector(''english'', raw_text) FROM narrative_chunks'
                    )
                    """)
                    
                    # Calculate IDF for each term
                    self.idf_dict = {}
                    for word, ndoc in cursor.fetchall():
                        # Standard IDF formula: log(N/df)
                        idf = math.log(self.total_docs / (ndoc + 1))
                        self.idf_dict[word] = idf
                    
                    logger.info(f"Built IDF dictionary with {len(self.idf_dict)} terms")
                    
                    # Save to cache
                    self._save_to_cache()
                    return self.idf_dict
                    
        except Exception as e:
            logger.error(f"Error building IDF dictionary: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    def _load_from_cache(self) -> bool:
        """Load IDF dictionary from cache file if it exists and is recent."""
        try:
            cache_path = Path(self.cache_path)
            if not cache_path.exists():
                return False
                
            # Check if cache is less than a day old
            cache_age = time.time() - cache_path.stat().st_mtime
            if cache_age > 86400:  # 24 hours
                logger.info("Cache is older than 24 hours, rebuilding")
                return False
                
            with open(cache_path, 'rb') as f:
                cache_data = pickle.load(f)
                self.idf_dict = cache_data['idf_dict']
                self.total_docs = cache_data['total_docs']
                self.last_updated = cache_data['timestamp']
                
            logger.info(f"Loaded IDF dictionary from cache with {len(self.idf_dict)} terms")
            return True
            
        except Exception as e:
            logger.error(f"Error loading IDF cache: {e}")
            return False
    
    def _save_to_cache(self) -> bool:
        """Save IDF dictionary to cache file."""
        try:
            cache_data = {
                'idf_dict': self.idf_dict,
                'total_docs': self.total_docs,
                'timestamp': time.time()
            }
            
            with open(self.cache_path, 'wb') as f:
                pickle.dump(cache_data, f)
                
            logger.info(f"Saved IDF dictionary to cache at {self.cache_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving IDF cache: {e}")
            return False
    
    def get_weight_class(self, term: str) -> str:
        """Get weight class (A, B, C, D) for a term based on its IDF."""
        # Convert to stemmed term if needed
        # TODO: Add stemming logic if needed
        
        # Get IDF value
        idf = self.idf_dict.get(term.lower(), 1.0)
        
        # Assign weight class based on IDF
        if idf > 2.5:      # Very rare terms
            return "A"     # Highest weight
        elif idf > 2.0:    # Rare terms
            return "B"     # High weight
        elif idf > 1.0:    # Uncommon terms
            return "C"     # Medium weight
        else:              # Common terms
            return "D"     # Low weight
    
    def generate_weighted_query(self, query_text: str) -> str:
        """Generate a weighted tsquery string for PostgreSQL."""
        terms = query_text.lower().split()
        weighted_terms = []
        
        for term in terms:
            weight_class = self.get_weight_class(term)
            weighted_terms.append(f"{term}:{weight_class}")
        
        # Join with & operator for AND search
        return " & ".join(weighted_terms)
        
    def get_idf(self, term: str) -> float:
        """Get IDF value for a specific term."""
        return self.idf_dict.get(term.lower(), 1.0)
```

### 2. Modify MEMNON Initialization (in `memnon.py`)

Find the `__init__` method in `memnon.py` (~line 200) and add:

```python
# Add import at the top
from .utils.idf_dictionary import IDFDictionary

# Inside __init__ method, after initializing embedding models
self.idf_dictionary = IDFDictionary(self.db_url)
self.idf_dictionary.build_dictionary()  # Build/load on startup
```

### 3. Update Hybrid Search Function (in `db_access.py`)

Modify `execute_hybrid_search` function (~line 200) to use weighted queries:

```python
# Add parameter for IDF dictionary
def execute_hybrid_search(db_url: str, query_text: str, query_embedding: list, 
                        model_key: str, vector_weight: float = 0.6, 
                        text_weight: float = 0.4, filters: Dict[str, Any] = None, 
                        top_k: int = 10, idf_dict = None) -> List[Dict[str, Any]]:
    """
    Execute a hybrid search combining vector similarity and text search.
    
    Args:
        db_url: PostgreSQL database URL
        query_text: The text query for keyword search
        query_embedding: Vector embedding for semantic search
        model_key: The embedding model key
        vector_weight: Weight to give vector search (0-1)
        text_weight: Weight to give text search (0-1)
        filters: Optional metadata filters
        top_k: Maximum number of results to return
        idf_dict: Optional IDF dictionary for term weighting
        
    Returns:
        List of matching chunks with scores and metadata
    """
    
    # [Existing code...]
    
    # When building the text search SQL query, use weighted query if IDF is available
    if idf_dict and hasattr(idf_dict, 'generate_weighted_query'):
        weighted_query = idf_dict.generate_weighted_query(query_text)
        logger.debug(f"Using weighted query: {weighted_query}")
        
        text_search_sql = f"""
        SELECT 
            nc.id, 
            nc.raw_text,
            cm.season, 
            cm.episode, 
            cm.scene as scene_number,
            ts_rank(to_tsvector('english', nc.raw_text), 
                    to_tsquery('english', %s)) AS text_score
        FROM 
            narrative_chunks nc
        JOIN 
            chunk_metadata cm ON nc.id = cm.chunk_id
        WHERE 
            to_tsvector('english', nc.raw_text) @@ to_tsquery('english', %s)
            {filter_sql}
        ORDER BY 
            text_score DESC
        LIMIT %s
        """
        
        # Use weighted query for both parameters
        cursor.execute(text_search_sql, (
            weighted_query, 
            weighted_query, 
            top_k * 2  # Double for text search
        ))
    else:
        # [Existing code for standard text search]
```

### 4. Modify Query Memory Function (in `memnon.py`)

Update the `query_memory` method (~line 1000) to pass the IDF dictionary:

```python
def query_memory(self, query: str, query_type: Optional[str] = None, 
               filters: Optional[Dict[str, Any]] = None, 
               k: Optional[int] = None, use_hybrid: bool = True) -> Dict[str, Any]:
    """
    Execute a query against memory and return matching results.
    """
    # [Existing code...]
    
    if use_hybrid and hybrid_enabled:
        # Add IDF dictionary to hybrid search
        results = self.perform_hybrid_search(
            query_text=strategy["query"],
            filters=strategy.get("filters"),
            top_k=strategy.get("limit", k),
            idf_dict=self.idf_dictionary  # Pass IDF dictionary
        )
        all_results.extend(results)
```

### 5. Update Perform Hybrid Search Method (in `memnon.py`)

Modify `perform_hybrid_search` method (~line 650) to pass IDF dictionary to db_access:

```python
def perform_hybrid_search(self, query_text: str, filters: Dict[str, Any] = None, 
                         top_k: int = None, idf_dict = None) -> List[Dict[str, Any]]:
    """
    Perform hybrid search using both vector embeddings and text search.
    """
    # [Existing code...]
    
    # Use provided IDF dict or class attribute
    idf_dictionary = idf_dict or getattr(self, 'idf_dictionary', None)
    
    # Execute hybrid search using our utility function
    results = execute_hybrid_search(
        db_url=self.db_url,
        query_text=query_text,
        query_embedding=query_embedding,
        model_key=target_model,
        vector_weight=vector_weight,
        text_weight=text_weight,
        filters=filters,
        top_k=top_k,
        idf_dict=idf_dictionary  # Pass IDF dictionary
    )
```

## Testing and Validation

1. Add logging to verify weighted queries are being used
2. Check improved relevance for queries with rare terms 
3. Verify cache functionality works
4. Run golden queries to see improvement in results

## Expected Improvements

- Terms like "gender" (4/1425 docs) will get weight class A
- Terms like "Alex" (3500/1425 docs) will get weight class D
- Queries with rare terms will return more relevant results
- Text scores will better reflect term importance

This implementation balances speed (through caching) with accuracy (through the mathematical IDF weighting model) and works with PostgreSQL's built-in weighting capabilities.