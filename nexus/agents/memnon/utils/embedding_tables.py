"""Shared helpers for MEMNON's dimension-specific embedding tables."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, List, Optional, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Connection

EMBEDDING_TABLE_PATTERN = re.compile(r"^chunk_embeddings_(?P<dimensions>\d+)d$")
RETROGRADE_SUMMARY_EMBEDDING_TABLE_PATTERN = re.compile(
    r"^retrograde_summary_embeddings_(?P<dimensions>\d+)d$"
)
CHARACTER_EXPERIENCE_EMBEDDING_TABLE_PATTERN = re.compile(
    r"^character_experience_embeddings_(?P<dimensions>\d+)d$"
)

# pgvector 0.8.x caps HNSW/IVFFlat indexes at 2000 dimensions in this local
# deployment. Higher-dimensional tables still support exact vector search.
PGVECTOR_ANN_INDEX_MAX_DIMENSIONS = 2000


class _DDLExecutor(Protocol):
    """Structural interface shared by SQLAlchemy connections and DBAPI cursors."""

    def execute(self, statement: Any) -> Any:
        """Execute one DDL statement."""


def _execute_ddl(executor: _DDLExecutor, statement: str) -> None:
    """Execute raw DDL through SQLAlchemy or a DBAPI cursor."""
    exec_driver_sql = getattr(executor, "exec_driver_sql", None)
    if callable(exec_driver_sql):
        exec_driver_sql(statement)
        return
    executor.execute(statement)


def table_name_for_dimensions(dimensions: int) -> str:
    """Return the canonical embedding table name for ``dimensions``."""
    if dimensions <= 0:
        raise ValueError(f"Embedding dimensions must be positive, got {dimensions}")
    return f"chunk_embeddings_{dimensions:04d}d"


def resolve_dimension_table(dimensions: int) -> str:
    """Return the embedding table that stores vectors for ``dimensions``."""
    return table_name_for_dimensions(dimensions)


def retrograde_summary_table_name_for_dimensions(dimensions: int) -> str:
    """Return the dedicated Retrograde summary table for ``dimensions``."""
    if dimensions <= 0:
        raise ValueError(f"Embedding dimensions must be positive, got {dimensions}")
    return f"retrograde_summary_embeddings_{dimensions:04d}d"


def character_experience_table_name_for_dimensions(dimensions: int) -> str:
    """Return the dedicated character-experience table for ``dimensions``."""
    if dimensions <= 0:
        raise ValueError(f"Embedding dimensions must be positive, got {dimensions}")
    return f"character_experience_embeddings_{dimensions:04d}d"


def parse_embedding_table_dimensions(table_name: str) -> Optional[int]:
    """Return dimensions encoded in an embedding table name, if it matches."""
    match = EMBEDDING_TABLE_PATTERN.match(table_name)
    if not match:
        return None
    return int(match.group("dimensions"))


def parse_retrograde_summary_embedding_table_dimensions(
    table_name: str,
) -> Optional[int]:
    """Return dimensions encoded in a Retrograde summary embedding table."""
    match = RETROGRADE_SUMMARY_EMBEDDING_TABLE_PATTERN.match(table_name)
    if not match:
        return None
    return int(match.group("dimensions"))


def parse_character_experience_embedding_table_dimensions(
    table_name: str,
) -> Optional[int]:
    """Return dimensions encoded in a character-experience embedding table."""
    match = CHARACTER_EXPERIENCE_EMBEDDING_TABLE_PATTERN.match(table_name)
    if not match:
        return None
    return int(match.group("dimensions"))


def supports_pgvector_ann_index(dimensions: int) -> bool:
    """Return whether pgvector ANN indexes support ``dimensions`` locally."""
    return 0 < dimensions <= PGVECTOR_ANN_INDEX_MAX_DIMENSIONS


def list_embedding_tables(connection: Connection) -> List[str]:
    """List existing dimension-specific embedding tables in the current schema."""
    rows = connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name ~ '^chunk_embeddings_[0-9]+d$'
            ORDER BY table_name
            """
        )
    )
    return [row[0] for row in rows]


def embedding_table_exists(connection: Connection, table_name: str) -> bool:
    """Return whether ``table_name`` exists in the current public schema."""
    exists = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    ).scalar()
    return bool(exists)


def _catalog_rows(connection: Any, statement: str) -> List[dict[str, Any]]:
    """Read catalog rows through SQLAlchemy or tuple/dictionary DBAPI cursors."""
    driver = getattr(connection, "exec_driver_sql", None)
    if callable(driver):
        return [dict(row) for row in driver(statement).mappings()]
    connection.execute(statement)
    names = [column[0] for column in connection.description]
    return [
        dict(row) if isinstance(row, Mapping) else dict(zip(names, row))
        for row in connection.fetchall()
    ]


