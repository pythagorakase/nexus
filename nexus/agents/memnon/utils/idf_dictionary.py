import math
import logging
import pickle
import re
import time
from pathlib import Path
from typing import Dict, Any, Iterable, List, Tuple

import psycopg2

try:
    import snowballstemmer
    STEMMER = snowballstemmer.stemmer('english')
except ImportError:
    STEMMER = None

logger = logging.getLogger("nexus.memnon.idf_dictionary")

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
}


class IDFDictionary:
    """Manages inverse document frequency calculations for text search."""
    
    def __init__(self, db_url: str, cache_path: str = None):
        self.db_url = db_url
        self.cache_path = cache_path or Path.home() / ".cache" / "nexus" / "idf_cache.pkl"
        # Create directory if it doesn't exist
        if not self.cache_path.parent.exists():
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created cache directory: {self.cache_path.parent}")
            except Exception as e:
                logger.warning(f"Could not create cache directory: {e}")
                # Fall back to local directory
                self.cache_path = Path("idf_cache.pkl")

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
        # Apply English stemming to match PostgreSQL's behavior
        lookup_term = term.lower()
        if STEMMER:
            lookup_term = STEMMER.stemWord(lookup_term)

        # Get IDF value
        idf = self.idf_dict.get(lookup_term, 1.0)
        
        # Assign weight class based on IDF
        if idf > 2.5:      # Very rare terms
            return "A"     # Highest weight
        elif idf > 2.0:    # Rare terms
            return "B"     # High weight
        elif idf > 1.0:    # Uncommon terms
            return "C"     # Medium weight
        else:              # Common terms
            return "D"     # Low weight
    
    def _tokenize(self, query_text: str) -> Iterable[str]:
        """Tokenize text into searchable lexemes compatible with to_tsquery."""

        tokens = re.findall(r"[a-z0-9]+", query_text.lower())
        for token in tokens:
            if len(token) < 2:
                continue
            # Apply English stemming to match PostgreSQL's behavior
            if STEMMER:
                stemmed = STEMMER.stemWord(token)
                yield stemmed
            else:
                yield token

    def _select_terms(self, tokens: Iterable[str]) -> List[Tuple[str, str, float]]:
        """Select unique tokens with their weight class and IDF score."""

        seen = set()
        selected: List[Tuple[str, str, float]] = []

        for token in tokens:
            if token in seen:
                continue
            seen.add(token)

            idf = self.get_idf(token)
            weight_class = self.get_weight_class(token)
            selected.append((token, weight_class, idf))

        # Sort by IDF descending so rare terms appear first
        selected.sort(key=lambda item: item[2], reverse=True)
        return selected

    def generate_weighted_query(self, query_text: str, max_terms: int = 12) -> str:
        """Generate a weighted OR tsquery string prioritizing rare keywords."""

        tokens = list(self._tokenize(query_text))
        if not tokens:
            return ""

        ranked_terms = self._select_terms(tokens)
        if not ranked_terms:
            return ""

        # Check if we have very rare terms (IDF > 3.0)
        very_rare_terms = [t for t in ranked_terms if t[2] > 3.0]

        # If we have very rare terms, be more selective
        if very_rare_terms:
            # Only include the very rare terms plus a few high-value terms
            high_value = [t for t in ranked_terms if t[2] >= 2.0]
            ordered_terms = high_value[:min(5, len(high_value))]
        else:
            # Normal behavior: separate high-value and fallback terms
            high_value: List[Tuple[str, str, float]] = []
            fallback: List[Tuple[str, str, float]] = []

            for term, weight_class, idf in ranked_terms:
                # Treat IDF >= 1.5 as meaningful enough to prioritize
                if idf >= 1.5:
                    high_value.append((term, weight_class, idf))
                else:
                    fallback.append((term, weight_class, idf))

            ordered_terms: List[Tuple[str, str, float]] = []
            ordered_terms.extend(high_value[:max_terms])

            if len(ordered_terms) < max_terms:
                remaining = max_terms - len(ordered_terms)
                ordered_terms.extend(fallback[:remaining])

        if not ordered_terms:
            # As an ultimate fallback, keep the first available term
            ordered_terms = ranked_terms[:1]

        # Note: PostgreSQL's to_tsquery doesn't support weight class syntax (term:A)
        # Weights must be applied via setweight() in to_tsvector, not in the query
        # So we just use the stemmed terms without weight modifiers
        terms_only = [term for term, weight_class, _ in ordered_terms]

        return " | ".join(terms_only)
        
    def get_idf(self, term: str) -> float:
        """Get IDF value for a specific term."""
        lookup_term = term.lower()
        if STEMMER:
            lookup_term = STEMMER.stemWord(lookup_term)
        return self.idf_dict.get(lookup_term, 1.0)

    def get_high_idf_terms(
        self,
        query_text: str,
        threshold: float = 2.0,
        stopwords: Iterable[str] = STOPWORDS,
    ) -> List[str]:
        """Return unique high-IDF terms present in the query text."""

        if not query_text:
            return []

        tokens = re.findall(r"[A-Za-z0-9']+", query_text.lower())
        high_idf_terms: List[str] = []

        for token in tokens:
            # Normalize possessives like "alex's" -> "alex"
            if token.endswith("'s"):
                token = token[:-2]

            normalized = token.strip("'")
            if not normalized or normalized in stopwords:
                continue

            # Apply English stemming to match PostgreSQL's behavior
            if STEMMER:
                normalized = STEMMER.stemWord(normalized)

            if self.get_idf(normalized) >= threshold and normalized not in high_idf_terms:
                high_idf_terms.append(normalized)

        return high_idf_terms