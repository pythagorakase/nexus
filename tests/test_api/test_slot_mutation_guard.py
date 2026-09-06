"""HTTP target validation and real PostgreSQL write protection for save slots."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg2
import pytest
from fastapi.testclient import TestClient
from psycopg2 import sql

from nexus.api import narrative, new_story_flow, slot_mutations, slot_utils
from nexus.api.save_slots import is_slot_locked, lock_slot, unlock_slot


BODY_MUTATIONS = [
    ("/api/narrative/continue", {}),
    ("/api/narrative/regenerate", {}),
    ("/api/narrative/approve", {}),
    (
        "/api/narrative/select-choice",
        {"chunk_id": 1, "selection": {"label": 1, "text": "Begin"}},
    ),
    ("/api/story/new/setup/start", {}),
    ("/api/story/new/setup/record", {}),
    ("/api/story/new/setup/reset", {}),
    ("/api/story/new/chat", {"message": "Begin"}),
    ("/api/story/new/chat/stream", {"message": "Begin"}),
    ("/api/story/new/transition", {}),
]


@pytest.mark.parametrize(
    "path,body", [*BODY_MUTATIONS, ("/api/story/new/slot/select", {})]
)
@pytest.mark.parametrize("slot", [None, 0, 6, True, False, 1.0, "1"])
def test_mutating_bodies_require_a_valid_explicit_slot(
    path: str, body: dict[str, object], slot: object
) -> None:
    """Omitting a target never selects an environment or default database."""
    payload = dict(body)
    if slot is not None:
        payload["slot"] = slot
    response = TestClient(narrative.app).post(path, json=payload)
    assert response.status_code == 422, response.text
    assert any(error["loc"] == ["body", "slot"] for error in response.json()["detail"])


@pytest.mark.parametrize(
    "method,path",
    [
        ("delete", "/api/narrative/incubator"),
        ("put", "/api/characters/1/images/1/main"),
        ("delete", "/api/characters/1/images/1"),
        ("put", "/api/places/1/images/1/main"),
        ("delete", "/api/places/1/images/1"),
    ],
)
def test_mutating_queries_require_an_explicit_slot(method: str, path: str) -> None:
    """Image and incubator writes cannot inherit the process's active slot."""
    response = TestClient(narrative.app).request(method, path)
    assert response.status_code == 422
    assert any(error["loc"] == ["query", "slot"] for error in response.json()["detail"])


@pytest.mark.parametrize("path", ["accept", "reject", "1/edit-user-input"])
def test_slot_blind_chunk_routes_are_retired(path: str) -> None:
    """The gateway never reaches the legacy default chunk workflow."""
    response = TestClient(narrative.app).post(f"/api/chunks/{path}", json={})
    assert response.status_code in {404, 405}
    assert f"/api/chunks/{path}" not in narrative.app.openapi()["paths"]


def test_path_approval_rejects_missing_or_conflicting_slots() -> None:
    """The retained path alias accepts one unambiguous explicit target."""
    client = TestClient(narrative.app)
    assert client.post("/api/narrative/approve/session").status_code == 422
    response = client.post("/api/narrative/approve/session?slot=4", json={"slot": 5})
    assert response.status_code == 422
    assert response.json()["detail"] == "Body and query slots disagree"


@pytest.fixture
def protected_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Create a tiny isolated database; never change an existing save slot."""
    dbname = f"test_slot_guard_{uuid.uuid4().hex}"
    connection_args = {
        "user": os.environ.get("PGUSER", "pythagor"),
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
    }
    admin = psycopg2.connect(dbname="postgres", **connection_args)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    try:
        with psycopg2.connect(dbname=dbname, **connection_args) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE incubator (id boolean PRIMARY KEY)")
                cur.execute("INSERT INTO incubator VALUES (true)")
                cur.execute("CREATE VIEW incubator_view AS SELECT * FROM incubator")
        conn.close()
        monkeypatch.setattr(
            slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname}
        )
        monkeypatch.setattr(slot_mutations, "slot_dbname", lambda _slot: dbname)
        monkeypatch.setattr(new_story_flow, "slot_dbname", lambda _slot: dbname)
        monkeypatch.setattr(
            narrative,
            "get_db_connection",
            lambda _slot: psycopg2.connect(dbname=dbname, **connection_args),
        )
        yield dbname
    finally:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(dbname))
            )
        admin.close()


@pytest.mark.requires_postgres
def test_locked_slot_rejects_http_side_effects_and_database_writes(
    protected_database: str,
) -> None:
    """The production lock protects SQL and rejects routes before paid/file work."""
    dbname = protected_database
    lock_slot(5, dbname=dbname)
    assert is_slot_locked(5, dbname=dbname)
    client = TestClient(narrative.app)
    for body in ({"commit": False}, {"slot": 5, "commit": False}):
        response = client.post("/api/narrative/approve/session?slot=5", json=body)
        assert response.status_code == 423
    for path, body in BODY_MUTATIONS:
        response = client.post(path, json={**body, "slot": 5})
        assert response.status_code == 423, (path, response.text)
    for method, path in [
        ("delete", "/api/narrative/incubator?slot=5"),
        ("delete", "/api/characters/1/images/1?slot=5"),
        ("delete", "/api/places/1/images/1?slot=5"),
        ("post", "/api/slot/5/undo"),
    ]:
        assert client.request(method, path).status_code == 423
    assert client.get("/api/narrative/incubator?slot=5").status_code == 200
    # Compatibility selection has no current writes and must remain available
    # for locked stories, just like reading their existing narrative.
    response = client.post("/api/story/new/slot/select", json={"slot": 5})
    assert response.status_code == 200
    assert response.json() == {
        "status": "activated",
        "results": {
            "1": "cleared",
            "2": "cleared",
            "3": "cleared",
            "4": "cleared",
            "5": "active",
        },
    }
    assert is_slot_locked(5, dbname=dbname)
    for owner in ["characters", "places"]:
        response = client.post(
            f"/api/{owner}/1/images?slot=5",
            files={"images": ("portrait.png", b"not-written", "image/png")},
        )
        assert response.status_code == 423
    assert client.post("/api/slot/5/model", json={"model": "unused"}).status_code == 423
    conn = narrative.get_db_connection(5)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone()[0] == 1
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cur.execute("DELETE FROM incubator")
    finally:
        conn.close()
    unlock_slot(5, dbname=dbname)
    assert not is_slot_locked(5, dbname=dbname)
    assert client.delete("/api/narrative/incubator?slot=5").status_code == 200
    conn = narrative.get_db_connection(5)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()
