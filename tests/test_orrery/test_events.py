"""Tests for canonical Orrery commit-time event materialization."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import nexus.agents.orrery.events as orrery_events
from nexus.agents.orrery.events import coerce_adjudications, commit_orrery_tick_sync
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryScenePressureDraft,
    OrreryTickProposal,
)
from nexus.api.lore_adapter import response_to_incubator


class RecordingCursor:
    """Small psycopg cursor stand-in keyed by the Orrery writer's SQL."""

    def __init__(
        self,
        *,
        duplicate_resolution: bool = False,
        known_tags=None,
        current_tags=None,
        clear_tag_ids=None,
        world_time=None,
        need_state=None,
        current_location=99,
        planned_destination=42,
        active_destination=42,
        travel_progress=0.4,
        geodesic_distance_m=10000,
        route_graph_nodes=None,
        route_graph_edges=None,
        authored_route_edges=None,
        travel_state_update_rowcount=1,
        character_entity_ids=None,
        inbound_pair_tag_clear_count=0,
    ):
        self.duplicate_resolution = duplicate_resolution
        self.known_tags = {"off_grid": 77} if known_tags is None else known_tags
        self.current_tags = set() if current_tags is None else current_tags
        self.clear_tag_ids = [] if clear_tag_ids is None else clear_tag_ids
        self.world_time = world_time or datetime(2073, 10, 31, 18, tzinfo=timezone.utc)
        self.need_state = {} if need_state is None else need_state
        self.current_location = current_location
        self.planned_destination = planned_destination
        self.active_destination = active_destination
        self.travel_progress = travel_progress
        self.geodesic_distance_m = geodesic_distance_m
        self.route_graph_nodes = list(route_graph_nodes or [])
        self.route_graph_edges = list(route_graph_edges or [])
        self.authored_route_edges = list(authored_route_edges or [])
        self.travel_state_update_rowcount = travel_state_update_rowcount
        self.character_entity_ids = (
            {11: 1} if character_entity_ids is None else character_entity_ids
        )
        self.inbound_pair_tag_clear_count = inbound_pair_tag_clear_count
        self.executed = []
        self.rowcount = 1
        self._fetchone = None
        self._fetchall = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._fetchone = None
        self._fetchall = []
        normalized = " ".join(str(sql).split())

        if "FROM entities WHERE id = ANY" in normalized:
            entity_ids = params[0]
            self._fetchall = [{"id": entity_id} for entity_id in entity_ids]
        elif "FROM characters WHERE id = ANY" in normalized:
            character_ids = params[0]
            self._fetchall = [
                {
                    "id": character_id,
                    "entity_id": self.character_entity_ids[character_id],
                }
                for character_id in character_ids
                if character_id in self.character_entity_ids
            ]
        elif "FROM entity_names_v WHERE id = ANY" in normalized:
            names = {1: "Mara", 2: "Vale"}
            self._fetchall = [
                {"id": entity_id, "name": names.get(entity_id, f"Entity {entity_id}")}
                for entity_id in params[0]
            ]
        elif "INSERT INTO orrery_resolutions" in normalized:
            self._fetchone = None if self.duplicate_resolution else {"id": 10}
        elif "UPDATE characters SET current_activity" in normalized:
            self.rowcount = 1
        elif "FROM tags WHERE tag" in normalized:
            tag = params[0]
            if tag in self.known_tags:
                self._fetchone = {"id": self.known_tags[tag]}
        elif "INSERT INTO entity_tags" in normalized:
            entity_id, tag_id, _template_id = params
            tags_by_id = {value: key for key, value in self.known_tags.items()}
            tag = tags_by_id[tag_id]
            if (entity_id, tag) not in self.current_tags:
                self._fetchone = {"id": 88}
        elif "FROM event_types WHERE type" in normalized:
            self._fetchone = {"type": params[0]}
        elif "SELECT world_time FROM chunk_metadata" in normalized:
            self._fetchone = {"world_time": self.world_time}
        elif "SELECT now() AS world_time" in normalized:
            self._fetchone = {"world_time": self.world_time}
        elif "INSERT INTO character_need_states" in normalized:
            entity_id, need_type, world_time = params
            self.need_state.setdefault(
                (entity_id, need_type),
                {"debt_score": 0, "last_evaluated_at": world_time},
            )
        elif (
            "SELECT debt_score, last_evaluated_at FROM character_need_states"
            in normalized
        ):
            entity_id, need_type = params
            self._fetchone = self.need_state.get((entity_id, need_type))
        elif "UPDATE character_need_states" in normalized:
            debt_score, world_time, _fulfilled_at, _metadata, entity_id, need_type = (
                params
            )
            self.need_state[(entity_id, need_type)] = {
                "debt_score": debt_score,
                "last_evaluated_at": world_time,
            }
        elif "SELECT t.tag FROM entity_tags et JOIN tags t" in normalized:
            entity_id, tags = params
            self._fetchall = [
                {"tag": tag} for tag in tags if (entity_id, tag) in self.current_tags
            ]
        elif (
            "SELECT destination_place_id FROM character_travel_states" in normalized
            and "status = 'planned'" in normalized
        ):
            self._fetchone = {"destination_place_id": self.planned_destination}
        elif (
            "SELECT destination_place_id FROM character_travel_states" in normalized
            and "status = 'in_transit'" in normalized
        ):
            self._fetchone = {"destination_place_id": self.active_destination}
        elif (
            "SELECT progress_ratio FROM character_travel_states" in normalized
            and "status = 'in_transit'" in normalized
        ):
            self._fetchone = {"progress_ratio": self.travel_progress}
        elif "FROM orrery_place_route_graph_nodes" in normalized:
            place_id, graph_key, travel_mode, _order_travel_mode = params
            candidates = []
            for node in self.route_graph_nodes:
                if node.get("place_id") != place_id:
                    continue
                if node.get("graph_key", "default") != graph_key:
                    continue
                node_travel_mode = node.get("travel_mode", "mixed")
                if node_travel_mode not in {travel_mode, "mixed"}:
                    continue
                candidates.append(
                    (
                        node_travel_mode != travel_mode,
                        node.get("distance_m") is None,
                        node.get("distance_m") or 0,
                        node.get("node_id"),
                        node,
                    )
                )
            if candidates:
                _is_mixed, _distance_null, _distance, _node_id, node = sorted(
                    candidates
                )[0]
                self._fetchone = {
                    "node_id": node["node_id"],
                    "travel_mode": node.get("travel_mode", "mixed"),
                    "distance_m": node.get("distance_m"),
                    "source": node.get("source"),
                    "metadata": node.get("metadata", {}),
                    "node_key": node.get("node_key", str(node["node_id"])),
                    "node_geojson": node.get("node_geojson"),
                }
        elif "FROM orrery_route_graph_edges" in normalized:
            graph_key, travel_mode, *limit_params = params
            edge_limit = limit_params[0] if limit_params else None
            self._fetchall = []
            for edge in self.route_graph_edges:
                if edge.get("graph_key", "default") != graph_key:
                    continue
                edge_travel_mode = edge.get("travel_mode", "mixed")
                if edge_travel_mode not in {travel_mode, "mixed"}:
                    continue
                self._fetchall.append(
                    {
                        "id": edge.get("id", 100),
                        "from_node_id": edge["from_node_id"],
                        "to_node_id": edge["to_node_id"],
                        "travel_mode": edge_travel_mode,
                        "risk": edge.get("risk", "low"),
                        "bidirectional": edge.get("bidirectional", True),
                        "distance_m": edge["distance_m"],
                        "duration_minutes": edge.get("duration_minutes"),
                    }
                )
            if edge_limit is not None:
                self._fetchall = self._fetchall[:edge_limit]
        elif "FROM orrery_travel_edges" in normalized:
            (
                origin_place_id,
                destination_place_id,
                travel_mode,
                _direct_from_place_id,
                _direct_to_place_id,
                reverse_from_place_id,
                reverse_to_place_id,
                _order_travel_mode,
            ) = params
            candidates = []
            for edge in self.authored_route_edges:
                if edge.get("route_method", "authored_edge") != "authored_edge":
                    continue
                edge_travel_mode = edge.get("travel_mode", "mixed")
                if edge_travel_mode not in {travel_mode, "mixed"}:
                    continue
                is_direct = (
                    edge["from_place_id"] == origin_place_id
                    and edge["to_place_id"] == destination_place_id
                )
                is_reversible = (
                    edge["from_place_id"] == reverse_from_place_id
                    and edge["to_place_id"] == reverse_to_place_id
                    and edge.get("bidirectional", False)
                )
                if is_direct or is_reversible:
                    candidates.append(
                        (
                            edge_travel_mode != travel_mode,
                            not is_direct,
                            edge.get("id", 7),
                            edge,
                        )
                    )
            if candidates:
                _is_mixed, _is_reverse, _edge_id, edge = sorted(candidates)[0]
                self._fetchone = {
                    "id": edge.get("id", 7),
                    "from_place_id": edge["from_place_id"],
                    "to_place_id": edge["to_place_id"],
                    "route_method": edge.get("route_method", "authored_edge"),
                    "travel_mode": edge.get("travel_mode", "mixed"),
                    "risk": edge.get("risk", "low"),
                    "bidirectional": edge.get("bidirectional", False),
                    "distance_m": edge.get("distance_m"),
                    "duration_minutes": edge.get("duration_minutes"),
                    "route_geometry_geojson": edge.get("route_geometry_geojson"),
                    "source": edge.get("source"),
                    "metadata": edge.get("metadata", {}),
                    "is_direct": (
                        edge["from_place_id"] == origin_place_id
                        and edge["to_place_id"] == destination_place_id
                    ),
                }
        elif "SELECT ST_Distance(o.coordinates, d.coordinates)" in normalized:
            self._fetchone = {"geodesic_distance_m": self.geodesic_distance_m}
        elif "SELECT current_location FROM characters" in normalized:
            self._fetchone = {"current_location": self.current_location}
        elif "INSERT INTO character_travel_states" in normalized:
            self.rowcount = 1
        elif "UPDATE character_travel_states" in normalized:
            self.rowcount = self.travel_state_update_rowcount
        elif "UPDATE characters SET current_location" in normalized:
            self.rowcount = 1
        elif "UPDATE entity_pair_tags ept SET cleared_at = now()" in normalized:
            self.rowcount = self.inbound_pair_tag_clear_count
        elif "INSERT INTO world_events" in normalized:
            self._fetchone = {"id": 20}
        elif "SELECT et.id FROM entity_tags et JOIN tags t" in normalized:
            self._fetchall = [{"id": tag_id} for tag_id in self.clear_tag_ids]
        elif "SELECT et.id FROM entity_tags et WHERE" in normalized:
            entity_id, tag_id = params
            tags_by_id = {value: key for key, value in self.known_tags.items()}
            tag = tags_by_id[tag_id]
            if (entity_id, tag) in self.current_tags:
                self._fetchall = [{"id": tag_id + 1000}]

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall


