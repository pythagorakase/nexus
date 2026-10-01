"""Regression tests for the turn-8 session hang (issue #401).

The narrative API constructs a fresh LORE -> MEMNON -> EmbeddingManager stack
per turn. Before the process-level model cache, every construction loaded its
own copy of the production embedder (~15.5 GB of MPS unified memory each),
and the per-turn stacks are reference-cycle islands that CPython's throttled
full GC never reclaimed mid-run -- ratcheting the server's footprint by one
model copy per turn until Metal allocation stalled at ~turn 8 on a 128 GB
machine.

The manager and turn-loop tests use a real local model (bge-large-en,
~1.3 GB) so they exercise the genuine SentenceTransformer load path without
the production model's cost; they skip when that directory is absent (e.g.
bare CI). The cache-key tests load a tiny randomly initialised model saved to
disk, so they always run and never download anything.
"""

from __future__ import annotations

import ast
import gc
import inspect
from pathlib import Path
from typing import Any, Dict, Iterator

import pytest
import tomlkit
from sentence_transformers import SentenceTransformer

from nexus.agents.memnon.utils import cross_encoder
from nexus.agents.memnon.utils import embedding_manager as em
from nexus.config import load_settings_as_dict
from tests.pg_fixtures import (
    disposable_slot_database,
    route_slot_to_disposable,
    seed_protagonist,
    sqlalchemy_url,
)
from tests.tiny_models import (
    write_drifted_sentence_transformer,
    write_tiny_sentence_transformer,
)

# Texts for the tiny embedders, whose BERT has 32 positions: ``SHORT`` encodes,
# while ``LONG`` (over 32 tokens) raises a size mismatch in the drifted folder.
SHORT = "needle"
LONG = " ".join(["needle"] * 40)


def _bge_large_path() -> Path:
    """Resolve bge-large's local path from the nexus.toml model registry."""
    models = (
        load_settings_as_dict()
        .get("Agent Settings", {})
        .get("MEMNON", {})
        .get("models", {})
    )
    return Path(models.get("bge-large", {}).get("local_path", "/nonexistent"))


MODEL_DIR = _bge_large_path()

requires_bge_large = pytest.mark.skipif(
    not MODEL_DIR.is_dir(),
    reason="bge-large local model from nexus.toml registry not present",
)


@pytest.fixture(autouse=True)
def isolated_model_cache(monkeypatch: pytest.MonkeyPatch):
    """Keep process-global model cache assertions scoped to each test."""
    monkeypatch.setattr(em, "_MODEL_CACHE", {})
    monkeypatch.setattr(cross_encoder, "_RERANKER_CACHE", {})
    yield
    em._MODEL_CACHE.clear()
    gc.collect()


@pytest.fixture()
def model_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Give native MEMNON/LORE construction a migrated, disposable empty slot."""
    with disposable_slot_database("qa_model_cache") as dbname:
        seed_protagonist(dbname)
        route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=dbname)
        yield dbname


@pytest.fixture()
def model_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use a real validated config with only the regression embedder active."""
    document = tomlkit.parse((Path(__file__).parents[1] / "nexus.toml").read_text())
    for name, model in document["memnon"]["models"].items():
        model["is_active"] = name == "bge-large"
    path = tmp_path / "model-cache.toml"
    path.write_text(tomlkit.dumps(document))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
    return path


def _settings() -> Dict[str, Any]:
    return {
        "models": {
            "bge-large": {
                "local_path": str(MODEL_DIR),
                "is_active": True,
            }
        }
    }


@requires_bge_large
def test_embedding_manager_shares_one_model_per_process() -> None:
    """Two EmbeddingManagers must hand out the SAME model object.

    Identity (not equality) is the contract: a second in-process copy of the
    production embedder is exactly the defect that exhausted unified memory.
    """
    first = em.EmbeddingManager(settings=_settings())
    second = em.EmbeddingManager(settings=_settings())
    assert first.models["bge-large"] is second.models["bge-large"]


