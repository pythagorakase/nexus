"""Runtime status endpoint regressions."""

from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import db_pool
from nexus.api import runtime_status


def test_database_status_uses_api_connection_path(monkeypatch):
    """The status probe must reuse API DB connection settings."""

    calls: list[str] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql: str) -> None:
            assert sql == "SELECT 1"

        def fetchone(self) -> tuple[int]:
            return (1,)

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    @contextmanager
    def fake_get_connection(dbname: str):
        calls.append(dbname)
        yield FakeConnection()

    monkeypatch.setenv("NEXUS_SLOT", "5")
    monkeypatch.setattr(db_pool, "get_connection", fake_get_connection)

    assert runtime_status._database_status() == {
        "ok": True,
        "slot": 5,
        "dbname": "save_05",
    }
    assert calls == ["save_05"]


def test_runtime_status_endpoint_offloads_sync_builder(monkeypatch):
    """The async endpoint must not run sync health probes on the event loop."""

    calls = []

    def fake_build_runtime_status():
        return {"ok": True}

    async def fake_to_thread(func):
        calls.append(func)
        return func()

    monkeypatch.setattr(
        runtime_status, "build_runtime_status", fake_build_runtime_status
    )
    monkeypatch.setattr(runtime_status.asyncio, "to_thread", fake_to_thread)

    app = FastAPI()
    runtime_status.register_runtime_status(app)

    response = TestClient(app).get("/runtime/status")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == [fake_build_runtime_status]
