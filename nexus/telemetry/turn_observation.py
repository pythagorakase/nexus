"""One derived, versioned observation of a generation turn.

The observation joins a turn's durable records on read and is never stored.
Every attempt is keyed by ``(generation_session, seat, attempt)`` and carries
its rendered window from the attempt manifest (or, for an attempt without a
manifest, the prompt-window ledger), its validation codes, and the tokens the
provider reported in the usage ledger. Observed phase transitions become spans,
and correlated job work is counted by queue and state.

Token counts are renderer or provider truth only: nothing is estimated and
nothing is priced (Decision 9, #858). Each section names its ``provenance``.
A value no source recorded reads ``"unknown"``; ``null`` means the source
records that the thing has not happened (no terminal outcome yet, no later
phase) or was not sent (no reasoning effort on the request).

Schema version 1 has these top-level keys: ``schema_version``,
``generation_session``, ``read_at`` (UTC), ``ledger_days_read`` (every UTC day
spanned by the observed phases), ``terminal_outcome``, ``wall_time``,
``phases``, ``attempts``, ``usage_totals`` and ``jobs``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

from nexus.telemetry.attempt_manifest import validation_metadata
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.usage import UsageEvent, read_prompt_windows, summarize_usage

SCHEMA_VERSION = 1
UNKNOWN = "unknown"
MANIFEST = "attempt_manifest"
WINDOW_LEDGER = "prompt_window_ledger"
USAGE_LEDGER = "provider_usage_ledger"
USAGE_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_creation_tokens",
    "reasoning_tokens",
)

Count = Union[int, str]
AttemptKey = tuple[str, int]


def _utc(value: str) -> datetime:
    """Parse a recorded timestamp that must carry its UTC offset."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Phase timestamp has no UTC offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seconds(delta: timedelta) -> float:
    return round(delta.total_seconds(), 6)


def _observed_phases(inspection: Mapping[str, Any]) -> list[tuple[str, datetime]]:
    return [(row["phase"], _utc(row["recorded_at"])) for row in inspection["phases"]]


def ledger_days(inspection: Mapping[str, Any]) -> list[str]:
    """Return every UTC day spanned by the turn's observed phase transitions."""
    moments = [moment for _, moment in _observed_phases(inspection)]
    if not moments:
        return []
    first, last = min(moments).date(), max(moments).date()
    return [
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    ]


def read_turn_ledgers(
    session: str, days: Sequence[str]
) -> tuple[list[UsageEvent], list[PromptWindowRecord]]:
    """Read the session's usage events and latest window records for each day."""
    events: list[UsageEvent] = []
    windows: dict[AttemptKey, PromptWindowRecord] = {}
    for day in days:
        summary = summarize_usage(day=day, run_id=session)
        events.extend(UsageEvent.model_validate(event) for event in summary["events"])
        # Revised snapshots of one attempt are appended; the latest one wins.
        for record in read_prompt_windows(session, day):
            windows[(record.seat, record.attempt)] = record
    return events, list(windows.values())


def observe_turn(
    inspection: Mapping[str, Any], *, read_at: Optional[datetime] = None
) -> dict[str, Any]:
    """Read the ledgers for every day the turn spans and derive its observation."""
    read_at = read_at or datetime.now(timezone.utc)
    days = ledger_days(inspection)
    events, windows = read_turn_ledgers(str(inspection["session"]["session_id"]), days)
    return derive_turn_observation(
        inspection, events, windows, ledger_days=days, read_at=read_at
    )


