"""
Pydantic models for NEXUS configuration validation.

These models provide type-safe, validated access to settings from nexus.toml.
All models use `extra='forbid'` to catch typos in configuration keys.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
import re
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# String prefix used for role references in consumer fields.
# Example: "@openai.default" resolves via api_models.openai.roles.default
MODEL_ROLE_PREFIX = "@"

# Providers with native SDK request paths. Every other provider in
# [global.model.api_models] is an OpenAI-compatible server and must declare a
# `base_url` (enforced by ``ModelConfig._validate_non_native_providers``).
NATIVE_API_PROVIDERS = frozenset({"openai", "anthropic"})


@dataclass
class _ModelRegistry:
    """Indexed view of [global.model.api_models] used during reference resolution.

    Built once per Settings load by ``Settings._build_model_registry`` and passed
    to ``_resolve_model_reference``. Replaces an earlier sentinel-keyed dict
    (``registry["_ids"]``) so the typing is honest and the consumer doesn't have
    to filter out a magic key when iterating providers.
    """

    roles: Dict[str, Dict[str, str]]  # provider name → {role_name → concrete_id}
    all_ids: Dict[str, str]  # concrete_id → provider, for error messages


# =============================================================================
# Global Settings Models
# =============================================================================


class APIModelEntry(BaseModel):
    """Single API model definition."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        ..., description="Concrete model identifier registered with this provider"
    )
    label: str = Field(..., description="Display label for UI")
    description: Optional[str] = Field(
        default=None, description="Human-readable description (optional)"
    )
    unsupported_params: List[str] = Field(
        default_factory=list,
        description=(
            "Request parameters this model's API rejects outright (e.g. "
            "'temperature' on reasoning-class models). Config load refuses any "
            "consumer field that configures one of these params for this model "
            "(see Settings._validate_param_capabilities); request builders only "
            "send explicitly configured params, so a rejected parameter can "
            "never reach the provider."
        ),
    )
    native_structured_output: Optional[bool] = Field(
        default=None,
        description=(
            "Override pydantic-ai's model-profile capability detection for "
            "native (grammar-level) structured output. True forces support ON "
            "for models the pinned pydantic-ai's allowlist predates (issue "
            "#454); False forces it OFF; None defers to pydantic-ai."
        ),
    )


class ProviderModels(BaseModel):
    """Models for a single API provider, plus named roles consumers can reference.

    Roles map symbolic names (e.g., "default", "fast", "deep") to concrete model
    IDs from this provider's `models` list. Consumer fields reference roles via
    "@provider.role" syntax (resolved at Settings load time).
    """

    model_config = ConfigDict(extra="forbid")

    roles: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Named roles mapping role name to a concrete model ID. The ID must "
            "appear in the `models` list. Consumers reference roles via "
            "'@provider.role' strings."
        ),
    )
    models: List[APIModelEntry] = Field(
        default_factory=list, description="List of models available from this provider"
    )
    ui_visible: bool = Field(
        default=True,
        description=(
            "Expose this provider's models in UI-facing pickers "
            "(/api/config/models, /api/settings settings_meta). Backend and "
            "CLI callers always see the full registry regardless of this flag."
        ),
    )
    base_url: Optional[str] = Field(
        default=None,
        description=(
            "OpenAI-compatible server base URL (e.g. 'http://127.0.0.1:5102/v1' "
            "for the mock server, or an Ollama/vLLM endpoint). Required for "
            "every provider outside NATIVE_API_PROVIDERS; requests for this "
            "provider's models are sent to this URL with the OpenAI client."
        ),
    )
    api_key_secret: Optional[str] = Field(
        default=None,
        description=(
            "Keychain account name (service 'nexus-api') holding the API key "
            "for a base_url provider, resolved via "
            "nexus.util.secret_manager.get_secret. Leave unset for servers "
            "that need no key (mock server, local Ollama/vLLM); a placeholder "
            "key is sent because OpenAI clients require a non-empty key."
        ),
    )
    structured_transport: Literal["responses", "chat_completions"] = Field(
        default="responses",
        description=(
            "OpenAI-compatible surface used for structured output. Use "
            "'chat_completions' for local servers such as llama-server, Ollama, "
            "or vLLM whose /v1/responses endpoint is missing or silently "
            "ignores text.format."
        ),
    )
    request_timeout_seconds: Optional[float] = Field(
        default=None,
        description=(
            "Override the OpenAI SDK's 600-second request timeout for slow "
            "local servers. None defers to the SDK default."
        ),
    )

    @model_validator(mode="after")
    def _validate_structured_transport(self) -> "ProviderModels":
        """Chat Completions structured output requires a base_url provider."""
        if self.structured_transport == "chat_completions" and not self.base_url:
            raise ValueError(
                "structured_transport='chat_completions' requires a base_url; "
                "native SDK providers must use structured_transport='responses'"
            )
        return self

    @model_validator(mode="after")
    def _validate_roles_reference_known_models(self) -> "ProviderModels":
        """Roles must resolve to a model ID declared in this provider's `models`."""
        if not self.roles:
            return self
        known_ids = {entry.id for entry in self.models}
        for role, target_id in self.roles.items():
            if target_id not in known_ids:
                raise ValueError(
                    f"Role '{role}' references unknown model id '{target_id}'. "
                    f"Known IDs: {sorted(known_ids)}"
                )
        return self


class ModelConfig(BaseModel):
    """Model defaults and provider registry."""

    model_config = ConfigDict(extra="forbid")

    default_model: str = Field(
        ...,
        description=(
            "Display-only model ID exposed to legacy settings consumers. "
            "Inference callers must use role-resolved agent fields instead."
        ),
    )
    default_slot_model: str = Field(
        default="TEST", description="Default model for newly created/reset slots"
    )
    api_models: Dict[str, ProviderModels] = Field(
        default_factory=dict,
        description="API models grouped by provider (openai, anthropic, test)",
    )

    @model_validator(mode="after")
    def _validate_defaults_reference_known_models(self) -> "ModelConfig":
        """Legacy/default UI fields must stay anchored to registered model IDs.

        "@provider.role" references are skipped here: they are resolved (and
        validated) by ``Settings._resolve_model_references`` once the full
        registry is available on the root model.
        """
        known_ids = {
            entry.id
            for provider in self.api_models.values()
            for entry in provider.models
        }
        for field_name in ("default_model", "default_slot_model"):
            model_id = getattr(self, field_name)
            if model_id.startswith(MODEL_ROLE_PREFIX):
                continue
            if model_id not in known_ids:
                raise ValueError(
                    f"{field_name} references unknown model id '{model_id}'. "
                    f"Known IDs: {sorted(known_ids)}"
                )
        return self

    @model_validator(mode="after")
    def _validate_non_native_providers(self) -> "ModelConfig":
        """Every provider without a native SDK path must declare a base_url.

        OpenAI and Anthropic requests go through their own SDK clients; any
        other provider section (test mock server, Ollama, vLLM, ...) is an
        OpenAI-compatible server whose endpoint lives in the registry, not in
        code.
        """
        for provider, config in self.api_models.items():
            if provider in NATIVE_API_PROVIDERS:
                if config.base_url is not None:
                    raise ValueError(
                        f"Provider '{provider}' uses its native SDK endpoint; "
                        f"base_url is not allowed here. Register a proxy or "
                        f"local server as its own provider section instead."
                    )
                continue
            if config.models and not config.base_url:
                raise ValueError(
                    f"Provider '{provider}' in [global.model.api_models] is not "
                    f"a native SDK provider ({sorted(NATIVE_API_PROVIDERS)}) and "
                    f"must declare a base_url for its OpenAI-compatible server."
                )
        return self


class NarrativeConfig(BaseModel):
    """Narrative test mode settings."""

    model_config = ConfigDict(extra="forbid")

    test_mode: bool = Field(..., description="Enable test mode")
    test_database_suffix: str = Field(..., description="Database suffix for testing")


class GlobalSettings(BaseModel):
    """Global configuration settings."""

    model_config = ConfigDict(extra="forbid")

    model: ModelConfig
    narrative: NarrativeConfig


class LocalModelCatalogEntry(BaseModel):
    """One downloadable/labelable GGUF variant known to NEXUS."""

    model_config = ConfigDict(extra="forbid")

    family: str
    label: str
    hf_repo: str
    subdir: str = Field(
        ...,
        description="Directory beneath local_models.models_dir for this family",
    )
    filename: str
    quant: str
    size_gb: float = Field(..., gt=0)
    min_ram_gb: float = Field(..., gt=0)

    @field_validator("subdir")
    @classmethod
    def _validate_subdir(cls, value: str) -> str:
        """Keep future downloads inside the configured models directory."""
        from pathlib import PurePath

        path = PurePath(value)
        if path.is_absolute() or ".." in path.parts or value in {"", "."}:
            raise ValueError("subdir must be a non-empty relative path without '..'")
        return value


class LocalModelsSettings(BaseModel):
    """Configuration for interactive local GGUF discovery and serving."""

    model_config = ConfigDict(extra="forbid")

    models_dir: str = Field(
        default="~/.lmstudio/models/lmstudio-community",
        description="Root directory scanned recursively for GGUF model files",
    )
    catalog: List[LocalModelCatalogEntry] = Field(default_factory=list)
    download_disable_xet: bool = Field(
        default=True,
        description=(
            "Spawn download workers with HF_HUB_DISABLE_XET=1 so multi-GB "
            "GGUF pulls use the classic HTTP path with genuine byte-append "
            "resume after a cancel; Xet's chunk transfer does not preserve "
            "byte partials across restarts"
        ),
    )

    @field_validator("models_dir")
    @classmethod
    def _expand_models_dir(cls, value: str) -> str:
        """Expand the configured home shortcut once at config load."""
        from pathlib import Path

        return str(Path(value).expanduser())


# =============================================================================
# Managed Runtime Settings Models (issue #396)
# =============================================================================


class RuntimeServiceSettings(BaseModel):
    """One supervised service in the local runtime profile."""

    model_config = ConfigDict(extra="forbid")

    command: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "argv template for spawning the service. Placeholders: {python} "
            "(current interpreter), {host}, {port}. No shell is involved."
        ),
    )
    host: str = Field(default="127.0.0.1", description="Bind host (loopback TCP)")
    port: int = Field(..., ge=1, le=65535, description="Service port")
    health_path: str = Field(
        default="/health", description="HTTP path probed for liveness"
    )
    env: Dict[str, str] = Field(
        default_factory=dict,
        description="Extra environment variables set on the spawned process",
    )
    enabled: Literal["always", "never", "auto"] = Field(
        default="always",
        description=(
            "'always' spawns the service in the local profile; 'never' skips "
            "it; 'auto' spawns only when the TEST provider is registered in "
            "[global.model.api_models] (the mock server's condition)."
        ),
    )
    autorestart: Literal["never", "on-failure"] = Field(
        default="never",
        description=(
            "'on-failure' respawns the service when it exits nonzero while a "
            "foreground supervisor (nexus up --foreground) is attached. "
            "Detached mode has no supervising process, so it is effectively "
            "'never' there."
        ),
    )
    autorestart_max_retries: int = Field(
        default=3,
        ge=0,
        description="Foreground autorestart attempts before giving up",
    )


