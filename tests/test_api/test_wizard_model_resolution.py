"""
Regression tests for wizard default-model resolution.

The wizard UI no longer carries a model picker; clients omit `model` and the
backend resolves it: explicit request override -> slot's stamped model
(locked at setup start) -> configured wizard default from nexus.toml. The
mock TEST server must never be selected implicitly.
"""

import pytest
from pydantic import ValidationError

from nexus.api.config_utils import get_new_story_model
from nexus.api.narrative_schemas import ChatRequest, StartSetupRequest


def test_chat_request_model_defaults_to_none() -> None:
    """Omitted model stays None so the slot's stamped model can win."""
    request = ChatRequest(slot=5, message="hello")
    assert request.model is None


def test_chat_request_rejects_unknown_model() -> None:
    with pytest.raises(ValidationError, match="Invalid model"):
        ChatRequest(slot=5, message="hello", model="not-a-registry-id")


def test_chat_request_accepts_explicit_test_model() -> None:
    """TEST stays available as an explicit, backend-only override."""
    request = ChatRequest(slot=5, message="hello", model="TEST")
    assert request.model == "TEST"


def test_start_setup_request_model_defaults_to_none() -> None:
    request = StartSetupRequest(slot=5)
    assert request.model is None


def test_configured_wizard_default_is_not_the_mock() -> None:
    """The resolved wizard.default_model must be a real model, never TEST."""
    assert get_new_story_model() != "TEST"
