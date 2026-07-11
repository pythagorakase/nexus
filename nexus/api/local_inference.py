"""Detached lifecycle manager for interactive local llama-server inference."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests  # type: ignore[import-untyped]

from nexus.config import get_local_models_settings, load_settings
from nexus.config.settings_models import Settings
from nexus.util.gguf_inspect import inspect_gguf

STATE_FILENAME = "local-model.pid.json"
LOG_FILENAME = "local-model.log"
DOWNLOAD_FILENAME = "local-model.download.json"
DOWNLOAD_LOG_FILENAME = "local-model.download.log"
REGISTERED_FILENAME = "local-models.registered.json"

_lifecycle_lock = threading.RLock()
_download_lock = threading.Lock()
_registration_lock = threading.Lock()
_MANAGED_OPTIONS = frozenset({"--model", "--alias", "--host", "--port"})
_SPLIT_GGUF_PATTERN = re.compile(
    r"^(?P<stem>.+)-(?P<part>\d{5})-of-(?P<total>\d{5})\.gguf$",
    re.IGNORECASE,
)


class LocalInferenceError(RuntimeError):
    """A loud, user-facing local inference lifecycle failure."""


def _repo_root() -> Path:
    """Return the repository root containing the active nexus package."""
    return Path(__file__).resolve().parents[2]


def _state_dir(settings: Settings) -> Path:
    """Resolve the shared managed-runtime state directory."""
    if settings.runtime is None:
        raise LocalInferenceError("[runtime] is required for local model process state")
    configured = Path(settings.runtime.state_dir).expanduser()
    return configured if configured.is_absolute() else _repo_root() / configured


def _state_path(settings: Settings) -> Path:
    return _state_dir(settings) / STATE_FILENAME


def _download_path(settings: Settings) -> Path:
    return _state_dir(settings) / DOWNLOAD_FILENAME


def _registered_path(settings: Settings) -> Path:
    return _state_dir(settings) / REGISTERED_FILENAME


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalInferenceError(
            f"Cannot read local model state {path}: {exc}"
        ) from exc


def _write_json(path: Path, value: Any) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise LocalInferenceError(
            f"Cannot write local model state {path}: {exc}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    """Return whether a recorded process still exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _allowed_roots() -> tuple[Path, Path]:
    """Return the canonical roots allowed for local-model filesystem actions."""
    return (
        Path(get_local_models_settings().models_dir).resolve(),
        Path.home().resolve(),
    )


def _is_within(path: Path, roots: tuple[Path, ...]) -> bool:
    """Return whether a resolved path is within one of the allowed roots."""
    return any(path == root or path.is_relative_to(root) for root in roots)


def split_shard(path: Path) -> tuple[str, int, int] | None:
    """Return split stem, part, and total for llama.cpp split filenames."""
    match = _SPLIT_GGUF_PATTERN.match(path.name)
    if match is None:
        return None
    return match.group("stem"), int(match.group("part")), int(match.group("total"))


def shard_set(path: Path, roots: tuple[Path, ...]) -> list[Path]:
    """Enumerate a GGUF's root-validated split siblings, or the file itself."""
    resolved_path = path.resolve()
    split = split_shard(resolved_path)
    if split is None:
        # Defense in depth: the split branch below already root-validates each
        # sibling, so the non-split path must too — a caller that skips the
        # endpoint's _verified_path guard must never delete outside the roots.
        return [resolved_path] if _is_within(resolved_path, roots) else []
    stem, _, total = split
    siblings: list[Path] = []
    for sibling in resolved_path.parent.glob(f"{stem}-*-of-{total:05d}.gguf"):
        resolved = sibling.resolve()
        sibling_split = split_shard(resolved)
        if (
            sibling_split is not None
            and sibling_split[0] == stem
            and sibling_split[2] == total
            and _is_within(resolved, roots)
            and resolved.is_file()
        ):
            siblings.append(resolved)
    return sorted(siblings)


