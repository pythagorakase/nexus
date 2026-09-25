"""Measure the 2560d ANN promotion gate on a disposable, read-only-source clone."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import tempfile
from time import perf_counter
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn

from nexus.agents.memnon.utils.embedding_tables import (
    build_candidate_ann_index,
    configure_ann_session,
    drop_candidate_ann_index,
    vector_distance_sql,
)
from nexus.api.slot_utils import slot_dbname
from nexus.config import load_settings
from nexus.config.settings_models import ANNConfig
from nexus.database import connection_kwargs
from scripts.new_story_setup import _postgres_tools

TABLE = "chunk_embeddings_2560d"
OUT = Path(__file__).resolve().parents[2] / "docs/qa/766-ann-gate"


@contextmanager
def slot_clone(slot: int) -> Iterator[str]:
    """Dump a slot in read-only mode; restore and always drop our unique clone."""
    source = slot_dbname(slot)
    name = "qa640_766_" + uuid4().hex[:12]
    binaries = _postgres_tools("pg_dump", "pg_restore")
    admin = psycopg2.connect(**connection_kwargs("postgres"))
    admin.autocommit = True
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix="ann-gate-") as directory:
            archive = Path(directory) / "source.dump"
            subprocess.run(
                [
                    binaries["pg_dump"],
                    "--format=custom",
                    "--file",
                    str(archive),
                    "--dbname",
                    make_dsn(
                        **connection_kwargs(
                            source, options="-c default_transaction_read_only=on"
                        )
                    ),
                ],
                check=True,
            )
            with admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                        sql.Identifier(name)
                    )
                )
            created = True
            subprocess.run(
                [
                    binaries["pg_restore"],
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    make_dsn(**connection_kwargs(name)),
                    str(archive),
                ],
                check=True,
            )
            yield name
    finally:
        try:
            if created:
                with admin.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                            sql.Identifier(name)
                        )
                    )
        finally:
            admin.close()


def promotion_verdict(evidence: dict[str, Any], config: ANNConfig) -> str:
    """Require scale, measured latency, speedup, and recall together."""
    passed = (
        evidence["documents"] >= config.min_documents
        and evidence["exact_p95_ms"] > config.max_exact_p95_ms
        and evidence["approximate_p95_ms"] < evidence["exact_p95_ms"]
        and evidence["recall_at_10"] >= config.minimum_recall_at_10
    )
    return "PROMOTE" if passed else "KEEP_EXACT"


def _p95(values: list[float]) -> float:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def measure_clone(dbname: str, config: ANNConfig) -> dict[str, Any]:
    """Measure exact and indexed queries in this process, using stored vectors."""
    if not dbname.startswith("qa640_766_"):
        raise ValueError("ANN measurement only accepts qa640_766_* clones")
    connection = psycopg2.connect(**connection_kwargs(dbname))
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), version()")
            actual, postgres_version = cursor.fetchone()
            if actual != dbname:
                raise RuntimeError("Measurement connection targets the wrong database")
            cursor.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            vector_version = cursor.fetchone()[0]
            # A source may eventually have a promoted index. Rebuild on the clone.
            drop_candidate_ann_index(cursor, TABLE)
            cursor.execute(f"ANALYZE {TABLE}")
            cursor.execute(f"SELECT count(*), count(DISTINCT chunk_id) FROM {TABLE}")
            rows, documents = cursor.fetchone()
            if documents < 10:
                raise ValueError("Recall@10 requires at least ten embedded documents")
            cursor.execute(
                f"SELECT chunk_id, model, embedding::text FROM {TABLE} "
                "ORDER BY md5(chunk_id::text || ':' || model), chunk_id, model LIMIT %s",
                (config.probe_queries,),
            )
            probes = cursor.fetchall()
            exact_config = config.model_copy(update={"enabled": False})
            ann_config = config.model_copy(update={"enabled": True})
            exact_distance = vector_distance_sql("embedding", "%s", 2560, exact_config)
            ann_distance = vector_distance_sql("embedding", "%s", 2560, ann_config)
            exact_sql = f"SELECT chunk_id FROM {TABLE} WHERE model = %s ORDER BY {exact_distance} LIMIT 10"
            ann_sql = f"SELECT chunk_id FROM {TABLE} WHERE model = %s ORDER BY {ann_distance} LIMIT 10"
            # Explicit exact control even if a future source has another ANN index.
            cursor.execute("SET LOCAL enable_indexscan = off")
            cursor.execute("SET LOCAL enable_bitmapscan = off")
            measurements = []
            for chunk_id, model, vector in probes:
                cursor.execute(exact_sql, (model, vector))  # Per-query warm-up.
                cursor.fetchall()
                start = perf_counter()
                cursor.execute(exact_sql, (model, vector))
                exact_ids = [row[0] for row in cursor.fetchall()]
                elapsed = (perf_counter() - start) * 1000
                if len(exact_ids) != 10:
                    raise ValueError(
                        f"Model {model} has fewer than ten searchable rows"
                    )
                measurements.append(
                    {
                        "query_chunk_id": chunk_id,
                        "model": model,
                        "exact_ms": elapsed,
                        "exact_top_10": exact_ids,
                    }
                )
            cursor.execute(
                "EXPLAIN (FORMAT JSON) " + exact_sql, (probes[0][1], probes[0][2])
            )
            exact_plan = cursor.fetchone()[0]
            cursor.execute("SET LOCAL enable_indexscan = on")
            cursor.execute("SET LOCAL enable_bitmapscan = on")
            start = perf_counter()
            index_name = build_candidate_ann_index(cursor, TABLE)
            build_ms = (perf_counter() - start) * 1000
            cursor.execute("SELECT pg_relation_size(%s::regclass)", (index_name,))
            index_bytes = cursor.fetchone()[0]
            configure_ann_session(cursor, 2560, ann_config)
            cursor.execute(
                "EXPLAIN (FORMAT JSON) " + ann_sql, (probes[0][1], probes[0][2])
            )
            natural_approximate_plan = cursor.fetchone()[0]
            # Tiny, toasted-vector tables are commonly cheaper in the planner's
            # model as a full scan + sort. Benchmark the actual ANN candidate,
            # recording this control separately from the natural runtime plan.
            cursor.execute("SET LOCAL enable_seqscan = off")
            cursor.execute("SET LOCAL enable_sort = off")
            cursor.execute("SET LOCAL jit = off")
            for (_, model, vector), measurement in zip(
                probes, measurements, strict=True
            ):
                cursor.execute(ann_sql, (model, vector))
                cursor.fetchall()
                start = perf_counter()
                cursor.execute(ann_sql, (model, vector))
                approximate_ids = [row[0] for row in cursor.fetchall()]
                elapsed = (perf_counter() - start) * 1000
                measurement.update(
                    {
                        "approximate_ms": elapsed,
                        "approximate_top_10": approximate_ids,
                        "recall_at_10": len(
                            set(approximate_ids) & set(measurement["exact_top_10"])
                        )
                        / 10,
                    }
                )
            cursor.execute(
                "EXPLAIN (FORMAT JSON) " + ann_sql, (probes[0][1], probes[0][2])
            )
            approximate_plan = cursor.fetchone()[0]
            if index_name not in json.dumps(approximate_plan):
                _redact_query_vector(approximate_plan)
                raise RuntimeError(
                    f"Planner did not use the candidate index; ANN evidence is invalid: {approximate_plan}"
                )
            # Avoid embedding vectors in EXPLAIN evidence (the Order By contains them).
            for plan in (exact_plan, approximate_plan, natural_approximate_plan):
                _redact_query_vector(plan)
            evidence = {
                "measured_at": datetime.now(timezone.utc).isoformat(),
                "machine": platform.platform(),
                "python": platform.python_version(),
                "postgres": postgres_version,
                "pgvector": vector_version,
                "clone": dbname,
                "table": TABLE,
                "rows": rows,
                "documents": documents,
                "probe_queries": len(probes),
                "settings": config.model_dump(),
                "sample_sha256": hashlib.sha256(
                    json.dumps(probes).encode()
                ).hexdigest(),
                "method": "Deterministic MD5-ordered stored-vector probes, self-match included; one warm-up then one timed query per path; nearest-rank p95; client execute+fetch wall time, same process/machine; exact before index build. No inference.",
                "exact_p95_ms": _p95([m["exact_ms"] for m in measurements]),
                "approximate_p95_ms": _p95([m["approximate_ms"] for m in measurements]),
                "recall_at_10": sum(m["recall_at_10"] for m in measurements)
                / len(measurements),
                "index_build_ms": build_ms,
                "index_bytes": index_bytes,
                "index_name": index_name,
                "exact_plan": exact_plan,
                "approximate_plan": approximate_plan,
                "natural_approximate_plan": natural_approximate_plan,
                "ann_planner_controls": {
                    "enable_seqscan": False,
                    "enable_sort": False,
                    "jit": False,
                },
                "queries": measurements,
            }
            evidence["verdict"] = promotion_verdict(evidence, config)
            return evidence
    finally:
        connection.close()


def _redact_query_vector(value: Any) -> None:
    import re

    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str):
                value[key] = re.sub(r"'\[[^]]+\]'", "'<stored query vector>'", child)
            else:
                _redact_query_vector(child)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, str):
                value[index] = re.sub(r"'\[[^]]+\]'", "'<stored query vector>'", child)
            else:
                _redact_query_vector(child)


def compact_table(evidence: dict[str, Any]) -> str:
    """Render the measured gate as one compact, copyable Markdown table."""
    return (
        "| Rows | Probes | Exact p95 ms | ANN p95 ms | Recall@10 | Build ms | Index bytes | Verdict |\n"
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |\n"
        f"| {evidence['rows']} | {evidence['probe_queries']} | {evidence['exact_p95_ms']:.3f} | "
        f"{evidence['approximate_p95_ms']:.3f} | {evidence['recall_at_10']:.4f} | "
        f"{evidence['index_build_ms']:.3f} | {evidence['index_bytes']} | {evidence['verdict']} |"
    )


def main() -> None:
    """Clone, measure, write evidence, and clean up without promoting a save."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", required=True, type=int, choices=range(1, 6))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    config = load_settings().memnon.retrieval.ann
    with slot_clone(args.slot) as dbname:
        evidence = measure_clone(dbname, config)
    evidence.update({"source": slot_dbname(args.slot), "clone_dropped": True})
    destination = args.output or OUT / f"save_{args.slot:02d}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2) + "\n")
    print(compact_table(evidence))
    print(f"Evidence: {destination}")


if __name__ == "__main__":
    main()
