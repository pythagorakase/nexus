"""Pin the assembled Writer and Gaia requests for one fixed TEST-provider turn.

The digests below were recorded before the storyteller readers moved from the
``API Settings`` / ``Agent Settings`` aliases to the typed settings models
(issue #809). The fixture gives the Writer and Gaia seats distinct output,
reserve and effort values, so a reader that maps to the wrong budget or apex
field, including one seat's field read for the other, changes an assembled
request, a recorded seat knob or a budget line instead of drifting silently.
Prompt or ``nexus.toml`` edits legitimately change these values; refresh them
from the failure message after reviewing the diff.
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
from nexus.config.seat_window import resolve_seat_window
from nexus.config.settings_models import Settings
from nexus.config.story_model import StorySettings
from nexus.memory.manager import (
    pass2_baseline_config_fingerprint,
    resolve_storyteller_context_window,
)
from scripts.api_openai import OpenAIProvider
from tests.settings_helpers import settings_with

WINDOW = 75_000
# The Writer keeps nexus.toml's [apex] values; Gaia differs on the output,
# reserve and effort fields the recorded requests and knobs can see. The
# 688cb431 export these digests come from had no Gaia temperature field, so
# the seats share 0.7 here and a separate test below pins the temperature
# seat mapping.
SEAT_OVERRIDES: dict[str, Any] = {
    "apex.gaia.max_output_tokens": 23_000,
    "apex.gaia.reasoning_reserve_tokens": 19_000,
    "apex.gaia.response_reserve_tokens": 3_500,
    "apex.gaia.reasoning_effort": "high",
}
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

# Recorded from an export of 688cb431, where every reader still used the alias
# dict, with SEAT_OVERRIDES applied (issue #809).
EXPECTED_REQUEST_DIGESTS: dict[str, str] = {
    "writer": "09b26dfed922d661ebbed44ac7f8e5621f5a21734d99d078c2718cb5b505cac6",
    "gaia": "cac3d730f8b3e3081aa4f297a642694fb1f937ffd0639f4f906c70c14e11da6f",
}
# "provider" is the writer route after _initialize_provider; the seat entries
# are each pass's provider after _clone_provider_for_two_pass configures it.
EXPECTED_SEAT_KNOBS: dict[str, Any] = {
    "provider": {
        "max_output_tokens": 25000,
        "reasoning_effort": "medium",
        "temperature": 0.7,
    },
    "skald_writer": {
        "max_output_tokens": 25000,
        "reasoning_effort": "medium",
        "temperature": 0.7,
    },
    "gaia": {
        "max_output_tokens": 23000,
        "reasoning_effort": "high",
        "temperature": 0.7,
    },
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
    "seat_windows": {
        "gaia": {
            "input_ceiling": 71500,
            "max_output_tokens": 23000,
            "model": "TEST",
            "policy_headroom": 3500,
            "seat": "gaia",
        },
        "skald_writer": {
            "input_ceiling": 71000,
            "max_output_tokens": 25000,
            "model": "TEST",
            "policy_headroom": 4000,
            "seat": "skald_writer",
        },
    },
}


def _digest(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _settings() -> Settings:
    return settings_with(SEAT_OVERRIDES)


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


def _seat_knobs(provider: Any) -> dict[str, Any]:
    """Return the per-seat request knobs a provider carries into its call."""

    return {
        "max_output_tokens": provider.max_output_tokens,
        "reasoning_effort": provider.reasoning_effort,
        "temperature": provider.temperature,
    }


def _utility(settings: Settings) -> LogonUtility:
    return LogonUtility(settings, model_override="TEST", story_settings=StorySettings())


def _assembled_requests(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    monkeypatch.setenv("NEXUS_SLOT", "3")
    utility = _utility(settings if settings is not None else _settings())
    # No story database or Setting Card backs this fixture turn.
    utility._setting_context_loaded = True
    utility._setting_context = None
    route = utility._resolve_storyteller_route()
    assert route[0] == "TEST" and route[1] == "test"
    utility._initialize_provider(False, resolved_route=route)
    assert isinstance(utility.provider, OpenAIProvider)
    knobs: dict[str, Any] = {"provider": _seat_knobs(utility.provider)}
    calls: list[dict[str, Any]] = []
    utility.provider.client = _recording_client(calls)
    clone = utility._clone_provider_for_two_pass

    def recording_clone(**kwargs: Any) -> Any:
        pass_provider = clone(**kwargs)
        knobs[kwargs["usage_seat"]] = _seat_knobs(pass_provider)
        return pass_provider

    monkeypatch.setattr(utility, "_clone_provider_for_two_pass", recording_clone)
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
    return {"writer": calls[0], "gaia": calls[1]}, knobs


def test_writer_and_gaia_temperatures_come_from_their_own_seats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each seat carries its own temperature, on the clone and on a pinned Gaia.

    The recorded digests above cannot see this: the seats share 0.7 there, so
    a Gaia site that read the Writer's ``apex.temperature`` would not change
    them.
    """

    settings = settings_with({**SEAT_OVERRIDES, "apex.gaia.temperature": 0.3})
    assert settings.apex.temperature == 0.7
    _requests, knobs = _assembled_requests(monkeypatch, settings)
    temperatures = {seat: knob["temperature"] for seat, knob in knobs.items()}
    assert temperatures == {"provider": 0.7, "skald_writer": 0.7, "gaia": 0.3}

    utility = _utility(settings)
    route = utility._resolve_storyteller_route()
    assert route[0] == "TEST" and route[3] != "anthropic"
    pinned_gaia = utility._build_gaia_provider(
        route, system_prompt=None, output_validator=None, anthropic_transport=None
    )
    assert isinstance(pinned_gaia, OpenAIProvider)
    assert pinned_gaia.temperature == 0.3


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
        "seat_windows": {
            seat: resolve_seat_window(
                settings.model_dump(), "TEST", seat=seat, window=WINDOW
            ).model_dump()
            for seat in ("skald_writer", "gaia")
        },
    }


def test_assembled_writer_and_gaia_requests_are_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both seats send exactly the recorded request for the fixture turn."""

    requests, knobs = _assembled_requests(monkeypatch)
    digests = {seat: _digest(request) for seat, request in requests.items()}
    assert digests == EXPECTED_REQUEST_DIGESTS, (
        "Assembled storyteller requests changed; if intended, record: "
        f"{json.dumps(digests, indent=4)}"
    )
    assert knobs == EXPECTED_SEAT_KNOBS, (
        "Per-seat request knobs changed; if intended, record: "
        f"{json.dumps(knobs, indent=4, sort_keys=True)}"
    )


def test_budget_lines_are_unchanged() -> None:
    """Payload budget, context windows and retrieval switches are unchanged."""

    lines = _budget_lines()
    assert lines == EXPECTED_BUDGET_LINES, (
        "Storyteller budget lines changed; if intended, record: "
        f"{json.dumps(lines, indent=4, sort_keys=True)}"
    )
