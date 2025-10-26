#!/usr/bin/env python3
"""
NEXUS OpenRouter API Library

This module provides a unified interface for accessing AI models through OpenRouter.
OpenRouter supports models from OpenAI, Anthropic, DeepSeek, and many other providers
through a single API endpoint.

Features:
- Unified interface for models from multiple providers
- Support for reasoning models (OpenAI o-series, GPT-5)
- Support for extended thinking (Anthropic Claude)
- Standard temperature/token controls
- Rate limiting protection
- Error handling and retries

This file is designed to be imported by other scripts rather than used directly.
"""

import os
import sys
import abc
import argparse
import logging
import json
import time
import subprocess
from typing import List, Dict, Any, Tuple, Optional, Union, Protocol, Type
from datetime import datetime, timedelta

# Try to import OpenAI SDK for OpenRouter compatibility
try:
    import openai
except ImportError:
    openai = None

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
logger = logging.getLogger("nexus.openrouter")

# Load settings.json for API limits
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "settings.json")

# Default TPM limits if settings file is not available
DEFAULT_TPM_LIMITS = {
    "openrouter": 50000
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
        """
        Estimate token count (rough approximation).
        OpenRouter doesn't provide token counting, so we estimate.
        """
        # Rough estimate: 1 token ≈ 4 characters
        return len(text) // 4

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


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider implementation for unified multi-provider access."""

    # Default model if none specified
    DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

    # OpenRouter API base URL
    API_BASE = "https://openrouter.ai/api/v1"

    # Model name mapping: database name -> OpenRouter model ID
    MODEL_MAPPING = {
        # OpenAI models
        "gpt-5": "openai/gpt-5",
        "gpt-4o": "openai/gpt-4o",
        "o3": "openai/o3",
        # Anthropic models
        "claude-sonnet-4-5": "anthropic/claude-sonnet-4.5",
        "claude-opus-4-1": "anthropic/claude-opus-4.1",
        # DeepSeek models
        "deepseek-v3.2-exp": "deepseek/deepseek-v3.2-exp",
    }

    def __init__(self,
                api_key: Optional[str] = None,
                model: Optional[str] = None,
                temperature: Optional[float] = 0.1,
                max_tokens: int = 4000,
                system_prompt: Optional[str] = None,
                reasoning_effort: Optional[str] = None,
                thinking_budget_tokens: Optional[int] = None,
                top_p: Optional[float] = None,
                min_p: Optional[float] = None,
                frequency_penalty: Optional[float] = None,
                presence_penalty: Optional[float] = None,
                repetition_penalty: Optional[float] = None):
        """
        Initialize OpenRouter provider.

        Args:
            api_key: OpenRouter API key
            model: Model name to use (e.g., "openai/gpt-5", "anthropic/claude-sonnet-4.5", "deepseek/deepseek-v3.2-exp")
            temperature: Temperature for generation (0.0-2.0)
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt
            reasoning_effort: Optional reasoning effort level ("minimal", "low", "medium", "high")
            thinking_budget_tokens: Optional thinking token budget for Anthropic extended thinking
        """
        self.reasoning_effort = reasoning_effort
        self.thinking_budget_tokens = thinking_budget_tokens
        self.top_p = top_p
        self.min_p = min_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.repetition_penalty = repetition_penalty

        # Call parent init
        super().__init__(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt
        )

    def initialize(self) -> None:
        """Initialize the OpenRouter client."""
        if not openai:
            raise ImportError("The 'openai' package is required for OpenRouterProvider. Install with 'pip install openai'.")

        self.provider_name = "openrouter"
        self.api_key = self.api_key or self._get_api_key()
        self.model = self.model or self.DEFAULT_MODEL

        # Map database model name to OpenRouter model ID
        if self.model in self.MODEL_MAPPING:
            original_model = self.model
            self.model = self.MODEL_MAPPING[self.model]
            logger.info(f"Mapped model {original_model} -> {self.model}")

        # Initialize the client with OpenRouter base URL
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.API_BASE
        )

        # Log the configuration
        logger.info(f"Using OpenRouter with model: {self.model}, temperature: {self.temperature}")
        if self.reasoning_effort:
            logger.info(f"Reasoning effort: {self.reasoning_effort}")
        if self.thinking_budget_tokens:
            logger.info(f"Thinking budget: {self.thinking_budget_tokens} tokens")
        if self.top_p is not None:
            logger.info(f"top_p: {self.top_p}")
        if self.min_p is not None:
            logger.info(f"min_p: {self.min_p}")
        if self.frequency_penalty is not None:
            logger.info(f"frequency_penalty: {self.frequency_penalty}")
        if self.presence_penalty is not None:
            logger.info(f"presence_penalty: {self.presence_penalty}")
        if self.repetition_penalty is not None:
            logger.info(f"repetition_penalty: {self.repetition_penalty}")

    def get_completion(self, prompt: str, enable_cache: bool = False) -> LLMResponse:
        """
        Get a completion from OpenRouter.

        Args:
            prompt: The prompt text
            enable_cache: Ignored for OpenRouter (no caching support)

        Returns:
            LLMResponse with completion
        """
        # Format messages for the API
        messages = []

        # Add system prompt if provided
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Add user prompt
        messages.append({"role": "user", "content": prompt})

        # Prepare parameters for the API call
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        # Add temperature if provided
        if self.temperature is not None:
            params["temperature"] = self.temperature

        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.min_p is not None:
            params["min_p"] = self.min_p
        if self.frequency_penalty is not None:
            params["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            params["presence_penalty"] = self.presence_penalty
        if self.repetition_penalty is not None:
            params["repetition_penalty"] = self.repetition_penalty

        # OpenRouter's REST API supports reasoning parameters but the OpenAI SDK doesn't
        # Route to HTTP if reasoning is enabled, otherwise use SDK for efficiency
        if self.reasoning_effort or self.thinking_budget_tokens:
            return self._get_completion_http(prompt, messages, enable_cache)

        try:
            # Call the API via SDK
            response = self.client.chat.completions.create(**params)

            # Extract the content from the response
            content = response.choices[0].message.content or ""

            # Create and return a standardized response
            return LLMResponse(
                content=content,
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                model=self.model,
                raw_response=response
            )
        except Exception as e:
            # Handle API errors
            logger.error(f"Error calling OpenRouter API: {str(e)}")

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
                return self.get_completion(prompt, enable_cache=enable_cache)

            # Re-raise other exceptions
            raise

    def _get_completion_http(self, prompt: str, messages: List[Dict[str, str]], enable_cache: bool) -> LLMResponse:
        """
        Get completion via HTTP REST API (required for reasoning parameters).

        The OpenAI SDK doesn't support OpenRouter's reasoning parameters, so we use
        direct HTTP requests when reasoning is enabled.
        """
        import requests

        # Build request payload
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        if self.temperature is not None:
            payload["temperature"] = self.temperature

        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.min_p is not None:
            payload["min_p"] = self.min_p
        if self.frequency_penalty is not None:
            payload["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            payload["presence_penalty"] = self.presence_penalty
        if self.repetition_penalty is not None:
            payload["repetition_penalty"] = self.repetition_penalty

        # Add reasoning configuration per OpenRouter docs
        if self.reasoning_effort or self.thinking_budget_tokens:
            reasoning_config: Dict[str, Any] = {}

            if self.reasoning_effort:
                # OpenAI models use effort levels
                reasoning_config["effort"] = self.reasoning_effort

            if self.thinking_budget_tokens:
                # Anthropic models use max_tokens
                reasoning_config["max_tokens"] = self.thinking_budget_tokens

            payload["reasoning"] = reasoning_config

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.API_BASE}/chat/completions",
                json=payload,
                headers=headers,
                timeout=300,  # 5 minutes
            )
            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response from OpenRouter. Raw response: {response.text[:500]}")
                raise

            content = data["choices"][0]["message"]["content"] or ""

            return LLMResponse(
                content=content,
                input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                output_tokens=data.get("usage", {}).get("completion_tokens", 0),
                model=self.model,
            )

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after", COOLDOWNS["rate_limit"])
                logger.warning(f"Rate limit exceeded. Waiting {retry_after} seconds...")
                time.sleep(int(retry_after))
                return self._get_completion_http(prompt, messages, enable_cache)

            logger.error(f"OpenRouter HTTP error: {e.response.status_code} - {e.response.text[:500]}")
            raise
        except json.JSONDecodeError:
            # Already logged above with raw response
            raise
        except Exception as e:
            logger.error(f"Error calling OpenRouter HTTP API: {str(e)}")
            raise

    def _get_api_key(self) -> str:
        """Get OpenRouter API key from 1Password CLI."""
        # First, check if API key is already in environment
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            return api_key

        # Otherwise, fetch from 1Password
        try:
            result = subprocess.run(
                ["op", "read", "op://API/OpenRouter/api key"],
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
            raise ValueError(
                "Failed to retrieve OpenRouter API key from 1Password. "
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


def get_default_llm_argument_parser():
    """
    Returns an argument parser with common LLM-related arguments pre-configured.

    Returns:
        argparse.ArgumentParser: An argument parser with common LLM-related arguments
    """
    parser = argparse.ArgumentParser(
        description="Process with OpenRouter API.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # OpenRouter options
    llm_group = parser.add_argument_group("OpenRouter API Options")
    llm_group.add_argument("--model", default=OpenRouterProvider.DEFAULT_MODEL,
                         help=f"Model name to use (default: {OpenRouterProvider.DEFAULT_MODEL})")
    llm_group.add_argument("--api-key", help="API key (optional)")
    llm_group.add_argument("--temperature", type=float, default=0.1,
                         help="Model temperature (0.0-2.0, default: 0.1)")
    llm_group.add_argument("--max-tokens", type=int, default=4000,
                         help="Maximum tokens to generate in response (default: 4000)")
    llm_group.add_argument("--system-prompt",
                         help="Optional system prompt to use")
    llm_group.add_argument("--reasoning-effort", choices=["minimal", "low", "medium", "high"],
                         help="Reasoning effort for reasoning models")
    llm_group.add_argument("--thinking-budget", type=int,
                         help="Thinking token budget for extended thinking models")

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
    Validate that the required packages are installed for OpenRouter.

    Args:
        api_key: Optional API key to validate

    Raises:
        ImportError: If the required package is not installed
        ValueError: If the configuration is invalid
    """
    if openai is None:
        raise ImportError("The 'openai' package is required. Install with 'pip install openai'")


# This file is now meant to be imported as a library, not run directly
if __name__ == "__main__":
    logger.warning("This file is intended to be used as a library, not run directly.")
    sys.exit(1)
