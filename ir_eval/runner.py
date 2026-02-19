"""CLI entrypoint for the IR evaluation V2 system."""

from __future__ import annotations

import argparse
import json
from typing import List, Optional

from nexus.config import load_settings_as_dict

from ir_eval.engine import ComparisonEngine, EvaluationStore, RunExecutor
from ir_eval.models import EvalModelConfig, EvalRunConfig


def default_db_url() -> str:
    """Resolve default DB URL from MEMNON settings."""
    settings = load_settings_as_dict()
    db_url = settings["Agent Settings"]["MEMNON"]["database"]["url"]
    if not db_url:
        raise ValueError("MEMNON database.url is not configured")
    return db_url


def parse_csv_ints(value: Optional[str]) -> Optional[List[int]]:
    """Parse comma-separated integers."""
    if not value:
        return None
    values = [item.strip() for item in value.split(",") if item.strip()]
    return [int(item) for item in values]


def parse_csv_strings(value: Optional[str]) -> Optional[List[str]]:
    """Parse comma-separated strings."""
    if not value:
        return None
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or None


def parse_model_specs(specs: List[str]) -> List[EvalModelConfig]:
    """Parse ``model:weight`` specifications into typed configs."""
    if not specs:
        raise ValueError("At least one --model spec is required")

    model_configs: List[EvalModelConfig] = []
    for spec in specs:
        if ":" not in spec:
            raise ValueError(
                f"Invalid model spec '{spec}'. Expected format model:weight"
            )

        model_name, weight_text = spec.split(":", 1)
        model_name = model_name.strip()
        if not model_name:
            raise ValueError(f"Invalid model spec '{spec}'. Model name is empty")

        try:
            weight = float(weight_text)
        except ValueError as exc:
            raise ValueError(f"Invalid model weight in spec '{spec}'") from exc

        model_configs.append(EvalModelConfig(model=model_name, weight=weight))

    return model_configs


def cmd_seed_queries(args: argparse.Namespace) -> None:
    """Seed `ir_eval.queries` from a golden queries JSON file."""
    store = EvaluationStore(args.db_url)
    inserted = store.seed_queries_from_json(args.file)
    print(json.dumps({"seeded_queries": inserted}, indent=2))


def cmd_create_run(args: argparse.Namespace) -> None:
    """Create a new evaluation run with immutable config."""
    store = EvaluationStore(args.db_url)
    executor = RunExecutor(store=store, db_url=args.db_url)

    run_config = EvalRunConfig(
        name=args.name,
        description=args.description or "",
        embedding_models=parse_model_specs(args.model),
        hybrid_search=args.hybrid,
        vector_weight=args.vector_weight,
        text_weight=args.text_weight,
        cross_encoder_enabled=args.cross_encoder,
        top_k=args.top_k,
        query_ids=parse_csv_ints(args.query_ids),
        query_categories=parse_csv_strings(args.query_categories),
    )

    run_id = executor.create_run(run_config)
    print(json.dumps({"run_id": run_id}, indent=2))


def cmd_execute_run(args: argparse.Namespace) -> None:
    """Execute a previously created run."""
    store = EvaluationStore(args.db_url)
    executor = RunExecutor(store=store, db_url=args.db_url)
    summary = executor.execute_run(args.run_id)
    print(json.dumps(summary.model_dump(mode="json"), indent=2))


def cmd_compare_runs(args: argparse.Namespace) -> None:
    """Compare two completed runs."""
    store = EvaluationStore(args.db_url)
    engine = ComparisonEngine(store)
    output = engine.compare_runs(args.run_a, args.run_b)
    print(json.dumps(output, indent=2))


def cmd_list_runs(args: argparse.Namespace) -> None:
    """List recent run statuses."""
    store = EvaluationStore(args.db_url)
    runs = store.list_runs(limit=args.limit)
    print(json.dumps(runs, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="IR evaluation V2 runner")
    parser.add_argument(
        "--db-url",
        default=default_db_url(),
        help="PostgreSQL URL (for example: postgresql://pythagor@localhost/NEXUS)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser(
        "seed-queries", help="Load queries from a golden JSON file"
    )
    seed.add_argument("--file", required=True, help="Path to golden_queries JSON")
    seed.set_defaults(func=cmd_seed_queries)

    create = subparsers.add_parser("create-run", help="Create a run configuration")
    create.add_argument("--name", required=True, help="Run name")
    create.add_argument("--description", default="", help="Run description")
    create.add_argument(
        "--model",
        action="append",
        required=True,
        help="Model spec in model:weight format (repeatable)",
    )
    create.add_argument("--hybrid", action=argparse.BooleanOptionalAction, default=True)
    create.add_argument("--vector-weight", type=float, default=0.6)
    create.add_argument("--text-weight", type=float, default=0.4)
    create.add_argument(
        "--cross-encoder",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable cross-encoder reranking",
    )
    create.add_argument("--top-k", type=int, default=10)
    create.add_argument("--query-ids", default=None, help="Comma-separated query IDs")
    create.add_argument(
        "--query-categories",
        default=None,
        help="Comma-separated query category filters",
    )
    create.set_defaults(func=cmd_create_run)

    execute = subparsers.add_parser("execute-run", help="Execute an existing run")
    execute.add_argument("--run-id", type=int, required=True)
    execute.set_defaults(func=cmd_execute_run)

    compare = subparsers.add_parser("compare-runs", help="Compare two runs")
    compare.add_argument("--run-a", type=int, required=True)
    compare.add_argument("--run-b", type=int, required=True)
    compare.set_defaults(func=cmd_compare_runs)

    list_runs = subparsers.add_parser("list-runs", help="List recent runs")
    list_runs.add_argument("--limit", type=int, default=20)
    list_runs.set_defaults(func=cmd_list_runs)

    return parser


def main() -> int:
    """Entry point for CLI execution."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
