"""Tests for the config-switched writer and gaia storyteller pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic_ai import ModelRetry

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
)
from nexus.agents.logon.orrery_tag_validation import (
    StorytellerVocabulary,
    build_storyteller_tag_validator,
)
from nexus.agents.logon.skald_wire import (
    PresenceBaseline,
    PresenceRef,
    SkaldGaiaWire,
    SkaldTurnWire,
    SkaldWriterWire,
    hydrate_skald_turn,
    skald_gaia_lenient_schema,
    skald_gaia_prompt_guide,
    skald_gaia_strict_text_format,
    skald_writer_lenient_schema,
    skald_writer_strict_text_format,
)
from nexus.agents.lore import logon_utility
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api.native_structured_output import (
    anthropic_output_config,
    openai_response_text_format,
    retry_prompt,
    run_output_validator,
)


@pytest.fixture(autouse=True)
def _hermetic_setting_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep gaia system prompts DB-free here; setting-card composition is
    covered in test_logon_prompt_formatting."""

    monkeypatch.setattr(LogonUtility, "_load_setting_context", lambda self: None)


WRITER_PAYLOAD: dict[str, Any] = {
    "narrative": 'Iona says, "Wait."\nThe drowned bell answers.',
    "choices": [
        "Follow Iona into the archive.",
        "Stay beneath the sluice gate.",
    ],
    "scene": {"elapsed_minutes": 7, "weather": "rain"},
    "presence": {
        "mentions": [{"kind": "faction", "name": "The Glass Choir", "id": 13}]
    },
    "operations": {
        "request_summary": {
            "summary_type": "episode",
            "reason": "The archive crossing closes the beat.",
        }
    },
    "letter": (
        "The bell is bait. Let Iona suspect the Choir before we confirm who "
        "actually rang it."
    ),
}
GAIA_PAYLOAD: dict[str, Any] = {
    "updates": {
        "characters": [
            {
                "name": "Iona Vale",
                "id": 4,
                "activity": "listening for the drowned bell",
            }
        ],
        "places": [],
        "factions": [],
        "relationships": [],
    },
    "orrery_adjudications": [],
    "new_entities": [
        {
            "kind": "faction",
            "name": "The Glass Choir",
            "summary": "An unseen choir carried through flooded pipes.",
        }
    ],
    "letter": (
        "Agreed. I will move the Choir through the pipes but leave the bell's "
        "ringer unresolved."
    ),
}
SINGLE_PASS_PAYLOAD: dict[str, Any] = {
    "narrative": 'Iona says, "Wait."\nThe drowned bell answers.',
    "choices": [
        "Follow Iona into the archive.",
        "Stay beneath the sluice gate.",
    ],
    "scene": {"elapsed_minutes": 7, "weather": "rain"},
    "presence": {
        "mentions": [{"kind": "faction", "name": "The Glass Choir", "id": 13}]
    },
    "updates": {
        "characters": [
            {
                "name": "Iona Vale",
                "id": 4,
                "activity": "listening for the drowned bell",
            }
        ],
        "places": [],
        "factions": [],
        "relationships": [],
    },
    "operations": {
        "request_summary": {
            "summary_type": "episode",
            "reason": "The archive crossing closes the beat.",
        }
    },
    "orrery_adjudications": [],
    "new_entities": [
        {
            "kind": "faction",
            "name": "The Glass Choir",
            "summary": "An unseen choir carried through flooded pipes.",
        }
    ],
    "letter": "Keep the bell's ringer unresolved while the Choir advances.",
}
BASELINE = PresenceBaseline(
    present=[PresenceRef(kind="character", name="Iona Vale", id=4)],
    setting=PresenceRef(kind="place", name="The Lower Sluice", id=9),
)


