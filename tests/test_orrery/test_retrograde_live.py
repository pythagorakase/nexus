"""Live Skald round-trip tests for Retrograde generation.

These tests are skipped unless ``NEXUS_RUN_LIVE_LLM=1`` is set.
"""

from __future__ import annotations


import json
import os
from typing import Any, Mapping

import pytest

from nexus.agents.orrery.retrograde_expansion import generate_expansion_with_skald
from nexus.agents.orrery.retrograde_packet import build_seed_generation_request
from nexus.agents.orrery.retrograde_seed_candidates import (
    render_seed_generation_prompt,
    run_seed_stage,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    SeedEligibleVocabulary,
    enumerate_seed_eligible_vocabulary,
)
from nexus.config import resolve_model_ref
from tests.model_registry_helpers import registry_model


@pytest.mark.live
@pytest.mark.live_llm
def test_live_retrograde_seed_and_expansion_round_trip() -> None:
    """Real Skald calls can generate seeds and weave a dry-run R6 plan."""

    packet = _compact_live_packet()
    model_name = resolve_model_ref(
        os.environ.get("NEXUS_RETROGRADE_LIVE_MODEL", registry_model("openai"))
    )
    max_tokens = int(os.environ.get("NEXUS_RETROGRADE_LIVE_MAX_TOKENS", "8000"))

    # R4 generation returns empty selections by prompt contract (#443);
    # run_seed_stage adds the decoupled R5 selection call before R6.
    seed_generation = run_seed_stage(
        packet=packet,
        model_name=model_name,
        max_tokens=max_tokens,
    )
    seed_response = seed_generation["seed_candidate_response"]
    # Evidence for #1007: every entity ref the validated seed response
    # carries, visible under ``pytest -s`` (print, not logging, so a passing
    # run still shows it).
    for location, ref in _seed_entity_refs(seed_response):
        print(f"SEED_ENTITY_REF {location} {json.dumps(ref)}")

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


def _seed_entity_refs(seed_response: Mapping[str, Any]) -> list[tuple[str, str]]:
    """List every prompt-local entity ref in a validated seed response."""

    refs: list[tuple[str, str]] = []
    for candidate in seed_response.get("candidates") or []:
        seed_id = candidate.get("seed_id")
        hints = candidate.get("mechanical_hints") or {}
        for event in hints.get("events") or []:
            for name in event.get("participating_entities") or []:
                refs.append((f"{seed_id}.events.participating_entities", name))
        for tag in hints.get("single_entity_tags") or []:
            refs.append((f"{seed_id}.single_entity_tags.entity_ref", tag["entity_ref"]))
        for section in ("pair_tags", "relationships"):
            for row in hints.get(section) or []:
                refs.append((f"{seed_id}.{section}.subject_ref", row["subject_ref"]))
                refs.append((f"{seed_id}.{section}.object_ref", row["object_ref"]))
        for edge in candidate.get("claimed_edges") or []:
            refs.append(
                (
                    f"{seed_id}.claimed_edges.open_endpoint_name",
                    edge["open_endpoint_name"],
                )
            )
        intent = candidate.get("project_intent")
        if intent and intent.get("target_ref"):
            refs.append((f"{seed_id}.project_intent.target_ref", intent["target_ref"]))
    return refs


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
