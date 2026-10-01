"""Prove the legacy settings façade and the typed models agree on every value.

``load_settings_as_dict()`` rebuilds ``Agent Settings`` (``global``, ``LORE``,
``MEMNON``) and ``API Settings`` (``apex``) from the typed ``Settings``. Before
any reader moves from those aliases to the typed models, this module pins the
invariant the move relies on: each façade leaf has one declared typed owner,
and both paths yield the same effective value. ``OWNERSHIP`` is the seed of
issue #809's ownership matrix and stays plain data.
"""

from __future__ import annotations

import copy
from enum import Enum
from pathlib import PurePath
from typing import Any

import pytest
from pydantic import BaseModel

from nexus.config.loader import load_settings, load_settings_as_dict
from nexus.config.settings_models import Settings

FacadePath = tuple[str, ...]

# Each façade root and the typed ``Settings`` attribute that builds it.
FACADE_ROOTS: dict[FacadePath, str] = {
    ("Agent Settings", "global"): "global_",
    ("Agent Settings", "LORE"): "lore",
    ("Agent Settings", "MEMNON"): "memnon",
    ("API Settings", "apex"): "apex",
}

# Open-keyed registries the façade copies wholesale. Their keys are data, not
# schema, so the whole sub-tree is compared instead of each leaf.
DYNAMIC_REGISTRIES: dict[FacadePath, tuple[str, str]] = {
    ("Agent Settings", "global", "model", "api_models"): (
        "global_.model.api_models",
        "provider registry keyed by provider name; entries carry model rosters",
    ),
    ("Agent Settings", "LORE", "token_budget", "provider_overrides"): (
        "lore.token_budget.provider_overrides",
        "context-window overrides keyed by registry provider name",
    ),
    ("Agent Settings", "LORE", "entity_inclusion", "provider_overrides"): (
        "lore.entity_inclusion.provider_overrides",
        "entity-inclusion overrides keyed by registry provider name",
    ),
    ("Agent Settings", "MEMNON", "models"): (
        "memnon.models",
        "embedding model registry keyed by model name",
    ),
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "weights_by_query_type",
    ): (
        "memnon.retrieval.hybrid_search.weights_by_query_type",
        "hybrid weights keyed by query type",
    ),
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "temporal_boost_factors",
    ): (
        "memnon.retrieval.hybrid_search.temporal_boost_factors",
        "temporal boost factors keyed by query type",
    ),
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "presence_boost_factors",
    ): (
        "memnon.retrieval.hybrid_search.presence_boost_factors",
        "presence boost factors keyed by query type",
    ),
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "weights_by_query_type",
    ): (
        "memnon.retrieval.cross_encoder_reranking.weights_by_query_type",
        "reranker blend weights keyed by query type",
    ),
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "candidates",
    ): (
        "memnon.retrieval.cross_encoder_reranking.candidates",
        "reranker candidate registry keyed by candidate name",
    ),
}

