"""Slot-backed explained resolution for the Orrery audit dashboard.

This module is the read-only bridge between the explain layer
(:mod:`nexus.agents.orrery.explain`) and real slot databases. It mirrors
:func:`nexus.agents.orrery.resolver.resolve_dry_run` **exactly** — the same
hydration, the same actor-only / two-party stack split, the same binding
composition (including source-aware routing through
``compose_actor_target_routes``), and the same present-target pressure pass —
but runs :func:`explain_stack` per binding set so every template's gate and
branch trace is retained, not just the winner.

The stack-split fidelity matters: tracing a two-party template with only
``ACTOR`` bound would make every ``@target`` leaf read ``None`` and report
``False``, rendering "not applicable, no target bound" indistinguishable from a
genuine gate failure. Here two-party templates are only ever explained against
composed (actor, target) bindings; an actor with no composed pair gets an
explicit not-applicable marker instead (scoped to the off-screen two-party
stack — the present-target pressure pass depends on scene composition, not on
a per-actor binding decision).

What-if mode: :func:`explain_dry_run` optionally takes a
:class:`~nexus.agents.orrery.overrides.WorldStateOverrides` set. Hydration and
binding composition run once (SQL); the tick is then explained twice — against
the hydrated state and against a copy with the overrides applied — and every
sandbox stack carries a compact diff against its baseline twin. Overrides edit
world state only: the actor roster and pair composition come from SQL, so the
payload's override echo carries the ``world_state_only`` scope marker.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text

from nexus.agents.orrery.communication import (
    CommunicationGraph,
    communication_graph_for_settings,
)
from nexus.agents.orrery.epistemics import (
    CLAIM_SCOPES,
    SOURCE_TIERS,
    coerce_epistemics_policy,
    load_epistemics_policy,
)
from nexus.agents.orrery.explain import StackExplanation, explain_stack
from nexus.agents.orrery.reciprocal import OrreryJointBeat, detect_joint_beats
from nexus.agents.orrery.overrides import (
    OverrideValidationError,
    WorldStateOverrides,
    apply_overrides,
)
from nexus.agents.orrery.needs import (
    NEED_SEVERITY_PREFIX,
    coerce_need_tuning,
    severity_for_debt,
)
from nexus.agents.orrery.resolver import (
    _LOCATION_CLASS_CATEGORY_SQL,
    OrreryScenePressureDraft,
    _apply_pair_fanout_quota,
    _arbitrate_project_starts,
    _coerce_fanout,
    _entity_label,
    _load_entity_names,
    _load_need_debt_scores,
    _load_routine_anchors,
    _load_travel_states,
    _load_world_time,
    _present_actor_ids_at_anchor,
    _present_need_pressure_specs,
    _render_bound_text,
    _scene_pressure_from_need_spec,
    compose_actor_bindings,
    compose_actor_faction_routes,
    compose_actor_target_faction_routes,
    compose_actor_target_routes,
    hydrate_world_state,
)
from nexus.agents.orrery.substrate import (
    Bindings,
    coerce_branch_selection,
    coerce_habituation,
    coerce_package_selection,
    coerce_project_policy,
    configure_project_magnitudes,
    CONSTRAINED_TAGS,
    DRAMATIC_CONTACT_TAGS,
    DRIVE_BAND_ORDER,
    ESTABLISHED_PARTNER_RELATIONSHIP_TYPES,
    HIDDEN_TAGS,
    INTIMACY_SUPPRESSOR_TAGS,
    PUBLIC_MOBILITY_TAGS,
    PUBLIC_PLACE_CLASSES,
    PresentTargetPolicy,
    Slot,
    Template,
    _condition_tree_leaves,
    drive_band_priority_warnings,
)

_ACTOR_ONLY_SLOTS: Tuple[Slot, ...] = (Slot.ACTOR,)
_ACTOR_TARGET_SLOTS: Tuple[Slot, ...] = (Slot.ACTOR, Slot.TARGET)
_ACTOR_FACTION_SLOTS: Tuple[Slot, ...] = (Slot.ACTOR, Slot.FACTION)
_ACTOR_TARGET_FACTION_SLOTS: Tuple[Slot, ...] = (
    Slot.ACTOR,
    Slot.TARGET,
    Slot.FACTION,
)

NOT_APPLICABLE_REASON = "no_target_bound"


@dataclass(frozen=True, slots=True)
class ActorGroupExplanation:
    """All explained stacks for one off-screen actor in one tick.

    In what-if mode the ``*_diff`` fields align positionally with their stack
    fields (same binding composition on both sides of the diff); in current
    mode they stay ``None``/empty.
    """

    actor_entity_id: int
    actor_stack: StackExplanation
    two_party_stacks: Tuple[StackExplanation, ...] = ()
    scene_pressure_stacks: Tuple[StackExplanation, ...] = ()
    not_applicable: Tuple[Mapping[str, Any], ...] = ()
    actor_stack_diff: Optional[Mapping[str, Any]] = None
    two_party_stack_diffs: Tuple[Optional[Mapping[str, Any]], ...] = ()
    scene_pressure_stack_diffs: Tuple[Optional[Mapping[str, Any]], ...] = ()


@dataclass(frozen=True, slots=True)
class ExplainedTickReport:
    """Full audit record for one dry-run tick against a real slot."""

    anchor_chunk_id: Optional[int]
    window_chunks: int
    world_time: Optional[datetime]
    time_of_day: str
    weather: Optional[str]
    actor_count: int
    actors: Tuple[ActorGroupExplanation, ...]
    need_pressures: Tuple[OrreryScenePressureDraft, ...]
    entity_names: Mapping[int, str]
    locations: Mapping[int, Any]
    location_names: Mapping[int, str]
    activities: Mapping[int, str]
    communication_graph: CommunicationGraph
    joint_beats: Tuple[OrreryJointBeat, ...] = ()
    fanout_trimmed: Tuple[Mapping[str, Any], ...] = ()
    project_start_arbitration_trimmed: Tuple[Mapping[str, Any], ...] = ()
    mode: str = "current"
    overrides: Optional[Mapping[str, Any]] = None
    need_pressures_diff: Optional[Mapping[str, Any]] = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_chunk_id": self.anchor_chunk_id,
            "window_chunks": self.window_chunks,
            "world_time": (
                self.world_time.isoformat() if self.world_time is not None else None
            ),
            "time_of_day": self.time_of_day,
            "weather": self.weather,
            "actor_count": self.actor_count,
            "mode": self.mode,
            "overrides": dict(self.overrides) if self.overrides is not None else None,
            "generated_at": self.generated_at,
            "actors": [self._group_payload(group) for group in self.actors],
            "joint_beats": [beat.to_dict() for beat in self.joint_beats],
            "fanout_trimmed": [dict(item) for item in self.fanout_trimmed],
            "project_start_arbitration_trimmed": [
                dict(item) for item in self.project_start_arbitration_trimmed
            ],
            "need_pressures": [draft.to_dict() for draft in self.need_pressures],
            "need_pressures_diff": (
                dict(self.need_pressures_diff)
                if self.need_pressures_diff is not None
                else None
            ),
            "entity_names": {
                str(entity_id): name for entity_id, name in self.entity_names.items()
            },
        }

    def _group_payload(self, group: ActorGroupExplanation) -> dict[str, Any]:
        actor_id = group.actor_entity_id
        place_id = self.locations.get(actor_id)
        location: Optional[dict[str, Any]] = None
        if place_id is not None:
            location = {
                "place_id": place_id,
                "name": self.location_names.get(place_id),
            }
        two_party_diffs: Tuple[Optional[Mapping[str, Any]], ...] = (
            group.two_party_stack_diffs or (None,) * len(group.two_party_stacks)
        )
        pressure_diffs: Tuple[Optional[Mapping[str, Any]], ...] = (
            group.scene_pressure_stack_diffs
            or (None,) * len(group.scene_pressure_stacks)
        )
        return {
            "actor_entity_id": actor_id,
            "actor_name": _entity_label(actor_id, self.entity_names),
            "location": location,
            "activity": self.activities.get(actor_id),
            "communication_edges": [
                edge.to_dict() for edge in self.communication_graph.outbound(actor_id)
            ],
            "actor_stack": self._stack_payload(
                group.actor_stack, group.actor_stack_diff
            ),
            "two_party_stacks": [
                self._stack_payload(stack, diff)
                for stack, diff in zip(group.two_party_stacks, two_party_diffs)
            ],
            "scene_pressure_stacks": [
                self._stack_payload(stack, diff)
                for stack, diff in zip(group.scene_pressure_stacks, pressure_diffs)
            ],
            "not_applicable": [dict(item) for item in group.not_applicable],
        }

    def _stack_payload(
        self, stack: StackExplanation, diff: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        payload = stack.to_dict()
        payload["diff"] = dict(diff) if diff is not None else None
        payload["binding_names"] = {
            slot: _entity_label(value, self.entity_names)
            for slot, value in stack.bindings.items()
        }
        for item in payload["templates"]:
            stub = item["narrative_stub"] if item["fired"] else None
            item["narrative_stub_rendered"] = (
                _render_bound_text(
                    stub,
                    stack.bindings,
                    self.entity_names,
                    template_id=item["template_id"],
                )
                if stub
                else None
            )
            pressure_stub = item["scene_pressure_stub"] if item["fired"] else None
            item["scene_pressure_prompt_rendered"] = (
                _render_bound_text(
                    pressure_stub,
                    stack.bindings,
                    self.entity_names,
                    template_id=item["template_id"],
                )
                if pressure_stub
                else None
            )
        return payload


@dataclass(frozen=True, slots=True)
class _TickStacks:
    """One state's explained stacks — the unit the what-if diff compares."""

    actor_stacks: Mapping[int, StackExplanation]
    two_party_stacks: Mapping[int, List[StackExplanation]]
    pressure_stacks: Mapping[int, List[StackExplanation]]
    need_pressure_specs: Sequence[Mapping[str, Any]]


