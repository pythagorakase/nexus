"""One log-writer process per captured stream (issue #842).

A captured service never writes its log file itself. ``spawn_captured`` starts
a writer process (``python -m nexus.runtime.log_capture``) whose stdin is a
pipe, then starts the service with that pipe as its stdout and stderr. The
writer is the only process that holds the file: it appends each line, and
before a line that would take the file past ``[runtime.logs].max_bytes`` it
renames ``<name>.log`` to ``<name>.log.1`` (older segments shift up to
``backup_count``; the oldest is dropped) and opens a fresh file. So a
long-running service's capture is bounded while it runs, not only at its next
spawn.

The writer runs in a session of its own and ignores SIGINT and SIGTERM: a
group signal to the service never reaches it, and it ends only at EOF, when
every process holding the pipe has exited, so it never drops a buffered line.
Its own errors go to ``<name>.log.writer-error`` beside the capture.

Whoever stops a captured service waits for its writer with
``wait_for_writer`` before reading the capture's last lines or starting a new
writer on the same file, so two writers never hold one file.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Dict, List, Mapping, Optional, Sequence

from nexus.config.settings_models import RuntimeLogsSettings
from nexus.runtime.home import repo_root

WRITER_MODULE = "nexus.runtime.log_capture"
WRITER_ERROR_SUFFIX = ".writer-error"


def rotated_segment(path: Path, index: int) -> Path:
    """The ``index``-th rotated segment of a captured log (``<name>.log.N``)."""
    if index < 1:
        raise ValueError(f"Rotated segment index must be >= 1, got {index}")
    return path.with_name(f"{path.name}.{index}")


def writer_error_path(log_path: Path) -> Path:
    """The file that receives a capture's writer's own stderr."""
    return log_path.with_name(f"{log_path.name}{WRITER_ERROR_SUFFIX}")


def rotate_segments(path: Path, backup_count: int) -> None:
    """Rename ``path`` to ``.1`` after shifting ``.1 .. .backup_count-1`` up one.

    Replacing ``.backup_count`` drops the oldest segment. Only the writer that
    owns ``path`` calls this, with its handle on ``path`` closed; it then opens
    a fresh file.
    """
    for index in range(backup_count - 1, 0, -1):
        source = rotated_segment(path, index)
        if source.exists():
            source.replace(rotated_segment(path, index + 1))
    path.replace(rotated_segment(path, 1))


def pid_alive(pid: int) -> bool:
    """Cross-platform process liveness check (never signals the process)."""
    if os.name == "nt":  # pragma: no cover - exercised on Windows hosts only
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return bool(ok) and exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------------------
# The writer process
# ---------------------------------------------------------------------------


def run_writer(
    path: Path, max_bytes: int, backup_count: int, source: IO[bytes]
) -> None:
    """Copy ``source`` into ``path`` line by line, rotating under the policy.

    At start, a file already holding at least ``max_bytes`` is rotated first.
    Before the first piece of each line, when the file is not empty and the
    piece would take it past ``max_bytes``, the file is rotated. A line is
    never split across segments: one longer than ``max_bytes`` fills a
    segment of its own. Reads are bounded by ``max_bytes`` per piece. Each
    write is flushed. At EOF a trailing fragment is written unchanged. A
    write or rename error raises.
    """
    handle = open(path, "ab")
    try:
        size = os.fstat(handle.fileno()).st_size
        if size >= max_bytes:
            handle.close()
            rotate_segments(path, backup_count)
            handle = open(path, "ab")
            size = 0
        at_line_start = True
        while True:
            piece = source.readline(max_bytes)
            if not piece:
                break
            if at_line_start and size > 0 and size + len(piece) > max_bytes:
                handle.close()
                rotate_segments(path, backup_count)
                handle = open(path, "ab")
                size = 0
            handle.write(piece)
            handle.flush()
            size += len(piece)
            at_line_start = piece.endswith(b"\n")
    finally:
        handle.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point of ``python -m nexus.runtime.log_capture``."""
    # The writer ends only at EOF, so it never drops a buffered line.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    parser = argparse.ArgumentParser(prog=f"python -m {WRITER_MODULE}")
    parser.add_argument("--path", required=True)
    parser.add_argument("--max-bytes", required=True, type=int)
    parser.add_argument("--backup-count", required=True, type=int)
    arguments = parser.parse_args(argv)
    if arguments.max_bytes < 1:
        parser.error("--max-bytes must be a positive byte count")
    if arguments.backup_count < 1:
        parser.error("--backup-count must be at least 1")
    run_writer(
        Path(arguments.path),
        arguments.max_bytes,
        arguments.backup_count,
        sys.stdin.buffer,
    )
    return 0


