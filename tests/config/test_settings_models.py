"""Tests for configuration schema validation."""

import tomllib

import pytest
import tomlkit
from pydantic import ValidationError

from nexus.config import (
    get_gateway_cors_allowed_origins,
    get_native_structured_output_override,
    load_settings,
    resolve_model_ref,
)
from nexus.config.settings_models import (
    APIModelEntry,
    ModelConfig,
    ProviderModels,
    RuntimeServiceSettings,
    Settings,
)


def _nexus_toml_dict() -> dict:
    with open("nexus.toml", "rb") as handle:
        return tomllib.load(handle)


def test_model_config_rejects_unknown_default_model():
    """Legacy display defaults must stay anchored to registered model IDs."""
    with pytest.raises(ValidationError, match="default_model references unknown"):
        ModelConfig(
            default_model="missing-model",
            default_slot_model="TEST",
            api_models={
                "test": ProviderModels(
                    roles={"default": "TEST"},
                    models=[APIModelEntry(id="TEST", label="TEST")],
                    base_url="http://127.0.0.1:5102/v1",
                )
            },
        )


def test_model_config_defers_role_references_to_settings_resolution():
    """ "@provider.role" defaults pass ModelConfig and resolve on the root model."""
    config = ModelConfig(
        default_model="@test.default",
        default_slot_model="TEST",
        api_models={
            "test": ProviderModels(
                roles={"default": "TEST"},
                models=[APIModelEntry(id="TEST", label="TEST")],
                base_url="http://127.0.0.1:5102/v1",
            )
        },
    )
    assert config.default_model == "@test.default"


def test_global_default_model_resolves_at_load():
    """nexus.toml's display default is a role reference resolved at load."""
    raw = _nexus_toml_dict()
    raw_default = raw["global"]["model"]["default_model"]
    assert raw_default.startswith("@"), (
        "global.model.default_model should be an @provider.role reference in "
        f"nexus.toml, found literal '{raw_default}'"
    )

    settings = load_settings("nexus.toml")
    openai_default = settings.global_.model.api_models["openai"].roles["default"]
    assert settings.global_.model.default_model == openai_default


def test_global_default_model_unknown_role_rejected():
    """An unknown role in the global display default fails Settings validation."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["default_model"] = "@openai.nonexistent_role"
    with pytest.raises(ValidationError, match="no role 'nonexistent_role'"):
        Settings(**raw)


def test_global_default_slot_model_unknown_role_rejected():
    """An unknown role in the slot default fails Settings validation too."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["default_slot_model"] = "@test.nonexistent_role"
    with pytest.raises(ValidationError, match="no role 'nonexistent_role'"):
        Settings(**raw)


def test_llama_server_port_drift_rejected_when_enabled():
    """An enabled llama_server whose port differs from the local base_url fails."""
    raw = _nexus_toml_dict()
    raw["runtime"]["services"]["llama_server"]["enabled"] = "always"
    raw["runtime"]["services"]["llama_server"]["port"] = 1299
    with pytest.raises(ValidationError, match="does not.*match the local provider"):
        Settings(**raw)


def test_llama_server_port_drift_ignored_while_disabled():
    """Port drift is tolerated while the service is disabled (nothing binds)."""
    raw = _nexus_toml_dict()
    raw["runtime"]["services"]["llama_server"]["port"] = 1299  # enabled stays "never"
    Settings(**raw)


