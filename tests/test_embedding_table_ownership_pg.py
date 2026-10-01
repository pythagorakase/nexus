"""Real catalog and transaction proofs for decision 810-Q3; no owner writes."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

from psycopg2.extras import RealDictCursor
import pytest
from sqlalchemy import create_engine

from nexus.agents.memnon.utils.content_processor import ContentProcessor
from nexus.agents.memnon.utils.db_schema import DatabaseManager
from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager
from nexus.agents.memnon.utils.embedding_tables import (
    ensure_embedding_table,
)
from nexus.agents.memnon.utils.source_embeddings import (
    CHARACTER_EXPERIENCE_SOURCE,
    RETROGRADE_SUMMARY_SOURCE,
    EmbeddingSource,
    active_memnon_embedding_model_dimensions,
    generate_source_vectors,
    load_memnon_settings,
    upsert_source_vectors,
)
from nexus.agents.orrery.experiences import _insert_experience
from nexus.database import database_url
from nexus.jobs.embeddings import _NARRATIVE_CHUNKS
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_character,
    seed_committed_chunk,
    seed_story_clock,
    sqlalchemy_url,
)
from tests.test_orrery.test_retrograde_embedding_pg import _insert_retrograde_summaries

pytestmark = pytest.mark.requires_postgres

CHUNK_SOURCE = EmbeddingSource(
    label="narrative chunk",
    plural_label="Narrative chunks",
    table="narrative_chunks",
    id_column="id",
    text_column="raw_text",
    embedding_fk_column="chunk_id",
    ensure_table=ensure_embedding_table,
    table_name_for_dimensions=lambda d: f"chunk_embeddings_{d:04d}d",
)
SOURCES = [CHUNK_SOURCE, RETROGRADE_SUMMARY_SOURCE, CHARACTER_EXPERIENCE_SOURCE]


@pytest.fixture
def ownership_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Clone stamped schema, pin TEST, and route before any runtime construction."""
    with disposable_slot_database("qa640_810s2_contract") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations ORDER BY version")
            print(f"clone {dbname} starting migration stamps: {cur.fetchall()}")
        yield dbname


