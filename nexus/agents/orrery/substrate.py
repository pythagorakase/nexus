"""Pure-Python substrate for Orrery off-screen behavior packages."""

from __future__ import annotations

from dataclasses import dataclass, field, replace as dataclass_replace
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
import math
import random
from typing import Any, Callable, Dict, Iterable, Literal, Mapping, Optional, Tuple

from nexus.agents.orrery.needs import normalize_need_type
from nexus.agents.orrery.status_family import (
    STATUS_LEVEL_RANKS,
    STATUS_TAG_PREFIX,
    normalize_status_level,
)


class EntityKind(str, Enum):
    """Entity kinds supported by the Orrery identity spine."""

    CHARACTER = "character"
    FACTION = "faction"
    PLACE = "place"


class Slot(str, Enum):
    """Typed parameter names a behavior package can bind."""

    ACTOR = "actor"
    TARGET = "target"
    TARGETS = "targets"
    LOCATION = "location"
    LOCATION_CLASS = "location_class"
    RESOURCE = "resource"
    THREAT = "threat"
    FACTION = "faction"


class PresentTargetPolicy(str, Enum):
    """How a package treats targets currently owned by the Storyteller scene."""

    OFFSCREEN_ONLY = "offscreen_only"
    STORYTELLER_PRESSURE = "storyteller_pressure"


class DriveBand(str, Enum):
    """Authoring-level package priority band.

    Drive bands explain why a package sits where it does in the priority
    ladder. They are not a replacement for static priority; they make unusual
    ordering choices visible so package composition stays intentional.
    """

    CRISIS_CONSTRAINT = "crisis_constraint"
    EMBODIED_MAINTENANCE = "embodied_maintenance"
    ANCHORED_ROUTINE = "anchored_routine"
    AFFILIATION = "affiliation"
    PROJECT_IDENTITY = "project_identity"


Bindings = Dict[Slot, Any]
Condition = Callable[["WorldState", Bindings], bool]
ContactKind = Literal["lodging", "social", "intimate"]
SUPPORTED_TRAVEL_PURPOSES: frozenset[str] = frozenset({"socialize"})
DRIVE_BAND_ORDER: Mapping[DriveBand, int] = {
    DriveBand.CRISIS_CONSTRAINT: 0,
    DriveBand.EMBODIED_MAINTENANCE: 1,
    DriveBand.ANCHORED_ROUTINE: 2,
    DriveBand.AFFILIATION: 3,
    DriveBand.PROJECT_IDENTITY: 4,
}

INTIMACY_SUPPRESSOR_TAGS: frozenset[str] = frozenset(
    {
        "closeted",
        "vow_of_celibacy",
        "religiously_abstinent",
        "grieving",
        "recently_traumatized_intimate",
        "focus_committed",
        "libido_absent",
    }
)
ESTABLISHED_PARTNER_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "romantic",
        "spouse",
        "lover",
        "partner",
        "romantic_partner",
    }
)
CONSTRAINED_TAGS: frozenset[str] = frozenset(
    {
        "captive",
        "contained",
        "dying",
        "immobile",
        "sandboxed",
        "unconscious",
    }
)
HIDDEN_TAGS: frozenset[str] = frozenset(
    {
        "deep_cover",
        "fugitive",
        "hidden_identity",
        "long_absent",
        "long_hidden",
        "off_grid",
        "presumed_dead",
        "presumed_dead_by_some",
        "wanted",
    }
)
PUBLIC_MOBILITY_TAGS: frozenset[str] = frozenset(
    {
        "broker",
        "courier",
        "field_worker",
        "fixer",
        "public_role",
        "route_familiar",
        "scout",
        "travel_ready",
    }
)
PUBLIC_PLACE_CLASSES: frozenset[str] = frozenset(
    {
        "commerce",
        "meeting",
        "place_open",
        "transit",
        "urban_dense",
        "urban_sparse",
        "water_source",
    }
)
DRAMATIC_CONTACT_TAGS: frozenset[str] = HIDDEN_TAGS | frozenset(
    {
        "long_estranged",
    }
)
CONTACT_PAIR_TAGS: Mapping[ContactKind, str] = {
    "lodging": "contact:lodging",
    "social": "contact:social",
    "intimate": "contact:intimate",
}
LOADED_TRUST_FORWARD_MIN = 2
LOADED_TRUST_REVERSE_MAX = -1

# Package self-awareness (issue #282): exclusive single-entity tier ladders the
# acting entity reads about *itself* during stage-2 branch selection. Ranks are
# vocabulary semantics (registry tag ordering), not tunable weights. Absence of
# a tier tag IS the default tier — the registry's documented default-absent
# pattern (`role.fame:obscure`, `role.resources:comfortable`).
FAME_TIER_RANKS: Mapping[str, int] = {
    "obscure": 0,
    "known": 1,
    "renowned": 2,
    "legendary": 3,
}
DEFAULT_FAME_TIER = "obscure"
RESOURCES_TIER_RANKS: Mapping[str, int] = {
    "destitute": 0,
    "poor": 1,
    "comfortable": 2,
    "wealthy": 3,
    "magnate": 4,
}
DEFAULT_RESOURCES_TIER = "comfortable"
# Fame predicates are stage-2/stage-3 vocabulary ONLY. Entry gating (stage 1)
# must never read fame; validate_no_fame_in_entry_gates enforces this.
_FAME_PREDICATE_NAME_PREFIXES: Tuple[str, ...] = (
    "fame_at_or_above(",
    "fame_below(",
)


@dataclass(frozen=True, slots=True)
class TravelState:
    """Read-side travel state for one character entity."""

    status: str = "at_place"
    anchor_place_id: Optional[int] = None
    origin_place_id: Optional[int] = None
    destination_place_id: Optional[int] = None
    route_method: str = "estimated"
    travel_mode: str = "mixed"
    risk: str = "low"
    progress_ratio: float = 0.0
    estimated_distance_m: Optional[float] = None
    estimated_duration_minutes: Optional[float] = None
    route_purpose: Optional[str] = None

    @property
    def is_in_transit(self) -> bool:
        """Return whether the character is currently between places."""

        return self.status == "in_transit"


@dataclass(frozen=True, slots=True)
class ProjectState:
    """Read-side state for one character's open project."""

    id: int
    project_type: str
    status: str
    stage: str
    target_place_id: Optional[int] = None
    target_character_entity_id: Optional[int] = None
    target_character_is_active: bool = False
    progress: float = 0.0
    stall_count: int = 0
    next_eligible_at_world_time: Optional[datetime] = None
    source_chunk_id: Optional[int] = None


@dataclass(frozen=True, slots=True)
class ProjectPolicy:
    """Runtime policy from [orrery.projects]."""

    enabled: bool = False
    advance_interval_hours: float = 24.0
    max_active_per_character: int = 1
    stall_abandon_threshold: int = 3
    abandon_after_stalled_world_hours: float = 168.0
    milestone_magnitude: float = 0.40
    coverage_distribution_tolerance: float = 0.05

    def __post_init__(self) -> None:
        if self.advance_interval_hours <= 0:
            raise ValueError("Project advance_interval_hours must be > 0")
        if self.max_active_per_character != 1:
            raise ValueError("Orrery projects require max_active_per_character = 1")
        if self.stall_abandon_threshold < 1:
            raise ValueError("Project stall_abandon_threshold must be >= 1")
        if self.abandon_after_stalled_world_hours <= 0:
            raise ValueError("Project abandon_after_stalled_world_hours must be > 0")
        if not 0 <= self.milestone_magnitude <= 1:
            raise ValueError("Project milestone_magnitude must be between 0 and 1")
        if not 0 < self.coverage_distribution_tolerance <= 1:
            raise ValueError(
                "Project coverage_distribution_tolerance must be in (0, 1]"
            )


def coerce_project_policy(raw: Any) -> ProjectPolicy:
    """Coerce [orrery.projects] config; None keeps the subsystem disabled."""

    if raw is None:
        return ProjectPolicy()
    if isinstance(raw, ProjectPolicy):
        return raw
    if isinstance(raw, Mapping):
        values = raw
    elif hasattr(raw, "advance_interval_hours"):
        values = {
            "advance_interval_hours": raw.advance_interval_hours,
            "max_active_per_character": raw.max_active_per_character,
            "stall_abandon_threshold": raw.stall_abandon_threshold,
            "abandon_after_stalled_world_hours": (
                raw.abandon_after_stalled_world_hours
            ),
            "milestone_magnitude": raw.milestone_magnitude,
            "coverage_distribution_tolerance": (raw.coverage_distribution_tolerance),
        }
    else:
        raise ValueError(f"Unsupported Orrery project settings: {type(raw)!r}")
    return ProjectPolicy(
        enabled=True,
        advance_interval_hours=float(values["advance_interval_hours"]),
        max_active_per_character=int(values["max_active_per_character"]),
        stall_abandon_threshold=int(values["stall_abandon_threshold"]),
        abandon_after_stalled_world_hours=float(
            values["abandon_after_stalled_world_hours"]
        ),
        milestone_magnitude=float(values["milestone_magnitude"]),
        coverage_distribution_tolerance=float(
            values.get("coverage_distribution_tolerance", 0.05)
        ),
    )


