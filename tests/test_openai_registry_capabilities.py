"""Offline capability contracts using the real configured provider and builders."""

import pytest
from pydantic import BaseModel

from scripts.api_openai import OpenAIProvider


class Output(BaseModel):
    text: str


@pytest.mark.parametrize(
    "model,temperature",
    [
        ("gpt-6-astra", False),  # pin: regression for registry-based Astra capabilities
        ("TEST", True),
    ],
)
def test_registry_controls_request_parameters(model, temperature):
    provider = OpenAIProvider(
        model=model,
        api_key="unused-offline",
        temperature=0.5,
        reasoning_effort="low",
        request_params={"temperature": 0.7, "top_p": 0.9},
    )
    assert provider.supports_temperature is temperature
    native = provider._build_native_structured_request_params("test", Output)
    chat = provider._build_chat_structured_request_params("test", Output)
    for params in (native, chat):
        assert ("temperature" in params) is temperature
        if not temperature:
            assert "top_p" not in params
            assert "temperature" not in params.get("extra_body", {})
            assert "top_p" not in params.get("extra_body", {})
    assert ("reasoning" in native) is (model != "TEST")
    provider.client.close()


def test_unregistered_model_fails_with_registry_guidance():
    with pytest.raises(ValueError, match=r"global.model.api_models"):
        OpenAIProvider(model="unregistered-800b", api_key="unused-offline")


def test_default_provider_and_cli_use_registered_judgment_model():
    from nexus.config import load_settings
    from scripts.api_openai import get_default_llm_argument_parser

    provider = OpenAIProvider(api_key="unused-offline")
    try:
        assert provider.model == load_settings().ir_eval.judgment.model
        assert get_default_llm_argument_parser().parse_args([]).model is None
    finally:
        provider.client.close()


def test_ir_judge_default_constructs_without_network():
    """Isolate the legacy CLI's sys.path setup and construct its real provider."""
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'ir_eval/scripts'); "
            "from ir_eval.scripts.auto_judge import AIJudge; "
            "from nexus.config import load_settings; "
            "judge = AIJudge(); "
            "assert judge.model == load_settings().ir_eval.judgment.model; "
            "assert judge.provider.model == judge.model; judge.provider.client.close()",
        ],
        env={
            **os.environ,
            "NEXUS_KEYRING_DISABLE": "1",
            "OPENAI_API_KEY": "unused-offline",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
