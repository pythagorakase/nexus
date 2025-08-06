#!/usr/bin/env python3
"""
MEMNON Diagnostic Test Script

This script tests individual components of the MEMNON implementation 
to identify where the issues might be occurring.
"""

import os
import sys
import json
import logging
import traceback
import time
from typing import Dict, Any, List, Optional
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("memnon_test.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("memnon-test")

# Add nexus directory to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def load_settings() -> Dict[str, Any]:
    """Load settings from settings.json file"""
    try:
        settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                logger.info(f"Successfully loaded settings from {settings_path}")
                return settings
        else:
            logger.warning(f"Warning: settings.json not found at {settings_path}")
            return {}
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return {}


def test_db_connection(db_url: str) -> bool:
    """Test database connection"""
    logger.info(f"Testing database connection to {db_url}")
    
    try:
        from sqlalchemy import create_engine, text
        
        engine = create_engine(db_url)
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).fetchone()
            if result and result[0] == 1:
                logger.info("Database connection successful!")
                return True
            else:
                logger.error("Database connection test failed!")
                return False
                
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False


def test_embedding_models(model_paths: Dict[str, str]) -> bool:
    """Test loading of embedding models"""
    logger.info("Testing embedding model loading")
    
    try:
        from sentence_transformers import SentenceTransformer
        
        for model_name, model_path in model_paths.items():
            logger.info(f"Attempting to load {model_name} from {model_path}")
            
            try:
                if not model_path or not os.path.exists(model_path):
                    logger.warning(f"Model path does not exist: {model_path}")
                    continue
                    
                model = SentenceTransformer(model_path)
                embedding = model.encode("Test sentence for embedding")
                
                logger.info(f"Successfully loaded {model_name} model")
                logger.info(f"Generated embedding with shape: {embedding.shape}")
                
            except Exception as e:
                logger.error(f"Error loading {model_name} model: {e}")
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"General error in embedding test: {e}")
        return False


