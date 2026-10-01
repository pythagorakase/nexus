"""Read-only, date-bounded demand coverage and input-error evidence for #759.

Ledger prefixes and each database inspection are separate snapshots. This is
not an atomic report-wide snapshot and it cannot measure concurrent dispatch.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extensions import TRANSACTION_STATUS_IDLE
from psycopg2.extras import RealDictCursor

from nexus.database import connection_kwargs
from nexus.telemetry.attempt_manifest import inspect_turn
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.turn_observation import (
    BACKGROUND_SEAT_QUEUES,
    _job_events,
    derive_turn_observation,
    job_ledger_days,
)
from nexus.telemetry.usage import UsageEvent

UNKNOWN = "unknown"
DIMENSIONS = ("slot", "seat", "provider", "model", "transport")
NO_DISPATCH = "Existing ledgers have no per-call dispatch timestamps."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _days(first: date, last: date) -> list[str]:
    if first > last:
        raise ValueError("from-day must not exceed through-day")
    return [
        (first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)
    ]


def read_snapshot(usage_dir: Path, first: date, last: date) -> dict[str, Any]:
    """Validate fixed byte prefixes, retaining events and folding window revisions."""
    if not usage_dir.is_dir():
        raise FileNotFoundError(usage_dir)
    days = _days(first, last)
    snapshot: dict[str, Any] = {
        "read_at": _now(),
        "from_day": first.isoformat(),
        "through_day": last.isoformat(),
        "files": [],
        "missing_days": {"windows": [], "usage": []},
        "days": days,
    }
    events = []
    windows: dict[tuple[str, str, int], dict[str, Any]] = {}
    window_rows = 0
    # Capture every length before reading any content; an append cannot expand it.
    files = []
    for day in days:
        for kind in ("windows", "usage"):
            path = usage_dir / f"{kind}-{day}.jsonl"
            if not path.exists():
                snapshot["missing_days"][kind].append(day)
            else:
                files.append((day, kind, path, path.stat().st_size))
    for day, kind, path, length in files:
        with path.open("rb") as stream:
            data = stream.read(length)
        if len(data) != length:
            raise ValueError(f"Ledger shrank during read: {path}")
        if data and not data.endswith(b"\n"):
            raise ValueError(f"Partial final JSON row: {path}")
        snapshot["files"].append(
            {
                "path": str(path),
                "bytes": length,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        for number, line in enumerate(data.splitlines(), 1):
            raw = json.loads(line)
            source = {"path": str(path), "line": number, "day": day}
            if kind == "usage":
                if not isinstance(raw, dict) or not isinstance(raw.get("ts"), str):
                    raise ValueError(f"Missing explicit usage timestamp: {source}")
                if datetime.fromisoformat(raw["ts"]).utcoffset() is None:
                    raise ValueError(f"Usage timestamp has no UTC offset: {source}")
                event = UsageEvent.model_validate(raw)
                if event.quota_day != day or raw.get("quota_day", day) != day:
                    raise ValueError(f"Contradictory usage day: {source}")
                if event.slot is not None and event.slot not in range(1, 6):
                    raise ValueError(f"Invalid recorded slot: {source}")
                events.append({"record": event, "source": source})
            else:
                window = PromptWindowRecord.model_validate(raw)
                key = (window.generation_session, window.seat, window.attempt)
                prior = windows.get(key)
                if prior and prior["record"].model != window.model:
                    raise ValueError(f"Contradictory window model: {source}")
                windows[key] = {
                    "record": window,
                    "source": source,
                    "revisions": [*(prior["revisions"] if prior else []), source],
                }
                window_rows += 1
    return {
        "snapshot": snapshot,
        "events": events,
        "windows": list(windows.values()),
        "window_rows": window_rows,
    }


def read_connection(dbname: str) -> Any:
    """Open an explicitly named, server-enforced read-only repeatable-read session."""
    return psycopg2.connect(
        **connection_kwargs(
            dbname,
            options=(
                "-c default_transaction_read_only=on "
                "-c default_transaction_isolation=repeatable\\ read"
            ),
        ),
        cursor_factory=RealDictCursor,
    )


def _verify(conn: Any) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT current_database() AS database, "
            "current_setting('transaction_read_only') AS read_only, "
            "current_setting('transaction_isolation') AS isolation, "
            "current_setting('port') AS port, "
            "pg_postmaster_start_time()::text AS server_started_at, "
            "transaction_timestamp()::text AS transaction_started_at, "
            "txid_current_snapshot()::text AS snapshot"
        )
        result = dict(cur.fetchone())
    if result["read_only"] != "on" or result["isolation"] != "repeatable read":
        raise RuntimeError("Read-only repeatable-read transaction is required")
    return result


def read_databases(slot_dbnames: Mapping[int, str]) -> list[dict[str, Any]]:
    """Enumerate sessions, roll back, then let each inspection own its transaction."""
    databases = []
    for slot, dbname in sorted(slot_dbnames.items()):
        if slot not in range(1, 6) or not dbname.strip():
            raise ValueError("A slot 1..5 and a nonempty database name are required")
        with closing(read_connection(dbname)) as conn:
            started = _now()
            identity = _verify(conn)
            if identity["database"] != dbname:
                raise ValueError("Database identity differs from requested target")
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id::text FROM narrative_generation_sessions "
                    "ORDER BY session_id"
                )
                sessions = [row["session_id"] for row in cur.fetchall()]
                cur.execute("SELECT count(*) AS n FROM generation_attempt_manifests")
                manifests = cur.fetchone()["n"]
                cur.execute("SELECT count(*) AS n FROM generation_session_phases")
                phases = cur.fetchone()["n"]
            conn.rollback()
            entry: dict[str, Any] = {
                "slot": slot,
                "dbname": dbname,
                "enumeration": {
                    **identity,
                    "started_at": started,
                    "ended_at": _now(),
                    "session_ids": sessions,
                    "session_count": len(sessions),
                    "manifest_count": manifests,
                    "phase_count": phases,
                    "ended_by": "rollback",
                },
                "inspections": [],
                "snapshot_limit": (
                    "Enumeration and every inspection use separate read-only "
                    "repeatable-read transactions; intervening changes are possible. "
                    "There is no report-wide atomic database snapshot."
                ),
            }
            for session in sessions:
                # Verification itself begins a transaction. End it before inspect_turn.
                verification = _verify(conn)
                conn.rollback()
                idle = conn.get_transaction_status() == TRANSACTION_STATUS_IDLE
                if not idle:
                    raise RuntimeError("inspect_turn requires an idle connection")
                started = _now()
                inspection = inspect_turn(conn, session=session)
                entry["inspections"].append(
                    {
                        "session": session,
                        "started_at": started,
                        "ended_at": _now(),
                        "idle_before": idle,
                        "idle_after": (
                            conn.get_transaction_status() == TRANSACTION_STATUS_IDLE
                        ),
                        "verification": verification,
                        "inspection": inspection,
                    }
                )
            databases.append(entry)
    return databases


def _empty_inspection(run: str) -> dict[str, Any]:
    return {
        "session": {"session_id": run, "terminal_outcome": None},
        "manifests": [],
        "phases": [],
        "jobs": [],
    }


def _percentiles(values: list[float | int]) -> dict[str, Any]:
    values = sorted(values)
    return {
        "count": len(values),
        "min": values[0] if values else UNKNOWN,
        "p50": values[math.ceil(0.50 * len(values)) - 1] if values else UNKNOWN,
        "p95": values[math.ceil(0.95 * len(values)) - 1] if values else UNKNOWN,
        "max": values[-1] if values else UNKNOWN,
    }


def _population(rows: Sequence[dict[str, Any]], comparison: str) -> dict[str, Any]:
    signed: list[int] = []
    relative: list[float] = []
    excluded: Counter[str] = Counter()
    relative_excluded: Counter[str] = Counter()
    for row in rows:
        item = row[comparison]
        if item["exclusion"] is not None:
            excluded[item["exclusion"]] += 1
            relative_excluded[item["exclusion"]] += 1
        else:
            signed.append(item["signed_error"])
            if item["relative_error"] == UNKNOWN:
                relative_excluded["zero_reported"] += 1
            else:
                relative.append(item["relative_error"])
    return {
        "signed_absolute": {
            "eligible": len(signed),
            "excluded": sum(excluded.values()),
            "exclusion_reasons": dict(sorted(excluded.items())),
            "mean_signed_error": sum(signed) / len(signed) if signed else UNKNOWN,
            "mean_absolute_error": (
                sum(abs(n) for n in signed) / len(signed) if signed else UNKNOWN
            ),
            "absolute_error": _percentiles([abs(n) for n in signed]),
        },
        "relative": {
            "eligible": len(relative),
            "excluded": sum(relative_excluded.values()),
            "exclusion_reasons": dict(sorted(relative_excluded.items())),
            "relative_error": _percentiles(relative),
        },
    }


def _statistics(rows: list[dict[str, Any]], comparison: str) -> dict[str, Any]:
    result = {"overall": _population(rows, comparison), "by": {}}
    for dimension in DIMENSIONS:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[json.dumps(row[dimension], sort_keys=True)].append(row)
        result["by"][dimension] = [
            {"value": json.loads(value), **_population(group, comparison)}
            for value, group in sorted(groups.items())
        ]
    return result


def _comparison(estimated: Any, reported: Any, reason: str | None) -> dict[str, Any]:
    numeric = all(type(value) is int and value >= 0 for value in (estimated, reported))
    reason = reason or (None if numeric else "missing_counts")
    signed = estimated - reported if reason is None else UNKNOWN
    return {
        "estimated": estimated if type(estimated) is int else UNKNOWN,
        "reported": reported if type(reported) is int else UNKNOWN,
        "exclusion": reason,
        "signed_error": signed,
        "absolute_error": abs(signed) if isinstance(signed, int) else UNKNOWN,
        "relative_error": signed / reported if reason is None and reported else UNKNOWN,
    }


def _reported(event: UsageEvent) -> int | str:
    counts = [event.input_tokens]
    if event.transport == "anthropic_messages":
        counts += [event.cached_input_tokens, event.cache_creation_tokens]
    return (
        UNKNOWN
        if any(n is None for n in counts)
        else sum(n for n in counts if n is not None)
    )


def reconcile(
    snapshot: dict[str, Any], databases: list[dict[str, Any]]
) -> dict[str, Any]:
    """Enrich selected ledger members through production observations, then measure."""
    events, windows = snapshot["events"], snapshot["windows"]
    days = snapshot["snapshot"]["days"]
    read_at = datetime.fromisoformat(snapshot["snapshot"]["read_at"])
    inspections = {
        (db["slot"], item["session"]): item["inspection"]
        for db in databases
        for item in db["inspections"]
    }
    run_slots: dict[str, set[int]] = defaultdict(set)
    for slot, run in inspections:
        run_slots[run].add(slot)
    for item in events:
        event = item["record"]
        if event.run_id and event.slot is not None:
            run_slots[event.run_id].add(event.slot)
    # Use the production enqueue/slot/seat/queue rules, never a bare numeric id.
    jobs: dict[tuple[int, str, str], dict[str, Any]] = {}
    for (slot, _), inspection in inspections.items():
        for job in inspection["jobs"]:
            if job["queue"] in set(BACKGROUND_SEAT_QUEUES.values()):
                job_identity = (slot, job["queue"], str(job["id"]))
                if job_identity in jobs and jobs[job_identity] != job:
                    raise ValueError(f"Contradictory job identity: {job_identity}")
                jobs[job_identity] = job
    members: dict[tuple[int, str | None, str, str, int], dict[str, Any]] = {}
    unattributed = []

    def member(
        slot: int, queue: str | None, run: str, seat: str, attempt: int
    ) -> dict[str, Any]:
        return members.setdefault(
            (slot, queue, run, seat, attempt),
            {
                "slot": slot,
                "queue": queue,
                "run": run,
                "seat": seat,
                "attempt": attempt,
                "events": [],
                "window": None,
            },
        )

    for item in events:
        event = item["record"]
        reason = None
        queue = None
        if not event.run_id:
            reason = "missing_run"
        elif event.slot is None:
            reason = "missing_slot"
        elif event.run_id.isdecimal():
            queue = BACKGROUND_SEAT_QUEUES.get(event.seat)
            job = jobs.get((event.slot, queue, event.run_id)) if queue else None
            if job is None or queue is None:
                reason = "unmatched_job"
            else:
                job_days = job_ledger_days({"jobs": [job]}, read_at=read_at)
                if not _job_events(
                    job, [event], job_days[(queue, int(event.run_id))], slot=event.slot
                ):
                    reason = "outside_job_boundary"
        if reason:
            unattributed.append(
                {"kind": "usage", "reason": reason, "source": item["source"]}
            )
        else:
            member(event.slot, queue, event.run_id, event.seat, event.attempt)[
                "events"
            ].append(item)
    for item in windows:
        window = item["record"]
        slots = run_slots[window.generation_session]
        reason = None
        if len(slots) != 1:
            reason = "ambiguous_slot" if slots else "missing_slot"
        elif window.generation_session.isdecimal():
            # A window has no enqueue-relative timestamp or explicit slot.
            reason = "untimed_job_window"
        if reason:
            unattributed.append(
                {"kind": "window", "reason": reason, "source": item["source"]}
            )
        else:
            member(
                next(iter(slots)),
                None,
                window.generation_session,
                window.seat,
                window.attempt,
            )["window"] = item

    observations = {}
    session_keys = set(inspections) | {
        (key[0], key[2]) for key in members if key[1] is None
    }
    for slot, run in sorted(session_keys):
        inspection = inspections.get((slot, run), _empty_inspection(run))
        selected = [
            m
            for m in members.values()
            if m["slot"] == slot and m["run"] == run and m["queue"] is None
        ]
        job_days = job_ledger_days(inspection, read_at=read_at)
        job_events = []
        for job in inspection["jobs"]:
            job_key = (job["queue"], int(job["id"]))
            if job_key in job_days:
                job_events.extend(
                    _job_events(
                        job, [e["record"] for e in events], job_days[job_key], slot=slot
                    )
                )
        observations[(slot, run)] = derive_turn_observation(
            inspection,
            [e["record"] for m in selected for e in m["events"]],
            [m["window"]["record"] for m in selected if m["window"]],
            ledger_days=days,
            job_events=job_events,
            slot=slot,
            read_at=read_at,
        )
    # The observation's union is deliberately filtered AFTER derivation.
    for db in databases:
        inventory = []
        for item in db["inspections"]:
            run = item["session"]
            for manifest in item["inspection"]["manifests"]:
                manifest_key = (
                    db["slot"],
                    None,
                    run,
                    manifest["seat"],
                    manifest["attempt"],
                )
                if manifest_key not in members:
                    inventory.append(
                        {
                            "run": run,
                            "seat": manifest["seat"],
                            "attempt": manifest["attempt"],
                            "model": manifest["model_id"],
                        }
                    )
        db["database_only_attempts"] = inventory
        db["database_only_attempt_count"] = len(inventory)

    rows = []
    for key, item in sorted(members.items(), key=lambda pair: str(pair[0])):
        own = [e["record"] for e in item["events"]]
        window = item["window"]["record"] if item["window"] else None
        models = {e.model for e in own} | ({window.model} if window else set())
        providers = {e.provider for e in own}
        if len(models) != 1 or len(providers) > 1:
            raise ValueError(f"Contradictory attempt identity: {key}")
        observation = observations.get((item["slot"], item["run"]))
        projected = (
            next(
                (
                    a
                    for a in observation["attempts"]
                    if a["seat"] == item["seat"] and a["attempt"] == item["attempt"]
                ),
                None,
            )
            if observation and item["queue"] is None
            else None
        )
        counts = projected["window"] if projected else {}
        reason = (
            "no_usage"
            if not own
            else (
                "multiple_events"
                if len(own) > 1
                else "aggregate" if own[0].aggregate else None
            )
        )
        transports = sorted({e.transport for e in own})
        row = {k: item[k] for k in ("slot", "queue", "run", "seat", "attempt")}
        row.update(
            {
                "model": next(iter(models)),
                "provider": next(iter(providers), UNKNOWN),
                "transport": (
                    transports[0] if len(transports) == 1 else transports or UNKNOWN
                ),
                "outcomes": [e.outcome for e in own],
                "manifest_outcome": projected["outcome"] if projected else UNKNOWN,
                "usage_events": len(own),
                "sources": {
                    "usage": [e["source"] for e in item["events"]],
                    "window": item["window"]["source"] if window else None,
                    "window_revisions": item["window"]["revisions"] if window else [],
                    "projection": counts.get("provenance", UNKNOWN),
                    "database": next(
                        (
                            db["dbname"]
                            for db in databases
                            if db["slot"] == item["slot"]
                            and (item["slot"], item["run"]) in inspections
                        ),
                        None,
                    ),
                },
                "estimate_vs_reported": _comparison(
                    counts.get("estimated_input_tokens"),
                    counts.get("reported_input_tokens"),
                    reason,
                ),
                "rendered_window_vs_reported": _comparison(
                    window.input_tokens if window else None,
                    _reported(own[0]) if len(own) == 1 else UNKNOWN,
                    reason,
                ),
            }
        )
        rows.append(row)
    raw_events = [item["record"] for item in events]
    duplicate_counts = Counter(event.model_dump_json() for event in raw_events)
    coverage = {
        "usage_events": len(events),
        "window_rows": snapshot["window_rows"],
        "distinct_windows": len(windows),
        "window_revisions_folded": snapshot["window_rows"] - len(windows),
        "attributed_attempts": len(rows),
        "attributed_usage_events": sum(row["usage_events"] for row in rows),
        "multiple_event_attempts": sum(row["usage_events"] > 1 for row in rows),
        "duplicate_usage_events": sum(n - 1 for n in duplicate_counts.values()),
        "aggregate_events": sum(e.aggregate for e in raw_events),
        "missing_run_events": sum(not e.run_id for e in raw_events),
        "test_events": sum(
            e.model == "TEST" or e.provider.lower() == "test" for e in raw_events
        ),
        "non_test_events": sum(
            e.model != "TEST" and e.provider.lower() != "test" for e in raw_events
        ),
        "event_inventory": [
            {"source": item["source"], "event": item["record"].model_dump()}
            for item in events
        ],
        "by_seat": dict(sorted(Counter(e.seat for e in raw_events).items())),
        "by_provider": dict(sorted(Counter(e.provider for e in raw_events).items())),
        "unattributed": unattributed,
        "unattributed_reasons": dict(
            sorted(Counter(f"{u['kind']}:{u['reason']}" for u in unattributed).items())
        ),
    }
    return {
        "schema_version": 1,
        "snapshot": snapshot["snapshot"],
        "databases": [
            {
                **db,
                "inspections": [
                    {k: v for k, v in item.items() if k != "inspection"}
                    for item in db["inspections"]
                ],
            }
            for db in databases
        ],
        "coverage": coverage,
        "attempts": rows,
        "estimate_vs_reported": _statistics(rows, "estimate_vs_reported"),
        "rendered_window_vs_reported": _statistics(rows, "rendered_window_vs_reported"),
        "concurrency": {
            "measurable_intervals": 0,
            "peak_concurrent_calls": UNKNOWN,
            "overlap_distribution": UNKNOWN,
            "reason": NO_DISPATCH,
            "missing_start_events": len(events),
            "missing_completion_events": 0,
            "windows_without_completion": sum(
                not m["events"] for m in members.values() if m["window"]
            )
            + sum(u["kind"] == "window" for u in unattributed),
            "ambiguous_identity_events": sum(u["kind"] == "usage" for u in unattributed)
            + sum(row["usage_events"] for row in rows if row["usage_events"] > 1),
            "aggregate_timing_events": sum(e.aggregate for e in raw_events),
        },
    }


def build_report(
    usage_dir: Path, slot_dbnames: Mapping[int, str], from_day: date, through_day: date
) -> dict[str, Any]:
    """Measure ledger members; database rows enrich but add no members."""
    snapshot = read_snapshot(usage_dir, from_day, through_day)
    return reconcile(snapshot, read_databases(slot_dbnames))


def main() -> None:
    """Print one JSON document from explicitly selected ledgers and databases."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage-dir", type=Path, required=True)
    parser.add_argument("--from-day", type=date.fromisoformat, required=True)
    parser.add_argument("--through-day", type=date.fromisoformat, required=True)
    parser.add_argument("--slot-db", action="append", default=[], metavar="N=dbname")
    args = parser.parse_args()
    slots = {}
    for value in args.slot_db:
        number, separator, dbname = value.partition("=")
        if (
            not separator
            or not number.isdecimal()
            or int(number) not in range(1, 6)
            or not dbname.strip()
        ):
            parser.error("--slot-db requires N=dbname with N in 1..5")
        slot = int(number)
        if slot in slots:
            parser.error(f"Duplicate --slot-db {slot}")
        slots[slot] = dbname
    report = build_report(args.usage_dir, slots, args.from_day, args.through_day)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
