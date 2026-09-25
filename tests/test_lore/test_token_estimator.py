"""Registry estimator and real loopback TEST exchange proof."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
from threading import Thread
from typing import Iterator

import pytest
import tiktoken
import tomlkit

from nexus.agents.lore.utils.chunk_operations import calculate_chunk_tokens
from nexus.config import load_settings
from nexus.config.story_model import StorySettings, resolve_seat
from nexus.telemetry.prompt_window import estimator_for
from nexus.telemetry.usage import summarize_usage
from scripts.api_openai import OpenAIProvider

SENTENCE = "The quick brown fox jumps over the lazy dog."


@pytest.mark.parametrize(
    "model",
    [
        entry.id
        for provider in load_settings().global_.model.api_models.values()
        for entry in provider.models
    ],
)
def test_registry_token_estimator(model: str) -> None:
    count = estimator_for(model)(SENTENCE)
    assert isinstance(count, int) and count > 0
    if model == "TEST":
        assert count == len(tiktoken.get_encoding("o200k_base").encode(SENTENCE))


def test_chunk_token_estimate_resolves_writer_and_story_pin() -> None:
    assert calculate_chunk_tokens(SENTENCE) == estimator_for(
        resolve_seat("skald").model
    )(SENTENCE)
    story = StorySettings(skald_model="TEST")
    assert calculate_chunk_tokens(SENTENCE, story=story) == estimator_for("TEST")(
        SENTENCE
    )


def test_registered_approximation_counts_without_a_provider_call() -> None:
    from nexus.telemetry.prompt_window import rendered_request_counter

    settings = load_settings()
    entry = next(
        entry
        for entry in settings.global_.model.api_models["openrouter"].models
        if entry.tokenizer_encoding and entry.token_count_safety_margin
    )
    provider = OpenAIProvider(
        model=entry.id,
        api_key="unused",
        usage_provider_name="openrouter",
        system_prompt="Local estimate.",
    )
    count = rendered_request_counter(provider)
    assert count(SENTENCE) == estimator_for(entry.id)(SENTENCE) + estimator_for(
        entry.id
    )("Local estimate.")
    assert provider._client is None


def test_settings_reject_missing_tokenizer_on_unused_entry(tmp_path: Path) -> None:
    settings = tomlkit.parse(Path("nexus.toml").read_text())
    entry = settings["global"]["model"]["api_models"]["openrouter"]["models"][0]
    entry.pop("tokenizer_encoding", None)
    entry.pop("tokenizer_repository", None)
    path = tmp_path / "settings.toml"
    path.write_text(tomlkit.dumps(settings))
    with pytest.raises(
        ValueError, match=f"No local tokenizer declared for '{entry['id']}'"
    ):
        load_settings(path)


def test_settings_reject_remote_code_tokenizer_without_executing_it(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "custom-tokenizer"
    repository.mkdir()
    (repository / "tokenizer_config.json").write_text(
        json.dumps(
            {
                "tokenizer_class": "CustomTokenizer",
                "auto_map": {
                    "AutoTokenizer": ["tokenization_custom.CustomTokenizer", None]
                },
            }
        )
    )
    (repository / "tokenization_custom.py").write_text(
        "raise AssertionError('Remote tokenizer code executed')\n"
    )
    settings = tomlkit.parse(Path("nexus.toml").read_text())
    entry = settings["global"]["model"]["api_models"]["openrouter"]["models"][0]
    entry.pop("tokenizer_encoding", None)
    entry["tokenizer_repository"] = str(repository)
    path = tmp_path / "settings.toml"
    path.write_text(tomlkit.dumps(settings))
    with pytest.raises(ValueError, match="trust_remote_code=False") as error:
        load_settings(path)
    assert entry["id"] in str(error.value)
    assert "tokenizer_encoding" in str(error.value)
    assert "Remote tokenizer code executed" not in str(error.value)


@contextmanager
def token_test_server() -> Iterator[str]:
    """Serve OpenAI envelopes over HTTP with independently counted TEST usage."""
    encoding = tiktoken.get_encoding("o200k_base")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert request["model"] == "TEST"
            messages = request.get("input", request.get("messages"))
            reported = sum(
                len(encoding.encode(message["content"])) for message in messages
            )
            usage = {
                "input_tokens": reported,
                "output_tokens": 1,
                "total_tokens": reported + 1,
            }
            response = {
                "id": "resp_token_estimate",
                "object": "response",
                "created_at": 1,
                "model": "TEST",
                "status": "completed",
                "usage": usage,
                "output": [
                    {
                        "id": "msg_token_estimate",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "Done", "annotations": []}
                        ],
                    }
                ],
            }
            if self.path.endswith("chat/completions"):
                response.update(
                    object="chat.completion",
                    created=1,
                    choices=[
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Done"},
                            "finish_reason": "stop",
                        }
                    ],
                    usage={
                        "prompt_tokens": reported,
                        "completion_tokens": 1,
                        "total_tokens": reported + 1,
                    },
                )
            payload = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("transport", ["responses", "chat_completions"])
def test_token_drift_real_test_http_exchange(transport, tmp_path, caplog) -> None:
    with token_test_server() as base_url:
        provider = OpenAIProvider(
            model="TEST",
            api_key="test-key",
            base_url=base_url,
            usage_provider_name="test",
            usage_seat="skald_writer",
            system_prompt="Count this sentence.",
        )
        with caplog.at_level(logging.INFO, logger="nexus.usage"):
            if transport == "responses":
                result = provider.get_completion(SENTENCE)
            else:
                result = provider._get_completion_chat_completions(SENTENCE)
        provider.client.close()
    expected = estimator_for("TEST")(SENTENCE) + estimator_for("TEST")(
        "Count this sentence."
    )
    line = f"token_estimate seat=skald_writer model=TEST estimated={expected} reported={expected} ratio=1.00"
    assert [
        record.message
        for record in caplog.records
        if record.message.startswith("token_estimate")
    ] == [line]
    assert result.input_tokens == expected
    event = summarize_usage(usage_dir=tmp_path / "usage")["events"][0]
    assert event["input_tokens"] == expected
    assert event["total_tokens"] == expected + 1
    print(line)


def test_token_drift_real_pydantic_ai_exchange(tmp_path, caplog) -> None:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider as PydanticOpenAIProvider
    from nexus.telemetry.usage import record_pydantic_ai_result

    with token_test_server() as base_url:
        model = OpenAIChatModel(
            "TEST",
            provider=PydanticOpenAIProvider(base_url=base_url, api_key="test-key"),
        )
        result = Agent(model, system_prompt="Count this sentence.").run_sync(SENTENCE)
        with caplog.at_level(logging.INFO, logger="nexus.usage"):
            record_pydantic_ai_result(
                result, provider="test", model="TEST", seat="wizard"
            )
    lines = [
        record.message
        for record in caplog.records
        if record.message.startswith("token_estimate")
    ]
    assert len(lines) == 1 and lines[0].endswith("ratio=1.00")
    assert (
        summarize_usage(usage_dir=tmp_path / "usage")["events"][0]["aggregate"] is True
    )


@pytest.mark.requires_postgres
def test_token_estimate_manifest_keeps_both_counts() -> None:
    from contextlib import closing
    from uuid import uuid4
    from nexus.telemetry.attempt_manifest import (
        manifest_scope,
        start_attempt,
        record_token_counts,
    )
    from nexus.telemetry.prompt_window import PromptWindowRecord
    from tests.pg_fixtures import connect, disposable_slot_database

    with disposable_slot_database("qa640_818_estimate") as dbname:
        session = str(uuid4())
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO narrative_generation_sessions (session_id, operation, status) VALUES (%s,'continue','initiated')",
                (session,),
            )
        record = PromptWindowRecord(
            generation_session=session,
            seat="skald_writer",
            attempt=1,
            model="TEST",
            block_tokens={"story": 10},
            input_tokens=10,
            effective_ceiling=100,
            policy_headroom=0,
            headroom=90,
        )
        with manifest_scope(lambda: connect(dbname)):
            start_attempt(
                record,
                blocks=[],
                system_prompt="",
                prompt=SENTENCE,
                settings={},
                wire_schema={},
            )
            record_token_counts(session, "skald_writer", 1, 10, 12)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT window_record FROM generation_attempt_manifests WHERE generation_session_id=%s",
                (session,),
            )
            window = cur.fetchone()[0]
        assert window["input_tokens"] == 10
        assert window["estimated_input_tokens"] == 10
        assert window["reported_input_tokens"] == 12
