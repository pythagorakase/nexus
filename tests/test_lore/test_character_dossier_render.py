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
        "current_location": 1,
        "current_location_name": "Hall",
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
        "current_location": 2,
        "current_location_name": "Garden",
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


@pytest.mark.parametrize("seat", ["writer", "gaia"])
@pytest.mark.parametrize("limit", [1, 8, 12])
def test_character_dossier_tag_cap_preserves_order(seat: str, limit: int) -> None:
    """Configured caps apply to both tiers without changing source attribution."""
    from nexus.config import load_settings_as_dict

    settings = load_settings_as_dict()
    settings["lore"]["render_limits"]["character_tags"] = limit
    utility = window_logon(settings)
    tags = [f"capacity:tag_{index:02}" for index in range(10)]
    character = {"name": "Iona", "orrery_tag_summary": ", ".join(tags)}
    prompt = utility._format_context_prompt(
        {
            "entity_data": {
                "characters": {"baseline": [character], "featured": [character]}
            }
        },
        seat=seat,
    )
    assert prompt.count("Tags: " + ", ".join(tags[:limit]) + "\n") == 2
    for tag in tags[limit:]:
        assert tag not in prompt
    assert character["orrery_tag_summary"] == ", ".join(tags)


def test_character_tag_limit_validation() -> None:
    """The shared typed render limit defaults to eight and rejects zero."""
    from pydantic import ValidationError

    from nexus.config.settings_models import RenderLimits

    limits = dict(relationships=5, events=5, threats=5, bleed_menu=5)
    assert RenderLimits(**limits).character_tags == 8
    with pytest.raises(ValidationError):
        RenderLimits(**limits, character_tags=0)


@pytest.mark.parametrize("seat", ["writer", "gaia"])
def test_dossier_omits_unknown_location_and_formats_decimal_valence(seat: str) -> None:
    """Real TEST rendering omits absent places and rounds database decimals."""
    from decimal import Decimal

    utility = window_logon()
    prompt = utility._format_context_prompt(
        {
            "entity_data": {
                "characters": {
                    "baseline": [
                        {
                            "name": "Hale",
                            "current_location": None,
                            "current_location_name": None,
                            "current_activity": "Waiting.",
                        },
                    ]
                },
                "relationships": [
                    {
                        "character1_name": "Hale",
                        "character2_name": "Iona",
                        "relationship_type": "complex",
                        "valence_current": Decimal(value),
                    }
                    for value in ("0E-20", "-0.18181818181818181818", "0.125")
                ],
            }
        },
        seat=seat,
    )
    assert "- Hale: Waiting." in prompt
    assert "at None" not in prompt
    for value in ("+0.00", "-0.18", "+0.12"):
        assert f"- Hale → Iona: complex (valence {value})" in prompt
