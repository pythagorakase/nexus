"""Ordering and failure semantics of the shared source-embedding orchestrator.

Only the true external boundaries are replaced: the pooled PostgreSQL
connection (a recording stand-in that keeps ``get_connection``'s commit-or-
rollback contract and answers the orchestrator's queries from in-memory rows)
and the sentence-transformer embedder. Configuration flows through the real
``load_settings_as_dict`` seam with an explicit model registry, and the real
dimension-table DDL helpers run against the recording cursor.

The public wrappers are exercised through seams the pre-#848 modules also
used, so the ordering and failure tests hold for both implementations. The
real upsert/stamp atomicity is proven against PostgreSQL in
``tests/test_orrery/test_retrograde_embedding_pg.py``.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Literal, Optional

import pytest

from nexus.agents.memnon.utils import source_embeddings
from nexus.agents.memnon.utils.source_embeddings import (
    RETROGRADE_SUMMARY_SOURCE,
    EmbeddingSource,
    embed_source_rows,
    generate_source_vectors,
    upsert_source_vectors,
)
from nexus.agents.orrery import retrograde_embedding
from nexus.agents.orrery.experience_embedding import embed_character_experiences
from nexus.agents.orrery.retrograde_embedding import embed_retrograde_summaries

STAMP = datetime(2196, 1, 1, tzinfo=timezone.utc)
REGISTRY = {
    "alpha": {"is_active": True, "dimensions": 3, "local_path": "/models/alpha"},
    "dormant": {"is_active": False, "dimensions": 7, "local_path": "/models/dormant"},
    "beta": {"is_active": True, "dimensions": 5, "local_path": "/models/beta"},
}

SUMMARIES: dict[int, dict[str, Any]] = {
    22: {"text": "The courier hid the ledger.", "valid": True},
    11: {"text": "The archive inherited a debt.", "valid": True},
}
EXPERIENCES: dict[int, dict[str, Any]] = {
    41: {"text": "I remembered the flood.", "valid": True},
    42: {"text": "I remembered the fire.", "valid": True},
    43: {"text": None, "valid": True},
    44: {"text": "I remembered a retracted day.", "valid": False},
}


class _Database:
    """In-memory rows plus an event trace shared by every connection."""

    def __init__(
        self, table: str, text_column: str, rows: dict[int, dict[str, Any]]
    ) -> None:
        self.table = table
        self.text_column = text_column
        self.rows = {row_id: dict(row) for row_id, row in rows.items()}
        self.trace: list[str] = []
        self.statements: list[tuple[str, Any]] = []
        self.after_load: Optional[Callable[["_Database"], None]] = None

    def _eligible(self, sql: str, row_id: int) -> bool:
        row = self.rows.get(row_id)
        if row is None:
            return False
        if "invalidation_status = 'valid'" in sql and not row["valid"]:
            return False
        if f"{self.text_column} IS NOT NULL" in sql and row["text"] is None:
            return False
        return True

    def respond(self, sql: str, params: Any) -> list[dict[str, Any]]:
        self.statements.append((sql, params))
        if sql.startswith(f"SELECT id, {self.text_column} FROM {self.table}"):
            self.trace.append("load")
            rows = [
                {"id": row_id, self.text_column: self.rows[row_id]["text"]}
                for row_id in params[0]
                if self._eligible(sql, row_id)
            ]
            if self.after_load is not None:
                self.after_load(self)
            return rows
        if sql.startswith(f"UPDATE {self.table} SET embedding_generated_at"):
            self.trace.append("stamp")
            return [
                {"id": row_id, "embedding_generated_at": STAMP}
                for row_id in params[0]
                if self._eligible(sql, row_id)
            ]
        if sql.startswith("CREATE TABLE IF NOT EXISTS"):
            self.trace.append("create " + sql.split()[5])
        elif sql.startswith("INSERT INTO"):
            self.trace.append(f"insert {sql.split()[2]} {params[0]} {params[1]}")
        return []

    @contextmanager
    def connect(self, dbname: str, dict_cursor: bool = False) -> Iterator[Any]:
        """Mirror db_pool.get_connection: commit on success, else roll back."""
        assert dict_cursor is True
        self.trace.append(f"open {dbname}")
        try:
            yield _Connection(self)
        except BaseException:
            self.trace.append("rollback")
            raise
        self.trace.append("commit")


class _Cursor:
    def __init__(self, database: _Database) -> None:
        self.database = database
        self.rows: list[dict[str, Any]] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: Any) -> Literal[False]:
        return False

    def execute(self, statement: str, params: Any = None) -> None:
        self.rows = self.database.respond(" ".join(statement.split()), params)

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class _Connection:
    def __init__(self, database: _Database) -> None:
        self.database = database

    def cursor(self) -> _Cursor:
        return _Cursor(self.database)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    database: _Database,
    *,
    loaded_models: Optional[list[str]] = None,
    fail_on: Optional[tuple[str, str]] = None,
) -> None:
    """Route the pool, the registry and the embedder to test doubles."""
    texts_to_ids = {
        row["text"]: row_id for row_id, row in database.rows.items() if row["text"]
    }

    class Embedder:
        def __init__(self, *, settings: dict[str, Any]) -> None:
            database.trace.append("load models")
            self.dimensions = {
                name: config["dimensions"]
                for name, config in settings["models"].items()
                if config["is_active"]
            }

        def get_available_models(self) -> list[str]:
            if loaded_models is not None:
                return list(loaded_models)
            return list(self.dimensions)

        def generate_embedding(self, text: str, model: str) -> Optional[list[float]]:
            database.trace.append(f"embed {texts_to_ids[text]}/{model}")
            if fail_on == (text, model):
                return None
            return [float(len(text))] + [0.5] * (self.dimensions[model] - 1)

    monkeypatch.setattr("nexus.api.db_pool.get_connection", database.connect)
    monkeypatch.setattr(
        "nexus.agents.memnon.utils.embedding_manager.EmbeddingManager", Embedder
    )
    monkeypatch.setattr(
        "nexus.config.load_settings_as_dict",
        lambda *_args: {"Agent Settings": {"MEMNON": {"models": REGISTRY}}},
    )


def _summaries(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> _Database:
    database = _Database("retrograde_summaries", "summary_text", SUMMARIES)
    _install(monkeypatch, database, **kwargs)
    return database


def _experiences(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> _Database:
    database = _Database("character_experiences", "experience_text", EXPERIENCES)
    _install(monkeypatch, database, **kwargs)
    return database


def test_summaries_generate_every_vector_before_one_write_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read, then embed everything, then DDL, upserts and stamp atomically."""
    database = _summaries(monkeypatch)

    results = embed_retrograde_summaries("save_05", [22, 11, 22])

    small = "retrograde_summary_embeddings_0003d"
    large = "retrograde_summary_embeddings_0005d"
    assert database.trace == [
        "open save_05",
        "load",
        "commit",
        "load models",
        "embed 22/alpha",
        "embed 22/beta",
        "embed 11/alpha",
        "embed 11/beta",
        "open save_05",
        f"create {small}",
        f"insert {small} 22 alpha",
        f"create {large}",
        f"insert {large} 22 beta",
        f"insert {small} 11 alpha",
        f"insert {large} 11 beta",
        "stamp",
        "commit",
    ]
    assert results == [
        {
            "summary_id": 22,
            "models": ["alpha", "beta"],
            "dimensions": [3, 5],
            "embedding_generated_at": STAMP.isoformat(),
        },
        {
            "summary_id": 11,
            "models": ["alpha", "beta"],
            "dimensions": [3, 5],
            "embedding_generated_at": STAMP.isoformat(),
        },
    ]
    inserts = [params for sql, params in database.statements if "INSERT" in sql]
    assert inserts[0] == (22, "alpha", "[27.0,0.5,0.5]")