def _stack_diff(
    baseline: StackExplanation, sandbox: StackExplanation
) -> dict[str, Any]:
    """Compact outcome diff between the same stack under two states.

    ``changed`` tracks the *card-level* outcome (winner or its branch);
    ``changed_template_ids`` tracks every template whose fired flag or chosen
    branch moved, so shadowed/ghost rows can carry diff markers too.
    """

    if dict(baseline.bindings) != dict(sandbox.bindings):
        raise AssertionError(
            "what-if diff misalignment: baseline and sandbox stacks carry "
            f"different bindings ({dict(baseline.bindings)} vs "
            f"{dict(sandbox.bindings)})"
        )
    baseline_by_id = {item.template_id: item for item in baseline.templates}
    changed_template_ids = [
        item.template_id
        for item in sandbox.templates
        if baseline_by_id[item.template_id].fired != item.fired
        or baseline_by_id[item.template_id].chosen_branch != item.chosen_branch
    ]
    baseline_winner = (
        baseline_by_id[baseline.winner_id] if baseline.winner_id is not None else None
    )
    sandbox_winner = next(
        (item for item in sandbox.templates if item.template_id == sandbox.winner_id),
        None,
    )
    changed = baseline.winner_id != sandbox.winner_id or (
        baseline_winner is not None
        and sandbox_winner is not None
        and baseline_winner.chosen_branch != sandbox_winner.chosen_branch
    )
    return {
        "changed": changed,
        "baseline_winner_id": baseline.winner_id,
        "baseline_chosen_branch": (
            baseline_winner.chosen_branch if baseline_winner is not None else None
        ),
        "baseline_magnitude": (
            baseline_winner.magnitude
            if baseline_winner is not None and baseline_winner.fired
            else None
        ),
        "changed_template_ids": changed_template_ids,
    }


def _need_pressure_diff(
    baseline: Tuple[OrreryScenePressureDraft, ...],
    sandbox: Tuple[OrreryScenePressureDraft, ...],
) -> dict[str, Any]:
    """Added/removed/changed need pressures keyed by (template, binding)."""

    def _key(draft: OrreryScenePressureDraft) -> Tuple[str, str]:
        return (draft.template_id, draft.binding_hash)

    baseline_by_key = {_key(draft): draft for draft in baseline}
    sandbox_by_key = {_key(draft): draft for draft in sandbox}
    added = sorted(sandbox_by_key.keys() - baseline_by_key.keys())
    removed = sorted(baseline_by_key.keys() - sandbox_by_key.keys())
    changed = [
        {
            "current": sandbox_by_key[key].to_dict(),
            "baseline": baseline_by_key[key].to_dict(),
        }
        for key in sorted(sandbox_by_key.keys() & baseline_by_key.keys())
        if sandbox_by_key[key].to_dict() != baseline_by_key[key].to_dict()
    ]
    return {
        "added": [sandbox_by_key[key].to_dict() for key in added],
        "removed": [baseline_by_key[key].to_dict() for key in removed],
        "changed": changed,
    }


def _override_entity_ids(overrides: WorldStateOverrides) -> set[int]:
    """Every entity id an override set references, for validation and naming."""

    entity_ids: set[int] = set()
    for tag_override in overrides.tags:
        entity_ids.add(tag_override.entity_id)
    for pair_override in overrides.pair_tags:
        entity_ids.add(pair_override.subject_entity_id)
        entity_ids.add(pair_override.object_entity_id)
    for need_override in overrides.needs:
        entity_ids.add(need_override.entity_id)
    for location_override in overrides.locations:
        entity_ids.add(location_override.entity_id)
    for event_override in overrides.events:
        for value in (
            event_override.actor_entity_id,
            event_override.target_entity_id,
        ):
            if value is not None:
                entity_ids.add(value)
    return entity_ids


def _validate_overrides(session: Any, overrides: WorldStateOverrides) -> None:
    """Validate an override set against the slot's live vocabularies.

    State-independent checks only — the state-dependent toggle checks (add an
    already-present tag, remove an absent one) live in ``apply_overrides``.
    Raises ``ValueError`` with a message naming every offending value.
    """

    entity_ids = _override_entity_ids(overrides)
    if entity_ids:
        known_entities = set(
            session.execute(
                text(
                    """
                    /* orrery_audit:override_entities */
                    SELECT id FROM entities WHERE id = ANY(:ids)
                    """
                ),
                {"ids": sorted(entity_ids)},
            ).scalars()
        )
        missing_entities = entity_ids - known_entities
        if missing_entities:
            raise OverrideValidationError(
                "Override references unknown entity ids: " f"{sorted(missing_entities)}"
            )

    if overrides.tags:
        requested = {item.tag for item in overrides.tags}
        vocab = {
            row["tag"]: row["is_ephemeral"]
            for row in session.execute(
                text(
                    """
                    /* orrery_audit:override_tag_vocab */
                    SELECT tag, is_ephemeral FROM tags
                    WHERE tag = ANY(:tags) AND NOT deprecated
                    """
                ),
                {"tags": sorted(requested)},
            ).mappings()
        }
        unknown_tags = requested - vocab.keys()
        if unknown_tags:
            raise OverrideValidationError(
                f"Override references unknown or deprecated tags: "
                f"{sorted(unknown_tags)}"
            )
        for item in overrides.tags:
            if vocab[item.tag] != item.ephemeral:
                actual = "ephemeral" if vocab[item.tag] else "durable"
                requested_layer = "ephemeral" if item.ephemeral else "durable"
                raise OverrideValidationError(
                    f"Tag {item.tag!r} is {actual} in the vocabulary but the "
                    f"override targets the {requested_layer} layer — predicates "
                    "read the two layers separately, so the override would "
                    "fabricate unreachable state"
                )

    if overrides.pair_tags:
        requested = {item.tag for item in overrides.pair_tags}
        known_pair_tags = set(
            session.execute(
                text(
                    """
                    /* orrery_audit:override_pair_tag_vocab */
                    SELECT tag FROM pair_tags
                    WHERE tag = ANY(:tags) AND NOT deprecated
                    """
                ),
                {"tags": sorted(requested)},
            ).scalars()
        )
        unknown_pair_tags = requested - known_pair_tags
        if unknown_pair_tags:
            raise OverrideValidationError(
                f"Override references unknown or deprecated pair tags: "
                f"{sorted(unknown_pair_tags)}"
            )

    if overrides.events:
        requested = {item.event_type for item in overrides.events}
        known_events = set(
            session.execute(
                text(
                    """
                    /* orrery_audit:override_event_vocab */
                    SELECT type FROM event_types
                    WHERE type = ANY(:types) AND NOT deprecated
                    """
                ),
                {"types": sorted(requested)},
            ).scalars()
        )
        unknown_events = requested - known_events
        if unknown_events:
            raise OverrideValidationError(
                f"Override references unknown or deprecated event types: "
                f"{sorted(unknown_events)}"
            )

    place_ids = {item.place_id for item in overrides.locations} | {
        item.location_id for item in overrides.events if item.location_id is not None
    }
    if place_ids:
        known_places = set(
            session.execute(
                text(
                    """
                    /* orrery_audit:override_places */
                    SELECT id FROM places WHERE id = ANY(:ids)
                    """
                ),
                {"ids": sorted(place_ids)},
            ).scalars()
        )
        missing_places = place_ids - known_places
        if missing_places:
            raise OverrideValidationError(
                f"Override references unknown place ids: {sorted(missing_places)}"
            )


