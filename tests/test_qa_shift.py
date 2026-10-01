"""Regression tests for the tracked adversarial QA shift utility."""

from __future__ import annotations


from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tomllib
from typing import Any, Mapping, cast

from pydantic import ValidationError
import pytest
import tomlkit

from nexus.config.settings_models import BoundaryCatchupSettings
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.contract import HOME_ENV
from scripts.qa_shift import qa_shift
from scripts.qa_shift.boundary_catchup import (
    load_config as load_boundary_catchup_config,
)


NOW = datetime(2026, 7, 30, 4, 30, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures"


def _event(
    *,
    model: str = "gpt-5.6-terra",
    provider: str = "openai",
    slot: int | None = 4,
    total: int | None = 100,
) -> dict[str, object]:
    return {
        "ts": "2026-07-30T04:31:00Z",
        "quota_day": "2026-07-30",
        "provider": provider,
        "model": model,
        "seat": "skald_single_pass",
        "slot": slot,
        "run_id": "run-one",
        "attempt": 1,
        "outcome": "accepted",
        "transport": "responses",
        "request_id": "resp-one",
        "input_tokens": None if total is None else total - 10,
        "output_tokens": None if total is None else 10,
        "total_tokens": total,
        "cached_input_tokens": None,
        "cache_creation_tokens": None,
        "reasoning_tokens": None,
        "service_tier": "default",
        "aggregate": False,
        "requests": None,
    }


def _usage(
    *,
    total: int = 100,
    unknown: int = 0,
    events: list[dict[str, object]] | None = None,
    day: str = "2026-07-30",
) -> dict[str, object]:
    return {
        "success": True,
        "usage": {
            "day": day,
            "events": events or [],
            "providers": {},
            "seats": {},
            "openai_day_total": {
                "total_tokens": total,
                "unknown_usage_events": unknown,
            },
            "allowance": {},
        },
    }


def _job(
    state: str,
    *,
    attempts: int = 1,
    queue: str = "retrograde_maturation",
    last_error: str | None = None,
) -> dict[str, object]:
    job: dict[str, object] = {
        "generation_session_id": None,
        "id": 17,
        "queue": queue,
        "state": state,
        "attempts": attempts,
        "available_at": "2026-07-30T04:31:00+00:00",
        "lease_until": ("2026-07-30T04:36:00+00:00" if state == "leased" else None),
        "last_error": last_error,
    }
    if queue == "retrograde_maturation":
        job.update(
            {
                "entity_kind": "character",
                "entity_name": "Nika Rel",
                "requesting_chunk_id": 47,
            }
        )
    elif queue == "experience_render":
        job.update(
            {
                "boundary_chunk_id": 48,
                "scene_end_chunk_id": 47,
                "batch_ordinal": 0,
                "experience_ids": [81, 82],
            }
        )
    else:
        raise ValueError(f"Unsupported fixture queue: {queue}")
    return job


def _jobs(
    *,
    state: str | None = None,
    attempts: int = 1,
    failed_jobs: int = 0,
    experience_failed_jobs: int = 0,
    queue: str = "retrograde_maturation",
    last_error: str | None = None,
) -> dict[str, object]:
    maturation_counts = {
        "queued": 0,
        "leased": 0,
        "succeeded": 0,
        "failed": failed_jobs,
    }
    experience_counts = {
        "queued": 0,
        "leased": 0,
        "succeeded": 0,
        "failed": experience_failed_jobs,
        "stale_rejected": 0,
    }
    queue_counts = (
        maturation_counts if queue == "retrograde_maturation" else experience_counts
    )
    non_terminal_jobs: list[dict[str, object]] = []
    if state is not None:
        queue_counts[state] += 1
        if state in ("queued", "leased"):
            non_terminal_jobs.append(
                _job(
                    state,
                    attempts=attempts,
                    queue=queue,
                    last_error=last_error,
                )
            )
    queues = {
        "retrograde_maturation": {
            "counts": maturation_counts,
            "non_terminal_jobs": (
                non_terminal_jobs if queue == "retrograde_maturation" else []
            ),
        },
        "experience_render": {
            "counts": experience_counts,
            "non_terminal_jobs": (
                non_terminal_jobs if queue == "experience_render" else []
            ),
        },
    }
    for name, states in qa_shift.QUEUE_STATES.items():
        if name not in queues:
            queues[name] = {"counts": dict.fromkeys(states, 0), "non_terminal_jobs": []}
    counts = {
        state: sum(q["counts"].get(state, 0) for q in queues.values())
        for state in qa_shift.SHARED_QUEUE_STATES
    }
    return {
        "success": True,
        "slot": 4,
        "queues": queues,
        "counts": counts,
        "non_terminal_jobs": sorted(
            non_terminal_jobs,
            key=lambda job: (str(job["queue"]), int(cast(int, job["id"]))),
        ),
    }


def _settled_jobs_reader(_root: Path, _slot: int) -> dict[str, object]:
    return _jobs()


def _bleed_uptake_reader(
    _root: Path,
    _slot: int,
) -> dict[str, object]:
    return {"offered_count": 4, "used_count": 1}


def _empty_bleed_uptake_reader(
    _root: Path,
    _slot: int,
) -> dict[str, object]:
    return {"offered_count": 0, "used_count": 0}


def _state(config: qa_shift.ShiftConfig) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "active",
        "started_at": "2026-07-30T04:30:00Z",
        "quota_day": "2026-07-30",
        "baseline_total": 100,
        "last_total": 100,
        "baseline_event_count": 0,
        "last_event_count": 0,
        "last_unknown_usage_events": 0,
        "baseline_failed_jobs": {
            **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
            "retrograde_maturation": 0,
            "experience_render": 0,
        },
        "checks": 0,
        "max_command_delta": 0,
        "config": qa_shift._config_payload(config),
    }


def _validation_evidence() -> qa_shift.ValidationEvidence:
    return qa_shift.ValidationEvidence(
        probe_command="poetry run nexus regenerate --slot 4 --note malformed",
        rejection_status=422,
        rejection_evidence="/archive/regenerate-note-422.json",
        rejection_evidence_sha256="a" * 64,
        rejection_evidence_excerpt='{"detail":[{"type":"string_too_long"}]}',
    )


def test_tracked_config_encodes_bounded_completion_policy() -> None:
    config = qa_shift.load_shift_config()

    assert config.slot == 4
    assert config.gateway_port == 8012
    assert config.target_model == "gpt-5.6-terra"
    assert config.issue_budget == 5
    assert config.minimum_probe_families == 5
    assert config.dry_well_families == 3
    assert config.wall_clock_minutes == 60
    assert config.daily_token_limit == 10_000_000
    assert config.reserve_tokens == 1_000_000
    assert config.token_fence == 9_000_000


def test_tracked_config_declares_boundary_catchup_skips() -> None:
    assert load_boundary_catchup_config().skip_minutes == [0, 60, 4320]
    for invalid in ([-1, 60], [0, 60, 60], [60, 0], []):
        with pytest.raises(ValidationError):
            BoundaryCatchupSettings.model_validate({"skip_minutes": invalid})
    with pytest.raises(ValidationError):
        BoundaryCatchupSettings.model_validate(
            {"skip_minutes": [0], "unexpected": True}
        )


