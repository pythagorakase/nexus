"""Embedding orchestration shared by MEMNON's source-owned corpora.

Narrative chunks, Retrograde summaries and character experiences each keep
their own table, identity, authorization and dimension-specific vector
tables. What they share is how a row becomes vectors: load its text, check the
loaded embedders against configuration, generate every vector before any
write, then create tables, upsert and stamp ``embedding_generated_at`` in one
transaction. An :class:`EmbeddingSource` names a corpus's storage; the
functions here do the rest identically for every corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from nexus.agents.memnon.utils.embedding_tables import (
    character_experience_table_name_for_dimensions,
    ensure_character_experience_embedding_table,
    ensure_retrograde_summary_embedding_table,
    retrograde_summary_table_name_for_dimensions,
)

ModelVectors = List[Tuple[str, List[float]]]
"""One row's ``(model name, vector)`` pairs, in embedder order."""


@dataclass(frozen=True)
class EmbeddingSource:
    """Storage facts for one corpus whose rows receive MEMNON vectors.

    Attributes:
        label: Singular noun for error messages, e.g. ``"Retrograde summary"``.
        plural_label: Capitalized plural for error messages.
        table: Source table that owns the rows and their ironman stamp.
        id_column: Source primary key.
        text_column: Column whose text is embedded.
        embedding_fk_column: Vector-table column referencing ``id_column``;
            also the id key of :func:`embed_source_rows`' payload.
        ensure_table: Creates the dimension table on a DBAPI cursor and
            returns its name.
        table_name_for_dimensions: Names the dimension table without DDL.
        validity_predicate: Extra SQL condition a row must satisfy to be
            loaded and stamped, or ``None``.
    """

    label: str
    plural_label: str
    table: str
    id_column: str
    text_column: str
    embedding_fk_column: str
    ensure_table: Callable[[Any, int], str]
    table_name_for_dimensions: Callable[[int], str]
    validity_predicate: Optional[str] = None

    def validity_sql(self) -> str:
        """Return the validity predicate as an ``AND`` clause, or ``""``."""
        if self.validity_predicate is None:
            return ""
        return f" AND {self.validity_predicate}"


RETROGRADE_SUMMARY_SOURCE = EmbeddingSource(
    label="Retrograde summary",
    plural_label="Retrograde summaries",
    table="retrograde_summaries",
    id_column="id",
    text_column="summary_text",
    embedding_fk_column="summary_id",
    ensure_table=ensure_retrograde_summary_embedding_table,
    table_name_for_dimensions=retrograde_summary_table_name_for_dimensions,
)

CHARACTER_EXPERIENCE_SOURCE = EmbeddingSource(
    label="character experience",
    plural_label="Character experiences",
    table="character_experiences",
    id_column="id",
    text_column="experience_text",
    embedding_fk_column="experience_id",
    ensure_table=ensure_character_experience_embedding_table,
    table_name_for_dimensions=character_experience_table_name_for_dimensions,
    validity_predicate="invalidation_status = 'valid'",
)

AUDITED_SOURCES: Tuple[EmbeddingSource, ...] = (
    RETROGRADE_SUMMARY_SOURCE,
    CHARACTER_EXPERIENCE_SOURCE,
)
"""Corpora whose stamps :func:`count_stamped_without_vectors` audits."""


def load_memnon_settings() -> Dict[str, Any]:
    """Load MEMNON's model registry without importing the MEMNON agent."""
    from nexus.config import load_settings_as_dict

    settings = load_settings_as_dict().get("Agent Settings", {}).get("MEMNON", {})
    if not settings:
        raise RuntimeError("nexus.toml has no MEMNON embedding settings")
    return settings


def active_embedding_models(
    memnon_settings: Mapping[str, Any],
) -> Dict[str, Mapping[str, Any]]:
    """Return the active ``[memnon.models]`` entries by name, in config order.

    Raises:
        RuntimeError: If no model is marked ``is_active``.
    """
    active = {
        str(name): config
        for name, config in (memnon_settings.get("models") or {}).items()
        if config["is_active"]
    }
    if not active:
        raise RuntimeError("No active MEMNON embedding models are configured")
    return active


def active_memnon_embedding_model_dimensions() -> Dict[str, int]:
    """Return configured active MEMNON model names and vector dimensions."""
    return {
        name: int(config["dimensions"])
        for name, config in active_embedding_models(load_memnon_settings()).items()
    }


