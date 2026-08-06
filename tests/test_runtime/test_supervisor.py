"""Unit coverage for managed-runtime configuration selection."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, cast

import pytest
import tomlkit

from nexus import cli
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.supervisor import _tail_lines


REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG = REPO_ROOT / "nexus.toml"
LOG_LINE_COUNT_ERROR = "Log line count must be a positive integer"


def _write_config(tmp_path: Path, name: str = "runtime.toml") -> Path:
    """Write a real temporary runtime config with isolated supervisor state."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    runtime = cast(Any, document["runtime"])
    runtime["state_dir"] = str(tmp_path / "state")
    path = tmp_path / name
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


@pytest.mark.parametrize("count", (-2, -1, 0))
def test_tail_lines_rejects_non_positive_counts(tmp_path: Path, count: int) -> None:
    """The low-level tail helper loudly rejects invalid counts."""
    with pytest.raises(ValueError, match=f"^{LOG_LINE_COUNT_ERROR}$"):
        _tail_lines(tmp_path / "missing.log", count)


@pytest.mark.parametrize(
    "count,expected",
    (
        (1, ["line-119"]),
        (100, [f"line-{index}" for index in range(20, 120)]),
        (500, [f"line-{index}" for index in range(120)]),
    ),
    ids=("one", "default-sized", "larger-than-window"),
)
def test_tail_lines_returns_requested_slice(
    tmp_path: Path, count: int, expected: list[str]
) -> None:
    """Positive tail counts preserve normal slicing behavior."""
    log_path = tmp_path / "gateway.log"
    log_path.write_text(
        "".join(f"line-{index}\n" for index in range(120)), encoding="utf-8"
    )

    assert _tail_lines(log_path, count) == expected


def test_from_config_explicit_path_beats_runtime_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit CLI path remains authoritative over the runtime environment."""
    explicit_config = _write_config(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(tmp_path / "missing.toml"))

    supervisor = Supervisor.from_config(explicit_config)

    assert supervisor.config_path == explicit_config.resolve()


def test_from_config_uses_runtime_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The managed supervisor honors the invoking shell's runtime config."""
    runtime_config = _write_config(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(runtime_config))

    supervisor = Supervisor.from_config()

    assert supervisor.config_path == runtime_config.resolve()


@pytest.mark.parametrize("runtime_config", (None, ""), ids=("unset", "empty"))
def test_from_config_without_runtime_environment_uses_repo_config(
    runtime_config: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset or empty runtime variable falls back to repository nexus.toml."""
    if runtime_config is None:
        monkeypatch.delenv(RUNTIME_CONFIG_ENV, raising=False)
    else:
        monkeypatch.setenv(RUNTIME_CONFIG_ENV, runtime_config)

    supervisor = Supervisor.from_config()

    assert supervisor.config_path == REPO_CONFIG.resolve()


def test_from_config_missing_runtime_environment_path_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured but missing runtime path never falls through to the repo."""
    missing_config = tmp_path / "missing.toml"
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(missing_config))

    with pytest.raises(FileNotFoundError, match=str(missing_config)):
        Supervisor.from_config()


def test_json_status_reports_resolved_runtime_environment_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``nexus --json status`` exposes the environment-selected config path."""
    runtime_config = _write_config(tmp_path)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(runtime_config))
    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)
    monkeypatch.setattr(
        Supervisor,
        "_fetch_runtime_status",
        lambda _supervisor: {"error": "network disabled for unit test"},
    )
    monkeypatch.setattr(sys, "argv", ["nexus", "--json", "status"])

    assert cli.main() == 0

    result = json.loads(capsys.readouterr().out)
    assert result["config"] == str(runtime_config.resolve())
