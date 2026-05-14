"""Tests for Apex response schema helpers."""

import pytest
from pydantic import ValidationError

from nexus.agents.logon.apex_schema import (
    PlaceType,
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
    create_minimal_response,
)


def test_bootstrap_response_schema_only_accepts_narrative_and_choices() -> None:
    """Bootstrap responses should not request entity metadata."""

    response = StorytellerResponseBootstrap(
        narrative="The story begins.",
        choices=["Step forward.", "Look around."],
    )

    assert response.narrative == "The story begins."
    assert response.choices == ["Step forward.", "Look around."]

    with pytest.raises(ValidationError):
        StorytellerResponseBootstrap(
            narrative="The story begins.",
            choices=["Step forward.", "Look around."],
            referenced_entities={"characters": []},
        )


def test_create_minimal_response_includes_valid_choices() -> None:
    """Minimal fallback responses should satisfy the response schema."""

    response = create_minimal_response("A short narrative beat.")

    assert response.narrative == "A short narrative beat."
    assert response.choices == [
        "Continue.",
        "Wait and observe.",
    ]


def test_extended_response_accepts_partial_new_character_context() -> None:
    """Normal narrative turns may introduce NPCs before all DB fields are known."""

    response = StorytellerResponseExtended(
        narrative="The watcher steps into the pharmacy light.",
        choices=["Ask his name.", "Step back."],
        chunk_metadata={
            "chronology": {
                "episode_transition": "continue",
                "time_delta_minutes": 1,
            },
            "world_layer": "primary",
        },
        referenced_entities={
            "characters": [
                {
                    "new_character": {
                        "name": "Adrian Vale",
                        "appearance": "A raincoated figure with tired eyes.",
                        "background": "An informant with missing records.",
                        "current_location": None,
                        "extra_data": {
                            "role": "Erased intelligence operative",
                            "asset": "A brass token stamped with an angel",
                        },
                    },
                    "reference_type": "present",
                }
            ],
            "places": [
                {
                    "new_place": {
                        "name": "Vey Street Transit Stop",
                        "type": "transit stop",
                        "coordinates": None,
                        "extra_data": {"atmosphere": "uneasy"},
                    },
                    "reference_type": "setting",
                }
            ],
            "factions": [
                {
                    "new_faction": {
                        "name": "The Glass Choir",
                        "ideology": "Control the city by controlling what it remembers.",
                        "history": "Formed after the station fire.",
                        "hidden_agenda": "Recover a witness list before dawn.",
                        "territory": "Transit stops, pharmacies, and late-night diners.",
                        "resources": "Lookouts, dead drops, and radio scanners.",
                        "primary_location": None,
                        "extra_data": {"leader": "unknown"},
                    },
                    "reference_type": "mentioned",
                }
            ],
        },
        state_updates={
            "characters": [],
            "relationships": [],
            "locations": [],
            "factions": [],
        },
    )

    new_character = response.referenced_entities.characters[0].new_character
    assert new_character is not None
    assert new_character.personality is None
    assert new_character.current_location is None
    assert new_character.extra_data.role == "Erased intelligence operative"
    new_place = response.referenced_entities.places[0].new_place
    assert new_place is not None
    assert new_place.type == PlaceType.FIXED_LOCATION
    assert new_place.coordinates is None
    assert new_place.extra_data.category == "transit stop"
    new_faction = response.referenced_entities.factions[0].new_faction
    assert new_faction is not None
    assert new_faction.primary_location is None
