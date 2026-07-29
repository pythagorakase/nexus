"""Exact provider-reported token usage recording and summaries."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterator, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus.config import load_settings


logger = logging.getLogger("nexus.usage")

UsageOutcome = Literal["accepted", "rejected_validation", "error", "aggregate"]
UsageTransport = Literal[
    "responses", "chat_completions", "anthropic_messages", "pydantic_ai"
]

_UNSET = object()
_seat_context: ContextVar[Optional[str]] = ContextVar("nexus_usage_seat", default=None)
_slot_context: ContextVar[Optional[int]] = ContextVar("nexus_usage_slot", default=None)
_run_id_context: ContextVar[Optional[str]] = ContextVar(
    "nexus_usage_run_id", default=None
)


class UsageWriteError(RuntimeError):
    """Raised when a usage event cannot be appended durably."""


class UsageReadError(RuntimeError):
    """Raised when a usage day file cannot be parsed exactly."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"ts must be an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("ts must include a UTC offset")
    return parsed.astimezone(timezone.utc)


class UsageEvent(BaseModel):
    """One completed provider response without prompt or response content."""

    model_config = ConfigDict(extra="forbid")

    ts: str = Field(default_factory=_utc_timestamp)
    quota_day: str = Field(default="")
    provider: str
    model: str
    seat: str
    slot: Optional[int] = None
    run_id: Optional[str] = None
    attempt: int = Field(ge=1)
    outcome: UsageOutcome
    transport: UsageTransport
    request_id: Optional[str] = None
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)
    cached_input_tokens: Optional[int] = Field(default=None, ge=0)
    cache_creation_tokens: Optional[int] = Field(default=None, ge=0)
    reasoning_tokens: Optional[int] = Field(default=None, ge=0)
    service_tier: Optional[str] = None
    aggregate: bool = False
    requests: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _derive_quota_day(self) -> "UsageEvent":
        """Derive the quota day from the timestamp after normalizing to UTC."""

        utc_ts = _parse_utc_timestamp(self.ts)
        self.quota_day = utc_ts.date().isoformat()
        return self


class _RecorderConfig(BaseModel):
    enabled: bool
    usage_dir: Path
    daily_allowance: Dict[str, int]


_config: Optional[_RecorderConfig] = None
_config_lock = Lock()


def _repo_root() -> Path:
    """The repository root, derived from the nexus package location.

    Mirrors nexus.runtime.supervisor.repo_root without importing the
    supervisor from this leaf module. Relative usage_dir values must anchor
    here — never to the NEXUS_RUNTIME_CONFIG file's directory — so alternate
    runtime configs (QA lanes) share one account-level usage ledger.
    """

    return Path(__file__).resolve().parents[2]


def _load_recorder_config() -> _RecorderConfig:
    settings = load_settings()
    usage_dir = Path(settings.usage.usage_dir)
    if not usage_dir.is_absolute():
        usage_dir = _repo_root() / usage_dir
    return _RecorderConfig(
        enabled=settings.usage.enabled,
        usage_dir=usage_dir,
        daily_allowance=dict(settings.usage.daily_allowance),
    )


def _get_recorder_config() -> _RecorderConfig:
    global _config
    if _config is None:
        with _config_lock:
            if _config is None:
                _config = _load_recorder_config()
    return _config


def _reset_usage_config_cache() -> None:
    """Reset the lazy config singleton for isolated tests."""

    global _config
    with _config_lock:
        _config = None


@contextmanager
def usage_context(
    *,
    seat: object = _UNSET,
    slot: object = _UNSET,
    run_id: object = _UNSET,
) -> Iterator[None]:
    """Temporarily supply usage correlation, overriding only provided fields."""

    tokens: list[tuple[ContextVar[Any], Any]] = []
    if seat is not _UNSET:
        tokens.append((_seat_context, _seat_context.set(_optional_str(seat, "seat"))))
    if slot is not _UNSET:
        tokens.append((_slot_context, _slot_context.set(_optional_int(slot, "slot"))))
    if run_id is not _UNSET:
        tokens.append(
            (_run_id_context, _run_id_context.set(_optional_str(run_id, "run_id")))
        )
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


