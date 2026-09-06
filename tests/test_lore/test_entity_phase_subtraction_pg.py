"""Real PostgreSQL coverage for the deterministic subtraction slice of #813.

Uses only a disposable template clone. Required tables: narrative_chunks,
chunk_metadata, characters, character_aliases, entities, places, factions,
chunk_faction_references, global_variables, and world_events; production entity
queries also read their canonical reference/tag tables and views.
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import closing
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.config import load_settings_as_dict
from nexus.memory import ContextMemoryManager
from nexus.memory.divergence import DivergenceResult
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_protagonist,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres


@pytest.fixture(scope="module")
def entity_corpus() -> Iterator[dict[str, Any]]:
    """Seed real typed entities and references without altering any save slot."""
    with disposable_slot_database("nexus_test_813") as dbname:
        character_id, character_entity_id = seed_protagonist(
            dbname, name="Mira Vale", summary="A courier with a known alias."
        )
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO character_aliases (character_id, alias) VALUES (%s, 'Ember')",
                (character_id,),
            )
            cur.execute("INSERT INTO entities (kind) VALUES ('place') RETURNING id")
            place_entity_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO places (name, type, entity_id) "
                "VALUES ('Glass Atrium', 'fixed_location', %s) RETURNING id",
                (place_entity_id,),
            )
            place_id = int(cur.fetchone()[0])
            cur.execute(
                "UPDATE characters SET current_location = %s WHERE id = %s",
                (place_id, character_id),
            )
            cur.execute("INSERT INTO entities (kind) VALUES ('faction') RETURNING id")
            faction_entity_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO factions (id, name, entity_id, primary_location) "
                "VALUES (%s, 'Night Guild', %s, %s) RETURNING id",
                (faction_entity_id, faction_entity_id, place_id),
            )
            faction_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
                "VALUES ('Mira waits in the atrium.', 'Mira waits in the atrium.') "
                "RETURNING id"
            )
            chunk_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO chunk_metadata (chunk_id) VALUES (%s)", (chunk_id,)
            )
            cur.execute(
                "INSERT INTO chunk_faction_references (chunk_id, faction_id) "
                "VALUES (%s, %s)",
                (chunk_id, faction_id),
            )
            cur.execute(
                "INSERT INTO world_events (event_type, tick_chunk_id, actor_entity_id, "
                "world_layer, source, changed_fields, payload) "
                "VALUES ('slept', %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb)",
                (chunk_id, character_entity_id),
            )
        engine = create_engine(sqlalchemy_url(dbname))
        try:
            yield {
                "engine": engine,
                "Session": sessionmaker(bind=engine),
                "character_id": character_id,
                "place_id": place_id,
                "faction_id": faction_id,
                "chunk_id": chunk_id,
            }
        finally:
            engine.dispose()


def test_entity_phase_uses_live_entities_without_dead_relation_queries(
    entity_corpus: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The real phase returns populated dossiers and never attempts dead SQL."""
    engine = entity_corpus["engine"]
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT to_regclass('events'), to_regclass('threats')")
        ).one() == (None, None)
        events_before = conn.execute(
            text("SELECT to_jsonb(e) FROM world_events e")
        ).all()

    statements: list[str] = []

    def record_sql(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    lore = SimpleNamespace(
        settings=load_settings_as_dict(),
        memnon=SimpleNamespace(Session=entity_corpus["Session"]),
        enable_logon=False,
    )
    turn = TurnContext(
        turn_id="dead-query-subtraction",
        user_input="Continue.",
        start_time=0,
        warm_slice=[{"id": entity_corpus["chunk_id"], "text": "Mira waits."}],
    )
    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        with caplog.at_level(logging.DEBUG, logger="nexus.lore.turn_cycle"):
            asyncio.run(TurnCycleManager(lore).query_entity_states(turn))
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)

    assert statements
    assert not any(
        re.search(r"\b(?:FROM|JOIN)\s+(?:public\.)?(?:events|threats)\b", sql, re.I)
        for sql in statements
    )
    assert "Failed to query" not in caplog.text
    for key, expected_id in (
        ("characters", entity_corpus["character_id"]),
        ("locations", entity_corpus["place_id"]),
        ("factions", entity_corpus["faction_id"]),
    ):
        assert [row["id"] for row in turn.entity_data[key]["baseline"]] == [expected_id]
        assert [row["id"] for row in turn.entity_data[key]["featured"]] == [expected_id]
    assert set(turn.entity_data) == {
        "characters",
        "locations",
        "factions",
        "relationships",
    }
    assert turn.phase_states["entity_state"]["characters_featured"] == 1
    assert turn.phase_states["entity_state"]["locations_featured"] == 1
    assert turn.phase_states["entity_state"]["factions_featured"] == 1
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT to_jsonb(e) FROM world_events e")).all()
            == events_before
        )


def test_live_entity_divergence_retains_result_contract_and_alias_matching(
    entity_corpus: dict[str, Any],
) -> None:
    """A database alias, location, and faction reach the retained result type."""
    memnon = SimpleNamespace(
        db=entity_corpus["engine"],
        Session=entity_corpus["Session"],
    )
    manager = ContextMemoryManager(load_settings_as_dict(), memnon=memnon)
    result = manager._detect_divergence(
        "Ember leaves the Glass Atrium to meet the Night Guild."
    )
    assert isinstance(result, DivergenceResult)
    assert result.detected is True
    assert result.confidence == 1.0
    assert result.unmatched_entities == {
        f"character_{entity_corpus['character_id']}",
        f"place_{entity_corpus['place_id']}",
        f"faction_{entity_corpus['faction_id']}",
    }
    assert (
        result.gaps[f"character_{entity_corpus['character_id']}"]
        == "Character 'Mira Vale' mentioned"
    )
    assert result.to_dict()["unmatched_entities"] == sorted(result.unmatched_entities)
    assert result.to_dict()["references_seen"] == ["user_input"]
    assert not hasattr(manager, "divergence_detector")

    unknown = manager._detect_divergence("An unfamiliar stranger crosses the street.")
    assert unknown.to_dict() == {
        "detected": False,
        "confidence": 0.0,
        "gaps": {},
        "unmatched_entities": [],
        "references_seen": [],
    }
