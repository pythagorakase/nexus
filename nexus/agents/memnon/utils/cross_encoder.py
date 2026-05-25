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
            return self._normalize_score(scores)
        except Exception as e:
            logger.error(f"Error scoring pair: {e}")
            return 0.0

    def _normalize_score(self, raw_score: Any) -> float:
        """Normalize a CrossEncoder score to the 0-1 relevance range."""
        if isinstance(raw_score, np.ndarray):
            flattened = raw_score.reshape(-1)
            if flattened.size == 0:
                return 0.0
            score = flattened[0]
        elif isinstance(raw_score, (list, tuple)):
            if not raw_score:
                return 0.0
            score = raw_score[0]
        else:
            score = raw_score

        score = float(score)
        if score < 0 or score > 1:
            score = 1 / (1 + np.exp(-score))  # Sigmoid
        return float(score)

    def score_batch(
        self,
        query: str,
        passages: List[str],
        batch_size: int = 8,
    ) -> List[float]:
        """
        Score query-passage pairs with true CrossEncoder batched inference.

        Args:
            query: The search query
            passages: Passages to score
            batch_size: Batch size for model inference

        Returns:
            Relevance scores between 0 and 1, one per passage
        """
        if not passages:
            return []

        try:
            pairs = [(query, passage) for passage in passages]
            raw_scores = self.model.predict(pairs, batch_size=batch_size)

            if isinstance(raw_scores, np.ndarray):
                score_values = raw_scores.reshape(-1).tolist()
            elif isinstance(raw_scores, list):
                score_values = raw_scores
            else:
                score_values = [raw_scores]

            if len(score_values) != len(passages):
                raise ValueError(
                    "CrossEncoder returned "
                    f"{len(score_values)} scores for {len(passages)} passages"
                )

            return [self._normalize_score(score) for score in score_values]
        except Exception as e:
            logger.error(f"Error scoring batch: {e}")
            return [0.0 for _ in passages]

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
        if not passages:
            return []

        scores = []

        # Process in batches
        for i in range(0, len(passages), batch_size):
            batch_passages = passages[i:i+batch_size]

            if not use_sliding_window:
                scores.extend(
                    self.score_batch(query, batch_passages, batch_size=batch_size)
                )
                continue

            batch_scores = [0.0 for _ in batch_passages]
            short_passage_indexes = []
            short_passages = []

            for batch_index, passage in enumerate(batch_passages):
                if len(passage) < self.max_length * 4:
                    short_passage_indexes.append(batch_index)
                    short_passages.append(passage)
                else:
                    batch_scores[batch_index] = self.score_pair_with_sliding_window(
                        query, passage
                    )

            short_scores = self.score_batch(
                query,
                short_passages,
                batch_size=batch_size,
            )
            for batch_index, score in zip(short_passage_indexes, short_scores):
                batch_scores[batch_index] = score

            scores.extend(batch_scores)

        return scores


