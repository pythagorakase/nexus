"""Shared configuration utilities for API modules."""

import logging
from typing import Dict, Any

from nexus.config import load_settings_as_dict

logger = logging.getLogger("nexus.api.config_utils")


def get_new_story_model() -> str:
    """Get the configured model for new story workflow."""
    settings = load_settings_as_dict()
    return settings.get("API Settings", {}).get("new_story", {}).get("model", "gpt-5.1")


def get_max_choice_text_length() -> int:
    """Get the maximum allowed length for choice selection text."""
    settings = load_settings_as_dict()
    return (
        settings.get("api", {})
        .get("constraints", {})
        .get("max_choice_text_length", 1000)
    )