# Every other façade leaf and its typed owner path on ``Settings``.
OWNERSHIP: dict[FacadePath, str] = {
    (
        "Agent Settings",
        "global",
        "model",
        "tokenizer_probe_timeout_seconds",
    ): "global_.model.tokenizer_probe_timeout_seconds",
    (
        "Agent Settings",
        "global",
        "model",
        "default_model_policy",
    ): "global_.model.default_model_policy",
    (
        "Agent Settings",
        "global",
        "model",
        "default_model",
    ): "global_.model.default_model",
    (
        "Agent Settings",
        "global",
        "model",
        "default_slot_model",
    ): "global_.model.default_slot_model",
    ("Agent Settings", "LORE", "debug"): "lore.debug",
    ("Agent Settings", "LORE", "agentic_sql"): "lore.agentic_sql",
    (
        "Agent Settings",
        "LORE",
        "render_limits",
        "relationships",
    ): "lore.render_limits.relationships",
    ("Agent Settings", "LORE", "render_limits", "events"): "lore.render_limits.events",
    (
        "Agent Settings",
        "LORE",
        "render_limits",
        "threats",
    ): "lore.render_limits.threats",
    (
        "Agent Settings",
        "LORE",
        "render_limits",
        "bleed_menu",
    ): "lore.render_limits.bleed_menu",
    (
        "Agent Settings",
        "LORE",
        "render_limits",
        "historical_passages",
    ): "lore.render_limits.historical_passages",
    (
        "Agent Settings",
        "LORE",
        "render_limits",
        "character_tags",
    ): "lore.render_limits.character_tags",
    (
        "Agent Settings",
        "LORE",
        "chunk_parameters",
        "warm_slice_initial",
    ): "lore.chunk_parameters.warm_slice_initial",
    (
        "Agent Settings",
        "LORE",
        "token_budget",
        "apex_context_window",
    ): "lore.token_budget.apex_context_window",
    (
        "Agent Settings",
        "LORE",
        "token_budget",
        "system_prompt_tokens",
    ): "lore.token_budget.system_prompt_tokens",
    (
        "Agent Settings",
        "LORE",
        "token_budget",
        "prompt_overhead_tokens",
    ): "lore.token_budget.prompt_overhead_tokens",
    (
        "Agent Settings",
        "LORE",
        "payload_percent_budget",
        "structured_summaries",
        "min",
    ): "lore.payload_percent_budget.structured_summaries.min",
    (
        "Agent Settings",
        "LORE",
        "payload_percent_budget",
        "structured_summaries",
        "max",
    ): "lore.payload_percent_budget.structured_summaries.max",
    (
        "Agent Settings",
        "LORE",
        "payload_percent_budget",
        "contextual_augmentation",
        "min",
    ): "lore.payload_percent_budget.contextual_augmentation.min",
    (
        "Agent Settings",
        "LORE",
        "payload_percent_budget",
        "contextual_augmentation",
        "max",
    ): "lore.payload_percent_budget.contextual_augmentation.max",
    (
        "Agent Settings",
        "LORE",
        "payload_percent_budget",
        "warm_slice",
        "min",
    ): "lore.payload_percent_budget.warm_slice.min",
    (
        "Agent Settings",
        "LORE",
        "payload_percent_budget",
        "warm_slice",
        "max",
    ): "lore.payload_percent_budget.warm_slice.max",
    (
        "Agent Settings",
        "LORE",
        "entity_inclusion",
        "warm_slice_lookback_chunks",
    ): "lore.entity_inclusion.warm_slice_lookback_chunks",
    (
        "Agent Settings",
        "LORE",
        "entity_inclusion",
        "max_characters_from_warm_slice",
    ): "lore.entity_inclusion.max_characters_from_warm_slice",
    (
        "Agent Settings",
        "LORE",
        "entity_inclusion",
        "max_locations_from_warm_slice",
    ): "lore.entity_inclusion.max_locations_from_warm_slice",
    (
        "Agent Settings",
        "LORE",
        "entity_inclusion",
        "include_all_relationships",
    ): "lore.entity_inclusion.include_all_relationships",
    (
        "Agent Settings",
        "LORE",
        "entity_inclusion",
        "max_total_characters",
    ): "lore.entity_inclusion.max_total_characters",
    (
        "Agent Settings",
        "LORE",
        "entity_inclusion",
        "max_total_relationships",
    ): "lore.entity_inclusion.max_total_relationships",
    (
        "Agent Settings",
        "LORE",
        "retrieval",
        "max_deep_queries",
    ): "lore.retrieval.max_deep_queries",
    (
        "Agent Settings",
        "LORE",
        "retrieval",
        "deep_query_k",
    ): "lore.retrieval.deep_query_k",
    (
        "Agent Settings",
        "LORE",
        "presence_audit",
        "enabled",
    ): "lore.presence_audit.enabled",
    ("Agent Settings", "MEMNON", "debug"): "memnon.debug",
    ("Agent Settings", "MEMNON", "database", "url"): "memnon.database.url",
    (
        "Agent Settings",
        "MEMNON",
        "database",
        "create_tables",
    ): "memnon.database.create_tables",
    (
        "Agent Settings",
        "MEMNON",
        "database",
        "drop_existing",
    ): "memnon.database.drop_existing",
    (
        "Agent Settings",
        "MEMNON",
        "artifacts",
        "lock_file",
    ): "memnon.artifacts.lock_file",
    (
        "Agent Settings",
        "MEMNON",
        "import",
        "base_directory",
    ): "memnon.import_.base_directory",
    (
        "Agent Settings",
        "MEMNON",
        "import",
        "file_pattern",
    ): "memnon.import_.file_pattern",
    ("Agent Settings", "MEMNON", "import", "chunk_regex"): "memnon.import_.chunk_regex",
    ("Agent Settings", "MEMNON", "import", "batch_size"): "memnon.import_.batch_size",
    ("Agent Settings", "MEMNON", "import", "verbose"): "memnon.import_.verbose",
    ("Agent Settings", "MEMNON", "import", "file_limit"): "memnon.import_.file_limit",
    (
        "Agent Settings",
        "MEMNON",
        "query",
        "default_limit",
    ): "memnon.query.default_limit",
    (
        "Agent Settings",
        "MEMNON",
        "query",
        "include_vector_results",
    ): "memnon.query.include_vector_results",
    (
        "Agent Settings",
        "MEMNON",
        "query",
        "include_text_results",
    ): "memnon.query.include_text_results",
    (
        "Agent Settings",
        "MEMNON",
        "query",
        "include_structured_results",
    ): "memnon.query.include_structured_results",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "max_results",
    ): "memnon.retrieval.max_results",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "ann",
        "min_documents",
    ): "memnon.retrieval.ann.min_documents",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "ann",
        "max_exact_p95_ms",
    ): "memnon.retrieval.ann.max_exact_p95_ms",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "ann",
        "minimum_recall_at_10",
    ): "memnon.retrieval.ann.minimum_recall_at_10",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "ann",
        "ef_search",
    ): "memnon.retrieval.ann.ef_search",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "ann",
        "probe_queries",
    ): "memnon.retrieval.ann.probe_queries",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "relevance_threshold",
    ): "memnon.retrieval.relevance_threshold",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "entity_boost_factor",
    ): "memnon.retrieval.entity_boost_factor",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "source_weights",
        "structured_data",
    ): "memnon.retrieval.source_weights.structured_data",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "source_weights",
        "vector_search",
    ): "memnon.retrieval.source_weights.vector_search",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "source_weights",
        "text_search",
    ): "memnon.retrieval.source_weights.text_search",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "enabled",
    ): "memnon.retrieval.vector_normalization.enabled",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "low_tier_map_enabled",
    ): "memnon.retrieval.vector_normalization.low_tier_map_enabled",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "low_tier_threshold",
    ): "memnon.retrieval.vector_normalization.low_tier_threshold",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "low_tier_input_max",
    ): "memnon.retrieval.vector_normalization.low_tier_input_max",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "low_tier_output_min",
    ): "memnon.retrieval.vector_normalization.low_tier_output_min",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "low_tier_output_max",
    ): "memnon.retrieval.vector_normalization.low_tier_output_max",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "below_low_tier_scale_factor",
    ): "memnon.retrieval.vector_normalization.below_low_tier_scale_factor",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "tiers",
    ): "memnon.retrieval.vector_normalization.tiers",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "text_search_base_score",
    ): "memnon.retrieval.text_search_base_score",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "text_search_count_bonus",
    ): "memnon.retrieval.text_search_count_bonus",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "text_search_max_score",
    ): "memnon.retrieval.text_search_max_score",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "structured_search_char_score",
    ): "memnon.retrieval.structured_search_char_score",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "structured_search_place_score",
    ): "memnon.retrieval.structured_search_place_score",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "user_character_focus_boost",
        "enabled",
    ): "memnon.retrieval.user_character_focus_boost.enabled",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "user_character_focus_boost",
        "action_patterns",
    ): "memnon.retrieval.user_character_focus_boost.action_patterns",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "user_character_focus_boost",
        "emotional_patterns",
    ): "memnon.retrieval.user_character_focus_boost.emotional_patterns",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "user_character_focus_boost",
        "knowledge_terms",
    ): "memnon.retrieval.user_character_focus_boost.knowledge_terms",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "user_character_focus_boost",
        "action_pattern_weight",
    ): "memnon.retrieval.user_character_focus_boost.action_pattern_weight",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "user_character_focus_boost",
        "emotional_pattern_weight",
    ): "memnon.retrieval.user_character_focus_boost.emotional_pattern_weight",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "user_character_focus_boost",
        "knowledge_term_weight",
    ): "memnon.retrieval.user_character_focus_boost.knowledge_term_weight",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "user_character_focus_boost",
        "max_boost",
    ): "memnon.retrieval.user_character_focus_boost.max_boost",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "enabled",
    ): "memnon.retrieval.hybrid_search.enabled",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "vector_weight_default",
    ): "memnon.retrieval.hybrid_search.vector_weight_default",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "text_weight_default",
    ): "memnon.retrieval.hybrid_search.text_weight_default",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "presence_boost_enabled",
    ): "memnon.retrieval.hybrid_search.presence_boost_enabled",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "presence_boost_factor",
    ): "memnon.retrieval.hybrid_search.presence_boost_factor",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "use_query_type_weights",
    ): "memnon.retrieval.hybrid_search.use_query_type_weights",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "use_query_type_temporal_factors",
    ): "memnon.retrieval.hybrid_search.use_query_type_temporal_factors",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "hybrid_search",
        "temporal_boost_factor",
    ): "memnon.retrieval.hybrid_search.temporal_boost_factor",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "enabled",
    ): "memnon.retrieval.cross_encoder_reranking.enabled",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "model_path",
    ): "memnon.retrieval.cross_encoder_reranking.model_path",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "api_type",
    ): "memnon.retrieval.cross_encoder_reranking.api_type",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "blend_weight",
    ): "memnon.retrieval.cross_encoder_reranking.blend_weight",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "top_k",
    ): "memnon.retrieval.cross_encoder_reranking.top_k",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "batch_size",
    ): "memnon.retrieval.cross_encoder_reranking.batch_size",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "use_sliding_window",
    ): "memnon.retrieval.cross_encoder_reranking.use_sliding_window",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "window_size",
    ): "memnon.retrieval.cross_encoder_reranking.window_size",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "window_overlap",
    ): "memnon.retrieval.cross_encoder_reranking.window_overlap",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "cross_encoder_reranking",
        "use_query_type_weights",
    ): "memnon.retrieval.cross_encoder_reranking.use_query_type_weights",
    (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "structured_data_enabled",
    ): "memnon.retrieval.structured_data_enabled",
    ("Agent Settings", "MEMNON", "logging", "file"): "memnon.logging.file",
    ("Agent Settings", "MEMNON", "logging", "level"): "memnon.logging.level",
    ("Agent Settings", "MEMNON", "logging", "console"): "memnon.logging.console",
    ("API Settings", "apex", "max_output_tokens"): "apex.max_output_tokens",
    (
        "API Settings",
        "apex",
        "reasoning_reserve_tokens",
    ): "apex.reasoning_reserve_tokens",
    ("API Settings", "apex", "response_reserve_tokens"): "apex.response_reserve_tokens",
    (
        "API Settings",
        "apex",
        "gaia",
        "max_output_tokens",
    ): "apex.gaia.max_output_tokens",
    (
        "API Settings",
        "apex",
        "gaia",
        "reasoning_reserve_tokens",
    ): "apex.gaia.reasoning_reserve_tokens",
    (
        "API Settings",
        "apex",
        "gaia",
        "response_reserve_tokens",
    ): "apex.gaia.response_reserve_tokens",
    ("API Settings", "apex", "gaia", "reasoning_effort"): "apex.gaia.reasoning_effort",
    ("API Settings", "apex", "gaia", "temperature"): "apex.gaia.temperature",
    ("API Settings", "apex", "temperature"): "apex.temperature",
    ("API Settings", "apex", "provider"): "apex.provider",
    ("API Settings", "apex", "model"): "apex.model",
    ("API Settings", "apex", "reasoning_effort"): "apex.reasoning_effort",
    (
        "API Settings",
        "apex",
        "anthropic_storyteller_transport",
    ): "apex.anthropic_storyteller_transport",
    ("API Settings", "apex", "turn_pipeline"): "apex.turn_pipeline",
    ("API Settings", "apex", "gaia_model"): "apex.gaia_model",
    (
        "API Settings",
        "apex",
        "tag_library",
        "contextual",
    ): "apex.tag_library.contextual",
    (
        "API Settings",
        "apex",
        "tag_library",
        "schema_enums",
    ): "apex.tag_library.schema_enums",
    (
        "API Settings",
        "apex",
        "tag_library",
        "suggestion_limit",
    ): "apex.tag_library.suggestion_limit",
    (
        "API Settings",
        "apex",
        "structured_output_retries",
    ): "apex.structured_output_retries",
    (
        "API Settings",
        "apex",
        "generation_timeout_seconds",
    ): "apex.generation_timeout_seconds",
}


