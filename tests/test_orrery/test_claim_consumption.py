"""Fast contracts for knower-gated claim-consumption predicates."""

from nexus.agents.orrery.epistemics import ClaimKnowledge, load_epistemics_hydration
from nexus.agents.orrery.evidence import resolve_evidence
from nexus.agents.orrery.resolver import hydrate_world_state
from nexus.agents.orrery.substrate import (
    Slot,
    WorldState,
    heard_secondhand,
    knows_claim_about,
    knows_recent_event,
)
from tests.test_orrery.test_resolver import FakeSession


ACTOR = 1
TARGET = 2
FACTION = 9
UNRELATED = 11


def _claim(
    claim_id: int,
    *,
    tier: str,
    about: int,
    scope: str = "bounded",
    channel: str | None = None,
    immediate_source: int | None = None,
) -> ClaimKnowledge:
    return ClaimKnowledge(
        claim_id=claim_id,
        world_event_id=claim_id + 100,
        scope=scope,
        source_tier=tier,
        about_entity_ids=frozenset({about}),
        channel=channel,
        immediate_source_entity_id=immediate_source,
    )


def test_claim_predicates_support_explicit_common_and_faction_knowers() -> None:
    """Possession semantics do not assume a character-only subject slot."""

    state = WorldState(
        claim_knowledge_by_entity={
            ACTOR: (_claim(1, tier="participant", about=TARGET),),
            FACTION: (
                _claim(
                    2,
                    tier="told",
                    about=TARGET,
                    channel="channel:authority_over",
                    immediate_source=ACTOR,
                ),
            ),
        },
        common_claim_knowledge=(
            _claim(3, tier="common", about=UNRELATED, scope="common"),
        ),
        epistemics_enabled=True,
    )

    assert knows_claim_about()(state, {Slot.ACTOR: ACTOR, Slot.TARGET: TARGET})
    assert knows_claim_about()(state, {Slot.ACTOR: ACTOR, Slot.TARGET: UNRELATED})
    assert not knows_claim_about()(state, {Slot.ACTOR: ACTOR, Slot.TARGET: FACTION})
    assert knows_claim_about(Slot.FACTION, Slot.TARGET)(
        state, {Slot.FACTION: FACTION, Slot.TARGET: TARGET}
    )
    assert heard_secondhand(Slot.FACTION)(state, {Slot.FACTION: FACTION})
    assert not heard_secondhand()(state, {Slot.ACTOR: ACTOR})


def test_claim_predicate_evidence_names_tier_channel_and_source() -> None:
    told = _claim(
        7,
        tier="told",
        about=TARGET,
        channel="dyad:associate",
        immediate_source=FACTION,
    )
    state = WorldState(claim_knowledge_by_entity={ACTOR: (told,)})
    bindings = {Slot.ACTOR: ACTOR, Slot.TARGET: TARGET}

    about_evidence = resolve_evidence(knows_claim_about().__name__, state, bindings)
    assert about_evidence["matched"] == [
        {"claim_id": 7, "tier": "told", "scope": "bounded"}
    ]

    secondhand_evidence = resolve_evidence(heard_secondhand().__name__, state, bindings)
    assert secondhand_evidence["matched"] == [
        {
            "claim_id": 7,
            "tier": "told",
            "channel": "dyad:associate",
            "immediate_source_entity_id": FACTION,
        }
    ]


def test_hydration_projects_event_subjects_and_awareness_without_predicate_sql() -> (
    None
):
    """The resolver's single epistemics query supplies both predicate shapes."""

    session = FakeSession(
        active_entity_rows=[
            {"id": ACTOR},
            {"id": TARGET},
            {"id": FACTION},
            {"id": UNRELATED},
        ],
        event_rows=[
            {
                "id": 140,
                "event_type": "threat_issued",
                "tick_chunk_id": 100,
                "actor_entity_id": ACTOR,
                "target_entity_id": TARGET,
                "location_id": None,
                "changed_fields": [],
                "world_layer": "primary",
                "payload": {},
            },
            {
                "id": 141,
                "event_type": "threat_issued",
                "tick_chunk_id": 100,
                "actor_entity_id": ACTOR,
                "target_entity_id": FACTION,
                "location_id": None,
                "changed_fields": [],
                "world_layer": "primary",
                "payload": {},
            },
        ],
        epistemics_rows=[
            {
                "claim_id": 40,
                "world_event_id": 140,
                "scope": "bounded",
                "about_entity_ids": [TARGET, UNRELATED],
            },
            {
                "claim_id": 41,
                "world_event_id": 141,
                "scope": "common",
                "about_entity_ids": [FACTION],
            },
        ],
        epistemics_awareness_rows=[
            {
                "claim_id": 40,
                "knower_entity_id": ACTOR,
                "source_tier": "told",
                "channel": "dyad:associate",
                "immediate_source_entity_id": FACTION,
            },
        ],
    )
    state = hydrate_world_state(
        session,
        anchor_chunk_id=100,
        window_chunks=1,
        epistemics_settings={"enabled": True},
    )

    assert knows_claim_about()(state, {Slot.ACTOR: ACTOR, Slot.TARGET: TARGET})
    assert knows_claim_about()(state, {Slot.ACTOR: ACTOR, Slot.TARGET: UNRELATED})
    assert knows_claim_about()(state, {Slot.ACTOR: ACTOR, Slot.TARGET: FACTION})
    assert heard_secondhand()(state, {Slot.ACTOR: ACTOR})
    assert state.claimed_event_scopes == {140: "bounded", 141: "common"}
    assert state.awareness_by_entity == {ACTOR: frozenset({140})}
    assert [
        record.claim_id for record in state.possessed_claim_knowledge_by_entity[ACTOR]
    ] == [40, 41]


def test_recent_claim_scope_is_independent_of_entity_claim_universe() -> None:
    """A recent claim remains gated when its endpoints are outside the universe."""

    event_id = 142
    state = hydrate_world_state(
        FakeSession(
            active_entity_rows=[{"id": ACTOR}],
            event_rows=[
                {
                    "id": event_id,
                    "event_type": "threat_issued",
                    "tick_chunk_id": 100,
                    "actor_entity_id": 50,
                    "target_entity_id": 51,
                    "location_id": None,
                    "changed_fields": [],
                    "world_layer": "primary",
                    "payload": {},
                }
            ],
            epistemics_scope_rows=[{"world_event_id": event_id, "scope": "bounded"}],
        ),
        anchor_chunk_id=100,
        window_chunks=1,
        epistemics_settings={"enabled": True},
    )

    assert state.claimed_event_scopes == {event_id: "bounded"}
    assert state.claim_knowledge_by_entity == {}
    assert not knows_recent_event("threat_issued", within_ticks=1)(
        state, {Slot.ACTOR: ACTOR}
    )


def test_empty_entity_universe_skips_all_claim_queries() -> None:
    """An empty hydration universe returns before touching the database."""

    class QueryCountingSession:
        calls = 0

        def execute(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("empty Epistemics hydration must not issue SQL")

    session = QueryCountingSession()
    hydration = load_epistemics_hydration(
        session,
        entity_ids=(),
        recent_event_ids=(),
        anchor_chunk_id=100,
    )

    assert session.calls == 0
    assert hydration.claimed_event_scopes == {}
    assert hydration.possessed_claim_knowledge_by_entity == {}
