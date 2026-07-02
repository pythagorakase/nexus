"""Slot-backed explained resolution for the Orrery audit dashboard.

This module is the read-only bridge between the explain layer
(:mod:`nexus.agents.orrery.explain`) and real slot databases. It mirrors
:func:`nexus.agents.orrery.resolver.resolve_dry_run` **exactly** — the same
hydration, the same actor-only / two-party stack split, the same binding
composition (including threading the actor set through
``compose_actor_target_bindings``), and the same present-target pressure pass —
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
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List, Mapping, Optional, Tuple

from sqlalchemy import text

from nexus.agents.orrery.explain import StackExplanation, explain_stack
from nexus.agents.orrery.needs import (
    NEED_SEVERITY_PREFIX,
    coerce_need_tuning,
    severity_for_debt,
)
from nexus.agents.orrery.resolver import (
    _LOCATION_CLASS_CATEGORY_SQL,
    OrreryScenePressureDraft,
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
    compose_actor_target_bindings,
    hydrate_world_state,
)
from nexus.agents.orrery.substrate import (
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

NOT_APPLICABLE_REASON = "no_target_bound"


@dataclass(frozen=True, slots=True)
class ActorGroupExplanation:
    """All explained stacks for one off-screen actor in one tick."""

    actor_entity_id: int
    actor_stack: StackExplanation
    two_party_stacks: Tuple[StackExplanation, ...] = ()
    scene_pressure_stacks: Tuple[StackExplanation, ...] = ()
    not_applicable: Tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ExplainedTickReport:
    """Full audit record for one dry-run tick against a real slot."""

    anchor_chunk_id: Optional[int]
    window_chunks: int
    world_time: Optional[datetime]
    time_of_day: str
    weather: str
    actor_count: int
    actors: Tuple[ActorGroupExplanation, ...]
    need_pressures: Tuple[OrreryScenePressureDraft, ...]
    entity_names: Mapping[int, str]
    locations: Mapping[int, Any]
    location_names: Mapping[int, str]
    activities: Mapping[int, str]
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
            "generated_at": self.generated_at,
            "actors": [self._group_payload(group) for group in self.actors],
            "need_pressures": [draft.to_dict() for draft in self.need_pressures],
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
        return {
            "actor_entity_id": actor_id,
            "actor_name": _entity_label(actor_id, self.entity_names),
            "location": location,
            "activity": self.activities.get(actor_id),
            "actor_stack": self._stack_payload(group.actor_stack),
            "two_party_stacks": [
                self._stack_payload(stack) for stack in group.two_party_stacks
            ],
            "scene_pressure_stacks": [
                self._stack_payload(stack) for stack in group.scene_pressure_stacks
            ],
            "not_applicable": [dict(item) for item in group.not_applicable],
        }

    def _stack_payload(self, stack: StackExplanation) -> dict[str, Any]:
        payload = stack.to_dict()
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


def explain_dry_run(
    session: Any,
    templates: Iterable[Template],
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
    sunhelm_settings: Optional[Any] = None,
    world_time_override: Optional[datetime] = None,
) -> ExplainedTickReport:
    """Hydrate, bind, and explain Orrery packages without database writes.

    Every step below has a line-for-line counterpart in ``resolve_dry_run``;
    keep them in lockstep. Winner/branch parity with production is enforced
    per template by ``explain_template``'s cross-check against ``evaluate``.
    """

    need_tuning = coerce_need_tuning(sunhelm_settings)
    state = hydrate_world_state(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
        need_tuning=need_tuning,
        world_time_override=world_time_override,
    )

    templates_list = list(templates)
    actor_only_templates = [
        t for t in templates_list if t.required_slots == _ACTOR_ONLY_SLOTS
    ]
    actor_target_templates = [
        t for t in templates_list if t.required_slots == _ACTOR_TARGET_SLOTS
    ]
    unsupported = [
        t
        for t in templates_list
        if t.required_slots not in (_ACTOR_ONLY_SLOTS, _ACTOR_TARGET_SLOTS)
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
    actor_stacks: dict[int, StackExplanation] = {}
    for bindings in actor_bindings:
        actor_stacks[bindings[Slot.ACTOR]] = explain_stack(
            actor_only_templates, state, bindings
        )
    actor_ids = set(actor_stacks)

    two_party_stacks: dict[int, List[StackExplanation]] = {}
    pressure_stacks: dict[int, List[StackExplanation]] = {}
    if actor_target_templates:
        offscreen_pair_bindings = compose_actor_target_bindings(
            session,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            actor_ids=actor_ids,
            target_presence="offscreen",
        )
        for bindings in offscreen_pair_bindings:
            two_party_stacks.setdefault(bindings[Slot.ACTOR], []).append(
                explain_stack(actor_target_templates, state, bindings)
            )

        pressure_templates = [
            template
            for template in actor_target_templates
            if template.present_target_policy
            is PresentTargetPolicy.STORYTELLER_PRESSURE
        ]
        if pressure_templates:
            present_pair_bindings = compose_actor_target_bindings(
                session,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=window_chunks,
                actor_ids=actor_ids,
                target_presence="present",
            )
            for bindings in present_pair_bindings:
                pressure_stacks.setdefault(bindings[Slot.ACTOR], []).append(
                    explain_stack(pressure_templates, state, bindings)
                )

    present_actor_ids = _present_actor_ids_at_anchor(
        session, anchor_chunk_id=anchor_chunk_id
    )
    need_pressure_specs = _present_need_pressure_specs(
        state,
        present_actor_ids=present_actor_ids,
        need_tuning=need_tuning,
    )

    entity_ids: set[int] = {spec["actor_entity_id"] for spec in need_pressure_specs}
    all_stacks: list[StackExplanation] = list(actor_stacks.values())
    for stacks in two_party_stacks.values():
        all_stacks.extend(stacks)
    for stacks in pressure_stacks.values():
        all_stacks.extend(stacks)
    for stack in all_stacks:
        for value in stack.bindings.values():
            if isinstance(value, int):
                entity_ids.add(value)
    place_entity_ids = {
        state.location_entity_ids[place_id]
        for actor_id in actor_ids
        if (place_id := state.locations.get(actor_id)) is not None
        and place_id in state.location_entity_ids
    }
    entity_names = _load_entity_names(session, entity_ids | place_entity_ids)
    location_names = {
        place_id: entity_names[entity_id]
        for place_id, entity_id in state.location_entity_ids.items()
        if entity_id in entity_names
    }

    need_pressures = tuple(
        _scene_pressure_from_need_spec(
            spec,
            entity_names,
            need_tuning=need_tuning,
        )
        for spec in need_pressure_specs
    )

    not_applicable_markers = tuple(
        {
            "template_id": template.id,
            "priority": template.priority,
            "drive_band": template.drive_band.value,
            "reason": NOT_APPLICABLE_REASON,
        }
        for template in actor_target_templates
    )
    groups = tuple(
        ActorGroupExplanation(
            actor_entity_id=actor_id,
            actor_stack=actor_stacks[actor_id],
            two_party_stacks=tuple(two_party_stacks.get(actor_id, ())),
            scene_pressure_stacks=tuple(pressure_stacks.get(actor_id, ())),
            not_applicable=(
                not_applicable_markers if not two_party_stacks.get(actor_id) else ()
            ),
        )
        for actor_id in sorted(actor_ids)
    )

    return ExplainedTickReport(
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
        world_time=state.world_time,
        time_of_day=state.time_of_day,
        weather=state.weather,
        actor_count=len(actor_ids),
        actors=groups,
        need_pressures=need_pressures,
        entity_names=entity_names,
        locations=dict(state.locations),
        location_names=location_names,
        activities=dict(state.activities),
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
            branch_payloads.append(
                {
                    "label": branch.label,
                    "magnitude": branch.magnitude,
                    "event_type": branch.event_type,
                    "has_scene_pressure_stub": branch.scene_pressure_stub is not None,
                }
            )
        for event_type in sorted(gate_consumed):
            _event_entry(event_type)["consumed_by_gate"].append(template.id)
        for event_type in sorted(branch_consumed):
            _event_entry(event_type)["consumed_by_branch"].append(template.id)
        for event_type in sorted(emitted):
            _event_entry(event_type)["emitted_by"].append(template.id)

        arity = (
            "two_party"
            if template.required_slots == _ACTOR_TARGET_SLOTS
            else "actor_only"
        )
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


def _tag_provenance(applied_at_world_time: Optional[datetime]) -> str:
    # "exact" is reserved for rows carrying a source_chunk_id bestowal key,
    # which does not exist pre-migration (see the reconstruction-sufficiency
    # notes in docs/orrery_audit_dashboard_notes.md).
    return "approximate" if applied_at_world_time is not None else "unknowable"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def entity_context(
    session: Any,
    entity_ids: Iterable[int],
    *,
    anchor_chunk_id: Optional[int],
    recent_events_limit: int = 5,
    sunhelm_settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Return the hover-audit payload for a set of entity ids.

    Everything the dashboard's HoverCard renders: name, place (with classes),
    activity, effective need debt, tags with per-row provenance and family
    membership, pair tags, relationships (explicitly labeled unversioned),
    travel state, routine anchors, and recent events. Read-only.
    """

    ids = sorted(set(entity_ids))
    if not ids:
        return {"anchor_chunk_id": anchor_chunk_id, "entities": []}

    need_tuning = coerce_need_tuning(sunhelm_settings)
    world_time = _load_world_time(session, anchor_chunk_id=anchor_chunk_id)

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
            SELECT entity_id, tag, category, is_ephemeral, source_kind::text
                   AS source_kind, template_id, applied_at,
                   applied_at_world_time
            FROM entity_tags_current
            WHERE entity_id = ANY(:ids)
            ORDER BY entity_id, tag
            """
        ),
        {"ids": ids},
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
                "provenance": _tag_provenance(row["applied_at_world_time"]),
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
                   ept.applied_at_world_time
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
            "provenance": _tag_provenance(row["applied_at_world_time"]),
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
                WHERE p.id = ANY(:place_ids)
                  AND etc.entity_kind = 'place'
                  AND etc.category IN ({_LOCATION_CLASS_CATEGORY_SQL})
                """
            ),
            {"place_ids": place_ids},
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
