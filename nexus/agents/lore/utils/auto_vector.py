"""
Auto-Vector Utility for Pass 2 User Input

Simple and generous filtering for piping user input directly to vector search.
Trust the vector engine to handle edge cases gracefully.
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("nexus.lore.auto_vector")


def should_auto_vector(user_text: str) -> bool:
    """
    Determine if user input should be piped to vector search.
    Be VERY generous - only skip truly useless input.
    
    Args:
        user_text: Raw user input
        
    Returns:
        True if input should be vectorized, False only for truly hopeless cases
    """
    if not user_text:
        return False
    
    cleaned = user_text.strip()
    
    # Skip only the truly barren
    if len(cleaned) <= 2:
        logger.debug(f"Skipping auto-vector: too short ({len(cleaned)} chars)")
        return False
    
    # Skip pure numbers
    if cleaned.isdigit():
        logger.debug(f"Skipping auto-vector: pure number '{cleaned}'")
        return False
    
    # Skip simple menu selections like "A, B, C" or "B, then A"
    menu_pattern = r'^[A-Z](\s*,\s*[A-Z])*\.?$'
    if re.match(menu_pattern, cleaned):
        logger.debug(f"Skipping auto-vector: menu selection '{cleaned}'")
        return False
    
    # Everything else goes through!
    # This includes:
    # - Brief responses with editorialization
    # - Long paragraphs (these work great!)
    # - Cryptic references ("too soon for karaoke")
    # - Mixed content ("#2, because Alex isn't ready...")
    
    logger.debug(f"Auto-vectoring user input: '{cleaned[:50]}...'")
    return True


def auto_vector_user_input(
    user_text: str,
    memnon_instance,
    k: int = 10
) -> Dict[str, Any]:
    """
    Pipe user input directly to vector search.
    
    Args:
        user_text: Raw user input
        memnon_instance: MEMNON instance for vector search
        k: Number of results to retrieve (default 10 for user input)
        
    Returns:
        Dict with vector search results and metadata
    """
    result = {
        "vectorized": False,
        "query": user_text,
        "chunks": [],
        "chunk_ids": [],
        "reasoning": ""
    }
    
    # Check if we should vector this input
    if not should_auto_vector(user_text):
        result["reasoning"] = "Input too short or non-semantic"
        return result
    
    try:
        # Just send it! Let the vector engine figure it out
        logger.info(f"Auto-vectoring user input: {len(user_text)} chars")
        
        vector_result = memnon_instance.query_memory(
            user_text,
            filters=None,
            k=k,
            use_hybrid=True  # Use hybrid for best results
        )
        
        # Extract results
        chunks = vector_result.get("results", [])
        result["vectorized"] = True
        result["chunks"] = chunks
        result["chunk_ids"] = [
            chunk.get("chunk_id", chunk.get("id")) 
            for chunk in chunks
        ]
        
        # Log what we found
        if chunks:
            logger.info(f"Auto-vector found {len(chunks)} chunks")
            result["reasoning"] = f"Found {len(chunks)} potentially relevant chunks"
            
            # Log top hits for debugging
            for i, chunk in enumerate(chunks[:3]):
                chunk_id = chunk.get("chunk_id", chunk.get("id"))
                score = chunk.get("score", 0)
                logger.debug(f"  Hit {i+1}: Chunk {chunk_id} (score: {score:.3f})")
        else:
            logger.info("Auto-vector returned no chunks")
            result["reasoning"] = "No matching chunks found"
            
    except Exception as e:
        logger.error(f"Auto-vector failed: {e}")
        result["reasoning"] = f"Vector search error: {str(e)}"
    
    return result


def detect_deep_cuts(
    auto_vector_results: Dict[str, Any],
    pass1_chunk_ids: List[int],
    distance_threshold: int = 100
) -> List[int]:
    """
    Detect "deep cut" references - chunks found by auto-vector that are
    far from the current narrative position.
    
    Args:
        auto_vector_results: Results from auto_vector_user_input
        pass1_chunk_ids: Chunk IDs already in Pass 1 context
        distance_threshold: Minimum distance to consider a "deep cut"
        
    Returns:
        List of chunk IDs that are deep cuts (remote references)
    """
    if not auto_vector_results.get("vectorized"):
        return []
    
    deep_cuts = []
    found_chunk_ids = auto_vector_results.get("chunk_ids", [])
    
    # Get the range of Pass 1 chunks
    if pass1_chunk_ids:
        min_pass1 = min(pass1_chunk_ids)
        max_pass1 = max(pass1_chunk_ids)
        
        for chunk_id in found_chunk_ids:
            if chunk_id:
                try:
                    cid = int(chunk_id)
                    # Check if this chunk is far from Pass 1 context
                    distance = min(
                        abs(cid - min_pass1),
                        abs(cid - max_pass1)
                    )
                    
                    if distance > distance_threshold:
                        deep_cuts.append(cid)
                        logger.info(f"Deep cut detected: Chunk {cid} (distance: {distance})")
                        
                except (ValueError, TypeError):
                    continue
    
    return deep_cuts


def extract_semantic_phrases(user_text: str) -> List[str]:
    """
    Extract potentially semantic phrases from user input.
    Used when full text auto-vector doesn't find much.
    
    Args:
        user_text: User input text
        
    Returns:
        List of extracted phrases worth searching
    """
    phrases = []
    
    # Look for quoted strings
    quoted = re.findall(r'"([^"]+)"', user_text)
    phrases.extend(quoted)
    
    # Look for capitalized phrases (proper nouns)
    # But not single letters (menu choices)
    proper_nouns = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', user_text)
    phrases.extend([p for p in proper_nouns if len(p) > 2])
    
    # Look for phrases after key words
    key_patterns = [
        r'about\s+(.+?)(?:\.|,|$)',
        r'regarding\s+(.+?)(?:\.|,|$)',
        r'remember\s+(.+?)(?:\.|,|$)',
        r'recall\s+(.+?)(?:\.|,|$)',
        r'mention\s+(.+?)(?:\.|,|$)'
    ]
    
    for pattern in key_patterns:
        matches = re.findall(pattern, user_text, re.IGNORECASE)
        phrases.extend(matches)
    
    # Deduplicate while preserving order
    seen = set()
    unique_phrases = []
    for phrase in phrases:
        if phrase not in seen:
            seen.add(phrase)
            unique_phrases.append(phrase)
    
    return unique_phrases