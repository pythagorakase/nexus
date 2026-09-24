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

from nexus.database import database_url

import os
import sys
import abc
import copy
import argparse
import asyncio
import logging
import re
import json
import time
import signal
import threading
from typing import (
    List,
    Dict,
    Any,
    Tuple,
    Optional,
    Union,
    Protocol,
    Type,
    TypeVar,
    Literal,
    cast,
    Callable,
)
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

from nexus.api.native_structured_output import (
    WireContractViolation,
    openai_response_text_format,
    retry_prompt,
    run_output_validator,
    structured_output_error_text,
)
from nexus.telemetry.usage import (
    provider_name_from_base_url,
    record_openai_response,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("metadata_processing.log"), logging.StreamHandler()],
)
logger = logging.getLogger("nexus.metadata")

# Default TPM limits if settings file is not available
DEFAULT_TPM_LIMITS = {"openai": 30000}

DEFAULT_COOLDOWNS = {"individual": 15, "batch": 30, "rate_limit": 300}

# Load settings using centralized config loader
try:
    from nexus.config import load_settings_as_dict

    SETTINGS = load_settings_as_dict()
    TPM_LIMITS = SETTINGS.get("API Settings", {}).get("TPM", DEFAULT_TPM_LIMITS)
    COOLDOWNS = SETTINGS.get("API Settings", {}).get("cooldowns", DEFAULT_COOLDOWNS)
except Exception as e:
    logger.warning(
        f"Failed to load settings via config loader: {str(e)}. Using defaults."
    )
    TPM_LIMITS = DEFAULT_TPM_LIMITS
    COOLDOWNS = DEFAULT_COOLDOWNS


class LLMResponse:
    """Standardized response object from any LLM provider."""

    def __init__(
        self,
        content: str,
        input_tokens: int,
        output_tokens: int,
        model: str,
        raw_response: Any = None,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ):
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
        if (
            model.startswith("gpt-3.5")
            or model.startswith("gpt-4")
            or model.startswith("o")
        ):
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
        logger.warning(
            f"Failed to get token count using tiktoken: {str(e)}. Falling back to character-based estimation."
        )
        return len(text) // 4


