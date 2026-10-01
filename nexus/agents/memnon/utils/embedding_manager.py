"""
Embedding Manager Utility for MEMNON Agent

Loads the configured sentence-transformer embedding models from their local
artifact directories only. There is no download path and no default model:
an active model whose ``local_path`` is missing, is not a directory, or fails
to load raises a RuntimeError naming the model, the path and the corrective
command, pinned to the locked revision when one is known (issue #812).
"""

import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from sentence_transformers import SentenceTransformer

from nexus.agents.memnon.utils.artifact_manifest import restore_command

logger = logging.getLogger("nexus.memnon.embedding_manager")

# Process-level cache of loaded SentenceTransformer models, keyed by resolved
# local artifact paths. Mirrors _RERANKER_CACHE in cross_encoder.py.
#
# This cache is load-bearing, not an optimization: the production embedder
# (Octen-Embedding-4B) materializes ~15.5 GB of unified (MPS) memory per
# instance, and the narrative API constructs a fresh LORE -> MEMNON ->
# EmbeddingManager stack for every turn. Those per-turn stacks are reference
# -cycle islands that CPython's throttled full GC does not reclaim mid-run,
# so without sharing, each turn permanently ratchets the server's Metal
# footprint by one full model copy -- exhausting a 128 GB machine at ~8
# turns and hanging the event loop inside Metal allocation (issue #401).
_MODEL_CACHE: Dict[str, SentenceTransformer] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def _cache_key_for_path(path: str) -> str:
    """Normalize local filesystem paths so aliases share one cache entry."""
    path_obj = Path(path)
    if path_obj.exists():
        return str(path_obj.resolve())
    return path


def sentence_transformer_kwargs(device: Optional[str]) -> Dict[str, Any]:
    """Return the keyword arguments the one SentenceTransformer load passes.

    ``local_files_only`` keeps the load off the Hugging Face Hub: an incomplete
    local folder fails instead of being patched from the network.

    Args:
        device: Device to place the model on; None lets sentence-transformers
            choose.

    Returns:
        Keyword arguments for ``SentenceTransformer(path, **kwargs)``
    """
    return {"device": device, "local_files_only": True}


def get_or_load_sentence_transformer(
    path: str, device: Optional[str] = None
) -> SentenceTransformer:
    """Return the process-wide SentenceTransformer for the local ``path``.

    This is the one sentence-transformers embedder loader: the runtime
    EmbeddingManager, the embedding job and the operator scripts all load
    through it. Loads on first request and reuses the same instance for every
    subsequent caller in this process. The lock is held across the load so
    concurrent first requests cannot race two copies of a multi-gigabyte
    model into memory. ``local_files_only`` keeps the load off the network:
    a local artifact that is incomplete fails here instead of being patched
    from the Hugging Face Hub.

    Args:
        path: Local artifact directory
        device: Device to place the model on; None lets sentence-transformers
            choose. A pinned device gets its own cache entry.

    Returns:
        The cached SentenceTransformer
    """
    cache_key = _cache_key_for_path(path)
    if device is not None:
        cache_key = f"{cache_key}|device={device}"
    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(cache_key)
        if model is None:
            model = SentenceTransformer(path, **sentence_transformer_kwargs(device))
            _MODEL_CACHE[cache_key] = model
        else:
            logger.info(f"Reusing process-cached SentenceTransformer: {cache_key}")
        return model


def artifact_remedy(local_path: str, remote_path: Optional[str]) -> str:
    """Name the command that restores and checks a missing local artifact.

    The ``hf download`` command carries ``--revision`` whenever the model
    artifact lock or the folder itself records one. Building it reads the
    lock and the folder, so callers build it only once a load has failed.
    """
    if remote_path:
        restore = f"Restore it with `{restore_command(remote_path, local_path)}`"
    else:
        restore = f"Restore the artifact directory at {local_path}"
    return f"{restore}, then run `nexus models verify`."


def load_local_model(
    model_name: str, model_config: Mapping[str, Any], device: Optional[str] = None
) -> SentenceTransformer:
    """Load one registered model from its local artifact directory or raise.

    Serves the active production embedder and, for operator scripts, any
    other ``[memnon.models]`` entry by its ``local_path``. There is no
    download path: a missing ``local_path``, a missing folder, a file in its
    place, or a folder that fails to load raises with the restore command.

    Args:
        model_name: The ``[memnon.models]`` entry name
        model_config: That entry (``local_path`` and optional ``remote_path``)
        device: Device to place the model on; None lets sentence-transformers
            choose

    Returns:
        The loaded SentenceTransformer

    Raises:
        RuntimeError: When the artifact is not declared, not installed, or
            fails to load.
    """
    local_path = model_config.get("local_path")
    remote_path = model_config.get("remote_path") or None
    if not local_path:
        raise RuntimeError(
            f"Embedding model '{model_name}' declares no local_path in "
            "[memnon.models]; embedders load only from local artifacts."
        )
    path = Path(local_path)
    if not path.exists():
        raise RuntimeError(
            f"Embedding model '{model_name}' is not installed: local_path "
            f"{path} does not exist. {artifact_remedy(str(local_path), remote_path)}"
        )
    if not path.is_dir():
        raise RuntimeError(
            f"Embedding model '{model_name}' local_path {path} is not a "
            f"directory. {artifact_remedy(str(local_path), remote_path)}"
        )
    try:
        model = get_or_load_sentence_transformer(str(path), device=device)
    except Exception as exc:
        raise RuntimeError(
            f"Embedding model '{model_name}' failed to load from local_path "
            f"{path}: {exc}. {artifact_remedy(str(local_path), remote_path)}"
        ) from exc
    logger.info(f"Loaded {model_name} from local path: {path}")
    return model