class _RecordingProvider:
    """Shallow-copy-friendly provider stub recording pass-local state."""

    def __init__(
        self,
        outputs: list[object],
        *,
        structured_transport: str = "responses",
        output_validator: Any = None,
        structured_output_retries: int = 3,
    ) -> None:
        self.model = "two-pass-test-model"
        self.system_prompt = "Core storyteller prompt"
        self.output_validator = output_validator
        self.structured_transport = structured_transport
        self.structured_output_retries = structured_output_retries
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def _record_attempt(
        self,
        prompt: str,
        schema_model: type,
        kwargs: dict[str, Any],
    ) -> None:
        self.calls.append(
            {
                "prompt": prompt,
                "schema_model": schema_model,
                "kwargs": kwargs,
                "system_prompt": self.system_prompt,
                "output_validator": self.output_validator,
                "structured_transport": self.structured_transport,
                "structured_output_retries": self.structured_output_retries,
            }
        )

    def _parse_next_output(self, schema_model: type) -> Any:
        output = self.outputs.pop(0)
        if isinstance(output, BaseException):
            raise output
        return schema_model.model_validate(output)

    def get_structured_completion(
        self,
        prompt: str,
        schema_model: type,
        **kwargs: Any,
    ) -> tuple[Any, object]:
        active_prompt = prompt
        for attempt in range(self.structured_output_retries + 1):
            self._record_attempt(active_prompt, schema_model, kwargs)
            parsed = self._parse_next_output(schema_model)
            try:
                parsed = asyncio.run(
                    run_output_validator(
                        self.output_validator,
                        parsed,
                        retry=attempt,
                    )
                )
                return parsed, object()
            except ModelRetry as exc:
                if attempt >= self.structured_output_retries:
                    raise
                active_prompt = retry_prompt(prompt, exc.message)
        raise AssertionError("Structured retry loop did not return or raise")

    async def get_structured_completion_async(
        self,
        prompt: str,
        schema_model: type,
        **kwargs: Any,
    ) -> tuple[Any, object]:
        active_prompt = prompt
        for attempt in range(self.structured_output_retries + 1):
            self._record_attempt(active_prompt, schema_model, kwargs)
            parsed = self._parse_next_output(schema_model)
            try:
                parsed = await run_output_validator(
                    self.output_validator,
                    parsed,
                    retry=attempt,
                )
                return parsed, object()
            except ModelRetry as exc:
                if attempt >= self.structured_output_retries:
                    raise
                active_prompt = retry_prompt(prompt, exc.message)
        raise AssertionError("Structured retry loop did not return or raise")


class _FixtureCursor:
    """Context-managed cursor unused by single-entity fixture validation."""

    def __enter__(self) -> "_FixtureCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class _FixtureConnection:
    """Connection stand-in for the real validator's read-only cursor seam."""

    def __enter__(self) -> "_FixtureConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def cursor(self) -> _FixtureCursor:
        return _FixtureCursor()


def _gaia_payload_with_character_tag(tag: str) -> dict[str, Any]:
    return {
        "updates": {
            "characters": [
                {
                    "name": "Iona Vale",
                    "id": 4,
                    "activity": "listening for the drowned bell",
                    "tags_add": [tag],
                }
            ],
            "places": [],
            "factions": [],
            "relationships": [],
        },
        "orrery_adjudications": [],
        "new_entities": [],
        "letter": GAIA_PAYLOAD["letter"],
    }


def _context(*, bootstrap: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_input": "Open the archive.",
        "warm_slice": {"chunks": []},
        "entity_data": {},
        "retrieved_passages": {"results": []},
    }
    if bootstrap:
        payload["is_bootstrap"] = True
        payload["metadata"] = {"is_bootstrap": True}
    return payload


def _utility(
    provider_type: str,
    outputs: list[object],
    *,
    anthropic_transport: str | None = None,
    bootstrap: bool = False,
    output_validator: Any = None,
    structured_output_retries: int = 3,
) -> tuple[LogonUtility, _RecordingProvider]:
    if provider_type == "anthropic":
        if anthropic_transport is None:
            raise ValueError("Anthropic test utility requires a transport")
        provider_transport = anthropic_transport
    else:
        if anthropic_transport is not None:
            raise ValueError("Non-Anthropic test utility cannot set a transport")
        provider_transport = "responses"
    settings = {
        "API Settings": {
            "apex": {
                "turn_pipeline": "two_pass",
                "anthropic_storyteller_transport": (anthropic_transport or "prompted"),
            }
        }
    }
    provider = _RecordingProvider(
        outputs,
        structured_transport=provider_transport,
        output_validator=output_validator,
        structured_output_retries=structured_output_retries,
    )
    utility = LogonUtility(settings, model_override=provider.model)
    utility.provider = cast(Any, provider)
    utility._provider_bootstrap_mode = bootstrap
    utility._provider_wire_type = cast(Any, provider_type)
    utility._provider_type_name = provider_type
    utility._system_prompt = provider.system_prompt
    return utility, provider


