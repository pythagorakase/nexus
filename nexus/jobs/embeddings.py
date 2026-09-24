"""Durable locked-chunk embeddings using the gateway's cached model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg2 import sql

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.config.settings_models import NarrativeJobSettings
from nexus.jobs.gate import before_provider_call
from nexus.jobs.narrative_jobs import drain_job


def enqueue_embedding(cur: Any, chunk_id: int, session_id: str | None = None) -> str:
    """Idempotently plan one locked chunk inside the caller's transaction."""
    cur.execute(
        """INSERT INTO narrative_embedding_jobs (chunk_id, generation_session_id)
        VALUES (%s, %s) ON CONFLICT (chunk_id) DO UPDATE
        SET chunk_id=EXCLUDED.chunk_id RETURNING id""",
        (chunk_id, session_id),
    )
    row = cur.fetchone()
    return str(row["id"] if isinstance(row, dict) else row[0])


def enqueue_locked_embeddings(cur: Any, parent_chunk_id: int, session_id: str) -> None:
    """Preserve the claims predicate: only chunks strictly older than the parent."""
    cur.execute(
        f"""INSERT INTO narrative_embedding_jobs (chunk_id, generation_session_id)
        SELECT nc.id, %s::uuid FROM narrative_chunks nc
        WHERE nc.id < %s AND nc.embedding_generated_at IS NULL
          AND {playable_narrative_predicate('nc')}
        ON CONFLICT (chunk_id) DO NOTHING""",
        (session_id, parent_chunk_id),
    )


def drain_embedding(
    conn: Any, *, settings: dict[str, Any], cfg: NarrativeJobSettings, owner: str
) -> int:
    """Generate locally, then atomically fence vectors, ironman stamp and job."""

    def prepare(job: dict[str, Any]) -> list[tuple[str, list[float]]]:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT raw_text, embedding_generated_at FROM narrative_chunks WHERE id=%s",
                (job["chunk_id"],),
            )
            text, embedded = cur.fetchone()
        if embedded is not None:
            return []
        models = {
            name: model
            for name, model in settings["Agent Settings"]["MEMNON"]["models"].items()
            if model["is_active"]
        }
        if not models:
            raise ValueError("No active MEMNON embedding model is configured")
        from nexus.agents.memnon.utils.embedding_manager import (
            _get_or_load_sentence_transformer,
        )

        vectors = []
        for name, config in models.items():
            before_provider_call()
            path = config.get("local_path")
            if not path or not Path(path).is_dir():
                raise ValueError(
                    f"Configured embedding model {name} is not installed at {path}"
                )
            model = _get_or_load_sentence_transformer(path)
            before_provider_call()
            vector = model.encode(text).tolist()
            if len(vector) != config["dimensions"]:
                raise ValueError(f"Embedding dimension mismatch for {name}")
            vectors.append((name, vector))
        return vectors

    def complete(
        cur: Any, job: dict[str, Any], vectors: list[tuple[str, list[float]]]
    ) -> None:
        from nexus.agents.memnon.utils.embedding_tables import ensure_embedding_table

        for name, vector in vectors:
            table = sql.Identifier(ensure_embedding_table(cur, len(vector)))
            cur.execute(
                sql.SQL(
                    """INSERT INTO {} (chunk_id, model, embedding)
                    VALUES (%s, %s, %s::vector) ON CONFLICT (chunk_id, model)
                    DO UPDATE SET embedding=EXCLUDED.embedding, created_at=now()"""
                ).format(table),
                (job["chunk_id"], name, str(vector)),
            )
        cur.execute(
            "UPDATE narrative_chunks SET embedding_generated_at=coalesce(embedding_generated_at, now()) WHERE id=%s",
            (job["chunk_id"],),
        )

    return drain_job(
        conn,
        table="narrative_embedding_jobs",
        owner=owner,
        cfg=cfg,
        prepare=prepare,
        complete=complete,
    )
