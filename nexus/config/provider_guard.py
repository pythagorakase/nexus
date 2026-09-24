"""Fail closed before a test session can construct a non-TEST provider."""

import os

from nexus.config.loader import load_settings
from nexus.config.settings_models import Settings


class ProviderForbiddenInTests(RuntimeError):
    """A test attempted to initialize a provider outside the TEST registry."""


def require_test_provider(model: str, *, settings: Settings | None = None) -> None:
    """Check registry identity before creating any network client or reading keys."""
    if os.environ.get("NEXUS_TEST_PROVIDER_ONLY") != "1":
        return
    settings = settings or load_settings()
    try:
        provider = settings.provider_for_model(model)
    except ValueError:
        provider = None
    if provider != "test":
        raise ProviderForbiddenInTests(
            f"Model {model!r} (provider={provider!r}) is forbidden by "
            "NEXUS_TEST_PROVIDER_ONLY=1"
        )