def test_begin_creates_archive_and_pins_every_remote_model(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    result = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=123),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )

    archive = Path(result["archive"])
    state = json.loads((archive / "shift_state.json").read_text())
    document = cast(Any, tomlkit.parse((archive / "nexus.qa.toml").read_text()))
    model = document["global"]["model"]

    assert state["baseline_total"] == 123
    assert state["baseline_bleed_offered_count"] == 0
    assert state["baseline_bleed_used_count"] == 0
    assert state["status"] == "active"
    assert model["default_slot_model"] == "gpt-5.6-terra"
    assert document["apex"]["model"] == config.target_model
    assert (
        document["apex"].get("gaia_model") or document["apex"]["model"]
    ) == config.target_model
    assert document["wizard"]["fallback_model"] == config.target_model
    assert "provider" not in document["orrery"]["narration"]
    assert "model_ref" not in document["orrery"]["narration"]
    assert document["usage"]["daily_allowance"]["openai"] == 10_000_000
    assert (archive / "runtime_env.sh").exists()
    assert (archive / "probe_ledger.md").exists()
    assert (archive / "mission_report.md").exists()
    ledger = (archive / "probe_ledger.md").read_text()
    report = (archive / "mission_report.md").read_text()
    assert "## Recent coverage" in ledger
    assert "## Structured-output rejection ledger" in ledger
    assert "Repair tax" in ledger
    assert "## Structured-output rejections" in report
    assert "## Bleed uptake" in report
    assert "Repair tax" in report
    assert "Seed-promotion disposition" in report


