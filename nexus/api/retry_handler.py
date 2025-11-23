"""
Retry and error handling utilities for NEXUS API operations.

Provides exponential backoff, rate limit handling, and graceful degradation
for external API calls and database operations.
"""

from __future__ import annotations

import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from datetime import datetime, timedelta
import random

import openai
from openai import OpenAIError, RateLimitError, APITimeoutError, APIConnectionError
import psycopg2
from psycopg2 import OperationalError, InterfaceError

logger = logging.getLogger("nexus.api.retry_handler")

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        timeout: Optional[float] = 30.0,
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.timeout = timeout


# Default configurations for different services
OPENAI_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    initial_delay=1.0,
    max_delay=60.0,
    timeout=30.0,
)

DATABASE_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    initial_delay=0.5,
    max_delay=10.0,
    timeout=10.0,
)

EMBEDDING_RETRY_CONFIG = RetryConfig(
    max_retries=2,
    initial_delay=2.0,
    max_delay=30.0,
    timeout=60.0,  # Embeddings can take longer
)


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute
        self.last_call_time = 0.0
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    async def wait_if_needed_async(self) -> None:
        """Async version of rate limiting."""
        if self._lock:
            async with self._lock:
                current_time = time.time()
                time_since_last_call = current_time - self.last_call_time
                if time_since_last_call < self.min_interval:
                    wait_time = self.min_interval - time_since_last_call
                    await asyncio.sleep(wait_time)
                self.last_call_time = time.time()

    def wait_if_needed(self) -> None:
        """Synchronous version of rate limiting."""
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        if time_since_last_call < self.min_interval:
            wait_time = self.min_interval - time_since_last_call
            time.sleep(wait_time)
        self.last_call_time = time.time()


# Global rate limiters
openai_rate_limiter = RateLimiter(calls_per_minute=50)  # Conservative default
embedding_rate_limiter = RateLimiter(calls_per_minute=30)


def calculate_backoff_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Calculate exponential backoff delay with optional jitter."""
    delay = min(
        config.initial_delay * (config.exponential_base ** attempt),
        config.max_delay
    )

    if config.jitter:
        # Add random jitter (±25% of delay)
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)

    return max(0.1, delay)  # Ensure minimum delay


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        config: Retry configuration
        on_retry: Optional callback when retry occurs

    Returns:
        Decorated function with retry logic
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except (RateLimitError, APITimeoutError) as e:
                    last_exception = e
                    if attempt < config.max_retries:
                        delay = calculate_backoff_delay(attempt, config)
                        logger.warning(
                            f"Rate limit or timeout in {func.__name__} "
                            f"(attempt {attempt + 1}/{config.max_retries + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        if on_retry:
                            on_retry(e, attempt)
                        time.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func.__name__}: {e}")

                except (OperationalError, InterfaceError) as e:
                    last_exception = e
                    if attempt < config.max_retries:
                        delay = calculate_backoff_delay(attempt, config)
                        logger.warning(
                            f"Database error in {func.__name__} "
                            f"(attempt {attempt + 1}/{config.max_retries + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        if on_retry:
                            on_retry(e, attempt)
                        time.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func.__name__}: {e}")

                except Exception as e:
                    # Don't retry for other exceptions
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise

            # If we get here, all retries failed
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f"All retries failed for {func.__name__}")

        return wrapper
    return decorator


def async_retry_with_backoff(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """
    Async version of retry_with_backoff decorator.
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except (RateLimitError, APITimeoutError) as e:
                    last_exception = e
                    if attempt < config.max_retries:
                        delay = calculate_backoff_delay(attempt, config)
                        logger.warning(
                            f"Rate limit or timeout in {func.__name__} "
                            f"(attempt {attempt + 1}/{config.max_retries + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        if on_retry:
                            on_retry(e, attempt)
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func.__name__}: {e}")

                except Exception as e:
                    # Don't retry for other exceptions
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise

            # If we get here, all retries failed
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f"All retries failed for {func.__name__}")

        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern for preventing cascading failures.

    States:
    - CLOSED: Normal operation
    - OPEN: Failures exceeded threshold, rejecting calls
    - HALF_OPEN: Testing if service recovered
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_duration: timedelta = timedelta(minutes=1),
        success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.timeout_duration = timeout_duration
        self.success_threshold = success_threshold

        self.state = self.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker."""
        if self.state == self.OPEN:
            if self._should_attempt_reset():
                self.state = self.HALF_OPEN
                self.success_count = 0
            else:
                raise RuntimeError(f"Circuit breaker is OPEN for {func.__name__}")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    async def async_call(self, func: Callable, *args, **kwargs) -> Any:
        """Async version of circuit breaker call."""
        if self.state == self.OPEN:
            if self._should_attempt_reset():
                self.state = self.HALF_OPEN
                self.success_count = 0
            else:
                raise RuntimeError(f"Circuit breaker is OPEN for {func.__name__}")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        return (
            self.last_failure_time and
            datetime.now() >= self.last_failure_time + self.timeout_duration
        )

    def _on_success(self) -> None:
        """Handle successful call."""
        if self.state == self.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = self.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker closed after successful recovery")
        elif self.state == self.CLOSED:
            self.failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.state == self.HALF_OPEN:
            self.state = self.OPEN
            logger.warning("Circuit breaker reopened after failure in half-open state")
        elif self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            logger.error(f"Circuit breaker opened after {self.failure_count} failures")


# Global circuit breakers
openai_circuit_breaker = CircuitBreaker(failure_threshold=5)
database_circuit_breaker = CircuitBreaker(failure_threshold=10)


def with_timeout(timeout_seconds: float) -> Callable:
    """
    Decorator to add timeout to synchronous functions.

    Note: For async functions, use asyncio.wait_for directly.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {timeout_seconds}s")

            # Set up timeout
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout_seconds))

            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Cancel alarm
                return result
            finally:
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper
    return decorator


