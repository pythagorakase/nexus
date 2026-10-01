"""Issue #812 (812-S2): embedder, reranker and search errors fail the turn.

Every layer from the model loaders to the LORE callers used to turn a model
or SQL error into ``None``, ``[]``, ``0.0`` or the unreranked results, so a
broken artifact silently cost the turn its retrieval. These tests build a real
MEMNON and LORE on a disposable clone with tiny on-disk models: a healthy or
drifted embedder registered as ``Octen-Embedding-4B`` and a tiny
cross-encoder as the reranker. The drifted embedder and the cross-encoder each
have 32 positions, so ``LONG`` raises a real size-mismatch error from torch
while ``SHORT`` succeeds. Nothing is downloaded and no paid call runs.

The clone has no 8-dimension ``chunk_embeddings_*`` table (NEXUS_template has
none), so retrieval returns the seeded chunk through the text leg.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Iterator, Tuple, cast

import psycopg2.errors
import pytest
import sqlalchemy.exc
import tomlkit

from nexus.agents.lore.lore import LORE
from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.memnon.utils import continuous_temporal_search, db_access
from nexus.agents.memnon.utils import cross_encoder
from nexus.agents.memnon.utils import embedding_manager as em
from nexus.database import database_url
from nexus.memory import ContextMemoryManager
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    require_disposable_target,
    route_slot_to_disposable,
    seed_committed_chunk,
    seed_protagonist,
)
from tests.tiny_models import (
    write_drifted_sentence_transformer,
    write_tiny_cross_encoder,
    write_tiny_sentence_transformer,
)

pytestmark = pytest.mark.requires_postgres

REPO_ROOT = Path(__file__).resolve().parents[1]
EMBEDDER = "Octen-Embedding-4B"
SHORT = "needle"
LONG = " ".join(["needle"] * 40)
SEEDED_TEXT = "The needle lies in the hay."

ConfigWriter = Callable[..., Tuple[Path, Path]]


@pytest.fixture(autouse=True)
def isolated_model_caches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give every test empty process-wide embedder and reranker caches."""

    monkeypatch.setattr(em, "_MODEL_CACHE", {})
    monkeypatch.setattr(cross_encoder, "_RERANKER_CACHE", {})
    yield


