"""Pydantic-AI wiring regressions."""

import pytest

from nexus.api import pydantic_ai_utils


def test_build_pydantic_ai_model_requires_base_url_for_non_native(monkeypatch):
    """Non-native providers must resolve to an OpenAI-compatible endpoint."""

    monkeypatch.setattr(
        pydantic_ai_utils, "get_provider_for_model", lambda model: "local"
    )
    monkeypatch.setattr(
        pydantic_ai_utils, "get_openai_compatible_endpoint", lambda model: None
    )

    with pytest.raises(ValueError, match="No base_url registry entry"):
        pydantic_ai_utils.build_pydantic_ai_model("LOCAL")