def _normalize(value: Any) -> Any:
    """Reduce typed values to the plain form the façade stores."""

    if isinstance(value, BaseModel):
        return _normalize(value.model_dump())
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _resolve_typed(settings: Settings, dotted: str) -> Any:
    """Follow one dotted owner path through models and keyed registries."""

    node: Any = settings
    for part in dotted.split("."):
        if isinstance(node, BaseModel):
            if part not in type(node).model_fields:
                raise LookupError(f"{dotted}: {type(node).__name__} has no {part!r}")
            node = getattr(node, part)
        elif isinstance(node, dict):
            if part not in node:
                raise LookupError(f"{dotted}: registry has no key {part!r}")
            node = node[part]
        else:
            raise LookupError(f"{dotted}: cannot descend into {type(node).__name__}")
    return node


def _facade_leaves(
    node: Any, path: FacadePath, registries: list[FacadePath]
) -> list[tuple[FacadePath, Any]]:
    """Walk one façade sub-tree, stopping at allowlisted registries."""

    if path in DYNAMIC_REGISTRIES:
        registries.append(path)
        return []
    if isinstance(node, dict) and node:
        leaves: list[tuple[FacadePath, Any]] = []
        for key, value in node.items():
            leaves.extend(_facade_leaves(value, path + (key,), registries))
        return leaves
    return [(path, node)]


