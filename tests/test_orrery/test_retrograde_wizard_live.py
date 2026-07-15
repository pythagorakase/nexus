"""Live end-to-end proof: the wizard transition cold-starts Retrograde history.

DESTRUCTIVE: this test drops and recreates an explicitly designated disposable
save slot, installs the canned wizard cache fixture, then runs the
real ``perform_transition_with_retrograde`` flow -- real Skald seed-candidate
and expansion calls, real persistence, real embedding, real MEMNON retrieval.

Gating: requires ``NEXUS_RUN_LIVE_LLM=1``, ``NEXUS_RUN_POSTGRES=1``, and the
explicit destructive opt-in ``NEXUS_RETROGRADE_WIZARD_E2E=1``. Set
``NEXUS_DISPOSABLE_TEST_SLOT`` to 1-4 and confirm its database name exactly in
``NEXUS_CONFIRM_DISPOSABLE_DB``. Slot 5 is categorically rejected.

Model selection: defaults to the wizard default model (wizard.default_model in
nexus.toml). Set ``NEXUS_RETROGRADE_WIZARD_MODEL`` to an ``@provider.role``
reference (e.g. ``@anthropic.default``) to prove the run on another provider.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

SLOT = int(os.environ.get("NEXUS_DISPOSABLE_TEST_SLOT", "0"))
DISPOSABLE_DBNAME = f"save_{SLOT:02d}"
DISPOSABLE_DSN = f"postgresql://pythagor@localhost:5432/{DISPOSABLE_DBNAME}"
MODEL_OVERRIDE_ENV = "NEXUS_RETROGRADE_WIZARD_MODEL"


def _live_run_model() -> str:
    """Wizard default model, or the @provider.role env override if set."""
    from nexus.api.config_utils import get_new_story_model
    from nexus.config import resolve_model_ref

    override = os.environ.get(MODEL_OVERRIDE_ENV)
    if override:
        return resolve_model_ref(override)
    return get_new_story_model()


pytestmark = [
    pytest.mark.live,
    pytest.mark.live_llm,
    pytest.mark.requires_postgres,
    pytest.mark.skipif(
        os.environ.get("NEXUS_RETROGRADE_WIZARD_E2E") != "1"
        or SLOT not in {1, 2, 3, 4}
        or os.environ.get("NEXUS_CONFIRM_DISPOSABLE_DB") != DISPOSABLE_DBNAME,
        reason=(
            "Set NEXUS_RETROGRADE_WIZARD_E2E=1, choose disposable slot 1-4 "
            "with NEXUS_DISPOSABLE_TEST_SLOT, and confirm its database name "
            "with NEXUS_CONFIRM_DISPOSABLE_DB. Slot 5 is forbidden."
        ),
    ),
]


def test_wizard_transition_cold_starts_retrograde_history() -> None:
    """A new story created through the transition gets retrievable history."""

    from nexus.agents.memnon.memnon import MEMNON
    from nexus.api.new_story_flow import perform_transition_with_retrograde
    from nexus.api.new_story_schemas import CharacterCreationState
    from nexus.api.wizard_test_cache import load_cache
    from nexus.config import load_settings

    settings = load_settings()
    assert settings.orrery is not None
    wizard_settings = settings.orrery.retrograde.wizard
    assert wizard_settings.enabled, "Enable orrery.retrograde.wizard for this test"

    transition_data = _install_fixture_world()

    result = perform_transition_with_retrograde(SLOT, transition_data)

    retrograde = result["retrograde"]
    assert retrograde["enabled"] is True, retrograde
    expected_model = _live_run_model()
    assert retrograde["model"] == expected_model, (
        "Retrograde ran with an unexpected model: "
        f"got {retrograde['model']!r}, expected {expected_model!r}"
    )

    # Canonical history landed with source='retrograde'.
    rows = _query(
        """
        SELECT we.id, we.event_type, rs.summary_text AS summary,
               rs.id AS summary_id
        FROM world_events we
        JOIN retrograde_summaries rs ON rs.world_event_id = we.id
        WHERE we.source = 'retrograde'
        ORDER BY we.id
        """
    )
    assert rows, "No retrograde world_events were persisted"
    assert all(row["summary_id"] is not None for row in rows)

    # Dedicated summaries went through their own embedding lifecycle.
    summary_ids = sorted(int(row["summary_id"]) for row in rows)
    embedded = _query(
        """
        SELECT id, embedding_generated_at
        FROM retrograde_summaries
        WHERE id = ANY(%s)
        """,
        (summary_ids,),
    )
    assert {int(row["id"]) for row in embedded} == set(summary_ids)
    assert all(row["embedding_generated_at"] is not None for row in embedded), (
        "Retrograde summaries are not embedded; embedded == ironman is " "the contract"
    )
    assert sorted(retrograde["embedded_summary_ids"]) == summary_ids

    # Decision 8: new minimum-viable stubs stay within the configured cap.
    stub_rows = _query(
        """
        SELECT name FROM characters
        WHERE extra_data ->> 'stub_kind' = 'retrograde_expansion_ref'
        UNION ALL
        SELECT name FROM places
        WHERE extra_data ->> 'stub_kind' = 'retrograde_expansion_ref'
        UNION ALL
        SELECT name FROM factions
        WHERE extra_data ->> 'stub_kind' = 'retrograde_expansion_ref'
        """
    )
    assert len(stub_rows) <= wizard_settings.max_new_entity_stubs

    # Trait-compiler stubs (if any) remain stubs: no recursive maturation.
    protagonist = _query(
        "SELECT id, name FROM characters WHERE id = %s",
        (result["character_id"],),
    )
    state = CharacterCreationState(**load_cache()["character_draft"])
    assert protagonist[0]["name"] == state.to_character_sheet().name

    # Decision 6 surface: visible roster + hidden counts, no event prose.
    surface = retrograde["surface"]
    assert surface["hidden_counts"]["world_events"] == len(rows)
    for event in rows:
        assert event["summary"] not in repr(surface["visible"])

    # MEMNON retrieves the generated history through the production path.
    memnon = MEMNON(interface=None, db_url=DISPOSABLE_DSN)
    target = max(rows, key=lambda row: len(row["summary"]))
    search = memnon.query_memory(query=target["summary"], k=10, use_hybrid=True)
    returned_ids = {
        int(item["summary_id"])
        for item in search["results"]
        if item.get("content_type") == "retrograde_summary"
    }
    assert returned_ids & set(summary_ids), (
        "MEMNON did not retrieve any Retrograde summary; "
        f"returned={sorted(returned_ids)} expected_any={summary_ids}"
    )


def _install_fixture_world() -> Any:
    """Reset the confirmed disposable slot and stage the canned wizard cache."""

    from nexus.api.db_pool import close_pool
    from nexus.api.new_story_cache import write_cache
    from nexus.api.new_story_schemas import (
        CharacterCreationState,
        CharacterSheet,
        LayerDefinition,
        PlaceProfile,
        SettingCard,
        StorySeed,
        TransitionData,
        ZoneDefinition,
    )
    from nexus.api.save_slots import upsert_slot
    from nexus.api.wizard_test_cache import load_cache
    from scripts.new_story_setup import create_slot_schema_only

    close_pool(DISPOSABLE_DBNAME)
    create_slot_schema_only(SLOT, source_db="NEXUS_template", force=True)

    # Fresh slots default to the mock TEST model (global.model.
    # default_slot_model); a real wizard run overrides it in start_setup.
    # Mirror that here so the transition engages real Retrograde generation.
    upsert_slot(SLOT, model=_live_run_model(), dbname=DISPOSABLE_DBNAME)

    cache = load_cache()
    seed = StorySeed(**cache["selected_seed"])
    write_cache(
        thread_id="thread_retrograde_wizard_live",
        setting_draft=cache["setting_draft"],
        character_draft=cache["character_draft"],
        selected_seed=cache["selected_seed"],
        layer_draft=cache["layer_draft"],
        zone_draft=cache["zone_draft"],
        initial_location=cache["initial_location"],
        base_timestamp=cache["base_timestamp"],
        target_slot=SLOT,
        dbname=DISPOSABLE_DBNAME,
    )

    state = CharacterCreationState(**cache["character_draft"])
    return TransitionData(
        setting=SettingCard(**cache["setting_draft"]),
        character=CharacterSheet(**state.to_character_sheet().model_dump()),
        seed=seed,
        layer=LayerDefinition(**cache["layer_draft"]),
        zone=ZoneDefinition(**cache["zone_draft"]),
        location=PlaceProfile(**cache["initial_location"]),
        base_timestamp=seed.get_base_datetime(),
        thread_id="thread_retrograde_wizard_live",
        setup_duration_minutes=None,
        ready_for_transition=True,
        validated=True,
    )


def _query(sql: str, params: Any = None) -> list[dict[str, Any]]:
    conn = psycopg2.connect(DISPOSABLE_DSN)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()