class RuntimeHealthSettings(BaseModel):
    """HTTP health-probe and process lifecycle timing."""

    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(
        default=2.0, gt=0, description="Per-probe HTTP timeout"
    )
    startup_deadline_seconds: float = Field(
        default=30.0, gt=0, description="How long nexus up waits per service"
    )
    poll_interval_seconds: float = Field(
        default=0.25, gt=0, description="Delay between startup health probes"
    )
    stop_grace_seconds: float = Field(
        default=10.0,
        gt=0,
        description="SIGTERM-to-SIGKILL escalation window on nexus down",
    )
    port_release_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description=(
            "How long a model swap waits for the just-stopped llama-server "
            "to release its port before treating the occupant as foreign"
        ),
    )


class RuntimeLogsSettings(BaseModel):
    """Captured-log presentation settings for nexus logs."""

    model_config = ConfigDict(extra="forbid")

    tail_lines: int = Field(
        default=100, ge=1, description="Default line count for nexus logs"
    )
    follow_poll_seconds: float = Field(
        default=0.5, gt=0, description="Poll interval for nexus logs -f"
    )


class RuntimeExternalSettings(BaseModel):
    """Attach targets for the external profile (spawn nothing)."""

    model_config = ConfigDict(extra="forbid")

    gateway_url: str = Field(..., description="Base URL of the already-running gateway")
    mock_openai_url: Optional[str] = Field(
        default=None,
        description="Base URL of an already-running mock server (optional)",
    )


class RuntimeCloudflareAccessSettings(BaseModel):
    """Secret-store references for a Cloudflare Access service token."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, str_to_lower=True
    )

    client_id_secret: str = Field(
        ...,
        min_length=1,
        description="Secret-store account containing CF-Access-Client-Id",
    )
    client_secret_secret: str = Field(
        ...,
        min_length=1,
        description="Secret-store account containing CF-Access-Client-Secret",
    )

    @model_validator(mode="after")
    def _require_distinct_accounts(self) -> "RuntimeCloudflareAccessSettings":
        """The ID and secret must never resolve from the same store entry."""
        if self.client_id_secret == self.client_secret_secret:
            raise ValueError(
                "Cloudflare Access client ID and client secret must use "
                "different secret-store accounts"
            )
        return self


class RuntimeRemoteSettings(BaseModel):
    """A hosted NEXUS runtime reached purely over HTTP(S)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    base_url: str = Field(
        ..., min_length=1, description="Base URL of the remote runtime origin"
    )
    cloudflare_access: Optional[RuntimeCloudflareAccessSettings] = Field(
        default=None,
        description="Optional Cloudflare Access service-token references",
    )

    @model_validator(mode="after")
    def _require_secure_access_origin(self) -> "RuntimeRemoteSettings":
        """Never transmit Cloudflare service-token credentials over plaintext."""
        if self.cloudflare_access is None:
            return self

        from urllib.parse import urlsplit

        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "cloudflare_access requires an HTTPS base_url without "
                "credentials, query, or fragment"
            )
        return self


class RuntimeGatewaySettings(BaseModel):
    """Gateway-wide network policy settings."""

    model_config = ConfigDict(extra="forbid")

    cors_allowed_origins: List[str] = Field(
        ...,
        min_length=1,
        description="Exact HTTP origins allowed to make credentialed CORS requests",
    )

    @model_validator(mode="after")
    def _validate_cors_allowed_origins(self) -> "RuntimeGatewaySettings":
        """Require exact HTTP(S) origins rather than wildcard or URL patterns."""
        from urllib.parse import urlsplit

        if len(self.cors_allowed_origins) != len(set(self.cors_allowed_origins)):
            raise ValueError("cors_allowed_origins must not contain duplicates")

        for origin in self.cors_allowed_origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "cors_allowed_origins entries must be exact HTTP(S) origins "
                    f"without credentials, paths, queries, or fragments: {origin!r}"
                )
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError(
                    f"cors_allowed_origins entry has an invalid port: {origin!r}"
                ) from exc
        return self


class RuntimeSettings(BaseModel):
    """Managed runtime configuration (nexus up / down / status / logs)."""

    model_config = ConfigDict(extra="forbid")

    profile: Literal["local", "external", "remote"] = Field(
        default="local",
        description=(
            "'local' spawns and manages services; 'external' attaches to "
            "already-running services (health/status only); 'remote' targets "
            "a hosted runtime via remote.base_url."
        ),
    )
    state_dir: str = Field(
        default=".nexus/runtime",
        description=(
            "Directory for pidfiles and captured service logs. Relative paths "
            "resolve against the repository root."
        ),
    )
    default_slot: int = Field(
        default=1,
        ge=1,
        le=5,
        description=(
            "Slot exported as NEXUS_SLOT to spawned services when neither "
            "--slot nor the NEXUS_SLOT environment variable is set."
        ),
    )
    services: Dict[str, RuntimeServiceSettings] = Field(
        default_factory=dict,
        description="Supervised services for the local profile, by name",
    )
    gateway: RuntimeGatewaySettings
    health: RuntimeHealthSettings = Field(default_factory=RuntimeHealthSettings)
    logs: RuntimeLogsSettings = Field(default_factory=RuntimeLogsSettings)
    external: Optional[RuntimeExternalSettings] = None
    remote: Optional[RuntimeRemoteSettings] = None

    @model_validator(mode="after")
    def _validate_profile_requirements(self) -> "RuntimeSettings":
        if self.profile == "local" and "gateway" not in self.services:
            raise ValueError(
                "[runtime] profile 'local' requires a [runtime.services.gateway] "
                "section"
            )
        if self.profile == "external" and self.external is None:
            raise ValueError(
                "[runtime] profile 'external' requires a [runtime.external] "
                "section with gateway_url"
            )
        if self.profile == "remote" and self.remote is None:
            raise ValueError(
                "[runtime] profile 'remote' requires a [runtime.remote] section "
                "with base_url"
            )
        return self


# =============================================================================
# LORE Agent Settings Models
# =============================================================================


class TokenBudgetConfig(BaseModel):
    """Token budget allocation for APEX generation."""

    model_config = ConfigDict(extra="forbid")

    apex_context_window: int = Field(..., ge=1000, description="Total tokens for APEX")
    system_prompt_tokens: int = Field(
        ..., ge=100, description="Reserved for system prompt"
    )


class PayloadBudgetRange(BaseModel):
    """Min/max percentage range for payload budget allocation."""

    model_config = ConfigDict(extra="forbid")

    min: int = Field(..., ge=0, le=100, description="Minimum percentage")
    max: int = Field(..., ge=0, le=100, description="Maximum percentage")


class PayloadPercentBudget(BaseModel):
    """Percentage allocations for different context payload sections."""

    model_config = ConfigDict(extra="forbid")

    structured_summaries: PayloadBudgetRange
    contextual_augmentation: PayloadBudgetRange
    warm_slice: PayloadBudgetRange


class EntityInclusionConfig(BaseModel):
    """Configuration for entity inclusion in context payloads."""

    model_config = ConfigDict(extra="forbid")

    warm_slice_lookback_chunks: int = Field(..., ge=1)
    max_characters_from_warm_slice: int = Field(..., ge=1)
    max_locations_from_warm_slice: int = Field(..., ge=1)
    include_all_relationships: bool
    include_all_active_events: bool
    include_all_active_threats: bool
    active_event_statuses: List[str]
    active_threat_statuses: List[str]
    max_total_characters: int = Field(..., ge=1)
    max_total_relationships: int = Field(..., ge=1)
    max_total_events: int = Field(..., ge=1)
    max_total_threats: int = Field(..., ge=1)


class LORERetrievalSettings(BaseModel):
    """LORE retrieval settings."""

    model_config = ConfigDict(extra="forbid")

    max_deep_queries: int = Field(
        default=5,
        ge=1,
        description="Maximum MEMNON queries to execute during LORE deep-query pass",
    )


class LORESettings(BaseModel):
    """LORE agent configuration."""

    model_config = ConfigDict(extra="forbid")

    debug: bool
    agentic_sql: bool
    token_budget: TokenBudgetConfig
    payload_percent_budget: PayloadPercentBudget
    entity_inclusion: EntityInclusionConfig
    retrieval: LORERetrievalSettings = Field(default_factory=LORERetrievalSettings)


# =============================================================================
# Orrery Settings Models
# =============================================================================


class OrreryBindingSettings(BaseModel):
    """Binding composer settings for Orrery."""

    model_config = ConfigDict(extra="forbid")

    window_chunks: int = Field(default=30, ge=1)


_CONTAGION_DURATION_RE = re.compile(r"^(?P<amount>\d+(?:\.\d+)?)(?P<unit>[smhdw])$")
_CONTAGION_DURATION_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
}


def _parse_contagion_duration(value: Any, *, allow_never: bool) -> Optional[timedelta]:
    """Parse one strict world-time duration used by Social Contagion."""

    if isinstance(value, timedelta):
        if value <= timedelta(0):
            raise ValueError("duration must be greater than zero")
        return value
    if allow_never and value is None:
        return None
    if allow_never and value == "never":
        return None
    if not isinstance(value, str):
        expected = (
            "a duration string or 'never'" if allow_never else "a duration string"
        )
        raise ValueError(f"expected {expected}")
    match = _CONTAGION_DURATION_RE.fullmatch(value.strip())
    if match is None:
        expected = "<number><s|m|h|d|w>"
        if allow_never:
            expected += " or 'never'"
        raise ValueError(f"malformed duration {value!r}; expected {expected}")
    seconds = (
        float(match.group("amount")) * _CONTAGION_DURATION_SECONDS[match.group("unit")]
    )
    if seconds <= 0:
        raise ValueError("duration must be greater than zero")
    return timedelta(seconds=seconds)


class OrreryContagionDyadTierSettings(BaseModel):
    """Outbound-valence latency defaults for character dyads."""

    model_config = ConfigDict(extra="forbid")

    trusting: Optional[timedelta] = timedelta(hours=24)
    neutral: Optional[timedelta] = timedelta(hours=96)
    hostile: Optional[timedelta] = None

    @field_validator("trusting", "neutral", "hostile", mode="before")
    @classmethod
    def _parse_latency(cls, value: Any) -> Optional[timedelta]:
        return _parse_contagion_duration(value, allow_never=True)


class OrreryContagionDyadOverrideSettings(BaseModel):
    """Directional latency override for one relationship type."""

    model_config = ConfigDict(extra="forbid")

    forward: Optional[timedelta]
    reverse: Optional[timedelta]

    @field_validator("forward", "reverse", mode="before")
    @classmethod
    def _parse_latency(cls, value: Any) -> Optional[timedelta]:
        return _parse_contagion_duration(value, allow_never=True)


