#!/usr/bin/env python3
"""
NEXUS Anthropic API Library

This module provides reusable components for Anthropic Claude API access across NEXUS scripts.
It centralizes common functionality to maintain consistency and avoid code duplication.

Features:
- Support for Claude models (standard, Sonnet, Opus, Haiku, etc.)
- Token counting and management
- Rate limiting protection
- Error handling and retries
- Support for Claude's reasoning capabilities via system prompts

This file is designed to be imported by other scripts rather than used directly.

Common Arguments for Scripts Using This Library:
--------------------------------------------
LLM Provider Options:
    --model MODEL           Model name to use (defaults to DEFAULT_MODEL)
    --api-key KEY           API key (optional, tries environment variables by default)
    --temperature FLOAT     Model temperature (0.0-1.0, default 0.1)
    --max-tokens INT        Maximum tokens to generate in response (default: 4000)
    --system-prompt TEXT    Optional system prompt to use
    --top-p FLOAT           Top-p sampling parameter (0.0-1.0, default None)
    --top-k INT             Top-k sampling parameter (default None)
    --timeout INT           Request timeout in seconds (default: 120)

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
    import anthropic
except ImportError:
    anthropic = None
    
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
    "anthropic": 30000
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
    Get an approximate token count.
    
    Args:
        text: The text to count tokens for
        model: The model name to use for tokenization
        
    Returns:
        The number of tokens in the text
    """
    # For Claude models, we can use the anthropic library if available
    if anthropic and model.startswith("claude"):
        try:
            client = anthropic.Anthropic()
            token_count = client.count_tokens(text)
            return token_count
        except Exception as e:
            logger.warning(f"Failed to get token count using anthropic library: {str(e)}. Falling back to approximation.")
    
    # If anthropic not available, use tiktoken with cl100k_base which is similar to Claude's tokenizer
    if tiktoken:
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(f"Failed to get token count using tiktoken: {str(e)}. Falling back to character-based estimation.")
    
    # Fallback to character-based estimation if all else fails
    # Claude's tokenization is roughly 4 characters per token
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


