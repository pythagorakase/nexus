"""Tests for Apex response schema helpers."""

import pytest
from pydantic import ValidationError

from nexus.agents.logon.apex_enums import WorldLayerType
from nexus.agents.logon.apex_schema import (
    CharacterReference,
    FactionReference,
    FactionStateUpdate,
    OrreryAdjudication,
    PlaceReference,
    PlaceReferenceType,
    StorytellerResponseBootstrap,
    create_minimal_response,
)
from nexus.api.storyteller import _coerce_story_response


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
        StorytellerResponseBootstrap.model_validate(
            {
                "narrative": "The story begins.",
                "choices": ["Step forward.", "Look around."],
                "authorial_directives": ["Retrieve the starting room."],
            }
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


def test_faction_state_update_rejects_legacy_current_activity() -> None:
    """Faction updates should use Orrery tags, not legacy activity columns."""

    with pytest.raises(ValidationError):
        FactionStateUpdate.model_validate(
            {
                "faction_id": 42,
                "current_activity": "Watching the station exits.",
            }
        )


def test_orrery_adjudication_schema_accepts_replace_delta() -> None:
    """Storyteller responses can rule on Orrery proposals without prose parsing."""

    adjudication = OrreryAdjudication.model_validate(
        {
            "proposal_id": "sleep_pressure:abc123",
            "action": "replace",
            "replacement_state_delta": {
                "character_current_activity": "nodding off mid-sentence",
                "entity_pair_tags_target_clear_inbound": ["hunting"],
            },
            "replacement_event_type": "sleep_need",
        }
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


@pytest.mark.parametrize(
    ("reference_model", "payload"),
    [
        (CharacterReference, {}),
        (PlaceReference, {"reference_type": PlaceReferenceType.SETTING}),
        (FactionReference, {}),
    ],
)
def test_entity_references_require_id_or_name(reference_model, payload) -> None:
    """Reference objects cannot stand in for new-entity declarations."""

    with pytest.raises(ValidationError, match="Must provide either"):
        reference_model(**payload)


@pytest.mark.parametrize(
    ("collection", "name_field", "legacy_field"),
    [
        ("characters", "character_name", "new_character"),
        ("places", "place_name", "new_place"),
        ("factions", "faction_name", "new_faction"),
    ],
)
def test_api_coercion_rejects_legacy_inline_dossiers_in_extended_payloads(
    collection: str,
    name_field: str,
    legacy_field: str,
) -> None:
    """Full legacy responses raise instead of silently degrading to Minimal."""

    referenced_entities: dict[str, list[dict[str, object]]] = {
        "characters": [],
        "places": [],
        "factions": [],
    }
    reference: dict[str, object] = {
        name_field: "Legacy Inline Entity",
        legacy_field: {"name": "Legacy Inline Entity"},
    }
    if collection == "places":
        reference["reference_type"] = "setting"
    referenced_entities[collection] = [reference]

    with pytest.raises(ValidationError):
        _coerce_story_response(
            {
                "narrative": "A legacy entity steps into view.",
                "choices": ["Continue.", "Wait."],
                "chunk_metadata": {},
                "referenced_entities": referenced_entities,
                "state_updates": {},
                "operations": {},
                "orrery_adjudications": [],
                "new_entities": [],
                "reasoning": "The inline dossier should be rejected.",
            }
        )