def _expected_schema_kwargs(
    provider_type: str,
    anthropic_transport: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if provider_type == "openai":
        return (
            {"text_format": skald_writer_strict_text_format()},
            {"text_format": skald_gaia_strict_text_format()},
        )
    if provider_type == "local":
        return (
            {
                "text_format": openai_response_text_format(
                    SkaldWriterWire,
                    schema=skald_writer_lenient_schema(),
                )
            },
            {
                "text_format": openai_response_text_format(
                    SkaldGaiaWire,
                    schema=skald_gaia_lenient_schema(),
                )
            },
        )
    if anthropic_transport not in {"prompted", "tool_envelope"}:
        raise ValueError("Successful Anthropic test requires a schema-free transport")
    gaia_kwargs = (
        {}
        if anthropic_transport == "prompted"
        else {"input_schema": skald_gaia_lenient_schema()}
    )
    return (
        {
            "output_config": anthropic_output_config(
                SkaldWriterWire,
                schema=skald_writer_lenient_schema(),
            )
        },
        gaia_kwargs,
    )


def _assert_two_pass_calls(
    provider: _RecordingProvider,
    provider_type: str,
    anthropic_transport: str | None,
) -> None:
    writer = SkaldWriterWire.model_validate(WRITER_PAYLOAD)
    assert len(provider.calls) == 2
    writer_call, gaia_call = provider.calls
    expected_writer_kwargs, expected_gaia_kwargs = _expected_schema_kwargs(
        provider_type,
        anthropic_transport,
    )

    assert writer_call["schema_model"] is SkaldWriterWire
    assert gaia_call["schema_model"] is SkaldGaiaWire
    assert writer_call["kwargs"] == expected_writer_kwargs
    assert gaia_call["kwargs"] == expected_gaia_kwargs
    assert writer_call["output_validator"] is None
    assert gaia_call["output_validator"] is None
    assert writer_call["structured_output_retries"] == 3
    assert gaia_call["structured_output_retries"] == 3
    # Writer pass = core doctrine + explicit scope note (gaia work excluded);
    # schema-free writers obey the core prompt over the repair loop without it.
    assert writer_call["system_prompt"].startswith("Core storyteller prompt")
    assert "# Writer Pass" in writer_call["system_prompt"]
    assert "# Writer Pass" not in gaia_call["system_prompt"]
    assert "## Gaia" in gaia_call["system_prompt"]
    assert gaia_call["prompt"].startswith(writer_call["prompt"])
    assert writer.narrative in gaia_call["prompt"]
    assert writer.scene is not None
    assert writer.scene.model_dump_json(exclude_none=True) in gaia_call["prompt"]
    assert writer.presence is not None
    assert writer.presence.model_dump_json(exclude_none=True) in gaia_call["prompt"]

    if provider_type == "anthropic":
        assert anthropic_transport is not None
        assert writer_call["structured_transport"] == "native"
        assert gaia_call["structured_transport"] == anthropic_transport
        if anthropic_transport == "prompted":
            assert gaia_call["kwargs"] == {}
            assert gaia_call["system_prompt"].endswith(skald_gaia_prompt_guide())
        else:
            assert gaia_call["kwargs"] == {"input_schema": skald_gaia_lenient_schema()}
            assert "output_config" not in gaia_call["kwargs"]
            assert skald_gaia_prompt_guide() not in gaia_call["system_prompt"]
            assert "=== OUTPUT FORMAT ===" not in gaia_call["system_prompt"]
    else:
        assert anthropic_transport is None
        assert writer_call["structured_transport"] == "responses"
        assert gaia_call["structured_transport"] == "responses"
        assert "=== OUTPUT FORMAT ===" not in gaia_call["system_prompt"]


def _assert_matches_independently_parsed_single_pass(
    actual: StorytellerResponseExtended,
) -> None:
    """Compare canonical fields against a separately parsed full-wire payload."""

    single_pass_wire = SkaldTurnWire.model_validate(SINGLE_PASS_PAYLOAD)
    expected = hydrate_skald_turn(
        single_pass_wire,
        presence_baseline=BASELINE,
    )
    for field_name in StorytellerResponseExtended.model_fields:
        if field_name != "generation_model":
            assert getattr(actual, field_name) == getattr(expected, field_name)


@pytest.mark.parametrize(
    ("provider_type", "anthropic_transport"),
    [
        ("openai", None),
        ("local", None),
        ("anthropic", "prompted"),
        ("anthropic", "tool_envelope"),
    ],
)
def test_sync_two_pass_pipeline_uses_provider_specific_transports(
    provider_type: str,
    anthropic_transport: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility(
        provider_type,
        [WRITER_PAYLOAD, GAIA_PAYLOAD],
        anthropic_transport=anthropic_transport,
    )
    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context",
        lambda _context_payload, _schema_model: BASELINE,
    )

    response = utility.generate_narrative(
        _context(),
        effective_context_window=75_000,
    )

    _assert_two_pass_calls(provider, provider_type, anthropic_transport)
    assert response.narrative == WRITER_PAYLOAD["narrative"]
    assert response.generation_model == provider.model


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_type", "anthropic_transport"),
    [
        ("openai", None),
        ("local", None),
        ("anthropic", "prompted"),
        ("anthropic", "tool_envelope"),
    ],
)
async def test_async_two_pass_pipeline_uses_provider_specific_transports(
    provider_type: str,
    anthropic_transport: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility(
        provider_type,
        [WRITER_PAYLOAD, GAIA_PAYLOAD],
        anthropic_transport=anthropic_transport,
    )

    async def read_baseline(
        _context_payload: dict[str, Any],
        _schema_model: type,
    ) -> PresenceBaseline:
        return BASELINE

    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context_async",
        read_baseline,
    )

    response = await utility.generate_narrative_async(
        _context(),
        effective_context_window=75_000,
    )

    _assert_two_pass_calls(provider, provider_type, anthropic_transport)
    assert response.narrative == WRITER_PAYLOAD["narrative"]
    assert response.generation_model == provider.model