def test_model_cache_normalizes_local_path_aliases(tmp_path: Path) -> None:
    """Filesystem aliases for one model directory must share one cache key."""

    target = write_tiny_sentence_transformer(tmp_path / "model")
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)

    first = em.get_or_load_sentence_transformer(str(alias))
    second = em.get_or_load_sentence_transformer(str(target))

    assert first is second
    assert list(em._MODEL_CACHE) == [str(target.resolve())]


def test_every_sentence_transformer_keyword_is_accepted_and_local_only() -> None:
    """The one embedder load stays local-only and uses keywords the library takes.

    A real check against the installed sentence-transformers, not a mock:
    dropping ``local_files_only`` would let a half-copied folder be patched
    from the Hugging Face Hub, and a keyword the library does not accept
    would raise TypeError before anything loads.
    """

    accepted = inspect.signature(SentenceTransformer.__init__).parameters
    passed = em.sentence_transformer_kwargs("cpu")

    assert passed["local_files_only"] is True
    assert set(passed) <= set(accepted), sorted(set(passed) - set(accepted))
    assert all(
        accepted[name].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        for name in passed
    )


def test_the_one_loader_passes_only_the_local_only_keywords() -> None:
    """The single SentenceTransformer call spreads exactly the helper's keywords.

    Guards embedding_manager.py's one load against losing ``local_files_only``
    by bypassing ``sentence_transformer_kwargs`` or adding keywords beside it.
    """

    source = Path(inspect.getsourcefile(em) or "").read_text()
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "SentenceTransformer"
    ]

    assert len(calls) == 1
    (call,) = calls
    assert [keyword.arg for keyword in call.keywords] == [None]
    spread = call.keywords[0].value
    assert isinstance(spread, ast.Call)
    assert isinstance(spread.func, ast.Name)
    assert spread.func.id == "sentence_transformer_kwargs"


def test_pinned_device_gets_its_own_cached_instance(tmp_path: Path) -> None:
    """A device-pinned load (the INT8 CPU rule) never reuses an unpinned one.

    ``regenerate_embeddings.py`` pins INT8 models to CPU; an unpinned instance
    of the same folder, placed wherever sentence-transformers chose, must not
    be handed back to that caller, and the pinned instance must stay cached.
    """

    target = write_tiny_sentence_transformer(tmp_path / "model")

    unpinned = em.get_or_load_sentence_transformer(str(target))
    pinned = em.get_or_load_sentence_transformer(str(target), device="cpu")

    assert pinned is not unpinned
    assert str(pinned.device) == "cpu"
    assert em.get_or_load_sentence_transformer(str(target), device="cpu") is pinned
    assert em.get_or_load_sentence_transformer(str(target)) is unpinned
    assert sorted(em._MODEL_CACHE) == sorted(
        [str(target.resolve()), f"{target.resolve()}|device=cpu"]
    )


@requires_bge_large
def test_cached_model_survives_manager_teardown() -> None:
    """Dropping a manager must not evict (or duplicate) the cached model."""
    manager = em.EmbeddingManager(settings=_settings())
    model = manager.models["bge-large"]
    del manager
    gc.collect()

    again = em.EmbeddingManager(settings=_settings())
    assert again.models["bge-large"] is model

    # The shared instance stays usable after a sibling manager's teardown.
    embedding = again.generate_embedding("the bell under the lintel", "bge-large")
    assert embedding is not None and len(embedding) > 0


@requires_bge_large
@pytest.mark.requires_postgres
def test_memnon_close_disposes_engine(model_config: Path, model_database: str) -> None:
    """MEMNON.close() must return its pooled Postgres connections.

    Pre-fix, each per-turn MEMNON's SQLAlchemy engine sat in cyclic garbage
    holding server-side connections until a full GC that effectively never
    ran mid-session.
    """
    import sqlalchemy as sa

    from nexus.agents.memnon import memnon as memnon_module
    from nexus.database import database_url

    instance = memnon_module.MEMNON(
        interface=None,
        db_url=database_url(model_database),
    )
    session = instance.db_manager.create_session()
    session.execute(sa.text("SELECT 1"))
    session.close()

    pool = instance.db_manager.engine.pool
    assert pool.checkedin() >= 1, "expected a pooled connection before close()"

    instance.close()
    assert pool.checkedin() == 0, "close() must dispose pooled connections"
    with pytest.raises(RuntimeError, match="DatabaseManager is closed"):
        instance.db_manager.create_session()


