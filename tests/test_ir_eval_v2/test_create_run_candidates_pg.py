"""Issue #812 (812-S4a): ir_eval create-run resolves its candidates first.

``create-run`` stores a settings snapshot whose ``models`` holds exactly the
selected embedders, resolved from the production ``[memnon.models]`` entry or
``[ir_eval.embedding_candidates]``, and whose reranker is the named
``[ir_eval.reranker_candidates]`` entry. Every name resolves before the row is
written. These tests drive the real parser against a disposable template
clone, which holds ``ir_eval.eval_runs``.
"""

from __future__ import annotations

import json
from contextlib import closing
from typing import Any, Dict, Iterator, List

import pytest

from ir_eval.runner import build_parser
from nexus.config import load_settings
from nexus.database import database_url
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres

PRODUCTION = "Octen-Embedding-4B"


@pytest.fixture()
def clone() -> Iterator[str]:
    """A disposable template clone holding an empty ir_eval.eval_runs."""

    with disposable_slot_database("qa640_812s4a") as dbname:
        yield dbname


def _create_run(
    dbname: str, extra: List[str], capsys: pytest.CaptureFixture[str]
) -> int:
    """Run ``create-run`` through the real parser and return the run id."""

    args = build_parser().parse_args(
        ["--db-url", database_url(dbname), "create-run", "--name", "812-s4a", *extra]
    )
    args.func(args)
    return int(json.loads(capsys.readouterr().out)["run_id"])


def _stored_runs(dbname: str) -> List[Dict[str, Any]]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, config FROM ir_eval.eval_runs ORDER BY id")
        return [{"id": row[0], "config": row[1]} for row in cur.fetchall()]


def test_fresh_clone_copies_ir_eval_schema_without_run_data(clone: str) -> None:
    """A template clone restores ir_eval objects covered by its migration stamps."""

    with closing(connect(clone)) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('ir_eval.eval_runs')::text")
        assert cur.fetchone()[0] == "ir_eval.eval_runs"
    assert _stored_runs(clone) == []


def test_create_run_resolves_an_embedding_candidate(
    clone: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The snapshot holds only the named candidate and the named reranker."""

    run_id = _create_run(
        clone,
        ["--model", "Octen-Embedding-8B:1.0", "--reranker", "qwen3-reranker-0.6b"],
        capsys,
    )

    settings = load_settings()
    assert settings.ir_eval is not None
    candidate = settings.ir_eval.embedding_candidates["Octen-Embedding-8B"]
    reranker = settings.ir_eval.reranker_candidates["qwen3-reranker-0.6b"]
    (run,) = _stored_runs(clone)
    assert run["id"] == run_id
    snapshot = run["config"]["settings_snapshot"]
    assert snapshot["models"] == {"Octen-Embedding-8B": candidate.model_dump()}
    reranking = snapshot["retrieval"]["cross_encoder_reranking"]
    assert (
        reranking["name"],
        reranking["model_path"],
        reranking["remote_path"],
        reranking["api_type"],
    ) == (
        "qwen3-reranker-0.6b",
        reranker.local_path,
        reranker.remote_path,
        reranker.api_type,
    )


def test_create_run_resolves_the_production_embedder(
    clone: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --reranker the run keeps the production reranker identity."""

    _create_run(clone, ["--model", f"{PRODUCTION}:1.0"], capsys)

    settings = load_settings()
    production = settings.memnon.models[PRODUCTION]
    production_reranker = settings.memnon.retrieval.cross_encoder_reranking
    (run,) = _stored_runs(clone)
    snapshot = run["config"]["settings_snapshot"]
    assert snapshot["models"] == {PRODUCTION: production.model_dump()}
    reranking = snapshot["retrieval"]["cross_encoder_reranking"]
    assert (
        reranking["name"],
        reranking["model_path"],
        reranking["remote_path"],
        reranking["api_type"],
    ) == (
        production_reranker.name,
        production_reranker.model_path,
        production_reranker.remote_path,
        production_reranker.api_type,
    )
    assert "candidates" not in reranking


def test_create_run_refuses_an_unknown_model_before_writing(
    clone: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unknown --model raises before ir_eval.eval_runs gains a row."""

    with pytest.raises(ValueError) as raised:
        _create_run(clone, ["--model", "bge-tiny:1.0"], capsys)

    message = str(raised.value)
    assert "[memnon.models]" in message
    assert "[ir_eval.embedding_candidates]" in message
    assert PRODUCTION in message
    assert _stored_runs(clone) == []


def test_create_run_refuses_an_unknown_reranker_before_writing(
    clone: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unknown enabled reranker is refused before a run row is stored."""

    with pytest.raises(ValueError, match=r"\[ir_eval.reranker_candidates\]"):
        _create_run(
            clone,
            ["--model", f"{PRODUCTION}:1.0", "--reranker", "unregistered-reranker"],
            capsys,
        )
    assert _stored_runs(clone) == []


def test_disabled_reranking_ignores_an_unknown_candidate(
    clone: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A disabled candidate neither resolves nor overwrites production identity."""

    _create_run(
        clone,
        [
            "--model",
            f"{PRODUCTION}:1.0",
            "--no-cross-encoder",
            "--reranker",
            "unregistered-reranker",
        ],
        capsys,
    )
    (run,) = _stored_runs(clone)
    assert run["config"]["cross_encoder_enabled"] is False
    stored = run["config"]["settings_snapshot"]["retrieval"]["cross_encoder_reranking"]
    assert (
        stored == load_settings().memnon.retrieval.cross_encoder_reranking.model_dump()
    )