class OrreryContagionChannelSettings(BaseModel):
    """Direction and base latency for one institutional conduit."""

    model_config = ConfigDict(extra="forbid")

    direction: Literal[
        "both",
        "subject_to_object",
        "object_to_subject",
        "faction_to_member",
    ]
    latency: Optional[timedelta]
    min_level: Optional[str] = None

    @field_validator("latency", mode="before")
    @classmethod
    def _parse_latency(cls, value: Any) -> Optional[timedelta]:
        return _parse_contagion_duration(value, allow_never=True)

    @field_validator("min_level")
    @classmethod
    def _validate_min_level(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        from nexus.agents.orrery.status_family import normalize_status_level

        return normalize_status_level(value)


class OrreryContagionGuardSettings(BaseModel):
    """Validated Stage 2c traversal guards shipped ahead of propagation."""

    model_config = ConfigDict(extra="forbid")

    depth_cap: int = Field(default=4, ge=1)
    age_horizon: timedelta = timedelta(days=14)
    fan_out_cap: int = Field(default=6, ge=1)

    @field_validator("age_horizon", mode="before")
    @classmethod
    def _parse_age_horizon(cls, value: Any) -> timedelta:
        parsed = _parse_contagion_duration(value, allow_never=False)
        assert parsed is not None
        return parsed


def _default_contagion_dyad_overrides() -> (
    Dict[str, OrreryContagionDyadOverrideSettings]
):
    return {
        "handler": OrreryContagionDyadOverrideSettings(
            forward=timedelta(hours=12), reverse=timedelta(hours=12)
        ),
        "captor": OrreryContagionDyadOverrideSettings(
            forward=None, reverse=timedelta(hours=24)
        ),
    }


def _default_contagion_channels() -> Dict[str, OrreryContagionChannelSettings]:
    return {
        "handles": OrreryContagionChannelSettings(
            direction="both", latency=timedelta(hours=12)
        ),
        "obligation": OrreryContagionChannelSettings(
            direction="object_to_subject", latency=timedelta(hours=48)
        ),
        "authority_over": OrreryContagionChannelSettings(
            direction="subject_to_object", latency=timedelta(hours=24)
        ),
        "mentors": OrreryContagionChannelSettings(
            direction="both", latency=timedelta(hours=24)
        ),
        "contact:social": OrreryContagionChannelSettings(
            direction="both", latency=timedelta(hours=72)
        ),
        "status:*": OrreryContagionChannelSettings(
            direction="faction_to_member",
            latency=timedelta(hours=48),
            min_level="junior",
        ),
    }


def _default_contagion_culture_profiles() -> Dict[str, float]:
    return {
        "cellular_clandestine": 4.0,
        "compartmented": 2.0,
        "covert": 2.0,
        "hybrid": 1.0,
        "overt": 0.5,
    }


class OrreryContagionSettings(BaseModel):
    """Deterministic read-side communication graph configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    dyad_tiers: OrreryContagionDyadTierSettings = Field(
        default_factory=OrreryContagionDyadTierSettings
    )
    dyad_overrides: Dict[str, OrreryContagionDyadOverrideSettings] = Field(
        default_factory=_default_contagion_dyad_overrides
    )
    channels: Dict[str, OrreryContagionChannelSettings] = Field(
        default_factory=_default_contagion_channels
    )
    culture_profiles: Dict[str, float] = Field(
        default_factory=_default_contagion_culture_profiles
    )
    guards: OrreryContagionGuardSettings = Field(
        default_factory=OrreryContagionGuardSettings
    )

    @field_validator("dyad_overrides")
    @classmethod
    def _validate_override_keys(
        cls,
        values: Dict[str, OrreryContagionDyadOverrideSettings],
    ) -> Dict[str, OrreryContagionDyadOverrideSettings]:
        if any(not key.strip() for key in values):
            raise ValueError("dyad_overrides keys must be non-empty")
        return values

    @field_validator("culture_profiles")
    @classmethod
    def _validate_culture_profiles(cls, values: Dict[str, float]) -> Dict[str, float]:
        blank = [key for key in values if not key.strip()]
        if blank:
            raise ValueError("culture_profiles keys must be non-empty")
        invalid = {key: value for key, value in values.items() if value <= 0}
        if invalid:
            raise ValueError(
                "culture profile multipliers must be greater than zero: " f"{invalid}"
            )
        return values

    @model_validator(mode="after")
    def _validate_channel_shapes(self) -> "OrreryContagionSettings":
        for key, channel in self.channels.items():
            if not key.strip():
                raise ValueError("channel keys must be non-empty")
            if key == "status:*":
                if channel.direction != "faction_to_member":
                    raise ValueError(
                        "orrery.contagion.channels.'status:*' must use "
                        "direction='faction_to_member'"
                    )
                if channel.min_level is None:
                    raise ValueError(
                        "orrery.contagion.channels.'status:*' requires min_level"
                    )
            elif channel.direction == "faction_to_member":
                raise ValueError(
                    "direction='faction_to_member' is reserved for the "
                    "'status:*' channel"
                )
            elif channel.min_level is not None:
                raise ValueError("min_level is only valid for the 'status:*' channel")
        return self


class OrreryRouteGraphSettings(BaseModel):
    """Offline route graph safety settings for Orrery travel."""

    model_config = ConfigDict(extra="forbid")

    max_edges_per_query: int = Field(default=5000, ge=1)


class OrreryNarrationSettings(BaseModel):
    """Frontier narration settings for promoted Orrery resolutions."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["async", "sync"] = "async"
    provider: str = "anthropic"
    model_ref: str = Field(..., description="Model ID or @provider.role reference")
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description=(
            "Sampling temperature for narration calls. Unset means the "
            "parameter is omitted entirely (API default). Configuring it for "
            "a model that lists 'temperature' in unsupported_params is a "
            "config-load error."
        ),
    )
    max_output_tokens: int = Field(
        default=1200, ge=1, description="Output-token ceiling for narration calls"
    )
    max_attempts: int = Field(
        default=3, ge=1, description="Narration job attempts before marked failed"
    )
    retry_delay_seconds: int = Field(
        default=300, ge=0, description="Delay before a failed narration job retries"
    )


class OrreryBleedSettings(BaseModel):
    """Bleed selector settings for storyteller-time ambient candidates."""

    model_config = ConfigDict(extra="forbid")

    latency_budget_ms: Optional[int] = Field(
        default=None,
        ge=1,
        exclude=True,
        description="Deprecated and ignored; Bleed selection is deterministic.",
    )
    candidate_pool_multiplier: Optional[int] = Field(
        default=None,
        ge=1,
        exclude=True,
        description="Deprecated and ignored; Bleed scans the eligible ordered pool.",
    )
    max_candidates: int = Field(default=3, ge=0)
    near_distance_max: int = Field(default=2, ge=0)
    reserved_remote_slots: int = Field(default=1, ge=0)
    scan_limit: int = Field(
        default=24,
        ge=1,
        description=(
            "Upper bound on eligible candidates fetched per anchored menu "
            "selection; the partition sees at most this many rows."
        ),
    )

    @model_validator(mode="after")
    def _validate_reserved_remote_slots(self) -> "OrreryBleedSettings":
        """The remote reservation must fit inside an enabled menu.

        The default reservation adapts to small menus (a legacy
        ``max_candidates = 1`` config stays bootable); an EXPLICIT
        contradictory reservation still fails loudly.
        """

        implicit = "reserved_remote_slots" not in self.model_fields_set
        if self.max_candidates == 0:
            if self.reserved_remote_slots != 0:
                if implicit:
                    object.__setattr__(self, "reserved_remote_slots", 0)
                    return self
                raise ValueError(
                    "orrery.bleed.reserved_remote_slots must be 0 when "
                    "max_candidates is 0"
                )
            return self
        if self.reserved_remote_slots >= self.max_candidates:
            if implicit:
                object.__setattr__(
                    self, "reserved_remote_slots", self.max_candidates - 1
                )
            else:
                raise ValueError(
                    "orrery.bleed.reserved_remote_slots must be < max_candidates"
                )
        if self.scan_limit < self.max_candidates:
            raise ValueError("orrery.bleed.scan_limit must be >= max_candidates")
        return self


class OrreryPromoteSettings(BaseModel):
    """Deterministic promotion discriminator settings for Orrery resolutions."""

    model_config = ConfigDict(extra="forbid")

    priority_threshold: float = Field(
        default=30.0,
        ge=0.0,
        description="Promote resolutions whose priority is at or above this value.",
    )
    magnitude_threshold: float = Field(
        default=0.35,
        ge=0.0,
        description="Promote resolutions whose magnitude is at or above this value.",
    )
    perceptual_summary_max_chars: int = Field(
        default=240,
        ge=1,
        description=(
            "Maximum characters copied from a resolution brief into the "
            "promotion summary."
        ),
    )
    provider: Optional[Literal["local"]] = Field(
        default=None,
        exclude=True,
        description="Deprecated and ignored; promotion is deterministic.",
    )


def _default_need_accrual_rates() -> Dict[str, float]:
    return {
        "sleep": 1.0,
        "hunger": 1.0,
        "thirst": 1.0,
        "socialize": 1.0,
        "intimacy": 1.0,
    }


def _default_need_priorities() -> Dict[str, int]:
    return {"sleep": 25, "thirst": 24, "hunger": 22, "socialize": 18, "intimacy": 16}


def _default_need_severity_thresholds() -> Dict[str, "OrreryNeedThresholdSettings"]:
    return {
        "sleep": OrreryNeedThresholdSettings(
            mild=16.0,
            moderate=30.0,
            severe=48.0,
            critical=72.0,
        ),
        "hunger": OrreryNeedThresholdSettings(
            mild=8.0,
            moderate=16.0,
            severe=30.0,
            critical=48.0,
        ),
        "thirst": OrreryNeedThresholdSettings(
            mild=4.0,
            moderate=8.0,
            severe=16.0,
            critical=24.0,
        ),
        "socialize": OrreryNeedThresholdSettings(
            mild=24.0,
            moderate=72.0,
            severe=168.0,
            critical=336.0,
        ),
        "intimacy": OrreryNeedThresholdSettings(
            mild=72.0,
            moderate=168.0,
            severe=336.0,
            critical=720.0,
        ),
    }


class OrreryNeedThresholdSettings(BaseModel):
    """Debt thresholds for one Sunhelm need severity track."""

    model_config = ConfigDict(extra="forbid")

    mild: float = Field(..., ge=0.0)
    moderate: float = Field(..., ge=0.0)
    severe: float = Field(..., ge=0.0)
    critical: float = Field(..., ge=0.0)

    @model_validator(mode="after")
    def _validate_monotonic(self) -> "OrreryNeedThresholdSettings":
        if not (self.mild <= self.moderate <= self.severe <= self.critical):
            raise ValueError(
                "Need severity thresholds must be monotonic: "
                "mild <= moderate <= severe <= critical"
            )
        return self


class OrreryNeedPressureSettings(BaseModel):
    """Present-character need pressure tuning for Storyteller prompt injection."""

    model_config = ConfigDict(extra="forbid")

    min_severity_level: int = Field(default=2, ge=1, le=4)
    magnitude_base: float = Field(default=0.35, ge=0.0)
    magnitude_per_level: float = Field(default=0.10, ge=0.0)
    magnitude_cap: float = Field(default=0.85, ge=0.0, le=1.0)


