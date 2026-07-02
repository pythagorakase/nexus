"""Runtime JSON Schema constraints for storyteller Orrery tag bestowals."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Dict, Mapping, Optional, Sequence, Type

from pydantic import BaseModel

from nexus.agents.orrery.tag_library import (
    read_event_types,
    read_pair_tag_library,
    read_tag_library,
)
from nexus.api.native_structured_output import (
    anthropic_output_config,
    openai_response_text_format,
    strict_json_schema,
)

logger = logging.getLogger("nexus.logon.orrery_tag_schema")

_KIND_DEF_NAMES = {
    "character": "OrreryTagBestowalCharacter",
    "place": "OrreryTagBestowalPlace",
    "faction": "OrreryTagBestowalFaction",
}

_OWNER_KINDS = {
    "CharacterStateUpdate": "character",
    "NewCharacter": "character",
    "LocationStateUpdate": "place",
    "NewPlace": "place",
    "FactionStateUpdate": "faction",
    "NewFaction": "faction",
}


def storyteller_openai_text_format(
    schema_model: Type[BaseModel], dbname: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Build an OpenAI text.format with live tag enums for LOGON responses."""

    schema = storyteller_schema_with_runtime_tag_enums(schema_model, dbname)
    if schema is None:
        return None
    return openai_response_text_format(schema_model, schema=schema)


def storyteller_anthropic_output_config(
    schema_model: Type[BaseModel], dbname: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Build an Anthropic output_config with live tag enums for LOGON responses."""

    compact_schema = storyteller_anthropic_compact_schema(schema_model, dbname)
    if compact_schema is not None:
        return anthropic_output_config(schema_model, schema=compact_schema)

    schema = storyteller_schema_with_runtime_tag_enums(schema_model, dbname)
    if schema is None:
        return None
    return anthropic_output_config(schema_model, schema=schema)


def storyteller_anthropic_compact_schema(
    schema_model: Type[BaseModel],
    dbname: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return a compact Anthropic wire schema for extended storyteller turns."""

    if schema_model.__name__ != "StorytellerResponseExtended":
        return None
    tag_names, pair_tag_names, event_types = _compact_storyteller_vocabulary(dbname)

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
                "items": _compact_orrery_adjudication_schema(event_types),
                "description": "Optional defer/replace/void rulings.",
            },
            "new_entities": {
                "type": "array",
                "items": _compact_new_entity_schema(tag_names, pair_tag_names),
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


def storyteller_schema_with_runtime_tag_enums(
    schema_model: Type[BaseModel], dbname: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Specialize LOGON's JSON Schema with slot-specific Orrery tag enums."""

    if not dbname:
        return None
    try:
        tags_by_kind = _read_tags_by_kind(dbname)
    except Exception as exc:
        logger.warning(
            "Failed to load runtime Orrery tag enums for storyteller schema: %s",
            exc,
        )
        return None
    if not any(tags_by_kind.values()):
        return None

    schema = deepcopy(strict_json_schema(schema_model))
    defs = schema.get("$defs")
    if not isinstance(defs, dict) or "OrreryTagBestowal" not in defs:
        return None

    base_bestowal = defs["OrreryTagBestowal"]
    for entity_kind, tags in tags_by_kind.items():
        if not tags:
            continue
        def_name = _KIND_DEF_NAMES[entity_kind]
        defs[def_name] = _bestowal_def_with_tag_enum(
            base_bestowal,
            tags,
            entity_kind=entity_kind,
        )

    replaced = False
    for owner_def, entity_kind in _OWNER_KINDS.items():
        if not tags_by_kind.get(entity_kind):
            continue
        if _replace_owner_bestowal_ref(
            defs,
            owner_def=owner_def,
            target_def=_KIND_DEF_NAMES[entity_kind],
        ):
            replaced = True

    return schema if replaced else None


def _string_array_schema(description: str) -> Dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": description,
    }


def _enum_string_array_schema(
    description: str,
    values: Sequence[str],
) -> Dict[str, Any]:
    items: Dict[str, Any] = {"type": "string"}
    if values:
        items["enum"] = list(values)
    return {
        "type": "array",
        "items": items,
        "description": description,
    }


def _enum_string_schema(values: Sequence[str]) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "string"}
    if values:
        schema["enum"] = list(values)
    return schema


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


