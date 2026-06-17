#!/usr/bin/env python3
"""
NEXUS OpenAI API Library

This module provides reusable components for OpenAI API access across NEXUS scripts.
It centralizes common functionality to maintain consistency and avoid code duplication.

Features:
- Support for both standard and reasoning models (GPT-4/GPT-4o vs o1/o4)
- Automatic handling of appropriate parameters based on model type
- Token counting and management
- Rate limiting protection
- Error handling and retries

This file is designed to be imported by other scripts rather than used directly.

Common Arguments for Scripts Using This Library:
--------------------------------------------
LLM Provider Options:
    --model MODEL           Model name to use (defaults to DEFAULT_MODEL)
    --api-key KEY           API key (optional, tries environment variables by default)
    --temperature FLOAT     Model temperature (0.0-1.0, default 0.1)
    --max-tokens INT        Maximum tokens to generate in response (default: 4000)
    --system-prompt TEXT    Optional system prompt to use
    --effort               Reasoning effort for o-prefixed models: "low", "medium", or "high"
                            (Only applicable for reasoning models like o1, o4)

Processing Options:
    --batch-size INT        Number of items to process before prompting to continue (default: 10)
    --dry-run               Don't actually save results to the database
    --db-url URL            Database connection URL (optional, defaults to environment variables)
"""

import os
import sys
import abc
import argparse
import asyncio
import logging
import re
import json
import time
import signal
import threading
from typing import List, Dict, Any, Tuple, Optional, Union, Protocol, Type, TypeVar
from datetime import datetime, timedelta

# Try to import keyboard module for abort functionality
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

# Provider-specific imports
try:
    import openai
except ImportError:
    openai = None
    
# For token counting
try:
    import tiktoken
except ImportError:
    tiktoken = None

# For database connection (utilities only, no ORM)
import sqlalchemy as sa
from sqlalchemy import create_engine
from pydantic import ValidationError

from nexus.api.native_structured_output import retry_prompt, run_output_validator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("metadata_processing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.metadata")

# Default TPM limits if settings file is not available
DEFAULT_TPM_LIMITS = {
    "openai": 30000
}

DEFAULT_COOLDOWNS = {
    "individual": 15,
    "batch": 30,
    "rate_limit": 300
}

# Load settings using centralized config loader
try:
    from nexus.config import load_settings_as_dict
    SETTINGS = load_settings_as_dict()
    TPM_LIMITS = SETTINGS.get("API Settings", {}).get("TPM", DEFAULT_TPM_LIMITS)
    COOLDOWNS = SETTINGS.get("API Settings", {}).get("cooldowns", DEFAULT_COOLDOWNS)
except Exception as e:
    logger.warning(f"Failed to load settings via config loader: {str(e)}. Using defaults.")
    TPM_LIMITS = DEFAULT_TPM_LIMITS
    COOLDOWNS = DEFAULT_COOLDOWNS


class LLMResponse:
    """Standardized response object from any LLM provider."""

    def __init__(self,
                content: str,
                input_tokens: int,
                output_tokens: int,
                model: str,
                raw_response: Any = None,
                cache_creation_tokens: int = 0,
                cache_read_tokens: int = 0):
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model
        self.raw_response = raw_response
        self.cache_creation_tokens = cache_creation_tokens
        self.cache_read_tokens = cache_read_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cache_hit(self) -> bool:
        """True if this request benefited from prompt caching."""
        return self.cache_read_tokens > 0


def get_token_count(text: str, model: str) -> int:
    """
    Get an accurate token count using tiktoken.
    
    Args:
        text: The text to count tokens for
        model: The model name to use for tokenization
        
    Returns:
        The number of tokens in the text
    """
    if not tiktoken:
        # Fallback to character-based estimation if tiktoken not available
        return len(text) // 4
        
    try:
        if model.startswith("gpt-3.5") or model.startswith("gpt-4") or model.startswith("o"):
            encoding_name = "cl100k_base"  # GPT-3.5/4/o* all use cl100k
        else:
            # Try to get encoding for the specific model
            try:
                encoding = tiktoken.encoding_for_model(model)
                return len(encoding.encode(text))
            except KeyError:
                # If that fails, fall back to cl100k
                encoding_name = "cl100k_base"
        
        # Get the tokenizer
        encoding = tiktoken.get_encoding(encoding_name)
        
        # Count tokens
        return len(encoding.encode(text))
    except Exception as e:
        # If anything goes wrong, fall back to character-based estimation
        logger.warning(f"Failed to get token count using tiktoken: {str(e)}. Falling back to character-based estimation.")
        return len(text) // 4


