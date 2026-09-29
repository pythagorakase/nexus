"""
Cross-Encoder Reranking Module for MEMNON

This module implements a sliding window approach for cross-encoder reranking
of search results, handling long text chunks effectively by splitting them
into overlapping windows when they exceed the model's context length.

Both rerankers (the SequenceClassification cross-encoder and the Qwen3 yes/no
causal LM) load only from the local folder they are given (the production
``[memnon.retrieval.cross_encoder_reranking].model_path``) with
``local_files_only=True``; a missing or broken folder raises a RuntimeError
naming the folder and the install command.
"""

import logging
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

import numpy as np
import torch
from sentence_transformers import CrossEncoder

# Set up logging
logger = logging.getLogger("nexus.memnon.cross_encoder")

# The nexus.toml key that names the production reranker folder.
MODEL_PATH_SETTING = "[memnon.retrieval.cross_encoder_reranking].model_path"


def reranker_repo_id(
    model_path: str, candidates: Mapping[str, Mapping[str, Any]]
) -> Optional[str]:
    """Return the Hugging Face repository of the reranker folder ``model_path``.

    The repository is the ``remote_path`` of the one
    ``[memnon.retrieval.cross_encoder_reranking.candidates]`` entry whose
    ``local_path`` is ``model_path``: the match ``nexus models lock`` uses to
    name the production reranker. None when no single entry matches or the
    entry names no repository.

    Args:
        model_path: The reranker folder that will be loaded
        candidates: The candidate registry, keyed by candidate name

    Returns:
        The repository id, or None when it cannot be derived
    """
    matches = [
        candidate
        for candidate in candidates.values()
        if Path(str(candidate["local_path"])) == Path(model_path)
    ]
    if len(matches) != 1:
        return None
    return str(matches[0].get("remote_path") or "") or None


def _reranker_remedy(path: Path, repo_id: Optional[str]) -> str:
    """Name the command that installs a missing reranker, then the check."""
    if repo_id:
        install = f"Download it with `hf download {repo_id} --local-dir {path}`"
    else:
        install = f"Point {MODEL_PATH_SETTING} at the downloaded reranker folder"
    return f"{install}, then run `nexus models verify`."


def _require_reranker_folder(kind: str, path: Path, repo_id: Optional[str]) -> str:
    """Check that ``path`` is an existing local folder and return the remedy.

    Every reranker loader runs this check before it touches the folder, so a
    missing folder or a file in its place is never passed to ``from_pretrained``
    (which would treat a non-directory as a Hub repository id).

    Args:
        kind: The reranker named in the error, such as "Cross-encoder reranker"
        path: The local folder that will be loaded
        repo_id: Hugging Face repository of the artifact, if known

    Returns:
        The remedy sentence to append to a later load error

    Raises:
        RuntimeError: When ``path`` does not exist or is not a directory.
    """
    remedy = _reranker_remedy(path, repo_id)
    if not path.exists():
        raise RuntimeError(
            f"{kind} is not installed: {MODEL_PATH_SETTING} "
            f"{path} does not exist. {remedy}"
        )
    if not path.is_dir():
        raise RuntimeError(
            f"{kind} {MODEL_PATH_SETTING} {path} is not a directory. {remedy}"
        )
    return remedy


# There is no 8-bit reranker load: the locked sentence-transformers 3.4.1
# CrossEncoder.__init__ always ends with ``if device is None: device =
# get_device_name()`` and ``self.model.to(device)`` (CrossEncoder.py:123-126),
# including after an ``automodel_args`` load with ``device_map="auto"``, and
# transformers 4.51.3 raises for every ``.to`` on a model loaded in 8-bit
# bitsandbytes (PreTrainedModel.to, modeling_utils.py:3682-3686). The former
# ``use_8bit`` setting could therefore only ever be false and was removed.


def cross_encoder_kwargs(device: Optional[str], max_length: int) -> Dict[str, Any]:
    """Return the keyword arguments every CrossEncoder load passes.

    ``local_files_only`` keeps the load off the Hugging Face Hub: an incomplete
    local folder fails instead of being patched from the network.

    Args:
        device: Device to place the model on ('cuda', 'mps' or 'cpu')
        max_length: Maximum sequence length for the model

    Returns:
        Keyword arguments for ``CrossEncoder(path, **kwargs)``
    """
    return {"device": device, "max_length": max_length, "local_files_only": True}


