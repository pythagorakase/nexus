#!/usr/bin/env python3
"""
Time Delta Estimation Script for NEXUS

This script processes narrative chunks using an API-based LLM to estimate 
realistic time_delta values for each chunk. By default, it uses OpenAI GPT-4.1.

Usage:
    python estimate_time_delta.py --start 1 --end 10 --test     # Test mode, print results
    python estimate_time_delta.py --start 5 --end 5 --write     # Write single chunk
    python estimate_time_delta.py --all --write                 # Process all chunks
    python estimate_time_delta.py --all --write --provider anthropic --model claude-3-7-sonnet

Options:
    --provider PROVIDER     LLM provider to use: "anthropic" or "openai" (default: openai)
    --model MODEL           Model name to use (defaults to provider's default model)
    --temperature FLOAT     Model temperature (0.0-1.0, default: 0.1)
    --auto                  Process all chunks automatically without prompting

Database URL:
postgresql://pythagor@localhost/NEXUS
"""

import os
import re
import sys
import argparse
import logging
import time
import json
from datetime import timedelta, datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Provider-specific imports
try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import openai
except ImportError:
    openai = None
    
# For token counting
try:
    import tiktoken
except ImportError:
    tiktoken = None

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("time_delta_processor.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Default TPM limits if settings file is not available
DEFAULT_TPM_LIMITS = {
    "openai": 30000,
    "anthropic": 20000
}

# Load settings using centralized config loader
try:
    from nexus.config import load_settings_as_dict
    SETTINGS = load_settings_as_dict()
    TPM_LIMITS = SETTINGS.get("API Settings", {}).get("TPM", DEFAULT_TPM_LIMITS)
    logger.info(f"Loaded API TPM limits via config loader: {TPM_LIMITS}")
except Exception as e:
    logger.warning(f"Failed to load settings via config loader: {str(e)}. Using defaults.")
    TPM_LIMITS = DEFAULT_TPM_LIMITS

# Database configuration
DB_URL = "postgresql://pythagor@localhost/NEXUS"


class NarrativeChunk:
    """Class to represent a narrative chunk."""
    
    def __init__(self, id: int, raw_text: str):
        self.id = id
        self.raw_text = raw_text


class LLMResponse:
    """Standardized response object from any LLM provider."""
    
    def __init__(self, 
                content: str, 
                input_tokens: int, 
                output_tokens: int,
                model: str,
                raw_response: Any = None,
                reasoning_summary: Any = None,
                structured_data: Optional[Dict[str, Any]] = None):
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model
        self.raw_response = raw_response
        self.reasoning_summary = reasoning_summary
        self.structured_data = structured_data  # JSON data from structured output
        
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
        # For Claude models, use cl100k_base encoding (same as GPT-4)
        if model.startswith("claude"):
            encoding_name = "cl100k_base"
        elif model.startswith("gpt-3.5") or model.startswith("gpt-4"):
            encoding_name = "cl100k_base"  # GPT-3.5/4 also use cl100k
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


class LLMProvider:
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
    
    def initialize(self) -> None:
        """Initialize the provider client."""
        pass
        
    def get_completion(self, prompt: str) -> LLMResponse:
        """Get a completion from the LLM."""
        pass
    
    def get_input_token_cost(self) -> float:
        """Get the cost per 1M input tokens for this model."""
        return 0.0
        
    def get_output_token_cost(self) -> float:
        """Get the cost per 1M output tokens for this model."""
        return 0.0
        
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
            # Default estimation based on model type
            if "claude" in self.model.lower():
                estimated_output_tokens = max(500, input_tokens // 4)
            else:
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
    
    @classmethod
    def from_provider_name(cls, provider_name: str, **kwargs) -> 'LLMProvider':
        """
        Factory method to create a provider from its name.
        
        Args:
            provider_name: Name of the provider ('anthropic' or 'openai')
            **kwargs: Additional arguments to pass to the provider constructor,
                      including api_key, model, temperature, max_tokens, system_prompt, 
                      and reasoning_effort (for OpenAI providers)
        """
        logger.info(f"DEBUG: LLMProvider.from_provider_name called with provider_name={provider_name}")
        logger.info(f"DEBUG: kwargs keys: {', '.join(kwargs.keys())}")
        providers = {
            'anthropic': AnthropicProvider,
            'openai': OpenAIProvider,
        }
        
        provider_class = providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider '{provider_name}'. Available providers: {', '.join(providers.keys())}")
        
        logger.info(f"DEBUG: Creating provider instance for class {provider_class.__name__}")
        try:
            return provider_class(**kwargs)
        except Exception as e:
            logger.error(f"DEBUG: Error creating provider instance: {str(e)}")
            logger.error(f"DEBUG: Exception repr: {repr(e)}")
            raise


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider implementation."""
    
    # Default model if none specified
    DEFAULT_MODEL = "claude-3-7-sonnet-20250219"
    
    # Model pricing (per 1M tokens as of April 2025)
    MODEL_PRICING = {
        "claude-3-7-sonnet-20250219": {"input": 15.0, "output": 75.0},
        "claude-3-opus-20240229": {"input": 30.0, "output": 150.0},
        "claude-3-haiku-20240307": {"input": 3.0, "output": 15.0},
        "claude-3-5-sonnet-20240620": {"input": 5.0, "output": 15.0},
        "claude-2.1": {"input": 8.0, "output": 24.0},
        "claude-2.0": {"input": 8.0, "output": 24.0},
        "claude-instant-1.2": {"input": 1.63, "output": 5.51},
    }
    
    def initialize(self) -> None:
        """Initialize the Anthropic client."""
        if not anthropic:
            raise ImportError("The 'anthropic' package is required for AnthropicProvider. Install with 'pip install anthropic'.")
            
        self.provider_name = "anthropic"
        self.api_key = self.api_key or self._get_api_key()
        self.model = self.model or self.DEFAULT_MODEL
        self.client = anthropic.Anthropic(api_key=self.api_key)
        
    def get_completion(self, prompt: str) -> LLMResponse:
        """Get a completion from Claude."""
        messages = [{"role": "user", "content": prompt}]
        
        # Add system prompt if provided
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})
            
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=messages
        )
        
        # Extract content from the response
        content = response.content[0].text
        
        return LLMResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
            raw_response=response
        )
    
    def get_input_token_cost(self) -> float:
        """Get the cost per 1M input tokens for this model."""
        model_info = self.MODEL_PRICING.get(self.model, {"input": 15.0})  # Default to Sonnet pricing
        return model_info["input"] / 1_000_000  # Convert to cost per token
        
    def get_output_token_cost(self) -> float:
        """Get the cost per 1M output tokens for this model."""
        model_info = self.MODEL_PRICING.get(self.model, {"output": 75.0})  # Default to Sonnet pricing
        return model_info["output"] / 1_000_000  # Convert to cost per token
    
    def _get_api_key(self) -> str:
        """Get Anthropic API key from various potential sources."""
        # Try different environment variables that might contain the API key
        for var_name in ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_KEY"]:
            if var_name in os.environ and os.environ[var_name]:
                return os.environ[var_name]
        
        # Try from a key file
        key_file_paths = [
            os.path.expanduser("~/.anthropic/api_key"),
            os.path.expanduser("~/.claude/api_key"),
            os.path.expanduser("~/.config/anthropic/api_key")
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
                        if "ANTHROPIC_API_KEY" in line:
                            # Extract the key using regex
                            match = re.search(r'ANTHROPIC_API_KEY=([a-zA-Z0-9_-]+)', line)
                            if match:
                                return match.group(1)
        except:
            pass
        
        raise ValueError("No Anthropic API key found. Please set ANTHROPIC_API_KEY environment variable.")


class OpenAIProvider(LLMProvider):
    """
    OpenAI provider implementation with support for reasoning.
    
    This provider supports the new OpenAI Responses API for 'o' series models (o3, o3-mini, etc.)
    with configurable reasoning effort ("low", "medium", "high") and reasoning summaries.
    
    When using an 'o' series model, the reasoning process will be displayed in the logs,
    providing insight into the model's chain-of-thought reasoning process.
    """
    
    # Default model if none specified
    DEFAULT_MODEL = "o3"
    
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
                reasoning_effort: Optional[str] = "high"):
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
        logger.info(f"DEBUG: Entering OpenAIProvider.initialize()")
        if not openai:
            raise ImportError("The 'openai' package is required for OpenAIProvider. Install with 'pip install openai'.")
            
        logger.info(f"DEBUG: Setting provider name and API key")
        self.provider_name = "openai"
        self.api_key = self.api_key or self._get_api_key()
        self.model = self.model or self.DEFAULT_MODEL
        logger.info(f"DEBUG: Creating OpenAI client with API key")
        try:
            self.client = openai.OpenAI(api_key=self.api_key)
            logger.info(f"DEBUG: OpenAI client created successfully")
        except Exception as e:
            logger.error(f"DEBUG: Error creating OpenAI client: {str(e)}")
            logger.error(f"DEBUG: Exception details: {repr(e)}")
            raise
    
    def get_completion(self, prompt: str) -> LLMResponse:
        """Get a completion from OpenAI."""
        # For models supporting the responses API with reasoning
        # o3, o3-mini, o4, o4-mini
        if self.model.startswith("o") and self.reasoning_effort is not None:
            return self._get_reasoned_completion(prompt)
        else:
            # Standard chat completions API for all other models
            return self._get_standard_completion(prompt)
    
    def _get_reasoned_completion(self, prompt: str) -> LLMResponse:
        """Get a completion using the responses API with reasoning parameter and structured output."""
        # Format input for responses API
        input_messages = [{"role": "user", "content": prompt}]
        
        # Add system prompt if provided
        if self.system_prompt:
            input_messages.insert(0, {"role": "system", "content": self.system_prompt})
        
        # Prepare reasoning parameter with summary
        reasoning_param = {
            "effort": self.reasoning_effort,
            "summary": "auto"  # Request the most detailed summary available
        }
        
        # Define JSON schema for structured output
        structured_output = {
            "format": {
                "type": "json_schema",
                "name": "time_delta_estimation",
                "schema": {
                    "type": "object",
                    "properties": {
                        "activities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "minutes": {"type": "integer"}
                                },
                                "required": ["name", "minutes"],
                                "additionalProperties": False
                            }
                        },
                        "total_hours": {"type": "integer"},
                        "total_minutes": {"type": "integer"},
                        "formatted_time": {"type": "string"}
                    },
                    "required": ["activities", "total_hours", "total_minutes", "formatted_time"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
        
        # Create the response using the responses API
        logger.info(f"Using OpenAI responses API with model {self.model}, reasoning effort: {self.reasoning_effort}, and structured output")
        
        # NOTE: The Responses API has different parameters than Chat Completions API
        # It doesn't accept max_tokens or maximum_content_length
        # Just use the essential parameters: model, reasoning, input, temperature, and structured output
        
        response = self.client.responses.create(
            model=self.model,
            reasoning=reasoning_param,
            input=input_messages,
            text=structured_output  # Add structured output format
        )
        
        # Print reasoning summary if available
        if hasattr(response, 'reasoning') and response.reasoning is not None:
            logger.info("===== Model Reasoning Summary =====")
            
            # Check if summary is a list/array
            if hasattr(response.reasoning, 'summary'):
                try:
                    if isinstance(response.reasoning.summary, list):
                        for idx, summary_item in enumerate(response.reasoning.summary):
                            logger.info(f"  {idx+1}. {summary_item}")
                    elif isinstance(response.reasoning.summary, str):
                        # If it's a single string
                        logger.info(response.reasoning.summary)
                    else:
                        # If it's some other format, try to display it
                        logger.info(f"Summary (format: {type(response.reasoning.summary)}): {response.reasoning.summary}")
                except Exception as e:
                    logger.info(f"Error displaying reasoning summary: {str(e)}")
                    logger.info(f"Raw reasoning: {response.reasoning}")
            else:
                # If there's reasoning but no summary attribute, show what's available
                logger.info(f"Reasoning available but no summary attribute.")
                logger.info(f"Reasoning attributes: {', '.join(dir(response.reasoning))}")
                
            logger.info("====================================")
        
        # Extract reasoning summary if available
        reasoning_summary = None
        if hasattr(response, 'reasoning') and response.reasoning is not None:
            if hasattr(response.reasoning, 'summary'):
                reasoning_summary = response.reasoning.summary
        
        # For OpenAI with structured output, attempt to parse as JSON directly
        content = response.output_text
        structured_data = None
        
        try:
            import json
            # Try to parse the response directly as structured JSON
            structured_data = json.loads(content)
            logger.info(f"Successfully parsed structured JSON output from OpenAI")
        except Exception as e:
            logger.warning(f"Could not parse response as JSON: {e}")
        
        return LLMResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
            raw_response=response,
            reasoning_summary=reasoning_summary,
            structured_data=structured_data  # Add the structured data if available
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


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Estimate time delta for narrative chunks")
    
    # Create mutually exclusive group for chunk selection
    chunk_selection = parser.add_mutually_exclusive_group(required=True)
    chunk_selection.add_argument("--start", type=int, help="Starting chunk id number")
    chunk_selection.add_argument("--all", action="store_true", help="Process all chunks needing time_delta")
    
    # Other arguments
    parser.add_argument("--end", type=int, help="Ending chunk id number (required with --start)")
    parser.add_argument("--test", action="store_true", help="Test mode, print results only")
    parser.add_argument("--write", action="store_true", help="Write results to database")
    parser.add_argument("--primary-only", action="store_true", 
                        help="Only process primary world layer chunks (others get 0 minutes automatically)")
    parser.add_argument("--include-all-world-layers", action="store_true",
                        help="Process all chunks regardless of world layer (override default behavior)")
    
    # LLM options
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="openai",
                        help="LLM provider to use (default: openai)")
    parser.add_argument("--model", type=str, help="Model name (defaults to provider's default model)")
    parser.add_argument("--temperature", type=float, default=0.1, 
                        help="Model temperature (0.0-1.0, default: 0.1)")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="Maximum tokens to generate in response (default: 2048)")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default="high",
                        help="Reasoning effort for OpenAI models: 'low', 'medium', or 'high' (default: high). "
                             "Also enables reasoning summary display in the logs.")
    parser.add_argument("--auto", action="store_true",
                        help="Process all chunks automatically without prompting")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed information including prompts sent to the LLM")
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.start is not None and args.end is None:
        args.end = args.start  # Default end to start if only start is provided
    
    if not args.test and not args.write:
        parser.error("Must specify either --test or --write mode")
    
    if args.primary_only and args.include_all_world_layers:
        parser.error("Cannot specify both --primary-only and --include-all-world-layers")
    
    return args


def get_db_connection() -> Engine:
    """Get database connection using project settings."""
    try:
        engine = create_engine(DB_URL)
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise


def get_chunk_by_id(db: Engine, chunk_id: int) -> Optional[NarrativeChunk]:
    """Get a narrative chunk by its id."""
    try:
        with db.connect() as conn:
            result = conn.execute(
                text("SELECT id, raw_text FROM narrative_chunks WHERE id = :id"),
                {"id": chunk_id}
            ).fetchone()
            
            if result:
                return NarrativeChunk(
                    id=result[0],
                    raw_text=result[1]
                )
            return None
    except Exception as e:
        logger.error(f"Error getting chunk by id {chunk_id}: {str(e)}")
        return None


def get_chunks_in_range(db: Engine, start_id: int, end_id: int) -> List[NarrativeChunk]:
    """Get all chunks in the specified id range."""
    try:
        with db.connect() as conn:
            results = conn.execute(
                text("""
                    SELECT id, raw_text 
                    FROM narrative_chunks 
                    WHERE id BETWEEN :start AND :end
                    ORDER BY id
                """),
                {"start": start_id, "end": end_id}
            ).fetchall()
            
            return [
                NarrativeChunk(
                    id=row[0],
                    raw_text=row[1]
                )
                for row in results
            ]
    except Exception as e:
        logger.error(f"Error getting chunks in range {start_id}-{end_id}: {str(e)}")
        return []


def get_all_chunks_needing_time_delta(db: Engine, primary_only: bool = False) -> List[NarrativeChunk]:
    """
    Get all chunks with missing or zero time_delta values.
    
    Args:
        db: Database engine
        primary_only: If True, return only chunks with world_layer='primary'
    """
    try:
        with db.connect() as conn:
            # Base query for chunks with missing time_delta
            query = """
                SELECT nc.id, nc.raw_text 
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE (cm.id IS NULL 
                   OR cm.time_delta IS NULL 
                   OR cm.time_delta = ''
                   OR cm.time_delta = '0 minutes')
            """
            
            # Add world_layer filter if requested
            if primary_only:
                query += " AND (cm.world_layer = 'primary' OR cm.world_layer IS NULL)"
                
            # Add ORDER BY clause
            query += " ORDER BY nc.id"
            
            results = conn.execute(text(query)).fetchall()
            
            return [
                NarrativeChunk(
                    id=row[0],
                    raw_text=row[1]
                )
                for row in results
            ]
    except Exception as e:
        logger.error(f"Error getting chunks needing time_delta: {str(e)}")
        return []


def get_chunk_world_layer(db: Engine, chunk_id: int) -> str:
    """Get the world_layer value for a chunk from the database."""
    try:
        with db.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT world_layer FROM chunk_metadata
                    WHERE chunk_id = :chunk_id
                """),
                {"chunk_id": chunk_id}
            ).fetchone()
            
            if result and result[0]:
                return result[0]
    except Exception as e:
        logger.warning(f"Error fetching chunk world_layer for chunk {chunk_id}: {str(e)}")
    
    # Default to "primary" if not found or error
    return "primary"


