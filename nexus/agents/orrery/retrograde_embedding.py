"""Embed Retrograde summary chunks through the standard chunk lifecycle."""

from __future__ import annotations

from typing import Any, Sequence


def embed_retrograde_summary_chunks(
    dbname: str,
    chunk_ids: Sequence[int],
) -> list[dict[str, Any]]:
    """Run the standard embedding lifecycle for Retrograde summary chunks.

    Uses ``ChunkWorkflow.trigger_embedding_generation`` — the same path play
    chunks take when they leave the incubator — so Retrograde history becomes
    ironman (``embedding_generated_at`` stamped) exactly like play-generated
    history. Must be called after the transaction that created the chunks has
    committed; the embedding subprocess opens its own connection.

    Args:
        dbname: Slot database name (save_01 through save_05).
        chunk_ids: Chunk ids still pending embedding.

    Returns:
        One result entry per chunk with the embedding job id.

    Raises:
        RuntimeError: If embedding generation fails for any chunk.
    """

    from nexus.api.chunk_workflow import ChunkWorkflow

    workflow = ChunkWorkflow(dbname)
    results: list[dict[str, Any]] = []
    for chunk_id in chunk_ids:
        job_id = workflow.trigger_embedding_generation(int(chunk_id))
        if job_id is None:
            raise RuntimeError(
                f"Embedding generation failed for Retrograde summary chunk "
                f"{chunk_id} in {dbname}; embedding_generated_at remains NULL "
                "for retry"
            )
        results.append({"chunk_id": int(chunk_id), "job_id": job_id})
    return results
