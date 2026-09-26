"""Unit coverage for managed-runtime configuration selection and log capture."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, cast

import pytest
import tomlkit

from nexus import cli
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.supervisor import _LogFollower, _tail_lines, rotated_segment


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


# ---------------------------------------------------------------------------
# Log rotation at spawn and reading across rotated segments (issue #842)
# ---------------------------------------------------------------------------


def _logging_supervisor(
    tmp_path: Path,
    *,
    max_bytes: int,
    backup_count: int,
    command: list[str] | None = None,
) -> Supervisor:
    """A real supervisor with an 'echo' service and tiny rotation limits."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    runtime = cast(Any, document["runtime"])
    runtime["state_dir"] = str(tmp_path / "state")
    runtime["logs"]["max_bytes"] = max_bytes
    runtime["logs"]["backup_count"] = backup_count
    echo = tomlkit.table()
    echo["command"] = command or [
        "{python}",
        "-c",
        "import os; print('run-' + os.environ['ECHO_RUN'])",
    ]
    echo["port"] = 1
    echo["enabled"] = "never"
    runtime["services"]["echo"] = echo
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")
    supervisor = Supervisor.from_config(config_path)
    supervisor.state_dir.mkdir(parents=True)
    return supervisor


def _spawn_to_exit(supervisor: Supervisor, run: str) -> None:
    """Spawn the echo service through the real _spawn and reap it."""
    service = supervisor.runtime.services["echo"]
    service.env["ECHO_RUN"] = run
    pid = supervisor._spawn("echo", service, slot=5, detached=True)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0


def _segment_texts(supervisor: Supervisor) -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(supervisor.state_dir.glob("echo.log*"))
    }


def test_spawn_rotates_log_once_it_reaches_max_bytes(tmp_path: Path) -> None:
    """Each spawn past max_bytes shifts segments and drops the oldest."""
    supervisor = _logging_supervisor(tmp_path, max_bytes=1, backup_count=2)
    supervisor.log_path("echo").write_text("seed\n", encoding="utf-8")

    _spawn_to_exit(supervisor, "1")
    assert _segment_texts(supervisor) == {"echo.log": "run-1\n", "echo.log.1": "seed\n"}

    _spawn_to_exit(supervisor, "2")
    _spawn_to_exit(supervisor, "3")

    # backup_count = 2: 'seed' fell off the end; no third segment exists.
    assert _segment_texts(supervisor) == {
        "echo.log": "run-3\n",
        "echo.log.1": "run-2\n",
        "echo.log.2": "run-1\n",
    }


def test_spawn_appends_below_max_bytes(tmp_path: Path) -> None:
    """A capture under max_bytes keeps appending across spawns."""
    supervisor = _logging_supervisor(tmp_path, max_bytes=1024, backup_count=2)

    _spawn_to_exit(supervisor, "1")
    _spawn_to_exit(supervisor, "2")

    assert _segment_texts(supervisor) == {"echo.log": "run-1\nrun-2\n"}


def test_spawn_writes_log_config_for_the_placeholder(tmp_path: Path) -> None:
    """{log_config} resolves to a JSON file written from [runtime.logs]."""
    reader = (
        "import json, sys; config = json.load(open(sys.argv[1])); "
        "print(config['root']['level'], config['formatters']['standard']['format'])"
    )
    supervisor = _logging_supervisor(
        tmp_path,
        max_bytes=1024,
        backup_count=1,
        command=["{python}", "-c", reader, "{log_config}"],
    )

    _spawn_to_exit(supervisor, "1")

    logs = supervisor.runtime.logs
    assert supervisor.log_path("echo").read_text(encoding="utf-8") == (
        f"{logs.level} {logs.format}\n"
    )


