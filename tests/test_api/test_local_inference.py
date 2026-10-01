"""Unit tests for detached local inference state and spawning."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, cast

import pytest
import tomlkit

from nexus.api import local_download_worker, local_inference
from nexus.config import load_settings
from nexus.runtime.log_capture import CapturedProcess, pid_alive, rotated_segment
from nexus.util.gguf_inspect import GgufInfo

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def reaped_pid() -> int:
    """The pid of a process this test started and reaped: never a live writer."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _settings_with_state_dir(tmp_path: Path):
    settings = load_settings()
    assert settings.runtime is not None
    settings.runtime.state_dir = str(tmp_path)
    return settings


def test_active_discards_dead_pid_after_readiness(tmp_path: Path, monkeypatch) -> None:
    """A process observed ready is inactive, rather than failed, after exit."""
    settings = _settings_with_state_dir(tmp_path)
    state_path = tmp_path / local_inference.STATE_FILENAME
    state_path.write_text(
        json.dumps(
            {
                "pid": 987654321,
                "gguf_path": "/tmp/model.gguf",
                "port": 1234,
                "started_at": "2026-01-01T00:00:00+00:00",
                "ready_observed": True,
            }
        )
    )
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)

    assert local_inference.active() is None
    assert not state_path.exists()


def test_activate_spawns_detached_and_records_state(
    tmp_path: Path, monkeypatch, reaped_pid: int
) -> None:
    """Activation uses a new session and returns before a health wait."""
    settings = _settings_with_state_dir(tmp_path)
    gguf_path = tmp_path / "model.gguf"
    gguf_path.write_bytes(b"GGUF")
    calls = []

    def fake_spawn_captured(argv, **kwargs):
        calls.append((argv, kwargs))
        return CapturedProcess(pid=43210, writer_pid=reaped_pid)

    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(
        local_inference,
        "inspect_gguf",
        lambda path: GgufInfo(architecture="test", quantization="Q4_K_M", valid=True),
    )
    monkeypatch.setattr(local_inference, "_read_active", lambda value: None)
    monkeypatch.setattr(
        local_inference, "_port_open", lambda settings, host, port: False
    )
    assert settings.runtime is not None
    settings.runtime.services["llama_server"].command = [
        "/fake/llama-server",
        "--model",
        "/configured/model.gguf",
        "--alias",
        "configured-alias",
        "--host",
        "{host}",
        "--port",
        "{port}",
        "--ctx-size",
        "6543",
        "--custom-flag",
    ]
    monkeypatch.setattr(local_inference.shutil, "which", lambda value: value)
    monkeypatch.setattr(
        local_inference.log_capture, "spawn_captured", fake_spawn_captured
    )

    result = local_inference.activate(str(gguf_path))

    assert result == {
        "gguf_path": str(gguf_path),
        "pid": 43210,
        "ready": False,
        "failed": False,
    }
    assert calls[0][1]["popen_kwargs"]["start_new_session"] is True
    assert calls[0][1]["popen_kwargs"]["close_fds"] is True
    assert calls[0][1]["log_path"] == tmp_path / local_inference.LOG_FILENAME
    command = calls[0][0]
    assert command.count("--model") == 1
    assert command.count("--alias") == 1
    assert "/configured/model.gguf" not in command
    assert "configured-alias" not in command
    assert command[-3:] == ["--ctx-size", "6543", "--custom-flag"]
    record = json.loads((tmp_path / local_inference.STATE_FILENAME).read_text())
    assert record["pid"] == 43210
    assert record["log_writer_pid"] == reaped_pid
    assert record["gguf_path"] == str(gguf_path)
    assert record["ready_observed"] is False
    assert not list(tmp_path.glob("*.tmp"))


def test_active_surfaces_recent_pre_ready_exit(tmp_path: Path, monkeypatch) -> None:
    """A process that dies during model load remains visible as failed."""
    settings = _settings_with_state_dir(tmp_path)
    state_path = tmp_path / local_inference.STATE_FILENAME
    state_path.write_text(
        json.dumps(
            {
                "pid": 987654321,
                "gguf_path": "/tmp/model.gguf",
                "port": 1234,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ready_observed": False,
            }
        )
    )
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)

    current = local_inference.active()

    assert current is not None
    assert current["failed"] is True
    assert current["ready"] is False
    assert "exited before becoming ready" in current["error"]
    assert json.loads(state_path.read_text())["failed"] is True