class OrrerySelectionSettings(BaseModel):
    """Branch-selection policy for Orrery behavior packages.

    ``stochastic`` samples all passing branches with a magnitude-softmax at
    ``temperature`` (seeded on persisted per-resolution values, so the same
    state always resolves the same way — reproducible dynamism, and replay
    of the committed state_delta log remains the reconstruction authority).
    ``authored_order`` is the legacy deterministic first-passing rule.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["authored_order", "stochastic"] = Field(
        default="stochastic",
        description=(
            "Branch-selection rule: legacy authored-order short-circuit, or "
            "seeded magnitude-softmax sampling over all passing branches."
        ),
    )
    temperature: float = Field(
        default=0.25,
        ge=0.0,
        description=(
            "Softmax temperature for stochastic mode. 0 degenerates to "
            "argmax-by-magnitude; higher values flatten toward uniform. "
            "Builtin magnitudes differ by ~0.1-0.3, so 0.25 keeps salient "
            "branches favored ~3:1 without silencing fallbacks."
        ),
    )
    seed_salt: str = Field(
        default="",
        description=(
            "Extra PRNG seed material. Change to reroll every stochastic "
            "choice without touching state; keep stable for reproducibility."
        ),
    )


class OrreryPackageSelectionSettings(BaseModel):
    """Near-tie stack-winner policy for [orrery.package_selection]."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["stochastic", "argmax"] = Field(
        default="stochastic",
        description=(
            "Package winner rule: strict effective-priority argmax, or a "
            "seeded softmax within window_points of the maximum."
        ),
    )
    window_points: float = Field(
        default=6.0,
        ge=0.0,
        description=(
            "Maximum effective-priority distance from the stack maximum for "
            "entry into stochastic package selection."
        ),
    )
    temperature: float = Field(
        default=2.0,
        gt=0.0,
        description=(
            "Softmax temperature on the package priority's 0-100 scale; this "
            "is intentionally separate from branch magnitude temperature."
        ),
    )
    exempt_bands: list[str] = Field(
        default_factory=lambda: ["crisis_constraint"],
        description=(
            "Drive bands that disable package randomization whenever any "
            "candidate in that band passes."
        ),
    )


class OrreryProjectSettings(BaseModel):
    """Long-arc project policy for [orrery.projects]."""

    model_config = ConfigDict(extra="forbid")

    advance_interval_hours: float = Field(
        default=24.0,
        gt=0.0,
        description=(
            "World-clock hours between project transitions; prevents an "
            "open project from firing on every resolver tick."
        ),
    )
    max_active_per_character: int = Field(
        default=1,
        ge=1,
        le=1,
        description=(
            "Open-project budget per character. V1 is intentionally fixed at "
            "one to match migration 074's partial unique index."
        ),
    )
    stall_abandon_threshold: int = Field(
        default=3,
        ge=1,
        description="Accumulated stalls that make abandonment preemptive when due.",
    )
    abandon_after_stalled_world_hours: float = Field(
        default=168.0,
        gt=0.0,
        description=(
            "Hours a project may remain overdue before deterministic "
            "abandonment at its next evaluation."
        ),
    )
    milestone_magnitude: float = Field(
        default=0.40,
        ge=0.0,
        le=1.0,
        description=(
            "Magnitude applied to start, stage-transition, abandonment, and "
            "completion branches so milestones enter the promotion funnel."
        ),
    )
    coverage_distribution_tolerance: float = Field(
        default=0.05,
        gt=0.0,
        le=1.0,
        description=(
            "Maximum accepted maintenance/routine winner-distribution shift "
            "for the active-project coverage acceptance probe."
        ),
    )