@requires_bge_large
@pytest.mark.requires_postgres
def test_per_turn_lore_stacks_share_embedder_and_close(
    model_config: Path,
    model_database: str,
) -> None:
    """Successive per-turn LORE stacks reuse ONE embedder and tear down cleanly.

    This is the turn-loop shape of the issue #401 regression: the narrative
    API builds LORE fresh per turn; without the process cache each build
    added a full embedder copy.
    """
    from nexus.agents.lore.lore import LORE

    first = LORE(enable_logon=False, debug=False, dbname=model_database)
    first.logon = object()
    first._logon_initialized = True
    first_model = first.memnon.embedding_manager.models["bge-large"]
    first.close()
    assert first.memnon is None, "close() must break the component back-refs"
    assert first.logon is None
    assert not first._logon_initialized

    second = LORE(enable_logon=False, debug=False, dbname=model_database)
    try:
        assert second.memnon.embedding_manager.models["bge-large"] is first_model
    finally:
        second.close()


@pytest.fixture()
def drifted_manager(tmp_path: Path) -> em.EmbeddingManager:
    """A manager whose only active model ``tiny`` is the drifted folder."""

    folder = write_drifted_sentence_transformer(tmp_path / "drifted")
    return em.EmbeddingManager(
        settings={"models": {"tiny": {"local_path": str(folder), "is_active": True}}}
    )


def test_generate_embedding_raises_when_the_model_cannot_encode(
    drifted_manager: em.EmbeddingManager,
) -> None:
    """An encode failure raises naming the model, chained to the model error."""

    embedding = drifted_manager.generate_embedding(SHORT, "tiny")
    assert len(embedding) == 8 and all(isinstance(x, float) for x in embedding)

    with pytest.raises(
        RuntimeError, match="Embedding model 'tiny' failed to encode"
    ) as raised:
        drifted_manager.generate_embedding(LONG, "tiny")
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert "size of tensor a" in str(raised.value.__cause__)


def test_generate_embeddings_batch_raises_when_the_model_cannot_encode(
    drifted_manager: em.EmbeddingManager,
) -> None:
    """A batch encode failure raises instead of returning None."""

    assert len(drifted_manager.generate_embeddings_batch([SHORT, SHORT], "tiny")) == 2

    with pytest.raises(
        RuntimeError, match="Embedding model 'tiny' failed to encode"
    ) as raised:
        drifted_manager.generate_embeddings_batch([SHORT, LONG], "tiny")
    assert "size of tensor a" in str(raised.value.__cause__)


def test_generate_embedding_raises_for_a_model_that_is_not_loaded(
    drifted_manager: em.EmbeddingManager,
) -> None:
    """Asking for a model that is not loaded names it and the loaded models."""

    with pytest.raises(RuntimeError) as raised:
        drifted_manager.generate_embedding(SHORT, "absent")

    assert "'absent' is not loaded" in str(raised.value)
    assert "['tiny']" in str(raised.value)
    with pytest.raises(RuntimeError, match="'absent' is not loaded"):
        drifted_manager.generate_embeddings_batch([SHORT], "absent")


def test_generate_embedding_raises_for_empty_text(
    drifted_manager: em.EmbeddingManager,
) -> None:
    """Empty or blank text is a caller error, not a None embedding."""

    for text in ("", "   "):
        with pytest.raises(ValueError, match="'tiny'"):
            drifted_manager.generate_embedding(text, "tiny")


def test_generate_embeddings_batch_raises_for_empty_text(
    drifted_manager: em.EmbeddingManager,
) -> None:
    """A blank text in a batch raises naming its index; no vector is dropped."""

    with pytest.raises(ValueError) as raised:
        drifted_manager.generate_embeddings_batch([SHORT, "  ", SHORT], "tiny")

    assert "'tiny'" in str(raised.value)
    assert "indexes [1]" in str(raised.value)
    assert drifted_manager.generate_embeddings_batch([], "tiny") == []
