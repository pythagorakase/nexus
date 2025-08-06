"""
Cross-Encoder Reranking Module for MEMNON

This module implements a sliding window approach for cross-encoder reranking
of search results, handling long text chunks effectively by splitting them
into overlapping windows when they exceed the model's context length.
"""

import os
import logging
import torch
import numpy as np
from typing import List, Dict, Any, Optional, Tuple, Union
from sentence_transformers import CrossEncoder
from tqdm import tqdm
import textwrap

# Set up logging
logger = logging.getLogger("nexus.memnon.cross_encoder")

class CrossEncoderReranker:
    """
    Cross-encoder based reranker for search results with sliding window support.
    """
    
    def __init__(
        self,
        model_name_or_path: str = "naver/trecdl22-crossencoder-debertav3",
        device: Optional[str] = None,
        max_length: int = 512,
        sliding_window_overlap: int = 128,
        cache_dir: Optional[str] = None,
        use_8bit: bool = False,
    ):
        """
        Initialize the cross-encoder reranker.
        
        Args:
            model_name_or_path: Path to the cross-encoder model
            device: Device to use for inference ('cuda', 'mps', or 'cpu')
            max_length: Maximum sequence length for the model
            sliding_window_overlap: Overlap size for sliding windows
            cache_dir: Directory to cache the model
            use_8bit: Whether to use 8-bit quantization for model loading
        """
        self.max_length = max_length
        self.sliding_window_overlap = sliding_window_overlap
        
        # Auto-detect device if not specified
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch, 'has_mps') and torch.backends.mps.is_built():
                device = "mps"
            else:
                device = "cpu"
        
        self.device = device
        logger.info(f"Using device: {self.device}")
        
        # Check for local model path first
        model_exists_locally = False
        local_model_path = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "models", model_name_or_path.split('/')[-1])
        
        if os.path.exists(local_model_path):
            logger.info(f"Using local model at: {local_model_path}")
            model_name_or_path = local_model_path
            model_exists_locally = True
        
        try:
            if use_8bit and device == "cuda" and torch.cuda.is_available():
                # Use 8-bit quantization when loading the model
                from transformers import AutoModelForSequenceClassification, AutoTokenizer, BitsAndBytesConfig
                
                logger.info(f"Loading cross-encoder model with 8-bit quantization: {model_name_or_path}")
                quantization_config = BitsAndBytesConfig(load_in_8bit=True)
                
                model = AutoModelForSequenceClassification.from_pretrained(
                    model_name_or_path, 
                    quantization_config=quantization_config,
                    device_map="auto"
                )
                tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
                
                # Create a custom CrossEncoder with the 8-bit model
                self.model = CrossEncoder(
                    model_name_or_path,
                    tokenizer=tokenizer,
                    model=model,
                    max_length=max_length,
                    device=None  # device is handled by device_map in 8-bit mode
                )
                logger.info(f"Cross-encoder model loaded successfully with 8-bit quantization")
            else:
                # Use sentence-transformers CrossEncoder without quantization
                if use_8bit and device != "cuda":
                    logger.warning("8-bit quantization requested but requires CUDA. Using full precision model.")
                elif use_8bit and not torch.cuda.is_available():
                    logger.warning("8-bit quantization requested but CUDA is not available. Using full precision model.")
                
                self.model = CrossEncoder(model_name_or_path, device=device, max_length=max_length)
                logger.info(f"Cross-encoder model loaded successfully: {model_name_or_path}")
        except Exception as e:
            logger.error(f"Error loading cross-encoder model: {e}")
            raise

    def score_pair(self, query: str, passage: str) -> float:
        """
        Score a single query-passage pair.
        
        Args:
            query: The search query
            passage: The passage to score
            
        Returns:
            Relevance score between 0 and 1
        """
        try:
            # Use sentence-transformers CrossEncoder predict method
            scores = self.model.predict([(query, passage)])
            
            # CrossEncoder might return a single score as a numpy array or list
            if isinstance(scores, np.ndarray):
                score = scores[0]
            elif isinstance(scores, list):
                score = scores[0]
            else:
                score = scores
                
            # Normalize to 0-1 range with sigmoid if needed
            if score < 0 or score > 1:
                score = 1 / (1 + np.exp(-score))  # Sigmoid
                
            return float(score)
        except Exception as e:
            logger.error(f"Error scoring pair: {e}")
            return 0.0

    def score_pair_with_sliding_window(self, query: str, passage: str) -> float:
        """
        Score a query-passage pair using sliding window approach for long passages.
        
        Args:
            query: The search query
            passage: The passage to score (can be longer than max_length)
            
        Returns:
            Maximum relevance score across windows
        """
        # If passage is not too long, score directly
        if len(passage) < self.max_length * 4:  # Rough character estimate
            return self.score_pair(query, passage)
        
        # For long passages, use sliding window approach
        try:
            # Split the passage into sentences to create more meaningful chunks
            sentences = self._split_into_sentences(passage)
            
            # If we couldn't split into sentences, fall back to character-based chunking
            if len(sentences) <= 1:
                # Split by character chunks
                chunks = textwrap.wrap(passage, width=self.max_length * 2)  # Rough character approximation
            else:
                chunks = []
                current_chunk = []
                current_text = ""
                
                for sentence in sentences:
                    # If adding this sentence would exceed max length, start a new chunk
                    if len(current_text + sentence) > self.max_length * 4:  # Rough character estimate
                        if current_chunk:  # Don't add empty chunks
                            chunks.append(" ".join(current_chunk))
                        current_chunk = [sentence]
                        current_text = sentence
                    else:
                        current_chunk.append(sentence)
                        current_text += sentence
                
                # Add the last chunk
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                
            # Create overlapping windows if needed
            if len(chunks) > 1:
                windows = []
                
                for i in range(len(chunks)):
                    windows.append(chunks[i])
                    
                    # Add overlapping windows
                    if i < len(chunks) - 1:
                        # Create an overlapping window with the end of current chunk and start of next chunk
                        overlap = chunks[i].split(" ")[-self.sliding_window_overlap//10:] + chunks[i+1].split(" ")[:self.sliding_window_overlap//10]
                        windows.append(" ".join(overlap))
                
                chunks = windows
            
            # Score each window
            scores = []
            for chunk in chunks:
                scores.append(self.score_pair(query, chunk))
            
            # Return the maximum score
            return max(scores) if scores else 0.0
            
        except Exception as e:
            logger.error(f"Error scoring with sliding window: {e}")
            # Fall back to direct scoring with truncation
            return self.score_pair(query, passage)
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using simple heuristics."""
        # Simple sentence splitting
        for sep in ['. ', '? ', '! ', '.\n', '?\n', '!\n']:
            text = text.replace(sep, sep + '[SEP]')
        
        return [s.strip() for s in text.split('[SEP]') if s.strip()]
    
    def rerank_batch(
        self, 
        query: str, 
        passages: List[str], 
        batch_size: int = 8, 
        use_sliding_window: bool = True
    ) -> List[float]:
        """
        Rerank a batch of passages against a query.
        
        Args:
            query: The search query
            passages: List of passages to score
            batch_size: Batch size for model inference
            use_sliding_window: Whether to use sliding window for long texts
            
        Returns:
            List of relevance scores for each passage
        """
        scores = []
        
        # Process in batches
        for i in range(0, len(passages), batch_size):
            batch_passages = passages[i:i+batch_size]
            batch_scores = []
            
            for passage in batch_passages:
                if use_sliding_window:
                    score = self.score_pair_with_sliding_window(query, passage)
                else:
                    score = self.score_pair(query, passage)
                batch_scores.append(score)
            
            scores.extend(batch_scores)
        
        return scores


def rerank_results(
    query: str,
    results: List[Dict[str, Any]],
    top_k: int = 10,
    alpha: float = 0.3,  # Blend weight for original scores
    batch_size: int = 8,
    use_sliding_window: bool = True,
    model_path: str = "naver/trecdl22-crossencoder-debertav3",
    device: Optional[str] = None,
    use_8bit: bool = False,
) -> List[Dict[str, Any]]:
    """
    Rerank results using cross-encoder model.
    
    Args:
        query: The search query
        results: List of result dicts from initial retrieval
                (must contain 'text' and 'score' fields)
        top_k: Number of results to return after reranking
        alpha: Weight for original score blending
              final_score = alpha * original_score + (1 - alpha) * reranker_score
        batch_size: Batch size for model inference
        use_sliding_window: Whether to use sliding window for long texts
        model_path: Path to the cross-encoder model
        device: Device to use for inference
        use_8bit: Whether to use 8-bit quantization
        
    Returns:
        Reranked list of result dicts with updated scores
    """
    if not results:
        logger.warning("No results to rerank")
        return []
    
    try:
        # Initialize the reranker
        reranker = CrossEncoderReranker(
            model_name_or_path=model_path,
            device=device,
            use_8bit=use_8bit
        )
        
        # Extract passages from results
        passages = [result.get('text', '') for result in results]
        original_scores = [result.get('score', 0.0) for result in results]
        
        # Get reranker scores
        reranker_scores = reranker.rerank_batch(
            query=query,
            passages=passages,
            batch_size=batch_size,
            use_sliding_window=use_sliding_window
        )
        
        # Blend scores
        final_scores = []
        for orig_score, reranker_score in zip(original_scores, reranker_scores):
            # Normalize original score to 0-1 range if needed
            norm_orig_score = min(max(orig_score, 0.0), 1.0)
            
            # Blend scores
            final_score = alpha * norm_orig_score + (1 - alpha) * reranker_score
            final_scores.append(final_score)
        
        # Create reranked results
        reranked_results = []
        for i, (result, score) in enumerate(zip(results, final_scores)):
            # Create a copy of the original result
            reranked_result = result.copy()
            
            # Update scores
            reranked_result['original_score'] = result.get('score', 0.0)
            reranked_result['reranker_score'] = reranker_scores[i]
            reranked_result['score'] = score  # Update the main score
            
            reranked_results.append(reranked_result)
        
        # Sort by score and limit to top_k
        reranked_results = sorted(reranked_results, key=lambda x: x.get('score', 0.0), reverse=True)
        reranked_results = reranked_results[:top_k]
        
        logger.info(f"Reranked {len(results)} results to {len(reranked_results)} using cross-encoder")
        return reranked_results
        
    except Exception as e:
        logger.error(f"Error during reranking: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return original results if reranking fails
        logger.warning("Returning original results due to reranking failure")
        return sorted(results, key=lambda x: x.get('score', 0.0), reverse=True)[:top_k]