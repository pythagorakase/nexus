"""Provider-boundary usage recorder regression tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import multiprocessing
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import Any, Iterator

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIChatModelSettings,
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.openai import OpenAIProvider as PydanticOpenAIProvider
from pydantic_ai.settings import ModelSettings
import pytest

from nexus import cli
from nexus.telemetry import usage as usage_telemetry
from nexus.telemetry.usage import (
    UsageEvent,
    UsageReadError,
    record_pydantic_ai_result,
    record_usage_event,
    request_generation_profile,
    summarize_usage,
)
from scripts.api_anthropic import AnthropicProvider
from scripts.api_openai import OpenAIProvider
from tests.model_registry_helpers import registry_model


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
        def create(self, **_kwargs: object) -> SimpleNamespace:
            return response

    provider = OpenAIProvider(
        model="TEST",
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
    assert "USAGE provider=openai model=TEST" in caplog.text

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
        def create(self, **_kwargs: object) -> SimpleNamespace:
            return next(responses)

    writer = OpenAIProvider(
        model=registry_model("openai"),
        api_key="test-key",
        usage_provider_name="openai",
        usage_seat="skald_writer",
    )
    writer.client = SimpleNamespace(responses=FakeResponses())
    gaia = OpenAIProvider(
        model="TEST",
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
        registry_model("openai"),
        "TEST",
    ]
    assert summary["providers"]["openai"]["total"] == 25


def test_usage_line_records_the_generation_profile_each_request_sent(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses = iter(
        [
            _response("gaia", input_tokens=8, output_tokens=3, response_id="r1"),
            _response("mock", input_tokens=8, output_tokens=3, response_id="r2"),
        ]
    )

    class FakeResponses:
        def create(self, **_kwargs: object) -> SimpleNamespace:
            return next(responses)

    # TEST declares no reasoning, so its request carries no effort at all.
    providers = [
        OpenAIProvider(
            model=model,
            api_key="test-key",
            reasoning_effort="high",
            max_output_tokens=allowance,
            usage_provider_name="openai",
            usage_seat="gaia",
        )
        for model, allowance in ((registry_model("openai"), 1234), ("TEST", 4321))
    ]
    with caplog.at_level(logging.INFO, logger="nexus.usage"):
        for provider in providers:
            provider.client = SimpleNamespace(responses=FakeResponses())
            provider.get_structured_completion("prompt", _StructuredAnswer)

    summary = summarize_usage(usage_dir=tmp_path / "usage")
    assert [
        (event["seat"], event["reasoning_effort"], event["max_output_tokens"])
        for event in summary["events"]
    ] == [("gaia", "high", 1234), ("gaia", None, 4321)]
    assert "seat=gaia" in caplog.text
    assert "effort=high max_output=1234" in caplog.text
    assert "effort=- max_output=4321" in caplog.text


def test_generation_profile_reads_anthropic_and_chat_request_bodies() -> None:
    anthropic = AnthropicProvider(
        model=registry_model("anthropic"),
        api_key="test-key",
        reasoning_effort="low",
        max_tokens=2048,
    )
    chat = OpenAIProvider(
        model=registry_model("local"),
        api_key="test-key",
        base_url="http://127.0.0.1:1234/v1",
        structured_transport="chat_completions",
        max_output_tokens=512,
        request_params={"reasoning": {"effort": "low"}},
    )

    assert request_generation_profile(
        anthropic._build_prompted_structured_request_params("prompt")
    ) == ("low", 2048)
    assert request_generation_profile(
        chat._build_chat_structured_request_params("prompt", _StructuredAnswer)
    ) == ("low", 512)
    assert request_generation_profile(None) == (None, None)


@contextmanager
def _capturing_openai_server(bodies: list[dict[str, Any]]) -> Iterator[str]:
    """Serve minimal OpenAI envelopes over loopback and keep each request body."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            bodies.append(body)
            message = {"role": "assistant", "content": "Done"}
            if self.path.endswith("chat/completions"):
                response: dict[str, Any] = {
                    "id": "chatcmpl-profile",
                    "object": "chat.completion",
                    "created": 1,
                    "model": body["model"],
                    "choices": [
                        {"index": 0, "message": message, "finish_reason": "stop"}
                    ],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 1,
                        "total_tokens": 6,
                    },
                }
            else:
                response = {
                    "id": "resp_profile",
                    "object": "response",
                    "created_at": 1,
                    "model": body["model"],
                    "status": "completed",
                    "usage": {
                        "input_tokens": 5,
                        "output_tokens": 1,
                        "total_tokens": 6,
                    },
                    "output": [
                        {
                            "id": "msg_profile",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Done",
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                }
            payload = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()


def _sent_wire_profile(body: dict[str, Any]) -> tuple[str | None, int | None]:
    """Read the effort and output allowance from a Pydantic AI request body."""

    if "messages" in body:
        return body.get("reasoning_effort"), body.get("max_completion_tokens")
    return (body.get("reasoning") or {}).get("effort"), body.get("max_output_tokens")


@pytest.mark.parametrize(
    ("model_class", "model_settings"),
    [
        pytest.param(
            OpenAIResponsesModel,
            ModelSettings(max_tokens=321),
            id="responses-allowance-only",
        ),
        pytest.param(
            OpenAIResponsesModel,
            OpenAIResponsesModelSettings(max_tokens=321, openai_reasoning_effort="low"),
            id="responses-effort",
        ),
        pytest.param(
            OpenAIChatModel,
            ModelSettings(max_tokens=321),
            id="chat-allowance-only",
        ),
        pytest.param(
            OpenAIChatModel,
            OpenAIChatModelSettings(max_tokens=321, openai_reasoning_effort="high"),
            id="chat-effort",
        ),
    ],
)
def test_pydantic_ai_usage_records_the_profile_the_run_sent(
    model_class: Any,
    model_settings: ModelSettings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A real Pydantic AI run's ledger profile matches the bodies it posted.

    The loopback server stands in for the provider; the Pydantic AI client,
    request construction, and HTTP exchange are real.
    """

    bodies: list[dict[str, Any]] = []
    with _capturing_openai_server(bodies) as base_url:
        model = model_class(
            "TEST",
            provider=PydanticOpenAIProvider(base_url=base_url, api_key="test-key"),
        )
        result = Agent(model).run_sync("Continue.", model_settings=model_settings)
        with caplog.at_level(logging.INFO, logger="nexus.usage"):
            record_pydantic_ai_result(
                result,
                provider="test",
                model="TEST",
                seat="wizard",
                model_settings=model_settings,
            )

    assert len(bodies) == 1
    sent_effort, sent_allowance = _sent_wire_profile(bodies[0])
    assert (sent_effort, sent_allowance) == (
        model_settings.get("openai_reasoning_effort"),
        321,
    )
    event = summarize_usage(usage_dir=tmp_path / "usage")["events"][0]
    assert event["transport"] == "pydantic_ai"
    assert (event["reasoning_effort"], event["max_output_tokens"]) == (
        sent_effort,
        sent_allowance,
    )
    assert f"effort={sent_effort or '-'} max_output=321" in caplog.text


def test_pydantic_ai_usage_requires_the_run_output_allowance() -> None:
    """Without max_tokens the ledger could not state what the run sent."""

    result = SimpleNamespace(
        usage=lambda: SimpleNamespace(
            requests=1, input_tokens=5, output_tokens=1, total_tokens=6, details={}
        )
    )
    with pytest.raises(ValueError, match="requires the run's max_tokens"):
        record_pydantic_ai_result(
            result,
            provider="anthropic",
            model="wizard-model",
            seat="wizard",
            model_settings=ModelSettings(),
        )


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
        def create(self, **_kwargs: object) -> SimpleNamespace:
            return next(responses)

    provider = OpenAIProvider(
        model="TEST",
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


def test_exhausted_repair_labels_final_attempt_rejected_validation(
    tmp_path: Path,
) -> None:
    """An exhausted repair attempt records what happened to IT, not the loop."""

    bad = SimpleNamespace(
        id="resp_bad",
        output_parsed=None,
        output_text='{"wrong":"shape"}',
        usage=_usage(9, 2),
    )

    class FakeResponses:
        def create(self, **_kwargs: object) -> SimpleNamespace:
            return bad

    provider = OpenAIProvider(
        model="TEST",
        api_key="test-key",
        structured_output_retries=1,
        usage_provider_name="openai",
        usage_seat="trait_input_derivation",
    )
    provider.client = SimpleNamespace(responses=FakeResponses())

    with pytest.raises(Exception):
        provider.get_structured_completion("prompt", _StructuredAnswer)

    summary = summarize_usage(usage_dir=tmp_path / "usage")
    assert [event["outcome"] for event in summary["events"]] == [
        "rejected_validation",
        "rejected_validation",
    ]
    assert summary["providers"]["openai"]["total"] == 22


def test_pydantic_ai_all_zero_usage_is_unknown_not_zero(tmp_path: Path) -> None:
    """pydantic-ai RunUsage zero-fills unreported counts; record them as unknown."""

    result = SimpleNamespace(
        usage=lambda: SimpleNamespace(
            requests=1,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            details={},
        )
    )

    record_pydantic_ai_result(
        result,
        provider="openai",
        model="wizard-model",
        seat="wizard",
        model_settings=ModelSettings(max_tokens=64),
    )

    summary = summarize_usage(usage_dir=tmp_path / "usage")
    event = summary["events"][0]
    assert event["input_tokens"] is None
    assert event["output_tokens"] is None
    assert event["total_tokens"] is None
    assert summary["providers"]["openai"]["total"] == 0
    assert summary["providers"]["openai"]["unknown_usage_events"] == 1


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
        model_settings=ModelSettings(max_tokens=64),
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
        def create(self, **_kwargs: object) -> SimpleNamespace:
            return response

    provider = OpenAIProvider(
        model="TEST",
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
