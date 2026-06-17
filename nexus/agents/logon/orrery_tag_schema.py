"""Runtime JSON Schema constraints for storyteller Orrery tag bestowals."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Dict, Mapping, Optional, Type

from pydantic import BaseModel

from nexus.agents.orrery.tag_library import read_tag_library
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

    schema = storyteller_schema_with_runtime_tag_enums(schema_model, dbname)
    if schema is None:
        return None
    return anthropic_output_config(schema_model, schema=schema)


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


def _read_tags_by_kind(dbname: str) -> dict[str, list[str]]:
    tags_by_kind = {kind: [] for kind in _KIND_DEF_NAMES}
    for entry in read_tag_library(dbname):
        tags_by_kind.setdefault(entry.entity_kind, []).append(entry.tag)
    return {
        kind: sorted(dict.fromkeys(tags))
        for kind, tags in tags_by_kind.items()
        if kind in _KIND_DEF_NAMES
    }


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
