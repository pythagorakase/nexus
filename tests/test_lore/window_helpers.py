"""Real renderer and deterministic TEST tokenizer for offline window tests."""

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.config import load_settings
from nexus.config.settings_models import Settings
from nexus.config.story_model import StorySettings


def window_logon(settings: Settings | None = None) -> LogonUtility:
    """Create the real TEST route without a story database or generation call."""
    settings = settings or load_settings()
    utility = LogonUtility(
        settings, model_override="TEST", story_settings=StorySettings()
    )
    utility._setting_context_loaded = True
    return utility
