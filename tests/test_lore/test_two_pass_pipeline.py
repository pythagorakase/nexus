"""Tests for the config-switched writer and clerk storyteller pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from nexus.agents.logon.apex_schema import StorytellerResponseBootstrap
from nexus.agents.logon.skald_wire import (
    PresenceBaseline,
    PresenceRef,
    SkaldClerkWire,
    SkaldWriterWire,
    combine_two_pass,
    hydrate_skald_turn,
    skald_clerk_lenient_schema,
    skald_clerk_prompt_guide,
    skald_clerk_strict_text_format,
    skald_writer_lenient_schema,
    skald_writer_strict_text_format,
)
from nexus.agents.lore import logon_utility
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api.native_structured_output import (
    anthropic_output_config,
    openai_response_text_format,
)


WRITER = SkaldWriterWire.model_validate(
    {
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
    }
)
CLERK = SkaldClerkWire.model_validate(
    {
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
    }
)
BASELINE = PresenceBaseline(
    present=[PresenceRef(kind="character", name="Iona Vale", id=4)],
    setting=PresenceRef(kind="place", name="The Lower Sluice", id=9),
)
VALIDATOR = object()


class _RecordingProvider:
    """Shallow-copy-friendly provider stub recording pass-local state."""

    def __init__(
        self,
        outputs: list[object],
        *,
        structured_transport: str = "responses",
    ) -> None:
        self.model = "two-pass-test-model"
        self.system_prompt = "Core storyteller prompt"
        self.output_validator = VALIDATOR
        self.structured_transport = structured_transport
        self.structured_output_retries = 3
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def _complete(
        self,
        prompt: str,
        schema_model: type,
        kwargs: dict[str, Any],
    ) -> tuple[Any, object]:
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
        output = self.outputs.pop(0)
        if isinstance(output, BaseException):
            raise output
        return output, object()

    def get_structured_completion(
        self,
        prompt: str,
        schema_model: type,
        **kwargs: Any,
    ) -> tuple[Any, object]:
        return self._complete(prompt, schema_model, kwargs)

    async def get_structured_completion_async(
        self,
        prompt: str,
        schema_model: type,
        **kwargs: Any,
    ) -> tuple[Any, object]:
        return self._complete(prompt, schema_model, kwargs)


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
    bootstrap: bool = False,
) -> tuple[LogonUtility, _RecordingProvider]:
    settings = {
        "API Settings": {
            "apex": {
                "turn_pipeline": "two_pass",
                "anthropic_storyteller_transport": "prompted",
            }
        }
    }
    provider = _RecordingProvider(
        outputs,
        structured_transport=(
            "prompted" if provider_type == "anthropic" else "responses"
        ),
    )
    utility = LogonUtility(settings, model_override=provider.model)
    utility.provider = cast(Any, provider)
    utility._provider_bootstrap_mode = bootstrap
    utility._provider_wire_type = cast(Any, provider_type)
    utility._system_prompt = provider.system_prompt
    return utility, provider


def _expected_schema_kwargs(
    provider_type: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if provider_type == "openai":
        return (
            {"text_format": skald_writer_strict_text_format()},
            {"text_format": skald_clerk_strict_text_format()},
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
                    SkaldClerkWire,
                    schema=skald_clerk_lenient_schema(),
                )
            },
        )
    return (
        {
            "output_config": anthropic_output_config(
                SkaldWriterWire,
                schema=skald_writer_lenient_schema(),
            )
        },
        {},
    )


def _assert_two_pass_calls(
    provider: _RecordingProvider,
    provider_type: str,
) -> None:
    assert len(provider.calls) == 2
    writer_call, clerk_call = provider.calls
    expected_writer_kwargs, expected_clerk_kwargs = _expected_schema_kwargs(
        provider_type
    )

    assert writer_call["schema_model"] is SkaldWriterWire
    assert clerk_call["schema_model"] is SkaldClerkWire
    assert writer_call["kwargs"] == expected_writer_kwargs
    assert clerk_call["kwargs"] == expected_clerk_kwargs
    assert writer_call["output_validator"] is None
    assert clerk_call["output_validator"] is VALIDATOR
    assert writer_call["structured_output_retries"] == 3
    assert clerk_call["structured_output_retries"] == 3
    assert writer_call["system_prompt"] == "Core storyteller prompt"
    assert "## Skald Clerk" in clerk_call["system_prompt"]
    assert clerk_call["prompt"].startswith(writer_call["prompt"])
    assert WRITER.narrative in clerk_call["prompt"]
    assert WRITER.scene is not None
    assert WRITER.scene.model_dump_json(exclude_none=True) in clerk_call["prompt"]
    assert WRITER.presence is not None
    assert WRITER.presence.model_dump_json(exclude_none=True) in clerk_call["prompt"]

    if provider_type == "anthropic":
        assert writer_call["structured_transport"] == "native"
        assert clerk_call["structured_transport"] == "prompted"
        assert clerk_call["system_prompt"].endswith(skald_clerk_prompt_guide())
    else:
        assert writer_call["structured_transport"] == "responses"
        assert clerk_call["structured_transport"] == "responses"
        assert "=== OUTPUT FORMAT ===" not in clerk_call["system_prompt"]


@pytest.mark.parametrize("provider_type", ["openai", "local", "anthropic"])
def test_sync_two_pass_pipeline_uses_provider_specific_transports(
    provider_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility(provider_type, [WRITER, CLERK])
    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context",
        lambda _context_payload, _schema_model: BASELINE,
    )

    response = utility.generate_narrative(
        _context(),
        effective_context_window=75_000,
    )

    _assert_two_pass_calls(provider, provider_type)
    expected = hydrate_skald_turn(
        combine_two_pass(WRITER, CLERK),
        presence_baseline=BASELINE,
    )
    assert response.model_dump(exclude={"generation_model"}) == expected.model_dump(
        exclude={"generation_model"}
    )
    assert response.generation_model == provider.model


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_type", ["openai", "local", "anthropic"])
async def test_async_two_pass_pipeline_uses_provider_specific_transports(
    provider_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility(provider_type, [WRITER, CLERK])

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

    _assert_two_pass_calls(provider, provider_type)
    expected = hydrate_skald_turn(
        combine_two_pass(WRITER, CLERK),
        presence_baseline=BASELINE,
    )
    assert response.model_dump(exclude={"generation_model"}) == expected.model_dump(
        exclude={"generation_model"}
    )
    assert response.generation_model == provider.model


def test_writer_failure_short_circuits_before_clerk_or_hydration(
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
async def test_clerk_failure_raises_without_partial_hydration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utility, provider = _utility(
        "anthropic",
        [WRITER, RuntimeError("clerk exhausted repairs")],
    )
    hydrated: list[object] = []
    monkeypatch.setattr(
        logon_utility,
        "hydrate_skald_turn",
        lambda *args, **kwargs: hydrated.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="clerk exhausted repairs"):
        await utility.generate_narrative_async(
            _context(),
            effective_context_window=75_000,
        )

    assert [call["schema_model"] for call in provider.calls] == [
        SkaldWriterWire,
        SkaldClerkWire,
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


def test_clerk_prompt_is_concise_and_references_core_doctrine() -> None:
    prompt_path = Path(__file__).parents[2] / "prompts" / "storyteller_clerk.md"
    prompt = prompt_path.read_text()
    normalized_prompt = " ".join(prompt.split())

    assert len(prompt.splitlines()) < 60
    assert "storyteller_core.md" in prompt
    assert "Do not rewrite, continue, summarize, or embellish" in prompt
    assert (
        "`characters`, `places`, `factions`, and `relationships`" in normalized_prompt
    )
