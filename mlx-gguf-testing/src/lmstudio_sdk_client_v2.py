"""LM Studio SDK-based client with proper resource management and error handling."""

import lmstudio as lms
import time
import logging
from typing import Dict, Any, List, Optional, Generator
from contextlib import contextmanager
from dataclasses import dataclass
import threading

logger = logging.getLogger(__name__)


@dataclass
class ModelLoadState:
    """Track model loading state."""
    model_id: str
    model_instance: Any
    load_time: float
    context_length: Optional[int] = None
    

class LMStudioSDKClient:
    """SDK-based client with proper resource management and GPU memory handling."""
    
    def __init__(self, base_url: str = "http://localhost:1234", 
                 timeout: int = 300, retry_attempts: int = 3, 
                 retry_delay: int = 5, memory_cleanup_delay: int = 10):
        """Initialize SDK client with configuration.
        
        Args:
            base_url: LM Studio server URL
            timeout: Timeout for operations in seconds
            retry_attempts: Number of retry attempts for failed operations
            retry_delay: Delay between retries in seconds
            memory_cleanup_delay: Delay after unload for memory cleanup
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.memory_cleanup_delay = memory_cleanup_delay
        
        # Model state tracking
        self._current_model: Optional[ModelLoadState] = None
        self._lock = threading.Lock()
        
        # Initialize SDK client
        try:
            # Extract host and port from base_url
            # Remove http:// or https:// prefix
            clean_url = base_url.replace('http://', '').replace('https://', '')
            
            # Create a new client instance with the cleaned URL
            self.client = lms.Client(api_host=clean_url)
            logger.info(f"Connected to LM Studio SDK at {clean_url}")
        except Exception as e:
            logger.error(f"Failed to connect to LM Studio: {e}")
            raise ConnectionError(f"Cannot connect to LM Studio at {base_url}: {e}")
    
    @contextmanager
    def loaded_model(self, model_id: str):
        """Context manager for model loading with automatic cleanup.
        
        Usage:
            with client.loaded_model("model-id") as model:
                result = model.complete("Hello")
        """
        model = None
        try:
            model = self._load_model_with_retry(model_id)
            yield model
        finally:
            if model:
                self._unload_model_safe(model_id)
    
    def _load_model_with_retry(self, model_id: str) -> Any:
        """Load model with retry logic and GPU memory handling."""
        last_error = None
        
        for attempt in range(self.retry_attempts):
            try:
                logger.info(f"Loading model {model_id} (attempt {attempt + 1}/{self.retry_attempts})")
                
                # First ensure any existing model is unloaded
                with self._lock:
                    if self._current_model:
                        logger.info(f"Unloading existing model: {self._current_model.model_id}")
                        self._unload_model_internal()
                
                # Attempt to load the model
                start_time = time.time()
                model = self.client.llm.load_new_instance(model_id)
                load_time = time.time() - start_time
                
                # Get model info
                try:
                    model_info = model.get_info()
                    context_length = model_info.get('context_length', 4096)
                except:
                    context_length = 4096
                
                # Store model state
                with self._lock:
                    self._current_model = ModelLoadState(
                        model_id=model_id,
                        model_instance=model,
                        load_time=load_time,
                        context_length=context_length
                    )
                
                # Verify model can generate
                logger.info("Verifying model can generate...")
                try:
                    # Use config object for parameters
                    config = {"maxTokens": 5, "temperature": 0.1}
                    test_result = model.complete("Hello", config=config)
                    if test_result and test_result.content:
                        logger.info(f"Model loaded successfully in {load_time:.2f}s")
                        return model
                    else:
                        raise ValueError("Model verification failed: No response")
                        
                except Exception as e:
                    if self._is_gpu_memory_error(str(e)):
                        logger.warning(f"GPU memory exhausted during verification: {e}")
                        # Unload and retry with more cleanup time
                        self._unload_model_internal()
                        time.sleep(self.memory_cleanup_delay * 2)
                        raise
                    else:
                        raise
                        
            except Exception as e:
                last_error = e
                logger.error(f"Failed to load model on attempt {attempt + 1}: {e}")
                
                if self._is_gpu_memory_error(str(e)):
                    # For GPU memory errors, wait longer between retries
                    logger.info(f"Waiting {self.memory_cleanup_delay * 2}s for GPU memory cleanup...")
                    time.sleep(self.memory_cleanup_delay * 2)
                else:
                    time.sleep(self.retry_delay)
        
        raise RuntimeError(f"Failed to load model {model_id} after {self.retry_attempts} attempts: {last_error}")
    
    def _unload_model_internal(self):
        """Internal method to unload current model."""
        if self._current_model and self._current_model.model_instance:
            try:
                self._current_model.model_instance.unload()
                logger.info(f"Unloaded model: {self._current_model.model_id}")
            except Exception as e:
                logger.warning(f"Error during unload: {e}")
            finally:
                self._current_model = None
    
    def _unload_model_safe(self, model_id: str):
        """Safely unload model with cleanup delay."""
        with self._lock:
            if self._current_model and self._current_model.model_id == model_id:
                self._unload_model_internal()
                # Wait for memory cleanup
                logger.info(f"Waiting {self.memory_cleanup_delay}s for memory cleanup...")
                time.sleep(self.memory_cleanup_delay)
    
    def _is_gpu_memory_error(self, error_msg: str) -> bool:
        """Check if error is related to GPU memory exhaustion."""
        gpu_error_patterns = [
            'Insufficient Memory',
            'kIOGPUCommandBufferCallbackErrorOutOfMemory',
            'out of memory',
            'GPU memory',
            'Metal memory'
        ]
        return any(pattern.lower() in error_msg.lower() for pattern in gpu_error_patterns)
    
    def get_models(self) -> List[Dict[str, Any]]:
        """Get list of currently loaded models."""
        try:
            loaded_models = self.client.list_loaded_models()
            result = [{"id": model.identifier, "loaded": True} for model in loaded_models]
            
            # Log for debugging
            if result:
                logger.debug(f"Currently loaded models: {[m['id'] for m in result]}")
            else:
                logger.debug("No models currently loaded")
                
            return result
        except Exception as e:
            logger.error(f"Failed to list loaded models: {e}")
            return []
    
    def load_model(self, model_id: str) -> bool:
        """Load a model (legacy interface for compatibility)."""
        try:
            self._load_model_with_retry(model_id)
            return True
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return False
    
    def unload_model(self, model_id: Optional[str] = None) -> bool:
        """Unload model (legacy interface for compatibility)."""
        try:
            # First check if any models are loaded via SDK
            loaded_models = self.client.list_loaded_models()
            
            if model_id:
                # Unload specific model
                for model in loaded_models:
                    if model.identifier == model_id:
                        logger.info(f"Found model {model_id} to unload")
                        model.unload()
                        time.sleep(self.memory_cleanup_delay)
                        
                        # Also clear our internal state if it matches
                        with self._lock:
                            if self._current_model and self._current_model.model_id == model_id:
                                self._current_model = None
                        return True
                        
                logger.warning(f"Model {model_id} not found in loaded models")
                return False
            else:
                # Unload all models
                if loaded_models:
                    logger.info(f"Unloading {len(loaded_models)} models")
                    for model in loaded_models:
                        model.unload()
                    time.sleep(self.memory_cleanup_delay)
                    
                # Clear internal state
                with self._lock:
                    self._current_model = None
                    
                return True
                
        except Exception as e:
            logger.error(f"Failed to unload model: {e}")
            return False
    
    def generate(self, model: str, prompt: str, max_tokens: int = 500,
                 temperature: float = 0.7, stream: bool = False,
                 **kwargs) -> Dict[str, Any]:
        """Generate text using the loaded model."""
        start_time = time.time()
        
        # First check if model is loaded via SDK
        loaded_models = self.client.list_loaded_models()
        model_instance = None
        
        for loaded_model in loaded_models:
            if loaded_model.identifier == model:
                model_instance = loaded_model
                break
        
        if not model_instance:
            logger.warning(f"Model not loaded: {model}")
            return {
                "error": f"Model {model} not loaded",
                "model": model,
                "duration": time.time() - start_time
            }
        
        try:
            if stream:
                return self._generate_stream(model_instance, prompt, max_tokens, 
                                           temperature, start_time, model)
            else:
                return self._generate_sync(model_instance, prompt, max_tokens, 
                                         temperature, start_time, model)
        except Exception as e:
            error_msg = str(e)
            if self._is_gpu_memory_error(error_msg):
                logger.error(f"GPU memory exhausted during generation: {e}")
                error_msg = f"GPU memory exhausted: {error_msg}"
            else:
                logger.error(f"Generation failed: {e}")
            
            return {
                "error": error_msg,
                "model": model,
                "duration": time.time() - start_time
            }
    
    def _generate_sync(self, model_instance: Any, prompt: str, max_tokens: int,
                      temperature: float, start_time: float, model_id: str) -> Dict[str, Any]:
        """Synchronous text generation."""
        # Use config object for parameters
        config = {"maxTokens": max_tokens, "temperature": temperature}
        result = model_instance.complete(prompt, config=config)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Get content and statistics from the result
        content = result.content or ""
        stats = result.stats
        
        # Use actual token counts from SDK statistics
        tokens_generated = stats.predicted_tokens_count or 0
        prompt_tokens = stats.prompt_tokens_count or 0
        total_tokens = stats.total_tokens_count or 0
        
        # Use SDK-provided tokens per second if available
        tokens_per_second = stats.tokens_per_second or (tokens_generated / duration if duration > 0 else 0)
        
        return {
            "content": content,
            "model": model_id,
            "duration": duration,
            "ttft": stats.time_to_first_token_sec,  # Available from stats
            "tokens_generated": tokens_generated,
            "tokens_per_second": tokens_per_second,
            "prompt_tokens": prompt_tokens,
            "total_tokens": total_tokens,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": tokens_generated,
                "total_tokens": total_tokens
            }
        }
    
    def _generate_stream(self, model_instance: Any, prompt: str, max_tokens: int,
                        temperature: float, start_time: float, model_id: str) -> Dict[str, Any]:
        """Streaming text generation with TTFT measurement."""
        content_parts = []
        ttft = None
        last_result = None
        
        # Create streaming completion
        config = {"maxTokens": max_tokens, "temperature": temperature}
        stream = model_instance.complete_stream(prompt, config=config)
        
        for chunk in stream:
            if chunk.content:
                if ttft is None:
                    ttft = time.time() - start_time
                content_parts.append(chunk.content)
            # Keep the last chunk which should have final statistics
            last_result = chunk
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Get the full generated content
        full_content = ''.join(content_parts)
        
        # Try to get statistics from the final chunk or collect it separately
        stats = None
        if hasattr(last_result, 'stats'):
            stats = last_result.stats
            
        if stats:
            tokens_generated = stats.predicted_tokens_count or 0
            prompt_tokens = stats.prompt_tokens_count or 0
            total_tokens = stats.total_tokens_count or 0
            tokens_per_second = stats.tokens_per_second or (tokens_generated / duration if duration > 0 else 0)
            # Use SDK's TTFT if available and ours isn't
            if stats.time_to_first_token_sec and not ttft:
                ttft = stats.time_to_first_token_sec
            logger.debug(f"Got stats from stream: tokens={tokens_generated}, tps={tokens_per_second}")
        else:
            # Streaming might not provide stats per chunk
            # Let's count actual tokens using the model's tokenizer
            try:
                tokens_generated = model_instance.count_tokens(full_content)
                prompt_token_count = model_instance.count_tokens(prompt)
                prompt_tokens = prompt_token_count
                total_tokens = prompt_tokens + tokens_generated
                # Calculate tokens/sec excluding TTFT (time spent processing prompt)
                generation_time = duration - ttft if ttft else duration
                tokens_per_second = tokens_generated / generation_time if generation_time > 0 else 0
                logger.debug(f"Counted tokens using tokenizer: {tokens_generated}, gen_time: {generation_time:.2f}s")
            except:
                # Final fallback to approximation
                tokens_generated = len(full_content) // 4
                if full_content and tokens_generated == 0:
                    tokens_generated = 1
                prompt_tokens = None
                total_tokens = None
                # Calculate tokens/sec excluding TTFT
                generation_time = duration - ttft if ttft else duration
                tokens_per_second = tokens_generated / generation_time if generation_time > 0 else 0
                logger.debug(f"Using approximation: {tokens_generated} tokens")
        
        return {
            "content": full_content,
            "model": model_id,
            "duration": duration,
            "ttft": ttft,
            "tokens_generated": tokens_generated,
            "tokens_per_second": tokens_per_second,
            "prompt_tokens": prompt_tokens,
            "total_tokens": total_tokens,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": tokens_generated,
                "total_tokens": total_tokens
            } if prompt_tokens is not None else {}
        }
    
    def health_check(self) -> bool:
        """Check if LM Studio is accessible."""
        try:
            # Try to list models as a health check
            self.client.list_loaded_models()
            return True
        except:
            return False
    
    def wait_for_ready(self, max_wait: int = 60) -> bool:
        """Wait for LM Studio to be ready."""
        # For SDK client, we assume it's ready if we successfully connected
        # The SDK handles its own connection management
        logger.info("LM Studio SDK client is ready")
        return True
    
    def get_model_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently loaded model."""
        with self._lock:
            if not self._current_model:
                return None
            
            return {
                "model_id": self._current_model.model_id,
                "load_time": self._current_model.load_time,
                "context_length": self._current_model.context_length
            }