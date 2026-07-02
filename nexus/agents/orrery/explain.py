"""Explainable evaluation for Orrery behavior packages.

This module mirrors :func:`evaluate` / :func:`evaluate_stack` from
:mod:`nexus.agents.orrery.substrate`, but instead of returning only the winning
branch it records *why* a package gate passed or failed and which branch was
selected. It exists to back the developer audit dashboard; the production
resolver hot path in ``substrate``/``resolver`` is deliberately left untouched.

Design notes
------------
* **No short-circuit.** Condition trees are walked exhaustively so that every
  clause's truth value is recorded, even ones a real ``AND``/``OR`` would skip.
  The authoritative gate/branch outcome is still taken from a real call to the
  condition object, and each :func:`explain_template` cross-checks its trace
  against :func:`evaluate` — a divergence means a predicate is non-deterministic
  or has a side effect, and is raised loudly rather than hidden.
* **Catalog-consistent labels.** Leaf predicates are rendered through the same
  ``_render_predicate_name`` the catalog uses, so trace prose matches
  ``docs/orrery_packages.md`` verbatim.
* **Whole-stack output.** :func:`explain_stack` returns an explanation for every
  template (priority-ordered, winner flagged), so the dashboard can show the
  winner *and* the shadowed packages that would also have fired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Mapping, Optional, Tuple

from nexus.agents.orrery.catalog import _render_predicate_name
from nexus.agents.orrery.evidence import resolve_evidence
from nexus.agents.orrery.substrate import (
    Bindings,
    CompoundCondition,
    Condition,
    Resolution,
    Slot,
    Template,
    WorldState,
    evaluate,
)


@dataclass(frozen=True, slots=True)
class ConditionTrace:
    """One node in an evaluated condition tree.

    ``op`` is ``None`` for leaf predicates and one of ``AND``/``OR``/``NOT`` for
    compound nodes. ``raw`` is the substrate ``__name__``; ``prose`` is the
    catalog-rendered, human-readable form.
    """

    raw: str
    prose: str
    result: bool
    op: Optional[str] = None
    children: Tuple["ConditionTrace", ...] = ()
    evidence: Optional[Mapping[str, Any]] = None

    @property
    def is_leaf(self) -> bool:
        return self.op is None

    def to_dict(self) -> dict[str, Any]:
        node: dict[str, Any] = {
            "raw": self.raw,
            "prose": self.prose,
            "result": self.result,
        }
        if self.op is not None:
            node["op"] = self.op
            node["children"] = [child.to_dict() for child in self.children]
        else:
            node["evidence"] = (
                dict(self.evidence) if self.evidence is not None else None
            )
        return node


@dataclass(frozen=True, slots=True)
class BranchTrace:
    """How one branch fared during selection.

    ``considered`` is ``False`` for branches that sit after the selected branch:
    the resolver never reaches them, so their conditions are not evaluated.
    """

    label: str
    magnitude: float
    considered: bool
    result: bool
    selected: bool
    trace: Optional[ConditionTrace] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "magnitude": self.magnitude,
            "considered": self.considered,
            "result": self.result,
            "selected": self.selected,
            "trace": self.trace.to_dict() if self.trace is not None else None,
        }


@dataclass(frozen=True, slots=True)
class TemplateExplanation:
    """Full audit record for one template against one binding set."""

    template_id: str
    priority: int
    drive_band: str
    blurb: str
    required_slots: Tuple[str, ...]
    present_target_policy: str
    gate_passed: bool
    gate_trace: ConditionTrace
    fired: bool
    chosen_branch: Optional[str]
    branches: Tuple[BranchTrace, ...]
    magnitude: float
    event_type: Optional[str]
    narrative_stub: Optional[str]
    binding_hash: str
    state_delta: Mapping[str, Any] = field(default_factory=dict)
    changed_fields: Tuple[str, ...] = ()
    scene_pressure_stub: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        # Payload hygiene: a non-fired template's magnitude/event_type are
        # Resolution defaults (0.0 / None), not observations — null them so a
        # consumer can't render them as meaningful.
        return {
            "template_id": self.template_id,
            "priority": self.priority,
            "drive_band": self.drive_band,
            "blurb": self.blurb,
            "required_slots": list(self.required_slots),
            "present_target_policy": self.present_target_policy,
            "gate_passed": self.gate_passed,
            "gate_trace": self.gate_trace.to_dict(),
            "fired": self.fired,
            "chosen_branch": self.chosen_branch,
            "branches": [branch.to_dict() for branch in self.branches],
            "magnitude": self.magnitude if self.fired else None,
            "event_type": self.event_type if self.fired else None,
            "narrative_stub": self.narrative_stub,
            "binding_hash": self.binding_hash,
            "state_delta": dict(self.state_delta),
            "changed_fields": list(self.changed_fields),
            "scene_pressure_stub": self.scene_pressure_stub,
        }


@dataclass(frozen=True, slots=True)
class StackExplanation:
    """Priority-ordered explanations for an entire template stack."""

    bindings: Mapping[str, Any]
    winner_id: Optional[str]
    templates: Tuple[TemplateExplanation, ...]

    @property
    def shadowed_ids(self) -> Tuple[str, ...]:
        """Templates that fired but lost the stack to a higher-priority winner."""

        return tuple(
            item.template_id
            for item in self.templates
            if item.fired and item.template_id != self.winner_id
        )

    def to_dict(self) -> dict[str, Any]:
        shadowed = set(self.shadowed_ids)
        templates: List[dict[str, Any]] = []
        for item in self.templates:
            payload = item.to_dict()
            payload["is_winner"] = item.template_id == self.winner_id
            payload["is_shadowed"] = item.template_id in shadowed
            templates.append(payload)
        return {
            "bindings": dict(self.bindings),
            "winner_id": self.winner_id,
            "shadowed_ids": list(self.shadowed_ids),
            "templates": templates,
        }


def trace_condition(
    condition: Condition, state: WorldState, bindings: Bindings
) -> ConditionTrace:
    """Walk a condition tree exhaustively, recording each node's truth value."""

    if isinstance(condition, CompoundCondition):
        children = tuple(
            trace_condition(child, state, bindings) for child in condition.children
        )
        if condition.op == "AND":
            result = all(child.result for child in children)
        elif condition.op == "OR":
            result = any(child.result for child in children)
        elif condition.op == "NOT":
            result = not children[0].result
        else:  # pragma: no cover - guarded by CompoundCondition.__call__
            raise ValueError(f"Unknown compound op: {condition.op}")
        return ConditionTrace(
            raw=condition.__name__,
            prose=condition.op.lower(),
            result=result,
            op=condition.op,
            children=children,
        )

    name = getattr(condition, "__name__", repr(condition))
    result = bool(condition(state, bindings))
    evidence = resolve_evidence(name, state, bindings)
    # Evidence recomputes its own verdict from the parsed name; a mismatch
    # means the factory closure and the evidence resolver have drifted.
    # evidence["result"] is None only for name-unrecoverable filters
    # (recent_event's changed_fields marker), where no cross-check is possible.
    if evidence["result"] is not None and bool(evidence["result"]) != result:
        raise AssertionError(
            f"evidence/predicate divergence for {name!r}: predicate returned "
            f"{result}, evidence recomputed {evidence['result']}"
        )
    return ConditionTrace(
        raw=name,
        prose=_render_predicate_name(name),
        result=result,
        evidence=evidence,
    )


