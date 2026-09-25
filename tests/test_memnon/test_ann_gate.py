"""Real ANN gate checks on a read-only-source save_01 clone.

Uses narrative_chunks, chunk_metadata, world_events, retrograde_summaries and
2560d embeddings. All index and fixture writes are confined to qa640_766_*.
The recording cursor executes real SQL and EXPLAIN; it fabricates no results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PostgreSQLCursor
import pytest
from sqlalchemy import create_engine

from nexus.agents.memnon.utils.alias_search import hybrid_alias_search
from nexus.agents.memnon.utils.db_access import (
    _execute_retrograde_summary_vector_search,
    execute_multi_model_hybrid_search,
    execute_vector_search,
)
from nexus.agents.memnon.utils.embedding_tables import (
    build_candidate_ann_index,
    candidate_ann_index_name,
    drop_candidate_ann_index,
    ensure_character_experience_embedding_table,
)
from nexus.agents.orrery.knowledge_surfacing import _Candidate, _semantic_scores
from nexus.config import load_settings
from nexus.config.settings_models import ANNConfig
from nexus.database import connection_kwargs, database_url
from scripts.qa_shift.ann_gate import (
    TABLE,
    measure_clone,
    promotion_verdict,
    slot_clone,
)


@pytest.mark.parametrize(
    "field,value",
    [
        ("documents", 9999),
        ("exact_p95_ms", 50),
        ("approximate_p95_ms", 61),
        ("recall_at_10", 0.97),
    ],
)
def test_ann_gate_requires_every_measurement(field: str, value: float) -> None:
    config = load_settings().memnon.retrieval.ann
    evidence = {
        "documents": 10000,
        "exact_p95_ms": 60,
        "approximate_p95_ms": 10,
        "recall_at_10": 0.99,
    }
    assert promotion_verdict(evidence, config) == "PROMOTE"
    evidence[field] = value
    assert promotion_verdict(evidence, config) == "KEEP_EXACT"


@pytest.mark.parametrize(
    "field,value",
    [
        ("probe_queries", 19),
        ("ef_search", 1001),
        ("minimum_recall_at_10", 1.01),
        ("max_exact_p95_ms", float("nan")),
    ],
)
def test_ann_settings_validate_bounds(field: str, value: float) -> None:
    values = load_settings().memnon.retrieval.ann.model_dump()
    values[field] = value
    with pytest.raises(ValueError):
        ANNConfig.model_validate(values)


@pytest.fixture(scope="module")
def ann_clone() -> Any:
    with slot_clone(1) as name:
        yield name
    connection = psycopg2.connect(**connection_kwargs("postgres"))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            assert cursor.fetchone() is None
    finally:
        connection.close()


@pytest.mark.requires_postgres
def test_ann_operator_measures_and_verdict(ann_clone: str) -> None:
    config = load_settings().memnon.retrieval.ann.model_copy(
        update={"probe_queries": 20}
    )
    evidence = measure_clone(ann_clone, config)
    for metric in (
        "exact_p95_ms",
        "approximate_p95_ms",
        "index_build_ms",
        "index_bytes",
    ):
        assert evidence[metric] > 0
    assert 0 <= evidence["recall_at_10"] <= 1
    assert evidence["probe_queries"] == 20
    assert evidence["verdict"] == promotion_verdict(evidence, config)
    assert candidate_ann_index_name(TABLE) in json.dumps(evidence["approximate_plan"])
    assert '"Node Type": "Seq Scan"' in json.dumps(evidence["exact_plan"])
    assert len(evidence["queries"]) == 20
    with pytest.raises(ValueError, match="only accepts"):
        measure_clone("save_01", config)


@pytest.mark.requires_postgres
def test_ann_runtime_searches_and_plans(
    ann_clone: str, monkeypatch: Any, tmp_path: Path
) -> None:
    original_connect = psycopg2.connect
    connection = original_connect(**connection_kwargs(ann_clone))
    summary_table = "retrograde_summary_embeddings_2560d"
    try:
        with connection.cursor() as cursor:
            # Existing stored vectors only; seed a second real corpus in the clone.
            cursor.execute(
                f"SELECT chunk_id, model, embedding::text FROM {TABLE} ORDER BY chunk_id LIMIT 1"
            )
            chunk_id, model, vector = cursor.fetchone()
            cursor.execute(
                "SELECT word FROM narrative_chunks c, "
                "unnest(tsvector_to_array(to_tsvector('english', c.raw_text))) word "
                "WHERE c.id = %s AND word ~ '^[a-z]{3,}$' AND word <> 'gender' "
                "ORDER BY word LIMIT 1",
                (chunk_id,),
            )
            query_word = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO world_events (event_type, tick_chunk_id, source) "
                "SELECT type, %s, 'retrograde' FROM event_types ORDER BY type LIMIT 1 RETURNING id",
                (chunk_id,),
            )
            event_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO character_experiences (character_entity_id, "
                "anchor_chunk_id, world_event_ids, basis, seed_summary, salience, "
                "source_digest, world_layer) "
                "SELECT entity_id, %s, ARRAY[%s]::bigint[], 'participant', "
                "'ANN proof experience', 0.8, 'ann-proof', 'primary' "
                "FROM characters WHERE entity_id IS NOT NULL ORDER BY id LIMIT 1 "
                "RETURNING id, character_entity_id",
                (chunk_id, event_id),
            )
            experience_id, owner_id = cursor.fetchone()
            experience_table = ensure_character_experience_embedding_table(cursor, 2560)
            cursor.execute(
                f"INSERT INTO {experience_table} (experience_id, model, embedding) "
                "VALUES (%s, %s, %s::vector(2560))",
                (experience_id, model, vector),
            )
            cursor.execute(
                "INSERT INTO retrograde_summaries (world_event_id, recorded_at_chunk_id, chronology, summary_text) "
                "VALUES (%s, %s, 'deep_past', 'ANN proof memory') RETURNING id",
                (event_id, chunk_id),
            )
            summary_id = cursor.fetchone()[0]
            cursor.execute(
                f"INSERT INTO {summary_table} (summary_id, model, embedding) VALUES (%s,%s,%s::vector(2560))",
                (summary_id, model, vector),
            )
            for table in (TABLE, summary_table):
                drop_candidate_ann_index(cursor, table)
                build_candidate_ann_index(cursor, table)
                cursor.execute(f"ANALYZE {table}")
        connection.commit()
    finally:
        connection.close()

    captured: list[dict[str, Any]] = []
    statements: list[str] = []
    enabled = False

    class RecordingCursor(PostgreSQLCursor):
        def execute(self, query: Any, vars: Any = None) -> Any:
            result = super().execute(query, vars)
            statement = self.query.decode() if self.query else str(query)
            statements.append(statement)
            if "<=>" in statement and statement.lstrip().upper().startswith(
                ("SELECT", "WITH")
            ):
                with self.connection.cursor(
                    cursor_factory=PostgreSQLCursor
                ) as observer:
                    observer.execute("EXPLAIN (FORMAT JSON) " + statement)
                    natural_plan = observer.fetchone()[0]
                    if enabled:
                        # Prove index eligibility on small fixtures; preserve natural
                        # plans separately, since cost-based planning can choose exact.
                        observer.execute("SET LOCAL enable_seqscan = off")
                        observer.execute("SET LOCAL enable_sort = off")
                        observer.execute("SET LOCAL jit = off")
                        observer.execute("EXPLAIN (FORMAT JSON) " + statement)
                        plan = observer.fetchone()[0]
                        # Return rows from the controlled index execution too,
                        # so top-1 equivalence exercises HNSW at this scale.
                        result = super().execute(query, vars)
                        observer.execute("RESET enable_seqscan")
                        observer.execute("RESET enable_sort")
                        observer.execute("RESET jit")
                    else:
                        plan = natural_plan
                    captured.append(
                        {"sql": statement, "plan": plan, "natural_plan": natural_plan}
                    )
            return result

    def observed_connect(*args: Any, **kwargs: Any) -> Any:
        kwargs["cursor_factory"] = RecordingCursor
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(psycopg2, "connect", observed_connect)
    config_path = tmp_path / "nexus.toml"
    baseline_config = Path("nexus.toml").read_text()
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config_path))
    # Explicit DB URL bypasses gameplay slot resolution; all connections target clone.
    config_path.write_text(baseline_config)
    url = database_url(ann_clone)
    embedding = json.loads(vector)
    results_by_mode = []
    for mode in (False, True):
        enabled = mode
        config_path.write_text(
            baseline_config.replace(
                "enabled = false\n# Require substantial growth",
                f"enabled = {str(mode).lower()}\n# Require substantial growth",
                1,
            )
        )
        captured.clear()
        statements.clear()
        vector_results = execute_vector_search(url, embedding, model, top_k=10)
        assert vector_results
        hybrid_results = execute_multi_model_hybrid_search(
            url,
            "",
            {model: embedding},
            {model: 1.0},
            vector_weight=1.0,
            text_weight=0.0,
            top_k=10,
        )
        assert hybrid_results
        connection = psycopg2.connect(**connection_kwargs(ann_clone))
        try:
            connection.set_session(readonly=True)
            with connection.cursor() as cursor:
                summaries = _execute_retrograde_summary_vector_search(
                    cursor, 2560, vector, model, 10
                )
                assert summaries[0]["summary_id"] == summary_id
                experience_scores = _semantic_scores(
                    cursor,
                    candidates=[
                        _Candidate(
                            kind="experience",
                            candidate_id=experience_id,
                            character_entity_id=owner_id,
                            character_name="ANN proof",
                            summary="ANN proof experience",
                            source_chunk_id=chunk_id,
                            claim_id=None,
                            claim_scope=None,
                            source_tier="participant",
                            immediate_source_entity_id=None,
                            immediate_source_name=None,
                            acquired_at_world_time=None,
                            location_id=None,
                            severity=None,
                            salience=0.8,
                            freshly_revealed=False,
                            current_scene_acquisition=False,
                        )
                    ],
                    query_embeddings={model: embedding},
                    missing_score=0.0,
                )
                score, status = experience_scores[experience_id]
                assert status == "scored"
                assert score == pytest.approx(1.0, abs=1e-6)
        finally:
            connection.close()
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                aliases = hybrid_alias_search(
                    conn, query_word, embedding, model, 2560, alias_lookup={}
                )
                alias_matches = hybrid_alias_search(
                    conn,
                    query_word,
                    embedding,
                    model,
                    2560,
                    alias_lookup={query_word: [query_word]},
                )
                assert aliases
                assert alias_matches
                assert aliases[0]["id"] == alias_matches[0]["id"] == chunk_id
        finally:
            engine.dispose()
        assert (
            len(captured) == 8
        )  # Two corpora per public search + summary + experience + two aliases.
        for item in captured:
            plan = json.dumps(item["plan"])
            table = summary_table if "rse.embedding" in item["sql"] else TABLE
            if mode:
                assert "halfvec(2560)" in item["sql"]
                # Experience scoring evaluates supplied IDs, not nearest neighbors.
                if "source.experience_id" not in item["sql"]:
                    assert candidate_ann_index_name(table) in plan
            else:
                assert "halfvec(2560)" not in item["sql"]
                if "source.experience_id" not in item["sql"]:
                    assert '"Node Type": "Seq Scan"' in plan
                else:
                    # ID-bound scoring may use its primary-key B-tree in either mode.
                    assert "hnsw" not in plan
        assert not any("CREATE INDEX" in statement.upper() for statement in statements)
        assert not any("enable_seqscan" in statement for statement in statements)
        assert any("SET LOCAL hnsw.ef_search" in s for s in statements) == mode
        results_by_mode.append(
            (
                vector_results[0]["id"],
                hybrid_results[0]["id"],
                summaries[0]["id"],
                aliases[0]["id"],
                alias_matches[0]["id"],
            )
        )
    assert results_by_mode[0] == results_by_mode[1]
