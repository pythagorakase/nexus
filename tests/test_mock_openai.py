"""Tests for the local TEST-mode OpenAI impersonator."""

import json

import pytest

from nexus.agents.logon.apex_schema import StorytellerResponseExtended
from nexus.api.mock_openai import ResponsesRequest, _collect_text, responses_create


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
