"""Tests for local Orrery route-graph algorithms."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from nexus.agents.orrery.events import _route_estimate_from_distance, _travel_mode
from nexus.agents.orrery.routing import RouteGraphEdge, shortest_route
from nexus.config.loader import settings_path_scope
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


def _walking_travel_config(tmp_path: Path, *, speed_kmh: str, detour: str) -> Path:
    """Write the real nexus.toml with the walking speed and detour replaced."""

    source = Path("nexus.toml").read_text()
    for table, value in (("speed_kmh", speed_kmh), ("detour_factor", detour)):
        source, replaced = re.subn(
            rf"(^\[orrery\.travel\.{table}\]\n)walking = .*$",
            rf"\g<1>walking = {value}",
            source,
            count=1,
            flags=re.MULTILINE,
        )
        assert replaced == 1
    config = tmp_path / "nexus.toml"
    config.write_text(source)
    return config


def test_route_estimate_reads_configured_speed_and_detour(tmp_path: Path) -> None:
    """The estimate's speed and detour come from [orrery.travel], not literals."""

    config = _walking_travel_config(tmp_path, speed_kmh="10.0", detour="2.0")
    with settings_path_scope(config):
        configured = _route_estimate_from_distance(
            1000.0,
            origin_place_id=1,
            destination_place_id=2,
            mode="walking",
            risk="low",
        )

    assert configured["distance_m"] == pytest.approx(2000.0, abs=1e-6)
    assert configured["duration_minutes"] == pytest.approx(12.0, abs=1e-6)
    assert configured["metadata"]["detour_factor"] == 2.0
    assert configured["metadata"]["speed_kmh"] == 10.0

    shipped = _route_estimate_from_distance(
        1000.0,
        origin_place_id=1,
        destination_place_id=2,
        mode="walking",
        risk="low",
    )

    assert shipped["distance_m"] == pytest.approx(1350.0, abs=1e-6)
    assert shipped["duration_minutes"] == pytest.approx(16.2, abs=1e-6)
    assert shipped["metadata"]["detour_factor"] == 1.35
    assert shipped["metadata"]["speed_kmh"] == 5.0


def test_travel_mode_rejects_unconfigured_mode() -> None:
    """A mode the travel tables do not price is refused loudly."""

    with pytest.raises(ValueError, match="Unsupported Orrery travel mode: 'teleport'"):
        _travel_mode({"mode": "teleport"})