def get_context_chunks(db: Engine, target_id: int) -> Tuple[Optional[NarrativeChunk], Optional[NarrativeChunk]]:
    """Get preceding and following chunks for context."""
    prev_chunk = None
    next_chunk = None
    
    try:
        # Get previous chunk
        prev_chunk = get_chunk_by_id(db, target_id - 1)
        
        # Get next chunk
        next_chunk = get_chunk_by_id(db, target_id + 1)
    except Exception as e:
        logger.error(f"Error getting context chunks for id {target_id}: {str(e)}")
    
    return prev_chunk, next_chunk


def get_extended_context_chunks(db: Engine, target_id: int) -> Tuple[List[NarrativeChunk], List[NarrativeChunk]]:
    """
    Get extended context chunks, optimized for world layer transitions.
    
    This function aims to include at most 4 key context chunks:
    1. primary_last - The last primary-layer chunk before the current one
    2. primary_next - The next chunk after the current one
    3. meta_start - The first chunk in a non-primary sequence (if applicable)
    4. meta_end - The last chunk in a non-primary sequence (if applicable)
    
    Returns:
        Tuple of (previous_chunks, next_chunks)
    """
    prev_chunks = []
    next_chunks = []
    
    try:
        # Get next chunk (simple, just one chunk) - This is primary_next
        next_chunk = get_chunk_by_id(db, target_id + 1)
        if next_chunk:
            next_chunks.append(next_chunk)
        
        # For previous chunks, we need to find:
        # 1. The last primary chunk before this one (primary_last)
        # 2. If there's a non-primary sequence, its start and end (meta_start and meta_end)
        
        # First, check the immediately previous chunk
        current_id = target_id - 1
        if current_id >= 1:
            prev_chunk = get_chunk_by_id(db, current_id)
            if prev_chunk:
                prev_world_layer = get_chunk_world_layer(db, prev_chunk.id)
                
                # Is the previous chunk non-primary?
                if prev_world_layer != "primary":
                    # This is meta_end (the last non-primary chunk before current)
                    meta_end = prev_chunk
                    prev_chunks.insert(0, meta_end)
                    
                    # Look for meta_start and primary_last by scanning backwards
                    scan_id = current_id - 1
                    in_meta_sequence = True
                    meta_start_found = False
                    primary_last_found = False
                    
                    while scan_id >= 1 and (not meta_start_found or not primary_last_found):
                        scan_chunk = get_chunk_by_id(db, scan_id)
                        if not scan_chunk:
                            break
                            
                        scan_world_layer = get_chunk_world_layer(db, scan_chunk.id)
                        
                        if in_meta_sequence and scan_world_layer != "primary":
                            # Still in the meta sequence
                            if scan_id == current_id - 1:
                                # We've only gone back one chunk, can't be meta_start yet
                                pass
                            elif scan_id > 1:
                                # Check if next chunk BEFORE this one is primary
                                prev_scan_chunk = get_chunk_by_id(db, scan_id - 1)
                                if prev_scan_chunk:
                                    prev_scan_world_layer = get_chunk_world_layer(db, prev_scan_chunk.id)
                                    if prev_scan_world_layer == "primary":
                                        # This is meta_start
                                        meta_start = scan_chunk
                                        prev_chunks.insert(0, meta_start)
                                        meta_start_found = True
                            else:
                                # We're at ID 1, this must be meta_start
                                meta_start = scan_chunk
                                prev_chunks.insert(0, meta_start)
                                meta_start_found = True
                        elif scan_world_layer == "primary":
                            # Found a primary chunk - this is primary_last
                            primary_last = scan_chunk
                            prev_chunks.insert(0, primary_last)
                            primary_last_found = True
                            break  # We've found both, or at least primary_last
                        
                        scan_id -= 1
                    
                    # If we couldn't find meta_start but did find primary_last
                    # then primary_last is effectively meta_start too
                    
                else:  # Previous chunk is already primary
                    # This is primary_last
                    primary_last = prev_chunk
                    prev_chunks.insert(0, primary_last)
        
        # Log what we found
        if prev_chunks:
            chunks_desc = []
            for chunk in prev_chunks:
                layer = get_chunk_world_layer(db, chunk.id)
                chunks_desc.append(f"#{chunk.id} ({layer})")
            logger.debug(f"Context includes previous chunks: {', '.join(chunks_desc)}")
            
    except Exception as e:
        logger.error(f"Error getting extended context chunks for id {target_id}: {str(e)}")
    
    return prev_chunks, next_chunks


