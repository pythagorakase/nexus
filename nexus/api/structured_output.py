"""Schema helpers for structured output across providers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


STRUCTURED_OUTPUT_BETA = "structured-outputs-2025-11-13"

SUPPORTED_STRING_FORMATS = {
    "date-time",
    "time",
    "date",
    "duration",
    "email",
    "hostname",
    "uri",
    "ipv4",
    "ipv6",
    "uuid",
}

UNSUPPORTED_KEYS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "maxItems",
    "uniqueItems",
    "minContains",
    "maxContains",
    "contains",
    "patternProperties",
    "propertyNames",
    "dependencies",
    "dependentRequired",
    "dependentSchemas",
    "unevaluatedProperties",
    "unevaluatedItems",
    "if",
    "then",
    "else",
}


def make_anthropic_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize a JSON schema for Anthropic structured outputs."""
    return _sanitize_schema(deepcopy(schema))


def _sanitize_schema(node: Any) -> Any:
    if isinstance(node, list):
        return [_sanitize_schema(item) for item in node]

    if not isinstance(node, dict):
        return node

    for key in list(node.keys()):
        if key in UNSUPPORTED_KEYS:
            node.pop(key, None)
        elif key == "minItems":
            if node.get("minItems") not in (0, 1):
                node.pop("minItems", None)
        elif key == "format":
            if node.get("type") == "string" and node.get("format") not in SUPPORTED_STRING_FORMATS:
                node.pop("format", None)

    if node.get("type") == "object" or "properties" in node:
        node.setdefault("additionalProperties", False)

    for key, value in list(node.items()):
        if isinstance(value, (dict, list)):
            node[key] = _sanitize_schema(value)

    return node
