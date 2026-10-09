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
import time
import threading
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

import pytest
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.retrograde_orchestrator import (
    finish_genesis_persistence,
    genesis_slot_claim,
    load_genesis_run,
    record_genesis_input_fingerprint,
    get_retrograde_progress,
    record_genesis_failure,
    record_genesis_stage_output,
    record_retrograde_progress,
    start_genesis_run,
)
from nexus.api.new_story_flow import perform_transition_with_retrograde
from nexus.api.save_slots import upsert_slot
from nexus.api.narrative_schemas import TransitionRequest
from nexus.api.wizard_chat import (
    retrograde_status_endpoint,
    transition_to_narrative_endpoint,
)
from fastapi import HTTPException
from tests.pg_fixtures import connect, routed_slot_environment
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
    assert rows["derivation"]["output"] == {
        "trait_compile_inputs": None,
        "outcome": {"derived": False},
    }
    assert rows["derivation"]["finished_at"] is not None
    assert rows["packet"]["output"]["weird"]
    assert rows["seed_candidates"]["output"] == {
        "candidates": [],
        "selected_seed_ids": [],
    }
    assert rows["expansion"]["output"] == {"canned": "expansion"}
    assert all(rows[stage]["finished_at"] is not None for stage in rows)


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
    if stage in (None, "derivation"):
        assert status["stage"] == "idle"
        assert status["stages"] == []
    else:
        assert status["stage"] == "failed"
        assert status["detail"] == {"stage": stage}
        assert status["stages"][-1]["stage"] == "failed"
    if stage is None:
        assert _rows(dbname, "genesis_run_stages") == []
    json.dumps(status)


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
    fingerprint = run["input_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert int(fingerprint, 16) >= 0
    assert run["opening_session_id"] is None
    assert asyncio.run(retrograde_status_endpoint(4))["stage"] == "idle"


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


def _confirm_staged_world(dbname: str) -> None:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE assets.new_story_creator SET "
            "setting_confirmed = TRUE, character_confirmed = TRUE"
        )


def _seed_failed_output(slot: int, fingerprint: str, output: Any) -> str:
    run = start_genesis_run(slot)
    record_genesis_input_fingerprint(slot, run, fingerprint)
    record_retrograde_progress(slot, run, "derivation", {})
    record_genesis_stage_output(slot, run, "derivation", output)
    record_genesis_failure(slot, run, "ValueError: seeded failure")
    return run


