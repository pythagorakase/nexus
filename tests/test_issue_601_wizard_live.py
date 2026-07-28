"""Live structured-call and hydrated-packet proof for issue #601."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.tools import DeferredToolRequests

from nexus.agents.orrery.retrograde_packet import build_retrograde_dry_run_packet
from nexus.agents.orrery.retrograde_seed_candidates import (
    render_seed_selection_prompt,
)
from nexus.agents.orrery.retrograde_vocabulary import (
    enumerate_seed_eligible_vocabulary,
)
from nexus.api.new_story_cache import read_cache, write_cache, write_suggested_traits
from nexus.api.pydantic_ai_utils import build_pydantic_ai_model
from nexus.api.slot_utils import slot_dbname
from nexus.api.wizard_agent import WizardContext, get_wizard_agent
from nexus.config import load_settings, resolve_model_ref

SLOT = int(os.environ.get("NEXUS_ISSUE_601_TEST_SLOT", "0"))
DBNAME = slot_dbname(SLOT) if SLOT in {1, 2, 3, 4} else ""

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_llm,
    pytest.mark.requires_postgres,
    pytest.mark.skipif(
        os.environ.get("NEXUS_ISSUE_601_LIVE") != "1"
        or not DBNAME
        or os.environ.get("NEXUS_CONFIRM_DISPOSABLE_DB") != DBNAME,
        reason=(
            "Set NEXUS_ISSUE_601_LIVE=1, choose disposable slot 1-4 with "
            "NEXUS_ISSUE_601_TEST_SLOT, and confirm its database name with "
            "NEXUS_CONFIRM_DISPOSABLE_DB."
        ),
    ),
]


@pytest.mark.asyncio
async def test_live_trait_confirmation_persists_and_threads_constraint() -> None:
    """The registry-selected wizard model types the live QA rationale in one call."""

    from nexus.api.save_slots import upsert_slot
    from scripts.new_story_setup import create_slot_schema_only

    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures" / "slot3_midnight_qa_wizard_cache.json"
        ).read_text()
    )
    model_ref = os.environ.get("NEXUS_ISSUE_601_MODEL", "@openai.default")
    model_name = resolve_model_ref(model_ref)

    create_slot_schema_only(SLOT, source_db="NEXUS_template", force=True)
    upsert_slot(SLOT, model=model_name, dbname=DBNAME)
    character = fixture["character"]
    seed = fixture["seed"]
    write_cache(
        thread_id="issue_601_live_trait_confirmation",
        setting_draft=fixture["setting"],
        character_draft={
            "concept": character["concept"],
            "wildcard": character["wildcard"],
        },
        selected_seed=seed["story_seed"],
        layer_draft=seed["layer"],
        zone_draft=seed["zone"],
        initial_location=seed["initial_location"],
        base_timestamp="2026-05-14T10:48:00+00:00",
        target_slot=SLOT,
        dbname=DBNAME,
    )
    write_suggested_traits(
        DBNAME,
        [
            {
                "trait": trait,
                "rationale": character["concept"]["trait_rationales"][trait],
            }
            for trait in character["concept"]["suggested_traits"]
        ],
    )

    context = WizardContext(
        slot=SLOT,
        cache=read_cache(DBNAME),
        phase="character",
        thread_id="issue_601_live_trait_confirmation",
        model=model_name,
        context_data={
            "setting": fixture["setting"],
            "character_state": {"concept": character["concept"]},
        },
        accept_fate=False,
        dev_mode=False,
        history_len=1,
        user_turns=1,
        assistant_turns=1,
    )
    agent: Any = get_wizard_agent(context)
    result = await agent.run(
        (
            "Confirm Status, Enemies, and Obligations exactly. Enemies must not "
            "invent a preexisting personal nemesis: opposition may arise only "
            "because of what Jules witnesses or carries during play."
        ),
        deps=context,
        model=build_pydantic_ai_model(model_name),
    )

    assert isinstance(result.output, DeferredToolRequests)
    assert context.last_tool_name == "submit_trait_selection"
    assert context.last_tool_result is not None
    submitted = context.last_tool_result["data"]["character_state"]["trait_selection"]
    submitted_constraints = {
        row["trait"]: row for row in submitted["trait_constraints"]
    }
    assert submitted_constraints["enemies"]["cold_start_relationships"] == "forbidden"
    assert submitted_constraints["enemies"]["preexisting_relationship_targets"] == []

    hydrated = read_cache(DBNAME)
    assert hydrated is not None
    packet = build_retrograde_dry_run_packet(
        slot=SLOT,
        dbname=DBNAME,
        cache=hydrated,
        vocabulary=enumerate_seed_eligible_vocabulary(dbname=DBNAME),
        settings=load_settings(),
        weird_level="low",
    )
    packet_constraints = {
        row["trait"]: row
        for row in packet["candidate_scaffolds"]["trait_hooks"]["constraints"]
    }
    assert packet_constraints["enemies"]["cold_start_relationships"] == "forbidden"
    assert packet_constraints["enemies"]["blocked_relationship_types"] == [
        "captor",
        "enemy",
        "rival",
    ]
    assert packet_constraints["enemies"]["blocked_pair_tags"] == ["hunting"]
    request_constraints = {
        row["trait"]: row
        for row in packet["seed_generation_request"]["trait_constraints"]
    }
    assert request_constraints["enemies"] == packet_constraints["enemies"]
    selection_prompt = render_seed_selection_prompt(
        seed_generation_request=packet["seed_generation_request"],
        candidates_payload={"candidates": []},
    )
    assert '"cold_start_relationships": "forbidden"' in selection_prompt
    assert '"blocked_relationship_types": [' in selection_prompt
    assert '"rival"' in selection_prompt
    assert '"blocked_pair_tags": [' in selection_prompt
    assert '"hunting"' in selection_prompt
