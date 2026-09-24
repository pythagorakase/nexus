"""Real renderer and deterministic TEST tokenizer for offline window tests."""

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.config import load_settings_as_dict
from nexus.config.story_model import StorySettings


def window_logon(settings=None):
    """Create the real TEST route without a story database or generation call."""
    settings = settings or load_settings_as_dict()
    utility = LogonUtility(
        settings, model_override="TEST", story_settings=StorySettings()
    )
    utility._setting_context_loaded = True
    return utility