def test_llm_api(api_url: str, model_id: str) -> bool:
    """Test connection to LM Studio API"""
    logger.info(f"Testing LLM API connection to {api_url}")
    
    try:
        import requests
        
        # Test models endpoint first
        try:
            logger.info("Testing models endpoint")
            response = requests.get(f"{api_url}/v1/models", timeout=5)
            
            if response.status_code == 200:
                logger.info(f"Successfully connected to models endpoint: {response.json()}")
            else:
                logger.warning(f"Models endpoint returned status code: {response.status_code}")
        except Exception as e:
            logger.warning(f"Error connecting to models endpoint: {e}")
        
        # Test completions endpoint with a simple prompt
        try:
            logger.info(f"Testing completions endpoint with model: {model_id}")
            
            payload = {
                "model": model_id,
                "prompt": "Hello, how are you?",
                "temperature": 0.2,
                "max_tokens": 20,
                "stream": False
            }
            
            response = requests.post(
                f"{api_url}/v1/completions", 
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30  # Longer timeout for model loading
            )
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"Successfully got completions response: {response_data}")
                return True
            else:
                logger.warning(f"Completions endpoint returned status code: {response.status_code}")
                logger.warning(f"Response: {response.text}")
                
                # Try chat completions as fallback
                logger.info("Testing chat completions endpoint")
                
                chat_payload = {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Hello, how are you?"}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 20
                }
                
                response = requests.post(
                    f"{api_url}/v1/chat/completions", 
                    json=chat_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    logger.info(f"Successfully got chat completions response: {response_data}")
                    return True
                else:
                    logger.warning(f"Chat completions endpoint returned status code: {response.status_code}")
                    logger.warning(f"Response: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error testing completions endpoint: {e}")
            return False
            
    except Exception as e:
        logger.error(f"General error in LLM API test: {e}")
        return False


def test_memnon_initialization() -> bool:
    """Test MEMNON initialization in isolation"""
    try:
        from nexus.agents.memnon.memnon import MEMNON
        
        # Create a simple interface
        class SimpleInterface:
            def assistant_message(self, message):
                print(f"Message: {message}")
        
        # Load settings
        settings = load_settings()
        memnon_settings = settings.get("Agent Settings", {}).get("MEMNON", {})
        global_settings = settings.get("Agent Settings", {}).get("global", {})
        
        # Get parameters
        db_url = memnon_settings.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
        model_id = global_settings.get("model", {}).get("default_model", "llama-3.3-70b-instruct@q6_k")
        
        logger.info(f"Initializing MEMNON with: db_url={db_url}, model_id={model_id}")
        
        # Initialize MEMNON
        memnon = MEMNON(
            interface=SimpleInterface(),
            agent_state=None,
            user=None,
            db_url=db_url,
            model_id=model_id,
            debug=True
        )
        
        logger.info("MEMNON agent initialized successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing MEMNON: {e}")
        traceback.print_exc()
        return False


def test_status_command() -> bool:
    """Test the status command"""
    try:
        from nexus.agents.memnon.memnon import MEMNON
        
        # Create a simple interface
        class SimpleInterface:
            def assistant_message(self, message):
                print(f"Message: {message}")
        
        # Load settings
        settings = load_settings()
        memnon_settings = settings.get("Agent Settings", {}).get("MEMNON", {})
        global_settings = settings.get("Agent Settings", {}).get("global", {})
        
        # Get parameters
        db_url = memnon_settings.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
        model_id = global_settings.get("model", {}).get("default_model", "llama-3.3-70b-instruct@q6_k")
        
        logger.info(f"Initializing MEMNON for status command test")
        
        # Initialize MEMNON
        memnon = MEMNON(
            interface=SimpleInterface(),
            agent_state=None,
            user=None,
            db_url=db_url,
            model_id=model_id,
            debug=True
        )
        
        # Get status
        logger.info("Getting MEMNON status")
        status = memnon._get_status()
        
        logger.info(f"Status response: {status}")
        return True
        
    except Exception as e:
        logger.error(f"Error testing status command: {e}")
        traceback.print_exc()
        return False


def main():
    """Run diagnostic tests"""
    print("\n🧠 MEMNON Diagnostic Test 🧠")
    print("=========================")
    
    # Load settings
    settings = load_settings()
    memnon_settings = settings.get("Agent Settings", {}).get("MEMNON", {})
    global_settings = settings.get("Agent Settings", {}).get("global", {})
    
    # Extract relevant settings
    db_url = memnon_settings.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
    model_id = global_settings.get("model", {}).get("default_model", "llama-3.3-70b-instruct@q6_k")
    llm_api_base = memnon_settings.get("llm", {}).get("api_base", "http://localhost:1234")
    
    # Get embedding model configurations
    model_paths = {}
    for model_name, model_config in memnon_settings.get("models", {}).items():
        model_paths[model_name] = model_config.get("local_path")
    
    # Run tests
    print("\n1. Testing Database Connection...")
    db_ok = test_db_connection(db_url)
    print(f"Database Connection Test: {'PASSED' if db_ok else 'FAILED'}\n")
    
    print("2. Testing Embedding Models...")
    embeddings_ok = test_embedding_models(model_paths)
    print(f"Embedding Models Test: {'PASSED' if embeddings_ok else 'FAILED'}\n")
    
    print("3. Testing LLM API Connection...")
    llm_ok = test_llm_api(llm_api_base, model_id)
    print(f"LLM API Test: {'PASSED' if llm_ok else 'FAILED'}\n")
    
    print("4. Testing MEMNON Initialization...")
    init_ok = test_memnon_initialization()
    print(f"MEMNON Initialization Test: {'PASSED' if init_ok else 'FAILED'}\n")
    
    if init_ok:
        print("5. Testing Status Command...")
        status_ok = test_status_command()
        print(f"Status Command Test: {'PASSED' if status_ok else 'FAILED'}\n")
    
    # Summary
    print("\nDiagnostic Test Summary:")
    print("-----------------------")
    print(f"Database Connection: {'✅' if db_ok else '❌'}")
    print(f"Embedding Models:    {'✅' if embeddings_ok else '❌'}")
    print(f"LLM API:            {'✅' if llm_ok else '❌'}")
    print(f"MEMNON Init:        {'✅' if init_ok else '❌'}")
    if init_ok:
        print(f"Status Command:     {'✅' if status_ok else '❌'}")
    
    print("\nCheck memnon_test.log for detailed logs")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Critical error in main: {e}")
        traceback.print_exc()