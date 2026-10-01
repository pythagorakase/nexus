"""Unit coverage for managed-runtime configuration selection and log capture."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any, cast

import pytest
import tomlkit

from nexus import cli
from nexus.config.settings_models import RuntimeServiceSettings
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime import supervisor as supervisor_module
from nexus.runtime.log_capture import (
    WriterProbeError,
    process_running,
    spawn_captured,
    wait_for_writer,
    writer_error_path,
)
from nexus.runtime.readiness import REGISTRY, ReadinessContext, run_readiness
from nexus.runtime.supervisor import (
    RuntimeError_,
    _LogFollower,
    _open_segments,
    _tail_lines,
    rotated_segment,
)
from tests.test_runtime import test_supervisor_live as live_helpers
from tests.test_runtime.test_supervisor_live import ephemeral_ports  # noqa: F401


REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG = REPO_ROOT / "nexus.toml"
LOG_LINE_COUNT_ERROR = "Log line count must be a positive integer"
UNBOUNDED_READ = 1024 * 1024
ECHO_COMMAND = [
    "{python}",
    "-c",
    "import os; print('run-' + os.environ['ECHO_RUN'])",
]
# The 200-line child: 200 numbered lines padded to 40 bytes (41 with the
# newline), each flushed as it is written.
TWO_HUNDRED_LINES = [f"line-{index:03d}".ljust(40, ".") for index in range(1, 201)]
TWO_HUNDRED_CHILD = [
    "{python}",
    "-c",
    "for index in range(1, 201):\n"
    "    print(('line-%03d' % index).ljust(40, '.'), flush=True)",
]
EMITTED = "".join(f"{line}\n" for line in TWO_HUNDRED_LINES).encode()
# The holding child: a grandchild in its own session keeps the child's stdout
# for 30 s after the child has printed the grandchild's pid and exited.
HOLDING_CHILD = [
    "{python}",
    "-c",
    "import subprocess, sys\n"
    "grandchild = subprocess.Popen(\n"
    "    [sys.executable, '-c', 'import time; time.sleep(30)'],\n"
    "    start_new_session=True,\n"
    ")\n"
    "print(grandchild.pid, flush=True)",
]


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
        _tail_lines(tmp_path / "missing.log", count, max_read_bytes=UNBOUNDED_READ)


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

    assert _tail_lines(log_path, count, max_read_bytes=UNBOUNDED_READ) == expected


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
    max_tail_bytes: int | None = None,
    stop_grace_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
    gateway_port: int | None = None,
) -> Supervisor:
    """A real supervisor with an 'echo' service and tiny rotation limits."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    runtime = cast(Any, document["runtime"])
    runtime["state_dir"] = str(tmp_path / "state")
    runtime["logs"]["max_bytes"] = max_bytes
    runtime["logs"]["backup_count"] = backup_count
    if max_tail_bytes is not None:
        runtime["logs"]["max_tail_bytes"] = max_tail_bytes
    if stop_grace_seconds is not None:
        runtime["health"]["stop_grace_seconds"] = stop_grace_seconds
    if poll_interval_seconds is not None:
        runtime["health"]["poll_interval_seconds"] = poll_interval_seconds
    if gateway_port is not None:
        runtime["services"]["gateway"]["port"] = gateway_port
    echo = tomlkit.table()
    echo["command"] = command or ECHO_COMMAND
    echo["port"] = 1
    echo["enabled"] = "never"
    runtime["services"]["echo"] = echo
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")
    supervisor = Supervisor.from_config(config_path)
    supervisor.state_dir.mkdir(parents=True)
    return supervisor


def _spawn_to_exit(supervisor: Supervisor, run: str) -> None:
    """Spawn the echo service through the real _spawn and reap it and its writer."""
    service = supervisor.runtime.services["echo"]
    service.env["ECHO_RUN"] = run
    pid, writer_pid = supervisor._spawn("echo", service, slot=5, detached=True)
    for process in (pid, writer_pid):
        _, status = os.waitpid(process, 0)
        assert os.waitstatus_to_exitcode(status) == 0


def _segment_texts(supervisor: Supervisor) -> dict[str, str]:
    """The capture and its rotated segments (not the writer's error file)."""
    error_file = writer_error_path(supervisor.log_path("echo"))
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(supervisor.state_dir.glob("echo.log*"))
        if path != error_file
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


def _create_with_lines(path: Path, lines: list[str]) -> None:
    """Create ``path`` holding ``lines`` in one step (no empty-file window)."""
    staging = path.with_name(f"{path.name}.staging")
    _write_lines(staging, lines)
    os.replace(staging, path)


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

    assert _tail_lines(log_path, 3999, max_read_bytes=UNBOUNDED_READ) == (
        current[-3999:]
    )
    assert (
        _tail_lines(log_path, 5000, max_read_bytes=UNBOUNDED_READ, backup_count=1)
        == older[-1000:] + current
    )
    assert _tail_lines(log_path, 5000, max_read_bytes=UNBOUNDED_READ) == current


@pytest.mark.parametrize(
    "max_read_bytes,expected_older",
    ((50, ["b-8", "b-9"]), (55, ["b-8", "b-9"]), (60, ["b-7", "b-8", "b-9"])),
    ids=("window-on-line-boundary", "window-cuts-a-line", "next-boundary"),
)
def test_tail_lines_read_bound_spans_segments(
    tmp_path: Path, max_read_bytes: int, expected_older: list[str]
) -> None:
    """The byte bound covers every segment read and drops a cut first line."""
    log_path = tmp_path / "gateway.log"
    # Ten-byte lines: 'b-N' plus padding plus the newline.
    older = [f"b-{index}".ljust(9, ".") for index in range(10)]
    current = [f"c-{index}".ljust(9, ".") for index in range(3)]
    _write_lines(rotated_segment(log_path, 1), older)
    _write_lines(log_path, current)

    tail = _tail_lines(log_path, 100, max_read_bytes=max_read_bytes, backup_count=1)

    assert tail == [line.ljust(9, ".") for line in expected_older] + current


@pytest.mark.parametrize("max_read_bytes", (0, -1))
def test_tail_lines_rejects_non_positive_read_bound(
    tmp_path: Path, max_read_bytes: int
) -> None:
    """A read bound that cannot read anything fails loudly."""
    with pytest.raises(ValueError, match="read bound"):
        _tail_lines(tmp_path / "missing.log", 1, max_read_bytes=max_read_bytes)


