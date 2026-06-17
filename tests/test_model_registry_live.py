"""Live verification for the model registry endpoint/param-capability work (#401).

These tests make REAL calls:

- the Orrery narration provider built from shipped nexus.toml settings must
  succeed against the configured Anthropic narration model (the golden-gate
  failure case was ``temperature=0.4`` hardcoded into the request);
- the rejection itself is reproduced live, proving the registry's
  ``unsupported_params`` declaration matches provider behavior;
- an ``@openai.default`` role call still works through the OpenAI provider;
- the TEST model works through an OpenAI-compatible server registered via the
  first-class ``base_url`` registry field (a real mock_openai process).

Run with: NEXUS_RUN_LIVE_LLM=1 python -m pytest tests/test_model_registry_live.py
"""

from __future__ import annotations

import copy
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
import requests

from nexus.config import load_settings
from nexus.config.settings_models import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_PORT = 5133  # lane-assigned test port; never the dev stack's 5102

pytestmark = pytest.mark.live_llm


def _nexus_toml_dict() -> dict:
    with open(REPO_ROOT / "nexus.toml", "rb") as handle:
        return tomllib.load(handle)


def test_narration_provider_succeeds_against_configured_anthropic_model():
    """The exact failing call from issue #401, rebuilt from shipped config.

    ``_narration_provider`` previously hardcoded ``temperature=0.4``, which the
    Anthropic model selected in commit 2a1f15d4 rejects with a 400. With
    sampling params sourced from [orrery.narration] (unset by default), the
    real call must succeed.
    """
    from nexus.agents.orrery.worker import _narration_provider

    settings = load_settings(REPO_ROOT / "nexus.toml")
    narration = settings.orrery.narration.model_copy(
        update={"max_output_tokens": 64}  # keep the live call cheap
    )
    provider = _narration_provider({"orrery": {"narration": narration}})

    response = provider.get_completion(
        "Write one sentence describing a courier crossing a rainy plaza."
    )
    assert response.content.strip(), "narration provider returned empty text"
    assert provider.temperature is None, "no temperature configured, none sent"


def test_temperature_rejected_live_matches_registry_declaration():
    """Prove unsupported_params is true: temperature really 400s on the model."""
    import anthropic

    from scripts.api_anthropic import AnthropicProvider

    settings = load_settings(REPO_ROOT / "nexus.toml")
    model = settings.orrery.narration.model_ref
    assert "temperature" in settings.model_entry(model).unsupported_params

    provider = AnthropicProvider(model=model, temperature=0.4, max_tokens=16)
    with pytest.raises(anthropic.BadRequestError, match="temperature"):
        provider.get_completion("Say OK.")


def test_openai_default_role_still_works():
    """An @openai role resolves and completes through the OpenAI provider."""
    from scripts.api_openai import OpenAIProvider

    settings = load_settings(REPO_ROOT / "nexus.toml")
    model = settings.resolve_model_ref("@openai.default")

    provider = OpenAIProvider(model=model, max_output_tokens=64)
    # The provider's reasoning-model detection must suppress temperature for
    # models whose registry entry rejects it.
    if "temperature" in settings.model_entry(model).unsupported_params:
        assert provider.supports_temperature is False

    response = provider.get_completion("Reply with the single word: ready")
    assert response.content.strip(), "OpenAI provider returned empty text"


def test_test_model_via_registry_base_url_against_real_mock_server():
    """The TEST model routes through a registry base_url to a real local server."""
    from scripts.api_openai import OpenAIProvider

    raw = copy.deepcopy(_nexus_toml_dict())
    raw["global"]["model"]["api_models"]["test"][
        "base_url"
    ] = f"http://127.0.0.1:{MOCK_PORT}/v1"
    raw["runtime"]["services"]["mock_openai"]["port"] = MOCK_PORT
    settings = Settings(**raw)
    entry = settings.global_.model.api_models["test"]

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "nexus.api.mock_openai:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(MOCK_PORT),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                if (
                    requests.get(
                        f"http://127.0.0.1:{MOCK_PORT}/health", timeout=1
                    ).status_code
                    == 200
                ):
                    break
            except requests.ConnectionError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError("mock_openai did not become healthy in 30s")
            time.sleep(0.25)

        provider = OpenAIProvider(
            model="TEST",
            base_url=entry.base_url,
            api_key="nexus-local-no-key",
            max_output_tokens=64,
        )
        response = provider.get_completion("ping")
        assert response.content.strip(), "mock server returned empty text"
    finally:
        server.terminate()
        server.wait(timeout=10)
