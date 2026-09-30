"""The live gates' clone fixtures and non-LLM paths, without the live opt-in.

The live-LLM gates (the golden path, the issue #600 and #601 wizard proofs,
runtime maturation, and the Orrery cycle) keep their live markers, so their
fixtures never run in the PostgreSQL gate. Each of them now runs on a
disposable template clone routed under a slot label instead of resetting or
writing a numbered owner slot. These tests run the same staging functions on
TEST-pinned clones under ``NEXUS_RUN_POSTGRES=1`` and assert what each gate
relies on before its first model call, including that the golden path's
gateway subprocess serves the clone for the routed slot and refuses any other
slot. No provider is called.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
import requests  # type: ignore[import-untyped]
from sqlalchemy.engine import make_url

from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.agents.orrery.retrograde_maturation import (
    enqueue_declared_entity_maturations,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.api import slot_utils
from nexus.api.config_utils import get_new_story_model
from nexus.api.new_story_cache import get_trait_menu, read_cache
from nexus.api.save_slots import get_slot_model
from nexus.config import load_settings_as_dict, resolve_model_ref
from tests.model_registry_helpers import registry_model
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
)
from tests.test_golden_path_live import (
    FIXTURE as GOLDEN_PATH_FIXTURE,
    ROUTED_SLOT as GOLDEN_PATH_SLOT,
    assert_server_log_clean,
    launch_routed_gateway,
    stage_reset_slot,
)
from tests.test_issue_601_wizard_live import (
    ROUTED_SLOT as ISSUE_601_SLOT,
    THREAD_ID as ISSUE_601_THREAD_ID,
    stage_trait_confirmation,
)
from tests.test_orrery.test_live_cycle import (
    ROUTED_SLOT as LIVE_CYCLE_SLOT,
    seed_live_cycle_story,
)
from tests.test_orrery.test_retrograde_maturation_live import (
    ROUTED_SLOT as MATURATION_SLOT,
    archivist_declaration,
    seed_maturation_story,
)
from tests.test_wizard_live import (
    ISSUE_600_ROUTED_SLOT,
    ISSUE_600_THREAD_ID,
    issue_600_seed_repair_setting,
    stage_issue_600_seed_context,
)

pytestmark = pytest.mark.requires_postgres

# The golden path's gateway subprocess serves this lane in the proof below.
GATEWAY_LANE = 8019


@pytest.fixture()
def clone(request: pytest.FixtureRequest) -> Iterator[str]:
    """A TEST-pinned template clone named for the requesting test."""

    with disposable_slot_database(f"qa640_{request.node.name[:24]}") as dbname:
        yield dbname


def test_live_cycle_seed_routes_and_queues_a_promotion_backlog(
    clone: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live cycle's seed binds actors and leaves a pending backlog."""

    route_slot_to_disposable(monkeypatch.setattr, slot=LIVE_CYCLE_SLOT, dbname=clone)
    monkeypatch.setenv("NEXUS_SLOT", str(LIVE_CYCLE_SLOT))
    story = seed_live_cycle_story(clone)
    assert make_url(slot_utils.get_slot_db_url(slot=LIVE_CYCLE_SLOT)).database == clone

    orrery_settings = load_settings_as_dict()["orrery"]
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(slot_utils.get_slot_db_url(slot=LIVE_CYCLE_SLOT))
    try:
        with Session(engine) as session:
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=story.anchor_chunk_id,
                window_chunks=int(orrery_settings["binding"]["window_chunks"]),
                sunhelm_settings=orrery_settings.get("sunhelm"),
            )
            session.rollback()
    finally:
        engine.dispose()
    assert proposal.actor_count >= 1, "the seeded cast binds as Orrery actors"
    with closing(connect(clone)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM orrery_resolutions "
            "WHERE promotion_status = 'pending' AND id = ANY(%s)",
            (list(story.backlog_resolution_ids),),
        )
        assert cur.fetchone()[0] == len(story.backlog_resolution_ids)


