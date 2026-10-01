"""Read-only gate inventory and reference-cadence evidence for 778-S4a."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import timezone
import inspect
import json
import logging
import os
from pathlib import Path
import re
import statistics
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery import substrate, templates
from nexus.agents.orrery.substrate import CompoundCondition, Slot
from nexus.database import connection_kwargs

PREDICATES = (
    "since_last_event_at_least",
    "count_recent_events_at_least",
    "knows_recent_event",
    "recent_event",
)
SOURCE = Path(templates.__file__)
SOURCE_LABEL = "nexus/agents/orrery/templates.py"
PACING = {
    "train/package_gate/3",
    "run_errands/package_gate/2",
    "stroll/package_gate/1",
    "upkeep/package_gate/1",
    "recreate/package_gate/2",
    "mourn_loss/package_gate/2",
}


def _literal(node: ast.expr) -> Any:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "Slot":
            return Slot[node.attr]
    return ast.literal_eval(node)


def _arguments(node: ast.Call) -> dict[str, Any]:
    assert isinstance(node.func, ast.Name)
    signature = inspect.signature(getattr(substrate, node.func.id))
    bound = signature.bind(
        *[_literal(arg) for arg in node.args],
        **{kw.arg: _literal(kw.value) for kw in node.keywords if kw.arg},
    )
    bound.apply_defaults()
    return dict(bound.arguments)


def _source_gates(tree: ast.Module) -> dict[str, ast.Call]:
    """Locate gate occurrences structurally, independently of runtime traversal."""
    result: dict[str, ast.Call] = {}

    def walk(node: ast.expr, prefix: str, path: tuple[int, ...] = ()) -> None:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            return
        if node.func.id in PREDICATES:
            name = prefix + "/" + ("/".join(map(str, path)) if path else "root")
            if name in result:
                raise ValueError(f"Duplicate source gate name: {name}")
            result[name] = node
        elif node.func.id in ("AND", "OR", "NOT"):
            for index, child in enumerate(node.args):
                walk(child, prefix, (*path, index))

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Template"
        ):
            continue
        fields = {kw.arg: kw.value for kw in node.keywords}
        template_id = ast.literal_eval(fields["id"])
        walk(fields["package_gate"], f"{template_id}/package_gate")
        branches = fields["branches"]
        if not isinstance(branches, ast.Tuple):
            raise ValueError(f"Unparsed branches for {template_id}")
        for index, branch in enumerate(branches.elts):
            if not isinstance(branch, ast.Call):
                raise ValueError(f"Unparsed branch for {template_id}")
            conditions = next(
                kw.value for kw in branch.keywords if kw.arg == "conditions"
            )
            walk(conditions, f"{template_id}/branches[{index}].conditions")
    census = Counter(
        (node.func.id, node.lineno, ast.dump(node))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in PREDICATES
    )
    mapped = Counter(
        (node.func.id, node.lineno, ast.dump(node))  # type: ignore[attr-defined]
        for node in result.values()
    )
    if mapped != census:
        raise ValueError("Source gate mapping disagrees with independent AST census")
    return result


def inventory() -> list[dict[str, Any]]:
    """Inventory every runtime tick leaf and cross-check its source and arguments."""
    source = SOURCE.read_text()
    sources = _source_gates(ast.parse(source))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def walk(
        condition: Any,
        template_id: str,
        scope: str,
        branch_label: str | None,
        path: tuple[int, ...] = (),
    ) -> None:
        if isinstance(condition, CompoundCondition):
            for index, child in enumerate(condition.children):
                walk(child, template_id, scope, branch_label, (*path, index))
            return
        label = getattr(condition, "__name__", "")
        predicate = label.split("(", 1)[0]
        closure = inspect.getclosurevars(condition).nonlocals
        if predicate not in PREDICATES:
            if any(key in closure for key in ("minimum_ticks", "within_ticks")):
                raise ValueError(f"Unparsed tick leaf: {label}")
            return
        name = f"{template_id}/{scope}/" + (
            "/".join(map(str, path)) if path else "root"
        )
        if name in seen:
            raise ValueError(f"Duplicate gate name: {name}")
        seen.add(name)
        node = sources.get(name)
        if node is None or not isinstance(node.func, ast.Name):
            raise ValueError(f"Source mismatch: {name}")
        arguments = _arguments(node)
        if node.func.id != predicate:
            raise ValueError(f"Source predicate mismatch: {name}")
        for key, value in arguments.items():
            actual = closure.get(key)
            if key == "changed_fields_any_of":
                actual = closure.get("changed_fields")
                value = frozenset(value)
            if actual != value:
                raise ValueError(f"Source argument mismatch: {name}: {key}")
        event = arguments["event_type"]
        cadence = name in PACING
        evidence = f"{SOURCE_LABEL}:{node.lineno}"
        if cadence:
            marker = (
                "# The mourning_completed cooldown paces back-to-back griefs"
                if template_id == "mourn_loss"
                else "# Anti-monoculture comes from cooldown staggering"
            )
            purpose_line = next(
                i for i, line in enumerate(source.splitlines(), 1) if marker in line
            )
            evidence += f"; {SOURCE_LABEL}:{purpose_line}"
            purpose = (
                "Proposed grief-completion pacing, based explicitly on "
                "the pacing comment."
                if template_id == "mourn_loss"
                else "Stagger mundane actions to preserve varied narration."
            )
        elif predicate == "since_last_event_at_least":
            scope_word = (
                "actor-target"
                if arguments["target_slot"] is not None
                else "actor-global"
            )
            purpose = f"Refractory period for {scope_word} {event} recurrence."
        elif predicate == "count_recent_events_at_least":
            purpose = (
                f"Accumulate {event} occurrences inside a bounded world-time window."
            )
        else:
            purpose = (
                f"Event-recency window for {event} under enclosing Boolean conditions."
            )
        rows.append(
            {
                "gate_name": name,
                "template_id": template_id,
                "scope": scope,
                "branch_label": branch_label,
                "predicate": predicate,
                "event_type": event,
                "tick_parameter": (
                    "minimum_ticks" if "minimum_ticks" in arguments else "within_ticks"
                ),
                "ticks": arguments.get("minimum_ticks", arguments.get("within_ticks")),
                "minimum_count": arguments.get("min_count"),
                "actor_scope": (
                    arguments["actor_slot"].value if arguments["actor_slot"] else None
                ),
                "target_scope": (
                    arguments["target_slot"].value if arguments["target_slot"] else None
                ),
                "knower_scope": "actor" if predicate == "knows_recent_event" else None,
                "changed_fields_any_of": list(
                    arguments.get("changed_fields_any_of", ())
                ),
                "source_line": node.lineno,
                "classification": "turn-cadenced" if cadence else "diegetic",
                "purpose": purpose,
                "evidence": evidence,
            }
        )

    for template in templates.BUILTIN_TEMPLATES:
        walk(template.package_gate, template.id, "package_gate", None)
        for index, branch in enumerate(template.branches):
            walk(
                branch.conditions,
                template.id,
                f"branches[{index}].conditions",
                branch.label,
            )
    if seen != set(sources):
        raise ValueError("Runtime inventory disagrees with source census")
    return sorted(rows, key=lambda row: row["gate_name"])


def validate_target(dbname: str) -> None:
    """Reject contaminated slot 2 and unapproved targets before connecting."""
    if dbname not in {
        "ref_codex_bakeoff_2026_07",
        "save_01",
        "save_03",
        "save_04",
        "save_05",
    } and not re.fullmatch(r"qa640_[A-Za-z0-9_]+", dbname):
        raise ValueError(f"Unapproved cooldown calibration target: {dbname}")


@contextmanager
def readonly_connection(dbname: str) -> Iterator[Any]:
    """Enforce and verify database identity, read-only, and repeatable-read state."""
    validate_target(dbname)
    options = (
        os.environ.get("PGOPTIONS", "")
        + " -c default_transaction_read_only=on"
        + " -c default_transaction_isolation=repeatable\\ read"
    )
    with closing(
        psycopg2.connect(
            **connection_kwargs(dbname, options=options), cursor_factory=RealDictCursor
        )
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database() AS dbname, "
                "current_setting('transaction_read_only') AS read_only, "
                "current_setting('transaction_isolation') AS isolation"
            )
            identity = dict(cur.fetchone())
            if identity != {
                "dbname": dbname,
                "read_only": "on",
                "isolation": "repeatable read",
            }:
                raise RuntimeError(f"Unprotected or mismatched transaction: {identity}")
        yield conn


def corpus_report(dbname: str) -> dict[str, Any]:
    """Measure stored primary clocks and stored resolutions without evaluating gates."""
    with readonly_connection(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS count, max(version) AS level FROM schema_migrations"
        )
        migration = dict(cur.fetchone())
        cur.execute("SELECT count(*) AS count FROM narrative_chunks")
        total_chunks = cur.fetchone()["count"]
        cur.execute(
            "SELECT chunk_id, world_time, time_delta FROM chunk_metadata "
            "WHERE world_layer = 'primary' ORDER BY chunk_id"
        )
        chunks = list(cur.fetchall())
        cur.execute(
            "SELECT template_id, count(*) AS rows, "
            "count(DISTINCT tick_chunk_id) AS ticks "
            "FROM orrery_resolutions GROUP BY template_id ORDER BY template_id"
        )
        firings = [dict(row) for row in cur.fetchall()]
        cur.execute(
            "SELECT count(*) AS rows, count(DISTINCT tick_chunk_id) AS ticks, "
            "count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM chunk_metadata cm "
            "WHERE cm.chunk_id = r.tick_chunk_id AND cm.world_layer = 'primary')) "
            "AS rows_without_primary_metadata FROM orrery_resolutions r"
        )
        totals = dict(cur.fetchone())
    if len(chunks) < 2:
        raise ValueError("Fewer than two primary chunks")
    if any(row["world_time"] is None for row in chunks):
        raise ValueError("NULL primary world clock")
    pairs = []
    for left, right in zip(chunks, chunks[1:]):
        gap = right["chunk_id"] - left["chunk_id"]
        hours = (right["world_time"] - left["world_time"]).total_seconds() / 3600
        if gap <= 0 or hours < 0:
            raise ValueError("Non-positive tick gap or reversed primary clock")
        pairs.append(
            {
                "from_chunk": left["chunk_id"],
                "to_chunk": right["chunk_id"],
                "tick_gap": gap,
                "world_hours": hours,
                "hours_per_tick": hours / gap,
            }
        )
    hours = [pair["world_hours"] for pair in pairs]
    tick_gaps = sum(pair["tick_gap"] for pair in pairs)
    weighted = sum(hours) / tick_gaps
    median_rate = statistics.median(pair["hours_per_tick"] for pair in pairs)
    gates = inventory()
    for gate in gates:
        gate["weighted_equivalent_hours"] = gate["ticks"] * weighted
        gate["median_equivalent_hours"] = gate["ticks"] * median_rate
    current = {template.id for template in templates.BUILTIN_TEMPLATES}
    indexed = {row["template_id"]: row for row in firings}
    post140 = int(migration["level"]) >= 140
    return {
        "header": {
            "database": dbname,
            "migration_count": migration["count"],
            "migration_level": migration["level"],
            "transaction_read_only": "on",
            "transaction_isolation": "repeatable read",
            "total_chunks": total_chunks,
            "classification_status": (
                "Analytical proposals under settled Q1; no policy adopted."
            ),
            "clock_basis": (
                "Post-140 primary-only stored clocks; "
                "slots already repaired by migration 140."
                if post140
                else "Inherited all-layer clock contamination: stored primary clocks "
                "retain intervening non-primary durations."
            ),
            "limitation": (
                "Reference stays at migration 114 with inherited "
                "all-layer contamination; "
                "its reference-cadence equivalents retain that contamination. "
                "Slots are already repaired (migration 140). "
                "Reference equivalents require remeasurement after the "
                "primary-layer trigger repair in 778-S1b reaches that corpus. "
                "Never reconstruct or subtract from stored clocks. "
                "Primary-only duration sums differ conceptually from "
                "stored-clock span and cadence. "
                "Equivalents are measurements, not hour policy values."
            ),
            "firing_basis": (
                "Stored resolution counts, not predicate evaluations or "
                "counterfactual firings; no actor-specific inference."
            ),
        },
        "cadence": {
            "first_clock_utc": chunks[0]["world_time"]
            .astimezone(timezone.utc)
            .isoformat(),
            "last_clock_utc": chunks[-1]["world_time"]
            .astimezone(timezone.utc)
            .isoformat(),
            "primary_chunks": len(chunks),
            "primary_duration_hours": sum(
                row["time_delta"].total_seconds()
                for row in chunks
                if row["time_delta"] is not None
            )
            / 3600,
            "null_primary_durations": sum(row["time_delta"] is None for row in chunks),
            "world_clock_span_hours": (
                chunks[-1]["world_time"] - chunks[0]["world_time"]
            ).total_seconds()
            / 3600,
            "adjacent_pairs": len(pairs),
            "total_tick_gaps": tick_gaps,
            "zero_deltas": hours.count(0),
            "mean_pair_hours": statistics.mean(hours),
            "median_pair_hours": statistics.median(hours),
            "weighted_hours_per_tick": weighted,
            "median_pair_hours_per_tick": median_rate,
            "pairs": pairs,
        },
        "gates": gates,
        "firings": {
            **totals,
            "current_packages": [
                indexed.get(name, {"template_id": name, "rows": 0, "ticks": 0})
                for name in sorted(current)
            ],
            "unknown_historical_packages": [
                row for row in firings if row["template_id"] not in current
            ],
        },
    }


def markdown(report: dict[str, Any]) -> str:
    """Render every JSON field in deterministic Markdown tables."""
    lines = ["# Cooldown Calibration"]

    def cell(value: Any) -> str:
        return (
            json.dumps(value, ensure_ascii=False)
            .replace("|", "&#124;")
            .replace("\n", "<br>")
        )

    def section(name: str, value: Any) -> None:
        lines.extend(["", f"## {name}", ""])
        if isinstance(value, list):
            if not value:
                lines.append("[]")
                return
            keys = list(value[0])
            lines.extend(
                [
                    "| " + " | ".join(keys) + " |",
                    "| " + " | ".join("---" for _ in keys) + " |",
                ]
            )
            lines.extend(
                "| " + " | ".join(cell(row[key]) for key in keys) + " |"
                for row in value
            )
        else:
            lines.extend(["| Field | Value |", "| --- | --- |"])
            for key, item in value.items():
                if not isinstance(item, list):
                    lines.append(f"| {key} | {cell(item)} |")
            for key, item in value.items():
                if isinstance(item, list):
                    section(key, item)

    for name, value in report.items():
        section(name, value)
    return "\n".join(lines) + "\n"


def main() -> None:
    """Print exactly one report, using only an enforced read-only corpus snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbname", required=True)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    report = corpus_report(args.dbname)
    print(
        (
            json.dumps(report, indent=2, ensure_ascii=False)
            if args.format == "json"
            else markdown(report)
        ),
        end="\n" if args.format == "json" else "",
    )


if __name__ == "__main__":
    main()
