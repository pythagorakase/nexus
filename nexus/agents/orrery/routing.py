"""Local route-graph helpers for Orrery travel."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Optional


DEFAULT_ROUTE_GRAPH_MAX_EDGES_PER_QUERY = 5000
ROUTE_GRAPH_MODES = frozenset({"walking", "vehicle", "covert", "mixed"})
RISK_RANK = {"low": 0, "moderate": 1, "high": 2, "extreme": 3}
RANK_RISK = {rank: risk for risk, rank in RISK_RANK.items()}


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

    heap: list[tuple[float, int]] = [(0.0, origin_node_id)]
    best: dict[int, float] = {origin_node_id: 0.0}
    came_from: dict[int, tuple[int, RouteGraphEdge]] = {}

    while heap:
        duration, node_id = heapq.heappop(heap)
        if duration > best.get(node_id, float("inf")):
            continue

        if node_id == destination_node_id:
            break

        for next_node_id, edge in adjacency.get(node_id, ()):
            edge_duration = _edge_duration_minutes(edge, speed_kmh=speed_kmh)
            next_duration = duration + edge_duration
            if next_duration >= best.get(next_node_id, float("inf")):
                continue
            best[next_node_id] = next_duration
            came_from[next_node_id] = (node_id, edge)
            heapq.heappush(heap, (next_duration, next_node_id))

    if destination_node_id not in best:
        return None

    node_ids: list[int] = [destination_node_id]
    edge_ids: list[int] = []
    edge_travel_modes: list[str] = []
    distance_m = 0.0
    risk_rank = RISK_RANK["low"]
    node_id = destination_node_id
    while node_id != origin_node_id:
        previous_node_id, edge = came_from[node_id]
        edge_ids.append(edge.edge_id)
        edge_travel_modes.append(edge.travel_mode)
        distance_m += float(edge.distance_m)
        risk_rank = max(risk_rank, RISK_RANK.get(edge.risk, RISK_RANK["low"]))
        node_ids.append(previous_node_id)
        node_id = previous_node_id

    return RouteGraphRoute(
        node_ids=tuple(reversed(node_ids)),
        edge_ids=tuple(reversed(edge_ids)),
        distance_m=distance_m,
        duration_minutes=best[destination_node_id],
        risk=_risk_for_rank(risk_rank),
        edge_travel_modes=tuple(reversed(edge_travel_modes)),
    )


def _edge_duration_minutes(edge: RouteGraphEdge, *, speed_kmh: float) -> float:
    if edge.duration_minutes is not None:
        return float(edge.duration_minutes)
    return (float(edge.distance_m) / 1000.0) / speed_kmh * 60.0


def _risk_for_rank(rank: int) -> str:
    return RANK_RISK.get(rank, "low")