def normalized_source_ids(spec: EmbeddingSource, ids: Sequence[int]) -> List[int]:
    """Return unique positive ids while preserving caller order.

    Raises:
        ValueError: If any id is not positive.
    """
    normalized: List[int] = []
    seen: set[int] = set()
    for value in ids:
        row_id = int(value)
        if row_id <= 0:
            raise ValueError(
                f"{spec.embedding_fk_column} must be positive, got {row_id}"
            )
        if row_id not in seen:
            normalized.append(row_id)
            seen.add(row_id)
    return normalized


def vector_literal(embedding: Sequence[float]) -> str:
    """Return the pgvector text form of ``embedding``."""
    return "[" + ",".join(str(value) for value in embedding) + "]"


def generate_source_vectors(
    spec: EmbeddingSource,
    texts: Mapping[int, Any],
    model_names: Sequence[str],
    embed: Callable[[Any, str], Optional[Sequence[float]]],
) -> Dict[int, ModelVectors]:
    """Generate every model's vector for every row before any write begins.

    Args:
        spec: The corpus the rows belong to, for error messages.
        texts: Row text by id, in the order vectors should be written.
        model_names: Embedders to run, in order, for every row.
        embed: Returns one vector for ``(text, model_name)``; it may raise.

    Returns:
        ``(model, vector)`` pairs by row id, in ``texts`` order.

    Raises:
        RuntimeError: If ``embed`` returns no vector for any row and model;
            nothing has been written, so the whole set stays retryable.
    """
    generated: Dict[int, ModelVectors] = {}
    for row_id, text in texts.items():
        vectors: ModelVectors = []
        for model_name in model_names:
            embedding = embed(text, model_name)
            if not embedding:
                raise RuntimeError(
                    f"Embedding generation failed for {spec.label} {row_id} "
                    f"with model {model_name}; embedding_generated_at remains "
                    "NULL for retry"
                )
            vectors.append((model_name, list(embedding)))
        generated[row_id] = vectors
    return generated


def upsert_source_vectors(
    cursor: Any,
    spec: EmbeddingSource,
    generated: Mapping[int, ModelVectors],
) -> Dict[int, str]:
    """Create each needed dimension table once, then upsert every vector.

    Runs inside the caller's transaction so the vectors land together with
    the caller's stamp or not at all.

    Returns:
        The dimension tables used, by dimension count.
    """
    ensured: Dict[int, str] = {}
    fk_column = spec.embedding_fk_column
    for row_id, vectors in generated.items():
        for model_name, embedding in vectors:
            dimensions = len(embedding)
            table_name = ensured.get(dimensions)
            if table_name is None:
                table_name = spec.ensure_table(cursor, dimensions)
                ensured[dimensions] = table_name
            cursor.execute(
                f"""
                INSERT INTO {table_name}
                    ({fk_column}, model, embedding, created_at)
                VALUES (%s, %s, %s::vector({dimensions}), NOW())
                ON CONFLICT ({fk_column}, model) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    created_at = EXCLUDED.created_at
                """,
                (row_id, model_name, vector_literal(embedding)),
            )
    return ensured


def _load_source_rows(
    cursor: Any, spec: EmbeddingSource, requested_ids: List[int]
) -> Dict[int, Any]:
    """Return the text of every requested row that exists and is valid."""
    cursor.execute(
        f"""
        SELECT {spec.id_column}, {spec.text_column}
        FROM {spec.table}
        WHERE {spec.id_column} = ANY(%s){spec.validity_sql()}
        """,
        (requested_ids,),
    )
    return {
        int(row[spec.id_column]): row[spec.text_column] for row in cursor.fetchall()
    }


def _require_texts(
    spec: EmbeddingSource,
    dbname: str,
    requested_ids: List[int],
    rows: Mapping[int, Any],
) -> Dict[int, str]:
    """Return every requested row's text in caller order, or raise."""
    missing = [row_id for row_id in requested_ids if row_id not in rows]
    if missing:
        raise RuntimeError(f"{spec.plural_label} not found in {dbname}: {missing}")
    unrendered = [row_id for row_id in requested_ids if not rows[row_id]]
    if unrendered:
        raise RuntimeError(
            f"{spec.plural_label} are not rendered in {dbname}: {unrendered}"
        )
    return {row_id: str(rows[row_id]) for row_id in requested_ids}


def _stamp_embedded_rows(
    cursor: Any, spec: EmbeddingSource, requested_ids: List[int]
) -> Dict[int, Any]:
    """Stamp ``embedding_generated_at`` for every requested row, or raise."""
    cursor.execute(
        f"""
        UPDATE {spec.table}
        SET embedding_generated_at = NOW()
        WHERE {spec.id_column} = ANY(%s)
          AND {spec.text_column} IS NOT NULL{spec.validity_sql()}
        RETURNING {spec.id_column}, embedding_generated_at
        """,
        (requested_ids,),
    )
    stamped = {
        int(row[spec.id_column]): row["embedding_generated_at"]
        for row in cursor.fetchall()
    }
    if len(stamped) != len(requested_ids):
        raise RuntimeError(
            f"{spec.label[:1].upper()}{spec.label[1:]} embedding stamp count did "
            f"not match request ({len(stamped)} of {len(requested_ids)})"
        )
    return stamped