def test_maturation_enqueue_is_idempotent_on_the_routed_clone(
    clone: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The maturation gate's declaration stubs once and queues one job."""

    monkeypatch.setenv("NEXUS_SLOT", str(MATURATION_SLOT))
    story = seed_maturation_story(clone, monkeypatch.setattr)
    name = "Archivist Veil-clone"
    declaration = archivist_declaration(name)
    with closing(connect(clone)) as conn:
        result = enqueue_declared_entity_maturations(
            conn,
            declarations=[declaration],
            chunk_id=story.chunk_id,
            raw_text=f"{name} surfaces from the archive stacks with a ledger.",
            slot=MATURATION_SLOT,
        )
        conn.commit()
        assert result.stubs_created == 1
        assert result.jobs_enqueued == 1
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.state::text, j.slot, j.requesting_chunk_id, c.name
                FROM orrery_maturation_jobs j
                JOIN characters c ON c.entity_id = j.entity_id
                WHERE j.entity_name = %s
                """,
                (name,),
            )
            jobs = cur.fetchall()
        conn.rollback()
        assert jobs == [("queued", str(MATURATION_SLOT), story.chunk_id, name)]

        rerun = enqueue_declared_entity_maturations(
            conn,
            declarations=[declaration],
            chunk_id=story.chunk_id,
            raw_text=f"{name} appears again.",
            slot=MATURATION_SLOT,
        )
        conn.commit()
    assert rerun.stubs_created == 0
    assert rerun.jobs_enqueued == 0
    assert rerun.jobs_already_present == 1


def test_issue_601_staging_persists_the_captured_cache(
    clone: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The trait-confirmation proof's cache, model, and suggestions persist."""

    route_slot_to_disposable(monkeypatch.setattr, slot=ISSUE_601_SLOT, dbname=clone)
    model_name = resolve_model_ref(registry_model("openai"))
    fixture, context = stage_trait_confirmation(clone, model_name)

    assert get_slot_model(ISSUE_601_SLOT, dbname=clone) == model_name
    assert context.cache is not None
    assert context.cache.thread_id == ISSUE_601_THREAD_ID
    assert context.cache.get_setting_dict() is not None
    rationales = fixture["character"]["concept"]["trait_rationales"]
    selected = {item.name: item.rationale for item in get_trait_menu(clone)}
    suggested = fixture["character"]["concept"]["suggested_traits"]
    assert {
        name: rationale for name, rationale in selected.items() if name in suggested
    } == {trait: rationales[trait] for trait in suggested}
    assert {item.name for item in get_trait_menu(clone) if item.is_selected} == set(
        suggested
    )


def test_issue_600_staging_confirms_setting_and_character(
    clone: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seed-repair proof reaches the seed phase with the dated setting."""

    route_slot_to_disposable(
        monkeypatch.setattr, slot=ISSUE_600_ROUTED_SLOT, dbname=clone
    )
    model_name = resolve_model_ref(registry_model("openai"))
    context = stage_issue_600_seed_context(clone, model_name)

    setting = issue_600_seed_repair_setting()
    assert context.cache is not None
    accepted_setting = context.cache.get_setting_dict()
    assert accepted_setting is not None
    assert accepted_setting["time_period"] == "October 2026"
    assert accepted_setting["diegetic_artifact"] == setting["diegetic_artifact"]
    persisted = read_cache(clone)
    assert persisted is not None
    assert persisted.thread_id == ISSUE_600_THREAD_ID
    assert persisted.pending_confirmation() is None
    assert persisted.base_timestamp is None, "the seed has not been submitted"


def test_golden_path_staging_and_routed_gateway_serve_only_the_clone(
    clone: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate's staged clone is what its gateway subprocess serves."""

    import json

    route_slot_to_disposable(monkeypatch.setattr, slot=GOLDEN_PATH_SLOT, dbname=clone)
    # No gateway scheduler: this proof covers the routed HTTP surface only.
    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    stage_reset_slot(clone)
    fixture_thread_id = json.loads(GOLDEN_PATH_FIXTURE.read_text())["thread_id"]
    staged = read_cache(clone)
    assert staged is not None
    assert staged.thread_id == fixture_thread_id
    assert staged.pending_confirmation() is None
    assert get_slot_model(GOLDEN_PATH_SLOT, dbname=clone) == get_new_story_model()

    check = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{GATEWAY_LANE}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 1, f"lane {GATEWAY_LANE} is busy: {check.stdout}"
    monkeypatch.setenv("NARRATIVE_API_PORT", str(GATEWAY_LANE))
    api = f"http://127.0.0.1:{GATEWAY_LANE}"
    log_path = tmp_path / "server.log"
    with log_path.open("w") as log_handle:
        server = launch_routed_gateway(clone, log_handle, store_access=False)
        try:
            from tests.test_golden_path_live import _wait_health

            _wait_health(api)
            routed = requests.get(
                f"{api}/api/slot/{GOLDEN_PATH_SLOT}/state", timeout=30
            )
            assert routed.status_code == 200, routed.text
            state = routed.json()
            assert state["slot"] == GOLDEN_PATH_SLOT
            assert state["is_wizard_mode"] is True
            assert state["thread_id"] == fixture_thread_id
            # The clone served the routed slot cleanly; the refusal below is
            # expected to log its error.
            assert_server_log_clean(log_path.read_text())
            refused = requests.get(f"{api}/api/slot/2/state", timeout=30)
            assert refused.status_code == 500, refused.text
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=15)
    assert "Slot 2 is not routed" in log_path.read_text()
