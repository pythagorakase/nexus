"""
Pydantic models for NEXUS configuration validation.

These models provide type-safe, validated access to settings from nexus.toml.
All models use `extra='forbid'` to catch typos in configuration keys.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Global Settings Models
# =============================================================================

class APIModelEntry(BaseModel):
    """Single API model definition."""
    model_config = ConfigDict(extra='forbid')

    id: str = Field(..., description="Model identifier (e.g., 'gpt-5.2', 'claude')")
    label: str = Field(..., description="Display label for UI")
    description: Optional[str] = Field(default=None, description="Human-readable description (optional)")


class ProviderModels(BaseModel):
    """Models for a single API provider."""
    model_config = ConfigDict(extra='forbid')

    models: List[APIModelEntry] = Field(
        default_factory=list,
        description="List of models available from this provider"
    )


class ModelConfig(BaseModel):
    """LLM model configuration with provider grouping."""
    model_config = ConfigDict(extra='forbid')

    default_model: str = Field(..., description="Default model to load for local inference")
    possible_values: List[str] = Field(..., description="Available local model options")
    default_slot_model: str = Field(
        default="TEST",
        description="Default model for newly created/reset slots"
    )
    api_models: Dict[str, ProviderModels] = Field(
        default_factory=dict,
        description="API models grouped by provider (openai, anthropic, test)"
    )


class LLMConfig(BaseModel):
    """Local LLM API settings (LM Studio)."""
    model_config = ConfigDict(extra='forbid')

    api_base: str = Field(..., description="LM Studio API endpoint")
    context_window: int = Field(..., ge=1024, description="Maximum context length")
    temperature: float = Field(..., ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(..., ge=1, description="Maximum output tokens")


class NarrativeConfig(BaseModel):
    """Narrative test mode settings."""
    model_config = ConfigDict(extra='forbid')

    test_mode: bool = Field(..., description="Enable test mode")
    test_database_suffix: str = Field(..., description="Database suffix for testing")


class GlobalAPIConfig(BaseModel):
    """Global API configuration."""
    model_config = ConfigDict(extra='forbid')

    test_mock_server_url: str = Field(
        default="http://localhost:5102/v1",
        description="Mock server URL for TEST model"
    )


class GlobalSettings(BaseModel):
    """Global configuration settings."""
    model_config = ConfigDict(extra='forbid')

    model: ModelConfig
    llm: LLMConfig
    narrative: NarrativeConfig
    api: Optional[GlobalAPIConfig] = Field(default=None, description="API configuration")


# =============================================================================
# LORE Agent Settings Models
# =============================================================================

class TokenBudgetConfig(BaseModel):
    """Token budget allocation for APEX generation."""
    model_config = ConfigDict(extra='forbid')

    apex_context_window: int = Field(..., ge=1000, description="Total tokens for APEX")
    system_prompt_tokens: int = Field(..., ge=100, description="Reserved for system prompt")


class PayloadBudgetRange(BaseModel):
    """Min/max percentage range for payload budget allocation."""
    model_config = ConfigDict(extra='forbid')

    min: int = Field(..., ge=0, le=100, description="Minimum percentage")
    max: int = Field(..., ge=0, le=100, description="Maximum percentage")


class PayloadPercentBudget(BaseModel):
    """Percentage allocations for different context payload sections."""
    model_config = ConfigDict(extra='forbid')

    structured_summaries: PayloadBudgetRange
    contextual_augmentation: PayloadBudgetRange
    warm_slice: PayloadBudgetRange


class EntityInclusionConfig(BaseModel):
    """Configuration for entity inclusion in context payloads."""
    model_config = ConfigDict(extra='forbid')

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


class LORESettings(BaseModel):
    """LORE agent configuration."""
    model_config = ConfigDict(extra='forbid')

    debug: bool
    agentic_sql: bool
    token_budget: TokenBudgetConfig
    payload_percent_budget: PayloadPercentBudget
    entity_inclusion: EntityInclusionConfig


# =============================================================================
# MEMNON Agent Settings Models
# =============================================================================

class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    model_config = ConfigDict(extra='forbid')

    url: str = Field(..., description="PostgreSQL connection URL")
    create_tables: bool
    drop_existing: bool


class EmbeddingModelConfig(BaseModel):
    """Configuration for an individual embedding model."""
    model_config = ConfigDict(extra='forbid')

    is_active: bool
    local_path: str
    remote_path: Optional[str] = None
    dimensions: int = Field(..., ge=1)
    weight: float = Field(..., ge=0.0, le=1.0, description="Ensemble weight")


class ImportConfig(BaseModel):
    """Settings for importing narrative chunks."""
    model_config = ConfigDict(extra='forbid')

    base_directory: str
    file_pattern: str
    chunk_regex: str
    batch_size: int = Field(..., ge=1)
    verbose: bool
    file_limit: Optional[int] = None


class QueryConfig(BaseModel):
    """Default query settings."""
    model_config = ConfigDict(extra='forbid')

    default_limit: int = Field(..., ge=1)
    include_vector_results: int = Field(..., ge=0)
    include_text_results: int = Field(..., ge=0)
    include_structured_results: int = Field(..., ge=0)


class SourceWeights(BaseModel):
    """Relative weights for different retrieval sources."""
    model_config = ConfigDict(extra='forbid')

    structured_data: float = Field(..., ge=0.0)
    vector_search: float = Field(..., ge=0.0)
    text_search: float = Field(..., ge=0.0)


class VectorNormalizationConfig(BaseModel):
    """Vector search score normalization settings."""
    model_config = ConfigDict(extra='forbid')

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
    model_config = ConfigDict(extra='forbid')

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
    model_config = ConfigDict(extra='forbid')

    vector: float = Field(..., ge=0.0, le=1.0)
    text: float = Field(..., ge=0.0, le=1.0)


class HybridSearchConfig(BaseModel):
    """Hybrid search (vector + text) configuration."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool
    vector_weight_default: float = Field(..., ge=0.0, le=1.0)
    text_weight_default: float = Field(..., ge=0.0, le=1.0)
    weights_by_query_type: Dict[str, QueryTypeWeights]
    temporal_boost_factors: Dict[str, float]
    use_query_type_weights: bool
    use_query_type_temporal_factors: bool
    target_model: str
    temporal_boost_factor: float = Field(..., ge=0.0)