class CrossEncoderReranker:
    """
    Cross-encoder based reranker for search results with sliding window support.
    """

    def __init__(
        self,
        model_path: str,
        device: Optional[str] = None,
        max_length: int = 512,
        sliding_window_overlap: int = 128,
        cache_dir: Optional[str] = None,
        repo_id: Optional[str] = None,
    ):
        """
        Load the cross-encoder from exactly ``model_path``, a local folder.

        Nothing is downloaded and no other folder is substituted:
        ``nexus models verify`` checks the folder named by
        ``[memnon.retrieval.cross_encoder_reranking].model_path``, so that
        folder is the one that loads (issue #812).

        Args:
            model_path: Local directory holding the cross-encoder artifact
            device: Device to use for inference ('cuda', 'mps', or 'cpu')
            max_length: Maximum sequence length for the model
            sliding_window_overlap: Overlap size for sliding windows
            cache_dir: Unused; the artifact is read from ``model_path``
            repo_id: Hugging Face repository of the artifact, named in the
                install command when the folder is missing or fails to load

        Raises:
            RuntimeError: When ``model_path`` does not exist, is not a
                directory, or fails to load.
        """
        path = Path(model_path)
        remedy = _require_reranker_folder("Cross-encoder reranker", path, repo_id)

        self.max_length = max_length
        self.sliding_window_overlap = sliding_window_overlap

        # Auto-detect device if not specified
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch, "has_mps") and torch.backends.mps.is_built():
                device = "mps"
            else:
                device = "cpu"

        self.device = device
        logger.info(f"Using device: {self.device}")

        try:
            self.model = CrossEncoder(
                str(path), **cross_encoder_kwargs(device, max_length)
            )
        except Exception as exc:
            raise RuntimeError(
                f"Cross-encoder reranker failed to load from {MODEL_PATH_SETTING} "
                f"{path}: {str(exc).rstrip('.')}. {remedy}"
            ) from exc
        logger.info(f"Cross-encoder model loaded from {path}")

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
        elif isinstance(raw_score, list):
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

        pairs = [(query, passage) for passage in passages]
        try:
            raw_scores = self.model.predict(pairs, batch_size=batch_size)
        except Exception as e:
            logger.error(
                f"Error scoring batch: {e}; falling back to per-passage scoring"
            )
            return [self.score_pair(query, passage) for passage in passages]

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
        if not self._needs_sliding_window(passage):
            return self.score_pair(query, passage)

        # For long passages, use sliding window approach
        try:
            windows = self._build_sliding_windows(passage)
            scores = [self.score_pair(query, window) for window in windows]
            return self._max_window_score(scores)

        except Exception as e:
            logger.error(f"Error scoring with sliding window: {e}")
            # Fall back to direct scoring with truncation
            return self.score_pair(query, passage)

    def _needs_sliding_window(self, passage: str) -> bool:
        """Return whether a passage is long enough to be scored in windows."""
        return len(passage) >= self.max_length * 4  # Rough character estimate

    def _build_sliding_windows(self, passage: str) -> List[str]:
        """
        Split a long passage into the windows scored by sliding-window reranking.

        The passage is grouped into sentence chunks of roughly ``max_length``
        tokens (character-wrapped when it has no sentence boundaries), and an
        overlap window spanning each adjacent chunk pair is interleaved between
        them.

        Args:
            passage: The long passage to split

        Returns:
            Windows in passage order; empty when the passage has no text
        """
        # Split the passage into sentences to create more meaningful chunks
        sentences = self._split_into_sentences(passage)

        # If we couldn't split into sentences, fall back to character-based chunking
        if len(sentences) <= 1:
            # Split by character chunks
            chunks = textwrap.wrap(
                passage, width=self.max_length * 2
            )  # Rough character approximation
        else:
            chunks = []
            current_chunk: List[str] = []
            current_text = ""

            for sentence in sentences:
                # If adding this sentence would exceed max length, start a new chunk
                if (
                    len(current_text + sentence) > self.max_length * 4
                ):  # Rough character estimate
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
        if len(chunks) <= 1:
            return chunks

        windows = []
        for i in range(len(chunks)):
            windows.append(chunks[i])

            # Add overlapping windows
            if i < len(chunks) - 1:
                # Create an overlapping window with the end of current chunk and
                # start of next chunk
                overlap = (
                    chunks[i].split(" ")[-self.sliding_window_overlap // 10 :]
                    + chunks[i + 1].split(" ")[: self.sliding_window_overlap // 10]
                )
                windows.append(" ".join(overlap))

        return windows

    @staticmethod
    def _max_window_score(window_scores: List[float]) -> float:
        """Reduce one passage's window scores to its maximum (0.0 if none)."""
        return max(window_scores) if window_scores else 0.0

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using simple heuristics."""
        # Simple sentence splitting
        for sep in [". ", "? ", "! ", ".\n", "?\n", "!\n"]:
            text = text.replace(sep, sep + "[SEP]")

        return [s.strip() for s in text.split("[SEP]") if s.strip()]

    def rerank_batch(
        self,
        query: str,
        passages: List[str],
        batch_size: int = 8,
        use_sliding_window: bool = True,
    ) -> List[float]:
        """
        Rerank a batch of passages against a query.

        With ``use_sliding_window``, short passages in each rerank batch are
        scored together, and the windows of every long passage in the batch are
        flattened and scored through batched inference in slices of
        ``batch_size``. Each long passage takes the maximum of its window scores.

        Args:
            query: The search query
            passages: List of passages to score
            batch_size: Batch size for model inference
            use_sliding_window: Whether to use sliding window for long texts

        Returns:
            List of relevance scores for each passage, in input order
        """
        if not passages:
            return []

        scores = []

        # Process in batches
        for i in range(0, len(passages), batch_size):
            batch_passages = passages[i : i + batch_size]

            if not use_sliding_window:
                scores.extend(
                    self.score_batch(query, batch_passages, batch_size=batch_size)
                )
                continue

            batch_scores = [0.0 for _ in batch_passages]
            short_passage_indexes = []
            short_passages = []
            window_scores_by_passage: Dict[int, List[float]] = {}
            window_owners: List[int] = []
            windows: List[str] = []

            for batch_index, passage in enumerate(batch_passages):
                if not self._needs_sliding_window(passage):
                    short_passage_indexes.append(batch_index)
                    short_passages.append(passage)
                else:
                    window_scores_by_passage[batch_index] = []
                    for window in self._build_sliding_windows(passage):
                        window_owners.append(batch_index)
                        windows.append(window)

            short_scores = self.score_batch(
                query,
                short_passages,
                batch_size=batch_size,
            )
            for batch_index, score in zip(short_passage_indexes, short_scores):
                batch_scores[batch_index] = score

            window_scores = self._score_windows(query, windows, batch_size=batch_size)
            for batch_index, score in zip(window_owners, window_scores):
                window_scores_by_passage[batch_index].append(score)
            for batch_index, passage_window_scores in window_scores_by_passage.items():
                batch_scores[batch_index] = self._max_window_score(
                    passage_window_scores
                )

            scores.extend(batch_scores)

        return scores

    def _score_windows(
        self,
        query: str,
        windows: List[str],
        batch_size: int,
    ) -> List[float]:
        """
        Score flattened sliding windows with batched inference.

        Windows are sent to the model in slices of at most ``batch_size`` pairs,
        each through :meth:`score_batch`, so window scores are normalized exactly
        like single-pair scores.

        Args:
            query: The search query
            windows: Windows from one or more long passages, in any order
            batch_size: Maximum pairs per model call

        Returns:
            One relevance score per window, in input order
        """
        window_scores: List[float] = []
        for start in range(0, len(windows), batch_size):
            window_scores.extend(
                self.score_batch(
                    query,
                    windows[start : start + batch_size],
                    batch_size=batch_size,
                )
            )
        return window_scores


class Qwen3LMReranker:
    """Qwen3-Reranker yes/no causal-LM scorer for (query, document) pairs.

    Qwen3-Reranker is a causal LM (not a SequenceClassification head). Scoring
    a pair runs the model once over `<Instruct>... <Query>... <Document>...`
    and reads P("yes") from the last-token logits over the {"yes", "no"} tokens.
    This class wraps that into the same ``rerank_batch(query, passages, ...)``
    surface as ``CrossEncoderReranker`` so callers don't branch.
    """

    _PREFIX = (
        "<|im_start|>system\n"
        "Judge whether the Document meets the requirements based on the Query "
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
        repo_id: Optional[str] = None,
    ):
        """Load the Qwen3 reranker from exactly ``model_name_or_path``, a folder.

        Nothing is downloaded: both ``from_pretrained`` calls pass
        ``local_files_only=True`` after the same folder check the cross-encoder
        uses, so a missing or half-copied folder fails instead of being
        patched from the Hugging Face Hub (issue #812).

        Args:
            model_name_or_path: Local directory holding the Qwen3 reranker
            device: Device to use for inference ('cuda' or 'cpu')
            max_length: Maximum sequence length, prefix and suffix included
            repo_id: Hugging Face repository of the artifact, named in the
                install command when the folder is missing or fails to load

        Raises:
            RuntimeError: When the folder does not exist, is not a directory,
                or fails to load.
        """
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

        path = Path(model_name_or_path)
        remedy = _require_reranker_folder("Qwen3 reranker", path, repo_id)
        logger.info(f"Loading Qwen3-Reranker from {path} on {device}")
        # fp32 on CPU (no native bf16 acceleration on most CPUs); bf16 on CUDA
        # to match Qwen3's native dtype.
        dtype = torch.float32 if device == "cpu" else torch.bfloat16
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(path), padding_side="left", local_files_only=True
            )
            self.model = (
                AutoModelForCausalLM.from_pretrained(
                    str(path), torch_dtype=dtype, local_files_only=True
                )
                .to(device)
                .eval()
            )
        except Exception as exc:
            raise RuntimeError(
                f"Qwen3 reranker failed to load from {MODEL_PATH_SETTING} "
                f"{path}: {str(exc).rstrip('.')}. {remedy}"
            ) from exc

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
        body_budget = (
            self.max_length - len(self._prefix_tokens) - len(self._suffix_tokens)
        )
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
            batch = formatted[start : start + batch_size]
            scores.extend(self._score_batch(batch))
        return scores


# Module-level cache for reranker instances. Loading a 0.6B model is seconds;
# a 4B model is ~10s. Per-query reloads would dominate eval wall time, so we
# keep the instance alive across calls within the process.
# Key includes `device` so a workflow that loads first on (say) MPS doesn't
# silently return that instance to a later caller that requests CPU.
_RERANKER_CACHE: Dict[Tuple[str, str, Optional[str]], Any] = {}


def _get_or_create_reranker(
    model_path: str,
    api_type: str,
    device: Optional[str],
    repo_id: Optional[str] = None,
):
    """Return a cached reranker, constructing it on first request.

    ``repo_id`` only names the install command when a reranker folder is
    missing; it is not part of the cache key.
    """
    key = (model_path, api_type, device)
    cached = _RERANKER_CACHE.get(key)
    if cached is not None:
        return cached

    instance: Union[CrossEncoderReranker, Qwen3LMReranker]
    if api_type == "cross_encoder":
        instance = CrossEncoderReranker(
            model_path=model_path,
            device=device,
            repo_id=repo_id,
        )
    elif api_type == "qwen3_lm":
        instance = Qwen3LMReranker(
            model_name_or_path=model_path,
            device=device,
            repo_id=repo_id,
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
    model_path: str,
    top_k: int = 10,
    alpha: float = 0.3,  # Blend weight for original scores
    batch_size: int = 8,
    use_sliding_window: bool = True,
    api_type: str = "cross_encoder",
    device: Optional[str] = None,
    repo_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Rerank results using a reranker model.

    Args:
        query: The search query
        results: List of result dicts from initial retrieval
                (must contain 'text' and 'score' fields)
        model_path: Local folder holding the reranker model
        top_k: Number of results to return after reranking
        alpha: Weight for original score blending
              final_score = alpha * original_score + (1 - alpha) * reranker_score
        batch_size: Batch size for model inference
        use_sliding_window: Whether to use sliding window for long texts
        api_type: "cross_encoder" (SequenceClassification: DeBERTa-v3, mxbai)
                  or "qwen3_lm" (Qwen3-Reranker yes/no causal-LM)
        device: Device to use for inference
        repo_id: Hugging Face repository of the reranker, named in the
                install command when its folder is missing

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
            repo_id=repo_id,
        )

        # Extract passages from results
        passages = [result.get("text", "") for result in results]
        original_scores = [result.get("score", 0.0) for result in results]

        # Get reranker scores
        reranker_scores = reranker.rerank_batch(
            query=query,
            passages=passages,
            batch_size=batch_size,
            use_sliding_window=use_sliding_window,
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
            reranked_result["original_score"] = result.get("score", 0.0)
            reranked_result["reranker_score"] = reranker_scores[i]
            reranked_result["score"] = score  # Update the main score

            reranked_results.append(reranked_result)

        # Sort by score and limit to top_k
        reranked_results = sorted(
            reranked_results, key=lambda x: x.get("score", 0.0), reverse=True
        )
        reranked_results = reranked_results[:top_k]

        logger.info(
            f"Reranked {len(results)} results to {len(reranked_results)} using cross-encoder"
        )
        return reranked_results

    except Exception as e:
        logger.error(f"Error during reranking: {e}")
        import traceback

        logger.error(traceback.format_exc())

        # Return original results if reranking fails
        logger.warning("Returning original results due to reranking failure")
        return sorted(results, key=lambda x: x.get("score", 0.0), reverse=True)[:top_k]