class RecordingConn:
    """Connection stand-in returning one recording cursor."""

    def __init__(self, cursor: RecordingCursor):
        self.cursor_obj = cursor

    def cursor(self):
        return self.cursor_obj


class MinimalStoryResponse:
    """Tiny response object for lore_adapter serialization tests."""

    narrative = "The corridor hums."
    response_id = "resp-1"
    chunk_metadata = None
    metadata = None
    state_updates = None
    entity_updates = None
    referenced_entities = None
    references = None
    choices = None


def _proposal() -> OrreryTickProposal:
    draft = OrreryResolutionDraft(
        template_id="evade_pursuers",
        priority=100,
        binding_hash="abc123",
        bindings={"actor": 1},
        branch_label="Go to ground",
        narrative_stub="{actor} vanishes into a maintenance corridor.",
        state_delta={
            "character.current_activity": "hiding from active pursuit",
            "entity_tags.add": ["off_grid"],
        },
        event_type="evade_pursuit",
        changed_fields=("character.current_activity", "entity_tags"),
        magnitude=0.72,
    )
    return OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )


def _scene_pressure() -> OrreryScenePressureDraft:
    return OrreryScenePressureDraft(
        template_id="protect_kin",
        priority=95,
        binding_hash="pressure-1",
        bindings={"actor": 1, "target": 2},
        branch_label="Travel toward the target's last known location",
        pressure_stub="{actor} is moving toward {target}.",
        prompt_text="Mara is moving toward Vale.",
        magnitude=0.52,
    )