# ---------------------------------------------------------------------------
# Spawning a captured process
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapturedProcess:
    """A spawned process and the writer that owns its captured output."""

    pid: int
    writer_pid: int


def _writer_argv(log_path: Path, logs: RuntimeLogsSettings) -> List[str]:
    return [
        sys.executable,
        # The nexus.runtime package imports this module before runpy runs it
        # as __main__, and runpy warns about that on stderr. The warning is
        # harmless here; silenced, the .writer-error file stays empty unless
        # the writer fails.
        "-W",
        f"ignore:'{WRITER_MODULE}' found in sys.modules:RuntimeWarning",
        "-m",
        WRITER_MODULE,
        "--path",
        str(log_path),
        "--max-bytes",
        str(logs.max_bytes),
        "--backup-count",
        str(logs.backup_count),
    ]


def spawn_captured(
    argv: Sequence[str],
    *,
    log_path: Path,
    logs: RuntimeLogsSettings,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[Path] = None,
    popen_kwargs: Optional[Dict[str, Any]] = None,
) -> CapturedProcess:
    """Start ``argv`` with its stdout and stderr captured by a log writer.

    The writer starts first, in a session of its own, with the capture's
    ``.writer-error`` file as its stderr (never a pipe of the caller's). The
    child then gets the writer's stdin pipe as stdout and stderr, and the
    caller's end of the pipe is closed, so the writer reaches EOF when the
    child (and anything it left holding the pipe) exits. If the child cannot
    be started, the writer reaches EOF at once and the error is re-raised.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = repo_root()
    writer_env = dict(os.environ)
    writer_env["PYTHONPATH"] = os.pathsep.join(
        [str(root)]
        + ([writer_env["PYTHONPATH"]] if writer_env.get("PYTHONPATH") else [])
    )
    writer_session: Dict[str, Any] = {"start_new_session": True}
    if os.name != "posix":  # pragma: no cover - Windows host path
        new_group = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        writer_session = {"creationflags": new_group}
    with open(writer_error_path(log_path), "ab") as error_handle:
        writer = subprocess.Popen(
            _writer_argv(log_path, logs),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=error_handle,
            cwd=root,
            env=writer_env,
            **writer_session,
        )
    assert writer.stdin is not None
    try:
        child = subprocess.Popen(
            list(argv),
            stdout=writer.stdin,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=None if env is None else dict(env),
            cwd=cwd,
            **(popen_kwargs or {}),
        )
    finally:
        writer.stdin.close()
    return CapturedProcess(pid=child.pid, writer_pid=writer.pid)


# ---------------------------------------------------------------------------
# Waiting for a writer
# ---------------------------------------------------------------------------


class WriterProbeError(RuntimeError):
    """The identity probe of a log writer could not run; it certifies nothing."""


def _child_state(pid: int) -> Optional[bool]:
    """Reap ``pid`` when it is an exited child of this process (POSIX).

    Returns None when ``pid`` is not a child of this process (only its parent
    can reap it), True when it is a running child, and False when it was an
    exited child, now collected.
    """
    if os.name != "posix":  # pragma: no cover - Windows host path
        return None
    try:
        reaped, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return None
    return reaped == 0


def _reap(pid: int) -> bool:
    """Collect ``pid`` when it is an exited child of this process (POSIX).

    Returns whether ``pid`` was a child of this process: only then can this
    process reap it.
    """
    return _child_state(pid) is not None


def _is_writer_for(pid: int, log_path: Path, timeout_seconds: float) -> bool:
    """True when ``pid``'s command line is the writer of ``log_path``.

    Only a probe that ran certifies anything. A ``ps`` that cannot be started,
    that exits non-zero while the pid is still alive, or that outlasts
    ``timeout_seconds`` raises ``WriterProbeError``: an unanswered probe never
    counts as "not the writer". A non-zero exit for a pid that has meanwhile
    gone is the probe's answer that no such process exists.
    """
    failure = f"Cannot tell whether pid {pid} is the log writer of {log_path}"
    try:
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise WriterProbeError(f"{failure}: ps could not be started ({exc}).") from exc
    except subprocess.TimeoutExpired as exc:
        raise WriterProbeError(
            f"{failure}: ps did not answer within {timeout_seconds}s."
        ) from exc
    except OSError as exc:
        raise WriterProbeError(f"{failure}: ps could not be run ({exc}).") from exc
    if result.returncode != 0:
        if not pid_alive(pid):
            return False
        raise WriterProbeError(
            f"{failure}: ps exited {result.returncode} while the pid is alive."
        )
    command = result.stdout.strip()
    return WRITER_MODULE in command and f"--path {log_path} " in command


def writer_alive(pid: int, log_path: Path, timeout_seconds: float) -> bool:
    """Whether ``pid`` is still the live log writer of ``log_path``.

    An exited child of this process is reaped first and counts as dead. A
    running child of this process still holds its pid (no unreaped pid is
    ever recycled), so it is the recorded writer. Any other live pid is the
    writer only when its command line names this file; a probe that cannot
    run raises ``WriterProbeError``. On Windows, liveness alone decides.
    """
    own = _child_state(pid)
    if own is not None:
        return own
    if not pid_alive(pid):
        return False
    if os.name != "posix":  # pragma: no cover - Windows host path
        return True
    return _is_writer_for(pid, log_path, timeout_seconds)


def wait_for_writer(
    pid: int, log_path: Path, timeout_seconds: float, poll_seconds: float
) -> bool:
    """Wait until the writer ``pid`` of ``log_path`` is gone.

    Returns True once the pid is gone or has exited (a zombie that another
    live process has not reaped yet), or at once when the pid is not this
    file's writer (a recycled pid is never waited on and never signalled).
    Returns False when the writer is still alive after ``timeout_seconds``:
    something still holds the captured process's output. Raises
    ``WriterProbeError`` when the identity probe cannot run: a probe that
    cannot answer never certifies that the writer is gone.
    """
    own_child = _reap(pid)
    if not pid_alive(pid):
        return True
    if os.name == "posix" and not _is_writer_for(pid, log_path, timeout_seconds):
        # An own writer that exited during the probe is a zombie whose command
        # line no longer names this file: collect it before reporting it gone.
        if own_child:
            _reap(pid)
        return True
    deadline = time.monotonic() + timeout_seconds
    while True:
        own_child = _reap(pid)
        if not pid_alive(pid):
            return True
        # Only the writer's parent can reap it. When that parent is another
        # live process, the exited writer stays a zombie that answers
        # kill(pid, 0); its command line no longer names this file.
        if (
            os.name == "posix"
            and not own_child
            and not _is_writer_for(pid, log_path, timeout_seconds)
        ):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_seconds)


def kill_writer(pid: int) -> None:
    """Kill one writer that ``wait_for_writer`` confirmed and that outlived it.

    Never call this after ``WriterProbeError``: an unconfirmed pid is never
    signalled.
    """
    kill_sig = signal.SIGKILL if os.name == "posix" else signal.SIGTERM
    try:
        os.kill(pid, kill_sig)
    except ProcessLookupError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