def _require_contract(object_name: str, expected: Any, observed: Any) -> None:
    """Refuse catalog drift without changing the caller's transaction."""
    if observed != expected:
        raise RuntimeError(
            f"{object_name}: expected {expected!r}; observed {observed!r}"
        )


def _ensure_corpus_table(
    connection: Any,
    dimensions: int,
    table_name: str,
    source_id: str,
    source_table: str,
    table_comment: str,
    column_comments: dict[str, str],
) -> str:
    """Validate all existing objects before lazy DDL or documentation writes."""
    relations = _catalog_rows(
        connection,
        f"""SELECT c.oid, c.relkind FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = '{table_name}'""",
    )
    primary_index = f"{table_name}_pkey"
    if relations:
        _require_contract(
            f"public.{table_name} relation kind", "r", relations[0]["relkind"]
        )
        oid = relations[0]["oid"]
        columns = _catalog_rows(
            connection,
            f"""SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS type,
            a.attnotnull, pg_get_expr(d.adbin, d.adrelid) AS default_expr
            FROM pg_attribute a LEFT JOIN pg_attrdef d
              ON d.adrelid = a.attrelid AND d.adnum = a.attnum
            WHERE a.attrelid = {oid} AND a.attnum > 0 AND NOT a.attisdropped""",
        )
        by_name = {row["attname"]: row for row in columns}
        for column, expected_type in {
            source_id: "bigint",
            "model": "text",
            "embedding": f"vector({dimensions})",
            "created_at": "timestamp with time zone",
        }.items():
            row = by_name.get(column)
            _require_contract(
                f"{table_name}.{column} type/nullability",
                (expected_type, True),
                None if row is None else (row["type"], row["attnotnull"]),
            )
        default = by_name["created_at"]["default_expr"]
        normalized = re.sub(r"\s+", "", default or "").lower()
        if normalized not in {"now()", "current_timestamp", "transaction_timestamp()"}:
            raise RuntimeError(
                f"{table_name}.created_at: expected NOW() or CURRENT_TIMESTAMP "
                f"default; observed {default!r}"
            )
        constraints = _catalog_rows(
            connection,
            f"""SELECT c.contype, c.convalidated, c.confdeltype,
            ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num, ord)
              JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num
              ORDER BY k.ord) AS columns,
            rn.nspname AS target_schema, r.relname AS target_table,
            ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num, ord)
              JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.num
              ORDER BY k.ord) AS target_columns,
            i.relname AS index_name
            FROM pg_constraint c LEFT JOIN pg_class r ON r.oid = c.confrelid
            LEFT JOIN pg_namespace rn ON rn.oid = r.relnamespace
            LEFT JOIN pg_class i ON i.oid = c.conindid
            WHERE c.conrelid = {oid}""",
        )
        primary = [row for row in constraints if row["contype"] == "p"]
        _require_contract(
            f"{table_name} primary key",
            [[source_id, "model"]],
            [row["columns"] for row in primary],
        )
        primary_index = primary[0]["index_name"]
        foreign = [
            row
            for row in constraints
            if row["contype"] == "f" and row["columns"] == [source_id]
        ]
        expected_fk = ([source_id], "public", source_table, ["id"], "c", True)
        observed_fk = [
            (
                row["columns"],
                row["target_schema"],
                row["target_table"],
                row["target_columns"],
                row["confdeltype"],
                row["convalidated"],
            )
            for row in foreign
        ]
        _require_contract(
            f"{table_name}.{source_id} foreign key", [expected_fk], observed_fk
        )

    index_name = f"{table_name}_model_idx"
    indexes = _catalog_rows(
        connection,
        f"""SELECT t.relname AS table_name, tn.nspname AS table_schema,
        am.amname, i.indisvalid, i.indisready, i.indisunique,
        i.indpred IS NULL AS nonpartial, i.indexprs IS NULL AS noexpressions,
        i.indnatts, i.indnkeyatts,
        ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY k(num, ord)
          JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.num
          ORDER BY k.ord) AS columns
        FROM pg_class idx JOIN pg_namespace n ON n.oid = idx.relnamespace
        LEFT JOIN pg_index i ON i.indexrelid = idx.oid
        LEFT JOIN pg_class t ON t.oid = i.indrelid
        LEFT JOIN pg_namespace tn ON tn.oid = t.relnamespace
        LEFT JOIN pg_am am ON am.oid = idx.relam
        WHERE n.nspname = 'public' AND idx.relname = '{index_name}'""",
    )
    if indexes:
        _require_contract(
            index_name,
            dict(
                table_name=table_name,
                table_schema="public",
                amname="btree",
                indisvalid=True,
                indisready=True,
                indisunique=False,
                nonpartial=True,
                noexpressions=True,
                indnatts=1,
                indnkeyatts=1,
                columns=["model"],
            ),
            indexes[0],
        )
    if not relations:
        _execute_ddl(
            connection,
            f"""CREATE TABLE public.{table_name} (
                {source_id} BIGINT NOT NULL
                    REFERENCES public.{source_table}(id) ON DELETE CASCADE,
                model TEXT NOT NULL,
                embedding vector({dimensions}) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY ({source_id}, model)
            )""",
        )
    if not indexes:
        _execute_ddl(
            connection,
            f"CREATE INDEX {index_name} ON public.{table_name} (model)",
        )
    _execute_ddl(
        connection, f"COMMENT ON TABLE public.{table_name} IS '{table_comment}'"
    )
    for column, description in column_comments.items():
        _execute_ddl(
            connection,
            f"COMMENT ON COLUMN public.{table_name}.{column} IS '{description}'",
        )
    _execute_ddl(
        connection,
        f"COMMENT ON INDEX public.{primary_index} IS 'One vector per source "
        f"row and embedding model.'",
    )
    _execute_ddl(
        connection,
        f"COMMENT ON INDEX public.{index_name} IS 'Lookup of vector rows by "
        f"embedding model.'",
    )
    return table_name


