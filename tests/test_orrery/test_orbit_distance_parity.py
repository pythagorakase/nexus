"""Production/audit parity for hydrated Orrery social-orbit distances."""

from __future__ import annotations

import pytest

from nexus.agents.orrery.audit import explain_dry_run
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    DriveBand,
    Slot,
    Template,
    relative_orbit_distance,
)
from tests.test_orrery.test_resolver import FakeSession


ACTOR = 1
INTERMEDIARY = 2
TARGET = 3


def _orbit_session() -> FakeSession:
    """Return A--B--C in the orbit graph with a directed A->C binding."""

    return FakeSession(
        chunk_ref_actor_rows=[{"entity_id": ACTOR}],
        actor_target_social_contact_rows=[
            {"source_entity_id": ACTOR, "target_entity_id": TARGET},
        ],
        orbit_rows=[
            {"source_entity_id": ACTOR, "target_entity_id": None},
            {"source_entity_id": INTERMEDIARY, "target_entity_id": None},
            {"source_entity_id": TARGET, "target_entity_id": None},
            {"source_entity_id": ACTOR, "target_entity_id": INTERMEDIARY},
            {"source_entity_id": INTERMEDIARY, "target_entity_id": TARGET},
        ],
    )


def _orbit_template(max_distance: int) -> Template:
    """Build one two-party package gated solely by social-orbit distance."""

    return Template(
        id=f"orbit_distance_at_most_{max_distance}",
        priority=10,
        drive_band=DriveBand.PROJECT_IDENTITY,
        blurb="Exercise hydrated social-orbit distance.",
        required_slots=(Slot.ACTOR, Slot.TARGET),
        package_gate=relative_orbit_distance(max_distance),
        branches=(
            Branch(
                label="Reach across the social orbit",
                conditions=ALWAYS,
                narrative_stub="{actor} reaches across the orbit to {target}.",
            ),
        ),
        starts_from_social_contact=True,
    )


@pytest.mark.parametrize(
    ("max_distance", "expected_to_fire"),
    [(2, True), (1, False)],
)
def test_hydrated_orbit_distance_keeps_production_audit_and_evidence_in_parity(
    max_distance: int,
    expected_to_fire: bool,
) -> None:
    """A--B--C is distance two in both resolver paths and gate evidence."""

    template = _orbit_template(max_distance)
    proposal = resolve_dry_run(
        _orbit_session(),
        [template],
        anchor_chunk_id=100,
        window_chunks=30,
    )
    report = explain_dry_run(
        _orbit_session(),
        [template],
        anchor_chunk_id=100,
        window_chunks=30,
    )

    production_fired = any(
        resolution.template_id == template.id for resolution in proposal.resolutions
    )
    assert production_fired is expected_to_fire

    assert report.actor_count == 1
    actor = report.actors[0]
    assert actor.actor_entity_id == ACTOR
    assert len(actor.two_party_stacks) == 1
    stack = actor.two_party_stacks[0]
    assert stack.bindings == {"actor": ACTOR, "target": TARGET}

    audit_fired = stack.winner_id == template.id
    assert audit_fired is production_fired
    explanation = stack.templates[0]
    assert explanation.template_id == template.id
    assert explanation.fired is expected_to_fire
    assert explanation.gate_trace.result is expected_to_fire

    evidence = explanation.gate_trace.evidence
    assert evidence is not None
    assert evidence["kind"] == "relative_orbit_distance"
    assert evidence["params"]["max_distance"] == max_distance
    assert evidence["entities"] == {"actor": ACTOR, "target": TARGET}
    assert evidence["observed"] == {"orbit_distance": 2}
    assert evidence["result"] is expected_to_fire
