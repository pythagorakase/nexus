"""Tests for Orrery dry-run resolver integration."""

from datetime import datetime, timezone

import pytest

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.resolver import (
    compose_actor_target_bindings,
    resolve_dry_run,
)
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    Slot,
    Template,
)
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
        present_actor_rows=None,
        actor_target_relationship_rows=None,
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
        self.present_actor_rows = present_actor_rows or []
        self.actor_target_relationship_rows = actor_target_relationship_rows or []
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
            assert "reference_type IS DISTINCT FROM 'present'" in sql
            return FakeResult(self.chunk_ref_actor_rows)
        if "/* orrery:actor_bindings_events */" in sql:
            assert "(world_layer IS NULL OR world_layer = 'primary')" in sql
            assert "superseded_by_event_id IS NULL" in sql
            return FakeResult(self.event_actor_rows)
        if "/* orrery:actor_bindings_ephemeral */" in sql:
            return FakeResult(self.ephemeral_actor_rows)
        if "/* orrery:present_actor_ids_at_anchor */" in sql:
            return FakeResult(self.present_actor_rows)
        if "/* orrery:actor_target_bindings_character_relationships */" in sql:
            assert "relationship_scope = 'character'" in sql
            return FakeResult(self.actor_target_relationship_rows)
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


def test_resolve_dry_run_excludes_anchor_present_characters() -> None:
    """Orrery does not drive characters currently owned by the storyteller."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}, {"entity_id": 2}],
            event_actor_rows=[{"entity_id": 3}],
            ephemeral_actor_rows=[{"entity_id": 4}],
            present_actor_rows=[{"entity_id": 1}, {"entity_id": 3}],
            location_rows=[
                {"entity_id": 1, "current_location": 10},
                {"entity_id": 2, "current_location": 10},
                {"entity_id": 3, "current_location": 10},
                {"entity_id": 4, "current_location": 10},
            ],
            activity_rows=[
                {"entity_id": 1, "current_activity": "in scene"},
                {"entity_id": 2, "current_activity": "mentioned elsewhere"},
                {"entity_id": 3, "current_activity": "recent event"},
                {"entity_id": 4, "current_activity": "ephemeral pressure"},
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.actor_count == 2
    assert [resolution.bindings for resolution in proposal.resolutions] == [
        {"actor": 2},
        {"actor": 4},
    ]


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


def test_compose_actor_target_bindings_is_empty_without_relationships() -> None:
    """No stored relationships ⇒ no actor-target pairs to evaluate."""

    bindings = compose_actor_target_bindings(
        FakeSession(),
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert bindings == ()


def test_compose_actor_target_bindings_yields_both_directions() -> None:
    """Each stored relationship row yields forward + reverse bindings.

    The actor side filter restricts pairs to actors in the recently-relevant
    set; both directions are emitted so symmetric templates can fire under
    either ordering and asymmetric templates can role-invert via OR clauses.
    """

    session = FakeSession(
        chunk_ref_actor_rows=[{"entity_id": 1}, {"entity_id": 2}],
        actor_target_relationship_rows=[
            {"source_entity_id": 1, "target_entity_id": 2},
        ],
    )

    bindings = compose_actor_target_bindings(
        session,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    pairs = {(b[Slot.ACTOR], b[Slot.TARGET]) for b in bindings}
    assert pairs == {(1, 2), (2, 1)}


def test_compose_actor_target_bindings_filters_to_recently_relevant_actors() -> None:
    """A pair (X, Y) emits only when X is in the recently-relevant actor set.

    The bidirectional emission in test_compose_actor_target_bindings_
    yields_both_directions requires BOTH actors to be in the set; here only
    actor 1 is, so only the (1, 2) direction emits and the (3, 4) pair is
    fully skipped.
    """

    session = FakeSession(
        chunk_ref_actor_rows=[{"entity_id": 1}],
        actor_target_relationship_rows=[
            {"source_entity_id": 1, "target_entity_id": 2},
            {"source_entity_id": 3, "target_entity_id": 4},
        ],
    )

    bindings = compose_actor_target_bindings(
        session,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    pairs = {(b[Slot.ACTOR], b[Slot.TARGET]) for b in bindings}
    assert pairs == {(1, 2)}


def test_resolve_dry_run_rejects_unsupported_slot_signatures() -> None:
    """Templates with non-(ACTOR,)/non-(ACTOR,TARGET) slot tuples fail loud."""

    weird_template = Template(
        id="weird",
        priority=1,
        blurb="declares an unsupported slot signature",
        required_slots=(Slot.ACTOR, Slot.FACTION),
        package_gate=ALWAYS,
        branches=(Branch("fallback", ALWAYS, "{actor} acts."),),
    )

    with pytest.raises(ValueError, match="required_slots"):
        resolve_dry_run(
            FakeSession(),
            [weird_template],
            anchor_chunk_id=100,
            window_chunks=30,
        )


def test_resolve_dry_run_produces_multi_slot_resolution() -> None:
    """A multi-slot template fires when its hydrated state + bindings line up.

    Builds a FakeSession that produces a single character→character
    relationship plus the ephemeral tag and event needed to satisfy
    PROTECT_KIN's gate. The reverse binding fires the intervene branch.
    """

    session = FakeSession(
        chunk_ref_actor_rows=[{"entity_id": 1}, {"entity_id": 2}],
        location_rows=[
            {"entity_id": 1, "current_location": 10},
            {"entity_id": 2, "current_location": 10},
        ],
        location_class_rows=[{"id": 10, "location_class": "the_glow"}],
        activity_rows=[],
        tag_rows=[
            {"entity_id": 2, "tag": "under_active_pursuit", "is_ephemeral": True},
        ],
        relationship_rows=[
            {
                "source_entity_id": 1,
                "target_entity_id": 2,
                "relationship_type": "family",
            },
        ],
        actor_target_relationship_rows=[
            {"source_entity_id": 1, "target_entity_id": 2},
        ],
        ephemeral_actor_rows=[{"entity_id": 2}],
    )

    proposal = resolve_dry_run(
        session,
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    protect_kin_drafts = [
        draft for draft in proposal.resolutions if draft.template_id == "protect_kin"
    ]
    assert protect_kin_drafts, (
        "PROTECT_KIN expected to fire under the constructed hydrated state; "
        f"got resolutions for {[d.template_id for d in proposal.resolutions]}"
    )
    assert protect_kin_drafts[0].branch_label == (
        "Physically intervene at the target's location"
    )
    assert protect_kin_drafts[0].bindings == {"actor": 1, "target": 2}
