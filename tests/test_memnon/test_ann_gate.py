"""Real ANN gate checks on a read-only-source save_01 clone.

Uses narrative_chunks, chunk_metadata, and 2560d embeddings. All index and
fixture writes are confined to qa640_766_*. SQL and EXPLAIN run on PostgreSQL;
no database results are fabricated.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg2
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from nexus.agents.memnon.utils.alias_search import hybrid_alias_search
from nexus.agents.memnon.utils.embedding_tables import (
    build_candidate_ann_index,
    candidate_ann_index_name,
    drop_candidate_ann_index,
)
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
        ("natural_uses_candidate_index", False),
        ("documents", 9999),
        ("exact_p95_ms", 50),
        ("approximate_p95_ms", 61),
        ("recall_at_10", 0.97),
    ],
)
def test_ann_gate_requires_every_measurement(field: str, value: float) -> None:
    config = load_settings().memnon.retrieval.ann
    evidence = {
        "natural_uses_candidate_index": True,
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
        ("enabled", True),
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
        "controlled_approximate_p95_ms",
        "index_build_ms",
        "index_bytes",
    ):
        assert evidence[metric] > 0
    assert 0 <= evidence["recall_at_10"] <= 1
    assert evidence["probe_queries"] == 20
    assert evidence["verdict"] == promotion_verdict(evidence, config)
    assert evidence["verdict"] == "KEEP_EXACT"
    assert evidence["reason"] == "planner_prefers_sequential_scan"
    assert not evidence["natural_uses_candidate_index"]
    assert 0 <= evidence["controlled_recall_at_10"] <= 1
    assert evidence["natural_session_settings"] == {"hnsw.ef_search": config.ef_search}
    for plan in evidence["natural_approximate_plans"]:
        assert '"Node Type": "Seq Scan"' in json.dumps(plan)
    for plan in evidence["controlled_approximate_plans"]:
        assert candidate_ann_index_name(TABLE) in json.dumps(plan)
    # Even permissive thresholds cannot promote test-only index performance.
    permissive = config.model_copy(
        update={"min_documents": 10, "max_exact_p95_ms": 0.0001}
    )
    assert promotion_verdict(evidence, permissive) == "KEEP_EXACT"
    assert '"Node Type": "Seq Scan"' in json.dumps(evidence["exact_plan"])
    assert len(evidence["queries"]) == 20
    with pytest.raises(ValueError, match="only accepts"):
        measure_clone("save_01", config)


@pytest.mark.requires_postgres
def test_ann_candidate_index_build_drop(ann_clone: str) -> None:
    connection = psycopg2.connect(**connection_kwargs(ann_clone))
    try:
        with connection.cursor() as cursor:
            drop_candidate_ann_index(cursor, TABLE)
            name = build_candidate_ann_index(cursor, TABLE)
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE indexname = %s", (name,)
            )
            definition = cursor.fetchone()[0]
            assert "USING hnsw" in definition
            assert "halfvec(2560)" in definition
            drop_candidate_ann_index(cursor, TABLE)
            cursor.execute("SELECT to_regclass(%s)", (name,))
            assert cursor.fetchone()[0] is None
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.requires_postgres
def test_ann_alias_candidates_and_database_errors(ann_clone: str) -> None:
    engine = create_engine(database_url(ann_clone))
    try:
        with engine.connect() as conn:
            chunk_id, model, vector = conn.execute(
                text(
                    f"SELECT chunk_id, model, embedding::text FROM {TABLE} ORDER BY chunk_id LIMIT 1"
                )
            ).one()
            query_word = conn.execute(
                text(
                    "SELECT word FROM narrative_chunks c, "
                    "unnest(tsvector_to_array(to_tsvector('english', c.raw_text))) word "
                    "WHERE c.id = :id AND word ~ '^[a-z]{3,}$' AND word <> 'gender' "
                    "ORDER BY word LIMIT 1"
                ),
                {"id": chunk_id},
            ).scalar_one()
            for aliases in ({}, {query_word: [query_word]}):
                results = hybrid_alias_search(
                    conn,
                    query_word,
                    json.loads(vector),
                    model,
                    2560,
                    alias_lookup=aliases,
                )
                assert results
                assert results[0]["id"] == chunk_id
            # Transactional schema damage only on this disposable clone.
            conn.execute(
                text(
                    "ALTER TABLE chunk_metadata RENAME COLUMN time_delta TO broken_time_delta"
                )
            )
            with pytest.raises(ProgrammingError, match="m.time_delta does not exist"):
                hybrid_alias_search(
                    conn, query_word, json.loads(vector), model, 2560, alias_lookup={}
                )
            conn.rollback()
            # The direct-text branch must propagate database failures as well.
            conn.execute(
                text(
                    "ALTER TABLE narrative_chunks RENAME COLUMN raw_text TO broken_raw_text"
                )
            )
            with pytest.raises(ProgrammingError, match="c.raw_text does not exist"):
                hybrid_alias_search(
                    conn, "gender", json.loads(vector), model, 2560, alias_lookup={}
                )
            conn.rollback()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "path",
    [
        "nexus/agents/memnon/utils/alias_search.py",
        "nexus/agents/memnon/utils/db_access.py",
        "nexus/agents/orrery/knowledge_surfacing.py",
    ],
)
def test_ann_search_sql_matches_repaired_baseline(path: str) -> None:
    # Frozen SQL AST fingerprints from 2b9266b5, with only the approved alias
    # metadata projection repair. Preserve literal whitespace and interpolations.
    expected = json.loads(
        (Path(__file__).parent / "fixtures/ann_repaired_sql.json").read_text()
    )
    source = Path(path).read_text()
    tree = ast.parse(source)
    expressions = [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.JoinedStr, ast.Constant))
        and any(
            keyword in (ast.get_source_segment(source, node) or "")
            for keyword in ("SELECT ", "WITH text_search", "<=>")
        )
    ]
    assert (
        hashlib.sha256(json.dumps(sorted(expressions)).encode()).hexdigest()
        == expected[path]
    )
    source = Path(path).read_text()
    assert "halfvec" not in source
    assert "hnsw.ef_search" not in source
    assert "build_candidate_ann_index" not in source
