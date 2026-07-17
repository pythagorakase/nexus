"""Storyteller-time Bleed selector for narrated Orrery resolutions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
import json
import logging
from typing import Any, Iterable, Mapping, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger("nexus.orrery.bleed")

_BLEED_GRAPH_NODES_SQL = """
    /* orrery:bleed_proximity_nodes */
    SELECT id AS entity_id
    FROM entities
    WHERE is_active = true
    ORDER BY id
"""
_BLEED_GRAPH_EDGES_SQL = """
    /* orrery:bleed_proximity_edges */
    SELECT source_entity_id, target_entity_id, edge_kind, edge_label
    FROM (
        SELECT c1.entity_id AS source_entity_id,
               c2.entity_id AS target_entity_id,
               'relationship'::text AS edge_kind,
               cr.relationship_type::text AS edge_label
        FROM character_relationships cr
        JOIN characters c1 ON c1.id = cr.character1_id
        JOIN characters c2 ON c2.id = cr.character2_id
        JOIN entities source ON source.id = c1.entity_id
        JOIN entities target ON target.id = c2.entity_id
        WHERE source.is_active = true
          AND target.is_active = true

        UNION ALL

        SELECT ept.subject_entity_id AS source_entity_id,
               ept.object_entity_id AS target_entity_id,
               'pair_tag'::text AS edge_kind,
               pt.tag AS edge_label
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        JOIN entities source ON source.id = ept.subject_entity_id
        JOIN entities target ON target.id = ept.object_entity_id
        WHERE ept.cleared_at IS NULL
          AND NOT pt.deprecated
          AND source.is_active = true
          AND target.is_active = true
          AND (
                pt.tag LIKE 'status:%'
             OR pt.tag IN (
                    'obligation',
                    'handles',
                    'authority_over',
                    'mentors',
                    'protects',
                    'hunting'
                )
          )
          AND (
                (source.kind = 'character'
                 AND target.kind IN ('character', 'faction'))
             OR (source.kind = 'faction' AND target.kind = 'character')
          )
    ) bleed_edges
    ORDER BY source_entity_id, target_entity_id, edge_kind, edge_label
