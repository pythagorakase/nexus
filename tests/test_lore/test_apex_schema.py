"""Tests for Apex response schema helpers."""

import pytest
from pydantic import ValidationError

from nexus.agents.logon.apex_enums import WorldLayerType
from nexus.agents.logon.apex_schema import (
    FactionStateUpdate,
    NewFaction,
    NewPlace,
    OrreryAdjudication,
    PlaceType,
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
    create_minimal_response,
)


def test_world_layer_type_uses_atemporal_clock_semantics() -> None:
    """Atemporal replaces the literary-mode dream layer."""

    assert WorldLayerType.ATEMPORAL.value == "atemporal"
    assert not hasattr(WorldLayerType, "DREAM")


def test_bootstrap_response_schema_rejects_legacy_directives_and_metadata() -> None:
    """Bootstrap responses should only include narrative and choices."""

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
            authorial_directives=["Retrieve the starting room."],
        )


def test_generation_model_is_internal_provenance_not_storyteller_output() -> None:
    """The provider stamp stays typed without entering the LLM or API schema."""

    response = StorytellerResponseBootstrap(
        generation_model="gpt-5.6-storyteller",
        narrative="The story begins.",
        choices=["Step forward.", "Look around."],
    )

    assert response.generation_model == "gpt-5.6-storyteller"
    assert "generation_model" not in response.model_dump()
    assert (
        "generation_model"
        not in StorytellerResponseBootstrap.model_json_schema()["properties"]
    )


def test_create_minimal_response_includes_valid_choices() -> None:
    """Minimal fallback responses should satisfy the response schema."""

    response = create_minimal_response("A short narrative beat.")

    assert response.narrative == "A short narrative beat."
    assert response.choices == [
        "Continue.",
        "Wait and observe.",
    ]


def test_new_place_normalization_does_not_mutate_input_payload() -> None:
    """Place type normalization should not leak mutations to caller data."""

    payload = {"name": "Mirror Tram", "type": "fixed location"}
    original_payload = dict(payload)

    place = NewPlace.model_validate(payload)

    assert payload == original_payload
    assert place.type == PlaceType.FIXED_LOCATION


def test_faction_state_update_rejects_legacy_current_activity() -> None:
    """Faction updates should use Orrery tags, not legacy activity columns."""

    with pytest.raises(ValidationError):
        FactionStateUpdate(
            faction_id=42,
            current_activity="Watching the station exits.",
        )


def test_new_faction_schema_excludes_obsolete_legacy_columns() -> None:
    """New faction creation should no longer advertise obsolete table columns."""

    obsolete_fields = {
        "ideology",
        "history",
        "current_activity",
        "hidden_agenda",
        "territory",
        "power_level",
        "resources",
    }

    assert obsolete_fields.isdisjoint(NewFaction.model_fields)
    assert {"name", "summary", "primary_location", "extra_data", "orrery_tags"} <= set(
        NewFaction.model_fields
    )

    with pytest.raises(ValidationError):
        NewFaction(name="The Glass Choir", ideology="memory control")


def test_orrery_adjudication_schema_accepts_replace_delta() -> None:
    """Storyteller responses can rule on Orrery proposals without prose parsing."""

    adjudication = OrreryAdjudication(
        proposal_id="sleep_pressure:abc123",
        action="replace",
        replacement_state_delta={
            "character_current_activity": "nodding off mid-sentence",
            "entity_pair_tags_target_clear_inbound": ["hunting"],
        },
        replacement_event_type="sleep_need",
    )

    assert adjudication.proposal_id == "sleep_pressure:abc123"
    assert adjudication.replacement_state_delta is not None
    assert (
        adjudication.replacement_state_delta.character_current_activity
        == "nodding off mid-sentence"
    )
    assert (
        adjudication.replacement_state_delta.entity_pair_tags_target_clear_inbound
        == ["hunting"]
    )
    assert adjudication.replacement_event_type == "sleep_need"


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
                        "summary": "A memory-control conspiracy around transit stops.",
                        "primary_location": None,
                        "extra_data": {"leader": "unknown"},
                        "orrery_tags": {
                            "applied_tags": ["covert", "information"],
                            "tags_to_clear": [],
                        },
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
