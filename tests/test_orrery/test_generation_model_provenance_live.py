"""Rollback-only live coverage for storyteller generation-model provenance."""

from __future__ import annotations

from typing import Any, Iterator
from uuid import uuid4

import pytest
from psycopg2.extras import Json
from sqlalchemy import create_engine, text

from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.narrative_generation import write_to_incubator
from nexus.api.narrative_lease import (
    acquire_generation_lease,
    bind_generation_parent,
)
from tests.pg_fixtures import disposable_slot_database, seed_protagonist, sqlalchemy_url
from nexus.memory.manager import empty_pass2_baseline


pytestmark = pytest.mark.requires_postgres

LIVE_SLOT = 5
TEST_BASELINE_PAYLOAD = empty_pass2_baseline({}).model_dump(mode="json")


class _NonCommittingConnection:
    """Let production transaction helpers run inside the fixture rollback."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def __enter__(self) -> "_NonCommittingConnection":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def commit(self) -> None:
        """Keep writes inside SQLAlchemy's rollback-only outer transaction."""


@pytest.fixture()
def provenance_db() -> Iterator[dict[str, Any]]:
    """Exercise the current schema on a seeded disposable clone."""
    with disposable_slot_database("qa640_provenance") as dbname:
        seed_protagonist(dbname)
        engine = create_engine(sqlalchemy_url(dbname), future=True)
        connection = engine.connect()
        transaction = connection.begin()
        raw_connection = connection.connection.driver_connection
        try:
            with raw_connection.cursor() as cur:
                cur.execute(
                    "INSERT INTO narrative_chunks (raw_text, storyteller_text) VALUES ('Rain falls.', 'Rain falls.') RETURNING id"
                )
                parent_chunk_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO chunk_metadata (chunk_id, season, episode, scene, world_layer) VALUES (%s, 1, 1, 1, 'primary')",
                    (parent_chunk_id,),
                )
            yield {
                "connection": connection,
                "raw_connection": raw_connection,
                "production_connection": _NonCommittingConnection(raw_connection),
                "parent_chunk_id": int(parent_chunk_id),
            }
        finally:
            if transaction.is_active:
                transaction.rollback()
            connection.close()
            engine.dispose()


def _incubator_payload(
    db: dict[str, Any], *, session_id: str, generation_model: str
) -> dict[str, Any]:
    """Build the smallest valid storyteller payload for the production writer."""

    parent_chunk_id = int(db["parent_chunk_id"])
    return {
        "chunk_id": None,
        "parent_chunk_id": parent_chunk_id,
        "user_text": "Continue the rollback-only provenance fixture.",
        "storyteller_text": "Rain stipples the empty platform.",
        "generation_model": generation_model,
        "choice_object": None,
        "choice_text": None,
        "metadata_updates": {
            "chronology": {
                "episode_transition": "continue",
                "time_delta_minutes": 1,
            },
            "world_layer": "primary",
        },
        "entity_updates": {},
        "reference_updates": {"characters": [], "places": [], "factions": []},
        "orrery_proposal": None,
        "orrery_adjudications": [],
        "new_entities": [],
        "lore_pass_baseline": TEST_BASELINE_PAYLOAD,
        "session_id": session_id,
        "llm_response_id": f"rollback-{uuid4().hex[:12]}",
        "status": "provisional",
    }


def _own_parent(db: dict[str, Any], session_id: str) -> None:
    """Establish the production writer precondition inside the rollback fixture."""
    conn = db["production_connection"]
    conflict = acquire_generation_lease(
        conn,
        session_id=session_id,
        operation="continue",
        stale_timeout_seconds=60,
    )
    assert conflict is None
    bind_generation_parent(
        conn,
        session_id=session_id,
        parent_chunk_id=int(db["parent_chunk_id"]),
    )


@pytest.mark.asyncio
async def test_sync_accept_copies_incubator_generation_model(
    provenance_db: dict[str, Any],
) -> None:
    """The synchronous accept path preserves the successful model id."""

    session_id = str(uuid4())
    _own_parent(provenance_db, session_id)
    await write_to_incubator(
        provenance_db["production_connection"],
        _incubator_payload(
            provenance_db,
            session_id=session_id,
            generation_model="gpt-5.6-provenance-fixture",
        ),
    )

    chunk_id = commit_incubator_to_database_sync(
        provenance_db["production_connection"], session_id, slot=LIVE_SLOT
    )

    stored_model = (
        provenance_db["connection"]
        .execute(
            text(
                "SELECT generation_model FROM chunk_metadata WHERE chunk_id = :chunk_id"
            ),
            {"chunk_id": chunk_id},
        )
        .scalar_one()
    )
    assert stored_model == "gpt-5.6-provenance-fixture"


@pytest.mark.asyncio
async def test_regenerate_singleton_write_replaces_generation_model(
    provenance_db: dict[str, Any],
) -> None:
    """The production DELETE+INSERT path replaces, rather than retains, the stamp."""

    session_id = str(uuid4())
    first = _incubator_payload(
        provenance_db,
        session_id=session_id,
        generation_model="first-generation-model",
    )
    second = _incubator_payload(
        provenance_db,
        session_id=session_id,
        generation_model="regenerating-model",
    )

    _own_parent(provenance_db, session_id)
    await write_to_incubator(provenance_db["production_connection"], first)
    await write_to_incubator(
        provenance_db["production_connection"],
        second,
        expected_incubator_session=session_id,
    )

    row = (
        provenance_db["connection"]
        .execute(text("SELECT count(*), min(generation_model) FROM incubator"))
        .one()
    )
    assert tuple(row) == (1, "regenerating-model")


def test_sync_accept_allows_historical_null_generation_model(
    provenance_db: dict[str, Any],
) -> None:
    """A pre-082-shaped incubator insert commits with NULL provenance."""

    session_id = str(uuid4())
    payload = _incubator_payload(
        provenance_db,
        session_id=session_id,
        generation_model="unused-by-historical-insert",
    )
    with provenance_db["raw_connection"].cursor() as cur:
        cur.execute("DELETE FROM incubator WHERE id = TRUE")
        cur.execute(
            """
            INSERT INTO incubator (
                id, chunk_id, parent_chunk_id, user_text, storyteller_text,
                choice_object, choice_text, metadata_updates, entity_updates,
                reference_updates, orrery_proposal, orrery_adjudications,
                new_entities, lore_pass_baseline, session_id, llm_response_id,
                status
            ) VALUES (
                TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                payload["chunk_id"],
                payload["parent_chunk_id"],
                payload["user_text"],
                payload["storyteller_text"],
                None,
                None,
                Json(payload["metadata_updates"]),
                Json(payload["entity_updates"]),
                Json(payload["reference_updates"]),
                None,
                Json([]),
                Json([]),
                Json(TEST_BASELINE_PAYLOAD),
                payload["session_id"],
                payload["llm_response_id"],
                payload["status"],
            ),
        )

    chunk_id = commit_incubator_to_database_sync(
        provenance_db["production_connection"], session_id, slot=LIVE_SLOT
    )

    stored_model = (
        provenance_db["connection"]
        .execute(
            text(
                "SELECT generation_model FROM chunk_metadata WHERE chunk_id = :chunk_id"
            ),
            {"chunk_id": chunk_id},
        )
        .scalar_one()
    )
    assert stored_model is None
