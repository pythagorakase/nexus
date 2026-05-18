"""Tests for the retrieval query bake-off harness."""

from scripts.retrieval_query_bakeoff import (
    bootstrap_ci,
    build_query_sets,
    dedupe_queries,
    resolve_api_model_reference,
    score_strategy_result,
)


def _context() -> dict:
    return {
        "slot": 5,
        "chunk_id": 50,
        "target_chunk_id": 51,
        "raw_text": "A long scene near the Mercy Flue ash boilers.",
        "choice_text": "Push toward the ash boilers.",
        "authorial_directives": [
            "Retrieve Mercy Flue ash-boiler layout.",
            "Retrieve Orrel laundry route.",
        ],
        "characters": ["Mara Vey", "Nerin", "Orrel"],
        "places": ["Mercy Flue", "Lantern Court"],
        "factions": ["Crown Inspectorate"],
    }


def test_dedupe_queries_preserves_order_and_limit() -> None:
    """Bake-off query sets should stay deterministic."""

    queries = dedupe_queries(
        [
            "  Mercy Flue  ",
            "",
            None,
            "mercy flue",
            "Orrel laundry route",
            "Crown inspectors",
        ],
        limit=2,
    )

    assert queries == ["Mercy Flue", "Orrel laundry route"]


def test_build_query_sets_includes_raw_skald_and_local_llm() -> None:
    """The harness should compare the three requested strategies."""

    query_sets = build_query_sets(
        _context(),
        local_llm_queries=[
            "Mercy Flue ash boilers past incidents",
            "Orrel laundry route inspector records",
        ],
    )

    assert [query_set.name for query_set in query_sets] == [
        "raw_chunk",
        "skald_directives",
        "local_llm",
    ]
    assert query_sets[0].queries == ["A long scene near the Mercy Flue ash boilers."]
    assert query_sets[1].queries == [
        "Retrieve Mercy Flue ash-boiler layout.",
        "Retrieve Orrel laundry route.",
    ]
    assert query_sets[2].queries == [
        "Mercy Flue ash boilers past incidents",
        "Orrel laundry route inspector records",
    ]


def test_build_query_sets_can_truncate_raw_chunk() -> None:
    """Long raw chunk queries can be capped for experiments."""

    query_sets = build_query_sets(_context(), raw_chars=12)

    assert query_sets[0].queries == ["A long scene"]


def test_score_strategy_result_uses_oracle_and_entity_grades() -> None:
    """Automatic judges should reward overlaps with both evidence pools."""

    result = {
        "top_results": [
            {"id": 10},
            {"id": 20},
            {"id": 30},
        ]
    }

    scores = score_strategy_result(
        result,
        oracle_grades={20: 3.0, 40: 2.0},
        entity_grades={10: 1.0, 30: 0.5, 50: 1.0},
        top_k=3,
    )

    assert scores["oracle_recall_at_k"] == 0.5
    assert scores["oracle_mrr"] == 0.5
    assert scores["entity_precision_at_k"] == 2 / 3
    assert scores["oracle_ndcg_at_k"] > 0
    assert scores["entity_ndcg_at_k"] > 0


def test_bootstrap_ci_reports_degenerate_singletons() -> None:
    """A one-sample interval should be explicit instead of pretending certainty."""

    interval = bootstrap_ci([0.42])

    assert interval == {"mean": 0.42, "ci_low": 0.42, "ci_high": 0.42, "n": 1}


def test_resolve_api_model_reference_uses_registry() -> None:
    """Diagnostic defaults should avoid hardcoded concrete model IDs."""

    resolved = resolve_api_model_reference("@openai.default")

    assert resolved
    assert not resolved.startswith("@")
