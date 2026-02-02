"""Router for pluggable LLM backends with auto-fallback."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Iterable, Optional, Sequence

from nexus.config import load_settings

from .base import LLMBackend, LLMResponse
from .cloud import CloudBackend
from .local import LocalLMStudioBackend
from .remote import RemoteLMStudioBackend

logger = logging.getLogger("nexus.llm.router")

# TTL for negative availability cache entries (seconds)
AVAILABILITY_CACHE_TTL = 60.0


class LLMRouter(LLMBackend):
    """Routes LLM calls across backends with availability caching."""

    def __init__(
        self,
        *,
        settings_path: Optional[str] = None,
        settings: Optional[Any] = None,
        backends: Optional[Sequence[LLMBackend]] = None,
        mode: Optional[str] = None,
    ) -> None:
        if backends is not None:
            self._backends = list(backends)
            self._mode = mode or "auto"
        else:
            settings_obj = settings or load_settings(settings_path or "nexus.toml")
            self._mode = mode or self._resolve_mode(settings_obj)
            self._backends = self._build_backends(settings_obj, settings_path)

        # Cache stores (available: bool, timestamp: float)
        self._availability_cache: dict[int, tuple[bool, float]] = {}

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Return a completion using the best available backend."""
        errors: list[Exception] = []
        for backend in self._iter_backends():
            if not await self._is_backend_available(backend):
                continue
            name = self._backend_name(backend)
            try:
                logger.info("LLM router using %s backend", name)
                return await backend.complete(prompt, **kwargs)
            except Exception as exc:
                logger.warning("LLM backend %s failed: %s", name, exc)
                self._availability_cache[id(backend)] = (False, time.monotonic())
                errors.append(exc)
                continue

        raise RuntimeError("No LLM backend available") from (errors[-1] if errors else None)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """Stream completion tokens using the best available backend."""
        errors: list[Exception] = []
        for backend in self._iter_backends():
            if not await self._is_backend_available(backend):
                continue
            name = self._backend_name(backend)
            logger.info("LLM router streaming from %s backend", name)
            yielded = False
            try:
                async for chunk in backend.stream(prompt, **kwargs):
                    yielded = True
                    yield chunk
                return
            except Exception as exc:
                logger.warning("LLM backend %s stream failed: %s", name, exc)
                self._availability_cache[id(backend)] = (False, time.monotonic())
                errors.append(exc)
                if yielded:
                    raise
                continue

        raise RuntimeError("No LLM backend available") from (errors[-1] if errors else None)

    def is_available(self) -> bool:
        """Return True if any configured backend is available (sync version)."""
        return any(self._is_backend_available_sync(b) for b in self._iter_backends())

    def refresh_availability(self) -> None:
        """Clear cached availability probes."""
        self._availability_cache.clear()

    def _iter_backends(self) -> Iterable[LLMBackend]:
        if self._mode == "auto":
            return self._backends
        return [backend for backend in self._backends if self._backend_name(backend) == self._mode]

    async def _is_backend_available(self, backend: LLMBackend) -> bool:
        """Check backend availability without blocking the event loop."""
        key = id(backend)
        now = time.monotonic()

        if key in self._availability_cache:
            available, timestamp = self._availability_cache[key]
            # Positive results cached indefinitely; negative results expire
            if available or (now - timestamp) < AVAILABILITY_CACHE_TTL:
                return available

        # Run blocking is_available() in thread pool to avoid blocking event loop
        available = await asyncio.to_thread(backend.is_available)
        self._availability_cache[key] = (available, now)
        return available

    def _is_backend_available_sync(self, backend: LLMBackend) -> bool:
        """Sync version for is_available() - blocks but expected in sync context."""
        key = id(backend)
        now = time.monotonic()

        if key in self._availability_cache:
            available, timestamp = self._availability_cache[key]
            if available or (now - timestamp) < AVAILABILITY_CACHE_TTL:
                return available

        available = backend.is_available()
        self._availability_cache[key] = (available, now)
        return available

    def _backend_name(self, backend: LLMBackend) -> str:
        return getattr(
            backend,
            "name",
            backend.__class__.__name__.replace("Backend", "").lower(),
        )

    def _resolve_mode(self, settings_obj: Any) -> str:
        llm_config = getattr(settings_obj, "llm", None)
        if llm_config and getattr(llm_config, "mode", None):
            return llm_config.mode
        return "auto"

    def _build_backends(self, settings_obj: Any, settings_path: Optional[str]) -> list[LLMBackend]:
        llm_config = getattr(settings_obj, "llm", None)
        global_llm = settings_obj.global_.llm
        global_model = settings_obj.global_.model

        default_params = {
            "temperature": global_llm.temperature,
            "max_tokens": global_llm.max_tokens,
        }

        backends: list[LLMBackend] = []

        if self._mode in {"local", "auto"}:
            local_base = None
            if llm_config and llm_config.local:
                local_base = llm_config.local.base_url
            if not local_base:
                local_base = global_llm.api_base
            backends.append(
                LocalLMStudioBackend(
                    base_url=local_base,
                    settings_path=settings_path,
                    default_params=default_params,
                )
            )

        if self._mode in {"remote", "auto"}:
            remote_base = None
            remote_model = None
            if llm_config and llm_config.remote:
                remote_base = llm_config.remote.base_url
                remote_model = llm_config.remote.model
            if remote_base:
                backends.append(
                    RemoteLMStudioBackend(
                        base_url=remote_base,
                        model=remote_model or global_model.default_model,
                        default_params=default_params,
                    )
                )
            elif self._mode == "remote":
                raise RuntimeError("Remote LLM mode requires llm.remote configuration")
            else:
                logger.info("Remote LLM backend not configured; skipping")

        if self._mode in {"cloud", "auto"}:
            cloud = llm_config.cloud if llm_config else None
            if cloud:
                backends.append(
                    CloudBackend(
                        provider=cloud.provider,
                        model=cloud.model,
                        api_key_env=cloud.api_key_env,
                    )
                )
            elif self._mode == "cloud":
                raise RuntimeError("Cloud LLM mode requires llm.cloud configuration")
            else:
                logger.info("Cloud LLM backend not configured; skipping")

        if not backends:
            raise RuntimeError("No LLM backends configured")

        return backends