def build_time_estimation_prompt(chunk: NarrativeChunk, 
                              prev_chunks: List[NarrativeChunk] = None,
                              next_chunks: List[NarrativeChunk] = None,
                              prev_chunk_time_delta: Optional[str] = None) -> str:
    """
    Build prompt for the LLM to estimate time delta.
    
    Args:
        chunk: The target chunk to estimate time for
        prev_chunks: List of previous chunks for context (in chronological order)
        next_chunks: List of next chunks for context
        prev_chunk_time_delta: Time delta of the immediate previous chunk if known
    """
    prompt = f"""You are a narrative time analysis specialist. Your ONLY job is to estimate how much in-world time passes during the TARGET CHUNK.

TARGET CHUNK #{chunk.id} (ESTIMATE TIME FOR THIS CHUNK ONLY):
```
{chunk.raw_text}
```
"""

    # Add previous chunks if available
    if prev_chunks and len(prev_chunks) > 0:
        prompt += "\nPRECEDING CONTEXT (FOR CONTEXT ONLY, DO NOT INCLUDE IN TIME ESTIMATE):\n"
        
        for i, prev_chunk in enumerate(prev_chunks):
            # Only include time_delta info for the immediate previous chunk
            time_delta_info = ""
            if i == len(prev_chunks) - 1 and prev_chunk_time_delta:
                time_delta_info = f" [TIME ALREADY ACCOUNTED FOR: {prev_chunk_time_delta}]"
                
            prompt += f"""
PRECEDING CHUNK #{prev_chunk.id}{time_delta_info}:
```
{prev_chunk.raw_text}
```
"""

    # Add next chunks if available
    if next_chunks and len(next_chunks) > 0:
        prompt += "\nFOLLOWING CONTEXT (FOR CONTEXT ONLY, DO NOT INCLUDE IN TIME ESTIMATE):\n"
        
        for next_chunk in next_chunks:
            prompt += f"""
FOLLOWING CHUNK #{next_chunk.id}:
```
{next_chunk.raw_text}
```
"""

    # Add instructions
    prompt += f"""

Determine the realistic time_delta (amount of time passing in-world) for the provided narrative chunk.

### Context
You'll receive three consecutive narrative chunks:
- Previous chunk (for context)
- Target chunk (analyze this one only)
- Next chunk (for context)

The time_delta value you provide will be used to advance a story world's internal clock.

### Guidelines
- Account for dialogue duration (conversations generally take 5+ minutes)
- Consider realistic movement times based on distance and method
- Include combat/action sequences (generally 5-30+ minutes)
- Include thinking/observation time (1-2+ minutes)
- Round up all times to at least the nearest minute
- If a time skip is indicated in the target chunk (e.g., "the next morning"), include that time
- Don't double-count time already accounted for in the previous chunk 

### Response Format
Return a properly formatted JSON object:
{{
  "activities": [
    {{"name": "Conversation with bartender", "minutes": 15}},
    {{"name": "Walking to subway station", "minutes": 20}}
  ],
  "total_hours": 0,
  "total_minutes": 35,
  "formatted_time": "35 minutes"
}}

The JSON should include all identified activities, their durations, and the total time in hours/minutes.
"""

    return prompt