def test_active_surfaces_old_pre_ready_exit(tmp_path: Path, monkeypatch) -> None:
    """Never-ready failures remain loud even long after the former window."""
    settings = _settings_with_state_dir(tmp_path)
    state_path = tmp_path / local_inference.STATE_FILENAME
    state_path.write_text(
        json.dumps(
            {
                "pid": 987654321,
                "gguf_path": "/tmp/large-model.gguf",
                "port": 1234,
                "started_at": "2000-01-01T00:00:00+00:00",
                "ready_observed": False,
            }
        )
    )
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)

    current = local_inference.active()

    assert current is not None
    assert current["failed"] is True
    assert current["ready"] is False
    assert "exited before becoming ready" in current["error"]
    persisted = json.loads(state_path.read_text())
    assert persisted["failed"] is True
    assert persisted["gguf_path"] == "/tmp/large-model.gguf"


def test_probes_use_runtime_health_timeout(tmp_path: Path, monkeypatch) -> None:
    """HTTP, socket, and process probes share the configured health timeout."""
    settings = _settings_with_state_dir(tmp_path)
    assert settings.runtime is not None
    settings.runtime.health.timeout_seconds = 7.25
    observed: list[float] = []

    def fake_get(url, timeout):
        observed.append(timeout)
        return SimpleNamespace(status_code=200)

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

        def settimeout(self, timeout):
            observed.append(timeout)

        def connect_ex(self, address):
            return 1

    def fake_run(command, **kwargs):
        observed.append(kwargs["timeout"])
        return SimpleNamespace(
            returncode=0,
            stdout="llama-server --model /tmp/model.gguf",
        )

    monkeypatch.setattr(local_inference.requests, "get", fake_get)
    monkeypatch.setattr(local_inference.socket, "socket", lambda *args: FakeSocket())
    monkeypatch.setattr(local_inference.subprocess, "run", fake_run)

    assert local_inference._health_ok(settings, "127.0.0.1", 1234) is True
    assert local_inference._port_open(settings, "127.0.0.1", 1234) is False
    assert local_inference._process_is_ours(settings, 43210, "/tmp/model.gguf") is True
    assert observed == [7.25, 7.25, 7.25]


def test_deactivate_uses_runtime_poll_interval(tmp_path: Path, monkeypatch) -> None:
    """Shutdown polling sleeps for the configured interval without live I/O."""
    settings = _settings_with_state_dir(tmp_path)
    assert settings.runtime is not None
    settings.runtime.health.poll_interval_seconds = 0.37
    expected_host, expected_port, _ = local_inference._endpoint(settings)
    alive = iter([True, False, False])
    sleeps: list[float] = []
    release_waits: list[tuple[str, int]] = []

    def fake_await_port_release(value, host, port):
        release_waits.append((host, port))
        return True

    def fail_on_port_probe(*args, **kwargs):
        pytest.fail("poll-interval unit test attempted a real port probe")

    monkeypatch.setattr(
        local_inference,
        "_read_active",
        lambda value: {
            "gguf_path": "/tmp/model.gguf",
            "pid": 43210,
            "ready": False,
            "failed": False,
        },
    )
    monkeypatch.setattr(
        local_inference,
        "_process_is_ours",
        lambda value, pid, path: True,
    )
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: next(alive))
    monkeypatch.setattr(local_inference, "_signal_process_group", lambda pid, sig: None)
    monkeypatch.setattr(local_inference, "_await_port_release", fake_await_port_release)
    monkeypatch.setattr(local_inference, "_port_open", fail_on_port_probe)
    monkeypatch.setattr(local_inference.time, "sleep", sleeps.append)

    result = local_inference._deactivate_locked(settings)

    assert result == {"stopped": True, "pid": 43210}
    assert sleeps == [0.37]
    assert release_waits == [(expected_host, expected_port)]


def test_deactivate_does_not_signal_unverified_reused_pid(
    tmp_path: Path, monkeypatch
) -> None:
    """A live PID with the wrong command line is never treated as owned."""
    settings = _settings_with_state_dir(tmp_path)
    state_path = tmp_path / local_inference.STATE_FILENAME
    state_path.write_text(
        json.dumps(
            {
                "pid": 43210,
                "gguf_path": "/tmp/model.gguf",
                "port": 1234,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ready_observed": False,
            }
        )
    )
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        local_inference,
        "_process_is_ours",
        lambda settings, pid, path: False,
    )
    monkeypatch.setattr(
        local_inference,
        "_signal_process_group",
        lambda pid, sig: pytest.fail("unverified PID was signaled"),
    )

    assert local_inference.deactivate() == {"stopped": False}
    assert not state_path.exists()


