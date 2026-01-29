"""Shared configuration utilities for API modules."""

import logging
from typing import Dict, Any

from nexus.config import load_settings, load_settings_as_dict
from nexus.config.settings_models import WizardSettings

logger = logging.getLogger("nexus.api.config_utils")


def get_wizard_settings() -> WizardSettings:
    """Get the wizard configuration from nexus.toml."""
    settings = load_settings()
    return settings.wizard


def get_new_story_model() -> str:
    """Get the configured model for new story workflow."""
    return get_wizard_settings().default_model


def get_wizard_history_limit() -> int:
    """Get the wizard message history limit."""
    return get_wizard_settings().message_history_limit


def get_wizard_retry_budget() -> int:
    """Get the wizard tool retry budget."""
    return get_wizard_settings().max_retries


def get_wizard_max_tokens() -> int:
    """Get the wizard max output tokens setting."""
    return get_wizard_settings().max_tokens


def get_wizard_streaming_enabled() -> bool:
    """Return whether the wizard streaming endpoint is enabled."""
    return get_wizard_settings().enable_streaming


def get_max_choice_text_length() -> int:
    """Get the maximum allowed length for choice selection text."""
    settings = load_settings_as_dict()
    return (
        settings.get("api", {})
        .get("constraints", {})
        .get("max_choice_text_length", 1000)
    )