class AnthropicProvider(LLMProvider):
    """Anthropic provider implementation."""
    
    # Default model if none specified
    DEFAULT_MODEL = "claude-3-haiku-20240307"

    def __init__(self,
                api_key: Optional[str] = None,
                model: Optional[str] = None,
                temperature: float = 0.1,
                max_tokens: int = 4000,
                system_prompt: Optional[str] = None,
                top_p: Optional[float] = None,
                top_k: Optional[int] = None,
                timeout: int = 120,
                thinking_enabled: bool = False,
                thinking_budget_tokens: Optional[int] = None):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            model: Model name to use
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate (includes thinking budget if enabled)
            system_prompt: Optional system prompt
            top_p: Optional top-p sampling parameter (0.0-1.0)
            top_k: Optional top-k sampling parameter
            timeout: Request timeout in seconds
            thinking_enabled: Enable extended thinking (requires Claude 4+ models)
            thinking_budget_tokens: Thinking token budget (typically 32000)
        """
        self.top_p = top_p
        self.top_k = top_k
        self.timeout = timeout
        self.thinking_enabled = thinking_enabled
        self.thinking_budget_tokens = thinking_budget_tokens

        # Validate thinking configuration
        if thinking_enabled and thinking_budget_tokens is None:
            raise ValueError("thinking_budget_tokens must be specified when thinking_enabled=True")

        # Call parent init
        super().__init__(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt
        )
    
    def initialize(self) -> None:
        """Initialize the Anthropic client."""
        if not anthropic:
            raise ImportError("The 'anthropic' package is required for AnthropicProvider. Install with 'pip install anthropic'.")

        self.provider_name = "anthropic"
        self.api_key = self.api_key or self._get_api_key()
        self.model = self.model or self.DEFAULT_MODEL

        # Initialize the client
        self.client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)

        # Log the model type and thinking status
        if self.thinking_enabled:
            logger.info(f"Using Anthropic model: {self.model} with temperature: {self.temperature}, "
                       f"extended thinking enabled (budget: {self.thinking_budget_tokens} tokens, "
                       f"total max_tokens: {self.max_tokens})")
        else:
            logger.info(f"Using Anthropic model: {self.model} with temperature: {self.temperature}")
        
    def get_completion(self, prompt: str, enable_cache: bool = False) -> LLMResponse:
        """
        Get a completion from Anthropic Claude.

        Args:
            prompt: The prompt text
            enable_cache: Whether to enable prompt caching for this request

        Returns:
            LLMResponse with completion and cache usage stats
        """
        # Format messages for the API
        if enable_cache:
            # Use structured content with cache control
            messages = self._format_messages_with_cache(prompt)
            system = self._format_system_with_cache() if self.system_prompt else None
        else:
            messages = [{"role": "user", "content": prompt}]
            system = self.system_prompt

        # Prepare parameters for the API call
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }

        # Add optional parameters if provided
        if system:
            params["system"] = system

        if self.top_p is not None:
            params["top_p"] = self.top_p

        if self.top_k is not None:
            params["top_k"] = self.top_k

        extra_body: Dict[str, Any] = {}

        # Add extended thinking parameters if enabled. The Anthropic SDK
        # currently exposes thinking controls only via extra_body.
        if self.thinking_enabled:
            extra_body["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget_tokens
            }

        try:
            # Call the API
            if extra_body:
                params["extra_body"] = extra_body
            response = self.client.messages.create(**params)

            # Extract the content from the response
            # For extended thinking, skip "thinking" blocks and get the first text block
            content = ""
            if response.content:
                for block in response.content:
                    if hasattr(block, 'type') and block.type == 'thinking':
                        continue  # Skip thinking blocks
                    if hasattr(block, 'text') and block.text:
                        content = block.text
                        break

            # Extract cache usage if available
            cache_creation_tokens = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
            cache_read_tokens = getattr(response.usage, 'cache_read_input_tokens', 0) or 0

            # Create and return a standardized response
            return LLMResponse(
                content=content,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model=self.model,
                raw_response=response,
                cache_creation_tokens=cache_creation_tokens,
                cache_read_tokens=cache_read_tokens
            )
        except Exception as e:
            # Handle API errors
            logger.error(f"Error calling Anthropic API: {str(e)}")
            
            # Check for rate limit errors
            if hasattr(e, "status_code") and e.status_code == 429:
                # Get retry information if available
                retry_after = None
                if hasattr(e, "response") and hasattr(e.response, "headers"):
                    retry_after = e.response.headers.get("retry-after")
                
                logger.warning(f"Rate limit exceeded. Retry after: {retry_after or 'unknown'}")
                
                # Implement exponential backoff retry
                retry_wait = int(retry_after) if retry_after and retry_after.isdigit() else COOLDOWNS["rate_limit"]
                logger.info(f"Waiting {retry_wait} seconds before retrying...")
                time.sleep(retry_wait)
                
                # Retry the request
                return self.get_completion(prompt)
            
            # Re-raise other exceptions
            raise
    
    def get_structured_completion(self, prompt: str, schema_model: Type):
        """
        Get a structured completion using a Pydantic model.
        
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
            provider = AnthropicProvider(model="claude-3-sonnet-20240229")
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
        messages = [{"role": "user", "content": prompt}]
        
        # Get the JSON schema from the Pydantic model
        json_schema = schema_model.model_json_schema()
        
        # Construct system prompt for structured output
        system_message = self.system_prompt or ""
        schema_instruction = f"""
        You must respond with valid JSON that matches the following schema:
        ```json
        {json.dumps(json_schema, indent=2)}
        ```
        Only respond with valid JSON that matches this schema, nothing else.
        """
        
        # Combine with existing system prompt if provided
        if self.system_prompt:
            system_message = f"{self.system_prompt}\n\n{schema_instruction}"
        else:
            system_message = schema_instruction
        
        # Prepare parameters for the API call
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system_message
        }
        
        # Add optional parameters if provided
        if self.top_p is not None:
            params["top_p"] = self.top_p
            
        if self.top_k is not None:
            params["top_k"] = self.top_k
        
        try:
            # Call the API
            response = self.client.messages.create(**params)

            # Extract the content from the response
            # For extended thinking, skip "thinking" blocks and get the first text block
            content = ""
            if response.content:
                for block in response.content:
                    if hasattr(block, 'type') and block.type == 'thinking':
                        continue  # Skip thinking blocks
                    if hasattr(block, 'text') and block.text:
                        content = block.text
                        break

            # Parse the JSON response into the Pydantic model
            try:
                parsed_obj = schema_model.model_validate_json(content)
            except Exception as parse_error:
                logger.error(f"Error parsing response as JSON schema: {parse_error}")
                logger.info(f"Raw response: {content}")
                raise ValueError(f"Failed to parse response as JSON schema: {parse_error}")
            
            # Create standardized response
            llm_response = LLMResponse(
                content=content,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model=self.model,
                raw_response=response
            )
            
            # Return both the parsed object and the standard LLMResponse
            return parsed_obj, llm_response
            
        except Exception as e:
            # Handle API errors
            logger.error(f"Error calling Anthropic API for structured completion: {str(e)}")
            raise
    
    def count_tokens(self, text: str) -> int:
        """
        Count tokens for Anthropic models.
        
        Args:
            text: The text to count tokens for
            
        Returns:
            The number of tokens in the text
        """
        try:
            # Use Anthropic's built-in token counter
            return self.client.count_tokens(text)
        except Exception as e:
            # Fall back to base implementation if Anthropic's counter fails
            logger.warning(f"Error using Anthropic token counter: {str(e)}. Falling back to approximation.")
            return super().count_tokens(text)

    def _format_system_with_cache(self) -> List[Dict[str, Any]]:
        """
        Format system prompt with cache control for prompt caching.

        Returns:
            System content blocks with cache_control directive
        """
        if not self.system_prompt:
            return []

        return [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"}
            }
        ]

    def _format_messages_with_cache(self, prompt: str) -> List[Dict[str, Any]]:
        """
        Format user message with cache control blocks for large context.

        This structures the prompt to maximize cache hit rate by marking
        stable content sections with cache_control directives.

        Args:
            prompt: The full prompt text (may include sections to cache)

        Returns:
            List of message dicts with cache_control where appropriate
        """
        # Split prompt into cacheable sections
        # For Apex Audition, the structure is:
        # 1. Chunk metadata (small, not worth caching)
        # 2. Target storyteller chunk (medium)
        # 3. User input (tiny)
        # 4. Recent context (LARGE - cache this!)
        # 5. Entity dossiers (LARGE - cache this!)
        # 6. Historical passages (LARGE - cache this!)
        # 7. Structured summaries (medium)
        # 8. Analysis notes (small)
        # 9. Instructions (tiny)

        # Simple implementation: mark the entire user prompt as cacheable
        # More sophisticated: split on section markers and cache large sections
        content_blocks = []

        # Check if prompt contains section markers
        if "=== RECENT STORYTELLER CONTEXT ===" in prompt:
            # Split into sections
            sections = []
            current_section = []
            current_name = None

            for line in prompt.split('\n'):
                if line.startswith('===') and line.endswith('==='):
                    if current_section:
                        sections.append((current_name, '\n'.join(current_section)))
                    current_name = line.strip('= ')
                    current_section = []
                else:
                    current_section.append(line)

            if current_section:
                sections.append((current_name, '\n'.join(current_section)))

            # Add sections as content blocks, marking large ones for caching
            for section_name, section_text in sections:
                # Preserve section headers in cached blocks
                header = f"=== {section_name} ===" if section_name else ""
                if header and section_text:
                    block_text = f"{header}\n{section_text}"
                elif header:
                    block_text = header
                else:
                    block_text = section_text

                block = {"type": "text", "text": block_text}

                # Mark large sections for caching (those over 1024 tokens estimated)
                # Anthropic caches minimum 1024 tokens, max 4 cache breakpoints
                # Use full block text (including header) for token estimation
                estimated_tokens = len(block_text) // 4  # Rough estimate

                if estimated_tokens > 1024 and section_name in [
                    "RECENT STORYTELLER CONTEXT",
                    "ENTITY DOSSIER",
                    "HISTORICAL PASSAGES",
                    "STRUCTURED SUMMARIES"
                ]:
                    block["cache_control"] = {"type": "ephemeral"}

                content_blocks.append(block)
        else:
            # Fallback: cache the entire prompt if it's large enough
            estimated_tokens = len(prompt) // 4
            block = {"type": "text", "text": prompt}
            if estimated_tokens > 1024:
                block["cache_control"] = {"type": "ephemeral"}
            content_blocks.append(block)

        return [{"role": "user", "content": content_blocks}]

    def _get_api_key(self) -> str:
        """Get Anthropic API key from environment variable or 1Password CLI."""
        import subprocess
        import os

        # First, check if API key is already in environment (e.g., pre-fetched by parent process)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            return api_key

        # Otherwise, fetch from 1Password using the secret reference syntax
        try:
            result = subprocess.run(
                ["op", "read", "op://API/Anthropic/api key"],
                capture_output=True,
                text=True,
                check=True
            )

            api_key = result.stdout.strip()
            if api_key:
                return api_key
            else:
                raise ValueError("Empty API key returned from 1Password")

        except subprocess.CalledProcessError as e:
            # Don't expose the actual error details which might contain sensitive info
            raise ValueError(
                "Failed to retrieve Anthropic API key from 1Password. "
                "Ensure 1Password CLI is installed and you're signed in. "
                "Run 'op signin' if needed."
            )
        except FileNotFoundError:
            raise ValueError(
                "1Password CLI (op) not found. Please install it from "
                "https://developer.1password.com/docs/cli/get-started/"
            )


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
        description="Process with Anthropic Claude API.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Anthropic options
    llm_group = parser.add_argument_group("Anthropic API Options")
    llm_group.add_argument("--model", default=AnthropicProvider.DEFAULT_MODEL,
                         help=f"Model name to use (default: {AnthropicProvider.DEFAULT_MODEL})")
    llm_group.add_argument("--api-key", help="API key (optional)")
    llm_group.add_argument("--temperature", type=float, default=0.1,
                         help="Model temperature (0.0-1.0, default: 0.1)")
    llm_group.add_argument("--max-tokens", type=int, default=4000,
                         help="Maximum tokens to generate in response (default: 4000)")
    llm_group.add_argument("--system-prompt", 
                         help="Optional system prompt to use")
    llm_group.add_argument("--top-p", type=float,
                         help="Top-p sampling parameter (0.0-1.0)")
    llm_group.add_argument("--top-k", type=int,
                         help="Top-k sampling parameter")
    llm_group.add_argument("--timeout", type=int, default=120,
                         help="Request timeout in seconds (default: 120)")
    
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
    Validate that the required packages are installed for Anthropic.
    
    Args:
        api_key: Optional API key to validate
        
    Raises:
        ImportError: If the required package is not installed
        ValueError: If the configuration is invalid
    """
    if anthropic is None:
        raise ImportError("The 'anthropic' package is required. Install with 'pip install anthropic'")


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