def test_concurrent_activate_spawns_only_one_process(
    tmp_path: Path, monkeypatch, reaped_pid: int
) -> None:
    """The lifecycle lock closes the check-then-spawn race."""
    settings = _settings_with_state_dir(tmp_path)
    gguf_path = tmp_path / "model.gguf"
    gguf_path.write_bytes(b"GGUF")
    barrier = threading.Barrier(2)
    spawn_count = 0

    def fake_spawn_captured(argv, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        time.sleep(0.05)
        return CapturedProcess(pid=43210, writer_pid=reaped_pid)

    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(
        local_inference,
        "inspect_gguf",
        lambda path: GgufInfo(architecture="test", quantization="Q4_K_M", valid=True),
    )
    monkeypatch.setattr(
        local_inference, "_port_open", lambda settings, host, port: False
    )
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        local_inference,
        "_process_is_ours",
        lambda settings, pid, path: True,
    )
    monkeypatch.setattr(
        local_inference, "_health_ok", lambda settings, host, port: False
    )
    monkeypatch.setattr(local_inference.shutil, "which", lambda value: value)
    monkeypatch.setattr(
        local_inference.log_capture, "spawn_captured", fake_spawn_captured
    )

    def run_activate():
        barrier.wait()
        return local_inference.activate(str(gguf_path))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_activate(), range(2)))

    assert spawn_count == 1
    assert [result["pid"] for result in results] == [43210, 43210]


def test_concurrent_download_spawns_only_one_process(
    tmp_path: Path, monkeypatch, reaped_pid: int
) -> None:
    """The download lock closes the singleton check-then-spawn race."""
    settings = _settings_with_state_dir(tmp_path)
    barrier = threading.Barrier(2)
    spawn_count = 0

    def fake_spawn_captured(argv, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        time.sleep(0.05)
        return CapturedProcess(pid=43210, writer_pid=reaped_pid)

    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: True)
    # This test exercises the lock's check-then-spawn race, so the fake PID
    # must read as ours — the recycled-PID case is covered separately below.
    monkeypatch.setattr(
        local_inference,
        "_download_process_is_ours",
        lambda settings, pid, repo_id: True,
    )
    monkeypatch.setattr(
        local_inference.log_capture, "spawn_captured", fake_spawn_captured
    )

    def run_download():
        barrier.wait()
        try:
            return local_inference.start_download(
                family="test",
                quant="Q4_K_M",
                repo_id="example/test",
                local_dir=str(tmp_path / "models"),
                files=["test.gguf"],
                total_bytes=100,
            )
        except local_inference.LocalInferenceError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_download(), range(2)))

    assert spawn_count == 1
    assert len([result for result in results if isinstance(result, dict)]) == 1
    errors = [
        result
        for result in results
        if isinstance(result, local_inference.LocalInferenceError)
    ]
    assert len(errors) == 1
    assert "already in progress" in str(errors[0])


def test_start_download_ignores_stale_record_with_recycled_pid(
    tmp_path: Path, monkeypatch, reaped_pid: int
) -> None:
    """A live PID recycled by an unrelated process must not block downloads."""
    settings = _settings_with_state_dir(tmp_path)
    _write_download_state(tmp_path, files=["test.gguf"])
    spawned = []

    def fake_spawn_captured(argv, **kwargs):
        spawned.append(argv)
        return CapturedProcess(pid=999, writer_pid=reaped_pid)

    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        local_inference,
        "_download_process_is_ours",
        lambda settings, pid, repo_id: False,
    )
    monkeypatch.setattr(
        local_inference.log_capture, "spawn_captured", fake_spawn_captured
    )

    record = local_inference.start_download(
        family="test",
        quant="Q4_K_M",
        repo_id="example/test",
        local_dir=str(tmp_path / "models"),
        files=["test.gguf"],
        total_bytes=100,
    )

    assert len(spawned) == 1
    assert record["pid"] == 999


