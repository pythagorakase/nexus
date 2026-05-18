"""Shared helpers for Storyteller-authored retrieval directives."""

from __future__ import annotations

import json
from typing import Any, List


def normalize_authorial_directives(
    raw_directives: Any, *, allow_json_string: bool = False
) -> List[str]:
    """Return trimmed, non-empty authorial directives.

    Runtime DB paths may receive JSONB values as decoded lists or as serialized
    JSON strings depending on driver boundaries. Structured response paths pass
    lists directly and should leave JSON-string coercion disabled.
    """

    if isinstance(raw_directives, str) and allow_json_string:
        try:
            raw_directives = json.loads(raw_directives)
        except json.JSONDecodeError:
            raw_directives = [raw_directives]

    if not isinstance(raw_directives, list):
        return []

    return [
        directive.strip()
        for directive in raw_directives
        if isinstance(directive, str) and directive.strip()
    ]