def query_llm(prompt: str, provider: str = "openai", model: Optional[str] = None, 
             temperature: float = 0.1, max_tokens: int = 2048, 
             reasoning_effort: str = "high", test_mode: bool = False) -> Union[str, LLMResponse]:
    """
    Query an LLM API with the prompt and return the response.
    
    Args:
        prompt: The prompt to send to the LLM
        provider: LLM provider to use, "openai" or "anthropic"
        model: Model name to use (defaults to provider's default)
        temperature: Model temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate in response
        reasoning_effort: Reasoning effort for OpenAI models ('low', 'medium', 'high')
        test_mode: If True, return a mock response instead of making an API call
        
    Returns:
        In test mode: A string containing the mock response
        In non-test mode: An LLMResponse object with structured data if available
    """
    logger.info(f"DEBUG: Entering query_llm for provider={provider}, model={model}")

    # Generate a mock response for testing/fallback
    mock_response = """
Activities identified in Chunk #1:
- Conversation between characters
- Brief scene description
- Movement within location

Estimated durations:
- Conversation: 10 minutes
- Scene observation: 2 minutes
- Movement: 3 minutes

Total time delta for Chunk #1: 15 minutes

{
  "activities": [
    {"name": "Conversation", "minutes": 10},
    {"name": "Scene observation", "minutes": 2},
    {"name": "Movement", "minutes": 3}
  ],
  "total_hours": 0,
  "total_minutes": 15,
  "formatted_time": "15 minutes"
}
"""
    
    # If in test mode, return mock response without making API call
    if test_mode:
        logger.info("TEST MODE: Using mock LLM response instead of making API call")
        return mock_response
    
    try:
        # Create LLM provider based on arguments
        logger.info(f"Creating LLM provider: {provider}")
        logger.info(f"DEBUG: Setting up provider kwargs with model={model}, temperature={temperature}")
        provider_kwargs = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Add reasoning_effort for OpenAI provider
        if provider.lower() == "openai":
            logger.info(f"DEBUG: Adding reasoning_effort={reasoning_effort} for OpenAI provider")
            provider_kwargs["reasoning_effort"] = reasoning_effort
            logger.info(f"Using reasoning effort: {reasoning_effort}")
        
        logger.info(f"DEBUG: About to create provider instance for {provider}")
        llm = LLMProvider.from_provider_name(
            provider_name=provider,
            **provider_kwargs
        )
        logger.info(f"DEBUG: Provider instance created successfully")
        
        # Log the actual model being used
        logger.info(f"Using {provider} model: {llm.model}")
        
        # Check TPM limits before calling the API
        logger.info(f"DEBUG: Checking TPM limits for prompt length {len(prompt)}")
        estimated_output_tokens = max(500, len(prompt) // 4)  # Rough estimate
        within_limit, input_tokens, total_tokens = llm.check_tpm_limit(prompt, estimated_output_tokens)
        logger.info(f"DEBUG: TPM check complete: within_limit={within_limit}, tokens={total_tokens}")
        
        if not within_limit:
            # This would exceed the TPM limit, abort
            logger.error(f"Request would exceed TPM limit set in settings.json")
            logger.error(f"Estimated tokens: {total_tokens} (input: {input_tokens}, output: ~{estimated_output_tokens})")
            logger.error(f"Try processing a smaller chunk or use a different provider")
            raise ValueError(f"TPM limit exceeded for {provider}. Too many tokens in a single request.")
        
        # Send the prompt to the LLM
        logger.info(f"Sending request to {provider} API")
        logger.info(f"DEBUG: About to call llm.get_completion()")
        response = llm.get_completion(prompt)
        logger.info(f"DEBUG: llm.get_completion() completed successfully")
        
        # Log token usage
        logger.info(f"API success: {response.input_tokens} input tokens, {response.output_tokens} output tokens")
        logger.info(f"Total token usage: {response.total_tokens}")
        
        # Calculate cost estimate
        cost_estimate = (
            response.input_tokens * llm.get_input_token_cost() +
            response.output_tokens * llm.get_output_token_cost()
        )
        logger.info(f"Estimated cost: ${cost_estimate:.6f}")
        
        # Return the full LLMResponse object for better parsing
        return response
        
    except Exception as e:
        logger.error(f"Error querying LLM: {str(e)}")
        
        # More detailed error logging based on provider
        if provider.lower() == "openai":
            if "insufficient_quota" in str(e) or "exceeded your current quota" in str(e):
                logger.error("OpenAI API quota exceeded. Please check your billing details.")
            elif "rate limit" in str(e).lower():
                logger.error("OpenAI API rate limit reached. Try again later or reduce request frequency.")
        elif provider.lower() == "anthropic":
            if "rate_limit" in str(e) or "rate limit" in str(e).lower():
                logger.error("Anthropic API rate limit reached. Try again later or reduce request frequency.")
            elif "auth" in str(e).lower() or "key" in str(e).lower():
                logger.error("Anthropic API authentication error. Check your API key.")
        
        # Instead of returning mock response on error, raise the exception
        logger.error("API call failed, raising exception.")
        raise e 


def parse_time_delta(response_input: Union[str, LLMResponse], test_mode: bool = False) -> timedelta:
    """Parse time delta from LLM response. Uses structured data if available,
    otherwise attempts to find JSON in the text, then falls back to regex patterns."""
    
    # If we're in test mode, use a fixed default time delta
    if test_mode:
        # If it's a primary chunk that needs time prediction, use a standard value
        logger.info("TEST MODE: Using default time delta of 15 minutes")
        return timedelta(minutes=15)
    
    # If response is an LLMResponse object, check for structured data
    if isinstance(response_input, LLMResponse) and response_input.structured_data is not None:
        try:
            # Use the structured data directly
            data = response_input.structured_data
            if 'total_hours' in data and 'total_minutes' in data:
                total_hours = int(data.get('total_hours', 0))
                total_minutes = int(data.get('total_minutes', 0))
                
                logger.info(f"Using structured data: {total_hours}h {total_minutes}m")
                
                # Also log the activities for informational purposes
                if 'activities' in data:
                    activities = data.get('activities', [])
                    logger.info(f"Activities breakdown:")
                    for activity in activities:
                        logger.info(f"  - {activity.get('name')}: {activity.get('minutes')} minutes")
                
                return timedelta(hours=total_hours, minutes=total_minutes)
            else:
                 logger.warning("Structured data found but missing 'total_hours' or 'total_minutes'")
        except Exception as e:
            logger.warning(f"Error parsing structured data: {e}")
    
    # Get the text to parse
    response_text = response_input.content if isinstance(response_input, LLMResponse) else response_input
    
    # Try to extract JSON from the response text
    try:
        import json
        
        # Log a small excerpt of the response for debugging
        excerpt = response_text[:200] + "..." if len(response_text) > 200 else response_text
        logger.debug(f"Parsing response text: {excerpt}")
        
        # First, check for any valid JSON block in the response
        # This is a more general approach to find JSON objects in text
        json_pattern = r'({[\s\S]*?"activities"[\s\S]*?"total_hours"[\s\S]*?"total_minutes"[\s\S]*?"formatted_time"[\s\S]*?})'
        json_matches = re.findall(json_pattern, response_text, re.DOTALL)
        
        if json_matches:
            logger.debug(f"Found {len(json_matches)} potential JSON blocks")
        else:
            logger.debug("No JSON objects found with standard pattern")
        
        for potential_json in json_matches:
            try:
                # Clean up the JSON string - replace any double braces (from our template) with single ones
                cleaned_json = potential_json.replace('{{', '{').replace('}}', '}')
                data = json.loads(cleaned_json)
                
                if 'total_hours' in data and 'total_minutes' in data:
                    total_hours = int(data.get('total_hours', 0))
                    total_minutes = int(data.get('total_minutes', 0))
                    
                    logger.info(f"Parsed JSON from response text: {total_hours}h {total_minutes}m")
                    logger.info(f"JSON: {cleaned_json}")
                    return timedelta(hours=total_hours, minutes=total_minutes)
            except Exception as e:
                logger.warning(f"JSON parsing error for candidate: {e}")
                continue
        
        # If no valid JSON found yet, try a more direct/simple approach
        try:
            # Try to simply parse the entire response as JSON
            data = json.loads(response_text)
            if 'total_hours' in data and 'total_minutes' in data:
                total_hours = int(data.get('total_hours', 0))
                total_minutes = int(data.get('total_minutes', 0))
                logger.info(f"Parsed entire response as JSON: {total_hours}h {total_minutes}m")
                return timedelta(hours=total_hours, minutes=total_minutes)
        except Exception as e:
            logger.debug(f"Could not parse entire response as JSON: {e}")
            
        # Look for JSON pattern with markdown code blocks as fallback
        json_pattern = r'```json\s*(.*?)\s*```'
        json_matches = re.findall(json_pattern, response_text, re.DOTALL)
        
        if json_matches:
            # Take the last match if multiple are found
            json_str = json_matches[-1]
            data = json.loads(json_str)
            
            # Extract time from the parsed JSON
            total_hours = int(data.get('total_hours', 0))
            total_minutes = int(data.get('total_minutes', 0))
            
            logger.info(f"Successfully parsed JSON from code block: {total_hours} hours, {total_minutes} minutes")
            logger.info(f"JSON: {json_str}")
            return timedelta(hours=total_hours, minutes=total_minutes)
                    
    except Exception as e:
        logger.warning(f"Failed during JSON extraction: {e}")

    # If we reached here, parsing failed. Raise an error instead of falling back.
    logger.error(f"Failed to parse time delta from response.")
    logger.error(f"Response excerpt: {response_text[:200]}...")
    raise ValueError("Could not parse time delta from LLM response")


def format_timedelta(td: timedelta) -> str:
    """Format timedelta as '2 hours 30 minutes' or '45 minutes'."""
    total_minutes = int(td.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    if hours > 0 and minutes > 0:
        return f"{hours} hours {minutes} minutes"
    elif hours > 0:
        return f"{hours} hours"
    else:
        return f"{minutes} minutes"


def update_chunk_metadata(db: Engine, chunk_id: int, time_delta: timedelta, test_mode: bool = False) -> bool:
    """Update time_delta in chunk_metadata table."""
    if test_mode:
        # Just print what would be updated
        formatted_time = format_timedelta(time_delta)
        logger.info(f"Would update chunk {chunk_id} with time_delta '{formatted_time}'")
        return True
    
    formatted_time = format_timedelta(time_delta)
    
    # Strip formatted_time to ensure there are no extra spaces
    formatted_time = formatted_time.strip()
    
    # Ensure we're not trying to store an empty string
    if not formatted_time:
        formatted_time = "0 minutes"
        logger.warning(f"Empty formatted_time, defaulting to '{formatted_time}'")
    
    try:
        # Use psycopg2 directly for better transaction control
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        try:
            # Check if metadata record exists
            cursor.execute(
                "SELECT 1 FROM chunk_metadata WHERE chunk_id = %s",
                (chunk_id,)
            )
            metadata_exists = cursor.fetchone() is not None
            
            if metadata_exists:
                # Update existing record
                cursor.execute(
                    """
                    UPDATE chunk_metadata 
                    SET time_delta = %s 
                    WHERE chunk_id = %s
                    """,
                    (formatted_time, chunk_id)
                )
                logger.info(f"Updated existing metadata record for chunk {chunk_id}")
            else:
                # Create new record
                cursor.execute(
                    """
                    INSERT INTO chunk_metadata 
                    (id, chunk_id, time_delta) 
                    VALUES (%s, %s, %s)
                    """,
                    (chunk_id, chunk_id, formatted_time)
                )
                logger.info(f"Created new metadata record for chunk {chunk_id}")
            
            # Verify the update actually happened
            cursor.execute(
                "SELECT time_delta FROM chunk_metadata WHERE chunk_id = %s",
                (chunk_id,)
            )
            result = cursor.fetchone()
            
            if result:
                logger.info(f"Verified database update: time_delta = '{result[0]}'")
            else:
                logger.warning("Update verification failed - could not find record after update")
            
            # Commit the transaction
            conn.commit()
            logger.info(f"Successfully committed transaction for chunk {chunk_id} with time_delta '{formatted_time}'")
            return True
        
        except Exception as inner_e:
            # Rollback in case of error
            conn.rollback()
            logger.error(f"Database error, transaction rolled back: {str(inner_e)}")
            raise inner_e
        
        finally:
            # Always close cursor and connection
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"Error updating chunk metadata for {chunk_id}: {str(e)}")
        return False


def get_chunk_time_delta(db: Engine, chunk_id: int) -> Optional[str]:
    """Get the time_delta for a specific chunk from the database."""
    try:
        with db.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT time_delta FROM chunk_metadata 
                    WHERE chunk_id = :chunk_id
                """),
                {"chunk_id": chunk_id}
            ).fetchone()
            
            if result and result[0]:
                return result[0]
    except Exception as e:
        logger.warning(f"Error fetching chunk time_delta: {str(e)}")
    
    return None


def process_chunk(db: Engine, chunk: NarrativeChunk, test_mode: bool = False,
                 provider: str = "openai", model: Optional[str] = None,
                 temperature: float = 0.1, max_tokens: int = 2048,
                 time_delta_cache: Optional[Dict[int, str]] = None,
                 auto_mode: bool = False,
                 reasoning_effort: str = "high",
                 verbose: bool = False) -> timedelta:
    """
    Process a single chunk to estimate and save time delta using an API-based LLM.
    
    For non-primary world layers (flashback, dream, etc.), time_delta is set to 0
    without calling the LLM.
    
    Args:
        db: Database engine
        chunk: The narrative chunk to process
        test_mode: If True, only print results and don't update the database
        provider: LLM provider to use ("openai" or "anthropic")
        model: Model name to use (defaults to provider's default)
        temperature: Model temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate in response
        time_delta_cache: Optional cache of time deltas by chunk ID
        auto_mode: If True, process without prompting
        
    Returns:
        Estimated time delta for the chunk
    """
    # Debug - log function entry and args
    logger.info(f"DEBUG: Entering process_chunk for chunk #{chunk.id}")

    # Initialize cache if needed (safety)
    if time_delta_cache is None:
        logger.warning(f"DEBUG: time_delta_cache was None, initializing empty dict")
        time_delta_cache = {}
    else:
        logger.info(f"DEBUG: Received time_delta_cache with {len(time_delta_cache)} entries")
    
    # Get the world layer for this chunk
    logger.info(f"DEBUG: Getting world_layer for chunk #{chunk.id}")
    world_layer = get_chunk_world_layer(db, chunk.id)
    logger.info(f"Processing chunk #{chunk.id} (id: {chunk.id}, world_layer: {world_layer})")
    
    # For non-primary world layers, automatically set time_delta to 0
    if world_layer != "primary":
        
        logger.info(f"Chunk #{chunk.id} has world_layer '{world_layer}' - setting time_delta to 0 minutes")
        
        # Set time_delta to 0 minutes
        zero_time_delta = timedelta(minutes=0)
        formatted_time = "0 minutes"
        
        # Update cache with zero time_delta
        time_delta_cache[chunk.id] = formatted_time
        
        # Print results in test mode
        if test_mode:
            logger.info(f"Chunk #{chunk.id} (non-primary world layer):")
            logger.info(f"Automatically set time_delta to: {formatted_time}")
        
        # Update database if not in test mode
        if not test_mode:
            update_chunk_metadata(db, chunk.id, zero_time_delta)
        
        return zero_time_delta
    
    # For primary world layer chunks, get extended context chunks
    logger.info(f"DEBUG: Getting extended context chunks for #{chunk.id}")
    prev_chunks, next_chunks = get_extended_context_chunks(db, chunk.id)
    logger.info(f"DEBUG: Got {len(prev_chunks)} previous chunks and {len(next_chunks)} next chunks")
    
    # Get time_delta for immediate previous chunk (from cache or database)
    prev_chunk_time_delta = None
    if prev_chunks and len(prev_chunks) > 0:
        logger.info(f"DEBUG: Getting time_delta for previous chunk #{prev_chunks[-1].id}")
        immediate_prev_chunk = prev_chunks[-1]  # Last in the list is immediate previous
        
        # Check cache first
        if immediate_prev_chunk.id in time_delta_cache:
            logger.info(f"DEBUG: Found prev chunk #{immediate_prev_chunk.id} in cache")
            prev_chunk_time_delta = time_delta_cache[immediate_prev_chunk.id]
            logger.info(f"Using cached time_delta for chunk #{immediate_prev_chunk.id}: {prev_chunk_time_delta}")
        else:
            # Not in cache, check database
            logger.info(f"DEBUG: Looking up prev chunk #{immediate_prev_chunk.id} in database")
            prev_chunk_time_delta = get_chunk_time_delta(db, immediate_prev_chunk.id)
            if prev_chunk_time_delta:
                logger.info(f"Found time_delta in database for chunk #{immediate_prev_chunk.id}: {prev_chunk_time_delta}")
    
    # Build prompt with context chunks
    logger.info(f"DEBUG: Building prompt for chunk #{chunk.id} with prev_chunk_time_delta={prev_chunk_time_delta}")
    prompt = build_time_estimation_prompt(
        chunk=chunk,
        prev_chunks=prev_chunks,
        next_chunks=next_chunks,
        prev_chunk_time_delta=prev_chunk_time_delta
    )
    logger.info(f"DEBUG: Prompt built successfully, length={len(prompt)}")
    
    # For test mode primary chunks, we can skip actual API calls and use defaults
    if test_mode and world_layer == "primary":
        logger.info(f"TEST MODE: Using mock response for primary chunk #{chunk.id}")
            
        # Return a default response
        llm_response = """
        {
          "activities": [
            {"name": "Conversation", "minutes": 10},
            {"name": "Scene observation", "minutes": 2},
            {"name": "Movement", "minutes": 3}
          ],
          "total_hours": 0,
          "total_minutes": 15,
          "formatted_time": "15 minutes"
        }
        """
    else:
        # Query LLM via API (or mock in test mode)
        logger.info(f"DEBUG: About to query {provider} API for chunk #{chunk.id}")
        llm_response = query_llm(
            prompt=prompt,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            test_mode=test_mode  # Pass test_mode to avoid making real API calls in test mode
        )
        logger.info(f"DEBUG: LLM query completed successfully")
    
    # Parse time delta - in production mode, llm_response may be a LLMResponse object or a string
    logger.info(f"DEBUG: About to parse time delta from response")
    time_delta = parse_time_delta(llm_response, test_mode=test_mode)
    formatted_time = format_timedelta(time_delta)
    
    # Update cache with new time_delta
    time_delta_cache[chunk.id] = formatted_time
    logger.info(f"Added chunk #{chunk.id} time_delta to cache: {formatted_time}")
    
    # Print results in test mode
    if test_mode:
        logger.info(f"Chunk #{chunk.id}:")
        logger.info(f"Estimated time delta: {formatted_time}")
        
        # Get response content for logging
        if isinstance(llm_response, str):
            response_content = llm_response
        else:
            response_content = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            
        # Log an excerpt of the response
        excerpt = response_content[:300] + "..." if len(response_content) > 300 else response_content
        logger.info(f"LLM response excerpt:\n{excerpt}\n")
    
    # Update database if not in test mode
    if not test_mode:
        update_chunk_metadata(db, chunk.id, time_delta)
    
    return time_delta


def main() -> int:
    """Main execution function."""
    # Parse arguments
    args = parse_arguments()
    
    # Print verbose mode message if enabled
    if args.verbose:
        logger.info("Verbose mode enabled - will print detailed prompts and context information")
        
    # Get database connection
    logger.info("Connecting to database")
    db = get_db_connection()
    
    # Determine which chunks to process
    if args.all:
        # Get all chunks, filtered by world layer if requested
        # By default, we only process primary world layer chunks
        primary_only = not args.include_all_world_layers
        logger.info(f"Retrieving all chunks needing time_delta (primary_only={primary_only})")
        chunks = get_all_chunks_needing_time_delta(db, primary_only=primary_only)
    else:
        logger.info(f"Retrieving chunks in range {args.start}-{args.end}")
        chunks = get_chunks_in_range(db, args.start, args.end)
    
    if not chunks:
        logger.info("No chunks found to process.")
        return 1
    
    logger.info(f"Processing {len(chunks)} chunks...")
    
    # Create a cache to store time_delta values across chunks
    time_delta_cache = {}
    
    # Initialize stats
    stats = {
        "total_chunks": len(chunks),
        "processed_chunks": 0,
        "api_calls": 0,
        "api_errors": 0,
        "provider": args.provider,
        "model": args.model or LLMProvider.from_provider_name(args.provider).model,
        "reasoning_effort": args.reasoning_effort if args.provider.lower() == "openai" else None,
        "primary_chunks": 0,
        "non_primary_chunks": 0
    }
    
    # Process chunks in batches for better user experience
    batch_size = 10
    for i in range(0, len(chunks), batch_size):
        # Get the current batch
        batch = chunks[i:i+batch_size]
        logger.info(f"Starting batch {i//batch_size + 1} of {(len(chunks) + batch_size - 1) // batch_size}")
        
        # Process each chunk in the batch
        for chunk in batch:
            try:
                # Check world layer first - if we're including all layers in processing
                world_layer = get_chunk_world_layer(db, chunk.id)
                
                # For non-primary chunks in verbose mode, print context info
                if world_layer != "primary" and args.verbose:
                    try:
                        # Print verbose info about this non-primary chunk
                        prev_chunks, next_chunks = get_extended_context_chunks(db, chunk.id)
                        
                        print("\n" + "="*80)
                        print(f"VERBOSE: Processing chunk #{chunk.id} (world_layer: {world_layer})")
                        print(f"VERBOSE: Non-primary world layer chunk - will automatically get 0 minutes")
                        print(f"VERBOSE: Context includes {len(prev_chunks)} previous chunks and {len(next_chunks)} next chunks")
                        
                        # Print details about included context
                        if prev_chunks:
                            print("\nVERBOSE: Previous context chunks:")
                            
                            # Identify each chunk's role in the context
                            for i, prev in enumerate(prev_chunks):
                                prev_layer = get_chunk_world_layer(db, prev.id)
                                role = ""
                                
                                if len(prev_chunks) == 1:
                                    # Only one chunk, must be primary_last
                                    role = "primary_last (last primary chunk before current)"
                                elif i == 0 and prev_layer == "primary":
                                    # First chunk and it's primary - must be primary_last
                                    role = "primary_last (last primary chunk before current)"
                                elif i == 0 and prev_layer != "primary":
                                    # First chunk but not primary - could be meta_start
                                    role = "meta_start (first non-primary chunk after primary)"
                                elif i == len(prev_chunks) - 1 and prev_layer != "primary":
                                    # Last chunk and not primary - must be meta_end
                                    role = "meta_end (last non-primary chunk before current)"
                                else:
                                    # Something else
                                    role = "context chunk"
                                    
                                print(f"  - Chunk #{prev.id} (world_layer: {prev_layer}) - {role}")
                        print("="*80 + "\n")
                    except Exception as e:
                        logger.warning(f"Error in verbose mode for non-primary chunk #{chunk.id}: {str(e)}")
                        logger.warning("Continuing with non-primary chunk processing")
                
                # In test mode for primary chunks
                if args.test and world_layer == "primary":
                    try:
                        # If verbose mode is enabled, show context information
                        if args.verbose:
                            # Print verbose info about this chunk's context
                            prev_chunks, next_chunks = get_extended_context_chunks(db, chunk.id)
                            
                            print("\n" + "="*80)
                            print(f"VERBOSE: Processing chunk #{chunk.id} (world_layer: {world_layer})")
                            print(f"VERBOSE: Context includes {len(prev_chunks)} previous chunks and {len(next_chunks)} next chunks")
                            
                            # Print details about included context
                            if prev_chunks:
                                print("\nVERBOSE: Previous context chunks:")
                                
                                # Identify each chunk's role in the context
                                for i, prev in enumerate(prev_chunks):
                                    prev_layer = get_chunk_world_layer(db, prev.id)
                                    role = ""
                                    
                                    if len(prev_chunks) == 1:
                                        # Only one chunk, must be primary_last
                                        role = "primary_last (last primary chunk before current)"
                                    elif i == 0 and prev_layer == "primary":
                                        # First chunk and it's primary - must be primary_last
                                        role = "primary_last (last primary chunk before current)"
                                    elif i == 0 and prev_layer != "primary":
                                        # First chunk but not primary - could be meta_start
                                        role = "meta_start (first non-primary chunk after primary)"
                                    elif i == len(prev_chunks) - 1 and prev_layer != "primary":
                                        # Last chunk and not primary - must be meta_end
                                        role = "meta_end (last non-primary chunk before current)"
                                    else:
                                        # Something else
                                        role = "context chunk"
                                        
                                    print(f"  - Chunk #{prev.id} (world_layer: {prev_layer}) - {role}")
                                        
                            # Print the prompt
                            prompt = build_time_estimation_prompt(
                                chunk=chunk,
                                prev_chunks=prev_chunks,
                                next_chunks=next_chunks,
                                prev_chunk_time_delta=get_chunk_time_delta(db, prev_chunks[-1].id) if prev_chunks and len(prev_chunks) > 0 else None
                            )
                            
                            # Print details about the prompt
                            print("\nVERBOSE: Prompt that would be sent to LLM (first 500 chars):")
                            print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
                            print("\nVERBOSE: Prompt excerpt (last 500 chars):")
                            print("..." + prompt[-500:] if len(prompt) > 500 else prompt)
                            
                            # Print a message explaining test mode
                            print("\nVERBOSE: TEST MODE - Using default time delta of 15 minutes (no API call made)")
                            print("="*80 + "\n")
                    except Exception as e:
                        logger.warning(f"Error in verbose mode for chunk #{chunk.id}: {str(e)}")
                        logger.warning("Continuing with test mode processing")
                    
                    # Use default 15 minutes for primary chunks - this part should run even if verbose mode has an error
                    time_delta = timedelta(minutes=15)
                    formatted_time = format_timedelta(time_delta)
                    logger.info(f"TEST MODE: Using default time delta of {formatted_time} for primary chunk #{chunk.id}")
                    
                    # Update cache
                    time_delta_cache[chunk.id] = formatted_time
                    
                    # Update stats
                    stats["processed_chunks"] += 1
                    stats["primary_chunks"] += 1
                    continue  # Skip to next chunk
                
                # The process_chunk function will automatically handle non-primary layers
                # by setting them to 0 without making API calls
                time_delta = process_chunk(
                    db=db,
                    chunk=chunk,
                    test_mode=args.test,
                    provider=args.provider,
                    model=args.model,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    time_delta_cache=time_delta_cache,
                    auto_mode=args.auto,
                    reasoning_effort=args.reasoning_effort,
                    verbose=args.verbose
                )
                
                # Update stats
                stats["processed_chunks"] += 1
                
                # Track primary vs. non-primary counts
                if world_layer == "primary":
                    stats["primary_chunks"] += 1
                    # Only count API calls for primary chunks in non-test mode
                    if not args.test:
                        stats["api_calls"] += 1
                else:
                    stats["non_primary_chunks"] += 1
                
                # Small delay between API calls (only for primary chunks in non-test mode)
                if not args.test and world_layer == "primary" and chunk != batch[-1]:
                    time.sleep(2)
                    
            except Exception as e:
                # Safer world_layer reference inside the exception handler
                try:
                    current_world_layer = get_chunk_world_layer(db, chunk.id)
                    if current_world_layer == "primary":
                        stats["api_errors"] += 1
                except:
                    # If we can't even get the world layer, assume it was a primary chunk
                    stats["api_errors"] += 1
                    current_world_layer = "unknown"
                
                # Provide more detailed error info in test mode
                if args.test:
                    import traceback
                    logger.error(f"TEST MODE Error processing chunk #{chunk.id} (world_layer: {current_world_layer}): {str(e)}")
                    logger.debug(traceback.format_exc())
                else:
                    logger.error(f"Error processing chunk #{chunk.id}: {str(e)}")
                    # Add repr(e) for more detailed exception info
                    logger.error(f"Exception repr: {repr(e)}") 
                    
                # Stop script execution on first error
                logger.error("Stopping script due to processing error.")
                sys.exit(1) # Exit with non-zero status
        
        # Print batch summary
        logger.info(f"Batch complete. Progress: {stats['processed_chunks']}/{stats['total_chunks']} chunks")
        logger.info(f"API calls: {stats['api_calls']} (errors: {stats['api_errors']})")
        logger.info(f"Primary chunks: {stats['primary_chunks']}, Non-primary: {stats['non_primary_chunks']}")
        
        # Check for rate limit errors
        rate_limited = False
        # Simple check - if more than 30% of the batch had errors, assume rate limits
        if stats["api_calls"] > 0 and stats["api_errors"] / max(1, stats["api_calls"]) > 0.3:
            rate_limited = True
        
        # If this isn't the last batch, handle continuation
        if i + batch_size < len(chunks) and not args.test:
            if rate_limited:
                # If we hit a rate limit, add longer wait time
                wait_time = 300  # 5 minutes
                logger.info(f"Rate limit detected. Waiting {wait_time} seconds before continuing...")
                
                if not args.auto:
                    # In manual mode, ask if user wants to wait or stop
                    continue_val = input(f"Continue after waiting {wait_time} seconds? [Y/n]: ")
                    if continue_val.lower() == 'n':
                        logger.info("Processing stopped by user")
                        break
                
                # Wait for the rate limit to reset
                time.sleep(wait_time)
                
            elif args.auto:
                # In auto mode, wait between batches to avoid API rate limits
                wait_time = 30  # seconds
                logger.info(f"Auto mode: Waiting {wait_time} seconds before next batch...")
                time.sleep(wait_time)
            else:
                # In manual mode, ask user to continue
                continue_val = input(f"Continue with next batch? [Y/n]: ")
                if continue_val.lower() == 'n':
                    logger.info("Processing stopped by user")
                    break
    
    # Print final summary
    logger.info(f"\nProcessing complete!")
    logger.info(f"Provider: {stats['provider']}")
    logger.info(f"Model: {stats['model']}")
    
    # Add reasoning effort info for OpenAI
    if stats['provider'].lower() == "openai" and stats['reasoning_effort']:
        logger.info(f"Reasoning effort: {stats['reasoning_effort']}")
    
    logger.info(f"Processed {stats['processed_chunks']}/{stats['total_chunks']} chunks successfully")
    logger.info(f"  - Primary world layer chunks: {stats['primary_chunks']}")
    logger.info(f"  - Non-primary world layer chunks: {stats['non_primary_chunks']}")
    logger.info(f"API calls: {stats['api_calls']} (errors: {stats['api_errors']})")
    
    # Log the cache contents for debugging
    if args.test:
        logger.info("Test mode - no changes made to database.")
    else:
        logger.info("Results written to database.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())