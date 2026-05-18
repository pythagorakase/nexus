"""Local route-graph helpers for Orrery travel."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Optional


RISK_RANK = {"low": 0, "moderate": 1, "high": 2, "extreme": 3}


@dataclass(frozen=True, slots=True)
class RouteGraphEdge:
    """One mode-aware edge in an offline route graph."""

    edge_id: int
    from_node_id: int
    to_node_id: int
    travel_mode: str
    risk: str
    bidirectional: bool
    distance_m: float
    duration_minutes: Optional[float] = None


@dataclass(frozen=True, slots=True)
class RouteGraphRoute:
    """Shortest local route result through an offline route graph."""

    node_ids: tuple[int, ...]
    edge_ids: tuple[int, ...]
    distance_m: float
    duration_minutes: float
    risk: str
    edge_travel_modes: tuple[str, ...]


def shortest_route(
    edges: list[RouteGraphEdge],
    *,
    origin_node_id: int,
    destination_node_id: int,
    requested_mode: str,
    speed_kmh: float,
) -> Optional[RouteGraphRoute]:
    """Return the shortest compatible route, if the graph connects both nodes."""

    if origin_node_id == destination_node_id:
        return RouteGraphRoute(
            node_ids=(origin_node_id,),
            edge_ids=(),
            distance_m=0.0,
            duration_minutes=0.0,
            risk="low",
            edge_travel_modes=(),
        )

    adjacency: dict[int, list[tuple[int, RouteGraphEdge]]] = {}
    for edge in edges:
        if edge.travel_mode not in {requested_mode, "mixed"}:
            continue
        adjacency.setdefault(edge.from_node_id, []).append((edge.to_node_id, edge))
        if edge.bidirectional:
            adjacency.setdefault(edge.to_node_id, []).append((edge.from_node_id, edge))

    heap: list[
        tuple[float, int, tuple[int, ...], tuple[int, ...], tuple[str, ...], int]
    ]
    heap = [(0.0, origin_node_id, (origin_node_id,), (), (), RISK_RANK["low"])]
    best: dict[int, float] = {}

    while heap:
        duration, node_id, node_path, edge_path, mode_path, risk_rank = heapq.heappop(
            heap
        )
        if node_id in best and duration >= best[node_id]:
            continue
        best[node_id] = duration

        if node_id == destination_node_id:
            distance = sum(edge.distance_m for edge in _edges_by_id(edges, edge_path))
            return RouteGraphRoute(
                node_ids=node_path,
                edge_ids=edge_path,
                distance_m=distance,
                duration_minutes=duration,
                risk=_risk_for_rank(risk_rank),
                edge_travel_modes=mode_path,
            )

        for next_node_id, edge in adjacency.get(node_id, ()):
            edge_duration = _edge_duration_minutes(edge, speed_kmh=speed_kmh)
            next_duration = duration + edge_duration
            if next_node_id in best and next_duration >= best[next_node_id]:
                continue
            heapq.heappush(
                heap,
                (
                    next_duration,
                    next_node_id,
                    node_path + (next_node_id,),
                    edge_path + (edge.edge_id,),
                    mode_path + (edge.travel_mode,),
                    max(risk_rank, RISK_RANK.get(edge.risk, RISK_RANK["low"])),
                ),
            )

    return None


def _edge_duration_minutes(edge: RouteGraphEdge, *, speed_kmh: float) -> float:
    if edge.duration_minutes is not None:
        return float(edge.duration_minutes)
    return (float(edge.distance_m) / 1000.0) / speed_kmh * 60.0


def _edges_by_id(
    edges: list[RouteGraphEdge], edge_ids: tuple[int, ...]
) -> list[RouteGraphEdge]:
    by_id = {edge.edge_id: edge for edge in edges}
    return [by_id[edge_id] for edge_id in edge_ids]


def _risk_for_rank(rank: int) -> str:
    for risk, candidate_rank in RISK_RANK.items():
        if candidate_rank == rank:
            return risk
    return "low"
