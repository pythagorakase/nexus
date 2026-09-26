"""One derived, versioned observation of a generation turn.

The observation serves decisions about a turn's token economics: which seat and
attempt spend the prompt window and the provider's tokens, what the background
work the turn enqueued spends, what retries and repairs cost, and where the
wall time goes (a seat's budget, retry policy or model choice). It is read
through ``nexus inspect-turn --json`` or ``--summary``, states its freshness in
``read_at`` and ``ledger_days_read``, and is proven by
``tests/test_turn_observation.py``.

The observation joins one generation session's durable records on read and is
never stored; a replacement session (``replaced_by_session_id``) is observed on
its own.

Critical path: every attempt is keyed by ``(generation_session, seat,
attempt)`` and carries its rendered window from the attempt manifest (or, for
an attempt without a manifest, the prompt-window ledger), its validation codes,
and the tokens the provider reported in the usage ledger under the session's
run id. Observed phase transitions become spans.

Background: ``jobs.entries`` lists each job the inspection correlates with the
session, with its queue, id, state, whether it is ``terminal``, and its enqueue
and last-transition times. A job on a provider-backed queue
(``PROVIDER_JOB_SEATS``) also carries ``usage``: the events recorded under its
numeric job id as run id, in the inspected slot, with a seat of its queue, at
or after its enqueue, read from its own ledger days (enqueue through last
transition, or through ``read_at`` while open). Events an earlier job with the
same id recorded before a slot reset precede the enqueue and are not its own.
A job on any other queue has no ``usage`` key: it never calls a provider.
Background usage never joins ``attempts``.

Token counts are renderer or provider truth only: nothing is estimated and
nothing is priced (Decision 9, #858). Each section names its ``provenance``.
A value no source recorded reads ``"unknown"``; this includes list-typed fields
(``repair_codes``, ``rejection_codes``, ``outcomes``, ``seats``, and a
``block_tokens`` or ``influence_tokens`` mapping), so a JSON consumer must not
assume they are always arrays or objects. ``null`` means the source records
that the thing has not happened (no terminal outcome yet, no later phase) or
was not sent (no reasoning effort on the request).

Seats without a manifest or window record restart attempt numbers at 1 for each
request, so such a row can sum several provider calls that share one attempt
number; ``events`` counts them. A ``transport``, ``reasoning_effort``,
``max_output_tokens`` (and, for a job, ``model`` or ``provider``) is the value
every event recorded, or the sorted distinct values when events differ. Only a
conflicting model or provider on one attempt refuses the join.

``usage_totals`` has three sums. ``critical_path`` covers the attempts and
counts ``attempts_without_usage``; ``background`` covers the provider-backed
jobs and counts ``jobs``, ``jobs_open`` (not terminal, so still spending) and
``jobs_without_usage`` (terminal, yet no usage found); ``overall`` adds the
two. Each sums a field over the attempts or jobs that reported usage, and reads
``"unknown"`` when none did or one of them lacks the field; the counts say how
partial a sum is. A turn without provider-backed jobs has a background of 0
with a null ``provenance``. Providers count differently (OpenAI's
``input_tokens`` includes cached input; Anthropic's excludes cache reads and
writes), so a total across providers is not one comparable quantity; every
attempt and job names its provider and transport.

The join refuses, instead of guessing, rows from another session or an unread
day, conflicting models or providers on one attempt, a timestamp without a UTC
offset, phases recorded out of order, a background seat under the session's run
id (background workers record under their job id), and an event under a listed
job's id and slot whose seat no provider-backed queue records.

Schema version 1 has these top-level keys: ``schema_version``,
``generation_session``, ``read_at`` (UTC), ``ledger_days_read`` (every UTC day
read: the turn's, from its first observed phase through the later of its last
phase and ``read_at``, and each provider-backed job's), ``terminal_outcome``,
``wall_time``, ``phases``, ``attempts``, ``usage_totals`` and ``jobs``
(``total``, state counts ``by_queue``, and ``entries``).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Union

from nexus.telemetry.attempt_manifest import PROVIDER_JOB_SEATS, validation_metadata
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
# Job states after which a job makes no further provider calls.
TERMINAL_JOB_STATES = frozenset({"succeeded", "failed", "stale_rejected"})
# The queue each background seat belongs to.
BACKGROUND_SEAT_QUEUES = {
    seat: queue for queue, seats in PROVIDER_JOB_SEATS.items() for seat in seats
}

Count = Union[int, str]
AttemptKey = tuple[str, int]
JobKey = tuple[str, int]


def _utc(value: str) -> datetime:
    """Parse a recorded timestamp that must carry its UTC offset."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp has no UTC offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seconds(delta: timedelta) -> float:
    return round(delta.total_seconds(), 6)


