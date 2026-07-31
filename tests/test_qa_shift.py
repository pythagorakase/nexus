"""Regression tests for the tracked adversarial QA shift utility."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shlex
import tomllib
from typing import Any, Mapping

import pytest
import tomlkit

from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from scripts.qa_shift import qa_shift


NOW = datetime(2026, 7, 30, 4, 30, tzinfo=timezone.utc)


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
        "checks": 0,
        "max_command_delta": 0,
        "config": qa_shift._config_payload(config),
    }


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
        now=NOW,
    )

    archive = Path(result["archive"])
    state = json.loads((archive / "shift_state.json").read_text())
    document = tomlkit.parse((archive / "nexus.qa.toml").read_text())
    model = document["global"]["model"]
    roles = model["api_models"]["openai"]["roles"]

    assert state["baseline_total"] == 123
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
    document = tomlkit.parse((qa_shift.REPO_ROOT / "nexus.toml").read_text())
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
                usage_reader=lambda _root, _day, value=payload: value,
                now=NOW,
            )

    assert list(tmp_path.iterdir()) == []


def test_post_call_check_reports_exact_delta_and_route() -> None:
    config = qa_shift.load_shift_config()
    event = _event(total=321)

    result, updated = qa_shift.evaluate_check(
        state=_state(config),
        usage_payload=_usage(total=421, events=[event]),
        expect_call=True,
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
        expect_call=True,
        now=NOW + timedelta(minutes=1),
    )
    wrong, _ = qa_shift.evaluate_check(
        state=_state(config),
        usage_payload=_usage(
            total=200,
            events=[_event(model="gpt-5.6-sol")],
        ),
        expect_call=True,
        now=NOW + timedelta(minutes=1),
    )

    assert missing["status"] == "stop"
    assert "expected_usage_event_missing" in missing["reasons"]
    assert wrong["status"] == "stop"
    assert "unexpected_qa_model_route" in wrong["reasons"]


def test_check_fails_closed_at_token_time_day_and_unknown_boundaries() -> None:
    config = qa_shift.load_shift_config()
    state = _state(config)

    fenced, _ = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=9_000_000),
        expect_call=False,
        now=NOW + timedelta(minutes=1),
    )
    timed, _ = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100),
        expect_call=False,
        now=NOW + timedelta(minutes=60),
    )
    rolled, rolled_state = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100, day="2026-07-31"),
        expect_call=False,
        now=NOW + timedelta(minutes=1),
    )
    unknown, _ = qa_shift.evaluate_check(
        state=state,
        usage_payload=_usage(total=100, unknown=1),
        expect_call=False,
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
        now=NOW,
    )
    archive = Path(begin["archive"])
    first_event = _event(total=200)

    check = qa_shift.check_shift(
        archive=archive,
        expect_call=True,
        usage_reader=lambda _root, _day: _usage(total=300, events=[first_event]),
        now=NOW + timedelta(minutes=1),
    )
    finish = qa_shift.finish_shift(
        archive=archive,
        exit_condition="dry_well",
        usage_reader=lambda _root, _day: _usage(total=350, events=[first_event]),
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
        now=NOW,
    )
    archive = Path(begin["archive"])

    rollover = qa_shift.check_shift(
        archive=archive,
        expect_call=False,
        usage_reader=lambda _root, _day: _usage(
            total=40,
            day="2026-07-31",
        ),
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
