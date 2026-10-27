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
from nexus.cli_contract import error_envelope
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
    turn_outcome,
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

    # Rejections on two seats, Gaia twice: each seat pairs its k-th rejected
    # event with its own k-th line, whatever the global line order.
    events = _accepted_turns(TURN_COUNT)
    events.append(
        _event("gaia", "rejected_validation", _BASE + timedelta(minutes=30, seconds=60))
    )
    events.append(
        _event(
            "skald_writer",
            "rejected_validation",
            _BASE + timedelta(minutes=40, seconds=60),
        )
    )
    events.append(
        _event("gaia", "rejected_validation", _BASE + timedelta(minutes=50, seconds=60))
    )
    writer_validation = _line(
        transport="native",
        seat="skald_writer",
        stop_reason="end_turn",
        block_types="thinking,text",
        error="narrative: Field required (missing)",
    )
    gaia_validation = _line(
        transport="prompted",
        seat="gaia",
        stop_reason="end_turn",
        block_types="text",
        error="letter: Field required (missing)",
    )
    result, attempts = _verdict(
        tmp_path,
        events,
        [writer_validation, empty_prompted, gaia_validation],
        name="two_seats",
    )
    assert result == "reproduced"
    rejected = [a for a in attempts if a["outcome"] == "rejected_validation"]
    assert [
        (a["turn"], a["seat"], a["transport"], a["block_types"], a["error_class"])
        for a in rejected
    ] == [
        (3, "gaia", "prompted", "thinking", "empty_prompted"),
        (4, "skald_writer", "native", "thinking,text", "validation"),
        (5, "gaia", "prompted", "text", "validation"),
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
    assert "- Excess over `CALL_CAP`: 0" in summary
    assert "### Fable Calls Beyond CALL_CAP by Seat\n\nNone." in summary

    # Follow-story calls push the run past CALL_CAP: the summary names the
    # seats of the calls beyond the cap, in ledger time order.
    late = _BASE + timedelta(hours=2, minutes=40)
    over = events + [
        _event("experience_renderer", "accepted", late + timedelta(minutes=i))
        for i in range(5)
    ]
    over += [
        _event("summaries", "accepted", late + timedelta(minutes=10 + i))
        for i in range(2)
    ]
    over.append(
        _event("correspondence_compaction", "accepted", late + timedelta(minutes=15))
    )
    assert len(over) == 33
    usage_over = tmp_path / "usage_over"
    usage_over.mkdir()
    (usage_over / f"usage-{_BASE.date().isoformat()}.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in over)
    )
    evidence_over = tmp_path / "evidence_over"
    evidence_over.mkdir()
    write_evidence(
        evidence_over,
        events_all=read_ledger(usage_over, _BASE, _BASE + timedelta(hours=3)),
        rejections=parse_rejection_lines(line),
        turns=turns,
        turn_windows=_windows(TURN_COUNT),
        stop_reason="completed",
        worst=8,
    )
    summary_over = (evidence_over / "summary.md").read_text()
    assert "- Fable calls: 33 against `CALL_CAP` 30" in summary_over
    assert "- Excess over `CALL_CAP`: 3" in summary_over
    beyond = summary_over.split("### Fable Calls Beyond CALL_CAP by Seat\n\n")[1]
    beyond_rows = beyond.split("\n\n")[0].splitlines()
    assert beyond_rows[2:] == [
        "| correspondence_compaction | 1 |",
        "| summaries | 2 |",
    ]

    # A run that aborts before its first turn records the aborted label and
    # no completed turn, never "completed".
    evidence_aborted = tmp_path / "evidence_aborted"
    evidence_aborted.mkdir()
    aborted = write_evidence(
        evidence_aborted,
        events_all=[],
        rejections=[],
        turns=[],
        turn_windows=[],
        stop_reason="aborted:RuntimeError",
        worst=8,
    )
    assert aborted == "incomplete"
    summary_aborted = (evidence_aborted / "summary.md").read_text()
    assert "- Stop reason: `aborted:RuntimeError`" in summary_aborted
    assert f"- Turns completed: 0 of {TURN_COUNT}" in summary_aborted
    assert "`completed`" not in summary_aborted


def test_turn_outcome_reads_the_failure_envelope_on_stderr() -> None:
    """A failed turn's CLI code and session id come from the stderr envelope.

    ``continue --json`` prints a failure envelope on stderr, so the turn that
    ends the run still records its ``code`` and ``partial.session_id``; the
    envelope's ``error`` text is never kept.
    """

    envelope = json.dumps(
        error_envelope("domain_failure", "x", {"session_id": "s"}),
        indent=2,
        sort_keys=True,
    )
    failed = turn_outcome(4, "", envelope)
    assert failed["code"] == "domain_failure"
    assert failed["session_id"] == "s"
    assert "x" not in failed.values()
    assert set(failed) == {"success", "code", "session_id"}
    # Log lines the child wrote to stderr before the envelope are skipped.
    noisy = turn_outcome(4, "", "WARNING something\n" + envelope + "\n")
    assert (noisy["code"], noisy["session_id"]) == ("domain_failure", "s")
    # Success is read from stdout; stderr is ignored.
    ok = turn_outcome(
        0, json.dumps({"success": True, "session_id": "t"}), "WARNING noise\n"
    )
    assert ok == {"success": True, "code": None, "session_id": "t"}
    # A timed-out turn records nothing.
    assert turn_outcome(None, "", "") == {
        "success": None,
        "code": None,
        "session_id": None,
    }


def test_probe_lane_refuses_unset_and_play_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe never defaults its lane and never binds an owner runtime port."""

    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)
    with pytest.raises(RuntimeError, match="unset"):
        probe_lane()
    for owner_port in ("8002", "8003"):
        monkeypatch.setenv("NEXUS_GATEWAY_PORT", owner_port)
        with pytest.raises(RuntimeError, match="owner's runtime port"):
            probe_lane()
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8031")
    assert probe_lane() == 8031
    monkeypatch.delenv("NEXUS_GATEWAY_PORT")
