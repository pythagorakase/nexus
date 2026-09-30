"""Live structured-call and hydrated-packet proof for issue #601.

The wizard runs against a disposable template clone created and migrated by
``disposable_slot_database`` (``initialize_slot_database``, the production
slot initializer) and routed under ``ROUTED_SLOT``; the clone is dropped
afterward, so no numbered owner slot is reset. Staging the captured QA cache
before the model call is proven without the live opt-in in
``tests/test_live_gate_clones_pg.py``.
"""

from __future__ import annotations


import json
import os
from collections.abc import Iterator
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
from nexus.api.wizard_agent import WizardContext, get_wizard_agent
from nexus.config import load_settings, resolve_model_ref
from tests.model_registry_helpers import registry_model
from tests.pg_fixtures import disposable_slot_database, route_slot_to_disposable

# The slot label the clone is routed under for the wizard's slot resolvers.
ROUTED_SLOT = 4
THREAD_ID = "issue_601_live_trait_confirmation"
FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "slot3_midnight_qa_wizard_cache.json"
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_llm,
    pytest.mark.requires_postgres,
    pytest.mark.skipif(
        os.environ.get("NEXUS_ISSUE_601_LIVE") != "1",
        reason="Set NEXUS_ISSUE_601_LIVE=1 to run the live trait-confirmation proof.",
    ),
]


def stage_trait_confirmation(
    dbname: str, model_name: str
) -> tuple[dict[str, Any], WizardContext]:
    """Stage the captured QA wizard cache in a routed clone; build the context.

    Persists the slot model, the setting/character/seed drafts, and the
    concept's three suggested traits with their rationales, then returns the
    fixture and the character-phase ``WizardContext`` read back from the clone.
    """

    from nexus.api.save_slots import upsert_slot

    fixture = json.loads(FIXTURE_PATH.read_text())
    upsert_slot(ROUTED_SLOT, model=model_name, dbname=dbname)
    character = fixture["character"]
    seed = fixture["seed"]
    write_cache(
        thread_id=THREAD_ID,
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
        target_slot=ROUTED_SLOT,
        dbname=dbname,
    )
    write_suggested_traits(
        dbname,
        [
            {
                "trait": trait,
                "rationale": character["concept"]["trait_rationales"][trait],
            }
            for trait in character["concept"]["suggested_traits"]
        ],
    )

    context = WizardContext(
        slot=ROUTED_SLOT,
        cache=read_cache(dbname),
        phase="character",
        thread_id=THREAD_ID,
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
    return fixture, context


@pytest.fixture()
def trait_confirmation_slot(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A fresh migrated clone routed under ``ROUTED_SLOT``, source pins kept."""

    with disposable_slot_database("qa640_issue_601", story_pin=None) as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=ROUTED_SLOT, dbname=dbname)
        yield dbname


@pytest.mark.asyncio
async def test_live_trait_confirmation_persists_and_threads_constraint(
    trait_confirmation_slot: str,
) -> None:
    """The registry-selected wizard model types the live QA rationale in one call."""

    dbname = trait_confirmation_slot
    model_ref = os.environ.get("NEXUS_ISSUE_601_MODEL", registry_model("openai"))
    model_name = resolve_model_ref(model_ref)
    _, context = stage_trait_confirmation(dbname, model_name)
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

    hydrated = read_cache(dbname)
    assert hydrated is not None
    packet = build_retrograde_dry_run_packet(
        slot=ROUTED_SLOT,
        dbname=dbname,
        cache=hydrated,
        vocabulary=enumerate_seed_eligible_vocabulary(dbname=dbname),
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