def test_sync_anthropic_two_pass_rejects_native_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility(
        "anthropic",
        [],
        anthropic_transport="native",
    )
    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context",
        lambda _context_payload, _schema_model: BASELINE,
    )

    with pytest.raises(ValueError) as exc_info:
        utility.generate_narrative(
            _context(),
            effective_context_window=75_000,
        )

    message = str(exc_info.value)
    assert "gaia wire cannot compile under Anthropic native enforcement" in message
    assert "probe G2b, issue #566" in message
    assert "'prompted'" in message
    assert "'tool_envelope'" in message
    assert provider.calls == []


@pytest.mark.asyncio
async def test_async_anthropic_two_pass_rejects_native_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility(
        "anthropic",
        [],
        anthropic_transport="native",
    )

    async def read_baseline(
        _context_payload: dict[str, Any],
        _schema_model: type,
    ) -> PresenceBaseline:
        return BASELINE

    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context_async",
        read_baseline,
    )

    with pytest.raises(ValueError) as exc_info:
        await utility.generate_narrative_async(
            _context(),
            effective_context_window=75_000,
        )

    message = str(exc_info.value)
    assert "gaia wire cannot compile under Anthropic native enforcement" in message
    assert "probe G2b, issue #566" in message
    assert "'prompted'" in message
    assert "'tool_envelope'" in message
    assert provider.calls == []


