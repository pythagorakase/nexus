"""Tests for local Orrery route-graph algorithms."""

from __future__ import annotations

import pytest

from nexus.agents.orrery.routing import RouteGraphEdge, shortest_route
from scripts.import_orrery_route_graph import _mode, _validate_edge_count


def test_shortest_route_uses_lowest_duration_path() -> None:
    """Dijkstra chooses the fastest compatible graph path."""

    route = shortest_route(
        [
            RouteGraphEdge(1, 10, 11, "vehicle", "low", True, 2000, 6),
            RouteGraphEdge(2, 11, 12, "vehicle", "moderate", True, 3000, 8),
            RouteGraphEdge(3, 10, 12, "vehicle", "low", True, 12000, 40),
        ],
        origin_node_id=10,
        destination_node_id=12,
        requested_mode="vehicle",
        speed_kmh=45,
    )

    assert route is not None
    assert route.node_ids == (10, 11, 12)
    assert route.edge_ids == (1, 2)
    assert route.distance_m == pytest.approx(5000)
    assert route.duration_minutes == pytest.approx(14)
    assert route.risk == "moderate"


def test_shortest_route_treats_mixed_edges_as_mode_compatible() -> None:
    """Generic graph edges can serve concrete mode requests."""

    route = shortest_route(
        [RouteGraphEdge(1, 10, 11, "mixed", "low", True, 4500, None)],
        origin_node_id=10,
        destination_node_id=11,
        requested_mode="vehicle",
        speed_kmh=45,
    )

    assert route is not None
    assert route.edge_ids == (1,)
    assert route.duration_minutes == pytest.approx(6)
    assert route.edge_travel_modes == ("mixed",)


def test_shortest_route_rejects_unreachable_graph() -> None:
    """Disconnected local graph data returns no route instead of guessing."""

    route = shortest_route(
        [RouteGraphEdge(1, 10, 11, "vehicle", "low", False, 1000, 2)],
        origin_node_id=11,
        destination_node_id=10,
        requested_mode="vehicle",
        speed_kmh=45,
    )

    assert route is None


def test_route_graph_importer_rejects_non_routable_modes() -> None:
    """The importer only accepts modes the graph router will query."""

    with pytest.raises(ValueError, match="rail"):
        _mode("rail")


def test_route_graph_importer_rejects_oversized_extract() -> None:
    """The importer applies the same bounded-extract posture as routing."""

    edges = [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]

    with pytest.raises(ValueError, match="exceeding the configured cap"):
        _validate_edge_count(edges, max_edges=1, graph_key="default")