def test_global_default_slot_model_role_ref_resolves_at_load():
    """A valid role ref in default_slot_model resolves to the concrete ID."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["default_slot_model"] = "@test.default"
    settings = Settings(**raw)
    test_default = settings.global_.model.api_models["test"].roles["default"]
    assert settings.global_.model.default_slot_model == test_default


def test_resolve_model_ref_resolves_roles_and_validates_literals():
    """The public resolver maps roles to concrete IDs and validates literals."""
    settings = load_settings("nexus.toml")
    anthropic_default = settings.global_.model.api_models["anthropic"].roles["default"]

    assert resolve_model_ref("@anthropic.default") == anthropic_default
    assert settings.resolve_model_ref("@anthropic.default") == anthropic_default
    # Literal registry IDs pass through unchanged.
    assert resolve_model_ref(anthropic_default) == anthropic_default

    with pytest.raises(ValueError, match="no role 'bogus'"):
        resolve_model_ref("@anthropic.bogus")
    with pytest.raises(ValueError, match="not declared"):
        resolve_model_ref("model-that-does-not-exist")


def test_ui_visible_filters_ui_model_lists_but_not_registry():
    """ui_visible = false hides a provider from UI lists, not the registry.

    The TEST mock server stays fully functional for backend/CLI callers
    (unfiltered loader calls, role resolution) while every UI-facing model
    list - /api/config/models and the settings pane metadata - omits it.
    """
    from nexus.config.loader import get_all_api_models, get_api_models_by_provider

    settings = load_settings("nexus.toml")
    assert settings.global_.model.api_models["test"].ui_visible is False
    assert settings.global_.model.api_models["anthropic"].ui_visible is True

    all_ids = {m["id"] for m in get_all_api_models()}
    ui_ids = {m["id"] for m in get_all_api_models(ui_only=True)}
    assert "TEST" in all_ids
    assert "TEST" not in ui_ids
    assert ui_ids == all_ids - {"TEST"}

    assert "test" not in get_api_models_by_provider(ui_only=True)
    assert "test" in get_api_models_by_provider()

    # Backend role resolution is untouched by UI visibility.
    assert resolve_model_ref("@test.default") == "TEST"


# =============================================================================
# Registry base_url + per-model parameter capability (#401)
# =============================================================================


def test_non_native_provider_requires_base_url():
    """Providers outside the native SDK set must declare an endpoint."""
    raw = _nexus_toml_dict()
    del raw["global"]["model"]["api_models"]["test"]["base_url"]
    with pytest.raises(ValidationError, match="must declare a base_url"):
        Settings(**raw)


def test_structured_transport_defaults_to_responses():
    """Providers keep the Responses structured-output surface by default."""
    provider = ProviderModels()

    assert provider.structured_transport == "responses"


def test_request_timeout_parses_and_defaults_to_none():
    """Base URL providers may override the SDK request timeout."""
    assert ProviderModels().request_timeout_seconds is None

    provider = ProviderModels(
        base_url="http://127.0.0.1:1234/v1",
        request_timeout_seconds=1800,
    )

    assert provider.request_timeout_seconds == 1800


def test_chat_completions_structured_transport_requires_base_url():
    """A native provider cannot opt into the local-server transport."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["api_models"]["anthropic"][
        "structured_transport"
    ] = "chat_completions"

    with pytest.raises(
        ValidationError,
        match="structured_transport='chat_completions' requires a base_url",
    ):
        Settings(**raw)


def test_chat_completions_structured_transport_accepts_base_url():
    """An OpenAI-compatible base_url provider may use Chat Completions."""
    provider = ProviderModels(
        base_url="http://127.0.0.1:1234/v1",
        structured_transport="chat_completions",
    )

    assert provider.structured_transport == "chat_completions"