class OrreryDriftSettings(BaseModel):
    """Continuous relationship-valence policy for ``[orrery.drift]``."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    copresence_rate_per_hour: Decimal = Field(default=Decimal("0.001"), gt=0)
    copresence_max_hours_per_tick: Decimal = Field(default=Decimal("12.0"), gt=0)
    project_milestone_delta: Decimal = Field(default=Decimal("0.03"), gt=0, lt=1)
    hostile_events: Dict[str, Decimal] = Field(
        default_factory=lambda: {
            "threat_issued": Decimal("-0.02"),
            "retaliation_attempted": Decimal("-0.04"),
            "retaliation_executed": Decimal("-0.06"),
        }
    )
    cooperative_events: Dict[str, Decimal] = Field(
        default_factory=lambda: {
            "protective_intervention": Decimal("0.04"),
            "warning_delivered": Decimal("0.02"),
            "welfare_check": Decimal("0.02"),
            "kin_visit": Decimal("0.02"),
            "confrontation_resolved": Decimal("0.03"),
        }
    )

    @field_validator("hostile_events")
    @classmethod
    def _validate_hostile_events(cls, values: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """Require named, strictly negative hostile-event deltas."""

        if any(not event_type.strip() for event_type in values):
            raise ValueError("hostile_events keys must be non-empty")
        nonnegative = sorted(
            event_type for event_type, delta in values.items() if delta >= 0
        )
        if nonnegative:
            raise ValueError(
                f"hostile_events deltas must be strictly negative: {nonnegative}"
            )
        oversized = sorted(
            event_type for event_type, delta in values.items() if abs(delta) >= 1
        )
        if oversized:
            raise ValueError(
                "hostile_events delta magnitudes must be < 1: " f"{oversized}"
            )
        return values

    @field_validator("cooperative_events")
    @classmethod
    def _validate_cooperative_events(
        cls, values: Dict[str, Decimal]
    ) -> Dict[str, Decimal]:
        """Require named, strictly positive cooperative-event deltas."""

        if any(not event_type.strip() for event_type in values):
            raise ValueError("cooperative_events keys must be non-empty")
        nonpositive = sorted(
            event_type for event_type, delta in values.items() if delta <= 0
        )
        if nonpositive:
            raise ValueError(
                f"cooperative_events deltas must be strictly positive: {nonpositive}"
            )
        oversized = sorted(
            event_type for event_type, delta in values.items() if abs(delta) >= 1
        )
        if oversized:
            raise ValueError(
                "cooperative_events delta magnitudes must be < 1: " f"{oversized}"
            )
        return values

    @model_validator(mode="after")
    def _validate_copresence_tick_delta(self) -> "OrreryDriftSettings":
        """Keep the maximum co-presence delta inside the soft-clamp domain."""

        maximum_delta = (
            self.copresence_rate_per_hour * self.copresence_max_hours_per_tick
        )
        if maximum_delta >= 1:
            raise ValueError(
                "copresence_rate_per_hour * copresence_max_hours_per_tick "
                "must be < 1"
            )
        return self

    @model_validator(mode="after")
    def _validate_event_maps_disjoint(self) -> "OrreryDriftSettings":
        """An event type in both maps would double-apply its deltas."""

        overlap = sorted(set(self.hostile_events) & set(self.cooperative_events))
        if overlap:
            raise ValueError(
                "hostile_events and cooperative_events must be disjoint: " f"{overlap}"
            )
        return self


class OrreryEpistemicsSettings(BaseModel):
    """Claim minting and awareness policy for [orrery.epistemics]."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True,
        description="Enable claim producers and knower-gated predicates.",
    )
    claim_event_types: List[str] = Field(
        default_factory=lambda: [
            "threat_issued",
            "relationship_drift_milestone",
        ],
        description="World event types that mint bounded claims at birth.",
    )
    aware_roles: List[str] = Field(
        default_factory=lambda: ["actor", "target", "observer", "witness"],
        description=(
            "world_event_entities roles that receive awareness when a claim is minted."
        ),
    )

    @field_validator("claim_event_types")
    @classmethod
    def _validate_claim_event_types(cls, values: List[str]) -> List[str]:
        """Reject blank or duplicate event-type policy entries."""

        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("claim_event_types entries must be non-empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("claim_event_types entries must be unique")
        if "claim_propagated" in normalized:
            raise ValueError(
                "claim_propagated cannot appear in claim_event_types; "
                "propagation ledger events never mint claims"
            )
        return normalized

    @field_validator("aware_roles")
    @classmethod
    def _validate_aware_roles(cls, values: List[str]) -> List[str]:
        """Reject duplicate awareness roles."""

        allowed = {"actor", "target", "observer", "witness", "beneficiary"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"aware_roles contains unknown roles: {sorted(unknown)}")
        if len(set(values)) != len(values):
            raise ValueError("aware_roles entries must be unique")
        return values


class OrreryRevealSettings(BaseModel):
    """Template-authored backstory reveal policy for ``[orrery.reveal]``."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class OrreryReconstructionSettings(BaseModel):
    """Reconstruction-sufficiency knobs (issue #426)."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_interval_chunks: int = Field(
        default=25,
        ge=0,
        description=(
            "Take a JSONB state checkpoint every N accepted chunks inside "
            "the commit transaction; 0 disables auto-checkpointing "
            "(scripts/checkpoint_state.py remains available for manual and "
            "genesis snapshots)."
        ),
    )


class OrrerySunhelmSettings(BaseModel):
    """Timestamp-plus-debt tuning for Orrery basic needs."""

    model_config = ConfigDict(extra="forbid")

    accrual_rates: Dict[str, float] = Field(default_factory=_default_need_accrual_rates)
    severity_thresholds: Dict[str, OrreryNeedThresholdSettings] = Field(
        default_factory=_default_need_severity_thresholds
    )
    priorities: Dict[str, int] = Field(default_factory=_default_need_priorities)
    pressure: OrreryNeedPressureSettings = Field(
        default_factory=OrreryNeedPressureSettings
    )

    @model_validator(mode="after")
    def _validate_need_keys(self) -> "OrrerySunhelmSettings":
        required = {"sleep", "hunger", "thirst", "socialize", "intimacy"}
        for field_name, mapping in (
            ("accrual_rates", self.accrual_rates),
            ("severity_thresholds", self.severity_thresholds),
            ("priorities", self.priorities),
        ):
            keys = set(mapping)
            if keys != required:
                raise ValueError(
                    f"orrery.sunhelm.{field_name} must define exactly "
                    f"{sorted(required)}; got {sorted(keys)}"
                )
        return self


RETROGRADE_SUPPORTED_GENRES = frozenset(
    {
        "fantasy",
        "scifi",
        "horror",
        "mystery",
        "historical",
        "contemporary",
        "postapocalyptic",
        "cyberpunk",
        "steampunk",
        "urban_fantasy",
        "space_opera",
        "noir",
        "thriller",
    }
)


class OrreryRetrogradeWeirdBandSettings(BaseModel):
    """Inclusive raw-float interval for one player-facing weirdness level."""

    model_config = ConfigDict(extra="forbid")

    min: float = Field(..., ge=0.0)
    max: float = Field(..., ge=0.0)

    @model_validator(mode="after")
    def _validate_order(self) -> "OrreryRetrogradeWeirdBandSettings":
        if self.min > self.max:
            raise ValueError("Weird band min must be less than or equal to max")
        return self


class OrreryRetrogradeWeirdGenreBands(BaseModel):
    """Per-genre remapping from coarse player level to raw weirdness band."""

    model_config = ConfigDict(extra="forbid")

    low: OrreryRetrogradeWeirdBandSettings
    medium: OrreryRetrogradeWeirdBandSettings
    high: OrreryRetrogradeWeirdBandSettings

    @model_validator(mode="after")
    def _validate_monotonic(self) -> "OrreryRetrogradeWeirdGenreBands":
        if not (
            self.low.min
            <= self.low.max
            <= self.medium.min
            <= self.medium.max
            <= self.high.min
            <= self.high.max
        ):
            raise ValueError(
                "Weird genre bands must be monotonic: "
                "low <= medium <= high without overlap"
            )
        if not (
            _same_float_boundary(self.low.max, self.medium.min)
            and _same_float_boundary(self.medium.max, self.high.min)
        ):
            raise ValueError(
                "Weird genre bands must be contiguous: "
                "low.max == medium.min and medium.max == high.min"
            )
        return self


class OrreryRetrogradeWeirdDevSettings(BaseModel):
    """Developer-facing raw weirdness float surface for calibration."""

    model_config = ConfigDict(extra="forbid")

    cli_flag: str = Field(
        default="--weird",
        description="Future calibration CLI flag for raw weirdness overrides.",
    )
    min: float = Field(default=0.0, ge=0.0)
    max: float = Field(default=1.0, ge=0.0)
    default: float = Field(default=0.5, ge=0.0)

    @model_validator(mode="after")
    def _validate_range(self) -> "OrreryRetrogradeWeirdDevSettings":
        if self.min > self.max:
            raise ValueError("Retrograde weird dev min must be <= max")
        if not self.min <= self.default <= self.max:
            raise ValueError("Retrograde weird dev default must be within range")
        return self


class OrreryRetrogradeWeirdSettings(BaseModel):
    """Entropy/coherence control for Retrograde seed generation."""

    model_config = ConfigDict(extra="forbid")

    default_level: Literal["low", "medium", "high"] = "medium"
    dev: OrreryRetrogradeWeirdDevSettings = Field(
        default_factory=OrreryRetrogradeWeirdDevSettings
    )
    bands_by_genre: Dict[str, OrreryRetrogradeWeirdGenreBands] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def _validate_bands_within_dev_range(self) -> "OrreryRetrogradeWeirdSettings":
        configured = set(self.bands_by_genre)
        if configured != RETROGRADE_SUPPORTED_GENRES:
            missing = sorted(RETROGRADE_SUPPORTED_GENRES - configured)
            unknown = sorted(configured - RETROGRADE_SUPPORTED_GENRES)
            raise ValueError(
                "orrery.retrograde.weird.bands_by_genre must define exactly "
                f"{sorted(RETROGRADE_SUPPORTED_GENRES)}; "
                f"missing={missing}, unknown={unknown}"
            )
        for genre, bands in self.bands_by_genre.items():
            for level in ("low", "medium", "high"):
                band = getattr(bands, level)
                if band.min < self.dev.min or band.max > self.dev.max:
                    raise ValueError(
                        f"orrery.retrograde.weird band {genre}.{level} "
                        "must stay within the dev raw range"
                    )
        return self


def _same_float_boundary(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-9


class OrreryRetrogradeRetrievalSettings(BaseModel):
    """Retrieval-surface settings for persisted Retrograde history."""

    model_config = ConfigDict(extra="forbid")

    summaries_enabled: bool = Field(
        default=True,
        description=(
            "Write one dedicated prose summary per persisted Retrograde world "
            "event so MEMNON can retrieve generated history without treating "
            "it as played narrative."
        ),
    )
    embed_after_apply: bool = Field(
        default=True,
        description=(
            "Trigger the Retrograde summary embedding lifecycle for pending "
            "summaries immediately after a successful apply."
        ),
    )


class OrreryRetrogradeWizardSettings(BaseModel):
    """Wizard-time cold-start firing of the Retrograde pipeline (spec M4)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True,
        description=(
            "Run the full Retrograde pipeline (packet, seed candidates, "
            "expansion, persistence, embedding) during the wizard ready -> "
            "narrative transition."
        ),
    )
    create_entity_stubs: bool = Field(
        default=True,
        description=(
            "Allow persistence to create minimum-viable character/place/"
            "faction stubs for expansion refs that resolve to no canonical row."
        ),
    )
    max_new_entity_stubs: int = Field(
        default=6,
        ge=0,
        description=(
            "Decision 8 entity-coverage cap: maximum number of new minimum-"
            "viable stubs one wizard-time expansion may introduce."
        ),
    )
    max_tokens: int = Field(
        default=16000,
        gt=0,
        description=(
            "Max output tokens for wizard-time R4/R6 Skald calls; seed and "
            "expansion responses are larger than ordinary wizard chat turns."
        ),
    )
    transition_timeout_seconds: int = Field(
        default=900,
        gt=0,
        description=(
            "HTTP client timeout for the wizard transition call; frontier "
            "generation runs inside it, so the budget is minutes, not seconds."
        ),
    )


class OrreryRetrogradeJunctionCountSettings(BaseModel):
    """Shared-entity junction counts by player-facing weirdness level."""

    model_config = ConfigDict(extra="forbid")

    low: int = Field(default=0, ge=0)
    medium: int = Field(default=1, ge=0)
    high: int = Field(default=1, ge=0)


class OrreryRetrogradeGraphSettings(BaseModel):
    """R3 candidate-graph sampling calibration ([orrery.retrograde.graph])."""

    model_config = ConfigDict(extra="forbid")

    edges_per_candidate: float = Field(
        default=1.5,
        gt=0,
        description=(
            "Dangling edges sampled per candidate seed; edges beyond claim "
            "capacity keep the menu wider than the funnel."
        ),
    )
    max_sample_retries: int = Field(
        default=12,
        ge=1,
        description="Resample attempts per edge slot before under-building.",
    )
    edge_kind_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "relationship": 0.4,
            "pair_tag": 0.3,
            "event": 0.3,
        },
        description=(
            "Sampling mix across edge kinds; relationships weighted up "
            "because the affiliation gates consume that surface."
        ),
    )
    anchor_role_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "protagonist": 3.0,
            "starting_location": 2.0,
            "default": 1.0,
        },
        description=(
            "Anchor-node preference by scaffold role; 'default' applies to "
            "roles not listed."
        ),
    )
    event_open_endpoint_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "character": 0.6,
            "faction": 0.25,
            "place": 0.15,
        },
        description="Open-endpoint kind mix for event edges.",
    )
    excluded_event_categories: List[str] = Field(
        default_factory=lambda: ["orrery_resolution", "physiological", "routine"],
        description=(
            "Event-type registry categories barred from the R3 event edge "
            "pool. Tick-loop bookkeeping (needs, upkeep, package resolution) "
            "makes weak backstory dice; expansion validation still accepts "
            "every registered type."
        ),
    )
    junction_counts_by_weird: OrreryRetrogradeJunctionCountSettings = Field(
        default_factory=OrreryRetrogradeJunctionCountSettings,
        description=(
            "Cold-start shared-entity junctions sampled at each player-facing "
            "weirdness level. Runtime maturation does not consume this setting."
        ),
    )


class OrreryRetrogradeMaturationSettings(BaseModel):
    """Runtime stub-maturation settings (spec decisions 9/10/12, M8)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True,
        description=(
            "Process Skald new-entity declarations at commit time and run "
            "asynchronous Retrograde maturation jobs for them."
        ),
    )
    budget_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description=(
            "Soft per-job wall-clock target for the runtime maturation "
            "pipeline (spec: ~5-30s). Exceeding it logs a warning and is "
            "recorded in the job manifest; it does not abort the job."
        ),
    )
    max_jobs_per_drain: int = Field(
        default=2,
        ge=1,
        description="Maximum queued maturation jobs leased per worker drain.",
    )
    max_attempts: int = Field(
        default=3,
        ge=1,
        description="Lease attempts before a job stays failed.",
    )
    retry_delay_seconds: int = Field(
        default=300,
        ge=0,
        description="Requeue delay after a failed attempt.",
    )
    generate_candidates: int = Field(
        default=4,
        ge=1,
        description=(
            "R4 over-generation budget for a single-entity runtime packet "
            "(tighter than wizard-time per the spec's ~2x guidance)."
        ),
    )
    select_target: int = Field(
        default=2,
        ge=1,
        description="R5 selection target for a single-entity runtime packet.",
    )
    deferred_secret_cap: int = Field(
        default=1,
        ge=0,
        description="Deferred-secret cap for a single-entity runtime packet.",
    )
    weird_level: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Coarse weirdness level for runtime maturation seeds.",
    )
    weird_band_fraction: float = Field(
        default=0.6,
        gt=0.0,
        le=1.0,
        description=(
            "Fraction of the genre weird band (measured from its floor) "
            "available to runtime maturation rolls. Cold-start wizard "
            "history rolls the full band; mid-story backstory retrofits "
            "around an entity's on-screen introduction, so its entropy "
            "ceiling stays lower. 1.0 reproduces the full cold-start band."
        ),
    )
    model_ref: Optional[str] = Field(
        default=None,
        description=(
            "Frontier model for the R4/R6 maturation calls "
            "(@provider.role reference). None falls back to the wizard "
            "default model."
        ),
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Max output tokens per maturation Skald call. None falls back "
            "to the wizard max-tokens setting."
        ),
    )
    chunk_excerpt_chars: int = Field(
        default=1200,
        ge=200,
        description=(
            "How much of the requesting chunk's text rides into the scoped "
            "maturation packet as prompt material."
        ),
    )

    @model_validator(mode="after")
    def _validate_seed_budget(self) -> "OrreryRetrogradeMaturationSettings":
        """Over-generation must cover the selection target.

        Asking R5 to select more seeds than R4 generated is silent semantic
        corruption (the multiplier clamps to 1 and selection starves), so a
        misconfigured budget fails at config load instead.
        """

        if self.generate_candidates < self.select_target:
            raise ValueError(
                "orrery.retrograde.maturation.generate_candidates must be >= "
                f"select_target (got {self.generate_candidates} < "
                f"{self.select_target})"
            )
        return self


class OrreryRetrogradeSettings(BaseModel):
    """Retrograde deep-history generation settings."""

    model_config = ConfigDict(extra="forbid")

    weird: OrreryRetrogradeWeirdSettings
    retrieval: OrreryRetrogradeRetrievalSettings = Field(
        default_factory=OrreryRetrogradeRetrievalSettings
    )
    wizard: OrreryRetrogradeWizardSettings = Field(
        default_factory=OrreryRetrogradeWizardSettings
    )
    graph: OrreryRetrogradeGraphSettings = Field(
        default_factory=OrreryRetrogradeGraphSettings
    )
    maturation: OrreryRetrogradeMaturationSettings = Field(
        default_factory=OrreryRetrogradeMaturationSettings
    )


class OrreryDashboardSettings(BaseModel):
    """Audit-dashboard settings for the Orrery dev surface."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description=(
            "Register the /api/dev/orrery/* audit router on the gateway. "
            "Server-side gate: import.meta.env.DEV only hides the client "
            "bundle, so this flag is what keeps the dev surface off any "
            "externally exposed gateway (issue #415). Default off; enable "
            "explicitly for local development."
        ),
    )
    coverage_max_anchors: int = Field(
        default=50,
        ge=1,
        description=(
            "Upper bound on anchors a single POST /api/dev/orrery/coverage "
            "request may analyze; each anchor is a full explained dry-run "
            "tick, so this bounds request latency and payload size."
        ),
    )
    coverage_epoch_min_world_times: int = Field(
        default=10,
        ge=2,
        description=(
            "Data-quality lint threshold: a single wall-clock second whose "
            "bestowals carry at least this many distinct world times is "
            "flagged as a retrograde backfill epoch."
        ),
    )


class OrreryPromptSettings(BaseModel):
    """Render caps for Orrery material in the storyteller prompt.

    The commit-time prompt-exposure log (orrery_prompt_exposures) records the
    same first-N slice these caps produce at render time — the two sites must
    read the same values or the recorded "shown set" lies.
    """

    model_config = ConfigDict(extra="forbid")

    max_rendered_proposals: int = Field(
        default=5,
        ge=1,
        description=(
            "How many current-tick Orrery proposals the storyteller prompt "
            "renders (ratify-by-omission applies only to rendered rows)."
        ),
    )
    max_rendered_pressures: int = Field(
        default=5,
        ge=1,
        description=("How many scene pressures the storyteller prompt renders."),
    )


class OrreryHabituationSettings(BaseModel):
    """Repetition dampening for stack selection ([orrery.habituation])."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description=(
            "Dampen a template's effective priority by penalty_per_win for "
            "each committed win by the same actor inside window_ticks, so a "
            "repeat winner eventually yields the stack to the packages it "
            "shadows. Deterministic: counts come from orrery_resolutions."
        ),
    )
    window_ticks: int = Field(
        default=40,
        ge=1,
        description="Trailing tick window for counting committed wins.",
    )
    penalty_per_win: float = Field(
        default=3.0,
        ge=0.0,
        description="Effective-priority debit per committed win.",
    )
    max_penalty: float = Field(
        default=10.0,
        ge=0.0,
        description=(
            "Cap on the total debit; keep small enough that dampening "
            "reorders within neighboring priorities without collapsing "
            "high-stakes packages into the mundane band."
        ),
    )
    exempt_bands: list[str] = Field(
        default_factory=lambda: ["crisis_constraint"],
        description=(
            "Drive bands never dampened — an actively hunted actor must "
            "not tire of evading."
        ),
    )