def explain_dry_run(
    session: Any,
    templates: Iterable[Template],
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
    sunhelm_settings: Optional[Any] = None,
    world_time_override: Optional[datetime] = None,
    overrides: Optional[WorldStateOverrides] = None,
    selection_settings: Optional[Any] = None,
    habituation_settings: Optional[Any] = None,
    package_selection_settings: Optional[Any] = None,
    project_settings: Optional[Any] = None,
    epistemics_settings: Optional[Any] = None,
    fanout_settings: Optional[Any] = None,
    contagion_settings: Optional[Any] = None,
    weather_settings: Optional[Any] = None,
    mood_settings: Optional[Any] = None,
    composition_settings: Optional[Any] = None,
) -> ExplainedTickReport:
    """Hydrate, bind, and explain Orrery packages without database writes.

    Every step below has a line-for-line counterpart in ``resolve_dry_run``;
    keep them in lockstep. Winner/branch parity with production is enforced
    per template by ``explain_template``'s cross-check against ``evaluate``.

    With a non-empty ``overrides`` set the report switches to what-if mode:
    hydration and binding composition still run once, the overrides are
    validated against the slot's vocabularies and applied to a copy of the
    state, and both the baseline and sandbox states are explained so each
    sandbox stack carries a diff against its baseline twin.
    """

    need_tuning = coerce_need_tuning(sunhelm_settings)
    selection = coerce_branch_selection(selection_settings)
    habituation = coerce_habituation(habituation_settings)
    package_selection = coerce_package_selection(package_selection_settings)
    project_policy = coerce_project_policy(project_settings)
    epistemics_policy = (
        load_epistemics_policy()
        if epistemics_settings is None
        else coerce_epistemics_policy(epistemics_settings)
    )
    state = hydrate_world_state(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
        need_tuning=need_tuning,
        world_time_override=world_time_override,
        win_history_window=habituation.window_ticks if habituation.enabled else 0,
        project_settings=project_settings,
        epistemics_settings=epistemics_policy,
        contagion_settings=contagion_settings,
        weather_settings=weather_settings,
        mood_settings=mood_settings,
    )

    templates_list = list(configure_project_magnitudes(templates, project_policy))
    actor_only_templates = [
        t for t in templates_list if t.required_slots == _ACTOR_ONLY_SLOTS
    ]
    actor_target_templates = [
        t for t in templates_list if t.required_slots == _ACTOR_TARGET_SLOTS
    ]
    actor_faction_templates = [
        t for t in templates_list if t.required_slots == _ACTOR_FACTION_SLOTS
    ]
    actor_target_faction_templates = [
        t for t in templates_list if t.required_slots == _ACTOR_TARGET_FACTION_SLOTS
    ]
    supported_slot_signatures = (
        _ACTOR_ONLY_SLOTS,
        _ACTOR_TARGET_SLOTS,
        _ACTOR_FACTION_SLOTS,
        _ACTOR_TARGET_FACTION_SLOTS,
    )
    unsupported = [
        t for t in templates_list if t.required_slots not in supported_slot_signatures
    ]
    if unsupported:
        raise ValueError(
            "Orrery audit resolver does not yet compose bindings for "
            "required_slots="
            + ", ".join(
                f"{t.id}:{tuple(s.value for s in t.required_slots)}"
                for t in unsupported
            )
        )

    actor_bindings = compose_actor_bindings(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
    )
    actor_ids = {bindings[Slot.ACTOR] for bindings in actor_bindings}

    pressure_templates = [
        template
        for template in actor_target_templates
        if template.present_target_policy is PresentTargetPolicy.STORYTELLER_PRESSURE
    ]
    offscreen_pair_routes: Tuple[Tuple[Bindings, Tuple[Template, ...]], ...] = ()
    present_pair_routes: Tuple[Tuple[Bindings, Tuple[Template, ...]], ...] = ()
    if actor_target_templates:
        offscreen_pair_routes = compose_actor_target_routes(
            session,
            state=state,
            templates=actor_target_templates,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            actor_ids=actor_ids,
            target_presence="offscreen",
            composition_settings=composition_settings,
        )
        if pressure_templates:
            present_pair_routes = compose_actor_target_routes(
                session,
                state=state,
                templates=pressure_templates,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=window_chunks,
                actor_ids=actor_ids,
                target_presence="present",
                composition_settings=composition_settings,
            )

    if actor_faction_templates:
        offscreen_pair_routes += compose_actor_faction_routes(
            session,
            state=state,
            templates=actor_faction_templates,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            actor_ids=actor_ids,
            composition_settings=composition_settings,
        )

    if actor_target_faction_templates:
        offscreen_pair_routes += compose_actor_target_faction_routes(
            session,
            state=state,
            templates=actor_target_faction_templates,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            actor_ids=actor_ids,
            target_presence="offscreen",
            composition_settings=composition_settings,
        )
        triple_pressure_templates = [
            template
            for template in actor_target_faction_templates
            if template.present_target_policy
            is PresentTargetPolicy.STORYTELLER_PRESSURE
        ]
        if triple_pressure_templates:
            present_pair_routes += compose_actor_target_faction_routes(
                session,
                state=state,
                templates=triple_pressure_templates,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=window_chunks,
                actor_ids=actor_ids,
                target_presence="present",
                composition_settings=composition_settings,
            )

    present_actor_ids = _present_actor_ids_at_anchor(
        session, anchor_chunk_id=anchor_chunk_id
    )

    def _explain_tick(tick_state: Any) -> _TickStacks:
        """Explain every composed binding set against one state snapshot."""

        actor_stacks: dict[int, StackExplanation] = {}
        for bindings in actor_bindings:
            actor_stacks[bindings[Slot.ACTOR]] = explain_stack(
                actor_only_templates,
                tick_state,
                bindings,
                selection,
                habituation,
                package_selection,
            )
        two_party_stacks: dict[int, List[StackExplanation]] = {}
        for pair_bindings, routed_templates in offscreen_pair_routes:
            two_party_stacks.setdefault(pair_bindings[Slot.ACTOR], []).append(
                explain_stack(
                    routed_templates,
                    tick_state,
                    pair_bindings,
                    selection,
                    habituation,
                    package_selection,
                )
            )
        pressure_stacks: dict[int, List[StackExplanation]] = {}
        for pair_bindings, routed_templates in present_pair_routes:
            pressure_stacks.setdefault(pair_bindings[Slot.ACTOR], []).append(
                explain_stack(
                    routed_templates,
                    tick_state,
                    pair_bindings,
                    selection,
                    habituation,
                    package_selection,
                )
            )
        need_pressure_specs = _present_need_pressure_specs(
            tick_state,
            present_actor_ids=present_actor_ids,
            need_tuning=need_tuning,
        )
        return _TickStacks(
            actor_stacks=actor_stacks,
            two_party_stacks=two_party_stacks,
            pressure_stacks=pressure_stacks,
            need_pressure_specs=need_pressure_specs,
        )

    baseline = _explain_tick(state)
    what_if = overrides is not None and not overrides.is_empty
    if what_if:
        assert overrides is not None  # narrowed by what_if
        _validate_overrides(session, overrides)
        active_state = apply_overrides(state, overrides)
        active = _explain_tick(active_state)
    else:
        active_state = state
        active = baseline

    entity_ids: set[int] = {
        spec["actor_entity_id"]
        for tick in (baseline, active)
        for spec in tick.need_pressure_specs
    }
    all_stacks: list[StackExplanation] = list(active.actor_stacks.values())
    for stacks in active.two_party_stacks.values():
        all_stacks.extend(stacks)
    for stacks in active.pressure_stacks.values():
        all_stacks.extend(stacks)
    for stack in all_stacks:
        for value in stack.bindings.values():
            if isinstance(value, int):
                entity_ids.add(value)
    if what_if:
        assert overrides is not None
        entity_ids |= _override_entity_ids(overrides)
    place_entity_ids = {
        active_state.location_entity_ids[place_id]
        for actor_id in actor_ids
        if (place_id := active_state.locations.get(actor_id)) is not None
        and place_id in active_state.location_entity_ids
    }
    entity_names = _load_entity_names(session, entity_ids | place_entity_ids)
    location_names = {
        place_id: entity_names[entity_id]
        for place_id, entity_id in active_state.location_entity_ids.items()
        if entity_id in entity_names
    }

    def _pressures(tick: _TickStacks) -> Tuple[OrreryScenePressureDraft, ...]:
        return tuple(
            _scene_pressure_from_need_spec(
                spec,
                entity_names,
                need_tuning=need_tuning,
            )
            for spec in tick.need_pressure_specs
        )

    need_pressures = _pressures(active)
    need_pressures_diff: Optional[dict[str, Any]] = None
    if what_if:
        need_pressures_diff = _need_pressure_diff(_pressures(baseline), need_pressures)

    class _WinnerShim:
        __slots__ = (
            "template_id",
            "binding_hash",
            "bindings",
            "magnitude",
            "narrative_stub",
        )

        def __init__(self, stack: StackExplanation, item: Any) -> None:
            self.template_id = item.template_id
            self.binding_hash = item.binding_hash
            self.bindings = dict(stack.bindings)
            self.magnitude = item.magnitude
            self.narrative_stub = item.narrative_stub

    joint_beat_inputs = [
        _WinnerShim(stack, item)
        for stacks in active.two_party_stacks.values()
        for stack in stacks
        if stack.winner_id is not None
        for item in stack.templates
        if item.template_id == stack.winner_id
    ]
    # Production applies the fan-out quota to the draft list BEFORE joint
    # beats; the audit path mirrors the trim for parity and reports what
    # was dropped instead of silently hiding it.
    fanout = _coerce_fanout(fanout_settings)
    kept_inputs = _apply_pair_fanout_quota(
        joint_beat_inputs,
        templates_list,
        max_pair_drafts_per_actor=fanout.max_pair_drafts_per_actor,
        exempt_bands=fanout.exempt_bands,
    )
    kept_ids = {id(shim) for shim in kept_inputs}
    fanout_trimmed = tuple(
        {
            "actor_entity_id": shim.bindings.get("actor"),
            "target_entity_id": shim.bindings.get("target"),
            "faction_entity_id": shim.bindings.get("faction"),
            "template_id": shim.template_id,
            "magnitude": shim.magnitude,
        }
        for shim in joint_beat_inputs
        if id(shim) not in kept_ids
    )
    # Production arbitrates project starts AFTER the fan-out quota
    # (resolver.resolve_dry_run: _apply_pair_fanout_quota then
    # _arbitrate_project_starts, then joint beats over the survivors).
    # Mirror both steps in that order and report what was dropped instead
    # of silently hiding it. Per-actor precedence is what matters: the
    # actor-only stack's winner precedes routed pair stacks, as it does in
    # production draft assembly.
    solo_winner_shims = [
        _WinnerShim(stack, item)
        for _actor_id, stack in sorted(active.actor_stacks.items())
        if stack.winner_id is not None
        for item in stack.templates
        if item.template_id == stack.winner_id
    ]
    arbitration_inputs = solo_winner_shims + kept_inputs
    arbitration_kept_ids = {
        id(shim)
        for shim in _arbitrate_project_starts(arbitration_inputs, templates_list)
    }
    project_start_arbitration_trimmed = tuple(
        {
            "actor_entity_id": shim.bindings.get("actor"),
            "target_entity_id": shim.bindings.get("target"),
            "faction_entity_id": shim.bindings.get("faction"),
            "template_id": shim.template_id,
        }
        for shim in arbitration_inputs
        if id(shim) not in arbitration_kept_ids
    )
    joint_beats = detect_joint_beats(
        [shim for shim in kept_inputs if id(shim) in arbitration_kept_ids],
        entity_names,
    )

    not_applicable_markers = tuple(
        {
            "template_id": template.id,
            "priority": template.priority,
            "drive_band": template.drive_band.value,
            "reason": NOT_APPLICABLE_REASON,
        }
        for template in (
            actor_target_templates
            + actor_faction_templates
            + actor_target_faction_templates
        )
    )

    def _group(actor_id: int) -> ActorGroupExplanation:
        two_party = tuple(active.two_party_stacks.get(actor_id, ()))
        pressures = tuple(active.pressure_stacks.get(actor_id, ()))
        actor_stack_diff: Optional[Mapping[str, Any]] = None
        two_party_diffs: Tuple[Optional[Mapping[str, Any]], ...] = ()
        pressure_diffs: Tuple[Optional[Mapping[str, Any]], ...] = ()
        if what_if:
            actor_stack_diff = _stack_diff(
                baseline.actor_stacks[actor_id], active.actor_stacks[actor_id]
            )
            two_party_diffs = tuple(
                _stack_diff(base_stack, sandbox_stack)
                for base_stack, sandbox_stack in zip(
                    baseline.two_party_stacks.get(actor_id, ()),
                    two_party,
                    strict=True,
                )
            )
            pressure_diffs = tuple(
                _stack_diff(base_stack, sandbox_stack)
                for base_stack, sandbox_stack in zip(
                    baseline.pressure_stacks.get(actor_id, ()),
                    pressures,
                    strict=True,
                )
            )
        return ActorGroupExplanation(
            actor_entity_id=actor_id,
            actor_stack=active.actor_stacks[actor_id],
            two_party_stacks=two_party,
            scene_pressure_stacks=pressures,
            not_applicable=(not_applicable_markers if not two_party else ()),
            actor_stack_diff=actor_stack_diff,
            two_party_stack_diffs=two_party_diffs,
            scene_pressure_stack_diffs=pressure_diffs,
        )

    groups = tuple(_group(actor_id) for actor_id in sorted(actor_ids))

    return ExplainedTickReport(
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
        world_time=active_state.world_time,
        time_of_day=active_state.time_of_day,
        weather=active_state.weather,
        actor_count=len(actor_ids),
        actors=groups,
        need_pressures=need_pressures,
        entity_names=entity_names,
        locations=dict(active_state.locations),
        location_names=location_names,
        activities=dict(active_state.activities),
        communication_graph=active_state.communication_graph,
        joint_beats=joint_beats,
        fanout_trimmed=fanout_trimmed,
        project_start_arbitration_trimmed=project_start_arbitration_trimmed,
        mode="what_if" if what_if else "current",
        overrides=overrides.to_dict() if what_if and overrides is not None else None,
        need_pressures_diff=need_pressures_diff,
    )


