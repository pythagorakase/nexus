"""Live Skald round-trip tests for Retrograde generation.

These tests are skipped unless ``NEXUS_RUN_LIVE_LLM=1`` is set.
"""

from __future__ import annotations

import os

import pytest

from nexus.agents.orrery.retrograde_expansion import generate_expansion_with_skald
from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
from nexus.agents.orrery.retrograde_seed_candidates import (
    generate_seed_candidates_with_skald,
    render_seed_generation_prompt,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)
from nexus.config import resolve_model_ref


@pytest.mark.live
@pytest.mark.live_llm
def test_live_retrograde_seed_and_expansion_round_trip() -> None:
    """Real Skald calls can generate seeds and weave a dry-run R6 plan."""

    packet = _compact_live_packet()
    model_name = resolve_model_ref(
        os.environ.get("NEXUS_RETROGRADE_LIVE_MODEL", "@openai.default")
    )
    max_tokens = int(os.environ.get("NEXUS_RETROGRADE_LIVE_MAX_TOKENS", "8000"))

    seed_generation = generate_seed_candidates_with_skald(
        packet=packet,
        model_name=model_name,
        max_tokens=max_tokens,
    )
    seed_response = seed_generation["seed_candidate_response"]

    assert seed_response["candidates"]
    assert seed_response["selected_seed_ids"]

    expansion_generation = generate_expansion_with_skald(
        packet=packet,
        seed_candidate_response=seed_response,
        model_name=model_name,
        max_tokens=max_tokens,
    )
    expansion_plan = expansion_generation["retrograde_expansion_plan"]

    assert expansion_plan["event_plan"]
    assert expansion_plan["thread_plan"]
    assert expansion_plan["commit_readiness"]["writes"] == "none"
    assert "pre_game_tick_chunk_id" in expansion_plan["commit_readiness"]["blocked_by"]


def _compact_live_packet() -> dict[str, object]:
    vocabulary = _compact_live_vocabulary()
    seed_request = build_seed_generation_request(
        candidate_scaffolds={
            "core_entities": [
                {
                    "kind": "character",
                    "role": "protagonist",
                    "name": "Mara",
                    "summary": "A debt-tracker with a borrowed identity.",
                },
                {
                    "kind": "place",
                    "role": "starting_location",
                    "name": "Shutter Hall",
                    "summary": "A dead mall corridor that still listens.",
                },
            ],
            "named_seed_npcs": [
                {"kind": "character", "role": "seed_npc", "name": "Vale"}
            ],
            "pressure_axes": [
                {
                    "kind": "hook",
                    "text": "A message arrives in a dead person's voice.",
                },
                {
                    "kind": "stakes",
                    "text": "Mara's borrowed identities may collapse.",
                },
            ],
            "trait_hooks": {
                "selected_traits": ["resources", "obligations"],
                "rationales": {
                    "resources": "Money opens doors until it becomes a leash.",
                    "obligations": "Some favors are older than her current name.",
                },
                "wildcard": {
                    "name": "Storm Marked",
                    "description": "Weather patterns react when she lies.",
                },
            },
        },
        vocabulary=vocabulary,
        weird={"level": "low", "genre": "cyberpunk", "raw_midpoint": 0.4},
    )
    seed_request["budget"] = {
        "generate_candidates": 2,
        "select_target": 1,
        "deferred_secret_cap": 0,
        "overgenerate_multiplier": 2,
    }
    return {
        "schema_version": "orrery_retrograde_dry_run_packet.v0",
        "dry_run": True,
        "mutation_policy": {"writes": "none"},
        "seed_generation_request": seed_request,
        "seed_eligible_vocabulary": vocabulary,
        "seed_generation_prompt": render_seed_generation_prompt(
            seed_generation_request=seed_request,
            vocabulary=vocabulary,
        ),
    }


def _compact_live_vocabulary() -> SeedEligibleVocabulary:
    vocabulary = enumerate_seed_eligible_vocabulary()
    vocabulary["registered_single_entity_tags"] = [
        "grieving",
        "scholar",
        "resourceful",
    ]
    vocabulary["registered_tags_by_seed_policy"] = {
        "stable_seed": ["scholar", "resourceful"],
        "event_anchored": ["grieving"],
        "prompt_visible_only": [],
    }
    vocabulary["registered_category_seed_policies"] = [
        {
            "category": "role.function",
            "entity_kind": "character",
            "policy": "stable_seed",
            "reason": "Stable role.",
        },
        {
            "category": "state",
            "entity_kind": "character",
            "policy": "event_anchored",
            "reason": "Current state needs an event.",
        },
    ]
    return vocabulary
