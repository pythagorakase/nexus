"""Issue #812 (812-S4b): the ensemble weighting lives in ir_eval.

Runtime retrieval runs the one ``[memnon.models]`` embedder, and only an
ir_eval run combines several embedders, by the ``--model NAME:WEIGHT``
weights it stores (Decision 812-Q4a). These tests build a disposable template
clone with four committed chunks and an 8-dimension vector table whose rows
prescribe each chunk's cosine to the query ``needle`` under each model. Two
tiny on-disk embedders with the same seed-0 weights stand in for the
production embedder and one ``[ir_eval.embedding_candidates]`` entry, so both
embed ``needle`` to the same vector ``q``. No chunk text contains ``needle``
or ``hay``, so the text leg scores zero. Nothing is downloaded and no paid
call runs.

Prescribed cosines (c1, c2, c3, c4):

- ``Octen-Embedding-4B``: 0.9, 0.8, 0.4, 0.2
- ``qa640-probe-b``: 0.1, 0.3, 0.5, 0.6

The runtime ranks c1-c4 by the production embedder alone; weights 0.25/0.75
rank c4, c3, c2, c1; equal weights would rank c2, c1, c3, c4.
"""

from __future__ import annotations

import math
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence, Tuple, cast

import pytest
import tomlkit

from ir_eval.engine.run_executor import RunExecutor
from ir_eval.engine.storage import EvaluationStore
from ir_eval.models.schemas import EvalModelConfig, EvalRunConfig
from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.memnon.utils import cross_encoder
from nexus.agents.memnon.utils import embedding_manager as em
from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager
from nexus.agents.memnon.utils.embedding_tables import ensure_embedding_table
from nexus.agents.memnon.utils.idf_dictionary import IDFDictionary
from nexus.agents.memnon.utils.search import SearchManager
from nexus.config import load_settings
from nexus.database import database_url
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_committed_chunk,
    seed_protagonist,
)
from tests.tiny_models import write_tiny_sentence_transformer

pytestmark = pytest.mark.requires_postgres

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = "Octen-Embedding-4B"
PROBE = "qa640-probe-b"
QUERY = "needle"
DIMENSIONS = 8
COSINES: Dict[str, Tuple[float, ...]] = {
    PRODUCTION: (0.9, 0.8, 0.4, 0.2),
    PROBE: (0.1, 0.3, 0.5, 0.6),
}
CHUNK_TEXTS = (
    "The lantern gutters in the stairwell.",
    "Rain drums on the copper roof.",
    "A courier waits beside the gate.",
    "Smoke curls above the empty forge.",
)


@dataclass(frozen=True)
class ParitySlot:
    """The disposable clone, its chunk ids (c1-c4) and the ir_eval query id."""

    dbname: str
    chunk_ids: List[int]
    query_id: int
    embedder_dirs: Tuple[Path, Path]

    @property
    def url(self) -> str:
        """The clone's database URL."""

        return database_url(self.dbname)