def test_logs_honors_configured_max_tail_bytes(tmp_path: Path) -> None:
    """[runtime.logs].max_tail_bytes bounds what nexus logs -n reads."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1024, backup_count=1, max_tail_bytes=30
    )
    log_path = supervisor.log_path("echo")
    _write_lines(rotated_segment(log_path, 1), ["b-1".ljust(9, ".")])
    _write_lines(log_path, [f"c-{index}".ljust(9, ".") for index in range(5)])

    assert list(supervisor.logs("echo", lines=100)) == [
        f"c-{index}".ljust(9, ".") for index in range(2, 5)
    ]


def test_tail_lines_stops_at_a_pinned_end_offset(tmp_path: Path) -> None:
    """A tail pinned at a follower's offset leaves later bytes to the follower."""
    log_path = tmp_path / "gateway.log"
    _write_lines(log_path, ["a", "b"])
    follower = _LogFollower(log_path, backup_count=1)
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("c\n")

    assert _tail_lines(
        log_path, 10, max_read_bytes=UNBOUNDED_READ, end=follower.offset
    ) == ["a", "b"]
    assert follower.read_lines() == ["c"]


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


def test_logs_follow_crosses_two_rotations_within_one_poll(tmp_path: Path) -> None:
    """A segment pushed past .1 before the next poll is still drained in order."""
    supervisor = _logging_supervisor(tmp_path, max_bytes=1, backup_count=3)
    log_path = supervisor.log_path("echo")
    _write_lines(log_path, ["old-1"])

    stream = supervisor.logs("echo", lines=1, follow=True)
    assert next(stream) == "old-1"

    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("old-2\nold-3")
    _spawn_to_exit(supervisor, "1")
    _spawn_to_exit(supervisor, "2")
    assert rotated_segment(log_path, 2).read_text(encoding="utf-8").endswith("old-3")

    assert [next(stream) for _ in range(4)] == ["old-2", "old-3", "run-1", "run-2"]


def test_log_follower_holds_fragments_and_picks_up_a_new_capture(
    tmp_path: Path,
) -> None:
    """The foreground follower emits whole lines only, from a file born later."""
    log_path = tmp_path / "gateway.log"
    follower = _LogFollower(log_path, backup_count=1)
    assert follower.read_lines() == []

    log_path.write_text("first\nsecond-part", encoding="utf-8")
    assert follower.read_lines() == ["first"]

    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("-done\n\nthird\n")
    assert follower.read_lines() == ["second-part-done", "", "third"]
    assert follower.read_lines() == []


# ---------------------------------------------------------------------------
# Live rotation by the log writer (issue #842, slice S2)
# ---------------------------------------------------------------------------


def _capture_files(log_path: Path, backup_count: int) -> list[Path]:
    """The retained segments oldest first, then the current capture."""
    rotated = [
        rotated_segment(log_path, index)
        for index in range(backup_count, 0, -1)
        if rotated_segment(log_path, index).exists()
    ]
    return rotated + [log_path]


def test_writer_rotates_a_live_capture_without_losing_lines(tmp_path: Path) -> None:
    """One run past max_bytes many times keeps every byte, in bounded segments."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=12, command=TWO_HUNDRED_CHILD
    )
    log_path = supervisor.log_path("echo")

    _spawn_to_exit(supervisor, "1")

    files = _capture_files(log_path, 12)
    assert b"".join(path.read_bytes() for path in files) == EMITTED
    assert len(files) - 1 >= 8
    for path in files:
        data = path.read_bytes()
        assert len(data) <= 1000, path.name
        assert data.endswith(b"\n"), path.name
    assert writer_error_path(log_path).read_bytes() == b""


def test_writer_retention_drops_only_the_oldest(tmp_path: Path) -> None:
    """With backup_count=2 the retained text is a line-aligned suffix."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=2, command=TWO_HUNDRED_CHILD
    )
    log_path = supervisor.log_path("echo")

    _spawn_to_exit(supervisor, "1")

    assert not rotated_segment(log_path, 3).exists()
    retained = b"".join(path.read_bytes() for path in _capture_files(log_path, 2))
    assert retained and EMITTED.endswith(retained)
    dropped = EMITTED[: len(EMITTED) - len(retained)]
    assert dropped == b"" or dropped.endswith(b"\n")


def test_writer_keeps_an_overlong_line_whole(tmp_path: Path) -> None:
    """A line longer than max_bytes fills one segment of its own, unsplit."""
    long_line = "x" * 3000
    supervisor = _logging_supervisor(
        tmp_path,
        max_bytes=1000,
        backup_count=5,
        command=[
            "{python}",
            "-c",
            f"print('short-1'); print('{long_line}'); print('short-2')",
        ],
    )
    log_path = supervisor.log_path("echo")

    _spawn_to_exit(supervisor, "1")

    files = _capture_files(log_path, 5)
    assert [path.read_bytes() for path in files] == [
        b"short-1\n",
        f"{long_line}\n".encode(),
        b"short-2\n",
    ]


