"""Unit tests for MEMNON database setup helpers."""

from nexus.agents.memnon.utils import db_access


class FakeCursor:
    """Small cursor stand-in that records SQL issued by setup_database_indexes."""

    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, *_args, **_kwargs):
        self.statements.append(str(statement))

    def fetchone(self):
        return (1,)


class FakeConnection:
    """Connection stand-in for setup_database_indexes."""

    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.autocommit = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_setup_database_indexes_skips_ann_indexes_for_high_dimensions(monkeypatch):
    """2560d tables should keep model indexes without attempting unsupported ANN."""
    cursor = FakeCursor()
    connection = FakeConnection(cursor)

    monkeypatch.setattr(db_access.psycopg2, "connect", lambda **_kwargs: connection)
    monkeypatch.setattr(
        db_access,
        "_list_existing_embedding_tables",
        lambda _cursor: ["chunk_embeddings_2560d"],
    )

    assert db_access.setup_database_indexes("postgresql://user:pass@localhost/NEXUS")

    statements = "\n".join(cursor.statements).lower()
    assert "chunk_embeddings_2560d_model_idx" in statements
    assert "using hnsw" not in statements
    assert "using ivfflat" not in statements
    assert connection.closed


def test_setup_database_indexes_fails_on_unparseable_embedding_table(monkeypatch):
    """Malformed embedding table names should not fall through to ANN creation."""
    cursor = FakeCursor()
    connection = FakeConnection(cursor)

    monkeypatch.setattr(db_access.psycopg2, "connect", lambda **_kwargs: connection)
    monkeypatch.setattr(
        db_access,
        "_list_existing_embedding_tables",
        lambda _cursor: ["chunk_embeddings_bad"],
    )

    assert not db_access.setup_database_indexes("postgresql://user:pass@localhost/NEXUS")
    assert connection.closed