@pytest.fixture(scope="module")
def loaded() -> tuple[Settings, dict[str, Any]]:
    """Load ``nexus.toml`` once through each path."""

    return load_settings(), load_settings_as_dict()


def _walk(
    facade: dict[str, Any],
) -> tuple[list[tuple[FacadePath, Any]], list[FacadePath]]:
    registries: list[FacadePath] = []
    leaves: list[tuple[FacadePath, Any]] = []
    for root in FACADE_ROOTS:
        leaves.extend(
            _facade_leaves(facade[root[0]][root[1]], root, registries),
        )
    return leaves, registries


def test_facade_roots_are_the_only_alias_keys(
    loaded: tuple[Settings, dict[str, Any]],
) -> None:
    """The façade adds exactly the two alias blocks and their declared roots."""

    typed, facade = loaded
    alias_keys = set(facade) - set(typed.model_dump())
    assert alias_keys == {"Agent Settings", "API Settings"}
    assert {(top, child) for top in sorted(alias_keys) for child in facade[top]} == set(
        FACADE_ROOTS
    )


def test_every_facade_leaf_has_a_typed_owner(
    loaded: tuple[Settings, dict[str, Any]],
) -> None:
    """A façade leaf without an ownership entry fails, naming the key."""

    _typed, facade = loaded
    leaves, _registries = _walk(facade)
    unowned = [" > ".join(path) for path, _ in leaves if path not in OWNERSHIP]
    assert not unowned, f"façade leaves with no typed owner: {unowned}"


