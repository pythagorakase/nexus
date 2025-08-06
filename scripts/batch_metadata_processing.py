#!/usr/bin/env python3
"""
Batch Processing Framework for NEXUS

This modular framework processes narrative chunks using various LLM providers.
It supports both Anthropic and OpenAI APIs, with a flexible architecture for
adding additional providers as needed.

Features:
- Multiple LLM provider support (Anthropic, OpenAI)
- Token-based windowing (defaults to 4000 tokens before, 2000 after)
- Batch processing with configurable batch size
- Retry logic for API failures
- Preserves existing values when updating records
- Comprehensive error handling and statistics

Usage:
    python batch_metadata_processing.py --all --provider anthropic --model claude-3-7-sonnet-20250219
    python batch_metadata_processing.py --missing --provider openai --model gpt-4o
    python batch_metadata_processing.py --range 1 100 --provider anthropic
    python batch_metadata_processing.py --chunk-id 42 --save-prompt
    python batch_metadata_processing.py --batch-size 10 --dry-run

Provider-specific options:
    --temperature FLOAT     Model temperature (0.0-1.0, default varies by provider)
    --max-tokens INT        Maximum tokens to generate in response
    --system-prompt TEXT    Optional system prompt to use (provider-specific)
"""

import os
import sys
import abc
import argparse
import logging
import re
import json
import time
import random
from typing import List, Dict, Any, Tuple, Optional, Union, Protocol, Type, runtime_checkable
from datetime import datetime, timedelta

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

import sqlalchemy as sa
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, Text, DateTime, inspect, Float
from sqlalchemy.dialects.postgresql import JSONB, INTERVAL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func

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

# Initialize database connection
Base = declarative_base()

# Load metadata schema
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                          "narrative_metadata_schema_modified.json")

try:
    with open(SCHEMA_PATH, 'r') as f:
        METADATA_SCHEMA = json.load(f)
    logger.info(f"Loaded metadata schema from {SCHEMA_PATH}")
except Exception as e:
    # Try falling back to original schema if modified schema is not found
    logger.warning(f"Failed to load modified schema: {str(e)}, trying original schema")
    ORIGINAL_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                        "narrative_metadata_schema_2.json")
    try:
        with open(ORIGINAL_SCHEMA_PATH, 'r') as f:
            METADATA_SCHEMA = json.load(f)
        logger.info(f"Loaded original metadata schema from {ORIGINAL_SCHEMA_PATH}")
    except Exception as e:
        logger.error(f"Failed to load any metadata schema: {str(e)}")
        METADATA_SCHEMA = {}


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
    
    @classmethod
    def from_provider_name(cls, provider_name: str, **kwargs) -> 'LLMProvider':
        """Factory method to create a provider from its name."""
        providers = {
            'anthropic': AnthropicProvider,
            'openai': OpenAIProvider,
        }
        
        provider_class = providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider '{provider_name}'. Available providers: {', '.join(providers.keys())}")
        
        return provider_class(**kwargs)


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
    """OpenAI provider implementation."""
    
    # Default model if none specified
    DEFAULT_MODEL = "gpt-4.1"
    
    # Model pricing (per 1M tokens as of April 2025)
    MODEL_PRICING = {
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    }
    
    def initialize(self) -> None:
        """Initialize the OpenAI client."""
        if not openai:
            raise ImportError("The 'openai' package is required for OpenAIProvider. Install with 'pip install openai'.")
            
        self.api_key = self.api_key or self._get_api_key()
        self.model = self.model or self.DEFAULT_MODEL
        self.client = openai.OpenAI(api_key=self.api_key)
        
    def get_completion(self, prompt: str) -> LLMResponse:
        """Get a completion from OpenAI."""
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


