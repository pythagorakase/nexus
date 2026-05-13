"""Tests for lazy initialization of LOGON provider."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from nexus.agents.logon.apex_schema import StorytellerResponseMinimal
from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_utility import LogonUtility


class _DummyResponse:
    def __init__(self, prompt: str):
        self.content = f"dummy:{prompt[:20]}"
        self.input_tokens = 1
        self.output_tokens = 1
        self.model = "dummy-model"
        self.raw_response = {"prompt": prompt}


class _DummyProvider:
    model = "dummy-model"

    def __init__(self) -> None:
        self.calls = 0
        self.completion_calls = 0

    def get_completion(self, prompt: str) -> _DummyResponse:
        self.completion_calls += 1
        return _DummyResponse(prompt)

    def get_structured_completion(
        self, prompt: str, schema_model: type
    ) -> tuple[StorytellerResponseMinimal, _DummyResponse]:
        self.calls += 1
        return self._response(prompt), _DummyResponse(prompt)

    async def get_structured_completion_async(
        self, prompt: str, schema_model: type
    ) -> tuple[StorytellerResponseMinimal, _DummyResponse]:
        self.calls += 1
        return self._response(prompt), _DummyResponse(prompt)

    def _response(self, prompt: str) -> StorytellerResponseMinimal:
        return StorytellerResponseMinimal(
            narrative=f"dummy:{prompt[:20]}",
            choices=[
                "Continue.",
                "Wait and observe.",
            ],
        )


class _FailingProvider:
    model = "dummy-model"

    def __init__(self) -> None:
        self.structured_calls = 0
        self.completion_calls = 0

    async def get_structured_completion_async(
        self, prompt: str, schema_model: type
    ) -> tuple[StorytellerResponseMinimal, _DummyResponse]:
        self.structured_calls += 1
        raise RuntimeError("structured boom")

    def get_completion(self, prompt: str) -> _DummyResponse:
        self.completion_calls += 1
        return _DummyResponse(prompt)


@pytest.fixture()
def patched_provider(monkeypatch: pytest.MonkeyPatch) -> Dict[str, int]:
    """Patch provider initialization so tests never talk to real services."""

    init_calls = {"count": 0}

    class _DummyLLMManager:
        unload_on_exit = False

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def is_available(self) -> bool:
            return True

        def ensure_model_loaded(self) -> None:
            return None

    def _fake_initialize(self: LogonUtility) -> None:
        init_calls["count"] += 1
        self.provider = _DummyProvider()

    for target in (
        "nexus.agents.lore.logon_utility.LogonUtility._initialize_provider",
        "logon_utility.LogonUtility._initialize_provider",
    ):
        monkeypatch.setattr(target, _fake_initialize)

    for target in (
        "nexus.agents.lore.lore.LocalLLMManager",
        "utils.local_llm.LocalLLMManager",
    ):
        monkeypatch.setattr(target, _DummyLLMManager)

    return init_calls


def _minimal_payload() -> Dict[str, Any]:
    return {
        "user_input": "Test",
        "warm_slice": {"chunks": []},
        "entity_data": {},
        "retrieved_passages": {"results": []},
    }


@pytest.mark.requires_local_llm
@pytest.mark.requires_postgres
def test_lore_keeps_logon_lazy(patched_provider: Dict[str, int]) -> None:
    """LORE should not initialize LOGON on construction when lazy mode is enabled."""

    lore = LORE(debug=True, enable_logon=True)
    assert patched_provider["count"] == 0
    assert lore.logon is None


@pytest.mark.requires_local_llm
@pytest.mark.requires_postgres
def test_logon_initializes_on_first_use(patched_provider: Dict[str, int]) -> None:
    """LOGON provider should initialize only when requested."""

    lore = LORE(debug=True, enable_logon=True)
    lore.ensure_logon()
    assert lore.logon is not None
    assert patched_provider["count"] == 0

    response = lore.logon.generate_narrative(_minimal_payload())
    assert patched_provider["count"] == 1
    assert isinstance(lore.logon.provider, _DummyProvider)
    assert lore.logon.provider.calls == 1
    assert response.narrative.startswith("dummy:")


@pytest.mark.asyncio
async def test_logon_async_generation_uses_structured_provider() -> None:
    """Async LOGON generation should use structured provider output directly."""

    provider = _DummyProvider()
    logon = LogonUtility({}, model_override="dummy-model")
    logon.provider = provider

    response = await logon.generate_narrative_async(_minimal_payload())

    assert provider.calls == 1
    assert provider.completion_calls == 0
    assert response.narrative.startswith("dummy:")
    assert len(response.choices) == 2


@pytest.mark.asyncio
async def test_logon_structured_failure_does_not_call_plain_text_fallback() -> None:
    """Structured LOGON failures should fail fast without a second LLM call."""

    provider = _FailingProvider()
    logon = LogonUtility({}, model_override="dummy-model")
    logon.provider = provider

    with pytest.raises(RuntimeError, match="structured boom"):
        await logon.generate_narrative_async(_minimal_payload())

    assert provider.structured_calls == 1
    assert provider.completion_calls == 0
