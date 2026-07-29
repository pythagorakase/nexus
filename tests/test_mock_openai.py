"""Tests for the local TEST-mode OpenAI impersonator."""

import json

import pytest

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
)
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    SkaldTurnWire,
    SkaldWriterWire,
)
from nexus.api.mock_openai import (
    ChatCompletionRequest,
    ResponsesRequest,
    _collect_text,
    _mock_gaia_response,
    _mock_storyteller_response,
    _mock_writer_response,
    _requested_output_properties,
    chat_completions,
    responses_create,
)
from nexus.api.native_structured_output import openai_response_text_format


def _final_result_tool(schema_model) -> dict:
    """Build the pydantic_ai-style output tool for a Storyteller schema."""
    return {
        "name": "final_result",
        "type": "function",
        "parameters": schema_model.model_json_schema(),
        "strict": True,
    }


def _native_text_format(schema_model) -> dict:
    """Build the OpenAI native Responses text.format payload."""

    return {"format": openai_response_text_format(schema_model)}


def test_mock_non_bootstrap_payload_is_sparse_skald_wire() -> None:
    """TEST turns track the provider wire and exercise optional omissions."""

    payload = _mock_storyteller_response("")

    wire = SkaldTurnWire.model_validate(payload)

    assert set(payload) == {"narrative", "choices", "letter"}
    assert wire.updates is None
    assert wire.model_dump(exclude_unset=True, mode="json") == payload


@pytest.mark.asyncio
async def test_mock_chat_completion_does_not_log_private_prompt(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even the TEST transport must not emit correspondence at INFO or below."""

    secret = "PRIVATE-CONSPIRACY-LETTER-617"
    monkeypatch.setattr(
        "nexus.api.mock_openai.get_cached_phase_response",
        lambda _phase, _subphase: {"data": {}},
    )
    with caplog.at_level("DEBUG", logger="nexus.api.mock_openai"):
        await chat_completions(
            ChatCompletionRequest(
                model="TEST",
                messages=[{"role": "user", "content": secret}],
            )
        )

    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_mock_responses_returns_orrery_adjudication_fixture() -> None:
    """TEST mode can force defer, void, and replace without live API calls."""

    prompt = """
=== ORRERY IMMINENT ACTIVITY ===
- drink:aaa [Drink routinely]: state_delta={'character.current_activity': 'drinking'}
- hide:bbb [Go dark]: state_delta={'character.current_activity': 'hiding'}
- tend_craft:ccc [Tend craft]: state_delta={'character.current_activity': 'tending'}
- evade_pursuers:ddd [Evade]: state_delta={'character.current_activity': 'moving'}
"""

    response = await responses_create(
        ResponsesRequest(model="TEST", input=[{"role": "user", "content": prompt}])
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldTurnWire.model_validate(payload)

    assert [item.action for item in parsed.orrery_adjudications] == [
        "defer",
        "void",
        "replace",
    ]
    assert parsed.orrery_adjudications[0].proposal_id == "drink:aaa"
    assert parsed.orrery_adjudications[1].proposal_id == "hide:bbb"
    replacement = parsed.orrery_adjudications[2]
    assert replacement.proposal_id == "tend_craft:ccc"
    assert replacement.replacement_event_type == "mock_replacement"
    assert replacement.replacement_state_delta is not None
    assert (
        replacement.replacement_state_delta.character_current_activity
        == "following the mock-server replacement beat"
    )


@pytest.mark.asyncio
async def test_mock_responses_single_orrery_proposal_only_defers() -> None:
    """A one-proposal prompt returns a schema-valid partial adjudication list."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[
                {
                    "role": "user",
                    "content": (
                        "=== ORRERY IMMINENT ACTIVITY ===\n"
                        "- sleep_pressure:aaa [Doze off]: "
                        "state_delta={'character.current_activity': 'sleeping'}"
                    ),
                }
            ],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldTurnWire.model_validate(payload)

    assert [item.action for item in parsed.orrery_adjudications] == ["defer"]
    assert parsed.orrery_adjudications[0].proposal_id == "sleep_pressure:aaa"


@pytest.mark.asyncio
async def test_mock_responses_parses_nested_responses_input_content() -> None:
    """Pydantic AI style nested content still exposes Orrery proposal IDs."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Story turn"},
                        {
                            "type": "input_text",
                            "text": '- "proposal_id": "drink:aaa"',
                        },
                    ],
                }
            ],
        )
    )

    payload = json.loads(response["output_text"])
    assert payload["orrery_adjudications"][0]["proposal_id"] == "drink:aaa"


@pytest.mark.asyncio
async def test_mock_responses_prioritizes_orrery_fixture_over_cached_story() -> None:
    """Orrery proposal prompts use the adjudication fixture even if narrative-like."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[
                {
                    "role": "user",
                    "content": (
                        "Continue the protagonist story.\n"
                        "=== ORRERY IMMINENT ACTIVITY ===\n"
                        "- honor_debt:aaa [Repay debt]: state_delta={}"
                    ),
                }
            ],
        )
    )

    payload = json.loads(response["output_text"])
    assert payload["narrative"].startswith("[TEST MODE]")
    assert payload["orrery_adjudications"][0]["proposal_id"] == "honor_debt:aaa"


