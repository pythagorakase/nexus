"""Tests for Orrery dry-run resolver integration."""

from datetime import datetime, timezone

import pytest

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.resolver import (
    LOCATION_CLASS_TAG_CATEGORIES,
    _need_pressure_stub,
    compose_actor_target_bindings,
    hydrate_world_state,
    resolve_dry_run,
)
from nexus.agents.orrery.substrate import (
    ALWAYS,
    AND,
    Branch,
    PresentTargetPolicy,
    Slot,
    Template,
    trust_at_least,
    trust_below,
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
        pair_tag_rows=None,
        faction_rows=None,
        event_rows=None,
        chunk_ref_actor_rows=None,
        event_actor_rows=None,
        ephemeral_actor_rows=None,
        inbound_ephemeral_pair_actor_rows=None,
        present_actor_rows=None,
        actor_target_relationship_rows=None,
        entity_name_rows=None,
        need_debt_rows=None,
        travel_state_rows=None,
        world_time=None,
        weather="",
        max_chunk_id=100,
    ):
        self.tag_rows = tag_rows or []
        self.location_rows = location_rows or [{"entity_id": 1, "current_location": 10}]
        self.location_class_rows = location_class_rows or [
            {"id": 10, "location_class": "fixed_location", "is_primary": True},
        ]
        self.activity_rows = activity_rows or [
            {"entity_id": 1, "current_activity": "idle"}
        ]
        self.relationship_rows = relationship_rows or []
        self.pair_tag_rows = pair_tag_rows or []
        self.faction_rows = faction_rows or []
        self.event_rows = event_rows or []
        self.chunk_ref_actor_rows = chunk_ref_actor_rows or [{"entity_id": 1}]
        self.event_actor_rows = event_actor_rows or []
        self.ephemeral_actor_rows = ephemeral_actor_rows or []
        self.inbound_ephemeral_pair_actor_rows = inbound_ephemeral_pair_actor_rows or []
        self.present_actor_rows = present_actor_rows or []
        self.actor_target_relationship_rows = actor_target_relationship_rows or []
        self.entity_name_rows = entity_name_rows or [
            {"id": 1, "name": "Mara"},
            {"id": 2, "name": "Vale"},
            {"id": 3, "name": "Iris"},
        ]
        self.need_debt_rows = need_debt_rows or []
        self.travel_state_rows = travel_state_rows or []
        self.world_time = world_time or datetime(2073, 10, 31, 12, tzinfo=timezone.utc)
        self.weather = weather
        self.max_chunk_id = max_chunk_id
        self.max_id_queries = 0
        self.world_time_queries = 0

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
            for category in LOCATION_CLASS_TAG_CATEGORIES:
                assert category in sql
            assert "place_affordance" not in sql
            return FakeResult(self.location_class_rows)
        if "/* orrery:character_activities */" in sql:
            return FakeResult(self.activity_rows)
        if "/* orrery:relationship_types */" in sql:
            assert "valence_magnitude" in sql
            return FakeResult(self.relationship_rows)
        if "/* orrery:pair_tags */" in sql:
            assert "ept.cleared_at IS NULL" in sql
            assert "NOT pt.deprecated" in sql
            return FakeResult(self.pair_tag_rows)
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
        if "/* orrery:actor_bindings_inbound_ephemeral_pair_tags */" in sql:
            assert "pt.is_ephemeral = true" in sql
            assert "pt.tag = 'hunting'" in sql
            assert "NOT pt.deprecated" in sql
            assert "subject_entity.is_active = true" in sql
            return FakeResult(self.inbound_ephemeral_pair_actor_rows)
        if "/* orrery:present_actor_ids_at_anchor */" in sql:
            return FakeResult(self.present_actor_rows)
        if "/* orrery:actor_target_bindings_character_relationships */" in sql:
            assert "relationship_scope = 'character'" in sql
            return FakeResult(self.actor_target_relationship_rows)
        if "/* orrery:entity_names */" in sql:
            return FakeResult(self.entity_name_rows)
        if "/* orrery:need_debt_scores */" in sql:
            assert "JOIN entities e" in sql
            assert "e.is_active = true" in sql
            return FakeResult(self.need_debt_rows)
        if "/* orrery:travel_states */" in sql:
            assert "JOIN entities e" in sql
            assert "e.is_active = true" in sql
            return FakeResult(self.travel_state_rows)
        if "/* orrery:anchor_world_time */" in sql:
            self.world_time_queries += 1
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


