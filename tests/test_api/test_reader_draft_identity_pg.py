"""Reader draft identity is per story: stable inside one, renewed on overwrite."""

from contextlib import closing
from datetime import timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2.extras import RealDictCursor
import pytest

from nexus.api import slot_endpoints, slot_state, slot_utils
from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist


pytestmark = pytest.mark.requires_postgres


def _expected_identity(dbname: str, player_id: int) -> str:
    with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT created_at FROM characters WHERE id = %s", (player_id,))
            created_at = cur.fetchone()["created_at"]
    return f"player:{player_id}:{created_at.astimezone(timezone.utc).isoformat()}"


def _snapshot(dbname: str, table: str, where: str = "TRUE") -> dict:
    with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {table} WHERE {where}")
            return dict(cur.fetchone())


@pytest.mark.parametrize("slot_created_at", ["present", "null"])
def test_reader_story_identity_is_stable_and_read_only(
    monkeypatch: pytest.MonkeyPatch, slot_created_at: str
) -> None:
    """Identity survives clock movement and never depends on slot metadata."""
    app = FastAPI()
    app.include_router(slot_endpoints.router)
    identities = []
    for _ in range(2):
        with disposable_slot_database("qa951_identity") as dbname:
            monkeypatch.setattr(
                slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname}
            )
            player_id, _ = seed_protagonist(dbname)
            monkeypatch.setattr(slot_state, "slot_dbname", lambda _slot: dbname)
            if slot_created_at == "null":
                with closing(connect(dbname)) as conn:
                    with conn, conn.cursor() as cur:
                        cur.execute(
                            "UPDATE global_variables SET slot_created_at = NULL "
                            "WHERE id = true"
                        )
            before = _snapshot(dbname, "global_variables", "id = true")
            player_before = _snapshot(dbname, "characters", f"id = {player_id}")
            expected = _expected_identity(dbname, player_id)
            with TestClient(app) as client:
                for _ in range(2):
                    response = client.get("/api/slot/4/state")
                    assert response.status_code == 200
                    assert response.json()["story_id"] == expected
                    assert response.json()["current_chunk_id"] == 0
            assert _snapshot(dbname, "global_variables", "id = true") == before
            assert _snapshot(dbname, "characters", f"id = {player_id}") == player_before
            with closing(connect(dbname)) as conn:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        "UPDATE global_variables SET base_timestamp = %s "
                        "WHERE id = true",
                        ("2200-01-01T00:00:00+00:00",),
                    )
            with TestClient(app) as client:
                assert client.get("/api/slot/4/state").json()["story_id"] == expected
            identities.append(expected)
    assert identities[0] != identities[1]


def test_overwriting_an_occupied_slot_renews_the_story_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replacement story keeps the slot row yet must not inherit old drafts."""
    app = FastAPI()
    app.include_router(slot_endpoints.router)
    with disposable_slot_database("qa951_overwrite") as dbname:
        monkeypatch.setattr(
            slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname}
        )
        monkeypatch.setattr(slot_state, "slot_dbname", lambda _slot: dbname)
        first_player, _ = seed_protagonist(dbname)
        with TestClient(app) as client:
            first = client.get("/api/slot/4/state").json()["story_id"]
        # Captured now: after the overwrite this id names the new protagonist.
        first_expected = _expected_identity(dbname, first_player)
        slot_row = _snapshot(dbname, "global_variables", "id = true")

        # Mirror perform_transition on an occupied slot: the global_variables
        # row is retained, the entity tables are cleared, their sequences are
        # reset, and a new protagonist is created for the replacement story.
        with closing(connect(dbname)) as conn:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE global_variables SET user_character = NULL WHERE id = true"
                )
                cur.execute("DELETE FROM characters")
                cur.execute("DELETE FROM entities")
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence('characters', 'id'), "
                    "1, false)"
                )
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence('entities', 'id'), 1, false)"
                )
        second_player, _ = seed_protagonist(dbname)
        assert second_player == first_player, "the id collides; only time differs"
        after = _snapshot(dbname, "global_variables", "id = true")
        assert after["slot_created_at"] == slot_row["slot_created_at"]

        with TestClient(app) as client:
            second = client.get("/api/slot/4/state").json()["story_id"]
        # The replacement story must not resolve to the first story's drafts.
        assert second != first
        assert first == first_expected
        assert second == _expected_identity(dbname, second_player)
