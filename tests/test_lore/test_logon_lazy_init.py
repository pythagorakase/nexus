"""Tests for lazy initialization of LOGON provider."""

from __future__ import annotations

from typing import Any, cast, Dict

import pytest

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
)
from nexus.agents.logon.skald_wire import SkaldTurnWire
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
        self.schema_models: list[type] = []

    def get_completion(self, prompt: str) -> _DummyResponse:
        self.completion_calls += 1
        return _DummyResponse(prompt)

    def get_structured_completion(
        self, prompt: str, schema_model: type
    ) -> tuple[Any, _DummyResponse]:
        self.calls += 1
        self.schema_models.append(schema_model)
        return self._response(prompt, schema_model), _DummyResponse(prompt)

    async def get_structured_completion_async(
        self, prompt: str, schema_model: type
    ) -> tuple[Any, _DummyResponse]:
        self.calls += 1
        self.schema_models.append(schema_model)
        return self._response(prompt, schema_model), _DummyResponse(prompt)

    def _response(self, prompt: str, schema_model: type) -> Any:
        response_type = (
            StorytellerResponseBootstrap
            if schema_model is StorytellerResponseBootstrap
            else SkaldTurnWire
        )
        return response_type(
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
    ) -> tuple[Any, _DummyResponse]:
        self.structured_calls += 1
        raise RuntimeError("structured boom")

    def get_completion(self, prompt: str) -> _DummyResponse:
        self.completion_calls += 1
        return _DummyResponse(prompt)


@pytest.fixture()
def patched_provider(monkeypatch: pytest.MonkeyPatch) -> Dict[str, int]:
    """Patch provider initialization so tests never talk to real services."""

    init_calls = {"count": 0}

    def _fake_initialize(self: LogonUtility, is_bootstrap: bool | None = None) -> None:
        init_calls["count"] += 1
        self.provider = cast(Any, _DummyProvider())
        self._provider_bootstrap_mode = (
            self.bootstrap_mode if is_bootstrap is None else is_bootstrap
        )

    for target in (
        "nexus.agents.lore.logon_utility.LogonUtility._initialize_provider",
        "logon_utility.LogonUtility._initialize_provider",
    ):
        monkeypatch.setattr(target, _fake_initialize)

    return init_calls


def _minimal_payload(*, is_bootstrap: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "user_input": "Test",
        "warm_slice": {"chunks": []},
        "entity_data": {},
        "retrieved_passages": {"results": []},
    }
    if is_bootstrap:
        payload["is_bootstrap"] = True
        payload["metadata"] = {"is_bootstrap": True}
    return payload


