"""Regression tests for the tracked adversarial QA shift utility."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shlex
import tomllib
from typing import Any, Mapping, cast

import pytest
import tomlkit

from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from scripts.qa_shift import qa_shift


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
    counts = {
        shared_state: maturation_counts[shared_state] + experience_counts[shared_state]
        for shared_state in ("queued", "leased", "succeeded", "failed")
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


def test_begin_creates_archive_and_pins_every_openai_role(
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
    roles = model["api_models"]["openai"]["roles"]

    assert state["baseline_total"] == 123
    assert state["baseline_bleed_offered_count"] == 0
    assert state["baseline_bleed_used_count"] == 0
    assert state["status"] == "active"
    assert model["default_slot_model"] == "gpt-5.6-terra"
    assert set(roles) >= {"default", "gaia"}
    assert all(value == "gpt-5.6-terra" for value in roles.values())
    assert document["wizard"]["fallback_model"] == "@openai.default"
    assert document["orrery"]["narration"]["provider"] == "openai"
    assert document["orrery"]["narration"]["model_ref"] == "@openai.default"
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
    environment_lines = (archive / "runtime_env.sh").read_text().splitlines()
    runtime_export = next(
        line
        for line in environment_lines
        if line.startswith(f"export {RUNTIME_CONFIG_ENV}=")
    )
    assignment = shlex.split(runtime_export)[1]
    name, value = assignment.split("=", 1)
    monkeypatch.setenv(name, value)

    supervisor = Supervisor.from_config()

    assert supervisor.config_path == (archive / "nexus.qa.toml").resolve()


@pytest.mark.parametrize("missing_table", ("roles", "daily_allowance", "narration"))
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
    if missing_table == "roles":
        del document["global"]["model"]["api_models"]["openai"]["roles"]
    elif missing_table == "narration":
        del document["orrery"]["narration"]
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
    "orrery.narration.model_ref",
    "wizard.fallback_model",
}

NON_REMOTE_ROUTES = {
    # Local embedding retriever; never a provider API call.
    "memnon.retrieval.hybrid_search.target_model",
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


def test_every_tracked_model_route_is_pinned_or_role_indirect() -> None:
    """Every remote model route in nexus.toml must be covered by the QA lane.

    The lane rewrites the openai roles table, so any ``@openai.<role>`` ref is
    pinned by indirection. Every other route must be pinned directly in
    ``_write_runtime_config`` (or be a non-remote local route). An unclassified
    route means the isolated lane silently leaks calls to an unpinned
    provider — the Orrery-narration leak the 2026-07-30 scratchpad audit
    caught live, and the wizard-fallback leak found while closing it.
    """
    document = tomllib.loads(
        (qa_shift.REPO_ROOT / "nexus.toml").read_text(encoding="utf-8")
    )
    routes = _collect_model_routes(document)

    missing = (DIRECTLY_PINNED_ROUTES | NON_REMOTE_ROUTES) - set(routes)
    assert not missing, (
        f"Routes {sorted(missing)} vanished from nexus.toml; update the pin "
        "roster and _write_runtime_config together"
    )
    openai_roles = document["global"]["model"]["api_models"]["openai"]["roles"]
    for path, value in routes.items():
        if path in DIRECTLY_PINNED_ROUTES | NON_REMOTE_ROUTES:
            continue
        assert value.startswith("@openai."), (
            f"{path} = {value!r} is not covered by the QA lane's openai role "
            "pins; pin it in _write_runtime_config and add it to "
            "DIRECTLY_PINNED_ROUTES"
        )
        role = value.removeprefix("@openai.")
        assert role in openai_roles, (
            f"{path} = {value!r} references openai role {role!r}, which is "
            "absent from the roles table _write_runtime_config rewrites; the "
            "lane would leave it unpinned"
        )


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
    result, _ = qa_shift.evaluate_check(
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
        "retrograde_maturation": 0,
        "experience_render": 0,
    }
    assert result["current_failed_jobs"] == {
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
        "retrograde_maturation": 2,
        "experience_render": 0,
    }
    assert check["status"] == "continue"
    assert "maturation_job_failed" not in check["reasons"]
    assert check["baseline_failed_jobs"] == {
        "retrograde_maturation": 2,
        "experience_render": 0,
    }
    assert check["current_failed_jobs"] == {
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
        "retrograde_maturation": 1,
        "experience_render": 0,
    }
    assert finish["current_failed_jobs"] == {
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
