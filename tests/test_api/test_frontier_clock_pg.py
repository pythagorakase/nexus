"""Real slot-state and reader routes against a disposable template clone.

Requires narrative_chunks, chunk_metadata, incubator, global_variables, and
the template's protagonist tables. Only the fixture-owned clone is mutated.
"""

from contextlib import closing
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.api.narrative_schemas import SlotStateResponse
from nexus.api.reader_endpoints import router as reader_router
from nexus.api.slot_endpoints import router as slot_router
from tests.pg_fixtures import connect, seed_protagonist

pytestmark = pytest.mark.requires_postgres


def test_frontier_clock_tracks_only_accepted_playable_chunks(
    offline_gate_db: str,
) -> None:
    """Empty, bootstrap, draft, accepted, and unknown clocks use the real routes."""
    app = FastAPI()
    app.include_router(slot_router)
    app.include_router(reader_router)

    def state(client: TestClient) -> dict:
        response = client.get("/api/slot/4/state")
        assert response.status_code == 200, response.text
        SlotStateResponse.model_validate(response.json())
        return response.json()

    with TestClient(app) as client:
        assert state(client)["frontier_clock"] is None
        seed_protagonist(offline_gate_db, base_timestamp="2189-10-17T18:37:00-04:00")
        with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, authorial_directives) "
                "VALUES ('Synthetic prologue', jsonb_build_array(%s::text))",
                (RETROGRADE_PROLOGUE_MARKER,),
            )
            cur.execute(
                "INSERT INTO incubator (parent_chunk_id, storyteller_text) "
                "VALUES (0, 'An unaccepted opening')"
            )
            conn.commit()
            bootstrap = state(client)
            assert bootstrap["has_pending"] is True
            assert bootstrap["frontier_clock"] is None

            cur.execute("DELETE FROM incubator")
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
                "VALUES ('The platform waits.', 'The platform waits.') RETURNING id"
            )
            parent = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO chunk_metadata "
                "(chunk_id, season, episode, scene, world_layer, time_delta) "
                "VALUES (%s, 1, 1, 1, 'primary', interval '0 minutes')",
                (parent,),
            )
            conn.commit()
            accepted = state(client)["frontier_clock"]
            assert accepted["face"] == "17 Oct 2189 · 22:37"
            reader = client.get("/api/narrative/latest-chunk?slot=4")
            assert reader.status_code == 200, reader.text
            metadata = reader.json()["metadata"]
            assert accepted["face"] == metadata["worldTimeFace"]
            assert datetime.fromisoformat(
                accepted["instant"]
            ) == datetime.fromisoformat(metadata["worldTime"])

            cur.execute(
                "INSERT INTO incubator (parent_chunk_id, storyteller_text, metadata_updates) "
                "VALUES (%s, 'The train arrives.', "
                '\'{"chronology": {"time_delta_minutes": 5}}\')',
                (parent,),
            )
            conn.commit()
            pending = state(client)
            assert pending["has_pending"] is True
            assert pending["frontier_clock"] == accepted

            # Materialize another accepted chunk; the route must select by
            # accepted story order, never the draft or the greatest timestamp.
            cur.execute("DELETE FROM incubator")
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
                "VALUES ('The train arrives.', 'The train arrives.') RETURNING id"
            )
            child = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO chunk_metadata "
                "(chunk_id, season, episode, scene, world_layer, time_delta) "
                "VALUES (%s, 1, 1, 2, 'primary', interval '5 minutes')",
                (child,),
            )
            conn.commit()
            assert state(client)["frontier_clock"]["face"] == "17 Oct 2189 · 22:42"

            cur.execute(
                "UPDATE chunk_metadata SET world_time = NULL WHERE chunk_id = %s",
                (child,),
            )
            conn.commit()
            assert state(client)["frontier_clock"] is None
