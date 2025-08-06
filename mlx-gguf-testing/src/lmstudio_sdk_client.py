"""LM Studio SDK-based client for model testing."""

import lmstudio as lms
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class LMStudioSDKClient:
    """Client for interacting with LM Studio using the official SDK."""
    
    def __init__(self, base_url: str = "http://localhost:1234", 
                 timeout: int = 300, retry_attempts: int = 3, 
                 retry_delay: int = 5):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.current_model = None
        self.current_model_id = None
        
        # Initialize the SDK client
        try:
            self.client = lms.get_client(base_url=base_url)
            logger.info(f"Connected to LM Studio at {base_url}")
        except Exception as e:
            logger.error(f"Failed to connect to LM Studio: {e}")
            raise
    
    def get_models(self) -> List[Dict[str, Any]]:
        """Get list of available models."""
        try:
            # SDK doesn't expose list models directly, return empty for compatibility
            # In practice, we know which models we want to test from config
            return []
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []
    
    def load_model(self, model_id: str) -> bool:
        """Load a model using LM Studio's SDK."""
        logger.info(f"Attempting to load model: {model_id}")
        
        try:
            # First unload any current model
            if self.current_model:
                logger.info(f"Unloading current model: {self.current_model_id}")
                self.unload_model()
                time.sleep(5)  # Give time for memory cleanup
            
            # Load the new model
            logger.info(f"Loading model: {model_id}")
            self.current_model = self.client.llm.load(model_id)
            self.current_model_id = model_id
            
            # Wait a bit for model to fully initialize
            time.sleep(10)
            
            # Verify the model can generate
            logger.info("Verifying model can generate...")
            try:
                result = self.current_model.complete(
                    "Hello",
                    max_tokens=5,
                    temperature=0.1
                )
                if result and result.content:
                    logger.info("Model verification successful")
                    return True
                else:
                    logger.error("Model verification failed: No response")
                    return False
            except Exception as e:
                logger.error(f"Model verification failed: {e}")
                if 'Insufficient Memory' in str(e) or 'kIOGPUCommandBufferCallbackErrorOutOfMemory' in str(e):
                    logger.error("GPU memory exhausted! Model cannot generate.")
                return False
                
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
    
    def unload_model(self, model_id: Optional[str] = None) -> bool:
        """Unload the current model."""
        try:
            if self.current_model:
                logger.info(f"Unloading model: {self.current_model_id}")
                self.current_model.unload()
                self.current_model = None
                self.current_model_id = None
                time.sleep(3)  # Give time for memory cleanup
                return True
            else:
                logger.info("No model currently loaded")
                return True
        except Exception as e:
            logger.warning(f"Error unloading model: {e}")
            return False
    
    def generate(self, model: str, prompt: str, max_tokens: int = 500,
                 temperature: float = 0.7, stream: bool = False,
                 **kwargs) -> Dict[str, Any]:
        """Generate text using the current model."""
        
        # Ensure we're using the right model
        if self.current_model_id != model:
            logger.warning(f"Model mismatch: expected {model}, current {self.current_model_id}")
            if not self.load_model(model):
                return {
                    "error": f"Failed to load model {model}",
                    "model": model,
                    "duration": 0
                }
        
        start_time = time.time()
        
        try:
            if stream:
                return self._generate_stream(prompt, max_tokens, temperature, start_time)
            else:
                return self._generate_sync(prompt, max_tokens, temperature, start_time)
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {
                "error": str(e),
                "model": model,
                "duration": time.time() - start_time
            }
    
    def _generate_sync(self, prompt: str, max_tokens: int, 
                      temperature: float, start_time: float) -> Dict[str, Any]:
        """Synchronous generation."""
        result = self.current_model.complete(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Extract metrics from result
        tokens_generated = len(result.content.split()) if result.content else 0  # Approximate
        
        return {
            "content": result.content,
            "model": self.current_model_id,
            "duration": duration,
            "ttft": None,  # Not available in sync mode
            "tokens_generated": tokens_generated,
            "tokens_per_second": tokens_generated / duration if duration > 0 else 0,
            "prompt_tokens": None,
            "total_tokens": None,
            "usage": {}
        }
    
    def _generate_stream(self, prompt: str, max_tokens: int,
                        temperature: float, start_time: float) -> Dict[str, Any]:
        """Streaming generation with TTFT measurement."""
        content_parts = []
        ttft = None
        tokens = 0
        
        # Use streaming completion
        stream = self.current_model.complete(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True
        )
        
        for chunk in stream:
            if chunk.content:
                if ttft is None:
                    ttft = time.time() - start_time
                content_parts.append(chunk.content)
                tokens += 1
        
        end_time = time.time()
        duration = end_time - start_time
        
        return {
            "content": ''.join(content_parts),
            "model": self.current_model_id,
            "duration": duration,
            "ttft": ttft,
            "tokens_generated": tokens,
            "tokens_per_second": tokens / duration if duration > 0 else 0,
            "prompt_tokens": None,
            "total_tokens": None,
            "usage": {}
        }
    
    def health_check(self) -> bool:
        """Check if LM Studio is accessible."""
        try:
            # Try to get client info
            return self.client is not None
        except:
            return False
    
    def wait_for_ready(self, max_wait: int = 60) -> bool:
        """Wait for LM Studio to be ready."""
        start = time.time()
        while time.time() - start < max_wait:
            if self.health_check():
                logger.info("LM Studio SDK client is ready")
                return True
            time.sleep(2)
        
        logger.error("LM Studio SDK client did not become ready in time")
        return False