def embed_source_rows(
    dbname: str,
    spec: EmbeddingSource,
    ids: Sequence[int],
) -> List[Dict[str, Any]]:
    """Embed source rows into their dimension-specific corpus, all or nothing.

    All embeddings are generated before the write transaction begins. The
    transaction then creates any newly needed dimension tables, upserts every
    active model's vector, and stamps ``embedding_generated_at``. If any model
    generation or database write fails, no requested row receives the stamp
    and the whole set remains retryable.

    Args:
        dbname: Valid slot database name (``save_01`` through ``save_05``).
        spec: The corpus the ids belong to.
        ids: Source row ids; duplicates are embedded once, in first-seen order.

    Returns:
        One entry per row, in caller order: the row id under
        ``spec.embedding_fk_column``, the stored ``models``, their
        ``dimensions`` and the ISO ``embedding_generated_at`` stamp.

    Raises:
        RuntimeError: If a row is missing, invalid or has no text, the loaded
            embedders differ from the configured active models, any model
            fails to embed a row, or the stamp misses a row.
        ValueError: If any id is not positive.
    """
    requested_ids = normalized_source_ids(spec, ids)
    if not requested_ids:
        return []

    from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager
    from nexus.api.db_pool import get_connection

    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cursor:
            rows = _load_source_rows(cursor, spec, requested_ids)
    texts = _require_texts(spec, dbname, requested_ids, rows)

    memnon_settings = load_memnon_settings()
    configured = set(active_embedding_models(memnon_settings))
    manager = EmbeddingManager(settings=memnon_settings)
    model_names = manager.get_available_models()
    if set(model_names) != configured:
        raise RuntimeError(
            "Active MEMNON embedding model load did not match configuration; "
            f"missing={sorted(configured - set(model_names))}, "
            f"unexpected={sorted(set(model_names) - configured)}"
        )

    generated = generate_source_vectors(
        spec, texts, model_names, manager.generate_embedding
    )

    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cursor:
            upsert_source_vectors(cursor, spec, generated)
            stamped = _stamp_embedded_rows(cursor, spec, requested_ids)

    return [
        {
            spec.embedding_fk_column: row_id,
            "models": [model for model, _embedding in generated[row_id]],
            "dimensions": sorted(
                {len(embedding) for _model, embedding in generated[row_id]}
            ),
            "embedding_generated_at": stamped[row_id].isoformat(),
        }
        for row_id in requested_ids
    ]


def _first_value(row: Any, key: str) -> Any:
    """Read one column from a dict-style or tuple-style cursor row."""
    return row[key] if isinstance(row, Mapping) else row[0]


def count_stamped_without_vectors(
    cursor: Any,
    spec: EmbeddingSource,
    model_dimensions: Mapping[str, int],
) -> int:
    """Count stamped rows that lack a vector for any active model.

    ``embedding_generated_at`` promises that every active model's vector
    exists. This read-only audit counts rows whose stamp breaks that promise.
    A dimension table that was never created means every stamped row lacks
    that model's vector.

    Args:
        cursor: Open DBAPI cursor, dict-style or tuple-style.
        spec: The corpus to audit.
        model_dimensions: Active model names and dimensions, normally
            :func:`active_memnon_embedding_model_dimensions`.

    Returns:
        The number of stamped rows missing at least one active vector.
    """
    missing_vector: List[str] = []
    models: List[str] = []
    for model, dimensions in model_dimensions.items():
        table_name = spec.table_name_for_dimensions(dimensions)
        cursor.execute(
            "SELECT to_regclass(%s) IS NOT NULL AS present",
            (f"public.{table_name}",),
        )
        if not _first_value(cursor.fetchone(), "present"):
            missing_vector.append("TRUE")
            continue
        missing_vector.append(
            f"NOT EXISTS (SELECT 1 FROM {table_name} vec"
            f" WHERE vec.{spec.embedding_fk_column} = src.{spec.id_column}"
            " AND vec.model = %s)"
        )
        models.append(model)
    cursor.execute(
        f"""
        SELECT count(*) AS stamped_without_vectors
        FROM {spec.table} src
        WHERE src.embedding_generated_at IS NOT NULL
          AND ({" OR ".join(missing_vector)})
        """,
        tuple(models),
    )
    return int(_first_value(cursor.fetchone(), "stamped_without_vectors"))
