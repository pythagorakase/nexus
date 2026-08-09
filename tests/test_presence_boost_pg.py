"""Disposable-PostgreSQL proofs for presence-weighted MEMNON retrieval."""

from __future__ import annotations

import json
import os
from typing import Any, Iterator
import uuid

import psycopg2
from psycopg2 import sql
import pytest

from nexus.agents.memnon.utils.search import SearchManager
from scripts.measure_presence_boost import (
    load_measurement_corpus,
    measure_presence_boost,
)


pytestmark = pytest.mark.requires_postgres


class FixedEmbeddingManager:
    """Return one deterministic embedding while exercising the real scorer."""

    def get_available_models(self) -> list[str]:
        """Return the fixture model key."""

        return ["presence-fixture"]

    def generate_embedding(self, _query_text: str, _model_key: str) -> list[float]:
        """Return the fixture query vector."""

        return [1.0, 0.0, 0.0]


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _database_url(dbname: str) -> str:
    user = os.environ.get("PGUSER", "pythagor")
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    return f"postgresql://{user}@{host}:{port}/{dbname}"


def _insert_chunk(cursor: Any, raw_text: str, scene: int) -> int:
    cursor.execute(
        """
        INSERT INTO narrative_chunks (
            raw_text, storyteller_text, authorial_directives,
            state, finalized_at
        ) VALUES (%s, %s, '[]'::jsonb, 'finalized', now())
        RETURNING id
        """,
        (raw_text, raw_text),
    )
    chunk_id = int(cursor.fetchone()[0])
    cursor.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer,
            time_delta, generation_date
        ) VALUES (
            %s, 1, 1, %s, 'primary', interval '0 seconds', now()
        )
        """,
        (chunk_id, scene),
    )
    return chunk_id


@pytest.fixture()
def presence_database() -> Iterator[dict[str, Any]]:
    """Clone the template and seed equal narrative/summary search candidates."""

    dbname = f"qa683_presence_{uuid.uuid4().hex[:12]}"
    admin = None
    connection = None
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )

        connection = _connect(dbname)
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.retrograde_summaries')")
                if cursor.fetchone()[0] is None:
                    pytest.skip("NEXUS_template has not applied migration 078")
                cursor.execute(
                    """
                    INSERT INTO global_variables (id, new_story, base_timestamp)
                    VALUES (true, true, now())
                    ON CONFLICT (id) DO UPDATE
                    SET base_timestamp = EXCLUDED.base_timestamp
                    """
                )
                cursor.execute(
                    "INSERT INTO characters (name, summary) "
                    "VALUES (%s, %s) RETURNING id",
                    ("Zephyr Fixture", "Disposable presence character."),
                )
                character_id = int(cursor.fetchone()[0])
                query_text = "Who is the zephyr fixture witness"
                nonpresent_chunk_id = _insert_chunk(cursor, query_text, 1)
                present_chunk_id = _insert_chunk(cursor, query_text, 2)
                cursor.execute(
                    """
                    INSERT INTO chunk_character_references (
                        chunk_id, character_id, reference
                    ) VALUES (%s, %s, 'present')
                    """,
                    (present_chunk_id, character_id),
                )
                cursor.execute(
                    """
                    CREATE TABLE chunk_embeddings_0003d (
                        chunk_id bigint NOT NULL REFERENCES narrative_chunks(id),
                        model text NOT NULL,
                        embedding vector(3) NOT NULL,
                        PRIMARY KEY (chunk_id, model)
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO chunk_embeddings_0003d (
                        chunk_id, model, embedding
                    ) VALUES
                        (%s, 'presence-fixture', '[1,0,0]'),
                        (%s, 'presence-fixture', '[1,0,0]')
                    """,
                    (nonpresent_chunk_id, present_chunk_id),
                )
                cursor.execute("SELECT type FROM event_types ORDER BY type LIMIT 1")
                event_type = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, world_layer, source,
                        changed_fields, payload
                    ) VALUES (
                        %s, %s, 'primary', 'retrograde', '{}', %s::jsonb
                    ) RETURNING id
                    """,
                    (
                        event_type,
                        nonpresent_chunk_id,
                        json.dumps(
                            {
                                "retrograde_event_ref": "qa683_summary",
                                "summary": query_text,
                                "chronology": "deep_past",
                            }
                        ),
                    ),
                )
                world_event_id = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    INSERT INTO retrograde_summaries (
                        world_event_id, recorded_at_chunk_id, chronology,
                        summary_text, embedding_generated_at
                    ) VALUES (%s, %s, 'deep_past', %s, now())
                    RETURNING id
                    """,
                    (world_event_id, nonpresent_chunk_id, query_text),
                )
                summary_id = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    CREATE TABLE retrograde_summary_embeddings_0003d (
                        summary_id bigint NOT NULL
                            REFERENCES retrograde_summaries(id),
                        model text NOT NULL,
                        embedding vector(3) NOT NULL,
                        PRIMARY KEY (summary_id, model)
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO retrograde_summary_embeddings_0003d (
                        summary_id, model, embedding
                    ) VALUES (%s, 'presence-fixture', '[1,0,0]')
                    """,
                    (summary_id,),
                )

        yield {
            "dbname": dbname,
            "db_url": _database_url(dbname),
            "query_text": query_text,
            "character_id": character_id,
            "nonpresent_chunk_id": nonpresent_chunk_id,
            "present_chunk_id": present_chunk_id,
            "summary_id": summary_id,
        }
    finally:
        if connection is not None:
            connection.close()
        if admin is not None:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cursor.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
            admin.close()


