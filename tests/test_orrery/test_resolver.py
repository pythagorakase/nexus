"""Tests for Orrery dry-run resolver integration."""

import pytest

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES


class FakeResult:
    """Tiny SQLAlchemy result stand-in for resolver unit tests."""

    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """Return deterministic rows keyed by the resolver's read-only queries."""

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, statement, _params=None):
        sql = str(statement)
        if "SELECT entity_id, tag, is_ephemeral" in sql:
            return FakeResult([])
        if "SELECT entity_id, current_location" in sql:
            return FakeResult([{"entity_id": 1, "current_location": 10}])
        if "SELECT id, type::text AS location_class" in sql:
            return FakeResult([{"id": 10, "location_class": "the_roots"}])
        if "SELECT entity_id, current_activity" in sql:
            return FakeResult([{"entity_id": 1, "current_activity": "idle"}])
        if "FROM character_relationships" in sql:
            return FakeResult([])
        if "FROM faction_character_relationships" in sql:
            return FakeResult([])
        if "FROM world_events" in sql and "event_type" in sql:
            return FakeResult([])
        if "FROM chunk_entity_references_v" in sql:
            return FakeResult([{"entity_id": 1}])
        if "SELECT DISTINCT candidate.entity_id" in sql:
            return FakeResult([])
        if "SELECT DISTINCT etc.entity_id" in sql:
            return FakeResult([])
        if "SELECT max(id) AS max_id" in sql:
            return FakeResult([{"max_id": 100}])
        raise AssertionError(f"Unexpected resolver query: {sql}")


class FakeMemnon:
    """Minimal MEMNON stand-in exposing the Session factory."""

    def Session(self):
        return FakeSession()


class FakeLore:
    """Minimal LORE stand-in for TurnCycleManager tests."""

    def __init__(self, settings):
        self.settings = settings
        self.memnon = FakeMemnon()


def test_resolve_dry_run_returns_inspectable_proposal() -> None:
    """Dry-run resolution hydrates, binds, and produces no-write drafts."""

    proposal = resolve_dry_run(
        FakeSession(),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.anchor_chunk_id == 100
    assert proposal.actor_count == 1
    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "maintain_cover"
    assert proposal.resolutions[0].bindings == {"actor": 1}


@pytest.mark.asyncio
async def test_resolve_orrery_skips_when_disabled() -> None:
    """The LORE phase is inert unless Orrery is explicitly enabled."""

    manager = TurnCycleManager(FakeLore({"orrery": {"enabled": False}}))
    context = TurnContext(turn_id="t1", user_input="continue", start_time=0)

    await manager.resolve_orrery(context)

    assert context.orrery_proposal is None
    assert context.phase_states["orrery_resolve"] == {
        "enabled": False,
        "skipped": True,
    }


@pytest.mark.asyncio
async def test_resolve_orrery_attaches_proposal_when_enabled() -> None:
    """Enabled dry-run integration stores the proposal on TurnContext only."""

    manager = TurnCycleManager(
        FakeLore({"orrery": {"enabled": True, "binding": {"window_chunks": 30}}})
    )
    context = TurnContext(
        turn_id="t1",
        user_input="continue",
        start_time=0,
        warm_slice=[{"id": 100}],
    )

    await manager.resolve_orrery(context)

    assert context.orrery_proposal is not None
    assert context.orrery_proposal.anchor_chunk_id == 100
    assert context.phase_states["orrery_resolve"]["resolution_count"] == 1
    assert context.context_payload == {}
