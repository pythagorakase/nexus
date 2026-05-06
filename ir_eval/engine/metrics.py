"""IR metrics calculations for evaluation runs."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List

from ir_eval.models.schemas import QueryExecutionResult


class MetricsCalculator:
    """Calculate standard IR metrics for evaluation runs."""

    @staticmethod
    def _precision_at_k(
        ranked_chunk_ids: List[int],
        judgments: Dict[int, int],
        k: int,
        relevance_threshold: int = 1,
    ) -> float:
        """Compute precision at rank ``k``."""
        if k <= 0:
            raise ValueError("k must be greater than 0")

        top_k = ranked_chunk_ids[:k]
        relevant = 0
        for chunk_id in top_k:
            if judgments.get(chunk_id, 0) >= relevance_threshold:
                relevant += 1

        return relevant / float(k)

    @staticmethod
    def _mrr(
        ranked_chunk_ids: List[int],
        judgments: Dict[int, int],
        relevance_threshold: int = 1,
    ) -> float:
        """Compute reciprocal rank of the first relevant result."""
        for index, chunk_id in enumerate(ranked_chunk_ids, start=1):
            if judgments.get(chunk_id, 0) >= relevance_threshold:
                return 1.0 / float(index)
        return 0.0

    @staticmethod
    def _bpref(
        ranked_chunk_ids: List[int],
        judgments: Dict[int, int],
        relevance_threshold: int = 1,
    ) -> float:
        """Compute BPREF using judged relevant/non-relevant sets only."""
        relevant_docs = {
            chunk_id
            for chunk_id, rel in judgments.items()
            if rel >= relevance_threshold
        }
        non_relevant_docs = {
            chunk_id for chunk_id, rel in judgments.items() if rel < relevance_threshold
        }

        relevant_total = len(relevant_docs)
        if relevant_total == 0:
            return 0.0

        bpref_total = 0.0
        non_relevant_seen = 0

        for chunk_id in ranked_chunk_ids:
            if chunk_id not in judgments:
                continue
            if chunk_id in non_relevant_docs:
                non_relevant_seen += 1
                continue
            if chunk_id in relevant_docs:
                penalty = min(non_relevant_seen, relevant_total) / float(relevant_total)
                bpref_total += 1.0 - penalty

        return bpref_total / float(relevant_total)

    @staticmethod
    def _ndcg_at_k(
        ranked_chunk_ids: List[int], judgments: Dict[int, int], k: int = 10
    ) -> float:
        """Compute NDCG@k using 0-3 relevance labels."""
        if k <= 0:
            raise ValueError("k must be greater than 0")

        def dcg(scores: Iterable[int]) -> float:
            total = 0.0
            for index, score in enumerate(scores, start=1):
                total += float(score) / math.log2(index + 1)
            return total

        ranked_scores = [
            judgments.get(chunk_id, 0) for chunk_id in ranked_chunk_ids[:k]
        ]
        ideal_scores = sorted(judgments.values(), reverse=True)[:k]

        ideal_dcg = dcg(ideal_scores)
        if ideal_dcg <= 0:
            return 0.0

        return dcg(ranked_scores) / ideal_dcg

    def calculate_per_query(
        self,
        query_results: List[QueryExecutionResult],
        judgments_by_query: Dict[int, Dict[int, int]],
    ) -> Dict[int, Dict[str, Any]]:
        """Calculate metrics for each query result set."""
        metrics: Dict[int, Dict[str, Any]] = {}

        for query_result in query_results:
            ranked_chunk_ids = [result.chunk_id for result in query_result.results]
            judgments = judgments_by_query.get(query_result.query_id, {})

            judged_chunk_ids = set(judgments.keys())
            returned_chunk_ids = set(ranked_chunk_ids)
            judged_total = len(judged_chunk_ids.intersection(returned_chunk_ids))
            unjudged_count = len(returned_chunk_ids) - judged_total

            metrics[query_result.query_id] = {
                "p_at_5": self._precision_at_k(ranked_chunk_ids, judgments, 5),
                "p_at_10": self._precision_at_k(ranked_chunk_ids, judgments, 10),
                "mrr": self._mrr(ranked_chunk_ids, judgments),
                "bpref": self._bpref(ranked_chunk_ids, judgments),
                "ndcg_at_10": self._ndcg_at_k(ranked_chunk_ids, judgments, 10),
                "judged_total": judged_total,
                "unjudged_count": unjudged_count,
            }

        return metrics

    def aggregate_metrics(
        self,
        per_query_metrics: Dict[int, Dict[str, Any]],
        query_categories: Dict[int, str],
    ) -> Dict[str, Dict[str, Any]]:
        """Aggregate query metrics overall and by category."""
        metric_keys = ["p_at_5", "p_at_10", "mrr", "bpref", "ndcg_at_10"]

        overall: Dict[str, float] = {key: 0.0 for key in metric_keys}
        overall["judged_total"] = 0.0
        overall["unjudged_count"] = 0.0

        by_category_sums: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {
                **{key: 0.0 for key in metric_keys},
                "judged_total": 0.0,
                "unjudged_count": 0.0,
            }
        )
        by_category_counts: Dict[str, int] = defaultdict(int)

        query_count = len(per_query_metrics)
        if query_count == 0:
            return {"overall": overall, "by_category": {}}

        for query_id, metrics in per_query_metrics.items():
            category = query_categories.get(query_id, "unknown")
            by_category_counts[category] += 1

            for key in metric_keys:
                value = float(metrics.get(key, 0.0))
                overall[key] += value
                by_category_sums[category][key] += value

            judged_total = float(metrics.get("judged_total", 0.0))
            unjudged_count = float(metrics.get("unjudged_count", 0.0))
            overall["judged_total"] += judged_total
            overall["unjudged_count"] += unjudged_count
            by_category_sums[category]["judged_total"] += judged_total
            by_category_sums[category]["unjudged_count"] += unjudged_count

        for key in metric_keys:
            overall[key] = overall[key] / float(query_count)

        by_category: Dict[str, Dict[str, float]] = {}
        for category, sums in by_category_sums.items():
            category_count = by_category_counts[category]
            by_category[category] = {}
            for key in metric_keys:
                by_category[category][key] = sums[key] / float(category_count)
            by_category[category]["judged_total"] = sums["judged_total"]
            by_category[category]["unjudged_count"] = sums["unjudged_count"]

        return {"overall": overall, "by_category": by_category}
