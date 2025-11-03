"""Batch orchestrator for intelligent API request sequencing with caching."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger("nexus.apex_audition.orchestrator")


@dataclass
class RateLimits:
    """Rate limits for a specific provider/model."""
    tokens_per_minute: int
    requests_per_minute: int
    batch_tokens_per_day: Optional[int] = None  # OpenAI only


@dataclass
class RequestMetrics:
    """Tracks usage for rate limit enforcement."""
    timestamp: float
    tokens: int
    is_request: bool = True  # vs just tokens


class SlidingWindowTracker:
    """Track requests and tokens in a sliding time window."""

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.events: deque[RequestMetrics] = deque()

    def add_event(self, tokens: int, is_request: bool = True) -> None:
        """Record a request or token usage event."""
        now = time.time()
        self.events.append(RequestMetrics(
            timestamp=now,
            tokens=tokens,
            is_request=is_request
        ))
        self._cleanup_old_events(now)

    def get_usage(self) -> Tuple[int, int]:
        """
        Get current usage in the sliding window.

        Returns:
            (total_tokens, total_requests) in the window
        """
        now = time.time()
        self._cleanup_old_events(now)

        total_tokens = sum(e.tokens for e in self.events)
        total_requests = sum(1 for e in self.events if e.is_request)

        return total_tokens, total_requests

    def can_accommodate(self, tokens: int, limits: RateLimits) -> Tuple[bool, str]:
        """
        Check if a request can be made without exceeding limits.

        Returns:
            (can_proceed, reason_if_blocked)
        """
        total_tokens, total_requests = self.get_usage()

        # Check request limit
        if total_requests + 1 > limits.requests_per_minute:
            return False, f"RPM limit ({limits.requests_per_minute})"

        # Check token limit
        if total_tokens + tokens > limits.tokens_per_minute:
            return False, f"TPM limit ({limits.tokens_per_minute})"

        return True, ""

    def wait_time_until_ready(self, tokens: int, limits: RateLimits) -> float:
        """
        Calculate seconds to wait before this request would be allowed.

        Returns:
            Seconds to wait (0 if can proceed now)
        """
        now = time.time()
        self._cleanup_old_events(now)

        if not self.events:
            return 0.0

        # Find oldest event that would cause us to exceed limits
        total_tokens, total_requests = self.get_usage()

        # If we're over request limit, wait until oldest request expires
        if total_requests >= limits.requests_per_minute:
            oldest_request_time = min(
                e.timestamp for e in self.events if e.is_request
            )
            wait_seconds = (oldest_request_time + self.window_seconds) - now
            return max(0, wait_seconds)

        # If adding tokens would exceed TPM, wait until enough tokens expire
        if total_tokens + tokens > limits.tokens_per_minute:
            # Sort events by timestamp
            sorted_events = sorted(self.events, key=lambda e: e.timestamp)
            cumulative_tokens = 0
            target_time = now

            # Find when enough old tokens expire to fit this request
            for event in sorted_events:
                cumulative_tokens += event.tokens
                if total_tokens - cumulative_tokens + tokens <= limits.tokens_per_minute:
                    target_time = event.timestamp + self.window_seconds
                    break

            wait_seconds = target_time - now
            return max(0, wait_seconds)

        return 0.0

    def _cleanup_old_events(self, current_time: float) -> None:
        """Remove events outside the sliding window."""
        cutoff = current_time - self.window_seconds
        while self.events and self.events[0].timestamp < cutoff:
            self.events.popleft()


class BatchOrchestrator:
    """
    Intelligent orchestrator for batch API requests with caching.

    Sequences requests per-context to maximize cache hits:
    - OpenAI: Automatic prefix caching, burst all requests per context
    - Anthropic: Manual cache warming + burst within 5-minute TTL
    """

    def __init__(self, rate_limits_path: Optional[Path] = None):
        """
        Initialize orchestrator with rate limits.

        Args:
            rate_limits_path: Path to api_limits.md (default: docs/api_limits.md)
        """
        self.rate_limits_path = rate_limits_path or Path("docs/api_limits.md")
        self.limits = self._load_rate_limits()
        self.trackers: Dict[str, SlidingWindowTracker] = {}
        self.cache_warm_times: Dict[Tuple[str, int], datetime] = {}  # (provider, prompt_id) -> timestamp

    def _load_rate_limits(self) -> Dict[str, RateLimits]:
        """
        Parse rate limits from docs/api_limits.md.

        Returns:
            Dict mapping provider/model keys to RateLimits
        """
        limits = {}

        if not self.rate_limits_path.exists():
            LOGGER.warning(f"Rate limits file not found: {self.rate_limits_path}")
            return self._get_default_limits()

        try:
            content = self.rate_limits_path.read_text()
            current_provider = None

            for line in content.split('\n'):
                line = line.strip()

                # Detect provider headers
                if line.startswith('# '):
                    current_provider = line[2:].strip().lower()
                    continue

                # Parse table rows
                if '|' in line and current_provider and line.count('|') >= 3:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) < 4 or parts[1].lower() in ['model', '']:
                        continue

                    model = parts[1].lower()

                    # Skip separator rows (e.g., "| -------- | ------------- |")
                    if model.startswith('-') or all(c in '-' for c in parts[2].replace(' ', '')):
                        continue

                    tpm = self._parse_number(parts[2])
                    rpm = self._parse_number(parts[3])
                    batch_tpd = self._parse_number(parts[4]) if len(parts) > 4 and parts[4].strip() else None

                    key = f"{current_provider}:{model}"
                    limits[key] = RateLimits(
                        tokens_per_minute=tpm,
                        requests_per_minute=rpm,
                        batch_tokens_per_day=batch_tpd
                    )

            LOGGER.info(f"Loaded rate limits for {len(limits)} provider/model combinations")
            return limits

        except Exception as e:
            LOGGER.error(f"Failed to parse rate limits: {e}")
            return self._get_default_limits()

    @staticmethod
    def _parse_number(value: str) -> int:
        """Parse formatted numbers like '2,000,000' or '10,000' to int."""
        return int(value.replace(',', '').replace(' ', ''))

    @staticmethod
    def _get_default_limits() -> Dict[str, RateLimits]:
        """Fallback rate limits if file can't be loaded."""
        return {
            "openai:gpt-5": RateLimits(4_000_000, 10_000, 200_000_000),
            "openai:o3": RateLimits(2_000_000, 10_000, 200_000_000),
            "openai:gpt-4o": RateLimits(2_000_000, 10_000, 200_000_000),
            "anthropic:sonnet 4.5": RateLimits(2_000_000, 4_000),
            "anthropic:opus 4.1": RateLimits(2_000_000, 4_000),
        }

    def get_tracker(self, provider: str, model: str) -> SlidingWindowTracker:
        """Get or create a rate limit tracker for a provider/model."""
        key = f"{provider.lower()}:{model.lower()}"
        if key not in self.trackers:
            self.trackers[key] = SlidingWindowTracker(window_seconds=60)
        return self.trackers[key]

    def get_limits(self, provider: str, model: str) -> RateLimits:
        """Get rate limits for a provider/model combination."""
        provider_key = provider.lower()
        model_key = model.lower()

        # OpenRouter handles its own rate limiting and load balancing
        # These providers are routed through OpenRouter (see engine.py:930-932)
        openrouter_providers = {"openrouter", "moonshot", "nousresearch", "deepseek"}
        if provider_key in openrouter_providers:
            LOGGER.debug(f"Using OpenRouter's built-in rate limiting for {provider}:{model}")
            return RateLimits(100_000_000, 100_000)  # Effectively unlimited

        key = f"{provider_key}:{model_key}"
        limits = self.limits.get(key)
        if not limits:
            # Try just provider
            for k, v in self.limits.items():
                if k.startswith(provider_key):
                    limits = v
                    break

        if not limits:
            LOGGER.warning(f"No limits found for {provider}:{model}, using conservative defaults")
            limits = RateLimits(100_000, 100)  # Very conservative

        return limits

    def wait_if_needed(
        self,
        provider: str,
        model: str,
        estimated_tokens: int
    ) -> float:
        """
        Wait if necessary to respect rate limits.

        Returns:
            Seconds actually waited
        """
        tracker = self.get_tracker(provider, model)
        limits = self.get_limits(provider, model)

        wait_time = tracker.wait_time_until_ready(estimated_tokens, limits)
        if wait_time > 0:
            LOGGER.info(
                f"Rate limit throttling: waiting {wait_time:.1f}s for {provider}:{model}"
            )
            time.sleep(wait_time)

        # Record the request
        tracker.add_event(estimated_tokens, is_request=True)

        return wait_time

    def mark_cache_warm(self, provider: str, prompt_id: int) -> None:
        """Mark that a cache-warming request was sent for this prompt."""
        self.cache_warm_times[(provider, prompt_id)] = datetime.now()

    def is_cache_warm(self, provider: str, prompt_id: int, ttl_seconds: int = 300) -> bool:
        """
        Check if the cache is still warm for this prompt.

        Args:
            provider: Provider name
            prompt_id: Prompt ID
            ttl_seconds: Cache TTL (default 300s = 5 minutes for Anthropic)

        Returns:
            True if cache was warmed within TTL window
        """
        key = (provider, prompt_id)
        if key not in self.cache_warm_times:
            return False

        elapsed = (datetime.now() - self.cache_warm_times[key]).total_seconds()
        return elapsed < ttl_seconds


__all__ = ["BatchOrchestrator", "RateLimits", "SlidingWindowTracker"]