def test_start_download_env_controls_xet(
    tmp_path, monkeypatch, reaped_pid: int
) -> None:
    """The worker env carries HF_HUB_DISABLE_XET=1 exactly when configured."""
    from types import SimpleNamespace as NS

    settings = _settings_with_state_dir(tmp_path)
    captured = {}

    def fake_spawn_captured(argv, **kwargs):
        captured.update(kwargs)
        return CapturedProcess(pid=4242, writer_pid=reaped_pid)

    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(
        local_inference.log_capture, "spawn_captured", fake_spawn_captured
    )

    for disable, expected in ((True, "1"), (False, None)):
        captured.clear()
        monkeypatch.setattr(
            local_inference,
            "get_local_models_settings",
            lambda disable=disable: NS(download_disable_xet=disable),
        )
        local_inference.start_download(
            family="test",
            quant="Q4_K_M",
            repo_id="example/test",
            local_dir=str(tmp_path / "models"),
            files=["test.gguf"],
            total_bytes=100,
        )
        assert captured["env"].get("HF_HUB_DISABLE_XET") == expected
        assert captured["popen_kwargs"] == {
            "close_fds": True,
            "start_new_session": True,
        }
        (tmp_path / local_inference.DOWNLOAD_FILENAME).unlink()


def _write_download_state(
    tmp_path: Path,
    *,
    files: list[str],
    total_bytes: int = 100,
    log_writer_pid: int | None = None,
) -> None:
    record: dict[str, Any] = {
        "pid": 43210,
        "family": "test",
        "quant": "Q4_K_M",
        "repo_id": "example/test",
        "local_dir": str(tmp_path / "models"),
        "files": files,
        "total_bytes": total_bytes,
        "started_at": "2026-01-01T00:00:00+00:00",
    }
    if log_writer_pid is not None:
        record["log_writer_pid"] = log_writer_pid
    (tmp_path / local_inference.DOWNLOAD_FILENAME).write_text(json.dumps(record))


def test_download_status_rediscovers_completed_download(
    tmp_path: Path, monkeypatch
) -> None:
    """A dead worker with every valid target is reported as done."""
    settings = _settings_with_state_dir(tmp_path)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "test.gguf").write_bytes(b"GGUF complete")
    _write_download_state(tmp_path, files=["test.gguf"])
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(
        local_inference,
        "inspect_gguf",
        lambda path: GgufInfo(valid=True),
    )

    status = local_inference.download_status()

    assert status is not None
    assert status["state"] == "done"
    assert status["downloaded_bytes"] == len(b"GGUF complete")


def test_download_status_rediscovers_failed_download(
    tmp_path: Path, monkeypatch
) -> None:
    """A dead worker with missing targets reports its final log error."""
    settings = _settings_with_state_dir(tmp_path)
    _write_download_state(tmp_path, files=["missing.gguf"])
    (tmp_path / local_inference.DOWNLOAD_LOG_FILENAME).write_text(
        "starting\n\nrepository file not found\n"
    )
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)

    status = local_inference.download_status()

    assert status is not None
    assert status["state"] == "failed"
    assert status["downloaded_bytes"] == 0
    assert status["error"] == "repository file not found"


def test_download_status_reports_live_progress(tmp_path: Path, monkeypatch) -> None:
    """A rediscovered owned worker includes completed and partial byte progress."""
    settings = _settings_with_state_dir(tmp_path)
    model_dir = tmp_path / "models"
    partial_dir = model_dir / ".cache" / "huggingface" / "download"
    partial_dir.mkdir(parents=True)
    (model_dir / "first.gguf").write_bytes(b"1234")
    (partial_dir / "second.gguf.hash.incomplete").write_bytes(b"12")
    _write_download_state(tmp_path, files=["first.gguf", "second.gguf"], total_bytes=12)
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        local_inference,
        "_download_process_is_ours",
        lambda value, pid, repo_id: True,
    )

    status = local_inference.download_status()

    assert status is not None
    assert status["state"] == "downloading"
    assert status["downloaded_bytes"] == 6
    assert status["progress"] == 0.5


