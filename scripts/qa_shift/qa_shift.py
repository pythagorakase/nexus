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
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tomllib
from typing import Any, Callable, Mapping, Sequence, cast

import tomlkit


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = Path(__file__).with_name("qa_shift.toml")
STATE_FILE = "shift_state.json"
CHECKS_FILE = "usage_checks.jsonl"
STOP_EXIT_CODE = 2


class ShiftError(RuntimeError):
    """Raised when the QA shift cannot continue safely."""


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
        openai["roles"]["default"] = config.target_model
        openai["roles"]["gaia"] = config.target_model
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
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a shift archive, isolated config, and usage baseline."""

    current_time = now or datetime.now(timezone.utc)
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


def evaluate_check(
    *,
    state: Mapping[str, Any],
    usage_payload: Mapping[str, Any],
    expect_call: bool,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate one pre/post-call usage check without filesystem access."""

    usage = _usage_snapshot(usage_payload)
    config = state["config"]
    reasons: list[str] = []
    previous_total = int(state["last_total"])
    previous_events = int(state["last_event_count"])
    same_quota_day = usage["day"] == state["quota_day"]
    raw_delta = usage["total"] - previous_total if same_quota_day else None
    delta = max(0, raw_delta) if raw_delta is not None else None

    if not same_quota_day:
        reasons.append("quota_day_changed")
    if raw_delta is not None and raw_delta < 0:
        reasons.append("daily_total_decreased")
    if same_quota_day and len(usage["events"]) < previous_events:
        reasons.append("event_count_decreased")
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
    if unexpected_routes:
        reasons.append("unexpected_qa_model_route")
    if expect_call and not expected_events:
        reasons.append("expected_usage_event_missing")
    if usage["unknown"] > 0:
        reasons.append("unknown_openai_usage")

    token_fence = int(config["token_fence"])
    if usage["total"] >= token_fence:
        reasons.append("token_fence_reached")

    started_at = _parse_utc(str(state["started_at"]))
    elapsed_minutes = (now.astimezone(timezone.utc) - started_at).total_seconds() / 60
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
    result = {
        "status": "stop" if reasons else "continue",
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
    }
    return result, updated


def check_shift(
    *,
    archive: Path,
    expect_call: bool,
    repo_root: Path = REPO_ROOT,
    usage_reader: UsageReader = _read_usage,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run and persist one fail-closed usage check."""

    archive = archive.resolve()
    state = _load_state(archive)
    current_time = now or datetime.now(timezone.utc)
    usage_payload = usage_reader(repo_root, None)
    result, updated = evaluate_check(
        state=state,
        usage_payload=usage_payload,
        expect_call=expect_call,
        now=current_time,
    )
    _atomic_write_json(archive / STATE_FILE, updated)
    _append_jsonl(
        archive / CHECKS_FILE,
        {
            "kind": "post_call" if expect_call else "pre_call",
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
    now: datetime | None = None,
) -> dict[str, Any]:
    """Capture final usage and close the shift state."""

    archive = archive.resolve()
    state = _load_state(archive)
    current_time = now or datetime.now(timezone.utc)
    quota_day = str(state["quota_day"])
    usage_payload = usage_reader(repo_root, quota_day)
    usage = _usage_snapshot(usage_payload)
    if usage["day"] != quota_day:
        raise ShiftError(
            "Final usage reader returned the wrong quota day "
            f"({usage['day']} != {quota_day})."
        )
    _atomic_write_json(archive / "usage_end.json", usage_payload)

    final_delta = max(0, usage["total"] - int(state["last_total"]))
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
            "shift_openai_total": max(0, usage["total"] - int(state["baseline_total"])),
            "max_command_delta": max(int(state["max_command_delta"]), final_delta),
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
        "archive": str(archive),
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
    check_parser.add_argument(
        "--expect-call",
        action="store_true",
        help="Fail closed unless the QA slot recorded a target-model event",
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
            result = check_shift(
                archive=args.archive,
                expect_call=args.expect_call,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
