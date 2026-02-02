"""
Automatic Model Manager for LM Studio

Manages loading/unloading of LLM models based on configuration.
Uses centralized config loader (nexus.toml with settings.json fallback).
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests

# Import centralized config loader
from nexus.config import load_settings_as_dict

try:
    import lmstudio as lms
    LMS_SDK_AVAILABLE = True
except ImportError:
    LMS_SDK_AVAILABLE = False
    raise RuntimeError("LM Studio SDK is required: pip install lmstudio")

logger = logging.getLogger("nexus.lore.model_manager")


class ModelManager:
    """Manages LM Studio model lifecycle based on settings configuration"""
    
    def __init__(self, settings_path: Optional[str] = None, unload_on_exit: bool = True):
        """
        Initialize model manager with settings

        Args:
            settings_path: Path to config file (optional, uses centralized loader if not specified)
            unload_on_exit: Whether to unload models on cleanup (overrides settings)
        """
        self.settings_path = settings_path
        self.settings = self._load_settings()
        # Store JSON path for save operations (settings.json is still used for model list updates)
        self._json_settings_path = Path(__file__).parent.parent.parent.parent.parent / "settings.json"
        self.unload_on_exit = unload_on_exit
        self.global_llm_config = (
            self.settings
            .get("Agent Settings", {})
            .get("global", {})
            .get("llm", {})
        )
        self.lmstudio_api_base = self._normalize_api_base(self.global_llm_config.get("api_base"))
        
        # Configure LM Studio client (idempotent)
        try:
            # Derive host from settings if available
            lore_llm_cfg = self.settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {})
            base_url = lore_llm_cfg.get("lmstudio_url", f"{self.lmstudio_api_base}/v1")
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
        """Load settings using centralized config loader."""
        try:
            if self.settings_path:
                return load_settings_as_dict(self.settings_path)
            else:
                return load_settings_as_dict()
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            raise RuntimeError(f"Cannot load settings: {e}")
    
    def _save_settings(self, settings: Dict[str, Any]) -> None:
        """Save settings back to JSON file (for model list updates).

        TODO: Migrate to TOML write support when nexus.config gains a save_settings() function.
        Currently writes to settings.json because the centralized loader only reads configs.
        See: https://github.com/pythagorakase/nexus/issues/168
        """
        try:
            with open(self._json_settings_path, 'w') as f:
                json.dump(settings, f, indent=4)
            logger.info(f"Updated settings saved to {self._json_settings_path}")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            raise RuntimeError(f"Cannot save settings to {self._json_settings_path}")

    def _normalize_api_base(self, raw_base: Optional[str]) -> str:
        """Ensure LM Studio API base is scheme://host:port without trailing paths"""
        base = raw_base or "http://localhost:1234"
        base = base.rstrip("/")
        for suffix in ("/v1", "/api/v0"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        return base.rstrip("/")

    def _extract_model_entries(self, payload: Any) -> List[Dict[str, Any]]:
        """Normalize LM Studio model payloads into a list of dict entries."""
        if isinstance(payload, list):
            return [entry for entry in payload if isinstance(entry, dict)]
        if isinstance(payload, dict):
            for key in ("data", "models", "items", "result"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [entry for entry in value if isinstance(entry, dict)]
        return []

    def _extract_loaded_identifiers(self, entries: List[Dict[str, Any]]) -> List[str]:
        loaded: List[str] = []
        for entry in entries:
            state = str(entry.get("state") or entry.get("status") or "").lower()
            is_loaded = entry.get("loaded") or entry.get("isLoaded") or entry.get("active")
            model_type = str(entry.get("type") or entry.get("category") or "").lower()
            if not is_loaded:
                if state not in {"loaded", "ready", "active"}:
                    continue
            if model_type and model_type not in {"llm", "language", "text"}:
                continue
            identifier = (
                entry.get("id")
                or entry.get("identifier")
                or entry.get("model_id")
                or entry.get("name")
                or entry.get("path")
            )
            if identifier:
                loaded.append(str(identifier))
        return loaded

    def _get_loaded_models_via_http(self) -> Optional[List[str]]:
        """Query LM Studio's HTTP API for loaded models."""
        endpoints = [
            f"{self.lmstudio_api_base}/api/v0/models",
            f"{self.lmstudio_api_base}/api/v0/models/list",
            f"{self.lmstudio_api_base}/api/models",
            f"{self.lmstudio_api_base}/models",
        ]
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, timeout=5)
                if response.status_code == 404:
                    logger.debug(f"LM Studio endpoint {endpoint} returned 404; trying next fallback")
                    continue
                response.raise_for_status()
                payload = response.json()
                entries = self._extract_model_entries(payload)
                if not entries:
                    logger.debug(f"LM Studio endpoint {endpoint} returned no model entries")
                return self._extract_loaded_identifiers(entries)
            except requests.RequestException as http_error:
                logger.warning(f"Failed to query LM Studio via {endpoint}: {http_error}")
            except ValueError as json_error:
                logger.warning(f"Invalid LM Studio response from {endpoint}: {json_error}")
        return None

    def _get_loaded_models_via_sdk(self) -> List[str]:
        """Fallback to LM Studio's Python SDK if HTTP probing fails."""
        try:
            loaded = lms.list_loaded_models()
        except Exception as sdk_error:
            logger.error(f"LM Studio SDK list_loaded_models failed: {sdk_error}")
            return []
        
        identifiers: List[str] = []
        for model in loaded or []:
            if hasattr(model, 'id') and model.id:
                identifiers.append(model.id)
            elif hasattr(model, 'identifier') and model.identifier:
                identifiers.append(model.identifier)
            elif hasattr(model, 'model_id') and model.model_id:
                identifiers.append(model.model_id)
        return identifiers
    
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
        
        # TODO: Re-enable when migrated to TOML write support
        # Currently disabled to prevent unintended settings.json rewrites
        # self._save_settings(self.settings)

        return llm_models
    
    def get_loaded_models(self) -> List[str]:
        """Get currently loaded models in LM Studio.

        Prefer the HTTP API (so manual loads via the desktop UI are detected),
        then fall back to the SDK if HTTP probing fails entirely.
        """
        http_result = self._get_loaded_models_via_http()
        if http_result is not None:
            return http_result
        return self._get_loaded_models_via_sdk()
    
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
    
    def load_model(self, model_id: str, context_window: Optional[int] = None) -> bool:
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
            
            # Get context window from settings when not explicitly provided
            if context_window is None:
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
                # Only unload if we're supposed to manage model lifecycle
                if self.unload_on_exit:
                    # Unload current and load default
                    self.unload_model()
                else:
                    logger.info("Keeping current model due to unload_on_exit=False")
                    # Return the current model instead of switching
                    self.current_model = lms.llm()
                    self.current_model_id = current
                    return current
        
        # Load the default model
        if self.load_model(default_model):
            return default_model
        else:
            raise RuntimeError(f"Failed to load default model: {default_model}")
    
    def cleanup(self) -> None:
        """Clean up resources - optionally unload model"""
        # Check if we should unload after use
        # Runtime flag overrides settings
        if not self.unload_on_exit:
            logger.debug("Model unload skipped due to unload_on_exit=False")
            return
            
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