class FallbackChain:
    """
    Manage fallback strategies for service failures.
    """

    def __init__(self, strategies: list[Callable]):
        """
        Initialize with list of fallback strategies in priority order.

        Args:
            strategies: List of callable strategies to try in order
        """
        self.strategies = strategies

    def execute(self, *args, **kwargs) -> Any:
        """Try each strategy until one succeeds."""
        errors = []

        for i, strategy in enumerate(self.strategies):
            try:
                logger.info(f"Trying strategy {i + 1}/{len(self.strategies)}: {strategy.__name__}")
                return strategy(*args, **kwargs)
            except Exception as e:
                errors.append((strategy.__name__, str(e)))
                logger.warning(f"Strategy {strategy.__name__} failed: {e}")

                if i == len(self.strategies) - 1:
                    # All strategies failed
                    error_summary = "; ".join([f"{name}: {err}" for name, err in errors])
                    raise RuntimeError(f"All fallback strategies failed: {error_summary}")

    async def async_execute(self, *args, **kwargs) -> Any:
        """Async version of execute."""
        errors = []

        for i, strategy in enumerate(self.strategies):
            try:
                logger.info(f"Trying strategy {i + 1}/{len(self.strategies)}: {strategy.__name__}")
                return await strategy(*args, **kwargs)
            except Exception as e:
                errors.append((strategy.__name__, str(e)))
                logger.warning(f"Strategy {strategy.__name__} failed: {e}")

                if i == len(self.strategies) - 1:
                    # All strategies failed
                    error_summary = "; ".join([f"{name}: {err}" for name, err in errors])
                    raise RuntimeError(f"All fallback strategies failed: {error_summary}")


# Example usage for OpenAI API calls with fallback models
def create_openai_fallback_chain(primary_model: str = "gpt-5.1") -> FallbackChain:
    """Create a fallback chain for OpenAI API calls."""

    @retry_with_backoff(OPENAI_RETRY_CONFIG)
    def try_primary():
        return {"model": primary_model}

    @retry_with_backoff(OPENAI_RETRY_CONFIG)
    def try_gpt5():
        return {"model": "gpt-5"}

    @retry_with_backoff(OPENAI_RETRY_CONFIG)
    def try_gpt4():
        return {"model": "gpt-4.1"}

    return FallbackChain([try_primary, try_gpt5, try_gpt4])


def log_retry_attempt(exception: Exception, attempt: int) -> None:
    """Standard logging for retry attempts."""
    logger.info(f"Retry attempt {attempt + 1} after error: {type(exception).__name__}: {exception}")