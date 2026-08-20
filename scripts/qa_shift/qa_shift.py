#!/usr/bin/env python3
"""Prepare and enforce the mechanical boundaries of a NEXUS QA shift.

The native Codex Scheduled task is the operator. This utility does not launch
another Codex process. It creates a per-run archive and isolated runtime
configuration, then wraps ``nexus usage --json`` with a fail-closed guard.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tomllib
from typing import Any, Callable, Mapping, Sequence, cast

import tomlkit

from nexus.api.db_pool import get_connection
from nexus.api.slot_utils import slot_dbname


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = Path(__file__).with_name("qa_shift.toml")
STATE_FILE = "shift_state.json"
CHECKS_FILE = "usage_checks.jsonl"
STOP_EXIT_CODE = 2
PENDING_EXIT_CODE = 3


class ShiftError(RuntimeError):
    """Raised when the QA shift cannot continue safely."""


class CheckMode(str, Enum):
    """Internal usage-check modes exposed through dedicated CLI flags."""

    PRE_CALL = "pre_call"
    POST_CALL = "post_call"
    VALIDATION_ONLY = "validation_only"


@dataclass(frozen=True)
class ValidationEvidence:
    """Filesystem-independent metadata proving a local validation rejection."""

    probe_command: str
    rejection_status: int
    rejection_evidence: str
    rejection_evidence_sha256: str
    rejection_evidence_excerpt: str


@dataclass(frozen=True)
class ShiftConfig:
    """Validated, durable QA shift settings."""

    slot: int
    gateway_port: int
    target_model: str
    issue_budget: int
    minimum_probe_families: int
    dry_well_families: int
    wall_clock_minutes: int
    archive_root: Path
    daily_token_limit: int
    reserve_tokens: int

    @property
    def token_fence(self) -> int:
        """Return the daily total at which generation must stop."""

        return self.daily_token_limit - self.reserve_tokens


UsageReader = Callable[[Path, str | None], dict[str, Any]]
JobsReader = Callable[[Path, int], dict[str, Any]]
BleedUptakeReader = Callable[[Path, int], dict[str, Any]]


def _required_int(table: Mapping[str, Any], key: str) -> int:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ShiftError(f"{key} must be an integer")
    return value


def _required_str(table: Mapping[str, Any], key: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ShiftError(f"{key} must be a non-empty string")
    return value


def load_shift_config(path: Path = DEFAULT_CONFIG_PATH) -> ShiftConfig:
    """Load and validate the tracked QA shift configuration."""

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ShiftError(f"Cannot read QA shift config {path}: {exc}") from exc

    shift = raw.get("shift")
    usage = raw.get("usage")
    if not isinstance(shift, dict) or not isinstance(usage, dict):
        raise ShiftError("qa_shift.toml requires [shift] and [usage] tables")

    config = ShiftConfig(
        slot=_required_int(shift, "slot"),
        gateway_port=_required_int(shift, "gateway_port"),
        target_model=_required_str(shift, "target_model"),
        issue_budget=_required_int(shift, "issue_budget"),
        minimum_probe_families=_required_int(shift, "minimum_probe_families"),
        dry_well_families=_required_int(shift, "dry_well_families"),
        wall_clock_minutes=_required_int(shift, "wall_clock_minutes"),
        archive_root=Path(_required_str(shift, "archive_root")),
        daily_token_limit=_required_int(usage, "daily_token_limit"),
        reserve_tokens=_required_int(usage, "reserve_tokens"),
    )

    if config.slot not in range(2, 6):
        raise ShiftError("slot must be one of the disposable slots 2-5")
    if not 1024 <= config.gateway_port <= 65535:
        raise ShiftError("gateway_port must be between 1024 and 65535")
    if config.gateway_port == 8002:
        raise ShiftError("gateway_port 8002 is the normal runtime, not a QA lane")
    for field_name in (
        "issue_budget",
        "minimum_probe_families",
        "dry_well_families",
        "wall_clock_minutes",
        "daily_token_limit",
        "reserve_tokens",
    ):
        if getattr(config, field_name) <= 0:
            raise ShiftError(f"{field_name} must be positive")
    if config.reserve_tokens >= config.daily_token_limit:
        raise ShiftError("reserve_tokens must be smaller than daily_token_limit")
    return config


def _config_payload(config: ShiftConfig) -> dict[str, Any]:
    payload = asdict(config)
    payload["archive_root"] = str(config.archive_root)
    payload["token_fence"] = config.token_fence
    return payload


def _read_usage(repo_root: Path, day: str | None = None) -> dict[str, Any]:
    """Read exact provider-reported usage through the public NEXUS CLI."""

    command = ["nexus", "usage", "--json"]
    if day is not None:
        command.extend(["--day", day])
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ShiftError(
            "The nexus executable is unavailable; run this utility with "
            "`poetry run python`."
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ShiftError(f"`nexus usage --json` failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ShiftError("`nexus usage --json` returned invalid JSON") from exc
    if payload.get("success") is not True:
        raise ShiftError(f"`nexus usage --json` reported failure: {payload}")
    return payload


def _read_jobs(repo_root: Path, slot: int) -> dict[str, Any]:
    """Read durable maturation jobs through the public NEXUS CLI."""

    command = ["nexus", "jobs", "--slot", str(slot), "--json"]
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ShiftError(
            "The nexus executable is unavailable; run this utility with "
            "`poetry run python`."
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ShiftError(f"`nexus jobs --slot {slot} --json` failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ShiftError(
            f"`nexus jobs --slot {slot} --json` returned invalid JSON"
        ) from exc
    if payload.get("success") is not True:
        raise ShiftError(
            f"`nexus jobs --slot {slot} --json` reported failure: {payload}"
        )
    return payload


def _read_bleed_uptake(
    _repo_root: Path,
    slot: int,
) -> dict[str, Any]:
    """Read cumulative Bleed offer and uptake counters for one QA slot."""

    with get_connection(slot_dbname(slot), dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(sum(offer_count), 0)::bigint AS offered_count,
                    COALESCE(sum(use_count), 0)::bigint AS used_count
                FROM orrery_resolutions
                """,
            )
            row = cur.fetchone()
    if row is None:
        raise ShiftError("Bleed uptake query returned no summary row")
    return dict(row)