class OrreryFanoutSettings(BaseModel):
    """Per-actor cap on two-party drafts ([orrery.fanout])."""

    model_config = ConfigDict(extra="forbid")

    max_pair_drafts_per_actor: int = Field(
        default=2,
        ge=0,
        description=(
            "Maximum two-party drafts one actor contributes per tick "
            "(0 disables trimming). Kept drafts prefer template diversity, "
            "then magnitude; crisis-band drafts are exempt. Bounds the "
            "near-duplicate flood that crowds the storyteller prompt's "
            "first-N slice."
        ),
    )
    exempt_bands: list[str] = Field(
        default_factory=lambda: ["crisis_constraint"],
        description="Drive bands whose pair drafts are never trimmed.",
    )


class OrreryEcologySettings(BaseModel):
    """Event-ecology tuning: cross-package chains and their throttles."""

    model_config = ConfigDict(extra="forbid")

    signal_detection_default: int = Field(
        default=100,
        ge=0,
        le=100,
        description=(
            "Percent chance an emitted branch signal (signal_event_type) is "
            "actually detected and lands as a world_events row, for event "
            "types without an explicit rate below. 100 = always detected. "
            "The roll is a deterministic hash of (template, actor, target, "
            "tick, event type), so replays reconstruct identical outcomes."
        ),
    )
    signal_detection: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Per-event-type detection percents overriding the default — "
            "e.g. compliance_alert = 35 means most surveillance goes "
            "unnoticed by its subject. Undetected signals are recorded in "
            "the primary event's payload for the audit layer, but feed no "
            "gates."
        ),
    )


class OrrerySettings(BaseModel):
    """Orrery off-screen behavior settings.

    Retrograde config is intentionally required so every slot has explicit
    weird-dial genre remapping before generation code starts reading it.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    binding: OrreryBindingSettings = Field(default_factory=OrreryBindingSettings)
    contagion: OrreryContagionSettings = Field(default_factory=OrreryContagionSettings)
    route_graph: OrreryRouteGraphSettings = Field(
        default_factory=OrreryRouteGraphSettings
    )
    narration: OrreryNarrationSettings
    bleed: OrreryBleedSettings = Field(default_factory=OrreryBleedSettings)
    promote: OrreryPromoteSettings = Field(default_factory=OrreryPromoteSettings)
    sunhelm: OrrerySunhelmSettings = Field(default_factory=OrrerySunhelmSettings)
    selection: OrrerySelectionSettings = Field(default_factory=OrrerySelectionSettings)
    package_selection: OrreryPackageSelectionSettings = Field(
        default_factory=OrreryPackageSelectionSettings
    )
    projects: OrreryProjectSettings = Field(default_factory=OrreryProjectSettings)
    drift: OrreryDriftSettings = Field(default_factory=OrreryDriftSettings)
    reveal: OrreryRevealSettings = Field(default_factory=OrreryRevealSettings)
    epistemics: OrreryEpistemicsSettings = Field(
        default_factory=OrreryEpistemicsSettings
    )
    retrograde: OrreryRetrogradeSettings
    dashboard: OrreryDashboardSettings = Field(default_factory=OrreryDashboardSettings)
    reconstruction: OrreryReconstructionSettings = Field(
        default_factory=OrreryReconstructionSettings
    )
    prompt: OrreryPromptSettings = Field(default_factory=OrreryPromptSettings)
    ecology: OrreryEcologySettings = Field(default_factory=OrreryEcologySettings)
    habituation: OrreryHabituationSettings = Field(
        default_factory=OrreryHabituationSettings
    )
    fanout: OrreryFanoutSettings = Field(default_factory=OrreryFanoutSettings)

    @model_validator(mode="after")
    def _validate_project_milestone_promotion_floor(self) -> "OrrerySettings":
        """Project milestones must enter the configured promotion funnel."""

        if self.projects.milestone_magnitude < self.promote.magnitude_threshold:
            raise ValueError(
                "orrery.projects.milestone_magnitude must be >= "
                "orrery.promote.magnitude_threshold"
            )
        return self


# =============================================================================
# MEMNON Agent Settings Models
# =============================================================================


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., description="PostgreSQL connection URL")
    create_tables: bool
    drop_existing: bool


class EmbeddingModelConfig(BaseModel):
    """Configuration for an individual embedding model."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool
    local_path: str
    remote_path: Optional[str] = None
    dimensions: int = Field(..., ge=1)
    weight: float = Field(..., ge=0.0, le=1.0, description="Ensemble weight")


class ImportConfig(BaseModel):
    """Settings for importing narrative chunks."""

    model_config = ConfigDict(extra="forbid")

    base_directory: str
    file_pattern: str
    chunk_regex: str
    batch_size: int = Field(..., ge=1)
    verbose: bool
    file_limit: Optional[int] = None


class QueryConfig(BaseModel):
    """Default query settings."""

    model_config = ConfigDict(extra="forbid")

    default_limit: int = Field(..., ge=1)
    include_vector_results: int = Field(..., ge=0)
    include_text_results: int = Field(..., ge=0)
    include_structured_results: int = Field(..., ge=0)


class SourceWeights(BaseModel):
    """Relative weights for different retrieval sources."""

    model_config = ConfigDict(extra="forbid")

    structured_data: float = Field(..., ge=0.0)
    vector_search: float = Field(..., ge=0.0)
    text_search: float = Field(..., ge=0.0)


class VectorNormalizationConfig(BaseModel):
    """Vector search score normalization settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    low_tier_map_enabled: bool
    low_tier_threshold: float = Field(..., ge=0.0, le=1.0)
    low_tier_input_max: float = Field(..., ge=0.0, le=1.0)
    low_tier_output_min: float = Field(..., ge=0.0, le=1.0)
    low_tier_output_max: float = Field(..., ge=0.0, le=1.0)
    below_low_tier_scale_factor: float = Field(..., ge=0.0)
    tiers: List[List[float]]


class UserCharacterFocusBoost(BaseModel):
    """Boost settings for user character focus detection."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    action_patterns: List[str]
    emotional_patterns: List[str]
    knowledge_terms: List[str]
    action_pattern_weight: float = Field(..., ge=0.0)
    emotional_pattern_weight: float = Field(..., ge=0.0)
    knowledge_term_weight: float = Field(..., ge=0.0)
    max_boost: float = Field(..., ge=0.0)


class QueryTypeWeights(BaseModel):
    """Vector/text weights for a query type."""

    model_config = ConfigDict(extra="forbid")

    vector: float = Field(..., ge=0.0, le=1.0)
    text: float = Field(..., ge=0.0, le=1.0)


class HybridSearchConfig(BaseModel):
    """Hybrid search (vector + text) configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    vector_weight_default: float = Field(..., ge=0.0, le=1.0)
    text_weight_default: float = Field(..., ge=0.0, le=1.0)
    weights_by_query_type: Dict[str, QueryTypeWeights]
    temporal_boost_factors: Dict[str, float]
    use_query_type_weights: bool
    use_query_type_temporal_factors: bool
    target_model: str
    temporal_boost_factor: float = Field(..., ge=0.0)


class RerankerCandidate(BaseModel):
    """One reranker model entry in the bakeoff candidate registry.

    `api_type` selects the inference path in ``cross_encoder.rerank_results``:
      - "cross_encoder": standard SequenceClassification (DeBERTa-v3,
        mxbai, BGE-v2, etc.)
      - "qwen3_lm": Qwen3-Reranker causal-LM with yes/no logit head

    Note: the production reranker is selected by the top-level
    ``CrossEncoderReranking.model_path`` + ``api_type`` fields, not by any
    flag on this candidate entry. This registry is for ir_eval bakeoff
    selection via ``ir_eval.runner create-run --reranker NAME``.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    local_path: str
    remote_path: str = ""
    api_type: Literal["cross_encoder", "qwen3_lm"] = "cross_encoder"
    notes: str = ""


class CrossEncoderReranking(BaseModel):
    """Cross-encoder reranking configuration."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    enabled: bool
    model_path: str
    api_type: Literal["cross_encoder", "qwen3_lm"] = "cross_encoder"
    blend_weight: float = Field(..., ge=0.0, le=1.0)
    top_k: int = Field(..., ge=1)
    batch_size: int = Field(..., ge=1)
    use_sliding_window: bool
    window_size: int = Field(..., ge=1)
    window_overlap: int = Field(..., ge=0)
    weights_by_query_type: Dict[str, float]
    use_query_type_weights: bool
    use_8bit: bool
    candidates: Dict[str, RerankerCandidate] = Field(default_factory=dict)


class RetrievalConfig(BaseModel):
    """Main retrieval configuration."""

    model_config = ConfigDict(extra="forbid")

    max_results: int = Field(..., ge=1)
    relevance_threshold: float = Field(..., ge=0.0, le=1.0)
    entity_boost_factor: float = Field(..., ge=0.0)
    source_weights: SourceWeights
    vector_normalization: VectorNormalizationConfig
    text_search_base_score: float = Field(..., ge=0.0, le=1.0)
    text_search_count_bonus: float = Field(..., ge=0.0)
    text_search_max_score: float = Field(..., ge=0.0, le=1.0)
    structured_search_char_score: float = Field(..., ge=0.0, le=1.0)
    structured_search_place_score: float = Field(..., ge=0.0, le=1.0)
    user_character_focus_boost: UserCharacterFocusBoost
    hybrid_search: HybridSearchConfig
    cross_encoder_reranking: CrossEncoderReranking
    structured_data_enabled: bool


class LoggingConfig(BaseModel):
    """Logging configuration."""

    model_config = ConfigDict(extra="forbid")

    file: str
    level: str = Field(..., pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    console: bool


class MEMNONSettings(BaseModel):
    """MEMNON agent configuration."""

    model_config = ConfigDict(extra="forbid")

    debug: bool
    database: DatabaseConfig
    models: Dict[str, EmbeddingModelConfig]
    import_: ImportConfig = Field(..., alias="import")
    query: QueryConfig
    retrieval: RetrievalConfig
    logging: LoggingConfig


# =============================================================================
# Memory Manager Settings Models
# =============================================================================


class MemorySettings(BaseModel):
    """Memory manager configuration."""

    model_config = ConfigDict(extra="forbid")

    phase2_fraction: float = Field(..., ge=0.0, le=1.0)
    raw_search_k: int = Field(..., ge=1)
    skip_simple_choices: bool
    pass2_budget_reserve: float = Field(..., ge=0.0, le=1.0)
    divergence_threshold: float = Field(..., ge=0.0, le=1.0)
    warm_slice_default: bool
    max_sql_iterations: int = Field(..., ge=1)


# =============================================================================
# APEX API Settings Models
# =============================================================================


class APEXSettings(BaseModel):
    """APEX API configuration for story generation."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., pattern="^(openai|anthropic|local)$")
    model: str
    reasoning_effort: str = Field(..., pattern="^(low|medium|high)$")
    max_output_tokens: int = Field(..., ge=1)
    structured_output_retries: int = Field(
        default=3,
        ge=0,
        description=(
            "Validation retry budget for apex structured-output calls. Each "
            "retry feeds the validation error back to the model."
        ),
    )
    generation_timeout_seconds: int = Field(
        default=300,
        gt=0,
        description=(
            "HTTP client timeout for a narrative continue turn. Frontier "
            "storyteller generation runs inside the request and the API "
            "worker blocks while it does, so status polls are not answered "
            "until the turn completes; the budget must exceed the slowest "
            "expected generation, not a status ping's round-trip."
        ),
    )


