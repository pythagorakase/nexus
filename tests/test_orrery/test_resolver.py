"""Tests for Orrery dry-run resolver integration."""

from datetime import datetime, timezone

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

    def __init__(
        self,
        *,
        tag_rows=None,
        location_rows=None,
        location_class_rows=None,
        activity_rows=None,
        relationship_rows=None,
        faction_rows=None,
        event_rows=None,
        chunk_ref_actor_rows=None,
        event_actor_rows=None,
        ephemeral_actor_rows=None,
        world_time=None,
        weather="",
        max_chunk_id=100,
    ):
        self.tag_rows = tag_rows or []
        self.location_rows = location_rows or [{"entity_id": 1, "current_location": 10}]
        self.location_class_rows = location_class_rows or [
            {"id": 10, "location_class": "the_roots"}
        ]
        self.activity_rows = activity_rows or [
            {"entity_id": 1, "current_activity": "idle"}
        ]
        self.relationship_rows = relationship_rows or []
        self.faction_rows = faction_rows or []
        self.event_rows = event_rows or []
        self.chunk_ref_actor_rows = chunk_ref_actor_rows or [{"entity_id": 1}]
        self.event_actor_rows = event_actor_rows or []
        self.ephemeral_actor_rows = ephemeral_actor_rows or []
        self.world_time = world_time or datetime(2073, 10, 31, 12, tzinfo=timezone.utc)
        self.weather = weather
        self.max_chunk_id = max_chunk_id
        self.max_id_queries = 0

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, statement, _params=None):
        sql = str(statement)
        if "/* orrery:current_tags */" in sql:
            return FakeResult(self.tag_rows)
        if "/* orrery:character_locations */" in sql:
            return FakeResult(self.location_rows)
        if "/* orrery:location_classes */" in sql:
            return FakeResult(self.location_class_rows)
        if "/* orrery:character_activities */" in sql:
            return FakeResult(self.activity_rows)
        if "/* orrery:relationship_types */" in sql:
            return FakeResult(self.relationship_rows)
        if "/* orrery:faction_memberships */" in sql:
            return FakeResult(self.faction_rows)
        if "/* orrery:recent_events */" in sql:
            assert "superseded_by_event_id IS NULL" in sql
            return FakeResult(self.event_rows)
        if "/* orrery:actor_bindings_chunk_refs */" in sql:
            return FakeResult(self.chunk_ref_actor_rows)
        if "/* orrery:actor_bindings_events */" in sql:
            assert "(world_layer IS NULL OR world_layer = 'primary')" in sql
            assert "superseded_by_event_id IS NULL" in sql
            return FakeResult(self.event_actor_rows)
        if "/* orrery:actor_bindings_ephemeral */" in sql:
            return FakeResult(self.ephemeral_actor_rows)
        if "/* orrery:anchor_world_time */" in sql:
            return FakeResult([{"world_time": self.world_time}])
        if "/* orrery:seed_weather */" in sql:
            return FakeResult([{"weather": self.weather}])
        if "SELECT max(id) AS max_id" in sql:
            self.max_id_queries += 1
            return FakeResult([{"max_id": self.max_chunk_id}])
        raise AssertionError(f"Unexpected resolver query: {sql}")


class FakeMemnon:
    """Minimal MEMNON stand-in exposing the Session factory."""

    def __init__(self, session=None):
        self.session = session or FakeSession()

    def Session(self):
        return self.session


class FakeLore:
    """Minimal LORE stand-in for TurnCycleManager tests."""

    def __init__(self, settings, session=None):
        self.settings = settings
        self.memnon = FakeMemnon(session)


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


@pytest.mark.parametrize(
    ("session", "template_id", "branch_label"),
    [
        (
            FakeSession(
                event_rows=[
                    {
                        "event_type": "compliance_alert",
                        "tick_chunk_id": 99,
                        "actor_entity_id": None,
                        "target_entity_id": 1,
                        "location_id": None,
                        "changed_fields": [],
                        "world_layer": "primary",
                        "payload": {},
                    }
                ],
                weather="hard rain",
            ),
            "evade_pursuers",
            "Go to ground in flooded tunnels",
        ),
        (
            FakeSession(
                tag_rows=[
                    {
                        "entity_id": 1,
                        "tag": "contacts_available",
                        "is_ephemeral": False,
                    }
                ],
                event_rows=[
                    {
                        "event_type": "encoded_message",
                        "tick_chunk_id": 99,
                        "actor_entity_id": None,
                        "target_entity_id": 1,
                        "location_id": None,
                        "changed_fields": [],
                        "world_layer": "primary",
                        "payload": {},
                    }
                ],
            ),
            "honor_debt",
            "Fulfill obligation through a dead-drop",
        ),
        (
            FakeSession(
                tag_rows=[
                    {
                        "entity_id": 1,
                        "tag": "seeking_identity",
                        "is_ephemeral": False,
                    }
                ],
                world_time=datetime(2073, 10, 31, 18, tzinfo=timezone.utc),
            ),
            "pursue_ghost_lead",
            "Recon a hideout their body remembers",
        ),
    ],
)
def test_resolve_dry_run_exercises_priority_packages(
    session, template_id: str, branch_label: str
) -> None:
    """The dry-run resolver covers non-fallback built-in package gates."""

    proposal = resolve_dry_run(
        session,
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == template_id
    assert proposal.resolutions[0].branch_label == branch_label


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


@pytest.mark.asyncio
async def test_resolve_orrery_uses_same_session_for_anchor_fallback() -> None:
    """Anchor fallback reads occur inside the dry-run resolver session."""

    session = FakeSession(max_chunk_id=101)
    manager = TurnCycleManager(
        FakeLore(
            {"orrery": {"enabled": True, "binding": {"window_chunks": 30}}},
            session=session,
        )
    )
    context = TurnContext(turn_id="t1", user_input="continue", start_time=0)

    await manager.resolve_orrery(context)

    assert session.max_id_queries == 1
    assert context.orrery_proposal is not None
    assert context.orrery_proposal.anchor_chunk_id == 101