def _days(first: date, last: date) -> list[str]:
    return [
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    ]


def _observed_phases(inspection: Mapping[str, Any]) -> list[tuple[str, datetime]]:
    return [(row["phase"], _utc(row["recorded_at"])) for row in inspection["phases"]]


def ledger_days(
    inspection: Mapping[str, Any], *, through: Optional[datetime] = None
) -> list[str]:
    """Return every UTC day from the turn's first observed phase onward.

    The days run through the last phase, or through ``through`` (the read time)
    when that is later. A turn without observed phases names no day.
    """
    moments = [moment for _, moment in _observed_phases(inspection)]
    if not moments:
        return []
    last = max(moments).date()
    if through is not None:
        last = max(last, through.astimezone(timezone.utc).date())
    return _days(min(moments).date(), last)


def _is_provider_job(job: Mapping[str, Any]) -> bool:
    return job["queue"] in PROVIDER_JOB_SEATS


def _job_key(job: Mapping[str, Any]) -> JobKey:
    return job["queue"], int(job["id"])


def job_ledger_days(
    inspection: Mapping[str, Any], *, read_at: datetime
) -> dict[JobKey, list[str]]:
    """Return the UTC days read for each provider-backed job's usage.

    A job's days run from its enqueue through its last transition, or through
    ``read_at`` while the job is open and may still call its provider.
    """
    days: dict[JobKey, list[str]] = {}
    for job in inspection["jobs"]:
        if not _is_provider_job(job):
            continue
        enqueued = _utc(job["created_at"])
        until = (
            _utc(job["updated_at"])
            if job["state"] in TERMINAL_JOB_STATES
            else read_at.astimezone(timezone.utc)
        )
        if until < enqueued:
            raise ValueError(
                f"Job {job['queue']} #{job['id']} was enqueued at {_iso(enqueued)}, "
                f"after its ledger read ends at {_iso(until)}"
            )
        days[_job_key(job)] = _days(enqueued.date(), until.date())
    return days


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


def read_job_ledgers(days: Mapping[JobKey, Sequence[str]]) -> list[UsageEvent]:
    """Read each job day once and keep the events recorded under a job's id."""
    run_ids = {str(job_id) for _, job_id in days}
    events: list[UsageEvent] = []
    for day in sorted({day for job_days in days.values() for day in job_days}):
        events.extend(
            UsageEvent.model_validate(event)
            for event in summarize_usage(day=day)["events"]
            if event["run_id"] in run_ids
        )
    return events


def observe_turn(
    inspection: Mapping[str, Any], *, slot: int, read_at: Optional[datetime] = None
) -> dict[str, Any]:
    """Read the turn's and its jobs' ledgers through the read and join them."""
    read_at = read_at or datetime.now(timezone.utc)
    days = ledger_days(inspection, through=read_at)
    events, windows = read_turn_ledgers(str(inspection["session"]["session_id"]), days)
    job_events = read_job_ledgers(job_ledger_days(inspection, read_at=read_at))
    return derive_turn_observation(
        inspection,
        events,
        windows,
        ledger_days=days,
        job_events=job_events,
        slot=slot,
        read_at=read_at,
    )