def _travel_start_proposal(
    *,
    destination_place_id: int = 42,
    mode: str = "vehicle",
    risk: str | None = None,
    route_graph: str | None = None,
) -> OrreryTickProposal:
    travel_start = {
        "destination_place_id": destination_place_id,
        "mode": mode,
        "initial_progress": 0.1,
    }
    if risk is not None:
        travel_start["risk"] = risk
    if route_graph is not None:
        travel_start["route_graph"] = route_graph
    draft = OrreryResolutionDraft(
        template_id="travel",
        priority=21,
        binding_hash=f"travel-start-{mode}-{destination_place_id}",
        bindings={"actor": 1},
        branch_label="Depart toward the planned destination",
        narrative_stub="{actor} starts the journey.",
        state_delta={
            "character.current_activity": "departing toward destination",
            "travel.start": travel_start,
        },
        event_type="travel_departed",
        changed_fields=(
            "character.current_activity",
            "character_travel_states.status",
        ),
        magnitude=0.28,
    )
    return OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )


def _inserted_travel_params(cursor: RecordingCursor) -> tuple[Any, ...]:
    return next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )


def _travel_insert_row(cursor: RecordingCursor) -> dict[str, Any]:
    params = _inserted_travel_params(cursor)
    return {
        "character_entity_id": params[0],
        "anchor_place_id": params[1],
        "origin_place_id": params[2],
        "destination_place_id": params[3],
        "route_method": params[4],
        "travel_mode": params[5],
        "risk": params[6],
        "progress_ratio": params[7],
        "estimated_distance_m": params[8],
        "estimated_duration_minutes": params[9],
        "route_metadata": json.loads(params[-1]),
    }


def test_proposal_round_trips_through_json_shape() -> None:
    """Commit can hydrate the exact proposal shape stored in incubator JSONB."""

    proposal = _proposal()
    payload = proposal.to_dict()

    assert payload["resolutions"][0]["proposal_id"] == "evade_pursuers:abc123"
    assert OrreryTickProposal.from_dict(payload) == proposal


def test_proposal_round_trips_scene_pressures_without_state_delta() -> None:
    """Scene pressure survives incubator JSONB without becoming commit state."""

    base = _proposal()
    proposal = replace(base, scene_pressures=(_scene_pressure(),))
    payload = proposal.to_dict()

    assert "state_delta" not in payload["scene_pressures"][0]
    assert OrreryTickProposal.from_dict(payload) == proposal


def test_response_to_incubator_serializes_orrery_proposal() -> None:
    """The preview-to-approval handoff carries Orrery proposals durably."""

    incubator_data = response_to_incubator(
        MinimalStoryResponse(),
        parent_chunk_id=99,
        user_text="Continue.",
        session_id="session-1",
        orrery_proposal=_proposal(),
    )

    assert incubator_data["orrery_proposal"]["anchor_chunk_id"] == 99
    assert incubator_data["orrery_proposal"]["resolutions"][0]["template_id"] == (
        "evade_pursuers"
    )
    assert incubator_data["orrery_proposal"]["scene_pressures"] == []


def test_response_to_incubator_serializes_orrery_adjudications() -> None:
    """Skald's structured Orrery rulings ride the incubator handoff."""

    class ResponseWithAdjudication(MinimalStoryResponse):
        orrery_adjudications = [
            {
                "proposal_id": "evade_pursuers:abc123",
                "action": "defer",
                "note": "Hold for the next beat.",
            }
        ]

    incubator_data = response_to_incubator(
        ResponseWithAdjudication(),
        parent_chunk_id=99,
        user_text="Continue.",
        session_id="session-1",
        orrery_proposal=_proposal(),
    )

    assert incubator_data["orrery_adjudications"] == [
        {
            "proposal_id": "evade_pursuers:abc123",
            "action": "defer",
            "note": "Hold for the next beat.",
        }
    ]


def test_commit_orrery_tick_ignores_scene_pressures() -> None:
    """Prompt-only pressures do not materialize canonical Orrery writes."""

    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(),
        scene_pressures=(_scene_pressure(),),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor()

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    assert result.resolution_count == 0
    assert result.event_count == 0
    assert result.tag_mutation_count == 0
    assert cursor.executed == []


def test_commit_orrery_tick_materializes_resolution_event_and_tags() -> None:
    """Accepted commits stamp the preview proposal into canonical Orrery tables."""

    cursor = RecordingCursor(clear_tag_ids=[55])
    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal().to_dict(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)
    resolution_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO orrery_resolutions" in sql
    )

    assert result.resolution_count == 1
    assert result.event_count == 1
    assert result.tag_mutation_count == 1
    assert result.cleared_tag_count == 1
    assert result.skipped_existing_count == 0
    assert "INSERT INTO orrery_resolutions" in statements
    assert "INSERT INTO world_events" in statements
    assert "INSERT INTO world_event_entities" in statements
    assert "INSERT INTO tag_clearance_log" in statements
    assert resolution_params[-1] == "Mara vanishes into a maintenance corridor."


def test_commit_orrery_tick_defers_explicit_adjudication() -> None:
    """Defer preserves pressure by skipping materialization this tick."""

    cursor = RecordingCursor()
    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
        adjudications=[
            {
                "proposal_id": "evade_pursuers:abc123",
                "action": "defer",
                "note": "Not during this exchange.",
            }
        ],
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert result.resolution_count == 0
    assert result.event_count == 0
    assert result.adjudication_count == 1
    assert result.deferred_count == 1
    assert "INSERT INTO orrery_adjudication_log" in statements
    assert "INSERT INTO orrery_resolutions" not in statements
    assert "UPDATE characters SET current_activity" not in statements


def test_commit_orrery_tick_voids_explicit_adjudication() -> None:
    """Void records a definitive Skald cancellation without side effects."""

    cursor = RecordingCursor()
    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
        adjudications=[
            {
                "proposal_id": "evade_pursuers:abc123",
                "action": "void",
                "note": "The pursuit no longer exists.",
            }
        ],
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert result.resolution_count == 0
    assert result.adjudication_count == 1
    assert result.voided_count == 1
    assert "INSERT INTO orrery_adjudication_log" in statements
    assert "INSERT INTO world_events" not in statements


