"""Init plans preserve readiness order, refusals and diagnostic receipt access.

These tests use real reports and the CLI entry point. Broken configurations
fail before any database or secret check, and receipts stay under tmp_path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys

import pytest

from nexus import cli
from nexus.cli_contract import (
    COMMAND_TRANSPORTS,
    ENVELOPE_COMMANDS,
    RUNTIME_CONFIG_COMMANDS,
    SELF_DIAGNOSTIC_COMMANDS,
)
from nexus.config import load_settings
from nexus.runtime.contract import HOME_ENV, RUNTIME_CONFIG_ENV, TEST_RECEIPTS_ENV
from nexus.runtime.init_plan import InitPlan, plan_from_report, render_plan
from nexus.runtime.readiness import (
    REGISTRY,
    CheckResult,
    CheckSpec,
    CheckStatus,
    ReadinessReport,
)


@pytest.fixture(autouse=True)
def private_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate configuration locators and each test's failure receipts."""
    for name in (HOME_ENV, RUNTIME_CONFIG_ENV, "NEXUS_API_URL", "NEXUS_GATEWAY_PORT"):
        monkeypatch.delenv(name, raising=False)
    receipts = tmp_path / "receipts"
    monkeypatch.setenv(TEST_RECEIPTS_ENV, str(receipts))
    return receipts


def _report(
    overrides: Mapping[str, tuple[CheckStatus, str, str | None]] | None = None,
) -> ReadinessReport:
    """Construct all current owner-host results in the registry's order."""
    changes = overrides or {}
    specs = [spec for spec in REGISTRY if "owner-host" in spec.targets]
    assert set(changes) <= {spec.id for spec in specs}
    checks = []
    for spec in specs:
        status, observed, remediation = changes.get(spec.id, ("pass", "ok", None))
        checks.append(
            CheckResult(
                id=spec.id,
                targets=list(spec.targets),
                depends_on=list(spec.depends_on),
                status=status,
                observed=observed,
                remediation=remediation,
            )
        )
    return ReadinessReport(
        target="owner-host",
        ok=all(check.status != "fail" for check in checks),
        checks=checks,
        omitted=[],
    )


def _dependents(root: str, specs: Sequence[CheckSpec]) -> list[str]:
    """Collect transitive dependents in the registry's dependency order."""
    result: list[str] = []
    for spec in specs:
        if any(parent == root or parent in result for parent in spec.depends_on):
            result.append(spec.id)
    return result


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *args: str,
) -> tuple[int, str, str]:
    """Run the actual entry point in-process and return its captured streams."""
    monkeypatch.setattr(sys, "argv", ["nexus", *args])
    exit_code = cli.main()
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_plan_lists_failed_checks_in_report_order() -> None:
    """Sorting by ID, splitting commands or listing passes changes these steps."""
    slot_remedy = (
        "python scripts/migrate.py --slot 1 --write-locked-slot; "
        "python scripts/migrate.py --slot 2"
    )
    plan = plan_from_report(
        _report(
            {
                "template.migrations_current": (
                    "fail",
                    "template pending",
                    "python scripts/migrate.py --template",
                ),
                "slots.migrations_current": ("fail", "slots pending", slot_remedy),
                "tools.pg_dump": (
                    "fail",
                    "pg_dump missing",
                    "Install PostgreSQL tools",
                ),
            }
        )
    )
    assert [step.number for step in plan.steps] == [1, 2, 3]
    assert [step.check_id for step in plan.steps] == [
        "template.migrations_current",
        "slots.migrations_current",
        "tools.pg_dump",
    ]
    assert [step.observed for step in plan.steps] == [
        "template pending",
        "slots pending",
        "pg_dump missing",
    ]
    assert plan.steps[1].remediation == slot_remedy
    assert plan.blocked == []
    assert not plan.ok


def test_plan_lists_skipped_checks_as_blocked() -> None:
    """Skipped dependents remain blocked checks, never additional setup steps."""
    specs = [spec for spec in REGISTRY if "owner-host" in spec.targets]
    blocked = _dependents("postgres.reachable", specs)
    overrides: dict[str, tuple[CheckStatus, str, str | None]] = {
        "postgres.reachable": ("fail", "server unavailable", "Start PostgreSQL")
    }
    overrides.update(
        {
            check_id: (
                "skip",
                "postgres.reachable failed",
                "Resolve postgres.reachable first.",
            )
            for check_id in blocked
        }
    )
    plan = plan_from_report(_report(overrides))
    assert len(plan.steps) == 1
    assert plan.steps[0].check_id == "postgres.reachable"
    assert plan.blocked == blocked
    assert render_plan(plan) == [
        "1. postgres.reachable: Start PostgreSQL",
        "Then run nexus init --plan again; these checks wait on the steps above: "
        + ", ".join(blocked),
    ]


