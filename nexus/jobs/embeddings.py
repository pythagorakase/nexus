"""Durable locked-chunk embeddings using the gateway's cached model."""

from __future__ import annotations

from typing import Any

from nexus.agents.memnon.utils.embedding_tables import (
    ensure_embedding_table,
    table_name_for_dimensions,
)
from nexus.agents.memnon.utils.source_embeddings import (
    EmbeddingSource,
    ModelVectors,
    active_embedding_models,
    generate_source_vectors,
    upsert_source_vectors,
)
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.config.settings_models import MEMNONSettings, NarrativeJobSettings
from nexus.jobs.gate import before_provider_call
from nexus.jobs.narrative_jobs import drain_job

# Chunks embed only through this durable queue, never through
# embed_source_rows: the job fences the stamp with its lease and keeps the
# first stamp, where the summary and experience corpora restamp on repair.
_NARRATIVE_CHUNKS = EmbeddingSource(
    label="narrative chunk",
    plural_label="Narrative chunks",
    table="narrative_chunks",
    id_column="id",
    text_column="raw_text",
    embedding_fk_column="chunk_id",
    ensure_table=ensure_embedding_table,
    table_name_for_dimensions=table_name_for_dimensions,
)


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
    conn: Any, *, memnon: MEMNONSettings, cfg: NarrativeJobSettings, owner: str
) -> int:
    """Generate locally, then atomically fence vectors, ironman stamp and job."""

    def prepare(job: dict[str, Any]) -> dict[int, ModelVectors]:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT raw_text, embedding_generated_at FROM narrative_chunks WHERE id=%s",
                (job["chunk_id"],),
            )
            text, embedded = cur.fetchone()
        if embedded is not None:
            return {}
        models = active_embedding_models(memnon.model_dump(by_alias=True))
        from nexus.agents.memnon.utils.embedding_manager import load_local_model

        def encode(chunk_text: str, name: str) -> list[float]:
            config = models[name]
            before_provider_call()
            # The shared local-only loader: a missing, misplaced or
            # unloadable artifact fails with the pinned restore command,
            # and the job records that error.
            model = load_local_model(name, config)
            before_provider_call()
            vector = model.encode(chunk_text).tolist()
            if len(vector) != config["dimensions"]:
                raise ValueError(f"Embedding dimension mismatch for {name}")
            return vector

        return generate_source_vectors(
            _NARRATIVE_CHUNKS, {int(job["chunk_id"]): text}, list(models), encode
        )

    def complete(
        cur: Any, job: dict[str, Any], generated: dict[int, ModelVectors]
    ) -> None:
        upsert_source_vectors(cur, _NARRATIVE_CHUNKS, generated)
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
