"""
Automatic Model Manager for LM Studio

Manages loading/unloading of LLM models based on settings.json configuration.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import lmstudio as lms
    LMS_SDK_AVAILABLE = True
except ImportError:
    LMS_SDK_AVAILABLE = False
    raise RuntimeError("LM Studio SDK is required: pip install lmstudio")

logger = logging.getLogger("nexus.lore.model_manager")


class ModelManager:
    """Manages LM Studio model lifecycle based on settings configuration"""
    
    def __init__(self, settings_path: Optional[str] = None):
        """
        Initialize model manager with settings
        
        Args:
            settings_path: Path to settings.json
        """
        self.settings_path = settings_path or Path(__file__).parent.parent.parent.parent.parent / "settings.json"
        self.settings = self._load_settings()
        
        # Configure LM Studio client (idempotent)
        try:
            # Derive host from settings if available
            lore_llm_cfg = self.settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {})
            base_url = lore_llm_cfg.get("lmstudio_url", "http://localhost:1234/v1")
            host = (
                str(base_url)
                .replace("https://", "")
                .replace("http://", "")
                .replace("/v1", "")
                .strip("/")
            ) or "localhost:1234"
            # Configure only if not already configured. If already configured, ensure host matches.
            try:
                lms.configure_default_client(host)
            except Exception as e:
                if "Default client is already created" in str(e):
                    logger.debug("Default client already exists; verifying connectivity")
                else:
                    raise
        except Exception as e:
            # If default client already exists, reuse it silently
            if "Default client is already created" in str(e):
                logger.debug("Default LM Studio client already configured; reusing existing client")
            else:
                raise
        
        # Track current loaded model
        self.current_model = None
        self.current_model_id = None
        
    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from JSON file"""
        try:
            with open(self.settings_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            raise RuntimeError(f"Cannot load settings from {self.settings_path}")
    
    def _save_settings(self, settings: Dict[str, Any]) -> None:
        """Save settings back to JSON file"""
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=4)
            logger.info(f"Updated settings saved to {self.settings_path}")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            raise RuntimeError(f"Cannot save settings to {self.settings_path}")
    
    def update_available_models(self) -> List[str]:
        """
        Update the possible_values array in settings with available models
        
        Returns:
            List of available model IDs
        """
        logger.info("Checking available LLM models in LM Studio...")
        
        # Get downloaded models
        downloaded_models = lms.list_downloaded_models()
        
        # Filter for LLM models only (not embedding models)
        llm_models = []
        for model in downloaded_models:
            if hasattr(model, 'type') and model.type == 'llm':
                # Get the model key/identifier
                if hasattr(model, 'model_key'):
                    llm_models.append(model.model_key)
                elif hasattr(model, 'id'):
                    llm_models.append(model.id)
                elif hasattr(model, 'path'):
                    # Extract from path if needed
                    llm_models.append(model.path)
        
        if not llm_models:
            logger.warning("No LLM models found in LM Studio!")
            return []
        
        logger.info(f"Found {len(llm_models)} LLM models: {llm_models}")
        
        # Update settings
        model_config = self.settings.get("Agent Settings", {}).get("global", {}).get("model", {})
        current_possible = model_config.get("possible_values", [])
        
        # Update possible_values with available models
        model_config["possible_values"] = llm_models
        
        # Ensure default_model is in the list
        default_model = model_config.get("default_model")
        if default_model and default_model not in llm_models:
            logger.warning(f"Default model '{default_model}' not available in LM Studio")
            if llm_models:
                # Set first available model as default
                model_config["default_model"] = llm_models[0]
                logger.info(f"Updated default_model to: {llm_models[0]}")
        
        # Save updated settings
        self._save_settings(self.settings)
        
        return llm_models
    
    def get_loaded_models(self) -> List[str]:
        """Get currently loaded models in LM Studio"""
        loaded = lms.list_loaded_models()
        if not loaded:
            return []
        
        # Extract model IDs
        model_ids = []
        for model in loaded:
            if hasattr(model, 'id'):
                model_ids.append(model.id)
            elif hasattr(model, 'identifier'):
                model_ids.append(model.identifier)
        
        return model_ids
    
    def unload_model(self, model_id: Optional[str] = None) -> bool:
        """
        Unload a model from LM Studio
        
        Args:
            model_id: Specific model to unload, or None to unload current
            
        Returns:
            True if successful
        """
        try:
            # Check what's currently loaded
            loaded = self.get_loaded_models()
            if not loaded:
                logger.debug("No models currently loaded")
                return True
            
            # Get the model handle if we don't have it
            if not self.current_model:
                self.current_model = lms.llm()
                self.current_model_id = loaded[0] if loaded else None
            
            if self.current_model:
                logger.info(f"Unloading model: {self.current_model_id or loaded[0]}")
                self.current_model.unload()
                self.current_model = None
                self.current_model_id = None
                time.sleep(3)  # Give time for memory cleanup
                logger.info("Model unloaded successfully")
                return True
            else:
                logger.debug("No model handle to unload")
                return True
        except Exception as e:
            logger.error(f"Failed to unload model: {e}")
            return False
    
    def load_model(self, model_id: str) -> bool:
        """
        Load a specific model in LM Studio
        
        Args:
            model_id: Model identifier to load
            
        Returns:
            True if successful
        """
        try:
            logger.info(f"Loading model: {model_id}")
            
            # First unload any existing model
            if self.current_model:
                self.unload_model()
                time.sleep(2)  # Extra time between unload and load
            
            # Get context window from settings
            global_llm_config = self.settings.get("Agent Settings", {}).get("global", {}).get("llm", {})
            context_window = global_llm_config.get("context_window", 65536)
            
            # Load the new model with explicit context window
            logger.info(f"Loading with context_window: {context_window}")
            
            # According to LM Studio docs, context length is set via load options
            # Note: This requires LM Studio SDK v0.3.0+
            try:
                # Try with contextLength option (newer SDK versions)
                self.current_model = lms.llm(model_id, config={"contextLength": context_window})
                logger.info(f"Loaded with contextLength: {context_window}")
            except TypeError:
                # Fall back to basic load if config not supported
                logger.warning("contextLength parameter not supported in this SDK version")
                self.current_model = lms.llm(model_id)
            
            self.current_model_id = model_id
            
            # Wait for model to initialize
            time.sleep(5)
            
            # Verify the model works
            logger.info("Verifying model...")
            chat = lms.Chat("You are a test assistant.")
            chat.add_user_message("Respond with 'OK'")
            
            result = self.current_model.respond(chat, config={"maxTokens": 10})
            if result and result.content:
                logger.info(f"Model {model_id} loaded and verified successfully")
                return True
            else:
                logger.error("Model verification failed: no response")
                return False
                
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return False
    
    def ensure_default_model(self) -> str:
        """
        Ensure the default model from settings is loaded
        
        Returns:
            The loaded model ID
        """
        # Update available models first
        available = self.update_available_models()
        
        if not available:
            raise RuntimeError("No LLM models available in LM Studio!")
        
        # Get the default model from settings
        model_config = self.settings.get("Agent Settings", {}).get("global", {}).get("model", {})
        default_model = model_config.get("default_model")
        
        if not default_model:
            # Use first available model
            default_model = available[0]
            logger.warning(f"No default_model set, using: {default_model}")
        
        # Check what's currently loaded
        loaded = self.get_loaded_models()
        
        if loaded:
            current = loaded[0]  # Assume first loaded model is active
            if current == default_model:
                logger.info(f"Default model {default_model} already loaded")
                # Get the model handle
                self.current_model = lms.llm()
                self.current_model_id = default_model
                return default_model
            else:
                logger.info(f"Current model {current} != default {default_model}")
                # Unload current and load default
                self.unload_model()
        
        # Load the default model
        if self.load_model(default_model):
            return default_model
        else:
            raise RuntimeError(f"Failed to load default model: {default_model}")
    
    def cleanup(self) -> None:
        """Clean up resources - optionally unload model"""
        # Check if we should unload after use
        lore_config = self.settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {})
        if lore_config.get("unload_after_turn", True):
            # Best-effort unload; if ws inactive, skip without warning
            if not self.unload_model():
                logger.debug("Model unload skipped or already inactive")


