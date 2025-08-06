#!/usr/bin/env python3
"""Utility script to clean up any loaded models in LM Studio."""

import sys
import time
import logging
from src.lmstudio_sdk_client_v2 import LMStudioSDKClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_all_models():
    """Clean up all loaded models with verification."""
    try:
        client = LMStudioSDKClient()
        
        # Check current state
        loaded_models = client.get_models()
        if not loaded_models:
            logger.info("No models are currently loaded")
            return True
            
        logger.info(f"Found {len(loaded_models)} loaded models:")
        for model in loaded_models:
            logger.info(f"  - {model['id']}")
        
        # Unload each model
        logger.info("\nUnloading models...")
        for model in loaded_models:
            model_id = model['id']
            logger.info(f"Unloading: {model_id}")
            success = client.unload_model(model_id)
            if not success:
                logger.error(f"Failed to unload {model_id}")
        
        # Wait for cleanup
        logger.info("Waiting 15 seconds for memory cleanup...")
        time.sleep(15)
        
        # Verify all unloaded
        remaining = client.get_models()
        if remaining:
            logger.error(f"Failed to unload all models. Still loaded: {[m['id'] for m in remaining]}")
            return False
        else:
            logger.info("✓ All models successfully unloaded")
            return True
            
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return False


if __name__ == "__main__":
    success = cleanup_all_models()
    sys.exit(0 if success else 1)