@pytest.fixture(autouse=True)
def isolated_model_caches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give every test empty process-wide embedder and reranker caches."""

    monkeypatch.setattr(em, "_MODEL_CACHE", {})
    monkeypatch.setattr(cross_encoder, "_RERANKER_CACHE", {})
    yield


def _write_config(tmp_path: Path, embedder_a: Path, embedder_b: Path) -> Path:
    """Write a nexus.toml copy whose embedders are the two tiny folders."""

    document = cast(Any, tomlkit.parse((REPO_ROOT / "nexus.toml").read_text()))
    production = document["memnon"]["models"][PRODUCTION]
    production["local_path"] = str(embedder_a)
    production["dimensions"] = DIMENSIONS
    probe = tomlkit.table()
    probe["local_path"] = str(embedder_b)
    probe["dimensions"] = DIMENSIONS
    document["ir_eval"]["embedding_candidates"][PROBE] = probe
    retrieval = document["memnon"]["retrieval"]
    retrieval["cross_encoder_reranking"]["enabled"] = False
    retrieval["hybrid_search"]["use_query_type_weights"] = False
    path = tmp_path / "ensemble-parity.toml"
    path.write_text(tomlkit.dumps(document))
    return path


def _unit(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


def _orthogonal_unit(q_hat: Sequence[float]) -> List[float]:
    """A unit vector orthogonal to ``q_hat`` (Gram-Schmidt on a basis vector)."""

    for index in range(len(q_hat)):
        basis = [1.0 if position == index else 0.0 for position in range(len(q_hat))]
        projection = q_hat[index]
        residual = [b - projection * q for b, q in zip(basis, q_hat)]
        if math.sqrt(sum(value * value for value in residual)) > 0.1:
            return _unit(residual)
    raise AssertionError(f"no basis vector is independent of {q_hat}")


def _vector_at(cosine: float, q_hat: Sequence[float], u_hat: Sequence[float]) -> str:
    """The pgvector literal of ``cos θ · q̂ + sin θ · û``."""

    sine = math.sqrt(1.0 - cosine * cosine)
    values = [cosine * q + sine * u for q, u in zip(q_hat, u_hat)]
    return "[" + ",".join(repr(value) for value in values) + "]"


@pytest.fixture()
def parity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ParitySlot]:
    """A clone with c1-c4, prescribed cosines under both models, one query."""

    embedder_a = write_tiny_sentence_transformer(tmp_path / "embedder-a")
    embedder_b = write_tiny_sentence_transformer(tmp_path / "embedder-b")
    config = _write_config(tmp_path, embedder_a, embedder_b)
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))

    q = EmbeddingManager(
        settings=load_settings().memnon.model_dump(by_alias=True)
    ).generate_embedding(QUERY, PRODUCTION)
    q_hat = _unit([float(value) for value in q])
    assert len(q_hat) == DIMENSIONS
    u_hat = _orthogonal_unit(q_hat)

    with disposable_slot_database("qa640_812s4b") as dbname:
        seed_protagonist(dbname)
        chunk_ids = [
            seed_committed_chunk(dbname, raw_text=text, scene=scene)
            for scene, text in enumerate(CHUNK_TEXTS, start=1)
        ]
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            table = ensure_embedding_table(cur, DIMENSIONS)
            for model, cosines in COSINES.items():
                for chunk_id, cosine in zip(chunk_ids, cosines):
                    cur.execute(
                        f"INSERT INTO {table} (chunk_id, model, embedding) "
                        "VALUES (%s, %s, %s::vector)",
                        (chunk_id, model, _vector_at(cosine, q_hat, u_hat)),
                    )
            cur.execute(
                "INSERT INTO ir_eval.queries (text, category, name) "
                "VALUES (%s, %s, %s) RETURNING id",
                (QUERY, "character", "qa640"),
            )
            query_id = int(cur.fetchone()[0])
        EvaluationStore(database_url(dbname)).upsert_judgment(
            query_id=query_id, chunk_id=chunk_ids[0], relevance=2
        )
        yield ParitySlot(
            dbname=dbname,
            chunk_ids=chunk_ids,
            query_id=query_id,
            embedder_dirs=(embedder_a, embedder_b),
        )


def _run_ir_eval(slot: ParitySlot, config: EvalRunConfig) -> List[Dict[str, Any]]:
    """Create and execute a run; return its eval_results rows by rank."""

    executor = RunExecutor(EvaluationStore(slot.url), db_url=slot.url)
    run_id = executor.create_run(config)
    executor.execute_run(run_id)
    with closing(connect(slot.dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_id, rank, final_score, vector_score, text_score, "
            "model_scores FROM ir_eval.eval_results "
            "WHERE run_id = %s AND query_id = %s ORDER BY rank",
            (run_id, slot.query_id),
        )
        return [
            {
                "chunk_id": int(row[0]),
                "rank": int(row[1]),
                "final_score": float(row[2]),
                "vector_score": float(row[3]),
                "text_score": float(row[4]),
                "model_scores": dict(row[5]),
            }
            for row in cur.fetchall()
        ]


def test_runtime_query_memory_ranks_by_the_one_embedder(parity: ParitySlot) -> None:
    """query_memory ranks c1-c4 by the production embedder's cosine alone."""

    memnon = MEMNON(interface=None, db_url=parity.url)
    try:
        response = memnon.query_memory(QUERY, k=4)
    finally:
        memnon.close()

    results = response["results"]
    assert [int(result["id"]) for result in results] == parity.chunk_ids
    for result, cosine in zip(results, COSINES[PRODUCTION]):
        assert set(result["model_scores"]) == {PRODUCTION}
        assert result["model_scores"][PRODUCTION] == pytest.approx(cosine, abs=1e-5)


