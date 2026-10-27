"""Pin the offline CI tier (issue #816, Decisions 816-D1 and 816-D10).

The ``offline-tests`` job becomes a required status check, so its name, its
triggers and its two suites are pinned here; the ``requires_local_models``
marker that CI deselects must stay registered and must never gain a local
skip.
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "offline-tests.yml"
GUARD_CHECK = "grep -qF 'secret-store guard: active; nexus-api: denied'"
DESELECT = "-m 'not requires_local_models'"
SUITES = (
    "tests --ignore=tests/test_api --ignore=tests/test_orrery",
    "tests/test_api tests/test_orrery",
)
TIER_VARIABLES = frozenset(
    {
        "NEXUS_RUN_POSTGRES",
        "NEXUS_RUN_CORPUS",
        "NEXUS_RUN_LIVE_LLM",
        "NEXUS_RUN_SECRET_STORE",
        "NEXUS_GATEWAY_PORT",
        "NEXUS_API_URL",
        "NEXUS_SLOT",
    }
)


def _workflow() -> dict[Any, Any]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _steps(job: str) -> list[dict[str, Any]]:
    steps = _workflow()["jobs"][job]["steps"]
    assert isinstance(steps, list)
    return steps


def _runs(job: str) -> list[str]:
    return [str(step["run"]) for step in _steps(job) if "run" in step]


def _checkout(job: str) -> dict[str, Any]:
    (checkout,) = [
        step
        for step in _steps(job)
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    return checkout


def test_offline_tests_job_is_the_unfiltered_required_check() -> None:
    """The required check reports on every push and pull request into main."""

    document = _workflow()
    # PyYAML reads the bare ``on`` key as the boolean True.
    triggers = document.get("on", document.get(True))
    assert isinstance(triggers, dict)
    assert set(triggers) == {"push", "pull_request"}
    for trigger in triggers.values():
        assert trigger["branches"] == ["main"]
        assert "paths" not in trigger
        assert "paths-ignore" not in trigger
    jobs = document["jobs"]
    assert set(jobs) == {"offline-tests", "ui-tests"}
    for job in jobs.values():
        assert "name" not in job
    assert jobs["offline-tests"]["timeout-minutes"] == 60


def test_offline_tests_run_both_suites_without_local_models() -> None:
    """Both offline suites run, deselect the marker and check the guard line."""

    runs = _runs("offline-tests")
    invocations = [
        (run, line.strip())
        for run in runs
        for line in run.splitlines()
        if "poetry run pytest" in line
    ]
    assert len(invocations) == 2
    for step in _steps("offline-tests"):
        if "poetry run pytest" in str(step.get("run", "")):
            # `shell: bash` runs the step as `bash -eo pipefail`; GitHub's
            # default `bash -e` takes tee's status, so a pytest failure would
            # pass the step.
            assert step.get("shell") == "bash"
    logs = []
    for (run, line), suite in zip(invocations, SUITES, strict=True):
        assert suite in line
        assert DESELECT in line
        # Each suite's guard check reads the log that same suite tee'd into.
        log = line.rsplit("tee", 1)[1].strip()
        logs.append(log)
        lines = [text.strip() for text in run.splitlines()]
        assert f"{GUARD_CHECK} {log}" in lines[lines.index(line) + 1 :]
    assert len(set(logs)) == 2

    document = _workflow()
    job = document["jobs"]["offline-tests"]
    environments = [document.get("env"), job.get("env")]
    environments += [step.get("env") for step in job["steps"]]
    for environment in environments:
        assert not TIER_VARIABLES & set(environment or {})
    for run in runs:
        for variable in TIER_VARIABLES:
            assert f"{variable}=" not in run

    (setup,) = [
        step
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/setup-python@")
    ]
    versions = str(setup["with"]["python-version"]).split()
    assert {"3.11", "3.12", "3.13"} <= set(versions)
    assert _checkout("offline-tests")["with"]["fetch-depth"] == 0


def test_ui_tests_job_fetches_only_ui_lfs_and_runs_vitest() -> None:
    """The UI job pulls only the LFS objects under ui/ and runs vitest."""

    checkout = _checkout("ui-tests")
    assert not (checkout.get("with") or {}).get("lfs", False)
    # state-shades.test.ts reads a historical commit with `git show`.
    assert checkout["with"]["fetch-depth"] == 0
    runs = _runs("ui-tests")
    lfs_commands = [
        line.strip() for run in runs for line in run.splitlines() if "git lfs" in line
    ]
    assert lfs_commands == ['git lfs pull --include="ui/**"']
    assert "npm --prefix ui ci" in runs
    assert "npm --prefix ui test" in runs


def test_local_models_marker_is_registered_without_a_local_skip() -> None:
    """The marker is registered, and only CI ``-m`` expressions deselect it."""

    parser = configparser.ConfigParser()
    parser.read(ROOT / "pytest.ini", encoding="utf-8")
    markers = [line.strip() for line in parser["pytest"]["markers"].splitlines()]
    assert any(line.startswith("requires_local_models:") for line in markers)
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "requires_local_models" not in conftest