class LLMProvider(abc.ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        system_prompt: Optional[str] = None,
    ):
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

    def check_tpm_limit(
        self, prompt: str, estimated_output_tokens: Optional[int] = None
    ) -> Tuple[bool, int, int]:
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
            logger.warning(
                f"No TPM limit found for provider {self.provider_name}. Proceeding without limits."
            )
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
            logger.warning(
                f"TPM limit exceeded: Request would use {total_tokens} tokens but limit is {tpm_limit}"
            )
            logger.warning(
                f"This exceeds the {self.provider_name} TPM limit set in settings.json"
            )

        return within_limit, input_tokens, total_tokens


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation."""

    STRUCTURED_OUTPUT_RETRIES = 1

    # Valid reasoning effort levels (model-specific)
    VALID_REASONING_EFFORTS = ["minimal", "medium", "high", "low", None]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = 0.1,
        max_tokens: int = 4000,
        max_output_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        base_url: Optional[str] = None,
        structured_transport: Literal["responses", "chat_completions"] = "responses",
        request_timeout: Optional[float] = None,
        structured_output_retries: Optional[int] = None,
        output_validator: Optional[Any] = None,
        request_params: Optional[Dict[str, Any]] = None,
        usage_provider_name: Optional[str] = None,
        usage_seat: Optional[str] = None,
    ):
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
            structured_transport: OpenAI-compatible surface used for strict
                structured output
            request_timeout: Optional request timeout in seconds. None uses the
                OpenAI SDK default.
            structured_output_retries: Validation retry budget for structured
                output agents (apex.structured_output_retries in nexus.toml)
            output_validator: Optional async pydantic_ai output validator
                registered on structured agents (may raise ModelRetry)
            request_params: Per-model provider-specific request-body params
                from the registry (issue #580), merged into chat-completions
                calls via the SDK's extra_body
            usage_provider_name: Registry provider name for billing identity
            usage_seat: Optional logical operation recorded for each response
        """
        self.reasoning_effort = reasoning_effort
        # Deep copy: nested param objects (e.g. {"reasoning": {"effort": ...}})
        # must not alias caller state or the built request dicts.
        self.request_params = copy.deepcopy(request_params) if request_params else {}
        self.max_output_tokens = max_output_tokens or max_tokens
        self.base_url = base_url
        self.usage_provider_name = usage_provider_name or provider_name_from_base_url(
            native_name="openai",
            base_url=base_url,
        )
        self.usage_seat = usage_seat
        self.request_timeout = request_timeout
        if structured_transport not in {"responses", "chat_completions"}:
            raise ValueError(
                "structured_transport must be 'responses' or 'chat_completions'"
            )
        if structured_transport == "chat_completions" and not base_url:
            raise ValueError(
                "structured_transport='chat_completions' requires a base_url"
            )
        self.structured_transport = structured_transport
        self.structured_output_retries = (
            structured_output_retries
            if structured_output_retries is not None
            else self.STRUCTURED_OUTPUT_RETRIES
        )
        self.output_validator = output_validator
        # Summary consumers inspect completion status before any JSON parsing.
        self.response_check: Optional[Callable[[Any], None]] = None

        # Validate reasoning effort if provided
        if (
            reasoning_effort is not None
            and reasoning_effort not in self.VALID_REASONING_EFFORTS
        ):
            raise ValueError(
                f"Invalid reasoning effort: {reasoning_effort}. Valid values: {self.VALID_REASONING_EFFORTS}"
            )

        # Call parent init
        super().__init__(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )

    def initialize(self) -> None:
        """Initialize the OpenAI client."""
        if not openai:
            raise ImportError(
                "The 'openai' package is required for OpenAIProvider. Install with 'pip install openai'."
            )

        self.provider_name = "openai"
        from nexus.config import load_settings

        settings = load_settings()
        if self.model is None:
            from nexus.config.story_model import resolve_seat

            self.model = resolve_seat("ir_eval.judgment.model", settings=settings).model
        from nexus.config.provider_guard import require_test_provider

        try:
            provider = settings.provider_for_model(self.model)
        except ValueError as exc:
            raise ValueError(
                f"Model {self.model!r} is not declared in nexus.toml's "
                "[global.model.api_models] registry; add its parameter capabilities."
            ) from exc
        require_test_provider(self.model, settings=settings)
        entry = next(
            entry
            for entry in settings.global_.model.api_models[provider].models
            if entry.id == self.model
        )
        self.unsupported_params = frozenset(entry.unsupported_params)
        self.is_reasoning_model = entry.reasoning_accounting != "none"
        self.supports_temperature = "temperature" not in self.unsupported_params

        self.api_key = self.api_key or self._get_api_key()

        # Create client with optional base_url for mock servers
        client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
            logger.info(f"Using custom base URL: {self.base_url}")
        if self.request_timeout is not None:
            client_kwargs["timeout"] = self.request_timeout
        self.client = openai.OpenAI(**client_kwargs)

        # Log the model type
        if self.is_reasoning_model:
            logger.info(
                f"Using reasoning model: {self.model} with effort: {self.reasoning_effort}"
            )
        else:
            logger.info(
                f"Using standard model: {self.model} with temperature: {self.temperature}"
            )

    def get_completion(
        self, prompt: str, cache_key: Optional[str] = None
    ) -> LLMResponse:
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
        prompt_cache_key: Optional[str] = None,
    ) -> Tuple[Any, LLMResponse]:
        """
        Get a structured completion using OpenAI native strict schema output.

        Args:
            prompt: The input prompt
            schema_model: A Pydantic BaseModel class defining the output schema
            prompt_cache_key: Optional stable routing key for OpenAI prompt caching

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
            provider = OpenAIProvider()  # Uses ir_eval.judgment.model
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
            prompt,
            schema_model,
            text_format=text_format,
            prompt_cache_key=prompt_cache_key,
        )

    async def get_structured_completion_async(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
        prompt_cache_key: Optional[str] = None,
    ) -> Tuple[Any, LLMResponse]:
        """Get a structured completion without blocking an existing event loop."""
        return await self._get_structured_completion_native_async(
            prompt,
            schema_model,
            text_format=text_format,
            prompt_cache_key=prompt_cache_key,
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

    def _log_structured_output_rejection(
        self,
        *,
        transport: Literal["responses", "chat_completions"],
        attempt: int,
        exc: BaseException,
    ) -> None:
        """Log one validation rejection and any terminal retry exhaustion."""

        attempt_number = attempt + 1
        error_text = structured_output_error_text(exc)
        exception_name = type(exc).__name__
        logger.warning(
            "structured-output rejected transport=%s model=%s seat=%s "
            "attempt=%d exception=%s error=%s",
            transport,
            self.model,
            self.usage_seat,
            attempt_number,
            exception_name,
            error_text,
        )
        if attempt >= self.structured_output_retries:
            logger.warning(
                "structured-output retries exhausted transport=%s model=%s "
                "seat=%s attempt=%d exception=%s error=%s action=propagate",
                transport,
                self.model,
                self.usage_seat,
                attempt_number,
                exception_name,
                error_text,
            )

    def _get_structured_completion_native_sync(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
        prompt_cache_key: Optional[str] = None,
    ) -> Tuple[Any, LLMResponse]:
        """Run a native strict-schema Responses request with bounded repair."""

        if self.structured_transport == "chat_completions":
            return self._get_structured_completion_chat_completions_sync(
                prompt, schema_model, text_format=text_format
            )

        from pydantic_ai import ModelRetry

        active_prompt = prompt
        last_error: Optional[BaseException] = None
        for attempt in range(self.structured_output_retries + 1):
            handed_off = False
            response: Any = None
            usage_outcome: Literal["accepted", "rejected_validation", "error"] = "error"
            guard = getattr(self, "prompt_window_guard", None)
            if guard is not None:
                guard(
                    active_prompt,
                    attempt + 1,
                    text_format=text_format
                    or openai_response_text_format(schema_model),
                )
            try:
                try:
                    from nexus.jobs.gate import before_provider_call

                    before_provider_call()
                    request_params = self._build_native_structured_request_params(
                        active_prompt,
                        schema_model,
                        text_format=text_format,
                        prompt_cache_key=prompt_cache_key,
                    )
                    # Keep the successful exchange in hand before local validation.
                    # SDK parse can raise before returning its usage and response ID.
                    response = self.client.responses.create(**request_params)
                except Exception as exc:
                    if not self._should_fallback_to_chat_completions(exc):
                        raise
                    logger.info(
                        "Responses structured output unsupported by %s; "
                        "falling back to chat.completions response_format",
                        self.base_url,
                    )
                    recorder = getattr(self, "attempt_manifest_result", None)
                    if recorder is not None:
                        recorder("error")
                    handed_off = True
                    return self._get_structured_completion_chat_completions_sync(
                        active_prompt, schema_model, text_format=text_format
                    )
                response_recorder = getattr(self, "attempt_manifest_response", None)
                if response_recorder is not None:
                    response_recorder(response)
                if self.response_check is not None:
                    self.response_check(response)
                parsed_output = self._extract_native_parsed_output(
                    response, schema_model
                )
                parsed_output = asyncio.run(
                    run_output_validator(
                        self.output_validator, parsed_output, retry=attempt
                    )
                )
                llm_response = self._native_response_to_llm_response(
                    parsed_output, response
                )
                usage_outcome = "accepted"
                return parsed_output, llm_response
            except WireContractViolation as exc:
                usage_outcome = "rejected_validation"
                self._log_structured_output_rejection(
                    transport="responses", attempt=attempt, exc=exc
                )
                raise
            except ModelRetry as exc:
                last_error = exc
                usage_outcome = "rejected_validation"
                self._log_structured_output_rejection(
                    transport="responses",
                    attempt=attempt,
                    exc=exc,
                )
                if attempt >= self.structured_output_retries:
                    raise
                active_prompt = retry_prompt(prompt, exc.message)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                usage_outcome = "rejected_validation"
                self._log_structured_output_rejection(
                    transport="responses",
                    attempt=attempt,
                    exc=exc,
                )
                if attempt >= self.structured_output_retries:
                    raise
                active_prompt = retry_prompt(prompt, str(exc))
            finally:
                try:
                    result_recorder = getattr(self, "attempt_manifest_result", None)
                    if result_recorder is not None and not handed_off:
                        result_recorder(usage_outcome)
                finally:
                    # One ledger event with the final outcome, even when the
                    # manifest callback or local validation itself fails.
                    if response is not None:
                        record_openai_response(
                            response,
                            provider=self.usage_provider_name,
                            model=cast(str, self.model),
                            seat=self.usage_seat,
                            attempt=attempt + 1,
                            outcome=usage_outcome,
                            transport="responses",
                        )

        raise RuntimeError("Structured completion failed") from last_error

    async def _get_structured_completion_native_async(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
        prompt_cache_key: Optional[str] = None,
    ) -> Tuple[Any, LLMResponse]:
        """Dispatch structured output without blocking an existing event loop."""

        if self.structured_transport == "chat_completions":
            return await self._get_structured_completion_chat_completions_async(
                prompt, schema_model, text_format=text_format
            )
        return await asyncio.to_thread(
            self._get_structured_completion_native_sync,
            prompt,
            schema_model,
            text_format=text_format,
            prompt_cache_key=prompt_cache_key,
        )

    def _should_fallback_to_chat_completions(self, exc: BaseException) -> bool:
        """Return True when a local OpenAI-compatible server needs Chat format."""

        if not self.base_url:
            return False
        status_code = getattr(exc, "status_code", None)
        if status_code in {404, 405}:
            return True
        if status_code not in {400, 422}:
            return False
        message = str(exc).lower()
        return "json_schema" in message and (
            "text" in message or "response_format" in message
        )

    def _should_fallback_plain_completion(self, exc: BaseException) -> bool:
        """Return True when a local server has Chat but not Responses."""

        if not self.base_url:
            return False
        return getattr(exc, "status_code", None) in {404, 405}

    def _get_structured_completion_chat_completions_sync(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, LLMResponse]:
        """Run strict structured output through Chat Completions response_format."""

        from pydantic_ai import ModelRetry

        active_prompt = prompt
        last_error: Optional[BaseException] = None
        for attempt in range(self.structured_output_retries + 1):
            response: Any = None
            usage_outcome: Literal["accepted", "rejected_validation", "error"] = "error"
            guard = getattr(self, "prompt_window_guard", None)
            if guard is not None:
                guard(
                    active_prompt,
                    attempt + 1,
                    text_format=text_format
                    or openai_response_text_format(schema_model),
                )
            try:
                from nexus.jobs.gate import before_provider_call

                before_provider_call()
                response = self.client.chat.completions.create(
                    **self._build_chat_structured_request_params(
                        active_prompt, schema_model, text_format=text_format
                    )
                )
                response_recorder = getattr(self, "attempt_manifest_response", None)
                if response_recorder is not None:
                    response_recorder(response)
                if self.response_check is not None:
                    self.response_check(response)
                parsed_output = self._extract_chat_parsed_output(response, schema_model)
                parsed_output = asyncio.run(
                    run_output_validator(
                        self.output_validator, parsed_output, retry=attempt
                    )
                )
                llm_response = self._chat_response_to_llm_response(
                    parsed_output, response
                )
                usage_outcome = "accepted"
                return parsed_output, llm_response
            except WireContractViolation as exc:
                usage_outcome = "rejected_validation"
                self._log_structured_output_rejection(
                    transport="chat_completions", attempt=attempt, exc=exc
                )
                raise
            except ModelRetry as exc:
                last_error = exc
                usage_outcome = "rejected_validation"
                self._log_structured_output_rejection(
                    transport="chat_completions",
                    attempt=attempt,
                    exc=exc,
                )
                if attempt >= self.structured_output_retries:
                    raise
                active_prompt = retry_prompt(prompt, exc.message)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                usage_outcome = "rejected_validation"
                self._log_structured_output_rejection(
                    transport="chat_completions",
                    attempt=attempt,
                    exc=exc,
                )
                if attempt >= self.structured_output_retries:
                    raise
                active_prompt = retry_prompt(prompt, str(exc))
            finally:
                result_recorder = getattr(self, "attempt_manifest_result", None)
                if result_recorder is not None:
                    result_recorder(usage_outcome)
                if response is not None:
                    record_openai_response(
                        response,
                        provider=self.usage_provider_name,
                        model=cast(str, self.model),
                        seat=self.usage_seat,
                        attempt=attempt + 1,
                        outcome=usage_outcome,
                        transport="chat_completions",
                    )

        raise RuntimeError("Structured chat completion failed") from last_error

    async def _get_structured_completion_chat_completions_async(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, LLMResponse]:
        """Run Chat Completions structured output off the event-loop thread."""

        return await asyncio.to_thread(
            self._get_structured_completion_chat_completions_sync,
            prompt,
            schema_model,
            text_format=text_format,
        )

    def _build_native_structured_request_params(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
        prompt_cache_key: Optional[str] = None,
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
        request_params["text"] = {
            "format": text_format or openai_response_text_format(schema_model)
        }
        if self.supports_temperature and self.temperature is not None:
            request_params["temperature"] = self.temperature
        if self.is_reasoning_model and self.reasoning_effort:
            request_params["reasoning"] = {"effort": self.reasoning_effort}
        if prompt_cache_key:
            request_params["prompt_cache_key"] = prompt_cache_key
        return self._filter_request_params(request_params)

    def _build_chat_structured_request_params(
        self,
        prompt: str,
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build Chat Completions params for OpenAI-compatible local servers."""

        messages = [{"role": "user", "content": prompt}]
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})

        request_params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_output_tokens,
            "response_format": self._chat_response_format(
                schema_model, text_format=text_format
            ),
        }
        if self.supports_temperature and self.temperature is not None:
            request_params["temperature"] = self.temperature
        if self.request_params:
            # Registry-declared provider-specific params (issue #580) ride
            # extra_body: the OpenAI SDK rejects unknown kwargs, and servers
            # (OpenRouter, llama-server) read them from the merged JSON body.
            # Structural keys are reserved at config load. Deep copy so a
            # caller mutating the built request cannot corrupt provider state.
            request_params["extra_body"] = copy.deepcopy(self.request_params)
        return self._filter_request_params(request_params)

    def _filter_request_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Omit registry-prohibited parameters from SDK kwargs and merged bodies."""
        filtered = {
            key: value
            for key, value in params.items()
            if key not in self.unsupported_params
        }
        if "extra_body" in filtered:
            filtered["extra_body"] = {
                key: value
                for key, value in filtered["extra_body"].items()
                if key not in self.unsupported_params
            }
        return filtered

    @staticmethod
    def _chat_response_format(
        schema_model: Type,
        *,
        text_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convert Responses text.format to Chat Completions response_format."""

        format_payload = text_format or openai_response_text_format(schema_model)
        if format_payload.get("type") != "json_schema":
            return {"type": "json_object"}

        json_schema = {
            "name": format_payload["name"],
            "schema": format_payload["schema"],
            "strict": format_payload.get("strict", True),
        }
        if format_payload.get("description"):
            json_schema["description"] = format_payload["description"]
        return {"type": "json_schema", "json_schema": json_schema}

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

    @staticmethod
    def _extract_chat_parsed_output(response: Any, schema_model: Type) -> Any:
        """Extract and validate JSON content from a Chat Completions response."""

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ValueError("Chat completion did not include choices")
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if not content:
            raise ValueError("Chat completion did not include message content")
        return schema_model.model_validate_json(content)

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

    def _chat_response_to_llm_response(
        self, parsed_output: Any, response: Any
    ) -> LLMResponse:
        """Convert a Chat Completions structured response into LLMResponse."""

        content = (
            parsed_output.model_dump_json()
            if hasattr(parsed_output, "model_dump_json")
            else json.dumps(parsed_output)
        )
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        if input_tokens is None:
            input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        if output_tokens is None:
            output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            raw_response=response,
        )

    def _get_completion_unified(
        self, prompt: str, cache_key: Optional[str] = None
    ) -> LLMResponse:
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
            "max_output_tokens": self.max_output_tokens,
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
        if self.is_reasoning_model and self.reasoning_effort:
            request_params["reasoning"] = {"effort": self.reasoning_effort}
            logger.info(
                f"Using OpenAI responses API with model {self.model} and reasoning effort: {self.reasoning_effort}, cache_key: {cache_key}"
            )
        else:
            logger.info(
                f"Using OpenAI responses API with model {self.model}, cache_key: {cache_key}"
            )

        if extra_body:
            request_params["extra_body"] = extra_body

        request_params = self._filter_request_params(request_params)

        # Create the response
        try:
            from nexus.jobs.gate import before_provider_call

            before_provider_call()
            response = self.client.responses.create(**request_params)
        except Exception as exc:
            if not self._should_fallback_plain_completion(exc):
                raise
            logger.info(
                "Responses completions unsupported by %s; falling back to "
                "chat.completions",
                self.base_url,
            )
            return self._get_completion_chat_completions(prompt)

        usage_outcome: Literal["accepted", "error"] = "error"
        try:
            # Format response to match our standard format
            result = LLMResponse(
                content=response.output_text,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model=cast(str, self.model),
                raw_response=response,
            )
            usage_outcome = "accepted"
            return result
        finally:
            record_openai_response(
                response,
                provider=self.usage_provider_name,
                model=cast(str, self.model),
                seat=self.usage_seat,
                attempt=1,
                outcome=usage_outcome,
                transport="responses",
            )

    def _get_completion_chat_completions(self, prompt: str) -> LLMResponse:
        """Get an unstructured completion through Chat Completions."""

        messages = [{"role": "user", "content": prompt}]
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})

        request_params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_output_tokens,
        }
        if self.supports_temperature and self.temperature is not None:
            request_params["temperature"] = self.temperature
        if self.request_params:
            # Registry request_params (issue #580) apply to plain completions
            # too — Orrery narration reaches OpenRouter through this path.
            request_params["extra_body"] = copy.deepcopy(self.request_params)

        from nexus.jobs.gate import before_provider_call

        before_provider_call()
        request_params = self._filter_request_params(request_params)
        response = self.client.chat.completions.create(**request_params)
        usage_outcome: Literal["accepted", "error"] = "error"
        try:
            choices = getattr(response, "choices", None) or []
            message = getattr(choices[0], "message", None) if choices else None
            content = getattr(message, "content", "") if message else ""
            usage = getattr(response, "usage", None)
            result = LLMResponse(
                content=content,
                input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                output_tokens=(getattr(usage, "completion_tokens", 0) if usage else 0),
                model=cast(str, self.model),
                raw_response=response,
            )
            usage_outcome = "accepted"
            return result
        finally:
            record_openai_response(
                response,
                provider=self.usage_provider_name,
                model=cast(str, self.model),
                seat=self.usage_seat,
                attempt=1,
                outcome=usage_outcome,
                transport="chat_completions",
            )

    def _get_api_key(self) -> str:
        """Get OpenAI API key via the central secret manager (Keychain)."""
        from nexus.util.secret_manager import get_secret

        return get_secret("openai")


