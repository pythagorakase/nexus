"""Offline proofs of the issue #845 probe's parsing, join and verdict.

The paid probe (``tests/test_fable_structured_output_live.py``) runs once,
by the coordinator. These tests run its importable functions on real
provider log lines and real ledger events, so a drift between the
``structured-output rejected`` format and the probe's parser, or a change in
the Decision 845-D1 classification, fails in every default gate.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, cast

import pytest
from anthropic.types.beta import BetaMessage, BetaThinkingBlock, BetaUsage

from nexus.agents.logon.skald_wire import SkaldWriterWire
from nexus.config import load_settings
from nexus.telemetry.usage import make_usage_event
from scripts.api_anthropic import AnthropicProvider
from tests.test_fable_structured_output_live import (
    MODEL_UNDER_TEST,
    TURN_COUNT,
    Rejection,
    TurnWindow,
    completed_turns,
    join_attempts,
    parse_rejection_lines,
    probe_lane,
    read_ledger,
    verdict,
    write_evidence,
)

_BASE = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)


def test_parser_reads_the_provider_line(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """The probe's regex reads the real provider's rejection line."""

    response = BetaMessage(
        id="msg_845",
        type="message",
        role="assistant",
        model=MODEL_UNDER_TEST,
        content=[
            BetaThinkingBlock(
                type="thinking", thinking="private thinking", signature="sig"
            )
        ],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=BetaUsage(input_tokens=33, output_tokens=812),
    )

    class FakeMessages:
        def create(self, **kwargs: Any) -> Any:
            return response

    provider = AnthropicProvider(
        model=MODEL_UNDER_TEST,
        api_key="test-key",
        structured_transport="native",
        structured_output_retries=0,
        usage_seat="skald_writer",
    )
    provider.client = cast(
        Any, SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    )
    with caplog.at_level(logging.WARNING, logger="nexus.metadata"):
        with pytest.raises(ValueError):
            provider.get_structured_completion("Prompt", SkaldWriterWire)

    records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("structured-output rejected")
    ]
    assert len(records) == 1
    runtime = load_settings().runtime
    assert runtime is not None
    formatter = logging.Formatter(runtime.logs.format)
    log_path = tmp_path / "gateway.log"
    log_path.write_text(
        "2026-10-26 18:00:00,000 - uvicorn - INFO - unrelated line\n"
        + formatter.format(records[0])
        + "\n"
    )

    assert parse_rejection_lines(log_path.read_text()) == [
        Rejection(
            transport="native",
            seat="skald_writer",
            attempt=1,
            exception="ValueError",
            stop_reason="end_turn",
            block_types="thinking",
            output_tokens="812",
            error=(
                "Anthropic structured response did not include JSON output; "
                "stop_reason=end_turn block_types=thinking output_tokens=812"
            ),
        )
    ]


def _event(
    seat: str,
    outcome: str,
    at: datetime,
    *,
    attempt: int = 1,
    provider: str = "anthropic",
    model: str = MODEL_UNDER_TEST,
) -> dict[str, Any]:
    data = make_usage_event(
        provider=provider,
        model=model,
        seat=seat,
        attempt=attempt,
        outcome=cast(Any, outcome),
        transport="anthropic_messages",
        request_id=f"req_{seat}_{at.isoformat()}",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
    ).model_dump(mode="json")
    data["ts"] = at.isoformat()
    return data


def _line(
    *,
    transport: str,
    seat: str,
    stop_reason: str,
    block_types: str,
    error: str,
    attempt: int = 1,
) -> str:
    return (
        "2026-10-26 18:00:00,000 - nexus.metadata - WARNING - "
        f"structured-output rejected transport={transport} "
        f"model={MODEL_UNDER_TEST} seat={seat} attempt={attempt} "
        f"exception=ValueError stop_reason={stop_reason} "
        f"block_types={block_types} output_tokens=40 error={error}"
    )


def _windows(count: int) -> list[TurnWindow]:
    return [
        TurnWindow(
            index=index,
            start=_BASE + timedelta(minutes=10 * index),
            end=_BASE + timedelta(minutes=10 * index + 5),
        )
        for index in range(1, count + 1)
    ]


def _accepted_turns(count: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for window in _windows(count):
        events.append(
            _event("skald_writer", "accepted", window.start + timedelta(seconds=30))
        )
        events.append(_event("gaia", "accepted", window.start + timedelta(seconds=90)))
    return events


def _turn_records(count: int, *, timeout_after: bool = False) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = [
        {"index": index, "exit_code": 0, "success": True}
        for index in range(1, count + 1)
    ]
    if timeout_after:
        records.append({"index": count + 1, "exit_code": None, "success": None})
    return records


def _verdict(
    tmp_path: Path,
    events: list[dict[str, Any]],
    lines: list[str],
    *,
    turns: int = TURN_COUNT,
    timeout_after: bool = False,
    name: str,
) -> tuple[str, list[dict[str, Any]]]:
    usage_dir = tmp_path / name
    usage_dir.mkdir()
    (usage_dir / f"usage-{_BASE.date().isoformat()}.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    ledger = read_ledger(usage_dir, _BASE, _BASE + timedelta(hours=3))
    assert len(ledger) == len(events)
    attempts = join_attempts(
        ledger, parse_rejection_lines("\n".join(lines)), _windows(turns)
    )
    records = _turn_records(turns, timeout_after=timeout_after)
    return verdict(attempts, completed_turns(records)), attempts


def _with_rejection(
    seat: str, at_turn: Optional[int]
) -> tuple[list[dict[str, Any]], datetime]:
    events = _accepted_turns(TURN_COUNT)
    at = (
        _BASE + timedelta(minutes=10 * at_turn, seconds=60)
        if at_turn is not None
        else _BASE + timedelta(hours=2, minutes=30)
    )
    events.append(_event(seat, "rejected_validation", at))
    return events, at


def test_join_and_verdict(tmp_path: Path) -> None:
    """Decision 845-D1 classification, the per-seat join and the verdict."""

    # Twelve clean turns, plus an OpenAI event that never joins: null.
    clean = _accepted_turns(TURN_COUNT) + [
        _event(
            "experience_renderer",
            "accepted",
            _BASE + timedelta(minutes=15),
            provider="openai",
            model="gpt-5.6-terra",
        )
    ]
    result, attempts = _verdict(tmp_path, clean, [], name="clean")
    assert result == "null"
    assert len(attempts) == 2 * TURN_COUNT
    assert {attempt["turn"] for attempt in attempts} == set(range(1, 13))

    # One Gaia empty prompted rejection: reproduced.
    events, _ = _with_rejection("gaia", 3)
    empty_prompted = _line(
        transport="prompted",
        seat="gaia",
        stop_reason="end_turn",
        block_types="thinking",
        error=(
            "Anthropic prompted structured response did not include text output; "
            "stop_reason=end_turn block_types=thinking output_tokens=40"
        ),
    )
    result, attempts = _verdict(tmp_path, events, [empty_prompted], name="gaia")
    assert result == "reproduced"
    rejected = [a for a in attempts if a["outcome"] == "rejected_validation"]
    assert [(a["turn"], a["error_class"], a["flake"]) for a in rejected] == [
        (3, "empty_prompted", True)
    ]

    # A validation rejection alone: null.
    events, _ = _with_rejection("gaia", 4)
    validation = _line(
        transport="prompted",
        seat="gaia",
        stop_reason="end_turn",
        block_types="text",
        error="letter: Field required (missing)",
    )
    result, attempts = _verdict(tmp_path, events, [validation], name="validation")
    assert result == "null"
    assert [a["error_class"] for a in attempts if a["error_class"]] == ["validation"]

    # A text-bearing max_tokens rejection on Gaia: null.
    events, _ = _with_rejection("gaia", 5)
    text_bearing = _line(
        transport="prompted",
        seat="gaia",
        stop_reason="max_tokens",
        block_types="thinking,text",
        error=(
            "Anthropic structured response stopped at the output-token limit "
            "before complete structured output; stop_reason=max_tokens "
            "block_types=thinking,text output_tokens=40"
        ),
    )
    result, attempts = _verdict(tmp_path, events, [text_bearing], name="text")
    assert result == "null"
    rejected = [a for a in attempts if a["outcome"] == "rejected_validation"]
    assert [
        (a["error_class"], a["text_bearing_stop"], a["flake"]) for a in rejected
    ] == [("max_tokens", True, False)]

    # A native max_tokens rejection with only thinking: reproduced.
    events, _ = _with_rejection("skald_writer", 6)
    native_cut = _line(
        transport="native",
        seat="skald_writer",
        stop_reason="max_tokens",
        block_types="thinking",
        error=(
            "Anthropic structured response stopped at the output-token limit "
            "before complete structured output; stop_reason=max_tokens "
            "block_types=thinking output_tokens=40"
        ),
    )
    result, _ = _verdict(tmp_path, events, [native_cut], name="native_cut")
    assert result == "reproduced"

    # An empty native rejection on a follow-story seat: reproduced.
    events, _ = _with_rejection("summaries", None)
    empty_native = _line(
        transport="native",
        seat="summaries",
        stop_reason="end_turn",
        block_types="thinking",
        error=(
            "Anthropic structured response did not include JSON output; "
            "stop_reason=end_turn block_types=thinking output_tokens=40"
        ),
    )
    result, attempts = _verdict(tmp_path, events, [empty_native], name="summaries")
    assert result == "reproduced"
    rejected = [a for a in attempts if a["outcome"] == "rejected_validation"]
    assert [(a["turn"], a["seat"], a["error_class"]) for a in rejected] == [
        (None, "summaries", "empty_native")
    ]

    # Eleven completed turns: incomplete.
    result, _ = _verdict(
        tmp_path, _accepted_turns(TURN_COUNT - 1), [], turns=11, name="eleven"
    )
    assert result == "incomplete"

    # Eleven completed turns plus a timed-out turn: incomplete.
    result, _ = _verdict(
        tmp_path,
        _accepted_turns(TURN_COUNT - 1),
        [],
        turns=11,
        timeout_after=True,
        name="timeout",
    )
    assert result == "incomplete"

    # A rejected event with no rejection line: the join refuses it.
    events, _ = _with_rejection("gaia", 7)
    with pytest.raises(RuntimeError, match="seat gaia: 1 .* but 0 rejection"):
        _verdict(tmp_path, events, [], name="unpaired")


def test_write_evidence_writes_every_file(tmp_path: Path) -> None:
    """The evidence writer the paid run ends with runs offline, without prose."""

    usage_dir = tmp_path / "usage"
    usage_dir.mkdir()
    events, _ = _with_rejection("gaia", 2)
    (usage_dir / f"usage-{_BASE.date().isoformat()}.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    ledger = read_ledger(usage_dir, _BASE, _BASE + timedelta(hours=3))
    line = _line(
        transport="prompted",
        seat="gaia",
        stop_reason="end_turn",
        block_types="text",
        error="letter: Field required (missing)",
    )
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    turns = [
        {
            "index": window.index,
            "input_kind": "choice",
            "exit_code": 0,
            "success": True,
            "code": None,
            "session_id": f"session-{window.index}",
            "seconds": 1.5,
        }
        for window in _windows(TURN_COUNT)
    ]

    result = write_evidence(
        evidence,
        events_all=ledger,
        rejections=parse_rejection_lines(line),
        turns=turns,
        turn_windows=_windows(TURN_COUNT),
        stop_reason="completed",
        worst=8,
    )

    assert result == "null"
    for name in ("attempts.jsonl", "turns.jsonl", "ledger_all.jsonl", "summary.md"):
        assert (evidence / name).is_file(), name
    assert len((evidence / "attempts.jsonl").read_text().splitlines()) == len(events)
    summary = (evidence / "summary.md").read_text()
    assert "- Verdict: `null`" in summary
    assert f"- Fable calls: {len(events)} against `CALL_CAP` 30" in summary
    assert "- Worst case per turn (`worst`): 8" in summary


def test_probe_lane_refuses_unset_and_play_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe never defaults its lane and never binds the play port."""

    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)
    with pytest.raises(RuntimeError, match="unset"):
        probe_lane()
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8002")
    with pytest.raises(RuntimeError, match="play port"):
        probe_lane()
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8031")
    assert probe_lane() == 8031
    monkeypatch.delenv("NEXUS_GATEWAY_PORT")