def test_two_pass_hydration_matches_independent_single_pass_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Split and full raw payloads reach equivalent canonical hydration."""

    utility, _provider = _utility(
        "openai",
        [WRITER_PAYLOAD, GAIA_PAYLOAD],
    )
    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context",
        lambda _context_payload, _schema_model: BASELINE,
    )

    actual = utility.generate_narrative(
        _context(),
        effective_context_window=75_000,
    )

    _assert_matches_independently_parsed_single_pass(actual)


def test_real_vocabulary_validator_belongs_to_gaia_and_consumes_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shipped validator traverses gaia fields and never reaches writer."""

    from nexus.agents.logon import orrery_tag_validation
    from nexus.api import db_pool

    vocabulary = StorytellerVocabulary(
        tag_names_by_kind={
            "character": frozenset({"perceptive"}),
            "place": frozenset(),
            "faction": frozenset(),
        },
        pair_tag_names=frozenset(),
        event_types=frozenset(),
    )
    monkeypatch.setattr(
        orrery_tag_validation,
        "read_storyteller_vocabulary",
        lambda _dbname: vocabulary,
    )
    monkeypatch.setattr(
        db_pool,
        "get_connection",
        lambda _dbname: _FixtureConnection(),
    )
    validator = build_storyteller_tag_validator(
        "fixture_slot",
        suggestion_limit=3,
    )
    assert validator is not None
    utility, provider = _utility(
        "openai",
        [
            WRITER_PAYLOAD,
            _gaia_payload_with_character_tag("unregistered"),
            _gaia_payload_with_character_tag("perceptive"),
        ],
        output_validator=validator,
        structured_output_retries=1,
    )
    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context",
        lambda _context_payload, _schema_model: BASELINE,
    )

    response = utility.generate_narrative(
        _context(),
        effective_context_window=75_000,
    )

    assert [call["schema_model"] for call in provider.calls] == [
        SkaldWriterWire,
        SkaldGaiaWire,
        SkaldGaiaWire,
    ]
    assert provider.calls[0]["output_validator"] is None
    assert all(call["output_validator"] is validator for call in provider.calls[1:])
    retry_prompt_text = provider.calls[2]["prompt"]
    assert "=== STRUCTURED OUTPUT RETRY ===" in retry_prompt_text
    assert "failed closed-registry validation" in retry_prompt_text
    assert "updates.characters[0]" in retry_prompt_text
    assert "'unregistered'" in retry_prompt_text
    assert provider.outputs == []
    bestowal = response.state_updates.characters[0].orrery_tags
    assert bestowal is not None
    assert bestowal.applied_tags == ["perceptive"]


def test_writer_failure_short_circuits_before_gaia_or_hydration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility("openai", [RuntimeError("writer exhausted repairs")])
    hydrated: list[object] = []
    monkeypatch.setattr(
        logon_utility,
        "hydrate_skald_turn",
        lambda *args, **kwargs: hydrated.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="writer exhausted repairs"):
        utility.generate_narrative(
            _context(),
            effective_context_window=75_000,
        )

    assert [call["schema_model"] for call in provider.calls] == [SkaldWriterWire]
    assert hydrated == []


@pytest.mark.asyncio
async def test_gaia_failure_raises_without_partial_hydration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility(
        "anthropic",
        [WRITER_PAYLOAD, RuntimeError("gaia exhausted repairs")],
        anthropic_transport="prompted",
    )
    hydrated: list[object] = []
    monkeypatch.setattr(
        logon_utility,
        "hydrate_skald_turn",
        lambda *args, **kwargs: hydrated.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="gaia exhausted repairs"):
        await utility.generate_narrative_async(
            _context(),
            effective_context_window=75_000,
        )

    assert [call["schema_model"] for call in provider.calls] == [
        SkaldWriterWire,
        SkaldGaiaWire,
    ]
    assert hydrated == []


def test_bootstrap_request_ignores_two_pass_lever() -> None:
    bootstrap = StorytellerResponseBootstrap(
        narrative="The first door opens.",
        choices=["Enter.", "Wait."],
    )
    utility, provider = _utility("openai", [bootstrap], bootstrap=True)

    response = utility.generate_narrative(
        _context(bootstrap=True),
        effective_context_window=75_000,
    )

    assert response.narrative == bootstrap.narrative
    assert len(provider.calls) == 1
    assert provider.calls[0]["schema_model"] is StorytellerResponseBootstrap
    assert "FINISHED WRITER" not in provider.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_async_bootstrap_request_ignores_two_pass_lever() -> None:
    bootstrap = StorytellerResponseBootstrap(
        narrative="The first door opens.",
        choices=["Enter.", "Wait."],
    )
    utility, provider = _utility("openai", [bootstrap], bootstrap=True)

    response = await utility.generate_narrative_async(
        _context(bootstrap=True),
        effective_context_window=75_000,
    )

    assert response.narrative == bootstrap.narrative
    assert len(provider.calls) == 1
    assert provider.calls[0]["schema_model"] is StorytellerResponseBootstrap