def test_runtime_roster_reference_resolves_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A @provider.role selection becomes the concrete provider model id."""

    seen: list[str] = []

    def fake_resolve(model_ref: str) -> str:
        seen.append(model_ref)
        return "resolved-roster-model"

    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.resolve_model_ref", fake_resolve
    )

    assert (
        LogonUtility._resolve_generation_model("@openai.storyteller")
        == "resolved-roster-model"
    )
    assert seen == ["@openai.storyteller"]


@pytest.mark.requires_postgres
def test_lore_keeps_logon_lazy(patched_provider: Dict[str, int]) -> None:
    """LORE should not initialize LOGON on construction when lazy mode is enabled."""

    lore = LORE(debug=True, enable_logon=True)
    assert patched_provider["count"] == 0
    assert lore.logon is None


@pytest.mark.requires_postgres
def test_logon_initializes_on_first_use(
    patched_provider: Dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """LOGON provider should initialize only when requested."""

    lore = LORE(debug=True, enable_logon=True)
    lore.ensure_logon()
    assert lore.logon is not None
    assert patched_provider["count"] == 0

    # This DB-backed utility legitimately demands a parent id for the
    # presence baseline; the test's subject is provider laziness, so the
    # reader is stubbed at its consumption seam.
    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.read_presence_baseline",
        lambda _dbname, _parent_chunk_id: None,
    )
    payload = _minimal_payload()
    payload["metadata"] = {"target_chunk_id": 1}
    response = lore.logon.generate_narrative(payload)
    assert patched_provider["count"] == 1
    assert isinstance(lore.logon.provider, _DummyProvider)
    assert lore.logon.provider.calls == 1
    assert lore.logon.provider.schema_models == [SkaldTurnWire]
    assert response.narrative.startswith("dummy:")
    assert response.generation_model == "dummy-model"


@pytest.mark.asyncio
async def test_logon_async_generation_uses_structured_provider() -> None:
    """Async LOGON generation should use structured provider output directly."""

    provider = _DummyProvider()
    logon = LogonUtility({}, model_override="dummy-model")
    logon.provider = cast(Any, provider)
    logon._provider_bootstrap_mode = False

    response = await logon.generate_narrative_async(_minimal_payload())

    assert provider.calls == 1
    assert provider.completion_calls == 0
    assert provider.schema_models == [SkaldTurnWire]
    assert response.narrative.startswith("dummy:")
    assert len(response.choices) == 2
    assert response.generation_model == "dummy-model"


@pytest.mark.asyncio
async def test_logon_async_generation_uses_bootstrap_schema_for_bootstrap() -> None:
    """Bootstrap LOGON generation should only request narrative and choices."""

    provider = _DummyProvider()
    logon = LogonUtility({}, model_override="dummy-model")
    logon.provider = cast(Any, provider)
    logon._provider_bootstrap_mode = True

    response = await logon.generate_narrative_async(_minimal_payload(is_bootstrap=True))

    assert provider.calls == 1
    assert provider.completion_calls == 0
    # The dummy mirrors the requested contract; this verifies schema selection.
    assert provider.schema_models == [StorytellerResponseBootstrap]
    assert response.narrative.startswith("dummy:")
    assert response.generation_model == "dummy-model"


@pytest.mark.asyncio
async def test_logon_stamps_model_exposed_by_last_successful_attempt() -> None:
    """Provider state after a successful retry is the provenance ground truth."""

    class RetrySwitchingProvider(_DummyProvider):
        model = "first-attempt-model"

        async def get_structured_completion_async(
            self, prompt: str, schema_model: type
        ) -> tuple[Any, _DummyResponse]:
            self.model = "successful-attempt-model"
            return await super().get_structured_completion_async(prompt, schema_model)

    provider = RetrySwitchingProvider()
    logon = LogonUtility({}, model_override="first-attempt-model")
    logon.provider = cast(Any, provider)
    logon._provider_bootstrap_mode = False

    response = await logon.generate_narrative_async(_minimal_payload())

    assert response.generation_model == "successful-attempt-model"


@pytest.mark.asyncio
async def test_logon_structured_failure_does_not_call_plain_text_fallback() -> None:
    """Structured LOGON failures should fail fast without a second LLM call."""

    provider = _FailingProvider()
    logon = LogonUtility({}, model_override="dummy-model")
    logon.provider = cast(Any, provider)
    logon._provider_bootstrap_mode = False

    with pytest.raises(RuntimeError, match="structured boom"):
        await logon.generate_narrative_async(_minimal_payload())

    assert provider.structured_calls == 1
    assert provider.completion_calls == 0


def test_context_bootstrap_mode_does_not_mutate_logon_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bootstrap payload can re-prompt the provider without flipping the utility."""

    initialized_modes: list[bool | None] = []

    def _fake_initialize(self: LogonUtility, is_bootstrap: bool | None = None) -> None:
        initialized_modes.append(is_bootstrap)
        self.provider = cast(Any, _DummyProvider())
        self._provider_bootstrap_mode = (
            self.bootstrap_mode if is_bootstrap is None else is_bootstrap
        )

    monkeypatch.setattr(LogonUtility, "_initialize_provider", _fake_initialize)

    logon = LogonUtility({}, model_override="dummy-model", bootstrap_mode=False)

    logon.generate_narrative(_minimal_payload(is_bootstrap=True))

    assert initialized_modes == [True]
    assert logon.bootstrap_mode is False
    assert logon._provider_bootstrap_mode is True