@pytest.fixture()
def clone(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A disposable migrated slot with a protagonist and one committed chunk."""

    with disposable_slot_database("qa_model_failures") as dbname:
        seed_protagonist(dbname)
        seed_committed_chunk(dbname, raw_text=SEEDED_TEXT)
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        yield dbname


@pytest.fixture()
def write_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ConfigWriter:
    """Return a writer for a real nexus.toml copy pointing at tiny models.

    The writer takes ``enabled`` (reranking), ``drifted`` (embedder) and
    ``reranker_missing`` and returns the embedder and reranker folders.
    """

    def write(
        *, enabled: bool, drifted: bool = False, reranker_missing: bool = False
    ) -> Tuple[Path, Path]:
        embedder_dir = tmp_path / "embedder"
        if drifted:
            write_drifted_sentence_transformer(embedder_dir)
        else:
            write_tiny_sentence_transformer(embedder_dir)
        reranker_dir = tmp_path / "reranker"
        if not reranker_missing:
            write_tiny_cross_encoder(reranker_dir)

        document = cast(Any, tomlkit.parse((REPO_ROOT / "nexus.toml").read_text()))
        for name, model in document["memnon"]["models"].items():
            model["is_active"] = name == EMBEDDER
        document["memnon"]["models"][EMBEDDER]["local_path"] = str(embedder_dir)
        document["memnon"]["models"][EMBEDDER]["dimensions"] = 8
        reranking = document["memnon"]["retrieval"]["cross_encoder_reranking"]
        reranking["model_path"] = str(reranker_dir)
        reranking["api_type"] = "cross_encoder"
        reranking["enabled"] = enabled

        path = tmp_path / "model-failures.toml"
        path.write_text(tomlkit.dumps(document))
        monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
        return embedder_dir, reranker_dir

    return write


@pytest.fixture()
def memnon_factory(clone: str) -> Iterator[Callable[[], MEMNON]]:
    """Build MEMNON instances on the clone and close each one afterwards."""

    built: list[MEMNON] = []

    def build() -> MEMNON:
        instance = MEMNON(interface=None, db_url=database_url(clone))
        built.append(instance)
        return instance

    yield build
    for instance in built:
        instance.close()


def _result_texts(response: dict[str, Any]) -> list[str]:
    return [str(result.get("text", "")) for result in response["results"]]


def test_memnon_construction_loads_the_reranker(
    write_config: ConfigWriter, memnon_factory: Callable[[], MEMNON]
) -> None:
    """MEMNON loads the reranker once; query_memory reuses that instance."""

    _embedder_dir, reranker_dir = write_config(enabled=True)

    memnon = memnon_factory()

    key = (str(reranker_dir), "cross_encoder", None)
    assert list(cross_encoder._RERANKER_CACHE) == [key]
    assert cross_encoder._RERANKER_CACHE[key] is memnon.reranker

    response = memnon.query_memory(SHORT)

    assert SEEDED_TEXT in _result_texts(response)
    assert all("reranker_score" in result for result in response["results"])
    assert list(cross_encoder._RERANKER_CACHE) == [key]
    assert cross_encoder._RERANKER_CACHE[key] is memnon.reranker


def test_memnon_construction_raises_when_the_reranker_folder_is_missing(
    write_config: ConfigWriter, clone: str
) -> None:
    """A missing reranker folder stops MEMNON and LORE at construction."""

    _embedder_dir, reranker_dir = write_config(enabled=True, reranker_missing=True)

    with pytest.raises(RuntimeError) as raised:
        MEMNON(interface=None, db_url=database_url(clone))
    assert "Cross-encoder reranker is not installed" in str(raised.value)
    assert str(reranker_dir) in str(raised.value)

    with pytest.raises(RuntimeError) as lore_raised:
        LORE(enable_logon=False, debug=False, dbname=clone)
    assert "FATAL: MEMNON initialization failed" in str(lore_raised.value)
    cause = lore_raised.value.__cause__
    assert isinstance(cause, RuntimeError)
    assert "Cross-encoder reranker is not installed" in str(cause)
    assert str(reranker_dir) in str(cause)
    assert cross_encoder._RERANKER_CACHE == {}


def test_disabled_reranking_loads_nothing(
    write_config: ConfigWriter, memnon_factory: Callable[[], MEMNON]
) -> None:
    """With reranking disabled, a missing reranker folder is never touched."""

    write_config(enabled=False, reranker_missing=True)

    memnon = memnon_factory()

    assert memnon.reranker is None
    assert cross_encoder._RERANKER_CACHE == {}


def test_query_memory_raises_when_the_embedder_cannot_encode(
    write_config: ConfigWriter, memnon_factory: Callable[[], MEMNON]
) -> None:
    """An encode failure fails query_memory instead of returning no results."""

    write_config(enabled=True, drifted=True)
    memnon = memnon_factory()

    assert SEEDED_TEXT in _result_texts(memnon.query_memory(SHORT))

    with pytest.raises(RuntimeError, match=f"'{EMBEDDER}' failed to encode"):
        memnon.query_memory(LONG)


def test_query_memory_raises_when_the_reranker_cannot_score(
    write_config: ConfigWriter, memnon_factory: Callable[[], MEMNON]
) -> None:
    """A scoring failure fails query_memory instead of skipping the rerank."""

    write_config(enabled=True)
    memnon = memnon_factory()

    with pytest.raises(RuntimeError, match="size of tensor a"):
        memnon.query_memory(LONG)


@pytest.mark.parametrize(
    "search",
    [
        db_access.execute_multi_model_hybrid_search,
        continuous_temporal_search.execute_multi_model_time_aware_search,
    ],
    ids=["hybrid", "time_aware"],
)
def test_sql_layer_propagates_a_query_error(
    clone: str, search: Callable[..., list[dict[str, Any]]]
) -> None:
    """A SQL error reaches the caller instead of becoming an empty result."""

    with pytest.raises(psycopg2.errors.UndefinedColumn) as raised:
        search(
            db_url=database_url(clone),
            query_text="needle",
            query_embeddings={EMBEDDER: [0.1] * 8},
            model_weights={EMBEDDER: 1.0},
            filters={"season": "missing_column"},
        )

    # An error re-raised from a catch-and-retry handler carries the first error
    # as __context__; none means no fallback search ran (item 9).
    assert raised.value.__context__ is None


def test_chunk_id_lookup_propagates_a_query_error(
    write_config: ConfigWriter, clone: str, memnon_factory: Callable[[], MEMNON]
) -> None:
    """A SQL error on a chunk_id: lookup fails query_memory (812-Q8)."""

    write_config(enabled=False)
    memnon = memnon_factory()
    require_disposable_target(clone)
    with closing(connect(clone)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM narrative_chunks WHERE raw_text = %s", (SEEDED_TEXT,)
        )
        chunk_id = int(cur.fetchone()[0])

    found = memnon.query_memory(f"chunk_id:{chunk_id}")
    assert _result_texts(found) == [SEEDED_TEXT]
    missing = memnon.query_memory(f"chunk_id:{chunk_id + 1000}")
    assert missing["results"] == []

    # Break the lookup's SQL on the disposable clone: the column it selects
    # no longer exists, so PostgreSQL rejects the statement.
    with closing(connect(clone)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE chunk_metadata RENAME COLUMN world_layer TO world_layer_gone"
        )

    with pytest.raises(sqlalchemy.exc.ProgrammingError) as raised:
        memnon.query_memory(f"chunk_id:{chunk_id}")
    assert isinstance(raised.value.orig, psycopg2.errors.UndefinedColumn)


@pytest.fixture()
def lore_on_clone(write_config: ConfigWriter, clone: str) -> Iterator[LORE]:
    """A fresh LORE per test on the clone: healthy reranker, drifted embedder."""

    write_config(enabled=True, drifted=True)
    lore = LORE(enable_logon=False, debug=False, dbname=clone)
    try:
        yield lore
    finally:
        lore.close()


def _memory(lore: LORE) -> ContextMemoryManager:
    """The LORE memory manager, which a built LORE always has."""

    assert lore.memory_manager is not None
    return lore.memory_manager


def _turns(lore: LORE) -> TurnCycleManager:
    """The LORE turn manager, which a built LORE always has."""

    assert lore.turn_manager is not None
    return lore.turn_manager


def _stage_baseline(lore: LORE) -> None:
    """Stage a Pass-1 baseline so Pass 2 runs its raw-input retrieval."""

    _memory(lore).handle_storyteller_response(
        narrative="Alex searches the barn while Emilia keeps watch.",
        warm_slice=[{"chunk_id": 1, "text": SEEDED_TEXT}],
        retrieved_passages=[],
        token_usage={
            "total_available": 1200,
            "warm_slice": 360,
            "structured": 180,
            "augmentation": 90,
        },
    )


def _raw_input(lore: LORE) -> Any:
    return _memory(lore).incremental.retrieve_from_raw_input(LONG, budget=10_000)


def _gap_context(lore: LORE) -> Any:
    return _memory(lore).incremental.retrieve_gap_context({LONG: "gap"}, budget=10_000)


def _retrieve_context(lore: LORE) -> Any:
    return asyncio.run(lore.retrieve_context([LONG], chunk_id=None))


def _deep_queries(lore: LORE) -> Any:
    ctx = TurnContext(
        turn_id="turn_model_failure_deep",
        user_input="Continue.",
        start_time=time.time(),
    )
    ctx.warm_slice = [{"id": 1, "is_target": True, "full_text": LONG}]
    return asyncio.run(_turns(lore).execute_deep_queries(ctx))


def _process_user_input(lore: LORE) -> Any:
    _stage_baseline(lore)
    ctx = TurnContext(
        turn_id="turn_model_failure_pass2",
        user_input=LONG,
        start_time=time.time(),
    )
    return asyncio.run(_turns(lore).process_user_input(ctx))


@pytest.mark.parametrize(
    "layer",
    [_raw_input, _gap_context, _retrieve_context, _deep_queries, _process_user_input],
    ids=[
        "retrieve_from_raw_input",
        "retrieve_gap_context",
        "retrieve_context",
        "execute_deep_queries",
        "process_user_input",
    ],
)
def test_retrieval_layer_propagates_an_encode_failure(
    lore_on_clone: LORE, layer: Callable[[LORE], Any]
) -> None:
    """Every LORE retrieval caller lets the encode failure fail the turn."""

    with pytest.raises(RuntimeError, match=f"'{EMBEDDER}' failed to encode"):
        layer(lore_on_clone)


def test_blank_raw_input_runs_no_query(lore_on_clone: LORE) -> None:
    """Blank raw input runs no query, so it never reaches the embedder."""

    assert _memory(lore_on_clone).incremental.retrieve_from_raw_input(
        "   ", budget=10_000
    ) == ([], 0)


def test_blank_directive_runs_no_query(lore_on_clone: LORE) -> None:
    """A directive that sanitizes to nothing runs no query_memory call."""

    result = asyncio.run(lore_on_clone.retrieve_context(["???"], chunk_id=None))

    assert result["directives"]["???"]["search_progress"] == []
