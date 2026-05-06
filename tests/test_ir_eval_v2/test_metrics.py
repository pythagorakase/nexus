"""Unit tests for IR evaluation V2 metrics."""

import pytest

from ir_eval.engine.metrics import MetricsCalculator
from ir_eval.models.schemas import QueryExecutionResult, RetrievedDocument


def make_result(
    query_id: int, category: str, chunk_ids: list[int]
) -> QueryExecutionResult:
    """Build a minimal QueryExecutionResult for test cases."""
    return QueryExecutionResult(
        query_id=query_id,
        query_text=f"query-{query_id}",
        query_category=category,
        elapsed_seconds=0.01,
        results=[
            RetrievedDocument(
                chunk_id=chunk_id, rank=index + 1, final_score=1.0 - index * 0.01
            )
            for index, chunk_id in enumerate(chunk_ids)
        ],
    )


def test_calculate_per_query_metrics() -> None:
    """Calculator returns deterministic per-query metrics from judgments."""
    calculator = MetricsCalculator()

    query_results = [
        make_result(1, "character", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
        make_result(2, "location", [11, 12, 13, 14, 15]),
    ]

    judgments = {
        1: {1: 3, 3: 2, 4: 0, 6: 1},
        2: {13: 3},
    }

    metrics = calculator.calculate_per_query(query_results, judgments)

    assert metrics[1]["p_at_5"] == 0.4
    assert metrics[1]["mrr"] == 1.0
    assert 0.0 <= metrics[1]["bpref"] <= 1.0
    assert 0.0 <= metrics[1]["ndcg_at_10"] <= 1.0

    assert metrics[2]["p_at_5"] == 0.2
    assert metrics[2]["mrr"] == 1.0 / 3.0


def test_aggregate_metrics_by_category() -> None:
    """Aggregator computes overall and category-level averages."""
    calculator = MetricsCalculator()

    per_query = {
        1: {
            "p_at_5": 0.4,
            "p_at_10": 0.3,
            "mrr": 1.0,
            "bpref": 0.8,
            "ndcg_at_10": 0.9,
            "judged_total": 3,
            "unjudged_count": 7,
        },
        2: {
            "p_at_5": 0.2,
            "p_at_10": 0.2,
            "mrr": 0.3333333333,
            "bpref": 0.5,
            "ndcg_at_10": 0.4,
            "judged_total": 1,
            "unjudged_count": 4,
        },
    }
    categories = {1: "character", 2: "location"}

    aggregate = calculator.aggregate_metrics(per_query, categories)

    assert aggregate["overall"]["p_at_5"] == pytest.approx(0.3)
    assert aggregate["overall"]["p_at_10"] == pytest.approx(0.25)
    assert aggregate["by_category"]["character"]["mrr"] == 1.0
    assert aggregate["by_category"]["location"]["p_at_5"] == 0.2
