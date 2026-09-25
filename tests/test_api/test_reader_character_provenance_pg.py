"""Real stub persistence and character-card reads on disposable databases.

Requires template characters, character_aliases, places, entities, and portrait
tables. No saved story is changed and no inference is needed.
"""

from collections.abc import Iterator
from contextlib import closing

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2.extras import RealDictCursor
import pytest

from nexus.agents.orrery.retrograde_persistence import _insert_character_stub
from nexus.api import reader_endpoints, slot_utils
from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist


pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def character_slot(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Keep the real router and SQL while routing slot 4 to a private clone."""
    with disposable_slot_database("qa946_character") as dbname:
        slot_utils.VALID_DBNAMES.add(dbname)
        monkeypatch.setattr(slot_utils, "slot_dbname", lambda _slot: dbname)
        try:
            seed_protagonist(dbname)
            yield dbname
        finally:
            slot_utils.VALID_DBNAMES.discard(dbname)


@pytest.mark.parametrize("legacy", [False, True])
def test_character_card_reads_preserve_provenance_and_later_facts(
    character_slot: str, legacy: bool
) -> None:
    """New and existing stubs stay sparse across reads, then expose real facts."""
    sources = [{"plan": "event_plan", "event_ref": "harbor_rescue"}]
    with closing(connect(character_slot, cursor_factory=RealDictCursor)) as conn:
        with conn, conn.cursor() as cur:
            assert _insert_character_stub(
                cur, entity_ref="Nell Rourke", sources=sources
            )
            cur.execute("SELECT * FROM characters WHERE name = 'Nell Rourke'")
            inserted = dict(cur.fetchone())
            assert inserted["summary"] is None
            assert inserted["background"] is None
            assert inserted["current_activity"] is None
            assert inserted["extra_data"] == {
                "source": "retrograde",
                "stub_kind": "retrograde_expansion_ref",
                "sources": sources,
            }
            if legacy:
                cur.execute(
                    """
                    UPDATE characters SET summary = %s, background = %s,
                        current_activity = %s WHERE id = %s
                    """,
                    (
                        "Retrograde-generated character stub for Nell Rourke. "
                        "Created so Skald-selected setup history can resolve "
                        "to canonical rows.",
                        "Retrograde-generated stub; details intentionally sparse "
                        "until play.",
                        "latent in generated backstory",
                        inserted["id"],
                    ),
                )
            cur.execute("SELECT * FROM characters WHERE id = %s", (inserted["id"],))
            stored = dict(cur.fetchone())

    app = FastAPI()
    app.include_router(reader_endpoints.router)
    # A new client performs a fresh read, like reloading the rendered card.
    for _ in range(2):
        with TestClient(app) as client:
            response = client.get("/api/characters?slot=4")
            assert response.status_code == 200, response.text
            nell = next(row for row in response.json() if row["id"] == inserted["id"])
            assert nell["summary"] is None
            assert nell["background"] is None
            assert nell["currentActivity"] is None
            assert nell["extraData"] == stored["extra_data"]

    with closing(connect(character_slot, cursor_factory=RealDictCursor)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM characters WHERE id = %s", (inserted["id"],))
            assert dict(cur.fetchone()) == stored
            cur.execute(
                """
                UPDATE characters SET summary = %s, background = %s,
                    current_activity = %s WHERE id = %s
                """,
                (
                    "Nell keeps the rescue ledger.",
                    "A former shipwright.",
                    "Sorting repair slips.",
                    inserted["id"],
                ),
            )
    with TestClient(app) as client:
        response = client.get("/api/characters?slot=4")
        assert response.status_code == 200, response.text
        nell = next(row for row in response.json() if row["id"] == inserted["id"])
        assert nell["summary"] == "Nell keeps the rescue ledger."
        assert nell["background"] == "A former shipwright."
        assert nell["currentActivity"] == "Sorting repair slips."
        assert nell["extraData"] == stored["extra_data"]
