"""Registry estimator and real loopback TEST exchange proof."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import subprocess
import sys
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


def test_commit_probe_and_first_use_reject_remote_code_tokenizer(
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
    from scripts.validate_config_commit import validate_tokenizer_registry

    loaded = load_settings(path)  # Declaration is valid; no runtime roster probe.
    for check in (
        lambda: validate_tokenizer_registry(loaded),
        lambda: estimator_for(entry["id"], settings=loaded),
    ):
        with pytest.raises(ValueError, match="trust_remote_code=False") as error:
            check()
        assert entry["id"] in str(error.value)
        assert "tokenizer_encoding" in str(error.value)
        assert "Remote tokenizer code executed" not in str(error.value)


def test_settings_reject_unknown_encoding(tmp_path: Path) -> None:
    config = tomlkit.parse(Path("nexus.toml").read_text())
    entry = config["global"]["model"]["api_models"]["test"]["models"][0]
    entry["tokenizer_encoding"] = "missing-encoding"
    path = tmp_path / "settings.toml"
    path.write_text(tomlkit.dumps(config))
    with pytest.raises(ValueError, match="Model 'TEST': unknown tokenizer_encoding"):
        load_settings(path)


def test_commit_tokenizer_probe_timeout_names_entries() -> None:
    from scripts.validate_config_commit import validate_tokenizer_registry

    settings = load_settings()
    settings.global_.model.tokenizer_probe_timeout_seconds = 0.000001
    with pytest.raises(ValueError, match="Tokenizer probe failed") as error:
        validate_tokenizer_registry(settings)
    for provider in settings.global_.model.api_models.values():
        for entry in provider.models:
            if entry.tokenizer_repository:
                assert entry.id in str(error.value)
    assert "timed out" in str(error.value)


def test_empty_hf_cache_offline_test_provider(tmp_path: Path) -> None:
    # Fresh process: neither settings nor TEST may initialize Transformers/HF.
    code = """import sys
