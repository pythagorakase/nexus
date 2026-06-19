"""Tests for adapting LOGON responses into incubator payloads."""

from nexus.agents.logon.apex_schema import (
    ReferencedEntities,
    StorytellerResponseExtended,
)
from nexus.api.lore_adapter import response_to_incubator


def test_response_to_incubator_serializes_current_reference_schema() -> None:
    """Current LOGON references should survive incubator conversion."""

    response = StorytellerResponseExtended(
        narrative="Jonas waits beneath the pharmacy sign.",
        choices=["Follow Jonas.", "Answer the phone."],
        chunk_metadata={
            "chronology": {
                "episode_transition": "continue",
                "time_delta_minutes": 1,
            },
            "world_layer": "primary",
        },
        referenced_entities={
            "characters": [
                {"character_name": "Eleanor Voss", "reference_type": "present"},
                {
                    "new_character": {
                        "name": "Jonas Vale",
                        "appearance": "A raincoated man with a milky prosthetic eye.",
                    },
                    "reference_type": "present",
                },
            ],
            "places": [
                {
                    "new_place": {
                        "name": "Kettering Street Transit Stop",
                        "type": "transit stop",
                    },
                    "reference_type": "setting",
                }
            ],
            "factions": [
                {
                    "new_faction": {"name": "Project Palimpsest"},
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

    incubator = response_to_incubator(
        response=response,
        parent_chunk_id=1,
        user_text="I cross the street.",
        session_id="session-1",
    )

    assert incubator["metadata_updates"]["chronology"]["time_delta_minutes"] == 1
    assert "authorial_directives" not in incubator
    reference_updates = incubator["reference_updates"]
    assert reference_updates["characters"][0]["character_name"] == "Eleanor Voss"
    assert reference_updates["characters"][1]["new_character"]["name"] == "Jonas Vale"
    assert reference_updates["places"][0]["new_place"]["type"] == "fixed_location"
    assert (
        reference_updates["places"][0]["new_place"]["extra_data"]["category"]
        == "transit stop"
    )
    assert (
        reference_updates["factions"][0]["new_faction"]["name"] == "Project Palimpsest"
    )

    # The commit path reparses this JSONB payload into the current schema.
    reparsed = ReferencedEntities(**reference_updates)
    assert reparsed.characters[1].new_character.name == "Jonas Vale"
