"""Persist wizard message provenance without changing model-facing history."""

import json
from typing import Literal, Mapping, Sequence

MessageOrigin = Literal["user", "wizard_control"]
_ENVELOPE_PREFIX = "NEXUS_WIZARD_MESSAGE_V1\n"

# Frozen pre-provenance UI/CLI messages, not a general [SYSTEM] prefix filter.
# Identical human-authored legacy text cannot be distinguished retrospectively;
# explicitly tagged user messages always win, even when their text is identical.
_LEGACY_CONTROLS = frozenset(
    {
        "[SYSTEM] Phase setting complete. Proceeding to character. "
        "Please introduce the next phase.",
        "[SYSTEM] Phase character complete. Proceeding to seed. "
        "Please introduce the next phase.",
        "[SYSTEM] Phase character subphase traits complete. "
        "Proceeding to wildcard. Please introduce the next subphase.",
        "[SYSTEM] Artifact submit_character_concept confirmed. Proceed to next step.",
        "[SYSTEM] Artifact submit_trait_selection confirmed. Proceed to next step.",
        "[SYSTEM] Artifact submit_wildcard_trait confirmed. Proceed to next step.",
    }
)


def encode_wizard_message(content: str, origin: MessageOrigin) -> str:
    """Wrap every new wizard input, including literal control/envelope text."""
    if origin not in {"user", "wizard_control"}:
        raise ValueError("Invalid wizard message origin")
    return _ENVELOPE_PREFIX + json.dumps(
        {"origin": origin, "content": content}, ensure_ascii=False
    )


def decode_wizard_message(content: str) -> tuple[str, MessageOrigin | None]:
    """Decode one storage envelope; never interpret its inner player text."""
    if not content.startswith(_ENVELOPE_PREFIX):
        return content, None
    payload = json.loads(content[len(_ENVELOPE_PREFIX) :])
    if (
        not isinstance(payload, dict)
        or set(payload) != {"origin", "content"}
        or payload["origin"] not in {"user", "wizard_control"}
        or not isinstance(payload["content"], str)
    ):
        raise ValueError("Invalid stored wizard message envelope")
    return payload["content"], payload["origin"]


def visible_wizard_messages(
    messages: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Project chronological history for the player without changing storage."""
    visible = []
    for message in messages:
        role = message["role"]
        if role not in {"user", "assistant"}:
            continue
        if role == "user":
            origin = message.get("origin")
            if origin == "wizard_control":
                continue
            if origin is None and message["content"] in _LEGACY_CONTROLS:
                continue
        visible.append({"role": role, "content": message["content"]})
    return visible