@dataclass(frozen=True, slots=True)
class RoutineAnchor:
    """Read-side home/work routine anchor for one character."""

    anchor_type: str
    place_id: Optional[int] = None
    zone_id: Optional[int] = None
    mobility_policy: str = "fixed_place"
    schedule: Mapping[str, Any] = field(default_factory=dict)

    @property
    def has_destination(self) -> bool:
        """Return whether this anchor can resolve to a concrete destination."""

        return self.mobility_policy in {
            "fixed_place",
            "zone_resolved",
            "works_from_home",
        }


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Compact read-side event shape consumed by condition predicates."""

    event_type: str
    tick: int
    event_id: Optional[int] = None
    actor_entity_id: Optional[int] = None
    target_entity_id: Optional[int] = None
    location_id: Optional[int] = None
    changed_fields: Tuple[str, ...] = ()
    world_layer: str = "primary"
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorldState:
    """Immutable snapshot read by package conditions for one resolver tick."""

    tags: Mapping[int, frozenset[str]] = field(default_factory=dict)
    ephemeral_tags: Mapping[int, frozenset[str]] = field(default_factory=dict)
    # Committed wins per (actor_entity_id, template_id) inside the
    # habituation window — hydrated from orrery_resolutions, so replay
    # reconstructs identical dampening. Empty when habituation is off.
    win_history: Mapping[Tuple[int, str], int] = field(default_factory=dict)
    locations: Mapping[int, int] = field(default_factory=dict)
    activities: Mapping[int, str] = field(default_factory=dict)
    trust: Mapping[Tuple[int, int], int] = field(default_factory=dict)
    relationship_types: Mapping[Tuple[int, int], frozenset[str]] = field(
        default_factory=dict
    )
    pair_tags: Mapping[Tuple[int, int], frozenset[str]] = field(default_factory=dict)
    faction_memberships: Mapping[int, frozenset[int]] = field(default_factory=dict)
    location_class: Mapping[int, str] = field(default_factory=dict)
    location_classes: Mapping[int, frozenset[str]] = field(default_factory=dict)
    location_entity_ids: Mapping[int, int] = field(default_factory=dict)
    location_zones: Mapping[int, int] = field(default_factory=dict)
    orbit_distance: Mapping[Tuple[int, int], int] = field(default_factory=dict)
    need_debt_scores: Mapping[Tuple[int, str], float] = field(default_factory=dict)
    travel_states: Mapping[int, TravelState] = field(default_factory=dict)
    project_states: Mapping[int, ProjectState] = field(default_factory=dict)
    project_policy: ProjectPolicy = field(default_factory=ProjectPolicy)
    routine_anchors: Mapping[Tuple[int, str], RoutineAnchor] = field(
        default_factory=dict
    )
    recent_events: Tuple[EventRecord, ...] = ()
    claimed_event_scopes: Mapping[int, str] = field(default_factory=dict)
    awareness_by_entity: Mapping[int, frozenset[int]] = field(default_factory=dict)
    epistemics_enabled: bool = False
    time_of_day: str = "midday"
    world_time: Optional[datetime] = None
    weather: str = "clear"
    current_tick: int = 0


def _slot_entity(bindings: Bindings, slot: Slot) -> Optional[int]:
    value = bindings.get(slot)
    return value if isinstance(value, int) else None


def _named(condition: Condition, name: str) -> Condition:
    condition.__name__ = name
    return condition


def _is_in_transit(state: WorldState, entity_id: int) -> bool:
    travel_state = state.travel_states.get(entity_id)
    return bool(travel_state and travel_state.is_in_transit)


def _has_outbound_pair_tag(state: WorldState, entity_id: int, pair_tag: str) -> bool:
    return any(
        subject_id == entity_id and pair_tag in tags
        for (subject_id, _object_id), tags in state.pair_tags.items()
    )


def _has_inbound_pair_tag(state: WorldState, entity_id: int, pair_tag: str) -> bool:
    return any(
        object_id == entity_id and pair_tag in tags
        for (_subject_id, object_id), tags in state.pair_tags.items()
    )


def has_tag(tag: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity has a durable tag."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        return entity_id is not None and tag in state.tags.get(entity_id, frozenset())

    return _named(_condition, f"has_tag({tag}@{slot.value})")


def lacks_tag(tag: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity lacks a durable tag."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        return entity_id is None or tag not in state.tags.get(entity_id, frozenset())

    return _named(_condition, f"lacks_tag({tag}@{slot.value})")


def has_any_tag(*tags: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity has any of the given tags."""

    candidates = frozenset(tags)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return bool(candidates & state.tags.get(entity_id, frozenset()))

    return _named(_condition, f"has_any_tag({','.join(tags)}@{slot.value})")


def has_pair_tag(
    tag: str,
    subject_slot: Slot = Slot.ACTOR,
    object_slot: Slot = Slot.TARGET,
) -> Condition:
    """Return whether a directed pair tag exists between two slot-bound entities."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        subject_id = _slot_entity(bindings, subject_slot)
        object_id = _slot_entity(bindings, object_slot)
        if subject_id is None or object_id is None:
            return False
        return tag in state.pair_tags.get((subject_id, object_id), frozenset())

    return _named(
        _condition,
        f"has_pair_tag({tag}@{subject_slot.value}->{object_slot.value})",
    )


def lacks_pair_tag(
    tag: str,
    subject_slot: Slot = Slot.ACTOR,
    object_slot: Slot = Slot.TARGET,
) -> Condition:
    """Return whether a directed pair tag is absent between slot-bound entities."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        subject_id = _slot_entity(bindings, subject_slot)
        object_id = _slot_entity(bindings, object_slot)
        if subject_id is None or object_id is None:
            return True
        return tag not in state.pair_tags.get((subject_id, object_id), frozenset())

    return _named(
        _condition,
        f"lacks_pair_tag({tag}@{subject_slot.value}->{object_slot.value})",
    )


def has_any_pair_tag(
    *tags: str,
    subject_slot: Slot = Slot.ACTOR,
    object_slot: Slot = Slot.TARGET,
) -> Condition:
    """Return whether any directed pair tag exists between slot-bound entities."""

    candidates = frozenset(tags)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        subject_id = _slot_entity(bindings, subject_slot)
        object_id = _slot_entity(bindings, object_slot)
        if subject_id is None or object_id is None:
            return False
        return bool(
            candidates & state.pair_tags.get((subject_id, object_id), frozenset())
        )

    return _named(
        _condition,
        f"has_any_pair_tag({','.join(tags)}@{subject_slot.value}->{object_slot.value})",
    )


