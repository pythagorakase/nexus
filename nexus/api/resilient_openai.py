"""
Resilient OpenAI client with built-in retry logic and error handling.

This module provides a drop-in replacement for the standard OpenAI client
that automatically handles retries, rate limiting, and circuit breaking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional
from functools import wraps

import openai
from openai import OpenAIError, RateLimitError, APITimeoutError, APIConnectionError

from nexus.api.retry_handler import (
    RetryConfig,
    OPENAI_RETRY_CONFIG,
    calculate_backoff_delay,
    openai_rate_limiter,
    openai_circuit_breaker,
)

logger = logging.getLogger("nexus.api.resilient_openai")


class ResilientOpenAI:
    """
    A wrapper around the OpenAI client that adds automatic retry logic.

    This class proxies all calls to the underlying OpenAI client and adds:
    - Exponential backoff retries for transient failures
    - Rate limiting protection
    - Circuit breaker pattern for service degradation
    - Detailed logging of retry attempts
    """

    def __init__(self, api_key: str, config: Optional[RetryConfig] = None):
        """
        Initialize the resilient OpenAI client.

        Args:
            api_key: OpenAI API key
            config: Optional retry configuration (uses OPENAI_RETRY_CONFIG by default)
        """
        self.config = config or OPENAI_RETRY_CONFIG
        self._client = openai.OpenAI(api_key=api_key)

    def __getattr__(self, name: str) -> Any:
        """
        Proxy attribute access to the underlying client.

        This allows the resilient client to be used as a drop-in replacement.
        """
        attr = getattr(self._client, name)

        # If it's a method that might make API calls, wrap it with retry logic
        if callable(attr):
            return self._wrap_with_retry(attr, name)

        # For nested objects like client.chat.completions, we need to wrap deeper
        if hasattr(attr, '__class__') and attr.__class__.__module__.startswith('openai'):
            return ResilientWrapper(attr, self.config)

        return attr

    def _wrap_with_retry(self, func: callable, func_name: str) -> callable:
        """
        Wrap a function with retry logic.

        Args:
            func: The function to wrap
            func_name: The name of the function for logging

        Returns:
            The wrapped function with retry logic
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(self.config.max_retries + 1):
                try:
                    # Check circuit breaker
                    if hasattr(openai_circuit_breaker, 'state') and openai_circuit_breaker.state == "open":
                        if not openai_circuit_breaker._should_attempt_reset():
                            raise RuntimeError(f"Circuit breaker is OPEN for OpenAI API")

                    # Apply rate limiting
                    openai_rate_limiter.wait_if_needed()

                    # Make the actual API call
                    result = func(*args, **kwargs)

                    # Mark success for circuit breaker
                    if hasattr(openai_circuit_breaker, '_on_success'):
                        openai_circuit_breaker._on_success()

                    return result

                except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                    last_exception = e

                    # Mark failure for circuit breaker
                    if hasattr(openai_circuit_breaker, '_on_failure'):
                        openai_circuit_breaker._on_failure()

                    if attempt < self.config.max_retries:
                        delay = calculate_backoff_delay(attempt, self.config)
                        logger.warning(
                            f"OpenAI API error in {func_name} "
                            f"(attempt {attempt + 1}/{self.config.max_retries + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func_name}: {e}")

                except Exception as e:
                    # Don't retry for other exceptions
                    logger.error(f"Non-retryable error in {func_name}: {e}")
                    raise

            # If we get here, all retries failed
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f"All retries failed for {func_name}")

        return wrapper