# =============================================================================
# Narrative Summary Settings Models
# =============================================================================


class SummariesSettings(BaseModel):
    """Episode/season summary generation configuration."""

    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = Field(
        default=None,
        description=(
            "Registry model reference used for episode and season summaries. "
            "Absent (the default) follows the storyteller (apex.model); set "
            "explicitly to decouple the summarizer from the storyteller. All "
            "registered native and OpenAI-compatible providers are routable."
        ),
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for summary models that accept it.",
    )
    reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Reasoning effort for summary models that reject temperature.",
    )
    episode_max_output_tokens: int = Field(
        default=2500,
        gt=0,
        description="Maximum output tokens for episode summaries.",
    )
    season_max_output_tokens: int = Field(
        default=4000,
        gt=0,
        description="Maximum output tokens for season summaries.",
    )
    request_token_budget: int = Field(
        default=30000,
        gt=0,
        description=(
            "Conservative combined input/output token budget for one summary request."
        ),
    )
    structured_output_retries: int = Field(
        default=0,
        ge=0,
        description="Validation retry budget for structured summary output.",
    )

    @model_validator(mode="after")
    def _validate_request_budget(self) -> "SummariesSettings":
        """Keep each output allowance below the combined request budget."""

        largest_output = max(
            self.episode_max_output_tokens,
            self.season_max_output_tokens,
        )
        if self.request_token_budget <= largest_output:
            raise ValueError(
                "summaries.request_token_budget must exceed both summary "
                "max-output-token settings"
            )
        return self


# =============================================================================
# Wizard Settings Models
# =============================================================================


class WizardTraitInputsSettings(BaseModel):
    """Transition-time derivation of typed trait-compiler inputs."""

    model_config = ConfigDict(extra="forbid")

    derive_at_transition: bool = Field(
        default=True,
        description=(
            "Derive TraitCompileInputs via one structured Skald call at the "
            "wizard -> narrative transition when the wizard did not collect "
            "them conversationally"
        ),
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        description="Max output tokens for the trait input derivation call",
    )


class WizardSettings(BaseModel):
    """Wizard configuration for new story setup and structured responses."""

    model_config = ConfigDict(extra="forbid")

    default_model: str = Field(..., description="Default model for wizard flow")
    fallback_model: Optional[str] = Field(
        default=None,
        description="Optional fallback model (manual use only; no automatic failover)",
    )
    message_history_limit: int = Field(
        default=20, ge=1, description="Max message history to send per wizard turn"
    )
    max_retries: int = Field(
        default=2, ge=0, description="Retry budget for tool validation failures"
    )
    max_tokens: int = Field(
        default=4096, ge=1, description="Max output tokens for wizard responses"
    )
    enable_streaming: bool = Field(
        default=True, description="Enable wizard streaming endpoint"
    )
    trait_inputs: WizardTraitInputsSettings = Field(
        default_factory=WizardTraitInputsSettings,
        description="Transition-time trait input derivation settings",
    )


# =============================================================================
# API Constraints Settings Models
# =============================================================================


class APIConstraintsConfig(BaseModel):
    """API constraints configuration."""

    model_config = ConfigDict(extra="forbid")

    max_choice_text_length: int = Field(
        default=1000, ge=1, description="Maximum length of choice text"
    )


class APIDatabaseSettings(BaseModel):
    """Connection behavior for slot database access."""

    model_config = ConfigDict(extra="forbid")

    connect_timeout_seconds: int = Field(
        ...,
        ge=1,
        description=(
            "Postgres connect_timeout (seconds) for API pools and worker "
            "connections, bounding outage pain when the server is unreachable"
        ),
    )


class APIUploadsSettings(BaseModel):
    """Limits for image upload endpoints (character portraits, place images)."""

    model_config = ConfigDict(extra="forbid")

    max_file_size_mb: int = Field(
        ...,
        ge=1,
        description="Per-file size cap (MB) for image uploads",
    )
    max_files_per_request: int = Field(
        ...,
        ge=1,
        description="Maximum number of files accepted in one upload request",
    )


class APISettings(BaseModel):
    """Top-level API settings."""

    model_config = ConfigDict(extra="forbid")

    constraints: Optional[APIConstraintsConfig] = Field(
        default=None, description="API constraints configuration"
    )
    database: APIDatabaseSettings = Field(
        ..., description="Slot database connection behavior"
    )
    uploads: Optional[APIUploadsSettings] = Field(
        default=None, description="Image upload limits"
    )


# =============================================================================
# Root Settings Model
# =============================================================================