def has_pair_tag_to_current_location(tag: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity has ``tag`` to its current place."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        location_id = state.locations.get(entity_id)
        if location_id is None:
            return False
        location_entity_id = state.location_entity_ids.get(location_id)
        if location_entity_id is None:
            return False
        return tag in state.pair_tags.get((entity_id, location_entity_id), frozenset())

    return _named(
        _condition,
        f"has_pair_tag_to_current_location({tag}@{slot.value})",
    )


def has_inbound_pair_tag(tag: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether any subject points ``tag`` at the slot-bound entity."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        return entity_id is not None and _has_inbound_pair_tag(state, entity_id, tag)

    return _named(_condition, f"has_inbound_pair_tag({tag}@{slot.value})")


def contact_pair_tag_for_kind(kind: ContactKind) -> str:
    """Return the pair-tag name for a kind-qualified contact edge."""

    try:
        return CONTACT_PAIR_TAGS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported contact kind: {kind!r}") from exc


def has_contact_of_kind(kind: ContactKind, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity has any outbound contact of ``kind``."""

    pair_tag = contact_pair_tag_for_kind(kind)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return _has_outbound_pair_tag(state, entity_id, pair_tag)

    return _named(_condition, f"has_contact_of_kind({kind}@{slot.value})")


def has_any_current_tag(*tags: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity has any durable or ephemeral tag."""

    candidates = frozenset(tags)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        current_tags = state.tags.get(
            entity_id, frozenset()
        ) | state.ephemeral_tags.get(entity_id, frozenset())
        return bool(candidates & current_tags)

    return _named(_condition, f"has_any_current_tag({','.join(tags)}@{slot.value})")


def _tier_rank(
    state: WorldState,
    entity_id: int,
    ranks: Mapping[str, int],
    default_tier: str,
    ladder: str,
) -> int:
    """Return an entity's rank on an exclusive tier ladder (durable tags).

    Tier ladders are exclusive-cardinality registry categories: an entity
    carrying more than one tier tag on the same ladder is corrupt state, and
    corrupt state must surface loudly rather than be quietly resolved.
    """

    present = sorted(
        tag for tag in state.tags.get(entity_id, frozenset()) if tag in ranks
    )
    if len(present) > 1:
        raise ValueError(
            f"Entity {entity_id} holds multiple {ladder} tier tags {present}; "
            f"{ladder} is an exclusive ladder"
        )
    if present:
        return ranks[present[0]]
    return ranks[default_tier]


def _validate_tier(tier: str, ranks: Mapping[str, int], ladder: str) -> str:
    normalized = str(tier).strip()
    if normalized not in ranks:
        raise ValueError(
            f"Unknown {ladder} tier {tier!r}; expected one of {sorted(ranks)}"
        )
    return normalized


def fame_at_or_above(tier: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity's own fame meets a tier threshold.

    Fame is an unvalenced ambient detection radius (inverse stealth); absence
    of a ``role.fame`` tag reads as ``obscure``. Stage-2/3 vocabulary only —
    never use this in a package gate (stage 1 entry gating).
    """

    normalized = _validate_tier(tier, FAME_TIER_RANKS, "fame")
    threshold = FAME_TIER_RANKS[normalized]

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return (
            _tier_rank(state, entity_id, FAME_TIER_RANKS, DEFAULT_FAME_TIER, "fame")
            >= threshold
        )

    return _named(_condition, f"fame_at_or_above({normalized}@{slot.value})")


def fame_below(tier: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity's own fame is below a tier threshold.

    Same stage discipline as :func:`fame_at_or_above`: stage-2/3 only.
    """

    normalized = _validate_tier(tier, FAME_TIER_RANKS, "fame")
    threshold = FAME_TIER_RANKS[normalized]

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return (
            _tier_rank(state, entity_id, FAME_TIER_RANKS, DEFAULT_FAME_TIER, "fame")
            < threshold
        )

    return _named(_condition, f"fame_below({normalized}@{slot.value})")


def resources_at_or_above(tier: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity's own wealth meets a tier threshold.

    Absence of a ``role.resources`` tag reads as ``comfortable`` per the
    registry's default-absent pattern.
    """

    normalized = _validate_tier(tier, RESOURCES_TIER_RANKS, "resources")
    threshold = RESOURCES_TIER_RANKS[normalized]

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return (
            _tier_rank(
                state,
                entity_id,
                RESOURCES_TIER_RANKS,
                DEFAULT_RESOURCES_TIER,
                "resources",
            )
            >= threshold
        )

    return _named(_condition, f"resources_at_or_above({normalized}@{slot.value})")


def resources_below(tier: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity's own wealth is below a tier threshold."""

    normalized = _validate_tier(tier, RESOURCES_TIER_RANKS, "resources")
    threshold = RESOURCES_TIER_RANKS[normalized]

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return (
            _tier_rank(
                state,
                entity_id,
                RESOURCES_TIER_RANKS,
                DEFAULT_RESOURCES_TIER,
                "resources",
            )
            < threshold
        )

    return _named(_condition, f"resources_below({normalized}@{slot.value})")


def has_any_status_at_or_above(threshold: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether the entity holds outbound status at a rank, in any scope.

    Status is scope-bound (``status:<level>`` pair tags, subject → faction);
    this is the self-scoped read: does the acting entity hold standing at or
    above ``threshold`` toward *any* scope faction. Negative levels never
    satisfy a positive threshold because ranks are ordered.
    """

    normalized = normalize_status_level(threshold)
    threshold_rank = STATUS_LEVEL_RANKS[normalized]

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        # Known cost: O(total pair-tag relationships) per evaluation, the
        # same shape as _has_outbound_pair_tag / _has_inbound_pair_tag.
        # WorldState.pair_tags is keyed by (subject, object) with no subject
        # index; if stage-3 encounter rolls make this measurable, add a
        # derived pair_tags_by_subject map at hydration rather than here.
        for (subject_id, _object_id), tags in state.pair_tags.items():
            if subject_id != entity_id:
                continue
            for tag in tags:
                if not tag.startswith(STATUS_TAG_PREFIX):
                    continue
                level = tag.removeprefix(STATUS_TAG_PREFIX)
                rank = STATUS_LEVEL_RANKS.get(level)
                if rank is not None and rank >= threshold_rank:
                    return True
        return False

    return _named(
        _condition,
        f"has_any_status_at_or_above({normalized}@{slot.value})",
    )


def has_ephemeral(tag: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity has a current ephemeral tag."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        return entity_id is not None and tag in state.ephemeral_tags.get(
            entity_id, frozenset()
        )

    return _named(_condition, f"has_ephemeral({tag}@{slot.value})")


def has_minimal_context(slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether Orrery has enough substrate to reason about an entity."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        if state.tags.get(entity_id) or state.ephemeral_tags.get(entity_id):
            return True
        if entity_id in state.locations or entity_id in state.activities:
            return True
        if entity_id in state.travel_states:
            return True
        return any(
            event.actor_entity_id == entity_id or event.target_entity_id == entity_id
            for event in state.recent_events
        )

    return _named(_condition, f"has_minimal_context(@{slot.value})")


def is_constrained(slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity is not free to act off-screen."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        current_tags = state.tags.get(
            entity_id, frozenset()
        ) | state.ephemeral_tags.get(entity_id, frozenset())
        return bool(CONSTRAINED_TAGS & current_tags)

    return _named(_condition, f"is_constrained(@{slot.value})")


def is_hidden(slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity is living under concealment."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        current_tags = state.tags.get(
            entity_id, frozenset()
        ) | state.ephemeral_tags.get(entity_id, frozenset())
        return bool(HIDDEN_TAGS & current_tags)

    return _named(_condition, f"is_hidden(@{slot.value})")


def can_move_publicly(slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether public-flow movement is plausible for the entity."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None or _is_in_transit(state, entity_id):
            return False
        current_tags = state.tags.get(
            entity_id, frozenset()
        ) | state.ephemeral_tags.get(entity_id, frozenset())
        if CONSTRAINED_TAGS & current_tags:
            return False
        if PUBLIC_MOBILITY_TAGS & current_tags:
            return True
        if _has_outbound_pair_tag(state, entity_id, CONTACT_PAIR_TAGS["social"]):
            return True
        location_id = state.locations.get(entity_id)
        if location_id is None:
            return False
        semantic_classes = state.location_classes.get(location_id, frozenset())
        if PUBLIC_PLACE_CLASSES & semantic_classes:
            return True
        location_class = state.location_class.get(location_id)
        return bool(location_class and location_class in PUBLIC_PLACE_CLASSES)

    return _named(_condition, f"can_move_publicly(@{slot.value})")


def has_any_intimacy_suppressor(slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity carries an intimacy suppressor.

    Suppressors may be durable identity/context tags or ephemeral conditions.
    The predicate intentionally treats ``libido_absent`` as a suppressor so
    intimacy rows can exist without forcing intimacy behavior for characters
    whose identity makes the need inapplicable.
    """

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        tags = state.tags.get(entity_id, frozenset()) | state.ephemeral_tags.get(
            entity_id, frozenset()
        )
        return bool(INTIMACY_SUPPRESSOR_TAGS & tags)

    return _named(_condition, f"has_any_intimacy_suppressor(@{slot.value})")


def has_severity_tag(prefix: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity has any tag in a severity track."""

    marker = f"{prefix}_"

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        tags = state.tags.get(entity_id, frozenset()) | state.ephemeral_tags.get(
            entity_id, frozenset()
        )
        return any(tag.startswith(marker) for tag in tags)

    return _named(_condition, f"has_severity_tag({prefix}@{slot.value})")


def has_severity_tag_at_or_above(
    prefix: str,
    level: int,
    slot: Slot = Slot.ACTOR,
) -> Condition:
    """Return whether a slot-bound entity has a severity tag at a threshold."""

    marker = f"{prefix}_"

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        tags = state.tags.get(entity_id, frozenset()) | state.ephemeral_tags.get(
            entity_id, frozenset()
        )
        for tag in tags:
            if not tag.startswith(marker):
                continue
            remainder = tag.removeprefix(marker)
            numeric, _sep, _label = remainder.partition("_")
            try:
                if int(numeric) >= level:
                    return True
            except ValueError:
                continue
        return False

    return _named(
        _condition,
        f"has_severity_tag_at_or_above({prefix},{level}@{slot.value})",
    )


def has_need_debt_at_or_above(
    need_type: str,
    threshold: float,
    slot: Slot = Slot.ACTOR,
) -> Condition:
    """Return whether a slot-bound entity has need debt at the threshold."""

    normalized = normalize_need_type(need_type)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return state.need_debt_scores.get((entity_id, normalized), 0.0) >= threshold

    return _named(
        _condition,
        f"has_need_debt_at_or_above({normalized},{threshold:g}@{slot.value})",
    )


def in_location_class(location_class: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether an entity is currently in a place of the given class.

    Location classes are semantic place tags first. ``state.location_class``
    remains as a single-value fallback for directly constructed ``WorldState``
    instances and structural ``places.type`` values.
    """

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        if _is_in_transit(state, entity_id):
            return False
        location_id = state.locations.get(entity_id)
        if location_id is None:
            return False
        semantic_classes = state.location_classes.get(location_id, frozenset())
        return (
            location_class in semantic_classes
            or state.location_class.get(location_id) == location_class
        )

    return _named(_condition, f"in_location_class({location_class}@{slot.value})")


def has_location_class_destination(
    *location_classes: str,
    slot: Slot = Slot.ACTOR,
) -> Condition:
    """Return whether the actor can target another place by semantic class."""

    classes = tuple(dict.fromkeys(str(item) for item in location_classes if str(item)))
    if not classes:
        raise ValueError("has_location_class_destination requires at least one class")
    class_set = frozenset(classes)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None or _is_in_transit(state, entity_id):
            return False
        current_place_id = state.locations.get(entity_id)
        if current_place_id is None:
            return False
        for place_id, semantic_classes in state.location_classes.items():
            if place_id == current_place_id:
                continue
            if class_set & semantic_classes:
                return True
        for place_id, location_class in state.location_class.items():
            if place_id == current_place_id:
                continue
            if location_class in class_set:
                return True
        return False

    class_names = ",".join(classes)
    return _named(
        _condition,
        f"has_location_class_destination({class_names}@{slot.value})",
    )


def in_location(location_id: int, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether an entity is currently at a specific place id."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        return (
            entity_id is not None
            and not _is_in_transit(state, entity_id)
            and state.locations.get(entity_id) == location_id
        )

    return _named(_condition, f"in_location({location_id}@{slot.value})")


def co_located(slot_a: Slot = Slot.ACTOR, slot_b: Slot = Slot.TARGET) -> Condition:
    """Return whether two slot-bound entities share a current location."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        left = _slot_entity(bindings, slot_a)
        right = _slot_entity(bindings, slot_b)
        if left is None or right is None:
            return False
        if _is_in_transit(state, left) or _is_in_transit(state, right):
            return False
        location_id = state.locations.get(left)
        return location_id is not None and location_id == state.locations.get(right)

    return _named(_condition, f"co_located({slot_a.value},{slot_b.value})")


def count_co_located(
    minimum: int,
    slot: Slot = Slot.ACTOR,
    *,
    with_tag: Optional[str] = None,
    with_ephemeral: Optional[str] = None,
) -> Condition:
    """Return whether enough entities share the slot entity's current location.

    Filters by ``with_tag`` against the durable ``state.tags`` map; filters
    by ``with_ephemeral`` against ``state.ephemeral_tags``. Both filters can
    be combined; both default to None (no tag filter).
    """

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        if _is_in_transit(state, entity_id):
            return False
        location_id = state.locations.get(entity_id)
        if location_id is None:
            return False
        count = 0
        for other_id, other_location in state.locations.items():
            if other_id == entity_id or other_location != location_id:
                continue
            if _is_in_transit(state, other_id):
                continue
            if with_tag and with_tag not in state.tags.get(other_id, frozenset()):
                continue
            if with_ephemeral and with_ephemeral not in state.ephemeral_tags.get(
                other_id, frozenset()
            ):
                continue
            count += 1
        return count >= minimum

    filters = []
    if with_tag:
        filters.append(f"tag={with_tag}")
    if with_ephemeral:
        filters.append(f"ephemeral={with_ephemeral}")
    suffix = "," + ",".join(filters) if filters else ""
    return _named(_condition, f"count_co_located({minimum}@{slot.value}{suffix})")


def has_established_partner_co_located(slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether the actor is co-located with an established partner.

    This intentionally reads existing relationship rows rather than deriving
    intimate compatibility. Orrery may notice an established relationship and
    shared place; it does not choose a new partner.
    """

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        if _is_in_transit(state, entity_id):
            return False
        location_id = state.locations.get(entity_id)
        if location_id is None:
            return False
        for (source, target), relationship_types in state.relationship_types.items():
            if entity_id not in (source, target):
                continue
            if not (ESTABLISHED_PARTNER_RELATIONSHIP_TYPES & relationship_types):
                continue
            partner_id = target if source == entity_id else source
            if (
                not _is_in_transit(state, partner_id)
                and state.locations.get(partner_id) == location_id
            ):
                return True
        return False

    return _named(_condition, f"has_established_partner_co_located(@{slot.value})")


def is_in_transit(slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound character is currently between places."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        return entity_id is not None and _is_in_transit(state, entity_id)

    return _named(_condition, f"is_in_transit(@{slot.value})")


def project_overdue_hours(world_time: Any, next_eligible_at_world_time: Any) -> float:
    """Shared overdue computation for the project_due predicate AND the
    explain/coverage evidence display — one formula so the dashboard can
    never silently diverge from the actual abandonment decision."""

    return max(
        0.0,
        (world_time - next_eligible_at_world_time).total_seconds() / 3600.0,
    )


_PROJECT_DUE_MODES = frozenset(
    {
        "start",
        "exists",
        "ready",
        "abandon",
        "saving",
        "scouting",
        "committing",
        "saving_milestone",
        "scouting_without_target",
        "scouting_milestone",
        "completion",
        "neglected",
        "sounding_out",
        "earning_trust",
        "sealing_commitment",
        "sounding_out_milestone",
        "earning_trust_milestone",
    }
)

_PROJECT_STAGE_LADDERS = {
    "plan_relocation": ("saving", "scouting", "committing"),
    "recruit_ally": ("sounding_out", "earning_trust", "sealing_commitment"),
}


def project_due(
    mode: str = "ready",
    *,
    project_type: str = "plan_relocation",
    slot: Slot = Slot.ACTOR,
) -> Condition:
    """Return a configured project lifecycle/due-ness verdict.

    ``project_due`` is deliberately the one project predicate authority used
    by production, explain, and coverage. Besides the base cadence verdict it
    exposes the stage/milestone cases templates need, and the deterministic
    abandonment case (stall threshold OR overdue world hours). ``start`` means
    the configured subsystem is enabled and no open project exists.
    """

    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in _PROJECT_DUE_MODES:
        raise ValueError(
            f"Unsupported project_due mode {mode!r}; expected one of "
            f"{sorted(_PROJECT_DUE_MODES)}"
        )
    if project_type not in _PROJECT_STAGE_LADDERS:
        raise ValueError(
            f"Unsupported project_due project type {project_type!r}; "
            f"expected one of {sorted(_PROJECT_STAGE_LADDERS)}"
        )
    project_stages = _PROJECT_STAGE_LADDERS[project_type]
    type_modes = {
        "start",
        "exists",
        "ready",
        "abandon",
        "completion",
        "neglected",
        *project_stages,
        *(f"{stage}_milestone" for stage in project_stages[:-1]),
    }
    if project_type == "plan_relocation":
        type_modes.add("scouting_without_target")
    if normalized_mode not in type_modes:
        raise ValueError(
            f"project_due mode {normalized_mode!r} is not valid for project "
            f"type {project_type!r}; expected one of {sorted(type_modes)}"
        )

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        policy = state.project_policy
        if not policy.enabled:
            return False
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        project = state.project_states.get(entity_id)
        if normalized_mode == "start":
            return project is None
        if project is not None and project.project_type not in _PROJECT_STAGE_LADDERS:
            raise ValueError(
                f"Actor {entity_id} has unsupported open project type "
                f"{project.project_type!r}"
            )
        if project is not None and project.project_type != project_type:
            return False
        if normalized_mode == "exists":
            return project is not None
        if project is None:
            return False
        if project.status not in {"active", "paused", "stalled"}:
            raise ValueError(
                f"Hydrated project {project.id} is not open: {project.status!r}"
            )
        if project.next_eligible_at_world_time is None:
            raise ValueError(
                f"Open project {project.id} lacks next_eligible_at_world_time"
            )
        if state.world_time is None:
            raise ValueError(
                f"Cannot evaluate project {project.id} due-ness without world_time"
            )
        due = project.next_eligible_at_world_time <= state.world_time
        if normalized_mode == "ready":
            return due
        overdue_hours = project_overdue_hours(
            state.world_time, project.next_eligible_at_world_time
        )
        if normalized_mode == "abandon":
            return due and (
                project.stall_count >= policy.stall_abandon_threshold
                or overdue_hours >= policy.abandon_after_stalled_world_hours
            )
        if normalized_mode == "neglected":
            # A setback is diegetic, not dice: the plan lost ground because
            # a full cadence interval passed unattended. Non-tautological by
            # construction, so authored_order/deterministic selection can
            # never stall a promptly-advanced project (PR #494 review).
            return due and overdue_hours >= policy.advance_interval_hours
        if not due:
            return False
        if normalized_mode in project_stages:
            return project.stage == normalized_mode
        if normalized_mode == f"{project_stages[0]}_milestone":
            return project.stage == project_stages[0] and project.progress >= 1.0
        if normalized_mode == "scouting_without_target":
            return (
                project_type == "plan_relocation"
                and project.stage == "scouting"
                and project.target_place_id is None
            )
        if normalized_mode == f"{project_stages[1]}_milestone":
            return (
                project.stage == project_stages[1]
                and (
                    project.target_place_id is not None
                    if project_type == "plan_relocation"
                    else project.target_character_entity_id is not None
                )
                and project.progress >= 1.0
            )
        if normalized_mode == "completion":
            return (
                project.stage == project_stages[2]
                and (
                    project.target_place_id is not None
                    if project_type == "plan_relocation"
                    else project.target_character_entity_id is not None
                )
                and project.progress >= 1.0
            )
        raise AssertionError(f"Unhandled project_due mode {normalized_mode!r}")

    return _named(
        _condition,
        f"project_due({project_type},{normalized_mode}@{slot.value})",
    )


def project_target_is(slot: Slot = Slot.TARGET) -> Condition:
    """Return whether ``slot`` is the actor's character-project target."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        actor_entity_id = _slot_entity(bindings, Slot.ACTOR)
        target_entity_id = _slot_entity(bindings, slot)
        if actor_entity_id is None or target_entity_id is None:
            return False
        project = state.project_states.get(actor_entity_id)
        return bool(
            project is not None
            and project.target_character_entity_id == target_entity_id
        )

    return _named(_condition, f"project_target_is({slot.value})")


def project_target_is_active(slot: Slot = Slot.TARGET) -> Condition:
    """Return whether the bound project target is an active character.

    Target identity and availability are separate predicates so a durable
    project can keep binding its original target after that entity retires or
    changes kind, then deterministically abandon instead of stranding the
    actor's one-open-project budget.
    """

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        actor_entity_id = _slot_entity(bindings, Slot.ACTOR)
        target_entity_id = _slot_entity(bindings, slot)
        if actor_entity_id is None or target_entity_id is None:
            return False
        project = state.project_states.get(actor_entity_id)
        return bool(
            project is not None
            and project.target_character_entity_id == target_entity_id
            and project.target_character_is_active
        )

    return _named(_condition, f"project_target_is_active({slot.value})")


def has_travel_destination(slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound character has a planned destination."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        travel_state = state.travel_states.get(entity_id)
        return bool(travel_state and travel_state.destination_place_id is not None)

    return _named(_condition, f"has_travel_destination(@{slot.value})")


def has_routine_anchor(anchor_type: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether the slot-bound actor has an active routine anchor."""

    normalized = str(anchor_type)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        anchor = _routine_anchor(state, entity_id, normalized)
        return bool(anchor and anchor.mobility_policy not in {"none", "nomadic"})

    return _named(_condition, f"has_routine_anchor({normalized}@{slot.value})")


def routine_anchor_due(anchor_type: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether the actor's anchor is scheduled for the current time."""

    normalized = str(anchor_type)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        anchor = _routine_anchor(state, entity_id, normalized)
        if anchor is None or anchor.mobility_policy in {"none", "nomadic"}:
            return False
        return _routine_schedule_due(anchor.schedule, state.world_time)

    return _named(_condition, f"routine_anchor_due({normalized}@{slot.value})")


def at_routine_anchor(anchor_type: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether the actor is currently at the named routine anchor."""

    normalized = str(anchor_type)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return _at_routine_anchor(state, entity_id, normalized)

    return _named(_condition, f"at_routine_anchor({normalized}@{slot.value})")


def away_from_routine_anchor(anchor_type: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether the actor is not currently at the named routine anchor."""

    normalized = str(anchor_type)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        anchor = _routine_anchor(state, entity_id, normalized)
        if anchor is None or anchor.mobility_policy in {"none", "nomadic"}:
            return False
        return not _at_routine_anchor(state, entity_id, normalized)

    return _named(_condition, f"away_from_routine_anchor({normalized}@{slot.value})")


def routine_anchor_has_destination(
    anchor_type: str,
    slot: Slot = Slot.ACTOR,
) -> Condition:
    """Return whether the actor's anchor can resolve to a place destination."""

    normalized = str(anchor_type)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        return _routine_anchor_destination_available(state, entity_id, normalized)

    return _named(
        _condition,
        f"routine_anchor_has_destination({normalized}@{slot.value})",
    )


def _routine_anchor(
    state: WorldState,
    entity_id: int,
    anchor_type: str,
) -> Optional[RoutineAnchor]:
    return state.routine_anchors.get((entity_id, anchor_type))


def _at_routine_anchor(state: WorldState, entity_id: int, anchor_type: str) -> bool:
    anchor = _routine_anchor(state, entity_id, anchor_type)
    if anchor is None or anchor.mobility_policy in {"none", "nomadic"}:
        return False
    if anchor.mobility_policy == "works_from_home":
        if anchor_type == "home":
            return False
        return _at_routine_anchor(state, entity_id, "home")
    current_place_id = state.locations.get(entity_id)
    if current_place_id is None:
        return False
    if anchor.place_id is not None:
        return current_place_id == anchor.place_id
    if anchor.zone_id is not None:
        return state.location_zones.get(current_place_id) == anchor.zone_id
    return False


def _routine_anchor_destination_available(
    state: WorldState,
    entity_id: int,
    anchor_type: str,
    seen: frozenset[str] = frozenset(),
) -> bool:
    if anchor_type in seen:
        return False
    anchor = _routine_anchor(state, entity_id, anchor_type)
    if anchor is None or anchor.mobility_policy in {"none", "nomadic"}:
        return False
    if anchor.mobility_policy == "fixed_place":
        return anchor.place_id is not None
    if anchor.mobility_policy == "zone_resolved":
        return anchor.zone_id is not None and anchor.zone_id in set(
            state.location_zones.values()
        )
    if anchor.mobility_policy == "works_from_home":
        if anchor_type == "home":
            return False
        return _routine_anchor_destination_available(
            state,
            entity_id,
            "home",
            seen | {anchor_type},
        )
    return False


def _routine_schedule_due(
    schedule: Mapping[str, Any],
    world_time: Optional[datetime],
) -> bool:
    if world_time is None or not schedule:
        return True
    weekdays = schedule.get("weekdays")
    if weekdays is not None and world_time.weekday() not in {
        int(day) for day in weekdays
    }:
        return False
    start = _minute_of_day(schedule.get("start"))
    end = _minute_of_day(schedule.get("end"))
    if start is None or end is None:
        return True
    minute = world_time.hour * 60 + world_time.minute
    if start <= end:
        return start <= minute < end
    return minute >= start or minute < end


def _minute_of_day(value: Any) -> Optional[int]:
    if value is None:
        return None
    raw = str(value)
    parts = raw.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Routine schedule time must be HH:MM, got {raw!r}")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"Routine schedule time must be HH:MM, got {raw!r}") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Routine schedule time out of range: {raw!r}")
    return hour * 60 + minute


def travel_progress_at_or_above(
    threshold: float,
    slot: Slot = Slot.ACTOR,
) -> Condition:
    """Return whether travel progress is at or above a ratio threshold."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        travel_state = state.travel_states.get(entity_id)
        if travel_state is None:
            return False
        return travel_state.progress_ratio >= threshold

    return _named(
        _condition,
        f"travel_progress_at_or_above({threshold:g}@{slot.value})",
    )


def travel_purpose_is(*purposes: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether current travel state carries one of the given purposes."""

    purpose_values = tuple(
        dict.fromkeys(
            normalized for item in purposes if (normalized := str(item).strip().lower())
        )
    )
    if not purpose_values:
        raise ValueError("travel_purpose_is requires at least one purpose")
    unsupported = set(purpose_values) - SUPPORTED_TRAVEL_PURPOSES
    if unsupported:
        raise ValueError(
            f"Unsupported Orrery travel purpose(s): {sorted(unsupported)!r}"
        )
    candidates = frozenset(purpose_values)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        travel_state = state.travel_states.get(entity_id)
        if travel_state is None or travel_state.route_purpose is None:
            return False
        return str(travel_state.route_purpose).strip().lower() in candidates

    purpose_names = ",".join(purpose_values)
    return _named(_condition, f"travel_purpose_is({purpose_names}@{slot.value})")


def travel_risk_is(*risks: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether current travel state has one of the given risk labels."""

    candidates = frozenset(risks)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        travel_state = state.travel_states.get(entity_id)
        return bool(travel_state and travel_state.risk in candidates)

    return _named(
        _condition,
        f"travel_risk_is({','.join(risks)}@{slot.value})",
    )


def trust_at_least(
    threshold: int,
    slot_from: Slot = Slot.ACTOR,
    slot_to: Slot = Slot.TARGET,
) -> Condition:
    """Return whether trust from one entity to another meets a threshold."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        source = _slot_entity(bindings, slot_from)
        target = _slot_entity(bindings, slot_to)
        if source is None or target is None:
            return False
        return state.trust.get((source, target), 0) >= threshold

    return _named(
        _condition, f"trust_at_least({threshold},{slot_from.value}->{slot_to.value})"
    )


def trust_below(
    threshold: int,
    slot_from: Slot = Slot.ACTOR,
    slot_to: Slot = Slot.TARGET,
) -> Condition:
    """Return whether trust from one entity to another is below a threshold."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        source = _slot_entity(bindings, slot_from)
        target = _slot_entity(bindings, slot_to)
        if source is None or target is None:
            return False
        return state.trust.get((source, target), 0) < threshold

    return _named(
        _condition, f"trust_below({threshold},{slot_from.value}->{slot_to.value})"
    )


def relationship_is_mutual_warm(
    slot_a: Slot = Slot.ACTOR,
    slot_b: Slot = Slot.TARGET,
) -> Condition:
    """Return whether two entities have enough mutual trust for warm contact."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        source = _slot_entity(bindings, slot_a)
        target = _slot_entity(bindings, slot_b)
        if source is None or target is None:
            return False
        return (
            state.trust.get((source, target), 0) >= 2
            and state.trust.get((target, source), 0) >= 1
        )

    return _named(
        _condition,
        f"relationship_is_mutual_warm({slot_a.value}<->{slot_b.value})",
    )


def relationship_is_asymmetric(
    threshold: int = 3,
    slot_a: Slot = Slot.ACTOR,
    slot_b: Slot = Slot.TARGET,
) -> Condition:
    """Return whether directional trust is dramatically lopsided."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        source = _slot_entity(bindings, slot_a)
        target = _slot_entity(bindings, slot_b)
        if source is None or target is None:
            return False
        forward = state.trust.get((source, target), 0)
        reverse = state.trust.get((target, source), 0)
        return _trust_values_are_asymmetric(forward, reverse, threshold)

    return _named(
        _condition,
        f"relationship_is_asymmetric({threshold},{slot_a.value}<->{slot_b.value})",
    )


def direct_contact_is_dramatic(
    slot_from: Slot = Slot.ACTOR,
    slot_to: Slot = Slot.TARGET,
) -> Condition:
    """Return whether direct contact should be treated as a story beat."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        source = _slot_entity(bindings, slot_from)
        target = _slot_entity(bindings, slot_to)
        if source is None or target is None:
            return False
        source_tags = state.tags.get(source, frozenset()) | state.ephemeral_tags.get(
            source, frozenset()
        )
        target_tags = state.tags.get(target, frozenset()) | state.ephemeral_tags.get(
            target, frozenset()
        )
        if DRAMATIC_CONTACT_TAGS & (source_tags | target_tags):
            return True
        forward = state.trust.get((source, target), 0)
        reverse = state.trust.get((target, source), 0)
        if reverse <= -2:
            return True
        return _trust_values_are_asymmetric(forward, reverse)

    return _named(
        _condition,
        f"direct_contact_is_dramatic({slot_from.value}->{slot_to.value})",
    )


def _trust_values_are_asymmetric(
    forward: int,
    reverse: int,
    threshold: int = 3,
) -> bool:
    """Return whether trust values are lopsided or one-sided warm/resentful."""

    return abs(forward - reverse) >= threshold or (
        forward >= LOADED_TRUST_FORWARD_MIN and reverse <= LOADED_TRUST_REVERSE_MAX
    )


def has_relationship_of_type(
    relationship_type: str,
    slot_from: Slot = Slot.ACTOR,
    slot_to: Slot = Slot.TARGET,
) -> Condition:
    """Return whether a typed relationship exists between two entities."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        source = _slot_entity(bindings, slot_from)
        target = _slot_entity(bindings, slot_to)
        if source is None or target is None:
            return False
        return relationship_type in state.relationship_types.get(
            (source, target), frozenset()
        )

    return _named(
        _condition,
        "has_relationship_of_type("
        f"{relationship_type},{slot_from.value}->{slot_to.value})",
    )


def has_symmetric_relationship_of_type(
    relationship_type: str,
    slot_a: Slot = Slot.ACTOR,
    slot_b: Slot = Slot.TARGET,
) -> Condition:
    """Return whether a directionally-symmetric typed relationship exists.

    WorldState hydration stores each relationship row in its stored direction
    only, preserving asymmetric semantics for handler/asset and similar pairs.
    Templates wanting symmetric semantics (family, romantic, comrade) check
    both directions; this helper expresses that intent without an explicit OR.
    """

    forward = has_relationship_of_type(relationship_type, slot_a, slot_b)
    reverse = has_relationship_of_type(relationship_type, slot_b, slot_a)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        return forward(state, bindings) or reverse(state, bindings)

    return _named(
        _condition,
        "has_symmetric_relationship_of_type("
        f"{relationship_type},{slot_a.value}<->{slot_b.value})",
    )


def faction_member(
    faction_slot: Slot = Slot.FACTION,
    member_slot: Slot = Slot.ACTOR,
) -> Condition:
    """Return whether a member entity belongs to a faction entity."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        member_id = _slot_entity(bindings, member_slot)
        faction_id = _slot_entity(bindings, faction_slot)
        if member_id is None or faction_id is None:
            return False
        return faction_id in state.faction_memberships.get(member_id, frozenset())

    return _named(
        _condition, f"faction_member({member_slot.value}->{faction_slot.value})"
    )


def relative_orbit_distance(
    max_distance: int,
    slot_from: Slot = Slot.ACTOR,
    slot_to: Slot = Slot.TARGET,
) -> Condition:
    """Return whether two entities are within an abstract social orbit distance."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        source = _slot_entity(bindings, slot_from)
        target = _slot_entity(bindings, slot_to)
        if source is None or target is None:
            return False
        distance = state.orbit_distance.get((source, target))
        return distance is not None and distance <= max_distance

    return _named(
        _condition,
        f"relative_orbit_distance(<={max_distance},{slot_from.value}->{slot_to.value})",
    )


def time_of_day_in(*times: str) -> Condition:
    """Return whether current in-world time of day is in the given set."""

    candidates = frozenset(times)

    def _condition(state: WorldState, _bindings: Bindings) -> bool:
        return state.time_of_day in candidates

    return _named(_condition, f"time_of_day_in({','.join(times)})")


def weather_is(*weather_values: str) -> Condition:
    """Return whether current weather is in the given set."""

    candidates = frozenset(weather_values)

    def _condition(state: WorldState, _bindings: Bindings) -> bool:
        return state.weather in candidates

    return _named(_condition, f"weather_is({','.join(weather_values)})")


def recent_event(
    event_type: Optional[str] = None,
    *,
    within_ticks: int = 5,
    actor_slot: Optional[Slot] = None,
    target_slot: Optional[Slot] = None,
    changed_fields_any_of: Iterable[str] = (),
) -> Condition:
    """Return whether a matching event happened inside the recent tick window."""

    changed_fields = frozenset(changed_fields_any_of)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        actor_id = _slot_entity(bindings, actor_slot) if actor_slot else None
        target_id = _slot_entity(bindings, target_slot) if target_slot else None
        if actor_slot is not None and actor_id is None:
            return False
        if target_slot is not None and target_id is None:
            return False
        cutoff = state.current_tick - within_ticks
        for event in state.recent_events:
            if event.tick < cutoff:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            if actor_id is not None and event.actor_entity_id != actor_id:
                continue
            if target_id is not None and event.target_entity_id != target_id:
                continue
            if changed_fields and not changed_fields.intersection(event.changed_fields):
                continue
            return True
        return False

    parts = [event_type or "*", f"<={within_ticks}"]
    if actor_slot:
        parts.append(f"actor={actor_slot.value}")
    if target_slot:
        parts.append(f"target={target_slot.value}")
    if changed_fields:
        parts.append("fields")
    return _named(_condition, f"recent_event({','.join(parts)})")


def knows_recent_event(
    event_type: Optional[str] = None,
    *,
    within_ticks: int = 5,
    actor_slot: Optional[Slot] = None,
    target_slot: Optional[Slot] = None,
    changed_fields_any_of: Iterable[str] = (),
) -> Condition:
    """Return whether the actor knows a matching recent event.

    Events without claims and common-scope claims remain visible to every
    actor. Bounded/private claims require an awareness row for the entity
    bound to :class:`Slot.ACTOR`. Disabling Epistemics makes this predicate
    exactly equivalent to :func:`recent_event`.
    """

    changed_fields = frozenset(changed_fields_any_of)

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        knower_id = _slot_entity(bindings, Slot.ACTOR)
        if state.epistemics_enabled and knower_id is None:
            return False
        actor_id = _slot_entity(bindings, actor_slot) if actor_slot else None
        target_id = _slot_entity(bindings, target_slot) if target_slot else None
        if actor_slot is not None and actor_id is None:
            return False
        if target_slot is not None and target_id is None:
            return False
        cutoff = state.current_tick - within_ticks
        known_events: frozenset[int] = frozenset()
        if knower_id is not None:
            known_events = state.awareness_by_entity.get(knower_id, frozenset())
        for event in state.recent_events:
            if event.tick < cutoff:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            if actor_id is not None and event.actor_entity_id != actor_id:
                continue
            if target_id is not None and event.target_entity_id != target_id:
                continue
            if changed_fields and not changed_fields.intersection(event.changed_fields):
                continue
            if not state.epistemics_enabled:
                return True
            scope = (
                state.claimed_event_scopes.get(event.event_id)
                if event.event_id is not None
                else None
            )
            if scope is None or scope == "common":
                return True
            if event.event_id in known_events:
                return True
        return False

    parts = [event_type or "*", f"<={within_ticks}", "knower=actor"]
    if actor_slot:
        parts.append(f"actor={actor_slot.value}")
    if target_slot:
        parts.append(f"target={target_slot.value}")
    if changed_fields:
        parts.append("fields")
    return _named(_condition, f"knows_recent_event({','.join(parts)})")


def since_last_event_at_least(
    event_type: str,
    minimum_ticks: int,
    *,
    actor_slot: Slot = Slot.ACTOR,
    target_slot: Optional[Slot] = None,
) -> Condition:
    """Return whether enough ticks have passed since the last matching event.

    When target_slot is provided, the match also requires the event's
    target to bind to the same entity — making the cooldown per-
    (actor, target) rather than actor-global. Use this in multi-slot
    templates whose cooldown is meant to bound interaction frequency with
    one specific target (e.g., handler/informant cadence), not the actor's
    behavior class across all targets.
    """

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        actor_id = _slot_entity(bindings, actor_slot)
        if actor_id is None:
            return False
        target_id = _slot_entity(bindings, target_slot) if target_slot else None
        if target_slot is not None and target_id is None:
            return False
        latest_tick: Optional[int] = None
        for event in state.recent_events:
            if event.event_type != event_type:
                continue
            if event.actor_entity_id != actor_id:
                continue
            if target_id is not None and event.target_entity_id != target_id:
                continue
            latest_tick = (
                event.tick if latest_tick is None else max(latest_tick, event.tick)
            )
        if latest_tick is None:
            return True
        return state.current_tick - latest_tick >= minimum_ticks

    suffix = f",target={target_slot.value}" if target_slot else ""
    return _named(
        _condition,
        f"since_last_event_at_least({event_type},{minimum_ticks}"
        f"@{actor_slot.value}{suffix})",
    )


def count_recent_events_at_least(
    event_type: str,
    *,
    within_ticks: int,
    min_count: int,
    actor_slot: Slot = Slot.ACTOR,
    target_slot: Optional[Slot] = None,
) -> Condition:
    """Return whether at least ``min_count`` matching events landed in the window.

    Counting is bounded by the recent-event hydration window
    (``[orrery.binding] window_chunks``), so ``within_ticks`` larger than
    that window only ever sees hydrated history. Use for
    accumulate-then-act thresholds (grief completing after enough
    mourning acts, acting on piled-up surveillance) rather than simple
    cooldowns, which belong to :func:`since_last_event_at_least`.
    """

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        actor_id = _slot_entity(bindings, actor_slot)
        if actor_id is None:
            return False
        target_id = _slot_entity(bindings, target_slot) if target_slot else None
        if target_slot is not None and target_id is None:
            return False
        cutoff = state.current_tick - within_ticks
        count = 0
        for event in state.recent_events:
            if event.tick < cutoff:
                continue
            if event.event_type != event_type:
                continue
            if event.actor_entity_id != actor_id:
                continue
            if target_id is not None and event.target_entity_id != target_id:
                continue
            count += 1
            if count >= min_count:
                return True
        return False

    suffix = f",target={target_slot.value}" if target_slot else ""
    return _named(
        _condition,
        f"count_recent_events_at_least({event_type},>={min_count},<={within_ticks}"
        f"@{actor_slot.value}{suffix})",
    )


@dataclass(frozen=True, slots=True)
class CompoundCondition:
    """Self-describing AND / OR / NOT composition.

    Compound conditions used to be closures whose __name__ carried only the
    child count, hiding the structure from introspection. CompoundCondition
    keeps the runtime semantics identical (it is still callable) while
    exposing children for tools that need to walk the gate tree — e.g., the
    catalog renderer in nexus/agents/orrery/catalog.py.
    """

    op: Literal["AND", "OR", "NOT"]
    children: Tuple[Condition, ...]

    def __call__(self, state: WorldState, bindings: Bindings) -> bool:
        if self.op == "AND":
            return all(child(state, bindings) for child in self.children)
        if self.op == "OR":
            return any(child(state, bindings) for child in self.children)
        if self.op == "NOT":
            return not self.children[0](state, bindings)
        raise ValueError(f"Unknown compound op: {self.op}")

    @property
    def __name__(self) -> str:
        if self.op == "NOT":
            inner = getattr(self.children[0], "__name__", "<lambda>")
            return f"NOT({inner})"
        return f"{self.op}({len(self.children)})"


def AND(*conditions: Condition) -> Condition:
    """Compose conditions with logical AND."""

    return CompoundCondition("AND", tuple(conditions))


def OR(*conditions: Condition) -> Condition:
    """Compose conditions with logical OR."""

    return CompoundCondition("OR", tuple(conditions))


def NOT(condition: Condition) -> Condition:
    """Compose a condition with logical NOT."""

    return CompoundCondition("NOT", (condition,))


def ALWAYS(_state: WorldState, _bindings: Bindings) -> bool:
    """Condition that always passes."""

    return True


def NEVER(_state: WorldState, _bindings: Bindings) -> bool:
    """Condition that never passes."""

    return False


ALWAYS.__name__ = "ALWAYS"
NEVER.__name__ = "NEVER"


@dataclass(frozen=True, slots=True)
class Branch:
    """One procedure-tree branch inside a behavior package."""

    label: str
    conditions: Condition
    narrative_stub: str
    state_delta: Mapping[str, Any] = field(default_factory=dict)
    event_type: Optional[str] = None
    changed_fields: Tuple[str, ...] = ()
    magnitude: float = 0.0
    scene_pressure_stub: Optional[str] = None
    # A second, additive world-event emission: the signal an act gives off
    # (threat_issued, compliance_alert, ...) alongside the deed's own
    # event_type. Signals feed other packages' gates without disturbing the
    # emitting package's cooldowns.
    signal_event_type: Optional[str] = None
    # Routine project maintenance can opt out of the promotion queue even
    # when package priority or branch magnitude clears a generic threshold.
    promotable: bool = True
    # Lifecycle-terminal branches (a state transition like grief completing)
    # must fire the tick they become eligible in EVERY selection mode;
    # stochastic sampling is for flavor variety among peer branches, not
    # state machines. Preemptive branches are checked first, in authored
    # order, before any mode-specific selection runs.
    preemptive: bool = False


@dataclass(frozen=True, slots=True)
class Template:
    """Deterministic behavior package evaluated by the resolver."""

    id: str
    priority: int
    drive_band: DriveBand
    blurb: str
    required_slots: Tuple[Slot, ...]
    package_gate: Condition
    branches: Tuple[Branch, ...]
    present_target_policy: PresentTargetPolicy = PresentTargetPolicy.OFFSCREEN_ONLY
    # Project-start packages may opt into directed contact:social edges in
    # addition to the shared relationship-derived ACTOR/TARGET pool. Keeping
    # this authoring metadata on Template prevents one package's broader
    # starting substrate from changing every other two-party package.
    starts_from_social_contact: bool = False
    # Character-targeted project continuations bind TARGET from the durable
    # open-project projection. This remains valid if the contact or
    # relationship edge that originally sourced the project later clears.
    binds_project_target: bool = False
    priority_override_rationale: Optional[str] = None
    drive_band_priority_exempt: bool = False

    def __post_init__(self) -> None:
        """Validate authoring invariants that affect resolver routing."""

        if isinstance(self.drive_band, str):
            object.__setattr__(self, "drive_band", DriveBand(self.drive_band))

        if self.present_target_policy is PresentTargetPolicy.STORYTELLER_PRESSURE:
            missing = [
                branch.label
                for branch in self.branches
                if not branch.scene_pressure_stub
            ]
            if missing:
                raise ValueError(
                    f"Template {self.id!r}: STORYTELLER_PRESSURE branches must set "
                    f"scene_pressure_stub; missing on: {missing}"
                )


def configure_project_magnitudes(
    templates: Iterable[Template], policy: ProjectPolicy
) -> Tuple[Template, ...]:
    """Apply the configured milestone magnitude to project lifecycle arms.

    Routine project.advance/project.stall arms keep their authored sub-floor
    magnitudes. A branch opts into the configured promotion magnitude through
    a ``milestone`` marker inside its project payload; the marker is also
    persisted in state_delta and harmless to the applier/replayer.
    """

    configured: list[Template] = []
    for template in templates:
        changed = False
        branches: list[Branch] = []
        for branch in template.branches:
            milestone = any(
                isinstance(branch.state_delta.get(key), Mapping)
                and bool(branch.state_delta[key].get("milestone"))
                for key in (
                    "project.start",
                    "project.advance",
                    "project.abandon",
                    "project.complete",
                )
            )
            if milestone and branch.magnitude != policy.milestone_magnitude:
                branch = dataclass_replace(branch, magnitude=policy.milestone_magnitude)
                changed = True
            branches.append(branch)
        configured.append(
            dataclass_replace(template, branches=tuple(branches))
            if changed
            else template
        )
    return tuple(configured)


@dataclass(frozen=True, slots=True)
class Resolution:
    """Result of evaluating one template against one set of bindings."""

    template_id: str
    priority: int
    binding_hash: str
    bindings: Bindings
    passes: bool
    branch_label: Optional[str] = None
    narrative_stub: Optional[str] = None
    state_delta: Mapping[str, Any] = field(default_factory=dict)
    event_type: Optional[str] = None
    changed_fields: Tuple[str, ...] = ()
    magnitude: float = 0.0
    scene_pressure_stub: Optional[str] = None
    signal_event_type: Optional[str] = None
    promotable: bool = True


def binding_hash(bindings: Bindings) -> str:
    """Return a stable hash for a bindings dictionary."""

    def _binding_sort_key(item: Tuple[Any, Any]) -> str:
        slot = item[0]
        return slot.value if isinstance(slot, Slot) else str(slot)

    serializable = {
        slot.value if isinstance(slot, Slot) else str(slot): value
        for slot, value in sorted(bindings.items(), key=_binding_sort_key)
    }
    encoded = json.dumps(serializable, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BranchSelection:
    """Branch-selection policy, threaded from [orrery.selection] in nexus.toml.

    ``authored_order`` is the legacy deterministic rule: first passing branch
    in authored order wins (magnitude ladders are convention, not engine).
    ``stochastic`` evaluates every branch and samples the passing set with a
    magnitude-softmax at ``temperature``; the PRNG is keyed on values
    persisted with every resolution (binding hash, tick, template id, plus
    ``seed_salt``), so the same state always picks the same branch —
    reproducible dynamism, and reconstruction stays owned by the committed
    state_delta log, never a re-run of the sampler.
    """

    mode: str = "authored_order"
    temperature: float = 0.0
    seed_salt: str = ""

    def __post_init__(self) -> None:
        if self.mode not in ("authored_order", "stochastic"):
            raise ValueError(
                f"Unknown branch-selection mode {self.mode!r}; expected "
                "'authored_order' or 'stochastic'"
            )
        if self.temperature < 0:
            raise ValueError(
                f"Branch-selection temperature must be >= 0, got {self.temperature}"
            )


def coerce_branch_selection(value: Any) -> Optional[BranchSelection]:
    """Coerce [orrery.selection] config (mapping / model / None) to policy.

    ``None`` means "no policy supplied" and preserves legacy authored-order
    selection — callers that want configured behavior must pass the settings.
    """

    if value is None or isinstance(value, BranchSelection):
        return value
    if isinstance(value, Mapping):
        return BranchSelection(
            mode=str(value["mode"]),
            temperature=float(value["temperature"]),
            seed_salt=str(value.get("seed_salt", "")),
        )
    return BranchSelection(
        mode=str(value.mode),
        temperature=float(value.temperature),
        seed_salt=str(getattr(value, "seed_salt", "")),
    )


def _selection_rng(
    digest: str, tick: int, template_id: str, seed_salt: str
) -> random.Random:
    seed_material = f"{digest}:{tick}:{template_id}:{seed_salt}"
    return random.Random(int(sha256(seed_material.encode("utf-8")).hexdigest(), 16))


def select_branch(
    template: Template,
    state: WorldState,
    bindings: Bindings,
    *,
    digest: str,
    selection: Optional["BranchSelection"] = None,
) -> Tuple[Optional[Branch], Tuple[bool, ...]]:
    """The single branch-selection authority for one gated template.

    Returns ``(chosen_branch_or_None, considered_flags)`` where
    ``considered_flags[i]`` says whether ``branches[i]``'s conditions were
    evaluated. Both :func:`evaluate` and the explain layer's
    ``explain_template`` MUST route through this function — they cross-check
    each other and raise on divergence, so a second selection implementation
    is a correctness bug by construction.

    Preemptive branches are checked first in authored order under every
    mode — a passing lifecycle-terminal branch wins outright and the
    remaining branches are not evaluated. Otherwise ``authored_order``
    (and a missing ``selection``) preserves the legacy short-circuit
    exactly; ``stochastic`` evaluates all non-preemptive branches (those
    traces become exhaustive) and softmax-samples the passing set by
    magnitude. At ``temperature == 0`` stochastic degenerates to argmax
    by magnitude (authored order breaking ties).
    """

    considered_flags = [False] * len(template.branches)

    for index, branch in enumerate(template.branches):
        if not branch.preemptive:
            continue
        considered_flags[index] = True
        if branch.conditions(state, bindings):
            return branch, tuple(considered_flags)

    if selection is None or selection.mode == "authored_order":
        for index, branch in enumerate(template.branches):
            if branch.preemptive:
                continue
            considered_flags[index] = True
            if branch.conditions(state, bindings):
                return branch, tuple(considered_flags)
        return None, tuple(considered_flags)

    passing = []
    for index, branch in enumerate(template.branches):
        if branch.preemptive:
            continue
        considered_flags[index] = True
        if branch.conditions(state, bindings):
            passing.append(branch)
    considered = tuple(considered_flags)
    if not passing:
        return None, considered
    if len(passing) == 1:
        return passing[0], considered

    if selection.temperature == 0:
        return max(passing, key=lambda branch: branch.magnitude), considered

    # Softmax over magnitude, shifted for numerical stability.
    peak = max(branch.magnitude for branch in passing)
    weights = [
        math.exp((branch.magnitude - peak) / selection.temperature)
        for branch in passing
    ]
    rng = _selection_rng(digest, state.current_tick, template.id, selection.seed_salt)
    return rng.choices(passing, weights=weights, k=1)[0], considered


def evaluate(
    template: Template,
    state: WorldState,
    bindings: Bindings,
    selection: Optional[BranchSelection] = None,
) -> Resolution:
    """Evaluate one template and binding set against world state."""

    digest = binding_hash(bindings)
    if not template.package_gate(state, bindings):
        return Resolution(
            template_id=template.id,
            priority=template.priority,
            binding_hash=digest,
            bindings=bindings,
            passes=False,
        )

    branch, _considered = select_branch(
        template, state, bindings, digest=digest, selection=selection
    )
    if branch is not None:
        return Resolution(
            template_id=template.id,
            priority=template.priority,
            binding_hash=digest,
            bindings=bindings,
            passes=True,
            branch_label=branch.label,
            narrative_stub=branch.narrative_stub,
            state_delta=branch.state_delta,
            event_type=branch.event_type,
            changed_fields=branch.changed_fields,
            magnitude=branch.magnitude,
            scene_pressure_stub=branch.scene_pressure_stub,
            signal_event_type=branch.signal_event_type,
            promotable=branch.promotable,
        )

    return Resolution(
        template_id=template.id,
        priority=template.priority,
        binding_hash=digest,
        bindings=bindings,
        passes=False,
    )


@dataclass(frozen=True)
class HabituationPolicy:
    """Repetition dampening for stack ordering ([orrery.habituation]).

    A template's effective priority drops by ``penalty_per_win`` for each
    committed win by the same actor inside the trailing window (capped at
    ``max_penalty``), so a package that keeps winning eventually yields the
    stack to the shadowed packages beneath it. Bands in ``exempt_bands``
    (crisis by default) never dampen — an actively hunted actor must not
    tire of evading. Deterministic: win counts come from committed
    orrery_resolutions rows hydrated into WorldState.
    """

    enabled: bool = False
    penalty_per_win: float = 0.0
    max_penalty: float = 0.0
    window_ticks: int = 0
    exempt_bands: frozenset[str] = frozenset({"crisis_constraint"})

    def effective_priority(
        self, template: Template, state: WorldState, bindings: Bindings
    ) -> float:
        base = float(template.priority)
        if not self.enabled or template.drive_band.value in self.exempt_bands:
            return base
        actor = bindings.get(Slot.ACTOR)
        if not isinstance(actor, int):
            return base
        wins = state.win_history.get((actor, template.id), 0)
        if not wins:
            return base
        return base - min(self.penalty_per_win * wins, self.max_penalty)


def coerce_habituation(raw: Any) -> HabituationPolicy:
    """[orrery.habituation] settings payload -> HabituationPolicy."""

    if raw is None:
        return HabituationPolicy()
    if hasattr(raw, "penalty_per_win"):
        return HabituationPolicy(
            enabled=bool(raw.enabled),
            penalty_per_win=float(raw.penalty_per_win),
            max_penalty=float(raw.max_penalty),
            window_ticks=int(raw.window_ticks),
            exempt_bands=frozenset(raw.exempt_bands),
        )
    if isinstance(raw, Mapping):
        return HabituationPolicy(
            enabled=bool(raw.get("enabled", False)),
            penalty_per_win=float(raw.get("penalty_per_win", 0.0)),
            max_penalty=float(raw.get("max_penalty", 0.0)),
            window_ticks=int(raw.get("window_ticks", 0)),
            exempt_bands=frozenset(raw.get("exempt_bands", ("crisis_constraint",))),
        )
    raise ValueError(f"Unsupported habituation settings: {type(raw)!r}")


@dataclass(frozen=True, slots=True)
class PackageSelection:
    """Stack-winner policy from [orrery.package_selection].

    ``argmax`` preserves the legacy first-firing template in effective-priority
    order. ``stochastic`` softmax-samples only the gate-passing templates whose
    effective priorities sit within ``window_points`` of the maximum. Any
    passing template in ``exempt_bands`` disables sampling for the whole stack,
    preserving strict priority for crisis and other configured safety bands.
    """

    mode: str
    window_points: float
    temperature: float
    exempt_bands: frozenset[str]

    def __post_init__(self) -> None:
        if self.mode not in ("argmax", "stochastic"):
            raise ValueError(
                f"Unknown package-selection mode {self.mode!r}; expected "
                "'argmax' or 'stochastic'"
            )
        if self.window_points < 0:
            raise ValueError(
                "Package-selection window_points must be >= 0, got "
                f"{self.window_points}"
            )
        if self.temperature <= 0:
            raise ValueError(
                "Package-selection temperature must be > 0, got " f"{self.temperature}"
            )


def coerce_package_selection(raw: Any) -> Optional[PackageSelection]:
    """Coerce [orrery.package_selection] config to its runtime policy.

    ``None`` preserves the legacy strict-argmax stack behavior for callers
    that have not supplied configuration.
    """

    if raw is None or isinstance(raw, PackageSelection):
        return raw
    if isinstance(raw, Mapping):
        return PackageSelection(
            mode=str(raw["mode"]),
            window_points=float(raw["window_points"]),
            temperature=float(raw["temperature"]),
            exempt_bands=frozenset(raw["exempt_bands"]),
        )
    return PackageSelection(
        mode=str(raw.mode),
        window_points=float(raw.window_points),
        temperature=float(raw.temperature),
        exempt_bands=frozenset(raw.exempt_bands),
    )


@dataclass(frozen=True, slots=True)
class PackageSelectionOutcome:
    """Auditable result from the shared stack-winner authority."""

    winner: Optional[Resolution]
    window_template_ids: Tuple[str, ...] = ()
    chosen_by_softmax: bool = False
    reason: str = "no_passing_candidate"


def _package_selection_rng(digest: str, tick: int) -> random.Random:
    """PRNG keyed on binding identity, persisted tick, and a distinct salt."""

    seed_material = f"{digest}:{tick}:package_selection"
    return random.Random(int(sha256(seed_material.encode("utf-8")).hexdigest(), 16))


def stack_order(
    templates: Iterable[Template],
    state: WorldState,
    bindings: Bindings,
    habituation: Optional[HabituationPolicy] = None,
) -> list[Template]:
    """The single stack-ordering authority.

    Both :func:`evaluate_stack` and the explain layer's ``explain_stack``
    MUST route through this function — a second ordering implementation
    would let the audit dashboard's winner silently diverge from
    production. Sort is stable: equal effective priorities keep authored
    registry order.
    """

    policy = habituation or HabituationPolicy()
    return sorted(
        templates,
        key=lambda item: policy.effective_priority(item, state, bindings),
        reverse=True,
    )


def select_package(
    templates: Iterable[Template],
    state: WorldState,
    bindings: Bindings,
    branch_selection: Optional[BranchSelection] = None,
    habituation: Optional[HabituationPolicy] = None,
    package_selection: Optional[PackageSelection] = None,
) -> PackageSelectionOutcome:
    """Choose one firing package through the production/explain authority.

    Evaluation is lazy in effective-priority order: with no policy or
    explicit ``argmax``, the first firing template returns immediately —
    exactly the legacy ``evaluate_stack`` short-circuit; shadowed templates
    are never evaluated. Stochastic mode keeps evaluating only down to the
    near-tie window's floor (``peak - window_points``); candidates below
    the floor cannot win under either regime, so their gates and branch
    RNG never run. An exempt-band candidate firing at or above the floor
    preempts randomization for the whole stack. The softmax seed uses
    binding identity and the persisted tick plus a package-specific salt,
    so the same evaluation is replay-identical without sharing
    branch-selection calibration.
    """

    habituation_policy = habituation or HabituationPolicy()
    ordered = stack_order(templates, state, bindings, habituation_policy)
    stochastic = (
        package_selection is not None and package_selection.mode == "stochastic"
    )

    window: list[tuple[Template, Resolution, float]] = []
    peak: Optional[float] = None
    for template in ordered:
        effective_priority = habituation_policy.effective_priority(
            template, state, bindings
        )
        if peak is not None and (
            effective_priority < peak - package_selection.window_points
        ):
            break  # ordered descending: nothing below the floor can win
        resolution = evaluate(template, state, bindings, branch_selection)
        if not resolution.passes:
            continue
        if not stochastic:
            return PackageSelectionOutcome(
                winner=resolution,
                window_template_ids=(template.id,),
                reason="argmax",
            )
        if peak is None:
            peak = effective_priority
        window.append((template, resolution, effective_priority))

    if not window:
        return PackageSelectionOutcome(winner=None)

    argmax = window[0]
    if any(
        template.drive_band.value in package_selection.exempt_bands
        for template, _resolution, _priority in window
    ):
        return PackageSelectionOutcome(
            winner=argmax[1],
            window_template_ids=(argmax[0].id,),
            reason="exempt_band_argmax",
        )

    peak = argmax[2]
    window_ids = tuple(template.id for template, _resolution, _priority in window)
    if len(window) == 1:
        return PackageSelectionOutcome(
            winner=argmax[1],
            window_template_ids=window_ids,
            reason="single_candidate_window",
        )

    weights = [
        math.exp((effective_priority - peak) / package_selection.temperature)
        for _template, _resolution, effective_priority in window
    ]
    digest = binding_hash(bindings)
    rng = _package_selection_rng(digest, state.current_tick)
    chosen = rng.choices(window, weights=weights, k=1)[0]
    return PackageSelectionOutcome(
        winner=chosen[1],
        window_template_ids=window_ids,
        chosen_by_softmax=True,
        reason="window_softmax",
    )


def evaluate_stack(
    templates: Iterable[Template],
    state: WorldState,
    bindings: Bindings,
    selection: Optional[BranchSelection] = None,
    habituation: Optional[HabituationPolicy] = None,
    package_selection: Optional[PackageSelection] = None,
) -> Optional[Resolution]:
    """Evaluate a stack through the shared package-selection authority."""

    return select_package(
        templates,
        state,
        bindings,
        selection,
        habituation,
        package_selection,
    ).winner


def validate_always_fallbacks(templates: Iterable[Template]) -> None:
    """Validate that every template ends with an ALWAYS-conditioned branch."""

    missing = [
        template.id
        for template in templates
        if not template.branches or template.branches[-1].conditions is not ALWAYS
    ]
    if missing:
        raise ValueError(
            "Orrery templates missing terminal ALWAYS branch: "
            + ", ".join(sorted(missing))
        )


def _condition_tree_leaves(condition: Condition) -> Iterable[Condition]:
    """Yield leaf predicates of a (possibly compound) condition tree."""

    if isinstance(condition, CompoundCondition):
        for child in condition.children:
            yield from _condition_tree_leaves(child)
    else:
        yield condition


def validate_no_fame_in_entry_gates(templates: Iterable[Template]) -> None:
    """Enforce the issue #282 stage contract: fame never gates package entry.

    Fame is stage-2 (branch selection) and stage-3 (outcome) vocabulary only.
    A package gate that reads the actor's fame would make recognizability
    decide *whether* a behavior fires instead of *how* it is performed, which
    the locked design forbids.
    """

    offenders: list[str] = []
    for template in templates:
        for leaf in _condition_tree_leaves(template.package_gate):
            name = getattr(leaf, "__name__", "")
            if name.startswith(_FAME_PREDICATE_NAME_PREFIXES):
                offenders.append(f"{template.id}: {name}")
    if offenders:
        raise ValueError(
            "Fame predicates are stage-2/3 only and must not appear in "
            "package gates (issue #282 stage contract): " + ", ".join(sorted(offenders))
        )


def drive_band_priority_warnings(templates: Iterable[Template]) -> Tuple[str, ...]:
    """Return package priority inversions without explicit rationale.

    A warning means a lower-urgency drive band outranks a higher-urgency band
    and the outranking template does not explain why. This is deliberately an
    authoring check, not a runtime resolver rule: Skald-facing story obligations
    can outrank routine needs, but the catalog should say so.
    """

    ordered = tuple(templates)
    warnings: list[str] = []
    for template in ordered:
        if template.drive_band_priority_exempt:
            continue
        template_rank = DRIVE_BAND_ORDER[template.drive_band]
        if template.priority_override_rationale:
            continue
        contradicted = [
            other
            for other in ordered
            if not other.drive_band_priority_exempt
            and other.priority < template.priority
            and DRIVE_BAND_ORDER[other.drive_band] < template_rank
        ]
        if contradicted:
            strongest = min(
                contradicted, key=lambda item: DRIVE_BAND_ORDER[item.drive_band]
            )
            warnings.append(
                f"{template.id} ({template.drive_band.value}, priority "
                f"{template.priority}) outranks {strongest.id} "
                f"({strongest.drive_band.value}, priority {strongest.priority}) "
                "without priority_override_rationale"
            )
    return tuple(sorted(warnings))
