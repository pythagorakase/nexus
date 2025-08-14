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

# Load settings.json for API limits
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                           "settings.json")

# Default TPM limits if settings file is not available
DEFAULT_TPM_LIMITS = {
    "openai": 30000
}

# Load settings
try:
    with open(SETTINGS_PATH, 'r') as f:
        SETTINGS = json.load(f)
    TPM_LIMITS = SETTINGS.get("API Settings", {}).get("TPM", DEFAULT_TPM_LIMITS)
    COOLDOWNS = SETTINGS.get("API Settings", {}).get("cooldowns", {
        "individual": 15,
        "batch": 30,
        "rate_limit": 300
    })
    # logger.info(f"Loaded API TPM limits from settings.json: {TPM_LIMITS}")
    # logger.info(f"Loaded API cooldown values from settings.json: {COOLDOWNS}")
except Exception as e:
    logger.warning(f"Failed to load settings.json: {str(e)}. Using default TPM limits: {DEFAULT_TPM_LIMITS}")
    TPM_LIMITS = DEFAULT_TPM_LIMITS
    COOLDOWNS = {
        "individual": 15,
        "batch": 30,
        "rate_limit": 300
    }


class LLMResponse:
    """Standardized response object from any LLM provider."""
    
    def __init__(self, 
                content: str, 
                input_tokens: int, 
                output_tokens: int,
                model: str,
                raw_response: Any = None):
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model
        self.raw_response = raw_response
        
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


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
    
    @abc.abstractmethod
    def get_input_token_cost(self) -> float:
        """Get the cost per 1M input tokens for this model."""
        pass
        
    @abc.abstractmethod
    def get_output_token_cost(self) -> float:
        """Get the cost per 1M output tokens for this model."""
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
    
    # Valid reasoning effort levels
    VALID_REASONING_EFFORTS = ["low", "medium", "high", None]
    
    # Model pricing (per 1M tokens as of April 2025)
    MODEL_PRICING = {
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        "o3": {"input": 5.0, "output": 15.0},  # o3/o3-mini are aliased to 4o for pricing
        "o3-mini": {"input": 0.15, "output": 0.6},
        "o4": {"input": 5.0, "output": 15.0},
        "o4-mini": {"input": 0.15, "output": 0.6},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    }
    
    def __init__(self, 
                api_key: Optional[str] = None, 
                model: Optional[str] = None,
                temperature: float = 0.1,
                max_tokens: int = 4000,
                system_prompt: Optional[str] = None,
                reasoning_effort: Optional[str] = None):
        """
        Initialize OpenAI provider with additional reasoning parameter.
        
        Args:
            api_key: OpenAI API key
            model: Model name to use
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt
            reasoning_effort: Optional reasoning effort level ('low', 'medium', 'high')
        """
        self.reasoning_effort = reasoning_effort
        
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
        self.is_reasoning_model = self.model.startswith("o")
        self.client = openai.OpenAI(api_key=self.api_key)
        
        # Log the model type
        if self.is_reasoning_model:
            logger.info(f"Using reasoning model: {self.model} with effort: {self.reasoning_effort}")
        else:
            logger.info(f"Using standard model: {self.model} with temperature: {self.temperature}")
        
    def get_completion(self, prompt: str) -> LLMResponse:
        """Get a completion from OpenAI."""
        # For reasoning models (o-prefixed) using the responses API
        if self.is_reasoning_model:
            return self._get_reasoned_completion(prompt)
        else:
            # Standard chat completions API for all other models
            return self._get_standard_completion(prompt)
    
    def get_structured_completion(self, prompt: str, schema_model: Type):
        """
        Get a structured completion using the Responses API with a Pydantic model.
        
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
        # Check if we have the required dependencies
        try:
            from pydantic import BaseModel
        except ImportError:
            raise ImportError("Pydantic is required for structured completions. Install with 'pip install pydantic'")
            
        # Format input messages
        input_messages = [{"role": "user", "content": prompt}]
        
        # Add system prompt if provided
        if self.system_prompt:
            input_messages.insert(0, {"role": "system", "content": self.system_prompt})
        
        logger.info(f"Using OpenAI structured output with model {self.model} and schema {schema_model.__name__}")
        
        try:
            # Call API with different parameters based on model type
            if self.is_reasoning_model:
                # For reasoning models (o1, o2, etc.)
                response = self.client.responses.parse(
                    model=self.model,
                    input=input_messages,
                    reasoning={"effort": self.reasoning_effort} if self.reasoning_effort else None,
                    text_format=schema_model
                )
                logger.info(f"Used reasoning model with effort: {self.reasoning_effort}")
            else:
                # For standard models (GPT-4, etc.)
                response = self.client.responses.parse(
                    model=self.model,
                    input=input_messages,
                    temperature=self.temperature,
                    text_format=schema_model
                )
                logger.info(f"Used standard model with temperature: {self.temperature}")
                
        except Exception as e:
            logger.error(f"Error using responses.parse: {e}")
            # Fall back to using model_json_schema for compatibility with older OpenAI API versions
            model_schema = schema_model.model_json_schema()
            
            # Extract properties and required fields
            schema_properties = model_schema.get("properties", {})
            required_fields = model_schema.get("required", [])
            
            # Create custom schema - handling the structure OpenAI expects
            custom_schema = {
                "type": "object",
                "properties": schema_properties,
                "required": required_fields,
                "additionalProperties": False
            }
            
            # Debug: Print custom schema
            logger.info(f"Falling back to custom JSON Schema for {schema_model.__name__}: {json.dumps(custom_schema)}")
            
            # Call the responses.create API with the custom schema
            schema_name = schema_model.__name__
            
            # Call with different parameters based on model type
            if self.is_reasoning_model:
                params = {
                    "model": self.model,
                    "input": input_messages,
                    "reasoning": {"effort": self.reasoning_effort} if self.reasoning_effort else None,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "schema": custom_schema,
                            "name": schema_name,
                            "strict": True
                        }
                    }
                }
            else:
                params = {
                    "model": self.model,
                    "input": input_messages,
                    "temperature": self.temperature,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "schema": custom_schema,
                            "name": schema_name,
                            "strict": True
                        }
                    }
                }
                
            response = self.client.responses.create(**params)
        
        # Create LLMResponse object for compatibility
        llm_response = LLMResponse(
            content=response.output_text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
            raw_response=response
        )
        
        # Return both the parsed object and the standard LLMResponse
        return response.output_parsed, llm_response
    
    def _get_reasoned_completion(self, prompt: str) -> LLMResponse:
        """Get a completion using the responses API with reasoning parameter."""
        # Format input for responses API
        input_messages = [{"role": "user", "content": prompt}]
        
        # Add system prompt if provided
        if self.system_prompt:
            input_messages.insert(0, {"role": "system", "content": self.system_prompt})
        
        # Prepare reasoning parameter if provided
        if self.reasoning_effort:
            reasoning_param = {"effort": self.reasoning_effort}
            logger.info(f"Using OpenAI responses API with model {self.model} and reasoning effort: {self.reasoning_effort}")
            
            # Create the response using the responses API with reasoning
            response = self.client.responses.create(
                model=self.model,
                reasoning=reasoning_param,
                input=input_messages,
                max_tokens=self.max_tokens
            )
        else:
            # Create the response using the responses API without reasoning (use default effort)
            logger.info(f"Using OpenAI responses API with model {self.model} without explicit reasoning effort")
            
            response = self.client.responses.create(
                model=self.model,
                input=input_messages,
                max_tokens=self.max_tokens
            )
        
        # Format response to match our standard format
        return LLMResponse(
            content=response.output_text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
            raw_response=response
        )
    
    def _get_standard_completion(self, prompt: str) -> LLMResponse:
        """Get a completion from OpenAI using standard chat completions API."""
        messages = [{"role": "user", "content": prompt}]
        
        # Add system prompt if provided
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})
            
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        
        return LLMResponse(
            content=response.choices[0].message.content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            model=self.model,
            raw_response=response
        )
    
    def get_input_token_cost(self) -> float:
        """Get the cost per 1M input tokens for this model."""
        model_info = self.MODEL_PRICING.get(self.model, {"input": 5.0})  # Default to GPT-4o pricing
        return model_info["input"] / 1_000_000  # Convert to cost per token
        
    def get_output_token_cost(self) -> float:
        """Get the cost per 1M output tokens for this model."""
        model_info = self.MODEL_PRICING.get(self.model, {"output": 15.0})  # Default to GPT-4o pricing
        return model_info["output"] / 1_000_000  # Convert to cost per token
    
    def _get_api_key(self) -> str:
        """Get OpenAI API key from various potential sources."""
        # Try environment variable
        if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"]:
            return os.environ["OPENAI_API_KEY"]
        
        # Try from a key file
        key_file_paths = [
            os.path.expanduser("~/.openai/api_key"),
            os.path.expanduser("~/.config/openai/api_key")
        ]
        
        for path in key_file_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        key = f.read().strip()
                        if key:
                            return key
                except:
                    pass
        
        # Try to read from ~/.zshrc
        try:
            zshrc_path = os.path.expanduser("~/.zshrc")
            if os.path.exists(zshrc_path):
                with open(zshrc_path, 'r') as f:
                    for line in f:
                        if "OPENAI_API_KEY" in line:
                            # Extract the key using regex
                            match = re.search(r'OPENAI_API_KEY=([a-zA-Z0-9_-]+)', line)
                            if match:
                                return match.group(1)
        except:
            pass
        
        raise ValueError("No OpenAI API key found. Please set OPENAI_API_KEY environment variable.")


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