def ensure_embedding_table(connection: Any, dimensions: int) -> str:
    """Validate or create the lazy chunk table in the caller's transaction."""
    return _ensure_corpus_table(
        connection,
        dimensions,
        table_name_for_dimensions(dimensions),
        "chunk_id",
        "narrative_chunks",
        "Narrative chunk vectors partitioned by embedding dimensions.",
        {
            "chunk_id": "Narrative chunk represented by this vector.",
            "model": "Configured embedding model identity.",
            "embedding": "Dense narrative text embedding.",
            "created_at": "Database time of the most recent successful vector upsert.",
        },
    )


def ensure_retrograde_summary_embedding_table(
    connection: _DDLExecutor, dimensions: int
) -> str:
    """Validate or create the lazy summary table in the caller's transaction."""
    return _ensure_corpus_table(
        connection,
        dimensions,
        retrograde_summary_table_name_for_dimensions(dimensions),
        "summary_id",
        "retrograde_summaries",
        "Retrograde summary vectors partitioned by embedding dimensions.",
        {
            "summary_id": "Retrograde summary represented by this vector.",
            "model": "Configured embedding model identity.",
            "embedding": "Dense Retrograde summary text embedding.",
            "created_at": "Database time of the most recent successful vector upsert.",
        },
    )


def ensure_character_experience_embedding_table(
    connection: _DDLExecutor, dimensions: int
) -> str:
    """Validate or create the lazy experience table in the caller's transaction."""
    return _ensure_corpus_table(
        connection,
        dimensions,
        character_experience_table_name_for_dimensions(dimensions),
        "experience_id",
        "character_experiences",
        "Actor-owned character-experience vectors partitioned by embedding dimensions.",
        {
            "experience_id": "Actor-owned character_experiences.id bound to "
            "this vector row.",
            "model": "Active MEMNON embedding model that produced this vector.",
            "embedding": f"Exact {dimensions}-dimension embedding of experience_text.",
            "created_at": "Database time of the most recent successful vector upsert.",
        },
    )


def candidate_ann_index_name(table_name: str) -> str:
    """Validate the table and return its stable, explicit promotion index name."""
    dimensions = (
        parse_embedding_table_dimensions(table_name)
        or parse_retrograde_summary_embedding_table_dimensions(table_name)
        or parse_character_experience_embedding_table_dimensions(table_name)
    )
    if dimensions != 2560:
        raise ValueError(f"ANN gate supports only 2560d embedding tables: {table_name}")
    return f"{table_name}_halfvec_hnsw_idx"


def build_candidate_ann_index(executor: Any, table_name: str) -> str:
    """Build an explicitly requested candidate; runtime search never calls this."""
    name = candidate_ann_index_name(table_name)
    _execute_ddl(
        executor,
        f"CREATE INDEX {name} ON {table_name} USING hnsw "
        "((embedding::halfvec(2560)) halfvec_cosine_ops)",
    )
    return name


def drop_candidate_ann_index(executor: Any, table_name: str) -> None:
    """Drop only the named candidate index for an explicitly supplied table."""
    _execute_ddl(
        executor, f"DROP INDEX IF EXISTS {candidate_ann_index_name(table_name)}"
    )
