"""Provider-boundary usage recorder regression tests."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import multiprocessing
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel
import pytest

from nexus import cli
from nexus.telemetry import usage as usage_telemetry
from nexus.telemetry.usage import (
    UsageEvent,
    UsageReadError,
    record_pydantic_ai_result,
    record_usage_event,
    summarize_usage,
)
from scripts.api_openai import OpenAIProvider


class _StructuredAnswer(BaseModel):
    value: str


def _usage(
    input_tokens: int,
    output_tokens: int,
    *,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )


def _response(
    value: str,
    *,
    input_tokens: int,
    output_tokens: int,
    response_id: str,
) -> SimpleNamespace:
    parsed = _StructuredAnswer(value=value)
    return SimpleNamespace(
        id=response_id,
        output_parsed=parsed,
        output_text=parsed.model_dump_json(),
        usage=_usage(input_tokens, output_tokens),
        service_tier="default",
    )


def _event(
    *,
    ts: str,
    provider: str = "openai",
    seat: str = "skald_single_pass",
    total: int | None = 3,
    run_id: str | None = None,
) -> UsageEvent:
    return UsageEvent(
        ts=ts,
        provider=provider,
        model=f"{provider}-model",
        seat=seat,
        run_id=run_id,
        attempt=1,
        outcome="accepted",
        transport="responses",
        input_tokens=None if total is None else 1,
        output_tokens=None if total is None else total - 1,
        total_tokens=total,
        cached_input_tokens=None,
        cache_creation_tokens=None,
        reasoning_tokens=None,
        aggregate=False,
        requests=None,
    )


def _concurrent_writer(path: str, process_index: int, events: int) -> None:
    usage_telemetry._config = usage_telemetry._RecorderConfig(
        enabled=True,
        usage_dir=Path(path),
        daily_allowance={},
    )
    for event_index in range(events):
        record_usage_event(
            _event(
                ts="2026-07-29T12:00:00Z",
                run_id=f"{process_index}-{event_index}",
            )
        )


def test_single_responses_call_records_jsonl_log_and_cli_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = _response(
        "done",
        input_tokens=123,
        output_tokens=45,
        response_id="resp_single",
    )

    class FakeResponses:
        def parse(self, **_kwargs: object) -> SimpleNamespace:
            return response

    provider = OpenAIProvider(
        model="gpt-test",
        api_key="test-key",
        usage_provider_name="openai",
        usage_seat="skald_single_pass",
    )
    provider.client = SimpleNamespace(responses=FakeResponses())

    with caplog.at_level(logging.INFO, logger="nexus.usage"):
        parsed, _llm_response = provider.get_structured_completion(
            "prompt", _StructuredAnswer
        )

    assert parsed.value == "done"
    day = datetime.now(timezone.utc).date().isoformat()
    path = tmp_path / "usage" / f"usage-{day}.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["input_tokens"] == 123
    assert events[0]["output_tokens"] == 45
    assert events[0]["total_tokens"] == 168
    assert "USAGE provider=openai model=gpt-test" in caplog.text

    monkeypatch.setattr(
        "sys.argv",
        ["nexus", "usage", "--json", "--day", day],
    )
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["usage"]["events"][0]["request_id"] == "resp_single"
    assert payload["usage"]["openai_day_total"]["total_tokens"] == 168


def test_two_provider_passes_keep_seats_models_and_sum(tmp_path: Path) -> None:
    responses = iter(
        [
            _response(
                "writer",
                input_tokens=10,
                output_tokens=4,
                response_id="resp_writer",
            ),
            _response(
                "gaia",
                input_tokens=8,
                output_tokens=3,
                response_id="resp_gaia",
            ),
        ]
    )

    class FakeResponses:
        def parse(self, **_kwargs: object) -> SimpleNamespace:
            return next(responses)

    writer = OpenAIProvider(
        model="writer-model",
        api_key="test-key",
        usage_provider_name="openai",
        usage_seat="skald_writer",
    )
    writer.client = SimpleNamespace(responses=FakeResponses())
    gaia = OpenAIProvider(
        model="gaia-model",
        api_key="test-key",
        usage_provider_name="openai",
        usage_seat="gaia",
    )
    gaia.client = SimpleNamespace(responses=FakeResponses())

    writer.get_structured_completion("writer", _StructuredAnswer)
    gaia.get_structured_completion("gaia", _StructuredAnswer)

    summary = summarize_usage(usage_dir=tmp_path / "usage")
    assert [event["seat"] for event in summary["events"]] == [
        "skald_writer",
        "gaia",
    ]
    assert [event["model"] for event in summary["events"]] == [
        "writer-model",
        "gaia-model",
    ]
    assert summary["providers"]["openai"]["total"] == 25


def test_repair_loop_records_rejected_then_accepted(tmp_path: Path) -> None:
    responses = iter(
        [
            SimpleNamespace(
                id="resp_rejected",
                output_parsed=None,
                output_text='{"wrong":"shape"}',
                usage=_usage(20, 5),
            ),
            _response(
                "repaired",
                input_tokens=24,
                output_tokens=6,
                response_id="resp_accepted",
            ),
        ]
    )

    class FakeResponses:
        def parse(self, **_kwargs: object) -> SimpleNamespace:
            return next(responses)

    provider = OpenAIProvider(
        model="repair-model",
        api_key="test-key",
        structured_output_retries=1,
        usage_provider_name="openai",
        usage_seat="geo_authoring",
    )
    provider.client = SimpleNamespace(responses=FakeResponses())

    parsed, _response_value = provider.get_structured_completion(
        "prompt", _StructuredAnswer
    )

    assert parsed.value == "repaired"
    summary = summarize_usage(usage_dir=tmp_path / "usage")
    assert [event["outcome"] for event in summary["events"]] == [
        "rejected_validation",
        "accepted",
    ]
    assert [event["attempt"] for event in summary["events"]] == [1, 2]
    assert summary["providers"]["openai"]["total"] == 55


def test_pydantic_ai_aggregate_records_internal_request_count(
    tmp_path: Path,
) -> None:
    result = SimpleNamespace(
        usage=lambda: SimpleNamespace(
            requests=3,
            input_tokens=30,
            output_tokens=12,
            total_tokens=42,
            details={"cached_input_tokens": 7, "reasoning_tokens": 4},
        )
    )

    record_pydantic_ai_result(
        result,
        provider="openai",
        model="wizard-model",
        seat="wizard",
        slot=2,
        run_id="thread-1",
    )

    event = summarize_usage(usage_dir=tmp_path / "usage")["events"][0]
    assert event["aggregate"] is True
    assert event["outcome"] == "aggregate"
    assert event["requests"] == 3
    assert event["total_tokens"] == 42


def test_missing_usage_stays_null_and_counts_unknown(tmp_path: Path) -> None:
    response = _response(
        "done",
        input_tokens=1,
        output_tokens=1,
        response_id="resp_unknown",
    )
    response.usage = None

    class FakeResponses:
        def parse(self, **_kwargs: object) -> SimpleNamespace:
            return response

    provider = OpenAIProvider(
        model="unknown-model",
        api_key="test-key",
        usage_provider_name="openai",
        usage_seat="skald_single_pass",
    )
    provider.client = SimpleNamespace(responses=FakeResponses())
    provider.get_structured_completion("prompt", _StructuredAnswer)

    summary = summarize_usage(usage_dir=tmp_path / "usage")
    event = summary["events"][0]
    assert event["input_tokens"] is None
    assert event["output_tokens"] is None
    assert event["total_tokens"] is None
    assert summary["providers"]["openai"]["total"] == 0
    assert summary["providers"]["openai"]["unknown_usage_events"] == 1


def test_concurrent_process_appends_are_complete_and_exact(tmp_path: Path) -> None:
    process_count = 4
    events_per_process = 40
    usage_dir = tmp_path / "concurrent"
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(
            target=_concurrent_writer,
            args=(str(usage_dir), process_index, events_per_process),
        )
        for process_index in range(process_count)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    summary = summarize_usage(
        day="2026-07-29",
        usage_dir=usage_dir,
    )
    expected_events = process_count * events_per_process
    assert len(summary["events"]) == expected_events
    assert summary["providers"]["openai"]["total"] == expected_events * 3
    assert len({event["run_id"] for event in summary["events"]}) == expected_events


def test_openai_day_total_excludes_other_providers(tmp_path: Path) -> None:
    for provider in ("openai", "test", "local", "anthropic"):
        record_usage_event(
            _event(
                ts="2026-07-29T12:00:00Z",
                provider=provider,
                total=10,
            )
        )

    summary = summarize_usage(day="2026-07-29", usage_dir=tmp_path / "usage")
    assert summary["openai_day_total"]["total_tokens"] == 10
    assert summary["providers"]["test"]["total"] == 10
    assert summary["providers"]["local"]["total"] == 10
    assert summary["providers"]["anthropic"]["total"] == 10


def test_utc_midnight_routes_events_to_distinct_day_files(tmp_path: Path) -> None:
    record_usage_event(_event(ts="2026-07-29T23:59:59.999999Z", total=5))
    record_usage_event(_event(ts="2026-07-30T00:00:00Z", total=7))

    before = summarize_usage(day="2026-07-29", usage_dir=tmp_path / "usage")
    after = summarize_usage(day="2026-07-30", usage_dir=tmp_path / "usage")
    assert before["openai_day_total"]["total_tokens"] == 5
    assert after["openai_day_total"]["total_tokens"] == 7


def test_malformed_line_raises_with_path_and_line(tmp_path: Path) -> None:
    path = tmp_path / "usage" / "usage-2026-07-29.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(_event(ts="2026-07-29T12:00:00Z").model_dump(mode="json"))
        + "\n"
        + "{not-json}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        UsageReadError,
        match=r"usage-2026-07-29\.jsonl at line 2",
    ):
        summarize_usage(day="2026-07-29", usage_dir=tmp_path / "usage")


def test_relative_usage_dir_anchors_to_repo_root_not_config_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA lanes with NEXUS_RUNTIME_CONFIG elsewhere share one usage ledger."""

    repo_root = Path(usage_telemetry.__file__).resolve().parents[2]
    config_copy = tmp_path / "lane" / "nexus.toml"
    config_copy.parent.mkdir(parents=True)
    config_copy.write_text(
        (repo_root / "nexus.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config_copy))

    config = usage_telemetry._load_recorder_config()

    assert not config.usage_dir.is_relative_to(tmp_path)
    assert config.usage_dir == repo_root / ".nexus" / "runtime" / "usage"


def test_missing_day_file_is_valid_empty_summary(tmp_path: Path) -> None:
    summary = summarize_usage(
        day="2026-07-29",
        usage_dir=tmp_path / "missing",
    )
    assert summary["events"] == []
    assert summary["providers"] == {}
    assert summary["openai_day_total"] == {
        "total_tokens": 0,
        "unknown_usage_events": 0,
    }
