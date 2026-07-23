"""Tests for adapting LOGON responses into incubator payloads."""

from nexus.agents.logon.apex_schema import (
    ReferencedEntities,
    StorytellerResponseExtended,
)
from nexus.api.lore_adapter import response_to_incubator


def test_response_to_incubator_serializes_current_reference_schema() -> None:
    """Current LOGON references should survive incubator conversion."""

    response = StorytellerResponseExtended(
        generation_model="gpt-5.6-storyteller",
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
                {"character_name": "Jonas Vale", "reference_type": "present"},
            ],
            "places": [
                {
                    "place_name": "Kettering Street Transit Stop",
                    "reference_type": "setting",
                }
            ],
            "factions": [
                {
                    "faction_name": "Project Palimpsest",
                    "reference_type": "mentioned",
                }
            ],
        },
        new_entities=[
            {
                "kind": "character",
                "name": "Jonas Vale",
                "summary": "A raincoated man with a milky prosthetic eye.",
            },
            {
                "kind": "place",
                "name": "Kettering Street Transit Stop",
                "summary": "A rain-slick transit stop across from the pharmacy.",
            },
            {
                "kind": "faction",
                "name": "Project Palimpsest",
                "summary": "A covert continuity office.",
            },
        ],
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
    assert incubator["generation_model"] == "gpt-5.6-storyteller"
    assert "authorial_directives" not in incubator
    reference_updates = incubator["reference_updates"]
    assert reference_updates["characters"][0]["character_name"] == "Eleanor Voss"
    assert reference_updates["characters"][1]["character_name"] == "Jonas Vale"
    assert reference_updates["places"][0]["place_name"] == (
        "Kettering Street Transit Stop"
    )
    assert reference_updates["factions"][0]["faction_name"] == "Project Palimpsest"
    assert [item["name"] for item in incubator["new_entities"]] == [
        "Jonas Vale",
        "Kettering Street Transit Stop",
        "Project Palimpsest",
    ]

    # The commit path reparses this JSONB payload into the current schema.
    reparsed = ReferencedEntities(**reference_updates)
    assert reparsed.characters[1].character_name == "Jonas Vale"


def test_response_to_incubator_threads_generation_model_verbatim() -> None:
    """The adapter threads provenance without validating it.

    Validation lives only at the boundaries (the LOGON stamp and
    write_to_incubator); the adapter passes the stamp through, or None for
    responses that never had one — the DB boundary rejects those downstream.
    """

    response = StorytellerResponseExtended(
        narrative="The unmarked door opens.",
        choices=["Enter.", "Wait."],
        chunk_metadata={
            "chronology": {
                "episode_transition": "continue",
                "time_delta_minutes": 1,
            },
            "world_layer": "primary",
        },
        referenced_entities={"characters": [], "places": [], "factions": []},
        state_updates={
            "characters": [],
            "relationships": [],
            "locations": [],
            "factions": [],
        },
    )

    unstamped = response_to_incubator(
        response=response,
        parent_chunk_id=1,
        user_text="Continue.",
        session_id="session-missing-model",
    )
    assert unstamped["generation_model"] is None

    response.generation_model = "gpt-5.6-terra"
    stamped = response_to_incubator(
        response=response,
        parent_chunk_id=1,
        user_text="Continue.",
        session_id="session-stamped-model",
    )
    assert stamped["generation_model"] == "gpt-5.6-terra"