def test_delete_model_rejects_active_shard(tmp_path: Path, monkeypatch) -> None:
    """No shard set containing the serving model can be deleted."""
    settings = _settings_with_state_dir(tmp_path)
    first = tmp_path / "Hermes-Q6_K-00001-of-00002.gguf"
    second = tmp_path / "Hermes-Q6_K-00002-of-00002.gguf"
    first.write_bytes(b"GGUF first")
    second.write_bytes(b"GGUF second")
    monkeypatch.setattr(
        local_inference,
        "get_local_models_settings",
        lambda: SimpleNamespace(models_dir=str(tmp_path)),
    )
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(
        local_inference,
        "active",
        lambda: {"gguf_path": str(second), "ready": True, "pid": 123},
    )

    with pytest.raises(local_inference.LocalInferenceError, match="active"):
        local_inference.delete_model(str(first))

    assert first.exists()
    assert second.exists()


def test_delete_model_removes_all_shards(tmp_path: Path, monkeypatch) -> None:
    """Deleting a split model removes every matching root-validated shard."""
    settings = _settings_with_state_dir(tmp_path)
    first = tmp_path / "Hermes-Q6_K-00001-of-00002.gguf"
    second = tmp_path / "Hermes-Q6_K-00002-of-00002.gguf"
    first.write_bytes(b"GGUF first")
    second.write_bytes(b"GGUF second")
    monkeypatch.setattr(
        local_inference,
        "get_local_models_settings",
        lambda: SimpleNamespace(models_dir=str(tmp_path)),
    )
    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "active", lambda: None)
    monkeypatch.setattr(local_inference, "registered_paths", lambda: [])

    result = local_inference.delete_model(str(first))

    assert result == {
        "deleted": [str(first), str(second)],
        "was_registered": False,
    }
    assert not first.exists()
    assert not second.exists()


def test_shard_set_excludes_non_split_path_outside_roots(tmp_path: Path) -> None:
    """A non-split path outside the allowed roots yields no deletable shards."""
    root = tmp_path / "models"
    root.mkdir()
    inside = root / "model.gguf"
    inside.write_bytes(b"GGUF inside")
    outside = tmp_path / "elsewhere.gguf"
    outside.write_bytes(b"GGUF outside")
    roots = (root.resolve(),)

    assert local_inference.shard_set(inside, roots) == [inside.resolve()]
    assert local_inference.shard_set(outside, roots) == []


def test_download_worker_fetches_files_in_order(tmp_path: Path, monkeypatch) -> None:
    """The worker sends each requested shard through hf_hub_download in order."""
    calls = []
    monkeypatch.setattr(
        local_download_worker.sys,
        "argv",
        [
            "local_download_worker",
            "--repo-id",
            "example/test",
            "--local-dir",
            str(tmp_path),
            "--file",
            "first.gguf",
            "--file",
            "second.gguf",
        ],
    )
    monkeypatch.setattr(
        local_download_worker,
        "hf_hub_download",
        lambda **kwargs: calls.append(kwargs),
    )

    assert local_download_worker.main() == 0
    assert calls == [
        {
            "repo_id": "example/test",
            "filename": "first.gguf",
            "local_dir": str(tmp_path),
        },
        {
            "repo_id": "example/test",
            "filename": "second.gguf",
            "local_dir": str(tmp_path),
        },
    ]


def test_deactivate_waits_for_port_release(tmp_path: Path, monkeypatch) -> None:
    """Teardown returns only after the dying server's socket frees.

    The record is unlinked before the wait, so without it an immediate
    follow-up activate (EJECT then APPLY) would fast-probe the port and
    misread the lingering socket as foreign occupancy.
    """
    settings = _settings_with_state_dir(tmp_path)
    state_path = tmp_path / local_inference.STATE_FILENAME
    state_path.write_text("{}")
    probes = {"count": 0}

    def flaky_port_open(settings, host, port):
        # Held for the first two probes (socket teardown lag), then free.
        probes["count"] += 1
        return probes["count"] <= 2

    monkeypatch.setattr(
        local_inference,
        "_read_active",
        lambda value: {
            "pid": 43210,
            "gguf_path": "/served/model.gguf",
            "ready": True,
            "failed": False,
        },
    )
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(
        local_inference, "_process_is_ours", lambda settings, pid, path: True
    )
    monkeypatch.setattr(local_inference, "_signal_process_group", lambda pid, sig: None)
    monkeypatch.setattr(local_inference, "_port_open", flaky_port_open)
    monkeypatch.setattr(local_inference.time, "sleep", lambda seconds: None)

    result = local_inference._deactivate_locked(settings)

    assert result == {"stopped": True, "pid": 43210}
    assert not state_path.exists()
    assert probes["count"] >= 3