class EmbeddingManager:
    """Manages embedding models for MEMNON."""

    def __init__(self, settings: Dict[str, Any]):
        """
        Initialize the EmbeddingManager.

        Args:
            settings: MEMNON agent settings dictionary. Must be provided.

        Raises:
            RuntimeError: When no model is active or an active model's local
                artifact is missing or fails to load.
            ValueError: When a model entry omits ``is_active``.
        """
        if settings is None:
            raise ValueError("EmbeddingManager requires the MEMNON settings mapping")
        self.settings = settings

        self.models: Dict[str, SentenceTransformer] = {}
        self.model_active_status: Dict[str, bool] = {}
        self._initialize_models()

    def _initialize_models(self) -> None:
        """Load every active model from its local artifact directory."""
        model_configs = self.settings.get("models") or {}
        if not model_configs:
            raise RuntimeError(
                "No embedding models are configured in [memnon.models]; "
                "declare the production embedder with is_active = true."
            )

        for model_name, model_config in model_configs.items():
            if "is_active" not in model_config:
                raise ValueError(
                    f"Embedding model '{model_name}' in [memnon.models] must "
                    "declare is_active"
                )
            is_active = bool(model_config["is_active"])
            self.model_active_status[model_name] = is_active
            if not is_active:
                logger.info(f"Skipping initialization for inactive model: {model_name}")
                continue

            logger.info(f"Initializing active model {model_name}...")
            self.models[model_name] = load_local_model(model_name, model_config)

        if not self.models:
            raise RuntimeError(
                "No embedding model in [memnon.models] is marked is_active = "
                f"true (configured: {sorted(model_configs)}); vector search "
                "requires the production embedder."
            )
        logger.info(
            f"EmbeddingManager initialized with {len(self.models)} active models: "
            f"{', '.join(self.models)}"
        )

    def get_model(self, model_key: str) -> Optional[SentenceTransformer]:
        """Get a specific embedding model by key."""
        if not self.model_active_status.get(model_key, False):
            logger.warning(f"Attempted to get inactive model: '{model_key}'")
            return None
        return self.models.get(model_key)

    def get_available_models(self) -> List[str]:
        """Return a list of keys for the loaded models."""
        return [
            name
            for name, model in self.models.items()
            if self.model_active_status.get(name, False)
        ]

    def _loaded_model(self, model_key: str) -> SentenceTransformer:
        """Return the loaded, active model ``model_key`` or raise.

        Raises:
            RuntimeError: When ``model_key`` is not a loaded, active model.
        """
        model = self.get_model(model_key)
        if model is None:
            raise RuntimeError(
                f"Embedding model '{model_key}' is not loaded; loaded models: "
                f"{self.get_available_models()}"
            )
        return model

    def generate_embedding(self, text: str, model_key: str) -> List[float]:
        """
        Generate an embedding for the given text using the specified model.

        Args:
            text: Text to embed.
            model_key: Key of the model to use (must be initialized).

        Returns:
            Embedding as a list of floats.

        Raises:
            RuntimeError: When ``model_key`` is not a loaded, active model, or
                the model fails to encode the text (chained from the error).
            ValueError: When ``text`` is empty, blank or not a string.
        """
        model = self._loaded_model(model_key)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"Embedding model '{model_key}' was given empty or non-string "
                f"text: {text!r}"
            )
        try:
            embedding = model.encode(text)
        except Exception as exc:
            raise RuntimeError(
                f"Embedding model '{model_key}' failed to encode: {exc}"
            ) from exc
        return embedding.tolist()

    def generate_embeddings_batch(
        self, texts: List[str], model_key: str
    ) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts using the specified model.

        Args:
            texts: List of texts to embed.
            model_key: Key of the model to use.

        Returns:
            One embedding per input text, in input order; an empty list for an
            empty ``texts``.

        Raises:
            RuntimeError: When ``model_key`` is not a loaded, active model, or
                the model fails to encode the batch (chained from the error).
            ValueError: When any text is empty, blank or not a string; the
                message names the indexes.
        """
        model = self._loaded_model(model_key)
        if not texts:
            return []
        invalid = [
            index
            for index, text in enumerate(texts)
            if not isinstance(text, str) or not text.strip()
        ]
        if invalid:
            raise ValueError(
                f"Embedding model '{model_key}' was given empty or non-string "
                f"texts at indexes {invalid}"
            )
        try:
            embeddings = model.encode(texts)
        except Exception as exc:
            raise RuntimeError(
                f"Embedding model '{model_key}' failed to encode: {exc}"
            ) from exc
        return [emb.tolist() for emb in embeddings]
