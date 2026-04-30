"""Run execution engine for embedding-model evaluation."""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Tuple

from nexus.config import load_settings_as_dict
from nexus.agents.memnon.utils.cross_encoder import rerank_results
from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager
from nexus.agents.memnon.utils.idf_dictionary import IDFDictionary
from nexus.agents.memnon.utils.query_analysis import QueryAnalyzer
from nexus.agents.memnon.utils.search import SearchManager

from ir_eval.engine.metrics import MetricsCalculator
from ir_eval.engine.storage import EvaluationStore
from ir_eval.models.schemas import (
    EvalRunConfig,
    QueryExecutionResult,
    RetrievedDocument,
    RunExecutionSummary,
)


class RunExecutor:
    """Execute eval runs with explicit, immutable model selection."""

    def __init__(
        self,
        store: EvaluationStore,
        *,
        settings_dict: Dict[str, Any] | None = None,
        db_url: str | None = None,
    ):
        """Create a run executor with repository and base settings."""
        self.store = store
        self.settings_dict = settings_dict or load_settings_as_dict()
        self.base_memnon_settings = copy.deepcopy(
            self.settings_dict["Agent Settings"]["MEMNON"]
        )

        configured_db_url = self.base_memnon_settings.get("database", {}).get("url")
        self.db_url = db_url or configured_db_url
        if not self.db_url:
            raise ValueError("MEMNON database.url is not configured")

    @staticmethod
    def _normalize_model_weights(config: EvalRunConfig) -> Dict[str, float]:
        """Normalize selected model weights so they sum to 1.0."""
        total = sum(model.weight for model in config.embedding_models)
        if total <= 0:
            raise ValueError("embedding_models must include weight > 0")

        return {
            model.model: (model.weight / total) for model in config.embedding_models
        }

    def _build_run_memnon_settings(
        self,
        config: EvalRunConfig,
        base_settings: Dict[str, Any] | None = None,
    ) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """Build a per-run MEMNON config copy from the immutable run config.

        When *base_settings* is provided (e.g. from a stored snapshot), it is
        used instead of the executor's current ``base_memnon_settings``.
        """
        run_settings = copy.deepcopy(base_settings or self.base_memnon_settings)
        run_settings.setdefault("database", {})["url"] = self.db_url

        selected_model_weights = self._normalize_model_weights(config)
        model_configs = run_settings.get("models", {})

        for model_name in selected_model_weights:
            if model_name not in model_configs:
                raise ValueError(
                    f"Run references model '{model_name}', but it is not configured in MEMNON settings"
                )

        # Disable all models first, then activate selected ones with normalized weights.
        for model_name, model_config in model_configs.items():
            model_config["is_active"] = model_name in selected_model_weights
            model_config["weight"] = selected_model_weights.get(model_name, 0.0)

        retrieval = run_settings.setdefault("retrieval", {})
        hybrid = retrieval.setdefault("hybrid_search", {})
        hybrid["enabled"] = config.hybrid_search
        hybrid["vector_weight_default"] = config.vector_weight
        hybrid["text_weight_default"] = config.text_weight
        hybrid["use_query_type_weights"] = False

        cross_encoder = retrieval.setdefault("cross_encoder_reranking", {})
        cross_encoder["enabled"] = config.cross_encoder_enabled

        query_settings = run_settings.setdefault("query", {})
        query_settings["default_limit"] = config.top_k

        return run_settings, selected_model_weights

    @staticmethod
    def _build_retrieval_settings(memnon_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Build SearchManager retrieval settings from MEMNON settings."""
        query_config = memnon_settings.get("query", {})
        retrieval_config = memnon_settings.get("retrieval", {})

        model_weights: Dict[str, float] = {}
        for model_name, model_config in memnon_settings.get("models", {}).items():
            if model_config.get("is_active", False):
                model_weights[model_name] = float(model_config.get("weight", 0.0))

        return {
            "default_top_k": int(query_config.get("default_limit", 10)),
            "max_query_results": int(retrieval_config.get("max_results", 50)),
            "relevance_threshold": float(
                retrieval_config.get("relevance_threshold", 0.65)
            ),
            "entity_boost_factor": float(
                retrieval_config.get("entity_boost_factor", 1.2)
            ),
            "recency_boost_factor": float(
                retrieval_config.get("recency_boost_factor", 1.1)
            ),
            "db_vector_balance": float(retrieval_config.get("db_vector_balance", 0.6)),
            "model_weights": model_weights,
            "highlight_matches": bool(query_config.get("highlight_matches", True)),
        }

    def _initialize_search_stack(
        self,
        memnon_settings: Dict[str, Any],
        selected_model_weights: Dict[str, float],
    ) -> Tuple[SearchManager, QueryAnalyzer]:
        """Initialize EmbeddingManager/SearchManager for the selected models."""
        embedding_manager = EmbeddingManager(settings=memnon_settings)
        available_models = set(embedding_manager.get_available_models())
        required_models = set(selected_model_weights.keys())
        missing_models = required_models - available_models

        if missing_models:
            raise RuntimeError(
                "Selected models failed to load: " + ", ".join(sorted(missing_models))
            )

        idf_dictionary = IDFDictionary(self.db_url)
        idf_dictionary.build_dictionary()

        retrieval_settings = self._build_retrieval_settings(memnon_settings)
        search_manager = SearchManager(
            db_url=self.db_url,
            embedding_manager=embedding_manager,
            idf_dictionary=idf_dictionary,
            settings=memnon_settings,
            retrieval_settings=retrieval_settings,
        )
        query_analyzer = QueryAnalyzer(settings=memnon_settings)

        return search_manager, query_analyzer

    @staticmethod
    def _to_query_execution_result(
        query_id: int,
        query_text: str,
        query_category: str,
        raw_results: List[Dict[str, Any]],
        elapsed_seconds: float,
    ) -> QueryExecutionResult:
        """Convert raw search results to typed query execution results."""
        typed_results: List[RetrievedDocument] = []

        for index, result in enumerate(raw_results, start=1):
            chunk_id = int(result["id"])
            model_scores_raw = result.get("model_scores", {}) or {}
            model_scores = {
                key: float(value) for key, value in model_scores_raw.items()
            }

            typed_results.append(
                RetrievedDocument(
                    chunk_id=chunk_id,
                    rank=index,
                    final_score=float(result.get("score", 0.0)),
                    vector_score=float(result.get("vector_score", 0.0)),
                    text_score=float(result.get("text_score", 0.0)),
                    reranker_score=(
                        float(result["reranker_score"])
                        if result.get("reranker_score") is not None
                        else None
                    ),
                    model_scores=model_scores,
                    source=str(result.get("source", "unknown")),
                    metadata=result.get("metadata", {}) or {},
                )
            )

        return QueryExecutionResult(
            query_id=query_id,
            query_text=query_text,
            query_category=query_category,
            elapsed_seconds=elapsed_seconds,
            results=typed_results,
        )

    def create_run(self, config: EvalRunConfig) -> int:
        """Persist a run configuration and return its run ID."""
        if not config.settings_snapshot:
            config = config.model_copy(
                update={"settings_snapshot": copy.deepcopy(self.base_memnon_settings)}
            )
        return self.store.create_run(config)

    def execute_run(self, run_id: int) -> RunExecutionSummary:
        """Execute a persisted run and store query results + metrics."""
        run_config = self.store.get_run_config(run_id)
        snapshot = run_config.settings_snapshot or None
        run_settings, selected_model_weights = self._build_run_memnon_settings(
            run_config,
            base_settings=snapshot,
        )
        search_manager, query_analyzer = self._initialize_search_stack(
            run_settings,
            selected_model_weights,
        )

        queries = self.store.get_queries(
            query_ids=run_config.query_ids,
            query_categories=run_config.query_categories,
        )

        self.store.set_run_status(run_id, "running", started=True)

        started_at = time.time()
        query_results: List[QueryExecutionResult] = []

        cross_encoder_settings = run_settings.get("retrieval", {}).get(
            "cross_encoder_reranking", {}
        )

        try:
            for query in queries:
                query_start = time.time()

                if run_config.hybrid_search:
                    raw_results = search_manager.perform_hybrid_search(
                        query_text=query.text,
                        filters=None,
                        top_k=run_config.top_k,
                    )
                else:
                    raw_results = search_manager.query_vector_search(
                        query_text=query.text,
                        collections=["narrative_chunks"],
                        filters=None,
                        top_k=run_config.top_k,
                    )

                if run_config.cross_encoder_enabled and raw_results:
                    query_type = query_analyzer.analyze_query(query.text).get(
                        "type", "general"
                    )
                    alpha = float(cross_encoder_settings.get("blend_weight", 0.3))

                    if cross_encoder_settings.get("use_query_type_weights", False):
                        query_type_weights = cross_encoder_settings.get(
                            "weights_by_query_type", {}
                        )
                        if query_type in query_type_weights:
                            alpha = float(query_type_weights[query_type])

                    raw_results = rerank_results(
                        query=query.text,
                        results=raw_results,
                        top_k=run_config.top_k,
                        alpha=alpha,
                        batch_size=int(cross_encoder_settings.get("batch_size", 8)),
                        use_sliding_window=bool(
                            cross_encoder_settings.get("use_sliding_window", True)
                        ),
                        model_path=str(
                            cross_encoder_settings.get(
                                "model_path",
                                "naver-trecdl22-crossencoder-debertav3",
                            )
                        ),
                        use_8bit=bool(cross_encoder_settings.get("use_8bit", False)),
                    )

                elapsed_seconds = time.time() - query_start
                typed_query_result = self._to_query_execution_result(
                    query_id=query.id,
                    query_text=query.text,
                    query_category=query.category,
                    raw_results=raw_results,
                    elapsed_seconds=elapsed_seconds,
                )

                query_results.append(typed_query_result)
                self.store.insert_query_results(run_id, typed_query_result)

            metrics_calculator = MetricsCalculator()
            judgments_by_query = self.store.fetch_judgments(
                [query.id for query in queries]
            )
            per_query_metrics = metrics_calculator.calculate_per_query(
                query_results, judgments_by_query
            )
            query_categories = {query.id: query.category for query in queries}
            aggregate = metrics_calculator.aggregate_metrics(
                per_query_metrics, query_categories
            )

            self.store.store_metrics(
                run_id=run_id,
                per_query_metrics=per_query_metrics,
                query_categories=query_categories,
                overall_metrics=aggregate["overall"],
                category_metrics=aggregate["by_category"],
            )

            self.store.set_run_status(run_id, "completed", completed=True)

            return RunExecutionSummary(
                run_id=run_id,
                status="completed",
                query_count=len(query_results),
                total_elapsed_seconds=time.time() - started_at,
                overall_metrics=aggregate["overall"],
                category_metrics=aggregate["by_category"],
            )

        except Exception as exc:
            self.store.set_run_status(
                run_id,
                "failed",
                error_message=str(exc),
                completed=True,
            )
            raise
