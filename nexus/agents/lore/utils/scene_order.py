"""Shared scene ordering and recalled-memory clock hydration."""

from typing import Any, Iterable

from sqlalchemy import text

from nexus.memory.context_state import is_retrograde_summary, memory_identity
from nexus.memory.retrieval_coverage import coerce_chunk_id
from nexus.util.clock_face import clock_face


def is_recalled(memory: dict[str, Any]) -> bool:
    """Identify incremental additions and the dedicated summary corpus."""
    return not memory.get("is_target") and (
        bool(memory.get("is_recalled")) or is_retrograde_summary(memory)
    )


def select_scene_memories(
    warm: list[dict[str, Any]],
    retrieved: list[dict[str, Any]],
    historical_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deduplicate by lane priority, then cap the remaining ranked retrievals.

    Keep the original objects and source order for window accounting and trimming.
    Recent narrative wins over recalled scenes, which win over historical context.
    Within a lane the first candidate wins, with warm additions before deep hits.
    """
    candidates = [(memory, True) for memory in warm] + [
        (memory, False) for memory in retrieved
    ]
    winners = {}
    for index, (memory, in_warm) in enumerate(candidates):
        identity = memory_identity(memory)
        key = identity if identity is not None else ("anonymous", id(memory))
        priority = (
            0
            if in_warm and not is_recalled(memory)
            else (1 if is_recalled(memory) else 2)
        )
        if key not in winners or priority < winners[key][0]:
            winners[key] = (priority, index)
    selected = {index for _, index in winners.values()}
    return (
        [memory for index, memory in enumerate(warm) if index in selected],
        [
            memory
            for index, memory in enumerate(retrieved, start=len(warm))
            if index in selected
        ][:historical_limit],
    )


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
        metadata[key] = stamp.isoformat() if stamp is not None else None


def recalled_clock_label(memory: dict[str, Any]) -> str:
    """Label narrative time or explicitly qualified summary recording time."""
    metadata = memory.get("metadata") or {}
    if is_retrograde_summary(memory):
        identity = memory_identity(memory)
        label = f"Retrograde summary {str(identity).split(':')[-1]}"
        anchor = metadata.get("recorded_at_chunk_id")
        if anchor is None or metadata.get("recorded_at_world_time") is None:
            return label
        return (
            f"{label} · recorded at chunk {anchor} · "
            f"{clock_face(metadata['recorded_at_world_time'])}"
        )
    label = f"chunk {coerce_chunk_id(memory)}"
    if metadata.get("world_time") is None:
        return label
    return f"{label} · {clock_face(metadata['world_time'])}"
