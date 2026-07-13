"""Hermetic HTTP tests for the local-model management router."""

from pathlib import Path
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import local_models_endpoints
from nexus.config.settings_models import LocalModelCatalogEntry, LocalModelsSettings
from nexus.util.gguf_inspect import GgufInfo


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(local_models_endpoints.router)
    return TestClient(app)


@pytest.fixture
def fake_settings(tmp_path: Path, monkeypatch) -> LocalModelsSettings:
    settings = LocalModelsSettings(
        models_dir=str(tmp_path),
        catalog=[
            LocalModelCatalogEntry(
                family="test",
                label="Test Q4",
                hf_repo="example/test",
                subdir="Test-GGUF",
                filename="test.gguf",
                quant="Q4_K_M",
                size_gb=1,
                min_ram_gb=2,
            )
        ],
    )
    monkeypatch.setattr(
        local_models_endpoints, "get_local_models_settings", lambda: settings
    )
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "get_local_models_settings",
        lambda: settings,
    )
    return settings


def test_status_shape(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    tmp_path: Path,
    monkeypatch,
) -> None:
    model = tmp_path / "test.gguf"
    model.write_bytes(b"GGUF fake")
    monkeypatch.setattr(local_models_endpoints.local_inference, "active", lambda: None)
    monkeypatch.setattr(
        local_models_endpoints.local_inference, "registered_paths", lambda: []
    )
    monkeypatch.setattr(
        local_models_endpoints,
        "inspect_gguf",
        lambda path: GgufInfo(architecture="llama", quantization="Q4_K_M", valid=True),
    )

    response = client.get("/api/local-models/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["models_dir"] == str(tmp_path)
    assert payload["catalog"][0]["family"] == "test"
    assert payload["active"] is None
    assert payload["installed"] == [
        {
            "path": str(model),
            "filename": "test.gguf",
            "arch": "llama",
            "quant": "Q4_K_M",
            "size_bytes": len(b"GGUF fake"),
            "verified": True,
            "active": False,
        }
    ]
    # GiB units so the client can compare against catalog min_ram_gb directly.
    assert isinstance(payload["system_ram_gb"], float)
    assert payload["system_ram_gb"] > 0


def test_status_surfaces_failed_load(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "active",
        lambda: {
            "gguf_path": "/allowed/model.gguf",
            "pid": 43210,
            "ready": False,
            "failed": True,
            "error": "llama-server exited before becoming ready",
        },
    )
    monkeypatch.setattr(
        local_models_endpoints.local_inference, "registered_paths", lambda: []
    )

    active = client.get("/api/local-models/status").json()["active"]

    assert active == {
        "gguf_path": "/allowed/model.gguf",
        "ready": False,
        "failed": True,
        "error": "llama-server exited before becoming ready",
    }


def test_browse_rejects_relative_traversal(
    client: TestClient, fake_settings: LocalModelsSettings
) -> None:
    response = client.get("/api/local-models/browse", params={"dir": "../../etc"})

    assert response.status_code == 400


def test_browse_rejects_absolute_path_outside_roots(
    client: TestClient, fake_settings: LocalModelsSettings
) -> None:
    response = client.get("/api/local-models/browse", params={"dir": "/etc"})

    assert response.status_code == 400


def test_activate_404s_non_gguf(
    client: TestClient, fake_settings: LocalModelsSettings, tmp_path: Path, monkeypatch
) -> None:
    invalid = tmp_path / "not-gguf.bin"
    invalid.write_bytes(b"NOPE")
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "activate",
        lambda path: pytest.fail("manager must not be called for an invalid GGUF"),
    )

    response = client.post("/api/local-models/activate", json={"path": str(invalid)})

    assert response.status_code == 404