def test_swap_proceeds_once_teardown_frees_the_port(
    tmp_path: Path, monkeypatch, reaped_pid: int
) -> None:
    """A swap spawns after real teardown (with its port wait) completes."""
    settings = _settings_with_state_dir(tmp_path)
    gguf_path = tmp_path / "next.gguf"
    gguf_path.write_bytes(b"GGUF")
    probes = {"count": 0}

    def flaky_port_open(settings, host, port):
        probes["count"] += 1
        return probes["count"] <= 2

    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(
        local_inference,
        "inspect_gguf",
        lambda path: GgufInfo(architecture="test", quantization="Q6_K", valid=True),
    )
    monkeypatch.setattr(
        local_inference,
        "_read_active",
        lambda value: {
            "pid": 43210,
            "gguf_path": "/previous/model.gguf",
            "ready": True,
            "failed": False,
        },
    )
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(
        local_inference, "_process_is_ours", lambda settings, pid, path: True
    )
    monkeypatch.setattr(local_inference, "_signal_process_group", lambda pid, sig: None)
    monkeypatch.setattr(local_inference, "_port_open", flaky_port_open)
    monkeypatch.setattr(local_inference.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(local_inference.shutil, "which", lambda value: value)
    monkeypatch.setattr(
        local_inference.log_capture,
        "spawn_captured",
        lambda argv, **kwargs: CapturedProcess(pid=54321, writer_pid=reaped_pid),
    )

    result = local_inference.activate(str(gguf_path))

    # Two held probes inside teardown's release wait, one free probe there,
    # then activate's own fast probe sees it free and spawns.
    assert result["pid"] == 54321
    assert probes["count"] >= 3


def test_swap_rejects_port_held_by_foreign_process(tmp_path: Path, monkeypatch) -> None:
    """A port still held past the release window is treated as foreign."""
    settings = _settings_with_state_dir(tmp_path)
    assert settings.runtime is not None
    settings.runtime.health.port_release_timeout_seconds = 0.01
    gguf_path = tmp_path / "next.gguf"
    gguf_path.write_bytes(b"GGUF")

    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(
        local_inference,
        "inspect_gguf",
        lambda path: GgufInfo(architecture="test", quantization="Q6_K", valid=True),
    )
    monkeypatch.setattr(
        local_inference,
        "_read_active",
        lambda value: {
            "pid": 43210,
            "gguf_path": "/previous/model.gguf",
            "ready": True,
            "failed": False,
        },
    )
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(
        local_inference, "_process_is_ours", lambda settings, pid, path: True
    )
    monkeypatch.setattr(local_inference, "_signal_process_group", lambda pid, sig: None)
    monkeypatch.setattr(
        local_inference, "_port_open", lambda settings, host, port: True
    )
    monkeypatch.setattr(local_inference.time, "sleep", lambda seconds: None)

    with pytest.raises(local_inference.LocalInferenceError, match="already in use"):
        local_inference.activate(str(gguf_path))


# ---------------------------------------------------------------------------
# Local-model captures under the rotation policy (issue #842, slice S3)
# ---------------------------------------------------------------------------

TWO_HUNDRED_LINES = [f"line-{index:03d}".ljust(40, ".") for index in range(1, 201)]
SEED = b"s" * 999 + b"\n"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _llama_server_stub(directory: Path) -> Path:
    """An executable named llama-server that prints 200 lines, then sleeps."""
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / "llama-server"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import time\n"
        "for index in range(1, 201):\n"
        "    print(f'line-{index:03d}'.ljust(40, '.'), flush=True)\n"
        "time.sleep(30)\n"
    )
    stub.chmod(0o755)
    return stub


def _llama_gguf(path: Path) -> Path:
    """A real GGUF v3 header whose general.architecture is llama."""
    arch = b"llama"
    key = b"general.architecture"
    header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0)
    header += struct.pack("<Q", 1)
    header += struct.pack("<Q", len(key)) + key
    header += struct.pack("<I", 8) + struct.pack("<Q", len(arch)) + arch
    path.write_bytes(header)
    return path