def _endpoint(settings: Settings) -> tuple[str, int, str]:
    """Derive host, port, and model alias from the local provider registry."""
    provider = settings.global_.model.api_models.get("local")
    if provider is None or not provider.base_url:
        raise LocalInferenceError(
            "[global.model.api_models.local] with base_url is required"
        )
    parsed = urlsplit(provider.base_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.port is None:
        raise LocalInferenceError(
            "Local provider base_url must be an explicit http://host:port URL"
        )
    alias = provider.roles.get("default")
    if not alias:
        raise LocalInferenceError(
            "[global.model.api_models.local].roles.default is required as alias"
        )
    return parsed.hostname, parsed.port, alias


def _configured_command(settings: Settings) -> tuple[str, list[str]]:
    """Return the configured binary and non-manager-owned llama-server flags."""
    if settings.runtime is None:
        raise LocalInferenceError("[runtime] is required for llama-server config")
    service = settings.runtime.services.get("llama_server")
    if service is None or not service.command:
        raise LocalInferenceError(
            "[runtime.services.llama_server].command is required to locate llama-server"
        )
    configured = service.command[0]
    resolved = shutil.which(configured)
    if resolved is None:
        raise LocalInferenceError(
            f"Configured llama-server binary does not exist or is not executable: "
            f"{configured}"
        )
    extras: list[str] = []
    index = 1
    while index < len(service.command):
        argument = service.command[index]
        if argument in _MANAGED_OPTIONS:
            if index + 1 >= len(service.command):
                raise LocalInferenceError(
                    f"Configured llama-server option {argument} is missing its value"
                )
            index += 2
            continue
        if any(argument.startswith(f"{option}=") for option in _MANAGED_OPTIONS):
            index += 1
            continue
        extras.append(argument)
        index += 1
    return resolved, extras


def _health_ok(settings: Settings, host: str, port: int) -> bool:
    """Probe llama-server using the managed runtime health timeout."""
    if settings.runtime is None:
        raise LocalInferenceError("[runtime] is required for health probe settings")
    try:
        response = requests.get(
            f"http://{host}:{port}/health",
            timeout=settings.runtime.health.timeout_seconds,
        )
    except requests.RequestException:
        return False
    return response.status_code == 200


def _port_open(settings: Settings, host: str, port: int) -> bool:
    """Probe the managed port using the runtime health timeout."""
    if settings.runtime is None:
        raise LocalInferenceError("[runtime] is required for port probe settings")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(settings.runtime.health.timeout_seconds)
        return sock.connect_ex((host, port)) == 0


def _process_is_ours(settings: Settings, pid: int, gguf_path: str) -> bool:
    """Verify a live PID still names our binary and exact recorded model path."""
    if settings.runtime is None:
        raise LocalInferenceError("[runtime] is required for process probe settings")
    try:
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            check=False,
            text=True,
            timeout=settings.runtime.health.timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    command = result.stdout.strip()
    return result.returncode == 0 and "llama-server" in command and gguf_path in command


def _download_process_is_ours(settings: Settings, pid: int, repo_id: str) -> bool:
    """Verify a live PID still names the detached downloader and its repository."""
    if settings.runtime is None:
        raise LocalInferenceError("[runtime] is required for process probe settings")
    try:
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            check=False,
            text=True,
            timeout=settings.runtime.health.timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    command = result.stdout.strip()
    return (
        result.returncode == 0
        and "local_download_worker" in command
        and repo_id in command
    )


def _read_active(settings: Settings) -> dict[str, Any] | None:
    record = _read_json(_state_path(settings))
    if record is None:
        return None
    try:
        pid = int(record["pid"])
        gguf_path = str(record["gguf_path"])
        port = int(record["port"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LocalInferenceError(f"Malformed local model state file: {exc}") from exc
    if record.get("failed") is True:
        return {
            "gguf_path": gguf_path,
            "pid": pid,
            "ready": False,
            "failed": True,
            "error": record.get("error", "llama-server exited before becoming ready"),
        }
    if not _pid_alive(pid):
        if record.get("ready_observed") is True:
            _state_path(settings).unlink(missing_ok=True)
            return None
        record["failed"] = True
        record["failed_at"] = datetime.now(timezone.utc).isoformat()
        record["error"] = (
            "llama-server exited before becoming ready; see "
            f"{_state_dir(settings) / LOG_FILENAME}"
        )
        _write_json(_state_path(settings), record)
        return {
            "gguf_path": gguf_path,
            "pid": pid,
            "ready": False,
            "failed": True,
            "error": record["error"],
        }
    if not _process_is_ours(settings, pid, gguf_path):
        _state_path(settings).unlink(missing_ok=True)
        return None
    host, _, _ = _endpoint(settings)
    is_ready = _health_ok(settings, host, port)
    if is_ready and record.get("ready_observed") is not True:
        record["ready_observed"] = True
        _write_json(_state_path(settings), record)
    return {
        "gguf_path": gguf_path,
        "pid": pid,
        "ready": is_ready,
        "failed": False,
    }


def active() -> dict[str, Any] | None:
    """Rediscover the detached managed process and report its readiness."""
    with _lifecycle_lock:
        return _read_active(load_settings())


def ready() -> bool:
    """Return whether the managed process is serving a healthy model."""
    current = active()
    return bool(current and current["ready"])


def _signal_process_group(pid: int, sig: int) -> None:
    if os.name == "posix":
        os.killpg(pid, sig)
    else:  # pragma: no cover - Windows is not a supported llama.cpp host here
        os.kill(pid, sig)


def _deactivate_locked(settings: Settings) -> dict[str, Any]:
    """Stop the recorded process while the lifecycle lock is held."""
    current = _read_active(settings)
    if current is None:
        _state_path(settings).unlink(missing_ok=True)
        return {"stopped": False}
    if current.get("failed") is True:
        _state_path(settings).unlink(missing_ok=True)
        return {"stopped": False, "failed_cleared": True}
    pid = int(current["pid"])
    gguf_path = str(current["gguf_path"])
    if not _process_is_ours(settings, pid, gguf_path):
        _state_path(settings).unlink(missing_ok=True)
        return {"stopped": False, "ownership_lost": True}
    try:
        _signal_process_group(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if settings.runtime is None:
        raise LocalInferenceError("[runtime] is required for shutdown settings")
    health = settings.runtime.health
    grace = health.stop_grace_seconds
    deadline = time.monotonic() + grace
    while (
        _pid_alive(pid)
        and _process_is_ours(settings, pid, gguf_path)
        and time.monotonic() < deadline
    ):
        time.sleep(health.poll_interval_seconds)
    if _pid_alive(pid) and _process_is_ours(settings, pid, gguf_path):
        try:
            _signal_process_group(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    _state_path(settings).unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}


def deactivate() -> dict[str, Any]:
    """Terminate the detached llama-server process group, if one is recorded."""
    with _lifecycle_lock:
        return _deactivate_locked(load_settings())


def activate(gguf_path: str) -> dict[str, Any]:
    """Start a detached llama-server for a verified GGUF and return immediately."""
    candidate = Path(gguf_path).expanduser().resolve()
    info = inspect_gguf(str(candidate))
    if not info.valid:
        raise LocalInferenceError(info.reason or f"Invalid GGUF file: {candidate}")

    with _lifecycle_lock:
        settings = load_settings()
        host, port, alias = _endpoint(settings)
        current = _read_active(settings)
        if current is not None and current.get("failed") is not True:
            if Path(current["gguf_path"]) == candidate:
                return current
            _deactivate_locked(settings)
        elif current is not None:
            _state_path(settings).unlink(missing_ok=True)
        if _port_open(settings, host, port):
            raise LocalInferenceError(
                f"Port {port} is already in use by a process this manager does "
                "not own; stop the static llama_server service or the other "
                "process first"
            )

        binary, extra_flags = _configured_command(settings)
        command = [
            binary,
            "--model",
            str(candidate),
            "--alias",
            alias,
            "--host",
            host,
            "--port",
            str(port),
            *extra_flags,
        ]
        state_dir = _state_dir(settings)
        state_dir.mkdir(parents=True, exist_ok=True)
        log_path = state_dir / LOG_FILENAME
        try:
            with log_path.open("ab") as log_handle:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                    start_new_session=True,
                )
        except OSError as exc:
            raise LocalInferenceError(f"Failed to spawn llama-server: {exc}") from exc

        record = {
            "pid": process.pid,
            "gguf_path": str(candidate),
            "port": port,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ready_observed": False,
        }
        try:
            _write_json(_state_path(settings), record)
        except LocalInferenceError:
            try:
                _signal_process_group(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            raise
        return {
            "gguf_path": str(candidate),
            "pid": process.pid,
            "ready": False,
            "failed": False,
        }


def _read_download_record(settings: Settings) -> dict[str, Any] | None:
    """Read and validate the manager-owned detached download record."""
    record = _read_json(_download_path(settings))
    if record is None:
        return None
    try:
        normalized = {
            "pid": int(record["pid"]),
            "family": str(record["family"]),
            "quant": str(record["quant"]),
            "repo_id": str(record["repo_id"]),
            "local_dir": str(record["local_dir"]),
            "files": [str(filename) for filename in record["files"]],
            "total_bytes": int(record["total_bytes"]),
            "started_at": str(record["started_at"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise LocalInferenceError(
            f"Malformed local-model download state: {exc}"
        ) from exc
    if not isinstance(record["files"], list) or not record["files"]:
        raise LocalInferenceError("Malformed local-model download state: files")
    return normalized


def start_download(
    *,
    family: str,
    quant: str,
    repo_id: str,
    local_dir: str,
    files: list[str],
    total_bytes: int,
) -> dict[str, Any]:
    """Start one detached curated-model download and persist its job record."""
    with _download_lock:
        settings = load_settings()
        existing = _read_download_record(settings)
        if existing is not None and _pid_alive(existing["pid"]):
            raise LocalInferenceError("A local-model download is already in progress")

        resolved_dir = Path(local_dir).expanduser().resolve()
        resolved_dir.mkdir(parents=True, exist_ok=True)
        state_dir = _state_dir(settings)
        state_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "nexus.api.local_download_worker",
            "--repo-id",
            repo_id,
            "--local-dir",
            str(resolved_dir),
            *[argument for filename in files for argument in ("--file", filename)],
        ]
        try:
            with (state_dir / DOWNLOAD_LOG_FILENAME).open("ab") as log_handle:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                    start_new_session=True,
                )
        except OSError as exc:
            raise LocalInferenceError(
                f"Failed to spawn local-model download worker: {exc}"
            ) from exc

        record = {
            "pid": process.pid,
            "family": family,
            "quant": quant,
            "repo_id": repo_id,
            "local_dir": str(resolved_dir),
            "files": files,
            "total_bytes": total_bytes,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _write_json(_download_path(settings), record)
        except LocalInferenceError:
            try:
                _signal_process_group(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            raise
        return record


def _downloaded_bytes(record: dict[str, Any]) -> int:
    """Sum completed target files plus any in-flight download blob.

    huggingface_hub stages each file as a HASH-named ``*.incomplete`` under
    ``<local_dir>/.cache/huggingface/download`` and moves it to the final path
    on completion — so a file is EITHER a final target OR an in-flight blob,
    never both (verified: no ``*.incomplete`` lingers after a file completes).
    We therefore count finals and cache-scoped incompletes separately, which is
    correct by construction. Granularity is per-completed-file at minimum;
    sub-file progress is best-effort and depends on how eagerly hf flushes the
    staged blob to disk. (The prior per-filename glob never matched hf's
    hash-named blob at all, so it only ever advanced per completed file.)
    """
    local_dir = Path(record["local_dir"])
    downloaded = 0
    for filename in record["files"]:
        try:
            downloaded += (local_dir / filename).stat().st_size
        except FileNotFoundError:
            pass
    cache = local_dir / ".cache" / "huggingface" / "download"
    if cache.exists():
        for partial in cache.rglob("*.incomplete"):
            try:
                downloaded += partial.stat().st_size
            except FileNotFoundError:
                pass
    return downloaded


def _download_error(settings: Settings) -> str:
    """Return the final non-empty worker log line, if the worker wrote one."""
    try:
        lines = (
            (Path(_state_dir(settings)) / DOWNLOAD_LOG_FILENAME)
            .read_text()
            .splitlines()
        )
    except FileNotFoundError:
        lines = []
    return next(
        (line.strip() for line in reversed(lines) if line.strip()),
        "download did not complete",
    )


def download_status() -> dict[str, Any] | None:
    """Rediscover and report the detached curated-model download."""
    with _download_lock:
        settings = load_settings()
        record = _read_download_record(settings)
        if record is None:
            return None
        pid_alive = _pid_alive(record["pid"]) and _download_process_is_ours(
            settings, record["pid"], record["repo_id"]
        )
        local_dir = Path(record["local_dir"])
        targets = [local_dir / filename for filename in record["files"]]
        downloaded_bytes = _downloaded_bytes(record)
        total_bytes = record["total_bytes"]
        progress = (
            min(1.0, max(0.0, downloaded_bytes / total_bytes))
            if total_bytes > 0
            else 0.0
        )
        payload: dict[str, Any] = {
            "state": "downloading",
            "family": record["family"],
            "quant": record["quant"],
            "downloaded_bytes": downloaded_bytes,
            "total_bytes": total_bytes,
            "progress": progress,
            "files": record["files"],
            "local_dir": record["local_dir"],
        }
        if pid_alive:
            return payload
        if (
            all(target.is_file() for target in targets)
            and inspect_gguf(str(targets[0])).valid
        ):
            payload["state"] = "done"
            return payload
        payload["state"] = "failed"
        payload["error"] = _download_error(settings)
        return payload


def cancel_download() -> dict[str, Any]:
    """Stop the detached download process group and clear its job record."""
    with _download_lock:
        settings = load_settings()
        record = _read_download_record(settings)
        if record is None or not _pid_alive(record["pid"]):
            return {"cancelled": False, "reason": "no active download"}
        pid = record["pid"]
        if not _download_process_is_ours(settings, pid, record["repo_id"]):
            _download_path(settings).unlink(missing_ok=True)
            return {"cancelled": False, "reason": "no active download"}
        try:
            _signal_process_group(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if settings.runtime is None:
            raise LocalInferenceError("[runtime] is required for shutdown settings")
        health = settings.runtime.health
        deadline = time.monotonic() + health.stop_grace_seconds
        while (
            _pid_alive(pid)
            and _download_process_is_ours(settings, pid, record["repo_id"])
            and time.monotonic() < deadline
        ):
            time.sleep(health.poll_interval_seconds)
        if _pid_alive(pid) and _download_process_is_ours(
            settings, pid, record["repo_id"]
        ):
            try:
                _signal_process_group(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        _download_path(settings).unlink(missing_ok=True)
        return {"cancelled": True}


def delete_model(path: str) -> dict[str, Any]:
    """Delete a root-validated GGUF shard set unless one shard is active."""
    with _lifecycle_lock:
        candidate = Path(path).resolve()
        shards = shard_set(candidate, _allowed_roots())
        current = active()
        if current is not None:
            active_path = Path(current["gguf_path"]).resolve()
            if active_path in shards:
                raise LocalInferenceError("Cannot delete the active local model")

        deleted: list[str] = []
        for shard in shards:
            try:
                os.remove(shard)
            except FileNotFoundError:
                continue
            deleted.append(str(shard))

        requested = str(candidate)
        with _registration_lock:
            paths = registered_paths()
            was_registered = requested in paths
            if was_registered:
                paths.remove(requested)
                _write_json(_registered_path(load_settings()), paths)
        return {"deleted": deleted, "was_registered": was_registered}


def registered_paths() -> list[str]:
    """Return persisted external GGUF paths."""
    settings = load_settings()
    value = _read_json(_registered_path(settings))
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LocalInferenceError("Malformed local-model registration state")
    return value


def register_path(path: str) -> list[str]:
    """Persist a verified external GGUF path for future discovery."""
    candidate = str(Path(path).expanduser().resolve())
    info = inspect_gguf(candidate)
    if not info.valid:
        raise LocalInferenceError(info.reason or f"Invalid GGUF file: {candidate}")
    with _registration_lock:
        paths = registered_paths()
        if candidate not in paths:
            paths.append(candidate)
            _write_json(_registered_path(load_settings()), sorted(paths))
        return paths
