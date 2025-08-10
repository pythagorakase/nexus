"""
Chunk Operations for LORE

Handles chunk selection, assembly, and chronological sorting.
All operations are deterministic - no LLM inference required.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
import tiktoken

logger = logging.getLogger("nexus.lore.chunk_operations")


def get_apex_model_encoding():
    """
    Get the tiktoken encoding for the Apex AI model from settings.
    """
    # Find settings.json
    module_dir = Path(__file__).parent.parent.parent.parent
    settings_path = module_dir / "settings.json"
    
    if settings_path.exists():
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                target_model = settings.get("Agent Settings", {}).get("LOGON", {}).get("apex_AI", {}).get("model", {}).get("target_model")
                if target_model:
                    # Map model names to tiktoken-compatible names
                    # Note: Using gpt-4o encoding as proxy until newer models are supported
                    model_map = {
                        "gpt-5": "gpt-4o",
                        "claude-opus-4-1": "gpt-4o",
                        "claude-opus-4-0": "gpt-4o",
                        "claude-sonnet-4-0": "gpt-4o"
                    }
                    model_name = model_map.get(target_model, target_model)
                    return tiktoken.encoding_for_model(model_name)
        except Exception as e:
            logger.warning(f"Failed to load target model from settings: {e}")
    
    # Default fallback
    return tiktoken.encoding_for_model("gpt-4o")


def calculate_chunk_tokens(text: str) -> int:
    """
    Calculate precise token count using tiktoken.
    Uses the Apex AI model's encoding from settings.json.
    
    Args:
        text: Text to tokenize
        
    Returns:
        Exact token count
        
    Raises:
        Exception if tokenization fails
    """
    encoding = get_apex_model_encoding()
    tokens = encoding.encode(text)
    return len(tokens)


def select_warm_slice(all_chunk_ids: List[int], span: int) -> List[int]:
    """
    Select the most recent N chunk IDs for warm slice.
    
    Since narrative_chunks.id is chronologically sequential,
    we simply take the highest IDs.
    
    Args:
        all_chunk_ids: List of all available chunk IDs
        span: Number of recent chunks to include
        
    Returns:
        List of chunk IDs for warm slice
    """
    if not all_chunk_ids or span <= 0:
        return []
    
    # Sort to ensure we get the most recent
    sorted_ids = sorted(all_chunk_ids)
    
    # Take the last N chunks
    warm_ids = sorted_ids[-span:] if span < len(sorted_ids) else sorted_ids
    
    logger.debug(f"Selected {len(warm_ids)} chunks for warm slice (requested {span})")
    return warm_ids


def assemble_chronological_context(warm_chunks: List[Dict], 
                                  augment_chunks: List[Dict]) -> List[Dict]:
    """
    Merge warm slice and augmentation chunks, then sort chronologically.
    
    Since narrative_chunks.id is chronologically sequential, we sort by ID.
    Each chunk is tagged with its source for debugging.
    
    Args:
        warm_chunks: List of warm slice chunk dictionaries
        augment_chunks: List of augmentation chunk dictionaries
        
    Returns:
        Chronologically sorted list of all chunks with source tags
    """
    context_chunks = []
    
    # Tag warm chunks
    for chunk in warm_chunks:
        tagged_chunk = chunk.copy()
        tagged_chunk['source'] = 'warm_slice'
        context_chunks.append(tagged_chunk)
    
    # Tag augmentation chunks, avoiding duplicates
    warm_ids = {chunk.get('id') for chunk in warm_chunks}
    for chunk in augment_chunks:
        if chunk.get('id') not in warm_ids:
            tagged_chunk = chunk.copy()
            tagged_chunk['source'] = 'augmentation'
            context_chunks.append(tagged_chunk)
    
    # Sort by ID (chronologically sequential)
    context_chunks.sort(key=lambda c: c.get('id', 0))
    
    logger.debug(f"Assembled {len(context_chunks)} chunks: "
                f"{len(warm_chunks)} warm, "
                f"{len([c for c in context_chunks if c['source'] == 'augmentation'])} augmentation")
    
    return context_chunks


def format_chunk_with_metadata(chunk_data: Dict, 
                              include_world_time: bool = True) -> str:
    """
    Format a chunk with its metadata headers for Apex AI.
    
    Uses the same format as narrative_view to maintain consistency.
    
    Args:
        chunk_data: Dictionary with chunk data and metadata
        include_world_time: Whether to include world time in header
        
    Returns:
        Formatted chunk text with headers
    """
    parts = []
    
    # Add episode/scene header if available
    if 'season' in chunk_data and 'episode' in chunk_data:
        parts.append(f"[S{chunk_data['season']:02d}E{chunk_data['episode']:02d}")
        if 'scene' in chunk_data:
            parts.append(f" Scene {chunk_data['scene']}")
        parts.append("]")
    
    # Add world time if available and requested
    if include_world_time and 'world_time' in chunk_data and chunk_data['world_time']:
        parts.append(f" {chunk_data['world_time']}")
    elif 'world_layer' in chunk_data and chunk_data['world_layer'] != 'primary':
        # For non-primary layers, indicate the layer type
        parts.append(f" [{chunk_data['world_layer'].upper()}]")
    
    # Add the text content
    if parts:
        header = "".join(parts)
        return f"{header}\n{chunk_data.get('raw_text', chunk_data.get('text', ''))}"
    else:
        return chunk_data.get('raw_text', chunk_data.get('text', ''))


def merge_deduplicate_chunks(chunks1: List[Dict], 
                            chunks2: List[Dict]) -> List[Dict]:
    """
    Merge two lists of chunks and remove duplicates by ID.
    
    Args:
        chunks1: First list of chunks
        chunks2: Second list of chunks
        
    Returns:
        Merged list with duplicates removed
    """
    seen_ids = set()
    merged = []
    
    for chunk in chunks1 + chunks2:
        chunk_id = chunk.get('id')
        if chunk_id and chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            merged.append(chunk)
    
    return merged


def filter_by_world_layer(chunks: List[Dict], 
                         allowed_layers: List[str] = None) -> List[Dict]:
    """
    Filter chunks by world layer (primary, flashback, dream, extradiegetic).
    
    Args:
        chunks: List of chunks with world_layer metadata
        allowed_layers: List of allowed world layers (default: ['primary'])
        
    Returns:
        Filtered list of chunks
    """
    if allowed_layers is None:
        allowed_layers = ['primary']
    
    filtered = [c for c in chunks 
                if c.get('world_layer', 'primary') in allowed_layers]
    
    logger.debug(f"Filtered {len(chunks)} chunks to {len(filtered)} "
                f"(layers: {allowed_layers})")
    
    return filtered


def get_chunk_time_range(chunks: List[Dict]) -> Dict[str, Any]:
    """
    Calculate the time range covered by a set of chunks.
    
    Only considers chunks from the 'primary' world layer.
    
    Args:
        chunks: List of chunks with world_time metadata
        
    Returns:
        Dictionary with start_time, end_time, and duration
    """
    primary_chunks = [c for c in chunks 
                      if c.get('world_layer') == 'primary' and c.get('world_time')]
    
    if not primary_chunks:
        return {
            'start_time': None,
            'end_time': None,
            'duration': None
        }
    
    times = [c['world_time'] for c in primary_chunks]
    
    return {
        'start_time': min(times),
        'end_time': max(times),
        'duration': max(times) - min(times) if len(times) > 1 else None
    }