class ResilientWrapper:
    """
    A wrapper for nested OpenAI client objects (like client.chat or client.beta).

    This ensures retry logic is applied even to nested method calls.
    """

    def __init__(self, wrapped_obj: Any, config: RetryConfig):
        """
        Initialize the wrapper.

        Args:
            wrapped_obj: The object to wrap
            config: Retry configuration
        """
        self._wrapped = wrapped_obj
        self._config = config

    def __getattr__(self, name: str) -> Any:
        """
        Proxy attribute access to the wrapped object.
        """
        attr = getattr(self._wrapped, name)

        # If it's a method, wrap it with retry logic
        if callable(attr):
            return self._wrap_with_retry(attr, f"{self._wrapped.__class__.__name__}.{name}")

        # For further nested objects, continue wrapping
        if hasattr(attr, '__class__') and attr.__class__.__module__.startswith('openai'):
            return ResilientWrapper(attr, self._config)

        return attr

    def _wrap_with_retry(self, func: callable, func_name: str) -> callable:
        """
        Wrap a function with retry logic.

        This is similar to the ResilientOpenAI version but for nested objects.
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(self._config.max_retries + 1):
                try:
                    # Apply rate limiting
                    openai_rate_limiter.wait_if_needed()

                    # Make the actual API call
                    return func(*args, **kwargs)

                except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                    last_exception = e

                    if attempt < self._config.max_retries:
                        delay = calculate_backoff_delay(attempt, self._config)
                        logger.warning(
                            f"OpenAI API error in {func_name} "
                            f"(attempt {attempt + 1}/{self._config.max_retries + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func_name}: {e}")

                except Exception as e:
                    # Don't retry for other exceptions
                    logger.error(f"Non-retryable error in {func_name}: {e}")
                    raise

            # If we get here, all retries failed
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f"All retries failed for {func_name}")

        return wrapper


class AsyncResilientOpenAI:
    """
    An async version of the resilient OpenAI client.

    This is used for async endpoints and supports the AsyncOpenAI client.
    """

    def __init__(self, api_key: str, config: Optional[RetryConfig] = None):
        """
        Initialize the async resilient OpenAI client.

        Args:
            api_key: OpenAI API key
            config: Optional retry configuration (uses OPENAI_RETRY_CONFIG by default)
        """
        self.config = config or OPENAI_RETRY_CONFIG
        self._client = openai.AsyncOpenAI(api_key=api_key)

    def __getattr__(self, name: str) -> Any:
        """
        Proxy attribute access to the underlying async client.
        """
        attr = getattr(self._client, name)

        # If it's a method that might make API calls, wrap it with async retry logic
        if callable(attr):
            return self._wrap_with_async_retry(attr, name)

        # For nested objects like client.chat.completions
        if hasattr(attr, '__class__') and attr.__class__.__module__.startswith('openai'):
            return AsyncResilientWrapper(attr, self.config)

        return attr

    def _wrap_with_async_retry(self, func: callable, func_name: str) -> callable:
        """
        Wrap an async function with retry logic.
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(self.config.max_retries + 1):
                try:
                    # Check circuit breaker
                    if hasattr(openai_circuit_breaker, 'state') and openai_circuit_breaker.state == "open":
                        if not openai_circuit_breaker._should_attempt_reset():
                            raise RuntimeError(f"Circuit breaker is OPEN for OpenAI API")

                    # Apply async rate limiting
                    await openai_rate_limiter.wait_if_needed_async()

                    # Make the actual API call
                    result = await func(*args, **kwargs)

                    # Mark success for circuit breaker
                    if hasattr(openai_circuit_breaker, '_on_success'):
                        openai_circuit_breaker._on_success()

                    return result

                except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                    last_exception = e

                    # Mark failure for circuit breaker
                    if hasattr(openai_circuit_breaker, '_on_failure'):
                        openai_circuit_breaker._on_failure()

                    if attempt < self.config.max_retries:
                        delay = calculate_backoff_delay(attempt, self.config)
                        logger.warning(
                            f"OpenAI API error in {func_name} "
                            f"(attempt {attempt + 1}/{self.config.max_retries + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func_name}: {e}")

                except Exception as e:
                    # Don't retry for other exceptions
                    logger.error(f"Non-retryable error in {func_name}: {e}")
                    raise

            # If we get here, all retries failed
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f"All retries failed for {func_name}")

        return wrapper


class AsyncResilientWrapper:
    """
    An async wrapper for nested OpenAI client objects.
    """

    def __init__(self, wrapped_obj: Any, config: RetryConfig):
        """
        Initialize the async wrapper.
        """
        self._wrapped = wrapped_obj
        self._config = config

    def __getattr__(self, name: str) -> Any:
        """
        Proxy attribute access to the wrapped object.
        """
        attr = getattr(self._wrapped, name)

        # If it's a method, wrap it with async retry logic
        if callable(attr):
            return self._wrap_with_async_retry(attr, f"{self._wrapped.__class__.__name__}.{name}")

        # For further nested objects, continue wrapping
        if hasattr(attr, '__class__') and attr.__class__.__module__.startswith('openai'):
            return AsyncResilientWrapper(attr, self._config)

        return attr

    def _wrap_with_async_retry(self, func: callable, func_name: str) -> callable:
        """
        Wrap an async function with retry logic.
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(self._config.max_retries + 1):
                try:
                    # Apply async rate limiting
                    await openai_rate_limiter.wait_if_needed_async()

                    # Make the actual API call
                    return await func(*args, **kwargs)

                except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                    last_exception = e

                    if attempt < self._config.max_retries:
                        delay = calculate_backoff_delay(attempt, self._config)
                        logger.warning(
                            f"OpenAI API error in {func_name} "
                            f"(attempt {attempt + 1}/{self._config.max_retries + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func_name}: {e}")

                except Exception as e:
                    # Don't retry for other exceptions
                    logger.error(f"Non-retryable error in {func_name}: {e}")
                    raise

            # If we get here, all retries failed
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f"All retries failed for {func_name}")

        return wrapper


def create_resilient_client(api_key: str, async_client: bool = False, config: Optional[RetryConfig] = None) -> Any:
    """
    Factory function to create a resilient OpenAI client.

    Args:
        api_key: OpenAI API key
        async_client: Whether to create an async client (default: False)
        config: Optional retry configuration

    Returns:
        Either ResilientOpenAI or AsyncResilientOpenAI instance
    """
    if async_client:
        return AsyncResilientOpenAI(api_key, config)
    else:
        return ResilientOpenAI(api_key, config)