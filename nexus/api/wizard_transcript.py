"""Typed slot-database wizard messages and their player-visible projection."""

from typing import Literal, Mapping, NotRequired, Sequence, TypedDict

MessageOrigin = Literal["user", "wizard_control"]


class WizardMessage(TypedDict):
    """A verbatim transcript message with its phase and input provenance."""

    role: str
    content: str
    phase: str
    origin: NotRequired[MessageOrigin]


def visible_wizard_messages(
    messages: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Project chronological history for the player without changing storage."""
    return [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message["role"] in {"user", "assistant"}
        and not (
            message["role"] == "user" and message.get("origin") == "wizard_control"
        )
    ]
