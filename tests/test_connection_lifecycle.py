"""Two-server isolation through the real CLI, gateway, and TEST provider.

The fixture owns every database on its two temporary clusters, including the
normal save_04 and mock names required by production entry points. The owner's
NEXUS_template is read only to export schema and vocabulary; no fleet writes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn
from psycopg2.extras import Json
import pytest
import requests
import tomlkit
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.api import db_pool, slot_utils
from nexus.database import connection_kwargs, database_url
from tests.test_database_contract import two_clusters  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.requires_postgres
RuntimeFixture = tuple[
    Callable[..., dict[str, Any]], dict[str, Any], dict[str, Any], Path
]


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, capture_output=True, text=True, **kwargs)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _cluster_params(cluster: dict[str, Any]) -> dict[str, Any]:
    return {key: cluster[key] for key in ("host", "port", "user")}


@contextmanager
def _watch_other(cluster: dict[str, Any], evidence: Path) -> Iterator[None]:
    """Watch the non-target server from before startup through shutdown."""
    observer = psycopg2.connect(dbname="save_04", **_cluster_params(cluster))
    observer.autocommit = True
    try:
        with observer.cursor() as cur:
            cur.execute("SELECT oid, relname FROM pg_class ORDER BY oid")
            before = cur.fetchall()
        offset = cluster["log"].stat().st_size
        yield
        with observer.cursor() as cur:
            cur.execute("SELECT oid, relname FROM pg_class ORDER BY oid")
            after = cur.fetchall()
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE backend_type = 'client backend' AND pid <> pg_backend_pid()"
            )
            clients = cur.fetchone()[0]
        log = cluster["log"].read_text()[offset:]
        evidence.write_text(
            json.dumps(
                {
                    "catalog_before_count": len(before),
                    "catalog_unchanged": before == after,
                    "other_clients": clients,
                    "new_connections": log.count("connection received"),
                    "schema_statements": log.count("CREATE "),
                },
                indent=2,
            )
        )
        assert after == before
        assert clients == 0
        assert "connection received" not in log
        assert "CREATE " not in log
    finally:
        observer.close()


def _seed_background_work() -> int:
    """Resolve real sleep pressure into durable work for the production worker."""
    from nexus.agents.orrery.events import commit_orrery_tick_sync
    from nexus.agents.orrery.resolver import resolve_dry_run
    from nexus.agents.orrery.templates import BUILTIN_TEMPLATES

    timestamp = datetime(2196, 7, 6, 23, tzinfo=timezone.utc)
    with db_pool.get_connection("save_04") as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
            "VALUES ('Background isolation anchor', 'Background isolation anchor') RETURNING id"
        )
        chunk_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO chunk_metadata (chunk_id, world_layer) VALUES (%s, 'primary')",
            (chunk_id,),
        )
        cur.execute(
            "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
            (timestamp, chunk_id),
        )
        cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
        actor_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO characters (name, entity_id) VALUES ('Isolation Courier', %s)",
            (actor_id,),
        )
        cur.execute(
            "UPDATE character_need_states SET debt_score = 60, last_evaluated_at = %s "
            "WHERE character_entity_id = %s AND need_type = 'sleep'",
            (timestamp, actor_id),
        )
        assert cur.rowcount == 1
        cur.execute(
            "INSERT INTO world_events (event_type, tick_chunk_id, actor_entity_id, "
            "world_layer, source, changed_fields, payload) "
            "VALUES ('slept', %s, %s, 'primary', 'resolver', '{}', '{}')",
            (chunk_id, actor_id),
        )
    engine = create_engine(database_url("save_04"))
    try:
        with Session(engine) as session:
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=chunk_id,
                window_chunks=30,
                epistemics_settings={"enabled": False},
            )
    finally:
        engine.dispose()
    assert any(draft.template_id == "sleep" for draft in proposal.resolutions)
    with db_pool.get_connection("save_04") as conn:
        result = commit_orrery_tick_sync(conn, proposal, tick_chunk_id=chunk_id, slot=4)
        assert result.resolution_count >= 1
    return int(chunk_id)


@pytest.fixture
def lifecycle_runtime(
    two_clusters: list[dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[RuntimeFixture]:
    """Restore actual schema and start only local deterministic services."""
    from scripts.new_story_setup import (
        TEMPLATE_SEED_TABLES,
        _initialize_empty_idf_corpora,
        _postgres_tools,
        ensure_global_variables,
    )
    from nexus.api.new_story_cache import write_cache

    private, other = two_clusters
    binaries = _postgres_tools("pg_dump", "psql")
    source = make_dsn(**connection_kwargs("NEXUS_template"))
    schema = _run(
        [binaries["pg_dump"], "--schema-only", "--no-owner", "--no-acl", source]
    ).stdout
    seeds = _run(
        [
            binaries["pg_dump"],
            "--data-only",
            "--no-owner",
            "--no-acl",
            source,
            *[arg for table in TEMPLATE_SEED_TABLES for arg in ("-t", table)],
        ]
    ).stdout
    for cluster in two_clusters:
        admin = psycopg2.connect(dbname="postgres", **_cluster_params(cluster))
        admin.autocommit = True
        try:
            for dbname in ("save_04", "mock"):
                with admin.cursor() as cur:
                    cur.execute(
                        sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname))
                    )
                if cluster is private:
                    _run(
                        [
                            binaries["psql"],
                            "-X",
                            "-v",
                            "ON_ERROR_STOP=1",
                            make_dsn(dbname=dbname, **_cluster_params(cluster)),
                        ],
                        input=schema + "\n" + seeds,
                    )
        finally:
            admin.close()

    doc = tomlkit.parse((ROOT / "nexus.toml").read_text())
    doc["api"]["database"].update(_cluster_params(private))
    doc["api"]["database"]["password_secret"] = ""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        mock_port = sock.getsockname()[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        gateway_port = sock.getsockname()[1]
    doc["runtime"]["state_dir"] = str(tmp_path / "runtime")
    doc["runtime"]["services"]["gateway"]["port"] = gateway_port
    doc["runtime"]["services"]["mock_openai"]["port"] = mock_port
    doc["runtime"]["services"]["mock_openai"]["enabled"] = "never"
    providers = doc["global"]["model"]["api_models"]
    # Route every registered model consumer to TEST; no hosted calls permitted.
    uses = []
    for provider in providers.values():
        for model in provider["models"]:
            model_uses = model.pop("uses", [])
            uses.extend(use for use in model_uses if use != "local_models.model")
            if "local_models.model" in model_uses:
                model["uses"] = ["local_models.model"]
    providers["test"]["models"][0]["uses"] = uses
    providers["test"]["base_url"] = f"http://127.0.0.1:{mock_port}/v1"
    config = tmp_path / "nexus.toml"
    config.write_text(tomlkit.dumps(doc))
    for key in ("PGPASSWORD", "PGSERVICE", "PGSERVICEFILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", str(gateway_port))
    monkeypatch.setenv("NEXUS_API_URL", f"http://127.0.0.1:{gateway_port}")
    monkeypatch.setenv("NEXUS_SLOT", "4")
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    for key, value in _cluster_params(other).items():
        monkeypatch.setenv(f"PG{key.upper()}", str(value))
    monkeypatch.setattr(
        slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {"mock"}
    )
    db_pool.close_all_pools()
    for dbname in ("save_04", "mock"):
        ensure_global_variables(dbname)
        _initialize_empty_idf_corpora(dbname)
    cache = json.loads(
        (ROOT / "tests/fixtures/golden_path_wizard_cache.json").read_text()
    )
    write_cache(**{**cache, "target_slot": 4, "dbname": "mock"})
    with db_pool.get_connection("mock") as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO incubator (parent_chunk_id, storyteller_text, choice_object) "
            "VALUES (0, %s, %s)",
            (
                "[TEST MODE] A sealed letter waits in the harbor archive.",
                Json({"presented": ["Read the sealed letter.", "Watch the harbor."]}),
            ),
        )
    db_pool.close_all_pools()

    def cli(*args: str) -> dict[str, Any]:
        result = _run(
            [sys.executable, "-m", "nexus.cli", "--json", *args], timeout=240, cwd=ROOT
        )
        payload = json.loads(result.stdout)
        assert payload.get("success", True), payload
        return payload

    # An override gateway intentionally does not spawn fixed-port siblings.
    # This fixture therefore owns its isolated TEST server directly.
    with (
        _watch_other(other, tmp_path / "isolation.json"),
        (tmp_path / "mock.log").open("w") as mock_log,
    ):
        mock = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "nexus.api.mock_openai:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(mock_port),
            ],
            cwd=ROOT,
            stdout=mock_log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                assert mock.poll() is None, (tmp_path / "mock.log").read_text()
                try:
                    if requests.get(
                        f"http://127.0.0.1:{mock_port}/health", timeout=1
                    ).ok:
                        break
                except requests.ConnectionError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("TEST provider did not become healthy")
            cli("up", "--slot", "4")
            yield cli, private, other, tmp_path
        finally:
            try:
                cli("down")
            finally:
                mock.terminate()
                mock.wait(timeout=15)
                db_pool.close_all_pools()


def test_connection_two_clusters_story_lifecycle(
    lifecycle_runtime: RuntimeFixture,
) -> None:
    """No foreign connections or DDL during wizard, turn, retrieval, and jobs."""
    cli, private, other, tmp_path = lifecycle_runtime
    status = cli("status")
    targets = status["runtime"]["database"]["targets"]
    assert (
        targets["pooled"]
        == targets["url"]
        == {**_cluster_params(private), "dbname": "save_04"}
    )
    started = cli("continue", "--slot", "4", "--model", "TEST")
    assert started["model"] == "TEST"
    steps = [started]
    for _ in range(12):
        result = cli("continue", "--slot", "4", "--accept-fate")
        steps.append(result)
        (tmp_path / "steps.json").write_text(json.dumps(steps, indent=2))
        state = requests.get(
            f"{os.environ['NEXUS_API_URL']}/api/slot/4/state", timeout=30
        ).json()
        if not state["is_wizard_mode"] and state.get("storyteller_text"):
            break
    else:
        pytest.fail(f"Wizard did not bootstrap: {steps[-1]}")
    assert "sealed letter" in state["storyteller_text"]
    continuation = cli("continue", "--slot", "4", "--choice", "1")
    (tmp_path / "continuation.json").write_text(json.dumps(continuation, indent=2))
    assert continuation["success"]

    from nexus.agents.memnon.utils.db_access import (
        execute_multi_model_hybrid_search,
    )

    results = execute_multi_model_hybrid_search(
        database_url("save_04"),
        "sealed letter",
        {},
        {},
        vector_weight=0,
        text_weight=1,
    )
    assert results, "MEMNON did not retrieve the committed bootstrap"
    # The gateway scheduler owns background work now. Observe its durable
    # completion rather than racing it with a second legacy worker.
    seeded_chunk_id = _seed_background_work()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        with db_pool.get_connection("save_04") as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM orrery_narration_jobs j "
                "JOIN orrery_resolutions r ON r.id = j.resolution_id "
                "WHERE j.state = 'succeeded' AND r.tick_chunk_id = %s",
                (seeded_chunk_id,),
            )
            if cur.fetchone()[0] >= 1:
                break
        time.sleep(0.05)
    else:
        pytest.fail("Gateway scheduler did not finish seeded narration work")

    with db_pool.get_connection("save_04") as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM orrery_narration_jobs j "
            "JOIN orrery_resolutions r ON r.id = j.resolution_id "
            "WHERE j.state = 'succeeded' AND r.tick_chunk_id = %s",
            (seeded_chunk_id,),
        )
        assert cur.fetchone()[0] >= 1
        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = 'save_04'")
        assert cur.fetchone()[0] >= 2  # gateway pool plus this observer
    from nexus.agents.orrery.job_queues import load_job_queues_sync

    with db_pool.get_connection("save_04") as conn:
        jobs = load_job_queues_sync(conn)
    assert jobs["counts"]["failed"] == 0, jobs
    (tmp_path / "background.json").write_text(json.dumps(jobs, indent=2, default=str))
