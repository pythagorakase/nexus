"""LM Studio API client for model testing."""

import requests
import json
import time
import logging
from typing import Dict, Any, Optional, Generator, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class LMStudioClient:
    """Client for interacting with LM Studio API."""
    
    def __init__(self, base_url: str = "http://localhost:1234", 
                 timeout: int = 300, retry_attempts: int = 3, 
                 retry_delay: int = 5):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=retry_attempts,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def get_models(self) -> List[Dict[str, Any]]:
        """Get list of available models."""
        try:
            response = self.session.get(
                f"{self.base_url}/v1/models",
                timeout=10
            )
            response.raise_for_status()
            return response.json().get('data', [])
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []
    
    def load_model(self, model_id: str) -> bool:
        """Load a model using LM Studio's API."""
        logger.info(f"Attempting to load model: {model_id}")
        
        # First check if model is already loaded
        current_models = self.get_models()
        for model in current_models:
            if model.get('id') == model_id:
                logger.info(f"Model {model_id} is already loaded")
                return True
        
        # Unload any currently loaded model first
        if current_models:
            logger.info("Unloading current model before loading new one")
            self.unload_model()
            time.sleep(3)
        
        # Load the new model
        try:
            # LM Studio uses POST /v1/models/load
            response = self.session.post(
                f"{self.base_url}/v1/models/load",
                json={
                    "model": model_id,
                    "gpu_layers": -1  # Use all available GPU layers
                },
                timeout=180  # Loading large models can take time
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully initiated loading of model: {model_id}")
                # Wait for model to be fully loaded
                if self.wait_for_model_ready(model_id, max_wait=120):
                    logger.info(f"Model {model_id} is fully loaded and ready")
                    # Extra wait to ensure model is fully initialized
                    time.sleep(10)
                    
                    # Verify the model can actually generate
                    logger.info("Verifying model can generate...")
                    try:
                        test_result = self.generate(
                            model=model_id,
                            prompt="Hello",
                            max_tokens=5,
                            temperature=0.1
                        )
                        if 'error' not in test_result:
                            logger.info("Model verification successful")
                            return True
                        else:
                            error_msg = test_result.get('error', '')
                            logger.error(f"Model verification failed: {error_msg}")
                            # Check for GPU memory issues
                            if 'Insufficient Memory' in error_msg or 'kIOGPUCommandBufferCallbackErrorOutOfMemory' in error_msg:
                                logger.error("GPU memory exhausted! Model cannot generate.")
                            return False
                    except Exception as e:
                        logger.error(f"Model verification failed with exception: {e}")
                        # Check if it's a GPU memory issue
                        if 'Insufficient Memory' in str(e):
                            logger.error("GPU memory exhausted! Model cannot generate.")
                        return False
                else:
                    logger.error(f"Model {model_id} failed to become ready")
                    return False
            else:
                logger.error(f"Failed to load model: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
    
    def unload_model(self, model_id: Optional[str] = None) -> bool:
        """Unload the current model."""
        # Note: LM Studio doesn't have a direct unload endpoint
        # We can try to load a small embedding model to free up memory
        try:
            logger.info("Unloading models by loading a small embedding model...")
            # Load a small embedding model to clear the LLM from memory
            response = self.session.post(
                f"{self.base_url}/v1/models/load",
                json={"model": "text-embedding-bge-small-en-v1.5"},
                timeout=30
            )
            
            if response.status_code in [200, 201, 204]:
                logger.info("Successfully unloaded model")
                time.sleep(3)  # Give it time to clean up memory
                return True
            else:
                logger.warning(f"Failed to unload model: {response.status_code}")
                return False
                
        except Exception as e:
            logger.warning(f"Error unloading model: {e}")
            return False
    
    def wait_for_model_ready(self, model_id: str, max_wait: int = 60) -> bool:
        """Wait for a specific model to be loaded and ready."""
        start = time.time()
        while time.time() - start < max_wait:
            models = self.get_models()
            for model in models:
                if model.get('id') == model_id:
                    # Check if it's an embedding model
                    if 'embedding' in model_id.lower():
                        logger.warning(f"Model {model_id} appears to be an embedding model, not a chat model")
                    logger.info(f"Model {model_id} is ready")
                    return True
            time.sleep(2)
        
        logger.error(f"Model {model_id} did not become ready in time")
        return False
    
    def generate(self, model: str, prompt: str, max_tokens: int = 500,
                 temperature: float = 0.7, stream: bool = False,
                 **kwargs) -> Dict[str, Any]:
        """Generate text using the specified model."""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        # Log the request for debugging
        logger.debug(f"Sending request with model: {model}")
        logger.debug(f"Request payload: messages={payload['messages']}, max_tokens={payload['max_tokens']}, temperature={payload['temperature']}")
        
        start_time = time.time()
        
        try:
            if stream:
                return self._generate_stream(payload, start_time)
            else:
                return self._generate_sync(payload, start_time)
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {
                "error": str(e),
                "model": model,
                "duration": time.time() - start_time
            }
    
    def _generate_sync(self, payload: Dict[str, Any], start_time: float) -> Dict[str, Any]:
        """Synchronous generation."""
        response = self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=self.timeout
        )
        
        # Better error handling for 400 errors
        if response.status_code == 400:
            try:
                error_detail = response.json() if response.text else {}
                logger.error(f"Bad Request: {error_detail}")
                # Handle case where error is a string or empty dict
                if isinstance(error_detail.get('error'), str):
                    error_msg = error_detail.get('error') or 'Unknown error'
                else:
                    error_msg = error_detail.get('error', {}).get('message', 'Unknown error')
                raise requests.HTTPError(f"400 Bad Request: {error_msg}")
            except ValueError:
                raise requests.HTTPError(f"400 Bad Request: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        end_time = time.time()
        
        # Extract metrics
        completion = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        usage = result.get('usage', {})
        
        return {
            "content": completion,
            "model": payload['model'],
            "duration": end_time - start_time,
            "ttft": None,  # Not available in sync mode
            "tokens_generated": usage.get('completion_tokens', 0),
            "tokens_per_second": usage.get('completion_tokens', 0) / (end_time - start_time),
            "prompt_tokens": usage.get('prompt_tokens', 0),
            "total_tokens": usage.get('total_tokens', 0),
            "usage": usage
        }
    
    def _generate_stream(self, payload: Dict[str, Any], start_time: float) -> Dict[str, Any]:
        """Streaming generation with TTFT measurement."""
        response = self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=self.timeout,
            stream=True
        )
        
        # Better error handling for 400 errors
        if response.status_code == 400:
            try:
                error_detail = response.json() if response.text else {}
                logger.error(f"Bad Request: {error_detail}")
                # Handle case where error is a string or empty dict
                if isinstance(error_detail.get('error'), str):
                    error_msg = error_detail.get('error') or 'Unknown error'
                else:
                    error_msg = error_detail.get('error', {}).get('message', 'Unknown error')
                raise requests.HTTPError(f"400 Bad Request: {error_msg}")
            except ValueError:
                raise requests.HTTPError(f"400 Bad Request: {response.text}")
        
        response.raise_for_status()
        
        content = []
        ttft = None
        tokens = 0
        
        for line in response.iter_lines():
            if not line:
                continue
                
            line = line.decode('utf-8')
            if line.startswith('data: '):
                if line.strip() == 'data: [DONE]':
                    break
                    
                try:
                    data = json.loads(line[6:])
                    chunk = data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                    
                    if chunk:
                        if ttft is None:
                            ttft = time.time() - start_time
                        content.append(chunk)
                        tokens += 1
                except json.JSONDecodeError:
                    continue
        
        end_time = time.time()
        duration = end_time - start_time
        
        return {
            "content": ''.join(content),
            "model": payload['model'],
            "duration": duration,
            "ttft": ttft,
            "tokens_generated": tokens,
            "tokens_per_second": tokens / duration if duration > 0 else 0,
            "prompt_tokens": None,  # Not available in stream mode
            "total_tokens": None,
            "usage": {}
        }
    
    def health_check(self) -> bool:
        """Check if LM Studio API is accessible."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def wait_for_ready(self, max_wait: int = 60) -> bool:
        """Wait for LM Studio API to be ready."""
        start = time.time()
        while time.time() - start < max_wait:
            if self.health_check():
                logger.info("LM Studio API is ready")
                return True
            time.sleep(2)
        
        logger.error("LM Studio API did not become ready in time")
        return False