"""Tests for Apex response schema helpers."""

import pytest
from pydantic import ValidationError

from nexus.agents.logon.apex_schema import (
    FactionStateUpdate,
    NewPlace,
    OrreryAdjudication,
    PlaceType,
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
    create_minimal_response,
)


def test_bootstrap_response_schema_accepts_directives_but_not_metadata() -> None:
    """Bootstrap responses should include successor directives, not entity metadata."""

    response = StorytellerResponseBootstrap(
        narrative="The story begins.",
        choices=["Step forward.", "Look around."],
        authorial_directives=["Retrieve the starting room and visible companion."],
    )

    assert response.narrative == "The story begins."
    assert response.choices == ["Step forward.", "Look around."]
    assert response.authorial_directives == [
        "Retrieve the starting room and visible companion."
    ]

    with pytest.raises(ValidationError):
        StorytellerResponseBootstrap(
            narrative="The story begins.",
            choices=["Step forward.", "Look around."],
            authorial_directives=["Retrieve the starting room."],
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
    assert response.authorial_directives == [
        "Preserve the immediate scene continuity and unresolved player choice."
    ]


def test_new_place_normalization_does_not_mutate_input_payload() -> None:
    """Place type normalization should not leak mutations to caller data."""

    payload = {"name": "Mirror Tram", "type": "fixed location"}
    original_payload = dict(payload)

    place = NewPlace.model_validate(payload)

    assert payload == original_payload
    assert place.type == PlaceType.FIXED_LOCATION


def test_faction_state_update_accepts_current_activity() -> None:
    """Faction updates can carry the activity field commit handlers persist."""

    update = FactionStateUpdate(
        faction_id=42,
        current_activity="Watching the station exits.",
    )

    assert update.current_activity == "Watching the station exits."


def test_orrery_adjudication_schema_accepts_replace_delta() -> None:
    """Storyteller responses can rule on Orrery proposals without prose parsing."""

    adjudication = OrreryAdjudication(
        proposal_id="sleep_pressure:abc123",
        action="replace",
        replacement_state_delta={
            "character_current_activity": "nodding off mid-sentence",
        },
        replacement_event_type="sleep_need",
    )

    assert adjudication.proposal_id == "sleep_pressure:abc123"
    assert adjudication.replacement_state_delta is not None
    assert (
        adjudication.replacement_state_delta.character_current_activity
        == "nodding off mid-sentence"
    )
    assert adjudication.replacement_event_type == "sleep_need"


def test_extended_response_accepts_partial_new_character_context() -> None:
    """Normal narrative turns may introduce NPCs before all DB fields are known."""

    response = StorytellerResponseExtended(
        narrative="The watcher steps into the pharmacy light.",
        choices=["Ask his name.", "Step back."],
        authorial_directives=[
            "Retrieve Adrian Vale's prior appearances and brass token references."
        ],
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