# ---------------------------------------------------------------------------
# Static catalog introspection
# ---------------------------------------------------------------------------

# Curated coupling families from substrate. `kind` says what vocabulary the
# members belong to, so consumers don't try to match relationship types or
# place classes against tag chips.
TAG_FAMILIES: Mapping[str, Mapping[str, Any]] = {
    "intimacy_suppressor_tags": {
        "kind": "tags",
        "members": INTIMACY_SUPPRESSOR_TAGS,
    },
    "hidden_tags": {"kind": "tags", "members": HIDDEN_TAGS},
    "dramatic_contact_tags": {"kind": "tags", "members": DRAMATIC_CONTACT_TAGS},
    "constrained_tags": {"kind": "tags", "members": CONSTRAINED_TAGS},
    "public_mobility_tags": {"kind": "tags", "members": PUBLIC_MOBILITY_TAGS},
    "public_place_classes": {
        "kind": "place_classes",
        "members": PUBLIC_PLACE_CLASSES,
    },
    "established_partner_relationship_types": {
        "kind": "relationship_types",
        "members": ESTABLISHED_PARTNER_RELATIONSHIP_TYPES,
    },
}

_TAG_FAMILY_TAG_SETS: Mapping[str, frozenset[str]] = {
    name: spec["members"]
    for name, spec in TAG_FAMILIES.items()
    if spec["kind"] == "tags"
}

# Same event-consumption grammar the catalog's vocabulary collector matches
# against predicate __name__s (catalog._VOCAB_PATTERNS); the wildcard
# `recent_event(*)` form is deliberately excluded — it consumes no specific
# event type.
_EVENT_CONSUMER_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"recent_event\(([^,*()]+),"),
    re.compile(r"since_last_event_at_least\(([^,()]+),"),
)


def _consumed_event_types(condition: Any) -> set[str]:
    consumed: set[str] = set()
    for leaf in _condition_tree_leaves(condition):
        name = getattr(leaf, "__name__", "")
        for pattern in _EVENT_CONSUMER_PATTERNS:
            match = pattern.search(name)
            if match:
                consumed.add(match.group(1))
    return consumed