def test_resolve_dry_run_allows_null_resolution() -> None:
    """Dry-run resolution can skip under-specified actors without fallback noise."""

    proposal = resolve_dry_run(
        FakeSession(),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.anchor_chunk_id == 100
    assert proposal.actor_count == 1
    assert proposal.resolution_count == 0
    assert proposal.pressure_count == 0


def test_resolve_dry_run_excludes_anchor_present_characters() -> None:
    """Orrery does not drive characters currently owned by the storyteller."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}, {"entity_id": 2}],
            event_actor_rows=[{"entity_id": 3}],
            ephemeral_actor_rows=[{"entity_id": 4}],
            present_actor_rows=[{"entity_id": 1}, {"entity_id": 3}],
            tag_rows=[
                {"entity_id": 2, "tag": "cover_identity", "is_ephemeral": False},
                {"entity_id": 4, "tag": "cover_identity", "is_ephemeral": False},
            ],
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
                location_class_rows=[
                    {"id": 10, "location_class": "subterranean", "is_primary": False},
                    {"id": 10, "location_class": "transit", "is_primary": False},
                    {"id": 10, "location_class": "fixed_location", "is_primary": True},
                ],
                weather="hard rain",
            ),
            "evade_pursuers",
            "Go to ground in flooded tunnels",
        ),
        (
            FakeSession(
                pair_tag_rows=[
                    {
                        "subject_entity_id": 1,
                        "object_entity_id": 2,
                        "tag": "contact:social",
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
                location_class_rows=[
                    {"id": 10, "location_class": "subterranean", "is_primary": False},
                    {"id": 10, "location_class": "transit", "is_primary": False},
                    {"id": 10, "location_class": "fixed_location", "is_primary": True},
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


def test_maintain_cover_requires_positive_cover_context() -> None:
    """MAINTAIN_COVER is not a generic fallback for every quiet actor."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[{"entity_id": 1, "tag": "cover_identity", "is_ephemeral": False}],
            location_class_rows=[
                {"id": 10, "location_class": "fixed_location", "is_primary": True}
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "maintain_cover"
    assert proposal.resolutions[0].branch_label == "Maintain a specific cover identity"


def test_maintain_cover_skips_constrained_actor() -> None:
    """Captive/sandboxed actors should not drift through public cover."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[
                {"entity_id": 1, "tag": "cover_identity", "is_ephemeral": False},
                {"entity_id": 1, "tag": "sandboxed", "is_ephemeral": True},
            ],
            location_class_rows=[
                {"id": 10, "location_class": "urban_dense", "is_primary": False},
                {"id": 10, "location_class": "place_open", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0


def test_evade_pursuers_skips_captive_public_flow() -> None:
    """Inbound hunting cannot make a captive actor blend into crowds."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[
                {"entity_id": 1, "tag": "captive", "is_ephemeral": True},
            ],
            pair_tag_rows=[
                {"subject_entity_id": 2, "object_entity_id": 1, "tag": "hunting"},
            ],
            location_class_rows=[
                {"id": 10, "location_class": "blacksite", "is_primary": True}
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0


def test_hide_handles_steady_state_concealment() -> None:
    """Off-grid concealment resolves through HIDE rather than cover fallback."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[{"entity_id": 1, "tag": "off_grid", "is_ephemeral": False}],
            location_class_rows=[
                {"id": 10, "location_class": "haven", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "hide"
    assert proposal.resolutions[0].branch_label == "Go dark and reduce signal exposure"


def test_active_pursuit_beats_hide() -> None:
    """EVADE owns active hunting while HIDE owns chronic concealment."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[
                {"entity_id": 1, "tag": "off_grid", "is_ephemeral": False},
            ],
            pair_tag_rows=[
                {
                    "subject_entity_id": 1,
                    "object_entity_id": 2,
                    "tag": "contact:lodging",
                },
                {"subject_entity_id": 2, "object_entity_id": 1, "tag": "hunting"},
            ],
            inbound_ephemeral_pair_actor_rows=[{"entity_id": 1}],
            location_class_rows=[
                {"id": 10, "location_class": "haven", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "evade_pursuers"
    assert proposal.resolutions[0].branch_label == "Reach a safe house through contacts"


def test_inbound_hunting_pair_tag_binds_actor_for_evade() -> None:
    """A hunted object is actor-eligible even without a legacy ephemeral flag."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[],
            pair_tag_rows=[
                {
                    "subject_entity_id": 1,
                    "object_entity_id": 2,
                    "tag": "contact:lodging",
                },
                {"subject_entity_id": 2, "object_entity_id": 1, "tag": "hunting"},
            ],
            inbound_ephemeral_pair_actor_rows=[{"entity_id": 1}],
            location_class_rows=[
                {"id": 10, "location_class": "haven", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "evade_pursuers"


def test_surveillance_offscreen_target_commits_resolution() -> None:
    """SURVEIL keeps tabs without creating contact."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            tag_rows=[
                {"entity_id": 1, "tag": "signal_operator", "is_ephemeral": False}
            ],
            actor_target_relationship_rows=[
                {"source_entity_id": 1, "target_entity_id": 2},
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    surveil = [
        draft for draft in proposal.resolutions if draft.template_id == "surveil"
    ]
    assert len(surveil) == 1
    assert surveil[0].branch_label == "Intercept signal traffic"
    assert surveil[0].event_type == "surveillance_performed"
    assert not any(draft.event_type == "contact_made" for draft in proposal.resolutions)


def test_surveillance_present_target_becomes_scene_pressure() -> None:
    """SURVEIL may pressure an on-screen target but cannot commit it."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            present_actor_rows=[{"entity_id": 2}],
            tag_rows=[
                {"entity_id": 1, "tag": "signal_operator", "is_ephemeral": False}
            ],
            actor_target_relationship_rows=[
                {"source_entity_id": 1, "target_entity_id": 2},
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert not any(draft.template_id == "surveil" for draft in proposal.resolutions)
    assert proposal.pressure_count == 1
    assert proposal.scene_pressures[0].template_id == "surveil"
    assert "not as a canonical breach" in proposal.scene_pressures[0].prompt_text


def test_asymmetric_kin_defers_contact_instead_of_affectionate_message() -> None:
    """Kinship alone no longer implies ordinary warm contact."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            relationship_rows=[
                {
                    "source_entity_id": 1,
                    "target_entity_id": 2,
                    "relationship_type": "family",
                    "valence_magnitude": 5,
                },
                {
                    "source_entity_id": 2,
                    "target_entity_id": 1,
                    "relationship_type": "family",
                    "valence_magnitude": -3,
                },
            ],
            actor_target_relationship_rows=[
                {"source_entity_id": 1, "target_entity_id": 2},
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    kin = [
        draft
        for draft in proposal.resolutions
        if draft.template_id == "reach_out_to_kin"
    ]
    assert len(kin) == 1
    assert kin[0].branch_label == "Draft the message and leave it unsent"
    assert kin[0].event_type == "contact_deferred"
    assert not any(draft.event_type == "contact_made" for draft in proposal.resolutions)


def test_resolve_dry_run_fires_sunhelm_need_template() -> None:
    """Off-screen need debt resolves through SLEEP/EAT/DRINK packages."""

    proposal = resolve_dry_run(
        FakeSession(
            world_time=datetime(2073, 10, 31, 23, tzinfo=timezone.utc),
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "sleep",
                    "debt_score": 10,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 23, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "sleep"
    assert proposal.resolutions[0].state_delta["need.fulfill"]["type"] == "sleep"


def test_resolve_dry_run_fires_socialize_need_template() -> None:
    """Interpersonal need debt can resolve through SOCIALIZE."""

    proposal = resolve_dry_run(
        FakeSession(
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "socialize",
                    "debt_score": 200,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 12, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "socialize"
    assert proposal.resolutions[0].branch_label == (
        "Seek company after extended isolation"
    )
    assert proposal.resolutions[0].state_delta["need.fulfill"]["type"] == "socialize"


def test_resolve_dry_run_fires_intimacy_need_template_without_pairing() -> None:
    """INTIMACY records pressure relief without selecting a partner target."""

    proposal = resolve_dry_run(
        FakeSession(
            location_class_rows=[
                {"id": 10, "location_class": "dwelling", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "intimacy",
                    "debt_score": 100,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 12, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "intimacy"
    assert proposal.resolutions[0].branch_label == "Attend to the need in private"
    assert proposal.resolutions[0].bindings == {"actor": 1}
    assert proposal.resolutions[0].state_delta["need.fulfill"]["type"] == "intimacy"


def test_intimacy_partner_branch_requires_partner_relationship() -> None:
    """Established-partner intimacy uses relationship-aware co-location."""

    proposal = resolve_dry_run(
        FakeSession(
            location_rows=[
                {"entity_id": 1, "current_location": 10},
                {"entity_id": 2, "current_location": 10},
            ],
            location_class_rows=[
                {"id": 10, "location_class": "dwelling", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
            relationship_rows=[
                {
                    "source_entity_id": 1,
                    "target_entity_id": 2,
                    "relationship_type": "romantic",
                    "valence_magnitude": 3,
                }
            ],
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "intimacy",
                    "debt_score": 100,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 12, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "intimacy"
    assert proposal.resolutions[0].branch_label == (
        "Spend private time with an established partner"
    )


def test_intimacy_suppressor_blocks_intimacy_template() -> None:
    """Named suppressors close INTIMACY without falling into cover noise."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[
                {
                    "entity_id": 1,
                    "tag": "closeted",
                    "is_ephemeral": False,
                }
            ],
            location_class_rows=[
                {"id": 10, "location_class": "dwelling", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "intimacy",
                    "debt_score": 100,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 12, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0


def test_hydrate_world_state_populates_trust_from_valence_magnitude() -> None:
    """Orrery trust reads the SQL-derived relationship valence magnitude."""

    state = hydrate_world_state(
        FakeSession(
            relationship_rows=[
                {
                    "source_entity_id": 1,
                    "target_entity_id": 2,
                    "relationship_type": "comrade",
                    "valence_magnitude": 3,
                },
                {
                    "source_entity_id": 2,
                    "target_entity_id": 1,
                    "relationship_type": "rival",
                    "valence_magnitude": -3,
                },
            ]
        ),
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert state.trust[(1, 2)] == 3
    assert state.trust[(2, 1)] == -3
    assert state.relationship_types[(1, 2)] == frozenset({"comrade"})
    assert state.relationship_types[(2, 1)] == frozenset({"rival"})


def test_hydrate_world_state_uses_stable_trust_magnitude_for_duplicate_pairs() -> None:
    """Defensively collapse duplicate pair rows without depending on row order."""

    state = hydrate_world_state(
        FakeSession(
            relationship_rows=[
                {
                    "source_entity_id": 1,
                    "target_entity_id": 2,
                    "relationship_type": "comrade",
                    "valence_magnitude": 3,
                },
                {
                    "source_entity_id": 1,
                    "target_entity_id": 2,
                    "relationship_type": "enemy",
                    "valence_magnitude": -4,
                },
                {
                    "source_entity_id": 2,
                    "target_entity_id": 1,
                    "relationship_type": "ally",
                    "valence_magnitude": 3,
                },
                {
                    "source_entity_id": 2,
                    "target_entity_id": 1,
                    "relationship_type": "rival",
                    "valence_magnitude": -3,
                },
            ]
        ),
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert state.trust[(1, 2)] == -4
    assert state.trust[(2, 1)] == -3
    assert state.relationship_types[(1, 2)] == frozenset({"comrade", "enemy"})
    assert state.relationship_types[(2, 1)] == frozenset({"ally", "rival"})


def test_hydrate_world_state_loads_pair_tags() -> None:
    """Orrery snapshots hydrate active directed pair tags."""

    state = hydrate_world_state(
        FakeSession(
            pair_tag_rows=[
                {
                    "subject_entity_id": 1,
                    "object_entity_id": 2,
                    "tag": "mentors",
                },
                {
                    "subject_entity_id": 2,
                    "object_entity_id": 1,
                    "tag": "protects",
                },
            ]
        ),
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert state.pair_tags[(1, 2)] == frozenset({"mentors"})
    assert state.pair_tags[(2, 1)] == frozenset({"protects"})


def test_hydrate_world_state_loads_travel_states() -> None:
    """Resolver snapshots keep additive travel state beside current_location."""

    state = hydrate_world_state(
        FakeSession(
            travel_state_rows=[
                {
                    "character_entity_id": 1,
                    "status": "in_transit",
                    "anchor_place_id": 10,
                    "origin_place_id": 10,
                    "destination_place_id": 20,
                    "route_method": "estimated",
                    "travel_mode": "vehicle",
                    "risk": "moderate",
                    "progress_ratio": "0.42",
                    "estimated_distance_m": "13000",
                    "estimated_duration_minutes": "18.6",
                }
            ]
        ),
        anchor_chunk_id=100,
        window_chunks=30,
    )

    travel = state.travel_states[1]
    assert travel.is_in_transit
    assert travel.anchor_place_id == 10
    assert travel.destination_place_id == 20
    assert travel.route_method == "estimated"
    assert travel.travel_mode == "vehicle"
    assert travel.risk == "moderate"
    assert travel.progress_ratio == pytest.approx(0.42)
    assert travel.estimated_distance_m == pytest.approx(13000)
    assert travel.estimated_duration_minutes == pytest.approx(18.6)


def test_hydrate_world_state_loads_semantic_place_classes() -> None:
    """Place tags supplement structural place types for location predicates."""

    state = hydrate_world_state(
        FakeSession(
            location_class_rows=[
                {"id": 10, "location_class": "dwelling", "is_primary": False},
                {"id": 10, "location_class": "haven", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
        ),
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert state.location_class[10] == "fixed_location"
    assert state.location_classes[10] == frozenset(
        {"fixed_location", "dwelling", "haven"}
    )


def test_hydrate_world_state_loads_new_place_category_classes() -> None:
    """Registry-backed place categories feed in_location_class() gates."""

    state = hydrate_world_state(
        FakeSession(
            location_class_rows=[
                {"id": 10, "location_class": "dwelling", "is_primary": False},
                {"id": 10, "location_class": "place_hidden", "is_primary": False},
                {
                    "id": 10,
                    "location_class": "place_restricted",
                    "is_primary": False,
                },
                {"id": 10, "location_class": "subterranean", "is_primary": False},
                {"id": 10, "location_class": "place_contested", "is_primary": False},
                {"id": 10, "location_class": "fixed_location", "is_primary": True},
            ],
        ),
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert state.location_class[10] == "fixed_location"
    assert state.location_classes[10] == frozenset(
        {
            "fixed_location",
            "dwelling",
            "place_hidden",
            "place_restricted",
            "subterranean",
            "place_contested",
        }
    )


def test_hydrate_world_state_computes_effective_need_debt() -> None:
    """Need debt accrues from last_evaluated_at without resolver writes."""

    session = FakeSession(
        world_time=datetime(2073, 10, 31, 12, tzinfo=timezone.utc),
        need_debt_rows=[
            {
                "character_entity_id": 1,
                "need_type": "sleep",
                "debt_score": 6,
                "last_evaluated_at": datetime(2073, 10, 31, 8, tzinfo=timezone.utc),
            }
        ],
    )
    state = hydrate_world_state(
        session,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert state.need_debt_scores[(1, "sleep")] == 10
    assert session.world_time_queries == 1


def test_resolve_dry_run_fires_travel_departure_from_planned_destination() -> None:
    """Planned travel starts as in-transit state without moving current_location."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[{"entity_id": 1, "tag": "travel_ready", "is_ephemeral": False}],
            travel_state_rows=[
                {
                    "character_entity_id": 1,
                    "status": "planned",
                    "anchor_place_id": 10,
                    "origin_place_id": 10,
                    "destination_place_id": 20,
                    "route_method": "estimated",
                    "travel_mode": "mixed",
                    "risk": "low",
                    "progress_ratio": 0,
                    "estimated_distance_m": None,
                    "estimated_duration_minutes": None,
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "travel"
    assert proposal.resolutions[0].branch_label == (
        "Depart toward the planned destination"
    )
    assert proposal.resolutions[0].state_delta["travel.start"]["mode"] == "mixed"


def test_resolve_dry_run_fires_travel_arrival_at_high_progress() -> None:
    """In-transit characters arrive only when progress reaches the threshold."""

    proposal = resolve_dry_run(
        FakeSession(
            travel_state_rows=[
                {
                    "character_entity_id": 1,
                    "status": "in_transit",
                    "anchor_place_id": 10,
                    "origin_place_id": 10,
                    "destination_place_id": 20,
                    "route_method": "estimated",
                    "travel_mode": "mixed",
                    "risk": "low",
                    "progress_ratio": 0.96,
                    "estimated_distance_m": 5000,
                    "estimated_duration_minutes": 20,
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "travel"
    assert proposal.resolutions[0].branch_label == "Arrive at the planned destination"
    assert proposal.resolutions[0].state_delta["travel.arrive"] is True


def test_resolve_dry_run_fires_work_for_obligation_without_craft_tags() -> None:
    """General work remains below specialist packages but above cover fallback."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[
                {"entity_id": 1, "tag": "work_obligation", "is_ephemeral": False}
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].template_id == "work"
    assert proposal.resolutions[0].branch_label == "Keep the obligation from slipping"


def test_work_template_uses_one_global_work_cooldown() -> None:
    """Household work intentionally blocks all Work branches for a few ticks."""

    proposal = resolve_dry_run(
        FakeSession(
            tag_rows=[
                {"entity_id": 1, "tag": "work_obligation", "is_ephemeral": False}
            ],
            event_rows=[
                {
                    "event_type": "household_work_performed",
                    "tick_chunk_id": 99,
                    "actor_entity_id": 1,
                    "target_entity_id": None,
                    "location_id": None,
                    "changed_fields": ["character.current_activity"],
                    "world_layer": "primary",
                    "payload": {},
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0


@pytest.mark.parametrize(
    ("valence_magnitude", "conditions", "expected_label"),
    [
        (3, trust_at_least(2), "Trust above threshold"),
        (-3, trust_below(-2), "Trust below threshold"),
    ],
)
def test_resolve_dry_run_trust_predicates_use_hydrated_valence(
    valence_magnitude: int,
    conditions,
    expected_label: str,
) -> None:
    """Trust-gated packages can fire from entity_relationships_v magnitudes."""

    template = Template(
        id="trust_gate_test",
        priority=10,
        blurb="test trust hydration",
        required_slots=(Slot.ACTOR, Slot.TARGET),
        package_gate=ALWAYS,
        branches=(
            Branch(
                label=expected_label,
                conditions=AND(conditions),
                narrative_stub="{actor} acts on their trust toward {target}.",
            ),
        ),
    )

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            relationship_rows=[
                {
                    "source_entity_id": 1,
                    "target_entity_id": 2,
                    "relationship_type": "comrade",
                    "valence_magnitude": valence_magnitude,
                }
            ],
            actor_target_relationship_rows=[
                {"source_entity_id": 1, "target_entity_id": 2},
            ],
        ),
        [template],
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.resolutions[0].branch_label == expected_label
    assert proposal.resolutions[0].bindings == {"actor": 1, "target": 2}


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
    assert context.phase_states["orrery_resolve"]["resolution_count"] == 0
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


def test_compose_actor_target_bindings_excludes_anchor_present_targets() -> None:
    """Multi-slot packages do not drive actors currently owned by storyteller."""

    session = FakeSession(
        chunk_ref_actor_rows=[{"entity_id": 1}, {"entity_id": 2}],
        present_actor_rows=[{"entity_id": 2}],
        actor_target_relationship_rows=[
            {"source_entity_id": 1, "target_entity_id": 2},
            {"source_entity_id": 1, "target_entity_id": 3},
        ],
    )

    bindings = compose_actor_target_bindings(
        session,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    pairs = {(b[Slot.ACTOR], b[Slot.TARGET]) for b in bindings}
    assert pairs == {(1, 3)}


def test_compose_actor_target_bindings_can_select_present_targets_for_pressure() -> (
    None
):
    """Scene-pressure binding allows present targets but still excludes actors."""

    session = FakeSession(
        chunk_ref_actor_rows=[{"entity_id": 1}, {"entity_id": 2}],
        present_actor_rows=[{"entity_id": 2}],
        actor_target_relationship_rows=[
            {"source_entity_id": 1, "target_entity_id": 2},
        ],
    )

    bindings = compose_actor_target_bindings(
        session,
        anchor_chunk_id=100,
        window_chunks=30,
        target_presence="present",
    )

    pairs = {(b[Slot.ACTOR], b[Slot.TARGET]) for b in bindings}
    assert pairs == {(1, 2)}


def test_resolve_dry_run_routes_present_targets_to_scene_pressures() -> None:
    """Opt-in packages produce prompt-only pressure instead of commit drafts."""

    pressure_template = Template(
        id="pressure_test",
        priority=10,
        blurb="test pressure",
        required_slots=(Slot.ACTOR, Slot.TARGET),
        package_gate=ALWAYS,
        branches=(
            Branch(
                label="Press the scene",
                conditions=ALWAYS,
                narrative_stub="{actor} would commit a canonical event on {target}.",
                state_delta={"character.current_activity": "pressuring target"},
                scene_pressure_stub=(
                    "{actor} is creating pressure around {target}, but the "
                    "Storyteller controls whether it appears now."
                ),
            ),
        ),
        present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
    )
    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            present_actor_rows=[{"entity_id": 2}],
            actor_target_relationship_rows=[
                {"source_entity_id": 1, "target_entity_id": 2},
            ],
        ),
        [pressure_template],
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0
    assert proposal.pressure_count == 1
    pressure = proposal.scene_pressures[0]
    assert pressure.template_id == "pressure_test"
    assert pressure.bindings == {"actor": 1, "target": 2}
    assert "Mara is creating pressure around Vale" in pressure.prompt_text
    assert "state_delta" not in pressure.to_dict()


def test_resolve_dry_run_routes_present_need_debt_to_scene_pressure() -> None:
    """On-screen actors get prompt-only need pressure, not resolutions."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            present_actor_rows=[{"entity_id": 1}],
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "sleep",
                    "debt_score": 30,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 12, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0
    assert proposal.pressure_count == 1
    pressure = proposal.scene_pressures[0]
    assert pressure.template_id == "sleep_need_pressure"
    assert pressure.bindings == {"actor": 1, "resource": "sleep"}
    assert "Mara is carrying moderate sleep debt" in pressure.prompt_text
    assert "Orrery does not decide what Mara does" in pressure.prompt_text


def test_need_pressure_stub_rejects_unhandled_need_types() -> None:
    """Need prompt-pressure copy must not silently reuse intimacy wording."""

    with pytest.raises(ValueError, match="Unhandled Orrery need pressure type"):
        _need_pressure_stub("wanderlust", severity_name="moderate", debt_score=1)


def test_resolve_dry_run_routes_present_intimacy_debt_to_scene_pressure() -> None:
    """Unsuppressed on-screen intimacy pressure can reach the Storyteller."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            present_actor_rows=[{"entity_id": 1}],
            tag_rows=[
                {"entity_id": 1, "tag": "libido_moderate", "is_ephemeral": False},
            ],
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "intimacy",
                    "debt_score": 168,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 12, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0
    assert proposal.pressure_count == 1
    pressure = proposal.scene_pressures[0]
    assert pressure.template_id == "intimacy_need_pressure"
    assert pressure.bindings == {"actor": 1, "resource": "intimacy"}
    assert "Mara is carrying moderate intimacy debt" in pressure.prompt_text
    assert "Orrery does not decide what Mara does" in pressure.prompt_text


@pytest.mark.parametrize(
    ("tag", "is_ephemeral"),
    [
        ("closeted", False),
        ("libido_absent", False),
        ("focus_committed", True),
    ],
)
def test_resolve_dry_run_suppresses_present_intimacy_pressure(
    tag: str,
    is_ephemeral: bool,
) -> None:
    """Intimacy suppressors keep prompt pressure out of active scenes."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            present_actor_rows=[{"entity_id": 1}],
            tag_rows=[
                {"entity_id": 1, "tag": tag, "is_ephemeral": is_ephemeral},
            ],
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "intimacy",
                    "debt_score": 720,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 12, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0
    assert proposal.pressure_count == 0


def test_resolve_dry_run_uses_configured_present_need_pressure_tuning() -> None:
    """Present-character need pressure uses config thresholds and priorities."""

    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            present_actor_rows=[{"entity_id": 1}],
            need_debt_rows=[
                {
                    "character_entity_id": 1,
                    "need_type": "thirst",
                    "debt_score": 3,
                    "last_evaluated_at": datetime(
                        2073, 10, 31, 12, tzinfo=timezone.utc
                    ),
                }
            ],
        ),
        BUILTIN_TEMPLATES,
        anchor_chunk_id=100,
        window_chunks=30,
        sunhelm_settings={
            "accrual_rates": {"sleep": 1, "hunger": 1, "thirst": 1},
            "severity_thresholds": {
                "sleep": {"mild": 16, "moderate": 30, "severe": 48, "critical": 72},
                "hunger": {"mild": 8, "moderate": 16, "severe": 30, "critical": 48},
                "thirst": {"mild": 1, "moderate": 3, "severe": 6, "critical": 9},
            },
            "priorities": {"sleep": 25, "thirst": 7, "hunger": 22},
            "pressure": {
                "min_severity_level": 2,
                "magnitude_base": 0.2,
                "magnitude_per_level": 0.05,
                "magnitude_cap": 0.5,
            },
        },
    )

    assert proposal.resolution_count == 0
    assert proposal.pressure_count == 1
    pressure = proposal.scene_pressures[0]
    assert pressure.template_id == "thirst_need_pressure"
    assert pressure.priority == 7
    assert pressure.magnitude == pytest.approx(0.3)


def test_default_templates_keep_present_targets_offscreen_only() -> None:
    """Default multi-slot templates cannot pressure an on-screen target."""

    default_template = Template(
        id="default_present_target",
        priority=10,
        blurb="default policy",
        required_slots=(Slot.ACTOR, Slot.TARGET),
        package_gate=ALWAYS,
        branches=(
            Branch(
                label="Would fire",
                conditions=ALWAYS,
                narrative_stub="{actor} affects {target}.",
                scene_pressure_stub="{actor} pressures {target}.",
            ),
        ),
    )
    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            present_actor_rows=[{"entity_id": 2}],
            actor_target_relationship_rows=[
                {"source_entity_id": 1, "target_entity_id": 2},
            ],
        ),
        [default_template],
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 0
    assert proposal.pressure_count == 0


def test_pressure_templates_still_commit_for_offscreen_targets() -> None:
    """Pressure opt-in is dual-mode: off-screen targets still commit normally."""

    pressure_template = Template(
        id="dual_mode_pressure",
        priority=10,
        blurb="dual-mode policy",
        required_slots=(Slot.ACTOR, Slot.TARGET),
        package_gate=ALWAYS,
        branches=(
            Branch(
                label="Off-screen action",
                conditions=ALWAYS,
                narrative_stub="{actor} acts around {target}.",
                state_delta={"character.current_activity": "acting off-screen"},
                scene_pressure_stub="{actor} pressures {target}.",
            ),
        ),
        present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
    )
    proposal = resolve_dry_run(
        FakeSession(
            chunk_ref_actor_rows=[{"entity_id": 1}],
            present_actor_rows=[],
            actor_target_relationship_rows=[
                {"source_entity_id": 1, "target_entity_id": 2},
            ],
        ),
        [pressure_template],
        anchor_chunk_id=100,
        window_chunks=30,
    )

    assert proposal.resolution_count == 1
    assert proposal.pressure_count == 0
    assert proposal.resolutions[0].template_id == "dual_mode_pressure"
    assert proposal.resolutions[0].state_delta == {
        "character.current_activity": "acting off-screen"
    }


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
    relationship plus the inbound hunting edge needed to satisfy
    PROTECT_KIN's gate. The reverse binding fires the intervene branch.
    """

    session = FakeSession(
        chunk_ref_actor_rows=[{"entity_id": 1}, {"entity_id": 2}],
        location_rows=[
            {"entity_id": 1, "current_location": 10},
            {"entity_id": 2, "current_location": 10},
        ],
        location_class_rows=[
            {"id": 10, "location_class": "urban_dense", "is_primary": False},
            {"id": 10, "location_class": "place_open", "is_primary": False},
            {"id": 10, "location_class": "fixed_location", "is_primary": True},
        ],
        activity_rows=[],
        pair_tag_rows=[
            {"subject_entity_id": 3, "object_entity_id": 2, "tag": "hunting"},
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
        inbound_ephemeral_pair_actor_rows=[{"entity_id": 2}],
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
    assert proposal.pressure_count == 0
