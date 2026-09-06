"""Fail before turn work when the caller omitted a canonical attempt identity."""

import asyncio

import pytest

from nexus.agents.lore.lore import LORE


@pytest.mark.parametrize("attempt_id", [None, 7, "", "turn_123", "conversation-id"])
def test_invalid_attempt_identity_rejects_before_turn_initialization(
    attempt_id: object,
) -> None:
    """Missing or conversation-style identities cannot reach memory/provider work."""
    lore = object.__new__(LORE)
    with pytest.raises(ValueError):
        asyncio.run(lore.process_turn("Continue.", attempt_id=attempt_id))
    assert not hasattr(lore, "turn_context")


def test_attempt_identity_is_required_for_direct_callers() -> None:
    """Direct diagnostic callers must supply an identity instead of minting one."""
    lore = object.__new__(LORE)
    with pytest.raises(TypeError, match="attempt_id"):
        asyncio.run(lore.process_turn("Continue."))