def test_commit_orrery_tick_replaces_from_structured_state_update() -> None:
    """Structured Skald writes to the same entity/field beat Orrery proposals."""

    cursor = RecordingCursor()
    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
        storyteller_state_updates={
            "characters": [
                {"character_id": 11, "current_activity": "arguing in the room"}
            ]
        },
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)
    audit_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO orrery_adjudication_log" in sql
    )

    assert result.resolution_count == 0
    assert result.adjudication_count == 1
    assert result.replaced_count == 1
    assert audit_params[5] == "structured_state_update"
    assert "INSERT INTO orrery_resolutions" not in statements
    assert "UPDATE characters SET current_activity" not in statements


def test_commit_orrery_tick_replaces_with_explicit_delta() -> None:
    """Replace can commit a Skald-authored Orrery-compatible delta."""

    cursor = RecordingCursor()
    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
        adjudications=[
            {
                "proposal_id": "evade_pursuers:abc123",
                "action": "replace",
                "note": "Mara stays engaged instead of vanishing.",
                "replacement_state_delta": {
                    "character_current_activity": "arguing in the room"
                },
            }
        ],
    )

    activity_params = next(
        params
        for sql, params in cursor.executed
        if "UPDATE characters SET current_activity" in sql
    )
    audit_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO orrery_adjudication_log" in sql
    )

    assert result.resolution_count == 1
    assert result.event_count == 0
    assert result.adjudication_count == 1
    assert result.replaced_count == 1
    assert activity_params == ("arguing in the room", 1)
    assert audit_params[5] == "explicit"
    assert not any("INSERT INTO world_events" in sql for sql, _ in cursor.executed)


def test_commit_orrery_tick_replacement_event_type_is_explicit() -> None:
    """Replacement deltas only emit canonical events when Skald names the event."""

    cursor = RecordingCursor()
    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
        adjudications=[
            {
                "proposal_id": "evade_pursuers:abc123",
                "action": "replace",
                "replacement_state_delta": {
                    "character_current_activity": "ducking out of sight"
                },
                "replacement_event_type": "evade_pursuit",
            }
        ],
    )

    event_params = next(
        params for sql, params in cursor.executed if "INSERT INTO world_events" in sql
    )

    assert result.event_count == 1
    assert event_params[0] == "evade_pursuit"


def test_coerce_adjudications_rejects_bare_mapping() -> None:
    """Adjudications must be a list or wrapper object, not guessed from a dict."""

    with pytest.raises(TypeError, match="must be a list"):
        coerce_adjudications(
            {
                "proposal_id": "evade_pursuers:abc123",
                "action": "defer",
            }
        )


def test_commit_orrery_tick_does_not_cancel_travel_for_activity_only_update() -> None:
    """A current_activity write alone does not supersede unrelated travel state."""

    draft = OrreryResolutionDraft(
        template_id="travel",
        priority=21,
        binding_hash="travel-state-only",
        bindings={"actor": 1},
        branch_label="Depart toward the planned destination",
        narrative_stub="{actor} starts the journey.",
        state_delta={
            "travel.start": {
                "destination_place_id": 42,
                "mode": "vehicle",
                "initial_progress": 0.1,
            },
        },
        event_type="travel_departed",
        changed_fields=("character_travel_states.status",),
        magnitude=0.28,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor()

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
        storyteller_state_updates={
            "characters": [
                {"character_id": 11, "current_activity": "reading in the room"}
            ]
        },
    )

    assert result.resolution_count == 1
    assert result.replaced_count == 0
    assert any(
        "INSERT INTO character_travel_states" in sql for sql, _ in cursor.executed
    )


def test_commit_orrery_tick_does_not_count_duplicate_replacement() -> None:
    """Replacement metrics describe applied or handled replacements, not duplicates."""

    cursor = RecordingCursor(duplicate_resolution=True)
    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
        adjudications=[
            {
                "proposal_id": "evade_pursuers:abc123",
                "action": "replace",
                "replacement_state_delta": {
                    "character_current_activity": "arguing in the room"
                },
            }
        ],
    )

    assert result.skipped_existing_count == 1
    assert result.replaced_count == 0


def test_commit_orrery_tick_skips_existing_resolution_without_double_writes() -> None:
    """The unique resolution key prevents duplicate event/state side effects."""

    cursor = RecordingCursor(duplicate_resolution=True)
    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert result.resolution_count == 0
    assert result.event_count == 0
    assert result.skipped_existing_count == 1
    assert "INSERT INTO world_events" not in statements
    assert "UPDATE characters SET current_activity" not in statements


def test_commit_orrery_tick_rejects_unregistered_tags() -> None:
    """State deltas cannot silently invent tag vocabulary at commit time."""

    cursor = RecordingCursor(known_tags={})

    with pytest.raises(ValueError, match="not registered"):
        commit_orrery_tick_sync(
            RecordingConn(cursor),
            _proposal(),
            tick_chunk_id=100,
            slot=5,
            world_layer="primary",
        )


def test_commit_orrery_tick_reports_missing_template_binding() -> None:
    """Template authoring errors identify the bad template and binding."""

    proposal = _proposal()
    broken = replace(
        proposal.resolutions[0],
        narrative_stub="{missing} vanishes into a maintenance corridor.",
    )
    broken_proposal = OrreryTickProposal(
        anchor_chunk_id=proposal.anchor_chunk_id,
        actor_count=proposal.actor_count,
        resolutions=(broken,),
        generated_at=proposal.generated_at,
    )

    with pytest.raises(ValueError, match="evade_pursuers.*missing binding 'missing'"):
        commit_orrery_tick_sync(
            RecordingConn(RecordingCursor()),
            broken_proposal,
            tick_chunk_id=100,
            slot=5,
            world_layer="primary",
        )


def test_commit_orrery_tick_skips_duplicate_active_tag_insert() -> None:
    """Active tag uniqueness conflicts do not double-count tag mutations."""

    cursor = RecordingCursor(current_tags={(1, "off_grid")})

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _proposal(),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert result.tag_mutation_count == 0
    assert "ON CONFLICT DO NOTHING" in statements