class IREvalJudgmentConfig(BaseModel):
    """LLM judgment-on-demand configuration for the IR eval V2 runner."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        ...,
        description="LLM model identifier for relevance judgments",
    )
    reasoning_effort: str = Field(
        default="high",
        description=(
            "Reasoning effort for the judgment model " "(e.g. minimal/medium/high)"
        ),
    )


class IREvalSettings(BaseModel):
    """Configuration for the IR evaluation V2 subsystem."""

    model_config = ConfigDict(extra="forbid")

    judgment: IREvalJudgmentConfig


class UIFontSlots(BaseModel):
    """Font choices for one theme's three slots (NEXUS IRIS keeper matrix).

    ``display`` is the marquee slot — reserved for the NEXUS wordmark per the
    design system's marquee rule. It is persisted for completeness but the
    settings pane renders it locked.
    """

    model_config = ConfigDict(extra="forbid")

    body: str = Field(..., description="Narrative prose font (--font-narrative)")
    menu: str = Field(..., description="Chrome/menu font (--font-mono)")
    display: str = Field(..., description="Marquee font (--font-display, locked)")


def _default_veil_fonts() -> UIFontSlots:
    return UIFontSlots(body="Spectral", menu="Cinzel", display="Megrim")


def _default_gilded_fonts() -> UIFontSlots:
    return UIFontSlots(body="Cormorant Garamond", menu="Space Mono", display="Monoton")


def _default_vector_fonts() -> UIFontSlots:
    return UIFontSlots(body="Rajdhani", menu="Source Code Pro", display="Sixtyfour")


class UIFontMatrix(BaseModel):
    """Per-theme font slot choices persisted from the settings pane."""

    model_config = ConfigDict(extra="forbid")

    veil: UIFontSlots = Field(default_factory=_default_veil_fonts)
    gilded: UIFontSlots = Field(default_factory=_default_gilded_fonts)
    vector: UIFontSlots = Field(default_factory=_default_vector_fonts)


def _default_lore_budget_stops() -> List[int]:
    return [75_000, 100_000, 150_000, 200_000]


class UILoreBudgetSlider(BaseModel):
    """Bounds and ladder stops for the LORE budget slider in the settings pane."""

    model_config = ConfigDict(extra="forbid")

    min: int = Field(default=10_000, ge=1000, description="Slider lower bound (tok)")
    max: int = Field(default=200_000, ge=1000, description="Slider upper bound (tok)")
    step: int = Field(default=1000, ge=1, description="Slider step size (tok)")
    stops: List[int] = Field(
        default_factory=_default_lore_budget_stops,
        description="Preset ladder stops rendered above the slider",
    )

    @model_validator(mode="after")
    def _validate_range(self) -> "UILoreBudgetSlider":
        if self.min > self.max:
            raise ValueError("lore_budget_slider min must be <= max")
        for stop in self.stops:
            if not self.min <= stop <= self.max:
                raise ValueError(
                    f"lore_budget_slider stop {stop} is outside "
                    f"[{self.min}, {self.max}]"
                )
        return self


class UILocalModelsSettings(BaseModel):
    """Cadence and interaction knobs for the local-model manager UI.

    Consumed by the settings-pane quant manager and the topbar memory
    meter; served raw through ``GET /api/settings`` like every other
    ``[ui]`` table.
    """

    model_config = ConfigDict(extra="forbid")

    poll_busy_ms: int = Field(
        default=1500,
        ge=250,
        le=60_000,
        description=(
            "Status poll interval (ms) while an activation swap is in "
            "flight — the UI is waiting for active.ready to flip"
        ),
    )
    poll_idle_ms: int = Field(
        default=15_000,
        ge=1000,
        le=300_000,
        description=(
            "Status poll interval (ms) at rest; catches llama-server "
            "changes made outside this client (CLI, another browser)"
        ),
    )
    download_poll_ms: int = Field(
        default=1000,
        ge=250,
        le=60_000,
        description="Download progress poll interval (ms)",
    )
    delete_arm_ms: int = Field(
        default=2800,
        ge=500,
        le=30_000,
        description=(
            "How long (ms) a quant delete stays armed after the first "
            "click before disarming back to safe"
        ),
    )


class UISettings(BaseModel):
    """Settings consumed by the React client.

    Served to the browser through ``GET /api/settings`` (FastAPI, proxied by
    Express; reads nexus.toml); keep keys JSON-friendly.
    """

    model_config = ConfigDict(extra="forbid")

    typewriter_ms_per_char: int = Field(
        default=35,
        ge=1,
        le=500,
        description=(
            "Typewriter reveal speed for incoming narrative chunks in "
            "milliseconds per character (design system: 30-50 ms/char)"
        ),
    )
    theme: Literal["veil", "gilded", "vector"] = Field(
        default="veil",
        description="Active NEXUS IRIS theme, persisted across sessions",
    )
    fonts: UIFontMatrix = Field(
        default_factory=UIFontMatrix,
        description="Per-theme font slot choices (keeper matrix)",
    )
    lore_budget_slider: UILoreBudgetSlider = Field(
        default_factory=UILoreBudgetSlider,
        description="Bounds and ladder stops for the LORE budget slider",
    )
    local_models: UILocalModelsSettings = Field(
        default_factory=UILocalModelsSettings,
        description="Cadence/interaction knobs for the local-model manager UI",
    )


class SecretsConfig(BaseModel):
    """Provider -> 1Password reference mappings.

    Consumed ONLY by ``scripts/sync_secrets.py`` during Keychain bootstrap or
    rotation. Runtime code never reads this section -- it reads from Keychain
    via ``nexus.util.secret_manager.get_secret``.

    Each value uses one of two schemes:

    * ``op-item:<item-id>:<field-name>`` -> resolved with ``op item get``.
    * ``op-read:<secret-reference>``     -> resolved with ``op read``.
    """

    model_config = ConfigDict(extra="forbid")

    providers: Dict[str, str] = Field(
        default_factory=dict,
        description="Provider name -> 1Password reference",
    )


class Settings(BaseModel):
    """
    Root configuration model for NEXUS.

    This model validates the entire nexus.toml configuration file and provides
    type-safe access to all settings. All nested models use `extra='forbid'` to
    catch typos and invalid keys at load time.
    """

    model_config = ConfigDict(extra="forbid")

    global_: GlobalSettings = Field(..., alias="global")
    local_models: LocalModelsSettings = Field(default_factory=LocalModelsSettings)
    secrets: Optional[SecretsConfig] = Field(
        default=None,
        description="Provider -> 1Password reference mappings (sync_secrets.py only)",
    )
    lore: LORESettings
    orrery: Optional[OrrerySettings] = Field(
        default=None,
        description="Off-screen behavior resolver settings",
    )
    memnon: MEMNONSettings
    memory: MemorySettings
    apex: APEXSettings
    summaries: SummariesSettings = Field(
        default_factory=SummariesSettings,
        description="Episode/season summary generation (follows apex by default)",
    )
    wizard: WizardSettings
    api: Optional[APISettings] = Field(default=None, description="API settings")
    ui: UISettings = Field(
        default_factory=UISettings,
        description="React client settings (served via GET /api/settings)",
    )
    ir_eval: Optional[IREvalSettings] = Field(
        default=None,
        description="IR evaluation subsystem settings",
    )
    runtime: Optional[RuntimeSettings] = Field(
        default=None,
        description="Managed runtime settings (nexus up/down/status/logs)",
    )

    @model_validator(mode="after")
    def _resolve_model_references(self) -> "Settings":
        """Resolve @provider.role refs in consumer fields and validate literal IDs.

        After this runs, every consumer field that names a model holds a literal
        ID, not an "@provider.role" reference. Downstream code therefore never
        sees role syntax — it can treat model fields as concrete IDs throughout.
        """
        registry = self._build_model_registry()
        # Each tuple is (container, attribute_name, optional_flag). When the
        # value is None on an optional field, skip resolution silently.
        targets: List[Tuple[Any, str, bool]] = [
            (self.global_.model, "default_model", False),
            (self.global_.model, "default_slot_model", False),
            (self.apex, "model", False),
            (self.summaries, "model", True),
            (self.wizard, "default_model", False),
            (self.wizard, "fallback_model", True),
        ]
        if self.orrery is not None:
            targets.append((self.orrery.narration, "model_ref", False))
            targets.append((self.orrery.retrograde.maturation, "model_ref", True))
        if self.ir_eval is not None and self.ir_eval.judgment is not None:
            targets.append((self.ir_eval.judgment, "model", False))

        for container, attr, optional in targets:
            current = getattr(container, attr)
            if current is None:
                if optional:
                    continue
                raise ValueError(
                    f"Required model field '{attr}' on "
                    f"{type(container).__name__} is missing"
                )
            resolved = _resolve_model_reference(
                current,
                registry=registry,
                source=f"{type(container).__name__}.{attr}",
            )
            # Mutate the child Pydantic model in place. We use object.__setattr__
            # rather than direct attribute assignment for two reasons:
            #   1. It works regardless of whether the child model is later marked
            #      frozen=True (Pydantic raises on direct assignment for frozen).
            #   2. It is intentionally a *bypass* — no @field_validator on the
            #      child model's `model` field will fire on the resolved value.
            #      If anyone later adds such a validator (e.g. on
            #      APEXSettings.model), they need to also wire it into this
            #      resolution pass or move that logic into _resolve_model_reference.
            object.__setattr__(container, attr, resolved)

        return self

    @model_validator(mode="after")
    def _resolve_summaries_model(self) -> "Settings":
        """Make summaries follow the storyteller unless explicitly decoupled."""

        if self.summaries.model is None:
            # Owner decision (2026-07-14): never choose a silently-cheaper
            # summarizer. Provider routing is shared across every registry model.
            self.summaries.model = self.apex.model
        return self

    @model_validator(mode="after")
    def _validate_param_capabilities(self) -> "Settings":
        """Refuse configured request params that the resolved model rejects.

        This is the enforcement boundary for Orrery narration sampling
        capability (issue #401): [orrery.narration] may only configure a
        sampling parameter when its resolved model does not list it in
        `unsupported_params`. Request builders send only explicitly configured
        params, so passing this validator guarantees Orrery never sends a
        narration parameter its provider rejects.

        Runs after ``_resolve_model_references`` (Pydantic executes model
        validators in definition order), so every model field holds a concrete
        registry ID by the time this checks it.
        """
        # Each tuple: (concrete model id, {param name: configured value}, source)
        checks: List[Tuple[str, Dict[str, Any], str]] = []
        if self.orrery is not None:
            checks.append(
                (
                    self.orrery.narration.model_ref,
                    {"temperature": self.orrery.narration.temperature},
                    "[orrery.narration]",
                )
            )

        for model_id, params, source in checks:
            entry = self.model_entry(model_id)
            for param, value in params.items():
                if value is None:
                    continue
                if param in entry.unsupported_params:
                    raise ValueError(
                        f"{source} configures {param}={value!r}, but model "
                        f"'{model_id}' declares '{param}' unsupported "
                        f"(unsupported_params in [global.model.api_models]). "
                        f"Remove the setting or choose a model that accepts it."
                    )
        return self

    @model_validator(mode="after")
    def _validate_runtime_mock_port_consistency(self) -> "Settings":
        """The mock service port and the test provider base_url must agree.

        The TEST registry entry's base_url is where clients send requests; the
        [runtime.services.mock_openai] port is where the supervisor binds the
        server. Drift between the two produces a runtime that "works" while
        every TEST call connection-refuses, so it is rejected at load.
        """
        if self.runtime is None:
            return self
        mock = self.runtime.services.get("mock_openai")
        test_provider = self.global_.model.api_models.get("test")
        if mock is None or mock.enabled == "never":
            return self
        if test_provider is None or not test_provider.base_url:
            return self
        from urllib.parse import urlparse

        base_port = urlparse(test_provider.base_url).port
        if base_port != mock.port:
            raise ValueError(
                f"[runtime.services.mock_openai] port {mock.port} does not match "
                f"the test provider base_url port {base_port} "
                f"({test_provider.base_url}). Keep them in sync."
            )
        return self

    @model_validator(mode="after")
    def _validate_runtime_llama_server_port_consistency(self) -> "Settings":
        """The llama_server service port and the local provider base_url must agree.

        Same failure mode as the mock/test pairing: if the supervised
        [runtime.services.llama_server] binds a different port than the local
        provider's base_url targets, every @local call connection-refuses at
        request time. Reject the drift at load instead. Skipped while the
        service is disabled (enabled = "never"), since nothing binds then.
        """
        if self.runtime is None:
            return self
        llama = self.runtime.services.get("llama_server")
        local_provider = self.global_.model.api_models.get("local")
        if llama is None or llama.enabled == "never":
            return self
        if local_provider is None or not local_provider.base_url:
            return self
        from urllib.parse import urlparse

        base_port = urlparse(local_provider.base_url).port
        if base_port != llama.port:
            raise ValueError(
                f"[runtime.services.llama_server] port {llama.port} does not "
                f"match the local provider base_url port {base_port} "
                f"({local_provider.base_url}). Keep them in sync."
            )
        return self

    def model_entry(self, model_id: str) -> APIModelEntry:
        """Return the registry entry for a concrete model ID (raises if absent)."""
        for provider_models in self.global_.model.api_models.values():
            for entry in provider_models.models:
                if entry.id == model_id:
                    return entry
        raise ValueError(
            f"Model ID '{model_id}' is not declared in "
            f"[global.model.api_models.*].models"
        )

    def provider_for_model(self, model_id: str) -> str:
        """Return the provider name owning a concrete model ID (raises if absent)."""
        for provider, provider_models in self.global_.model.api_models.items():
            for entry in provider_models.models:
                if entry.id == model_id:
                    return provider
        raise ValueError(
            f"Model ID '{model_id}' is not declared in "
            f"[global.model.api_models.*].models"
        )

    def resolve_model_ref(self, ref: str) -> str:
        """Resolve an "@provider.role" reference against the api_models registry.

        Literal model IDs are validated against the registry and returned
        unchanged. Intended for callers outside the load-time resolution pass
        (live tests, env overrides) that accept role references at runtime.
        """
        return _resolve_model_reference(
            ref,
            registry=self._build_model_registry(),
            source="Settings.resolve_model_ref",
        )

    def _build_model_registry(self) -> _ModelRegistry:
        """Index [global.model.api_models] for fast role / literal-ID lookup.

        Returns a small dataclass with two maps: provider→{role→id} and id→provider.
        Both are needed by ``_resolve_model_reference`` — the first to resolve
        ``@provider.role`` refs, the second to validate that any literal ID
        names a model declared *somewhere* in the registry.
        """
        roles: Dict[str, Dict[str, str]] = {}
        all_ids: Dict[str, str] = {}
        for provider, provider_models in self.global_.model.api_models.items():
            roles[provider] = dict(provider_models.roles)
            for entry in provider_models.models:
                all_ids[entry.id] = provider
        return _ModelRegistry(roles=roles, all_ids=all_ids)

    def model_dump(self, **kwargs) -> dict:
        """
        Convert settings to dict, preserving dict-style access.

        This keeps existing settings.get("key", default) callers working.
        """
        return super().model_dump(by_alias=True, **kwargs)


def _resolve_model_reference(
    value: str,
    *,
    registry: _ModelRegistry,
    source: str,
) -> str:
    """Resolve @provider.role references and validate literal model IDs.

    - "@<provider>.<role>" is looked up in ``registry.roles[provider][role]``
      and replaced with the concrete model ID from the api_models entry.
    - Literal IDs are validated against ``registry.all_ids``; unknown IDs raise
      ValueError with the source field for debuggability.

    Raises ValueError on:
    - Malformed @ref (missing dot separator).
    - Unknown provider in @ref.
    - Unknown role for known provider.
    - Literal ID not present in any provider's model list.
    """
    if not isinstance(value, str):
        raise TypeError(f"{source}: expected string, got {type(value).__name__}")

    if value.startswith(MODEL_ROLE_PREFIX):
        body = value[len(MODEL_ROLE_PREFIX) :]
        if "." not in body:
            raise ValueError(
                f"{source}: malformed model role reference '{value}'. "
                f"Expected '@provider.role' (e.g., '@openai.default')"
            )
        provider, role = body.split(".", 1)
        provider_roles = registry.roles.get(provider)
        if provider_roles is None:
            known = sorted(registry.roles)
            raise ValueError(
                f"{source}: unknown provider '{provider}' in '{value}'. "
                f"Known providers: {known}"
            )
        resolved = provider_roles.get(role)
        if resolved is None:
            known_roles = sorted(provider_roles)
            raise ValueError(
                f"{source}: provider '{provider}' has no role '{role}'. "
                f"Known roles: {known_roles}"
            )
        return resolved

    # Literal ID — validate it exists somewhere in the registry.
    if value not in registry.all_ids:
        known = sorted(registry.all_ids)
        raise ValueError(
            f"{source}: model ID '{value}' is not declared in "
            f"[global.model.api_models.*].models. Known IDs: {known}. "
            f"Either add it to the registry or use a '@provider.role' reference."
        )
    return value
