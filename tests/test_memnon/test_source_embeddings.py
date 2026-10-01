"""Real write-path proofs plus unchanged pre-write rejection contract tests."""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Literal, Optional

import pytest

from nexus.agents.memnon.utils import source_embeddings
from nexus.agents.memnon.utils.source_embeddings import (
    RETROGRADE_SUMMARY_SOURCE,
    CHARACTER_EXPERIENCE_SOURCE,
    embed_source_rows,
    generate_source_vectors,
    upsert_source_vectors,
)
from nexus.agents.orrery import retrograde_embedding
from nexus.agents.orrery.experience_embedding import embed_character_experiences
from nexus.agents.orrery.retrograde_embedding import embed_retrograde_summaries
from nexus.config import load_settings
from nexus.config.settings_models import EmbeddingModelConfig
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
)
from tests.test_embedding_table_ownership_pg import (
    CHUNK_SOURCE,
    seed_source,
    assert_corpus_contract,
)
from psycopg2.extras import RealDictCursor


@pytest.fixture
def source_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Route all slot-dependent paths to one TEST-pinned disposable clone."""
    with disposable_slot_database("qa640_810s2_source") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        yield dbname


def _assert_vectors(
    dbname: str, spec: Any, ids: list[int], dimensions: dict[str, int]
) -> None:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        for model, dimension in dimensions.items():
            table = spec.table_name_for_dimensions(dimension)
            assert_corpus_contract(cur, spec, dimension)
            cur.execute(
                f"SELECT {spec.embedding_fk_column}, vector_dims(embedding) "
                f"FROM {table} "
                f"WHERE {spec.embedding_fk_column} = ANY(%s) AND model = %s "
                f"ORDER BY {spec.embedding_fk_column}",
                (ids, model),
            )
            assert cur.fetchall() == [(row_id, dimension) for row_id in sorted(ids)]


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
    # Two active embedders exercise multi-model ordering; the live config
    # validator admits one, so the registry is assigned after loading.
    registry_settings = load_settings()
    registry_settings.memnon.models = {
        name: EmbeddingModelConfig.model_validate({**config, "weight": 0.0})
        for name, config in REGISTRY.items()
    }
    monkeypatch.setattr("nexus.config.load_settings", lambda *_args: registry_settings)


def _summaries(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> _Database:
    database = _Database("retrograde_summaries", "summary_text", SUMMARIES)
    _install(monkeypatch, database, **kwargs)
    return database


def _experiences(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> _Database:
    database = _Database("character_experiences", "experience_text", EXPERIENCES)
    _install(monkeypatch, database, **kwargs)
    return database


@pytest.mark.requires_postgres
def test_summaries_generate_every_vector_before_one_write_transaction(
    source_db: str,
) -> None:
    """Callback generation finishes before real DDL, vectors and atomic stamps."""
    spec = RETROGRADE_SUMMARY_SOURCE
    ids = [
        seed_source(source_db, spec, text)
        for text in ["The courier hid the ledger.", "The archive inherited a debt."]
    ]
    texts = dict(
        zip(ids, ["The courier hid the ledger.", "The archive inherited a debt."])
    )
    calls = []

    def embed(text: str, model: str) -> list[float]:
        with closing(connect(source_db)) as conn, conn.cursor() as cur:
            for dimension in [3, 5]:
                cur.execute(
                    "SELECT to_regclass(%s)",
                    (spec.table_name_for_dimensions(dimension),),
                )
                assert cur.fetchone() == (None,)
            cur.execute(
                "SELECT embedding_generated_at FROM retrograde_summaries "
                "WHERE id = ANY(%s)",
                (ids,),
            )
            assert cur.fetchall() == [(None,), (None,)]
        calls.append((text, model))
        return [float(len(text))] + [0.5] * ((3 if model == "alpha" else 5) - 1)

    generated = generate_source_vectors(spec, texts, ["alpha", "beta"], embed)
    assert calls == [
        (text, model) for text in texts.values() for model in ["alpha", "beta"]
    ]
    with (
        closing(connect(source_db, cursor_factory=RealDictCursor)) as conn,
        conn,
        conn.cursor() as cur,
    ):
        upsert_source_vectors(cur, spec, generated)
        stamps = source_embeddings._stamp_embedded_rows(cur, spec, ids)
        assert set(stamps) == set(ids)
        assert len(set(stamps.values())) == 1
    _assert_vectors(source_db, spec, ids, {"alpha": 3, "beta": 5})
    with closing(connect(source_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT embedding::text FROM retrograde_summary_embeddings_0003d "
            "WHERE summary_id=%s AND model='alpha'",
            (ids[0],),
        )
        assert cur.fetchone() == ("[27,0.5,0.5]",)
        cur.execute(
            "SELECT embedding_generated_at FROM retrograde_summaries WHERE "
            "id = ANY(%s)",
            (ids,),
        )
        assert all(row[0] == stamps[ids[0]] for row in cur.fetchall())


@pytest.mark.requires_postgres
def test_experiences_load_and_stamp_only_valid_rendered_rows(source_db: str) -> None:
    """Real loaded rows, configured local vectors and validity-filtered stamps."""
    spec = CHARACTER_EXPERIENCE_SOURCE
    ids = [
        seed_source(source_db, spec, f"I remembered the ledger {i}.") for i in range(4)
    ]
    with closing(connect(source_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE character_experiences SET experience_text=NULL, "
            "render_model=NULL, renderer_version=NULL, "
            "render_generation_id=NULL WHERE id=%s",
            (ids[2],),
        )
        cur.execute(
            "UPDATE character_experiences SET "
            "invalidation_status='invalidated', invalidated_at=now() WHERE id=%s",
            (ids[3],),
        )
    results = embed_character_experiences(source_db, [ids[1], ids[0]])
    assert [row["experience_id"] for row in results] == [ids[1], ids[0]]
    _assert_vectors(
        source_db,
        spec,
        ids[:2],
        source_embeddings.active_memnon_embedding_model_dimensions(),
    )
    with (
        closing(connect(source_db, cursor_factory=RealDictCursor)) as conn,
        conn.cursor() as cur,
    ):
        loaded = source_embeddings._load_source_rows(cur, spec, ids)
        assert set(loaded) == set(ids[:3]) and loaded[ids[2]] is None
    with closing(connect(source_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, embedding_generated_at FROM character_experiences "
            "WHERE id=ANY(%s) ORDER BY id",
            (ids,),
        )
        rows = cur.fetchall()
        assert all(row[1] is not None for row in rows[:2])
        assert rows[2:] == [(ids[2], None), (ids[3], None)]


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


@pytest.mark.requires_postgres
def test_stamp_shortfall_rolls_back_the_upserted_vectors(source_db: str) -> None:
    """Concurrent invalidation makes the real stamp reject and roll back vectors."""
    spec = CHARACTER_EXPERIENCE_SOURCE
    ids = [
        seed_source(source_db, spec, f"I remembered the flood {i}.") for i in range(2)
    ]
    with (
        closing(connect(source_db, cursor_factory=RealDictCursor)) as conn,
        conn.cursor() as cur,
    ):
        rows = source_embeddings._load_source_rows(cur, spec, ids)
    generated = generate_source_vectors(
        spec,
        rows,
        ["alpha", "beta"],
        lambda _text, model: [0.5] * (3 if model == "alpha" else 5),
    )
    with closing(connect(source_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE character_experiences SET "
            "invalidation_status='invalidated', invalidated_at=now() WHERE id=%s",
            (ids[1],),
        )
    with closing(connect(source_db, cursor_factory=RealDictCursor)) as conn:
        with pytest.raises(RuntimeError, match=r"stamp count did not match.*1 of 2"):
            with conn, conn.cursor() as cur:
                upsert_source_vectors(cur, spec, generated)
                source_embeddings._stamp_embedded_rows(cur, spec, ids)
    with closing(connect(source_db)) as conn, conn.cursor() as cur:
        for dimension in [3, 5]:
            cur.execute(
                "SELECT to_regclass(%s)", (spec.table_name_for_dimensions(dimension),)
            )
            assert cur.fetchone() == (None,)
        cur.execute(
            "SELECT embedding_generated_at FROM character_experiences WHERE id=ANY(%s)",
            (ids,),
        )
        assert cur.fetchall() == [(None,), (None,)]


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


@pytest.mark.requires_postgres
def test_wrappers_are_the_shared_orchestrator(source_db: str) -> None:
    """Public wrapper and shared orchestrator use the real configured embedder."""
    assert (
        retrograde_embedding.active_memnon_embedding_model_dimensions
        is source_embeddings.active_memnon_embedding_model_dimensions
    )
    row_id = seed_source(source_db, RETROGRADE_SUMMARY_SOURCE)
    shared = embed_source_rows(source_db, RETROGRADE_SUMMARY_SOURCE, [row_id])
    wrapped = embed_retrograde_summaries(source_db, [row_id])
    assert [
        {k: v for k, v in row.items() if k != "embedding_generated_at"}
        for row in shared
    ] == [
        {k: v for k, v in row.items() if k != "embedding_generated_at"}
        for row in wrapped
    ]
    assert all(row["embedding_generated_at"] for row in shared + wrapped)
    _assert_vectors(
        source_db,
        RETROGRADE_SUMMARY_SOURCE,
        [row_id],
        source_embeddings.active_memnon_embedding_model_dimensions(),
    )


def test_active_dimensions_read_the_real_registry() -> None:
    """nexus.toml declares at least one active embedder with real dimensions."""
    dimensions = source_embeddings.active_memnon_embedding_model_dimensions()

    assert dimensions
    assert all(value > 0 for value in dimensions.values())


@pytest.mark.requires_postgres
def test_shared_helpers_serve_a_caller_supplied_embedder(source_db: str) -> None:
    """Public callback errors propagate, and real chunk upserts preserve identities."""
    ids = [seed_source(source_db, CHUNK_SOURCE, text) for text in ["a", "b"]]
    texts = dict(zip(ids, ["a", "b"]))

    def mismatched(_text: str, model: str) -> list[float]:
        raise ValueError(f"Embedding dimension mismatch for {model}")

    with pytest.raises(ValueError, match="dimension mismatch for alpha"):
        generate_source_vectors(CHUNK_SOURCE, texts, ["alpha"], mismatched)
    generated = generate_source_vectors(
        CHUNK_SOURCE, texts, ["alpha"], lambda _text, _model: [1.0, 2.0]
    )
    with closing(connect(source_db)) as conn, conn, conn.cursor() as cur:
        assert upsert_source_vectors(cur, CHUNK_SOURCE, generated) == {
            2: "chunk_embeddings_0002d"
        }
        upsert_source_vectors(cur, CHUNK_SOURCE, generated)
        cur.execute(
            "SELECT chunk_id, model, embedding::text FROM "
            "chunk_embeddings_0002d ORDER BY chunk_id"
        )
        assert cur.fetchall() == [(row_id, "alpha", "[1,2]") for row_id in ids]
        assert_corpus_contract(cur, CHUNK_SOURCE, 2)
