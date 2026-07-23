"""Tests for the universal Skald storyteller wire boundary."""

from __future__ import annotations

import json
from typing import Any, cast, get_args

import pytest
import tiktoken
from pydantic import BaseModel, ValidationError

from nexus.agents.logon.apex_schema import (
    ChunkMetadataUpdate,
    Coordinates,
    NewEntityPairTagHint,
    OrreryAdjudication,
    ReferencedEntities,
    StateUpdates,
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
)
from nexus.agents.logon.skald_wire import (
    SkaldTurnWire,
    hydrate_skald_turn,
    skald_wire_lenient_schema,
    skald_wire_strict_text_format,
)
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api.native_structured_output import anthropic_output_config
from scripts.api_openai import OpenAIProvider


# Slice 1's literal component reuse measures 23,345 strict bytes; this leaves
# about 500 bytes of drift. #555's semantic-delta redesign owns the next cut.
SKALD_WIRE_STRICT_MAX_BYTES = 23_850
# The corresponding lenient schema measures 22,413 bytes.
SKALD_WIRE_LENIENT_MAX_BYTES = 22_950
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
    "OrreryAdjudication.replacement_event_type": (REPLACEMENT_EVENT_TYPE_DESCRIPTION),
}


FULL_WIRE_PAYLOAD: dict[str, Any] = {
    "narrative": "Brena follows the bell-sound through the flooded stacks.",
    "choices": [
        "Follow the footprints into the archive.",
        "Call for Odile before proceeding.",
    ],
    "chunk_metadata": {
        "chronology": {
            "episode_transition": "new_episode",
            "time_delta_minutes": 12,
            "time_delta_description": "twelve minutes later",
        },
        "world_layer": "primary",
        "scene_weather": "rain",
    },
    "referenced_entities": {
        "characters": [
            {
                "character_name": "Brena Tideloft",
                "reference_type": "present",
            }
        ],
        "places": [
            {
                "place_name": "The Lower Sluice",
                "reference_type": "setting",
            }
        ],
        "factions": [
            {
                "faction_name": "The Sluice Guild",
                "reference_type": "mentioned",
            }
        ],
    },
    "state_updates": {
        "characters": [
            {
                "character_name": "Brena Tideloft",
                "current_activity": "tracking the drowned clerk",
                "orrery_tags": {
                    "applied_tags": ["perceptive"],
                    "tags_to_clear": [],
                },
            }
        ],
        "relationships": [
            {
                "character1_name": "Brena Tideloft",
                "character2_name": "Odile",
                "relationship_type": "ally",
                "emotional_valence": "+2|friendly",
                "dynamic": "Trust sharpened by shared danger.",
            }
        ],
        "locations": [
            {
                "place_name": "The Lower Sluice",
                "current_conditions": "Floodwater rising between the stacks.",
                "notable_changes": ["The archive bell is ringing underwater."],
            }
        ],
        "factions": [
            {
                "faction_name": "The Sluice Guild",
                "recent_actions": ["Sealed the eastern lock."],
                "stance_changes": [
                    {
                        "target": "Brena Tideloft",
                        "stance": "watchful cooperation",
                    }
                ],
            }
        ],
    },
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

SPARSE_WIRE_PAYLOAD = {
    "narrative": "Rain beads on the sealed archive door.",
    "choices": ["Knock twice.", "Wait beneath the awning."],
}

FORMER_COMPACT_SEMANTICS_PAYLOAD: dict[str, Any] = {
    "narrative": "Brena follows the wet bell-sound into the stacks.",
    "choices": ["Follow the footprints.", "Call for Odile."],
    "state_updates": {
        "characters": [
            {
                "character_name": "Brena Tideloft",
                "current_activity": "following a wet bell-sound",
                "orrery_tags": {
                    "applied_tags": ["perceptive"],
                    "tags_to_clear": [],
                },
            }
        ]
    },
    "new_entities": [
        {
            "kind": "character",
            "name": "Marra Kest",
            "summary": "A drowned clerk animated by echo and current.",
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


def _canonical_from_wire_payload(
    payload: dict[str, Any],
) -> StorytellerResponseExtended:
    """Construct today's canonical equivalent for a wire fixture."""

    canonical_payload = dict(payload)
    canonical_payload.setdefault("chunk_metadata", {})
    canonical_payload.setdefault("referenced_entities", {})
    canonical_payload.setdefault("state_updates", {})
    canonical_payload.setdefault("operations", None)
    canonical_payload.setdefault("orrery_adjudications", [])
    canonical_payload.setdefault("new_entities", [])
    canonical_payload["reasoning"] = None
    return StorytellerResponseExtended.model_validate(canonical_payload)


@pytest.mark.parametrize(
    "payload",
    [
        FULL_WIRE_PAYLOAD,
        SPARSE_WIRE_PAYLOAD,
        FORMER_COMPACT_SEMANTICS_PAYLOAD,
    ],
)
def test_golden_wire_payloads_hydrate_field_by_field(
    payload: dict[str, Any],
) -> None:
    wire = SkaldTurnWire.model_validate(payload)
    hydrated = hydrate_skald_turn(wire)
    expected = _canonical_from_wire_payload(payload)

    _assert_canonical_fields_equal(hydrated, expected)


def test_sparse_wire_matches_direct_canonical_defaults() -> None:
    """The sparse fixture preserves today's direct canonical result."""

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


def test_lenient_sparse_round_trip_has_no_scaffold_keys() -> None:
    schema = skald_wire_lenient_schema()
    assert schema["required"] == ["narrative", "choices"]

    serialized = json.dumps(SPARSE_WIRE_PAYLOAD, separators=(",", ":"))
    wire = SkaldTurnWire.model_validate_json(serialized)
    assert wire.model_dump(exclude_unset=True, mode="json") == SPARSE_WIRE_PAYLOAD

    hydrated = hydrate_skald_turn(wire)
    assert hydrated.chunk_metadata == ChunkMetadataUpdate()
    assert hydrated.referenced_entities == ReferencedEntities()
    assert hydrated.state_updates == StateUpdates()
    assert hydrated.operations is None
    assert hydrated.orrery_adjudications == []
    assert hydrated.new_entities == []
    assert hydrated.reasoning is None


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


def test_wire_schema_size_and_description_budget() -> None:
    strict_schema = skald_wire_strict_text_format()["schema"]
    lenient_schema = skald_wire_lenient_schema()
    strict_wire = _compact_schema_json(strict_schema)
    lenient_wire = _compact_schema_json(lenient_schema)

    assert len(strict_wire.encode("utf-8")) <= SKALD_WIRE_STRICT_MAX_BYTES
    assert len(lenient_wire.encode("utf-8")) <= SKALD_WIRE_LENIENT_MAX_BYTES

    overlong_descriptions = {
        f"{model.__name__}.{field_name}": field.description
        for model in _wire_component_models()
        for field_name, field in model.model_fields.items()
        if field.description is not None
        and len(field.description) > SKALD_WIRE_DESCRIPTION_MAX_CHARS
    }
    assert overlong_descriptions == WIRE_DESCRIPTION_SURVIVORS


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
        ("unknown_key", "not in the contract"),
    ],
)
def test_wire_rejects_reasoning_and_unknown_keys_loudly(
    field_name: str,
    field_value: str,
) -> None:
    payload = {**SPARSE_WIRE_PAYLOAD, field_name: field_value}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SkaldTurnWire.model_validate(payload)


def test_logon_selects_transport_appropriate_wire_serialization() -> None:
    utility = LogonUtility({}, dbname="save_05")

    utility._provider_wire_type = "openai"
    native_kwargs = utility._schema_format_kwargs(SkaldTurnWire)
    assert native_kwargs == {"text_format": skald_wire_strict_text_format()}

    utility._provider_wire_type = "local"
    utility._schema_format_cache = {}
    local_kwargs = utility._schema_format_kwargs(SkaldTurnWire)
    local_format = local_kwargs["text_format"]
    assert local_format["name"] == "SkaldTurnWire"
    assert local_format["schema"] == skald_wire_lenient_schema()

    utility._provider_wire_type = "anthropic"
    utility._schema_format_cache = {}
    anthropic_kwargs = utility._schema_format_kwargs(SkaldTurnWire)
    assert anthropic_kwargs == {
        "output_config": anthropic_output_config(
            SkaldTurnWire,
            schema=skald_wire_lenient_schema(),
        )
    }


def test_local_chat_response_format_carries_lenient_wire_schema() -> None:
    """The local Chat transport receives the omittable-field schema unchanged."""

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


def test_sync_logon_hydrates_wire_before_returning_canonical_response() -> None:
    class WireProvider:
        model = "wire-test-model"

        def __init__(self) -> None:
            self.schema_models: list[type] = []

        def get_structured_completion(
            self,
            _prompt: str,
            schema_model: type,
            **_kwargs: Any,
        ) -> tuple[SkaldTurnWire, object]:
            self.schema_models.append(schema_model)
            return SkaldTurnWire.model_validate(SPARSE_WIRE_PAYLOAD), object()

    provider = WireProvider()
    utility = LogonUtility({}, model_override=provider.model)
    utility.provider = cast(Any, provider)
    utility._provider_bootstrap_mode = False

    response = utility.generate_narrative(
        {
            "user_input": "Continue.",
            "warm_slice": {"chunks": []},
            "entity_data": {},
            "retrieved_passages": {"results": []},
        }
    )

    assert isinstance(response, StorytellerResponseExtended)
    assert provider.schema_models == [SkaldTurnWire]
    assert response.chunk_metadata == ChunkMetadataUpdate()
    assert response.referenced_entities == ReferencedEntities()
    assert response.state_updates == StateUpdates()
    assert response.generation_model == "wire-test-model"


def test_canonical_state_updates_reject_deleted_flat_compact_dialect() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StateUpdates.model_validate(
            {
                "updates": [
                    {
                        "kind": "character",
                        "name": "Brena Tideloft",
                        "tag_add": "perceptive",
                    }
                ]
            }
        )


def test_schema_token_measurement_uses_o200k() -> None:
    """Keep the report's deterministic token measurement executable."""

    encoding = tiktoken.get_encoding("o200k_base")
    strict_wire = _compact_schema_json(skald_wire_strict_text_format()["schema"])
    lenient_wire = _compact_schema_json(skald_wire_lenient_schema())

    assert len(encoding.encode(strict_wire)) > 0
    assert len(encoding.encode(lenient_wire)) > 0
