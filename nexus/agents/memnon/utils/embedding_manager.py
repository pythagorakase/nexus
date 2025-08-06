"""
Embedding Manager Utility for MEMNON Agent

Handles initialization and usage of sentence transformer embedding models.
"""
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from sentence_transformers import SentenceTransformer

# Assumes MEMNON_SETTINGS is accessible or passed during initialization
# For standalone testing, provide a default or load manually
# REMOVED try...except block for top-level import
# try:
#     from ..memnon import MEMNON_SETTINGS 
# except ImportError:
#     # Fallback for direct execution or testing
#     # In a real scenario, settings should be loaded more robustly
#     MEMNON_SETTINGS = {} 
#     print("Warning: Could not import MEMNON_SETTINGS. Using empty defaults.")

logger = logging.getLogger("nexus.memnon.embedding_manager")

class EmbeddingManager:
    """Manages embedding models for MEMNON."""

    def __init__(self, settings: Dict[str, Any]): # Changed settings to be non-optional
        """
        Initialize the EmbeddingManager.

        Args:
            settings: MEMNON agent settings dictionary. Must be provided.
        """
        if settings is None:
             # This case should ideally not happen if instantiated correctly from MEMNON
             logger.error("EmbeddingManager initialized without settings!")
             self.settings = {}
        else:
             self.settings = settings
             
        self.models: Dict[str, SentenceTransformer] = {}
        self.model_active_status: Dict[str, bool] = {}
        self._initialize_models()

    def _initialize_models(self):
        """Initialize embedding models based on settings."""
        model_configs = self.settings.get("models", {})
        
        if not model_configs:
             logger.warning("No embedding models defined in MEMNON settings. Vector search might be unavailable.")
             # Attempt to load defaults if no config provided
             self._load_default_models()
             return

        # Load each model defined in settings
        for model_name, model_config in model_configs.items():
            # Added: Check if model is explicitly set to active
            is_active = model_config.get("is_active", True) # Default to True if flag is missing
            self.model_active_status[model_name] = is_active
            if not is_active:
                logger.info(f"Skipping initialization for inactive model: {model_name}")
                continue # Skip loading if not active

            logger.info(f"Initializing active model {model_name}...")
            
            local_path = model_config.get("local_path")
            remote_path = model_config.get("remote_path")
            # dimensions = model_config.get("dimensions") # Dimension info not directly used by ST library here

            loaded = False
            # Try loading from local path first
            if local_path:
                local_path_obj = Path(local_path)
                if local_path_obj.exists() and local_path_obj.is_dir():
                    try:
                        model = SentenceTransformer(str(local_path_obj))
                        self.models[model_name] = model
                        logger.info(f"Loaded {model_name} from local path: {local_path}")
                        loaded = True
                    except Exception as e:
                        logger.warning(f"Failed to load {model_name} from local path '{local_path}': {e}")
                else:
                    logger.warning(f"Local path for {model_name} does not exist or is not a directory: {local_path}")
            
            # Fall back to remote path if local failed or wasn't specified
            if not loaded and remote_path:
                try:
                    logger.info(f"Attempting to load {model_name} from remote path: {remote_path}")
                    model = SentenceTransformer(remote_path)
                    self.models[model_name] = model
                    logger.info(f"Loaded {model_name} from remote path: {remote_path}")
                    loaded = True
                except Exception as e:
                    logger.warning(f"Failed to load {model_name} from remote path '{remote_path}': {e}")
            
            if not loaded:
                 logger.error(f"Could not load embedding model '{model_name}' from either local or remote paths.")

        # If absolutely no models were loaded after checking config, try defaults as last resort
        if not self.models:
            logger.warning("No active models loaded from settings, attempting to load hardcoded defaults...")
            # Defaults are assumed active if loaded
            self._load_default_models()
            # Update active status for defaults that were loaded
            for name in self.models:
                 if name not in self.model_active_status:
                      self.model_active_status[name] = True

        active_models = self.get_available_models() # Get filtered list
        if not active_models:
            logger.error("CRITICAL: No ACTIVE embedding models could be loaded. Vector search will be unavailable.")
        else:
            logger.info(f"EmbeddingManager initialized with {len(active_models)} active models: {', '.join(active_models)}")

    def _load_default_models(self):
        """Loads hardcoded default models as a fallback."""
        defaults = {
            "bge-large": "BAAI/bge-large-en",
            "e5-large": "intfloat/e5-large-v2"
        }
        for name, path in defaults.items():
            # Only load if not present AND not explicitly marked inactive in config
            if name not in self.models and self.model_active_status.get(name, True): # Check active status
                try:
                    logger.info(f"Loading default model {name} from {path}")
                    self.models[name] = SentenceTransformer(path)
                    logger.info(f"Successfully loaded default {name}")
                except Exception as e:
                    logger.warning(f"Failed to load default model {name}: {e}")

    def get_model(self, model_key: str) -> Optional[SentenceTransformer]:
        """Get a specific embedding model by key."""
        if not self.model_active_status.get(model_key, False):
             logger.warning(f"Attempted to get inactive model: '{model_key}'")
             return None
        return self.models.get(model_key)

    def get_available_models(self) -> List[str]:
        """Return a list of keys for the loaded models."""
        return [name for name, model in self.models.items() if self.model_active_status.get(name, False)]

    def generate_embedding(self, text: str, model_key: str) -> Optional[List[float]]:
        """
        Generate an embedding for the given text using the specified model.

        Args:
            text: Text to embed.
            model_key: Key of the model to use (must be initialized).

        Returns:
            Embedding as a list of floats, or None if the model is not found or embedding fails.
        """
        model = self.get_model(model_key)
        if not model:
            # get_model already logged warning if inactive
            # logger.error(f"Model '{model_key}' not found or not active.") # Simplified log message
            return None
        
        try:
            # Ensure text is not empty
            if not text or not isinstance(text, str) or not text.strip():
                 logger.warning(f"Attempted to generate embedding for empty or invalid text with model {model_key}. Returning None.")
                 return None

            embedding = model.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating embedding with model '{model_key}': {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    def generate_embeddings_batch(self, texts: List[str], model_key: str) -> Optional[List[List[float]]]:
        """
        Generate embeddings for a batch of texts using the specified model.

        Args:
            texts: List of texts to embed.
            model_key: Key of the model to use.

        Returns:
            List of embeddings, or None if the model is not found or embedding fails.
        """
        model = self.get_model(model_key)
        if not model:
            # get_model already logged warning if inactive
            # logger.error(f"Model '{model_key}' not found or not active for batch generation.")
            return None
            
        # Filter out empty texts before sending to model
        valid_texts = [text for text in texts if text and isinstance(text, str) and text.strip()]
        if not valid_texts:
             logger.warning(f"generate_embeddings_batch called with no valid texts for model {model_key}. Returning empty list.")
             return []
        if len(valid_texts) < len(texts):
             logger.warning(f"Filtered out {len(texts) - len(valid_texts)} empty/invalid texts from batch for model {model_key}.")

        try:
            embeddings = model.encode(valid_texts)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"Error generating batch embeddings with model '{model_key}': {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

# Example usage (for testing purposes)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Testing EmbeddingManager...")
    
    # Create dummy settings if needed (since top-level import was removed)
    # In a real test setup, you might load settings from a file here.
    test_settings = {
        "models": {
             "bge-small-test": {
                 "remote_path": "BAAI/bge-small-en-v1.5", # Use a real small model for testing
                 "local_path": None,
                 "is_active": True
             },
              "nonexistent-model": {
                  "local_path": "/path/does/not/exist",
                   "remote_path": "fake/model-path",
                   "is_active": False
              }
        }
    }

    manager = EmbeddingManager(settings=test_settings)
    
    print(f"Available models: {manager.get_available_models()}")

    test_text = "This is a test sentence."
    model_to_use = "bge-small-test"

    if model_to_use in manager.get_available_models():
        embedding = manager.generate_embedding(test_text, model_to_use)
        if embedding:
            print(f"Generated embedding for '{test_text}' using {model_to_use}:")
            print(f"  Dimensions: {len(embedding)}")
            print(f"  First 5 values: {embedding[:5]}")
        else:
            print(f"Failed to generate embedding for {model_to_use}.")
            
        # Test batch embedding
        batch_texts = ["First sentence.", "", "Third sentence.", "Another test."]
        batch_embeddings = manager.generate_embeddings_batch(batch_texts, model_to_use)
        if batch_embeddings is not None:
             print(f"\nGenerated batch embeddings using {model_to_use}:")
             print(f"  Requested: {len(batch_texts)}, Generated: {len(batch_embeddings)}")
             if batch_embeddings:
                 print(f"  Dimensions of first embedding: {len(batch_embeddings[0])}")
        else:
             print(f"\nFailed to generate batch embeddings for {model_to_use}.")

    else:
         print(f"Model {model_to_use} not available for testing.")

    # Test getting a non-existent model
    print(f"\nAttempting to get non-existent model: {manager.get_model('invalid-key')}")
    print(f"Attempting to generate embedding with non-existent model: {manager.generate_embedding(test_text, 'invalid-key')}")
    
    # Test generating embedding for empty text
    print(f"Attempting to generate embedding for empty text: {manager.generate_embedding('', model_to_use)}") 