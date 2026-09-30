"""Live end-to-end proof: the wizard transition cold-starts Retrograde history.

The test runs against a disposable template clone created and migrated by
``disposable_slot_database`` (``initialize_slot_database``, the production
slot initializer) and routed under ``ROUTED_SLOT``; the clone is dropped
afterward, so no numbered owner slot is reset, read, or written. It installs
the canned wizard cache fixture, then runs the real
``perform_transition_with_retrograde`` flow -- real Skald seed-candidate and
expansion calls, real persistence, real embedding, real MEMNON retrieval.

Gating: requires ``NEXUS_RUN_LIVE_LLM=1``, ``NEXUS_RUN_POSTGRES=1``, and the
expensive-run opt-in ``NEXUS_RETROGRADE_WIZARD_E2E=1``. Staging the wizard
cache and slot model before the first model call is proven without the live
opt-in in ``tests/test_live_gate_clones_pg.py``.

Model selection: defaults to the wizard default model (wizard.default_model in
nexus.toml). Set ``NEXUS_RETROGRADE_WIZARD_MODEL`` to a registered model ID to
prove the run on another provider.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import closing
from typing import Any

import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
)

# The slot label the clone is routed under for the transition's slot
# resolvers.
ROUTED_SLOT = 4
THREAD_ID = "thread_retrograde_wizard_live"
MODEL_OVERRIDE_ENV = "NEXUS_RETROGRADE_WIZARD_MODEL"


def _live_run_model() -> str:
    """Wizard default model, or an explicit model ID override if set."""
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
        os.environ.get("NEXUS_RETROGRADE_WIZARD_E2E") != "1",
        reason="Set NEXUS_RETROGRADE_WIZARD_E2E=1 to run the live cold-start proof.",
    ),
]


@pytest.fixture()
def retrograde_wizard_slot(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A fresh migrated clone routed under ``ROUTED_SLOT``, source pins kept."""

    with disposable_slot_database("qa640_retrograde_wizard", story_pin=None) as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=ROUTED_SLOT, dbname=dbname)
        monkeypatch.setenv("NEXUS_SLOT", str(ROUTED_SLOT))
        yield dbname


def test_wizard_transition_cold_starts_retrograde_history(
    retrograde_wizard_slot: str,
) -> None:
    """A new story created through the transition gets retrievable history."""

    from nexus.agents.memnon.memnon import MEMNON
    from nexus.api.new_story_flow import perform_transition_with_retrograde
    from nexus.api.new_story_schemas import CharacterCreationState
    from nexus.api.wizard_test_cache import load_cache
    from nexus.config import load_settings
    from nexus.database import database_url

    settings = load_settings()
    assert settings.orrery is not None
    wizard_settings = settings.orrery.retrograde.wizard
    assert wizard_settings.enabled, "Enable orrery.retrograde.wizard for this test"

    dbname = retrograde_wizard_slot
    transition_data = stage_fixture_world(dbname)

    # The player's strangeness reaches generation and is recorded as genesis
    # provenance with the genre band it resolved to (#838).
    result = perform_transition_with_retrograde(
        ROUTED_SLOT, transition_data, weird_level="high"
    )

    retrograde = result["retrograde"]
    assert retrograde["enabled"] is True, retrograde
    genre = retrograde["weird"]["genre"]
    band = settings.orrery.retrograde.weird.bands_by_genre[genre].high
    [provenance] = _query(dbname, "SELECT genesis_weird FROM global_variables")
    assert provenance["genesis_weird"] == {
        **retrograde["weird"],
        "selected_level": "high",
    }
    assert provenance["genesis_weird"]["level"] == "high"
    assert provenance["genesis_weird"]["source"] == "configured_band"
    assert (
        provenance["genesis_weird"]["raw_min"],
        provenance["genesis_weird"]["raw_max"],
    ) == (band.min, band.max)
    expected_model = _live_run_model()
    assert retrograde["model"] == expected_model, (
        "Retrograde ran with an unexpected model: "
        f"got {retrograde['model']!r}, expected {expected_model!r}"
    )

    # Canonical history landed with source='retrograde'.
    rows = _query(
        dbname,
        """
        SELECT we.id, we.event_type, rs.summary_text AS summary,
               rs.id AS summary_id
        FROM world_events we
        JOIN retrograde_summaries rs ON rs.world_event_id = we.id
        WHERE we.source = 'retrograde'
        ORDER BY we.id
        """,
    )
    assert rows, "No retrograde world_events were persisted"
    assert all(row["summary_id"] is not None for row in rows)

    # Dedicated summaries went through their own embedding lifecycle.
    summary_ids = sorted(int(row["summary_id"]) for row in rows)
    embedded = _query(
        dbname,
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

    # Decision 8: stubs beyond the first-class starting set stay within the
    # configured cap. First-class stubs (for example, trait targets without a
    # trait-compiler row) are inserted but not charged, as in R6 validation.
    stub_budget = retrograde["entity_stub_budget"]
    assert stub_budget["max_new_entity_stubs"] == wizard_settings.max_new_entity_stubs
    assert len(stub_budget["charged_stubs"]) <= wizard_settings.max_new_entity_stubs
    stub_rows = _query(
        dbname,
        """
        SELECT name FROM characters
        WHERE extra_data ->> 'stub_kind' = 'retrograde_expansion_ref'
        UNION ALL
        SELECT name FROM places
        WHERE extra_data ->> 'stub_kind' = 'retrograde_expansion_ref'
        UNION ALL
        SELECT name FROM factions
        WHERE extra_data ->> 'stub_kind' = 'retrograde_expansion_ref'
        """,
    )
    assert len(stub_rows) <= len(stub_budget["charged_stubs"]) + len(
        stub_budget["first_class_stubs"]
    )

    # Trait-compiler stubs (if any) remain stubs: no recursive maturation.
    protagonist = _query(
        dbname,
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
    memnon = MEMNON(interface=None, db_url=database_url(dbname))
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


def stage_fixture_world(dbname: str) -> Any:
    """Stage the canned wizard cache in a fresh routed clone; build the data.

    Persists the live run's slot model and the confirmed setting, character,
    seed, layer, zone, and location drafts under ``ROUTED_SLOT``, then returns
    the ``TransitionData`` the transition consumes.
    """

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

    # Fresh slots default to the mock TEST model (global.model.
    # default_slot_model); a real wizard run overrides it in start_setup.
    # Mirror that here so the transition engages real Retrograde generation.
    upsert_slot(ROUTED_SLOT, model=_live_run_model(), dbname=dbname)

    cache = load_cache()
    seed = StorySeed(**cache["selected_seed"])
    write_cache(
        thread_id=THREAD_ID,
        setting_draft=cache["setting_draft"],
        character_draft=cache["character_draft"],
        selected_seed=cache["selected_seed"],
        layer_draft=cache["layer_draft"],
        zone_draft=cache["zone_draft"],
        initial_location=cache["initial_location"],
        base_timestamp=cache["base_timestamp"],
        target_slot=ROUTED_SLOT,
        dbname=dbname,
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
        thread_id=THREAD_ID,
        setup_duration_minutes=None,
        ready_for_transition=True,
        validated=True,
    )


def _query(dbname: str, sql: str, params: Any = None) -> list[dict[str, Any]]:
    with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
