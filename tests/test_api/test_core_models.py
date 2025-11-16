import pytest
from fastapi.testclient import TestClient

from nexus.api.core import app


@pytest.fixture()
def client() -> TestClient:
  """
  Provide a TestClient instance for exercising the core FastAPI routes.
  """
  return TestClient(app)


@pytest.fixture()
def manager_stub(monkeypatch: pytest.MonkeyPatch) -> dict:
  """
  Replace ModelManager with a controllable stub so tests can assert the HTTP contract
  without touching LM Studio.
  """
  controller: dict = {
      "load_result": True,
      "unload_result": True,
      "loaded_models": [],
      "available_models": [],
  }

  class StubManager:
      def __init__(self, *args, **kwargs):
          controller.setdefault("inits", []).append({"args": args, "kwargs": kwargs})

      def load_model(self, model_id: str, context_window: int | None = None) -> bool:
          controller["last_load"] = {"model_id": model_id, "context_window": context_window}
          result = controller.get("load_result", True)
          if isinstance(result, Exception):
              raise result
          return bool(result)

      def unload_model(self) -> bool:
          controller["unload_called"] = True
          result = controller.get("unload_result", True)
          if isinstance(result, Exception):
              raise result
          return bool(result)

      def get_loaded_models(self) -> list[str]:
          controller["status_checked"] = True
          return list(controller.get("loaded_models", []))

      def update_available_models(self) -> list[str]:
          controller["available_checked"] = True
          return list(controller.get("available_models", []))

  monkeypatch.setattr("nexus.api.core.ModelManager", StubManager)
  return controller


def test_load_model_success(client: TestClient, manager_stub: dict) -> None:
  manager_stub["load_result"] = True

  response = client.post("/api/models/load", json={"model_id": "lmstudio/foo", "context_window": 4096})

  assert response.status_code == 200
  data = response.json()
  assert data["success"] is True
  assert data["model_id"] == "lmstudio/foo"
  assert manager_stub["last_load"] == {"model_id": "lmstudio/foo", "context_window": 4096}


def test_load_model_failure(client: TestClient, manager_stub: dict) -> None:
  manager_stub["load_result"] = False

  response = client.post("/api/models/load", json={"model_id": "lmstudio/foo"})

  assert response.status_code == 200
  data = response.json()
  assert data["success"] is False
  assert data["message"].startswith("Failed to load model")


def test_load_model_exception(client: TestClient, manager_stub: dict) -> None:
  manager_stub["load_result"] = RuntimeError("LM Studio offline")

  response = client.post("/api/models/load", json={"model_id": "lmstudio/foo"})

  assert response.status_code == 500
  assert response.json()["detail"] == "LM Studio offline"


def test_unload_model_success(client: TestClient, manager_stub: dict) -> None:
  manager_stub["unload_result"] = True
  manager_stub["loaded_models"] = ["lmstudio/foo"]

  response = client.post("/api/models/unload")

  assert response.status_code == 200
  data = response.json()
  assert data["success"] is True
  assert data["model_id"] == "lmstudio/foo"
  assert manager_stub["unload_called"] is True


def test_unload_model_failure(client: TestClient, manager_stub: dict) -> None:
  manager_stub["unload_result"] = False

  response = client.post("/api/models/unload")

  assert response.status_code == 200
  data = response.json()
  assert data["success"] is False
  assert data["message"] == "Failed to unload model"


def test_model_status_endpoint(client: TestClient, manager_stub: dict) -> None:
  manager_stub["loaded_models"] = ["alpha", "beta"]

  response = client.get("/api/models/status")

  assert response.status_code == 200
  assert response.json()["loaded_models"] == ["alpha", "beta"]
  assert manager_stub["status_checked"] is True


def test_model_available_endpoint(client: TestClient, manager_stub: dict) -> None:
  manager_stub["available_models"] = ["alpha", "beta"]

  response = client.get("/api/models/available")

  assert response.status_code == 200
  assert response.json()["available_models"] == ["alpha", "beta"]
  assert manager_stub["available_checked"] is True
