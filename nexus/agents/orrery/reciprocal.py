"""Reciprocal/conflict post-pass over a tick's two-party resolutions.

The spec's "richest untapped vein" (docs/orrery_audit_dashboard_notes.md,
idea 6): ``compose_actor_target_bindings`` emits both orderings of every
relationship edge, so A→B and B→A drafts already coexist in one
``OrreryTickProposal``. This module is the pure post-pass that notices —
no resolver changes, no writes.

When both directions of a pair fire in the same tick, the pair composes
into a **joint beat**:

- ``reciprocal`` — both directions fired the *same* template (mutual reach,
  mutual surveillance): the two halves are one scene.
- ``crossed`` — the directions fired *different* templates (one cultivates
  while the other hunts): tension the storyteller can spring.

Joint beats are advisory prose for the storyteller and the audit dashboard;
the two underlying drafts remain the committable, adjudicable units — a
beat never replaces its parents in the commit path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True, slots=True)
class OrreryJointBeat:
    """One composed two-way beat between a pair of entities in one tick."""

    kind: str  # 'reciprocal' | 'crossed'
    entity_a: int
    entity_b: int
    forward_proposal_id: str
    reverse_proposal_id: str
    forward_template_id: str
    reverse_template_id: str
    forward_stub: str
    reverse_stub: str
    magnitude: float
    entity_names: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "forward_proposal_id": self.forward_proposal_id,
            "reverse_proposal_id": self.reverse_proposal_id,
            "forward_template_id": self.forward_template_id,
            "reverse_template_id": self.reverse_template_id,
            "forward_stub": self.forward_stub,
            "reverse_stub": self.reverse_stub,
            "magnitude": self.magnitude,
            "entity_names": dict(self.entity_names),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OrreryJointBeat":
        return cls(
            kind=str(data["kind"]),
            entity_a=int(data["entity_a"]),
            entity_b=int(data["entity_b"]),
            forward_proposal_id=str(data["forward_proposal_id"]),
            reverse_proposal_id=str(data["reverse_proposal_id"]),
            forward_template_id=str(data["forward_template_id"]),
            reverse_template_id=str(data["reverse_template_id"]),
            forward_stub=str(data["forward_stub"]),
            reverse_stub=str(data["reverse_stub"]),
            magnitude=float(data["magnitude"]),
            entity_names=dict(data.get("entity_names") or {}),
        )


def _pair_key(item: Any) -> Optional[Tuple[int, int]]:
    bindings = getattr(item, "bindings", None) or {}
    actor = bindings.get("actor")
    target = bindings.get("target")
    if isinstance(actor, int) and isinstance(target, int):
        return actor, target
    return None


def detect_joint_beats(
    resolutions: Iterable[Any],
    entity_names: Optional[Mapping[Any, str]] = None,
) -> Tuple[OrreryJointBeat, ...]:
    """Compose joint beats from a tick's two-party resolution drafts.

    Accepts anything draft-shaped (``bindings`` with int actor/target,
    ``template_id``, ``binding_hash``, ``branch stub`` fields, ``magnitude``)
    so both the production proposal and the audit layer's stack winners can
    feed it. Deterministic: pairs are keyed on the unordered entity pair,
    with the forward direction being the lower entity id's draft.
    """

    by_direction: dict[Tuple[int, int], Any] = {}
    for item in resolutions:
        key = _pair_key(item)
        if key is not None:
            # Winner-take-all means at most one two-party draft per ordered
            # pair; keep the first defensively if that invariant ever bends.
            by_direction.setdefault(key, item)

    names = entity_names or {}
    beats: list[OrreryJointBeat] = []
    for (actor, target), forward in sorted(by_direction.items()):
        if actor > target:
            continue  # handled from the lower-id side
        reverse = by_direction.get((target, actor))
        if reverse is None:
            continue
        forward_template = str(forward.template_id)
        reverse_template = str(reverse.template_id)
        beats.append(
            OrreryJointBeat(
                kind=(
                    "reciprocal" if forward_template == reverse_template else "crossed"
                ),
                entity_a=actor,
                entity_b=target,
                forward_proposal_id=(f"{forward_template}:{forward.binding_hash}"),
                reverse_proposal_id=(f"{reverse_template}:{reverse.binding_hash}"),
                forward_template_id=forward_template,
                reverse_template_id=reverse_template,
                forward_stub=str(getattr(forward, "narrative_stub", "") or ""),
                reverse_stub=str(getattr(reverse, "narrative_stub", "") or ""),
                magnitude=max(
                    float(getattr(forward, "magnitude", 0.0) or 0.0),
                    float(getattr(reverse, "magnitude", 0.0) or 0.0),
                ),
                entity_names={
                    str(actor): str(names.get(actor, f"entity {actor}")),
                    str(target): str(names.get(target, f"entity {target}")),
                },
            )
        )
    return tuple(beats)


def coerce_joint_beats(value: Any) -> Tuple[OrreryJointBeat, ...]:
    """Hydrate joint beats from serialized proposal data (tolerant of
    pre-beat payloads: missing/None means no beats)."""

    if not value:
        return ()
    if isinstance(value, Sequence):
        return tuple(
            (
                item
                if isinstance(item, OrreryJointBeat)
                else OrreryJointBeat.from_dict(item)
            )
            for item in value
        )
    raise ValueError(f"Unsupported joint-beat payload: {type(value)!r}")
