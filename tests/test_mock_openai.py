"""Tests for the local TEST-mode OpenAI impersonator."""

import json

import pytest

from nexus.agents.logon.apex_schema import StorytellerResponseExtended
from nexus.api.mock_openai import ResponsesRequest, responses_create


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
    assert replacement.replacement_state_delta is not None
    assert (
        replacement.replacement_state_delta.character_current_activity
        == "following the mock-server replacement beat"
    )


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