def _optional_str(value: object, field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be str or None")
    return value


def _optional_int(value: object, field: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int):
        raise TypeError(f"{field} must be int or None")
    return value


def current_usage_context() -> tuple[Optional[str], Optional[int], Optional[str]]:
    """Return the effective ambient seat, slot, and run id."""

    slot = _slot_context.get()
    if slot is None:
        raw_slot = os.environ.get("NEXUS_SLOT")
        if raw_slot is not None:
            try:
                slot = int(raw_slot)
            except ValueError as exc:
                raise ValueError(
                    f"NEXUS_SLOT must be an integer for usage telemetry: {raw_slot!r}"
                ) from exc
    return _seat_context.get(), slot, _run_id_context.get()


def provider_name_from_base_url(
    *,
    native_name: str,
    base_url: Optional[str],
) -> str:
    """Resolve native or explicit OpenAI-compatible provider identity."""

    if base_url is None:
        return native_name
    host = urlparse(base_url).hostname
    if not host:
        raise ValueError(
            f"Cannot derive usage provider from base_url without a host: {base_url!r}"
        )
    return f"openai_compatible:{host}"


def record_usage_event(event: UsageEvent) -> None:
    """Atomically append one event and emit its grep-stable gateway log line."""

    config = _get_recorder_config()
    if not config.enabled:
        return

    path = config.usage_dir / f"usage-{event.quota_day}.jsonl"
    line = (
        json.dumps(event.model_dump(mode="json"), separators=(",", ":")) + "\n"
    ).encode("utf-8")
    try:
        config.usage_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            written = os.write(fd, line)
            if written != len(line):
                raise UsageWriteError(
                    f"Short usage append to {path}: wrote {written} of "
                    f"{len(line)} bytes"
                )
        finally:
            os.close(fd)
    except UsageWriteError:
        raise
    except OSError as exc:
        raise UsageWriteError(f"Failed to append usage event to {path}: {exc}") from exc

    logger.info(
        "USAGE provider=%s model=%s seat=%s slot=%s run=%s attempt=%s "
        "outcome=%s in=%s out=%s total=%s cached=%s reasoning=%s tier=%s",
        event.provider,
        event.model,
        event.seat or "unknown",
        event.slot if event.slot is not None else "-",
        event.run_id if event.run_id is not None else "-",
        event.attempt,
        event.outcome,
        _display_unknown(event.input_tokens),
        _display_unknown(event.output_tokens),
        _display_unknown(event.total_tokens),
        _display_unknown(event.cached_input_tokens),
        _display_unknown(event.reasoning_tokens),
        _display_unknown(event.service_tier),
    )


def _display_unknown(value: object) -> object:
    return "?" if value is None else value


def _empty_totals() -> Dict[str, int]:
    return {
        "input": 0,
        "output": 0,
        "total": 0,
        "cached_input": 0,
        "reasoning": 0,
        "events": 0,
        "unknown_usage_events": 0,
    }


def _add_event(totals: Dict[str, int], event: UsageEvent) -> None:
    totals["events"] += 1
    if (
        event.input_tokens is None
        and event.output_tokens is None
        and event.total_tokens is None
    ):
        totals["unknown_usage_events"] += 1
    for output_key, field_name in (
        ("input", "input_tokens"),
        ("output", "output_tokens"),
        ("total", "total_tokens"),
        ("cached_input", "cached_input_tokens"),
        ("reasoning", "reasoning_tokens"),
    ):
        value = getattr(event, field_name)
        if value is not None:
            totals[output_key] += value


def summarize_usage(
    day: Optional[str] = None,
    run_id: Optional[str] = None,
    usage_dir: Optional[Path] = None,
) -> dict:
    """Read one UTC day exactly and aggregate provider and seat totals."""

    selected_day = day or datetime.now(timezone.utc).date().isoformat()
    try:
        datetime.strptime(selected_day, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Usage day must be YYYY-MM-DD, got {selected_day!r}") from exc

    config = _get_recorder_config()
    directory = Path(usage_dir) if usage_dir is not None else config.usage_dir
    path = directory / f"usage-{selected_day}.jsonl"
    events: list[UsageEvent] = []
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, raw_line in enumerate(handle, start=1):
                    try:
                        payload = json.loads(raw_line)
                        event = UsageEvent.model_validate(payload)
                    except Exception as exc:
                        raise UsageReadError(
                            f"Malformed usage event in {path} at line "
                            f"{line_number}: {exc}"
                        ) from exc
                    if event.quota_day != selected_day:
                        raise UsageReadError(
                            f"Usage event day mismatch in {path} at line "
                            f"{line_number}: event quota_day={event.quota_day}"
                        )
                    if run_id is None or event.run_id == run_id:
                        events.append(event)
        except UsageReadError:
            raise
        except OSError as exc:
            raise UsageReadError(f"Failed to read usage file {path}: {exc}") from exc

    providers: Dict[str, Dict[str, int]] = {}
    seats: Dict[str, Dict[str, int]] = {}
    for event in events:
        provider_totals = providers.setdefault(event.provider, _empty_totals())
        seat_totals = seats.setdefault(event.seat or "unknown", _empty_totals())
        _add_event(provider_totals, event)
        _add_event(seat_totals, event)

    openai_totals = providers.get("openai", _empty_totals())
    allowance = {}
    for provider, limit in config.daily_allowance.items():
        totals = providers.get(provider, _empty_totals())
        used = totals["total"]
        allowance[provider] = {
            "allowance": limit,
            "used": used,
            "remaining": max(0, limit - used),
            "unknown_usage_events": totals["unknown_usage_events"],
        }

    return {
        "day": selected_day,
        "events": [event.model_dump(mode="json") for event in events],
        "providers": providers,
        "seats": seats,
        "openai_day_total": {
            "total_tokens": openai_totals["total"],
            "unknown_usage_events": openai_totals["unknown_usage_events"],
        },
        "allowance": allowance,
    }


def make_usage_event(
    *,
    provider: str,
    model: str,
    seat: Optional[str],
    attempt: int,
    outcome: UsageOutcome,
    transport: UsageTransport,
    request_id: Optional[str],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    total_tokens: Optional[int],
    cached_input_tokens: Optional[int] = None,
    cache_creation_tokens: Optional[int] = None,
    reasoning_tokens: Optional[int] = None,
    service_tier: Optional[str] = None,
    aggregate: bool = False,
    requests: Optional[int] = None,
    slot: Optional[int] = None,
    run_id: Optional[str] = None,
) -> UsageEvent:
    """Build an event using ambient correlation only when explicit values are absent."""

    ambient_seat, ambient_slot, ambient_run_id = current_usage_context()
    return UsageEvent(
        provider=provider,
        model=model,
        seat=seat if seat is not None else (ambient_seat or "unknown"),
        slot=slot if slot is not None else ambient_slot,
        run_id=run_id if run_id is not None else ambient_run_id,
        attempt=attempt,
        outcome=outcome,
        transport=transport,
        request_id=request_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_creation_tokens=cache_creation_tokens,
        reasoning_tokens=reasoning_tokens,
        service_tier=service_tier,
        aggregate=aggregate,
        requests=requests,
    )


def _nested_attr(value: Any, *names: str) -> Any:
    current = value
    for name in names:
        if current is None:
            return None
        current = getattr(current, name, None)
    return current


def record_openai_response(
    response: Any,
    *,
    provider: str,
    model: str,
    seat: Optional[str],
    attempt: int,
    outcome: UsageOutcome,
    transport: Literal["responses", "chat_completions"],
) -> None:
    """Extract truthful usage from one raw OpenAI-compatible response."""

    usage = getattr(response, "usage", None)
    if transport == "responses":
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        cached_input_tokens = _nested_attr(
            usage, "input_tokens_details", "cached_tokens"
        )
        reasoning_tokens = _nested_attr(
            usage, "output_tokens_details", "reasoning_tokens"
        )
    else:
        input_tokens = getattr(usage, "prompt_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(usage, "output_tokens", None)
        cached_input_tokens = _nested_attr(
            usage, "prompt_tokens_details", "cached_tokens"
        )
        reasoning_tokens = None
    total_tokens = getattr(usage, "total_tokens", None)
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    event = make_usage_event(
        provider=provider,
        model=model,
        seat=seat,
        attempt=attempt,
        outcome=outcome,
        transport=transport,
        request_id=getattr(response, "id", None),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
        service_tier=getattr(response, "service_tier", None),
    )
    record_usage_event(event)


def record_anthropic_response(
    response: Any,
    *,
    provider: str,
    model: str,
    seat: Optional[str],
    attempt: int,
    outcome: UsageOutcome,
) -> None:
    """Extract truthful usage from one raw Anthropic Messages response."""

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    event = make_usage_event(
        provider=provider,
        model=model,
        seat=seat,
        attempt=attempt,
        outcome=outcome,
        transport="anthropic_messages",
        request_id=getattr(response, "id", None),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=getattr(usage, "cache_read_input_tokens", None),
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", None),
    )
    record_usage_event(event)


def record_pydantic_ai_result(
    result: Any,
    *,
    provider: str,
    model: str,
    seat: str,
    slot: Optional[int] = None,
    run_id: Optional[str] = None,
) -> None:
    """Record one Pydantic AI run-level aggregate including internal requests."""

    usage = result.usage()
    input_tokens = getattr(usage, "input_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(usage, "request_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if output_tokens is None:
        output_tokens = getattr(usage, "response_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    details = getattr(usage, "details", None) or {}
    cached_input_tokens = getattr(usage, "cache_read_tokens", None)
    if cached_input_tokens is None:
        cached_input_tokens = details.get("cached_input_tokens")
    cache_creation_tokens = getattr(usage, "cache_write_tokens", None)
    if cache_creation_tokens is None:
        cache_creation_tokens = details.get("cache_creation_tokens")
    event = make_usage_event(
        provider=provider,
        model=model,
        seat=seat,
        slot=slot,
        run_id=run_id,
        attempt=1,
        outcome="aggregate",
        transport="pydantic_ai",
        request_id=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_creation_tokens=cache_creation_tokens,
        reasoning_tokens=details.get("reasoning_tokens"),
        aggregate=True,
        requests=getattr(usage, "requests", None),
    )
    record_usage_event(event)
