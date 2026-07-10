"""Live structured-output verification against the registered LM Studio model."""

from __future__ import annotations

import pytest
import requests

from nexus.agents.logon.apex_schema import StorytellerResponseBootstrap
from nexus.config import get_openai_compatible_endpoint, resolve_model_ref
from scripts.api_openai import OpenAIProvider

pytestmark = pytest.mark.live_llm


def _require_lmstudio_model(base_url: str, model: str) -> None:
    """Skip clearly when LM Studio or the configured model is unavailable."""
    models_url = f"{base_url.rstrip('/')}/models"
    try:
        response = requests.get(models_url, timeout=2)
        response.raise_for_status()
    except requests.RequestException as exc:
        pytest.skip(f"LM Studio models endpoint is unreachable at {models_url}: {exc}")

    listed_models = {
        entry.get("id")
        for entry in response.json().get("data", [])
        if isinstance(entry, dict)
    }
    if model not in listed_models:
        pytest.skip(f"LM Studio does not list the configured model {model!r}")


def test_lmstudio_bootstrap_structured_completion_live() -> None:
    """Generate and validate the Bootstrap schema through Chat Completions."""
    model = resolve_model_ref("@lmstudio.default")
    endpoint = get_openai_compatible_endpoint(model)
    assert endpoint is not None
    _require_lmstudio_model(endpoint["base_url"], model)

    provider = OpenAIProvider(
        model=model,
        base_url=endpoint["base_url"],
        api_key=endpoint["api_key"],
        structured_transport=endpoint["structured_transport"],
        max_output_tokens=600,
        temperature=0.1,
    )
    parsed, _response = provider.get_structured_completion(
        "Write a two-sentence opening about a traveler arriving at a quiet inn. "
        "Offer exactly two concise, actionable player choices.",
        StorytellerResponseBootstrap,
    )

    assert isinstance(parsed, StorytellerResponseBootstrap)
    StorytellerResponseBootstrap.model_validate(parsed.model_dump())
