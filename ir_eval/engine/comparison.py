"""Run-to-run metric comparison utilities for IR evaluation."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from ir_eval.engine.storage import EvaluationStore


class ComparisonEngine:
    """Compare run metrics with paired significance estimates."""

    METRICS = ["p_at_5", "p_at_10", "mrr", "bpref", "ndcg_at_10"]

    def __init__(self, store: EvaluationStore):
        """Create a comparison engine bound to one evaluation store."""
        self.store = store

    @staticmethod
    def _paired_arrays(
        metrics_a: Dict[int, Dict[str, Any]],
        metrics_b: Dict[int, Dict[str, Any]],
        metric_name: str,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Build paired metric arrays on the intersection of query IDs."""
        shared_query_ids = sorted(set(metrics_a.keys()).intersection(metrics_b.keys()))
        if not shared_query_ids:
            raise ValueError("Runs do not share any query IDs for comparison")

        array_a = np.array(
            [float(metrics_a[query_id][metric_name]) for query_id in shared_query_ids]
        )
        array_b = np.array(
            [float(metrics_b[query_id][metric_name]) for query_id in shared_query_ids]
        )
        return array_a, array_b

    @staticmethod
    def _paired_permutation_pvalue(
        scores_a: np.ndarray,
        scores_b: np.ndarray,
        iterations: int = 10000,
        seed: int = 42,
    ) -> float:
        """Estimate a paired permutation p-value for mean difference."""
        differences = scores_a - scores_b
        observed = abs(float(np.mean(differences)))

        if observed == 0.0:
            return 1.0

        rng = np.random.default_rng(seed)
        extreme = 0

        for _ in range(iterations):
            signs = rng.choice([-1.0, 1.0], size=differences.shape[0])
            permuted = differences * signs
            if abs(float(np.mean(permuted))) >= observed:
                extreme += 1

        # Add-one smoothing to avoid 0.0 p-values.
        return float((extreme + 1) / float(iterations + 1))

    @staticmethod
    def _bootstrap_ci(
        scores_a: np.ndarray,
        scores_b: np.ndarray,
        iterations: int = 2000,
        alpha: float = 0.95,
        seed: int = 42,
    ) -> Tuple[float, float]:
        """Bootstrap confidence interval for mean metric delta (A - B)."""
        if not (0.0 < alpha < 1.0):
            raise ValueError("alpha must be between 0 and 1")

        deltas = scores_a - scores_b
        rng = np.random.default_rng(seed)
        bootstrap_means = []

        for _ in range(iterations):
            sampled = rng.choice(deltas, size=deltas.shape[0], replace=True)
            bootstrap_means.append(float(np.mean(sampled)))

        lower_percentile = ((1.0 - alpha) / 2.0) * 100.0
        upper_percentile = (alpha + (1.0 - alpha) / 2.0) * 100.0

        return (
            float(np.percentile(bootstrap_means, lower_percentile)),
            float(np.percentile(bootstrap_means, upper_percentile)),
        )

    def compare_runs(self, run_a_id: int, run_b_id: int) -> Dict[str, Any]:
        """Compare two runs and persist comparison output."""
        metrics_a = self.store.get_query_metrics(run_a_id)
        metrics_b = self.store.get_query_metrics(run_b_id)

        if not metrics_a:
            raise ValueError(f"No query metrics found for run {run_a_id}")
        if not metrics_b:
            raise ValueError(f"No query metrics found for run {run_b_id}")

        metric_comparison: Dict[str, Dict[str, Any]] = {}

        for metric in self.METRICS:
            scores_a, scores_b = self._paired_arrays(metrics_a, metrics_b, metric)
            mean_a = float(np.mean(scores_a))
            mean_b = float(np.mean(scores_b))
            delta = mean_a - mean_b
            p_value = self._paired_permutation_pvalue(scores_a, scores_b)
            ci_low, ci_high = self._bootstrap_ci(scores_a, scores_b)

            metric_comparison[metric] = {
                "run_a_mean": mean_a,
                "run_b_mean": mean_b,
                "delta": delta,
                "paired_permutation_pvalue": p_value,
                "significant_at_05": p_value < 0.05,
                "bootstrap_ci_95": [ci_low, ci_high],
            }

        output = {
            "run_a_id": run_a_id,
            "run_b_id": run_b_id,
            "metrics": metric_comparison,
        }

        self.store.save_comparison(run_a_id, run_b_id, output)
        return output
