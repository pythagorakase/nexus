"""Report Pass 2 retrieval coverage telemetry for one save slot.

Usage:
    python scripts/report_retrieval_coverage.py --slot 2
"""

from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import psycopg2  # type: ignore[import-untyped]
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.api.slot_utils import slot_dbname


_LENGTH_BUCKETS = (
    ("1-4 words", 1, 4),
    ("5-9 words", 5, 9),
    ("10-19 words", 10, 19),
    ("20+ words", 20, None),
)


def _length_bucket(user_input: str) -> str:
    word_count = len(user_input.split())
    for label, minimum, maximum in _LENGTH_BUCKETS:
        if word_count >= minimum and (maximum is None or word_count <= maximum):
            return label
    return "0 words"


def _percentage(numerator: int, denominator: int) -> str:
    if not denominator:
        return "n/a"
    return f"{numerator / denominator * 100:.1f}%"


def format_retrieval_coverage_report(
    slot: int,
    rows: Iterable[Mapping[str, Any]],
) -> str:
    """Format decision-facing retrieval coverage measures as plain text."""

    row_list = list(rows)
    total_turns = len(row_list)
    detected_turns = 0
    kind_detections: Counter[str] = Counter()
    kind_gaps: Counter[str] = Counter()
    entity_detections: Counter[tuple[str, int, str]] = Counter()
    entity_gaps: Counter[tuple[str, int, str]] = Counter()
    bucket_counts: Dict[str, Counter[str]] = defaultdict(Counter)

    for row in row_list:
        detected_entities = row.get("detected_entities") or []
        gap_entities = row.get("gap_entities") or []
        gap_keys = {(str(entity["kind"]), int(entity["id"])) for entity in gap_entities}
        detected = bool(detected_entities)
        missed = bool(gap_entities)
        detected_turns += int(detected)

        bucket = _length_bucket(str(row.get("user_input") or ""))
        bucket_counts[bucket]["turns"] += 1
        bucket_counts[bucket]["detected_turns"] += int(detected)
        bucket_counts[bucket]["missed_turns"] += int(missed)

        for entity in detected_entities:
            kind = str(entity["kind"])
            entity_id = int(entity["id"])
            name = str(entity["name"])
            key = (kind, entity_id, name)
            kind_detections[kind] += 1
            entity_detections[key] += 1
            if (kind, entity_id) in gap_keys:
                kind_gaps[kind] += 1
                entity_gaps[key] += 1

    lines = [
        f"Retrieval coverage report - slot {slot}",
        f"Total turns audited: {total_turns}",
        "Detection rate: "
        f"{_percentage(detected_turns, total_turns)} "
        f"({detected_turns}/{total_turns})",
        "",
        "Per-kind miss rate",
    ]

    if kind_detections:
        for kind in sorted(kind_detections):
            gaps = kind_gaps[kind]
            detections = kind_detections[kind]
            lines.append(
                f"  {kind:<10} {_percentage(gaps, detections):>6} "
                f"({gaps}/{detections})"
            )
    else:
        lines.append("  no detected entities")

    lines.extend(("", "Gap frequency by entity"))
    if entity_gaps:
        ordered_entities = sorted(
            entity_gaps,
            key=lambda key: (-entity_gaps[key], key[0], key[2].lower(), key[1]),
        )
        for kind, entity_id, name in ordered_entities:
            key = (kind, entity_id, name)
            gaps = entity_gaps[key]
            detections = entity_detections[key]
            lines.append(
                f"  {kind}:{name} [{entity_id}] {gaps} gap(s) / "
                f"{detections} detection(s) ({_percentage(gaps, detections)})"
            )
    else:
        lines.append("  no gaps")

    lines.extend(("", "Miss rate by user-input length (among detected turns)"))
    bucket_labels = [label for label, _minimum, _maximum in _LENGTH_BUCKETS]
    if "0 words" in bucket_counts:
        bucket_labels.insert(0, "0 words")
    for label in bucket_labels:
        counts = bucket_counts[label]
        missed_turns = counts["missed_turns"]
        detected_in_bucket = counts["detected_turns"]
        lines.append(
            f"  {label:<12} {_percentage(missed_turns, detected_in_bucket):>6} "
            f"({missed_turns}/{detected_in_bucket}); "
            f"audited turns={counts['turns']}"
        )

    return "\n".join(lines)


def _load_rows(slot: int) -> List[Mapping[str, Any]]:
    # Honor the standard libpq env vars (the pattern the live-test helpers
    # use); bare defaults match the documented single-machine setup.
    connection = psycopg2.connect(
        dbname=slot_dbname(slot),
        host=os.environ.get("PGHOST", "localhost"),
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )
    connection.set_session(readonly=True)
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT user_input, detected_entities, gap_entities
                FROM retrieval_coverage_log
                ORDER BY id
                """
            )
            return list(cursor.fetchall())
    finally:
        connection.close()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, choices=range(1, 6), required=True)
    args = parser.parse_args(argv)
    print(format_retrieval_coverage_report(args.slot, _load_rows(args.slot)))


if __name__ == "__main__":
    main()
