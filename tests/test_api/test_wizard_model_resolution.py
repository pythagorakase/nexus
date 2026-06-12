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
from nexus.api.wizard_chat import resolve_wizard_model, wizard_model_lock_candidate


def test_chat_request_model_defaults_to_none() -> None:
    """Omitted model stays None so the slot's stamped model can win."""
    request = ChatRequest(slot=5, message="hello")
    assert request.model is None


def test_chat_request_rejects_unknown_model() -> None:
    with pytest.raises(ValidationError, match="Invalid model"):
        ChatRequest(slot=5, message="hello", model="not-a-registry-id")


def test_chat_request_accepts_explicit_test_model() -> None:
    """TEST stays available as an explicit, backend-only override.

    Requires the test provider entry in nexus.toml's api_models registry;
    validate_model checks against get_available_api_models().
    """
    request = ChatRequest(slot=5, message="hello", model="TEST")
    assert request.model == "TEST"


def test_start_setup_request_model_defaults_to_none() -> None:
    request = StartSetupRequest(slot=5)
    assert request.model is None


def test_configured_wizard_default_is_not_the_mock() -> None:
    """The resolved wizard.default_model must be a real model, never TEST."""
    assert get_new_story_model() != "TEST"


def test_resolve_wizard_model_explicit_override_wins() -> None:
    assert resolve_wizard_model("explicit-model", "slot-model") == "explicit-model"


def test_resolve_wizard_model_falls_back_to_slot_stamp() -> None:
    """Omitted request model resolves to the slot's stamped (locked) model."""
    assert resolve_wizard_model(None, "slot-model") == "slot-model"


def test_resolve_wizard_model_falls_back_to_configured_default() -> None:
    resolved = resolve_wizard_model(None, None)
    assert resolved == get_new_story_model()
    assert resolved != "TEST"


def test_omitted_model_is_never_a_lock_conflict() -> None:
    """Normal UI requests (no model) can never trip the 409 model lock."""
    assert wizard_model_lock_candidate(None, "slot-model") is False
    assert wizard_model_lock_candidate(None, None) is False


def test_matching_override_is_not_a_lock_conflict() -> None:
    assert wizard_model_lock_candidate("slot-model", "slot-model") is False


def test_differing_override_is_a_lock_conflict_candidate() -> None:
    assert wizard_model_lock_candidate("other-model", "slot-model") is True
