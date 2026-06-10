"""
Pydantic models for NEXUS configuration validation.

These models provide type-safe, validated access to settings from nexus.toml.
All models use `extra='forbid'` to catch typos in configuration keys.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, ConfigDict, model_validator


# String prefix used for role references in consumer fields.
# Example: "@openai.default" resolves via api_models.openai.roles.default
MODEL_ROLE_PREFIX = "@"


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
        """Legacy/default UI fields must stay anchored to registered model IDs."""
        known_ids = {
            entry.id
            for provider in self.api_models.values()
            for entry in provider.models
        }
        for field_name in ("default_model", "default_slot_model"):
            model_id = getattr(self, field_name)
            if model_id not in known_ids:
                raise ValueError(
                    f"{field_name} references unknown model id '{model_id}'. "
                    f"Known IDs: {sorted(known_ids)}"
                )
        return self


class NarrativeConfig(BaseModel):
    """Narrative test mode settings."""

    model_config = ConfigDict(extra="forbid")

    test_mode: bool = Field(..., description="Enable test mode")
    test_database_suffix: str = Field(..., description="Database suffix for testing")


class GlobalAPIConfig(BaseModel):
    """Global API configuration."""

    model_config = ConfigDict(extra="forbid")

    test_mock_server_url: str = Field(
        default="http://localhost:5102/v1", description="Mock server URL for TEST model"
    )


class GlobalSettings(BaseModel):
    """Global configuration settings."""

    model_config = ConfigDict(extra="forbid")

    model: ModelConfig
    narrative: NarrativeConfig
    api: Optional[GlobalAPIConfig] = Field(
        default=None, description="API configuration"
    )


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
        description="Deprecated and ignored; Bleed fetches max_candidates.",
    )
    max_candidates: int = Field(default=3, ge=0)


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

    summary_chunks: bool = Field(
        default=True,
        description=(
            "Write one finalized prose summary chunk per persisted Retrograde "
            "world event so MEMNON chunk search retrieves generated history."
        ),
    )
    embed_after_apply: bool = Field(
        default=True,
        description=(
            "Trigger the standard chunk embedding lifecycle for pending "
            "Retrograde summary chunks immediately after a successful apply."
        ),
    )


class OrreryRetrogradeSettings(BaseModel):
    """Retrograde deep-history generation settings."""

    model_config = ConfigDict(extra="forbid")

    weird: OrreryRetrogradeWeirdSettings
    retrieval: OrreryRetrogradeRetrievalSettings = Field(
        default_factory=OrreryRetrogradeRetrievalSettings
    )


class OrrerySettings(BaseModel):
    """Orrery off-screen behavior settings.

    Retrograde config is intentionally required so every slot has explicit
    weird-dial genre remapping before generation code starts reading it.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    binding: OrreryBindingSettings = Field(default_factory=OrreryBindingSettings)
    route_graph: OrreryRouteGraphSettings = Field(
        default_factory=OrreryRouteGraphSettings
    )
    narration: OrreryNarrationSettings
    bleed: OrreryBleedSettings = Field(default_factory=OrreryBleedSettings)
    promote: OrreryPromoteSettings = Field(default_factory=OrreryPromoteSettings)
    sunhelm: OrrerySunhelmSettings = Field(default_factory=OrrerySunhelmSettings)
    retrograde: OrreryRetrogradeSettings


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

    provider: str = Field(..., pattern="^(openai|anthropic)$")
    model: str
    reasoning_effort: str = Field(..., pattern="^(low|medium|high)$")
    max_output_tokens: int = Field(..., ge=1)


# =============================================================================
# Wizard Settings Models
# =============================================================================


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


# =============================================================================
# API Constraints Settings Models
# =============================================================================


class APIConstraintsConfig(BaseModel):
    """API constraints configuration."""

    model_config = ConfigDict(extra="forbid")

    max_choice_text_length: int = Field(
        default=1000, ge=1, description="Maximum length of choice text"
    )


class APISettings(BaseModel):
    """Top-level API settings."""

    model_config = ConfigDict(extra="forbid")

    constraints: Optional[APIConstraintsConfig] = Field(
        default=None, description="API constraints configuration"
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


class UISettings(BaseModel):
    """Settings consumed by the React client.

    Served verbatim to the browser through the Express ``GET /api/settings``
    endpoint (which reads nexus.toml); keep keys JSON-friendly.
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
            (self.apex, "model", False),
            (self.wizard, "default_model", False),
            (self.wizard, "fallback_model", True),
        ]
        if self.orrery is not None:
            targets.append((self.orrery.narration, "model_ref", False))
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