def test_passing_report_plans_nothing() -> None:
    """A fully passing dynamic report contributes no step or blocked check."""
    plan = plan_from_report(_report())
    assert plan.schema_version == 1
    assert plan.target == "owner-host"
    assert plan.steps == []
    assert plan.blocked == []
    assert plan.ok
    assert render_plan(plan) == ["No setup steps: every owner-host check passes."]


def test_plan_refuses_reports_it_cannot_plan_from() -> None:
    """Wrong target, omitted checks and missing remediation cannot form a plan."""
    report = _report()
    with pytest.raises(ValueError, match="owner-host"):
        plan_from_report(report.model_copy(update={"target": "owner-client"}))
    with pytest.raises(ValueError, match="omitted"):
        plan_from_report(report.model_copy(update={"omitted": [report.checks[0].id]}))
    with pytest.raises(RuntimeError, match="config.valid"):
        plan_from_report(_report({"config.valid": ("fail", "invalid config", None)}))


def test_init_plan_matches_doctor_under_a_broken_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    private_environment: Path,
) -> None:
    """Real broken-config findings bypass remote refusal and keep private receipts."""
    config = tmp_path / "nexus.toml"
    config.write_text("[runtime\n", encoding="utf-8")
    monkeypatch.setenv("NEXUS_API_URL", "https://nexus.example.invalid")
    code, output, error = _run_cli(
        monkeypatch, capsys, "doctor", "--config", str(config), "--json"
    )
    assert code == 1
    assert "config_error" not in error and "transport_refused" not in error
    doctor = json.loads(output)
    code, output, error = _run_cli(
        monkeypatch, capsys, "init", "--plan", "--config", str(config), "--json"
    )
    assert code == 1
    assert "config_error" not in error and "transport_refused" not in error
    plan = InitPlan.model_validate_json(output)
    failures = [check for check in doctor["checks"] if check["status"] == "fail"]
    assert [step.model_dump() for step in plan.steps] == [
        {
            "number": number,
            "check_id": check["id"],
            "observed": check["observed"],
            "remediation": check["remediation"],
        }
        for number, check in enumerate(failures, start=1)
    ]
    assert plan.steps[0].check_id == "config.valid"
    assert plan.blocked == [
        check["id"] for check in doctor["checks"] if check["status"] == "skip"
    ]
    assert not plan.ok
    records = [
        json.loads(line)
        for path in private_environment.rglob("failures-*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 2
    assert all(record["config_path"] == str(config) for record in records)

    code, output, error = _run_cli(
        monkeypatch, capsys, "init", "--plan", "--config", str(config)
    )
    assert code == 1
    assert output.splitlines() == render_plan(plan)
    assert "config_error" not in error and "transport_refused" not in error


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("init", "--json"), "--plan"),
        (("init", "--plan", "--apply", "--json"), "unrecognized arguments: --apply"),
    ],
)
def test_init_requires_plan_and_has_no_apply(
    arguments: tuple[str, ...],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Parser refusals remain usage envelopes and cannot reach readiness."""
    monkeypatch.setattr(sys, "argv", ["nexus", *arguments])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["code"] == "usage_error"
    assert message in failure["error"]


def test_init_preserves_existing_self_diagnostic_commands() -> None:
    """Adding init must retain receipts and doctor without envelope/config opt-ins."""
    assert {"doctor", "init", "receipts"} <= SELF_DIAGNOSTIC_COMMANDS
    assert COMMAND_TRANSPORTS["init"] == "local_operator"
    assert "init" not in ENVELOPE_COMMANDS
    assert "init" not in RUNTIME_CONFIG_COMMANDS


def test_receipts_still_runs_with_broken_config_and_remote_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    private_environment: Path,
) -> None:
    """The real receipt reader works despite both pre-dispatch refusal triggers."""
    config = tmp_path / "broken.toml"
    config.write_text("[runtime\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(config)
    before = {
        path: path.read_bytes()
        for path in private_environment.rglob("failures-*.jsonl")
    }
    assert before
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))
    monkeypatch.setenv("NEXUS_API_URL", "https://nexus.example.invalid")
    code, output, error = _run_cli(monkeypatch, capsys, "receipts", "--json")
    assert code == 0
    assert error == ""
    document = json.loads(output)
    assert document["home_dir"] == str(private_environment / "home")
    assert document["fallback_dir"] == str(private_environment / "fallback")
    assert sum(group["count"] for group in document["groups"]) == 1
    assert document["groups"][0]["first"]["config_path"] == str(config)
    assert {
        path: path.read_bytes()
        for path in private_environment.rglob("failures-*.jsonl")
    } == before
