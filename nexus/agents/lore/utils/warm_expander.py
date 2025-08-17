"""
Warm Slice Expander for Pass 2

Simple, robust expansion of the warm slice when no gaps are detected.
No fancy algorithms - just extend backward and forward until tokens are filled.
"""

import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("nexus.lore.warm_expander")


class WarmSliceExpander:
    """
    Simple warm slice expansion for Pass 2.
    
    When no gaps are detected, we just extend the existing warm slice
    backward and forward to use the remaining token budget.
    """
    
    def __init__(self, memnon_instance=None):
        """
        Initialize WarmSliceExpander.
        
        Args:
            memnon_instance: MEMNON for fetching chunks
        """
        self.memnon = memnon_instance
        logger.info("WarmSliceExpander initialized - keeping it simple")
    
    def expand_warm_slice(
        self,
        current_range: Dict[str, int],
        tokens_available: int,
        avg_tokens_per_chunk: int = 2000
    ) -> Dict[str, Any]:
        """
        Expand the warm slice to fill available tokens.
        
        Args:
            current_range: Current warm slice {"start": chunk_id, "end": chunk_id}
            tokens_available: Remaining token budget for Pass 2
            avg_tokens_per_chunk: Estimated tokens per chunk (default 2000)
            
        Returns:
            Dict with expansion plan
        """
        if not current_range or not tokens_available:
            return {
                "strategy": "no_expansion",
                "reason": "No current range or no tokens available",
                "chunks_to_add": []
            }
        
        start_chunk = current_range.get("start", 0)
        end_chunk = current_range.get("end", 0)
        
        # Calculate how many chunks we can add
        chunks_to_add = tokens_available // avg_tokens_per_chunk
        
        if chunks_to_add < 1:
            return {
                "strategy": "no_expansion",
                "reason": "Insufficient tokens for expansion",
                "chunks_to_add": []
            }
        
        logger.info(f"Can add approximately {chunks_to_add} chunks with {tokens_available} tokens")
        
        # Balance expansion backward and forward
        backward_chunks = chunks_to_add // 2
        forward_chunks = chunks_to_add - backward_chunks
        
        # Calculate new range
        new_start = max(1, start_chunk - backward_chunks)
        new_end = end_chunk + forward_chunks
        
        # Build list of chunks to add
        chunks_to_add_list = []
        
        # Add backward chunks
        for chunk_id in range(new_start, start_chunk):
            chunks_to_add_list.append({
                "chunk_id": chunk_id,
                "direction": "backward",
                "priority": start_chunk - chunk_id  # Closer chunks have lower priority value
            })
        
        # Add forward chunks
        for chunk_id in range(end_chunk + 1, new_end + 1):
            chunks_to_add_list.append({
                "chunk_id": chunk_id,
                "direction": "forward",
                "priority": chunk_id - end_chunk
            })
        
        # Sort by priority (closer chunks first)
        chunks_to_add_list.sort(key=lambda x: x["priority"])
        
        return {
            "strategy": "balanced_expansion",
            "original_range": current_range,
            "new_range": {"start": new_start, "end": new_end},
            "chunks_to_add": chunks_to_add_list,
            "estimated_tokens": len(chunks_to_add_list) * avg_tokens_per_chunk,
            "reasoning": f"Expanding warm slice by {backward_chunks} chunks backward and {forward_chunks} chunks forward"
        }
    
    def fetch_chunks_for_expansion(
        self,
        expansion_plan: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Fetch the actual chunks for expansion.
        
        Args:
            expansion_plan: Plan from expand_warm_slice()
            
        Returns:
            List of chunk data
        """
        if not self.memnon:
            logger.warning("No MEMNON instance - cannot fetch chunks")
            return []
        
        chunks = []
        chunks_to_fetch = expansion_plan.get("chunks_to_add", [])
        
        for chunk_info in chunks_to_fetch:
            chunk_id = chunk_info["chunk_id"]
            try:
                chunk_data = self.memnon.get_chunk_by_id(chunk_id)
                if chunk_data:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": chunk_data.get("text", ""),
                        "direction": chunk_info["direction"],
                        "metadata": chunk_data.get("metadata", {})
                    })
                    logger.debug(f"Fetched chunk {chunk_id} ({chunk_info['direction']})")
            except Exception as e:
                logger.warning(f"Failed to fetch chunk {chunk_id}: {e}")
        
        logger.info(f"Fetched {len(chunks)} chunks for warm slice expansion")
        return chunks
    
    def get_expansion_summary(
        self,
        expansion_plan: Dict[str, Any],
        fetched_chunks: List[Dict[str, Any]]
    ) -> str:
        """
        Generate a summary of the expansion.
        
        Args:
            expansion_plan: The expansion plan
            fetched_chunks: Actually fetched chunks
            
        Returns:
            Human-readable summary
        """
        if expansion_plan.get("strategy") == "no_expansion":
            return expansion_plan.get("reason", "No expansion performed")
        
        original = expansion_plan.get("original_range", {})
        new = expansion_plan.get("new_range", {})
        
        summary_parts = [
            f"Warm Slice Expansion Complete:",
            f"- Original range: chunks {original.get('start', '?')}-{original.get('end', '?')}",
            f"- New range: chunks {new.get('start', '?')}-{new.get('end', '?')}",
            f"- Chunks added: {len(fetched_chunks)}",
            f"- Strategy: {expansion_plan.get('reasoning', 'balanced expansion')}"
        ]
        
        return "\n".join(summary_parts)
    
    def simple_extend(
        self,
        current_chunk_ids: List[int],
        tokens_to_fill: int,
        tokens_per_chunk: int = 2000
    ) -> Tuple[List[int], str]:
        """
        Even simpler interface - just give chunk IDs to add.
        
        Args:
            current_chunk_ids: Chunks currently in context
            tokens_to_fill: Tokens available to fill
            tokens_per_chunk: Estimated tokens per chunk
            
        Returns:
            Tuple of (new_chunk_ids, reasoning)
        """
        if not current_chunk_ids:
            return [], "No current chunks to expand from"
        
        chunks_to_add = tokens_to_fill // tokens_per_chunk
        if chunks_to_add < 1:
            return [], f"Insufficient tokens ({tokens_to_fill}) to add chunks"
        
        min_chunk = min(current_chunk_ids)
        max_chunk = max(current_chunk_ids)
        
        new_chunks = []
        
        # Add backward
        for i in range(chunks_to_add // 2):
            new_id = min_chunk - i - 1
            if new_id > 0:
                new_chunks.append(new_id)
        
        # Add forward
        for i in range(chunks_to_add - (chunks_to_add // 2)):
            new_id = max_chunk + i + 1
            new_chunks.append(new_id)
        
        reasoning = f"Extended warm slice by {len(new_chunks)} chunks (balanced backward/forward)"
        
        return new_chunks, reasoning