def test_register_rejects_non_gguf(
    client: TestClient, fake_settings: LocalModelsSettings, tmp_path: Path, monkeypatch
) -> None:
    invalid = tmp_path / "not-gguf.gguf"
    invalid.write_bytes(b"NOPE")
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "register_path",
        lambda path: pytest.fail("invalid GGUF must not be persisted"),
    )

    response = client.post("/api/local-models/register", json={"path": str(invalid)})

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("endpoint", "expected_status"),
    [("activate", 404), ("register", 400)],
)
def test_actions_reject_out_of_root_valid_gguf_before_inspection(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    monkeypatch,
    endpoint: str,
    expected_status: int,
) -> None:
    """Even a valid GGUF is outside the parser surface when outside roots."""
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        outside = Path(directory) / "valid.gguf"
        outside.write_bytes(b"GGUF")
        monkeypatch.setattr(
            local_models_endpoints,
            "inspect_gguf",
            lambda path: pytest.fail("out-of-root file reached GGUF inspection"),
        )

        response = client.post(
            f"/api/local-models/{endpoint}", json={"path": str(outside)}
        )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": "No accessible GGUF model at the requested path."
    }


@pytest.mark.parametrize(
    ("endpoint", "expected_status"),
    [("activate", 404), ("register", 400)],
)
def test_action_failures_have_one_non_oracular_response(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    tmp_path: Path,
    endpoint: str,
    expected_status: int,
) -> None:
    missing = tmp_path / "secret-name.gguf"
    wrong_magic = tmp_path / "readable-secret-name.gguf"
    wrong_magic.write_bytes(b"NOPE")
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        outside = Path(directory) / "outside-secret-name.gguf"
        outside.write_bytes(b"GGUF")
        requested = [missing, wrong_magic, outside]
        responses = [
            client.post(f"/api/local-models/{endpoint}", json={"path": str(path)})
            for path in requested
        ]

    assert {response.status_code for response in responses} == {expected_status}
    details = {response.json()["detail"] for response in responses}
    assert details == {"No accessible GGUF model at the requested path."}
    for path in requested:
        assert all(str(path) not in response.text for response in responses)


def test_status_collapses_split_gguf_to_first_shard(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    tmp_path: Path,
    monkeypatch,
) -> None:
    first = tmp_path / "Hermes-Q6_K-00001-of-00002.gguf"
    second = tmp_path / "Hermes-Q6_K-00002-of-00002.gguf"
    first.write_bytes(b"GGUF first")
    second.write_bytes(b"GGUF second shard")
    monkeypatch.setattr(local_models_endpoints.local_inference, "active", lambda: None)
    monkeypatch.setattr(
        local_models_endpoints.local_inference, "registered_paths", lambda: []
    )
    monkeypatch.setattr(
        local_models_endpoints,
        "inspect_gguf",
        lambda path: GgufInfo(architecture="llama", quantization="Q6_K", valid=True),
    )

    installed = client.get("/api/local-models/status").json()["installed"]

    assert [entry["path"] for entry in installed] == [str(first)]
    assert installed[0]["size_bytes"] == first.stat().st_size + second.stat().st_size
    assert installed[0]["quant"] == "Q6_K"


def test_status_ignores_stale_out_of_root_registration(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        outside = Path(directory) / "registered.gguf"
        outside.write_bytes(b"GGUF")
        monkeypatch.setattr(
            local_models_endpoints.local_inference, "active", lambda: None
        )
        monkeypatch.setattr(
            local_models_endpoints.local_inference,
            "registered_paths",
            lambda: [str(outside)],
        )
        monkeypatch.setattr(
            local_models_endpoints,
            "inspect_gguf",
            lambda path: pytest.fail("stale out-of-root registration was inspected"),
        )

        installed = client.get("/api/local-models/status").json()["installed"]

    assert installed == []


def test_activate_rejects_non_first_split_shard(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    tmp_path: Path,
    monkeypatch,
) -> None:
    second = tmp_path / "Hermes-Q6_K-00002-of-00002.gguf"
    second.write_bytes(b"GGUF")
    monkeypatch.setattr(
        local_models_endpoints,
        "inspect_gguf",
        lambda path: pytest.fail("non-first shard reached GGUF inspection"),
    )

    response = client.post("/api/local-models/activate", json={"path": str(second)})

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "No accessible GGUF model at the requested path."
    )