def test_commit_orrery_tick_applies_target_tag_deltas() -> None:
    """Multi-slot packages can mutate actor and target tag state explicitly."""

    draft = OrreryResolutionDraft(
        template_id="extract_vengeance",
        priority=90,
        binding_hash="vengeance-1",
        bindings={"actor": 1, "target": 2},
        branch_label="Surface a reputation attack",
        narrative_stub="{actor} compromises {target}'s reputation.",
        state_delta={
            "character.current_activity": "running a reputation attack",
            "entity_tags.add": ["off_grid"],
            "entity_tags_target.add": ["reputation_compromised"],
            "entity_tags_target.remove": ["grudge_active"],
        },
        event_type="retaliation_attempted",
        changed_fields=("character.current_activity", "entity_tags"),
        magnitude=0.58,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor(
        known_tags={
            "off_grid": 77,
            "reputation_compromised": 78,
            "grudge_active": 79,
        },
        current_tags={(2, "grudge_active")},
    )

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)
    event_params = next(
        params for sql, params in cursor.executed if "INSERT INTO world_events" in sql
    )

    assert result.resolution_count == 1
    assert result.event_count == 1
    assert result.tag_mutation_count == 3
    assert "VALUES (%s, 'target', %s)" in statements
    assert "mechanism, justification, source_chunk_id" in statements
    assert event_params[3] == 2


def test_commit_orrery_tick_clears_inbound_target_pair_tags() -> None:
    """Multi-slot packages can clear relational pressure aimed at a target."""

    draft = OrreryResolutionDraft(
        template_id="protect_kin",
        priority=95,
        binding_hash="protect-1",
        bindings={"actor": 1, "target": 2},
        branch_label="Physically intervene at the target's location",
        narrative_stub="{actor} pulls {target} out of danger.",
        state_delta={
            "character.current_activity": "shielding kin from active threat",
            "entity_pair_tags_target.clear_inbound": ["hunting"],
        },
        event_type="protective_intervention",
        changed_fields=("character.current_activity", "entity_pair_tags"),
        magnitude=0.78,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor(inbound_pair_tag_clear_count=2)

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)
    pair_clear_params = next(
        params for sql, params in cursor.executed if "UPDATE entity_pair_tags" in sql
    )

    assert result.tag_mutation_count == 2
    assert "FROM pair_tags pt" in statements
    assert pair_clear_params == (2, "hunting")


def test_commit_orrery_tick_starts_estimated_travel_without_moving_actor() -> None:
    """Departure records route state; current_location remains the place anchor."""

    draft = OrreryResolutionDraft(
        template_id="travel",
        priority=21,
        binding_hash="travel-start-1",
        bindings={"actor": 1},
        branch_label="Depart toward the planned destination",
        narrative_stub="{actor} starts the journey.",
        state_delta={
            "character.current_activity": "departing toward destination",
            "travel.start": {
                "destination_place_id": 42,
                "mode": "vehicle",
                "initial_progress": 0.1,
            },
        },
        event_type="travel_departed",
        changed_fields=(
            "character.current_activity",
            "character_travel_states.status",
        ),
        magnitude=0.28,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor(current_location=99, geodesic_distance_m=10000)

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)
    travel_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )
    route_metadata = json.loads(travel_params[-1])

    assert result.resolution_count == 1
    assert result.event_count == 1
    assert "UPDATE characters SET current_location" not in statements
    assert travel_params[:4] == (1, 99, 99, 42)
    assert travel_params[4] == "estimated"
    assert travel_params[5] == "vehicle"
    assert travel_params[7] == pytest.approx(0.1)
    assert travel_params[8] > 10000
    assert route_metadata["route_method"] == "estimated"
    assert route_metadata["origin_place_id"] == 99
    assert route_metadata["destination_place_id"] == 42
    assert route_metadata["travel_mode"] == "vehicle"
    assert route_metadata["detour_factor"] > 1


def test_commit_orrery_tick_prefers_osm_graph_route() -> None:
    """Local graph routing wins before authored edges or coarse estimates."""

    cursor = RecordingCursor(
        current_location=99,
        geodesic_distance_m=999999,
        route_graph_nodes=[
            {
                "place_id": 99,
                "node_id": 1001,
                "travel_mode": "vehicle",
                "distance_m": 12,
                "node_key": "origin-road",
                "node_geojson": '{"type":"Point","coordinates":[0,0]}',
            },
            {
                "place_id": 42,
                "node_id": 1003,
                "travel_mode": "vehicle",
                "distance_m": 18,
                "node_key": "destination-road",
            },
        ],
        route_graph_edges=[
            {
                "id": 501,
                "from_node_id": 1001,
                "to_node_id": 1002,
                "travel_mode": "vehicle",
                "distance_m": 3000,
                "duration_minutes": 4,
            },
            {
                "id": 502,
                "from_node_id": 1002,
                "to_node_id": 1003,
                "travel_mode": "vehicle",
                "risk": "moderate",
                "distance_m": 7000,
                "duration_minutes": 11,
            },
        ],
        authored_route_edges=[
            {
                "id": 17,
                "from_place_id": 99,
                "to_place_id": 42,
                "travel_mode": "vehicle",
                "distance_m": 12345,
                "duration_minutes": 37.5,
            }
        ],
    )

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_row = _travel_insert_row(cursor)
    route_metadata = travel_row["route_metadata"]

    assert result.resolution_count == 1
    assert not any("FROM orrery_travel_edges" in sql for sql, _ in cursor.executed)
    assert not any(
        "ST_Distance(o.coordinates, d.coordinates)" in sql for sql, _ in cursor.executed
    )
    assert travel_row["route_method"] == "osm_graph"
    assert travel_row["travel_mode"] == "vehicle"
    assert travel_row["risk"] == "moderate"
    assert travel_row["estimated_distance_m"] == pytest.approx(10000)
    assert travel_row["estimated_duration_minutes"] == pytest.approx(15)
    assert route_metadata["route_method"] == "osm_graph"
    assert route_metadata["route_edge_ids"] == [501, 502]
    assert route_metadata["route_node_ids"] == [1001, 1002, 1003]
    assert route_metadata["origin_node_key"] == "origin-road"
    assert route_metadata["destination_node_key"] == "destination-road"
    assert route_metadata["origin_node_geometry"]["type"] == "Point"


