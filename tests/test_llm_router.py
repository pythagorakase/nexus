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


# =============================================================================
# Remote Backend Model Configuration Tests
# =============================================================================


class MockSettings:
    """Mock settings object for testing router configuration."""

    def __init__(
        self,
        *,
        mode: str = "remote",
        remote_base_url: str | None = "http://remote:1234/v1",
        remote_model: str | None = None,
        default_model: str = "default-model",
    ) -> None:
        self.llm = MockLLMConfig(
            mode=mode,
            remote_base_url=remote_base_url,
            remote_model=remote_model,
        )
        self.global_ = MockGlobalConfig(default_model=default_model)


class MockLLMConfig:
    """Mock LLM routing config."""

    def __init__(
        self,
        *,
        mode: str,
        remote_base_url: str | None,
        remote_model: str | None,
    ) -> None:
        self.mode = mode
        self.local = None
        self.remote = (
            MockEndpointConfig(base_url=remote_base_url, model=remote_model)
            if remote_base_url
            else None
        )
        self.cloud = None


class MockEndpointConfig:
    """Mock endpoint config with optional model."""

    def __init__(self, *, base_url: str, model: str | None) -> None:
        self.base_url = base_url
        self.model = model


class MockGlobalConfig:
    """Mock global config."""

    def __init__(self, *, default_model: str) -> None:
        self.llm = MockGlobalLLM()
        self.model = MockModelConfig(default_model=default_model)


class MockGlobalLLM:
    """Mock global LLM settings."""

    def __init__(self) -> None:
        self.api_base = "http://localhost:1234"
        self.temperature = 0.8
        self.max_tokens = 4096


class MockModelConfig:
    """Mock model config."""

    def __init__(self, *, default_model: str) -> None:
        self.default_model = default_model


def test_remote_backend_uses_explicit_model_when_configured() -> None:
    """Remote backend should use explicitly configured model over global default."""
    settings = MockSettings(
        mode="remote",
        remote_base_url="http://macbook:1234/v1",
        remote_model="nexveridian/gpt-oss-120b",
        default_model="some-other-model",
    )

    router = LLMRouter(settings=settings, mode="remote")

    # Access the single backend (remote) and check its model
    assert len(router._backends) == 1
    remote_backend = router._backends[0]
    # _model is the internal attribute where model is stored
    assert remote_backend._model == "nexveridian/gpt-oss-120b"


def test_remote_backend_falls_back_to_global_default_when_model_not_specified() -> None:
    """Remote backend should use global default_model when endpoint model is None."""
    settings = MockSettings(
        mode="remote",
        remote_base_url="http://macbook:1234/v1",
        remote_model=None,  # Not specified
        default_model="global-default-model",
    )

    router = LLMRouter(settings=settings, mode="remote")

    assert len(router._backends) == 1
    remote_backend = router._backends[0]
    # _model is the internal attribute where model is stored
    assert remote_backend._model == "global-default-model"
