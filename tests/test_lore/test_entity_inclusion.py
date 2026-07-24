"""Provider-scaled storyteller entity-inclusion tests."""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict

import pytest

from nexus.agents.lore.utils.entity_inclusion import resolve_entity_inclusion
from nexus.config import load_settings_as_dict


def _effective_values(config: Any) -> Dict[str, Any]:
    """Return effective base fields without the routing table."""
    return config.model_dump(exclude={"provider_overrides"})


def test_local_entity_inclusion_resolves_shipped_overrides(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Local routing applies four overrides and inherits every absent field."""
    settings = load_settings_as_dict()
    base = resolve_entity_inclusion(settings, provider_wire_type=None)

    with caplog.at_level(logging.DEBUG, logger="nexus.lore.entity_inclusion"):
        resolved = resolve_entity_inclusion(settings, provider_wire_type="local")

    assert resolved.warm_slice_lookback_chunks == 12
    assert resolved.max_characters_from_warm_slice == 12
    assert resolved.max_locations_from_warm_slice == 6
    assert resolved.include_all_relationships is False
    assert resolved.include_all_active_events == base.include_all_active_events
    assert resolved.include_all_active_threats == base.include_all_active_threats
    assert resolved.active_event_statuses == base.active_event_statuses
    assert resolved.max_total_events == base.max_total_events

    override_records = [
        record
        for record in caplog.records
        if record.name == "nexus.lore.entity_inclusion"
    ]
    assert len(override_records) == 1
    assert "class=local" in override_records[0].getMessage()
    assert "'warm_slice_lookback_chunks': 12" in override_records[0].getMessage()
    assert "'include_all_relationships': False" in override_records[0].getMessage()


@pytest.mark.parametrize("provider_wire_type", ["openai", "anthropic"])
def test_unconfigured_provider_entity_inclusion_is_pure_base(
    provider_wire_type: str,
) -> None:
    """Provider classes without a table inherit the complete base config."""
    settings = load_settings_as_dict()
    base = resolve_entity_inclusion(settings, provider_wire_type=None)

    resolved = resolve_entity_inclusion(settings, provider_wire_type)

    assert _effective_values(resolved) == _effective_values(base)


def test_logon_disabled_entity_inclusion_is_explicit_base() -> None:
    """The named no-wire-class path preserves the complete base config."""
    settings = load_settings_as_dict()

    resolved = resolve_entity_inclusion(settings, provider_wire_type=None)

    assert resolved.warm_slice_lookback_chunks == 20
    assert resolved.max_characters_from_warm_slice == 25
    assert resolved.max_locations_from_warm_slice == 10
    assert resolved.include_all_relationships is True


def test_empty_entity_inclusion_override_table_is_pure_base(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty provider table neither changes values nor emits an override log."""
    settings = copy.deepcopy(load_settings_as_dict())
    settings["lore"]["entity_inclusion"]["provider_overrides"] = {"local": {}}
    base = resolve_entity_inclusion(settings, provider_wire_type=None)

    with caplog.at_level(logging.DEBUG, logger="nexus.lore.entity_inclusion"):
        resolved = resolve_entity_inclusion(settings, provider_wire_type="local")

    assert _effective_values(resolved) == _effective_values(base)
    assert not [
        record
        for record in caplog.records
        if record.name == "nexus.lore.entity_inclusion"
    ]


def test_unknown_entity_inclusion_wire_class_fails_loudly() -> None:
    """Runtime callers cannot bypass the closed provider-class contract."""
    with pytest.raises(RuntimeError, match="unknown provider wire class.*bedrock"):
        resolve_entity_inclusion(
            load_settings_as_dict(),
            provider_wire_type="bedrock",
        )
