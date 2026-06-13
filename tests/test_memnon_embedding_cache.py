"""Regression tests for the turn-8 session hang (issue #401).

The narrative API constructs a fresh LORE -> MEMNON -> EmbeddingManager stack
per turn. Before the process-level model cache, every construction loaded its
own copy of the production embedder (~15.5 GB of MPS unified memory each),
and the per-turn stacks are reference-cycle islands that CPython's throttled
full GC never reclaimed mid-run -- ratcheting the server's footprint by one
model copy per turn until Metal allocation stalled at ~turn 8 on a 128 GB
machine.

These tests use a real local model (bge-large-en, ~1.3 GB) so they exercise
the genuine SentenceTransformer load path without the production model's
cost. They skip when the local model directory is absent (e.g. bare CI).
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any, Dict

import pytest

from nexus.agents.memnon.utils import embedding_manager as em
from nexus.config import load_settings_as_dict


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

pytestmark = pytest.mark.skipif(
    not MODEL_DIR.is_dir(),
    reason="bge-large local model from nexus.toml registry not present",
)


def _settings() -> Dict[str, Any]:
    return {
        "models": {
            "bge-large": {
                "local_path": str(MODEL_DIR),
                "is_active": True,
            }
        }
    }


def test_embedding_manager_shares_one_model_per_process() -> None:
    """Two EmbeddingManagers must hand out the SAME model object.

    Identity (not equality) is the contract: a second in-process copy of the
    production embedder is exactly the defect that exhausted unified memory.
    """
    first = em.EmbeddingManager(settings=_settings())
    second = em.EmbeddingManager(settings=_settings())
    assert first.models["bge-large"] is second.models["bge-large"]


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


@pytest.mark.requires_postgres
def test_memnon_close_disposes_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """MEMNON.close() must return its pooled Postgres connections.

    Pre-fix, each per-turn MEMNON's SQLAlchemy engine sat in cyclic garbage
    holding server-side connections until a full GC that effectively never
    ran mid-session.
    """
    import sqlalchemy as sa

    from nexus.agents.memnon import memnon as memnon_module

    monkeypatch.setitem(memnon_module.MEMNON_SETTINGS, "models", _settings()["models"])

    instance = memnon_module.MEMNON(
        interface=None,
        db_url="postgresql://pythagor@localhost:5432/save_05",
    )
    session = instance.db_manager.create_session()
    session.execute(sa.text("SELECT 1"))
    session.close()

    pool = instance.db_manager.engine.pool
    assert pool.checkedin() >= 1, "expected a pooled connection before close()"

    instance.close()
    assert pool.checkedin() == 0, "close() must dispose pooled connections"


@pytest.mark.requires_postgres
def test_per_turn_lore_stacks_share_embedder_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successive per-turn LORE stacks reuse ONE embedder and tear down cleanly.

    This is the turn-loop shape of the issue #401 regression: the narrative
    API builds LORE fresh per turn; without the process cache each build
    added a full embedder copy.
    """
    from nexus.agents.memnon import memnon as memnon_module

    monkeypatch.setitem(memnon_module.MEMNON_SETTINGS, "models", _settings()["models"])

    from nexus.agents.lore.lore import LORE

    first = LORE(enable_logon=False, debug=False, slot=5)
    first_model = first.memnon.embedding_manager.models["bge-large"]
    first.close()
    assert first.memnon is None, "close() must break the component back-refs"

    second = LORE(enable_logon=False, debug=False, slot=5)
    try:
        assert second.memnon.embedding_manager.models["bge-large"] is first_model
    finally:
        second.close()
