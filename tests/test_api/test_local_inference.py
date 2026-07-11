"""Unit tests for detached local inference state and spawning."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from nexus.api import local_download_worker, local_inference
from nexus.config import load_settings
from nexus.util.gguf_inspect import GgufInfo


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
    tmp_path: Path, monkeypatch
) -> None:
    """Activation uses a new session and returns before a health wait."""
    settings = _settings_with_state_dir(tmp_path)
    gguf_path = tmp_path / "model.gguf"
    gguf_path.write_bytes(b"GGUF")
    calls = []

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(pid=43210)

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
    monkeypatch.setattr(local_inference.subprocess, "Popen", fake_popen)

    result = local_inference.activate(str(gguf_path))

    assert result == {
        "gguf_path": str(gguf_path),
        "pid": 43210,
        "ready": False,
        "failed": False,
    }
    assert calls[0][1]["start_new_session"] is True
    assert calls[0][1]["close_fds"] is True
    command = calls[0][0]
    assert command.count("--model") == 1
    assert command.count("--alias") == 1
    assert "/configured/model.gguf" not in command
    assert "configured-alias" not in command
    assert command[-3:] == ["--ctx-size", "6543", "--custom-flag"]
    record = json.loads((tmp_path / local_inference.STATE_FILENAME).read_text())
    assert record["pid"] == 43210
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
    """Shutdown polling sleeps for the configured runtime interval."""
    settings = _settings_with_state_dir(tmp_path)
    assert settings.runtime is not None
    settings.runtime.health.poll_interval_seconds = 0.37
    alive = iter([True, False, False])
    sleeps: list[float] = []
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
    monkeypatch.setattr(local_inference.time, "sleep", sleeps.append)

    result = local_inference._deactivate_locked(settings)

    assert result == {"stopped": True, "pid": 43210}
    assert sleeps == [0.37]


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
    tmp_path: Path, monkeypatch
) -> None:
    """The lifecycle lock closes the check-then-spawn race."""
    settings = _settings_with_state_dir(tmp_path)
    gguf_path = tmp_path / "model.gguf"
    gguf_path.write_bytes(b"GGUF")
    barrier = threading.Barrier(2)
    spawn_count = 0

    def fake_popen(command, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        time.sleep(0.05)
        return SimpleNamespace(pid=43210)

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
    monkeypatch.setattr(local_inference.subprocess, "Popen", fake_popen)

    def run_activate():
        barrier.wait()
        return local_inference.activate(str(gguf_path))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_activate(), range(2)))

    assert spawn_count == 1
    assert [result["pid"] for result in results] == [43210, 43210]


def test_concurrent_download_spawns_only_one_process(
    tmp_path: Path, monkeypatch
) -> None:
    """The download lock closes the singleton check-then-spawn race."""
    settings = _settings_with_state_dir(tmp_path)
    barrier = threading.Barrier(2)
    spawn_count = 0

    def fake_popen(command, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        time.sleep(0.05)
        return SimpleNamespace(pid=43210)

    monkeypatch.setattr(local_inference, "load_settings", lambda: settings)
    monkeypatch.setattr(local_inference, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(local_inference.subprocess, "Popen", fake_popen)

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


def _write_download_state(
    tmp_path: Path, *, files: list[str], total_bytes: int = 100
) -> None:
    (tmp_path / local_inference.DOWNLOAD_FILENAME).write_text(
        json.dumps(
            {
                "pid": 43210,
                "family": "test",
                "quant": "Q4_K_M",
                "repo_id": "example/test",
                "local_dir": str(tmp_path / "models"),
                "files": files,
                "total_bytes": total_bytes,
                "started_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )


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