def get_db_connection_string():
    """
    Get the database connection string from environment variables or defaults.
    
    By default, connects to NEXUS database on localhost with the current user.
    Override with DB_* environment variables or --db-url flag.
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

# Define ORM models
class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'
    
    id = Column(Integer, primary_key=True)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())

class ChunkMetadata(Base):
    __tablename__ = 'chunk_metadata'
    
    # Primary key
    id = Column(Integer, primary_key=True)
    chunk_id = Column(Integer, ForeignKey('narrative_chunks.id', ondelete='CASCADE'), 
                     nullable=False, unique=True)
    
    # Required scalar fields - exactly matching the database schema
    world_layer = Column(String(50))
    location = Column(String(255))
    atmosphere = Column(String(255))
    season = Column(Integer)
    episode = Column(Integer)
    time_delta = Column(String(100))
    arc_position = Column(String(50))
    magnitude = Column(String(50))
    metadata_version = Column(String(20))
    generation_date = Column(DateTime)
    scene = Column(Integer)
    
    # JSON fields for complex metadata - these must match exactly what's in the database
    characters = Column(JSONB)
    direction = Column(JSONB)
    character_elements = Column(JSONB)
    perspective = Column(JSONB)
    interactions = Column(JSONB)
    dialogue_analysis = Column(JSONB)
    emotional_tone = Column(JSONB)
    narrative_function = Column(JSONB)
    narrative_techniques = Column(JSONB)
    thematic_elements = Column(JSONB)
    causality = Column(JSONB)
    continuity_markers = Column(JSONB)
    
    # Relationship to parent chunk
    chunk = relationship("NarrativeChunk", backref="metadata")

class ChunkEmbedding(Base):
    __tablename__ = 'chunk_embeddings'
    
    chunk_id = Column(Integer, ForeignKey('narrative_chunks.id', ondelete='CASCADE'), 
                     primary_key=True, nullable=False)
    model = Column(String(100), primary_key=True, nullable=False)
    embedding = Column(sa.dialects.postgresql.BYTEA, nullable=False)
    
    # Relationship to parent chunk
    chunk = relationship("NarrativeChunk", backref="embeddings")

def to_json(obj):
    """Convert an object to a JSON-serializable format."""
    if isinstance(obj, (datetime, timedelta)):
        return str(obj)
    elif isinstance(obj, uuid.UUID):
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

class MetadataProcessor:
    """
    Processes narrative chunks to generate metadata using various LLM providers.
    Supports both Anthropic Claude and OpenAI models.
    """
    
    def __init__(self, 
                db_url: str, 
                provider: Union[str, LLMProvider] = "anthropic", 
                model: Optional[str] = None,
                api_key: Optional[str] = None, 
                dry_run: bool = False, 
                window_tokens_before: int = 4000, 
                window_tokens_after: int = 2000,
                save_prompt: bool = False,
                temperature: float = 0.1,
                max_tokens: int = 4000,
                system_prompt: Optional[str] = None,
                batch_mode: bool = False,
                edge_context_chars: int = 500,
                overwrite_existing: bool = False):
        """
        Initialize the metadata processor.
        
        Args:
            db_url: PostgreSQL database URL
            provider: Either a string ('anthropic' or 'openai') or an LLMProvider instance
            model: Model name to use (defaults to provider's default)
            api_key: API key (optional, will try to get from environment)
            dry_run: If True, don't actually save results to the database
            window_tokens_before: Token count for context before the current chunk
            window_tokens_after: Token count for context after the current chunk
            save_prompt: If True, save the generated prompt to a file
            temperature: Model temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate in response
            system_prompt: Optional system prompt to use
            batch_mode: If True, process chunks in batches rather than individually
            edge_context_chars: Number of characters to include from adjacent chunks in batch mode
            overwrite_existing: If True, overwrite existing values even if not null
        """
        self.db_url = db_url
        self.dry_run = dry_run
        self.window_tokens_before = window_tokens_before
        self.window_tokens_after = window_tokens_after
        self.save_prompt = save_prompt
        self.batch_mode = batch_mode
        self.edge_context_chars = edge_context_chars
        self.overwrite_existing = overwrite_existing
        
        # Initialize LLM provider
        if isinstance(provider, LLMProvider):
            self.llm = provider
        else:
            self.llm = LLMProvider.from_provider_name(
                provider_name=provider,
                api_key=api_key,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt
            )
        
        # Initialize database connection
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # Initialize the database schema if needed
        self.initialize_database()
        
        # Load schema for prompt construction
        self.schema = METADATA_SCHEMA
        
        # Statistics
        self.stats = {
            "total_chunks": 0,
            "processed_chunks": 0,
            "api_calls": 0,
            "api_errors": 0,
            "created_metadata": 0,
            "updated_metadata": 0,
            "tokens_used": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_estimate": 0.0,
            "provider": provider if isinstance(provider, str) else provider.__class__.__name__,
            "model": self.llm.model
        }
    
    def initialize_database(self):
        """Initialize database tables if they don't exist."""
        # Create chunk_metadata table if it doesn't exist
        inspector = inspect(self.engine)
        
        if 'chunk_metadata' not in inspector.get_table_names():
            ChunkMetadata.__table__.create(self.engine)
            logger.info("Created chunk_metadata table")
    
    def get_chunks_by_id_range(self, start: int, end: int) -> List[NarrativeChunk]:
        """Get chunks within an ID range."""
        session = self.Session()
        try:
            chunks = session.query(NarrativeChunk)\
                .filter(NarrativeChunk.id >= start)\
                .filter(NarrativeChunk.id <= end)\
                .order_by(NarrativeChunk.id).all()
            return chunks
        finally:
            session.close()
    
    def get_all_chunks(self) -> List[NarrativeChunk]:
        """Get all narrative chunks ordered by ID."""
        session = self.Session()
        try:
            chunks = session.query(NarrativeChunk).order_by(NarrativeChunk.id).all()
            return chunks
        finally:
            session.close()
    
    def get_chunks_without_metadata(self) -> List[NarrativeChunk]:
        """Get all chunks that don't have metadata yet."""
        session = self.Session()
        try:
            # Query for chunks that don't have a related metadata record
            chunks = session.query(NarrativeChunk)\
                .outerjoin(ChunkMetadata, NarrativeChunk.id == ChunkMetadata.chunk_id)\
                .filter(ChunkMetadata.chunk_id == None)\
                .order_by(NarrativeChunk.id).all()
            return chunks
        finally:
            session.close()
    
    def get_chunk_by_id(self, chunk_id: int) -> Optional[NarrativeChunk]:
        """Get a specific chunk by its ID."""
        session = self.Session()
        try:
            chunk = session.query(NarrativeChunk).filter(NarrativeChunk.id == chunk_id).first()
            return chunk
        finally:
            session.close()
    
    def get_context_chunks(self, chunk: NarrativeChunk, 
                         tokens_before: int = None, 
                         tokens_after: int = None) -> Dict[str, Any]:
        """
        Get surrounding chunks as context, based on token count.
        
        Args:
            chunk: The current chunk being processed
            tokens_before: Max token count for context before current chunk
            tokens_after: Max token count for context after current chunk
            
        Returns:
            Dict with context chunks and token counts
        """
        if tokens_before is None:
            tokens_before = self.window_tokens_before
            
        if tokens_after is None:
            tokens_after = self.window_tokens_after
        
        session = self.Session()
        try:
            # Get chunks before the current one
            before_chunks = []
            before_tokens = 0
            
            if tokens_before > 0:
                # Query chunks before the current one, ordered by id descending
                chunks_before = session.query(NarrativeChunk)\
                    .filter(NarrativeChunk.id < chunk.id)\
                    .order_by(NarrativeChunk.id.desc()).all()
                
                for before_chunk in chunks_before:
                    # Estimate token count (approx 1 token per 4 chars)
                    token_estimate = len(before_chunk.raw_text) // 4
                    
                    if before_tokens + token_estimate <= tokens_before:
                        before_chunks.append(before_chunk)
                        before_tokens += token_estimate
                    else:
                        break
                
                # Reverse to get chronological order
                before_chunks.reverse()
            
            # Get chunks after the current one
            after_chunks = []
            after_tokens = 0
            
            if tokens_after > 0:
                # Query chunks after the current one, ordered by id
                chunks_after = session.query(NarrativeChunk)\
                    .filter(NarrativeChunk.id > chunk.id)\
                    .order_by(NarrativeChunk.id).all()
                
                for after_chunk in chunks_after:
                    # Estimate token count
                    token_estimate = len(after_chunk.raw_text) // 4
                    
                    if after_tokens + token_estimate <= tokens_after:
                        after_chunks.append(after_chunk)
                        after_tokens += token_estimate
                    else:
                        break
            
            # Current chunk token count
            current_tokens = len(chunk.raw_text) // 4
            
            return {
                "before_chunks": before_chunks,
                "after_chunks": after_chunks,
                "before_tokens": before_tokens,
                "current_tokens": current_tokens,
                "after_tokens": after_tokens,
                "total_tokens": before_tokens + current_tokens + after_tokens
            }
        finally:
            session.close()
    
    def ensure_jsonb(self, value: Any, field_name: str) -> Any:
        """
        Ensures a value is suitable for a JSONB column by handling string conversions.
        
        Args:
            value: The value to convert/validate
            field_name: Name of the field (for logging)
            
        Returns:
            Python object suitable for JSONB storage
        """
        if value is None:
            return None
            
        if isinstance(value, str):
            try:
                # If it's a string, try to parse it as JSON
                result = json.loads(value)
                logger.info(f"Parsed {field_name} from JSON string")
                return result
            except Exception as e:
                logger.warning(f"Could not parse {field_name} JSON: {str(e)}")
                # Return the original string if parsing fails - will be stored as a JSON string
                return value
        else:
            # If it's already a Python object, return it as is
            return value
    
    def build_prompt(self, chunk: NarrativeChunk, context: Dict[str, Any]) -> str:
        """
        Build the prompt for Claude API to generate metadata.
        
        Args:
            chunk: Current chunk to process
            context: Context chunks and token counts
            
        Returns:
            Prompt string for Claude API
        """
        # Construct the prompt
        prompt = f"""You are an advanced narrative annotation system. Your task is to analyze a narrative passage and extract structured metadata according to the provided schema.

# CHUNK TO ANALYZE
This is chunk #{chunk.id} that needs metadata analysis:

```
{chunk.raw_text}
```

# SURROUNDING CONTEXT (FOR REFERENCE ONLY)
"""

        if context["before_chunks"]:
            prompt += "## PRECEDING NARRATIVE:\n"
            for i, c in enumerate(context["before_chunks"]):
                prompt += f"[Chunk #{c.id}]\n"
                
                # If we have many chunks, summarize older ones
                if i < len(context["before_chunks"]) - 2:
                    # Include first paragraph only for older context
                    text_lines = c.raw_text.split('\n')
                    first_para = '\n'.join(text_lines[:min(5, len(text_lines))])
                    prompt += f"{first_para}\n...[content truncated]...\n\n"
                else:
                    # Show full text for immediate context
                    prompt += f"{c.raw_text}\n\n"
        
        if context["after_chunks"]:
            prompt += "## FOLLOWING NARRATIVE:\n"
            for i, c in enumerate(context["after_chunks"]):
                prompt += f"[Chunk #{c.id}]\n"
                
                # Always include just the first few lines of future chunks
                text_lines = c.raw_text.split('\n')
                first_para = '\n'.join(text_lines[:min(5, len(text_lines))])
                prompt += f"{first_para}\n...[content truncated]...\n\n"
        
        # Add schema 
        prompt += f"""
# METADATA SCHEMA
Below is the JSON schema for the metadata. You must follow this structure exactly.
```json
{json.dumps(self.schema["chunk_metadata"], indent=2)}
```

# INSTRUCTIONS
1. Analyze the chunk and extract metadata according to the schema.
2. Return ONLY a valid JSON object with your analysis.
3. Ensure every field is filled appropriately; use null for unknown values.
4. DO NOT include comments or explanations outside the JSON.
5. DO NOT include the season, episode, or time_delta fields - we already have those or handle them separately.
6. Use the context for continuity but focus your analysis on the main chunk.

Your response should be ONLY a valid JSON object.
"""
        
        return prompt
    
    def process_chunk(self, chunk: NarrativeChunk, retries: int = 3, 
                    backoff_factor: float = 1.5) -> Dict[str, Any]:
        """
        Process a single chunk using the configured LLM provider.
        
        Args:
            chunk: Narrative chunk to process
            retries: Number of API retries on failure
            backoff_factor: Exponential backoff factor for retries
            
        Returns:
            Metadata dictionary
        """
        logger.info(f"Processing chunk with ID: {chunk.id} using {self.llm.__class__.__name__} ({self.llm.model})")
        
        # Get context chunks
        context = self.get_context_chunks(chunk)
        logger.info(f"Context: {context['before_tokens']} tokens before, "
                  f"{context['after_tokens']} tokens after")
        
        # Build prompt
        prompt = self.build_prompt(chunk, context)
        
        # Save prompt to file if requested
        if self.save_prompt:
            prompt_dir = "prompts"
            os.makedirs(prompt_dir, exist_ok=True)
            prompt_file = os.path.join(prompt_dir, f"chunk_{chunk.id}_{self.llm.__class__.__name__}_{self.llm.model}_prompt.txt")
            with open(prompt_file, 'w') as f:
                f.write(prompt)
            logger.info(f"Saved prompt to {prompt_file}")
        
        # If we're in dry run mode, estimate token usage without making an API call
        if self.dry_run:
            # Get accurate token count using tiktoken
            input_tokens = self.llm.count_tokens(prompt)
            
            # Estimate output token count based on prompt structure and model
            # Generally LLMs return more concise outputs for structured JSON
            if "claude" in self.llm.model.lower():
                # Claude tends to be slightly more verbose
                output_tokens = max(500, input_tokens // 4)
            else:
                # Other models like GPT tend to be more concise with JSON
                output_tokens = max(400, input_tokens // 5)
            
            # Update token usage stats with accurate counts
            self.stats["api_calls"] += 1
            self.stats["input_tokens"] += input_tokens
            self.stats["output_tokens"] += output_tokens
            self.stats["tokens_used"] += input_tokens + output_tokens
            
            # Calculate cost estimate
            input_cost = input_tokens * self.llm.get_input_token_cost()
            output_cost = output_tokens * self.llm.get_output_token_cost()
            self.stats["cost_estimate"] += input_cost + output_cost
            
            logger.info(f"DRY RUN - Accurate count: {input_tokens} input tokens, ~{output_tokens} output tokens (estimated)")
            logger.info(f"DRY RUN - The prompt is {input_tokens} tokens and {len(prompt)} characters")
            
            # Return a minimal mock metadata to continue processing flow
            return {"dry_run": True, "orientation": {"world_layer": "primary"}}
        
        # Call LLM API with retries
        attempt = 0
        while attempt < retries:
            try:
                attempt += 1
                
                logger.info(f"API call attempt {attempt}/{retries}")
                self.stats["api_calls"] += 1
                
                # Get completion from the LLM provider
                response = self.llm.get_completion(prompt)
                
                # Update token usage stats
                self.stats["input_tokens"] += response.input_tokens
                self.stats["output_tokens"] += response.output_tokens
                self.stats["tokens_used"] += response.total_tokens
                
                # Calculate cost estimate
                input_cost = response.input_tokens * self.llm.get_input_token_cost()
                output_cost = response.output_tokens * self.llm.get_output_token_cost()
                self.stats["cost_estimate"] += input_cost + output_cost
                
                logger.info(f"API success: {response.input_tokens} input tokens, {response.output_tokens} output tokens")
                
                # Extract and clean up content
                content = response.content
                
                # Clean up response to extract just the JSON
                # Some models might add markdown code block markers
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                metadata = json.loads(content)
                return metadata
                
            except Exception as e:
                self.stats["api_errors"] += 1
                error_str = str(e)
                
                # Enhanced error handling with provider-specific guidance
                if "openai" in self.stats["provider"].lower():
                    if "insufficient_quota" in error_str or "exceeded your current quota" in error_str:
                        logger.error(f"OpenAI API quota exceeded. Please check your billing details or use a different API key.")
                    elif "rate limit" in error_str.lower():
                        logger.error(f"OpenAI API rate limit reached. Try again later or reduce request frequency.")
                    else:
                        logger.error(f"OpenAI API Error on attempt {attempt}: {error_str}")
                elif "anthropic" in self.stats["provider"].lower():
                    if "rate_limit" in error_str or "rate limit" in error_str.lower():
                        logger.error(f"Anthropic API rate limit reached. Try again later or reduce request frequency.")
                    elif "auth" in error_str.lower() or "key" in error_str.lower():
                        logger.error(f"Anthropic API authentication error. Check your API key.")
                    else:
                        logger.error(f"Anthropic API Error on attempt {attempt}: {error_str}")
                else:
                    logger.error(f"API Error on attempt {attempt}: {error_str}")
                
                if attempt < retries:
                    # Exponential backoff with jitter
                    sleep_time = backoff_factor ** attempt + random.uniform(0, 1)
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Failed all {retries} attempts. Giving up on chunk with ID: {chunk.id}")
                    raise
        
        return None
    
    def should_update_field(self, existing_obj, field_name) -> bool:
        """
        Determine if a field should be updated based on overwrite setting.
        
        Args:
            existing_obj: The existing database object
            field_name: Name of the field to check
            
        Returns:
            True if the field should be updated
        """
        if self.overwrite_existing:
            return True
        
        # If the field doesn't exist or is None, update it
        current_value = getattr(existing_obj, field_name, None)
        return current_value is None
        
    def save_metadata(self, chunk: NarrativeChunk, metadata: Dict[str, Any]) -> None:
        """
        Save metadata to the database.
        
        Args:
            chunk: Narrative chunk
            metadata: Metadata dictionary from API
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Would save metadata for chunk with ID: {chunk.id}")
            return
        
        session = self.Session()
        try:
            # We'll read season and episode from database - they're already set by extract_season_episode.py
            # Let's query the existing values to make sure we preserve them
            session2 = self.Session()
            chunk_meta = session2.query(ChunkMetadata).filter(ChunkMetadata.chunk_id == chunk.id).first()
            if chunk_meta:
                # Use existing values from database
                season = chunk_meta.season
                episode = chunk_meta.episode
                session2.close()
            else:
                # Default values if not found
                season = 1
                episode = 1
            
            # Check if metadata already exists for this chunk
            metadata_exists = session.query(ChunkMetadata).filter(ChunkMetadata.chunk_id == chunk.id).first()
            
            # If metadata exists and we're not overwriting, check if we should skip any fields
            if metadata_exists and not self.overwrite_existing:
                logger.info(f"Existing metadata found for chunk {chunk.id}, preserving non-null values")
            
            if metadata_exists:
                # Update existing metadata
                # Always update world_layer as it's a fundamental classification
                metadata_exists.world_layer = metadata.get("orientation", {}).get("world_layer", "primary")
                
                # The database doesn't have a 'setting' column - it has location and atmosphere as separate columns
                if "orientation" in metadata and "setting" in metadata.get("orientation", {}):
                    setting = metadata.get("orientation", {}).get("setting", {})
                    
                    # Check if we should update location
                    if "location" in setting and (self.overwrite_existing or metadata_exists.location is None):
                        metadata_exists.location = setting.get("location")
                        
                    # Check if we should update atmosphere
                    if "atmosphere" in setting and (self.overwrite_existing or metadata_exists.atmosphere is None):
                        metadata_exists.atmosphere = setting.get("atmosphere")
                
                # Preserve season and episode values
                # DO NOT update these from the API response
                metadata_exists.season = season
                metadata_exists.episode = episode
                
                # Try to parse time_delta if it exists
                time_delta_str = metadata.get("chronology", {}).get("time_delta")
                if time_delta_str and isinstance(time_delta_str, str):
                    try:
                        # Try to parse time_delta to a timedelta
                        parts = time_delta_str.split()
                        hours = 0
                        minutes = 0
                        for i in range(0, len(parts)-1, 2):
                            if parts[i+1].startswith('hour'):
                                hours = int(parts[i])
                            elif parts[i+1].startswith('minute'):
                                minutes = int(parts[i])
                        metadata_exists.time_delta = timedelta(hours=hours, minutes=minutes)
                    except Exception as e:
                        logger.warning(f"Could not parse time_delta '{time_delta_str}': {str(e)}")
                        metadata_exists.time_delta = timedelta(0)
                
                # Handle fields from schema that map to database columns
                # First, handle scalar fields
                if "narrative_vector" in metadata:
                    narrative_vector = metadata.get("narrative_vector", {})
                    
                    # Apply overwrite rules to each field
                    if "arc_position" in narrative_vector and (self.overwrite_existing or metadata_exists.arc_position is None):
                        metadata_exists.arc_position = narrative_vector.get("arc_position")
                        
                    if "magnitude" in narrative_vector and (self.overwrite_existing or metadata_exists.magnitude is None):
                        metadata_exists.magnitude = narrative_vector.get("magnitude")
                        
                    if "direction" in narrative_vector and (self.overwrite_existing or metadata_exists.direction is None):
                        # Direction is JSONB in database, but array in schema
                        direction = narrative_vector.get("direction")
                        if isinstance(direction, str):
                            try:
                                metadata_exists.direction = json.loads(direction)
                            except Exception as e:
                                logger.warning(f"Could not parse direction JSON: {str(e)}")
                        else:
                            metadata_exists.direction = direction
                
                # Handle setting fields
                if "orientation" in metadata and "setting" in metadata.get("orientation", {}):
                    setting = metadata.get("orientation", {}).get("setting", {})
                    if "location" in setting:
                        metadata_exists.location = setting.get("location")
                    if "atmosphere" in setting:
                        metadata_exists.atmosphere = setting.get("atmosphere")
                
                # Handle prose fields
                if "prose" in metadata:
                    prose = metadata.get("prose", {})
                    # Process narrative_function which is a JSONB array in the database
                    if "function" in prose:
                        function_value = prose.get("function")
                        if isinstance(function_value, str):
                            try:
                                metadata_exists.narrative_function = json.loads(function_value)
                            except Exception as e:
                                logger.warning(f"Could not parse function JSON: {str(e)}")
                        else:
                            metadata_exists.narrative_function = function_value
                    
                    # Process narrative_techniques
                    if "narrative_techniques" in prose:
                        techniques = prose.get("narrative_techniques")
                        if isinstance(techniques, str):
                            try:
                                metadata_exists.narrative_techniques = json.loads(techniques)
                            except Exception as e:
                                logger.warning(f"Could not parse techniques JSON: {str(e)}")
                        else:
                            metadata_exists.narrative_techniques = techniques
                    
                    # Process thematic_elements
                    if "thematic_elements" in prose:
                        elements = prose.get("thematic_elements")
                        if isinstance(elements, str):
                            try:
                                metadata_exists.thematic_elements = json.loads(elements)
                            except Exception as e:
                                logger.warning(f"Could not parse elements JSON: {str(e)}")
                        else:
                            metadata_exists.thematic_elements = elements
                
                # Process character elements
                if "characters" in metadata and "elements" in metadata.get("characters", {}):
                    elements = metadata.get("characters", {}).get("elements")
                    if isinstance(elements, str):
                        try:
                            metadata_exists.character_elements = json.loads(elements)
                        except Exception as e:
                            logger.warning(f"Could not parse character elements JSON: {str(e)}")
                    else:
                        metadata_exists.character_elements = elements
                
                # Process each field from the API and map to the database structure
                # Some fields map directly to columns, others are stored as JSONB

                # Handle narrative_vector fields - split between scalar columns and JSONB
                if "narrative_vector" in metadata:
                    narrative_vector = metadata.get("narrative_vector", {})
                    
                    # Scalar fields
                    if "arc_position" in narrative_vector:
                        metadata_exists.arc_position = narrative_vector.get("arc_position")
                    if "magnitude" in narrative_vector:
                        metadata_exists.magnitude = narrative_vector.get("magnitude")
                    
                    # JSONB field 'direction'
                    if "direction" in narrative_vector:
                        metadata_exists.direction = self.ensure_jsonb(narrative_vector.get("direction"), "direction")
                
                # Handle prose-related fields - all are JSONB
                if "prose" in metadata:
                    prose = metadata.get("prose", {})
                    
                    # JSONB fields
                    if "function" in prose:
                        metadata_exists.narrative_function = self.ensure_jsonb(prose.get("function"), "narrative_function")
                    if "narrative_techniques" in prose:
                        metadata_exists.narrative_techniques = self.ensure_jsonb(prose.get("narrative_techniques"), "narrative_techniques")
                    if "thematic_elements" in prose:
                        metadata_exists.thematic_elements = self.ensure_jsonb(prose.get("thematic_elements"), "thematic_elements")
                    if "emotional_tone" in prose:
                        metadata_exists.emotional_tone = self.ensure_jsonb(prose.get("emotional_tone"), "emotional_tone")
                    if "dialogue_analysis" in prose:
                        metadata_exists.dialogue_analysis = self.ensure_jsonb(prose.get("dialogue_analysis"), "dialogue_analysis")
                
                # Handle character-related fields - all are JSONB
                if "characters" in metadata:
                    chars = metadata.get("characters", {})
                    
                    # Main characters field - could be a roster or the whole object
                    metadata_exists.characters = self.ensure_jsonb(chars, "characters")
                    
                    # Other character-related fields
                    if "elements" in chars:
                        metadata_exists.character_elements = self.ensure_jsonb(chars.get("elements"), "character_elements")
                    if "perspective" in chars:
                        metadata_exists.perspective = self.ensure_jsonb(chars.get("perspective"), "perspective")
                    if "interactions" in chars:
                        metadata_exists.interactions = self.ensure_jsonb(chars.get("interactions"), "interactions")
                
                # Handle causality field - JSONB
                if "causality" in metadata:
                    metadata_exists.causality = self.ensure_jsonb(metadata.get("causality"), "causality")
                
                # Handle continuity markers - JSONB
                if "orientation" in metadata and "continuity_markers" in metadata.get("orientation", {}):
                    metadata_exists.continuity_markers = self.ensure_jsonb(
                        metadata.get("orientation", {}).get("continuity_markers"), 
                        "continuity_markers"
                    )
                
                # Update generation_date to track when this metadata was updated
                metadata_exists.generation_date = datetime.now()
                
                # Extract and save slug if available
                if "chronology" in metadata and season and episode:
                    scene_id = f"S{season:02d}E{episode:02d}"
                    metadata_exists.slug = scene_id
                
                self.stats["updated_metadata"] += 1
                logger.info(f"Updated metadata for chunk with ID: {chunk.id}")
            else:
                # Initialize a new metadata record with basic scalar fields
                new_metadata = ChunkMetadata(
                    chunk_id=chunk.id,
                    world_layer=metadata.get("orientation", {}).get("world_layer", "primary"),
                    
                    # Preserve season and episode values from the database
                    season=season,
                    episode=episode,
                    
                    # Set generation date
                    generation_date=datetime.now()
                )
                
                # Handle scalar fields from nested structures
                
                # Process setting fields - go to separate scalar columns
                if "orientation" in metadata and "setting" in metadata.get("orientation", {}):
                    setting = metadata.get("orientation", {}).get("setting", {})
                    if "location" in setting:
                        new_metadata.location = setting.get("location")
                    if "atmosphere" in setting:
                        new_metadata.atmosphere = setting.get("atmosphere")
                
                # Handle narrative_vector fields - some go to scalar columns
                if "narrative_vector" in metadata:
                    narrative_vector = metadata.get("narrative_vector", {})
                    if "arc_position" in narrative_vector:
                        new_metadata.arc_position = narrative_vector.get("arc_position")
                    if "magnitude" in narrative_vector:
                        new_metadata.magnitude = narrative_vector.get("magnitude")
                    # Direction is a JSONB field
                    if "direction" in narrative_vector:
                        new_metadata.direction = self.ensure_jsonb(narrative_vector.get("direction"), "direction")
                
                # Process JSONB fields - using our helper method for consistency
                
                # Handle prose-related fields
                if "prose" in metadata:
                    prose = metadata.get("prose", {})
                    
                    if "function" in prose:
                        new_metadata.narrative_function = self.ensure_jsonb(prose.get("function"), "narrative_function")
                    if "narrative_techniques" in prose:
                        new_metadata.narrative_techniques = self.ensure_jsonb(prose.get("narrative_techniques"), "narrative_techniques")
                    if "thematic_elements" in prose:
                        new_metadata.thematic_elements = self.ensure_jsonb(prose.get("thematic_elements"), "thematic_elements")
                    if "emotional_tone" in prose:
                        new_metadata.emotional_tone = self.ensure_jsonb(prose.get("emotional_tone"), "emotional_tone")
                    if "dialogue_analysis" in prose:
                        new_metadata.dialogue_analysis = self.ensure_jsonb(prose.get("dialogue_analysis"), "dialogue_analysis")
                
                # Handle character-related fields
                if "characters" in metadata:
                    chars = metadata.get("characters", {})
                    
                    # Characters is the whole object or just the roster
                    new_metadata.characters = self.ensure_jsonb(chars, "characters")
                    
                    # Process other character-related fields
                    if "elements" in chars:
                        new_metadata.character_elements = self.ensure_jsonb(chars.get("elements"), "character_elements")
                    if "perspective" in chars:
                        new_metadata.perspective = self.ensure_jsonb(chars.get("perspective"), "perspective")
                    if "interactions" in chars:
                        new_metadata.interactions = self.ensure_jsonb(chars.get("interactions"), "interactions")
                
                # Handle other top-level JSONB fields
                if "causality" in metadata:
                    new_metadata.causality = self.ensure_jsonb(metadata.get("causality"), "causality")
                
                if "orientation" in metadata and "continuity_markers" in metadata.get("orientation", {}):
                    new_metadata.continuity_markers = self.ensure_jsonb(
                        metadata.get("orientation", {}).get("continuity_markers"),
                        "continuity_markers"
                    )
                
                # Try to parse time_delta if it exists
                time_delta_str = metadata.get("chronology", {}).get("time_delta")
                if time_delta_str and isinstance(time_delta_str, str):
                    try:
                        # Try to parse time_delta to a timedelta
                        parts = time_delta_str.split()
                        hours = 0
                        minutes = 0
                        for i in range(0, len(parts)-1, 2):
                            if parts[i+1].startswith('hour'):
                                hours = int(parts[i])
                            elif parts[i+1].startswith('minute'):
                                minutes = int(parts[i])
                        new_metadata.time_delta = timedelta(hours=hours, minutes=minutes)
                    except Exception as e:
                        logger.warning(f"Could not parse time_delta '{time_delta_str}': {str(e)}")
                        new_metadata.time_delta = timedelta(0)
                
                # Extract and save slug if available
                if "chronology" in metadata and season and episode:
                    scene_id = f"S{season:02d}E{episode:02d}"
                    new_metadata.slug = scene_id
                
                session.add(new_metadata)
                self.stats["created_metadata"] += 1
                logger.info(f"Created new metadata for chunk with ID: {chunk.id}")
            
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving metadata: {str(e)}")
        finally:
            session.close()
    
    def process_chunks_in_batches(self, chunks: List[NarrativeChunk], batch_size: int = 10) -> Dict[str, Any]:
        """
        Process chunks by sending entire batches to the LLM at once.
        
        Args:
            chunks: List of chunks to process
            batch_size: Number of chunks to include in each LLM request
            
        Returns:
            Statistics dictionary
        """
        self.stats["total_chunks"] = len(chunks)
        
        if self.stats["total_chunks"] == 0:
            logger.info("No chunks to process")
            return self.stats
        
        logger.info(f"Processing {self.stats['total_chunks']} chunks in batches of {batch_size}")
        
        # Process chunks in batches
        for i in range(0, len(chunks), batch_size):
            chunk_batch = chunks[i:i+batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} of {(len(chunks) + batch_size - 1) // batch_size}")
            
            # Get edge context if needed and available
            edge_context_before = ""
            edge_context_after = ""
            
            if self.edge_context_chars > 0:
                # Get context from chunk before this batch
                if i > 0:
                    edge_context_before = chunks[i-1].raw_text[-self.edge_context_chars:]
                    logger.info(f"Added {len(edge_context_before)} chars of context before batch")
                
                # Get context from chunk after this batch
                if i + batch_size < len(chunks):
                    edge_context_after = chunks[i+batch_size].raw_text[:self.edge_context_chars]
                    logger.info(f"Added {len(edge_context_after)} chars of context after batch")
            
            try:
                # Process the entire batch at once
                batch_metadata = self.process_chunk_batch(chunk_batch, edge_context_before, edge_context_after)
                
                # Save the metadata for each chunk
                if batch_metadata:
                    for chunk_id, metadata in batch_metadata.items():
                        # Find the chunk with this ID
                        chunk = next((c for c in chunk_batch if str(c.id) == str(chunk_id)), None)
                        if chunk:
                            self.save_metadata(chunk, metadata)
                            self.stats["processed_chunks"] += 1
                        else:
                            logger.warning(f"Chunk with ID {chunk_id} not found in batch")
                
            except Exception as e:
                logger.error(f"Error processing batch {i//batch_size + 1}: {str(e)}")
            
            # Print status after each batch
            cost = self.stats["cost_estimate"]
            logger.info(f"Batch complete. Progress: {self.stats['processed_chunks']}/{self.stats['total_chunks']} chunks")
            logger.info(f"API calls: {self.stats['api_calls']} (errors: {self.stats['api_errors']})")
            logger.info(f"Tokens used: {self.stats['tokens_used']} (est. cost: ${cost:.4f})")
            
            # If this isn't the last batch, ask to continue
            if i + batch_size < len(chunks) and not self.dry_run:
                continue_val = input(f"Continue with next batch? [Y/n]: ")
                if continue_val.lower() == 'n':
                    logger.info("Processing stopped by user")
                    break
        
        return self.stats
        
    def process_chunk_batch(self, chunks: List[NarrativeChunk], 
                          edge_context_before: str = "", 
                          edge_context_after: str = "",
                          retries: int = 3,
                          backoff_factor: float = 1.5) -> Dict[str, Dict[str, Any]]:
        """
        Process multiple chunks in a single API call.
        
        Args:
            chunks: List of chunks to process together
            edge_context_before: Text from a chunk before the batch
            edge_context_after: Text from a chunk after the batch
            retries: Number of API retries on failure
            backoff_factor: Exponential backoff factor for retries
            
        Returns:
            Dictionary mapping chunk IDs to their metadata dictionaries
        """
        if not chunks:
            return {}
            
        logger.info(f"Processing batch of {len(chunks)} chunks using {self.llm.__class__.__name__} ({self.llm.model})")
        
        # Build batch prompt
        prompt = self.build_batch_prompt(chunks, edge_context_before, edge_context_after)
        
        # Save prompt to file if requested
        if self.save_prompt:
            prompt_dir = "prompts"
            os.makedirs(prompt_dir, exist_ok=True)
            chunk_ids = "_".join([str(chunk.id) for chunk in chunks[:3]])
            if len(chunks) > 3:
                chunk_ids += f"_and_{len(chunks)-3}_more"
            prompt_file = os.path.join(prompt_dir, 
                                     f"batch_{chunk_ids}_{self.llm.__class__.__name__}_{self.llm.model}_prompt.txt")
            with open(prompt_file, 'w') as f:
                f.write(prompt)
            logger.info(f"Saved batch prompt to {prompt_file}")
        
        # If we're in dry run mode, estimate token usage without making an API call
        if self.dry_run:
            # Get accurate token count using tiktoken
            input_tokens = self.llm.count_tokens(prompt)
            
            # Estimate output token count based on prompt structure, model, and batch size
            # Each chunk in the batch will require some amount of output tokens
            if "claude" in self.llm.model.lower():
                # Claude tends to be more verbose with JSON structures
                base_tokens = 300
                per_chunk_output = 250
            else:
                # GPT models tend to be more concise
                base_tokens = 200
                per_chunk_output = 200
                
            # Calculate total output tokens
            output_tokens = base_tokens + (len(chunks) * per_chunk_output)
            
            # Update token usage stats with accurate counts
            self.stats["api_calls"] += 1
            self.stats["input_tokens"] += input_tokens
            self.stats["output_tokens"] += output_tokens
            self.stats["tokens_used"] += input_tokens + output_tokens
            
            # Calculate cost estimate
            input_cost = input_tokens * self.llm.get_input_token_cost()
            output_cost = output_tokens * self.llm.get_output_token_cost()
            self.stats["cost_estimate"] += input_cost + output_cost
            
            # Log detailed token information
            avg_tokens_per_chunk = input_tokens // max(1, len(chunks))
            logger.info(f"DRY RUN - Accurate count: {input_tokens} input tokens (~{avg_tokens_per_chunk} per chunk)")
            logger.info(f"DRY RUN - Estimated output: ~{output_tokens} tokens (~{per_chunk_output} per chunk)")
            logger.info(f"DRY RUN - Total batch size: {input_tokens + output_tokens} tokens")
            
            # Create mock results for all chunks in the batch
            mock_result = {}
            for chunk in chunks:
                mock_result[str(chunk.id)] = {
                    "dry_run": True, 
                    "orientation": {"world_layer": "primary"}
                }
            return mock_result
        
        # Call LLM API with retries
        attempt = 0
        while attempt < retries:
            try:
                attempt += 1
                
                logger.info(f"API call attempt {attempt}/{retries}")
                self.stats["api_calls"] += 1
                
                # Get completion from the LLM provider
                response = self.llm.get_completion(prompt)
                
                # Update token usage stats
                self.stats["input_tokens"] += response.input_tokens
                self.stats["output_tokens"] += response.output_tokens
                self.stats["tokens_used"] += response.total_tokens
                
                # Calculate cost estimate
                input_cost = response.input_tokens * self.llm.get_input_token_cost()
                output_cost = response.output_tokens * self.llm.get_output_token_cost()
                self.stats["cost_estimate"] += input_cost + output_cost
                
                logger.info(f"API success: {response.input_tokens} input tokens, {response.output_tokens} output tokens")
                
                # Extract and clean up content
                content = response.content
                
                # Clean up response to extract just the JSON
                # Some models might add markdown code block markers
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                batch_metadata = json.loads(content)
                return batch_metadata
                
            except Exception as e:
                self.stats["api_errors"] += 1
                error_str = str(e)
                
                # Enhanced error handling with provider-specific guidance
                if "openai" in self.stats["provider"].lower():
                    if "insufficient_quota" in error_str or "exceeded your current quota" in error_str:
                        logger.error(f"OpenAI API quota exceeded. Please check your billing details or use a different API key.")
                    elif "rate limit" in error_str.lower():
                        logger.error(f"OpenAI API rate limit reached. Try again later or reduce request frequency.")
                    else:
                        logger.error(f"OpenAI API Error on attempt {attempt}: {error_str}")
                elif "anthropic" in self.stats["provider"].lower():
                    if "rate_limit" in error_str or "rate limit" in error_str.lower():
                        logger.error(f"Anthropic API rate limit reached. Try again later or reduce request frequency.")
                    elif "auth" in error_str.lower() or "key" in error_str.lower():
                        logger.error(f"Anthropic API authentication error. Check your API key.")
                    else:
                        logger.error(f"Anthropic API Error on attempt {attempt}: {error_str}")
                else:
                    logger.error(f"API Error on attempt {attempt}: {error_str}")
                
                if attempt < retries:
                    # Exponential backoff with jitter
                    sleep_time = backoff_factor ** attempt + random.uniform(0, 1)
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Failed all {retries} attempts. Giving up on batch")
                    raise
        
        return {}
        
    def build_batch_prompt(self, chunks: List[NarrativeChunk], 
                         edge_context_before: str = "", 
                         edge_context_after: str = "") -> str:
        """
        Build a prompt for processing multiple chunks in a single API call.
        
        Args:
            chunks: List of chunks to process together
            edge_context_before: Text from a chunk before the batch
            edge_context_after: Text from a chunk after the batch
            
        Returns:
            Prompt string for the LLM API
        """
        # Construct the prompt
        prompt = f"""You are an advanced narrative annotation system. Your task is to analyze multiple narrative passages and extract structured metadata for each one.

# CHUNKS TO ANALYZE
"""
        # Add each chunk with its ID
        for i, chunk in enumerate(chunks):
            prompt += f"\n## CHUNK {chunk.id}\n"
            prompt += f"```\n{chunk.raw_text}\n```\n"
            
        # Add edge context if provided
        if edge_context_before or edge_context_after:
            prompt += "\n# EDGE CONTEXT (FOR REFERENCE ONLY)\n"
            
            if edge_context_before:
                prompt += f"\n## CONTEXT BEFORE FIRST CHUNK\n```\n{edge_context_before}\n```\n"
                
            if edge_context_after:
                prompt += f"\n## CONTEXT AFTER LAST CHUNK\n```\n{edge_context_after}\n```\n"
        
        # Add schema
        prompt += f"""
# METADATA SCHEMA
Below is the JSON schema for the metadata. You must follow this structure exactly.
```json
{json.dumps(self.schema["chunk_metadata"], indent=2)}
```

# INSTRUCTIONS
1. Analyze each chunk and extract metadata according to the schema.
2. Return a JSON object where keys are chunk IDs and values are the metadata for each chunk.
3. Example format:
```json
{{
  "1": {{ 
    "orientation": {{ ... }},
    "chronology": {{ ... }},
    ...
  }},
  "2": {{ 
    "orientation": {{ ... }},
    "chronology": {{ ... }},
    ...
  }}
}}
```
4. Ensure every field is filled appropriately; use null for unknown values.
5. DO NOT include comments or explanations outside the JSON.
6. DO NOT include the season, episode, or time_delta fields - we already have those or handle them separately.
7. Use the context for continuity but focus your analysis on the main chunks.

Your response must be a valid JSON object only.
"""
        
        return prompt

    def process_batch(self, chunks: List[NarrativeChunk], batch_size: int = 10) -> Dict[str, Any]:
        """
        Process chunks, either individually or in batches based on configuration.
        
        Args:
            chunks: List of chunks to process
            batch_size: Number of chunks to process in a batch before prompting to continue
            
        Returns:
            Statistics dictionary
        """
        self.stats["total_chunks"] = len(chunks)
        
        if self.stats["total_chunks"] == 0:
            logger.info("No chunks to process")
            return self.stats
        
        if self.batch_mode:
            return self.process_chunks_in_batches(chunks, batch_size)
        
        # Traditional mode - process chunks individually
        logger.info(f"Processing {self.stats['total_chunks']} chunks in batches of {batch_size}")
        
        # Process chunks in batches for user interaction purposes
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            logger.info(f"Starting batch {i//batch_size + 1} of {(len(chunks) + batch_size - 1) // batch_size}")
            
            for chunk in batch:
                try:
                    # Process the chunk
                    metadata = self.process_chunk(chunk)
                    
                    # Save the metadata
                    if metadata:
                        self.save_metadata(chunk, metadata)
                        self.stats["processed_chunks"] += 1
                    
                except Exception as e:
                    logger.error(f"Error processing chunk with ID {chunk.id}: {str(e)}")
            
            # Print status after each batch
            cost = self.stats["cost_estimate"]
            logger.info(f"Batch complete. Progress: {self.stats['processed_chunks']}/{self.stats['total_chunks']} chunks")
            logger.info(f"API calls: {self.stats['api_calls']} (errors: {self.stats['api_errors']})")
            logger.info(f"Tokens used: {self.stats['tokens_used']} (est. cost: ${cost:.4f})")
            
            # If this isn't the last batch, ask to continue
            if i + batch_size < len(chunks) and not self.dry_run:
                if len(chunks) > batch_size:
                    continue_val = input(f"Continue with next batch? [Y/n]: ")
                    if continue_val.lower() == 'n':
                        logger.info("Processing stopped by user")
                        break
        
        return self.stats

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Process narrative chunks and generate metadata with various LLM providers")
    
    # Target chunk selection arguments
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Process all chunks")
    group.add_argument("--missing", action="store_true", help="Process only chunks without metadata")
    group.add_argument("--range", nargs=2, type=int, metavar=("START", "END"),
                      help="Process chunks in an ID range (inclusive)")
    group.add_argument("--chunk-id", type=int, help="Process a specific chunk by ID")
    
    # LLM provider options
    provider_group = parser.add_argument_group("LLM Provider Options")
    provider_group.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic",
                             help="LLM provider to use (default: anthropic)")
    provider_group.add_argument("--model", 
                             help="Model name to use (defaults to provider's default)")
    provider_group.add_argument("--api-key", help="API key (optional)")
    provider_group.add_argument("--temperature", type=float, default=0.1,
                             help="Model temperature (0.0-1.0, default: 0.1)")
    provider_group.add_argument("--max-tokens", type=int, default=4000,
                             help="Maximum tokens to generate in response (default: 4000)")
    provider_group.add_argument("--system-prompt", 
                             help="Optional system prompt to use (provider-specific)")
    
    # Context window options
    context_group = parser.add_argument_group("Context Window Options")
    context_group.add_argument("--window-before", type=int, default=4000,
                             help="Token window size for context before the chunk (default: 4000)")
    context_group.add_argument("--window-after", type=int, default=2000,
                             help="Token window size for context after the chunk (default: 2000)")
    
    # Processing options
    process_group = parser.add_argument_group("Processing Options")
    process_group.add_argument("--batch-size", type=int, default=10,
                             help="Number of chunks to process before prompting to continue (default: 10)")
    process_group.add_argument("--batch-mode", action="store_true",
                             help="Process multiple chunks in a single API call")
    process_group.add_argument("--edge-context", type=int, default=500,
                             help="Characters of context to include from adjacent chunks in batch mode (default: 500)")
    process_group.add_argument("--dry-run", action="store_true", 
                             help="Don't actually save results to the database")
    process_group.add_argument("--overwrite-existing", action="store_true",
                             help="Overwrite existing metadata values even if not null")
    process_group.add_argument("--save-prompt", action="store_true",
                             help="Save the generated prompts to files for inspection")
    process_group.add_argument("--db-url", 
                        help="Database connection URL (optional, defaults to environment variables or NEXUS database on localhost)")
    process_group.add_argument("--output-json", help="Save processing statistics to JSON file")
    
    args = parser.parse_args()
    
    # Get database connection string
    db_url = args.db_url or get_db_connection_string()
    
    # Validate provider-specific requirements
    try:
        if args.provider == "anthropic" and anthropic is None:
            raise ImportError("The 'anthropic' package is required for the Anthropic provider. Install with 'pip install anthropic'")
        if args.provider == "openai" and openai is None:
            raise ImportError("The 'openai' package is required for the OpenAI provider. Install with 'pip install openai'")
            
        # Initialize processor
        processor = MetadataProcessor(
            db_url=db_url,
            provider=args.provider,
            model=args.model,
            api_key=args.api_key,
            dry_run=args.dry_run,
            window_tokens_before=args.window_before,
            window_tokens_after=args.window_after,
            save_prompt=args.save_prompt,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            system_prompt=args.system_prompt,
            batch_mode=args.batch_mode,
            edge_context_chars=args.edge_context,
            overwrite_existing=args.overwrite_existing
        )
        
        # Log configuration info
        logger.info(f"Initialized processor with {args.provider} provider, model: {processor.llm.model}")
        
    except ImportError as e:
        logger.error(f"Error: {str(e)}")
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        print(f"Configuration error: {str(e)}", file=sys.stderr)
        return 1
    
    # Get chunks to process
    if args.all:
        logger.info("Processing all chunks")
        chunks = processor.get_all_chunks()
    elif args.missing:
        logger.info("Processing chunks without metadata")
        chunks = processor.get_chunks_without_metadata()
    elif args.range:
        start, end = args.range
        logger.info(f"Processing chunks in ID range {start}-{end}")
        chunks = processor.get_chunks_by_id_range(start, end)
    elif args.chunk_id:
        logger.info(f"Processing chunk with ID {args.chunk_id}")
        chunk = processor.get_chunk_by_id(args.chunk_id)
        if chunk:
            chunks = [chunk]
        else:
            logger.error(f"Chunk with ID {args.chunk_id} not found")
            return 1
    
    # Process chunks
    stats = processor.process_batch(chunks, batch_size=args.batch_size)
    
    # Print summary
    logger.info("\nProcessing Summary:")
    logger.info(f"Provider: {stats['provider']}")
    logger.info(f"Model: {stats['model']}")
    logger.info(f"Total chunks: {stats['total_chunks']}")
    logger.info(f"Processed chunks: {stats['processed_chunks']}")
    logger.info(f"API calls: {stats['api_calls']} (errors: {stats['api_errors']})")
    logger.info(f"Tokens: {stats['tokens_used']} total ({stats['input_tokens']} input, {stats['output_tokens']} output)")
    logger.info(f"Estimated cost: ${stats['cost_estimate']:.4f}")
    
    if args.dry_run:
        logger.info("DRY RUN: No changes were made to the database")
    else:
        logger.info(f"Created new metadata records: {stats['created_metadata']}")
        logger.info(f"Updated existing metadata records: {stats['updated_metadata']}")
    
    # Save stats to JSON if requested
    if args.output_json:
        try:
            stats_copy = stats.copy()
            stats_copy["run_completed_at"] = datetime.utcnow().isoformat() + "Z"
            stats_copy["command_line_args"] = vars(args)
            
            with open(args.output_json, 'w') as f:
                json.dump(stats_copy, f, indent=2)
            logger.info(f"Statistics saved to {args.output_json}")
        except Exception as e:
            logger.error(f"Failed to save statistics to {args.output_json}: {str(e)}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())