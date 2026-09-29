"""Pin the assembled Writer and Gaia requests for one fixed TEST-provider turn.

The digests below were recorded before the storyteller readers moved from the
``API Settings`` / ``Agent Settings`` aliases to the typed settings models
(issue #809). A reader that maps to the wrong budget or apex field changes an
assembled request or a budget line, so the move shows up here instead of as
silent drift. Prompt or ``nexus.toml`` edits legitimately change these values;
refresh them from the failure message after reviewing the diff.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.agents.logon import orrery_tag_validation
from nexus.agents.logon.skald_wire import CharacterRef, PlaceRef, PresenceBaseline
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.utils.entity_inclusion import resolve_entity_inclusion
from nexus.agents.lore.utils.token_budget import TokenBudgetManager
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.api import db_pool
from nexus.config import load_settings
from nexus.config.settings_models import Settings
from nexus.config.story_model import StorySettings
from nexus.memory.manager import (
    pass2_baseline_config_fingerprint,
    resolve_storyteller_context_window,
)
from scripts.api_openai import OpenAIProvider

WINDOW = 75_000
USER_INPUT = "Open the archive."
BASELINE = PresenceBaseline(
    present=[CharacterRef(kind="character", name="Iona Vale", id=4)],
    setting=PlaceRef(kind="place", name="The Lower Sluice", id=9),
)
WRITER_OUTPUT: dict[str, Any] = {
    "narrative": 'Iona says, "Wait."\nThe drowned bell answers.',
    "choices": ["Follow Iona into the archive.", "Stay beneath the sluice gate."],
    "scene": {"elapsed_minutes": 7, "weather": "rain"},
    "letter": "The bell is bait. Let Iona suspect the Choir first.",
}
GAIA_OUTPUT: dict[str, Any] = {
    "updates": {
        "characters": [],
        "places": [],
        "factions": [],
        "relationships": [],
    },
    "orrery_adjudications": [],
    "new_entities": [],
    "letter": "Agreed. The ringer stays unresolved.",
}

# Recorded at 588fc543, before the alias readers moved (issue #809).
EXPECTED_REQUEST_DIGESTS: dict[str, str] = {
    "writer": "09b26dfed922d661ebbed44ac7f8e5621f5a21734d99d078c2718cb5b505cac6",
    "gaia": "cf619d7092fe80a3e4dd3680b046d3e26ac4e6166077980d91e84b7d52d1ed43",
}
_LOCAL_ENTITY_OVERRIDE: dict[str, Any] = {
    "include_all_relationships": False,
    "max_characters_from_warm_slice": 12,
    "max_locations_from_warm_slice": 6,
    "warm_slice_lookback_chunks": 12,
}
EXPECTED_BUDGET_LINES: dict[str, Any] = {
    "context_window": {"local": 32000, "test": 75000},
    "entity_inclusion": {
        "local": {
            **_LOCAL_ENTITY_OVERRIDE,
            "max_total_characters": 30,
            "max_total_relationships": 100,
            "provider_overrides": {"local": _LOCAL_ENTITY_OVERRIDE},
        },
        "test": {
            "include_all_relationships": True,
            "max_characters_from_warm_slice": 25,
            "max_locations_from_warm_slice": 10,
            "max_total_characters": 30,
            "max_total_relationships": 100,
            "provider_overrides": {"local": _LOCAL_ENTITY_OVERRIDE},
            "warm_slice_lookback_chunks": 20,
        },
    },
    "max_deep_queries": 5,
    "pass2_config_fingerprint": (
        "a3b2eb7891eda6732d1190e69eaff3add40d591637e52f8669d9bbe797d78ad7"
    ),
    "payload_budget": {
        "apex_window": 75000,
        "augmentation": 3550,
        "effective_input_ceiling": 71000,
        "reasoning_reserve": 0,
        "response_reserve": 4000,
        "structured": 49700,
        "system_prompt": 5000,
        "total_available": 71000,
        "user_input": 4,
        "warm_slice": 3550,
    },
    "presence_boost_enabled": True,
}


def _digest(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _settings() -> Settings:
    return load_settings()


class _NoStoryConnection:
    """Context-managed stand-in for a slot connection the fixture never queries."""

    def __enter__(self) -> "_NoStoryConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def cursor(self) -> "_NoStoryConnection":
        return self


def _recording_client(calls: list[dict[str, Any]]) -> Any:
    outputs = [WRITER_OUTPUT, GAIA_OUTPUT]

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        output = outputs[len(calls) - 1]
        return SimpleNamespace(
            id=f"resp_fingerprint_{len(calls)}",
            output_parsed=None,
            output_text=json.dumps(output),
            usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create))


def _assembled_requests(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv("NEXUS_SLOT", "3")
    utility = LogonUtility(
        _settings(), model_override="TEST", story_settings=StorySettings()
    )
    # No story database or Setting Card backs this fixture turn.
    utility._setting_context_loaded = True
    utility._setting_context = None
    endpoint: dict[str, Any] = {
        "base_url": "http://127.0.0.1:5102/v1",
        "api_key": "test-dummy-key",
        "structured_transport": "responses",
        "request_timeout_seconds": None,
        "request_params": {},
    }
    utility._initialize_provider(
        False, resolved_route=("TEST", "test", endpoint, "local")
    )
    assert isinstance(utility.provider, OpenAIProvider)
    calls: list[dict[str, Any]] = []
    utility.provider.client = _recording_client(calls)
    monkeypatch.setattr(
        utility,
        "_read_presence_baseline_for_context",
        lambda _context_payload, _schema_model: BASELINE,
    )
    # Gaia's tag validator reads the live vocabulary after the request is sent;
    # this fixture's empty Gaia output never touches the cursor.
    monkeypatch.setattr(db_pool, "get_connection", lambda _dbname: _NoStoryConnection())
    monkeypatch.setattr(
        orrery_tag_validation,
        "read_storyteller_vocabulary",
        lambda _dbname: orrery_tag_validation.StorytellerVocabulary(
            tag_names_by_kind={},
            pair_tag_names=frozenset(),
            event_types=frozenset(),
        ),
    )
    utility.generate_narrative(
        {
            "user_input": USER_INPUT,
            "warm_slice": {"chunks": [{"text": "The sluice gate groans."}]},
            "entity_data": {},
            "retrieved_passages": {"results": []},
        },
        effective_context_window=WINDOW,
    )
    return {"writer": calls[0], "gaia": calls[1]}


def _budget_lines() -> dict[str, Any]:
    settings = _settings()
    turn_cycle = TurnCycleManager(SimpleNamespace(settings=settings))
    return {
        "payload_budget": TokenBudgetManager(settings).calculate_budget(
            USER_INPUT, apex_context_window=WINDOW
        ),
        "context_window": {
            provider: resolve_storyteller_context_window(settings, wire, provider)
            for provider, wire in (("test", "local"), ("local", "local"))
        },
        "entity_inclusion": {
            provider: resolve_entity_inclusion(settings, wire, provider).model_dump()
            for provider, wire in (("test", "local"), ("local", "local"))
        },
        "max_deep_queries": turn_cycle._max_deep_queries(),
        "presence_boost_enabled": turn_cycle._presence_boost_enabled(),
        "pass2_config_fingerprint": pass2_baseline_config_fingerprint(settings),
    }


def test_assembled_writer_and_gaia_requests_are_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both seats send exactly the recorded request for the fixture turn."""

    requests = _assembled_requests(monkeypatch)
    digests = {seat: _digest(request) for seat, request in requests.items()}
    assert digests == EXPECTED_REQUEST_DIGESTS, (
        "Assembled storyteller requests changed; if intended, record: "
        f"{json.dumps(digests, indent=4)}"
    )


def test_budget_lines_are_unchanged() -> None:
    """Payload budget, context windows and retrieval switches are unchanged."""

    lines = _budget_lines()
    assert lines == EXPECTED_BUDGET_LINES, (
        "Storyteller budget lines changed; if intended, record: "
        f"{json.dumps(lines, indent=4, sort_keys=True)}"
    )