def explain_template(
    template: Template, state: WorldState, bindings: Bindings
) -> TemplateExplanation:
    """Produce a full audit record for one template against one binding set."""

    gate_trace = trace_condition(template.package_gate, state, bindings)
    gate_passed = bool(template.package_gate(state, bindings))

    branch_traces: List[BranchTrace] = []
    chosen_branch: Optional[str] = None
    if gate_passed:
        decided = False
        for branch in template.branches:
            if decided:
                branch_traces.append(
                    BranchTrace(
                        label=branch.label,
                        magnitude=branch.magnitude,
                        considered=False,
                        result=False,
                        selected=False,
                        trace=None,
                    )
                )
                continue
            branch_trace = trace_condition(branch.conditions, state, bindings)
            passes = bool(branch.conditions(state, bindings))
            branch_traces.append(
                BranchTrace(
                    label=branch.label,
                    magnitude=branch.magnitude,
                    considered=True,
                    result=passes,
                    selected=passes,
                    trace=branch_trace,
                )
            )
            if passes:
                chosen_branch = branch.label
                decided = True

    # Source-of-truth cross-check against the production resolver. Any mismatch
    # means a predicate is non-deterministic or side-effecting; surface it.
    truth: Resolution = evaluate(template, state, bindings)
    if (
        truth.passes != (chosen_branch is not None)
        or truth.branch_label != chosen_branch
    ):
        raise AssertionError(
            f"explain/evaluate divergence for {template.id!r}: "
            f"explain chose {chosen_branch!r}, evaluate chose "
            f"{truth.branch_label!r} (passes={truth.passes})"
        )

    return TemplateExplanation(
        template_id=template.id,
        priority=template.priority,
        drive_band=template.drive_band.value,
        blurb=template.blurb,
        required_slots=tuple(slot.value for slot in template.required_slots),
        present_target_policy=template.present_target_policy.value,
        gate_passed=gate_passed,
        gate_trace=gate_trace,
        fired=truth.passes,
        chosen_branch=chosen_branch,
        branches=tuple(branch_traces),
        magnitude=truth.magnitude,
        event_type=truth.event_type,
        narrative_stub=truth.narrative_stub,
        binding_hash=truth.binding_hash,
        state_delta=dict(truth.state_delta),
        changed_fields=truth.changed_fields,
        scene_pressure_stub=truth.scene_pressure_stub,
    )


def explain_stack(
    templates: Iterable[Template], state: WorldState, bindings: Bindings
) -> StackExplanation:
    """Explain every template in priority order and flag the stack winner.

    Mirrors :func:`evaluate_stack` selection (highest priority firing template
    wins) while retaining the full audit record for every template, so the
    dashboard can render the winner alongside the shadowed packages.
    """

    ordered = sorted(templates, key=lambda item: item.priority, reverse=True)
    explanations = tuple(
        explain_template(template, state, bindings) for template in ordered
    )
    winner_id = next((item.template_id for item in explanations if item.fired), None)
    serialized_bindings = {
        slot.value if isinstance(slot, Slot) else str(slot): value
        for slot, value in bindings.items()
    }
    return StackExplanation(
        bindings=serialized_bindings,
        winner_id=winner_id,
        templates=explanations,
    )