def test_every_ownership_entry_names_a_live_leaf_and_typed_path(
    loaded: tuple[Settings, dict[str, Any]],
) -> None:
    """Stale entries and typed paths that do not exist fail, naming them."""

    typed, facade = loaded
    leaves, _registries = _walk(facade)
    live = {path for path, _ in leaves}
    stale = [" > ".join(path) for path in OWNERSHIP if path not in live]
    assert not stale, f"ownership entries with no façade leaf: {stale}"
    missing: list[str] = []
    for path, owner in {
        **OWNERSHIP,
        **{path: owner for path, (owner, _) in DYNAMIC_REGISTRIES.items()},
    }.items():
        try:
            _resolve_typed(typed, owner)
        except LookupError as exc:
            missing.append(f"{' > '.join(path)} -> {exc}")
    assert not missing, f"typed owner paths that do not exist: {missing}"


def test_owner_paths_start_at_their_facade_root() -> None:
    """Each owner sits under the typed attribute that builds its façade root."""

    misplaced = [
        f"{' > '.join(path)} -> {owner}"
        for path, owner in {
            **OWNERSHIP,
            **{path: owner for path, (owner, _) in DYNAMIC_REGISTRIES.items()},
        }.items()
        if owner.split(".", 1)[0] != FACADE_ROOTS[path[:2]]
    ]
    assert not misplaced, f"owners outside their façade root: {misplaced}"