def derive_turn_observation(
    inspection: Mapping[str, Any],
    usage_events: Sequence[UsageEvent],
    windows: Sequence[PromptWindowRecord],
    *,
    ledger_days: Sequence[str],
    read_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Join one ``inspect_turn`` result with the ledger rows read for it.

    ``ledger_days`` names the UTC days whose ledgers supplied ``usage_events``
    and ``windows``. Rows from another session or another day, or sources that
    disagree on an attempt's model or request, raise instead of joining.
    """
    read_at = read_at or datetime.now(timezone.utc)
    session_id = str(inspection["session"]["session_id"])
    manifests: dict[AttemptKey, Mapping[str, Any]] = {}
    for row in inspection["manifests"]:
        if str(row["generation_session_id"]) != session_id:
            raise ValueError(
                f"Manifest belongs to session {row['generation_session_id']}, "
                f"not {session_id}"
            )
        manifests[(row["seat"], int(row["attempt"]))] = row
    window_records: dict[AttemptKey, PromptWindowRecord] = {}
    for record in windows:
        if record.generation_session != session_id:
            raise ValueError(
                f"Window record belongs to session {record.generation_session}, "
                f"not {session_id}"
            )
        key = (record.seat, record.attempt)
        if key in window_records:
            raise ValueError(f"Duplicate window record for {key} in {session_id}")
        window_records[key] = record
    usage: dict[AttemptKey, list[UsageEvent]] = {}
    for event in usage_events:
        if event.run_id != session_id:
            raise ValueError(
                f"Usage event belongs to run {event.run_id}, not {session_id}"
            )
        if event.quota_day not in ledger_days:
            raise ValueError(
                f"Usage event from {event.quota_day} is outside the ledger days "
                f"read: {list(ledger_days)}"
            )
        usage.setdefault((event.seat, event.attempt), []).append(event)
    attempts = [
        _attempt(
            session_id,
            key,
            manifests.get(key),
            window_records.get(key),
            usage.get(key, []),
        )
        for key in sorted(set(manifests) | set(window_records) | set(usage))
    ]
    phases, wall_time = _phase_spans(_observed_phases(inspection))
    return {
        "schema_version": SCHEMA_VERSION,
        "generation_session": session_id,
        "read_at": _iso(read_at),
        "ledger_days_read": list(ledger_days),
        "terminal_outcome": inspection["session"]["terminal_outcome"],
        "wall_time": wall_time,
        "phases": phases,
        "attempts": attempts,
        "usage_totals": _usage_totals(attempts),
        "jobs": _job_work(inspection["jobs"]),
    }


def _attempt(
    session_id: str,
    key: AttemptKey,
    manifest: Optional[Mapping[str, Any]],
    window: Optional[PromptWindowRecord],
    events: list[UsageEvent],
) -> dict[str, Any]:
    seat, attempt = key
    models = {event.model for event in events}
    if manifest is not None:
        models.add(manifest["model_id"])
    if window is not None:
        models.add(window.model)
    if len(models) != 1:
        raise ValueError(
            f"Attempt {seat} #{attempt} of {session_id} names conflicting models: "
            f"{sorted(models)}"
        )
    return {
        "generation_session": session_id,
        "seat": seat,
        "attempt": attempt,
        "model": models.pop(),
        "outcome": UNKNOWN if manifest is None else manifest["outcome"],
        "provider_outcome": (
            UNKNOWN if manifest is None else manifest["provider_outcome"]
        ),
        "window": _window(manifest, window),
        "validation": _validation(manifest, window),
        "usage": _usage(session_id, key, events),
    }


def _window(
    manifest: Optional[Mapping[str, Any]], record: Optional[PromptWindowRecord]
) -> dict[str, Any]:
    if manifest is not None:
        provenance, values = MANIFEST, manifest["window_record"]
    elif record is not None:
        provenance, values = WINDOW_LEDGER, record.model_dump()
    else:
        return {
            "provenance": UNKNOWN,
            **dict.fromkeys(
                (
                    "input_tokens",
                    "effective_ceiling",
                    "policy_headroom",
                    "headroom",
                    "block_tokens_total",
                    "block_tokens",
                    "influence_tokens",
                ),
                UNKNOWN,
            ),
        }
    block_tokens = dict(values["block_tokens"])
    # Records written before influence roles were declared (#744) carry none.
    influence_tokens = values.get("influence_tokens") or UNKNOWN
    return {
        "provenance": provenance,
        "input_tokens": values["input_tokens"],
        "effective_ceiling": values["effective_ceiling"],
        "policy_headroom": values["policy_headroom"],
        "headroom": values["headroom"],
        "block_tokens_total": sum(block_tokens.values()),
        "block_tokens": block_tokens,
        "influence_tokens": influence_tokens,
    }


def _validation(
    manifest: Optional[Mapping[str, Any]], record: Optional[PromptWindowRecord]
) -> dict[str, Any]:
    if manifest is not None:
        provenance, metadata = MANIFEST, list(manifest["validation"])
    elif record is not None:
        # Reduce ledger notes exactly as the manifest does; never copy free text.
        provenance = WINDOW_LEDGER
        metadata = validation_metadata(record.validation_notes)
    else:
        return {
            "provenance": UNKNOWN,
            **dict.fromkeys(
                ("notes", "repairs", "repair_codes", "rejections", "rejection_codes"),
                UNKNOWN,
            ),
        }
    repair_codes = [item["repair"] for item in metadata if "repair" in item]
    rejection_codes = [item["rejection"] for item in metadata if "rejection" in item]
    return {
        "provenance": provenance,
        "notes": len(metadata),
        "repairs": len(repair_codes),
        "repair_codes": repair_codes,
        "rejections": len(rejection_codes),
        "rejection_codes": rejection_codes,
    }


def _sum_reported(values: Iterable[Optional[int]]) -> Count:
    """Sum a token field only when every contributing event reported it."""
    total = 0
    for value in values:
        if value is None:
            return UNKNOWN
        total += value
    return total


def _agreed(session_id: str, key: AttemptKey, field: str, values: set[Any]) -> Any:
    if len(values) != 1:
        raise ValueError(
            f"Attempt {key[0]} #{key[1]} of {session_id} records conflicting "
            f"{field} values: {sorted(map(str, values))}"
        )
    return next(iter(values))


def _usage(
    session_id: str, key: AttemptKey, events: list[UsageEvent]
) -> dict[str, Any]:
    if not events:
        return {
            "provenance": UNKNOWN,
            "events": 0,
            **dict.fromkeys(
                (
                    "provider",
                    "transport",
                    "outcomes",
                    *USAGE_TOKEN_FIELDS,
                    "reasoning_effort",
                    "max_output_tokens",
                ),
                UNKNOWN,
            ),
        }
    result: dict[str, Any] = {"provenance": USAGE_LEDGER, "events": len(events)}
    for field in ("provider", "transport"):
        result[field] = _agreed(
            session_id, key, field, {getattr(event, field) for event in events}
        )
    result["outcomes"] = [event.outcome for event in events]
    for field in USAGE_TOKEN_FIELDS:
        result[field] = _sum_reported(getattr(event, field) for event in events)
    # The generation profile the request sent; null means none was sent.
    for field in ("reasoning_effort", "max_output_tokens"):
        result[field] = _agreed(
            session_id, key, field, {getattr(event, field) for event in events}
        )
    return result


def _usage_totals(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    reported = [
        attempt["usage"]
        for attempt in attempts
        if attempt["usage"]["provenance"] == USAGE_LEDGER
    ]
    totals: dict[str, Any] = {
        "provenance": USAGE_LEDGER if reported else UNKNOWN,
        "events": sum(usage["events"] for usage in reported),
        "attempts_without_usage": len(attempts) - len(reported),
    }
    for field in USAGE_TOKEN_FIELDS:
        values = [usage[field] for usage in reported]
        totals[field] = sum(values) if reported and UNKNOWN not in values else UNKNOWN
    return totals


def _phase_spans(
    observed: list[tuple[str, datetime]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spans = []
    for index, (phase, started) in enumerate(observed):
        ended = observed[index + 1][1] if index + 1 < len(observed) else None
        spans.append(
            {
                "phase": phase,
                "started_at": _iso(started),
                "ended_at": None if ended is None else _iso(ended),
                "seconds": UNKNOWN if ended is None else _seconds(ended - started),
            }
        )
    if len(observed) < 2:
        wall_time: dict[str, Any] = dict.fromkeys(
            ("started_at", "ended_at", "seconds"), UNKNOWN
        )
    else:
        started, ended = observed[0][1], observed[-1][1]
        wall_time = {
            "started_at": _iso(started),
            "ended_at": _iso(ended),
            "seconds": _seconds(ended - started),
        }
    return spans, wall_time


def _job_work(jobs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    by_queue: dict[str, Counter[str]] = {}
    total = 0
    for job in jobs:
        by_queue.setdefault(job["queue"], Counter())[job["state"]] += 1
        total += 1
    return {
        "total": total,
        "by_queue": {
            queue: dict(sorted(states.items()))
            for queue, states in sorted(by_queue.items())
        },
    }


def _tokens(value: Any) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value)


def _duration(value: Any) -> str:
    return f"{value:.3f}s" if isinstance(value, float) else str(value)


def _attempt_lines(attempt: Mapping[str, Any]) -> list[str]:
    """Render one attempt; a section no source recorded collapses to unknown."""
    window, usage = attempt["window"], attempt["usage"]
    validation = attempt["validation"]
    lines = [
        f"{attempt['seat']} #{attempt['attempt']} {attempt['model']} · "
        f"outcome {attempt['outcome'] or 'open'} · provider "
        f"{attempt['provider_outcome'] or 'open'}"
    ]
    if window["provenance"] == UNKNOWN:
        lines.append(f"  window {UNKNOWN}")
    else:
        lines.append(
            f"  window {_tokens(window['input_tokens'])} / "
            f"{_tokens(window['effective_ceiling'])} · headroom "
            f"{_tokens(window['headroom'])} [{window['provenance']}]"
        )
        influence = window["influence_tokens"]
        if isinstance(influence, dict):
            lines.append(
                "  roles "
                + " · ".join(
                    f"{role} {_tokens(tokens)}" for role, tokens in influence.items()
                )
            )
    if usage["provenance"] == UNKNOWN:
        lines.append(f"  usage {UNKNOWN}")
    else:
        lines.append(
            f"  usage in {_tokens(usage['input_tokens'])} · cached "
            f"{_tokens(usage['cached_input_tokens'])} · cache write "
            f"{_tokens(usage['cache_creation_tokens'])} · out "
            f"{_tokens(usage['output_tokens'])} · reasoning "
            f"{_tokens(usage['reasoning_tokens'])} · effort "
            f"{usage['reasoning_effort'] or '-'} · max out "
            f"{_tokens(usage['max_output_tokens'] or '-')} "
            f"[{usage['provenance']} ×{usage['events']}]"
        )
    if validation["provenance"] == UNKNOWN:
        lines.append(f"  validation {UNKNOWN}")
    else:
        codes = [*validation["repair_codes"], *validation["rejection_codes"]]
        lines.append(
            f"  validation repairs {validation['repairs']} · rejections "
            f"{validation['rejections']}"
            + (f" ({', '.join(codes)})" if codes else "")
            + f" [{validation['provenance']}]"
        )
    return lines


def format_turn_summary(observation: Mapping[str, Any]) -> str:
    """Render the observation as a few concise lines of text, in tokens."""
    days = ", ".join(observation["ledger_days_read"]) or "none"
    lines = [
        f"Turn {observation['generation_session']} "
        f"({observation['terminal_outcome'] or 'open'}) · read "
        f"{observation['read_at']} · ledger {days} · "
        f"schema v{observation['schema_version']}",
        f"Wall {_duration(observation['wall_time']['seconds'])}: "
        + (
            " → ".join(
                span["phase"]
                + ("" if span["ended_at"] is None else f" {_duration(span['seconds'])}")
                for span in observation["phases"]
            )
            or "no phases observed"
        ),
    ]
    for attempt in observation["attempts"]:
        lines.extend(_attempt_lines(attempt))
    totals = observation["usage_totals"]
    lines.append(
        f"Usage in {_tokens(totals['input_tokens'])} · cached "
        f"{_tokens(totals['cached_input_tokens'])} · cache write "
        f"{_tokens(totals['cache_creation_tokens'])} · out "
        f"{_tokens(totals['output_tokens'])} · reasoning "
        f"{_tokens(totals['reasoning_tokens'])} · events {totals['events']} · "
        f"attempts without usage {totals['attempts_without_usage']}"
    )
    jobs = observation["jobs"]
    lines.append(
        f"Jobs {jobs['total']}"
        + "".join(
            f" · {queue} "
            + ", ".join(f"{state} {count}" for state, count in states.items())
            for queue, states in jobs["by_queue"].items()
        )
    )
    return "\n".join(lines)