class LLMProvider(abc.ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, 
                api_key: Optional[str] = None, 
                model: Optional[str] = None,
                temperature: float = 0.1,
                max_tokens: int = 4000,
                system_prompt: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.provider_name = None  # Will be set by subclasses
        self.initialize()
    
    @abc.abstractmethod
    def initialize(self) -> None:
        """Initialize the provider client."""
        pass
        
    @abc.abstractmethod
    def get_completion(self, prompt: str) -> LLMResponse:
        """Get a completion from the LLM."""
        pass

    def count_tokens(self, text: str) -> int:
        """Count tokens for the provider's model."""
        return get_token_count(text, self.model)
    
    def check_tpm_limit(self, prompt: str, estimated_output_tokens: Optional[int] = None) -> Tuple[bool, int, int]:
        """
        Check if the request would exceed TPM limits from settings.json.
        
        Args:
            prompt: The prompt text to be sent
            estimated_output_tokens: Optional estimate of output tokens (calculated if not provided)
            
        Returns:
            Tuple of (within_limit, input_tokens, total_tokens)
        """
        if not self.provider_name or self.provider_name.lower() not in TPM_LIMITS:
            # No provider name or no limit defined - assume it's safe
            logger.warning(f"No TPM limit found for provider {self.provider_name}. Proceeding without limits.")
            return True, 0, 0
        
        # Count input tokens
        input_tokens = self.count_tokens(prompt)
        
        # Estimate output tokens if not provided
        if estimated_output_tokens is None:
            # Default estimation
            estimated_output_tokens = max(400, input_tokens // 5)
                
        # Get total tokens
        total_tokens = input_tokens + estimated_output_tokens
        
        # Get TPM limit for this provider
        tpm_limit = TPM_LIMITS.get(self.provider_name.lower(), 0)
        
        # Check if we're within the limit
        within_limit = total_tokens <= tpm_limit
        
        if not within_limit:
            logger.warning(f"TPM limit exceeded: Request would use {total_tokens} tokens but limit is {tpm_limit}")
            logger.warning(f"This exceeds the {self.provider_name} TPM limit set in settings.json")
        
        return within_limit, input_tokens, total_tokens


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation."""
    
    # Default model if none specified
    DEFAULT_MODEL = "gpt-4.1"
    STRUCTURED_OUTPUT_RETRIES = 1
    
    # Valid reasoning effort levels (model-specific)
    VALID_REASONING_EFFORTS = ["minimal", "medium", "high", "low", None]

    def __init__(self,
                api_key: Optional[str] = None,
                model: Optional[str] = None,
                temperature: Optional[float] = 0.1,
                max_tokens: int = 4000,
                max_output_tokens: Optional[int] = None,
                system_prompt: Optional[str] = None,
                reasoning_effort: Optional[str] = None,
                base_url: Optional[str] = None,
                structured_output_retries: Optional[int] = None,
                output_validator: Optional[Any] = None):
        """
        Initialize OpenAI provider with additional reasoning parameter.

        Args:
            api_key: OpenAI API key
            model: Model name to use
            temperature: Temperature for generation (NOT used for GPT-5/o3)
            max_tokens: Maximum tokens to generate (deprecated, use max_output_tokens)
            max_output_tokens: Maximum output tokens (preferred)
            system_prompt: Optional system prompt
            reasoning_effort: Optional reasoning effort level
                - GPT-5: 'minimal', 'medium', 'high'
                - o3: 'low', 'medium', 'high'
            base_url: Optional base URL for API (e.g., for mock servers)
            structured_output_retries: Validation retry budget for structured
                output agents (apex.structured_output_retries in nexus.toml)
            output_validator: Optional async pydantic_ai output validator
                registered on structured agents (may raise ModelRetry)
        """
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens or max_tokens
        self.base_url = base_url
        self.structured_output_retries = (
            structured_output_retries
            if structured_output_retries is not None
            else self.STRUCTURED_OUTPUT_RETRIES
        )
        self.output_validator = output_validator

        # Validate reasoning effort if provided
        if reasoning_effort is not None and reasoning_effort not in self.VALID_REASONING_EFFORTS:
            raise ValueError(f"Invalid reasoning effort: {reasoning_effort}. Valid values: {self.VALID_REASONING_EFFORTS}")

        # Call parent init
        super().__init__(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt
        )
    
    def initialize(self) -> None:
        """Initialize the OpenAI client."""
        if not openai:
            raise ImportError("The 'openai' package is required for OpenAIProvider. Install with 'pip install openai'.")

        self.provider_name = "openai"
        self.api_key = self.api_key or self._get_api_key()
        self.model = self.model or self.DEFAULT_MODEL

        # Detect model type
        model_lower = self.model.lower()
        self.is_reasoning_model = "gpt-5" in model_lower or model_lower == "o3" or model_lower.startswith("o3-")  # pin: family-prefix feature detection
        self.supports_temperature = not self.is_reasoning_model

        # Create client with optional base_url for mock servers
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
            logger.info(f"Using custom base URL: {self.base_url}")
        self.client = openai.OpenAI(**client_kwargs)

        # Log the model type
        if self.is_reasoning_model:
            logger.info(f"Using reasoning model: {self.model} with effort: {self.reasoning_effort} (temperature NOT supported)")
        else:
            logger.info(f"Using standard model: {self.model} with temperature: {self.temperature}")
        
    def get_completion(self, prompt: str, cache_key: Optional[str] = None) -> LLMResponse:
        """Get a completion from OpenAI using unified /v1/responses endpoint.

        Args:
            prompt: The input prompt
            cache_key: Optional cache key for prompt caching (best practice for shared context)
        """
        return self._get_completion_unified(prompt, cache_key=cache_key)
    
    def get_structured_completion(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, LLMResponse]:
        """
        Get a structured completion using OpenAI native strict schema output.
        
        Args:
            prompt: The input prompt
            schema_model: A Pydantic BaseModel class defining the output schema
            
        Returns:
            A tuple of (parsed_object, LLMResponse)
            
        Example:
            ```python
            from pydantic import BaseModel, Field
            
            # Define your output schema
            class SentimentAnalysis(BaseModel):
                sentiment: str = Field(description="Sentiment of the text (positive, negative, neutral)")
                score: float = Field(description="Confidence score (0-1)")
                
            # Get structured completion
            provider = OpenAIProvider(model="gpt-4o")
            result, response = provider.get_structured_completion(
                "Analyze this text: 'I love this product!'",
                SentimentAnalysis
            )
            
            # Access the structured data directly
            print(f"Sentiment: {result.sentiment}, Score: {result.score}")
            ```
        """
        self._raise_if_running_loop(
            "get_structured_completion",
            "get_structured_completion_async",
        )
        return self._get_structured_completion_native_sync(
            prompt, schema_model, text_format=text_format
        )

    async def get_structured_completion_async(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, LLMResponse]:
        """Get a structured completion without blocking an existing event loop."""
        return await asyncio.to_thread(
            self._get_structured_completion_native_sync,
            prompt,
            schema_model,
            text_format=text_format,
        )

    def _raise_if_running_loop(self, method_name: str, async_method_name: str) -> None:
        """Reject sync structured calls from async contexts with a clear error."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        raise RuntimeError(
            f"OpenAIProvider.{method_name}() cannot be called from a running "
            f"event loop; use OpenAIProvider.{async_method_name}() instead."
        )

    def _get_structured_completion_native_sync(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, LLMResponse]:
        """Run a native strict-schema Responses request with bounded repair."""

        from pydantic_ai import ModelRetry

        active_prompt = prompt
        last_error: Optional[BaseException] = None
        for attempt in range(self.structured_output_retries + 1):
            try:
                response = self.client.responses.parse(
                    **self._build_native_structured_request_params(
                        active_prompt, schema_model, text_format=text_format
                    )
                )
                parsed_output = self._extract_native_parsed_output(
                    response, schema_model
                )
                parsed_output = asyncio.run(
                    run_output_validator(
                        self.output_validator, parsed_output, retry=attempt
                    )
                )
                return parsed_output, self._native_response_to_llm_response(
                    parsed_output, response
                )
            except ModelRetry as exc:
                last_error = exc
                if attempt >= self.structured_output_retries:
                    raise
                active_prompt = retry_prompt(prompt, exc.message)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                if attempt >= self.structured_output_retries:
                    raise
                active_prompt = retry_prompt(prompt, str(exc))

        raise RuntimeError("Structured completion failed") from last_error

    def _build_native_structured_request_params(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build OpenAI Responses params for native strict structured output."""

        input_messages = [{"role": "user", "content": prompt}]
        if self.system_prompt:
            input_messages.insert(0, {"role": "system", "content": self.system_prompt})

        request_params: Dict[str, Any] = {
            "model": self.model,
            "input": input_messages,
            "max_output_tokens": self.max_output_tokens,
        }
        if text_format is None:
            request_params["text_format"] = schema_model
        else:
            request_params["text"] = {"format": text_format}
        if self.supports_temperature and self.temperature is not None:
            request_params["temperature"] = self.temperature
        if self.reasoning_effort:
            request_params["reasoning"] = {"effort": self.reasoning_effort}
        return request_params

    @staticmethod
    def _extract_native_parsed_output(response: Any, schema_model: Type) -> Any:
        """Extract the parsed model from an OpenAI parsed response."""

        parsed_output = getattr(response, "output_parsed", None)
        if parsed_output is not None:
            return parsed_output

        output_text = getattr(response, "output_text", "")
        if output_text:
            return schema_model.model_validate_json(output_text)

        raise ValueError("OpenAI structured response did not include parsed output")

    def _native_response_to_llm_response(
        self, parsed_output: Any, response: Any
    ) -> LLMResponse:
        """Convert an OpenAI native structured response into LLMResponse."""

        content = (
            parsed_output.model_dump_json()
            if hasattr(parsed_output, "model_dump_json")
            else json.dumps(parsed_output)
        )
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            raw_response=response,
        )

    def _get_completion_unified(self, prompt: str, cache_key: Optional[str] = None) -> LLMResponse:
        """Get a completion using the unified /v1/responses API.

        All OpenAI models (GPT-5, o3, GPT-4o) now use the responses endpoint.

        Args:
            prompt: The input prompt
            cache_key: Optional cache key for prompt caching
        """
        # Format input for responses API
        input_messages = [{"role": "user", "content": prompt}]

        # Add system prompt if provided
        if self.system_prompt:
            input_messages.insert(0, {"role": "system", "content": self.system_prompt})

        # Build request parameters
        request_params = {
            "model": self.model,
            "input": input_messages,
            "max_output_tokens": self.max_output_tokens
        }

        # Inject prompt cache key via extra_body because the SDK has not yet
        # added first-class support for prompt_cache_key on responses.create.
        extra_body: Dict[str, Any] = {}
        if cache_key:
            extra_body["prompt_cache_key"] = cache_key

        # Add temperature if model supports it (GPT-4o and other non-reasoning models)
        if self.supports_temperature and self.temperature is not None:
            request_params["temperature"] = self.temperature

        # Add reasoning effort if provided (GPT-5, o3)
        if self.reasoning_effort:
            request_params["reasoning"] = {"effort": self.reasoning_effort}
            logger.info(f"Using OpenAI responses API with model {self.model} and reasoning effort: {self.reasoning_effort}, cache_key: {cache_key}")
        else:
            logger.info(f"Using OpenAI responses API with model {self.model}, cache_key: {cache_key}")

        if extra_body:
            request_params["extra_body"] = extra_body

        # Create the response
        response = self.client.responses.create(**request_params)

        # Format response to match our standard format
        return LLMResponse(
            content=response.output_text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
            raw_response=response
        )

    def _get_api_key(self) -> str:
        """Get OpenAI API key via the central secret manager (Keychain)."""
        from nexus.util.secret_manager import get_secret

        return get_secret("openai")


# Database utilities
def get_db_connection_string() -> str:
    """
    Get the database connection string from environment variables or defaults.
    
    By default, connects to NEXUS database on localhost with the current user.
    Override with DB_* environment variables or custom URL.
    """
    DB_USER = os.environ.get("DB_USER", "pythagor") 
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "NEXUS")
    
    # Build connection string (with password if provided)
    if DB_PASSWORD:
        connection_string = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        connection_string = f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        
    logger.info(f"Using database connection: {connection_string.replace(DB_PASSWORD, '********' if DB_PASSWORD else '')}")
    return connection_string

def to_json(obj):
    """Convert an object to a JSON-serializable format."""
    if isinstance(obj, (datetime, timedelta)):
        return str(obj)
    elif hasattr(obj, '__dict__'):
        return {k: to_json(v) for k, v in obj.__dict__.items() 
                if not k.startswith('_')}
    elif isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [to_json(item) for item in obj]
    else:
        return obj


def get_default_llm_argument_parser():
    """
    Returns an argument parser with common LLM-related arguments pre-configured.
    
    This is a helper function for scripts that want to use this library.
    It sets up the standard arguments for LLM options.
    
    Returns:
        argparse.ArgumentParser: An argument parser with common LLM-related arguments
    """
    parser = argparse.ArgumentParser(
        description="Process with OpenAI API.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # OpenAI options
    llm_group = parser.add_argument_group("OpenAI API Options")
    llm_group.add_argument("--model", default=OpenAIProvider.DEFAULT_MODEL,
                         help=f"Model name to use (default: {OpenAIProvider.DEFAULT_MODEL})")
    llm_group.add_argument("--api-key", help="API key (optional)")
    llm_group.add_argument("--temperature", type=float, default=0.1,
                         help="Model temperature for standard models (0.0-1.0, default: 0.1)")
    llm_group.add_argument("--max-tokens", type=int, default=4000,
                         help="Maximum tokens to generate in response (default: 4000)")
    llm_group.add_argument("--system-prompt", 
                         help="Optional system prompt to use")
    llm_group.add_argument("--effort", choices=["low", "medium", "high"], default="medium",
                         help="Reasoning effort for o-prefixed models (default: medium)")
    
    # Common processing options
    process_group = parser.add_argument_group("Processing Options")
    process_group.add_argument("--batch-size", type=int, default=10,
                             help="Number of items to process before prompting to continue (default: 10)")
    process_group.add_argument("--dry-run", action="store_true", 
                             help="Don't actually save results to the database")
    process_group.add_argument("--db-url", 
                        help="Database connection URL (optional, defaults to environment variables)")
    
    return parser


def validate_llm_requirements(api_key: Optional[str] = None) -> None:
    """
    Validate that the required packages are installed for OpenAI.
    
    Args:
        api_key: Optional API key to validate
        
    Raises:
        ImportError: If the required package is not installed
        ValueError: If the configuration is invalid
    """
    if openai is None:
        raise ImportError("The 'openai' package is required. Install with 'pip install openai'")


# Abort functionality
# Global abort flag
ABORT_REQUESTED = False

def setup_abort_handler(abort_message: str = "Abort requested! Will finish current operation and stop."):
    """
    Set up handlers to catch abort requests (Esc key or Ctrl+C)
    
    Args:
        abort_message: Custom message to display when abort is requested
        
    Returns:
        True if handlers were successfully set up, False otherwise
    """
    global ABORT_REQUESTED
    
    # Setup keyboard handler if available
    if KEYBOARD_AVAILABLE:
        def on_escape_press(event):
            global ABORT_REQUESTED
            if event.name == 'esc':
                print(f"\n{abort_message}")
                logger.info("Abort requested via ESC key")
                ABORT_REQUESTED = True
                
        # Register escape key handler
        keyboard.on_press(on_escape_press)
        logger.info("Keyboard abort handler active - Press ESC to abort processing")
    
    # Setup signal handler for Ctrl+C
    def signal_handler(sig, frame):
        global ABORT_REQUESTED
        print(f"\n{abort_message}")
        logger.info("Abort requested via Ctrl+C")
        ABORT_REQUESTED = True
        
    try:
        signal.signal(signal.SIGINT, signal_handler)
        logger.info("Signal handler active - Press Ctrl+C to abort processing")
        return True
    except Exception as e:
        logger.warning(f"Failed to set up signal handler: {e}")
        return False

def is_abort_requested() -> bool:
    """
    Check if abort has been requested
    
    Returns:
        True if abort has been requested, False otherwise
    """
    global ABORT_REQUESTED
    return ABORT_REQUESTED

def reset_abort_flag():
    """Reset the abort flag to False"""
    global ABORT_REQUESTED
    ABORT_REQUESTED = False
    logger.info("Abort flag has been reset")

# This file is now meant to be imported as a library, not run directly
if __name__ == "__main__":
    logger.warning("This file is intended to be used as a library, not run directly.")
    sys.exit(1)
