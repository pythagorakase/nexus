"""Database storage layer for IR evaluation V2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import psycopg2
import psycopg2.extras

from ir_eval.models.schemas import EvalQuery, EvalRunConfig, QueryExecutionResult


class EvaluationStore:
    """Persist and retrieve evaluation runs/results from PostgreSQL."""

    def __init__(self, db_url: str):
        """Initialize the store with a PostgreSQL DSN/URL."""
        self.db_url = db_url

    def _connect(self) -> psycopg2.extensions.connection:
        """Create a new PostgreSQL connection."""
        return psycopg2.connect(self.db_url)

    def create_run(self, config: EvalRunConfig) -> int:
        """Insert a pending run and return its ID."""
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ir_eval.eval_runs (name, description, config)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (
                        config.name,
                        config.description,
                        psycopg2.extras.Json(config.model_dump(mode="json")),
                    ),
                )
                run_id = cursor.fetchone()[0]
            conn.commit()

        return int(run_id)

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent runs ordered by creation time."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT id, name, status, created_at, started_at, completed_at, error_message
                    FROM ir_eval.eval_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def get_run_config(self, run_id: int) -> EvalRunConfig:
        """Load and validate a run configuration."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT config FROM ir_eval.eval_runs WHERE id = %s",
                    (run_id,),
                )
                row = cursor.fetchone()

        if not row:
            raise ValueError(f"Run {run_id} does not exist")

        return EvalRunConfig.model_validate(row["config"])

    def set_run_status(
        self,
        run_id: int,
        status: str,
        *,
        error_message: Optional[str] = None,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        """Update run status and optional timestamps."""
        updates = ["status = %s", "error_message = %s"]
        params: List[Any] = [status, error_message]

        if started:
            updates.append("started_at = NOW()")
        if completed:
            updates.append("completed_at = NOW()")

        params.append(run_id)

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE ir_eval.eval_runs SET {', '.join(updates)} WHERE id = %s",
                    tuple(params),
                )
            conn.commit()

    def get_queries(
        self,
        query_ids: Optional[List[int]] = None,
        query_categories: Optional[List[str]] = None,
    ) -> List[EvalQuery]:
        """Fetch evaluation queries from `ir_eval.queries`."""
        where_clauses: List[str] = []
        params: List[Any] = []

        if query_ids:
            where_clauses.append("id = ANY(%s)")
            params.append(query_ids)

        if query_categories:
            where_clauses.append("category = ANY(%s)")
            params.append(query_categories)

        sql = "SELECT id, text, COALESCE(category, 'unknown') AS category, COALESCE(name, '') AS name FROM ir_eval.queries"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY id ASC"

        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()

        queries = [EvalQuery.model_validate(dict(row)) for row in rows]
        if not queries:
            raise ValueError(
                "No queries found in ir_eval.queries for the selected filters"
            )

        return queries

    def seed_queries_from_json(self, json_path: str) -> int:
        """Load golden queries from JSON and upsert into `ir_eval.queries`."""
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Missing golden queries file: {json_path}")

        data = json.loads(path.read_text())
        inserted = 0

        with self._connect() as conn:
            with conn.cursor() as cursor:
                for category, payload in data.items():
                    if category == "settings" or not isinstance(payload, dict):
                        continue

                    for name, query_payload in payload.items():
                        if (
                            not isinstance(query_payload, dict)
                            or "query" not in query_payload
                        ):
                            continue

                        cursor.execute(
                            """
                            INSERT INTO ir_eval.queries (text, category, name)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (text)
                            DO UPDATE SET category = EXCLUDED.category, name = EXCLUDED.name
                            """,
                            (query_payload["query"], category, name),
                        )
                        inserted += 1

            conn.commit()

        return inserted

    def insert_query_results(
        self, run_id: int, query_result: QueryExecutionResult
    ) -> None:
        """Persist scored retrieval results for one query."""
        if not query_result.results:
            return

        rows = []
        for result in query_result.results:
            rows.append(
                (
                    run_id,
                    query_result.query_id,
                    result.chunk_id,
                    result.rank,
                    result.final_score,
                    result.vector_score,
                    result.text_score,
                    result.reranker_score,
                    psycopg2.extras.Json(result.model_scores),
                    result.source,
                    psycopg2.extras.Json(result.metadata),
                )
            )

        with self._connect() as conn:
            with conn.cursor() as cursor:
                psycopg2.extras.execute_values(
                    cursor,
                    """
                    INSERT INTO ir_eval.eval_results (
                        run_id,
                        query_id,
                        chunk_id,
                        rank,
                        final_score,
                        vector_score,
                        text_score,
                        reranker_score,
                        model_scores,
                        source,
                        metadata
                    )
                    VALUES %s
                    ON CONFLICT (run_id, query_id, chunk_id)
                    DO UPDATE SET
                        rank = EXCLUDED.rank,
                        final_score = EXCLUDED.final_score,
                        vector_score = EXCLUDED.vector_score,
                        text_score = EXCLUDED.text_score,
                        reranker_score = EXCLUDED.reranker_score,
                        model_scores = EXCLUDED.model_scores,
                        source = EXCLUDED.source,
                        metadata = EXCLUDED.metadata
                    """,
                    rows,
                )
            conn.commit()

    def fetch_judgments(self, query_ids: Iterable[int]) -> Dict[int, Dict[int, int]]:
        """Return relevance judgments keyed by query and chunk ID."""
        query_id_list = list(query_ids)
        if not query_id_list:
            return {}

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT query_id, chunk_id, relevance
                    FROM ir_eval.judgments
                    WHERE query_id = ANY(%s)
                    """,
                    (query_id_list,),
                )
                rows = cursor.fetchall()

        by_query: Dict[int, Dict[int, int]] = {
            query_id: {} for query_id in query_id_list
        }
        for query_id, chunk_id, relevance in rows:
            by_query[int(query_id)][int(chunk_id)] = int(relevance)

        return by_query

    def store_metrics(
        self,
        run_id: int,
        per_query_metrics: Dict[int, Dict[str, Any]],
        query_categories: Dict[int, str],
        overall_metrics: Dict[str, float],
        category_metrics: Dict[str, Dict[str, float]],
    ) -> None:
        """Persist query-level and aggregate metrics for a run."""
        with self._connect() as conn:
            with conn.cursor() as cursor:
                for query_id, metrics in per_query_metrics.items():
                    cursor.execute(
                        """
                        INSERT INTO ir_eval.eval_query_metrics (
                            run_id,
                            query_id,
                            category,
                            p_at_5,
                            p_at_10,
                            mrr,
                            bpref,
                            ndcg_at_10,
                            judged_total,
                            unjudged_count
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_id, query_id)
                        DO UPDATE SET
                            category = EXCLUDED.category,
                            p_at_5 = EXCLUDED.p_at_5,
                            p_at_10 = EXCLUDED.p_at_10,
                            mrr = EXCLUDED.mrr,
                            bpref = EXCLUDED.bpref,
                            ndcg_at_10 = EXCLUDED.ndcg_at_10,
                            judged_total = EXCLUDED.judged_total,
                            unjudged_count = EXCLUDED.unjudged_count
                        """,
                        (
                            run_id,
                            query_id,
                            query_categories.get(query_id, "unknown"),
                            metrics.get("p_at_5", 0.0),
                            metrics.get("p_at_10", 0.0),
                            metrics.get("mrr", 0.0),
                            metrics.get("bpref", 0.0),
                            metrics.get("ndcg_at_10", 0.0),
                            metrics.get("judged_total", 0),
                            metrics.get("unjudged_count", 0),
                        ),
                    )

                cursor.execute(
                    """
                    INSERT INTO ir_eval.eval_run_metrics (
                        run_id,
                        overall_metrics,
                        category_metrics,
                        per_query_metrics
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (run_id)
                    DO UPDATE SET
                        overall_metrics = EXCLUDED.overall_metrics,
                        category_metrics = EXCLUDED.category_metrics,
                        per_query_metrics = EXCLUDED.per_query_metrics
                    """,
                    (
                        run_id,
                        psycopg2.extras.Json(overall_metrics),
                        psycopg2.extras.Json(category_metrics),
                        psycopg2.extras.Json(per_query_metrics),
                    ),
                )

            conn.commit()

    def get_query_metrics(self, run_id: int) -> Dict[int, Dict[str, Any]]:
        """Load per-query metrics for a run."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT query_id, category, p_at_5, p_at_10, mrr, bpref, ndcg_at_10
                    FROM ir_eval.eval_query_metrics
                    WHERE run_id = %s
                    ORDER BY query_id
                    """,
                    (run_id,),
                )
                rows = cursor.fetchall()

        metrics: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            metrics[int(row["query_id"])] = {
                "category": row["category"],
                "p_at_5": float(row["p_at_5"] or 0.0),
                "p_at_10": float(row["p_at_10"] or 0.0),
                "mrr": float(row["mrr"] or 0.0),
                "bpref": float(row["bpref"] or 0.0),
                "ndcg_at_10": float(row["ndcg_at_10"] or 0.0),
            }

        return metrics

    def save_comparison(
        self, run_a_id: int, run_b_id: int, comparison: Dict[str, Any]
    ) -> None:
        """Persist run comparison output."""
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ir_eval.eval_comparisons (run_a_id, run_b_id, comparison)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (run_a_id, run_b_id)
                    DO UPDATE SET comparison = EXCLUDED.comparison
                    """,
                    (run_a_id, run_b_id, psycopg2.extras.Json(comparison)),
                )
            conn.commit()