def test_generated_runtime_environment_selects_qa_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generated shell variable selects the QA config for the supervisor."""
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    result = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=123),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(result["archive"])
    # An owner's exported runtime home must not survive into the QA lane.
    owner_home = tmp_path / "owner-home"
    owner_home.mkdir()
    sourced = subprocess.run(
        ["bash", "-c", '. "$1" && env -0', "bash", str(archive / "runtime_env.sh")],
        capture_output=True,
        check=True,
        env={"PATH": os.environ["PATH"], HOME_ENV: str(owner_home)},
    )
    environment = dict(
        item.split("=", 1) for item in sourced.stdout.decode().split("\0") if item
    )
    assert HOME_ENV not in environment
    monkeypatch.delenv(HOME_ENV, raising=False)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, environment[RUNTIME_CONFIG_ENV])

    supervisor = Supervisor.from_config()

    assert supervisor.config_path == (archive / "nexus.qa.toml").resolve()


@pytest.mark.parametrize("missing_table", ("models", "daily_allowance"))
def test_runtime_config_shape_errors_are_clean_shift_errors(
    tmp_path: Path,
    missing_table: str,
) -> None:
    repo = tmp_path / "repo"
    archive = tmp_path / "archive"
    repo.mkdir()
    archive.mkdir()
    document = cast(
        Any,
        tomlkit.parse((qa_shift.REPO_ROOT / "nexus.toml").read_text()),
    )
    if missing_table == "models":
        del document["global"]["model"]["api_models"]["openai"]["models"]
    else:
        del document["usage"]["daily_allowance"]
    (repo / "nexus.toml").write_text(tomlkit.dumps(document))

    with pytest.raises(qa_shift.ShiftError, match="Cannot derive isolated config"):
        qa_shift._write_runtime_config(
            repo_root=repo,
            archive=archive,
            config=qa_shift.load_shift_config(),
        )


MODEL_ROUTE_KEYS = {
    "compaction_model",
    "default_model",
    "default_slot_model",
    "fallback_model",
    "gaia_model",
    "model",
    "model_ref",
    "target_model",
}

DIRECTLY_PINNED_ROUTES = {
    "global.model.default_slot_model",
    "wizard.fallback_model",
}

NON_REMOTE_ROUTES = {
    "local_models.model",
}


def _collect_model_routes(table: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    routes: dict[str, str] = {}
    for key, value in table.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            routes.update(_collect_model_routes(value, path))
        elif isinstance(value, str) and key in MODEL_ROUTE_KEYS:
            routes[path] = value
    return routes


def test_every_tracked_model_route_is_pinned(tmp_path: Path) -> None:
    """An isolated QA config must not leak inference onto an unpinned model."""
    from nexus.config.settings_models import materialize_model_selections

    config = qa_shift.load_shift_config()
    path = qa_shift._write_runtime_config(
        repo_root=qa_shift.REPO_ROOT, archive=tmp_path, config=config
    )
    document = materialize_model_selections(tomllib.loads(path.read_text()))
    routes = _collect_model_routes(document)
    assert DIRECTLY_PINNED_ROUTES <= set(routes)
    for route, model in routes.items():
        if route not in NON_REMOTE_ROUTES:
            assert model == config.target_model, f"{route} escaped the QA model pin"


def test_begin_refuses_untrustworthy_or_exhausted_usage(tmp_path: Path) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)

    for payload in (
        _usage(total=100, unknown=1),
        _usage(total=config.token_fence),
    ):
        with pytest.raises(qa_shift.ShiftError):
            qa_shift.begin_shift(
                config=config,
                usage_reader=cast(
                    qa_shift.UsageReader,
                    lambda _root, _day, value=payload: value,
                ),
                jobs_reader=_settled_jobs_reader,
                now=NOW,
            )

    assert list(tmp_path.iterdir()) == []


def test_post_call_check_reports_exact_delta_and_route() -> None:
    config = qa_shift.load_shift_config()
    event = _event(total=321)

    result, updated = qa_shift.evaluate_check(
        state=_state(config),
        usage_payload=_usage(total=421, events=[event]),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.POST_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "continue"
    assert result["openai_delta_since_last_check"] == 321
    assert result["shift_openai_total"] == 321
    assert result["max_command_delta"] == 321
    assert result["qa_models_seen"] == ["gpt-5.6-terra"]
    assert result["unexpected_routes"] == []
    assert result["qa_api_calls"] == [
        {
            "request_id": "resp-one",
            "run_id": "run-one",
            "seat": "skald_single_pass",
            "provider": "openai",
            "model": "gpt-5.6-terra",
            "attempt": 1,
            "outcome": "accepted",
            "input_tokens": 311,
            "output_tokens": 10,
            "total_tokens": 321,
        }
    ]
    assert updated["last_total"] == 421


def test_post_call_check_fails_closed_on_missing_or_wrong_route() -> None:
    config = qa_shift.load_shift_config()

    missing, _ = qa_shift.evaluate_check(
        state=_state(config),
        usage_payload=_usage(total=100),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.POST_CALL,
        now=NOW + timedelta(minutes=1),
    )
    wrong, _ = qa_shift.evaluate_check(
        state=_state(config),
        usage_payload=_usage(
            total=200,
            events=[_event(model="gpt-5.6-sol")],
        ),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.POST_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert missing["status"] == "stop"
    assert "expected_usage_event_missing" in missing["reasons"]
    assert wrong["status"] == "stop"
    assert "unexpected_qa_model_route" in wrong["reasons"]


@pytest.mark.parametrize(
    ("fixture_name", "probe_command"),
    (
        (
            "qa_shift_regenerate_note_too_long_422.json",
            "poetry run nexus regenerate --slot 4 --note <501-character-note>",
        ),
        (
            "qa_shift_invalid_model_422.json",
            "curl -X POST http://127.0.0.1:8012/api/narrative/continue "
            '-d \'{"slot":4,"model":"gpt-malformed"}\'',
        ),
    ),
)
def test_validation_only_check_persists_rejection_evidence_and_continues(
    tmp_path: Path,
    fixture_name: str,
    probe_command: str,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    evidence = archive / fixture_name
    evidence.write_bytes((FIXTURES / fixture_name).read_bytes())

    result = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.VALIDATION_ONLY,
        probe_command=probe_command,
        rejection_status=422,
        rejection_evidence=evidence,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        now=NOW + timedelta(minutes=1),
    )

    state = json.loads((archive / "shift_state.json").read_text())
    checks = [
        json.loads(line)
        for line in (archive / "usage_checks.jsonl").read_text().splitlines()
    ]
    record = checks[-1]
    evidence_bytes = evidence.read_bytes()
    evidence_text = evidence_bytes.decode("utf-8")
    assert result["status"] == "continue"
    assert result["reasons"] == []
    assert record["kind"] == "validation_only"
    assert record["probe_command"] == probe_command
    assert record["rejection_status"] == 422
    assert record["rejection_evidence"] == str(evidence.resolve())
    assert (
        record["rejection_evidence_sha256"]
        == hashlib.sha256(evidence_bytes).hexdigest()
    )
    assert record["rejection_evidence_excerpt"] == evidence_text[:500]
    assert len(record["rejection_evidence_excerpt"]) <= 500
    assert record["observed_token_delta"] == 0
    assert record["observed_new_usage_events"] == 0
    assert record["observed_qa_usage_events"] == 0
    assert record["disposition"] == "continue"
    assert state["last_total"] == 100
    assert state["last_event_count"] == 0
    assert state["checks"] == 1


def test_validation_only_stops_on_zero_token_event_outside_qa_slot(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    poisoned_begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    poisoned_archive = Path(poisoned_begin["archive"])
    poisoned_evidence = poisoned_archive / "regenerate-note-422.json"
    poisoned_evidence.write_bytes(
        (FIXTURES / "qa_shift_regenerate_note_too_long_422.json").read_bytes()
    )
    other_slot_event = {
        **_event(slot=3, total=10),
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    poisoned = qa_shift.check_shift(
        archive=poisoned_archive,
        mode=qa_shift.CheckMode.VALIDATION_ONLY,
        probe_command="poetry run nexus regenerate --slot 4 --note malformed",
        rejection_status=422,
        rejection_evidence=poisoned_evidence,
        usage_reader=lambda _root, _day: _usage(
            total=100,
            events=[other_slot_event],
        ),
        jobs_reader=_settled_jobs_reader,
        now=NOW + timedelta(minutes=1),
    )

    poisoned_record = json.loads(
        (poisoned_archive / "usage_checks.jsonl").read_text().splitlines()[-1]
    )
    assert poisoned["status"] == "stop"
    assert "usage_present_for_validation_only" in poisoned["reasons"]
    assert poisoned_record["observed_new_usage_events"] == 1
    assert poisoned_record["observed_qa_usage_events"] == 0
    assert poisoned_record["observed_token_delta"] == 0
    assert poisoned_record["disposition"] == "stop"

    quiet_begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW + timedelta(seconds=1),
    )
    quiet_archive = Path(quiet_begin["archive"])
    quiet_evidence = quiet_archive / "regenerate-note-422.json"
    quiet_evidence.write_bytes(poisoned_evidence.read_bytes())

    quiet = qa_shift.check_shift(
        archive=quiet_archive,
        mode=qa_shift.CheckMode.VALIDATION_ONLY,
        probe_command="poetry run nexus regenerate --slot 4 --note malformed",
        rejection_status=422,
        rejection_evidence=quiet_evidence,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        now=NOW + timedelta(minutes=1, seconds=1),
    )

    quiet_record = json.loads(
        (quiet_archive / "usage_checks.jsonl").read_text().splitlines()[-1]
    )
    assert quiet["status"] == "continue"
    assert quiet["reasons"] == []
    assert quiet_record["observed_new_usage_events"] == 0
    assert quiet_record["observed_qa_usage_events"] == 0
    assert quiet_record["observed_token_delta"] == 0
    assert quiet_record["disposition"] == "continue"


def test_validation_only_check_stops_when_qa_usage_appears() -> None:
    zero_token_event = {
        **_event(total=10),
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    result, _ = qa_shift.evaluate_check(
        state=_state(qa_shift.load_shift_config()),
        usage_payload=_usage(total=100, events=[zero_token_event]),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.VALIDATION_ONLY,
        validation_evidence=_validation_evidence(),
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "stop"
    assert result["reasons"] == ["usage_present_for_validation_only"]
    assert result["observed_token_delta"] == 0
    assert result["observed_new_usage_events"] == 1
    assert result["observed_qa_usage_events"] == 1
    assert result["disposition"] == "stop"


def test_validation_only_check_stops_on_nonzero_delta_without_qa_event() -> None:
    result, _ = qa_shift.evaluate_check(
        state=_state(qa_shift.load_shift_config()),
        usage_payload=_usage(total=125),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.VALIDATION_ONLY,
        validation_evidence=_validation_evidence(),
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "stop"
    assert result["reasons"] == ["usage_present_for_validation_only"]
    assert result["observed_token_delta"] == 25
    assert result["observed_qa_usage_events"] == 0


def test_validation_only_pending_preserves_watermark_and_evidence(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    evidence = archive / "regenerate-note-422.json"
    evidence.write_bytes(
        (FIXTURES / "qa_shift_regenerate_note_too_long_422.json").read_bytes()
    )
    state_before = (archive / "shift_state.json").read_bytes()

    result = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.VALIDATION_ONLY,
        probe_command="poetry run nexus regenerate --slot 4 --note malformed",
        rejection_status=422,
        rejection_evidence=evidence,
        usage_reader=lambda _root, _day: _usage(total=125),
        jobs_reader=lambda _root, _slot: _jobs(state="leased"),
        now=NOW + timedelta(minutes=1),
    )

    state_after = (archive / "shift_state.json").read_bytes()
    record = json.loads((archive / "usage_checks.jsonl").read_text().splitlines()[-1])
    assert result["status"] == "pending"
    assert result["reasons"] == []
    assert result["openai_delta_since_last_check"] == 25
    assert state_after == state_before
    assert record["kind"] == "validation_only"
    assert record["disposition"] == "pending"
    assert record["observed_token_delta"] == 25
    assert record["non_terminal_jobs"] == [_job("leased")]


def test_missing_validation_evidence_is_loud_without_state_mutation(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    state_before = (archive / "shift_state.json").read_bytes()
    checks_before = (archive / "usage_checks.jsonl").read_bytes()

    with pytest.raises(qa_shift.ShiftError, match="Cannot read rejection evidence"):
        qa_shift.check_shift(
            archive=archive,
            mode=qa_shift.CheckMode.VALIDATION_ONLY,
            probe_command="poetry run nexus regenerate --slot 4 --note malformed",
            rejection_status=422,
            rejection_evidence=archive / "missing-response.json",
            usage_reader=lambda _root, _day: pytest.fail("usage reader was called"),
            jobs_reader=lambda _root, _slot: pytest.fail("jobs reader was called"),
            now=NOW + timedelta(minutes=1),
        )

    assert (archive / "shift_state.json").read_bytes() == state_before
    assert (archive / "usage_checks.jsonl").read_bytes() == checks_before


def test_validation_evidence_flags_without_mode_are_loud(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = qa_shift.main(
        [
            "check",
            str(tmp_path),
            "--probe-command",
            "poetry run nexus regenerate --slot 4 --note malformed",
        ]
    )

    assert exit_code == 1
    error = json.loads(capsys.readouterr().out)
    assert error["status"] == "error"
    assert "require --expect-validation-only" in error["error"]


def test_validation_only_mode_requires_all_evidence_flags(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = qa_shift.main(["check", str(tmp_path), "--expect-validation-only"])

    assert exit_code == 1
    error = json.loads(capsys.readouterr().out)
    assert error["status"] == "error"
    assert "requires --probe-command" in error["error"]


def test_check_modes_are_mutually_exclusive_at_argparse_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        qa_shift.main(
            [
                "check",
                str(tmp_path),
                "--expect-call",
                "--expect-validation-only",
            ]
        )

    assert exc_info.value.code == 2
    assert "not allowed with argument --expect-call" in capsys.readouterr().err


def test_queued_experience_job_is_pending_without_advancing_state() -> None:
    config = qa_shift.load_shift_config()
    state = _state(config)
    state["max_command_delta"] = 77

    result, updated = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100),
        jobs_payload=_jobs(state="queued", queue="experience_render"),
        mode=qa_shift.CheckMode.POST_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "pending"
    assert result["reasons"] == []
    assert "expected_usage_event_missing" not in result["reasons"]
    assert result["non_terminal_jobs"] == [_job("queued", queue="experience_render")]
    assert result["max_command_delta"] == 77
    assert updated == state
    assert updated["last_total"] == 100
    assert updated["last_event_count"] == 0
    assert updated["max_command_delta"] == 77


def test_pending_post_check_retains_late_usage_in_causal_command_delta(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    sync_events = [
        {**_event(total=200), "seat": "skald_writer", "request_id": "writer"},
        {
            **_event(total=100),
            "seat": "experience_seed_formation",
            "request_id": "experience-formation",
        },
    ]
    late_event = {
        **_event(total=50),
        "seat": "experience_renderer",
        "request_id": "late-experience-renderer",
    }

    pre = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.PRE_CALL,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        now=NOW + timedelta(seconds=1),
    )
    pending = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.POST_CALL,
        usage_reader=lambda _root, _day: _usage(total=400, events=sync_events),
        jobs_reader=lambda _root, _slot: _jobs(
            state="leased", queue="experience_render"
        ),
        now=NOW + timedelta(seconds=2),
    )
    pending_state = json.loads((archive / "shift_state.json").read_text())
    settled = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.POST_CALL,
        usage_reader=lambda _root, _day: _usage(
            total=450,
            events=[*sync_events, late_event],
        ),
        jobs_reader=_settled_jobs_reader,
        now=NOW + timedelta(seconds=12),
    )
    final_state = json.loads((archive / "shift_state.json").read_text())

    assert pre["status"] == "continue"
    assert pending["status"] == "pending"
    assert pending["openai_delta_since_last_check"] == 300
    assert pending_state["last_total"] == 100
    assert pending_state["last_event_count"] == 0
    assert pending_state["max_command_delta"] == 0
    assert settled["status"] == "continue"
    assert settled["openai_delta_since_last_check"] == 350
    assert settled["new_usage_events"] == 3
    assert settled["max_command_delta"] == 350
    assert {call["seat"] for call in settled["qa_api_calls"]} == {
        "skald_writer",
        "experience_seed_formation",
        "experience_renderer",
    }
    assert final_state["last_total"] == 450
    assert final_state["last_event_count"] == 3
    assert final_state["max_command_delta"] == 350
    checks = [
        json.loads(line)
        for line in (archive / "usage_checks.jsonl").read_text().splitlines()
    ]
    assert checks[2]["status"] == "pending"
    assert checks[2]["non_terminal_jobs"] == [_job("leased", queue="experience_render")]


def test_failure_during_pending_stops_after_settlement_with_full_delta(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    synchronous_event = {
        **_event(total=200),
        "seat": "skald_writer",
        "request_id": "writer-before-failure",
    }
    late_event = {
        **_event(total=50),
        "seat": "retrograde_expansion",
        "request_id": "late-before-failure",
    }

    pending = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.POST_CALL,
        usage_reader=lambda _root, _day: _usage(
            total=300,
            events=[synchronous_event],
        ),
        jobs_reader=lambda _root, _slot: _jobs(
            state="leased",
            failed_jobs=1,
        ),
        now=NOW + timedelta(seconds=2),
    )
    pending_state = json.loads((archive / "shift_state.json").read_text())
    settled = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.POST_CALL,
        usage_reader=lambda _root, _day: _usage(
            total=350,
            events=[synchronous_event, late_event],
        ),
        jobs_reader=lambda _root, _slot: _jobs(failed_jobs=1),
        now=NOW + timedelta(seconds=12),
    )

    assert pending["status"] == "pending"
    assert pending["reasons"] == []
    assert pending["current_failed_jobs"] == {
        **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
        "retrograde_maturation": 1,
        "experience_render": 0,
    }
    assert pending_state["last_total"] == 100
    assert pending_state["last_event_count"] == 0
    assert pending_state["max_command_delta"] == 0
    assert settled["status"] == "stop"
    assert "maturation_job_failed" in settled["reasons"]
    assert settled["openai_delta_since_last_check"] == 250
    assert settled["new_usage_events"] == 2
    assert settled["max_command_delta"] == 250


def test_check_reads_queue_before_usage_to_close_settlement_race(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    calls: list[str] = []

    def read_jobs(_root: Path, _slot: int) -> dict[str, object]:
        calls.append("jobs")
        return _jobs()

    def read_usage(_root: Path, _day: str | None) -> dict[str, object]:
        calls.append("usage")
        return _usage(total=100)

    result = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.PRE_CALL,
        jobs_reader=read_jobs,
        usage_reader=read_usage,
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "continue"
    assert calls == ["jobs", "usage"]


@pytest.mark.parametrize(
    ("state", "attempts", "expected_status"),
    (
        ("queued", 1, "pending"),
        ("leased", 1, "pending"),
        ("succeeded", 1, "continue"),
        ("failed", 3, "continue"),
    ),
)
def test_only_non_terminal_maturation_states_block_checks(
    state: str,
    attempts: int,
    expected_status: str,
) -> None:
    shift_state = _state(qa_shift.load_shift_config())
    if state == "failed":
        shift_state["baseline_failed_jobs"] = {
            **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
            "retrograde_maturation": 1,
            "experience_render": 0,
        }
    result, _ = qa_shift.evaluate_check(
        state=shift_state,
        usage_payload=_usage(total=100),
        jobs_payload=_jobs(state=state, attempts=attempts),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == expected_status


def test_requeued_experience_job_stops_with_last_error() -> None:
    state = _state(qa_shift.load_shift_config())
    result, updated = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100),
        jobs_payload=_jobs(
            state="queued",
            attempts=2,
            queue="experience_render",
            last_error="invented entity: Sitting",
        ),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "stop"
    assert result["reasons"] == ["job_requeued:experience_render:17"]
    assert result["non_terminal_jobs"][0]["last_error"] == ("invented entity: Sitting")
    # Sol review (PR #738): a stop records the watermark like every other stop.
    assert updated["last_total"] == 100
    assert updated["last_event_count"] == 0
    assert updated["checks"] == int(state["checks"]) + 1


def test_leased_retry_stays_pending_until_its_call_settles() -> None:
    """A leased retry may be inside its provider call; it must hold pending."""
    state = _state(qa_shift.load_shift_config())
    state["max_command_delta"] = 77
    result, updated = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100),
        jobs_payload=_jobs(
            state="leased",
            attempts=2,
            queue="experience_render",
            last_error="invented entity: Sitting",
        ),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "pending"
    assert result["reasons"] == []
    assert result["requeued_jobs"] == []
    assert result["max_command_delta"] == 77
    assert updated == state


def test_unknown_queue_kind_fails_closed() -> None:
    payload = json.loads(json.dumps(_jobs()))
    payload["queues"]["unknown_provider_queue"] = {
        "counts": {},
        "non_terminal_jobs": [],
    }

    with pytest.raises(qa_shift.ShiftError, match="queue kinds must be exactly"):
        qa_shift._jobs_snapshot(payload, slot=4)


def test_aggregate_and_per_queue_mismatch_fails_closed() -> None:
    payload = json.loads(json.dumps(_jobs()))
    payload["counts"]["queued"] = 1

    with pytest.raises(qa_shift.ShiftError, match="aggregate counts"):
        qa_shift._jobs_snapshot(payload, slot=4)


def test_new_terminal_maturation_failure_stops_settled_check() -> None:
    result, _ = qa_shift.evaluate_check(
        state=_state(qa_shift.load_shift_config()),
        usage_payload=_usage(total=100),
        jobs_payload=_jobs(failed_jobs=1),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "stop"
    assert "maturation_job_failed" in result["reasons"]
    assert result["baseline_failed_jobs"] == {
        **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
        "retrograde_maturation": 0,
        "experience_render": 0,
    }
    assert result["current_failed_jobs"] == {
        **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
        "retrograde_maturation": 1,
        "experience_render": 0,
    }


def test_new_terminal_experience_failure_stops_settled_check() -> None:
    result, _ = qa_shift.evaluate_check(
        state=_state(qa_shift.load_shift_config()),
        usage_payload=_usage(total=100),
        jobs_payload=_jobs(experience_failed_jobs=1),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert result["status"] == "stop"
    assert "experience_job_failed" in result["reasons"]


def test_preexisting_failed_jobs_become_shift_baseline(tmp_path: Path) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=lambda _root, _slot: _jobs(failed_jobs=2),
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    state = json.loads((archive / "shift_state.json").read_text())

    check = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.PRE_CALL,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=lambda _root, _slot: _jobs(failed_jobs=2),
        now=NOW + timedelta(minutes=1),
    )

    assert state["baseline_failed_jobs"] == {
        **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
        "retrograde_maturation": 2,
        "experience_render": 0,
    }
    assert check["status"] == "continue"
    assert "maturation_job_failed" not in check["reasons"]
    assert check["baseline_failed_jobs"] == {
        **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
        "retrograde_maturation": 2,
        "experience_render": 0,
    }
    assert check["current_failed_jobs"] == {
        **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
        "retrograde_maturation": 2,
        "experience_render": 0,
    }


def test_begin_refuses_dirty_maturation_queue(tmp_path: Path) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    usage_read = False

    def read_usage(_root: Path, _day: str | None) -> dict[str, object]:
        nonlocal usage_read
        usage_read = True
        return _usage(total=100)

    with pytest.raises(
        qa_shift.ShiftError,
        match=r"cannot begin.*Nika Rel",
    ):
        qa_shift.begin_shift(
            config=config,
            usage_reader=read_usage,
            jobs_reader=lambda _root, _slot: _jobs(state="queued", attempts=2),
            now=NOW,
        )

    assert usage_read is False
    assert list(tmp_path.iterdir()) == []


def test_begin_refuses_dirty_experience_queue(tmp_path: Path) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)

    with pytest.raises(
        qa_shift.ShiftError,
        match=r"cannot begin.*experience_render",
    ):
        qa_shift.begin_shift(
            config=config,
            usage_reader=lambda _root, _day: pytest.fail("usage reader was called"),
            jobs_reader=lambda _root, _slot: _jobs(
                state="queued", queue="experience_render"
            ),
            now=NOW,
        )


def test_check_fails_closed_at_token_time_day_and_unknown_boundaries() -> None:
    config = qa_shift.load_shift_config()
    state = _state(config)

    fenced, _ = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=9_000_000),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=1),
    )
    timed, _ = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=60),
    )
    rolled, rolled_state = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100, day="2026-07-31"),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=1),
    )
    unknown, _ = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100, unknown=1),
        jobs_payload=_jobs(),
        mode=qa_shift.CheckMode.PRE_CALL,
        now=NOW + timedelta(minutes=1),
    )

    assert "token_fence_reached" in fenced["reasons"]
    assert "wall_clock_reached" in timed["reasons"]
    assert "quota_day_changed" in rolled["reasons"]
    assert rolled["shift_openai_total"] is None
    assert rolled["openai_delta_since_last_check"] is None
    assert rolled_state["last_total"] == 100
    assert rolled_state["rollover_day"] == "2026-07-31"
    assert "unknown_openai_usage" in unknown["reasons"]


def test_check_and_finish_persist_end_to_end_tally(tmp_path: Path) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    first_event = _event(total=200)

    check = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.POST_CALL,
        usage_reader=lambda _root, _day: _usage(total=300, events=[first_event]),
        jobs_reader=_settled_jobs_reader,
        now=NOW + timedelta(minutes=1),
    )
    finish = qa_shift.finish_shift(
        archive=archive,
        exit_condition="dry_well",
        usage_reader=lambda _root, _day: _usage(total=350, events=[first_event]),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_bleed_uptake_reader,
        now=NOW + timedelta(minutes=2),
    )

    state = json.loads((archive / "shift_state.json").read_text())
    checks = [
        json.loads(line)
        for line in (archive / "usage_checks.jsonl").read_text().splitlines()
    ]
    assert check["openai_delta_since_last_check"] == 200
    assert finish["shift_openai_total"] == 250
    assert finish["max_command_delta"] == 200
    assert state["status"] == "finished"
    assert state["exit_condition"] == "dry_well"
    assert (archive / "usage_end.json").exists()
    assert (archive / "rejection_ledger.json").exists()
    assert (archive / "bleed_uptake.json").exists()
    assert finish["bleed_uptake"]["offered_count"] == 4
    assert finish["bleed_uptake"]["used_count"] == 1
    assert finish["bleed_uptake"]["uptake_rate_percent"] == 25.0
    assert finish["rejected_attempts"] == 0
    assert finish["repair_tax_tokens"] == 0
    assert finish["repair_tax_percent"] == 0.0
    assert finish["repair_tax_percent_unavailable_reasons"] == []
    assert finish["skald_writer_tripwire"] is False
    assert [entry["kind"] for entry in checks] == [
        "begin",
        "post_call",
        "finish",
    ]


def test_finish_persists_exact_repair_tax_and_writer_tripwire(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    historical_rejection = {
        **_event(total=999),
        "seat": "gaia",
        "outcome": "rejected_validation",
        "request_id": "resp-before-shift",
    }
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(
            total=100,
            events=[historical_rejection],
        ),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    writer_rejection = {
        **_event(total=75),
        "seat": "skald_writer",
        "outcome": "rejected_validation",
        "request_id": "resp-rejected",
    }
    accepted_retry = {
        **_event(total=225),
        "seat": "skald_writer",
        "attempt": 2,
        "request_id": "resp-accepted",
    }

    finish = qa_shift.finish_shift(
        archive=archive,
        exit_condition="dry_well",
        usage_reader=lambda _root, _day: _usage(
            total=400,
            events=[historical_rejection, writer_rejection, accepted_retry],
        ),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_bleed_uptake_reader,
        now=NOW + timedelta(minutes=2),
    )
    ledger = json.loads((archive / "rejection_ledger.json").read_text())

    assert finish["shift_openai_total"] == 300
    assert finish["rejected_attempts"] == 1
    assert finish["repair_tax_tokens"] == 75
    assert finish["repair_tax_percent"] == 25.0
    assert finish["repair_tax_percent_unavailable_reasons"] == []
    assert finish["skald_writer_tripwire"] is True
    assert ledger["by_seat"] == [
        {
            "attempts": 1,
            "seat": "skald_writer",
            "tokens": 75,
            "unknown_token_events": 0,
        }
    ]
    assert ledger["rejections"] == [
        {
            "attempt": 1,
            "model": "gpt-5.6-terra",
            "provider": "openai",
            "request_id": "resp-rejected",
            "run_id": "run-one",
            "seat": "skald_writer",
            "total_tokens": 75,
            "ts": "2026-07-30T04:31:00Z",
        }
    ]


@pytest.mark.parametrize(
    ("provider", "unknown_usage", "reason"),
    (
        ("anthropic", 0, "unexpected_rejection_provider"),
        ("openai", 1, "unknown_openai_usage"),
    ),
)
def test_finish_withholds_repair_tax_percent_for_untrusted_denominator(
    tmp_path: Path,
    provider: str,
    unknown_usage: int,
    reason: str,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])
    rejection = {
        **_event(total=50, provider=provider),
        "outcome": "rejected_validation",
    }

    finish = qa_shift.finish_shift(
        archive=archive,
        exit_condition="blocked",
        usage_reader=lambda _root, _day: _usage(
            total=150,
            unknown=unknown_usage,
            events=[rejection],
        ),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_bleed_uptake_reader,
        now=NOW + timedelta(minutes=2),
    )
    ledger = json.loads((archive / "rejection_ledger.json").read_text())

    assert finish["repair_tax_tokens"] == 50
    assert finish["repair_tax_percent"] is None
    assert finish["repair_tax_percent_unavailable_reasons"] == [reason]
    assert ledger["repair_tax_percent_of_shift"] is None
    assert ledger["repair_tax_percent_unavailable_reasons"] == [reason]


def test_finish_reads_original_quota_day_after_rollover(tmp_path: Path) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])

    rollover = qa_shift.check_shift(
        archive=archive,
        mode=qa_shift.CheckMode.PRE_CALL,
        usage_reader=lambda _root, _day: _usage(
            total=40,
            day="2026-07-31",
        ),
        jobs_reader=_settled_jobs_reader,
        now=datetime(2026, 7, 31, 0, 1, tzinfo=timezone.utc),
    )
    requested_days: list[str | None] = []

    def read_original_day(_root: Path, day: str | None) -> dict[str, object]:
        requested_days.append(day)
        return _usage(total=350, day="2026-07-30")

    finish = qa_shift.finish_shift(
        archive=archive,
        exit_condition="token_fence",
        usage_reader=read_original_day,
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_bleed_uptake_reader,
        now=datetime(2026, 7, 31, 0, 2, tzinfo=timezone.utc),
    )
    state = json.loads((archive / "shift_state.json").read_text())

    assert rollover["status"] == "stop"
    assert "quota_day_changed" in rollover["reasons"]
    assert requested_days == ["2026-07-30"]
    assert finish["quota_day"] == "2026-07-30"
    assert finish["shift_openai_total"] == 250
    assert state["final_usage_day"] == "2026-07-30"
    assert state["finished_after_quota_rollover"] is True


@pytest.mark.parametrize(
    ("job_state", "usage_settled"),
    ((None, True), ("leased", False)),
)
def test_finish_reports_maturation_settlement_without_refusal(
    tmp_path: Path,
    job_state: str | None,
    usage_settled: bool,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])

    finish = qa_shift.finish_shift(
        archive=archive,
        exit_condition="blocked",
        usage_reader=lambda _root, _day: _usage(total=125),
        jobs_reader=lambda _root, _slot: _jobs(state=job_state),
        bleed_uptake_reader=_bleed_uptake_reader,
        now=NOW + timedelta(minutes=1),
    )
    final_state = json.loads((archive / "shift_state.json").read_text())

    assert finish["status"] == "finished"
    assert finish["usage_settled"] is usage_settled
    assert finish["jobs"]["non_terminal_jobs"] == (
        [] if job_state is None else [_job("leased")]
    )
    assert final_state["usage_settled"] is usage_settled


def test_finish_marks_new_maturation_failure_unsettled(tmp_path: Path) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=lambda _root, _slot: _jobs(failed_jobs=1),
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )
    archive = Path(begin["archive"])

    finish = qa_shift.finish_shift(
        archive=archive,
        exit_condition="blocked",
        usage_reader=lambda _root, _day: _usage(total=125),
        jobs_reader=lambda _root, _slot: _jobs(failed_jobs=2),
        bleed_uptake_reader=_bleed_uptake_reader,
        now=NOW + timedelta(minutes=1),
    )

    assert finish["status"] == "finished"
    assert finish["usage_settled"] is False
    assert finish["baseline_failed_jobs"] == {
        **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
        "retrograde_maturation": 1,
        "experience_render": 0,
    }
    assert finish["current_failed_jobs"] == {
        **dict.fromkeys(qa_shift.QUEUE_STATES, 0),
        "retrograde_maturation": 2,
        "experience_render": 0,
    }


def test_finish_reports_usage_unsettled_for_experience_queue(
    tmp_path: Path,
) -> None:
    config = replace(qa_shift.load_shift_config(), archive_root=tmp_path)
    begin = qa_shift.begin_shift(
        config=config,
        usage_reader=lambda _root, _day: _usage(total=100),
        jobs_reader=_settled_jobs_reader,
        bleed_uptake_reader=_empty_bleed_uptake_reader,
        now=NOW,
    )

    finish = qa_shift.finish_shift(
        archive=Path(begin["archive"]),
        exit_condition="blocked",
        usage_reader=lambda _root, _day: _usage(total=125),
        jobs_reader=lambda _root, _slot: _jobs(
            state="leased", queue="experience_render"
        ),
        bleed_uptake_reader=_bleed_uptake_reader,
        now=NOW + timedelta(minutes=1),
    )

    assert finish["usage_settled"] is False
    assert finish["jobs"]["non_terminal_jobs"] == [
        _job("leased", queue="experience_render")
    ]


def test_pending_check_exit_code_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        qa_shift,
        "check_shift",
        lambda **_kwargs: {"status": "pending"},
    )

    assert qa_shift.main(["check", str(tmp_path)]) == qa_shift.PENDING_EXIT_CODE == 3
    assert json.loads(capsys.readouterr().out) == {"status": "pending"}


# 778-S4a: all PostgreSQL state belongs to qa640_778s4a_* clones. Requires
# global_variables, narrative_chunks, chunk_metadata, orrery_resolutions, and
# the production commit path's event/adjudication tables. Clones are dropped.
def test_cooldown_inventory_covers_every_tick_gate() -> None:
    """An independent whole-file AST census checks every occurrence and argument."""
    import ast
    from collections import Counter

    from scripts.qa_shift import cooldown_calibration as calibration

    rows = calibration.inventory()
    kinds = {
        "since_last_event_at_least",
        "count_recent_events_at_least",
        "knows_recent_event",
        "recent_event",
    }
    tree = ast.parse(calibration.SOURCE.read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in kinds
    ]
    assert Counter((r["predicate"], r["source_line"]) for r in rows) == Counter(
        (cast(ast.Name, node.func).id, node.lineno) for node in calls
    )
    indexed = {r["source_line"]: r for r in rows}
    for node in calls:
        row = indexed[node.lineno]
        keyword = {kw.arg: kw.value for kw in node.keywords}
        assert row["event_type"] == ast.literal_eval(node.args[0])
        tick_key = (
            "minimum_ticks"
            if row["predicate"] == "since_last_event_at_least"
            else "within_ticks"
        )
        tick_node = keyword.get(tick_key)
        if tick_node is None and len(node.args) > 1:
            tick_node = node.args[1]
        assert row["tick_parameter"] == tick_key
        assert row["ticks"] == (ast.literal_eval(tick_node) if tick_node else 5)
        assert row["minimum_count"] == (
            ast.literal_eval(keyword["min_count"]) if "min_count" in keyword else None
        )
        for scope in ("actor", "target"):
            scope_node = keyword.get(scope + "_slot")
            expected = (
                "actor"
                if scope == "actor"
                and row["predicate"]
                in {"since_last_event_at_least", "count_recent_events_at_least"}
                else None
            )
            if scope_node is not None:
                assert isinstance(scope_node, ast.Attribute)
                expected = scope_node.attr.lower()
            assert row[scope + "_scope"] == expected
    assert len({row["gate_name"] for row in rows}) == len(calls)


def test_cooldown_gate_names_preserve_scope_and_classification() -> None:
    """Named policies preserve branch, NOT/OR paths, target scope, and purpose."""
    from scripts.qa_shift.cooldown_calibration import inventory

    rows = inventory()
    indexed = {r["gate_name"]: r for r in rows}
    assert indexed["mourn_loss/branches[0].conditions/root"]["predicate"] == (
        "count_recent_events_at_least"
    )
    assert indexed["mourn_loss/package_gate/2"]["event_type"] == "mourning_completed"
    assert (
        indexed["start_relocation_plan/package_gate/5/0"]["event_type"] == "upkeep_done"
    )
    hunt = [r for r in rows if r["event_type"] == "hunt_declared"]
    intel = [r for r in rows if r["event_type"] == "intel_acquired"]
    assert len(hunt) == len(intel) == 2
    assert len({r["gate_name"] for r in hunt + intel}) == 4
    assert {r["scope"] for r in hunt} == {"package_gate", "branches[0].conditions"}
    assert {r["scope"] for r in intel} == {"package_gate", "branches[0].conditions"}
    assert {r["target_scope"] for r in hunt} == {None, "target"}
    assert {r["target_scope"] for r in intel} == {"target"}
    paced = {
        "train/package_gate/3",
        "run_errands/package_gate/2",
        "stroll/package_gate/1",
        "upkeep/package_gate/1",
        "recreate/package_gate/2",
        "mourn_loss/package_gate/2",
    }
    assert {
        r["gate_name"] for r in rows if r["classification"] == "turn-cadenced"
    } == paced
    assert all(
        r["classification"] == "diegetic" for r in rows if r["gate_name"] not in paced
    )
    assert all(r["purpose"] and r["evidence"] for r in rows)
    assert "pacing comment" in indexed["mourn_loss/package_gate/2"]["purpose"]


def test_cooldown_calibration_sql_is_select_only() -> None:
    """Every issued statement is literal SELECT SQL with explicit protection checks."""
    import ast
    import inspect

    from scripts.qa_shift import cooldown_calibration as calibration

    tree = ast.parse(inspect.getsource(calibration))
    statements = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        assert node.func.attr not in {
            "executemany",
            "callproc",
            "copy_expert",
            "copy_from",
        }
        if node.func.attr == "execute":
            statement = ast.literal_eval(node.args[0])
            assert statement.strip().upper().startswith("SELECT ")
            assert ";" not in statement
            statements.append(statement)
    assert len(statements) == 6
    sql = "\n".join(statements)
    assert "current_database()" in sql
    assert "current_setting('transaction_read_only')" in sql
    assert "current_setting('transaction_isolation')" in sql
    assert "narrative_view" not in sql
    assert "set_config" not in sql


@pytest.fixture()
def cooldown_db() -> Any:
    """Seed clocks before chunks and use the production metadata writer on a clone."""
    from contextlib import closing

    from nexus.api.commit_handler_sync import insert_chunk_metadata_sync
    from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist

    with disposable_slot_database("qa640_778s4a_tests") as dbname:
        _, actor = seed_protagonist(dbname, base_timestamp=NOW.isoformat())
        ids = []
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("INSERT INTO seasons (id) VALUES (1)")
            cur.execute("INSERT INTO episodes (season, episode) VALUES (1, 1)")
            for scene, (layer, minutes) in enumerate(
                [("primary", 0), ("primary", None), ("flashback", 7), ("primary", 2)],
                1,
            ):
                cur.execute(
                    "INSERT INTO narrative_chunks (raw_text) VALUES (%s) RETURNING id",
                    (f"Cooldown evidence {scene}",),
                )
                chunk = cur.fetchone()[0]
                ids.append(chunk)
                insert_chunk_metadata_sync(
                    cur,
                    chunk_id=chunk,
                    season=1,
                    episode=1,
                    scene=scene,
                    world_layer=layer,
                    time_delta=(
                        timedelta(minutes=minutes) if minutes is not None else None
                    ),
                    generation_date=NOW,
                    slug=f"S01E01_{scene:03d}",
                    generation_model=None,
                    scene_weather=None,
                )
        yield dbname, ids, actor


@pytest.mark.requires_postgres
def test_cooldown_connection_rejects_writes(
    cooldown_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real read-only transactions reject INSERT even with hostile ambient options."""
    import psycopg2.errors

    from scripts.qa_shift.cooldown_calibration import readonly_connection

    dbname, _, _ = cooldown_db
    monkeypatch.setenv(
        "PGOPTIONS",
        "-c default_transaction_read_only=off"
        " -c default_transaction_isolation=read\\ committed -c statement_timeout=12345",
    )
    with readonly_connection(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT current_database() AS db, "
            "current_setting('transaction_read_only') AS ro, "
            "current_setting('transaction_isolation') AS isolation, "
            "current_setting('statement_timeout') AS timeout"
        )
        assert dict(cur.fetchone()) == {
            "db": dbname,
            "ro": "on",
            "isolation": "repeatable read",
            "timeout": "12345ms",
        }
        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            cur.execute("INSERT INTO narrative_chunks (raw_text) VALUES ('Forbidden')")