def _compact_new_entity_schema(
    tag_names: Sequence[str],
    pair_tag_names: Sequence[str],
) -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": ["character", "place", "faction"]},
            "name": {"type": "string"},
            "summary": {"type": "string"},
            "tag_hints": _enum_string_array_schema(
                "Registered single-entity tag names.",
                tag_names,
            ),
            "pair_tag_hints": {
                "type": "array",
                "items": _compact_pair_tag_hint_schema(pair_tag_names),
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


def _compact_pair_tag_hint_schema(pair_tag_names: Sequence[str]) -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "tag": _enum_string_schema(pair_tag_names),
            "other_entity_name": {"type": "string"},
            "declared_entity_role": {
                "type": "string",
                "enum": ["subject", "object"],
            },
        },
        "required": ["tag", "other_entity_name", "declared_entity_role"],
    }


def _compact_orrery_adjudication_schema(
    event_types: Sequence[str],
) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "proposal_id": {"type": "string"},
        "action": {"type": "string", "enum": ["defer", "replace", "void"]},
        "note": {"type": "string"},
    }
    if event_types:
        properties["replacement_event_type"] = _enum_string_schema(event_types)

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": [
            "proposal_id",
            "action",
        ],
    }


def _compact_storyteller_vocabulary(
    dbname: Optional[str],
) -> tuple[list[str], list[str], list[str]]:
    if not dbname:
        return [], [], []
    try:
        tags_by_kind = _read_tags_by_kind(dbname)
        tag_names = sorted({tag for tags in tags_by_kind.values() for tag in tags})
        pair_tag_names = _read_pair_tags(dbname)
        event_types = _read_event_types(dbname)
    except Exception as exc:
        logger.warning(
            "Failed to load compact Anthropic storyteller vocab enums: %s",
            exc,
        )
        return [], [], []
    return tag_names, pair_tag_names, event_types


def _read_tags_by_kind(dbname: str) -> dict[str, list[str]]:
    tags_by_kind = {kind: [] for kind in _KIND_DEF_NAMES}
    for entry in read_tag_library(dbname):
        tags_by_kind.setdefault(entry.entity_kind, []).append(entry.tag)
    return {
        kind: sorted(dict.fromkeys(tags))
        for kind, tags in tags_by_kind.items()
        if kind in _KIND_DEF_NAMES
    }


def _read_pair_tags(dbname: str) -> list[str]:
    return read_pair_tag_library(dbname)


def _read_event_types(dbname: str) -> list[str]:
    return read_event_types(dbname)


def _bestowal_def_with_tag_enum(
    base_bestowal: Mapping[str, Any], tags: list[str], *, entity_kind: str
) -> Dict[str, Any]:
    bestowal = deepcopy(dict(base_bestowal))
    bestowal["title"] = _KIND_DEF_NAMES[entity_kind]
    bestowal["description"] = (
        f"{base_bestowal.get('description', '')}\n\n"
        f"Runtime constraint: tag names must be registered {entity_kind} tags "
        "from this slot."
    ).strip()
    properties = bestowal.get("properties", {})
    if isinstance(properties, dict):
        for field_name in ("applied_tags", "tags_to_clear"):
            field_schema = properties.get(field_name)
            if isinstance(field_schema, dict):
                items = field_schema.setdefault("items", {})
                if isinstance(items, dict):
                    items["type"] = "string"
                    items["enum"] = tags
    return bestowal


def _replace_owner_bestowal_ref(
    defs: Dict[str, Any], *, owner_def: str, target_def: str
) -> bool:
    owner_schema = defs.get(owner_def)
    if not isinstance(owner_schema, dict):
        return False
    properties = owner_schema.get("properties")
    if not isinstance(properties, dict):
        return False
    bestowal_field = properties.get("orrery_tags")
    if not isinstance(bestowal_field, dict):
        return False
    return _replace_bestowal_ref(bestowal_field, target_def=target_def)


def _replace_bestowal_ref(schema: Any, *, target_def: str) -> bool:
    if isinstance(schema, dict):
        if schema.get("$ref") == "#/$defs/OrreryTagBestowal":
            schema["$ref"] = f"#/$defs/{target_def}"
            return True
        return any(
            _replace_bestowal_ref(value, target_def=target_def)
            for value in schema.values()
        )
    if isinstance(schema, list):
        return any(
            _replace_bestowal_ref(item, target_def=target_def) for item in schema
        )
    return False