from nexus.config import load_settings
from scripts.api_openai import OpenAIProvider
from nexus.telemetry import usage
from pathlib import Path
usage._config = usage._RecorderConfig(enabled=False, usage_dir=Path(sys.argv[2]), daily_allowance={})
load_settings()
provider = OpenAIProvider(model="TEST", api_key="test", base_url=sys.argv[1], usage_provider_name="test")
result = provider.get_completion("Literal <|endoftext|> stays text.")
assert result.input_tokens > 0
provider.client.close()
assert "transformers" not in sys.modules
print("offline TEST exchange passed; Transformers not imported")
"""
    with token_test_server() as base_url:
        result = subprocess.run(
            [sys.executable, "-c", code, base_url, str(tmp_path / "usage")],
            env={
                **os.environ,
                "HF_HUB_OFFLINE": "1",
                "HF_HOME": str(tmp_path / "empty-hf"),
                "HUGGINGFACE_HUB_CACHE": str(tmp_path / "empty-hf" / "hub"),
                "TRANSFORMERS_CACHE": str(tmp_path / "empty-hf" / "transformers"),
            },
            capture_output=True,
            text=True,
            timeout=30,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "empty-hf").exists()
    print(result.stdout.strip())


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
                len(encoding.encode(message["content"], disallowed_special=()))
                for message in messages
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
@pytest.mark.parametrize("prompt", [SENTENCE, "Literal <|endoftext|> stays text."])
def test_token_drift_real_test_http_exchange(
    transport, prompt, tmp_path, caplog
) -> None:
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
                result = provider.get_completion(prompt)
            else:
                result = provider._get_completion_chat_completions(prompt)
        provider.client.close()
    expected = estimator_for("TEST")(prompt) + estimator_for("TEST")(
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


@pytest.mark.parametrize("transport", ["responses", "chat_completions"])
def test_drift_failure_does_not_break_real_exchange(
    transport, tmp_path, caplog
) -> None:
    from nexus.config.loader import settings_path_scope

    config = tomlkit.parse(Path("nexus.toml").read_text())
    entry = config["global"]["model"]["api_models"]["test"]["models"][0]
    entry.pop("tokenizer_encoding")
    entry["tokenizer_repository"] = str(tmp_path / "absent-tokenizer")
    path = tmp_path / "settings.toml"
    path.write_text(tomlkit.dumps(config))
    with token_test_server() as base_url, settings_path_scope(path):
        provider = OpenAIProvider(
            model="TEST",
            api_key="test",
            base_url=base_url,
            usage_provider_name="test",
            usage_seat="skald_writer",
        )
        with caplog.at_level(logging.INFO, logger="nexus.usage"):
            result = (
                provider.get_completion(SENTENCE)
                if transport == "responses"
                else provider._get_completion_chat_completions(SENTENCE)
            )
        provider.client.close()
    errors = [
        record
        for record in caplog.records
        if record.message.startswith("token_estimate_failed")
    ]
    assert len(errors) == 1 and errors[0].levelno == logging.ERROR
    assert "absent-tokenizer" in errors[0].message
    assert "\n" not in errors[0].message
    assert result.input_tokens == estimator_for("TEST")(SENTENCE)
    event = summarize_usage(usage_dir=tmp_path / "usage")["events"][0]
    assert event["input_tokens"] == result.input_tokens


@pytest.mark.requires_postgres
@pytest.mark.parametrize("override", [False, True])
def test_memory_admission_uses_resolved_writer_token_estimate(override: bool) -> None:
    """Clone-owned pin, real LOGON route, turn setup, and MEMNON SQL admission."""
    import asyncio
    from contextlib import closing
    from types import SimpleNamespace
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from nexus.agents.lore.logon_utility import LogonUtility
    from nexus.agents.lore.utils.token_budget import TokenBudgetManager
    from nexus.agents.lore.utils.turn_context import TurnContext
    from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
    from nexus.agents.memnon.memnon import MEMNON
    from nexus.config import load_settings_as_dict
    from nexus.config.story_model import read_story_settings
    from nexus.memory import ContextMemoryManager
    from tests.pg_fixtures import connect, disposable_slot_database, sqlalchemy_url

    settings = load_settings()
    model = next(
        entry.id
        for provider in settings.global_.model.api_models.values()
        for entry in provider.models
        if entry.tokenizer_repository and entry.id != settings.apex.model
    )
    text = "token_estimate"  # Hermes and o200k differ at this admission boundary.
    expected = estimator_for(model)(text)
    default = estimator_for(settings.apex.model)(text)
    assert expected != default
    with disposable_slot_database(
        "qa640_818_pin", story_pin="TEST" if override else model
    ) as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, storyteller_text) VALUES (%s, %s) RETURNING id",
                (text, text),
            )
            chunk_id = cur.fetchone()[0]
        runtime = load_settings_as_dict()
        memory = ContextMemoryManager(runtime, dbname=dbname)
        logon = LogonUtility(
            runtime,
            dbname=dbname,
            model_override=model if override else None,
            story_settings=read_story_settings(dbname),
        )
        lore = SimpleNamespace(
            settings=runtime,
            memory_manager=memory,
            token_manager=TokenBudgetManager(runtime),
            logon=logon,
            ensure_logon=lambda: None,
            enable_logon=True,
        )
        turn = TurnContext(turn_id="token-pin", user_input="1", start_time=0.0)
        asyncio.run(TurnCycleManager(lore).process_user_input(turn))
        assert turn.apex_model == model
        # A subsequent window refresh must not overwrite a request override.
        memory._refresh_story_settings()
        assert memory._estimate_tokens(text) == expected
        # Exercise the real SQL-only retrieval method without constructing
        # inference/embedding models that this path never uses.
        engine = create_engine(sqlalchemy_url(dbname))
        memnon = MEMNON.__new__(MEMNON)
        memnon.Session = sessionmaker(bind=engine)
        memory.incremental.memnon = memnon
        try:
            chunks, used = memory.incremental.expand_warm_slice(expected)
            assert [chunk["id"] for chunk in chunks] == [chunk_id]
            assert used == expected
            chunks, used = memory.incremental.expand_warm_slice(expected - 1)
            assert chunks == [] and used == 0
        finally:
            engine.dispose()
        print(
            f"writer={model} admission={expected} repository_default={default} override={override}"
        )
