"""Durable genesis proofs on slot 4's disposable, migrated template clones.

Tables: genesis_runs, genesis_run_stages, assets.new_story_creator and the
world tables consumed by the real wizard mapper. No owner database is written.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import uuid
from contextlib import closing
from typing import Any

import pytest
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.retrograde_orchestrator import (
    finish_genesis_persistence,
    get_retrograde_progress,
    record_genesis_failure,
    record_genesis_stage_output,
    record_retrograde_progress,
    start_genesis_run,
)
from nexus.api.new_story_flow import perform_transition_with_retrograde
from nexus.api.save_slots import upsert_slot
from nexus.api.wizard_chat import retrograde_status_endpoint
from tests.pg_fixtures import connect, routed_slot_environment
from tests.settings_helpers import settings_with
from tests.test_orrery.test_retrograde_wizard_live import stage_fixture_world

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def staged(monkeypatch: pytest.MonkeyPatch, offline_gate_db: str) -> tuple[str, Any]:
    """Stage the real cache and pin, replacing only the provider boundaries."""
    monkeypatch.delenv("NEXUS_RETROGRADE_WIZARD_MODEL", raising=False)
    data = stage_fixture_world(offline_gate_db)
    monkeypatch.setattr(
        "nexus.api.trait_input_derivation.ensure_trait_compile_inputs",
        lambda *args, **kwargs: {"derived": False},
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_seed_candidates.run_seed_stage",
        lambda **kwargs: {
            "model": "TEST",
            "seed_candidate_response": {
                "candidates": [],
                "selected_seed_ids": [],
            },
        },
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_expansion.generate_expansion_with_skald",
        lambda **kwargs: {"retrograde_expansion_plan": {"canned": "expansion"}},
    )
    return offline_gate_db, data


def _rows(dbname: str, table: str) -> list[dict[str, Any]]:
    with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
        with conn.cursor() as cur:
            # Table names are fixed by the callers, never user input.
            cur.execute(f"SELECT * FROM {table} ORDER BY started_at")
            return list(cur.fetchall())


def test_stage_rows_and_outputs_persist(staged: tuple[str, Any]) -> None:
    """Successful generation outputs survive the mapper's validation refusal."""
    dbname, data = staged
    data = data.model_copy(
        update={"zone": None, "ready_for_transition": False, "validated": False}
    )
    with pytest.raises(ValueError, match="Transition data is incomplete"):
        perform_transition_with_retrograde(4, data)
    rows = {row["stage"]: row for row in _rows(dbname, "genesis_run_stages")}
    assert rows["derivation"]["output"] is None
    assert rows["derivation"]["finished_at"] is not None
    assert rows["packet"]["output"]["weird"]
    assert rows["seed_candidates"]["output"] == {
        "candidates": [],
        "selected_seed_ids": [],
    }
    assert rows["expansion"]["output"] == {"canned": "expansion"}
    assert all(rows[stage]["finished_at"] is not None for stage in rows)
    status = asyncio.run(retrograde_status_endpoint(4))
    assert [item["stage"] for item in status["stages"]] == [
        "derivation",
        "packet",
        "seed_candidates",
        "expansion",
        "persistence",
        "failed",
    ]


@pytest.mark.parametrize(
    "stage",
    ["derivation", "packet", "seed_candidates", "expansion", "persistence", None],
)
def test_failure_is_recorded_at_each_stage(
    staged: tuple[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    stage: str | None,
) -> None:
    """Every fallible stage and a stage-less refusal retain the original error."""
    dbname, data = staged
    boundaries = {
        "derivation": "nexus.api.trait_input_derivation.ensure_trait_compile_inputs",
        "packet": (
            "nexus.agents.orrery.retrograde_packet.build_retrograde_dry_run_packet"
        ),
        "seed_candidates": (
            "nexus.agents.orrery.retrograde_seed_candidates.run_seed_stage"
        ),
        "expansion": (
            "nexus.agents.orrery.retrograde_expansion.generate_expansion_with_skald"
        ),
    }

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise ValueError(f"refused {stage}")

    if stage in boundaries:
        monkeypatch.setattr(boundaries[stage], refuse)
        message = f"refused {stage}"
    else:
        data = data.model_copy(
            update={"zone": None, "ready_for_transition": False, "validated": False}
        )
        message = "Transition data is incomplete"
        if stage is None:
            upsert_slot(4, model="TEST", dbname=dbname)
    with pytest.raises(ValueError, match=message) as raised:
        perform_transition_with_retrograde(4, data)
    [run] = _rows(dbname, "genesis_runs")
    assert run["status"] == "failed"
    assert run["stage"] == stage
    assert run["error"] == f"ValueError: {raised.value}"
    assert run["finished_at"] is not None
    status = asyncio.run(retrograde_status_endpoint(4))
    assert status["run_status"] == "failed"
    assert status["error"] == run["error"]
    if stage is None:
        assert status["stage"] == "idle"
        assert status["stages"] == []
    else:
        assert status["stage"] == "failed"
        assert status["detail"] == {"stage": stage}
        assert status["stages"][-1]["stage"] == "failed"
        if stage == "derivation":
            assert [item["stage"] for item in status["stages"]] == [
                "derivation",
                "failed",
            ]
    if stage is None:
        assert _rows(dbname, "genesis_run_stages") == []
    json.dumps(status)


def test_running_derivation_reports_its_stage(
    staged: tuple[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The status route exposes committed derivation while its call is held."""
    _dbname, data = staged
    entered, release = threading.Event(), threading.Event()
    errors: list[Exception] = []

    def derive(*args: Any, **kwargs: Any) -> None:
        entered.set()
        if not release.wait(20):
            raise RuntimeError("derivation release timed out")
        raise ValueError("derivation released")

    def transition() -> None:
        try:
            perform_transition_with_retrograde(4, data)
        except Exception as exc:
            errors.append(exc)

    monkeypatch.setattr(
        "nexus.api.trait_input_derivation.ensure_trait_compile_inputs", derive
    )
    thread = threading.Thread(target=transition)
    thread.start()
    try:
        assert entered.wait(20)
        status = asyncio.run(retrograde_status_endpoint(4))
        assert status["stage"] == "derivation"
        assert status["run_status"] == "running"
        assert status["stages"][0]["stage"] == "derivation"
    finally:
        release.set()
        thread.join(20)
    assert not thread.is_alive()
    assert len(errors) == 1 and str(errors[0]) == "derivation released"


def test_another_process_reads_the_running_stage(
    staged: tuple[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A separate interpreter sees the committed packet stage while it runs."""
    dbname, data = staged
    entered, release = threading.Event(), threading.Event()
    errors: list[Exception] = []

    def packet(**kwargs: Any) -> None:
        entered.set()
        if not release.wait(20):
            raise RuntimeError("packet release timed out")
        raise ValueError("packet released")

    def transition() -> None:
        try:
            perform_transition_with_retrograde(4, data)
        except Exception as exc:
            errors.append(exc)

    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_packet.build_retrograde_dry_run_packet", packet
    )
    thread = threading.Thread(target=transition)
    thread.start()
    try:
        assert entered.wait(20)
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from tests.pg_fixtures import route_slot_from_environment; "
                    "route_slot_from_environment(); "
                    "from nexus.agents.orrery.retrograde_orchestrator "
                    "import get_retrograde_progress; "
                    "import json; print(json.dumps(get_retrograde_progress(4)))"
                ),
            ],
            env={
                **os.environ,
                "PYTHONPATH": os.getcwd(),
                **routed_slot_environment(4, dbname),
            },
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        status = json.loads(child.stdout)
        [run] = _rows(dbname, "genesis_runs")
        assert status["run"] == uuid.UUID(str(run["run_id"])).hex
        assert (status["stage"], status["run_status"]) == ("packet", "running")
    finally:
        release.set()
        thread.join(20)
    assert not thread.is_alive()
    assert len(errors) == 1 and str(errors[0]) == "packet released"