def build_catalog(
    templates: Iterable[Template],
    *,
    sunhelm_settings: Optional[Any] = None,
    promote_settings: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return the static template catalog payload for the audit dashboard.

    Pure introspection over the template tuple plus config-derived
    pseudo-template metadata; no database access. Tuple index is included
    because ``evaluate_stack``'s stable sort makes authored order the
    tie-breaker between equal priorities.
    """

    templates_tuple = tuple(templates)
    need_tuning = coerce_need_tuning(sunhelm_settings)

    template_payloads: list[dict[str, Any]] = []
    event_map: dict[str, dict[str, list[str]]] = {}

    def _event_entry(event_type: str) -> dict[str, list[str]]:
        return event_map.setdefault(
            event_type,
            {"consumed_by_gate": [], "consumed_by_branch": [], "emitted_by": []},
        )

    for tuple_index, template in enumerate(templates_tuple):
        gate_consumed = _consumed_event_types(template.package_gate)
        branch_consumed: set[str] = set()
        emitted: set[str] = set()
        branch_payloads: list[dict[str, Any]] = []
        for branch in template.branches:
            branch_consumed |= _consumed_event_types(branch.conditions)
            if branch.event_type:
                emitted.add(branch.event_type)
            if branch.signal_event_type:
                emitted.add(branch.signal_event_type)
            branch_payloads.append(
                {
                    "label": branch.label,
                    "magnitude": branch.magnitude,
                    "promotable": branch.promotable,
                    "event_type": branch.event_type,
                    "signal_event_type": branch.signal_event_type,
                    "has_scene_pressure_stub": branch.scene_pressure_stub is not None,
                }
            )
        for event_type in sorted(gate_consumed):
            _event_entry(event_type)["consumed_by_gate"].append(template.id)
        for event_type in sorted(branch_consumed):
            _event_entry(event_type)["consumed_by_branch"].append(template.id)
        for event_type in sorted(emitted):
            _event_entry(event_type)["emitted_by"].append(template.id)

        arity = {
            _ACTOR_ONLY_SLOTS: "actor_only",
            _ACTOR_TARGET_SLOTS: "two_party",
            _ACTOR_FACTION_SLOTS: "actor_faction",
            _ACTOR_TARGET_FACTION_SLOTS: "actor_target_faction",
        }.get(template.required_slots, "unsupported")
        template_payloads.append(
            {
                "template_id": template.id,
                "priority": template.priority,
                "tuple_index": tuple_index,
                "drive_band": template.drive_band.value,
                "blurb": template.blurb,
                "required_slots": [slot.value for slot in template.required_slots],
                "arity": arity,
                "present_target_policy": template.present_target_policy.value,
                "drive_band_priority_exempt": template.drive_band_priority_exempt,
                "priority_override_rationale": template.priority_override_rationale,
                "branches": branch_payloads,
                "consumed_event_types": {
                    "gate": sorted(gate_consumed),
                    "branch": sorted(branch_consumed),
                },
                "emitted_event_types": sorted(emitted),
            }
        )

    bands = [
        {
            "band": band.value,
            "urgency_rank": rank,
            "templates": [
                payload
                for payload in template_payloads
                if payload["drive_band"] == band.value
            ],
        }
        for band, rank in sorted(DRIVE_BAND_ORDER.items(), key=lambda item: item[1])
    ]

    for entry in event_map.values():
        entry_any: dict[str, Any] = entry  # widen for the derived flag
        entry_any["exogenous_only"] = not entry["emitted_by"] and bool(
            entry["consumed_by_gate"] or entry["consumed_by_branch"]
        )

    pseudo_templates = [
        {
            "template_id": f"{need_type}_need_pressure",
            "kind": "need_pressure",
            "need_type": need_type,
            "priority": need_tuning.priorities[need_type],
            "min_severity_level": need_tuning.pressure.min_severity_level,
        }
        for need_type in NEED_SEVERITY_PREFIX
    ]

    priority_ties: list[dict[str, Any]] = []
    for arity, slots in (
        ("actor_only", _ACTOR_ONLY_SLOTS),
        ("two_party", _ACTOR_TARGET_SLOTS),
        ("actor_faction", _ACTOR_FACTION_SLOTS),
        ("actor_target_faction", _ACTOR_TARGET_FACTION_SLOTS),
    ):
        partition = [t for t in templates_tuple if t.required_slots == slots]
        by_priority: dict[int, list[str]] = {}
        for template in partition:
            by_priority.setdefault(template.priority, []).append(template.id)
        for priority, ids in sorted(by_priority.items(), reverse=True):
            if len(ids) > 1:
                priority_ties.append(
                    {
                        "arity": arity,
                        "priority": priority,
                        # Tuple order — the actual tie-breaker.
                        "template_ids": ids,
                    }
                )

    promotion: Optional[dict[str, Any]] = None
    if promote_settings is not None:
        promotion = {
            "priority_threshold": promote_settings["priority_threshold"],
            "magnitude_threshold": promote_settings["magnitude_threshold"],
        }

    return {
        "drive_bands": bands,
        "pseudo_templates": pseudo_templates,
        "tag_families": {
            name: {"kind": spec["kind"], "members": sorted(spec["members"])}
            for name, spec in TAG_FAMILIES.items()
        },
        "event_map": event_map,
        "priority_ties": priority_ties,
        "drive_band_priority_warnings": list(
            drive_band_priority_warnings(templates_tuple)
        ),
        "promotion": promotion,
    }


# ---------------------------------------------------------------------------
# Entity hover/context hydration
# ---------------------------------------------------------------------------


def _tag_provenance(
    applied_at_world_time: Optional[datetime],
    source_chunk_id: Optional[int] = None,
) -> str:
    # Three tiers per the reconstruction-sufficiency notes: "exact" rows
    # carry the migration-064 chunk bestowal key; "approximate" rows have
    # only an in-world timestamp; the rest are "unknowable".
    if source_chunk_id is not None:
        return "exact"
    return "approximate" if applied_at_world_time is not None else "unknowable"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _cognition_source_chain(
    row: Mapping[str, Any], entity_names: Mapping[int, str]
) -> list[dict[str, Any]]:
    """Build an ordered acquisition chain without inferring missing sources."""

    chain: list[dict[str, Any]] = []
    root_id = row.get("root_source_entity_id")
    immediate_id = row.get("immediate_source_entity_id")
    if root_id is not None:
        root = int(root_id)
        chain.append(
            {
                "kind": "root_source",
                "entity_id": root,
                "name": _entity_label(root, entity_names),
            }
        )
    if immediate_id is not None and immediate_id != root_id:
        immediate = int(immediate_id)
        chain.append(
            {
                "kind": "immediate_source",
                "entity_id": immediate,
                "name": _entity_label(immediate, entity_names),
            }
        )
    owner = int(row["character_entity_id"])
    chain.append(
        {
            "kind": "possession",
            "entity_id": owner,
            "name": _entity_label(owner, entity_names),
        }
    )
    return chain


def _cognition_effective_config(orrery_settings: Mapping[str, Any]) -> dict[str, Any]:
    """Project only cognition-relevant, developer-adjustable configuration."""

    knowledge = dict(orrery_settings.get("knowledge") or {})
    recall = dict(orrery_settings.get("recall") or {})
    disclosure = dict(orrery_settings.get("disclosure") or {})
    experiences = dict(orrery_settings.get("experiences") or {})
    epistemics = dict(orrery_settings.get("epistemics") or {})
    prompt = dict(orrery_settings.get("prompt") or {})
    return {
        "enabled": {
            "knowledge": bool(knowledge.get("enabled")),
            "experiences": bool(experiences.get("enabled")),
            "epistemics": bool(epistemics.get("enabled")),
        },
        "caps": {
            "knowledge_max_entries": knowledge.get("max_entries"),
            "recall_per_character_max_entries": recall.get("per_character_max_entries"),
            "recall_mandatory_reserved_entries": recall.get(
                "mandatory_reserved_entries"
            ),
            "recall_trace_rows_per_character": recall.get("trace_rows_per_character"),
            "experience_max_seeds_per_render": experiences.get("max_seeds_per_render"),
            "experience_max_jobs_per_drain": experiences.get("max_jobs_per_drain"),
            "prompt_max_rendered_proposals": prompt.get("max_rendered_proposals"),
            "prompt_max_rendered_pressures": prompt.get("max_rendered_pressures"),
            "prompt_max_rendered_recent_rulings": prompt.get(
                "max_rendered_recent_rulings"
            ),
        },
        "weights": {
            key: recall.get(key)
            for key in (
                "semantic_fit_weight",
                "event_severity_weight",
                "actor_involvement_weight",
                "emotional_salience_weight",
                "recency_weight",
                "place_match_weight",
            )
        },
        "thresholds": {
            "disclosure_minimum_score": disclosure.get("minimum_score"),
            "disclosure_private_claim_minimum_score": disclosure.get(
                "private_claim_minimum_score"
            ),
            "recall_decay_half_life_hours": recall.get("decay_half_life_hours"),
            "recall_recency_horizon_hours": recall.get("recency_horizon_hours"),
        },
        "producer_coverage": {
            "claim_event_types": list(epistemics.get("claim_event_types") or []),
            "aware_roles": list(epistemics.get("aware_roles") or []),
            "experience_basis": ["participant", "witness", "acquisition"],
        },
    }


def cognition_trace(
    session: Any,
    entity_id: int,
    *,
    anchor_chunk_id: int,
    orrery_settings: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one character's cognition chain at an accepted scene anchor.

    Actor-facing material is assembled only from possession rows, actor-owned
    experiences, and durable recall/exposure traces. Unpossessed sibling
    accounts and latent secrets are queried independently into
    ``canonical_truth`` so callers cannot accidentally interleave them.
    """

    if entity_id <= 0 or anchor_chunk_id <= 0:
        raise ValueError("entity_id and anchor_chunk_id must be positive")
    anchor = (
        session.execute(
            text(
                """
            /* orrery_audit:cognition_anchor */
            SELECT cm.chunk_id, cm.world_time,
                   cm.world_layer::text AS world_layer,
                   cm.season, cm.episode, cm.scene,
                   nc.created_at
            FROM chunk_metadata cm
            JOIN narrative_chunks nc ON nc.id = cm.chunk_id
            WHERE cm.chunk_id = :anchor_chunk_id
            """
            ),
            {"anchor_chunk_id": anchor_chunk_id},
        )
        .mappings()
        .first()
    )
    if anchor is None:
        raise ValueError(f"Anchor chunk {anchor_chunk_id} has no timeline metadata")
    character = (
        session.execute(
            text(
                """
            /* orrery_audit:cognition_character */
            SELECT character.entity_id, character.name
            FROM characters character
            JOIN entities entity ON entity.id = character.entity_id
            WHERE character.entity_id = :entity_id
              AND entity.is_active = true
            """
            ),
            {"entity_id": entity_id},
        )
        .mappings()
        .first()
    )
    if character is None:
        raise ValueError(f"Entity {entity_id} is not an active character")

    account_rows = list(
        session.execute(
            text(
                """
                /* orrery_audit:cognition_possessed_accounts */
                WITH anchor AS (
                    SELECT cm.world_layer::text AS world_layer,
                           cm.world_time, nc.created_at
                    FROM chunk_metadata cm
                    JOIN narrative_chunks nc ON nc.id = cm.chunk_id
                    WHERE cm.chunk_id = :anchor_chunk_id
                )
                SELECT awareness.id AS awareness_id,
                       awareness.knower_entity_id AS character_entity_id,
                       awareness.source_tier, awareness.channel,
                       awareness.immediate_source_entity_id,
                       awareness.root_source_entity_id,
                       awareness.acquired_at_world_time,
                       awareness.source_chunk_id AS acquisition_chunk_id,
                       claim.id AS claim_id, claim.world_event_id,
                       claim.summary, claim.scope, claim.account_label,
                       claim.account_payload, claim.distorted_from_claim_id,
                       claim.distortion_min_depth,
                       incident.event_type, incident.tick_chunk_id,
                       incident.actor_entity_id, incident.target_entity_id,
                       incident.location_id, incident.world_time,
                       event_type.severity::text AS event_severity,
                       propagated.depth
                FROM claim_awareness awareness
                JOIN claims claim ON claim.id = awareness.claim_id
                JOIN world_events incident ON incident.id = claim.world_event_id
                JOIN event_types event_type ON event_type.type = incident.event_type
                JOIN chunk_metadata source_meta ON source_meta.chunk_id =
                    COALESCE(awareness.source_chunk_id, claim.source_chunk_id)
                CROSS JOIN anchor
                LEFT JOIN LATERAL (
                    SELECT (event.payload ->> 'depth')::integer AS depth
                    FROM world_events event
                    WHERE event.event_type = 'claim_propagated'
                      AND event.payload ? 'awareness_id'
                      AND (event.payload ->> 'awareness_id')::bigint = awareness.id
                    ORDER BY event.id DESC
                    LIMIT 1
                ) propagated ON TRUE
                WHERE awareness.knower_entity_id = :entity_id
                  AND incident.tick_chunk_id <= :anchor_chunk_id
                  AND source_meta.chunk_id <= :anchor_chunk_id
                  AND source_meta.world_layer::text IS NOT DISTINCT FROM
                      anchor.world_layer
                  AND (
                      awareness.acquired_at_world_time IS NULL
                      OR awareness.acquired_at_world_time <= anchor.world_time
                  )
                  AND (
                      awareness.source_chunk_id IS NOT NULL
                      OR awareness.created_at <= anchor.created_at
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM backstory_secrets secret
                      WHERE secret.claim_id = claim.id
                        AND secret.status = 'latent'
                  )
                ORDER BY awareness.id
                """
            ),
            {"entity_id": entity_id, "anchor_chunk_id": anchor_chunk_id},
        ).mappings()
    )
    referenced_ids = {entity_id}
    for row in account_rows:
        for key in (
            "immediate_source_entity_id",
            "root_source_entity_id",
            "actor_entity_id",
            "target_entity_id",
        ):
            if row[key] is not None:
                referenced_ids.add(int(row[key]))
    entity_names = _load_entity_names(session, referenced_ids)

    accounts: list[dict[str, Any]] = []
    for row in account_rows:
        accounts.append(
            {
                "awareness_id": int(row["awareness_id"]),
                "claim_id": int(row["claim_id"]),
                "summary": str(row["summary"]),
                "scope": str(row["scope"]),
                "account_label": str(row["account_label"]),
                "account_payload": row["account_payload"],
                "distorted_from_claim_id": row["distorted_from_claim_id"],
                "distortion_min_depth": row["distortion_min_depth"],
                "possession": {
                    "source_tier": str(row["source_tier"]),
                    "channel": row["channel"],
                    "acquisition_chunk_id": row["acquisition_chunk_id"],
                    "acquired_at_world_time": _iso(row["acquired_at_world_time"]),
                    "propagation_depth": row["depth"],
                    "source_chain": _cognition_source_chain(row, entity_names),
                },
                "source_event": {
                    "event_id": int(row["world_event_id"]),
                    "event_type": str(row["event_type"]),
                    "severity": row["event_severity"],
                    "tick_chunk_id": int(row["tick_chunk_id"]),
                    "actor_entity_id": row["actor_entity_id"],
                    "target_entity_id": row["target_entity_id"],
                    "location_id": row["location_id"],
                    "world_time": _iso(row["world_time"]),
                },
            }
        )

    experience_rows = list(
        session.execute(
            text(
                """
                /* orrery_audit:cognition_experiences */
                SELECT experience.*
                FROM character_experiences experience
                JOIN chunk_metadata source_meta
                  ON source_meta.chunk_id = experience.anchor_chunk_id
                WHERE experience.character_entity_id = :entity_id
                  AND experience.anchor_chunk_id <= :anchor_chunk_id
                  AND source_meta.world_layer::text IS NOT DISTINCT FROM
                      :world_layer
                  AND (
                      experience.world_time IS NULL
                      OR experience.world_time <= :anchor_world_time
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM backstory_secrets secret
                      WHERE secret.claim_id = experience.claim_id
                        AND secret.status = 'latent'
                  )
                ORDER BY experience.anchor_chunk_id, experience.id
                """
            ),
            {
                "entity_id": entity_id,
                "anchor_chunk_id": anchor_chunk_id,
                "world_layer": anchor["world_layer"],
                "anchor_world_time": anchor["world_time"],
            },
        ).mappings()
    )
    event_ids = sorted(
        {
            int(event_id)
            for row in experience_rows
            for event_id in row["world_event_ids"]
        }
    )
    events_by_id: dict[int, dict[str, Any]] = {}
    if event_ids:
        for row in session.execute(
            text(
                """
                /* orrery_audit:cognition_experience_events */
                SELECT event.id, event.event_type, event.tick_chunk_id,
                       event.actor_entity_id, event.target_entity_id,
                       event.location_id, event.world_time,
                       event_type.severity::text AS severity
                FROM world_events event
                JOIN event_types event_type ON event_type.type = event.event_type
                WHERE event.id = ANY(:event_ids)
                ORDER BY event.tick_chunk_id, event.id
                """
            ),
            {"event_ids": event_ids},
        ).mappings():
            events_by_id[int(row["id"])] = {
                "event_id": int(row["id"]),
                "event_type": str(row["event_type"]),
                "severity": row["severity"],
                "tick_chunk_id": int(row["tick_chunk_id"]),
                "actor_entity_id": row["actor_entity_id"],
                "target_entity_id": row["target_entity_id"],
                "location_id": row["location_id"],
                "world_time": _iso(row["world_time"]),
            }
    experiences: list[dict[str, Any]] = []
    for row in experience_rows:
        rendered = row["experience_text"] is not None
        status = (
            "invalidated"
            if str(row["invalidation_status"]) == "invalidated"
            else ("rendered" if rendered else "unrendered")
        )
        experiences.append(
            {
                "experience_id": int(row["id"]),
                "anchor_chunk_id": int(row["anchor_chunk_id"]),
                "basis": str(row["basis"]),
                "claim_id": row["claim_id"],
                "claim_awareness_id": row["claim_awareness_id"],
                "location_id": row["location_id"],
                "world_time": _iso(row["world_time"]),
                "seed_summary": str(row["seed_summary"]),
                "experience_text": row["experience_text"],
                "emotion": row["emotion"],
                "salience": float(row["salience"]),
                "render_status": status,
                "render_model": row["render_model"],
                "renderer_version": row["renderer_version"],
                "render_generation_id": (
                    str(row["render_generation_id"])
                    if row["render_generation_id"] is not None
                    else None
                ),
                "source_digest": str(row["source_digest"]),
                "world_layer": str(row["world_layer"]),
                "invalidated_at": _iso(row["invalidated_at"]),
                "source_events": [
                    events_by_id[int(event_id)] for event_id in row["world_event_ids"]
                ],
            }
        )

    trace_rows = list(
        session.execute(
            text(
                """
                /* orrery_audit:cognition_recall_trace */
                SELECT trace.*,
                       COALESCE(claim.summary, experience.seed_summary) AS summary,
                       COALESCE(claim.source_chunk_id,
                                experience.anchor_chunk_id) AS source_chunk_id
                FROM orrery_recall_trace trace
                LEFT JOIN claim_awareness awareness
                  ON trace.candidate_kind = 'claim'
                 AND awareness.id = trace.candidate_id
                LEFT JOIN claims claim ON claim.id = awareness.claim_id
                LEFT JOIN character_experiences experience
                  ON trace.candidate_kind = 'experience'
                 AND experience.id = trace.candidate_id
                WHERE trace.character_entity_id = :entity_id
                  AND trace.anchor_chunk_id = :anchor_chunk_id
                ORDER BY trace.created_at, trace.id
                """
            ),
            {"entity_id": entity_id, "anchor_chunk_id": anchor_chunk_id},
        ).mappings()
    )
    recall_candidates: list[dict[str, Any]] = []
    disclosure_results: list[dict[str, Any]] = []
    knowledge_exposures: list[dict[str, Any]] = []
    for row in trace_rows:
        components = dict(row["score_components"])
        disclosure = dict(components.get("disclosure") or {})
        candidate = {
            "trace_id": int(row["id"]),
            "turn_id": str(row["turn_id"]),
            "candidate_kind": str(row["candidate_kind"]),
            "candidate_id": int(row["candidate_id"]),
            "claim_id": row["claim_id"],
            "summary": row["summary"],
            "source_chunk_id": row["source_chunk_id"],
            "decision": str(row["decision"]),
            "reason": str(row["reason"]),
            "mandatory": bool(row["mandatory"]),
            "score": float(row["score"]),
            "score_components": components,
            "threshold": disclosure.get("threshold"),
            "truncated": str(row["decision"]) == "excluded",
            "created_at": _iso(row["created_at"]),
        }
        recall_candidates.append(candidate)
        if row["decision"] in {"included", "suppressed"}:
            disclosure_results.append(
                {
                    "trace_id": int(row["id"]),
                    "candidate_kind": str(row["candidate_kind"]),
                    "candidate_id": int(row["candidate_id"]),
                    "allowed": row["decision"] == "included",
                    "reason": str(row["reason"]),
                    "blocking_reasons": (
                        [] if row["decision"] == "included" else [str(row["reason"])]
                    ),
                    "components": disclosure,
                }
            )
        if row["decision"] == "included":
            knowledge_exposures.append(
                {
                    "kind": "knowledge_surfacing",
                    "trace_id": int(row["id"]),
                    "turn_id": str(row["turn_id"]),
                    "candidate_kind": str(row["candidate_kind"]),
                    "candidate_id": int(row["candidate_id"]),
                    "summary": row["summary"],
                    "position": len(knowledge_exposures),
                }
            )

    proposal_exposures: list[dict[str, Any]] = []
    for row in session.execute(
        text(
            """
            /* orrery_audit:cognition_prompt_exposures */
            SELECT exposure.id, exposure.kind, exposure.proposal_id,
                   exposure.template_id, exposure.binding_hash,
                   exposure.position, exposure.created_at,
                   resolution.actor_entity_id AS resolution_actor_entity_id,
                   resolution.brief, resolution.state_delta,
                   pressure.actor_entity_id AS pressure_actor_entity_id,
                   pressure.target_entity_id AS pressure_target_entity_id,
                   pressure.prompt_text, pressure.bindings
            FROM orrery_prompt_exposures exposure
            LEFT JOIN orrery_resolutions resolution
              ON exposure.kind = 'resolution'
             AND resolution.tick_chunk_id = exposure.tick_chunk_id
             AND resolution.template_id = exposure.template_id
             AND resolution.binding_hash = exposure.binding_hash
            LEFT JOIN orrery_scene_pressures pressure
              ON exposure.kind = 'scene_pressure'
             AND pressure.tick_chunk_id = exposure.tick_chunk_id
             AND pressure.template_id = exposure.template_id
             AND pressure.binding_hash = exposure.binding_hash
            WHERE exposure.tick_chunk_id = :anchor_chunk_id
              AND (
                  resolution.actor_entity_id = :entity_id
                  OR pressure.actor_entity_id = :entity_id
                  OR pressure.target_entity_id = :entity_id
              )
            ORDER BY exposure.kind, exposure.position, exposure.id
            """
        ),
        {"entity_id": entity_id, "anchor_chunk_id": anchor_chunk_id},
    ).mappings():
        proposal_exposures.append(
            {
                "kind": str(row["kind"]),
                "exposure_id": int(row["id"]),
                "proposal_id": str(row["proposal_id"]),
                "template_id": str(row["template_id"]),
                "binding_hash": str(row["binding_hash"]),
                "position": int(row["position"]),
                "created_at": _iso(row["created_at"]),
                "actor_entity_id": (
                    row["resolution_actor_entity_id"]
                    if row["kind"] == "resolution"
                    else row["pressure_actor_entity_id"]
                ),
                "target_entity_id": row["pressure_target_entity_id"],
                "payload": (
                    {
                        "brief": row["brief"],
                        "state_delta": row["state_delta"],
                    }
                    if row["kind"] == "resolution"
                    else {
                        "prompt_text": row["prompt_text"],
                        "bindings": row["bindings"],
                    }
                ),
            }
        )

    experience_ids = [row["experience_id"] for row in experiences]
    jobs: list[dict[str, Any]] = []
    if experience_ids:
        for row in session.execute(
            text(
                """
                /* orrery_audit:cognition_experience_jobs */
                SELECT *
                FROM character_experience_jobs
                WHERE experience_ids && CAST(:experience_ids AS bigint[])
                ORDER BY boundary_chunk_id, batch_ordinal, id
                """
            ),
            {"experience_ids": experience_ids},
        ).mappings():
            jobs.append(
                {
                    "job_id": int(row["id"]),
                    "state": str(row["state"]),
                    "attempts": int(row["attempts"]),
                    "available_at": _iso(row["available_at"]),
                    "lease_until": _iso(row["lease_until"]),
                    "locked_by": row["locked_by"],
                    "lease_nonce": (
                        str(row["lease_nonce"])
                        if row["lease_nonce"] is not None
                        else None
                    ),
                    "last_error": row["last_error"],
                    "requested_model": str(row["requested_model"]),
                    "source_digest": str(row["source_digest"]),
                    "experience_ids": list(row["experience_ids"]),
                    "timeline_identity": {
                        "world_layer": str(row["world_layer"]),
                        "boundary_chunk_id": int(row["boundary_chunk_id"]),
                        "boundary_season": int(row["boundary_season"]),
                        "boundary_episode": int(row["boundary_episode"]),
                        "boundary_scene": int(row["boundary_scene"]),
                        "scene_end_chunk_id": int(row["scene_end_chunk_id"]),
                        "scene_end_season": int(row["scene_end_season"]),
                        "scene_end_episode": int(row["scene_end_episode"]),
                        "scene_end_scene": int(row["scene_end_scene"]),
                    },
                }
            )

    sibling_accounts = [
        {
            "claim_id": int(row["claim_id"]),
            "world_event_id": int(row["world_event_id"]),
            "summary": str(row["summary"]),
            "scope": str(row["scope"]),
            "account_label": str(row["account_label"]),
            "account_payload": row["account_payload"],
            "distorted_from_claim_id": row["distorted_from_claim_id"],
            "distortion_min_depth": row["distortion_min_depth"],
        }
        for row in session.execute(
            text(
                """
                /* orrery_audit:cognition_unpossessed_siblings */
                WITH possessed_incidents AS (
                    SELECT DISTINCT claim.world_event_id
                    FROM claim_awareness awareness
                    JOIN claims claim ON claim.id = awareness.claim_id
                    WHERE awareness.knower_entity_id = :entity_id
                      AND (
                          awareness.source_chunk_id <= :anchor_chunk_id
                          OR (
                              awareness.source_chunk_id IS NULL
                              AND claim.source_chunk_id <= :anchor_chunk_id
                          )
                      )
                )
                SELECT claim.id AS claim_id, claim.world_event_id,
                       claim.summary, claim.scope, claim.account_label,
                       claim.account_payload, claim.distorted_from_claim_id,
                       claim.distortion_min_depth
                FROM claims claim
                JOIN possessed_incidents incident
                  ON incident.world_event_id = claim.world_event_id
                JOIN world_events event ON event.id = claim.world_event_id
                WHERE event.tick_chunk_id <= :anchor_chunk_id
                  AND NOT EXISTS (
                      SELECT 1 FROM claim_awareness awareness
                      WHERE awareness.claim_id = claim.id
                        AND awareness.knower_entity_id = :entity_id
                  )
                ORDER BY claim.world_event_id, claim.id
                """
            ),
            {"entity_id": entity_id, "anchor_chunk_id": anchor_chunk_id},
        ).mappings()
    ]
    latent_secrets = [
        {
            "secret_id": int(row["secret_id"]),
            "claim_id": int(row["claim_id"]),
            "summary": str(row["summary"]),
            "account_payload": row["account_payload"],
            "gate_template_id": str(row["gate_template_id"]),
            "holder_entity_id": int(row["holder_entity_id"]),
            "source_chunk_id": row["source_chunk_id"],
            "status": str(row["status"]),
        }
        for row in session.execute(
            text(
                """
                /* orrery_audit:cognition_latent_secrets */
                SELECT secret.id AS secret_id, secret.claim_id,
                       claim.summary, claim.account_payload,
                       secret.gate_template_id, secret.holder_entity_id,
                       secret.source_chunk_id, secret.status
                FROM backstory_secrets secret
                JOIN claims claim ON claim.id = secret.claim_id
                JOIN world_events event ON event.id = claim.world_event_id
                WHERE secret.holder_entity_id = :entity_id
                  AND secret.status = 'latent'
                  AND event.tick_chunk_id <= :anchor_chunk_id
                ORDER BY secret.id
                """
            ),
            {"entity_id": entity_id, "anchor_chunk_id": anchor_chunk_id},
        ).mappings()
    ]

    render_generation_ids = sorted(
        {
            row["render_generation_id"]
            for row in experiences
            if row["render_generation_id"] is not None
        }
    )
    return {
        "entity": {"entity_id": entity_id, "name": str(character["name"])},
        "anchor": {
            "chunk_id": int(anchor["chunk_id"]),
            "world_time": _iso(anchor["world_time"]),
            "world_layer": str(anchor["world_layer"]),
            "season": int(anchor["season"]),
            "episode": int(anchor["episode"]),
            "scene": int(anchor["scene"]),
        },
        "actor_facing": {
            "possessed_accounts": accounts,
            "experiences": experiences,
            "recall_candidates": recall_candidates,
            "recall_truncated": any(row["truncated"] for row in recall_candidates),
            "disclosure_results": disclosure_results,
            "prompt_exposure": {
                "orrery_proposals": proposal_exposures,
                "knowledge_surfacing": knowledge_exposures,
            },
            "experience_jobs": jobs,
            "generation_identity": {
                "render_generation_ids": render_generation_ids,
                "timeline": {
                    "world_layer": str(anchor["world_layer"]),
                    "season": int(anchor["season"]),
                    "episode": int(anchor["episode"]),
                    "scene": int(anchor["scene"]),
                },
            },
        },
        "effective_config": _cognition_effective_config(orrery_settings),
        "canonical_truth": {
            "guarded": True,
            "unpossessed_sibling_accounts": sibling_accounts,
            "latent_secrets": latent_secrets,
        },
    }


def entity_context(
    session: Any,
    entity_ids: Iterable[int],
    *,
    anchor_chunk_id: Optional[int],
    recent_events_limit: int = 5,
    sunhelm_settings: Optional[Any] = None,
    contagion_settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Return the hover-audit payload for a set of entity ids.

    Everything the dashboard's HoverCard renders: name, place (with classes),
    activity, effective need debt, tags with per-row provenance and family
    membership, pair tags, relationships (explicitly labeled unversioned),
    possessed claims with acquisition provenance, travel state, routine
    anchors, and recent events. Read-only.
    """

    ids = sorted(set(entity_ids))
    if not ids:
        return {"anchor_chunk_id": anchor_chunk_id, "entities": []}

    need_tuning = coerce_need_tuning(sunhelm_settings)
    world_time = _load_world_time(session, anchor_chunk_id=anchor_chunk_id)
    communication_graph = communication_graph_for_settings(
        session, contagion_settings, world_time=world_time
    )

    kinds = {
        row["id"]: row["kind"]
        for row in session.execute(
            text(
                """
                /* orrery_audit:entity_kinds */
                SELECT id, kind::text AS kind
                FROM entities
                WHERE id = ANY(:ids)
                """
            ),
            {"ids": ids},
        ).mappings()
    }

    tags_by_entity: dict[int, list[dict[str, Any]]] = {}
    tag_sets: dict[int, set[str]] = {}
    for row in session.execute(
        text(
            """
            /* orrery_audit:entity_tags */
            SELECT etc.entity_id, etc.tag, etc.category, etc.is_ephemeral,
                   etc.source_kind::text AS source_kind, etc.template_id,
                   etc.applied_at, etc.applied_at_world_time,
                   etc.source_chunk_id
            FROM entity_tags_current etc
            JOIN entity_tags et ON et.id = etc.entity_tag_id
            WHERE etc.entity_id = ANY(:ids)
              AND (
                  :current_world_time IS NULL
                  OR et.expires_at_world_time IS NULL
                  OR et.expires_at_world_time > :current_world_time
              )
            ORDER BY etc.entity_id, etc.tag
            """
        ),
        {"ids": ids, "current_world_time": world_time},
    ).mappings():
        tag = row["tag"]
        tags_by_entity.setdefault(row["entity_id"], []).append(
            {
                "tag": tag,
                "category": row["category"],
                "is_ephemeral": row["is_ephemeral"],
                "source_kind": row["source_kind"],
                "template_id": row["template_id"],
                "applied_at": _iso(row["applied_at"]),
                "applied_at_world_time": _iso(row["applied_at_world_time"]),
                "source_chunk_id": row["source_chunk_id"],
                "provenance": _tag_provenance(
                    row["applied_at_world_time"], row["source_chunk_id"]
                ),
                "families": [
                    name
                    for name, members in _TAG_FAMILY_TAG_SETS.items()
                    if tag in members
                ],
            }
        )
        # Production hydration feeds only durable tags into the need-immunity
        # check (hydrate_world_state's `tags` excludes ephemerals); match it.
        if not row["is_ephemeral"]:
            tag_sets.setdefault(row["entity_id"], set()).add(tag)

    pair_tags_by_entity: dict[int, list[dict[str, Any]]] = {}
    referenced_ids: set[int] = set(ids)
    for row in session.execute(
        text(
            """
            /* orrery_audit:entity_pair_tags */
            SELECT ept.subject_entity_id,
                   ept.object_entity_id,
                   pt.tag,
                   ept.source_kind::text AS source_kind,
                   ept.template_id,
                   ept.applied_at,
                   ept.applied_at_world_time,
                   ept.source_chunk_id
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.cleared_at IS NULL
              AND NOT pt.deprecated
              AND (ept.subject_entity_id = ANY(:ids)
                   OR ept.object_entity_id = ANY(:ids))
            ORDER BY ept.subject_entity_id, ept.object_entity_id, pt.tag
            """
        ),
        {"ids": ids},
    ).mappings():
        subject_id = row["subject_entity_id"]
        object_id = row["object_entity_id"]
        referenced_ids.update((subject_id, object_id))
        base = {
            "tag": row["tag"],
            "source_kind": row["source_kind"],
            "template_id": row["template_id"],
            "applied_at": _iso(row["applied_at"]),
            "applied_at_world_time": _iso(row["applied_at_world_time"]),
            "source_chunk_id": row["source_chunk_id"],
            "provenance": _tag_provenance(
                row["applied_at_world_time"], row["source_chunk_id"]
            ),
        }
        if subject_id in kinds:
            pair_tags_by_entity.setdefault(subject_id, []).append(
                {**base, "direction": "outbound", "other_entity_id": object_id}
            )
        if object_id in kinds:
            pair_tags_by_entity.setdefault(object_id, []).append(
                {**base, "direction": "inbound", "other_entity_id": subject_id}
            )

    relationships_by_entity: dict[int, list[dict[str, Any]]] = {}
    for row in session.execute(
        text(
            """
            /* orrery_audit:entity_relationships */
            SELECT source_entity_id,
                   target_entity_id,
                   relationship_type,
                   valence_magnitude
            FROM entity_relationships_v
            WHERE relationship_scope = 'character'
              AND source_entity_id IS NOT NULL
              AND target_entity_id IS NOT NULL
              AND relationship_type IS NOT NULL
              AND (source_entity_id = ANY(:ids)
                   OR target_entity_id = ANY(:ids))
            """
        ),
        {"ids": ids},
    ).mappings():
        source_id = row["source_entity_id"]
        target_id = row["target_entity_id"]
        referenced_ids.update((source_id, target_id))
        base = {
            "relationship_type": row["relationship_type"],
            "valence_magnitude": row["valence_magnitude"],
            # No versioned relationship storage exists; the UI renders this
            # as the "unversioned" watermark.
            "versioned": False,
        }
        if source_id in kinds:
            relationships_by_entity.setdefault(source_id, []).append(
                {**base, "direction": "outbound", "other_entity_id": target_id}
            )
        if target_id in kinds:
            relationships_by_entity.setdefault(target_id, []).append(
                {**base, "direction": "inbound", "other_entity_id": source_id}
            )

    common_claims_by_entity: dict[int, dict[int, dict[str, Any]]] = {}
    explicit_claims_by_entity: dict[int, dict[int, dict[str, Any]]] = {}
    for row in session.execute(
        text(
            """
            /* orrery_audit:entity_claim_knowledge */
            WITH anchor AS (
                SELECT created_at
                FROM narrative_chunks
                WHERE id = :anchor_chunk_id
            ),
            requested_awareness AS (
                SELECT id,
                       claim_id,
                       knower_entity_id,
                       source_tier,
                       channel,
                       immediate_source_entity_id,
                       root_source_entity_id,
                       acquired_at_world_time
                FROM claim_awareness
                WHERE knower_entity_id = ANY(:ids)
                  -- Mirror replay.py's claim-awareness readmission visibility.
                  AND (
                      :anchor_chunk_id IS NULL
                      OR (source_chunk_id IS NOT NULL
                          AND source_chunk_id <= :anchor_chunk_id)
                      OR (source_chunk_id IS NULL
                          AND created_at <= (SELECT created_at FROM anchor))
                  )
            ),
            requested_common_claims AS (
                SELECT c.id AS claim_id,
                       array_agg(
                           DISTINCT about.entity_id ORDER BY about.entity_id
                       ) AS about_entity_ids
                FROM claims c
                JOIN world_events mint_event
                  ON mint_event.id = c.world_event_id
                JOIN LATERAL (
                    SELECT mint_event.actor_entity_id AS entity_id
                    WHERE mint_event.actor_entity_id IS NOT NULL
                    UNION
                    SELECT mint_event.target_entity_id AS entity_id
                    WHERE mint_event.target_entity_id IS NOT NULL
                    UNION
                    SELECT wee.entity_id
                    FROM world_event_entities wee
                    WHERE wee.event_id = mint_event.id
                ) about ON about.entity_id = ANY(:ids)
                WHERE c.scope = 'common'
                  AND (:anchor_chunk_id IS NULL
                       OR mint_event.tick_chunk_id <= :anchor_chunk_id)
                GROUP BY c.id
            ),
            propagated AS (
                SELECT requested.id AS awareness_id,
                       (event.payload ->> 'depth')::integer AS depth
                FROM requested_awareness requested
                JOIN world_events event
                  ON event.event_type = 'claim_propagated'
                 AND COALESCE(
                         (event.payload ->> 'delivered_claim_id')::bigint,
                         (event.payload ->> 'claim_id')::bigint
                     ) = requested.claim_id
                 AND (event.payload ->> 'awareness_id')::bigint = requested.id
                WHERE event.payload ? 'claim_id'
                  AND event.payload ? 'awareness_id'
            )
            SELECT c.id AS claim_id,
                   c.summary,
                   c.scope,
                   requested_common.about_entity_ids AS common_about_entity_ids,
                   ca.id AS awareness_id,
                   ca.knower_entity_id,
                   ca.source_tier,
                   ca.channel,
                   ca.immediate_source_entity_id,
                   ca.root_source_entity_id,
                   ca.acquired_at_world_time,
                   propagated.depth
            FROM claims c
            JOIN world_events mint_event ON mint_event.id = c.world_event_id
            LEFT JOIN requested_common_claims requested_common
              ON requested_common.claim_id = c.id
            LEFT JOIN requested_awareness ca ON ca.claim_id = c.id
            LEFT JOIN propagated ON propagated.awareness_id = ca.id
            WHERE (:anchor_chunk_id IS NULL
                   OR mint_event.tick_chunk_id <= :anchor_chunk_id)
              AND (requested_common.claim_id IS NOT NULL OR ca.id IS NOT NULL)
            ORDER BY c.id, ca.knower_entity_id NULLS FIRST
            """
        ),
        {"ids": ids, "anchor_chunk_id": anchor_chunk_id},
    ).mappings():
        claim_id = int(row["claim_id"])
        scope = str(row["scope"])
        if scope not in CLAIM_SCOPES:
            raise ValueError(f"Claim {claim_id} has unknown scope {scope!r}")
        base_claim = {
            "claim_id": claim_id,
            "summary": str(row["summary"]),
            "scope": scope,
        }
        if scope == "common":
            common_claim = {
                **base_claim,
                "tier": "common",
                "channel": None,
                "immediate_source_entity_id": None,
                "root_source_entity_id": None,
                "acquired_at_world_time": None,
                "depth": None,
            }
            for about_entity_id in row["common_about_entity_ids"] or ():
                common_claims_by_entity.setdefault(int(about_entity_id), {})[
                    claim_id
                ] = common_claim
        knower_entity_id = row["knower_entity_id"]
        if knower_entity_id is None:
            continue
        knower_id = int(knower_entity_id)
        immediate_source = row["immediate_source_entity_id"]
        root_source = row["root_source_entity_id"]
        if immediate_source is not None:
            referenced_ids.add(int(immediate_source))
        if root_source is not None:
            referenced_ids.add(int(root_source))
        by_claim = explicit_claims_by_entity.setdefault(knower_id, {})
        if claim_id in by_claim:
            raise RuntimeError(
                "Duplicate claim_propagated audit ledger entries for awareness "
                f"{row['awareness_id']}"
            )
        source_tier = str(row["source_tier"])
        if source_tier not in SOURCE_TIERS:
            raise ValueError(
                f"Claim {claim_id} has unknown awareness tier {source_tier!r}"
            )
        depth = int(row["depth"]) if row["depth"] is not None else None
        if depth is not None and depth < 1:
            raise ValueError(
                f"Claim {claim_id} awareness {row['awareness_id']} has invalid "
                f"propagation depth {depth}"
            )
        by_claim[claim_id] = {
            **base_claim,
            "tier": source_tier,
            "channel": row["channel"],
            "immediate_source_entity_id": (
                int(immediate_source) if immediate_source is not None else None
            ),
            "root_source_entity_id": (
                int(root_source) if root_source is not None else None
            ),
            "acquired_at_world_time": _iso(row["acquired_at_world_time"]),
            "depth": depth,
        }

    place_rows = {
        row["entity_id"]: row
        for row in session.execute(
            text(
                """
                /* orrery_audit:character_places */
                SELECT c.entity_id,
                       c.current_location,
                       c.current_activity,
                       p.type::text AS place_type,
                       p.entity_id AS place_entity_id
                FROM characters c
                LEFT JOIN places p ON p.id = c.current_location
                WHERE c.entity_id = ANY(:ids)
                """
            ),
            {"ids": ids},
        ).mappings()
    }
    place_ids = sorted(
        {
            row["current_location"]
            for row in place_rows.values()
            if row["current_location"] is not None
        }
    )
    place_classes: dict[int, set[str]] = {}
    if place_ids:
        for row in session.execute(
            text(
                f"""
                /* orrery_audit:place_classes */
                SELECT p.id AS place_id, etc.tag
                FROM places p
                JOIN entity_tags_current etc ON etc.entity_id = p.entity_id
                JOIN entity_tags et ON et.id = etc.entity_tag_id
                WHERE p.id = ANY(:place_ids)
                  AND etc.entity_kind = 'place'
                  AND etc.category IN ({_LOCATION_CLASS_CATEGORY_SQL})
                  AND (
                      :current_world_time IS NULL
                      OR et.expires_at_world_time IS NULL
                      OR et.expires_at_world_time > :current_world_time
                  )
                """
            ),
            {"place_ids": place_ids, "current_world_time": world_time},
        ).mappings():
            place_classes.setdefault(row["place_id"], set()).add(row["tag"])
    for row in place_rows.values():
        if row["place_entity_id"] is not None:
            referenced_ids.add(row["place_entity_id"])

    need_scores = _load_need_debt_scores(
        session,
        current_world_time=world_time,
        need_tuning=need_tuning,
        tags_by_entity={
            entity_id: frozenset(values) for entity_id, values in tag_sets.items()
        },
    )
    needs_by_entity: dict[int, list[dict[str, Any]]] = {}
    for (entity_id, need_type), score in sorted(need_scores.items()):
        if entity_id not in kinds:
            continue
        severity = severity_for_debt(need_type, score, tuning=need_tuning)
        needs_by_entity.setdefault(entity_id, []).append(
            {
                "need_type": need_type,
                "debt_score": score,
                "severity_level": severity[0] if severity else None,
                "severity_name": severity[1] if severity else None,
            }
        )

    travel_states = _load_travel_states(session)
    routine_anchors = _load_routine_anchors(session)
    anchors_by_entity: dict[int, list[dict[str, Any]]] = {}
    for (anchor_entity_id, _), anchor in sorted(
        routine_anchors.items(), key=lambda item: item[0]
    ):
        anchors_by_entity.setdefault(anchor_entity_id, []).append(asdict(anchor))

    events_by_entity: dict[int, list[dict[str, Any]]] = {}
    # Anchor-bound like production _load_recent_events: a historical anchor
    # must not surface events from its own future next to the anchor's clock.
    anchor_bound = (
        "AND tick_chunk_id <= :anchor_chunk_id" if anchor_chunk_id is not None else ""
    )
    for entity_id in ids:
        event_params: dict[str, Any] = {
            "entity_id": entity_id,
            "limit": recent_events_limit,
        }
        if anchor_chunk_id is not None:
            event_params["anchor_chunk_id"] = anchor_chunk_id
        rows = session.execute(
            text(
                f"""
                /* orrery_audit:entity_recent_events */
                SELECT event_type,
                       tick_chunk_id,
                       actor_entity_id,
                       target_entity_id,
                       location_id
                FROM world_events
                WHERE (actor_entity_id = :entity_id
                       OR target_entity_id = :entity_id)
                  AND (world_layer IS NULL OR world_layer = 'primary')
                  AND superseded_by_event_id IS NULL
                  {anchor_bound}
                ORDER BY tick_chunk_id DESC, id DESC
                LIMIT :limit
                """
            ),
            event_params,
        ).mappings()
        events = []
        for row in rows:
            events.append(dict(row))
            for key in ("actor_entity_id", "target_entity_id"):
                if row[key] is not None:
                    referenced_ids.add(row[key])
        events_by_entity[entity_id] = events

    entity_names = _load_entity_names(session, referenced_ids)

    def _named(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for row in rows:
            if "other_entity_id" in row:
                row["other_name"] = _entity_label(row["other_entity_id"], entity_names)
        return rows

    for events in events_by_entity.values():
        for event in events:
            for key, name_key in (
                ("actor_entity_id", "actor_name"),
                ("target_entity_id", "target_name"),
            ):
                event[name_key] = (
                    _entity_label(event[key], entity_names)
                    if event[key] is not None
                    else None
                )

    def _knowledge(entity_id: int) -> list[dict[str, Any]]:
        possessed = dict(common_claims_by_entity.get(entity_id, {}))
        possessed.update(explicit_claims_by_entity.get(entity_id, {}))
        rows = []
        for claim_id in sorted(possessed):
            claim = possessed[claim_id]

            def source_payload(key: str) -> Optional[dict[str, Any]]:
                source_id = claim[key]
                if source_id is None:
                    return None
                return {
                    "entity_id": source_id,
                    "name": _entity_label(source_id, entity_names),
                }

            rows.append(
                {
                    "claim_id": claim["claim_id"],
                    "summary": claim["summary"],
                    "scope": claim["scope"],
                    "tier": claim["tier"],
                    "channel": claim["channel"],
                    "immediate_source": source_payload("immediate_source_entity_id"),
                    "root_source": source_payload("root_source_entity_id"),
                    "acquired_at_world_time": claim["acquired_at_world_time"],
                    "depth": claim["depth"],
                }
            )
        return rows

    entities: list[dict[str, Any]] = []
    for entity_id in ids:
        place_row = place_rows.get(entity_id)
        place: Optional[dict[str, Any]] = None
        activity: Optional[str] = None
        if place_row is not None:
            activity = place_row["current_activity"]
            if place_row["current_location"] is not None:
                place = {
                    "place_id": place_row["current_location"],
                    "name": (
                        entity_names.get(place_row["place_entity_id"])
                        if place_row["place_entity_id"] is not None
                        else None
                    ),
                    "place_type": place_row["place_type"],
                    "classes": sorted(
                        place_classes.get(place_row["current_location"], set())
                    ),
                }
        tag_rows = tags_by_entity.get(entity_id, [])
        travel = travel_states.get(entity_id)
        anchors = anchors_by_entity.get(entity_id, [])
        entities.append(
            {
                "entity_id": entity_id,
                "name": _entity_label(entity_id, entity_names),
                "kind": kinds.get(entity_id),
                "place": place,
                "activity": activity,
                "needs": needs_by_entity.get(entity_id, []),
                "tags": {
                    "durable": [t for t in tag_rows if not t["is_ephemeral"]],
                    "ephemeral": [t for t in tag_rows if t["is_ephemeral"]],
                },
                "pair_tags": _named(pair_tags_by_entity.get(entity_id, [])),
                "relationships": _named(relationships_by_entity.get(entity_id, [])),
                "communication_edges": [
                    edge.to_dict() for edge in communication_graph.outbound(entity_id)
                ],
                "knowledge": _knowledge(entity_id),
                "travel_state": asdict(travel) if travel is not None else None,
                "routine_anchors": anchors,
                "recent_events": events_by_entity.get(entity_id, []),
            }
        )

    return {
        "anchor_chunk_id": anchor_chunk_id,
        "world_time": _iso(world_time),
        "entities": entities,
    }