def test_native_provider_rejects_base_url():
    """Native SDK providers use their own endpoints; base_url is a config error."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["api_models"]["openai"]["base_url"] = "http://x/v1"
    with pytest.raises(ValidationError, match="base_url is not allowed"):
        Settings(**raw)


def test_configured_param_rejected_when_model_declares_it_unsupported():
    """[orrery.narration] temperature on a temperature-rejecting model fails load.

    This is the #401 proving instance: the narration model resolves to a model
    whose registry entry lists 'temperature' in unsupported_params, so setting
    temperature in nexus.toml must be refused at config load, not at request
    time.
    """
    raw = _nexus_toml_dict()
    narration_model = Settings(**raw).orrery.narration.model_ref
    assert "temperature" in {
        p
        for provider in Settings(**raw).global_.model.api_models.values()
        for entry in provider.models
        if entry.id == narration_model
        for p in entry.unsupported_params
    }, f"expected nexus.toml to declare temperature unsupported for {narration_model}"

    raw["orrery"]["narration"]["temperature"] = 0.4
    with pytest.raises(ValidationError, match="declares 'temperature' unsupported"):
        Settings(**raw)


def test_configured_param_allowed_when_model_supports_it():
    """A supporting model (Sonnet 4.6) accepts a configured temperature."""
    raw = _nexus_toml_dict()
    raw["orrery"]["narration"]["model_ref"] = "claude-sonnet-4-6"
    raw["orrery"]["narration"]["temperature"] = 0.4
    settings = Settings(**raw)
    assert settings.orrery.narration.temperature == 0.4


def test_narration_temperature_unset_by_default():
    """Shipped config omits narration temperature so the param is never sent."""
    settings = load_settings("nexus.toml")
    assert settings.orrery.narration.temperature is None


def test_get_openai_compatible_endpoint_routing():
    """Registry base_url providers resolve to an endpoint; native ones do not."""
    from nexus.config import get_openai_compatible_endpoint

    settings = load_settings("nexus.toml")
    endpoint = get_openai_compatible_endpoint("TEST")
    assert endpoint == {
        "base_url": settings.global_.model.api_models["test"].base_url,
        "api_key": "nexus-local-no-key",
        "structured_transport": "responses",
        "request_timeout_seconds": None,
    }
    local = settings.global_.model.api_models["local"]
    assert resolve_model_ref("@local.default") == "nousresearch/hermes-4-70b"
    assert get_openai_compatible_endpoint(local.roles["default"]) == {
        "base_url": local.base_url,
        "api_key": "nexus-local-no-key",
        "structured_transport": "chat_completions",
        "request_timeout_seconds": 1800,
    }
    assert get_openai_compatible_endpoint("gpt-5.5") is None
    assert get_openai_compatible_endpoint("claude-opus-4-8") is None
    # Models absent from the registry are treated as native/legacy overrides.
    assert get_openai_compatible_endpoint("unregistered-model") is None


def test_llama_server_runtime_service_parses():
    """The local llama-server is a disabled-by-default managed service."""
    service = load_settings("nexus.toml").runtime.services["llama_server"]

    assert isinstance(service, RuntimeServiceSettings)
    assert service.command[0] == "/opt/homebrew/bin/llama-server"
    assert service.enabled == "never"
    assert service.port == 1234
    assert service.health_path == "/health"


def test_native_structured_output_override_parses_and_resolves(tmp_path, monkeypatch):
    """Registry entries expose explicit true/false and default to None."""
    assert (
        APIModelEntry(
            id="forced-on", label="Forced on", native_structured_output=True
        ).native_structured_output
        is True
    )
    assert (
        APIModelEntry(id="upstream", label="Upstream").native_structured_output is None
    )

    raw = _nexus_toml_dict()
    models = raw["global"]["model"]["api_models"]["anthropic"]["models"]
    models[0]["native_structured_output"] = True
    models[1]["native_structured_output"] = False
    models[2].pop("native_structured_output", None)
    config = tmp_path / "runtime.toml"
    config.write_text(tomlkit.dumps(raw))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))

    assert get_native_structured_output_override(models[0]["id"]) is True
    assert get_native_structured_output_override(models[1]["id"]) is False
    assert get_native_structured_output_override(models[2]["id"]) is None
    assert get_native_structured_output_override("unregistered-model") is None


def test_shipped_anthropic_models_decide_native_structured_output_support():
    """Every shipped Anthropic model carries an explicit #454 decision."""
    entries = load_settings("nexus.toml").global_.model.api_models["anthropic"].models
    expected_ids = {
        "claude-sonnet-4-6",
        "claude-opus-4-8",
        "claude-fable-5",
    }

    assert expected_ids <= {entry.id for entry in entries}
    assert all(entry.native_structured_output is not None for entry in entries)
    assert all(
        entry.native_structured_output is True
        for entry in entries
        if entry.id in expected_ids
    )


def test_default_load_honors_runtime_config_env(tmp_path, monkeypatch):
    """Managed services use the config path exported by the supervisor."""
    from nexus.config import get_openai_compatible_endpoint
    from nexus.config.loader import get_provider_for_model

    raw = _nexus_toml_dict()
    raw["global"]["model"]["default_slot_model"] = "TEMPTEST"
    raw["global"]["model"]["api_models"]["test"]["roles"]["default"] = "TEMPTEST"
    raw["global"]["model"]["api_models"]["test"]["models"][0]["id"] = "TEMPTEST"
    raw["global"]["model"]["api_models"]["test"][
        "base_url"
    ] = "http://127.0.0.1:5999/v1"
    raw["runtime"]["services"]["mock_openai"]["port"] = 5999
    config = tmp_path / "runtime.toml"
    config.write_text(tomlkit.dumps(raw))

    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))

    assert load_settings().global_.model.api_models["test"].models[0].id == "TEMPTEST"
    assert get_provider_for_model("TEMPTEST") == "test"
    assert get_openai_compatible_endpoint("TEMPTEST") == {
        "base_url": "http://127.0.0.1:5999/v1",
        "api_key": "nexus-local-no-key",
        "structured_transport": "responses",
        "request_timeout_seconds": None,
    }
    assert (
        load_settings("nexus.toml")
        .global_.model.api_models["test"]
        .base_url.endswith(":5102/v1")
    )


def test_gateway_cors_origins_parse_and_accessor_returns_default() -> None:
    """The shipped gateway allowlist is typed and exposed by its accessor."""
    expected = [
        "http://localhost:8002",
        "http://127.0.0.1:8002",
        "https://nexus.pythagora.net",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    settings = load_settings("nexus.toml")
    assert settings.runtime is not None
    assert settings.runtime.gateway.cors_allowed_origins == expected
    assert get_gateway_cors_allowed_origins() == expected


def test_gateway_cors_origins_reject_wildcard() -> None:
    """Credentialed CORS configuration fails loudly for a wildcard origin."""
    raw = _nexus_toml_dict()
    raw["runtime"]["gateway"]["cors_allowed_origins"] = ["*"]

    with pytest.raises(ValidationError, match="exact HTTP\\(S\\) origins"):
        Settings(**raw)
