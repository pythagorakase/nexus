"""Managed runtime supervisor: nexus up / down / restart / status / logs.

Pure-Python, cross-platform process management (issue #396). No bash in the
runtime path, no UNIX sockets — services are spawned directly from argv
templates and observed over loopback TCP. Process state lives in JSON
pidfiles and captured log files under [runtime].state_dir.

Profiles (configured in nexus.toml [runtime]):

- ``local``    — spawn and manage the services in [runtime.services.*]
- ``external`` — attach to already-running services: health-check and status
                 only; never spawns or stops anything
- ``remote``   — a hosted runtime; status hits <base_url>/runtime/status
"""

from __future__ import annotations

import json
import os
import signal
import socket
import string
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import requests

from nexus.config import load_settings
from nexus.config.settings_models import (
    RuntimeServiceSettings,
    RuntimeSettings,
    Settings,
)
from nexus.runtime.contract import (
    GATEWAY_PORT_ENV,
    RUNTIME_CONFIG_ENV,
    RUNTIME_STATUS_PATH,
    gateway_port_override,
)
from nexus.runtime.logging_config import build_logging_config
from nexus.runtime.remote_auth import build_runtime_request_auth

LOG_CONFIG_PLACEHOLDER = "log_config"
LOG_CONFIG_FILENAME = "logging.json"
_TAIL_BLOCK_BYTES = 64 * 1024


class RuntimeError_(Exception):
    """Supervisor-level failure with a user-facing message."""


def repo_root() -> Path:
    """The repository root, derived from the nexus package location."""
    return Path(__file__).resolve().parents[2]


def _pid_alive(pid: int) -> bool:
    """Cross-platform process liveness check (never signals the process)."""
    if os.name == "nt":  # pragma: no cover - exercised on Windows hosts only
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
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


def _signal_pid(pid: int, sig: int) -> None:
    """Deliver a signal to the service's process group (POSIX) or process."""
    if os.name == "nt":  # pragma: no cover - Windows: TerminateProcess semantics
        os.kill(pid, sig)
        return
    try:
        # Detached services run in their own session (start_new_session=True),
        # so the group id equals the pid; signaling the group reaches any
        # workers the service forked.
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        os.kill(pid, sig)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _describe_port_occupant(port: int) -> Optional[str]:
    """Best-effort identity of the process listening on a local port.

    Diagnostics only: returns ``"pid=<pid> elapsed=<etime> <command>"`` via
    lsof+ps on POSIX hosts, or None when the tools are unavailable or the
    listener cannot be resolved. Never raises.
    """
    if os.name != "posix":  # pragma: no cover - Windows host path
        return None
    try:
        lsof = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = lsof.stdout.split()
        if not pids:
            return None
        ps = subprocess.run(
            ["ps", "-o", "pid=,etime=,command=", "-p", pids[0]],
            capture_output=True,
            text=True,
            timeout=5,
        )
        described = " ".join(ps.stdout.split())
        if not described:
            return None
        parts = described.split(" ", 2)
        if len(parts) < 2:
            # A process that exited between the lsof snapshot and the ps
            # call can leave a truncated line; diagnostics never raise.
            return None
        command = parts[2] if len(parts) == 3 else ""
        return f"pid={parts[0]} elapsed={parts[1]} {command}".rstrip()
    except (OSError, subprocess.SubprocessError):
        return None


def _template_fields(command: List[str]) -> Set[str]:
    """Placeholder names referenced by an argv template."""
    return {
        field
        for part in command
        for _, field, _, _ in string.Formatter().parse(part)
        if field
    }


def rotated_segment(path: Path, index: int) -> Path:
    """The ``index``-th rotated segment of a captured log (``<name>.log.N``)."""
    if index < 1:
        raise ValueError(f"Rotated segment index must be >= 1, got {index}")
    return path.with_name(f"{path.name}.{index}")


