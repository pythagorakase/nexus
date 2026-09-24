"""Shared scene ordering and recalled-memory clock hydration."""

from typing import Any, Iterable

from sqlalchemy import text

from nexus.memory.context_state import is_retrograde_summary, memory_identity
from nexus.memory.retrieval_coverage import coerce_chunk_id
from nexus.util.clock_face import clock_face


def is_recalled(memory: dict[str, Any]) -> bool:
    """Identify incremental additions and the dedicated summary corpus."""
    return bool(memory.get("is_recalled")) or is_retrograde_summary(memory)


def scene_order(memory: dict[str, Any]) -> tuple[bool, int, str]:
    """Order chunks by id, summaries by recording anchor, then undated summaries."""
    anchor = (
        (memory.get("metadata") or {}).get("recorded_at_chunk_id")
        if is_retrograde_summary(memory)
        else coerce_chunk_id(memory)
    )
    return anchor is None, int(anchor or 0), str(memory_identity(memory))


def hydrate_recalled_clocks(session: Any, memories: Iterable[dict[str, Any]]) -> None:
    """Read story clocks in one query; never substitute storage or event time."""
    pending = []
    for memory in memories:
        if not is_recalled(memory):
            continue
        metadata = memory.setdefault("metadata", {})
        summary = is_retrograde_summary(memory)
        anchor = (
            metadata.get("recorded_at_chunk_id") if summary else coerce_chunk_id(memory)
        )
        if summary and anchor is None:
            continue
        if anchor is None:
            raise ValueError("Recalled narrative requires a chunk id")
        key = "recorded_at_world_time" if summary else "world_time"
        pending.append((metadata, key, int(anchor)))
    if not pending:
        return
    clocks = dict(
        session.execute(
            text("SELECT id, world_time FROM narrative_view WHERE id = ANY(:ids)"),
            {"ids": sorted({anchor for _, _, anchor in pending})},
        ).all()
    )
    for metadata, key, anchor in pending:
        stamp = clocks.get(anchor)
        if stamp is None:
            raise ValueError(
                f"Recalled memory anchor chunk {anchor} has no story clock"
            )
        metadata[key] = stamp.isoformat()


def recalled_clock_label(memory: dict[str, Any]) -> str:
    """Label narrative time or explicitly qualified summary recording time."""
    metadata = memory.get("metadata") or {}
    if is_retrograde_summary(memory):
        identity = memory_identity(memory)
        label = f"Retrograde summary {str(identity).split(':')[-1]}"
        anchor = metadata.get("recorded_at_chunk_id")
        if anchor is None:
            return label
        return (
            f"{label} · recorded at chunk {anchor} · "
            f"{clock_face(metadata['recorded_at_world_time'])}"
        )
    return f"chunk {coerce_chunk_id(memory)} · {clock_face(metadata['world_time'])}"
