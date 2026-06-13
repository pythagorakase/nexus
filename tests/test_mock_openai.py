"""Tests for the local TEST-mode OpenAI impersonator."""

import json

import pytest

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
)
from nexus.api.mock_openai import (
    ResponsesRequest,
    _collect_text,
    _requested_output_properties,
    responses_create,
)


def _final_result_tool(schema_model) -> dict:
    """Build the pydantic_ai-style output tool for a Storyteller schema."""
    return {
        "name": "final_result",
        "type": "function",
        "parameters": schema_model.model_json_schema(),
        "strict": True,
    }


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
    parsed = StorytellerResponseExtended.model_validate(payload)

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
    parsed = StorytellerResponseExtended.model_validate(payload)

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
    """A turn request with no Orrery section still gets an Extended payload.

    Regression for the issue #401 reproduction blocker: keyword routing sent
    proposal-free turn requests to the bootstrap-shaped payload, which fails
    StorytellerResponseExtended validation and stalls TEST-mode turn loops.
    """

    response = await responses_create(
        ResponsesRequest(
            model="TEST",
            input=[{"role": "user", "content": "Continue the protagonist story."}],
            tools=[_final_result_tool(StorytellerResponseExtended)],
        )
    )

    payload = json.loads(response["output_text"])
    parsed = StorytellerResponseExtended.model_validate(payload)
    assert parsed.narrative.startswith("[TEST MODE]")
    assert parsed.orrery_adjudications == []


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
    assert "state_updates" not in fields

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
