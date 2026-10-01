"""Unit coverage for managed-runtime configuration selection and log capture."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, cast

import pytest
import tomlkit

from nexus import cli
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.log_capture import wait_for_writer, writer_error_path
from nexus.runtime.supervisor import (
    RuntimeError_,
    _LogFollower,
    _tail_lines,
    rotated_segment,
)


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
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from nexus.config.settings_models import RuntimeLogsSettings\n"
        "from nexus.runtime.log_capture import spawn_captured\n"
        "captured = spawn_captured(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(30)'],\n"
        "    log_path=Path(sys.argv[1]),\n"
        "    logs=RuntimeLogsSettings(),\n"
        "    popen_kwargs={'start_new_session': True},\n"
        ")\n"
        "print(captured.pid, captured.writer_pid)\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    pids: list[int] = []
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script, str(capture)],
            capture_output=True,
            timeout=10,
            cwd=REPO_ROOT,
            env=env,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        pids = [int(value) for value in completed.stdout.split()]
        assert len(pids) == 2
        assert writer_error_path(capture).exists()
    finally:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


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