def test_ir_eval_run_scores_by_its_own_weights(parity: ParitySlot) -> None:
    """A 0.25/0.75 run scores each chunk by the run's own model weights."""

    rows = _run_ir_eval(
        parity,
        EvalRunConfig(
            name="qa640-812s4b-weights",
            embedding_models=[
                EvalModelConfig(model=PRODUCTION, weight=0.25),
                EvalModelConfig(model=PROBE, weight=0.75),
            ],
            hybrid_search=False,
            cross_encoder_enabled=False,
            top_k=4,
        ),
    )

    c1, c2, c3, c4 = parity.chunk_ids
    assert [row["chunk_id"] for row in rows] == [c4, c3, c2, c1]
    assert [row["rank"] for row in rows] == [1, 2, 3, 4]
    assert [row["final_score"] for row in rows] == pytest.approx(
        [0.5, 0.475, 0.425, 0.3], abs=1e-5
    )
    for row in rows:
        assert set(row["model_scores"]) == {PRODUCTION, PROBE}


def test_ir_eval_production_run_matches_the_runtime_path(parity: ParitySlot) -> None:
    """A production-only hybrid run stores exactly what the runtime returns."""

    rows = _run_ir_eval(
        parity,
        EvalRunConfig(
            name="qa640-812s4b-parity",
            embedding_models=[EvalModelConfig(model=PRODUCTION, weight=1.0)],
            hybrid_search=True,
            vector_weight=0.6,
            text_weight=0.4,
            cross_encoder_enabled=False,
            top_k=4,
        ),
    )

    memnon = MEMNON(interface=None, db_url=parity.url)
    try:
        runtime = memnon.search_manager.perform_hybrid_search(QUERY, top_k=4)
    finally:
        memnon.close()

    assert len(rows) == len(runtime) == 4
    for rank, (row, result) in enumerate(zip(rows, runtime), start=1):
        assert row["chunk_id"] == int(result["id"])
        assert row["rank"] == rank
        assert row["final_score"] == pytest.approx(result["score"], abs=1e-9)
        assert row["vector_score"] == pytest.approx(result["vector_score"], abs=1e-9)
        assert row["text_score"] == pytest.approx(result["text_score"], abs=1e-9)
        assert set(row["model_scores"]) == set(result["model_scores"])
        for model, score in result["model_scores"].items():
            assert row["model_scores"][model] == pytest.approx(score, abs=1e-9)


def test_runtime_search_refuses_an_ensemble(parity: ParitySlot) -> None:
    """Runtime search refuses to run with two loaded embedders."""

    settings = load_settings().memnon.model_dump(by_alias=True)
    settings["models"][PROBE] = {
        "is_active": True,
        "local_path": str(parity.embedder_dirs[1]),
        "remote_path": None,
        "dimensions": DIMENSIONS,
    }
    embedding_manager = EmbeddingManager(settings=settings)
    assert set(embedding_manager.get_available_models()) == {PRODUCTION, PROBE}
    manager = SearchManager(
        db_url=parity.url,
        embedding_manager=embedding_manager,
        idf_dictionary=IDFDictionary(parity.url),
        settings=settings,
        retrieval_settings={"default_top_k": 4},
    )

    with pytest.raises(RuntimeError) as hybrid:
        manager.perform_hybrid_search(QUERY)
    with pytest.raises(RuntimeError) as vector:
        manager.query_vector_search(QUERY, ["narrative_chunks"], {}, 4)
    for raised in (hybrid, vector):
        message = str(raised.value)
        assert PRODUCTION in message and PROBE in message
        assert "only in ir_eval" in message