@pytest.mark.requires_postgres
def test_cooldown_report_uses_metadata_and_tick_gaps(cooldown_db: Any) -> None:
    """Stored clocks win over a disagreeing view and retain inherited time."""
    from contextlib import closing

    from scripts.qa_shift.cooldown_calibration import corpus_report
    from tests.pg_fixtures import connect

    dbname, ids, _ = cooldown_db
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        # This clone alone models migration-114 stored-clock contamination.
        # A world_time-only edit does not fire migration 140's refresh trigger.
        cur.execute(
            "UPDATE chunk_metadata SET world_time = world_time + interval '7 minutes' "
            "WHERE chunk_id = %s",
            (ids[-1],),
        )
        cur.execute("ALTER VIEW narrative_view RENAME TO calibration_original_view")
        cur.execute(
            "CREATE VIEW narrative_view AS SELECT chunk_id AS id, "
            "world_time + interval '90 days' AS world_time FROM chunk_metadata"
        )
        cur.execute(
            "SELECT count(*), sum(time_delta), "
            "count(*) FILTER (WHERE time_delta IS NULL) "
            "FROM chunk_metadata WHERE world_layer = 'primary'"
        )
        count, duration, nulls = cur.fetchone()
        cur.execute(
            "WITH pairs AS (SELECT chunk_id - "
            "lag(chunk_id) OVER (ORDER BY chunk_id) AS gap, "
            "extract(epoch FROM world_time - lag(world_time) OVER (ORDER BY chunk_id)) "
            "/ 3600.0 AS hours FROM chunk_metadata WHERE world_layer = 'primary') "
            "SELECT sum(hours)/sum(gap), "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY hours/gap), "
            "avg(hours), percentile_cont(0.5) WITHIN GROUP (ORDER BY hours), "
            "count(*) FILTER (WHERE hours = 0) FROM pairs WHERE gap IS NOT NULL"
        )
        weighted, median, mean_delta, median_delta, zeros = cur.fetchone()
    report = corpus_report(dbname)
    cadence = report["cadence"]
    assert cadence["primary_chunks"] == count == 3
    assert (
        cadence["primary_duration_hours"] == duration.total_seconds() / 3600 == 2 / 60
    )
    assert cadence["null_primary_durations"] == nulls == 1
    assert cadence["world_clock_span_hours"] == 9 / 60
    assert cadence["zero_deltas"] == zeros == 1
    assert [p["tick_gap"] for p in cadence["pairs"]] == [1, 2]
    assert cadence["weighted_hours_per_tick"] == pytest.approx(float(weighted))
    assert cadence["median_pair_hours_per_tick"] == pytest.approx(float(median))
    assert cadence["mean_pair_hours"] == pytest.approx(float(mean_delta))
    assert cadence["median_pair_hours"] == pytest.approx(float(median_delta))
    for row in report["gates"]:
        assert row["weighted_equivalent_hours"] == pytest.approx(
            row["ticks"] * float(weighted)
        )
        assert row["median_equivalent_hours"] == pytest.approx(
            row["ticks"] * float(median)
        )