def main():
    """Test the model manager"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LM Studio Model Manager")
    parser.add_argument("--settings", help="Path to settings.json")
    parser.add_argument("--list", action="store_true", help="List available models")
    parser.add_argument("--loaded", action="store_true", help="Show loaded models")
    parser.add_argument("--ensure", action="store_true", help="Ensure default model is loaded")
    parser.add_argument("--load", help="Load a specific model")
    parser.add_argument("--unload", action="store_true", help="Unload current model")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    manager = ModelManager(args.settings)
    
    if args.list:
        models = manager.update_available_models()
        print("\nAvailable LLM models:")
        for model in models:
            print(f"  - {model}")
    
    elif args.loaded:
        loaded = manager.get_loaded_models()
        if loaded:
            print(f"\nLoaded models: {loaded}")
        else:
            print("\nNo models currently loaded")
    
    elif args.ensure:
        model_id = manager.ensure_default_model()
        print(f"\nDefault model ensured: {model_id}")
    
    elif args.load:
        if manager.load_model(args.load):
            print(f"\nSuccessfully loaded: {args.load}")
        else:
            print(f"\nFailed to load: {args.load}")
    
    elif args.unload:
        if manager.unload_model():
            print("\nModel unloaded")
        else:
            print("\nFailed to unload model")
    
    else:
        # Default action: ensure default model
        model_id = manager.ensure_default_model()
        print(f"\nDefault model loaded: {model_id}")


if __name__ == "__main__":
    main()