def test_invalid_saved_output_fails_before_any_provider_call(
    staged: tuple[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed saved prefix fails without spending, then forces a fresh run."""
    dbname, _ = staged
    _confirm_staged_world(dbname)

    def stop_derivation(*args: Any, **kwargs: Any) -> None:
        raise ValueError("fingerprint probe")

    monkeypatch.setattr(
        "nexus.api.trait_input_derivation.ensure_trait_compile_inputs", stop_derivation
    )
    with pytest.raises(HTTPException, match="fingerprint probe") as initial:
        asyncio.run(transition_to_narrative_endpoint(TransitionRequest(slot=4)))
    assert initial.value.status_code == 400
    failed = load_genesis_run(4)
    assert failed is not None and failed.input_fingerprint is not None
    seeded = _seed_failed_output(4, failed.input_fingerprint, {"unexpected": 1})
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
    calls: list[str] = []

    def boundary(stage: str) -> Callable[..., None]:
        def refuse(*args: Any, **kwargs: Any) -> None:
            calls.append(stage)
            raise AssertionError(f"{stage} provider called")

        return refuse

    for stage, target in boundaries.items():
        monkeypatch.setattr(target, boundary(stage))
    with pytest.raises(HTTPException) as refused:
        asyncio.run(transition_to_narrative_endpoint(TransitionRequest(slot=4)))
    assert refused.value.status_code == 500
    assert "Saved derivation output" in refused.value.detail
    assert seeded in refused.value.detail
    assert calls == []
    invalid = load_genesis_run(4)
    assert invalid is not None and invalid.status == "failed" and invalid.stages == {}
    with pytest.raises(HTTPException) as retry:
        asyncio.run(transition_to_narrative_endpoint(TransitionRequest(slot=4)))
    assert retry.value.status_code == 500
    assert "derivation provider called" in retry.value.detail
    assert calls == ["derivation"]


def test_claim_is_exclusive_and_dies_with_its_process(
    offline_gate_db: str, tmp_path: Path
) -> None:
    """A real child owns a session claim; SIGKILL releases it without a commit."""
    ready = tmp_path / "claim-ready"
    script = """
import sys, time
from pathlib import Path
from tests.pg_fixtures import route_slot_from_environment
route_slot_from_environment()
from nexus.agents.orrery.retrograde_orchestrator import genesis_slot_claim
with genesis_slot_claim(4) as won:
    if not won:
        raise RuntimeError('child could not claim fixture slot')
    Path(sys.argv[1]).write_text('held')
    time.sleep(60)
"""
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        **routed_slot_environment(4, offline_gate_db),
    }
    with (tmp_path / "child.log").open("w") as output:
        child = subprocess.Popen(
            [sys.executable, "-c", script, str(ready)],
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 10
            while (
                not ready.exists()
                and child.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            assert ready.read_text() == "held"
            with genesis_slot_claim(4) as won:
                assert won is False
            child.kill()
            child.wait(timeout=10)
            deadline = time.monotonic() + 10
            acquired = False
            while time.monotonic() < deadline:
                with genesis_slot_claim(4) as won:
                    acquired = won
                if acquired:
                    break
                time.sleep(0.05)
            assert acquired, "The killed child's session claim did not release"
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)


def test_skipped_run_reports_reused_derivation_in_direct_and_ledger_answers(
    staged: tuple[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skipping Retrograde does not erase an actually reused derivation stage."""
    import tomlkit

    from nexus.api.new_story_flow import transition_result_from_ledger
    from nexus.config import load_settings
    from nexus.runtime.home import resolve_config_path

    config: Any = tomlkit.parse(resolve_config_path().read_text())
    config["orrery"]["enabled"] = False
    config["wizard"]["trait_inputs"]["derive_at_transition"] = True
    config["runtime"]["state_dir"] = str(tmp_path / "state")
    config_path = tmp_path / "skip-retrograde.toml"
    config_path.write_text(tomlkit.dumps(config))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config_path))
    dbname, _ = staged
    _confirm_staged_world(dbname)
    assert load_settings().wizard.trait_inputs.derive_at_transition

    def first_derivation(*args: Any, **kwargs: Any) -> None:
        raise ValueError("capture skip fingerprint")

    monkeypatch.setattr(
        "nexus.api.trait_input_derivation.ensure_trait_compile_inputs", first_derivation
    )
    with pytest.raises(HTTPException) as first:
        asyncio.run(transition_to_narrative_endpoint(TransitionRequest(slot=4)))
    assert first.value.status_code == 400
    assert "capture skip fingerprint" in first.value.detail
    failed = load_genesis_run(4)
    assert failed is not None and failed.input_fingerprint is not None
    seeded = _seed_failed_output(
        4,
        failed.input_fingerprint,
        {"trait_compile_inputs": None, "outcome": {"derived": False}},
    )

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("reused derivation must not call a provider")

    monkeypatch.setattr(
        "nexus.api.trait_input_derivation.ensure_trait_compile_inputs", forbidden
    )
    answer = asyncio.run(transition_to_narrative_endpoint(TransitionRequest(slot=4)))
    reconstructed = transition_result_from_ledger(4, answer.run)
    assert (
        answer.retrograde
        == reconstructed["retrograde"]
        == {
            "enabled": False,
            "skip_reason": "orrery_disabled",
            "reused_stages": ["derivation"],
        }
    )
    assert answer.trait_inputs == reconstructed["trait_inputs"] == {"derived": False}
    completed = load_genesis_run(4, answer.run)
    assert completed is not None and completed.status == "done"
    assert completed.stages["derivation"].detail["reused_from"] == seeded