def test_spawn_captured_releases_the_callers_stderr(tmp_path: Path) -> None:
    """A spawning process that exits leaves no writer holding its pipes."""
    capture = tmp_path / "logs" / "sleeper.log"
    pid_file = tmp_path / "pids.txt"
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from nexus.config.settings_models import (\n"
        "    RuntimeHealthSettings,\n"
        "    RuntimeLogsSettings,\n"
        ")\n"
        "from nexus.runtime.log_capture import spawn_captured\n"
        "captured = spawn_captured(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(30)'],\n"
        "    log_path=Path(sys.argv[1]),\n"
        "    logs=RuntimeLogsSettings(),\n"
        "    health=RuntimeHealthSettings(),\n"
        "    popen_kwargs={'start_new_session': True},\n"
        ")\n"
        "Path(sys.argv[2]).write_text(f'{captured.pid} {captured.writer_pid}')\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script, str(capture), str(pid_file)],
            capture_output=True,
            timeout=10,
            cwd=REPO_ROOT,
            env=env,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert len(pid_file.read_text().split()) == 2
        assert writer_error_path(capture).exists()
    finally:
        # The pids are on disk before the script exits, so a run that times
        # out on a held pipe still leaves no sleeper or writer behind.
        if pid_file.exists():
            for value in pid_file.read_text().split():
                _kill_quietly(int(value))


def test_follow_crosses_live_rotation(tmp_path: Path) -> None:
    """A pinned follower reads every line once across eight live rotations."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=12, command=TWO_HUNDRED_CHILD
    )
    log_path = supervisor.log_path("echo")
    _write_lines(log_path, ["seed"])
    follower = _LogFollower(log_path, backup_count=12)

    _spawn_to_exit(supervisor, "1")

    assert rotated_segment(log_path, 8).exists()
    assert follower.read_lines() == TWO_HUNDRED_LINES


def test_logs_since_mark_crosses_live_rotation(tmp_path: Path) -> None:
    """logs_since returns exactly the lines after the mark, across rotations."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=12, command=TWO_HUNDRED_CHILD
    )
    log_path = supervisor.log_path("echo")
    _write_lines(log_path, ["before-1", "before-2"])
    mark = supervisor.log_mark("echo")
    assert mark.split(":")[:2] == [
        str(log_path.stat().st_ino),
        str(log_path.stat().st_size),
    ]

    _spawn_to_exit(supervisor, "1")

    assert rotated_segment(log_path, 8).exists()
    assert supervisor.logs_since("echo", mark) == TWO_HUNDRED_LINES
    assert supervisor.logs_since("echo", supervisor.log_mark("echo")) == []


def test_logs_since_refuses_a_mark_out_of_retention(tmp_path: Path) -> None:
    """A mark whose file left retention, or whose crc differs, is refused."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=2, command=TWO_HUNDRED_CHILD
    )
    log_path = supervisor.log_path("echo")
    _write_lines(log_path, ["before"])
    mark = supervisor.log_mark("echo")

    _spawn_to_exit(supervisor, "1")

    with pytest.raises(RuntimeError_, match=f"Log mark {mark}: no retained segment"):
        supervisor.logs_since("echo", mark)

    inode, size, crc = supervisor.log_mark("echo").split(":")
    forged = f"{inode}:{size}:{(int(crc) + 1) % 2**32}"
    with pytest.raises(RuntimeError_, match=f"Log mark {forged}: .* inode was reused"):
        supervisor.logs_since("echo", forged)


def test_logs_since_from_no_capture(tmp_path: Path) -> None:
    """The empty mark reads everything retained, until .backup_count exists."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=12, command=TWO_HUNDRED_CHILD
    )
    log_path = supervisor.log_path("echo")
    mark = supervisor.log_mark("echo")
    assert mark == "0:0:0"
    assert supervisor.logs_since("echo", mark) == []

    _spawn_to_exit(supervisor, "1")

    assert supervisor.logs_since("echo", mark) == TWO_HUNDRED_LINES
    rotated_segment(log_path, 12).write_text("oldest\n", encoding="utf-8")
    with pytest.raises(RuntimeError_, match="Log mark 0:0:0 names no capture"):
        supervisor.logs_since("echo", mark)


def test_logs_since_waits_out_a_rotation_in_progress(tmp_path: Path) -> None:
    """A slice or mark taken mid-rotation waits for the chain to close."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=3, stop_grace_seconds=10
    )
    log_path = supervisor.log_path("echo")
    _write_lines(log_path, ["current"])
    _write_lines(rotated_segment(log_path, 2), ["oldest"])

    def finish_rotation() -> None:
        # The writer's rename of the current file, then its fresh open.
        time.sleep(0.5)
        log_path.replace(rotated_segment(log_path, 1))
        time.sleep(0.5)
        _create_with_lines(log_path, ["fresh"])

    # .2 exists while .1 is absent: the shift of .1 -> .2 just ran.
    rotation = threading.Thread(target=finish_rotation)
    rotation.start()
    try:
        assert supervisor.logs_since("echo", "0:0:0") == ["oldest", "current", "fresh"]
    finally:
        rotation.join()

    # The current file is absent while .1 exists: the rename just ran.
    log_path.replace(rotated_segment(log_path, 1))

    def open_fresh_file() -> None:
        time.sleep(0.5)
        _create_with_lines(log_path, ["newer"])

    rotation = threading.Thread(target=open_fresh_file)
    rotation.start()
    try:
        mark = supervisor.log_mark("echo")
    finally:
        rotation.join()
    assert mark.split(":")[0] == str(log_path.stat().st_ino)
    assert supervisor.logs_since("echo", mark) == []


def test_logs_since_refuses_a_lasting_gap_in_the_chain(tmp_path: Path) -> None:
    """A segment missing past the grace raises instead of dropping lines."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=3, stop_grace_seconds=1
    )
    log_path = supervisor.log_path("echo")
    _write_lines(log_path, ["current"])
    _write_lines(rotated_segment(log_path, 2), ["oldest"])

    with pytest.raises(RuntimeError_, match="echo.log.1 is missing while"):
        supervisor.logs_since("echo", "0:0:0")

    log_path.replace(rotated_segment(log_path, 1))
    with pytest.raises(RuntimeError_, match="echo.log is missing while"):
        supervisor.log_mark("echo")
    with pytest.raises(RuntimeError_, match="echo.log is missing while"):
        supervisor.logs_since("echo", "0:0:0")


def test_wait_for_writer_ignores_a_pid_that_is_not_the_writer(tmp_path: Path) -> None:
    """A live pid that is not this file's writer counts as gone, unsignalled."""
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        started = time.monotonic()
        assert wait_for_writer(sleeper.pid, tmp_path / "echo.log", 5, 0.1) is True
        assert time.monotonic() - started < 1
        assert sleeper.poll() is None
    finally:
        sleeper.kill()
        sleeper.wait()


