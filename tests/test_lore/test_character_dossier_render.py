"""Attributed character tags through the real writer and Gaia renderer."""

import pytest

from tests.test_lore.window_helpers import window_logon


@pytest.mark.parametrize("seat", ["writer", "gaia"])
def test_character_dossier_tags_preserve_featured_details(seat: str) -> None:
    """Both seats retain status/prose and match faction tag punctuation."""
    utility = window_logon()
    tags = "capacity:perceptive, disposition:cautious"
    tagged = {
        "id": 7,
        "name": "Iona",
        "current_location": "Hall",
        "current_activity": "Waiting.",
        "summary": "A patient observer.",
        "personality": "Deliberate.",
        "emotional_state": "Uneasy.",
        "reference_type": "present",
        "orrery_tag_summary": tags,
    }
    untagged = {
        "id": 9,
        "name": "Ren",
        "current_location": "Garden",
        "current_activity": "Reading.",
        "orrery_tag_summary": "",
    }
    prompt = utility._format_context_prompt(
        {
            "user_input": "Continue.",
            "entity_data": {
                "characters": {"baseline": [tagged, untagged], "featured": [tagged]},
                "factions": {
                    "baseline": [{"name": "Guild", "orrery_tag_summary": tags}],
                    "featured": [
                        {
                            "name": "Guild",
                            "summary": "A guild.",
                            "orrery_tag_summary": tags,
                        }
                    ],
                },
            },
        },
        seat=seat,
    )
    assert f"- Iona: at Hall, Waiting. Tags: {tags}" in prompt
    assert f"- Iona [present]: A patient observer. Tags: {tags}" in prompt
    assert "  Personality: Deliberate.\n  Emotional State: Uneasy." in prompt
    assert "- Ren: at Garden, Reading.\n" in prompt
    assert f"- Guild: {tags}" in prompt
    assert f"- Guild: A guild. Tags: {tags}" in prompt