def test_experiences_load_and_stamp_only_valid_rendered_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The validity predicate guards both the read and the ironman stamp."""
    database = _experiences(monkeypatch)

    results = embed_character_experiences("save_05", [42, 41])

    assert [row["experience_id"] for row in results] == [42, 41]
    load_sql, stamp_sql = (
        sql
        for sql, _params in database.statements
        if sql.startswith(("SELECT", "UPDATE"))
    )
    assert "invalidation_status = 'valid'" in load_sql
    assert "invalidation_status = 'valid'" in stamp_sql
    assert "experience_text IS NOT NULL" in stamp_sql
    assert [line for line in database.trace if line.startswith("insert")] == [
        "insert character_experience_embeddings_0003d 42 alpha",
        "insert character_experience_embeddings_0005d 42 beta",
        "insert character_experience_embeddings_0003d 41 alpha",
        "insert character_experience_embeddings_0005d 41 beta",
    ]


def test_missing_summary_raises_before_any_model_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing row stops the batch before generation or any write."""
    database = _summaries(monkeypatch)

    with pytest.raises(RuntimeError, match=r"not found in save_05: \[99\]"):
        embed_retrograde_summaries("save_05", [22, 99])

    assert database.trace == ["open save_05", "load", "commit"]


def test_invalidated_experience_is_missing_and_unrendered_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid rows never load; valid rows without text refuse to embed."""
    database = _experiences(monkeypatch)
    with pytest.raises(RuntimeError, match=r"not found in save_05: \[44\]"):
        embed_character_experiences("save_05", [41, 44])
    with pytest.raises(RuntimeError, match=r"not rendered in save_05: \[43\]"):
        embed_character_experiences("save_05", [41, 43])

    assert "load models" not in database.trace
    assert database.trace.count("open save_05") == 2


def test_model_mismatch_raises_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loaded embedders must equal the configured active models exactly."""
    database = _summaries(monkeypatch, loaded_models=["alpha"])

    with pytest.raises(RuntimeError, match="did not match configuration"):
        embed_retrograde_summaries("save_05", [22])

    assert database.trace[-1] == "load models"
    assert not any(line.startswith("embed") for line in database.trace)


