"""Unit tests for the LLM router."""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from nexus.llm import LLMBackend, LLMResponse, LLMRouter


class DummyBackend(LLMBackend):
    """Simple backend stub for router tests."""

    def __init__(self, name: str, *, available: bool = True, fail: bool = False) -> None:
        self.name = name
        self.available = available
        self.fail = fail
        self.availability_calls = 0
        self.complete_calls = 0

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.complete_calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} failure")
        return LLMResponse(content=f"{self.name}:{prompt}", model=self.name)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        if self.fail:
            raise RuntimeError(f"{self.name} failure")
        yield f"{self.name}:{prompt}"

    def is_available(self) -> bool:
        self.availability_calls += 1
        return self.available


@pytest.mark.asyncio
async def test_router_auto_uses_first_available() -> None:
    """Auto mode should select the first available backend."""
    local = DummyBackend("local")
    remote = DummyBackend("remote")
    router = LLMRouter(backends=[local, remote], mode="auto")

    response = await router.complete("ping")

    assert response.content == "local:ping"
    assert local.complete_calls == 1
    assert remote.complete_calls == 0


@pytest.mark.asyncio
async def test_router_auto_fallbacks_on_unavailable() -> None:
    """Auto mode should skip unavailable backends."""
    local = DummyBackend("local", available=False)
    remote = DummyBackend("remote")
    router = LLMRouter(backends=[local, remote], mode="auto")

    response = await router.complete("ping")

    assert response.content == "remote:ping"
    assert local.complete_calls == 0
    assert remote.complete_calls == 1


@pytest.mark.asyncio
async def test_router_caches_availability() -> None:
    """Availability probes should be cached between calls."""
    local = DummyBackend("local")
    router = LLMRouter(backends=[local], mode="auto")

    await router.complete("ping")
    await router.complete("pong")

    assert local.availability_calls == 1


@pytest.mark.asyncio
async def test_router_auto_fallbacks_on_failure() -> None:
    """Auto mode should fall back when a backend errors."""
    local = DummyBackend("local", fail=True)
    remote = DummyBackend("remote")
    router = LLMRouter(backends=[local, remote], mode="auto")

    response = await router.complete("ping")

    assert response.content == "remote:ping"
    assert local.complete_calls == 1
    assert remote.complete_calls == 1