def _bleed_uptake_summary(
    payload: Mapping[str, Any],
    *,
    baseline_offered_count: int,
    baseline_used_count: int,
    started_at: datetime,
    ended_at: datetime,
) -> dict[str, Any]:
    """Validate and annotate one shift-window Bleed uptake summary."""

    offered_count, used_count = _bleed_uptake_counts(payload)
    if offered_count < baseline_offered_count or used_count < baseline_used_count:
        raise ShiftError("Bleed uptake counters decreased during the shift")
    shift_offered_count = offered_count - baseline_offered_count
    shift_used_count = used_count - baseline_used_count
    uptake_rate_percent = (
        round(shift_used_count * 100 / shift_offered_count, 4)
        if shift_offered_count
        else 0.0
    )
    return {
        "started_at": _utc_text(started_at),
        "ended_at": _utc_text(ended_at),
        "offered_count": shift_offered_count,
        "used_count": shift_used_count,
        "uptake_rate_percent": uptake_rate_percent,
    }


def _bleed_uptake_counts(payload: Mapping[str, Any]) -> tuple[int, int]:
    """Validate cumulative Bleed counters from the QA slot."""

    offered_count = payload.get("offered_count")
    used_count = payload.get("used_count")
    if (
        isinstance(offered_count, bool)
        or not isinstance(offered_count, int)
        or offered_count < 0
    ):
        raise ShiftError("Bleed uptake offered_count must be a non-negative integer")
    if (
        isinstance(used_count, bool)
        or not isinstance(used_count, int)
        or used_count < 0
    ):
        raise ShiftError("Bleed uptake used_count must be a non-negative integer")
    return offered_count, used_count


def _usage_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise ShiftError("Usage payload has no object at .usage")
    openai = usage.get("openai_day_total")
    events = usage.get("events")
    day = usage.get("day")
    if not isinstance(openai, dict):
        raise ShiftError("Usage payload has no .usage.openai_day_total object")
    if not isinstance(events, list):
        raise ShiftError("Usage payload has no .usage.events list")
    if not isinstance(day, str):
        raise ShiftError("Usage payload has no string at .usage.day")

    total = openai.get("total_tokens")
    unknown = openai.get("unknown_usage_events")
    if isinstance(total, bool) or not isinstance(total, int):
        raise ShiftError("OpenAI total_tokens is not an integer")
    if isinstance(unknown, bool) or not isinstance(unknown, int):
        raise ShiftError("OpenAI unknown_usage_events is not an integer")
    return {
        "day": day,
        "total": total,
        "unknown": unknown,
        "events": events,
    }


