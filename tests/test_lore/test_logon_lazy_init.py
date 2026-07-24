"""Tests for lazy initialization of LOGON provider."""

from __future__ import annotations

from typing import Any, cast, Dict

import pytest

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
)
from nexus.agents.logon.skald_wire import SkaldTurnWire, skald_wire_prompt_guide
from nexus.agents.lore import logon_utility
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


@pytest.mark.parametrize(
    ("configured_transport", "is_bootstrap", "expected_transport", "has_guide"),
    [
        ("prompted", False, "prompted", True),
        ("native", False, "native", False),
        ("prompted", True, "native", False),
    ],
)
def test_anthropic_storyteller_transport_and_guide_follow_settings(
    monkeypatch: pytest.MonkeyPatch,
    configured_transport: str,
    is_bootstrap: bool,
    expected_transport: str,
    has_guide: bool,
) -> None:
    captured: dict[str, Any] = {}

    class RecordingAnthropicProvider:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)
            self.model = kwargs["model"]
            self.structured_transport = kwargs["structured_transport"]

    monkeypatch.setattr(
        logon_utility,
        "get_provider_for_model",
        lambda _model: "anthropic",
    )
    monkeypatch.setattr(
        "nexus.config.get_openai_compatible_endpoint",
        lambda _model: None,
    )
    monkeypatch.setattr(
        "nexus.agents.logon.orrery_tag_validation." "build_storyteller_tag_validator",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        LogonUtility,
        "_load_system_prompt",
        lambda _self, _is_bootstrap=None: "Core prompt",
    )
    monkeypatch.setattr(
        logon_utility,
        "AnthropicProvider",
        RecordingAnthropicProvider,
    )
    settings = {
        "API Settings": {
            "apex": {
                "anthropic_storyteller_transport": configured_transport,
                "max_output_tokens": 1234,
                "reasoning_effort": "medium",
                "structured_output_retries": 2,
            }
        }
    }
    utility = LogonUtility(settings, model_override="claude-sonnet-4-5")

    utility._initialize_provider(is_bootstrap)

    assert captured["structured_transport"] == expected_transport
    assert captured["reasoning_effort"] == "medium"
    expected_system = (
        f"Core prompt\n\n{skald_wire_prompt_guide()}" if has_guide else "Core prompt"
    )
    assert captured["system_prompt"] == expected_system
    assert utility._system_prompt == expected_system


@pytest.mark.parametrize(
    ("provider_type", "base_url", "expected_wire_type"),
    [
        ("openai", None, "openai"),
        ("anthropic", None, "anthropic"),
        ("local", "http://127.0.0.1:1234/v1", "local"),
    ],
)
def test_storyteller_route_resolves_without_constructing_provider(
    monkeypatch: pytest.MonkeyPatch,
    provider_type: str,
    base_url: str | None,
    expected_wire_type: str,
) -> None:
    """Budget classification reuses LOGON routing while provider init stays lazy."""
    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.get_provider_for_model",
        lambda _model: provider_type,
    )
    monkeypatch.setattr(
        "nexus.config.get_openai_compatible_endpoint",
        lambda _model: {"base_url": base_url} if base_url else None,
    )
    logon = LogonUtility({}, model_override="storyteller-model")

    assert logon.resolve_storyteller_route() == (
        "storyteller-model",
        expected_wire_type,
    )
    assert logon.provider is None


def test_provider_initialization_reuses_the_compared_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A matching Phase 6 comparison must not perform a third route read."""
    logon = LogonUtility({}, model_override="storyteller-model")
    route = ("storyteller-model", "openai", None, "openai")
    route_calls = {"count": 0}
    initialized_routes: list[tuple[Any, ...] | None] = []

    def resolve_route() -> tuple[str, str, None, str]:
        route_calls["count"] += 1
        return route

    def initialize_provider(
        _is_bootstrap: bool | None = None,
        *,
        resolved_route: tuple[Any, ...] | None = None,
    ) -> None:
        initialized_routes.append(resolved_route)
        logon.provider = cast(Any, _DummyProvider())

    monkeypatch.setattr(logon, "_resolve_storyteller_route", resolve_route)
    monkeypatch.setattr(logon, "_initialize_provider", initialize_provider)

    logon._ensure_provider(
        _minimal_payload(),
        expected_model="storyteller-model",
        expected_wire_type="openai",
    )

    assert route_calls["count"] == 1
    assert initialized_routes == [route]


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
