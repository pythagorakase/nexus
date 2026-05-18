# Orrery Offline Route Graphs

Orrery route graphs are local, preprocessed routing data. NEXUS deliberately
uses Earth/Earth-mirror geography: `places.coordinates` are WGS84 latitude and
longitude, even when the fictional world is not literally Earth. An alien desert
spaceport still needs coordinates in an Earth desert analogue. Normal
`travel.start` commits must not call Google Maps, OSM services, or an LLM.

## Data Model

Migration `035_orrery_osm_route_graph.py` adds three tables:

- `orrery_route_graph_nodes`: graph nodes with a `graph_key`, stable `node_key`,
  optional OSM node id, and WGS84 point geometry.
- `orrery_route_graph_edges`: mode-aware graph edges with distance, optional
  duration, risk, bidirectionality, and optional LineString geometry.
- `orrery_place_route_graph_nodes`: explicit place-to-graph anchors. Orrery uses
  these anchors instead of doing nearest-node search during a turn.

`graph_key` defaults to `default`. Use a different key for bounded regional
extracts or experimental routing data, not for arbitrary non-Earth coordinate
systems. Future non-Earth settings should still choose Earth analogue locations
and store normal GIS coordinates.

## Import Format

Use `scripts/import_orrery_route_graph.py` with pre-digested JSON:

```json
{
  "graph_key": "default",
  "source": "local-osm-extract",
  "nodes": [
    {"key": "a", "lat": 47.0, "lon": -122.0, "osm_node_id": 1},
    {"key": "b", "lat": 47.1, "lon": -122.1, "osm_node_id": 2}
  ],
  "edges": [
    {
      "from": "a",
      "to": "b",
      "mode": "vehicle",
      "distance_m": 12000,
      "duration_minutes": 16,
      "bidirectional": true
    }
  ],
  "place_nodes": [
    {"place_id": 99, "node": "a", "mode": "vehicle", "distance_m": 20},
    {"place_id": 42, "node": "b", "mode": "vehicle", "distance_m": 30}
  ]
}
```

Run:

```bash
poetry run python scripts/import_orrery_route_graph.py path/to/graph.json --database save_05 --replace
```

The JSON is deliberately not raw `.osm.pbf`. Convert OSM extracts offline into a
small graph that matches the campaign region, then import that graph. The graph
router currently accepts only `walking`, `vehicle`, `covert`, and `mixed` edges;
`rail`, `water`, and `air` still route through authored edges or coordinate
estimates until they get dedicated graph support.

Imports and turn-time graph queries are bounded by
`orrery.route_graph.max_edges_per_query` in `nexus.toml` (default `5000`). If a
graph extract exceeds the cap, NEXUS raises instead of falling through to an
estimate. Trim the regional extract, split it by `graph_key`, or raise the cap
deliberately after profiling.

## Route Selection

At `travel.start`, Orrery tries routes in this order:

1. `osm_graph`: local graph route for `walking`, `vehicle`, `covert`, or `mixed`
   when both places have graph anchors and the graph connects them.
2. `authored_edge`: explicit `orrery_travel_edges` rows, including `mixed`
   edges as generic fallbacks.
3. `estimated`: coordinate-distance fallback with mode speed and detour factors.

Prefer authored edges when the route has story semantics the graph cannot know:
safehouse tunnels, ritual paths, private transit, faction-controlled shortcuts,
blocked passages, or deliberate narrative exceptions. Prefer graph routes for
ordinary roads where ballpark distance and duration matter more than bespoke
story meaning.