def _jobs_snapshot(payload: Mapping[str, Any], *, slot: int) -> dict[str, Any]:
    """Validate one public maturation-jobs payload for the configured slot."""

    payload_slot = payload.get("slot")
    if isinstance(payload_slot, bool) or not isinstance(payload_slot, int):
        raise ShiftError("Jobs payload has no integer at .slot")
    if payload_slot != slot:
        raise ShiftError(
            f"Jobs payload returned the wrong slot ({payload_slot} != {slot})"
        )
    raw_counts = payload.get("counts")
    raw_jobs = payload.get("non_terminal_jobs")
    if not isinstance(raw_counts, dict):
        raise ShiftError("Jobs payload has no object at .counts")
    if not isinstance(raw_jobs, list):
        raise ShiftError("Jobs payload has no list at .non_terminal_jobs")

    counts: dict[str, int] = {}
    for state in ("queued", "leased", "succeeded", "failed"):
        value = raw_counts.get(state)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ShiftError(f"Jobs payload count for {state!r} is invalid")
        counts[state] = value

    jobs: list[dict[str, Any]] = []
    required_fields = (
        "id",
        "state",
        "entity_kind",
        "entity_name",
        "requesting_chunk_id",
        "attempts",
        "available_at",
        "lease_until",
    )
    for index, raw_job in enumerate(raw_jobs):
        if not isinstance(raw_job, dict):
            raise ShiftError(f"Jobs payload row {index} is not an object")
        missing = [field for field in required_fields if field not in raw_job]
        if missing:
            raise ShiftError(f"Jobs payload row {index} is missing fields: {missing}")
        if raw_job["state"] not in ("queued", "leased"):
            raise ShiftError(
                f"Jobs payload row {index} has terminal state " f"{raw_job['state']!r}"
            )
        jobs.append({field: raw_job[field] for field in required_fields})
    if counts["queued"] + counts["leased"] != len(jobs):
        raise ShiftError(
            "Jobs payload non-terminal counts do not match its diagnostic list"
        )
    return {"slot": slot, "counts": counts, "non_terminal_jobs": jobs}


