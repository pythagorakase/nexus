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
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests

from nexus.config import load_settings
from nexus.config.settings_models import (
    RuntimeServiceSettings,
    RuntimeSettings,
    Settings,
)
from nexus.runtime.contract import (
    RUNTIME_CONFIG_ENV,
    RUNTIME_STATUS_PATH,
)
from nexus.runtime.remote_auth import build_runtime_request_auth


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


def _tail_lines(path: Path, count: int) -> List[str]:
    if not path.exists():
        return []
    with open(path, "rb") as handle:
        try:
            handle.seek(-min(path.stat().st_size, 256 * 1024), os.SEEK_END)
        except OSError:
            handle.seek(0)
        text = handle.read().decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-count:]


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

    @classmethod
    def from_config(cls, config_path: Optional[Path] = None) -> "Supervisor":
        path = Path(config_path) if config_path else repo_root() / "nexus.toml"
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
        log_path = self.log_path(name)
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

    def _await_healthy(self, name: str, service: RuntimeServiceSettings, pid: int):
        health = self.runtime.health
        url = f"http://{service.host}:{service.port}{service.health_path}"
        deadline = time.monotonic() + health.startup_deadline_seconds
        while True:
            if not _pid_alive(pid):
                excerpt = "\n".join(_tail_lines(self.log_path(name), 30))
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
                excerpt = "\n".join(_tail_lines(self.log_path(name), 30))
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
        if _port_open(service.host, service.port):
            raise RuntimeError_(
                f"Port {service.port} is already in use by an unmanaged process; "
                f"refusing to spawn '{name}'. Adjust [runtime.services.{name}] "
                f"port or stop the other process."
            )
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
                if echo:
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
        """Yield captured log lines for a service; generator so -f can stream."""
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
        count = lines if lines is not None else self.runtime.logs.tail_lines
        for line in _tail_lines(log_path, count):
            yield line
        if not follow:
            return
        with open(log_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            while True:
                chunk = handle.readline()
                if chunk:
                    yield chunk.decode("utf-8", errors="replace").rstrip("\n")
                else:
                    time.sleep(self.runtime.logs.follow_poll_seconds)

    # ------------------------------------------------------------------
    # Foreground supervision
    # ------------------------------------------------------------------

    def _foreground_loop(self, slot: int, echo: bool = True) -> None:
        """Tail service logs to the console and supervise until interrupted."""
        offsets: Dict[str, int] = {}
        restarts: Dict[str, int] = {}
        services = self.enabled_services()
        for name in services:
            path = self.log_path(name)
            offsets[name] = path.stat().st_size if path.exists() else 0

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
                    path = self.log_path(name)
                    if not path.exists():
                        continue
                    size = path.stat().st_size
                    if size > offsets[name]:
                        with open(path, "rb") as handle:
                            handle.seek(offsets[name])
                            data = handle.read()
                            offsets[name] = handle.tell()
                        if echo:
                            text = data.decode("utf-8", errors="replace")
                            for line in text.splitlines():
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