# Database utilities
def get_db_connection_string() -> str:
    """Resolve the database through the runtime connection contract."""
    return database_url()


def to_json(obj):
    """Convert an object to a JSON-serializable format."""
    if isinstance(obj, (datetime, timedelta)):
        return str(obj)
    elif hasattr(obj, "__dict__"):
        return {k: to_json(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # OpenAI options
    llm_group = parser.add_argument_group("OpenAI API Options")
    llm_group.add_argument(
        "--model",
        default=None,
        help="Model name to use (default: ir_eval.judgment.model in nexus.toml)",
    )
    llm_group.add_argument("--api-key", help="API key (optional)")
    llm_group.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Model temperature for standard models (0.0-1.0, default: 0.1)",
    )
    llm_group.add_argument(
        "--max-tokens",
        type=int,
        default=4000,
        help="Maximum tokens to generate in response (default: 4000)",
    )
    llm_group.add_argument("--system-prompt", help="Optional system prompt to use")
    llm_group.add_argument(
        "--effort",
        choices=["low", "medium", "high"],
        default="medium",
        help="Reasoning effort for o-prefixed models (default: medium)",
    )

    # Common processing options
    process_group = parser.add_argument_group("Processing Options")
    process_group.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of items to process before prompting to continue (default: 10)",
    )
    process_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually save results to the database",
    )
    process_group.add_argument(
        "--db-url",
        help="Database connection URL (optional, defaults to environment variables)",
    )

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
        raise ImportError(
            "The 'openai' package is required. Install with 'pip install openai'"
        )


# Abort functionality
# Global abort flag
ABORT_REQUESTED = False


def setup_abort_handler(
    abort_message: str = "Abort requested! Will finish current operation and stop.",
):
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
            if event.name == "esc":
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
