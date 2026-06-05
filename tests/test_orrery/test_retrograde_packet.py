"""Tests for Retrograde dry-run packet assembly."""

from __future__ import annotations

import pytest

from nexus.agents.orrery.retrograde_packet import (
    build_retrograde_dry_run_packet,
    resolve_weird_profile,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    enumerate_seed_eligible_vocabulary,
)
from nexus.config import load_settings


class FakeRetrogradeCache:
    """Complete wizard cache stand-in for Retrograde packet tests."""

    def current_phase(self) -> str:
        return "ready"

    def get_setting_dict(self) -> dict[str, object]:
        return {
            "genre": "cyberpunk",
            "secondary_genres": ["noir"],
            "world_name": "Glass District",
            "tone": "dangerous but intimate",
        }

    def get_character_dict(self) -> dict[str, object]:
        return {
            "concept": {
                "name": "Mara",
                "archetype": "wary operator",
                "background": "Mara survives by tracking debts.",
                "appearance": "Prepared for quick exits.",
            },
            "trait_selection": {
                "selected_traits": ["resources", "status"],
                "trait_rationales": {
                    "resources": "Money opens doors.",
                    "status": "The badge matters narrowly.",
                },
            },
            "wildcard": {
                "wildcard_name": "Storm Marked",
                "wildcard_description": "Weather notices her.",
            },
        }

    def get_seed_dict(self) -> dict[str, object]:
        return {
            "seed_type": "inciting pressure",
            "title": "The Ledger Wakes",
            "situation": "An old debt becomes active.",
            "hook": "A message arrives in a dead person's voice.",
            "immediate_goal": "Find who sent it.",
            "stakes": "Mara's safe names may burn.",
            "tension_source": "A sponsor wants the secret first.",
            "key_npcs": ["Vale"],
            "secrets": "The debt was never hers.",
        }

    def get_layer_dict(self) -> dict[str, object]:
        return {"name": "Night City", "type": "urban", "description": "Dense sprawl."}

    def get_zone_dict(self) -> dict[str, object]:
        return {"name": "The Mall", "summary": "Commerce and surveillance."}

    def get_initial_location(self) -> dict[str, object]:
        return {"name": "Shutter Hall", "description": "A quiet mall corridor."}


def test_retrograde_packet_is_dry_run_and_selection_oriented() -> None:
    """A0 packets expose candidate material without implying persistence."""

    packet = build_retrograde_dry_run_packet(
        slot=5,
        dbname="save_05",
        cache=FakeRetrogradeCache(),
        vocabulary=enumerate_seed_eligible_vocabulary(),
        settings=load_settings(),
        weird_level="high",
    )

    assert packet["dry_run"] is True
    assert packet["mutation_policy"]["writes"] == "none"
    assert (
        "Skald-as-weaver pass must select"
        in packet["mutation_policy"]["review_contract"]
    )
    assert packet["weird"]["level"] == "high"
    assert packet["weird"]["genre"] == "cyberpunk"
    assert (
        packet["candidate_scaffolds"]["candidate_seed_contract"]["selection_required"]
        is True
    )
    assert packet["candidate_scaffolds"]["named_seed_npcs"] == [
        {"kind": "character", "role": "seed_npc", "name": "Vale"}
    ]
    assert packet["vocabulary_summary"]["event_types"] > 0


def test_retrograde_packet_requires_complete_wizard_sections() -> None:
    """Incomplete wizard cache state fails before packet assembly."""

    class IncompleteCache(FakeRetrogradeCache):
        def get_seed_dict(self) -> None:
            return None

    with pytest.raises(ValueError, match="complete wizard seed data"):
        build_retrograde_dry_run_packet(
            slot=5,
            dbname="save_05",
            cache=IncompleteCache(),
            vocabulary=enumerate_seed_eligible_vocabulary(),
            settings=load_settings(),
        )


def test_retrograde_weird_raw_override_stays_in_dev_range() -> None:
    """Developer raw weirdness overrides are explicit and range checked."""

    settings = load_settings()
    profile = resolve_weird_profile(
        settings=settings,
        setting={"genre": "cyberpunk"},
        weird_level="low",
        weird_raw=0.42,
    )

    assert profile["source"] == "raw_override"
    assert profile["raw"] == 0.42

    with pytest.raises(ValueError, match="raw weirdness"):
        resolve_weird_profile(
            settings=settings,
            setting={"genre": "cyberpunk"},
            weird_raw=999,
        )
