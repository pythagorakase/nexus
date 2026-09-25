"""Reader draft identity uses existing fresh-slot creation metadata, read-only."""

from contextlib import closing

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2.extras import RealDictCursor
import pytest

from nexus.api import slot_endpoints, slot_state, slot_utils
from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist


pytestmark = pytest.mark.requires_postgres


def test_reader_story_identity_is_stable_and_fresh_on_slot_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two fresh stories at slot 4 have distinct identities without a migration."""
    app = FastAPI()
    app.include_router(slot_endpoints.router)
    identities = []
    for _ in range(2):
        with disposable_slot_database("qa951_identity") as dbname:
            monkeypatch.setattr(
                slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname}
            )
            seed_protagonist(dbname)
            monkeypatch.setattr(slot_state, "slot_dbname", lambda _slot: dbname)
            with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
                with conn, conn.cursor() as cur:
                    cur.execute("SELECT * FROM global_variables WHERE id = true")
                    before = dict(cur.fetchone())
            with TestClient(app) as client:
                first = client.get("/api/slot/4/state")
                second = client.get("/api/slot/4/state")
            assert first.status_code == second.status_code == 200
            story_id = first.json()["story_id"]
            assert story_id == before["slot_created_at"].isoformat()
            assert second.json()["story_id"] == story_id
            assert first.json()["current_chunk_id"] == 0
            identities.append(story_id)
            with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
                with conn, conn.cursor() as cur:
                    cur.execute("SELECT * FROM global_variables WHERE id = true")
                    assert dict(cur.fetchone()) == before
                    cur.execute(
                        "UPDATE global_variables SET base_timestamp = %s WHERE id = true",
                        ("2200-01-01T00:00:00+00:00",),
                    )
            with TestClient(app) as client:
                assert client.get("/api/slot/4/state").json()["story_id"] == story_id
    assert identities[0] != identities[1]
