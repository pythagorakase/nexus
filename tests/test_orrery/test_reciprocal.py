"""Tests for the reciprocal/conflict joint-beat post-pass.

Pure synthetic drafts pin the composition semantics; the live test asserts
the endpoint payload and production proposal agree on the same slots. Joint
beats are advisory (prompt + audit surface): the underlying drafts remain
the committable units, so no commit-path behavior changes here.
"""

from __future__ import annotations

import json

import pytest

from nexus.agents.orrery.reciprocal import (
    OrreryJointBeat,
    coerce_joint_beats,
    detect_joint_beats,
)
from nexus.agents.orrery.resolver import OrreryResolutionDraft, OrreryTickProposal


def _draft(
    template_id: str, actor: int, target: int | None, magnitude: float = 0.2
) -> OrreryResolutionDraft:
    bindings: dict[str, int] = {"actor": actor}
    if target is not None:
        bindings["target"] = target
    return OrreryResolutionDraft(
        template_id=template_id,
        priority=50,
        binding_hash=f"hash-{template_id}-{actor}-{target}",
        bindings=bindings,
        branch_label="test branch",
        narrative_stub=f"{{actor}} acts toward {{target}} via {template_id}.",
        magnitude=magnitude,
    )


NAMES = {1: "Alex", 2: "Emilia", 3: "Pete"}


def test_reciprocal_pair_composes_one_beat() -> None:
    beats = detect_joint_beats(
        [
            _draft("reach_out_to_kin", 1, 2, magnitude=0.3),
            _draft("reach_out_to_kin", 2, 1, magnitude=0.5),
            _draft("sleep", 3, None),
        ],
        NAMES,
    )
    assert len(beats) == 1
    (beat,) = beats
    assert beat.kind == "reciprocal"
    assert (beat.entity_a, beat.entity_b) == (1, 2)
    assert beat.magnitude == 0.5
    assert beat.entity_names == {"1": "Alex", "2": "Emilia"}
    assert beat.forward_proposal_id.startswith("reach_out_to_kin:")
    assert beat.forward_proposal_id != beat.reverse_proposal_id


def test_crossed_pair_flags_divergent_intents() -> None:
    beats = detect_joint_beats(
        [
            _draft("cultivate_informant", 1, 2),
            _draft("extract_vengeance", 2, 1),
        ],
        NAMES,
    )
    (beat,) = beats
    assert beat.kind == "crossed"
    assert beat.forward_template_id == "cultivate_informant"
    assert beat.reverse_template_id == "extract_vengeance"


def test_one_sided_drafts_produce_no_beat() -> None:
    """(1,2) stays one-sided and yields nothing; (1,3)/(3,1) composes."""

    beats = detect_joint_beats(
        [
            _draft("surveil", 1, 2),
            _draft("surveil", 1, 3),
            _draft("keep_vigil", 3, 1),
        ],
        NAMES,
    )
    assert len(beats) == 1
    assert (beats[0].entity_a, beats[0].entity_b) == (1, 3)
    assert beats[0].kind == "crossed"

    assert detect_joint_beats([_draft("surveil", 1, 2)], NAMES) == ()


def test_beats_are_deterministic_and_lower_id_forward() -> None:
    drafts = [
        _draft("keep_vigil", 9, 4),
        _draft("keep_vigil", 4, 9),
        _draft("surveil", 2, 1),
        _draft("surveil", 1, 2),
    ]
    beats = detect_joint_beats(drafts, NAMES)
    assert [(b.entity_a, b.entity_b) for b in beats] == [(1, 2), (4, 9)]
    assert beats == detect_joint_beats(list(reversed(drafts)), NAMES)


def test_proposal_serialization_round_trips_joint_beats() -> None:
    proposal = OrreryTickProposal(
        anchor_chunk_id=100,
        actor_count=2,
        resolutions=(
            _draft("reach_out_to_kin", 1, 2),
            _draft("reach_out_to_kin", 2, 1),
        ),
        joint_beats=detect_joint_beats(
            [
                _draft("reach_out_to_kin", 1, 2),
                _draft("reach_out_to_kin", 2, 1),
            ],
            NAMES,
        ),
    )
    payload = json.loads(json.dumps(proposal.to_dict()))
    assert len(payload["joint_beats"]) == 1
    hydrated = OrreryTickProposal.from_dict(payload)
    assert hydrated.joint_beats == proposal.joint_beats

    # Pre-beat incubator payloads hydrate cleanly (advisory field).
    del payload["joint_beats"]
    assert OrreryTickProposal.from_dict(payload).joint_beats == ()


def test_coerce_joint_beats_rejects_garbage() -> None:
    assert coerce_joint_beats(None) == ()
    assert coerce_joint_beats([]) == ()
    round_tripped = coerce_joint_beats(
        [
            OrreryJointBeat(
                kind="reciprocal",
                entity_a=1,
                entity_b=2,
                forward_proposal_id="a:1",
                reverse_proposal_id="b:2",
                forward_template_id="a",
                reverse_template_id="a",
                forward_stub="x",
                reverse_stub="y",
                magnitude=0.1,
            )
        ]
    )
    assert round_tripped[0].kind == "reciprocal"
    with pytest.raises(ValueError, match="Unsupported joint-beat payload"):
        coerce_joint_beats(42)