@pytest.mark.asyncio
async def test_mock_responses_routes_turn_schema_without_orrery_proposals() -> None:
    """A turn request with no Orrery section still gets a wire payload.

    Regression for the issue #401 reproduction blocker: keyword routing sent
    proposal-free turn requests to the bootstrap-shaped payload, which fails
    turn-wire validation and stalls TEST-mode turn loops.
    """

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            tools=[_final_result_tool(SkaldTurnWire)],
        )
    )

    tool_call = response["output"][0]
    assert tool_call["type"] == "function_call"
    assert tool_call["name"] == "final_result"

    payload = json.loads(response["output_text"])
    assert json.loads(tool_call["arguments"]) == payload
    parsed = SkaldTurnWire.model_validate(payload)
    assert parsed.narrative.startswith("[TEST MODE]")
    assert parsed.updates is None
    assert parsed.orrery_adjudications == []


@pytest.mark.asyncio
async def test_mock_responses_routes_turn_schema_as_native_text_format() -> None:
    """Native OpenAI strict schemas should route without a final_result tool."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            text=_native_text_format(SkaldTurnWire),
        )
    )

    message = response["output"][0]
    assert message["type"] == "message"

    payload = json.loads(response["output_text"])
    parsed = SkaldTurnWire.model_validate(payload)
    assert parsed.narrative.startswith("[TEST MODE]")
    assert parsed.updates is None
    assert parsed.orrery_adjudications == []


_ORRERY_PROMPT = """
=== ORRERY IMMINENT ACTIVITY ===
- drink:aaa [Drink routinely]: state_delta={'character.current_activity': 'x'}
"""


def test_mock_two_pass_projections_partition_the_full_fixture() -> None:
    """Every full-fixture key lands in exactly one pass (extra=forbid guard)."""

    full = _mock_storyteller_response(_ORRERY_PROMPT)
    writer = _mock_writer_response(_ORRERY_PROMPT)
    gaia = _mock_gaia_response(_ORRERY_PROMPT)

    SkaldWriterWire.model_validate(writer)
    SkaldGaiaWire.model_validate(gaia)
    assert set(writer) | set(gaia) == set(full)
    assert set(writer) & set(gaia) == {"letter"}


@pytest.mark.asyncio
async def test_mock_responses_routes_writer_schema_to_writer_projection() -> None:
    """The two-pass writer request must not receive bootstrap or gaia fields.

    Regression for the PR #579 Codex P1: before signature routing, a writer
    schema (no updates property) fell through to the cached bootstrap payload.
    """

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            tools=[_final_result_tool(SkaldWriterWire)],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldWriterWire.model_validate(payload)
    assert parsed.narrative.startswith("[TEST MODE]")
    assert "updates" not in payload


@pytest.mark.asyncio
async def test_mock_responses_routes_gaia_schema_to_gaia_projection() -> None:
    """The two-pass gaia request must not receive narrative/choices extras.

    Regression for the PR #579 Codex P1: the gaia schema contains the updates
    property, so the old routing returned the FULL turn payload, whose
    narrative/choices are forbidden extras under SkaldGaiaWire.
    """

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": _ORRERY_PROMPT}],
            tools=[_final_result_tool(SkaldGaiaWire)],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldGaiaWire.model_validate(payload)
    assert "narrative" not in payload
    assert [item.action for item in parsed.orrery_adjudications] == ["defer"]


@pytest.mark.asyncio
async def test_mock_responses_gaia_schema_without_proposals_is_empty() -> None:
    """A proposal-free gaia request returns a valid all-defaults payload."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            tools=[_final_result_tool(SkaldGaiaWire)],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = SkaldGaiaWire.model_validate(payload)
    assert set(payload) == {"letter"}
    assert payload["letter"]
    assert parsed.updates is None
    assert parsed.orrery_adjudications == []


@pytest.mark.asyncio
@pytest.mark.requires_postgres
async def test_mock_responses_routes_bootstrap_schema_as_final_result_tool() -> None:
    """Bootstrap structured output must also call the required output tool."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Bootstrap the protagonist story."}],
            tools=[_final_result_tool(StorytellerResponseBootstrap)],
        )
    )

    tool_call = response["output"][0]
    assert tool_call["type"] == "function_call"
    assert tool_call["name"] == "final_result"
    payload = json.loads(tool_call["arguments"])
    StorytellerResponseBootstrap.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.requires_postgres
async def test_mock_responses_routes_bootstrap_schema_as_native_text_format() -> None:
    """Bootstrap native structured output should return message JSON."""

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Bootstrap the protagonist story."}],
            text=_native_text_format(StorytellerResponseBootstrap),
        )
    )

    message = response["output"][0]
    assert message["type"] == "message"
    StorytellerResponseBootstrap.model_validate_json(response["output_text"])


def test_requested_output_properties_extracts_schema_fields() -> None:
    """The output-tool discriminator sees the schema's top-level properties."""

    request = ResponsesRequest(
        model="TEST",
        input=[],
        tools=[_final_result_tool(StorytellerResponseBootstrap)],
    )
    fields = _requested_output_properties(request)
    assert "narrative" in fields
    assert "choices" in fields
    assert "updates" not in fields

    native_request = ResponsesRequest(
        model="TEST",
        input=[],
        text=_native_text_format(SkaldTurnWire),
    )
    native_fields = _requested_output_properties(native_request)
    assert "updates" in native_fields
    assert "presence" in native_fields

    bare = ResponsesRequest(model="TEST", input=[])
    assert _requested_output_properties(bare) == set()


def test_collect_text_uses_first_prompt_like_key() -> None:
    """Sibling text fields do not duplicate or alter higher-priority content."""

    assert (
        _collect_text(
            {
                "content": "canonical prompt with drink:aaa",
                "text": "ignored sibling with hide:bbb",
            }
        )
        == "canonical prompt with drink:aaa"
    )