def _rejection_ledger(
    *,
    state: Mapping[str, Any],
    usage: Mapping[str, Any],
    shift_openai_total: int,
) -> dict[str, Any]:
    """Summarize current-run rejected attempts from the exact usage delta."""

    baseline_event_count = int(state["baseline_event_count"])
    events = usage["events"]
    if len(events) < baseline_event_count:
        raise ShiftError(
            "Final usage event count is smaller than the shift baseline; "
            "the rejection ledger cannot be trusted."
        )

    current_events = [
        event for event in events[baseline_event_count:] if isinstance(event, dict)
    ]
    slot = int(state["config"]["slot"])
    qa_events = [event for event in current_events if event.get("slot") == slot]
    rejected_events = [
        event for event in qa_events if event.get("outcome") == "rejected_validation"
    ]

    rejection_rows: list[dict[str, Any]] = []
    by_seat: dict[str, dict[str, Any]] = {}
    rejected_tokens = 0
    unknown_token_events = 0
    for event in rejected_events:
        raw_tokens = event.get("total_tokens")
        tokens = (
            raw_tokens
            if isinstance(raw_tokens, int) and not isinstance(raw_tokens, bool)
            else None
        )
        if tokens is None:
            unknown_token_events += 1
        else:
            rejected_tokens += tokens

        seat = str(event.get("seat") or "unknown")
        seat_summary = by_seat.setdefault(
            seat,
            {"attempts": 0, "tokens": 0, "unknown_token_events": 0},
        )
        seat_summary["attempts"] += 1
        if tokens is None:
            seat_summary["unknown_token_events"] += 1
        else:
            seat_summary["tokens"] += tokens

        rejection_rows.append(
            {
                key: event.get(key)
                for key in (
                    "ts",
                    "request_id",
                    "run_id",
                    "seat",
                    "provider",
                    "model",
                    "attempt",
                    "total_tokens",
                )
            }
        )

    exact_rejected_tokens: int | None = (
        rejected_tokens if unknown_token_events == 0 else None
    )
    unexpected_rejection_providers = sorted(
        {
            str(event.get("provider") or "unknown")
            for event in rejected_events
            if event.get("provider") != "openai"
        }
    )
    percent_unavailable_reasons: list[str] = []
    if exact_rejected_tokens is None:
        percent_unavailable_reasons.append("unknown_rejected_attempt_tokens")
    if int(usage["unknown"]) > 0:
        percent_unavailable_reasons.append("unknown_openai_usage")
    if unexpected_rejection_providers:
        percent_unavailable_reasons.append("unexpected_rejection_provider")
    if (
        exact_rejected_tokens is not None
        and exact_rejected_tokens > 0
        and shift_openai_total == 0
    ):
        percent_unavailable_reasons.append("zero_openai_denominator")

    repair_tax_percent: float | None
    if percent_unavailable_reasons:
        repair_tax_percent = None
    elif exact_rejected_tokens is None:
        raise AssertionError("exact token total missing without an unavailable reason")
    elif shift_openai_total == 0:
        repair_tax_percent = 0.0
    else:
        repair_tax_percent = round(
            exact_rejected_tokens * 100 / shift_openai_total,
            4,
        )

    return {
        "quota_day": usage["day"],
        "baseline_event_count": baseline_event_count,
        "final_event_count": len(events),
        "current_run_events": len(current_events),
        "qa_slot": slot,
        "qa_events": len(qa_events),
        "rejected_attempts": len(rejected_events),
        "rejected_tokens": exact_rejected_tokens,
        "unknown_rejected_token_events": unknown_token_events,
        "repair_tax_percent_of_shift": repair_tax_percent,
        "repair_tax_percent_unavailable_reasons": percent_unavailable_reasons,
        "unexpected_rejection_providers": unexpected_rejection_providers,
        "shift_openai_total": shift_openai_total,
        "by_seat": [
            {"seat": seat, **summary} for seat, summary in sorted(by_seat.items())
        ],
        "skald_writer_tripwire": any(
            event.get("seat") == "skald_writer" for event in rejected_events
        ),
        "rejections": rejection_rows,
    }


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShiftError(f"Invalid shift timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise ShiftError(f"Shift timestamp lacks an offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        handle.write("\n")


def _new_archive(root: Path, now: datetime) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stem = f"qa_night_{now.astimezone(timezone.utc):%Y-%m-%d_%H%M%SZ}"
    for suffix in ("", *[f"_{index}" for index in range(2, 100)]):
        candidate = root / f"{stem}{suffix}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise ShiftError(f"Could not allocate a unique archive under {root}")


def _write_runtime_config(
    *,
    repo_root: Path,
    archive: Path,
    config: ShiftConfig,
) -> Path:
    source = repo_root / "nexus.toml"
    try:
        document = tomlkit.parse(source.read_text(encoding="utf-8"))
        dynamic_document = cast(Any, document)
        model = dynamic_document["global"]["model"]
        openai = model["api_models"]["openai"]
        registered = {
            entry["id"]
            for entry in openai["models"]
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }
        if config.target_model not in registered:
            raise ShiftError(
                f"Target model {config.target_model!r} is not registered in {source}"
            )

        model["default_slot_model"] = config.target_model
        for role in openai["roles"]:
            openai["roles"][role] = config.target_model
        # Remote routes not expressed as @openai.<role> refs escape the role
        # pins above and need direct pins; tests/test_qa_shift.py enforces the
        # full route roster against drift.
        dynamic_document["wizard"]["fallback_model"] = "@openai.default"
        narration = dynamic_document["orrery"]["narration"]
        narration["provider"] = "openai"
        narration["model_ref"] = "@openai.default"
        dynamic_document["usage"]["daily_allowance"][
            "openai"
        ] = config.daily_token_limit
    except ShiftError:
        raise
    except (KeyError, OSError, TypeError, tomlkit.exceptions.ParseError) as exc:
        raise ShiftError(f"Cannot derive isolated config from {source}: {exc}") from exc

    destination = archive / "nexus.qa.toml"
    try:
        destination.write_text(tomlkit.dumps(document), encoding="utf-8")
    except (OSError, TypeError) as exc:
        raise ShiftError(f"Cannot write isolated config {destination}: {exc}") from exc
    return destination


def _write_environment(
    *,
    archive: Path,
    runtime_config: Path,
    config: ShiftConfig,
) -> Path:
    environment = archive / "runtime_env.sh"
    values = {
        "NEXUS_RUNTIME_CONFIG": str(runtime_config.resolve()),
        "NEXUS_GATEWAY_PORT": str(config.gateway_port),
        "NEXUS_API_URL": f"http://127.0.0.1:{config.gateway_port}",
        "NEXUS_SLOT": str(config.slot),
    }
    lines = ["# Generated by scripts/qa_shift/qa_shift.py; source per shell."]
    lines.extend(
        f"export {name}={shlex.quote(value)}" for name, value in values.items()
    )
    environment.write_text("\n".join(lines) + "\n", encoding="utf-8")
    environment.chmod(0o700)
    return environment


def begin_shift(
    *,
    config: ShiftConfig,
    repo_root: Path = REPO_ROOT,
    usage_reader: UsageReader = _read_usage,
    jobs_reader: JobsReader = _read_jobs,
    bleed_uptake_reader: BleedUptakeReader = _read_bleed_uptake,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a shift archive, isolated config, and usage baseline."""

    current_time = now or datetime.now(timezone.utc)
    jobs = _jobs_snapshot(jobs_reader(repo_root, config.slot), slot=config.slot)
    if jobs["non_terminal_jobs"]:
        raise ShiftError(
            "QA shift cannot begin with non-terminal maturation jobs: "
            + json.dumps(jobs["non_terminal_jobs"], sort_keys=True)
        )
    usage_payload = usage_reader(repo_root, None)
    usage = _usage_snapshot(usage_payload)
    if usage["unknown"]:
        raise ShiftError(
            "OpenAI usage already contains unknown events for this UTC day; "
            "the complimentary-token fence cannot be trusted."
        )
    if usage["total"] >= config.token_fence:
        raise ShiftError(
            "OpenAI daily usage has reached the configured token fence "
            f"({usage['total']:,} >= {config.token_fence:,})."
        )
    baseline_bleed_offered, baseline_bleed_used = _bleed_uptake_counts(
        bleed_uptake_reader(repo_root, config.slot)
    )

    archive_root = config.archive_root
    if not archive_root.is_absolute():
        archive_root = repo_root / archive_root
    archive = _new_archive(archive_root.resolve(), current_time)
    runtime_config = _write_runtime_config(
        repo_root=repo_root,
        archive=archive,
        config=config,
    )
    environment = _write_environment(
        archive=archive,
        runtime_config=runtime_config,
        config=config,
    )
    utility_root = Path(__file__).resolve().parent
    shutil.copyfile(
        utility_root / "probe_ledger_template.md",
        archive / "probe_ledger.md",
    )
    shutil.copyfile(
        utility_root / "mission_report_template.md",
        archive / "mission_report.md",
    )
    _atomic_write_json(archive / "usage_start.json", usage_payload)

    state = {
        "schema_version": 1,
        "status": "active",
        "started_at": _utc_text(current_time),
        "quota_day": usage["day"],
        "baseline_total": usage["total"],
        "last_total": usage["total"],
        "baseline_event_count": len(usage["events"]),
        "last_event_count": len(usage["events"]),
        "last_unknown_usage_events": usage["unknown"],
        "baseline_failed_jobs": jobs["counts"]["failed"],
        "baseline_bleed_offered_count": baseline_bleed_offered,
        "baseline_bleed_used_count": baseline_bleed_used,
        "checks": 0,
        "max_command_delta": 0,
        "config": _config_payload(config),
    }
    _atomic_write_json(archive / STATE_FILE, state)
    result = {
        "status": "ready",
        "archive": str(archive),
        "runtime_environment": str(environment),
        "quota_day": usage["day"],
        "daily_total": usage["total"],
        "daily_limit": config.daily_token_limit,
        "token_fence": config.token_fence,
        "tokens_before_fence": config.token_fence - usage["total"],
        "bleed_uptake_baseline": {
            "offered_count": baseline_bleed_offered,
            "used_count": baseline_bleed_used,
        },
        "jobs": jobs,
    }
    _append_jsonl(
        archive / CHECKS_FILE,
        {"kind": "begin", "at": _utc_text(current_time), **result},
    )
    return result


def _load_state(archive: Path) -> dict[str, Any]:
    path = archive / STATE_FILE
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShiftError(f"Cannot read shift state {path}: {exc}") from exc
    if state.get("schema_version") != 1:
        raise ShiftError(f"Unsupported shift state schema in {path}")
    if state.get("status") != "active":
        raise ShiftError(f"Shift state is not active: {state.get('status')!r}")
    return state


def _read_validation_evidence(
    *,
    mode: CheckMode,
    probe_command: str | None,
    rejection_status: int | None,
    rejection_evidence: Path | None,
) -> ValidationEvidence | None:
    supplied = (
        probe_command is not None,
        rejection_status is not None,
        rejection_evidence is not None,
    )
    if mode is not CheckMode.VALIDATION_ONLY:
        if any(supplied):
            raise ShiftError(
                "Rejection evidence flags require --expect-validation-only"
            )
        return None

    if not all(supplied):
        raise ShiftError(
            "--expect-validation-only requires --probe-command, "
            "--rejection-status, and --rejection-evidence"
        )
    assert probe_command is not None
    assert rejection_status is not None
    assert rejection_evidence is not None
    if not probe_command.strip():
        raise ShiftError("--probe-command must be a non-empty string")
    if isinstance(rejection_status, bool) or not isinstance(rejection_status, int):
        raise ShiftError("--rejection-status must be an integer")

    evidence_path = rejection_evidence.resolve()
    try:
        evidence_bytes = evidence_path.read_bytes()
        evidence_text = evidence_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ShiftError(
            f"Cannot read rejection evidence {evidence_path}: {exc}"
        ) from exc
    return ValidationEvidence(
        probe_command=probe_command,
        rejection_status=rejection_status,
        rejection_evidence=str(evidence_path),
        rejection_evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
        rejection_evidence_excerpt=evidence_text[:500],
    )


def evaluate_check(
    *,
    state: Mapping[str, Any],
    usage_payload: Mapping[str, Any],
    jobs_payload: Mapping[str, Any],
    mode: CheckMode,
    validation_evidence: ValidationEvidence | None = None,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate one pre/post-call usage check without filesystem access."""

    if mode is CheckMode.VALIDATION_ONLY and validation_evidence is None:
        raise ShiftError("Validation-only checks require rejection evidence metadata")
    if mode is not CheckMode.VALIDATION_ONLY and validation_evidence is not None:
        raise ShiftError("Rejection evidence metadata requires validation-only mode")

    usage = _usage_snapshot(usage_payload)
    config = state["config"]
    previous_total = int(state["last_total"])
    previous_events = int(state["last_event_count"])
    same_quota_day = usage["day"] == state["quota_day"]
    raw_delta = usage["total"] - previous_total if same_quota_day else None
    delta = max(0, raw_delta) if raw_delta is not None else None

    if same_quota_day and len(usage["events"]) < previous_events:
        new_events: list[Any] = []
    elif same_quota_day:
        new_events = usage["events"][previous_events:]
    else:
        new_events = usage["events"]

    slot = int(config["slot"])
    target_model = str(config["target_model"])
    qa_events = [
        event
        for event in new_events
        if isinstance(event, dict) and event.get("slot") == slot
    ]
    qa_api_calls = [
        {
            key: event.get(key)
            for key in (
                "request_id",
                "run_id",
                "seat",
                "provider",
                "model",
                "attempt",
                "outcome",
                "input_tokens",
                "output_tokens",
                "total_tokens",
            )
        }
        for event in qa_events
    ]
    expected_events = [
        event
        for event in qa_events
        if event.get("provider") == "openai" and event.get("model") == target_model
    ]
    unexpected_routes = sorted(
        {
            f"{event.get('provider', 'unknown')}:{event.get('model', 'unknown')}"
            for event in qa_events
            if event.get("provider") != "openai" or event.get("model") != target_model
        }
    )
    token_fence = int(config["token_fence"])
    started_at = _parse_utc(str(state["started_at"]))
    elapsed_minutes = (now.astimezone(timezone.utc) - started_at).total_seconds() / 60
    jobs = _jobs_snapshot(jobs_payload, slot=slot)
    baseline_failed_jobs = int(state["baseline_failed_jobs"])
    current_failed_jobs = int(jobs["counts"]["failed"])
    expect_call = mode is CheckMode.POST_CALL
    validation_fields: dict[str, Any] = {}
    if validation_evidence is not None:
        validation_fields = {
            **asdict(validation_evidence),
            "observed_token_delta": delta,
            "observed_new_usage_events": len(new_events),
            "observed_qa_usage_events": len(qa_events),
        }
    if jobs["non_terminal_jobs"]:
        return (
            {
                "status": "pending",
                "reasons": [],
                "quota_day": usage["day"],
                "daily_total": usage["total"],
                "daily_limit": int(config["daily_token_limit"]),
                "daily_headroom": max(
                    0, int(config["daily_token_limit"]) - usage["total"]
                ),
                "token_fence": token_fence,
                "tokens_before_fence": max(0, token_fence - usage["total"]),
                "openai_delta_since_last_check": delta,
                "shift_openai_total": (
                    max(0, usage["total"] - int(state["baseline_total"]))
                    if same_quota_day
                    else None
                ),
                "max_command_delta": int(state["max_command_delta"]),
                "elapsed_minutes": round(elapsed_minutes, 2),
                "new_usage_events": len(new_events),
                "qa_usage_events": len(qa_events),
                "qa_api_calls": qa_api_calls,
                "qa_models_seen": sorted(
                    {
                        str(event.get("model"))
                        for event in qa_events
                        if event.get("model") is not None
                    }
                ),
                "unexpected_routes": unexpected_routes,
                "expect_call": expect_call,
                "jobs": jobs,
                "non_terminal_jobs": jobs["non_terminal_jobs"],
                "baseline_failed_jobs": baseline_failed_jobs,
                "current_failed_jobs": current_failed_jobs,
                **validation_fields,
                **(
                    {"disposition": "pending"}
                    if validation_evidence is not None
                    else {}
                ),
            },
            dict(state),
        )

    reasons: list[str] = []
    if not same_quota_day:
        reasons.append("quota_day_changed")
    if raw_delta is not None and raw_delta < 0:
        reasons.append("daily_total_decreased")
    if same_quota_day and len(usage["events"]) < previous_events:
        reasons.append("event_count_decreased")
    if current_failed_jobs > baseline_failed_jobs:
        reasons.append("maturation_job_failed")
    if unexpected_routes:
        reasons.append("unexpected_qa_model_route")
    if expect_call and not expected_events:
        reasons.append("expected_usage_event_missing")
    if mode is CheckMode.VALIDATION_ONLY and (
        qa_events or (delta is not None and delta != 0)
    ):
        reasons.append("usage_present_for_validation_only")
    if usage["unknown"] > 0:
        reasons.append("unknown_openai_usage")

    if usage["total"] >= token_fence:
        reasons.append("token_fence_reached")

    if elapsed_minutes >= int(config["wall_clock_minutes"]):
        reasons.append("wall_clock_reached")

    updated = dict(state)
    updated.update(
        {
            "last_unknown_usage_events": usage["unknown"],
            "last_checked_at": _utc_text(now),
            "checks": int(state["checks"]) + 1,
            "max_command_delta": (
                max(int(state["max_command_delta"]), delta)
                if delta is not None
                else int(state["max_command_delta"])
            ),
        }
    )
    if same_quota_day:
        updated["last_total"] = usage["total"]
        updated["last_event_count"] = len(usage["events"])
    else:
        updated.update(
            {
                "rollover_seen_at": _utc_text(now),
                "rollover_day": usage["day"],
                "rollover_day_total": usage["total"],
            }
        )
    status = "stop" if reasons else "continue"
    result = {
        "status": status,
        "reasons": reasons,
        "quota_day": usage["day"],
        "daily_total": usage["total"],
        "daily_limit": int(config["daily_token_limit"]),
        "daily_headroom": max(0, int(config["daily_token_limit"]) - usage["total"]),
        "token_fence": token_fence,
        "tokens_before_fence": max(0, token_fence - usage["total"]),
        "openai_delta_since_last_check": delta,
        "shift_openai_total": (
            max(0, usage["total"] - int(state["baseline_total"]))
            if same_quota_day
            else None
        ),
        "max_command_delta": updated["max_command_delta"],
        "elapsed_minutes": round(elapsed_minutes, 2),
        "new_usage_events": len(new_events),
        "qa_usage_events": len(qa_events),
        "qa_api_calls": qa_api_calls,
        "qa_models_seen": sorted(
            {
                str(event.get("model"))
                for event in qa_events
                if event.get("model") is not None
            }
        ),
        "unexpected_routes": unexpected_routes,
        "expect_call": expect_call,
        "jobs": jobs,
        "non_terminal_jobs": jobs["non_terminal_jobs"],
        "baseline_failed_jobs": baseline_failed_jobs,
        "current_failed_jobs": current_failed_jobs,
        **validation_fields,
        **({"disposition": status} if validation_evidence is not None else {}),
    }
    return result, updated


def check_shift(
    *,
    archive: Path,
    mode: CheckMode,
    probe_command: str | None = None,
    rejection_status: int | None = None,
    rejection_evidence: Path | None = None,
    repo_root: Path = REPO_ROOT,
    usage_reader: UsageReader = _read_usage,
    jobs_reader: JobsReader = _read_jobs,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run and persist one fail-closed usage check."""

    evidence = _read_validation_evidence(
        mode=mode,
        probe_command=probe_command,
        rejection_status=rejection_status,
        rejection_evidence=rejection_evidence,
    )
    archive = archive.resolve()
    state = _load_state(archive)
    current_time = now or datetime.now(timezone.utc)
    jobs_payload = jobs_reader(repo_root, int(state["config"]["slot"]))
    usage_payload = usage_reader(repo_root, None)
    result, updated = evaluate_check(
        state=state,
        usage_payload=usage_payload,
        jobs_payload=jobs_payload,
        mode=mode,
        validation_evidence=evidence,
        now=current_time,
    )
    _atomic_write_json(archive / STATE_FILE, updated)
    _append_jsonl(
        archive / CHECKS_FILE,
        {
            "kind": mode.value,
            "at": _utc_text(current_time),
            **result,
        },
    )
    return result


def finish_shift(
    *,
    archive: Path,
    exit_condition: str,
    repo_root: Path = REPO_ROOT,
    usage_reader: UsageReader = _read_usage,
    jobs_reader: JobsReader = _read_jobs,
    bleed_uptake_reader: BleedUptakeReader = _read_bleed_uptake,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Capture final usage and close the shift state."""

    archive = archive.resolve()
    state = _load_state(archive)
    current_time = now or datetime.now(timezone.utc)
    quota_day = str(state["quota_day"])
    slot = int(state["config"]["slot"])
    jobs = _jobs_snapshot(jobs_reader(repo_root, slot), slot=slot)
    baseline_failed_jobs = int(state["baseline_failed_jobs"])
    current_failed_jobs = int(jobs["counts"]["failed"])
    usage_settled = (
        not jobs["non_terminal_jobs"] and current_failed_jobs <= baseline_failed_jobs
    )
    usage_payload = usage_reader(repo_root, quota_day)
    usage = _usage_snapshot(usage_payload)
    if usage["day"] != quota_day:
        raise ShiftError(
            "Final usage reader returned the wrong quota day "
            f"({usage['day']} != {quota_day})."
        )
    _atomic_write_json(archive / "usage_end.json", usage_payload)

    final_delta = max(0, usage["total"] - int(state["last_total"]))
    shift_openai_total = max(0, usage["total"] - int(state["baseline_total"]))
    rejection_ledger = _rejection_ledger(
        state=state,
        usage=usage,
        shift_openai_total=shift_openai_total,
    )
    _atomic_write_json(archive / "rejection_ledger.json", rejection_ledger)
    started_at = _parse_utc(str(state["started_at"]))
    bleed_uptake = _bleed_uptake_summary(
        bleed_uptake_reader(repo_root, slot),
        baseline_offered_count=int(state["baseline_bleed_offered_count"]),
        baseline_used_count=int(state["baseline_bleed_used_count"]),
        started_at=started_at,
        ended_at=current_time,
    )
    _atomic_write_json(archive / "bleed_uptake.json", bleed_uptake)
    final_state = dict(state)
    final_state.update(
        {
            "status": "finished",
            "ended_at": _utc_text(current_time),
            "exit_condition": exit_condition,
            "final_total": usage["total"],
            "final_usage_day": usage["day"],
            "final_unknown_usage_events": usage["unknown"],
            "finished_after_quota_rollover": (
                current_time.astimezone(timezone.utc).date().isoformat() != quota_day
            ),
            "shift_openai_total": shift_openai_total,
            "max_command_delta": max(int(state["max_command_delta"]), final_delta),
            "rejected_attempts": rejection_ledger["rejected_attempts"],
            "repair_tax_tokens": rejection_ledger["rejected_tokens"],
            "repair_tax_percent": rejection_ledger["repair_tax_percent_of_shift"],
            "repair_tax_percent_unavailable_reasons": rejection_ledger[
                "repair_tax_percent_unavailable_reasons"
            ],
            "skald_writer_tripwire": rejection_ledger["skald_writer_tripwire"],
            "bleed_uptake": bleed_uptake,
            "jobs": jobs,
            "usage_settled": usage_settled,
            "baseline_failed_jobs": baseline_failed_jobs,
            "current_failed_jobs": current_failed_jobs,
        }
    )
    _atomic_write_json(archive / STATE_FILE, final_state)
    result = {
        "status": "finished",
        "exit_condition": exit_condition,
        "quota_day": usage["day"],
        "daily_total": usage["total"],
        "shift_openai_total": final_state["shift_openai_total"],
        "max_command_delta": final_state["max_command_delta"],
        "unknown_usage_events": usage["unknown"],
        "rejected_attempts": rejection_ledger["rejected_attempts"],
        "repair_tax_tokens": rejection_ledger["rejected_tokens"],
        "repair_tax_percent": rejection_ledger["repair_tax_percent_of_shift"],
        "repair_tax_percent_unavailable_reasons": rejection_ledger[
            "repair_tax_percent_unavailable_reasons"
        ],
        "skald_writer_tripwire": rejection_ledger["skald_writer_tripwire"],
        "rejection_ledger": str(archive / "rejection_ledger.json"),
        "bleed_uptake": bleed_uptake,
        "bleed_uptake_report": str(archive / "bleed_uptake.json"),
        "archive": str(archive),
        "jobs": jobs,
        "usage_settled": usage_settled,
        "baseline_failed_jobs": baseline_failed_jobs,
        "current_failed_jobs": current_failed_jobs,
    }
    _append_jsonl(
        archive / CHECKS_FILE,
        {"kind": "finish", "at": _utc_text(current_time), **result},
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and guard a native Codex NEXUS QA shift"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="Print effective settings")
    config_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Tracked QA shift TOML",
    )

    begin_parser = subparsers.add_parser("begin", help="Create a guarded run")
    begin_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Tracked QA shift TOML",
    )

    check_parser = subparsers.add_parser("check", help="Check the token fence")
    check_parser.add_argument("archive", type=Path, help="Run archive from begin")
    check_mode = check_parser.add_mutually_exclusive_group()
    check_mode.add_argument(
        "--expect-call",
        action="store_true",
        help="Fail closed unless the QA slot recorded a target-model event",
    )
    check_mode.add_argument(
        "--expect-validation-only",
        action="store_true",
        help="Fail closed if local validation rejection recorded any usage",
    )
    check_parser.add_argument(
        "--probe-command",
        help="Public command rejected before provider dispatch",
    )
    check_parser.add_argument(
        "--rejection-status",
        type=int,
        help="HTTP status or CLI exit status of the validation rejection",
    )
    check_parser.add_argument(
        "--rejection-evidence",
        type=Path,
        help="Saved complete local validation rejection response",
    )

    finish_parser = subparsers.add_parser("finish", help="Capture final usage")
    finish_parser.add_argument("archive", type=Path, help="Run archive from begin")
    finish_parser.add_argument(
        "--exit-condition",
        required=True,
        choices=(
            "issue_budget",
            "dry_well",
            "token_fence",
            "wall_clock",
            "blocked",
            "manual",
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the QA shift helper CLI."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "config":
            result = _config_payload(load_shift_config(args.config))
        elif args.command == "begin":
            result = begin_shift(config=load_shift_config(args.config))
        elif args.command == "check":
            if args.expect_validation_only:
                mode = CheckMode.VALIDATION_ONLY
            elif args.expect_call:
                mode = CheckMode.POST_CALL
            else:
                mode = CheckMode.PRE_CALL
            result = check_shift(
                archive=args.archive,
                mode=mode,
                probe_command=args.probe_command,
                rejection_status=args.rejection_status,
                rejection_evidence=args.rejection_evidence,
            )
        elif args.command == "finish":
            result = finish_shift(
                archive=args.archive,
                exit_condition=args.exit_condition,
            )
        else:
            raise AssertionError(f"Unhandled command {args.command}")
    except ShiftError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "check" and result["status"] == "stop":
        return STOP_EXIT_CODE
    if args.command == "check" and result["status"] == "pending":
        return PENDING_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
