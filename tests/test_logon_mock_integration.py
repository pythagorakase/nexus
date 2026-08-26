"""Integration test for LogonUtility → mock server routing."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any, Iterator
import uuid

import psycopg2
from psycopg2 import sql
import pytest
import requests  # type: ignore[import-untyped]

from nexus.agents.logon.skald_wire import SkaldTurnWire
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api import db_pool
from nexus.telemetry.usage import summarize_usage
from scripts.api_openai import OpenAIProvider
from scripts import new_story_setup


REPO_ROOT = Path(__file__).resolve().parents[1]


def _connect(dbname: str) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
    )


def get_slot_model(dbname: str) -> str | None:
    """Query slot model directly from global_variables."""
    conn = _connect(dbname)
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
            result = cur.fetchone()
            return result[0] if result else None
    finally:
        conn.close()


@pytest.fixture(scope="module")
def slot_model_database() -> Iterator[str]:
    """Yield a TEST-configured NEXUS_template clone without mutating a save."""

    dbname = f"qa735_slot_model_{uuid.uuid4().hex[:12]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        with _connect(dbname) as conn, conn.cursor() as cur:
            cur.execute("UPDATE global_variables SET model = 'TEST' WHERE id = TRUE")
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
        pool = db_pool._pools.pop(dbname, None)
        if pool is not None:
            pool.closeall()
        if admin is not None:
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
            admin.close()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture
def mock_openai_server(tmp_path: Path) -> Iterator[str]:
    """Spawn the repository mock on a free port and tear it down reliably."""

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "mock_openai.log"
    env = dict(os.environ)
    env.pop("NEXUS_GATEWAY_PORT", None)
    env.pop("NEXUS_API_URL", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "nexus.api.mock_openai:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    log.flush()
                    raise RuntimeError(
                        "mock_openai exited before readiness:\n"
                        f"{log_path.read_text(errors='replace')}"
                    )
                try:
                    response = requests.get(f"{base_url}/health", timeout=0.5)
                    if response.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                if time.monotonic() >= deadline:
                    log.flush()
                    raise TimeoutError(
                        "mock_openai did not become ready:\n"
                        f"{log_path.read_text(errors='replace')}"
                    )
                time.sleep(0.1)
            yield f"{base_url}/v1"
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


@pytest.mark.requires_postgres
def test_slot_model_detection(slot_model_database: str):
    """Test that we can detect TEST model from slot config."""
    model = get_slot_model(slot_model_database)
    assert model == "TEST", f"Expected TEST, got {model}"


@pytest.mark.requires_postgres
def test_provider_routes_to_mock_server(mock_openai_server: str):
    """Test OpenAI provider routes TEST model to mock server."""
    provider = OpenAIProvider(
        model="TEST",
        base_url=mock_openai_server,
        api_key="test-dummy-key",
        system_prompt="Test system prompt",
    )

    assert provider.model == "TEST"
    assert provider.base_url == mock_openai_server

    # Initialize and call mock server
    provider.initialize()

    response, llm_response = provider.get_structured_completion(
        "Generate narrative for the story protagonist",
        SkaldTurnWire,
    )

    assert len(response.narrative) > 100, "Narrative too short"
    assert (
        len(response.choices) == 3
    ), f"Expected 3 choices, got {len(response.choices)}"
    assert response.narrative.startswith("[TEST MODE]")
    assert response.updates is None
    assert response.orrery_adjudications == []
    assert "deterministic mock control" in response.narrative


def test_logon_real_entrypoint_records_registry_provider_and_single_pass_seat(
    tmp_path: Path,
) -> None:
    """The genuine LOGON path preserves registry billing identity at the SDK seam."""

    utility = LogonUtility(
        {
            "API Settings": {"apex": {"turn_pipeline": "single_pass"}},
            "storyteller": {
                "correspondence": {
                    "max_letter_tokens": 300,
                }
            },
        },
        model_override="registry-test-model",
    )
    endpoint: dict[str, Any] = {
        "base_url": "http://127.0.0.1:5102/v1",
        "api_key": "test-dummy-key",
        "structured_transport": "responses",
        "request_timeout_seconds": None,
        "request_params": {},
    }
    utility._initialize_provider(
        False,
        resolved_route=("registry-test-model", "test", endpoint, "local"),
    )
    assert isinstance(utility.provider, OpenAIProvider)

    wire = SkaldTurnWire(
        narrative="The mocked boundary returns a complete turn.",
        choices=["Continue.", "Wait."],
        letter="Keep the next consequence private.",
    )
    raw_response = SimpleNamespace(
        id="resp_logon_integration",
        output_parsed=wire,
        output_text=wire.model_dump_json(),
        usage=SimpleNamespace(
            input_tokens=101,
            output_tokens=23,
            total_tokens=124,
        ),
    )
    utility.provider.client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **_kwargs: raw_response)
    )

    response = utility.generate_narrative(
        {
            "user_input": "Continue.",
            "warm_slice": {"chunks": []},
            "entity_data": {},
            "retrieved_passages": {"results": []},
        },
        effective_context_window=75_000,
    )

    assert response.generation_model == "registry-test-model"
    event = summarize_usage(usage_dir=tmp_path / "usage")["events"][0]
    assert event["provider"] == "test"
    assert event["seat"] == "skald_single_pass"
    assert event["total_tokens"] == 124