def derive_turn_observation(
    inspection: Mapping[str, Any],
    usage_events: Sequence[UsageEvent],
    windows: Sequence[PromptWindowRecord],
    *,
    ledger_days: Sequence[str],
    job_events: Sequence[UsageEvent] = (),
    slot: int,
    read_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Join one ``inspect_turn`` result with the ledger rows read for it.

    ``ledger_days`` names the UTC days whose ledgers supplied ``usage_events``
    and ``windows``; ``job_events`` are the rows read for the provider-backed
    jobs over the days ``job_ledger_days`` names for the same ``read_at``.
    ``slot`` is the inspected slot, which background events must name. Rows
    the join cannot attribute raise instead of joining.
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
        if event.seat in BACKGROUND_SEAT_QUEUES:
            raise ValueError(
                f"Usage event for background seat {event.seat} is recorded under "
                f"session {session_id}; background workers record under their "
                "job id, so it cannot be attributed to a job"
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
    job_days = job_ledger_days(inspection, read_at=read_at)
    entries = _job_entries(inspection["jobs"], job_events, job_days, slot=slot)
    phases, wall_time = _phase_spans(session_id, _observed_phases(inspection))
    critical_path = _critical_path_totals(attempts)
    background = _background_totals(entries)
    return {
        "schema_version": SCHEMA_VERSION,
        "generation_session": session_id,
        "read_at": _iso(read_at),
        "ledger_days_read": sorted(
            {*ledger_days, *(day for days in job_days.values() for day in days)}
        ),
        "terminal_outcome": inspection["session"]["terminal_outcome"],
        "wall_time": wall_time,
        "phases": phases,
        "attempts": attempts,
        "usage_totals": {
            "critical_path": critical_path,
            "background": background,
            "overall": _overall_totals(critical_path, background),
        },
        "jobs": _job_work(inspection["jobs"], entries),
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


def _profile(values: set[Any]) -> Any:
    """Return the value every event recorded, or the sorted distinct values.

    Request settings are not identity: calls that share an attempt number on a
    seat without a manifest, or one job's several calls, may differ.
    """
    if len(values) == 1:
        return next(iter(values))
    return sorted(values, key=lambda value: (value is None, value))


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
    result: dict[str, Any] = {
        "provenance": USAGE_LEDGER,
        "events": len(events),
        "provider": _agreed(
            session_id, key, "provider", {event.provider for event in events}
        ),
        "transport": _profile({event.transport for event in events}),
        "outcomes": [event.outcome for event in events],
    }
    for field in USAGE_TOKEN_FIELDS:
        result[field] = _sum_reported(getattr(event, field) for event in events)
    # The generation profile the request sent; null means none was sent.
    for field in ("reasoning_effort", "max_output_tokens"):
        result[field] = _profile({getattr(event, field) for event in events})
    return result


def _job_usage(events: list[UsageEvent]) -> dict[str, Any]:
    """Sum one job's provider calls; a job may call several seats or models."""
    if not events:
        return {
            "provenance": UNKNOWN,
            "events": 0,
            **dict.fromkeys(
                (
                    "seats",
                    "model",
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
    events = sorted(events, key=lambda event: _utc(event.ts))
    result: dict[str, Any] = {
        "provenance": USAGE_LEDGER,
        "events": len(events),
        "seats": sorted({event.seat for event in events}),
        "model": _profile({event.model for event in events}),
        "provider": _profile({event.provider for event in events}),
        "transport": _profile({event.transport for event in events}),
        "outcomes": [event.outcome for event in events],
    }
    for field in USAGE_TOKEN_FIELDS:
        result[field] = _sum_reported(getattr(event, field) for event in events)
    for field in ("reasoning_effort", "max_output_tokens"):
        result[field] = _profile({getattr(event, field) for event in events})
    return result


def _job_events(
    job: Mapping[str, Any],
    events: Sequence[UsageEvent],
    days: Sequence[str],
    *,
    slot: int,
) -> list[UsageEvent]:
    """Select the events one provider-backed job recorded under its identity."""
    enqueued = _utc(job["created_at"])
    own = []
    for event in events:
        if (
            event.run_id != str(job["id"])
            or event.slot != slot
            or event.quota_day not in days
            # An earlier job with this id, before a slot reset, spent these.
            or _utc(event.ts) < enqueued
        ):
            continue
        queue = BACKGROUND_SEAT_QUEUES.get(event.seat)
        if queue is None:
            raise ValueError(
                f"Usage event for seat {event.seat} under job run {event.run_id} "
                f"in slot {slot} belongs to no provider-backed queue"
            )
        # A job of another queue can share the numeric id; its seat tells.
        if queue == job["queue"]:
            own.append(event)
    return own


def _job_entries(
    jobs: Iterable[Mapping[str, Any]],
    events: Sequence[UsageEvent],
    days: Mapping[JobKey, Sequence[str]],
    *,
    slot: int,
) -> list[dict[str, Any]]:
    """Describe each correlated job; provider-backed ones carry their usage."""
    jobs = list(jobs)
    read_days = {day for job_days in days.values() for day in job_days}
    run_ids = {str(job["id"]) for job in jobs if _is_provider_job(job)}
    for event in events:
        if event.run_id not in run_ids:
            raise ValueError(
                f"Usage event belongs to run {event.run_id}, not a provider-backed "
                "job of this session"
            )
        if event.quota_day not in read_days:
            raise ValueError(
                f"Usage event from {event.quota_day} is outside the job ledger "
                f"days read: {sorted(read_days)}"
            )
    entries = []
    for job in sorted(jobs, key=_job_key):
        created_at, updated_at = job["created_at"], job["updated_at"]
        entry: dict[str, Any] = {
            "queue": job["queue"],
            "id": int(job["id"]),
            "state": job["state"],
            "terminal": job["state"] in TERMINAL_JOB_STATES,
            "created_at": None if created_at is None else _iso(_utc(created_at)),
            "updated_at": None if updated_at is None else _iso(_utc(updated_at)),
        }
        if _is_provider_job(job):
            job_days = list(days[_job_key(job)])
            entry["usage"] = {
                "run_id": str(job["id"]),
                "ledger_days": job_days,
                **_job_usage(_job_events(job, events, job_days, slot=slot)),
            }
        entries.append(entry)
    return entries


def _sum_totals(usages: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum each token field over the usage sections that reported usage."""
    reported = [usage for usage in usages if usage["provenance"] == USAGE_LEDGER]
    totals: dict[str, Any] = {
        "provenance": USAGE_LEDGER if reported else UNKNOWN,
        "events": sum(usage["events"] for usage in reported),
    }
    for field in USAGE_TOKEN_FIELDS:
        values = [usage[field] for usage in reported]
        totals[field] = sum(values) if reported and UNKNOWN not in values else UNKNOWN
    return totals


def _critical_path_totals(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    usages = [attempt["usage"] for attempt in attempts]
    return {
        **_sum_totals(usages),
        "attempts_without_usage": sum(
            usage["provenance"] == UNKNOWN for usage in usages
        ),
    }


def _background_totals(entries: list[dict[str, Any]]) -> dict[str, Any]:
    jobs = [entry for entry in entries if "usage" in entry]
    if jobs:
        totals = _sum_totals([job["usage"] for job in jobs])
    else:
        # No correlated job calls a provider, so background work spent nothing.
        totals = {
            "provenance": None,
            "events": 0,
            **dict.fromkeys(USAGE_TOKEN_FIELDS, 0),
        }
    return {
        **totals,
        "jobs": len(jobs),
        "jobs_open": sum(not job["terminal"] for job in jobs),
        "jobs_without_usage": sum(
            job["terminal"] and job["usage"]["provenance"] == UNKNOWN for job in jobs
        ),
    }


def _overall_totals(
    critical_path: Mapping[str, Any], background: Mapping[str, Any]
) -> dict[str, Any]:
    parts = (critical_path, background)
    totals: dict[str, Any] = {
        "provenance": (
            USAGE_LEDGER
            if any(part["provenance"] == USAGE_LEDGER for part in parts)
            else UNKNOWN
        ),
        "events": sum(part["events"] for part in parts),
    }
    for field in USAGE_TOKEN_FIELDS:
        values = [part[field] for part in parts]
        totals[field] = UNKNOWN if UNKNOWN in values else sum(values)
    return totals


def _phase_spans(
    session_id: str, observed: list[tuple[str, datetime]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spans = []
    for index, (phase, started) in enumerate(observed):
        ended = observed[index + 1][1] if index + 1 < len(observed) else None
        if ended is not None and ended < started:
            raise ValueError(
                f"Phase {observed[index + 1][0]} of {session_id} was recorded at "
                f"{_iso(ended)}, before the preceding phase {phase} at "
                f"{_iso(started)}"
            )
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


def _job_work(
    jobs: Iterable[Mapping[str, Any]], entries: list[dict[str, Any]]
) -> dict[str, Any]:
    by_queue: dict[str, Counter[str]] = {}
    for job in jobs:
        by_queue.setdefault(job["queue"], Counter())[job["state"]] += 1
    return {
        "total": len(entries),
        "by_queue": {
            queue: dict(sorted(states.items()))
            for queue, states in sorted(by_queue.items())
        },
        "entries": entries,
    }


def _tokens(value: Any) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value)


def _duration(value: Any) -> str:
    return f"{value:.3f}s" if isinstance(value, float) else str(value)


def _setting(value: Any) -> str:
    """Render a request setting; distinct values join and unsent reads ``-``."""
    if isinstance(value, list):
        return "/".join(_setting(item) for item in value)
    return "-" if value is None else _tokens(value)


def _usage_line(usage: Mapping[str, Any]) -> str:
    """Render one attempt's or job's usage; unrecorded usage reads unknown."""
    if usage["provenance"] == UNKNOWN:
        return f"  usage {UNKNOWN}"
    return (
        f"  usage in {_tokens(usage['input_tokens'])} · cached "
        f"{_tokens(usage['cached_input_tokens'])} · cache write "
        f"{_tokens(usage['cache_creation_tokens'])} · out "
        f"{_tokens(usage['output_tokens'])} · reasoning "
        f"{_tokens(usage['reasoning_tokens'])} · effort "
        f"{_setting(usage['reasoning_effort'])} · max out "
        f"{_setting(usage['max_output_tokens'])} "
        f"[{usage['provenance']} ×{usage['events']}]"
    )


def _attempt_lines(attempt: Mapping[str, Any]) -> list[str]:
    """Render one attempt; a section no source recorded collapses to unknown."""
    window, validation = attempt["window"], attempt["validation"]
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
    lines.append(_usage_line(attempt["usage"]))
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


def _job_lines(entry: Mapping[str, Any]) -> list[str]:
    """Render one provider-backed job: its model and state, then its usage."""
    usage = entry["usage"]
    model = "" if usage["model"] == UNKNOWN else f" {_setting(usage['model'])}"
    return [
        f"{entry['queue']} #{entry['id']}{model} · {entry['state']}",
        _usage_line(usage),
    ]


def _totals_line(label: str, totals: Mapping[str, Any]) -> str:
    return (
        f"{label} in {_tokens(totals['input_tokens'])} · cached "
        f"{_tokens(totals['cached_input_tokens'])} · cache write "
        f"{_tokens(totals['cache_creation_tokens'])} · out "
        f"{_tokens(totals['output_tokens'])} · reasoning "
        f"{_tokens(totals['reasoning_tokens'])} · events {totals['events']}"
    )


def _ledger_days(days: Sequence[str]) -> str:
    """Name the days read: a contiguous run by its ends, otherwise each day."""
    if not days:
        return "none"
    first, last = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    if len(days) == 1:
        return days[0]
    if list(days) == _days(first, last):
        return f"{days[0]} to {days[-1]}"
    return ", ".join(days)


def format_turn_summary(observation: Mapping[str, Any]) -> str:
    """Render the observation as a few concise lines of text, in tokens."""
    lines = [
        f"Turn {observation['generation_session']} "
        f"({observation['terminal_outcome'] or 'open'}) · read "
        f"{observation['read_at']} · ledger "
        f"{_ledger_days(observation['ledger_days_read'])} · "
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
    critical_path, background = totals["critical_path"], totals["background"]
    lines.append(
        _totals_line("Critical path", critical_path)
        + f" · attempts without usage {critical_path['attempts_without_usage']}"
    )
    jobs = observation["jobs"]
    for entry in jobs["entries"]:
        if "usage" in entry:
            lines.extend(_job_lines(entry))
    if background["jobs"]:
        lines.append(
            _totals_line("Background", background)
            + f" · jobs {background['jobs']} · open {background['jobs_open']} · "
            f"without usage {background['jobs_without_usage']}"
        )
        lines.append(_totals_line("Overall", totals["overall"]))
    else:
        lines.append("Background none")
    lines.append(
        f"Jobs {jobs['total']}"
        + "".join(
            f" · {queue} "
            + ", ".join(f"{state} {count}" for state, count in states.items())
            for queue, states in jobs["by_queue"].items()
        )
    )
    return "\n".join(lines)
