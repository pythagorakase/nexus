"""Durable genesis proofs on slot 4's disposable, migrated template clones.

Tables: genesis_runs, genesis_run_stages, assets.new_story_creator and the
world tables consumed by the real wizard mapper. No owner database is written.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
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
from tests.genesis_owner_child import BOUNDARY_TARGETS
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
    fingerprint = run["input_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert int(fingerprint, 16) >= 0
    assert run["opening_session_id"] is None
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
    overridden = load_settings()
    # The override this test depends on: Retrograde is off, derivation is on.
    assert overridden.orrery is not None and overridden.orrery.enabled is False
    assert overridden.wizard.trait_inputs.derive_at_transition

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


# -- Phase 2: replay of the real captured genesis bundle ----------------------
#
# tests/fixtures/genesis_776_real_bundle.json holds the four stage outputs one
# paid genesis run saved (tests/test_api/test_genesis_resume_live.py). Every
# provider boundary raises AssertionError("<stage> provider called") unless a
# test says otherwise; persistence and embedding run for real, embedding with
# the configured MEMNON models as tests/test_orrery/test_retrograde_embedding_pg.py
# does.

CAPTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "genesis_776_real_bundle.json"
)
CAPTURED_STAGES = ("derivation", "packet", "seed_candidates", "expansion")
# Proof parameters, not runtime settings: how long a held boundary, a child
# owner or a full persisted run may take on a loaded machine.
HOLD_SECONDS = 60
CHILD_SECONDS = 120
RUN_SECONDS = 420


class Boundaries:
    """Replace the four provider boundaries and record every call."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.calls: list[str] = []
        self._lock = threading.Lock()
        for stage in CAPTURED_STAGES:
            self.set(stage, self._refuse(stage))

    @staticmethod
    def _refuse(stage: str) -> Callable[..., Any]:
        def refuse(*args: Any, **kwargs: Any) -> None:
            raise AssertionError(f"{stage} provider called")

        return refuse

    def set(self, stage: str, replacement: Callable[..., Any]) -> None:
        """Route ``stage``'s boundary to ``replacement``, recording each call."""

        def recorded(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                self.calls.append(stage)
            return replacement(*args, **kwargs)

        self.monkeypatch.setattr(BOUNDARY_TARGETS[stage], recorded)


@pytest.fixture
def captured() -> dict[str, Any]:
    """The real bundle the live probe captured."""
    capture: dict[str, Any] = json.loads(CAPTURE_PATH.read_text())
    assert set(capture["outputs"]) == set(CAPTURED_STAGES)
    return capture


@pytest.fixture
def fingerprinted(
    staged: tuple[str, Any], monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str]:
    """Confirm the staged world and read the production fingerprint F.

    The first POST's derivation boundary raises, so its failed run carries the
    fingerprint the route computes for this world; seeded runs copy it.
    """
    dbname, _ = staged
    _confirm_staged_world(dbname)

    def stop_derivation(*args: Any, **kwargs: Any) -> None:
        raise ValueError("fingerprint probe")

    monkeypatch.setattr(BOUNDARY_TARGETS["derivation"], stop_derivation)
    with pytest.raises(HTTPException, match="fingerprint probe"):
        _post()
    first = load_genesis_run(4)
    assert first is not None and first.input_fingerprint is not None
    return dbname, first.input_fingerprint


def _post() -> Any:
    return asyncio.run(transition_to_narrative_endpoint(TransitionRequest(slot=4)))


def _seed_capture_run(
    fingerprint: str,
    capture: dict[str, Any],
    stages: tuple[str, ...],
    *,
    error: str = "ValueError: seeded failure",
    open_persistence: bool = False,
) -> str:
    """Seed a failed run through the production writers from the capture."""
    run = start_genesis_run(4)
    record_genesis_input_fingerprint(4, run, fingerprint)
    for stage in stages:
        record_retrograde_progress(4, run, stage, capture["details"][stage])
        record_genesis_stage_output(4, run, stage, capture["outputs"][stage])
    if open_persistence:
        record_retrograde_progress(4, run, "persistence", {})
    record_genesis_failure(4, run, error)
    return run


def _runs_after(seeded: str) -> list[str]:
    """Run ids (hex) started after ``seeded``, oldest first."""
    rows = _rows_query(
        "SELECT run_id::text AS run_id FROM genesis_runs WHERE started_at > "
        "(SELECT started_at FROM genesis_runs WHERE run_id = %s::uuid) "
        "ORDER BY started_at",
        (seeded,),
    )
    return [uuid.UUID(row["run_id"]).hex for row in rows]


def _rows_query(sql: str, params: Any = None) -> list[dict[str, Any]]:
    from nexus.api.slot_utils import slot_dbname

    with closing(connect(slot_dbname(4), cursor_factory=RealDictCursor)) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def _committed_summary_ids() -> list[int]:
    return [
        int(row["id"])
        for row in _rows_query("SELECT id FROM retrograde_summaries ORDER BY id")
    ]


def test_retry_resumes_saved_outputs(
    fingerprinted: tuple[str, str],
    captured: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A matching failed run's four saved outputs replace every generator."""
    _dbname, fingerprint = fingerprinted
    boundaries = Boundaries(monkeypatch)
    seeded = _seed_capture_run(fingerprint, captured, CAPTURED_STAGES)
    answer = _post()
    assert boundaries.calls == []
    assert answer.retrograde["reused_stages"] == list(CAPTURED_STAGES)
    [history] = _rows_query(
        "SELECT count(*) AS n FROM world_events WHERE source = 'retrograde'"
    )
    assert history["n"] > 0
    record = load_genesis_run(4, answer.run)
    assert record is not None and record.status == "done"
    for stage in CAPTURED_STAGES:
        row = record.stages[stage]
        assert row.detail["reused_from"] == seeded
        assert row.output == captured["outputs"][stage]
    assert answer.retrograde["embedded_summary_ids"] == _committed_summary_ids()


@pytest.mark.parametrize("change", ["weird_level", "slot_model"])
def test_changed_input_rebuilds_the_run(
    fingerprinted: tuple[str, str],
    captured: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    """Any changed whole-run input rebuilds every stage (Decision 776-Q4)."""
    from nexus.api.narrative_schemas import WeirdLevel
    from nexus.api.new_story_cache import read_cache, write_weird_level
    from nexus.api.save_slots import get_slot_model
    from nexus.config import load_settings

    dbname, fingerprint = fingerprinted
    boundaries = Boundaries(monkeypatch)
    seeded = _seed_capture_run(fingerprint, captured, CAPTURED_STAGES)
    if change == "weird_level":
        cache = read_cache(dbname)
        assert cache is not None
        levels: tuple[WeirdLevel, ...] = ("low", "medium", "high")
        level = next(level for level in levels if level != cache.weird_level)
        write_weird_level(dbname, level)
    else:
        current = get_slot_model(4, dbname=dbname)
        other = next(
            entry.id
            for provider, config in load_settings().global_.model.api_models.items()
            if provider != "test"
            for entry in config.models
            if entry.id != current and "wizard.fallback_model" in entry.uses
        )
        upsert_slot(4, model=other, dbname=dbname)

    def rebuilt(*args: Any, **kwargs: Any) -> None:
        raise ValueError("rebuilt")

    boundaries.set("derivation", rebuilt)
    with pytest.raises(HTTPException) as raised:
        _post()
    assert raised.value.status_code == 400 and raised.value.detail == "rebuilt"
    assert boundaries.calls == ["derivation"]
    [rebuild] = _runs_after(seeded)
    record = load_genesis_run(4, rebuild)
    assert record is not None and record.input_fingerprint != fingerprint
    assert all("reused_from" not in row.detail for row in record.stages.values())


def test_repeated_post_joins_the_running_run(
    fingerprinted: tuple[str, str],
    captured: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second POST while a run holds the claim joins it (Decision 776-Q5)."""
    from contextlib import contextmanager

    from nexus.agents.orrery import retrograde_orchestrator
    from tests.genesis_owner_child import capture_boundaries

    _dbname, fingerprint = fingerprinted
    boundaries = Boundaries(monkeypatch)
    replay = capture_boundaries(captured)
    # A second owner would need these; the joiner must never call them.
    for stage in ("derivation", "packet", "seed_candidates"):
        boundaries.set(stage, replay[stage])
    release, joiner_lost = threading.Event(), threading.Event()

    def held_expansion(**kwargs: Any) -> Any:
        if not release.wait(2 * HOLD_SECONDS):
            raise RuntimeError("expansion release timed out")
        return replay["expansion"](**kwargs)

    boundaries.set("expansion", held_expansion)
    real_claim = retrograde_orchestrator.genesis_slot_claim

    @contextmanager
    def observed_claim(slot: int) -> Any:
        # Only the second POST can find the claim held (the route runs each
        # POST in an executor thread, so the caller's thread name is lost).
        with real_claim(slot) as won:
            if not won:
                joiner_lost.set()
            yield won

    monkeypatch.setattr(retrograde_orchestrator, "genesis_slot_claim", observed_claim)
    seeded = _seed_capture_run(
        fingerprint, captured, ("derivation", "packet", "seed_candidates")
    )
    answers: dict[str, Any] = {}

    def post(name: str) -> None:
        try:
            answers[name] = _post()
        except Exception as exc:
            answers[name] = exc

    first = threading.Thread(target=post, args=("first",), name="first")
    second = threading.Thread(target=post, args=("second",), name="second")
    first.start()
    try:
        deadline = time.monotonic() + HOLD_SECONDS
        while time.monotonic() < deadline:
            latest = load_genesis_run(4)
            if latest is not None and latest.run != seeded:
                if "expansion" in latest.stages:
                    break
            time.sleep(0.05)
        else:
            pytest.fail("The owner never reached expansion")
        second.start()
        deadline = time.monotonic() + HOLD_SECONDS
        while time.monotonic() < deadline and not joiner_lost.is_set():
            if boundaries.calls.count("expansion") > 1:
                break
            time.sleep(0.05)
    finally:
        release.set()
        first.join(RUN_SECONDS)
        if second.is_alive() or second.ident is not None:
            second.join(RUN_SECONDS)
    assert not first.is_alive() and not second.is_alive()
    runs = _runs_after(seeded)
    assert (len(runs), boundaries.calls) == (1, ["expansion"]), (runs, answers)
    assert not isinstance(answers["first"], Exception), answers["first"]
    assert not isinstance(answers["second"], Exception), answers["second"]
    assert answers["first"] == answers["second"]
    assert runs == [answers["first"].run]


def test_stopped_owner_run_is_closed_and_resumed(
    offline_gate_db: str,
    captured: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A SIGKILLed owner's run is closed as interrupted; one POST resumes it."""
    from nexus.agents.orrery.retrograde_orchestrator import GENESIS_RUN_INTERRUPTED
    from tests.genesis_owner_child import capture_boundaries

    monkeypatch.delenv("NEXUS_RETROGRADE_WIZARD_MODEL", raising=False)
    capture_file = tmp_path / "capture.json"
    capture_file.write_text(json.dumps(captured))
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        **routed_slot_environment(4, offline_gate_db),
    }
    with (tmp_path / "owner-child.log").open("w") as output:
        child = subprocess.Popen(
            [sys.executable, "-m", "tests.genesis_owner_child", str(capture_file)],
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + CHILD_SECONDS
            owner = None
            while time.monotonic() < deadline and child.poll() is None:
                owner = load_genesis_run(4)
                if owner is not None and "expansion" in owner.stages:
                    break
                time.sleep(0.05)
            assert owner is not None and "expansion" in owner.stages, (
                tmp_path / "owner-child.log"
            ).read_text()
            child.send_signal(signal.SIGKILL)
            child.wait(timeout=CHILD_SECONDS)
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=CHILD_SECONDS)
    stopped = load_genesis_run(4, owner.run)
    assert stopped is not None and stopped.status == "running"

    boundaries = Boundaries(monkeypatch)
    boundaries.set("expansion", capture_boundaries(captured)["expansion"])
    answers: dict[str, Any] = {}

    def post(name: str) -> None:
        try:
            answers[name] = _post()
        except Exception as exc:
            answers[name] = exc

    threads = [
        threading.Thread(target=post, args=(name,), name=name)
        for name in ("one", "two")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(RUN_SECONDS)
    assert not any(thread.is_alive() for thread in threads)
    assert not isinstance(answers["one"], Exception), answers["one"]
    assert not isinstance(answers["two"], Exception), answers["two"]
    assert answers["one"] == answers["two"]
    closed = load_genesis_run(4, owner.run)
    assert closed is not None
    assert (closed.status, closed.error) == ("failed", GENESIS_RUN_INTERRUPTED)
    [resumed] = _runs_after(owner.run)
    assert resumed == answers["one"].run
    record = load_genesis_run(4, resumed)
    assert record is not None and record.status == "done"
    for stage in ("derivation", "packet", "seed_candidates"):
        assert record.stages[stage].detail["reused_from"] == owner.run
    assert "reused_from" not in record.stages["expansion"].detail
    assert boundaries.calls == ["expansion"]


def test_blocked_persistence_retry_calls_expansion_again(
    fingerprinted: tuple[str, str],
    captured: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plan whose persistence was blocked is regenerated, never reused."""
    _dbname, fingerprint = fingerprinted
    boundaries = Boundaries(monkeypatch)
    seeded = _seed_capture_run(
        fingerprint,
        captured,
        CAPTURED_STAGES,
        error="RetrogradePersistenceBlockedError: seeded block",
        open_persistence=True,
    )

    def rebuilt(**kwargs: Any) -> None:
        raise ValueError("expansion rebuilt")

    boundaries.set("expansion", rebuilt)
    with pytest.raises(HTTPException) as raised:
        _post()
    assert raised.value.status_code == 400
    assert raised.value.detail == "expansion rebuilt"
    assert boundaries.calls == ["expansion"]
    [retry] = _runs_after(seeded)
    record = load_genesis_run(4, retry)
    assert record is not None
    for stage in ("derivation", "packet", "seed_candidates"):
        assert record.stages[stage].detail["reused_from"] == seeded
    assert "reused_from" not in record.stages["expansion"].detail


def _fail_embedding_after_commit(
    fingerprint: str, captured: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> str:
    """Commit the captured world with the embedder down; return that run."""
    from nexus.agents.orrery.retrograde_orchestrator import load_genesis_run as load
    from nexus.api.new_story_cache import read_cache
    from nexus.api.slot_utils import slot_dbname

    seeded = _seed_capture_run(fingerprint, captured, CAPTURED_STAGES)
    with monkeypatch.context() as down:

        def embedder_down(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("embedder down")

        down.setattr(
            "nexus.agents.orrery.retrograde_embedding.embed_retrograde_summaries",
            embedder_down,
        )
        with pytest.raises(HTTPException) as raised:
            _post()
    assert raised.value.status_code == 500
    assert raised.value.detail == (
        "Transition failed: embedder down -- Retrograde history is committed but "
        "not yet embedded; retry the transition to finish it (the wizard's "
        "Retry, or: nexus continue --slot 4)"
    )
    assert read_cache(slot_dbname(4)) is None
    [committed] = _rows_query("SELECT user_character FROM global_variables")
    assert committed["user_character"] is not None
    [first] = _runs_after(seeded)
    record = load(4, first)
    assert record is not None and record.status == "failed"
    assert record.stages["persistence"].output["embedding_pending_summary_ids"]
    return first


def _assert_embedding_finished(answer: Any, committed_run: str) -> None:
    record = load_genesis_run(4, answer.run)
    assert record is not None and record.status == "done"
    assert record.stages["persistence"].detail["reused_from"] == committed_run
    committed = load_genesis_run(4, committed_run)
    assert committed is not None
    pending = committed.stages["persistence"].output["embedding_pending_summary_ids"]
    assert sorted(record.stages["embedding"].output) == sorted(pending)
    unstamped = _rows_query(
        "SELECT id FROM retrograde_summaries WHERE embedding_generated_at IS NULL"
    )
    assert unstamped == []
    assert sorted(answer.retrograde["embedded_summary_ids"]) == (
        _committed_summary_ids()
    )


def test_retry_after_embedding_failure_completes_from_the_run(
    fingerprinted: tuple[str, str],
    captured: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The committed world's pending embedding finishes without the cache."""
    _dbname, fingerprint = fingerprinted
    boundaries = Boundaries(monkeypatch)
    committed_run = _fail_embedding_after_commit(fingerprint, captured, monkeypatch)
    answer = _post()
    assert boundaries.calls == []
    assert answer.retrograde["reused_stages"] == [*CAPTURED_STAGES, "persistence"]
    _assert_embedding_finished(answer, committed_run)


def test_resume_that_failed_before_copying_persistence_still_finishes(
    fingerprinted: tuple[str, str],
    captured: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A resume that stopped before its persistence copy keeps its anchor."""
    from nexus.api import new_story_flow

    _dbname, fingerprint = fingerprinted
    boundaries = Boundaries(monkeypatch)
    committed_run = _fail_embedding_after_commit(fingerprint, captured, monkeypatch)
    real_copy = new_story_flow._reuse_genesis_stage

    with monkeypatch.context() as broken:

        def copy_interrupted(slot: int, run: str, prior: Any, stage: str) -> None:
            if stage == "packet":
                raise RuntimeError("copy interrupted")
            real_copy(slot, run, prior, stage)

        broken.setattr(new_story_flow, "_reuse_genesis_stage", copy_interrupted)
        with pytest.raises(HTTPException) as raised:
            _post()
    assert raised.value.status_code == 500
    assert "copy interrupted" in raised.value.detail
    stranded = load_genesis_run(4)
    assert stranded is not None and stranded.run != committed_run
    assert stranded.status == "failed" and "persistence" not in stranded.stages
    answer = _post()
    assert boundaries.calls == []
    _assert_embedding_finished(answer, committed_run)