def test_gaia_prompt_is_concise_and_self_contained() -> None:
    prompt_path = Path(__file__).parents[2] / "prompts" / "storyteller_gaia.md"
    prompt = prompt_path.read_text()
    normalized_prompt = " ".join(prompt.split())

    # Word count, not line count: the file keeps one line per paragraph, so
    # line count no longer measures concision (currently ~500 words).
    assert len(prompt.split()) < 700
    # The persona rewrite (owner brief, 2026-07-27) made gaia.md
    # self-sufficient: the shared doctrine it needs (canon hierarchy,
    # setting idiom, sincere beliefs) is inlined in Gaia's voice instead of
    # referencing a core document the seat never receives.
    assert "storyteller_core.md" not in prompt
    assert "recent narrative over retrieved context over" in normalized_prompt
    assert "The prose is finished — Gaia's medium is state" in prompt
    assert "riffs off it, never against it" in prompt
    assert (
        "`characters`, `places`, `factions`, and `relationships`" in normalized_prompt
    )


# --- Pinned gaia seat (#578 rung 2) -----------------------------------------


def _pinned_gaia_utility(
    provider_type: str,
    outputs: list[object],
    *,
    anthropic_transport: str | None = None,
) -> tuple[LogonUtility, _RecordingProvider]:
    """Writer runs the active provider; gaia_model pins a different seat."""

    utility, provider = _utility(
        provider_type,
        outputs,
        anthropic_transport=anthropic_transport,
    )
    utility.settings["API Settings"]["apex"]["gaia_model"] = "pinned-gaia-model"
    utility.settings["Agent Settings"] = {
        "LORE": {
            "token_budget": {
                "apex_context_window": 75_000,
                "provider_overrides": {"local": 32_000},
            }
        }
    }
    return utility, provider


