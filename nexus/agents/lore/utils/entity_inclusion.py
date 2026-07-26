"""Resolve provider-scaled entity inclusion for storyteller payloads."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Optional

from nexus.config.settings_models import EntityInclusionConfig

logger = logging.getLogger("nexus.lore.entity_inclusion")

_STORYTELLER_WIRE_CLASSES = frozenset({"openai", "anthropic", "local"})


def _base_entity_inclusion(
    settings: Mapping[str, Any],
) -> EntityInclusionConfig:
    """Return the validated base entity-inclusion configuration."""
    legacy_agent_settings = settings.get("Agent Settings")
    legacy_lore_settings = (
        legacy_agent_settings.get("LORE")
        if isinstance(legacy_agent_settings, Mapping)
        else None
    )
    lore_settings = (
        legacy_lore_settings
        if isinstance(legacy_lore_settings, Mapping)
        else settings.get("lore")
    )
    if not isinstance(lore_settings, Mapping):
        raise ValueError(
            "LORE settings are required to resolve storyteller entity inclusion"
        )

    entity_inclusion = lore_settings.get("entity_inclusion")
    if not isinstance(entity_inclusion, Mapping):
        raise ValueError(
            "entity_inclusion must be configured under the LORE settings section"
        )
    return EntityInclusionConfig.model_validate(entity_inclusion)


def resolve_entity_inclusion(
    settings: Mapping[str, Any],
    provider_wire_type: Optional[str],
    provider_name: Optional[str],
) -> EntityInclusionConfig:
    """Resolve effective entity inclusion for one storyteller provider.

    ``None``/``None`` is the named LOGON-disabled path and returns base values.
    Active LOGON callers must establish the full route first. The override
    lookup keys on the registry provider NAME: resource profiles belong to the
    serving provider, not the wire dialect, so an OpenAI-compatible remote
    provider (openrouter) shares the "local" wire class but keeps base
    inclusion unless it has its own override entry.
    """
    if (provider_wire_type is None) != (provider_name is None):
        raise RuntimeError(
            "provider_wire_type and provider_name must be supplied together; got "
            f"wire={provider_wire_type!r}, provider={provider_name!r}"
        )
    if (
        provider_wire_type is not None
        and provider_wire_type not in _STORYTELLER_WIRE_CLASSES
    ):
        raise RuntimeError(
            "Cannot resolve storyteller entity inclusion for an unknown provider "
            "wire class; expected one of "
            f"{sorted(_STORYTELLER_WIRE_CLASSES)}, got {provider_wire_type!r}"
        )

    base = _base_entity_inclusion(settings)
    if provider_wire_type is None or provider_name is None:
        return base

    override = base.provider_overrides.get(provider_name)
    if override is None:
        return base

    override_values = override.model_dump(exclude_none=True)
    resolved_differences = {
        field: value
        for field, value in override_values.items()
        if getattr(base, field) != value
    }
    if resolved_differences:
        logger.debug(
            "Storyteller entity inclusion override: provider=%s class=%s "
            "resolved=%s",
            provider_name,
            provider_wire_type,
            resolved_differences,
        )
    return base.model_copy(update=override_values)