def _search_manager(db_url: str) -> SearchManager:
    hybrid_config = {
        "enabled": True,
        "vector_weight_default": 0.6,
        "text_weight_default": 0.4,
        "weights_by_query_type": {"character": {"vector": 0.6, "text": 0.4}},
        "use_query_type_weights": True,
        "temporal_boost_factor": 0.0,
        "temporal_boost_factors": {},
        "use_query_type_temporal_factors": False,
        "presence_boost_enabled": False,
        "presence_boost_factor": 0.15,
        "presence_boost_factors": {"character": 0.25},
    }
    return SearchManager(
        db_url=db_url,
        embedding_manager=FixedEmbeddingManager(),
        idf_dictionary=None,
        settings={"retrieval": {"hybrid_search": hybrid_config}},
        retrieval_settings={
            "default_top_k": 10,
            "model_weights": {"presence-fixture": 1.0},
        },
    )


def _result_by_id(results: list[dict[str, Any]], result_id: str) -> dict[str, Any]:
    return next(result for result in results if result["id"] == result_id)


def test_presence_boost_entry_point_and_summary_scope(
    presence_database: dict[str, Any],
) -> None:
    """Off is identical; on lifts only the co-present narrative candidate."""

    fixture = presence_database
    manager = _search_manager(fixture["db_url"])
    legacy = manager.perform_hybrid_search(
        query_text=fixture["query_text"],
        top_k=10,
    )
    disabled = manager.perform_hybrid_search(
        query_text=fixture["query_text"],
        top_k=10,
        present_character_ids=[fixture["character_id"]],
        presence_boost_enabled=False,
    )
    boosted = manager.perform_hybrid_search(
        query_text=fixture["query_text"],
        top_k=10,
        present_character_ids=[fixture["character_id"]],
        presence_boost_enabled=True,
    )

    assert disabled == legacy
    present_id = str(fixture["present_chunk_id"])
    nonpresent_id = str(fixture["nonpresent_chunk_id"])
    summary_id = f"retrograde_summary:{fixture['summary_id']}"
    assert boosted[0]["id"] == present_id
    assert _result_by_id(boosted, present_id)["score"] == pytest.approx(
        _result_by_id(disabled, present_id)["score"] + 0.25
    )
    assert _result_by_id(boosted, nonpresent_id) == _result_by_id(
        disabled, nonpresent_id
    )
    assert _result_by_id(boosted, summary_id) == _result_by_id(disabled, summary_id)
    assert "presence_boost" not in _result_by_id(boosted, summary_id)


def test_measurement_harness_uses_ephemeral_corpus(
    presence_database: dict[str, Any],
) -> None:
    """The harness loads real rosters and reports paired entry-point results."""

    fixture = presence_database
    with _connect(fixture["dbname"]) as connection:
        chunks, character_names = load_measurement_corpus(connection)
    source_chunks = [
        chunk for chunk in chunks if chunk.chunk_id == fixture["present_chunk_id"]
    ]
    report = measure_presence_boost(
        source_chunks,
        character_names,
        _search_manager(fixture["db_url"]),
        top_k=3,
    )

    assert report["accepted_chunks"] == 1
    assert report["per_query_type"]["character"]["queries"] == 1
    assert report["counterfactual_coverage"]["entity_opportunities"] == 1
    assert report["counterfactual_coverage"]["introduced_gap_entities"] == []
