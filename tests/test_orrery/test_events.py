"""Tests for canonical Orrery commit-time event materialization."""

from __future__ import annotations

from dataclasses import replace

import pytest

from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.resolver import OrreryResolutionDraft, OrreryTickProposal
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
    ):
        self.duplicate_resolution = duplicate_resolution
        self.known_tags = {"off_grid": 77} if known_tags is None else known_tags
        self.current_tags = set() if current_tags is None else current_tags
        self.clear_tag_ids = [] if clear_tag_ids is None else clear_tag_ids
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
        elif "SELECT current_location FROM characters" in normalized:
            self._fetchone = {"current_location": 99}
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


def test_proposal_round_trips_through_json_shape() -> None:
    """Commit can hydrate the exact proposal shape stored in incubator JSONB."""

    proposal = _proposal()

    assert OrreryTickProposal.from_dict(proposal.to_dict()) == proposal


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