def seed_source(
    dbname: str, spec: EmbeddingSource, text: str = "The ledger survived."
) -> int:
    """Seed production source identities and render without inference."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT coalesce(max(scene), 0) + 1 FROM chunk_metadata")
        scene = int(cur.fetchone()[0])
    if spec is CHUNK_SOURCE:
        return seed_committed_chunk(dbname, raw_text=text, scene=scene)
    summary_id = _insert_retrograde_summaries(dbname, [text])[0]
    if spec is RETROGRADE_SUMMARY_SOURCE:
        return summary_id
    seed_story_clock(
        dbname, world_time=datetime(2196, 1, 1, tzinfo=timezone.utc), scene=scene
    )
    _, entity_id = seed_character(dbname, name=f"Witness {summary_id}")
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT recorded_at_chunk_id, world_event_id FROM "
            "retrograde_summaries WHERE id = %s",
            (summary_id,),
        )
        chunk_id, event_id = cur.fetchone()
        _insert_experience(
            cur,
            character_entity_id=entity_id,
            anchor_chunk_id=chunk_id,
            world_event_ids=[event_id],
            claim_id=None,
            claim_awareness_id=None,
            basis="witness",
            location_id=None,
            world_time=datetime.now(timezone.utc),
            seed_summary=text,
            salience=0.5,
            world_layer="primary",
        )
        cur.execute(
            "SELECT id FROM character_experiences WHERE character_entity_id = %s",
            (entity_id,),
        )
        experience_id = int(cur.fetchone()[0])
        # No deterministic rendering writer exists outside the provider/lease path.
        cur.execute(
            "UPDATE character_experiences SET experience_text = %s, "
            "render_model = 'TEST', "
            "renderer_version = '810-S2', render_generation_id = %s WHERE id = %s",
            (text, str(uuid4()), experience_id),
        )
        return experience_id


def catalog_snapshot(cur: Any) -> list[Any]:
    """Capture public objects, definitions, comments, keys and extension inventory."""
    queries = [
        "SELECT c.oid, c.relname, c.relkind, obj_description(c.oid, 'pg_class') "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' ORDER BY c.oid",
        "SELECT a.attrelid, a.attnum, a.attname, format_type(a.atttypid,a.atttypmod), "
        "a.attnotnull, pg_get_expr(d.adbin,d.adrelid), "
        "col_description(a.attrelid,a.attnum) "
        "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d "
        "ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
        "WHERE n.nspname='public' AND a.attnum>0 ORDER BY a.attrelid,a.attnum",
        "SELECT oid, conrelid, conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace='public'::regnamespace ORDER BY oid",
        "SELECT indexrelid, indrelid, pg_get_indexdef(indexrelid), indisvalid "
        "FROM pg_index WHERE indrelid IN (SELECT oid FROM pg_class "
        "WHERE relnamespace='public'::regnamespace) ORDER BY indexrelid",
        "SELECT oid, extname, extversion FROM pg_extension ORDER BY oid",
    ]
    result = []
    for query in queries:
        cur.execute(query)
        result.append(cur.fetchall())
    return result


def assert_corpus_contract(cur: Any, spec: EmbeddingSource, dimensions: int) -> None:
    """Assert real definitions and every exact comment independently of validation."""
    name = spec.table_name_for_dimensions(dimensions)
    fk = spec.embedding_fk_column
    cur.execute(
        "SELECT attname, format_type(atttypid,atttypmod), attnotnull, "
        "col_description(attrelid,attnum) FROM pg_attribute "
        "WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum",
        (f"public.{name}",),
    )
    columns = cur.fetchall()
    descriptions = {
        "chunk_id": "Narrative chunk represented by this vector.",
        "summary_id": "Retrograde summary represented by this vector.",
        "experience_id": (
            "Actor-owned character_experiences.id bound to this vector row."
        ),
    }
    experience = fk == "experience_id"
    assert columns == [
        (fk, "bigint", True, descriptions[fk]),
        (
            "model",
            "text",
            True,
            (
                "Active MEMNON embedding model that produced this vector."
                if experience
                else "Configured embedding model identity."
            ),
        ),
        (
            "embedding",
            f"vector({dimensions})",
            True,
            (
                f"Exact {dimensions}-dimension embedding of experience_text."
                if experience
                else (
                    "Dense narrative text embedding."
                    if fk == "chunk_id"
                    else "Dense Retrograde summary text embedding."
                )
            ),
        ),
        (
            "created_at",
            "timestamp with time zone",
            True,
            "Database time of the most recent successful vector upsert.",
        ),
    ]
    cur.execute(
        "SELECT pg_get_expr(adbin,adrelid) FROM pg_attrdef WHERE adrelid=%s::regclass",
        (name,),
    )
    assert cur.fetchall() == [("now()",)]
    cur.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE "
        "conrelid=%s::regclass ORDER BY contype",
        (name,),
    )
    assert cur.fetchall() == [
        (f"FOREIGN KEY ({fk}) REFERENCES {spec.table}(id) ON DELETE CASCADE",),
        (f"PRIMARY KEY ({fk}, model)",),
    ]
    cur.execute("SELECT obj_description(%s::regclass,'pg_class')", (name,))
    table_comments = {
        "chunk_id": "Narrative chunk vectors partitioned by embedding dimensions.",
        "summary_id": "Retrograde summary vectors partitioned by embedding dimensions.",
        "experience_id": (
            "Actor-owned character-experience vectors partitioned by "
            "embedding dimensions."
        ),
    }
    assert cur.fetchone() == (table_comments[fk],)
    cur.execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname=%s", (f"{name}_model_idx",)
    )
    assert cur.fetchone() == (
        f"CREATE INDEX {name}_model_idx ON public.{name} USING btree (model)",
    )
    for suffix, comment in [
        ("pkey", "One vector per source row and embedding model."),
        ("model_idx", "Lookup of vector rows by embedding model."),
    ]:
        cur.execute(
            "SELECT obj_description(%s::regclass,'pg_class')", (f"{name}_{suffix}",)
        )
        assert cur.fetchone() == (comment,)


@pytest.mark.parametrize("spec", SOURCES, ids=lambda s: s.embedding_fk_column)
@pytest.mark.parametrize("adapter", ["sqlalchemy", "tuple", "dict"])
def test_ensure_creates_commented_corpus_contract(
    ownership_db: str, spec: EmbeddingSource, adapter: str
) -> None:
    row_id = seed_source(ownership_db, spec)
    name = spec.table_name_for_dimensions(3)
    if adapter == "sqlalchemy":
        engine = create_engine(sqlalchemy_url(ownership_db))
        try:
            with engine.begin() as sa_conn:
                assert spec.ensure_table(sa_conn, 3) == name
        finally:
            engine.dispose()
    else:
        with (
            closing(
                connect(
                    ownership_db,
                    cursor_factory=RealDictCursor if adapter == "dict" else None,
                )
            ) as conn,
            conn,
            conn.cursor() as cur,
        ):
            assert spec.ensure_table(cur, 3) == name
    with closing(connect(ownership_db)) as conn, conn, conn.cursor() as cur:
        assert_corpus_contract(cur, spec, 3)
        upsert_source_vectors(cur, spec, {row_id: [("proof", [1.0, 2.0, 3.0])]})
        cur.execute(f"DELETE FROM {spec.table} WHERE id=%s", (row_id,))
        cur.execute(f"SELECT count(*) FROM {name}")
        assert cur.fetchone() == (0,)


@pytest.mark.parametrize("spec", SOURCES, ids=lambda s: s.embedding_fk_column)
def test_ensure_is_idempotent_and_never_builds_ann(
    ownership_db: str, spec: EmbeddingSource
) -> None:
    row_id = seed_source(ownership_db, spec)
    with closing(connect(ownership_db)) as conn, conn, conn.cursor() as cur:
        for dimensions in [3, 2560]:
            name = spec.ensure_table(cur, dimensions)
            upsert_source_vectors(cur, spec, {row_id: [("proof", [0.5] * dimensions)]})
            before = catalog_snapshot(cur)
            cur.execute(f"SELECT embedding::text FROM {name}")
            vector = cur.fetchall()
            spec.ensure_table(cur, dimensions)
            assert catalog_snapshot(cur) == before
            cur.execute(f"SELECT embedding::text FROM {name}")
            assert cur.fetchall() == vector
            assert_corpus_contract(cur, spec, dimensions)
            cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename=%s", (name,))
            assert all(
                "hnsw" not in row[0] and "ivfflat" not in row[0]
                for row in cur.fetchall()
            )


@pytest.mark.parametrize("spec", SOURCES, ids=lambda s: s.embedding_fk_column)
@pytest.mark.parametrize("initially", ["IMMEDIATE", "DEFERRED"])
def test_ensure_refuses_deferrable_primary_key_before_comment_writes(
    ownership_db: str, spec: EmbeddingSource, initially: str
) -> None:
    """Reject an unusable ON CONFLICT arbiter before documenting the table."""
    name = spec.table_name_for_dimensions(3)
    constraint = f"{name}_deferrable_pk"
    with closing(connect(ownership_db)) as conn, conn, conn.cursor() as cur:
        spec.ensure_table(cur, 3)
        cur.execute(f"ALTER TABLE {name} DROP CONSTRAINT {name}_pkey")
        cur.execute(
            f"ALTER TABLE {name} ADD CONSTRAINT {constraint} "
            f"PRIMARY KEY ({spec.embedding_fk_column}, model) "
            f"DEFERRABLE INITIALLY {initially}"
        )
        cur.execute(f"COMMENT ON TABLE {name} IS NULL")
        cur.execute("SELECT obj_description(%s::regclass, 'pg_class')", (name,))
        comment_before = cur.fetchone()
        assert comment_before == (None,)
        before = catalog_snapshot(cur)

        with pytest.raises(
            RuntimeError, match=name + r".*" + constraint + r".*expected.*observed"
        ) as error:
            spec.ensure_table(cur, 3)
        print(str(error.value))
        cur.execute("SELECT obj_description(%s::regclass, 'pg_class')", (name,))
        assert cur.fetchone() == comment_before
        assert catalog_snapshot(cur) == before


MALFORMED = [
    "dimension",
    "source_type",
    "nullable_model",
    "primary",
    "fk_target",
    "fk_delete",
    "timestamp",
    "view",
    "index",
]


@pytest.mark.parametrize("spec", SOURCES, ids=lambda s: s.embedding_fk_column)
@pytest.mark.parametrize("malformation", MALFORMED)
def test_ensure_refuses_malformed_objects_before_writing(
    ownership_db: str, spec: EmbeddingSource, malformation: str
) -> None:
    row_id = seed_source(ownership_db, spec)
    name = spec.table_name_for_dimensions(3)
    fk = spec.embedding_fk_column
    with closing(connect(ownership_db)) as conn:
        with conn, conn.cursor() as cur:
            if malformation == "view":
                cur.execute(f"CREATE VIEW {name} AS SELECT 810 AS marker")
            else:
                spec.ensure_table(cur, 3)
                upsert_source_vectors(
                    cur, spec, {row_id: [("marker", [1.0, 2.0, 3.0])]}
                )
                if malformation == "dimension":
                    cur.execute(
                        f"ALTER TABLE {name} ALTER COLUMN embedding TYPE "
                        "vector(4) USING '[1,2,3,4]'::vector(4)"
                    )
                elif malformation == "source_type":
                    cur.execute(f"ALTER TABLE {name} ALTER COLUMN {fk} TYPE integer")
                elif malformation == "nullable_model":
                    cur.execute(f"ALTER TABLE {name} DROP CONSTRAINT {name}_pkey")
                    cur.execute(f"ALTER TABLE {name} ALTER COLUMN model DROP NOT NULL")
                elif malformation == "primary":
                    cur.execute(f"ALTER TABLE {name} DROP CONSTRAINT {name}_pkey")
                elif malformation.startswith("fk_"):
                    cur.execute(f"ALTER TABLE {name} DROP CONSTRAINT {name}_{fk}_fkey")
                    # Remove marker so a wrong target constraint remains valid.
                    cur.execute(f"DELETE FROM {name}")
                    target = (
                        (
                            "narrative_chunks"
                            if spec.table != "narrative_chunks"
                            else "retrograde_summaries"
                        )
                        if malformation == "fk_target"
                        else spec.table
                    )
                    target_column = "id"
                    action = "CASCADE" if malformation == "fk_target" else "NO ACTION"
                    cur.execute(
                        f"ALTER TABLE {name} ADD FOREIGN KEY ({fk}) "
                        f"REFERENCES {target}({target_column}) ON DELETE {action}"
                    )
                elif malformation == "timestamp":
                    cur.execute(
                        f"ALTER TABLE {name} ALTER COLUMN created_at SET "
                        "DEFAULT '2000-01-01'::timestamptz"
                    )
                elif malformation == "index":
                    cur.execute(f"DROP INDEX {name}_model_idx")
                    cur.execute(f"CREATE INDEX {name}_model_idx ON {name} ({fk})")
        with conn.cursor() as cur:
            before = catalog_snapshot(cur)
            cur.execute(f"SELECT * FROM {name}")
            marker = cur.fetchall()
            with pytest.raises(
                RuntimeError, match=name + r".*expected.*observed"
            ) as error:
                spec.ensure_table(cur, 3)
            print(str(error.value))
            assert catalog_snapshot(cur) == before
            cur.execute(f"SELECT * FROM {name}")
            assert cur.fetchall() == marker
        conn.rollback()
        with conn.cursor() as cur:
            assert catalog_snapshot(cur) == before
            cur.execute(f"SELECT * FROM {name}")
            assert cur.fetchall() == marker


@pytest.mark.parametrize("spec", SOURCES, ids=lambda s: s.embedding_fk_column)
def test_ensure_and_upsert_roll_back_with_the_caller(
    ownership_db: str, spec: EmbeddingSource
) -> None:
    row_id = seed_source(ownership_db, spec)
    name = spec.table_name_for_dimensions(3)
    with closing(connect(ownership_db)) as conn:
        with pytest.raises(ValueError, match="caller abort"):
            with conn, conn.cursor() as cur:
                upsert_source_vectors(cur, spec, {row_id: [("proof", [1.0, 2.0, 3.0])]})
                raise ValueError("caller abort")
        with conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (name,))
            assert cur.fetchone() == (None,)
            spec.ensure_table(cur, 3)
        with pytest.raises(ValueError, match="caller abort"):
            with conn, conn.cursor() as cur:
                upsert_source_vectors(cur, spec, {row_id: [("proof", [1.0, 2.0, 3.0])]})
                raise ValueError("caller abort")
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {name}")
            assert cur.fetchone() == (0,)


def test_constructor_leaves_missing_indexes_and_catalog_unchanged(
    ownership_db: str,
) -> None:
    with closing(connect(ownership_db)) as conn, conn, conn.cursor() as cur:
        name = ensure_embedding_table(cur, 3)
        cur.execute(f"DROP INDEX {name}_model_idx")
        cur.execute("DROP INDEX narrative_chunks_text_idx")
        before = catalog_snapshot(cur)
    for enabled in [False, True]:
        manager = DatabaseManager(
            database_url(ownership_db),
            {"retrieval": {"hybrid_search": {"enabled": enabled}}},
        )
        manager.close()
        with closing(connect(ownership_db)) as conn, conn.cursor() as cur:
            assert catalog_snapshot(cur) == before
            for index in [f"{name}_model_idx", "narrative_chunks_text_idx"]:
                cur.execute("SELECT to_regclass(%s)", (index,))
                assert cur.fetchone() == (None,)


def test_constructor_refuses_missing_vector_extension(ownership_db: str) -> None:
    with closing(connect(ownership_db)) as conn, conn, conn.cursor() as cur:
        cur.execute("DROP EXTENSION vector CASCADE")
    with pytest.raises(
        ConnectionError, match="Missing vector extension.*migration 022"
    ):
        DatabaseManager(database_url(ownership_db))


def test_embedding_job_source_path_propagates_ensure_failure(ownership_db: str) -> None:
    """The job's real source upsert propagates drift and rolls back prior writes."""
    settings = load_memnon_settings()
    embedder = EmbeddingManager(settings=settings)
    dimensions = next(iter(active_memnon_embedding_model_dimensions().values()))
    spec = _NARRATIVE_CHUNKS
    row_id = seed_source(ownership_db, CHUNK_SOURCE)
    name = spec.table_name_for_dimensions(dimensions)
    with closing(connect(ownership_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {name} (marker text)")
        cur.execute(f"INSERT INTO {name} VALUES ('preserved')")
        before = catalog_snapshot(cur)
        with pytest.raises(RuntimeError) as direct_error:
            spec.ensure_table(cur, dimensions)
    generated = generate_source_vectors(
        spec,
        {row_id: "The clerk carried the ledger across the empty hall."},
        embedder.get_available_models(),
        embedder.generate_embedding,
    )
    # A prior vector and its lazy table must disappear when the active table fails.
    generated[row_id].insert(0, ("rollback-proof", [1.0, 2.0, 3.0]))
    with closing(connect(ownership_db)) as conn:
        with pytest.raises(RuntimeError, match=name + r".*expected.*observed") as error:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE narrative_chunks SET raw_text='uncommitted' WHERE id=%s",
                    (row_id,),
                )
                upsert_source_vectors(cur, spec, generated)
        assert type(error.value) is type(direct_error.value)
        assert str(error.value) == str(direct_error.value)
        print(f"job source failure propagated unchanged: {error.value}")
        with conn.cursor() as cur:
            assert catalog_snapshot(cur) == before
            cur.execute(
                "SELECT raw_text, embedding_generated_at FROM "
                "narrative_chunks WHERE id=%s",
                (row_id,),
            )
            assert cur.fetchone() == ("The ledger survived.", None)
            cur.execute("SELECT to_regclass('chunk_embeddings_0003d')")
            assert cur.fetchone() == (None,)
            cur.execute(f"SELECT * FROM {name}")
            assert cur.fetchall() == [("preserved",)]


def test_content_processor_embedding_method_propagates_ensure_failure(
    ownership_db: str,
) -> None:
    """Exercise the legacy embedding method without the #1091 metadata INSERT."""
    settings = load_memnon_settings()
    embedder = EmbeddingManager(settings=settings)
    dimensions = next(iter(active_memnon_embedding_model_dimensions().values()))
    name = CHUNK_SOURCE.table_name_for_dimensions(dimensions)
    row_id = seed_source(ownership_db, CHUNK_SOURCE)
    with closing(connect(ownership_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {name} (marker text)")
        before = catalog_snapshot(cur)
    manager = DatabaseManager(database_url(ownership_db))
    try:
        processor = ContentProcessor(manager, embedder, settings)
        with pytest.raises(RuntimeError, match=name + r".*expected.*observed"):
            with manager.Session.begin() as session:
                processor._generate_chunk_embeddings(
                    session, row_id, "The ledger survived."
                )
    finally:
        manager.close()
    with closing(connect(ownership_db)) as conn, conn.cursor() as cur:
        assert catalog_snapshot(cur) == before
        cur.execute(f"SELECT count(*) FROM {name}")
        assert cur.fetchone() == (0,)
