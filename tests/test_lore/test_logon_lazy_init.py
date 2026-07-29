"""Tests for lazy initialization of LOGON provider."""

from __future__ import annotations

import logging
from typing import Any, cast, Dict

import pytest

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
)
from nexus.agents.logon.skald_wire import (
    SkaldTurnWire,
    skald_wire_lenient_schema,
    skald_wire_prompt_guide,
)
from nexus.agents.lore import logon_utility
from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.memory import ContextMemoryManager


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
        self, prompt: str, schema_model: type, **_kwargs: Any
    ) -> tuple[Any, _DummyResponse]:
        self.calls += 1
        self.schema_models.append(schema_model)
        return self._response(prompt, schema_model), _DummyResponse(prompt)

    async def get_structured_completion_async(
        self, prompt: str, schema_model: type, **_kwargs: Any
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
        kwargs = (
            {"letter": "Keep the test turn private."}
            if response_type is SkaldTurnWire
            else {}
        )
        return response_type(
            narrative=f"dummy:{prompt[:20]}",
            choices=[
                "Continue.",
                "Wait and observe.",
            ],
            **kwargs,
        )


class _FailingProvider:
    model = "dummy-model"

    def __init__(self) -> None:
        self.structured_calls = 0
        self.completion_calls = 0

    async def get_structured_completion_async(
        self, prompt: str, schema_model: type, **_kwargs: Any
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
        self._provider_wire_type = "openai"
        self._provider_type_name = "openai"

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

    def fake_resolve(model_ref: str, path: object = None) -> str:
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
    (
        "configured_transport",
        "is_bootstrap",
        "turn_pipeline",
        "expected_transport",
        "has_guide",
    ),
    [
        ("prompted", False, "single_pass", "prompted", True),
        ("native", False, "single_pass", "native", False),
        ("tool_envelope", False, "single_pass", "tool_envelope", False),
        ("prompted", True, "single_pass", "native", False),
        ("tool_envelope", True, "single_pass", "native", False),
        ("prompted", False, "two_pass", "prompted", False),
        ("tool_envelope", False, "two_pass", "tool_envelope", False),
        ("native", False, "two_pass", "native", False),
        ("prompted", True, "two_pass", "native", False),
    ],
)
def test_anthropic_storyteller_transport_and_guide_follow_settings(
    monkeypatch: pytest.MonkeyPatch,
    configured_transport: str,
    is_bootstrap: bool,
    turn_pipeline: str,
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
        lambda _model, _path=None: "anthropic",
    )
    monkeypatch.setattr(
        "nexus.config.get_openai_compatible_endpoint",
        lambda _model, _path=None: None,
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
                "turn_pipeline": turn_pipeline,
                "max_output_tokens": 1234,
                "reasoning_effort": "medium",
                "structured_output_retries": 2,
            }
        },
        "storyteller": {
            "correspondence": {
                "floor_turns": 5,
                "ceiling_turns": 10,
                "compaction_model": "claude-sonnet-4-5",
                "max_letter_tokens": 300,
                "max_digest_tokens": 2000,
                "max_rendered_tokens": 12000,
            }
        },
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
    if expected_transport == "tool_envelope" and turn_pipeline == "single_pass":
        assert utility._schema_format_kwargs(SkaldTurnWire) == {
            "input_schema": skald_wire_lenient_schema()
        }


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
        lambda _model, _path=None: provider_type,
    )
    monkeypatch.setattr(
        "nexus.config.get_openai_compatible_endpoint",
        lambda _model, _path=None: {"base_url": base_url} if base_url else None,
    )
    logon = LogonUtility({}, model_override="storyteller-model")

    assert logon.resolve_storyteller_route() == (
        "storyteller-model",
        expected_wire_type,
        provider_type,
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


def test_sync_generation_rejects_mid_turn_route_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The synchronous generation path compares the authoritative turn route."""
    logon = LogonUtility({}, model_override="phase-one-model")
    monkeypatch.setattr(
        logon,
        "_resolve_storyteller_route",
        lambda: ("changed-model", "openai", None, "local"),
    )

    with pytest.raises(
        RuntimeError,
        match="slot model changed mid-turn; aborting the turn",
    ):
        logon.generate_narrative(
            _minimal_payload(),
            expected_model="phase-one-model",
            expected_wire_type="openai",
            effective_context_window=75_000,
        )

    assert logon.provider is None


@pytest.mark.requires_postgres
def test_lore_keeps_logon_lazy(patched_provider: Dict[str, int]) -> None:
    """LORE should construct LOGON without eagerly constructing its provider."""

    lore = LORE(debug=True, enable_logon=True)
    assert patched_provider["count"] == 0
    assert lore.logon is None
    lore.ensure_logon()
    assert lore.logon is not None
    assert lore.logon.provider is None
    assert patched_provider["count"] == 0


def test_logon_initializes_provider_on_first_generation(
    patched_provider: Dict[str, int],
) -> None:
    """The first narrative generation should initialize the provider exactly once."""

    # Provider laziness is independent of the production two-pass default.
    # Pin the simplest generation route so this regression test does not absorb
    # database, contextual-tag-library, or writer/Gaia fixture contracts.
    logon = LogonUtility(
        {"API Settings": {"apex": {"turn_pipeline": "single_pass"}}},
        model_override="dummy-model",
    )
    assert logon.provider is None
    assert patched_provider["count"] == 0

    response = logon.generate_narrative(
        _minimal_payload(),
        effective_context_window=75_000,
    )

    assert patched_provider["count"] == 1
    assert isinstance(logon.provider, _DummyProvider)
    assert logon.provider.calls == 1
    assert logon.provider.schema_models == [SkaldTurnWire]
    assert response.narrative.startswith("dummy:")
    assert response.generation_model == "dummy-model"


@pytest.mark.asyncio
async def test_logon_async_generation_uses_structured_provider() -> None:
    """Async LOGON generation should use structured provider output directly."""

    provider = _DummyProvider()
    logon = LogonUtility({}, model_override="dummy-model")
    logon.provider = cast(Any, provider)
    logon._provider_bootstrap_mode = False
    logon._provider_wire_type = "openai"
    logon._provider_type_name = "openai"

    response = await logon.generate_narrative_async(
        _minimal_payload(),
        effective_context_window=75_000,
    )

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
    logon._provider_wire_type = "openai"
    logon._provider_type_name = "openai"

    response = await logon.generate_narrative_async(
        _minimal_payload(is_bootstrap=True),
        effective_context_window=75_000,
    )

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
            self, prompt: str, schema_model: type, **kwargs: Any
        ) -> tuple[Any, _DummyResponse]:
            self.model = "successful-attempt-model"
            return await super().get_structured_completion_async(
                prompt,
                schema_model,
                **kwargs,
            )

    provider = RetrySwitchingProvider()
    logon = LogonUtility({}, model_override="first-attempt-model")
    logon.provider = cast(Any, provider)
    logon._provider_bootstrap_mode = False
    logon._provider_wire_type = "openai"
    logon._provider_type_name = "openai"

    response = await logon.generate_narrative_async(
        _minimal_payload(),
        effective_context_window=75_000,
    )

    assert response.generation_model == "successful-attempt-model"


@pytest.mark.asyncio
async def test_logon_structured_failure_does_not_call_plain_text_fallback() -> None:
    """Structured LOGON failures should fail fast without a second LLM call."""

    provider = _FailingProvider()
    logon = LogonUtility({}, model_override="dummy-model")
    logon.provider = cast(Any, provider)
    logon._provider_bootstrap_mode = False
    logon._provider_wire_type = "openai"
    logon._provider_type_name = "openai"

    with pytest.raises(RuntimeError, match="structured boom"):
        await logon.generate_narrative_async(
            _minimal_payload(),
            effective_context_window=75_000,
        )

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
        self._provider_wire_type = "openai"
        self._provider_type_name = "openai"

    monkeypatch.setattr(LogonUtility, "_initialize_provider", _fake_initialize)

    logon = LogonUtility({}, model_override="dummy-model", bootstrap_mode=False)

    logon.generate_narrative(
        _minimal_payload(is_bootstrap=True),
        effective_context_window=75_000,
    )

    assert initialized_modes == [True]
    assert logon.bootstrap_mode is False
    assert logon._provider_bootstrap_mode is True


@pytest.mark.asyncio
async def test_final_prompt_overflow_from_tag_library_raises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Too-small overhead cannot let LOGON send an oversized final prompt."""
    settings = {
        "Agent Settings": {
            "LORE": {
                "token_budget": {
                    "apex_context_window": 1_000,
                    "prompt_overhead_tokens": 0,
                    "provider_overrides": {"local": 1_000},
                }
            }
        }
    }
    provider = _DummyProvider()
    logon = LogonUtility(settings, model_override="dummy-model")
    logon.provider = cast(Any, provider)
    logon._provider_bootstrap_mode = False
    logon._provider_wire_type = "local"
    logon._provider_type_name = "local"

    class PromptLore:
        def __init__(self) -> None:
            self.settings = settings
            self.memnon = None
            self.memory_manager = ContextMemoryManager(settings)
            self.token_manager = None

    turn_manager = TurnCycleManager(PromptLore())
    turn_context = TurnContext(
        turn_id="undersized-overhead",
        user_input="Continue.",
        start_time=0,
    )
    turn_context.provider_wire_type = "local"
    turn_context.warm_slice = [{"chunk_id": 1, "text": "Parent.", "is_target": True}]
    turn_context.token_counts = {
        "total_available": 1_000,
        "warm_slice": 100,
        "structured": 0,
        "augmentation": 0,
    }
    await turn_manager.assemble_context_payload(turn_context)
    assert turn_context.phase_states["payload_assembly"]["payload_ceiling"] == 1_000

    monkeypatch.setattr(
        logon,
        "_format_turn_tag_library",
        lambda _context, *, presence_baseline: "oversized-tag " * 2_000,
    )

    with caplog.at_level(logging.DEBUG, logger="nexus.lore.logon"):
        with pytest.raises(
            ValueError,
            match="Final storyteller prompt exceeds the effective context window",
        ):
            await logon.generate_narrative_async(
                turn_context.context_payload,
                effective_context_window=1_000,
            )

    assert provider.calls == 0
    assert "Final storyteller prompt size: wire_class=local" in caplog.text