def test_generation_failure_leaves_every_row_unwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late model failure writes nothing, so the whole set stays retryable."""
    database = _summaries(monkeypatch, fail_on=(SUMMARIES[11]["text"], "beta"))

    with pytest.raises(
        RuntimeError,
        match=(
            "Embedding generation failed for Retrograde summary 11 with model "
            "beta; embedding_generated_at remains NULL for retry"
        ),
    ):
        embed_retrograde_summaries("save_05", [22, 11])

    assert database.trace.count("open save_05") == 1
    assert "stamp" not in database.trace
    assert not any(line.startswith("insert") for line in database.trace)


def test_stamp_shortfall_rolls_back_the_upserted_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row invalidated mid-batch aborts the write transaction as a whole."""
    database = _experiences(monkeypatch)

    def invalidate_42(db: _Database) -> None:
        db.rows[42]["valid"] = False

    database.after_load = invalidate_42

    with pytest.raises(RuntimeError, match=r"stamp count did not match.*1 of 2"):
        embed_character_experiences("save_05", [41, 42])

    assert database.trace[-3:] == [
        "insert character_experience_embeddings_0005d 42 beta",
        "stamp",
        "rollback",
    ]


@pytest.mark.parametrize(
    "embed", [embed_retrograde_summaries, embed_character_experiences]
)
def test_invalid_or_empty_ids_never_connect(
    monkeypatch: pytest.MonkeyPatch, embed: Callable[..., Any]
) -> None:
    """Id validation happens before any connection or model load."""
    database = _summaries(monkeypatch)

    assert embed("save_05", []) == []
    with pytest.raises(ValueError, match="must be positive"):
        embed("save_05", [3, 0])

    assert database.trace == []


def test_wrappers_are_the_shared_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The summary wrapper and re-export add nothing to the shared path."""
    _summaries(monkeypatch)

    assert (
        retrograde_embedding.active_memnon_embedding_model_dimensions
        is source_embeddings.active_memnon_embedding_model_dimensions
    )
    assert source_embeddings.active_memnon_embedding_model_dimensions() == {
        "alpha": 3,
        "beta": 5,
    }
    assert embed_source_rows(
        "save_05", RETROGRADE_SUMMARY_SOURCE, [11]
    ) == embed_retrograde_summaries("save_05", [11])


def test_active_dimensions_read_the_real_registry() -> None:
    """nexus.toml declares at least one active embedder with real dimensions."""
    dimensions = source_embeddings.active_memnon_embedding_model_dimensions()

    assert dimensions
    assert all(value > 0 for value in dimensions.values())


def test_shared_helpers_serve_a_caller_supplied_embedder() -> None:
    """The job path's own encoder errors propagate unwrapped; DDL runs once."""
    ddl: list[int] = []

    def ensure_chunk_table(_cursor: Any, dimensions: int) -> str:
        ddl.append(dimensions)
        return f"chunks_{dimensions}"

    chunks = EmbeddingSource(
        label="narrative chunk",
        plural_label="Narrative chunks",
        table="narrative_chunks",
        id_column="id",
        text_column="raw_text",
        embedding_fk_column="chunk_id",
        ensure_table=ensure_chunk_table,
        table_name_for_dimensions=lambda dimensions: f"chunks_{dimensions}",
    )

    def mismatched(_text: str, model: str) -> list[float]:
        raise ValueError(f"Embedding dimension mismatch for {model}")

    with pytest.raises(ValueError, match="dimension mismatch for alpha"):
        generate_source_vectors(chunks, {7: "text"}, ["alpha"], mismatched)

    generated = generate_source_vectors(
        chunks, {7: "a", 8: "b"}, ["alpha"], lambda text, _model: [1.0, 2.0]
    )
    database = _Database("narrative_chunks", "raw_text", {})
    with database.connect("save_05", dict_cursor=True) as conn:
        with conn.cursor() as cursor:
            assert upsert_source_vectors(cursor, chunks, generated) == {2: "chunks_2"}

    assert ddl == [2]
    assert [params for _sql, params in database.statements] == [
        (7, "alpha", "[1.0,2.0]"),
        (8, "alpha", "[1.0,2.0]"),
    ]
    assert "ON CONFLICT (chunk_id, model)" in database.statements[0][0]