class Qwen3LMReranker:
    """Qwen3-Reranker yes/no causal-LM scorer for (query, document) pairs.

    Qwen3-Reranker is a causal LM (not a SequenceClassification head). Scoring
    a pair runs the model once over `<Instruct>... <Query>... <Document>...`
    and reads P("yes") from the last-token logits over the {"yes", "no"} tokens.
    This class wraps that into the same ``rerank_batch(query, passages, ...)``
    surface as ``CrossEncoderReranker`` so callers don't branch.
    """

    _PREFIX = (
        '<|im_start|>system\n'
        'Judge whether the Document meets the requirements based on the Query '
        'and the Instruct provided. Note that the answer can only be "yes" or '
        '"no".<|im_end|>\n<|im_start|>user\n'
    )
    _SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    # TODO(issue #175): the model-card default instruction is tuned for web
    # search; a narrative-domain instruction (e.g., "Given a narrative query,
    # retrieve relevant story passages...") may improve scores. Re-bakeoff
    # before changing.
    _INSTRUCTION = (
        "Given a web search query, retrieve relevant passages that answer the query"
    )

    def __init__(
        self,
        model_name_or_path: str,
        device: Optional[str] = None,
        max_length: int = 2048,
    ):
        # NOTE: max_length defaults to 2048 (vs the model card's 8192) and
        # device defaults to CPU on Apple Silicon, both for MPS-stability
        # reasons. On MPS, Qwen3 inference with batched long sequences hits
        # "NDArray dimension length > INT_MAX" inside Metal regardless of
        # attention implementation (eager or SDPA, fp16 or bf16, max_length
        # 2048 or 8192 — all reproduce). CPU is slower but reliable.
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            else:
                # Apple Silicon path: prefer CPU over MPS for Qwen3 because of
                # the Metal indexing bug noted above.
                device = "cpu"
        self.device = device
        self.max_length = max_length

        logger.info(f"Loading Qwen3-Reranker from {model_name_or_path} on {device}")
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name_or_path, padding_side="left"
        )
        # fp32 on CPU (no native bf16 acceleration on most CPUs); bf16 on CUDA
        # to match Qwen3's native dtype.
        dtype = torch.float32 if device == "cpu" else torch.bfloat16
        self.model = (
            AutoModelForCausalLM.from_pretrained(model_name_or_path, torch_dtype=dtype)
            .to(device)
            .eval()
        )

        self._token_yes = self.tokenizer.convert_tokens_to_ids("yes")
        self._token_no = self.tokenizer.convert_tokens_to_ids("no")
        # Fail fast if the tokenizer doesn't have unique tokens for "yes"/"no".
        # `convert_tokens_to_ids` returns `unk_token_id` for missing tokens,
        # which would silently produce garbage relevance scores at scoring
        # time. This catches future tokenizer variants (e.g., BPE that
        # encodes "yes" as " yes" or "Ġyes").
        unk = self.tokenizer.unk_token_id
        if self._token_yes == unk or self._token_no == unk:
            raise ValueError(
                f"Qwen3-Reranker tokenizer at {model_name_or_path} does not "
                f"map 'yes' or 'no' to a unique vocab id "
                f"(got yes={self._token_yes}, no={self._token_no}, unk={unk}). "
                f"Check token surface forms (e.g., 'Ġyes' / '▁yes')."
            )
        self._prefix_tokens = self.tokenizer.encode(
            self._PREFIX, add_special_tokens=False
        )
        self._suffix_tokens = self.tokenizer.encode(
            self._SUFFIX, add_special_tokens=False
        )
        logger.info(
            f"Qwen3-Reranker ready: yes_id={self._token_yes}, no_id={self._token_no}"
        )

    def _format_pair(self, query: str, doc: str) -> str:
        return (
            f"<Instruct>: {self._INSTRUCTION}\n"
            f"<Query>: {query}\n"
            f"<Document>: {doc}"
        )

    def _build_inputs(self, pairs: List[str]):
        body_budget = self.max_length - len(self._prefix_tokens) - len(self._suffix_tokens)
        inputs = self.tokenizer(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=body_budget,
        )
        for i, body in enumerate(inputs["input_ids"]):
            inputs["input_ids"][i] = self._prefix_tokens + body + self._suffix_tokens
        inputs = self.tokenizer.pad(
            inputs, padding=True, return_tensors="pt", max_length=self.max_length
        )
        return {k: v.to(self.device) for k, v in inputs.items()}

    @torch.no_grad()
    def _score_batch(self, pairs: List[str]) -> List[float]:
        inputs = self._build_inputs(pairs)
        logits = self.model(**inputs).logits[:, -1, :]
        yes_logit = logits[:, self._token_yes]
        no_logit = logits[:, self._token_no]
        stacked = torch.stack([no_logit, yes_logit], dim=1)
        log_probs = torch.nn.functional.log_softmax(stacked, dim=1)
        return log_probs[:, 1].exp().tolist()

    def rerank_batch(
        self,
        query: str,
        passages: List[str],
        batch_size: int = 8,
        use_sliding_window: bool = True,  # API-compat; Qwen3 truncates internally.
    ) -> List[float]:
        if not passages:
            return []
        formatted = [self._format_pair(query, p or "") for p in passages]
        scores: List[float] = []
        for start in range(0, len(formatted), batch_size):
            batch = formatted[start:start + batch_size]
            scores.extend(self._score_batch(batch))
        return scores


# Module-level cache for reranker instances. Loading a 0.6B model is seconds;
# a 4B model is ~10s. Per-query reloads would dominate eval wall time, so we
# keep the instance alive across calls within the process.
# Key includes `device` so a workflow that loads first on (say) MPS doesn't
# silently return that instance to a later caller that requests CPU.
_RERANKER_CACHE: Dict[Tuple[str, str, Optional[str], bool], Any] = {}


def _get_or_create_reranker(
    model_path: str,
    api_type: str,
    device: Optional[str],
    use_8bit: bool,
):
    """Return a cached reranker, constructing it on first request."""
    key = (model_path, api_type, device, use_8bit)
    cached = _RERANKER_CACHE.get(key)
    if cached is not None:
        return cached

    if api_type == "cross_encoder":
        instance = CrossEncoderReranker(
            model_name_or_path=model_path,
            device=device,
            use_8bit=use_8bit,
        )
    elif api_type == "qwen3_lm":
        instance = Qwen3LMReranker(
            model_name_or_path=model_path,
            device=device,
        )
    else:
        raise ValueError(
            f"Unknown reranker api_type: {api_type!r}. "
            "Expected 'cross_encoder' or 'qwen3_lm'."
        )

    _RERANKER_CACHE[key] = instance
    return instance


def rerank_results(
    query: str,
    results: List[Dict[str, Any]],
    top_k: int = 10,
    alpha: float = 0.3,  # Blend weight for original scores
    batch_size: int = 8,
    use_sliding_window: bool = True,
    model_path: str = "naver/trecdl22-crossencoder-debertav3",
    api_type: str = "cross_encoder",
    device: Optional[str] = None,
    use_8bit: bool = False,
) -> List[Dict[str, Any]]:
    """
    Rerank results using a reranker model.

    Args:
        query: The search query
        results: List of result dicts from initial retrieval
                (must contain 'text' and 'score' fields)
        top_k: Number of results to return after reranking
        alpha: Weight for original score blending
              final_score = alpha * original_score + (1 - alpha) * reranker_score
        batch_size: Batch size for model inference
        use_sliding_window: Whether to use sliding window for long texts
        model_path: Path to the reranker model
        api_type: "cross_encoder" (SequenceClassification: DeBERTa-v3, mxbai)
                  or "qwen3_lm" (Qwen3-Reranker yes/no causal-LM)
        device: Device to use for inference
        use_8bit: Whether to use 8-bit quantization (cross_encoder only)

    Returns:
        Reranked list of result dicts with updated scores
    """
    if not results:
        logger.warning("No results to rerank")
        return []

    try:
        # Get cached reranker (loaded once per process; eviction is not needed
        # at our scale and would defeat the latency win).
        reranker = _get_or_create_reranker(
            model_path=model_path,
            api_type=api_type,
            device=device,
            use_8bit=use_8bit,
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