def test_wait_for_writer_returns_for_another_parents_exited_writer(
    tmp_path: Path,
) -> None:
    """An exited writer that its live parent has not reaped counts as gone."""
    capture = tmp_path / "logs" / "brief.log"
    pid_file = tmp_path / "pids.txt"
    # The parent spawns the capture, records the pids, and never reaps them.
    script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from nexus.config.settings_models import (\n"
        "    RuntimeHealthSettings,\n"
        "    RuntimeLogsSettings,\n"
        ")\n"
        "from nexus.runtime.log_capture import spawn_captured\n"
        "captured = spawn_captured(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(1)'],\n"
        "    log_path=Path(sys.argv[1]),\n"
        "    logs=RuntimeLogsSettings(),\n"
        "    health=RuntimeHealthSettings(),\n"
        ")\n"
        "Path(sys.argv[2]).write_text(f'{captured.pid} {captured.writer_pid}')\n"
        "time.sleep(30)\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    parent = subprocess.Popen(
        [sys.executable, "-c", script, str(capture), str(pid_file)],
        cwd=REPO_ROOT,
        env=env,
    )
    try:
        deadline = time.monotonic() + 10
        while not pid_file.exists() or len(pid_file.read_text().split()) < 2:
            assert time.monotonic() < deadline, "the parent never recorded its pids"
            time.sleep(0.05)
        _child_pid, writer_pid = (int(value) for value in pid_file.read_text().split())

        started = time.monotonic()
        assert wait_for_writer(writer_pid, capture, 5, 0.1) is True
        # The child sleeps 1 s; the writer exits at its EOF right after.
        assert time.monotonic() - started < 2.5
        state = subprocess.run(
            ["ps", "-p", str(writer_pid), "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        assert state.startswith("Z"), f"the writer is not a zombie: {state!r}"
    finally:
        parent.kill()
        parent.wait()


def _spawn_holding_child(supervisor: Supervisor) -> tuple[int, int, int]:
    """Spawn the holding child, reap it, and return its pid, writer and grandchild."""
    service = supervisor.runtime.services["echo"]
    pid, writer_pid = supervisor._spawn("echo", service, slot=5, detached=True)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    log_path = supervisor.log_path("echo")
    deadline = time.monotonic() + 10
    while not log_path.exists() or not log_path.read_text(encoding="utf-8"):
        assert time.monotonic() < deadline, "the holding child never printed"
        time.sleep(0.05)
    grandchild = int(log_path.read_text(encoding="utf-8").split()[0])
    return pid, writer_pid, grandchild


def _assert_killed(pid: int) -> None:
    _, status = os.waitpid(pid, 0)
    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL


def _kill_quietly(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def test_stop_raises_when_a_writer_outlives_its_service(tmp_path: Path) -> None:
    """A writer still held open after the grace is killed and the stop fails."""
    supervisor = _logging_supervisor(
        tmp_path,
        max_bytes=1000,
        backup_count=2,
        command=HOLDING_CHILD,
        stop_grace_seconds=1,
    )
    pid, writer_pid, grandchild = _spawn_holding_child(supervisor)
    try:
        supervisor._write_pidfile(
            "echo",
            {"pid": pid, "service": "echo", "port": 1, "log_writer_pid": writer_pid},
        )

        with pytest.raises(
            RuntimeError_, match=f"Log writer for 'echo' \\(pid {writer_pid}\\)"
        ):
            supervisor._stop_service("echo")

        _assert_killed(writer_pid)
    finally:
        _kill_quietly(grandchild)


def test_start_waits_for_a_stale_records_writer(tmp_path: Path) -> None:
    """up over a stale pidfile waits for its writer before spawning anything."""
    supervisor = _logging_supervisor(
        tmp_path,
        max_bytes=1000,
        backup_count=2,
        command=HOLDING_CHILD,
        stop_grace_seconds=1,
    )
    pid, writer_pid, grandchild = _spawn_holding_child(supervisor)
    try:
        supervisor._write_pidfile(
            "echo",
            {"pid": pid, "service": "echo", "port": 1, "log_writer_pid": writer_pid},
        )
        service = supervisor.runtime.services["echo"]
        service.command = list(ECHO_COMMAND)
        service.env["ECHO_RUN"] = "late"

        with pytest.raises(
            RuntimeError_, match=f"Log writer for 'echo' \\(pid {writer_pid}\\)"
        ):
            supervisor._start_service("echo", service, slot=5, detached=True)

        assert supervisor._pidfile("echo").exists()
        log_path = supervisor.log_path("echo")
        assert "run-late" not in log_path.read_text(encoding="utf-8")
        _assert_killed(writer_pid)
    finally:
        _kill_quietly(grandchild)


# ---------------------------------------------------------------------------
# After the independent review (#842): probes, dead writers, snapshot bounds
# ---------------------------------------------------------------------------

SLEEPER_COMMAND = ["{python}", "-c", "import time; time.sleep(30)"]


def _free_port() -> int:
    """An OS-assigned loopback port nothing listens on once this returns."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _ps_directory(tmp_path: Path, kind: str) -> Path:
    """A PATH directory whose ps is missing, exits 1, or never answers."""
    directory = tmp_path / f"ps-{kind}"
    directory.mkdir()
    if kind == "exits-1":
        script = "#!/bin/sh\nexit 1\n"
    elif kind == "sleeps":
        script = "#!/bin/sh\nexec /bin/sleep 30\n"
    else:
        return directory
    stub = directory / "ps"
    stub.write_text(script)
    stub.chmod(0o755)
    return directory


def _reap_quietly(pid: int) -> None:
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


@pytest.mark.parametrize("kind", ["missing", "exits-1", "sleeps"])
def test_wait_for_writer_raises_when_the_probe_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """A ps that cannot answer is an error, never "the writer is gone"."""
    capture = tmp_path / "logs" / "held.log"
    runtime = Supervisor.from_config(_write_config(tmp_path)).runtime
    captured = spawn_captured(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        log_path=capture,
        logs=runtime.logs,
        health=runtime.health,
    )
    try:
        monkeypatch.setenv("PATH", str(_ps_directory(tmp_path, kind)))
        with pytest.raises(WriterProbeError) as raised:
            wait_for_writer(captured.writer_pid, capture, 0.5, 0.1)
        assert f"pid {captured.writer_pid}" in str(raised.value)
        assert str(capture) in str(raised.value)
        assert os.waitpid(captured.writer_pid, os.WNOHANG) == (0, 0)
        assert os.waitpid(captured.pid, os.WNOHANG) == (0, 0)
    finally:
        _kill_quietly(captured.pid)
        _reap_quietly(captured.pid)
        _reap_quietly(captured.writer_pid)


def test_stop_keeps_the_record_when_the_writer_probe_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_stop_service raises and keeps the pidfile; the live writer is untouched."""
    supervisor = _logging_supervisor(
        tmp_path,
        max_bytes=1000,
        backup_count=2,
        command=HOLDING_CHILD,
        stop_grace_seconds=1,
    )
    pid, writer_pid, grandchild = _spawn_holding_child(supervisor)
    try:
        supervisor._write_pidfile(
            "echo",
            {"pid": pid, "service": "echo", "port": 1, "log_writer_pid": writer_pid},
        )
        monkeypatch.setenv("PATH", str(_ps_directory(tmp_path, "missing")))
        with pytest.raises(RuntimeError_, match=f"pid {writer_pid}"):
            supervisor._stop_service("echo")
        assert supervisor._pidfile("echo").exists()
        assert os.waitpid(writer_pid, os.WNOHANG) == (0, 0)
    finally:
        _kill_quietly(grandchild)
        _reap_quietly(writer_pid)


def _spawn_sleeper_record(
    supervisor: Supervisor, *, detached: bool, with_writer: bool = True
) -> tuple[int, int]:
    """Spawn the 30 s sleeper as 'echo' and write its pidfile; return both pids."""
    service = supervisor.runtime.services["echo"]
    service.command = list(SLEEPER_COMMAND)
    pid, writer_pid = supervisor._spawn("echo", service, slot=5, detached=detached)
    record: dict[str, Any] = {
        "pid": pid,
        "service": "echo",
        "port": 1,
        "host": "127.0.0.1",
        "slot": 5,
        "started_at": "2026-10-01T00:00:00+00:00",
    }
    if with_writer:
        record["log_writer_pid"] = writer_pid
    supervisor._write_pidfile("echo", record)
    return pid, writer_pid


def test_check_children_stops_a_service_whose_writer_died(tmp_path: Path) -> None:
    """A live foreground service without its writer is stopped, loudly."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=2, stop_grace_seconds=1
    )
    pid, writer_pid = _spawn_sleeper_record(supervisor, detached=False)
    try:
        os.kill(writer_pid, signal.SIGKILL)
        _reap_quietly(writer_pid)
        services = {"echo": supervisor.runtime.services["echo"]}
        expected = (
            f"Log writer for 'echo' (pid {writer_pid}) died while the service "
            f"(pid {pid}) was running; its output had nowhere to go. Stopped the "
            "service."
        )
        with pytest.raises(RuntimeError_) as raised:
            supervisor._check_children(services, 5, {}, echo=False)
        assert str(raised.value) == expected
        _, status = os.waitpid(pid, 0)
        assert os.WIFSIGNALED(status)
        assert not supervisor._pidfile("echo").exists()
    finally:
        _kill_quietly(pid)
        _reap_quietly(pid)


def _json_status(
    supervisor: Supervisor,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(supervisor.config_path))
    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)
    monkeypatch.setattr(sys, "argv", ["nexus", "--json", "status"])
    assert cli.main() == 0
    return cast(dict[str, Any], json.loads(capsys.readouterr().out))


def test_status_reports_each_services_log_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """nexus status shows alive, then dead after a kill, and - for a legacy record."""
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=2, gateway_port=_free_port()
    )
    pid, writer_pid = _spawn_sleeper_record(supervisor, detached=True)
    try:
        echo = _json_status(supervisor, monkeypatch, capsys)["processes"]["echo"]
        assert (echo["state"], echo["log_writer"]) == ("running", "alive")

        os.kill(writer_pid, signal.SIGKILL)
        echo = _json_status(supervisor, monkeypatch, capsys)["processes"]["echo"]
        assert (echo["state"], echo["log_writer"]) == ("running", "dead")

        record = supervisor._read_pidfile("echo")
        assert record is not None
        del record["log_writer_pid"]
        supervisor._write_pidfile("echo", record)
        echo = _json_status(supervisor, monkeypatch, capsys)["processes"]["echo"]
        assert (echo["state"], echo["log_writer"]) == ("running", "-")
    finally:
        _kill_quietly(pid)
        _reap_quietly(pid)
        _reap_quietly(writer_pid)


def test_doctor_fails_a_live_service_without_its_writer(tmp_path: Path) -> None:
    """runtime.log_writers names the service and says to restart it by name."""
    supervisor = _logging_supervisor(tmp_path, max_bytes=1000, backup_count=2)
    registry = [
        spec for spec in REGISTRY if spec.id in {"config.valid", "runtime.log_writers"}
    ]

    def check() -> Any:
        report = run_readiness(
            "owner-host",
            ReadinessContext(config_path=supervisor.config_path),
            registry=registry,
        )
        return {result.id: result for result in report.checks}["runtime.log_writers"]

    pid, writer_pid = _spawn_sleeper_record(supervisor, detached=True)
    try:
        assert check().status == "pass"
        os.kill(writer_pid, signal.SIGKILL)
        failed = check()
        assert failed.status == "fail"
        assert failed.observed == (
            f"echo (pid {pid}) runs without its log writer (pid {writer_pid})"
        )
        assert failed.remediation == "Restart the service by name: nexus restart echo"
    finally:
        _kill_quietly(pid)
        _reap_quietly(pid)
        _reap_quietly(writer_pid)


def test_logs_since_empty_mark_rechecks_retention_after_the_wait(
    tmp_path: Path,
) -> None:
    """Retention filled during the snapshot's wait raises, not three lines."""
    supervisor = _logging_supervisor(
        tmp_path,
        max_bytes=1000,
        backup_count=2,
        stop_grace_seconds=10,
        poll_interval_seconds=0.05,
    )
    log_path = supervisor.log_path("echo")
    # The writer just renamed the current file: .1 holds lines 1-2, no .2.
    _write_lines(rotated_segment(log_path, 1), ["line-1", "line-2"])

    def rotate_twice() -> None:
        # Two more rotations push lines 1-2 out of retention.
        time.sleep(0.4)
        for target, line in (
            (rotated_segment(log_path, 2), "line-3"),
            (rotated_segment(log_path, 1), "line-4"),
            (log_path, "line-5"),
        ):
            staged = log_path.with_name("staged.tmp")
            staged.write_text(f"{line}\n", encoding="utf-8")
            staged.replace(target)

    rotation = threading.Thread(target=rotate_twice)
    rotation.start()
    try:
        with pytest.raises(RuntimeError_, match="Log mark 0:0:0 names no capture"):
            supervisor.logs_since("echo", "0:0:0")
    finally:
        rotation.join()


def test_open_segments_deadline_bounds_identity_churn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Segments that keep changing identity raise within the grace plus a poll."""
    log_path = tmp_path / "churn.log"
    _write_lines(log_path, ["first"])
    real_open = open

    def churning_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        handle = real_open(path, *args, **kwargs)
        if Path(path) == log_path:
            staged = tmp_path / "churn.tmp"
            staged.write_text("replaced\n", encoding="utf-8")
            staged.replace(log_path)
        return handle

    monkeypatch.setattr(supervisor_module, "open", churning_open, raising=False)
    grace, poll = 1.0, 0.1
    outcome: dict[str, Any] = {}

    def snapshot() -> None:
        started = time.monotonic()
        try:
            outcome["handles"] = _open_segments(log_path, 2, grace, poll)
        except RuntimeError_ as exc:
            outcome["error"] = exc
        outcome["elapsed"] = time.monotonic() - started

    worker = threading.Thread(target=snapshot, daemon=True)
    worker.start()
    worker.join(timeout=grace + poll + 5)
    assert not worker.is_alive(), "the snapshot retried past its deadline"
    for handle in outcome.get("handles", []):
        handle.close()
    assert outcome["elapsed"] <= grace + poll + 0.5
    assert "kept changing identity" in str(outcome["error"])
    assert str(log_path) in str(outcome["error"])


# ---------------------------------------------------------------------------
# After the second independent review (#842): reaping, records, failed spawns
# ---------------------------------------------------------------------------

# Prints one line. Without its marker file it creates the marker and exits 0;
# with the marker it serves 200 on GET at the {port} argument until stopped.
ONE_LINE_CHILD = [
    "{python}",
    "-c",
    "import http.server, os, pathlib, sys\n"
    "print('one-line', flush=True)\n"
    "marker = pathlib.Path(os.environ['ECHO_MARKER'])\n"
    "if not marker.exists():\n"
    "    marker.touch()\n"
    "    sys.exit(0)\n"
    "class Health(http.server.BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        self.send_response(200)\n"
    "        self.end_headers()\n"
    "    def log_message(self, *args):\n"
    "        pass\n"
    "http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), Health)"
    ".serve_forever()\n",
    "{port}",
]
EXITS_AT_ONCE = ["{python}", "-c", "raise SystemExit(3)"]


def _ps_state(pid: int) -> str:
    """The ps state of ``pid``, probed without the subprocess module.

    Each new subprocess.Popen first reaps the exited children of discarded
    Popen objects (spawn_captured discards both of its own), so a probe made
    through subprocess would collect the very zombie this test needs.
    """
    read_fd, write_fd = os.pipe()
    try:
        probe = os.posix_spawn(
            "/bin/ps",
            ["ps", "-p", str(pid), "-o", "stat="],
            os.environ,
            file_actions=[
                (os.POSIX_SPAWN_DUP2, write_fd, 1),
                (os.POSIX_SPAWN_CLOSE, read_fd),
            ],
        )
    finally:
        os.close(write_fd)
    with os.fdopen(read_fd, "rb") as handle:
        output = handle.read()
    os.waitpid(probe, 0)
    return output.decode().strip()


def _wait_for_zombie(pid: int) -> None:
    """Wait until an unreaped child of this process has exited, without reaping."""
    deadline = time.monotonic() + 10
    while True:
        state = _ps_state(pid)
        if state.startswith("Z"):
            return
        assert time.monotonic() < deadline, f"pid {pid} never exited: {state!r}"
        time.sleep(0.05)


def _live_writers(log_path: Path) -> list[int]:
    """Pids of live (non-zombie) log writers of ``log_path``, from the real ps."""
    listing = subprocess.run(
        ["/bin/ps", "-ax", "-ww", "-o", "pid=,stat=,command="],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    writers = []
    for line in listing.splitlines():
        pid, stat, command = line.split(None, 2)
        if stat.startswith("Z"):
            continue
        if "nexus.runtime.log_capture" in command and f"--path {log_path} " in command:
            writers.append(int(pid))
    return writers


def _one_line_supervisor(tmp_path: Path) -> Supervisor:
    """A supervisor whose 'echo' is the one-line child, restartable once."""
    supervisor = _logging_supervisor(
        tmp_path,
        max_bytes=1000,
        backup_count=2,
        command=ONE_LINE_CHILD,
        stop_grace_seconds=1,
    )
    service = supervisor.runtime.services["echo"]
    service.port = _free_port()
    service.autorestart = "on-failure"
    service.autorestart_max_retries = 1
    service.env["ECHO_MARKER"] = str(tmp_path / "marker")
    return supervisor


def _write_spawn_record(supervisor: Supervisor, pid: int, writer_pid: int) -> None:
    supervisor._write_pidfile(
        "echo",
        {
            "pid": pid,
            "service": "echo",
            "port": supervisor.runtime.services["echo"].port,
            "host": "127.0.0.1",
            "slot": 5,
            "started_at": "2026-10-01T00:00:00+00:00",
            "log_writer_pid": writer_pid,
        },
    )


def test_check_children_restarts_an_unreaped_service_exit(tmp_path: Path) -> None:
    """An exited foreground child is reaped first and autorestarts, silently."""
    supervisor = _one_line_supervisor(tmp_path)
    service = supervisor.runtime.services["echo"]
    pid, writer_pid = supervisor._spawn("echo", service, slot=5, detached=False)
    _write_spawn_record(supervisor, pid, writer_pid)
    restarted: dict[str, Any] | None = None
    try:
        # Both have exited and neither is reaped: the child still answers
        # kill(pid, 0), and its writer drained and exited normally.
        _wait_for_zombie(pid)
        _wait_for_zombie(writer_pid)
        restarts: dict[str, int] = {}

        supervisor._check_children({"echo": service}, 5, restarts, echo=False)

        assert restarts == {"echo": 1}
        restarted = supervisor._read_pidfile("echo")
        assert restarted is not None
        assert restarted["pid"] != pid
        log_path = supervisor.log_path("echo")
        deadline = time.monotonic() + 10
        while log_path.read_text(encoding="utf-8") != "one-line\none-line\n":
            assert time.monotonic() < deadline, log_path.read_text(encoding="utf-8")
            time.sleep(0.05)
    finally:
        _reap_quietly(pid)
        _reap_quietly(writer_pid)
        if restarted is not None:
            supervisor._stop_service("echo")
            _reap_quietly(int(restarted["pid"]))


def test_check_children_still_fails_a_live_child_without_its_writer(
    tmp_path: Path,
) -> None:
    """The same child, running, with its writer killed, is a capture failure."""
    supervisor = _one_line_supervisor(tmp_path)
    (tmp_path / "marker").touch()
    service = supervisor.runtime.services["echo"]
    pid, writer_pid = supervisor._spawn("echo", service, slot=5, detached=False)
    _write_spawn_record(supervisor, pid, writer_pid)
    try:
        os.kill(writer_pid, signal.SIGKILL)
        _reap_quietly(writer_pid)
        expected = (
            f"Log writer for 'echo' (pid {writer_pid}) died while the service "
            f"(pid {pid}) was running; its output had nowhere to go. Stopped the "
            "service."
        )
        with pytest.raises(RuntimeError_) as raised:
            supervisor._check_children({"echo": service}, 5, {}, echo=False)
        assert str(raised.value) == expected
        assert not supervisor._pidfile("echo").exists()
    finally:
        _kill_quietly(pid)
        _reap_quietly(pid)


def _only_echo_enabled(supervisor: Supervisor, command: list[str]) -> None:
    for name, service in supervisor.runtime.services.items():
        service.enabled = "always" if name == "echo" else "never"
    supervisor.runtime.services["echo"].command = list(command)


def test_up_leaves_no_record_and_no_writer_when_a_service_exits_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start that fails cleanly unlinks its record once the writer drained."""
    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=2, stop_grace_seconds=1
    )
    _only_echo_enabled(supervisor, EXITS_AT_ONCE)

    with pytest.raises(RuntimeError_, match="'echo' exited during startup"):
        supervisor.up(echo=False)

    assert not supervisor._pidfile("echo").exists()
    assert _live_writers(supervisor.log_path("echo")) == []


def test_failed_start_keeps_the_record_when_the_writer_probe_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record outlives an unanswered probe; a second start spawns nothing."""
    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    supervisor = _logging_supervisor(
        tmp_path, max_bytes=1000, backup_count=2, stop_grace_seconds=1
    )
    _only_echo_enabled(supervisor, HOLDING_CHILD)
    log_path = supervisor.log_path("echo")
    real_path = os.environ["PATH"]
    grandchild: int | None = None
    writer_pid: int | None = None
    try:
        monkeypatch.setenv("PATH", str(_ps_directory(tmp_path, "missing")))
        with pytest.raises(RuntimeError_, match="Cannot tell whether pid") as raised:
            supervisor.up(echo=False)
        record = supervisor._read_pidfile("echo")
        assert record is not None
        writer_pid = int(record["log_writer_pid"])
        assert f"pid {writer_pid}" in str(raised.value)
        # This start never returned its record, so up() does not own a
        # successful start to roll back or retry the failed writer probe.
        assert not getattr(raised.value, "__notes__", [])
        deadline = time.monotonic() + 10
        while not log_path.read_text(encoding="utf-8").endswith("\n"):
            assert time.monotonic() < deadline, "the holding child never printed"
            time.sleep(0.05)
        grandchild = int(log_path.read_text(encoding="utf-8").split()[0])

        service = supervisor.runtime.services["echo"]
        with pytest.raises(
            RuntimeError_, match=f"Cannot tell whether pid {writer_pid}"
        ):
            supervisor._start_service("echo", service, slot=5, detached=True)

        monkeypatch.setenv("PATH", real_path)
        assert _live_writers(log_path) == [writer_pid]
        assert supervisor._read_pidfile("echo") == record
    finally:
        monkeypatch.setenv("PATH", real_path)
        if grandchild is not None:
            _kill_quietly(grandchild)
        if writer_pid is not None:
            _reap_quietly(writer_pid)


def test_failed_child_spawn_waits_out_its_writer(tmp_path: Path) -> None:
    """A child that cannot start leaves no writer behind, and no writer error."""
    runtime = Supervisor.from_config(_write_config(tmp_path)).runtime
    capture = tmp_path / "logs" / "missing.log"

    with pytest.raises(FileNotFoundError):
        spawn_captured(
            [str(tmp_path / "no-such-executable")],
            log_path=capture,
            logs=runtime.logs,
            health=runtime.health,
        )

    assert _live_writers(capture) == []
    assert writer_error_path(capture).read_bytes() == b""


# ---------------------------------------------------------------------------
# After the third independent review (#842): ownership and exit races
# ---------------------------------------------------------------------------


def _managed_echo(tmp_path: Path) -> Supervisor:
    """An isolated health-serving echo on the fixture's OS-assigned port."""
    supervisor = _logging_supervisor(
        tmp_path,
        max_bytes=1000,
        backup_count=2,
        command=ONE_LINE_CHILD,
        stop_grace_seconds=1,
        poll_interval_seconds=0.05,
    )
    _only_echo_enabled(supervisor, ONE_LINE_CHILD)
    service = supervisor.runtime.services["echo"]
    service.port = live_helpers.GATEWAY_PORT
    service.env["ECHO_MARKER"] = str(tmp_path / "marker")
    (tmp_path / "marker").touch()
    return supervisor


def test_up_abandons_a_service_whose_pidfile_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real failed write leaves neither spawned process running nor a record."""
    supervisor = _managed_echo(tmp_path)
    log_path = supervisor.log_path("echo")
    log_path.write_bytes(b"")
    writer_error_path(log_path).write_bytes(b"")
    spawned: list[tuple[int, int]] = []
    spawn = supervisor._spawn

    def observe_spawn(
        name: str, service: RuntimeServiceSettings, slot: int, detached: bool
    ) -> tuple[int, int]:
        pids = spawn(name, service, slot, detached)
        spawned.append(pids)
        return pids

    monkeypatch.setattr(supervisor, "_spawn", observe_spawn)
    supervisor.state_dir.chmod(0o555)
    try:
        with pytest.raises(PermissionError):
            supervisor.up(slot=5, echo=False)
        assert len(spawned) == 1
        pid, writer_pid = spawned[0]
        assert not process_running(pid), f"service pid {pid} is still running"
        assert not process_running(
            writer_pid
        ), f"writer pid {writer_pid} is still running"
        assert _ps_state(pid) == ""
        assert _ps_state(writer_pid) == ""
        assert not supervisor._pidfile("echo").exists()
    finally:
        supervisor.state_dir.chmod(0o755)
        for pids in spawned:
            for pid in pids:
                _kill_quietly(pid)
                _reap_quietly(pid)


@pytest.mark.parametrize("concurrent", (False, True), ids=("existing", "concurrent"))
def test_refused_up_preserves_another_invocations_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, concurrent: bool
) -> None:
    """Refusal preserves even a record created after this up() began."""
    refused = _managed_echo(tmp_path)
    owner = Supervisor.from_config(refused.config_path)
    owner.runtime.services = {
        name: service.model_copy(deep=True)
        for name, service in refused.runtime.services.items()
    }
    original_start = refused._start_service
    record: dict[str, Any] | None = None

    def start_after_owner(
        name: str, service: RuntimeServiceSettings, slot: int, detached: bool
    ) -> dict[str, Any]:
        nonlocal record
        # Deterministic interleaving at the real _start_service boundary.
        # Under the old rollback, the earlier snapshot has already been taken.
        owner.up(slot=5, echo=False)
        record = owner._read_pidfile("echo")
        return original_start(name, service, slot, detached)

    try:
        if concurrent:
            monkeypatch.setattr(refused, "_start_service", start_after_owner)
        else:
            owner.up(slot=5, echo=False)
            record = owner._read_pidfile("echo")
        with pytest.raises(RuntimeError_, match="'echo' is already running"):
            refused.up(slot=5, echo=False)
        assert record is not None
        assert refused._read_pidfile("echo") == record
        assert process_running(int(record["pid"]))
        assert owner._writer_alive("echo", int(record["log_writer_pid"]))
        assert owner._probe(f"http://127.0.0.1:{live_helpers.GATEWAY_PORT}/health")
    finally:
        if record is not None:
            owner._abandon_service(
                "echo", int(record["pid"]), int(record["log_writer_pid"])
            )
            owner._pidfile("echo").unlink(missing_ok=True)
            _reap_quietly(int(record["pid"]))


def test_up_rolls_back_only_its_successfully_started_pids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second service's startup failure cleans it and rolls back the first."""
    supervisor = _managed_echo(tmp_path)
    service = supervisor.runtime.services["echo"].model_copy(deep=True)
    service.command = list(EXITS_AT_ONCE)
    service.port = live_helpers.MOCK_PORT
    supervisor.runtime.services["fails"] = service
    spawned: dict[str, tuple[int, int]] = {}
    spawn = supervisor._spawn

    def observe_spawn(
        name: str, service: RuntimeServiceSettings, slot: int, detached: bool
    ) -> tuple[int, int]:
        pids = spawn(name, service, slot, detached)
        spawned[name] = pids
        return pids

    monkeypatch.setattr(supervisor, "_spawn", observe_spawn)
    try:
        with pytest.raises(RuntimeError_, match="'fails' exited during startup"):
            supervisor.up(slot=5, echo=False)
        assert set(spawned) == {"echo", "fails"}
        for name, (pid, writer_pid) in spawned.items():
            assert not process_running(pid)
            assert not process_running(writer_pid)
            assert not supervisor._pidfile(name).exists()
    finally:
        for pids in spawned.values():
            for pid in pids:
                _kill_quietly(pid)
                _reap_quietly(pid)


def test_check_children_restarts_a_service_that_exits_during_the_writer_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real exit after the first liveness check still reaches autorestart."""
    supervisor = _managed_echo(tmp_path)
    service = supervisor.runtime.services["echo"]
    service.autorestart = "on-failure"
    service.autorestart_max_retries = 1
    release = tmp_path / "release"
    # The first child waits until the writer probe releases it. The restarted
    # child takes the other branch and serves the real health endpoint.
    first_run = tmp_path / "first-run"
    service.env["FIRST_RUN"] = str(first_run)
    service.env["RELEASE"] = str(release)
    service.command = [
        "{python}",
        "-c",
        "import os, pathlib, time\n"
        "first = pathlib.Path(os.environ['FIRST_RUN'])\n"
        "if not first.exists():\n"
        "    first.touch()\n"
        "    print('one-line', flush=True)\n"
        "    while not pathlib.Path(os.environ['RELEASE']).exists():\n"
        "        time.sleep(0.01)\n"
        "else:\n"
        f"    exec({ONE_LINE_CHILD[2]!r})\n",
        "{port}",
    ]
    pid, writer_pid = supervisor._spawn("echo", service, slot=5, detached=False)
    _write_spawn_record(supervisor, pid, writer_pid)
    real_writer_alive = supervisor._writer_alive
    restarted: dict[str, Any] | None = None
    checked = False

    def probe_after_exit(name: str, writer: int) -> bool:
        nonlocal checked
        assert writer == writer_pid
        checked = True
        # _child_capture_state already checked the still-running child.
        release.touch()
        _wait_for_zombie(pid)
        _wait_for_zombie(writer_pid)
        return real_writer_alive(name, writer)

    monkeypatch.setattr(supervisor, "_writer_alive", probe_after_exit)
    try:
        restarts: dict[str, int] = {}
        supervisor._check_children({"echo": service}, 5, restarts, echo=False)
        assert checked
        assert restarts == {"echo": 1}
        restarted = supervisor._read_pidfile("echo")
        assert restarted is not None
        assert restarted["pid"] != pid
        assert process_running(int(restarted["pid"]))
        deadline = time.monotonic() + supervisor.runtime.health.stop_grace_seconds
        while list(supervisor.logs("echo", lines=2)) != ["one-line", "one-line"]:
            assert time.monotonic() < deadline, "the restarted writer never drained"
            time.sleep(supervisor.runtime.health.poll_interval_seconds)
        assert list(supervisor.logs("echo", lines=2)) == ["one-line", "one-line"]
    finally:
        # On a red run _check_children raises after deleting the old record.
        current = supervisor._read_pidfile("echo")
        if current is not None and int(current["pid"]) != pid:
            restarted = current
        if restarted is not None:
            supervisor._abandon_service(
                "echo", int(restarted["pid"]), int(restarted["log_writer_pid"])
            )
            supervisor._pidfile("echo").unlink(missing_ok=True)
            _reap_quietly(int(restarted["pid"]))
        for process in (pid, writer_pid):
            _kill_quietly(process)
            _reap_quietly(process)
