"""All-or-nothing embeddings for rendered character experiences."""

from __future__ import annotations

from typing import Any, Sequence

from nexus.agents.memnon.utils.embedding_tables import (
    ensure_character_experience_embedding_table,
)


def _normalized_experience_ids(experience_ids: Sequence[int]) -> list[int]:
    """Return unique positive ids while preserving caller order."""
    normalized: list[int] = []
    seen: set[int] = set()
    for value in experience_ids:
        experience_id = int(value)
        if experience_id <= 0:
            raise ValueError(f"experience_id must be positive, got {experience_id}")
        if experience_id not in seen:
            normalized.append(experience_id)
            seen.add(experience_id)
    return normalized


def _memnon_settings() -> dict[str, Any]:
    from nexus.config import load_settings_as_dict

    settings = load_settings_as_dict().get("Agent Settings", {}).get("MEMNON", {})
    if not settings:
        raise RuntimeError("nexus.toml has no MEMNON embedding settings")
    return settings


def embed_character_experiences(
    dbname: str,
    experience_ids: Sequence[int],
) -> list[dict[str, Any]]:
    """Embed rendered recollections and stamp only after every vector upsert.

    Every active-model embedding is generated before the write transaction.
    Dimension tables, all model vectors, and every ironman timestamp then land
    in one transaction. A generation or write failure leaves the entire input
    set unstamped and retryable.
    """
    requested_ids = _normalized_experience_ids(experience_ids)
    if not requested_ids:
        return []

    from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager
    from nexus.agents.orrery.retrograde_embedding import (
        active_memnon_embedding_model_dimensions,
    )
    from nexus.api.db_pool import get_connection

    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, experience_text
                FROM character_experiences
                WHERE id = ANY(%s)
                  AND invalidation_status = 'valid'
                """,
                (requested_ids,),
            )
            experiences = {
                int(row["id"]): row["experience_text"] for row in cursor.fetchall()
            }
    missing = [item for item in requested_ids if item not in experiences]
    if missing:
        raise RuntimeError(f"Character experiences not found in {dbname}: {missing}")
    unrendered = [item for item in requested_ids if not experiences[item]]
    if unrendered:
        raise RuntimeError(
            f"Character experiences are not rendered in {dbname}: {unrendered}"
        )

    memnon_settings = _memnon_settings()
    configured = list(active_memnon_embedding_model_dimensions())
    manager = EmbeddingManager(settings=memnon_settings)
    model_names = manager.get_available_models()
    if set(model_names) != set(configured):
        raise RuntimeError(
            "Active MEMNON embedding model load did not match configuration; "
            f"configured={sorted(configured)}, loaded={sorted(model_names)}"
        )

    generated: dict[int, list[tuple[str, list[float]]]] = {}
    for experience_id in requested_ids:
        model_embeddings: list[tuple[str, list[float]]] = []
        for model_name in model_names:
            embedding = manager.generate_embedding(
                str(experiences[experience_id]), model_name
            )
            if not embedding:
                raise RuntimeError(
                    "Embedding generation failed for character experience "
                    f"{experience_id} with model {model_name}; "
                    "embedding_generated_at remains NULL for retry"
                )
            model_embeddings.append((model_name, embedding))
        generated[experience_id] = model_embeddings

    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cursor:
            ensured: dict[int, str] = {}
            for experience_id, model_embeddings in generated.items():
                for model_name, embedding in model_embeddings:
                    dimensions = len(embedding)
                    table_name = ensured.get(dimensions)
                    if table_name is None:
                        table_name = ensure_character_experience_embedding_table(
                            cursor, dimensions
                        )
                        ensured[dimensions] = table_name
                    value = "[" + ",".join(str(number) for number in embedding) + "]"
                    cursor.execute(
                        f"""
                        INSERT INTO {table_name}
                            (experience_id, model, embedding, created_at)
                        VALUES (%s, %s, %s::vector({dimensions}), NOW())
                        ON CONFLICT (experience_id, model) DO UPDATE
                        SET embedding = EXCLUDED.embedding,
                            created_at = EXCLUDED.created_at
                        """,
                        (experience_id, model_name, value),
                    )
            cursor.execute(
                """
                UPDATE character_experiences
                SET embedding_generated_at = NOW()
                WHERE id = ANY(%s)
                  AND experience_text IS NOT NULL
                  AND invalidation_status = 'valid'
                RETURNING id, embedding_generated_at
                """,
                (requested_ids,),
            )
            stamped = {
                int(row["id"]): row["embedding_generated_at"]
                for row in cursor.fetchall()
            }
            if len(stamped) != len(requested_ids):
                raise RuntimeError(
                    "Character experience embedding stamp count did not match "
                    f"request ({len(stamped)} of {len(requested_ids)})"
                )
    return [
        {
            "experience_id": experience_id,
            "models": [model for model, _embedding in generated[experience_id]],
            "dimensions": sorted(
                {len(embedding) for _model, embedding in generated[experience_id]}
            ),
            "embedding_generated_at": stamped[experience_id].isoformat(),
        }
        for experience_id in requested_ids
    ]