# Owners that deliberately sit somewhere other than the façade path's mirror.
# Empty today; an entry here needs a one-line reason beside it.
OWNER_PATH_EXCEPTIONS: dict[FacadePath, str] = {}


def _mirrored_owner(settings: Settings, path: FacadePath) -> str:
    """Map a façade path to the typed path that mirrors it through field aliases."""

    root = FACADE_ROOTS[path[:2]]
    parts = [root]
    node: Any = getattr(settings, root)
    for key in path[2:]:
        if isinstance(node, BaseModel):
            fields = type(node).model_fields
            name = next(
                (
                    field
                    for field, info in fields.items()
                    if (info.alias or field) == key
                ),
                None,
            )
            if name is None:
                raise LookupError(
                    f"{type(node).__name__} has no field dumped as {key!r}"
                )
            parts.append(name)
            node = getattr(node, name)
        elif isinstance(node, dict):
            parts.append(key)
            node = node[key]
        else:
            raise LookupError(f"cannot descend into {type(node).__name__} at {key!r}")
    return ".".join(parts)


def _misrouted_owners(
    settings: Settings, ownership: dict[FacadePath, str]
) -> list[str]:
    """Name every owner that is not the aliased mirror of its façade path."""

    misrouted: list[str] = []
    for path, owner in {
        **ownership,
        **{path: owner for path, (owner, _) in DYNAMIC_REGISTRIES.items()},
    }.items():
        if path in OWNER_PATH_EXCEPTIONS:
            continue
        expected = _mirrored_owner(settings, path)
        if owner != expected:
            misrouted.append(f"{' > '.join(path)} -> {owner} (mirror: {expected})")
    return misrouted


def test_owner_paths_mirror_their_facade_paths(
    loaded: tuple[Settings, dict[str, Any]],
) -> None:
    """Each owner is its façade path mapped through the models' field aliases.

    Value equality alone cannot catch an owner mis-mapped to a sibling that
    happens to hold the same value; this structural check does.
    """

    typed, _facade = loaded
    misrouted = _misrouted_owners(typed, OWNERSHIP)
    assert not misrouted, f"owners that do not mirror their façade path: {misrouted}"
    stale = [
        " > ".join(path) for path in OWNER_PATH_EXCEPTIONS if path not in OWNERSHIP
    ]
    assert not stale, f"owner-path exceptions with no ownership entry: {stale}"


def _value_drift(typed: Settings, facade: dict[str, Any]) -> list[str]:
    """Name every façade leaf whose value or scalar type differs from its owner.

    List leaves are compared element-wise, so a bool/int or int/float drift
    inside a list fails as it does for a scalar leaf.
    """

    leaves, _registries = _walk(facade)
    return [
        f"{' > '.join(path)}: façade={value!r} typed={expected!r}"
        for path, value in leaves
        for expected in [_normalize(_resolve_typed(typed, OWNERSHIP[path]))]
        if _strict_mismatch(value, expected) is not None
    ]


def test_every_facade_leaf_equals_its_typed_value(
    loaded: tuple[Settings, dict[str, Any]],
) -> None:
    """Each façade leaf and its typed owner yield the same effective value."""

    typed, facade = loaded
    drift = _value_drift(typed, facade)
    assert not drift, f"façade values drift from typed owners: {drift}"


