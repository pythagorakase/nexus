"""Compact native JSON Schema constraints for storyteller responses."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Type

from pydantic import BaseModel

from nexus.api.native_structured_output import (
    anthropic_output_config,
    openai_response_text_format,
    strict_json_schema,
)

# Interim #558 diet until #554 replaces the full wire model. This cutoff removes
# at least 2,000 o200k tokens from the Extended strict schema while keeping terse
# leaf-field hints.
STORYTELLER_WIRE_DESCRIPTION_MAX_LENGTH = 70


def diet_storyteller_wire_schema(value: Any) -> Any:
    """Return a copy with overlong JSON Schema descriptions removed."""

    if isinstance(value, list):
        return [diet_storyteller_wire_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: diet_storyteller_wire_schema(item)
        for key, item in value.items()
        if not (
            key == "description"
            and isinstance(item, str)
            and len(item) > STORYTELLER_WIRE_DESCRIPTION_MAX_LENGTH
        )
    }


def storyteller_openai_text_format(
    schema_model: Type[BaseModel],
) -> Dict[str, Any]:
    """Build the dieted strict OpenAI text.format storyteller payload."""

    dieted_schema = diet_storyteller_wire_schema(strict_json_schema(schema_model))
    return openai_response_text_format(schema_model, schema=dieted_schema)


def storyteller_anthropic_output_config(
    schema_model: Type[BaseModel], dbname: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Build an Anthropic output_config without live vocabulary catalogs."""

    compact_schema = storyteller_anthropic_compact_schema(schema_model, dbname)
    if compact_schema is not None:
        return anthropic_output_config(schema_model, schema=compact_schema)

    return anthropic_output_config(
        schema_model,
        schema=strict_json_schema(schema_model),
    )


def storyteller_anthropic_compact_schema(
    schema_model: Type[BaseModel],
    dbname: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return a compact Anthropic wire schema for extended storyteller turns."""

    del dbname  # The wire contract must remain stable as live registries grow.
    if schema_model.__name__ != "StorytellerResponseExtended":
        return None

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "narrative": {
                "type": "string",
                "description": "The narrative prose.",
            },
            "choices": _string_array_schema(
                "Player choices, each as a complete actionable option."
            ),
            "chunk_metadata": _empty_object_schema(
                "Default chunk metadata; runtime fills normal chronology."
            ),
            "referenced_entities": _empty_object_schema(
                "Default referenced entity set; leave empty in compact Anthropic wire."
            ),
            "state_updates": _compact_state_updates_schema(),
            "operations": _empty_object_schema("No operations."),
            "orrery_adjudications": {
                "type": "array",
                "items": _compact_orrery_adjudication_schema(),
                "description": "Optional defer/replace/void rulings.",
            },
            "new_entities": {
                "type": "array",
                "items": _compact_new_entity_schema(),
                "description": (
                    "Sparing declarations for newly introduced persistent entities."
                ),
            },
            "reasoning": {"type": "string", "description": "Optional debug reasoning."},
        },
        "required": [
            "narrative",
            "choices",
            "chunk_metadata",
            "referenced_entities",
            "state_updates",
            "operations",
            "orrery_adjudications",
            "new_entities",
            "reasoning",
        ],
    }


def _string_array_schema(description: str) -> Dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": description,
    }


def _optional_string_schema(description: str) -> Dict[str, Any]:
    return {"type": "string", "description": description}


def _empty_object_schema(description: str) -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
        "description": description,
    }


def _nullable_schema(schema: Mapping[str, Any]) -> Dict[str, Any]:
    return {"anyOf": [dict(schema), {"type": "null"}]}


def _compact_state_updates_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "updates": {
                "type": "array",
                "items": _compact_state_update_entry_schema(),
            }
        },
        "required": ["updates"],
        "description": "Compact per-turn entity state updates expanded by runtime.",
    }


def _compact_state_update_entry_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["character", "place", "faction"],
            },
            "name": _optional_string_schema("Subject entity name."),
            "status": _optional_string_schema(
                "Current activity, condition, or faction action."
            ),
            "tag_add": _optional_string_schema("Registered tag name to apply."),
            "tag_clear": _optional_string_schema("Registered tag name to clear."),
        },
        "required": ["kind"],
    }


def _compact_new_entity_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": ["character", "place", "faction"]},
            "name": {"type": "string"},
            "summary": {"type": "string"},
            "tag_hints": _string_array_schema(
                "Registered single-entity tag names.",
            ),
            "pair_tag_hints": {
                "type": "array",
                "items": _compact_pair_tag_hint_schema(),
            },
        },
        "required": [
            "kind",
            "name",
            "summary",
            "tag_hints",
            "pair_tag_hints",
        ],
    }


def _compact_pair_tag_hint_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "tag": {"type": "string"},
            "other_entity_name": {"type": "string"},
            "declared_entity_role": {
                "type": "string",
                "enum": ["subject", "object"],
            },
        },
        "required": ["tag", "other_entity_name", "declared_entity_role"],
    }


def _compact_orrery_adjudication_schema() -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "proposal_id": {"type": "string"},
        "action": {"type": "string", "enum": ["defer", "replace", "void"]},
        "note": {"type": "string"},
        "replacement_event_type": {"type": "string"},
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": [
            "proposal_id",
            "action",
        ],
    }