@pytest.fixture()
def capture_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real runtime config: tiny rotation limits, a stub llama-server."""
    port = _free_port()
    document: Any = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    runtime = cast(Any, document["runtime"])
    runtime["state_dir"] = str(tmp_path / "state")
    runtime["logs"]["max_bytes"] = 1000
    runtime["logs"]["backup_count"] = 12
    document["global"]["model"]["api_models"]["local"][
        "base_url"
    ] = f"http://127.0.0.1:{port}/v1"
    llama = runtime["services"]["llama_server"]
    llama["port"] = port
    command = [str(part) for part in llama["command"]]
    command[0] = str(_llama_server_stub(tmp_path / "bin"))
    llama["command"] = command
    config = tmp_path / "nexus.toml"
    config.write_text(tomlkit.dumps(document))
    for name in ("NEXUS_HOME", "NEXUS_GATEWAY_PORT", "NEXUS_API_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    (tmp_path / "state").mkdir()
    return config


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _capture_holds(log_path: Path, text: str) -> bool:
    """Whether the current capture holds ``text``; absent mid-rotation is "not yet".

    The writer renames the capture to ``.1`` before it opens the fresh file, so
    a read that lands between the two finds no file.
    """
    try:
        return text in log_path.read_text()
    except FileNotFoundError:
        return False


def test_activate_captures_through_the_writer_under_the_policy(
    tmp_path: Path, capture_config: Path
) -> None:
    """llama-server's capture rotates at start and live, losing no line."""
    log_path = tmp_path / "state" / local_inference.LOG_FILENAME
    log_path.write_bytes(SEED)
    gguf = _llama_gguf(tmp_path / "model.gguf")

    result = local_inference.activate(str(gguf))
    stopped = False
    try:
        record = json.loads(
            (tmp_path / "state" / local_inference.STATE_FILENAME).read_text()
        )
        writer_pid = record["log_writer_pid"]
        deadline = time.monotonic() + 30
        while not _capture_holds(log_path, TWO_HUNDRED_LINES[-1]):
            assert time.monotonic() < deadline, "the 200th line never reached disk"
            time.sleep(0.1)

        # Rotated once before the spawn, then eight times live (24 lines each).
        assert rotated_segment(log_path, 9).read_bytes() == SEED
        assert not rotated_segment(log_path, 10).exists()

        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT)
        env.pop("NEXUS_SLOT", None)
        completed = subprocess.run(
            [sys.executable, "-m", "nexus.cli", "--json", "logs", "local-model"]
            + ["-n", "200"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout)["lines"] == TWO_HUNDRED_LINES

        stopped = local_inference.deactivate()["stopped"]
        assert stopped is True
        assert not pid_alive(writer_pid)
    finally:
        if not stopped:
            _kill_group(result["pid"])


def test_download_capture_rotates_under_the_policy(
    tmp_path: Path, capture_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The download worker's capture rotates at start; the error is its last line."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    log_path = tmp_path / "state" / local_inference.DOWNLOAD_LOG_FILENAME
    log_path.write_bytes(SEED)

    record = local_inference.start_download(
        family="qa842",
        quant="Q4_K_M",
        repo_id="qa842/none",
        local_dir=str(tmp_path / "models"),
        files=["none.gguf"],
        total_bytes=100,
    )
    status: dict[str, Any] | None = None
    try:
        deadline = time.monotonic() + 60
        while True:
            status = local_inference.download_status()
            assert status is not None
            if status["state"] == "failed":
                break
            assert time.monotonic() < deadline, status
            time.sleep(0.2)

        assert rotated_segment(log_path, 1).read_bytes() == SEED
        last_line = next(
            line.strip()
            for line in reversed(log_path.read_text().splitlines())
            if line.strip()
        )
        assert status["error"] == last_line
        assert not pid_alive(record["log_writer_pid"])
    finally:
        if status is None or status["state"] != "failed":
            _kill_group(record["pid"])


def test_download_status_ignores_a_reused_writer_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recorded writer pid now naming another process is never waited on."""
    settings = _settings_with_state_dir(tmp_path)
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        _write_download_state(
            tmp_path, files=["missing.gguf"], log_writer_pid=sleeper.pid
        )
        (tmp_path / local_inference.DOWNLOAD_LOG_FILENAME).write_text(
            "repository file not found\n"
        )
        monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
        monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: False)

        started = time.monotonic()
        status = local_inference.download_status()

        assert status is not None
        assert status["state"] == "failed"
        assert status["error"] == "repository file not found"
        assert time.monotonic() - started < 2
        assert sleeper.poll() is None
    finally:
        sleeper.kill()
        sleeper.wait()