def test_commit_orrery_tick_uses_mixed_osm_graph_edges_for_concrete_mode() -> None:
    """Generic graph edges can route concrete mode requests."""

    cursor = RecordingCursor(
        current_location=99,
        route_graph_nodes=[
            {"place_id": 99, "node_id": 1001, "travel_mode": "mixed"},
            {"place_id": 42, "node_id": 1002, "travel_mode": "mixed"},
        ],
        route_graph_edges=[
            {
                "id": 501,
                "from_node_id": 1001,
                "to_node_id": 1002,
                "travel_mode": "mixed",
                "distance_m": 9000,
                "duration_minutes": 12,
            }
        ],
    )

    commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_row = _travel_insert_row(cursor)
    route_metadata = travel_row["route_metadata"]

    assert travel_row["route_method"] == "osm_graph"
    assert travel_row["travel_mode"] == "vehicle"
    assert route_metadata["edge_travel_modes"] == ["mixed"]


def test_commit_orrery_tick_propagates_non_default_route_graph_key() -> None:
    """Travel starts can request a named graph namespace."""

    cursor = RecordingCursor(
        current_location=99,
        route_graph_nodes=[
            {
                "place_id": 99,
                "node_id": 1001,
                "travel_mode": "vehicle",
                "graph_key": "regional",
            },
            {
                "place_id": 42,
                "node_id": 1002,
                "travel_mode": "vehicle",
                "graph_key": "regional",
            },
        ],
        route_graph_edges=[
            {
                "id": 501,
                "from_node_id": 1001,
                "to_node_id": 1002,
                "travel_mode": "vehicle",
                "graph_key": "regional",
                "distance_m": 7200,
                "duration_minutes": 9,
            }
        ],
    )

    commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle", route_graph="regional"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_row = _travel_insert_row(cursor)

    assert travel_row["route_method"] == "osm_graph"
    assert travel_row["route_metadata"]["graph_key"] == "regional"
    assert travel_row["estimated_distance_m"] == pytest.approx(7200)