def _rotate_log(path: Path, max_bytes: int, backup_count: int) -> bool:
    """Rotate a captured log at spawn once it has reached ``max_bytes``.

    Shifts ``.1 .. .backup_count-1`` up by one (replacing, and so dropping,
    the oldest ``.backup_count``) and renames the current file to ``.1``; the
    caller then opens a fresh file. Returns True when a rotation happened.
    Only the supervisor calls this, and only before spawning the service that
    owns the file, so no live child is writing to it.
    """
    if not path.exists() or path.stat().st_size < max_bytes:
        return False
    for index in range(backup_count - 1, 0, -1):
        source = rotated_segment(path, index)
        if source.exists():
            source.replace(rotated_segment(path, index + 1))
    path.replace(rotated_segment(path, 1))
    return True


def _read_last_lines(
    path: Path, count: int, max_read_bytes: int, end: Optional[int] = None
) -> Tuple[List[str], int, bool]:
    """Return the last ``count`` lines of one file, reading backwards in blocks.

    Reads at most ``max_read_bytes`` bytes, ending at byte ``end`` (the end of
    the file when None). A line cut by the start of the window is dropped, not
    returned as a fragment. Returns the lines, the bytes read, and whether the
    read reached the start of the file (every line before ``end`` was seen), so
    callers can tell when to continue into an older segment.
    """
    blocks: List[bytes] = []
    newlines = 0
    with open(path, "rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        position = size if end is None else min(end, size)
        stop = position
        while position > 0 and newlines <= count and stop - position < max_read_bytes:
            step = min(_TAIL_BLOCK_BYTES, position, max_read_bytes - (stop - position))
            position -= step
            handle.seek(position)
            block = handle.read(step)
            blocks.append(block)
            newlines += block.count(b"\n")
        # A mid-file window starts on a line boundary only when the byte
        # before it is a newline; otherwise its first line is a fragment.
        whole_first_line = position == 0
        if not whole_first_line:
            handle.seek(position - 1)
            whole_first_line = handle.read(1) == b"\n"
    lines = b"".join(reversed(blocks)).decode("utf-8", errors="replace").splitlines()
    if not whole_first_line:
        lines = lines[1:]
    return lines[-count:], stop - position, position == 0


def _tail_lines(
    path: Path,
    count: int,
    *,
    max_read_bytes: int,
    backup_count: int = 0,
    end: Optional[int] = None,
) -> List[str]:
    """Return the last ``count`` lines of a captured log.

    When the current file holds fewer than ``count`` lines, reading continues
    backwards through the rotated segments ``.1 .. .backup_count`` (newest
    first) and stops at the first missing segment. At most ``max_read_bytes``
    are read in all ([runtime.logs].max_tail_bytes), so a huge ``count`` never
    loads every retained segment. ``end`` bounds the read of the current file
    at a byte offset a follower has pinned. Lines come back in chronological
    order.
    """
    if count < 1:
        raise ValueError("Log line count must be a positive integer")
    if max_read_bytes < 1:
        raise ValueError(
            f"Log read bound must be a positive byte count, got {max_read_bytes}"
        )
    segments = [path] + [
        rotated_segment(path, index) for index in range(1, backup_count + 1)
    ]
    collected: List[str] = []
    budget = max_read_bytes
    for segment in segments:
        if not segment.exists():
            break
        lines, consumed, reached_start = _read_last_lines(
            segment,
            count - len(collected),
            budget,
            end if segment == path else None,
        )
        collected = lines + collected
        budget -= consumed
        if not reached_start or len(collected) >= count or budget < 1:
            break
    return collected


def _terminated(data: bytes) -> bytes:
    """``data`` ending in a newline: a closed segment's fragment is its own line."""
    return data + b"\n" if data and not data.endswith(b"\n") else data


class _LogFollower:
    """Incrementally read complete lines appended to a captured log.

    Spawn-time rotation renames ``<name>.log`` to ``<name>.log.1`` and opens a
    fresh file. The follower tracks the file identity it was reading; when the
    path names a new file it drains the rest of the renamed segment (and any
    segment rotated after it) first, so a restart neither strands the reader
    on the old file nor drops the dead process's last lines.
    """

    def __init__(self, path: Path, backup_count: int) -> None:
        self.path = path
        self.backup_count = backup_count
        self._inode: Optional[int] = None
        self._offset = 0
        self._partial = b""
        if path.exists():
            stat = path.stat()
            self._inode = stat.st_ino
            self._offset = stat.st_size

    @property
    def offset(self) -> int:
        """Byte offset in the current capture that following starts from."""
        return self._offset

    def read_lines(self) -> List[str]:
        """Return the complete lines appended since the previous call."""
        if not self.path.exists():
            return []
        finished = b""
        with open(self.path, "rb") as handle:
            inode = os.fstat(handle.fileno()).st_ino
            if inode != self._inode:
                if self._inode is not None:
                    finished = self._drain_rotated()
                    self._partial = b""
                self._inode = inode
                self._offset = 0
            handle.seek(self._offset)
            chunk = handle.read()
            self._offset = handle.tell()
        buffered = finished + self._partial + chunk
        complete, newline, self._partial = buffered.rpartition(b"\n")
        if not newline:
            return []
        return complete.decode("utf-8", errors="replace").split("\n")

    def _drain_rotated(self) -> bytes:
        """Unread bytes of the rotated segment this follower was reading.

        Each respawn past ``max_bytes`` shifts segments up by one, so within
        one poll the file being read may have moved past ``.1``. Its unread
        tail comes first, then every newer segment in full; each segment is
        closed for good, so its trailing fragment ends a line of its own.
        """
        for index in range(1, self.backup_count + 1):
            segment = rotated_segment(self.path, index)
            if not segment.exists():
                continue
            with open(segment, "rb") as handle:
                if os.fstat(handle.fileno()).st_ino != self._inode:
                    continue
                handle.seek(self._offset)
                pieces = [self._partial + handle.read()]
            pieces.extend(
                rotated_segment(self.path, newer).read_bytes()
                for newer in range(index - 1, 0, -1)
            )
            return b"".join(_terminated(piece) for piece in pieces)
        # The segment was rotated out of retention before it could be read.
        return _terminated(self._partial)


class Supervisor:
    """Process supervisor for the configured runtime profile."""

    def __init__(self, settings: Settings, config_path: Path):
        if settings.runtime is None:
            raise RuntimeError_(
                "nexus.toml has no [runtime] section; the managed runtime "
                "requires one (see docs/runtime.md)."
            )
        self.settings = settings
        self.runtime: RuntimeSettings = settings.runtime
        self.config_path = config_path.resolve()
        self.root = repo_root()
        state_dir = Path(self.runtime.state_dir)
        self.state_dir = state_dir if state_dir.is_absolute() else self.root / state_dir
        # NEXUS_GATEWAY_PORT: run this instance's gateway on an alternate
        # port with fully isolated state (pidfiles, logs, slot bookkeeping),
        # so agent/test sessions and the desktop app can coexist on one
        # checkout without ever contending for the configured port.
        try:
            self._gateway_port_override = gateway_port_override()
        except ValueError as exc:
            raise RuntimeError_(str(exc)) from exc
        # The default instance's state dir stays visible under an override:
        # it is the ownership ledger for fixed-port siblings (see
        # _start_service's borrow path).
        self._base_state_dir = self.state_dir
        if self._gateway_port_override is not None:
            gateway = self.runtime.services.get("gateway")
            if gateway is None:
                raise RuntimeError_(
                    f"{GATEWAY_PORT_ENV} is set but nexus.toml has no "
                    "[runtime.services.gateway] to apply it to."
                )
            for name, service in self.runtime.services.items():
                if name != "gateway" and service.port == self._gateway_port_override:
                    raise RuntimeError_(
                        f"{GATEWAY_PORT_ENV}={self._gateway_port_override} "
                        f"collides with [runtime.services.{name}] port "
                        f"{service.port}; pick a port no service is "
                        "configured on."
                    )
            gateway.port = self._gateway_port_override
            self.state_dir = self.state_dir / f"gateway-{gateway.port}"

    @classmethod
    def from_config(cls, config_path: Optional[Path] = None) -> "Supervisor":
        """Build a supervisor from an explicit, runtime, or repository config."""
        runtime_config = os.environ.get(RUNTIME_CONFIG_ENV)
        if config_path is not None:
            path = Path(config_path)
        elif runtime_config:
            path = Path(runtime_config)
        else:
            path = repo_root() / "nexus.toml"
        return cls(load_settings(path), path)

    # ------------------------------------------------------------------
    # Service selection
    # ------------------------------------------------------------------

    def enabled_services(self) -> Dict[str, RuntimeServiceSettings]:
        """Services the local profile should spawn, honoring 'auto' gating."""
        test_registered = bool(
            self.settings.global_.model.api_models.get("test")
            and self.settings.global_.model.api_models["test"].models
        )
        selected: Dict[str, RuntimeServiceSettings] = {}
        for name, service in self.runtime.services.items():
            if service.enabled == "never":
                continue
            if service.enabled == "auto" and not test_registered:
                continue
            selected[name] = service
        return selected

    # ------------------------------------------------------------------
    # State files
    # ------------------------------------------------------------------

    def _pidfile(self, name: str) -> Path:
        return self.state_dir / f"{name}.pid.json"

    def log_path(self, name: str) -> Path:
        return self.state_dir / f"{name}.log"

    def log_config_path(self) -> Path:
        """The dictConfig JSON substituted for the ``{log_config}`` placeholder."""
        return self.state_dir / LOG_CONFIG_FILENAME

    def _write_log_config(self) -> Path:
        """Write ``[runtime.logs]`` as a dictConfig JSON file for ``--log-config``."""
        path = self.log_config_path()
        path.write_text(
            json.dumps(build_logging_config(self.runtime.logs), indent=2) + "\n"
        )
        return path

    def _read_pidfile(self, name: str) -> Optional[Dict[str, Any]]:
        path = self._pidfile(name)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _running_slot(self) -> Optional[int]:
        """Return the slot recorded by running services, if any.

        A full restart should preserve the slot chosen by ``nexus up --slot N``;
        once ``down()`` removes pidfiles that information is gone.
        """
        slots = {
            int(record["slot"])
            for path in self.state_dir.glob("*.pid.json")
            if (record := json.loads(path.read_text()))
            and _pid_alive(int(record["pid"]))
            and record.get("slot") is not None
        }
        if len(slots) > 1:
            raise RuntimeError_(
                f"Running services disagree about active slot: {sorted(slots)}. "
                "Pass --slot explicitly."
            )
        return next(iter(slots), None)

    def _write_pidfile(self, name: str, record: Dict[str, Any]) -> None:
        self._pidfile(name).write_text(json.dumps(record, indent=2))

    def _sibling_owned_by_default(
        self, name: str, service: RuntimeServiceSettings
    ) -> bool:
        """True when the default instance's ledger owns this service's port.

        The proof is the default state dir's pidfile: a live pid recorded on
        exactly the configured port. A foreign process answering the health
        path does not qualify — health alone is not ownership.
        """
        path = self._base_state_dir / f"{name}.pid.json"
        if not path.exists():
            return False
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        return (
            _pid_alive(int(record.get("pid", -1)))
            and int(record.get("port", -1)) == service.port
        )

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------

    def _resolve_slot(self, slot: Optional[int]) -> int:
        if slot is not None:
            return slot
        env_slot = os.environ.get("NEXUS_SLOT")
        if env_slot:
            return int(env_slot)
        return self.runtime.default_slot

    def _service_argv(self, service: RuntimeServiceSettings) -> List[str]:
        substitutions = {
            "python": sys.executable,
            "host": service.host,
            "port": str(service.port),
            LOG_CONFIG_PLACEHOLDER: str(self.log_config_path()),
        }
        return [part.format(**substitutions) for part in service.command]

    def _service_env(
        self, service: RuntimeServiceSettings, slot: int
    ) -> Dict[str, str]:
        env = dict(os.environ)
        env.update(service.env)
        env["NEXUS_SLOT"] = str(slot)
        env[RUNTIME_CONFIG_ENV] = str(self.config_path)
        # Spawned services must import this checkout's nexus package even when
        # an editable install of another checkout exists in the environment.
        env["PYTHONPATH"] = os.pathsep.join(
            [str(self.root)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )
        return env

    def _spawn(
        self,
        name: str,
        service: RuntimeServiceSettings,
        slot: int,
        detached: bool,
    ) -> int:
        argv = self._service_argv(service)
        if LOG_CONFIG_PLACEHOLDER in _template_fields(service.command):
            self._write_log_config()
        log_path = self.log_path(name)
        # The supervisor is the single rotation owner: the previous process
        # holding this file is gone, so the rename cannot race a live writer.
        _rotate_log(
            log_path, self.runtime.logs.max_bytes, self.runtime.logs.backup_count
        )
        popen_kwargs: Dict[str, Any] = {}
        if detached:
            if os.name == "posix":
                popen_kwargs["start_new_session"] = True
            else:  # pragma: no cover - Windows host path
                popen_kwargs["creationflags"] = (
                    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                )
        elif os.name == "posix":
            # Foreground children still get their own session so a group
            # signal on teardown reaches forked workers without hitting the
            # supervisor itself.
            popen_kwargs["start_new_session"] = True
        with open(log_path, "ab") as log_handle:
            process = subprocess.Popen(
                argv,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=self.root,
                env=self._service_env(service, slot),
                **popen_kwargs,
            )
        return process.pid

    def _startup_excerpt(self, name: str) -> str:
        """The last lines a service wrote during a failed start (current file)."""
        return "\n".join(
            _tail_lines(
                self.log_path(name),
                30,
                max_read_bytes=self.runtime.logs.max_tail_bytes,
            )
        )

    def _await_healthy(self, name: str, service: RuntimeServiceSettings, pid: int):
        health = self.runtime.health
        url = f"http://{service.host}:{service.port}{service.health_path}"
        deadline = time.monotonic() + health.startup_deadline_seconds
        while True:
            if not _pid_alive(pid):
                excerpt = self._startup_excerpt(name)
                raise RuntimeError_(
                    f"Service '{name}' exited during startup. Last log lines:\n"
                    f"{excerpt}"
                )
            try:
                if requests.get(url, timeout=health.timeout_seconds).status_code == 200:
                    return
            except requests.RequestException:
                pass
            if time.monotonic() > deadline:
                excerpt = self._startup_excerpt(name)
                self._stop_pid(pid)
                raise RuntimeError_(
                    f"Service '{name}' failed to become healthy at {url} within "
                    f"{health.startup_deadline_seconds}s. Last log lines:\n"
                    f"{excerpt}"
                )
            time.sleep(health.poll_interval_seconds)

    def _start_service(
        self,
        name: str,
        service: RuntimeServiceSettings,
        slot: int,
        detached: bool,
    ) -> Dict[str, Any]:
        existing = self._read_pidfile(name)
        if existing and _pid_alive(int(existing["pid"])):
            raise RuntimeError_(
                f"Service '{name}' is already running (pid {existing['pid']}). "
                f"Use 'nexus restart' or 'nexus down' first."
            )
        if existing:
            self._pidfile(name).unlink()  # stale pidfile from a dead process
        if self._gateway_port_override is not None and name != "gateway":
            # Fixed-port siblings (the mock provider) belong to the default
            # instance. An override instance borrows one only when the
            # default state ledger proves the listener is the managed
            # sibling — pidfile alive, same port, healthy — and never
            # spawns its own, so a later default `nexus up` always finds
            # its ports either free or owned by its own pidfiles.
            if self._sibling_owned_by_default(name, service) and self._probe(
                f"http://{service.host}:{service.port}{service.health_path}"
            ):
                return {
                    "attached": True,
                    "service": name,
                    "port": service.port,
                    "host": service.host,
                }
            if not _port_open(service.host, service.port):
                return {
                    "skipped": True,
                    "service": name,
                    "port": service.port,
                    "host": service.host,
                    "reason": (
                        "fixed-port sibling is not running; start the "
                        "default stack if this instance needs it"
                    ),
                }
            # Port open but not verifiably ours: fall through to the
            # unmanaged-port refusal below.
        if _port_open(service.host, service.port):
            occupant = _describe_port_occupant(service.port)
            listener = f" Listener: {occupant}." if occupant else ""
            raise RuntimeError_(
                f"Port {service.port} is already in use by an unmanaged process; "
                f"refusing to spawn '{name}'. Adjust [runtime.services.{name}] "
                f"port or stop the other process.{listener} If the listener is "
                "a stale NEXUS service from a dead session, kill that pid. "
                f"Agent/test shells should export {GATEWAY_PORT_ENV} to run on "
                "a separate port with isolated state."
            )
        if name == "gateway":
            from nexus.api.choice_recovery import recover_active_slot_choice

            recover_active_slot_choice(slot)
        pid = self._spawn(name, service, slot, detached=detached)
        self._await_healthy(name, service, pid)
        record = {
            "pid": pid,
            "service": name,
            "port": service.port,
            "host": service.host,
            "slot": slot,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "command": self._service_argv(service),
            "log": str(self.log_path(name)),
        }
        self._write_pidfile(name, record)
        return record

    # ------------------------------------------------------------------
    # Public verbs
    # ------------------------------------------------------------------

    def up(
        self,
        slot: Optional[int] = None,
        foreground: bool = False,
        echo: bool = True,
    ) -> Dict[str, Any]:
        """Start the runtime per the configured profile."""
        profile = self.runtime.profile
        if profile == "external":
            return self._attach_external()
        if profile == "remote":
            return self._check_remote()

        self.state_dir.mkdir(parents=True, exist_ok=True)
        resolved_slot = self._resolve_slot(slot)
        ui_index = self.root / "ui" / "dist" / "public" / "index.html"
        if echo and not ui_index.exists():
            print(
                "warning: ui/dist/public/index.html is missing - the gateway "
                "will serve 503 for UI routes. Build it with: "
                "npm --prefix ui run build",
                file=sys.stderr,
            )

        started: Dict[str, Any] = {}
        try:
            for name, service in self.enabled_services().items():
                record = self._start_service(
                    name, service, resolved_slot, detached=not foreground
                )
                started[name] = record
                if echo and record.get("attached"):
                    print(
                        f"attached to existing {name} on "
                        f"http://{service.host}:{service.port}"
                    )
                elif echo and record.get("skipped"):
                    print(f"skipped {name}: {record['reason']}")
                elif echo:
                    print(
                        f"started {name} (pid {record['pid']}) on "
                        f"http://{service.host}:{service.port}"
                    )
        except Exception:
            # Partial starts are torn down so up() is all-or-nothing.
            for name in started:
                self._stop_service(name)
            raise

        gateway = self.runtime.services.get("gateway")
        if echo and gateway:
            print(
                f"NEXUS is up: http://{gateway.host}:{gateway.port} "
                f"(slot {resolved_slot}, profile local)"
            )

        if foreground:
            self._foreground_loop(resolved_slot, echo=echo)
            return {"success": True, "profile": profile, "stopped": True}
        return {
            "success": True,
            "profile": profile,
            "slot": resolved_slot,
            "services": started,
        }

    def _attach_external(self) -> Dict[str, Any]:
        external = self.runtime.external
        targets = {"gateway": external.gateway_url.rstrip("/") + "/health"}
        if external.mock_openai_url:
            targets["mock_openai"] = external.mock_openai_url.rstrip("/") + "/health"
        results: Dict[str, Any] = {}
        failures = []
        for name, url in targets.items():
            ok = self._probe(url)
            results[name] = {"ok": ok, "url": url}
            if not ok:
                failures.append(f"{name} ({url})")
        if failures:
            raise RuntimeError_(
                "External profile attach failed; unhealthy services: "
                + ", ".join(failures)
            )
        return {"success": True, "profile": "external", "services": results}

    def _check_remote(self) -> Dict[str, Any]:
        remote = self.runtime.remote
        url = remote.base_url.rstrip("/") + RUNTIME_STATUS_PATH
        auth = build_runtime_request_auth(url, remote)
        response = requests.get(
            url,
            timeout=self.runtime.health.timeout_seconds,
            headers=auth.headers,
            allow_redirects=auth.allow_redirects,
        )
        response.raise_for_status()
        return {"success": True, "profile": "remote", "runtime": response.json()}

    def _probe(self, url: str) -> bool:
        try:
            return (
                requests.get(
                    url, timeout=self.runtime.health.timeout_seconds
                ).status_code
                == 200
            )
        except requests.RequestException:
            return False

    def _stop_pid(self, pid: int) -> None:
        grace = self.runtime.health.stop_grace_seconds
        if not _pid_alive(pid):
            return
        _signal_pid(pid, signal.SIGTERM)
        deadline = time.monotonic() + grace
        while _pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if _pid_alive(pid):
            kill_sig = signal.SIGKILL if os.name == "posix" else signal.SIGTERM
            _signal_pid(pid, kill_sig)
            time.sleep(0.2)

    def _wait_port_closed(self, host: str, port: int) -> bool:
        """Return true once a stopped service's TCP port is closed."""
        deadline = time.monotonic() + self.runtime.health.stop_grace_seconds
        while time.monotonic() < deadline:
            if not _port_open(host, port):
                return True
            time.sleep(0.1)
        return not _port_open(host, port)

    def _stop_service(self, name: str) -> Optional[int]:
        record = self._read_pidfile(name)
        if record is None:
            return None
        pid = int(record["pid"])
        self._stop_pid(pid)
        self._pidfile(name).unlink(missing_ok=True)
        return pid

    def down(self, service: Optional[str] = None) -> Dict[str, Any]:
        """Stop managed services and remove their pidfiles (local only)."""
        if self.runtime.profile != "local":
            raise RuntimeError_(
                f"'nexus down' manages local processes; profile is "
                f"'{self.runtime.profile}'."
            )
        names = (
            [service]
            if service
            else [
                p.name[: -len(".pid.json")] for p in self.state_dir.glob("*.pid.json")
            ]
        )
        stopped: Dict[str, Any] = {}
        for name in names:
            record = self._read_pidfile(name)
            pid = self._stop_service(name)
            if pid is None:
                continue
            stopped[name] = {"pid": pid}
            if record and not self._wait_port_closed(
                record.get("host", "127.0.0.1"), record["port"]
            ):
                raise RuntimeError_(
                    f"Service '{name}' was signaled but port {record['port']} is "
                    f"still open - a process outlived shutdown."
                )
        return {"success": True, "stopped": stopped}

    def restart(
        self, service: Optional[str] = None, slot: Optional[int] = None
    ) -> Dict[str, Any]:
        if self.runtime.profile != "local":
            raise RuntimeError_(
                f"'nexus restart' manages local processes; profile is "
                f"'{self.runtime.profile}'."
            )
        if service:
            services = self.enabled_services()
            if service not in services:
                raise RuntimeError_(
                    f"Unknown or disabled service '{service}'. Enabled: "
                    f"{sorted(services)}"
                )
            previous = self._read_pidfile(service)
            self._stop_service(service)
            resolved_slot = self._resolve_slot(
                slot if slot is not None else (previous or {}).get("slot")
            )
            record = self._start_service(
                service, services[service], resolved_slot, detached=True
            )
            return {"success": True, "services": {service: record}}
        resolved_slot = self._resolve_slot(
            slot if slot is not None else self._running_slot()
        )
        self.down()
        return self.up(slot=resolved_slot, echo=False)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _gateway_url(self) -> str:
        if self.runtime.profile == "external":
            return self.runtime.external.gateway_url.rstrip("/")
        if self.runtime.profile == "remote":
            return self.runtime.remote.base_url.rstrip("/")
        gateway = self.runtime.services["gateway"]
        return f"http://{gateway.host}:{gateway.port}"

    def _fetch_runtime_status(self) -> Dict[str, Any]:
        url = self._gateway_url() + RUNTIME_STATUS_PATH
        try:
            remote = self.runtime.remote if self.runtime.profile == "remote" else None
            auth = build_runtime_request_auth(url, remote)
            response = requests.get(
                url,
                timeout=self.runtime.health.timeout_seconds,
                headers=auth.headers,
                allow_redirects=auth.allow_redirects,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return {"error": f"runtime status unreachable at {url}: {exc}"}

    def status(self) -> Dict[str, Any]:
        """Supervisor-side process state merged with /runtime/status."""
        result: Dict[str, Any] = {
            "success": True,
            "profile": self.runtime.profile,
            "config": str(self.config_path),
            "gateway_url": self._gateway_url(),
        }
        if self.runtime.profile == "local":
            processes: Dict[str, Any] = {}
            for name, service in self.runtime.services.items():
                record = self._read_pidfile(name)
                if record and _pid_alive(int(record["pid"])):
                    started = datetime.fromisoformat(record["started_at"])
                    uptime = (datetime.now(timezone.utc) - started).total_seconds()
                    processes[name] = {
                        "state": "running",
                        "pid": record["pid"],
                        "port": record["port"],
                        "slot": record.get("slot"),
                        "uptime_seconds": round(uptime, 1),
                    }
                else:
                    processes[name] = {"state": "stopped", "port": service.port}
            result["processes"] = processes
        result["runtime"] = self._fetch_runtime_status()
        return result

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def logs(
        self,
        service: str = "gateway",
        lines: Optional[int] = None,
        follow: bool = False,
    ) -> Iterator[str]:
        """Yield captured log lines for a service; generator so -f can stream.

        The tail reads back through rotated segments when the current capture
        is shorter than ``lines``; ``follow`` tails the current capture and
        crosses the rotation a respawn performs.
        """
        if self.runtime.profile != "local":
            raise RuntimeError_(
                f"'nexus logs' reads captured local logs; profile is "
                f"'{self.runtime.profile}'."
            )
        log_path = self.log_path(service)
        if not log_path.exists():
            raise RuntimeError_(
                f"No captured log for service '{service}' at {log_path}. "
                f"Known services: {sorted(self.runtime.services)}"
            )
        settings = self.runtime.logs
        count = lines if lines is not None else settings.tail_lines
        # Pin the follow position first and read the tail up to exactly that
        # offset, so a line written meanwhile is followed: never skipped and
        # never repeated.
        follower = _LogFollower(log_path, settings.backup_count) if follow else None
        tail = _tail_lines(
            log_path,
            count,
            max_read_bytes=settings.max_tail_bytes,
            backup_count=settings.backup_count,
            end=None if follower is None else follower.offset,
        )
        yield from tail
        if follower is None:
            return
        while True:
            appended = follower.read_lines()
            if appended:
                yield from appended
            else:
                time.sleep(self.runtime.logs.follow_poll_seconds)

    # ------------------------------------------------------------------
    # Foreground supervision
    # ------------------------------------------------------------------

    def _foreground_loop(self, slot: int, echo: bool = True) -> None:
        """Tail service logs to the console and supervise until interrupted."""
        restarts: Dict[str, int] = {}
        services = self.enabled_services()
        followers = {
            name: _LogFollower(self.log_path(name), self.runtime.logs.backup_count)
            for name in services
        }

        interrupted = {"flag": False}

        def _handle_signal(_signum, _frame):
            interrupted["flag"] = True

        previous_handlers = {
            sig: signal.signal(sig, _handle_signal)
            for sig in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            while not interrupted["flag"]:
                for name in services:
                    appended = followers[name].read_lines()
                    if echo:
                        for line in appended:
                            print(f"[{name}] {line}")
                self._check_children(services, slot, restarts, echo=echo)
                time.sleep(self.runtime.logs.follow_poll_seconds)
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
            if echo:
                print("shutting down...")
            self.down()

    def _check_children(
        self,
        services: Dict[str, RuntimeServiceSettings],
        slot: int,
        restarts: Dict[str, int],
        echo: bool,
    ) -> None:
        exited: list[tuple[str, RuntimeServiceSettings, Dict[str, Any]]] = []
        for name, service in services.items():
            record = self._read_pidfile(name)
            if record is None or _pid_alive(int(record["pid"])):
                continue
            self._pidfile(name).unlink(missing_ok=True)
            exited.append((name, service, record))

        failures: list[str] = []
        for name, service, record in exited:
            if service.autorestart != "on-failure":
                failures.append(
                    f"Service '{name}' (pid {record['pid']}) exited and "
                    f"autorestart is 'never'."
                )
                continue
            attempts = restarts.get(name, 0)
            if attempts >= service.autorestart_max_retries:
                failures.append(
                    f"Service '{name}' exceeded autorestart_max_retries "
                    f"({service.autorestart_max_retries})."
                )
                continue
            restarts[name] = attempts + 1
            if echo:
                print(
                    f"[{name}] exited; restarting "
                    f"({restarts[name]}/{service.autorestart_max_retries})"
                )
            self._start_service(name, service, slot, detached=False)
        if failures:
            raise RuntimeError_(" ".join(failures))