def test_skipped_run_commits_with_the_world(staged: tuple[str, Any]) -> None:
    """TEST-provider transition commits the real world and its skipped run."""
    dbname, data = staged
    upsert_slot(4, model="TEST", dbname=dbname)
    result = perform_transition_with_retrograde(4, data)
    assert result["character_id"]
    [run] = _rows(dbname, "genesis_runs")
    assert (run["status"], run["skip_reason"]) == ("done", "mock_wizard_model")
    assert run["input_fingerprint"] is None and run["opening_session_id"] is None
    assert asyncio.run(retrograde_status_endpoint(4))["stage"] == "idle"


def test_skipped_retrograde_keeps_its_derivation_record(
    staged: tuple[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabling Retrograde preserves the derivation that preceded the skip."""
    import nexus.config

    dbname, data = staged
    settings = settings_with({"orrery.retrograde.wizard.enabled": False})
    monkeypatch.setattr(nexus.config, "load_settings", lambda *args, **kwargs: settings)
    result = perform_transition_with_retrograde(4, data)
    assert result["character_id"]
    [run] = _rows(dbname, "genesis_runs")
    assert (run["status"], run["skip_reason"]) == (
        "done",
        "retrograde_wizard_disabled",
    )
    status = asyncio.run(retrograde_status_endpoint(4))
    assert status["stage"] == "idle"
    assert status["run_status"] == "done"
    assert [item["stage"] for item in status["stages"]] == ["derivation"]


def test_persistence_record_shares_the_transaction(offline_gate_db: str) -> None:
    """Rollback leaves persistence open; commit saves its output and closure."""
    run = start_genesis_run(4)
    record_retrograde_progress(4, run, "persistence", {})
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        finish_genesis_persistence(cur, run=run, output={"counters": {}})
        conn.rollback()
        [stage] = _rows(offline_gate_db, "genesis_run_stages")
        assert stage["finished_at"] is None and stage["output"] is None
        finish_genesis_persistence(cur, run=run, output={"counters": {}})
        conn.commit()
    [stage] = _rows(offline_gate_db, "genesis_run_stages")
    assert stage["finished_at"] is not None and stage["output"] == {"counters": {}}


def test_unknown_stage_and_foreign_run_fail_loudly(offline_gate_db: str) -> None:
    """Unknown vocabulary and missing/finished runs cannot receive writes."""
    with pytest.raises(ValueError, match="Unknown Retrograde wizard stage"):
        record_retrograde_progress(4, "not-a-run", "unknown", {})
    run = start_genesis_run(4)
    record_retrograde_progress(4, run, "done", {"embedded_summaries": 0})
    status = get_retrograde_progress(4)
    assert status is not None and status["stage"] == "done"
    assert status["detail"] == {"embedded_summaries": 0}
    json.dumps(status)
    for foreign in (run, uuid.uuid4().hex):
        for writer in (
            lambda: record_retrograde_progress(4, foreign, "packet", {}),
            lambda: record_genesis_stage_output(4, foreign, "packet", {}),
            lambda: record_genesis_failure(4, foreign, "refused"),
        ):
            with pytest.raises(RuntimeError, match=foreign):
                writer()
    assert len(_rows(offline_gate_db, "genesis_run_stages")) == 1