class CrossEncoderReranking(BaseModel):
    """Cross-encoder reranking configuration."""
    model_config = ConfigDict(extra='forbid', protected_namespaces=())

    enabled: bool
    model_path: str
    blend_weight: float = Field(..., ge=0.0, le=1.0)
    top_k: int = Field(..., ge=1)
    batch_size: int = Field(..., ge=1)
    use_sliding_window: bool
    window_size: int = Field(..., ge=1)
    window_overlap: int = Field(..., ge=0)
    weights_by_query_type: Dict[str, float]
    use_query_type_weights: bool
    use_8bit: bool


class RetrievalConfig(BaseModel):
    """Main retrieval configuration."""
    model_config = ConfigDict(extra='forbid')

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
    model_config = ConfigDict(extra='forbid')

    file: str
    level: str = Field(..., pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    console: bool


class MEMNONSettings(BaseModel):
    """MEMNON agent configuration."""
    model_config = ConfigDict(extra='forbid')

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

class DivergenceDetectionConfig(BaseModel):
    """Divergence detection configuration."""
    model_config = ConfigDict(extra='forbid')

    use_llm: bool
    use_local_llm: bool
    llm_temperature: float = Field(..., ge=0.0, le=2.0)
    llm_max_tokens: int = Field(..., ge=1)
    confidence_threshold: float = Field(..., ge=0.0, le=1.0)


class MemorySettings(BaseModel):
    """Memory manager configuration."""
    model_config = ConfigDict(extra='forbid')

    phase2_fraction: float = Field(..., ge=0.0, le=1.0)
    raw_search_k: int = Field(..., ge=1)
    skip_simple_choices: bool
    pass2_budget_reserve: float = Field(..., ge=0.0, le=1.0)
    divergence_threshold: float = Field(..., ge=0.0, le=1.0)
    warm_slice_default: bool
    max_sql_iterations: int = Field(..., ge=1)
    divergence_detection: DivergenceDetectionConfig


# =============================================================================
# APEX API Settings Models
# =============================================================================

class APEXSettings(BaseModel):
    """APEX API configuration for story generation."""
    model_config = ConfigDict(extra='forbid')

    provider: str = Field(..., pattern="^(openai|anthropic)$")
    model: str
    reasoning_effort: str = Field(..., pattern="^(low|medium|high)$")
    max_output_tokens: int = Field(..., ge=1)


# =============================================================================
# Wizard Settings Models
# =============================================================================

class WizardSettings(BaseModel):
    """Wizard configuration for new story setup and structured responses."""
    model_config = ConfigDict(extra='forbid')

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
        default=2048, ge=1, description="Max output tokens for wizard responses"
    )
    enable_streaming: bool = Field(
        default=True, description="Enable wizard streaming endpoint"
    )


# =============================================================================
# API Constraints Settings Models
# =============================================================================

class APIConstraintsConfig(BaseModel):
    """API constraints configuration."""
    model_config = ConfigDict(extra='forbid')

    max_choice_text_length: int = Field(
        default=1000,
        ge=1,
        description="Maximum length of choice text"
    )


class APISettings(BaseModel):
    """Top-level API settings."""
    model_config = ConfigDict(extra='forbid')

    constraints: Optional[APIConstraintsConfig] = Field(
        default=None,
        description="API constraints configuration"
    )


# =============================================================================
# Root Settings Model
# =============================================================================

class Settings(BaseModel):
    """
    Root configuration model for NEXUS.

    This model validates the entire nexus.toml configuration file and provides
    type-safe access to all settings. All nested models use `extra='forbid'` to
    catch typos and invalid keys at load time.
    """
    model_config = ConfigDict(extra='forbid')

    global_: GlobalSettings = Field(..., alias="global")
    lore: LORESettings
    memnon: MEMNONSettings
    memory: MemorySettings
    apex: APEXSettings
    wizard: WizardSettings
    api: Optional[APISettings] = Field(default=None, description="API settings")

    def model_dump(self, **kwargs) -> dict:
        """
        Convert settings to dict, preserving dict-style access for backward compatibility.

        This ensures that existing code using settings.get("key", default) continues to work.
        """
        return super().model_dump(by_alias=True, **kwargs)