def test_commit_orrery_tick_rejects_oversized_route_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bounded graph extracts fail fast instead of silently falling back."""

    monkeypatch.setattr(orrery_events, "_route_graph_max_edges_per_query", lambda: 1)
    cursor = RecordingCursor(
        current_location=99,
        route_graph_nodes=[
            {"place_id": 99, "node_id": 1001, "travel_mode": "vehicle"},
            {"place_id": 42, "node_id": 1003, "travel_mode": "vehicle"},
        ],
        route_graph_edges=[
            {
                "id": 501,
                "from_node_id": 1001,
                "to_node_id": 1002,
                "travel_mode": "vehicle",
                "distance_m": 3000,
            },
            {
                "id": 502,
                "from_node_id": 1002,
                "to_node_id": 1003,
                "travel_mode": "vehicle",
                "distance_m": 7000,
            },
        ],
        authored_route_edges=[
            {
                "id": 17,
                "from_place_id": 99,
                "to_place_id": 42,
                "travel_mode": "vehicle",
                "distance_m": 12345,
            }
        ],
    )

    with pytest.raises(ValueError, match="route graph query exceeded"):
        commit_orrery_tick_sync(
            RecordingConn(cursor),
            _travel_start_proposal(mode="vehicle"),
            tick_chunk_id=100,
            slot=5,
            world_layer="primary",
        )


def test_commit_orrery_tick_falls_back_to_authored_when_osm_unreachable() -> None:
    """Graph anchors without a connecting path do not block authored routes."""

    cursor = RecordingCursor(
        current_location=99,
        route_graph_nodes=[
            {"place_id": 99, "node_id": 1001, "travel_mode": "vehicle"},
            {"place_id": 42, "node_id": 1003, "travel_mode": "vehicle"},
        ],
        route_graph_edges=[
            {
                "id": 501,
                "from_node_id": 1001,
                "to_node_id": 1002,
                "travel_mode": "vehicle",
                "distance_m": 3000,
                "duration_minutes": 4,
            }
        ],
        authored_route_edges=[
            {
                "id": 17,
                "from_place_id": 99,
                "to_place_id": 42,
                "travel_mode": "vehicle",
                "distance_m": 12345,
                "duration_minutes": 37.5,
            }
        ],
    )

    commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )
    route_metadata = json.loads(travel_params[-1])

    assert travel_params[4] == "authored_edge"
    assert route_metadata["route_method"] == "authored_edge"
    assert route_metadata["route_edge_id"] == 17


def test_commit_orrery_tick_prefers_direct_authored_route_edge() -> None:
    """An authored edge wins over the coarse coordinate estimate."""

    cursor = RecordingCursor(
        current_location=99,
        geodesic_distance_m=999999,
        authored_route_edges=[
            {
                "id": 17,
                "from_place_id": 99,
                "to_place_id": 42,
                "travel_mode": "vehicle",
                "risk": "high",
                "distance_m": 12345,
                "duration_minutes": 37.5,
                "source": "author:route-notes",
                "metadata": {"name": "checkpoint road"},
                "route_geometry_geojson": (
                    '{"type":"LineString","coordinates":[[0,0],[1,1]]}'
                ),
            }
        ],
    )

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )
    route_metadata = json.loads(travel_params[-1])

    assert result.resolution_count == 1
    assert not any(
        "ST_Distance(o.coordinates, d.coordinates)" in sql for sql, _ in cursor.executed
    )
    assert travel_params[4] == "authored_edge"
    assert travel_params[5] == "vehicle"
    assert travel_params[6] == "high"
    assert travel_params[8] == pytest.approx(12345)
    assert travel_params[9] == pytest.approx(37.5)
    assert route_metadata["route_method"] == "authored_edge"
    assert route_metadata["route_edge_id"] == 17
    assert route_metadata["reversed"] is False
    assert route_metadata["bidirectional"] is False
    assert route_metadata["travel_mode"] == "vehicle"
    assert route_metadata["edge_travel_mode"] == "vehicle"
    assert route_metadata["source"] == "author:route-notes"
    assert route_metadata["edge_metadata"] == {"name": "checkpoint road"}
    assert route_metadata["route_geometry"]["type"] == "LineString"


def test_commit_orrery_tick_uses_mixed_authored_edge_for_concrete_mode() -> None:
    """Generic authored edges still serve concrete travel-mode requests."""

    cursor = RecordingCursor(
        current_location=99,
        geodesic_distance_m=999999,
        authored_route_edges=[
            {
                "id": 31,
                "from_place_id": 99,
                "to_place_id": 42,
                "travel_mode": "mixed",
                "risk": "moderate",
                "distance_m": 15000,
                "duration_minutes": 45,
            }
        ],
    )

    commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )
    route_metadata = json.loads(travel_params[-1])

    assert not any(
        "ST_Distance(o.coordinates, d.coordinates)" in sql for sql, _ in cursor.executed
    )
    assert travel_params[4] == "authored_edge"
    assert travel_params[5] == "vehicle"
    assert route_metadata["route_edge_id"] == 31
    assert route_metadata["travel_mode"] == "vehicle"
    assert route_metadata["edge_travel_mode"] == "mixed"


def test_commit_orrery_tick_allows_authored_route_without_duration() -> None:
    """Incomplete authored estimates still preserve route provenance."""

    cursor = RecordingCursor(
        current_location=99,
        authored_route_edges=[
            {
                "id": 19,
                "from_place_id": 99,
                "to_place_id": 42,
                "travel_mode": "vehicle",
                "distance_m": 12345,
                "duration_minutes": None,
            }
        ],
    )

    commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )
    route_metadata = json.loads(travel_params[-1])

    assert travel_params[4] == "authored_edge"
    assert travel_params[8] == pytest.approx(12345)
    assert travel_params[9] is None
    assert travel_params[12] is None
    assert route_metadata["route_edge_id"] == 19


def test_commit_orrery_tick_uses_bidirectional_authored_edge_in_reverse() -> None:
    """Reverse traversal is allowed only when the authored edge opts in."""

    cursor = RecordingCursor(
        current_location=99,
        authored_route_edges=[
            {
                "id": 23,
                "from_place_id": 42,
                "to_place_id": 99,
                "travel_mode": "vehicle",
                "risk": "moderate",
                "bidirectional": True,
                "distance_m": 8000,
                "duration_minutes": 20,
            }
        ],
    )

    commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )
    route_metadata = json.loads(travel_params[-1])

    assert travel_params[4] == "authored_edge"
    assert travel_params[6] == "moderate"
    assert route_metadata["route_edge_id"] == 23
    assert route_metadata["edge_from_place_id"] == 42
    assert route_metadata["edge_to_place_id"] == 99
    assert route_metadata["reversed"] is True


def test_commit_orrery_tick_rejects_non_bidirectional_reverse_edge() -> None:
    """One-way authored edges do not leak into reverse travel."""

    cursor = RecordingCursor(
        current_location=99,
        geodesic_distance_m=10000,
        authored_route_edges=[
            {
                "id": 23,
                "from_place_id": 42,
                "to_place_id": 99,
                "travel_mode": "vehicle",
                "risk": "moderate",
                "bidirectional": False,
                "distance_m": 8000,
                "duration_minutes": 20,
            }
        ],
    )

    commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )
    route_metadata = json.loads(travel_params[-1])

    route_queries = [
        sql for sql, _ in cursor.executed if "FROM orrery_travel_edges" in sql
    ]
    assert len(route_queries) == 1
    assert any(
        "ST_Distance(o.coordinates, d.coordinates)" in sql for sql, _ in cursor.executed
    )
    assert travel_params[4] == "estimated"
    assert route_metadata["route_method"] == "estimated"


def test_commit_orrery_tick_falls_back_when_authored_edge_mode_incompatible() -> None:
    """Edges for another travel mode are ignored instead of coerced."""

    cursor = RecordingCursor(
        current_location=99,
        geodesic_distance_m=10000,
        authored_route_edges=[
            {
                "id": 17,
                "from_place_id": 99,
                "to_place_id": 42,
                "travel_mode": "rail",
                "risk": "low",
                "distance_m": 5000,
                "duration_minutes": 12,
            }
        ],
    )

    commit_orrery_tick_sync(
        RecordingConn(cursor),
        _travel_start_proposal(mode="vehicle"),
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    travel_params = next(
        params
        for sql, params in cursor.executed
        if "INSERT INTO character_travel_states" in sql
    )
    route_metadata = json.loads(travel_params[-1])

    assert travel_params[4] == "estimated"
    assert route_metadata["route_method"] == "estimated"
    assert route_metadata["travel_mode"] == "vehicle"


def test_commit_orrery_tick_advances_travel_progress_without_moving_actor() -> None:
    """Progress updates the route row but leaves arrival to an explicit branch."""

    draft = OrreryResolutionDraft(
        template_id="travel",
        priority=21,
        binding_hash="travel-progress-1",
        bindings={"actor": 1},
        branch_label="Make steady progress along the route",
        narrative_stub="{actor} keeps moving.",
        state_delta={
            "character.current_activity": "traveling toward destination",
            "travel.advance": {"progress_delta": 0.35},
        },
        event_type="travel_progressed",
        changed_fields=("character_travel_states.progress_ratio",),
        magnitude=0.18,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor(travel_progress=0.5)

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)
    advance_params = next(
        params
        for sql, params in cursor.executed
        if "UPDATE character_travel_states" in sql and "progress_ratio = %s" in sql
    )

    assert result.resolution_count == 1
    assert "UPDATE characters SET current_location" not in statements
    assert advance_params[0] == pytest.approx(0.85)


def test_commit_orrery_tick_records_travel_delay_risk() -> None:
    """Travel delay validates and stores risk escalation explicitly."""

    draft = OrreryResolutionDraft(
        template_id="travel",
        priority=21,
        binding_hash="travel-delay-1",
        bindings={"actor": 1},
        branch_label="Lose time to bad conditions or route friction",
        narrative_stub="{actor} loses time.",
        state_delta={
            "character.current_activity": "delayed in transit",
            "travel.delay": {"risk": "high", "reason": "storm"},
        },
        event_type="travel_delayed",
        changed_fields=("character_travel_states.risk",),
        magnitude=0.24,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor()

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    delay_params = next(
        params
        for sql, params in cursor.executed
        if "UPDATE character_travel_states" in sql and "COALESCE" in sql
    )

    assert result.resolution_count == 1
    assert delay_params[0] == "high"
    assert json.loads(delay_params[2]) == {
        "last_delay": {"risk": "high", "reason": "storm"}
    }


def test_commit_orrery_tick_arrival_moves_actor_to_destination() -> None:
    """Arrival is the only travel effect that rewrites current_location."""

    draft = OrreryResolutionDraft(
        template_id="travel",
        priority=21,
        binding_hash="travel-arrive-1",
        bindings={"actor": 1},
        branch_label="Arrive at the planned destination",
        narrative_stub="{actor} arrives.",
        state_delta={
            "character.current_activity": "arriving at destination",
            "travel.arrive": True,
        },
        event_type="travel_arrived",
        changed_fields=(
            "character.current_location",
            "character_travel_states.status",
        ),
        magnitude=0.34,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor(active_destination=42)

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    location_params = next(
        params
        for sql, params in cursor.executed
        if "UPDATE characters SET current_location" in sql
    )
    travel_params = next(
        params
        for sql, params in cursor.executed
        if "UPDATE character_travel_states" in sql and "status = 'at_place'" in sql
    )

    assert result.resolution_count == 1
    assert result.event_count == 1
    assert location_params == (42, 1)
    assert travel_params[0] == 42


def test_commit_orrery_tick_arrival_requires_travel_state_row() -> None:
    """Arrival cannot move location while leaving travel state unsynchronized."""

    draft = OrreryResolutionDraft(
        template_id="travel",
        priority=21,
        binding_hash="travel-arrive-missing-state",
        bindings={"actor": 1},
        branch_label="Arrive at the planned destination",
        narrative_stub="{actor} arrives.",
        state_delta={
            "character.current_activity": "arriving at destination",
            "travel.arrive": {"destination_place_id": 42},
        },
        event_type="travel_arrived",
        changed_fields=(
            "character.current_location",
            "character_travel_states.status",
        ),
        magnitude=0.34,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )

    with pytest.raises(ValueError, match="has no travel state row"):
        commit_orrery_tick_sync(
            RecordingConn(RecordingCursor(travel_state_update_rowcount=0)),
            proposal,
            tick_chunk_id=100,
            slot=5,
            world_layer="primary",
        )


def test_commit_orrery_tick_applies_need_fulfillment_delta() -> None:
    """Need fulfillment accrues debt, discharges it, and syncs severity tags."""

    world_time = datetime(2073, 10, 31, 18, tzinfo=timezone.utc)
    draft = OrreryResolutionDraft(
        template_id="sleep",
        priority=25,
        binding_hash="sleep-1",
        bindings={"actor": 1},
        branch_label="Sleep rough in cover or transit",
        narrative_stub="{actor} sleeps in fragments.",
        state_delta={
            "character.current_activity": "sleeping rough",
            "need.fulfill": {
                "type": "sleep",
                "quality": "rough",
                "discharge_debt": 4,
            },
        },
        event_type="slept",
        changed_fields=(
            "character.current_activity",
            "character_need_states.debt_score",
        ),
        magnitude=0.36,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )
    cursor = RecordingCursor(
        known_tags={
            "sleep_deprived_1_mild": 101,
            "sleep_deprived_2_moderate": 102,
            "sleep_deprived_3_severe": 103,
            "sleep_deprived_4_critical": 104,
        },
        current_tags={(1, "sleep_deprived_2_moderate")},
        world_time=world_time,
        need_state={
            (1, "sleep"): {
                "debt_score": 20,
                "last_evaluated_at": world_time - timedelta(hours=2),
            }
        },
    )

    result = commit_orrery_tick_sync(
        RecordingConn(cursor),
        proposal,
        tick_chunk_id=100,
        slot=5,
        world_layer="primary",
    )

    statements = "\n".join(sql for sql, _params in cursor.executed)

    assert result.resolution_count == 1
    assert result.event_count == 1
    assert result.tag_mutation_count == 2
    assert cursor.need_state[(1, "sleep")]["debt_score"] == 18
    assert "UPDATE character_need_states" in statements
    assert any(
        "INSERT INTO entity_tags" in sql and params == (1, 101, "sleep")
        for sql, params in cursor.executed
    )


def test_commit_orrery_tick_reports_missing_need_type() -> None:
    """Malformed need.fulfill payloads get an actionable error."""

    draft = OrreryResolutionDraft(
        template_id="sleep",
        priority=25,
        binding_hash="sleep-1",
        bindings={"actor": 1},
        branch_label="Sleep rough in cover or transit",
        narrative_stub="{actor} sleeps in fragments.",
        state_delta={"need.fulfill": {"quality": "rough"}},
        event_type="slept",
        changed_fields=("character_need_states.debt_score",),
        magnitude=0.36,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )

    with pytest.raises(ValueError, match="must include a 'type' or 'need' field"):
        commit_orrery_tick_sync(
            RecordingConn(RecordingCursor()),
            proposal,
            tick_chunk_id=100,
            slot=5,
            world_layer="primary",
        )


def test_commit_orrery_tick_reports_missing_need_actor() -> None:
    """Malformed need.fulfill templates fail before database integrity errors."""

    draft = OrreryResolutionDraft(
        template_id="sleep",
        priority=25,
        binding_hash="sleep-1",
        bindings={},
        branch_label="Sleep rough in cover or transit",
        narrative_stub="Someone sleeps in fragments.",
        state_delta={"need.fulfill": {"type": "sleep", "quality": "rough"}},
        event_type="slept",
        changed_fields=("character_need_states.debt_score",),
        magnitude=0.36,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=99,
        actor_count=1,
        resolutions=(draft,),
        generated_at="2073-10-31T18:00:00+00:00",
    )

    with pytest.raises(ValueError, match="requires an actor binding"):
        commit_orrery_tick_sync(
            RecordingConn(RecordingCursor()),
            proposal,
            tick_chunk_id=100,
            slot=5,
            world_layer="primary",
        )