@pytest.mark.requires_postgres
def test_cooldown_firing_counts_and_formats(cooldown_db: Any) -> None:
    """Commit resolutions, retain zeros/history, and round-trip Markdown fields."""
    from contextlib import closing
    import sys

    from nexus.agents.orrery.events import commit_orrery_tick_sync
    from nexus.agents.orrery.resolver import OrreryResolutionDraft, OrreryTickProposal
    from scripts.qa_shift.cooldown_calibration import corpus_report, markdown
    from tests.pg_fixtures import connect

    dbname, ids, actor = cooldown_db
    with closing(connect(dbname)) as conn, conn:
        for tick, package_ids in (
            (ids[0], ["hide", "hide", "historical_calibration"]),
            (ids[-1], ["hide"]),
            (ids[2], ["historical_calibration"]),
        ):
            drafts = tuple(
                OrreryResolutionDraft(
                    template_id=package,
                    priority=40,
                    binding_hash=f"calibration-{tick}-{i}",
                    bindings={"actor": actor},
                    branch_label="Calibration",
                    narrative_stub="{actor} waits.",
                    magnitude=0.1,
                )
                for i, package in enumerate(package_ids)
            )
            result = commit_orrery_tick_sync(
                conn,
                OrreryTickProposal(
                    anchor_chunk_id=tick, actor_count=1, resolutions=drafts
                ),
                tick_chunk_id=tick,
            )
            assert result.resolution_count == len(package_ids)
    report = corpus_report(dbname)
    firings = report["firings"]
    assert (
        firings["rows"],
        firings["ticks"],
        firings["rows_without_primary_metadata"],
    ) == (5, 3, 1)
    packages = {row["template_id"]: row for row in firings["current_packages"]}
    assert packages["hide"] == {"template_id": "hide", "rows": 3, "ticks": 2}
    assert packages["mourn_loss"]["rows"] == packages["mourn_loss"]["ticks"] == 0
    assert firings["unknown_historical_packages"] == [
        {"template_id": "historical_calibration", "rows": 2, "ticks": 2}
    ]
    assert list(packages) == sorted(packages)
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        str(root / "scripts/qa_shift/cooldown_calibration.py"),
        "--dbname",
        dbname,
        "--format",
    ]
    env = {**os.environ, "PYTHONPATH": str(root)}
    outputs = [
        subprocess.run(
            command + ["json"], env=env, check=True, capture_output=True, text=True
        ).stdout
        for _ in range(2)
    ]
    assert outputs[0] == outputs[1]
    assert json.loads(outputs[0]) == report
    rendered = subprocess.run(
        command + ["markdown"], env=env, check=True, capture_output=True, text=True
    ).stdout
    assert rendered == markdown(report)
    # Decode Markdown tables without calling the renderer: all four sections,
    # including nested pair/firing tables, must retain exactly the JSON values.
    tables: dict[str, list[list[str]]] = {}
    section = ""
    for line in rendered.splitlines():
        if line.startswith("## "):
            section = line[3:]
            tables[section] = []
        elif line.startswith("| "):
            tables[section].append(
                [cell.strip() for cell in line.strip("| ").split(" | ")]
            )
    for name, value in report.items():
        if isinstance(value, dict):
            scalars = {
                key: item for key, item in value.items() if not isinstance(item, list)
            }
            assert {
                row[0]: json.loads(row[1].replace("&#124;", "|"))
                for row in tables[name][2:]
            } == scalars
            children = {
                key: item for key, item in value.items() if isinstance(item, list)
            }
        else:
            children = {name: value}
        for key, rows in children.items():
            table = tables[key]
            assert [
                dict(
                    zip(
                        table[0],
                        [json.loads(cell.replace("&#124;", "|")) for cell in row],
                    )
                )
                for row in table[2:]
            ] == rows


@pytest.mark.requires_postgres
@pytest.mark.parametrize("invalid", ["null", "reversed", "insufficient"])
def test_cooldown_invalid_clock_and_target_fail_loudly(
    cooldown_db: Any, invalid: str
) -> None:
    """Bad stored clocks fail; slot 2 rejection precedes any database attempt."""
    from contextlib import closing

    from scripts.qa_shift.cooldown_calibration import corpus_report
    from tests.pg_fixtures import connect

    dbname, ids, _ = cooldown_db
    # dbname_audit would record an owner target even if its refusal were caught.
    for target in ("save_02", "NEXUS_template", "postgres", "unapproved", "qa640_"):
        with pytest.raises(ValueError, match="Unapproved"):
            corpus_report(target)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        if invalid == "null":
            cur.execute(
                "UPDATE chunk_metadata SET world_time = NULL WHERE chunk_id = %s",
                (ids[-1],),
            )
        elif invalid == "reversed":
            cur.execute(
                "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
                (NOW - timedelta(days=1), ids[-1]),
            )
        else:
            cur.execute("DELETE FROM chunk_metadata WHERE chunk_id <> %s", (ids[0],))
    with pytest.raises(ValueError, match="NULL|reversed|Fewer than two"):
        corpus_report(dbname)
