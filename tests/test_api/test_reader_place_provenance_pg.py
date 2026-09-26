"""Real place-stub persistence and reader projection on disposable databases.

Requires template places, zones, layers, characters, global_variables and entity
triggers. The fixture creates its own active place and never rewrites a save.
"""

from collections.abc import Iterator
from contextlib import closing

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2.extras import RealDictCursor
import pytest

from nexus.agents.orrery.retrograde_persistence import _insert_place_stub
from nexus.api import reader_endpoints, slot_utils
from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist


pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def place_slot(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Route the real reader and stub producer to a private active story zone."""
    with disposable_slot_database("qa950_place") as dbname:
        slot_utils.VALID_DBNAMES.add(dbname)
        monkeypatch.setattr(slot_utils, "slot_dbname", lambda _slot: dbname)
        try:
            character_id, _ = seed_protagonist(dbname)
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                cur.execute("INSERT INTO layers DEFAULT VALUES RETURNING id")
                layer_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO zones (name, layer) VALUES (%s, %s) RETURNING id",
                    ("Administrative Ring", layer_id),
                )
                zone_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO places (name, type, zone) "
                    "VALUES ('Council Office', 'fixed_location', %s) RETURNING id",
                    (zone_id,),
                )
                place_id = cur.fetchone()[0]
                cur.execute(
                    "UPDATE characters SET current_location = %s WHERE id = %s",
                    (place_id, character_id),
                )
            yield dbname
        finally:
            slot_utils.VALID_DBNAMES.discard(dbname)


@pytest.mark.parametrize("legacy", [False, True])
def test_place_stub_reads_preserve_provenance_and_later_facts(
    place_slot: str, legacy: bool
) -> None:
    """New and historical stubs render sparsely; later facts survive fresh reads."""
    sources = [{"plan": "event_plan", "event_ref": "annex_quarantine"}]
    with closing(connect(place_slot, cursor_factory=RealDictCursor)) as conn:
        with conn, conn.cursor() as cur:
            _insert_place_stub(cur, entity_ref="Old Pump Annex", sources=sources)
            cur.execute("SELECT * FROM places WHERE name = 'Old Pump Annex'")
            inserted = dict(cur.fetchone())
            assert inserted["summary"] is None
            assert inserted["history"] is None
            assert inserted["current_status"] is None
            assert inserted["zone"] is not None
            assert inserted["entity_id"] is not None
            assert inserted["extra_data"] == {
                "source": "retrograde",
                "stub_kind": "retrograde_expansion_ref",
                "sources": sources,
            }
            if legacy:
                cur.execute(
                    "UPDATE places SET summary = %s, current_status = %s WHERE id = %s",
                    (
                        "Retrograde-generated place stub for Old Pump Annex. "
                        "Created so Skald-selected setup history can resolve "
                        "to canonical rows.",
                        "latent in generated backstory",
                        inserted["id"],
                    ),
                )
            cur.execute("SELECT * FROM places WHERE id = %s", (inserted["id"],))
            stored = dict(cur.fetchone())

    app = FastAPI()
    app.include_router(reader_endpoints.router)
    for _ in range(2):
        with TestClient(app) as client:
            response = client.get("/api/places?slot=4")
            assert response.status_code == 200, response.text
            annex = next(row for row in response.json() if row["id"] == inserted["id"])
            assert annex["summary"] is None
            assert annex["history"] is None
            assert annex["currentStatus"] is None
            assert annex["extraData"] == stored["extra_data"]

    with closing(connect(place_slot, cursor_factory=RealDictCursor)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM places WHERE id = %s", (inserted["id"],))
            assert dict(cur.fetchone()) == stored
            cur.execute(
                """
                UPDATE places SET summary = %s, history = %s, current_status = %s
                WHERE id = %s
                """,
                (
                    "The annex houses the station's reserve pumps.",
                    "Built after the south-ring freeze.",
                    "Workers are repairing the intake.",
                    inserted["id"],
                ),
            )
    for _ in range(2):
        with TestClient(app) as client:
            response = client.get("/api/places?slot=4")
            assert response.status_code == 200, response.text
            annex = next(row for row in response.json() if row["id"] == inserted["id"])
            assert annex["summary"] == "The annex houses the station's reserve pumps."
            assert annex["history"] == "Built after the south-ring freeze."
            assert annex["currentStatus"] == "Workers are repairing the intake."
            assert annex["extraData"] == stored["extra_data"]
