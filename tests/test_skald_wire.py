"""Tests for the sparse Skald semantic-delta wire boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast, get_args

import psycopg2
import pytest
import tiktoken
from pydantic import BaseModel, ValidationError

from nexus.agents.logon.apex_enums import (
    EmotionalValence,
    PlaceReferenceType,
    ReferenceType,
    RelationshipType,
    WorldLayerType,
)
from nexus.agents.logon.apex_schema import (
    CharacterReference,
    CharacterStateUpdate,
    ChronologyUpdate,
    ChunkMetadataUpdate,
    Coordinates,
    FactionReference,
    FactionStanceChange,
    FactionStateUpdate,
    LocationStateUpdate,
    NamedObservation,
    NewEntityPairTagHint,
    OrreryAdjudication,
    PlaceReference,
    ReferencedEntities,
    RelationshipUpdate,
    StateUpdates,
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
)
from nexus.agents.logon.skald_wire import (
    PresenceBaseline,
    PresenceRef,
    SkaldTurnWire,
    hydrate_skald_turn,
    skald_wire_lenient_schema,
    skald_wire_strict_text_format,
)
from nexus.agents.lore import logon_utility
from nexus.agents.lore.logon_utility import LogonUtility, read_presence_baseline
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.api.native_structured_output import anthropic_output_config
from scripts.api_openai import OpenAIProvider


# Filled from the deterministic compact serializations, with modest drift room.
SKALD_WIRE_STRICT_MAX_BYTES = 19_600
SKALD_WIRE_LENIENT_MAX_BYTES = 18_950
SKALD_WIRE_DESCRIPTION_MAX_CHARS = 70

DECLARED_ENTITY_ROLE_DESCRIPTION = (
    "Whether the declared entity is the subject or object of the directed pair tag."
)
REPLACEMENT_EVENT_TYPE_DESCRIPTION = (
    "Optional registered event type for a replacement_state_delta. "
    "Leave unset unless the replacement should emit a canonical world_event."
)
COORDINATES_DESCRIPTION = (
    "Earth-based lat/lon coordinates.\n\n"
    "All worlds in NEXUS share Earth's physical geography—same size, same\n"
    "continental shapes, same coastlines. Choose coordinates that make sense\n"
    "for the location's described characteristics (climate, terrain, proximity\n"
    "to water)."
)

WIRE_DESCRIPTION_SURVIVORS = {
    "NewEntityPairTagHint.declared_entity_role": DECLARED_ENTITY_ROLE_DESCRIPTION,
    "OrreryAdjudication.replacement_event_type": REPLACEMENT_EVENT_TYPE_DESCRIPTION,
}

SPARSE_WIRE_PAYLOAD = {
    "narrative": "Rain beads on the sealed archive door.",
    "choices": ["Knock twice.", "Wait beneath the awning."],
}

BASELINE = PresenceBaseline(
    present=[
        PresenceRef(kind="character", name="Brena Tideloft", id=7),
        PresenceRef(kind="character", name="Odile", id=8),
    ],
    setting=PresenceRef(kind="place", name="The Lower Sluice", id=41),
)

RICH_WIRE_PAYLOAD: dict[str, Any] = {
    "narrative": "Brena follows the bell-sound through the flooded stacks.",
    "choices": [
        "Follow the footprints into the archive.",
        "Call for Odile before proceeding.",
    ],
    "scene": {
        "elapsed_minutes": 1505,
        "transition": "new_episode",
        "world_layer": "flashback",
        "weather": "rain",
    },
    "presence": {
        "enter": [{"kind": "character", "name": "Marra Kest", "id": 9}],
        "exit": [{"kind": "character", "name": "Odile", "id": 8}],
        "mentions": [
            {"kind": "character", "name": "Joryn Peale", "id": 10},
            {"kind": "place", "name": "The Bell Archive", "id": 42},
            {"kind": "faction", "name": "The Sluice Guild", "id": 12},
        ],
        "transit": [{"kind": "place", "name": "The East Lock", "id": 43}],
    },
    "updates": [
        {
            "kind": "character",
            "name": "Brena Tideloft",
            "id": 7,
            "activity": "tracking the drowned clerk",
            "location": 41,
            "emotional_state": "alert but composed",
            "observations": [{"key": "clue", "value": "heard the drowned bell"}],
            "tags_add": ["perceptive", "alert"],
            "tags_clear": ["resting"],
        },
        {
            "kind": "place",
            "name": "The Lower Sluice",
            "id": 41,
            "condition": "Floodwater rising between the stacks.",
            "notable_change": "The archive bell is ringing underwater.",
            "tags_add": ["hazardous"],
            "tags_clear": ["sheltered"],
        },
        {
            "kind": "faction",
            "name": "The Sluice Guild",
            "id": 12,
            "action": "Sealed the eastern lock.",
            "stance_toward": "Brena Tideloft",
            "stance": "watchful cooperation",
            "tags_add": ["mobilized"],
            "tags_clear": ["dormant"],
        },
        {
            "kind": "relationship",
            "name": "Brena Tideloft",
            "other_name": "Odile",
            "id": 7,
            "other_id": 8,
            "type": "ally",
            "valence": "+2|friendly",
            "dynamic": "Trust sharpened by shared danger.",
            "recent_events": "Odile stayed behind at the eastern lock.",
        },
    ],
    "operations": {
        "request_summary": {
            "summary_type": "episode",
            "reason": "The sluice investigation crossed an episode boundary.",
        }
    },
    "orrery_adjudications": [
        {
            "proposal_id": "sleep_pressure:brena",
            "action": "replace",
            "note": "The immediate danger keeps Brena alert.",
            "replacement_state_delta": {
                "character_current_activity": "tracking the drowned clerk",
                "entity_tags_add": ["alert"],
            },
            "replacement_event_type": "evade_pursuit",
        }
    ],
    "new_entities": [
        {
            "kind": "place",
            "name": "The Bell Archive",
            "summary": "A submerged registry beneath the Lower Sluice.",
            "coordinates": {"lat": 41.8781, "lon": -87.6298},
            "tag_hints": ["haven"],
            "pair_tag_hints": [
                {
                    "tag": "protects",
                    "other_entity_name": "The Lower Sluice",
                    "declared_entity_role": "object",
                }
            ],
        }
    ],
}


def _assert_canonical_fields_equal(
    actual: StorytellerResponseExtended,
    expected: StorytellerResponseExtended,
) -> None:
    """Assert every canonical field individually, including internal fields."""

    for field_name in StorytellerResponseExtended.model_fields:
        assert getattr(actual, field_name) == getattr(expected, field_name)


def _rich_canonical_expectation(wire: SkaldTurnWire) -> StorytellerResponseExtended:
    """Build the hand-authored canonical expectation for the rich fixture."""

    return StorytellerResponseExtended(
        narrative=wire.narrative,
        choices=wire.choices,
        chunk_metadata=ChunkMetadataUpdate(
            chronology=ChronologyUpdate(
                episode_transition="new_episode",
                time_delta_minutes=5,
                time_delta_hours=1,
                time_delta_days=1,
                time_delta_description=None,
            ),
            world_layer=WorldLayerType.FLASHBACK,
            scene_weather="rain",
        ),
        referenced_entities=ReferencedEntities(
            characters=[
                CharacterReference(
                    character_id=7,
                    character_name="Brena Tideloft",
                    reference_type=ReferenceType.PRESENT,
                ),
                CharacterReference(
                    character_id=9,
                    character_name="Marra Kest",
                    reference_type=ReferenceType.PRESENT,
                ),
                CharacterReference(
                    character_id=10,
                    character_name="Joryn Peale",
                    reference_type=ReferenceType.MENTIONED,
                ),
            ],
            places=[
                PlaceReference(
                    place_id=41,
                    place_name="The Lower Sluice",
                    reference_type=PlaceReferenceType.SETTING,
                ),
                PlaceReference(
                    place_id=43,
                    place_name="The East Lock",
                    reference_type=PlaceReferenceType.TRANSIT,
                ),
                PlaceReference(
                    place_id=42,
                    place_name="The Bell Archive",
                    reference_type=PlaceReferenceType.MENTIONED,
                ),
            ],
            factions=[
                FactionReference(
                    faction_id=12,
                    faction_name="The Sluice Guild",
                    reference_type=ReferenceType.MENTIONED,
                )
            ],
        ),
        state_updates=StateUpdates(
            characters=[
                CharacterStateUpdate(
                    character_id=7,
                    character_name="Brena Tideloft",
                    current_location=41,
                    current_activity="tracking the drowned clerk",
                    emotional_state="alert but composed",
                    extra_observations=[
                        NamedObservation(
                            key="clue",
                            value="heard the drowned bell",
                        )
                    ],
                    orrery_tags=OrreryTagBestowal(
                        applied_tags=["perceptive", "alert"],
                        tags_to_clear=["resting"],
                    ),
                )
            ],
            locations=[
                LocationStateUpdate(
                    place_id=41,
                    place_name="The Lower Sluice",
                    current_conditions="Floodwater rising between the stacks.",
                    notable_changes=["The archive bell is ringing underwater."],
                    orrery_tags=OrreryTagBestowal(
                        applied_tags=["hazardous"],
                        tags_to_clear=["sheltered"],
                    ),
                )
            ],
            factions=[
                FactionStateUpdate(
                    faction_id=12,
                    faction_name="The Sluice Guild",
                    recent_actions=["Sealed the eastern lock."],
                    stance_changes=[
                        FactionStanceChange(
                            target="Brena Tideloft",
                            stance="watchful cooperation",
                        )
                    ],
                    orrery_tags=OrreryTagBestowal(
                        applied_tags=["mobilized"],
                        tags_to_clear=["dormant"],
                    ),
                )
            ],
            relationships=[
                RelationshipUpdate(
                    character1_id=7,
                    character1_name="Brena Tideloft",
                    character2_id=8,
                    character2_name="Odile",
                    relationship_type=RelationshipType.ALLY,
                    emotional_valence=EmotionalValence.FRIENDLY,
                    dynamic="Trust sharpened by shared danger.",
                    recent_events="Odile stayed behind at the eastern lock.",
                )
            ],
        ),
        operations=wire.operations,
        orrery_adjudications=wire.orrery_adjudications,
        new_entities=wire.new_entities,
        reasoning=None,
    )


def test_rich_wire_hydrates_every_block_field_by_field() -> None:
    wire = SkaldTurnWire.model_validate(RICH_WIRE_PAYLOAD)
    actual = hydrate_skald_turn(wire, presence_baseline=BASELINE)
    _assert_canonical_fields_equal(actual, _rich_canonical_expectation(wire))


def test_sparse_prose_only_wire_needs_no_baseline() -> None:
    hydrated = hydrate_skald_turn(SkaldTurnWire.model_validate(SPARSE_WIRE_PAYLOAD))
    expected = StorytellerResponseExtended(
        narrative=str(SPARSE_WIRE_PAYLOAD["narrative"]),
        choices=list(SPARSE_WIRE_PAYLOAD["choices"]),
        chunk_metadata=ChunkMetadataUpdate(),
        referenced_entities=ReferencedEntities(),
        state_updates=StateUpdates(),
        operations=None,
        orrery_adjudications=[],
        new_entities=[],
        reasoning=None,
    )
    _assert_canonical_fields_equal(hydrated, expected)


def test_absent_presence_block_carries_supplied_baseline() -> None:
    hydrated = hydrate_skald_turn(
        SkaldTurnWire.model_validate(SPARSE_WIRE_PAYLOAD),
        presence_baseline=BASELINE,
    )
    assert hydrated.referenced_entities == ReferencedEntities(
        characters=[
            CharacterReference(
                character_id=7,
                character_name="Brena Tideloft",
                reference_type=ReferenceType.PRESENT,
            ),
            CharacterReference(
                character_id=8,
                character_name="Odile",
                reference_type=ReferenceType.PRESENT,
            ),
        ],
        places=[
            PlaceReference(
                place_id=41,
                place_name="The Lower Sluice",
                reference_type=PlaceReferenceType.SETTING,
            )
        ],
    )


def test_scene_reset_replaces_roster_and_setting() -> None:
    wire = SkaldTurnWire.model_validate(
        {
            **SPARSE_WIRE_PAYLOAD,
            "presence": {
                "scene_reset": {
                    "place": {
                        "kind": "place",
                        "name": "The Bell Archive",
                        "id": 42,
                    },
                    "present": [
                        {
                            "kind": "character",
                            "name": "Marra Kest",
                            "id": 9,
                        }
                    ],
                },
                "mentions": [
                    {
                        "kind": "faction",
                        "name": "The Sluice Guild",
                        "id": 12,
                    }
                ],
            },
        }
    )
    hydrated = hydrate_skald_turn(wire, presence_baseline=BASELINE)
    assert hydrated.referenced_entities == ReferencedEntities(
        characters=[
            CharacterReference(
                character_id=9,
                character_name="Marra Kest",
                reference_type=ReferenceType.PRESENT,
            )
        ],
        places=[
            PlaceReference(
                place_id=42,
                place_name="The Bell Archive",
                reference_type=PlaceReferenceType.SETTING,
            )
        ],
        factions=[
            FactionReference(
                faction_id=12,
                faction_name="The Sluice Guild",
                reference_type=ReferenceType.MENTIONED,
            )
        ],
    )


def test_enter_present_and_exit_absent_are_idempotent() -> None:
    wire = SkaldTurnWire.model_validate(
        {
            **SPARSE_WIRE_PAYLOAD,
            "presence": {
                "enter": [{"kind": "character", "name": "Brena Tideloft"}],
                "exit": [{"kind": "character", "name": "Never Here"}],
            },
        }
    )
    hydrated = hydrate_skald_turn(wire, presence_baseline=BASELINE)
    assert [
        (reference.character_id, reference.character_name)
        for reference in hydrated.referenced_entities.characters
    ] == [(7, "Brena Tideloft"), (8, "Odile")]


def test_presence_without_baseline_raises_loudly() -> None:
    wire = SkaldTurnWire.model_validate(
        {
            **SPARSE_WIRE_PAYLOAD,
            "presence": {"mentions": [{"kind": "faction", "name": "Guild"}]},
        }
    )
    with pytest.raises(ValueError, match="presence_baseline is required"):
        hydrate_skald_turn(wire)


@pytest.mark.parametrize(
    "presence",
    [
        {"enter": [{"kind": "faction", "name": "Guild"}]},
        {"exit": [{"kind": "faction", "name": "Guild"}]},
        {"transit": [{"kind": "character", "name": "Brena"}]},
        {
            "scene_reset": {
                "place": {"kind": "character", "name": "Brena"},
                "present": [],
            }
        },
        {
            "scene_reset": {
                "place": {"kind": "place", "name": "Archive"},
                "present": [{"kind": "faction", "name": "Guild"}],
            }
        },
    ],
)
def test_presence_rejects_ontology_invalid_kinds(
    presence: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        SkaldTurnWire.model_validate({**SPARSE_WIRE_PAYLOAD, "presence": presence})


@pytest.mark.parametrize("roster_operation", ["enter", "exit"])
def test_scene_reset_rejects_roster_operations(roster_operation: str) -> None:
    with pytest.raises(
        ValidationError,
        match="scene_reset cannot be combined with enter or exit",
    ):
        SkaldTurnWire.model_validate(
            {
                **SPARSE_WIRE_PAYLOAD,
                "presence": {
                    "scene_reset": {
                        "place": {"kind": "place", "name": "Archive"},
                        "present": [],
                    },
                    roster_operation: [{"kind": "character", "name": "Brena Tideloft"}],
                },
            }
        )


def test_presence_rejects_same_name_in_enter_and_exit_casefolded() -> None:
    with pytest.raises(
        ValidationError,
        match="presence cannot enter and exit the same character",
    ):
        SkaldTurnWire.model_validate(
            {
                **SPARSE_WIRE_PAYLOAD,
                "presence": {
                    "enter": [{"kind": "character", "name": "Brena Tideloft"}],
                    "exit": [{"kind": "character", "name": "BRENA TIDELOFT"}],
                },
            }
        )


@pytest.mark.parametrize(
    ("update", "message"),
    [
        (
            {"kind": "character", "name": "Brena Tideloft"},
            "character update requires a substantive field",
        ),
        (
            {"kind": "place", "name": "The Lower Sluice"},
            "place update requires a substantive field",
        ),
        (
            {"kind": "faction", "name": "The Sluice Guild"},
            "faction update requires a substantive field",
        ),
        (
            {
                "kind": "relationship",
                "name": "Brena Tideloft",
                "other_name": "Odile",
            },
            "relationship update requires a substantive field",
        ),
    ],
)
def test_update_arms_require_substantive_fields(
    update: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        SkaldTurnWire.model_validate({**SPARSE_WIRE_PAYLOAD, "updates": [update]})


def test_faction_stance_fields_must_travel_together() -> None:
    with pytest.raises(
        ValidationError,
        match="stance_toward and stance must travel together",
    ):
        SkaldTurnWire.model_validate(
            {
                **SPARSE_WIRE_PAYLOAD,
                "updates": [
                    {
                        "kind": "faction",
                        "name": "Guild",
                        "stance_toward": "Brena",
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("elapsed", "minutes", "hours", "days"),
    [
        (0, 0, None, None),
        (59, 59, None, None),
        (60, None, 1, None),
        (1439, 59, 23, None),
        (1440, None, None, 1),
        (4385, 5, 1, 3),
    ],
)
def test_chronology_elapsed_minutes_split(
    elapsed: int,
    minutes: int | None,
    hours: int | None,
    days: int | None,
) -> None:
    wire = SkaldTurnWire.model_validate(
        {**SPARSE_WIRE_PAYLOAD, "scene": {"elapsed_minutes": elapsed}}
    )
    chronology = hydrate_skald_turn(wire).chunk_metadata.chronology
    assert chronology == ChronologyUpdate(
        episode_transition="continue",
        time_delta_minutes=minutes,
        time_delta_hours=hours,
        time_delta_days=days,
        time_delta_description=None,
    )


def test_lenient_sparse_round_trip_has_no_scaffold_keys() -> None:
    schema = skald_wire_lenient_schema()
    assert schema["required"] == ["narrative", "choices"]
    update_items = schema["properties"]["updates"]["items"]
    assert update_items["discriminator"]["propertyName"] == "kind"
    assert set(update_items["discriminator"]["mapping"]) == {
        "character",
        "place",
        "faction",
        "relationship",
    }

    serialized = json.dumps(SPARSE_WIRE_PAYLOAD, separators=(",", ":"))
    wire = SkaldTurnWire.model_validate_json(serialized)
    assert wire.model_dump(exclude_unset=True, mode="json") == SPARSE_WIRE_PAYLOAD


def _compact_schema_json(schema: dict[str, Any]) -> str:
    return json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _wire_component_models() -> set[type[BaseModel]]:
    """Return every Pydantic model reachable from the wire envelope."""

    models: set[type[BaseModel]] = set()

    def visit(annotation: Any) -> None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if annotation in models:
                return
            models.add(annotation)
            for field in annotation.model_fields.values():
                visit(field.annotation)
            return
        for argument in get_args(annotation):
            visit(argument)

    visit(SkaldTurnWire)
    return models


def _schema_descriptions(value: Any) -> set[str]:
    """Collect exact descriptions from a serialized JSON Schema."""

    descriptions: set[str] = set()
    if isinstance(value, dict):
        description = value.get("description")
        if isinstance(description, str):
            descriptions.add(description)
        for nested in value.values():
            descriptions.update(_schema_descriptions(nested))
    elif isinstance(value, list):
        for nested in value:
            descriptions.update(_schema_descriptions(nested))
    return descriptions


def test_lenient_wire_closes_every_object_schema_node() -> None:
    """No wire-reachable object may silently discard unknown provider keys."""

    open_object_nodes: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            node_type = value.get("type")
            is_object = node_type == "object" or (
                isinstance(node_type, list) and "object" in node_type
            )
            if is_object and value.get("additionalProperties") is not False:
                open_object_nodes.append(path)
            for key, nested in value.items():
                visit(nested, f"{path}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, f"{path}[{index}]")

    visit(skald_wire_lenient_schema(), "$")
    assert open_object_nodes == []


def test_wire_schema_size_and_description_budget() -> None:
    strict_schema = skald_wire_strict_text_format()["schema"]
    lenient_schema = skald_wire_lenient_schema()
    strict_wire = _compact_schema_json(strict_schema)
    lenient_wire = _compact_schema_json(lenient_schema)
    described_models = _wire_component_models() | {PresenceBaseline}

    assert len(strict_wire.encode("utf-8")) <= SKALD_WIRE_STRICT_MAX_BYTES
    assert len(lenient_wire.encode("utf-8")) <= SKALD_WIRE_LENIENT_MAX_BYTES

    overlong_descriptions = {
        f"{model.__name__}.{field_name}": field.description
        for model in described_models
        for field_name, field in model.model_fields.items()
        if field.description is not None
        and len(field.description) > SKALD_WIRE_DESCRIPTION_MAX_CHARS
    }
    assert overlong_descriptions == WIRE_DESCRIPTION_SURVIVORS
    overlong_new_model_descriptions = {
        model.__name__: description
        for model in described_models
        if model.__module__ == "nexus.agents.logon.skald_wire"
        if isinstance(
            description := model.model_json_schema().get("description"),
            str,
        )
        and len(description) > SKALD_WIRE_DESCRIPTION_MAX_CHARS
    }
    assert overlong_new_model_descriptions == {}


def test_component_guidance_survives_both_wire_serializations() -> None:
    assert (
        NewEntityPairTagHint.model_fields["declared_entity_role"].description
        == DECLARED_ENTITY_ROLE_DESCRIPTION
    )
    assert (
        OrreryAdjudication.model_fields["replacement_event_type"].description
        == REPLACEMENT_EVENT_TYPE_DESCRIPTION
    )
    assert Coordinates.model_json_schema()["description"] == COORDINATES_DESCRIPTION

    for schema in (
        skald_wire_strict_text_format()["schema"],
        skald_wire_lenient_schema(),
    ):
        descriptions = _schema_descriptions(schema)
        assert DECLARED_ENTITY_ROLE_DESCRIPTION in descriptions
        assert REPLACEMENT_EVENT_TYPE_DESCRIPTION in descriptions
        assert COORDINATES_DESCRIPTION in descriptions


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("reasoning", "debug chain"),
        ("generation_model", "provider-owned"),
        ("state_updates", {}),
        ("chunk_metadata", {}),
        ("referenced_entities", {}),
        ("unknown_key", "not in the contract"),
    ],
)
def test_wire_rejects_v1_and_unknown_keys_loudly(
    field_name: str,
    field_value: Any,
) -> None:
    payload = {**SPARSE_WIRE_PAYLOAD, field_name: field_value}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SkaldTurnWire.model_validate(payload)


def test_logon_selects_transport_appropriate_wire_serialization() -> None:
    utility = LogonUtility({}, dbname="save_05")

    utility._provider_wire_type = "openai"
    assert utility._schema_format_kwargs(SkaldTurnWire) == {
        "text_format": skald_wire_strict_text_format()
    }

    utility._provider_wire_type = "local"
    utility._schema_format_cache = {}
    local_format = utility._schema_format_kwargs(SkaldTurnWire)["text_format"]
    assert local_format["name"] == "SkaldTurnWire"
    assert local_format["schema"] == skald_wire_lenient_schema()

    utility._provider_wire_type = "anthropic"
    utility._schema_format_cache = {}
    assert utility._schema_format_kwargs(SkaldTurnWire) == {
        "output_config": anthropic_output_config(
            SkaldTurnWire,
            schema=skald_wire_lenient_schema(),
        )
    }


def test_local_chat_response_format_carries_lenient_wire_schema() -> None:
    utility = LogonUtility({})
    utility._provider_wire_type = "local"
    text_format = utility._schema_format_kwargs(SkaldTurnWire)["text_format"]
    response_format = OpenAIProvider._chat_response_format(
        SkaldTurnWire,
        text_format=text_format,
    )
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["schema"] == skald_wire_lenient_schema()
    assert response_format["json_schema"]["schema"]["required"] == [
        "narrative",
        "choices",
    ]


def test_bootstrap_schema_selection_and_contract_are_unchanged() -> None:
    utility = LogonUtility({})
    assert utility._select_response_schema({"is_bootstrap": True}) is (
        StorytellerResponseBootstrap
    )
    assert utility._select_response_schema({}) is SkaldTurnWire

    utility._provider_wire_type = "openai"
    text_format = utility._schema_format_kwargs(StorytellerResponseBootstrap)[
        "text_format"
    ]
    assert text_format["name"] == "StorytellerResponseBootstrap"
    assert set(text_format["schema"]["properties"]) == {"narrative", "choices"}


def test_non_bootstrap_logon_requires_parent_chunk_id() -> None:
    utility = LogonUtility({}, dbname="save_05")
    with pytest.raises(
        ValueError,
        match="requires metadata.target_chunk_id",
    ):
        utility._read_presence_baseline_for_context({}, SkaldTurnWire)


@pytest.mark.asyncio
async def test_async_non_bootstrap_logon_requires_parent_chunk_id() -> None:
    utility = LogonUtility({}, dbname="save_05")
    with pytest.raises(
        ValueError,
        match="requires metadata.target_chunk_id",
    ):
        await utility._read_presence_baseline_for_context_async({}, SkaldTurnWire)


def test_storyteller_prompt_defines_reset_and_world_layer_semantics() -> None:
    prompt = (Path(__file__).parents[1] / "prompts" / "storyteller_core.md").read_text()
    assert "on a reset, list the full roster instead of `enter` / `exit`" in prompt
    assert "A flashback is a scene set in the past" in prompt
    assert "atemporal means dreams or time-abnormal realms" in prompt
    assert "extradiegetic means the user addressing out-of-game" in prompt


def test_sync_logon_reads_and_supplies_parent_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WireProvider:
        model = "wire-test-model"

        def get_structured_completion(
            self,
            _prompt: str,
            _schema_model: type,
            **_kwargs: Any,
        ) -> tuple[SkaldTurnWire, object]:
            return SkaldTurnWire.model_validate(SPARSE_WIRE_PAYLOAD), object()

    calls: list[tuple[str, int]] = []

    def fake_read(dbname: str, parent_chunk_id: int) -> PresenceBaseline:
        calls.append((dbname, parent_chunk_id))
        return BASELINE

    monkeypatch.setattr(logon_utility, "read_presence_baseline", fake_read)
    utility = LogonUtility(
        {},
        dbname="save_05",
        model_override="wire-test-model",
    )
    utility.provider = cast(Any, WireProvider())
    utility._provider_bootstrap_mode = False
    response = utility.generate_narrative(
        {
            "user_input": "Continue.",
            "warm_slice": {"chunks": []},
            "entity_data": {},
            "retrieved_passages": {"results": []},
            "metadata": {"target_chunk_id": 77},
        }
    )
    assert calls == [("save_05", 77)]
    assert isinstance(response, StorytellerResponseExtended)
    assert len(response.referenced_entities.characters) == 2
    assert response.generation_model == "wire-test-model"


@pytest.mark.asyncio
async def test_async_logon_reads_and_supplies_parent_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WireProvider:
        model = "wire-test-model"

        async def get_structured_completion_async(
            self,
            _prompt: str,
            _schema_model: type,
            **_kwargs: Any,
        ) -> tuple[SkaldTurnWire, object]:
            return SkaldTurnWire.model_validate(SPARSE_WIRE_PAYLOAD), object()

    calls: list[tuple[str, int]] = []

    async def fake_read(dbname: str, parent_chunk_id: int) -> PresenceBaseline:
        calls.append((dbname, parent_chunk_id))
        return BASELINE

    monkeypatch.setattr(logon_utility, "read_presence_baseline_async", fake_read)
    utility = LogonUtility(
        {},
        dbname="save_05",
        model_override="wire-test-model",
    )
    utility.provider = cast(Any, WireProvider())
    utility._provider_bootstrap_mode = False
    response = await utility.generate_narrative_async(
        {
            "user_input": "Continue.",
            "warm_slice": {"chunks": []},
            "entity_data": {},
            "retrieved_passages": {"results": []},
            "metadata": {"target_chunk_id": 77},
        }
    )
    assert calls == [("save_05", 77)]
    assert isinstance(response, StorytellerResponseExtended)
    assert len(response.referenced_entities.characters) == 2
    assert response.generation_model == "wire-test-model"


@pytest.mark.requires_postgres
def test_presence_baseline_reads_real_slot_parent_rows() -> None:
    """Read a real parent chunk without mutating its slot database."""

    dbname = os.environ.get("NEXUS_BASELINE_TEST_DB", "save_05")
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(chunk_id)
                FROM (
                    SELECT ccr.chunk_id
                    FROM chunk_character_references AS ccr
                    WHERE ccr.reference::text = 'present'
                    UNION ALL
                    SELECT pcr.chunk_id
                    FROM place_chunk_references AS pcr
                    WHERE pcr.reference_type::text = 'setting'
                ) AS candidates
                """
            )
            parent_row = cur.fetchone()
    finally:
        conn.close()

    assert parent_row is not None
    parent_chunk_id = parent_row[0]
    if parent_chunk_id is None:
        pytest.skip("Slot has no parent chunk with presence junction rows")
    baseline = read_presence_baseline(dbname, parent_chunk_id)
    assert baseline.present or baseline.setting is not None
    assert all(reference.kind == "character" for reference in baseline.present)
    assert baseline.setting is None or baseline.setting.kind == "place"


def test_schema_token_measurement_uses_o200k() -> None:
    encoding = tiktoken.get_encoding("o200k_base")
    strict_wire = _compact_schema_json(skald_wire_strict_text_format()["schema"])
    lenient_wire = _compact_schema_json(skald_wire_lenient_schema())
    assert len(encoding.encode(strict_wire)) > 0
    assert len(encoding.encode(lenient_wire)) > 0