def test_spawn_without_placeholder_writes_no_log_config(tmp_path: Path) -> None:
    """Services that do not opt in never get a logging.json written for them."""
    supervisor = _logging_supervisor(tmp_path, max_bytes=1024, backup_count=1)

    _spawn_to_exit(supervisor, "1")

    assert not supervisor.log_config_path().exists()


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def test_logs_reads_backwards_across_rotated_segments(tmp_path: Path) -> None:
    """nexus logs -n N continues into .1, .2 when the current file is short."""
    supervisor = _logging_supervisor(tmp_path, max_bytes=1024, backup_count=3)
    log_path = supervisor.log_path("echo")
    _write_lines(rotated_segment(log_path, 2), ["a-1", "a-2", "a-3"])
    _write_lines(rotated_segment(log_path, 1), ["b-1", "b-2", "b-3"])
    _write_lines(log_path, ["c-1", "c-2"])

    assert list(supervisor.logs("echo", lines=2)) == ["c-1", "c-2"]
    assert list(supervisor.logs("echo", lines=4)) == ["b-2", "b-3", "c-1", "c-2"]
    assert list(supervisor.logs("echo", lines=100)) == [
        "a-1",
        "a-2",
        "a-3",
        "b-1",
        "b-2",
        "b-3",
        "c-1",
        "c-2",
    ]


def test_logs_stop_at_a_missing_segment_and_at_backup_count(tmp_path: Path) -> None:
    """A gap or a segment past backup_count is never stitched into the tail."""
    supervisor = _logging_supervisor(tmp_path, max_bytes=1024, backup_count=1)
    log_path = supervisor.log_path("echo")
    _write_lines(rotated_segment(log_path, 2), ["stale"])
    _write_lines(rotated_segment(log_path, 1), ["b-1"])
    _write_lines(log_path, ["c-1"])

    assert list(supervisor.logs("echo", lines=10)) == ["b-1", "c-1"]

    rotated_segment(log_path, 1).unlink()
    assert list(supervisor.logs("echo", lines=10)) == ["c-1"]


def test_tail_lines_reads_multiple_blocks_without_gaps(tmp_path: Path) -> None:
    """Long tails read the current file fully before crossing to .1."""
    log_path = tmp_path / "gateway.log"
    older = [f"old-{index:05d}-{'x' * 40}" for index in range(3000)]
    current = [f"cur-{index:05d}-{'y' * 40}" for index in range(4000)]
    _write_lines(rotated_segment(log_path, 1), older)
    _write_lines(log_path, current)
    assert log_path.stat().st_size > 3 * 64 * 1024

    assert _tail_lines(log_path, 3999) == current[-3999:]
    assert _tail_lines(log_path, 5000, backup_count=1) == older[-1000:] + current
    assert _tail_lines(log_path, 5000) == current


def test_logs_follow_crosses_spawn_rotation(tmp_path: Path) -> None:
    """-f drains the renamed segment, then continues in the fresh capture."""
    supervisor = _logging_supervisor(tmp_path, max_bytes=1, backup_count=2)
    log_path = supervisor.log_path("echo")
    _write_lines(log_path, ["old-1"])

    stream = supervisor.logs("echo", lines=1, follow=True)
    assert next(stream) == "old-1"

    # The dying process's last words, the final one unterminated.
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("old-2\nold-3")
    _spawn_to_exit(supervisor, "1")
    assert rotated_segment(log_path, 1).read_text(encoding="utf-8").endswith("old-3")

    assert [next(stream) for _ in range(3)] == ["old-2", "old-3", "run-1"]


def test_log_follower_holds_fragments_and_picks_up_a_new_capture(
    tmp_path: Path,
) -> None:
    """The foreground follower emits whole lines only, from a file born later."""
    log_path = tmp_path / "gateway.log"
    follower = _LogFollower(log_path)
    assert follower.read_lines() == []

    log_path.write_text("first\nsecond-part", encoding="utf-8")
    assert follower.read_lines() == ["first"]

    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("-done\n\nthird\n")
    assert follower.read_lines() == ["second-part-done", "", "third"]
    assert follower.read_lines() == []