def test_download_endpoint_rejects_unknown_catalog_entry(
    client: TestClient, fake_settings: LocalModelsSettings, monkeypatch
) -> None:
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "start_download",
        lambda **kwargs: pytest.fail("unknown catalog entry started a download"),
    )

    response = client.post(
        "/api/local-models/download",
        json={"family": "missing", "quant": "Q4_K_M"},
    )

    assert response.status_code == 404


def test_download_endpoint_starts_curated_entry(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []
    expected_status = {
        "state": "downloading",
        "family": "test",
        "quant": "Q4_K_M",
        "downloaded_bytes": 0,
        "total_bytes": 1000**3,
        "progress": 0.0,
        "files": ["test.gguf"],
        "local_dir": str(tmp_path / "Test-GGUF"),
    }
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "start_download",
        lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "download_status",
        lambda: expected_status,
    )

    response = client.post(
        "/api/local-models/download",
        json={"family": "test", "quant": "Q4_K_M"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "started", **expected_status}
    assert calls == [
        {
            "family": "test",
            "quant": "Q4_K_M",
            "repo_id": "example/test",
            "local_dir": str(tmp_path / "Test-GGUF"),
            "files": ["test.gguf"],
            "total_bytes": 1000**3,
        }
    ]


def test_download_endpoint_returns_already_installed(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    tmp_path: Path,
    monkeypatch,
) -> None:
    model_dir = tmp_path / "Test-GGUF"
    model_dir.mkdir()
    (model_dir / "test.gguf").write_bytes(b"GGUF complete")
    monkeypatch.setattr(
        local_models_endpoints,
        "inspect_gguf",
        lambda path: GgufInfo(valid=True),
    )
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "start_download",
        lambda **kwargs: pytest.fail("installed model spawned a download"),
    )

    response = client.post(
        "/api/local-models/download",
        json={"family": "test", "quant": "Q4_K_M"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "already_installed"
    assert response.json()["files"] == ["test.gguf"]


def test_delete_endpoint_rejects_active_model(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    tmp_path: Path,
    monkeypatch,
) -> None:
    model = tmp_path / "active.gguf"
    model.write_bytes(b"GGUF")
    monkeypatch.setattr(
        local_models_endpoints,
        "inspect_gguf",
        lambda path: GgufInfo(valid=True),
    )
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "delete_model",
        lambda path: (_ for _ in ()).throw(
            local_models_endpoints.local_inference.LocalInferenceError(
                "Cannot delete the active local model"
            )
        ),
    )

    response = client.post("/api/local-models/delete", json={"path": str(model)})

    assert response.status_code == 409
    assert model.exists()


def test_delete_failures_have_one_non_oracular_response(
    client: TestClient,
    fake_settings: LocalModelsSettings,
    tmp_path: Path,
    monkeypatch,
) -> None:
    missing = tmp_path / "secret-name.gguf"
    wrong_magic = tmp_path / "readable-secret-name.gguf"
    wrong_magic.write_bytes(b"NOPE")
    manager_calls = []
    original_inspect = local_models_endpoints.inspect_gguf

    def guarded_inspect(path: str):
        assert Path(path).is_relative_to(tmp_path)
        return original_inspect(path)

    monkeypatch.setattr(local_models_endpoints, "inspect_gguf", guarded_inspect)
    monkeypatch.setattr(
        local_models_endpoints.local_inference,
        "delete_model",
        lambda path: manager_calls.append(path),
    )
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        outside = Path(directory) / "outside-secret-name.gguf"
        outside.write_bytes(b"GGUF")
        requested = [missing, wrong_magic, outside]
        responses = [
            client.post("/api/local-models/delete", json={"path": str(path)})
            for path in requested
        ]

    assert {response.status_code for response in responses} == {404}
    assert {response.json()["detail"] for response in responses} == {
        "No accessible GGUF model at the requested path."
    }
    assert manager_calls == []
    for path in requested:
        assert all(str(path) not in response.text for response in responses)