def test_planted_drift_and_unowned_leaf_are_named(
    loaded: tuple[Settings, dict[str, Any]],
) -> None:
    """The walk is not vacuous: a changed value and a new leaf both surface."""

    typed, facade = loaded
    planted = copy.deepcopy(facade)
    planted["Agent Settings"]["LORE"]["render_limits"]["planted"] = 1
    leaves, _registries = _walk(planted)
    assert [path for path, _ in leaves if path not in OWNERSHIP] == [
        ("Agent Settings", "LORE", "render_limits", "planted")
    ]

    drifted = copy.deepcopy(facade)
    drifted["API Settings"]["apex"]["max_output_tokens"] += 1
    assert _value_drift(typed, drifted) == [
        "API Settings > apex > max_output_tokens: "
        f"façade={typed.apex.max_output_tokens + 1!r} "
        f"typed={typed.apex.max_output_tokens!r}"
    ]

    # An int/float drift inside a list leaf compares equal with ``==``; the
    # element-wise check still names it.
    tiers_path = (
        "Agent Settings",
        "MEMNON",
        "retrieval",
        "vector_normalization",
        "tiers",
    )
    float_typed = typed.model_copy(deep=True)
    float_typed.memnon.retrieval.vector_normalization.tiers[0][0] = 1.0
    int_facade = copy.deepcopy(facade)
    int_facade["Agent Settings"]["MEMNON"]["retrieval"]["vector_normalization"][
        "tiers"
    ][0][0] = 1
    tier_drift = _value_drift(float_typed, int_facade)
    assert len(tier_drift) == 1
    assert tier_drift[0].startswith(" > ".join(tiers_path) + ": façade=[[1, ")

    # Writer and Gaia share this value in nexus.toml, so only the structural
    # check can see an owner swapped onto its sibling seat.
    swapped = dict(OWNERSHIP)
    swapped[("API Settings", "apex", "max_output_tokens")] = (
        "apex.gaia.max_output_tokens"
    )
    assert _misrouted_owners(typed, swapped) == [
        "API Settings > apex > max_output_tokens -> apex.gaia.max_output_tokens "
        "(mirror: apex.max_output_tokens)"
    ]


def test_dynamic_registries_match_as_whole_subtrees(
    loaded: tuple[Settings, dict[str, Any]],
) -> None:
    """Every allowlisted registry is present and equals its typed sub-tree."""

    typed, facade = loaded
    _leaves, registries = _walk(facade)
    assert sorted(registries) == sorted(DYNAMIC_REGISTRIES)
    for path, (owner, _reason) in DYNAMIC_REGISTRIES.items():
        node: Any = facade
        for key in path:
            node = node[key]
        mismatch = _strict_mismatch(node, _normalize(_resolve_typed(typed, owner)))
        assert mismatch is None, f"{' > '.join(path)}: {mismatch}"


def _strict_mismatch(actual: Any, expected: Any, where: str = "") -> str | None:
    """Describe the first place two trees differ in value or scalar type."""

    if type(actual) is not type(expected):
        return (
            f"{where or '<root>'}: type {type(actual).__name__} "
            f"!= {type(expected).__name__} ({actual!r} vs {expected!r})"
        )
    if isinstance(actual, dict):
        if actual.keys() != expected.keys():
            return f"{where or '<root>'}: keys {sorted(actual)} != {sorted(expected)}"
        for key in actual:
            found = _strict_mismatch(actual[key], expected[key], f"{where}/{key}")
            if found is not None:
                return found
        return None
    if isinstance(actual, list):
        if len(actual) != len(expected):
            return f"{where or '<root>'}: length {len(actual)} != {len(expected)}"
        for index, (left, right) in enumerate(zip(actual, expected)):
            found = _strict_mismatch(left, right, f"{where}[{index}]")
            if found is not None:
                return found
        return None
    if actual != expected:
        return f"{where or '<root>'}: {actual!r} != {expected!r}"
    return None


def test_registry_comparison_is_type_strict() -> None:
    """A bool/int or int/float drift inside a registry is not equal."""

    assert _strict_mismatch({"a": [1, {"b": 2.0}]}, {"a": [1, {"b": 2.0}]}) is None
    assert _strict_mismatch({"a": True}, {"a": 1}) == (
        "/a: type bool != int (True vs 1)"
    )
    assert _strict_mismatch({"a": [1]}, {"a": [1.0]}) == (
        "/a[0]: type int != float (1 vs 1.0)"
    )
