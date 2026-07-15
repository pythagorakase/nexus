"""Embedding lifecycle for the dedicated Retrograde summary corpus."""

from __future__ import annotations

from typing import Any, Sequence

from nexus.agents.memnon.utils.embedding_tables import (
    ensure_retrograde_summary_embedding_table,
)


def _normalized_summary_ids(summary_ids: Sequence[int]) -> list[int]:
    """Return unique positive summary ids while preserving caller order."""
    normalized: list[int] = []
    seen: set[int] = set()
    for value in summary_ids:
        summary_id = int(value)
        if summary_id <= 0:
            raise ValueError(f"summary_id must be positive, got {summary_id}")
        if summary_id not in seen:
            normalized.append(summary_id)
            seen.add(summary_id)
    return normalized


def _load_memnon_settings() -> dict[str, Any]:
    """Load MEMNON's model registry without importing the MEMNON agent."""
    from nexus.config import load_settings_as_dict

    settings = load_settings_as_dict().get("Agent Settings", {}).get("MEMNON", {})
    if not settings:
        raise RuntimeError("nexus.toml has no MEMNON embedding settings")
    return settings


def embed_retrograde_summaries(
    dbname: str,
    summary_ids: Sequence[int],
) -> list[dict[str, Any]]:
    """Embed summaries into their own dimension-specific corpus.

    All embeddings are generated before the write transaction begins. The
    transaction then creates any newly discovered dimension tables, upserts
    every active model's vector, and stamps ``embedding_generated_at``. If any
    model generation or database write fails, no requested summary receives
    the ironman stamp and the whole set remains retryable.

    Args:
        dbname: Valid slot database name (``save_01`` through ``save_05``).
        summary_ids: Dedicated ``retrograde_summaries.id`` values.

    Returns:
        One entry per summary, in caller order, describing stored models and
        dimensions.

    Raises:
        RuntimeError: If a summary is missing, no model is active, or any
            active model fails to generate an embedding.
        ValueError: If any summary id is not positive.
    """
    requested_ids = _normalized_summary_ids(summary_ids)
    if not requested_ids:
        return []

    from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager
    from nexus.api.db_pool import get_connection

    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, summary_text
                FROM retrograde_summaries
                WHERE id = ANY(%s)
                """,
                (requested_ids,),
            )
            summaries = {
                int(row["id"]): str(row["summary_text"]) for row in cursor.fetchall()
            }

    missing_ids = [
        summary_id for summary_id in requested_ids if summary_id not in summaries
    ]
    if missing_ids:
        raise RuntimeError(f"Retrograde summaries not found in {dbname}: {missing_ids}")

    memnon_settings = _load_memnon_settings()
    configured_models = memnon_settings.get("models", {})
    configured_active_models = [
        name
        for name, config in configured_models.items()
        if config.get("is_active", True)
    ]
    if not configured_active_models:
        raise RuntimeError("No active MEMNON embedding models are configured")

    embedding_manager = EmbeddingManager(settings=memnon_settings)
    model_names = embedding_manager.get_available_models()
    if set(model_names) != set(configured_active_models):
        missing_models = sorted(set(configured_active_models) - set(model_names))
        unexpected_models = sorted(set(model_names) - set(configured_active_models))
        raise RuntimeError(
            "Active MEMNON embedding model load did not match configuration; "
            f"missing={missing_models}, unexpected={unexpected_models}"
        )

    generated: dict[int, list[tuple[str, list[float]]]] = {}
    for summary_id in requested_ids:
        text = summaries[summary_id]
        model_embeddings: list[tuple[str, list[float]]] = []
        for model_name in model_names:
            embedding = embedding_manager.generate_embedding(text, model_name)
            if not embedding:
                raise RuntimeError(
                    "Embedding generation failed for Retrograde summary "
                    f"{summary_id} with model {model_name}; "
                    "embedding_generated_at remains NULL for retry"
                )
            model_embeddings.append((model_name, embedding))
        generated[summary_id] = model_embeddings

    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cursor:
            ensured_tables: dict[int, str] = {}
            for model_embeddings in generated.values():
                for model_name, embedding in model_embeddings:
                    dimensions = len(embedding)
                    table_name = ensured_tables.get(dimensions)
                    if table_name is None:
                        table_name = ensure_retrograde_summary_embedding_table(
                            cursor, dimensions
                        )
                        ensured_tables[dimensions] = table_name

                    embedding_value = "[" + ",".join(str(x) for x in embedding) + "]"
                    cursor.execute(
                        f"""
                        INSERT INTO {table_name}
                            (summary_id, model, embedding, created_at)
                        VALUES (%s, %s, %s::vector({dimensions}), NOW())
                        ON CONFLICT (summary_id, model) DO UPDATE
                        SET embedding = EXCLUDED.embedding,
                            created_at = EXCLUDED.created_at
                        """,
                        (summary_id, model_name, embedding_value),
                    )

            cursor.execute(
                """
                UPDATE retrograde_summaries
                SET embedding_generated_at = NOW()
                WHERE id = ANY(%s)
                RETURNING id, embedding_generated_at
                """,
                (requested_ids,),
            )
            stamped_at = {
                int(row["id"]): row["embedding_generated_at"]
                for row in cursor.fetchall()
            }
            if len(stamped_at) != len(requested_ids):
                raise RuntimeError(
                    "Retrograde summary embedding stamp count did not match "
                    f"request ({len(stamped_at)} of {len(requested_ids)})"
                )

    return [
        {
            "summary_id": summary_id,
            "models": [model for model, _embedding in generated[summary_id]],
            "dimensions": sorted(
                {len(embedding) for _model, embedding in generated[summary_id]}
            ),
            "embedding_generated_at": stamped_at[summary_id].isoformat(),
        }
        for summary_id in requested_ids
    ]