"""


@dataclass(frozen=True, slots=True)
class BleedProximityGraph:
    """Purpose-specific, immutable undirected graph for Bleed proximity."""

    nodes: Tuple[int, ...]
    adjacency: Mapping[int, Tuple[int, ...]]

    def distances_from(self, anchor_entity_ids: Iterable[int]) -> dict[int, int]:
        """Return deterministic minimum hop counts from any active anchor."""

        node_set = frozenset(self.nodes)
        roots = tuple(
            sorted(
                {
                    int(entity_id)
                    for entity_id in anchor_entity_ids
                    if int(entity_id) in node_set
                }
            )
        )
        distances = {entity_id: 0 for entity_id in roots}
        frontier = deque(roots)
        while frontier:
            entity_id = frontier.popleft()
            next_distance = distances[entity_id] + 1
            for neighbor_id in self.adjacency.get(entity_id, ()):
                if neighbor_id in distances:
                    continue
                distances[neighbor_id] = next_distance
                frontier.append(neighbor_id)
        return distances


class BleedCandidate(BaseModel):
    """One narrated off-screen resolution eligible for Storyteller-time Bleed."""

    resolution_id: int
    narration_id: int
    tick_chunk_id: int
    template_id: str
    actor_entity_id: Optional[int] = None
    event_type: Optional[str] = None
    actor_name: Optional[str] = None
    target_name: Optional[str] = None
    channel: Optional[str] = None
    summary: Optional[str] = None
    brief: Optional[str] = None
    text: str
    magnitude: Optional[float] = None
    distance: Optional[int] = None

    def to_prompt_dict(self) -> dict[str, Any]:
        """Return the spoiler-limited shape injected into the Storyteller prompt."""

        return {
            "resolution_id": self.resolution_id,
            "template_id": self.template_id,
            "channel": self.channel,
            "summary": self.summary or self.brief,
            "actor_name": self.actor_name,
            "target_name": self.target_name,
            "magnitude": self.magnitude,
        }


class BleedSelectorResult(BaseModel):
    """Result of a Bleed selector pass."""

    candidates_considered: int = 0
    selected: list[BleedCandidate] = Field(default_factory=list)
    near_count: int = 0
    remote_count: int = 0


def load_bleed_anchor_entity_ids(
    session: Any,
    *,
    anchor_chunk_id: int,
) -> Tuple[int, ...]:
    """Resolve character and faction references on one chunk to spine ids."""

    rows = session.execute(
        text(
            """
            /* orrery:bleed_anchor_entities */
            SELECT entity_id
            FROM (
                SELECT c.entity_id
                FROM chunk_character_references ccr
                JOIN characters c ON c.id = ccr.character_id
                WHERE ccr.chunk_id = :anchor_chunk_id

                UNION

                SELECT f.entity_id
                FROM chunk_faction_references cfr
                JOIN factions f ON f.id = cfr.faction_id
                WHERE cfr.chunk_id = :anchor_chunk_id
            ) anchor_entities
            WHERE entity_id IS NOT NULL
            ORDER BY entity_id
            """
        ),
        {"anchor_chunk_id": anchor_chunk_id},
    ).mappings()
    return tuple(int(row["entity_id"]) for row in rows)


def assemble_bleed_proximity_graph(session_or_cur: Any) -> BleedProximityGraph:
    """Assemble the bounded, read-only graph used only by Bleed selection."""

    node_rows = [
        dict(row)
        for row in session_or_cur.execute(text(_BLEED_GRAPH_NODES_SQL)).mappings()
    ]
    edge_rows = [
        dict(row)
        for row in session_or_cur.execute(text(_BLEED_GRAPH_EDGES_SQL)).mappings()
    ]
    nodes = tuple(sorted({int(row["entity_id"]) for row in node_rows}))
    node_set = frozenset(nodes)
    neighbors: dict[int, set[int]] = {entity_id: set() for entity_id in nodes}
    for row in edge_rows:
        source_id = int(row["source_entity_id"])
        target_id = int(row["target_entity_id"])
        if source_id not in node_set or target_id not in node_set:
            raise ValueError(
                "Bleed proximity edge references an entity outside the active graph: "
                f"{source_id}->{target_id}"
            )
        neighbors[source_id].add(target_id)
        neighbors[target_id].add(source_id)
    adjacency = {
        entity_id: tuple(sorted(entity_neighbors))
        for entity_id, entity_neighbors in neighbors.items()
    }
    return BleedProximityGraph(nodes=nodes, adjacency=adjacency)


def load_bleed_candidates(
    session: Any,
    *,
    anchor_chunk_id: int,
    limit: Optional[int],
) -> list[BleedCandidate]:
    """Load narrated Orrery candidates that are eligible before the anchor."""

    if limit is not None and limit <= 0:
        return []

    limit_clause = "LIMIT :limit" if limit is not None else ""
    rows = session.execute(
        text(
            f"""
            /* orrery:bleed_candidates */
            SELECT
                r.id AS resolution_id,
                n.id AS narration_id,
                r.tick_chunk_id,
                r.template_id,
                r.actor_entity_id,
                r.brief,
                r.magnitude,
                n.text,
                n.perceptual_descriptor,
                actor.name AS actor_name,
                target.name AS target_name,
                we.event_type
            FROM orrery_resolutions r
            JOIN offscreen_narrations n ON n.id = r.narration_chunk_id
            LEFT JOIN entity_names_v actor ON actor.id = r.actor_entity_id
            LEFT JOIN LATERAL (
                SELECT event_type, target_entity_id
                FROM world_events
                WHERE resolution_id = r.id
                ORDER BY id
                LIMIT 1
            ) we ON TRUE
            LEFT JOIN entity_names_v target ON target.id = we.target_entity_id
            WHERE r.promotion_status = 'promoted'
              AND r.narration_status = 'succeeded'
              AND r.tick_chunk_id <= :anchor_chunk_id
              AND (
                    r.last_offered_chunk_id IS NULL
                 OR r.last_offered_chunk_id <> :anchor_chunk_id
              )
              AND r.offer_count < 3
            ORDER BY r.tick_chunk_id DESC,
                     r.magnitude DESC NULLS LAST,
                     r.priority DESC,
                     r.id DESC
            {limit_clause}
            """
        ),
        {
            "anchor_chunk_id": anchor_chunk_id,
            **({"limit": limit} if limit is not None else {}),
        },
    ).mappings()

    return [_candidate_from_row(row) for row in rows]


def select_bleed_menu(
    session: Any,
    *,
    anchor_chunk_id: int,
    anchor_entity_ids: Iterable[int],
    max_candidates: int,
    near_distance_max: int,
    reserved_remote_slots: int,
    scan_limit: int,
) -> BleedSelectorResult:
    """Select a proximity-balanced ambient menu from eligible candidates."""

    if max_candidates <= 0:
        return BleedSelectorResult()

    anchors = tuple(sorted({int(entity_id) for entity_id in anchor_entity_ids}))
    # Bounds on near_distance_max / reserved_remote_slots are owned by
    # OrreryBleedSettings; callers pass validated values.
    candidate_pool = load_bleed_candidates(
        session,
        anchor_chunk_id=anchor_chunk_id,
        # The empty-anchor fallback needs only the top of the pure ordering;
        # the proximity path partitions a bounded scan window (scan_limit).
        limit=max_candidates if not anchors else scan_limit,
    )
    if not candidate_pool:
        return BleedSelectorResult()
    if not anchors:
        selected = candidate_pool[:max_candidates]
        return BleedSelectorResult(
            candidates_considered=len(candidate_pool),
            selected=selected,
            remote_count=len(selected),
        )

    graph = assemble_bleed_proximity_graph(session)
    distances = graph.distances_from(anchors)
    annotated = [
        candidate.model_copy(
            update={
                "distance": (
                    distances.get(candidate.actor_entity_id)
                    if candidate.actor_entity_id is not None
                    else None
                )
            }
        )
        for candidate in candidate_pool
    ]
    near = [
        candidate
        for candidate in annotated
        if candidate.distance is not None and candidate.distance <= near_distance_max
    ]
    remote = [
        candidate
        for candidate in annotated
        if candidate.distance is None or candidate.distance > near_distance_max
    ]

    near_slots = max_candidates - reserved_remote_slots
    selected_near = near[:near_slots]
    selected_remote = remote[:reserved_remote_slots]
    selected = [*selected_near, *selected_remote]
    remaining_slots = max_candidates - len(selected)
    if remaining_slots and len(selected_near) < near_slots:
        selected.extend(remote[reserved_remote_slots:][:remaining_slots])
    elif remaining_slots and len(selected_remote) < reserved_remote_slots:
        selected.extend(near[near_slots:][:remaining_slots])

    return BleedSelectorResult(
        candidates_considered=len(candidate_pool),
        selected=selected,
        near_count=sum(
            candidate.distance is not None and candidate.distance <= near_distance_max
            for candidate in selected
        ),
        remote_count=sum(
            candidate.distance is None or candidate.distance > near_distance_max
            for candidate in selected
        ),
    )


def record_bleed_offers(
    session: Any,
    candidates: list[BleedCandidate],
    *,
    anchor_chunk_id: int,
) -> None:
    """Update surfacing bookkeeping for candidates offered to the Storyteller."""

    resolution_ids = [candidate.resolution_id for candidate in candidates]
    if not resolution_ids:
        return

    session.execute(
        text(
            """
            /* orrery:record_bleed_offers */
            UPDATE orrery_resolutions
            SET first_surfaced_chunk_id = COALESCE(
                    first_surfaced_chunk_id,
                    :anchor_chunk_id
                ),
                last_offered_chunk_id = :anchor_chunk_id,
                offer_count = offer_count + 1
            WHERE id = ANY(:resolution_ids)
            """
        ),
        {
            "anchor_chunk_id": anchor_chunk_id,
            "resolution_ids": resolution_ids,
        },
    )
    session.commit()


def _candidate_from_row(row: Mapping[str, Any]) -> BleedCandidate:
    descriptor = _coerce_descriptor(row.get("perceptual_descriptor"))
    return BleedCandidate(
        resolution_id=int(row["resolution_id"]),
        narration_id=int(row["narration_id"]),
        tick_chunk_id=int(row["tick_chunk_id"]),
        template_id=str(row["template_id"]),
        actor_entity_id=_int_or_none(row.get("actor_entity_id")),
        event_type=row.get("event_type"),
        actor_name=row.get("actor_name"),
        target_name=row.get("target_name"),
        channel=descriptor.get("channel"),
        summary=descriptor.get("summary"),
        brief=row.get("brief") or descriptor.get("brief"),
        text=str(row.get("text") or ""),
        magnitude=_float_or_none(row.get("magnitude")),
    )


def _coerce_descriptor(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, Mapping):
        return dict(raw)
    raise TypeError(f"Unsupported perceptual_descriptor type: {type(raw).__name__}")


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)