def _patch_gaia_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register the fake pinned gaia id as a native OpenAI model."""

    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.get_provider_for_model",
        lambda model_id, path=None: (
            "openai" if model_id == "pinned-gaia-model" else None
        ),
    )
    monkeypatch.setattr(
        "nexus.config.get_openai_compatible_endpoint",
        lambda model_id, path=None: None,
    )


def _install_gaia_capture(
    utility: LogonUtility,
    monkeypatch: pytest.MonkeyPatch,
    gaia_recorder: _RecordingProvider,
) -> tuple[dict[str, Any], list[Any]]:
    """Capture the gaia build args and every enforcement window."""

    captured: dict[str, Any] = {}

    def fake_build(
        gaia_route: Any,
        *,
        system_prompt: Any,
        output_validator: Any,
        anthropic_transport: Any,
    ) -> _RecordingProvider:
        captured["route"] = gaia_route
        captured["system_prompt"] = system_prompt
        captured["anthropic_transport"] = anthropic_transport
        gaia_recorder.system_prompt = system_prompt
        gaia_recorder.output_validator = output_validator
        return gaia_recorder

    monkeypatch.setattr(utility, "_build_gaia_provider", fake_build)

    windows: list[Any] = []
    real_enforce = utility._enforce_final_prompt_window

    def spy_enforce(prompt: str, *, effective_context_window: Any) -> int:
        windows.append(effective_context_window)
        return real_enforce(prompt, effective_context_window=effective_context_window)

    monkeypatch.setattr(utility, "_enforce_final_prompt_window", spy_enforce)
    return captured, windows


@pytest.mark.parametrize(
    ("writer_type", "writer_transport"),
    [
        ("anthropic", "prompted"),
        ("local", None),
        # Native + two_pass was rejected outright (probe G2b); with the gaia
        # pinned OFF Anthropic, the writer's native output_config compiles
        # (G2a) and the pipeline must proceed.
        ("anthropic", "native"),
    ],
)
def test_sync_pinned_gaia_runs_fresh_openai_seat(
    writer_type: str,
    writer_transport: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _pinned_gaia_utility(
        writer_type,
        [WRITER_PAYLOAD],
        anthropic_transport=writer_transport,
    )
    _patch_gaia_registry(monkeypatch)
    gaia_recorder = _RecordingProvider([GAIA_PAYLOAD])
    captured, windows = _install_gaia_capture(utility, monkeypatch, gaia_recorder)
    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context",
        lambda _context_payload, _schema_model: BASELINE,
    )

    response = utility.generate_narrative(
        _context(),
        effective_context_window=32_000,
    )

    # Writer ran on the active provider's clone; gaia on the pinned seat.
    assert len(provider.calls) == 1
    assert provider.calls[0]["schema_model"] is SkaldWriterWire
    assert len(gaia_recorder.calls) == 1
    gaia_call = gaia_recorder.calls[0]
    assert gaia_call["schema_model"] is SkaldGaiaWire
    # Heterogeneous kwargs: strict OpenAI gaia schema under this writer wire.
    assert gaia_call["kwargs"] == {"text_format": skald_gaia_strict_text_format()}
    assert captured["route"][0] == "pinned-gaia-model"
    assert captured["route"][3] == "openai"
    assert captured["anthropic_transport"] is None
    assert "## Gaia" in captured["system_prompt"]
    assert skald_gaia_prompt_guide() not in captured["system_prompt"]
    # Gaia enforcement used the GAIA provider's window, not the writer's 32K.
    assert windows[-1] == 75_000
    assert response.narrative == WRITER_PAYLOAD["narrative"]


@pytest.mark.asyncio
async def test_async_pinned_gaia_runs_fresh_openai_seat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _pinned_gaia_utility("local", [WRITER_PAYLOAD])
    _patch_gaia_registry(monkeypatch)
    gaia_recorder = _RecordingProvider([GAIA_PAYLOAD])
    captured, windows = _install_gaia_capture(utility, monkeypatch, gaia_recorder)

    async def read_baseline(
        _context_payload: dict[str, Any],
        _schema_model: type,
    ) -> Any:
        return BASELINE

    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context_async",
        read_baseline,
    )

    response = await utility.generate_narrative_async(
        _context(),
        effective_context_window=32_000,
    )

    assert len(provider.calls) == 1
    assert len(gaia_recorder.calls) == 1
    assert gaia_recorder.calls[0]["kwargs"] == {
        "text_format": skald_gaia_strict_text_format()
    }
    assert captured["route"][3] == "openai"
    assert windows[-1] == 75_000
    assert response.narrative == WRITER_PAYLOAD["narrative"]


def test_gaia_route_guards_fall_back_to_the_clone_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset, TEST-provider, and same-model configs all keep the clone path."""

    unset_utility, _provider = _utility("openai", [])
    assert unset_utility._resolve_gaia_route() is None

    test_utility, _provider = _utility("openai", [])
    test_utility.settings["API Settings"]["apex"]["gaia_model"] = "pinned-gaia-model"
    test_utility._provider_type_name = "test"
    assert test_utility._resolve_gaia_route() is None

    same_utility, same_provider = _utility("openai", [])
    same_utility.settings["API Settings"]["apex"]["gaia_model"] = same_provider.model
    assert same_utility._resolve_gaia_route() is None

    junk_utility, _provider = _utility("openai", [])
    junk_utility.settings["API Settings"]["apex"]["gaia_model"] = "pinned-gaia-model"
    monkeypatch.setattr(
        "nexus.agents.lore.logon_utility.get_provider_for_model",
        lambda _model_id, _path=None: None,
    )
    with pytest.raises(ValueError, match="not in the model registry"):
        junk_utility._resolve_gaia_route()


def test_anthropic_gaia_under_non_anthropic_writer_reads_the_setting() -> None:
    """A pinned Anthropic gaia must honor the configured transport loudly."""

    utility, _provider = _utility("openai", [])
    utility.settings["API Settings"]["apex"][
        "anthropic_storyteller_transport"
    ] = "native"
    with pytest.raises(ValueError, match="gaia wire cannot"):
        utility._resolve_anthropic_two_pass_gaia_transport("anthropic")


def test_two_pass_schema_kwargs_cache_is_wire_keyed() -> None:
    """The same schema must yield per-wire kwargs, never a stale cache hit."""

    utility, _provider = _utility("anthropic", [], anthropic_transport="prompted")
    anthropic_kwargs = utility._two_pass_schema_format_kwargs(SkaldGaiaWire)
    openai_kwargs = utility._two_pass_schema_format_kwargs(
        SkaldGaiaWire, wire_type="openai"
    )
    assert anthropic_kwargs == {}
    assert openai_kwargs == {"text_format": skald_gaia_strict_text_format()}
