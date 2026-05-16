"""Pure-Python substrate for Orrery off-screen behavior packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple


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


Bindings = Dict[Slot, Any]
Condition = Callable[["WorldState", Bindings], bool]


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Compact read-side event shape consumed by condition predicates."""

    event_type: str
    tick: int
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
    locations: Mapping[int, int] = field(default_factory=dict)
    activities: Mapping[int, str] = field(default_factory=dict)
    trust: Mapping[Tuple[int, int], int] = field(default_factory=dict)
    relationship_types: Mapping[Tuple[int, int], frozenset[str]] = field(
        default_factory=dict
    )
    faction_memberships: Mapping[int, frozenset[int]] = field(default_factory=dict)
    location_class: Mapping[int, str] = field(default_factory=dict)
    orbit_distance: Mapping[Tuple[int, int], int] = field(default_factory=dict)
    recent_events: Tuple[EventRecord, ...] = ()
    time_of_day: str = "midday"
    weather: str = "clear"
    current_tick: int = 0


def _slot_entity(bindings: Bindings, slot: Slot) -> Optional[int]:
    value = bindings.get(slot)
    return value if isinstance(value, int) else None


def _named(condition: Condition, name: str) -> Condition:
    condition.__name__ = name
    return condition


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


def has_ephemeral(tag: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether a slot-bound entity has a current ephemeral tag."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        return entity_id is not None and tag in state.ephemeral_tags.get(
            entity_id, frozenset()
        )

    return _named(_condition, f"has_ephemeral({tag}@{slot.value})")


def in_location_class(location_class: str, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether an entity is currently in a place of the given class."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        location_id = state.locations.get(entity_id)
        return (
            location_id is not None
            and state.location_class.get(location_id) == location_class
        )

    return _named(_condition, f"in_location_class({location_class}@{slot.value})")


def in_location(location_id: int, slot: Slot = Slot.ACTOR) -> Condition:
    """Return whether an entity is currently at a specific place id."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        return entity_id is not None and state.locations.get(entity_id) == location_id

    return _named(_condition, f"in_location({location_id}@{slot.value})")


def co_located(slot_a: Slot = Slot.ACTOR, slot_b: Slot = Slot.TARGET) -> Condition:
    """Return whether two slot-bound entities share a current location."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        left = _slot_entity(bindings, slot_a)
        right = _slot_entity(bindings, slot_b)
        if left is None or right is None:
            return False
        location_id = state.locations.get(left)
        return location_id is not None and location_id == state.locations.get(right)

    return _named(_condition, f"co_located({slot_a.value},{slot_b.value})")


def count_co_located(
    minimum: int,
    slot: Slot = Slot.ACTOR,
    *,
    with_tag: Optional[str] = None,
) -> Condition:
    """Return whether enough entities share the slot entity's current location."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        entity_id = _slot_entity(bindings, slot)
        if entity_id is None:
            return False
        location_id = state.locations.get(entity_id)
        if location_id is None:
            return False
        count = 0
        for other_id, other_location in state.locations.items():
            if other_id == entity_id or other_location != location_id:
                continue
            if with_tag and with_tag not in state.tags.get(other_id, frozenset()):
                continue
            count += 1
        return count >= minimum

    suffix = f",tag={with_tag}" if with_tag else ""
    return _named(_condition, f"count_co_located({minimum}@{slot.value}{suffix})")


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
        f"has_relationship_of_type({relationship_type},{slot_from.value}->{slot_to.value})",
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
        cutoff = state.current_tick - within_ticks
        for event in state.recent_events:
            if event.tick < cutoff:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            if actor_id is not None and actor_id not in (
                event.actor_entity_id,
                event.target_entity_id,
            ):
                continue
            if target_id is not None and target_id not in (
                event.actor_entity_id,
                event.target_entity_id,
            ):
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


def since_last_event_at_least(
    event_type: str,
    minimum_ticks: int,
    *,
    actor_slot: Slot = Slot.ACTOR,
) -> Condition:
    """Return whether enough ticks have passed since the last matching event."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        actor_id = _slot_entity(bindings, actor_slot)
        latest_tick: Optional[int] = None
        for event in state.recent_events:
            if event.event_type != event_type:
                continue
            if actor_id is not None and actor_id not in (
                event.actor_entity_id,
                event.target_entity_id,
            ):
                continue
            latest_tick = (
                event.tick if latest_tick is None else max(latest_tick, event.tick)
            )
        if latest_tick is None:
            return True
        return state.current_tick - latest_tick >= minimum_ticks

    return _named(
        _condition,
        f"since_last_event_at_least({event_type},{minimum_ticks}@{actor_slot.value})",
    )


def AND(*conditions: Condition) -> Condition:
    """Compose conditions with logical AND."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        return all(condition(state, bindings) for condition in conditions)

    return _named(_condition, f"AND({len(conditions)})")


def OR(*conditions: Condition) -> Condition:
    """Compose conditions with logical OR."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        return any(condition(state, bindings) for condition in conditions)

    return _named(_condition, f"OR({len(conditions)})")


def NOT(condition: Condition) -> Condition:
    """Compose a condition with logical NOT."""

    def _condition(state: WorldState, bindings: Bindings) -> bool:
        return not condition(state, bindings)

    return _named(_condition, f"NOT({condition.__name__})")


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


@dataclass(frozen=True, slots=True)
class Template:
    """Deterministic behavior package evaluated by the resolver."""

    id: str
    priority: int
    blurb: str
    required_slots: Tuple[Slot, ...]
    package_gate: Condition
    branches: Tuple[Branch, ...]


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


def binding_hash(bindings: Bindings) -> str:
    """Return a stable hash for a bindings dictionary."""

    serializable = {
        slot.value if isinstance(slot, Slot) else str(slot): value
        for slot, value in sorted(bindings.items(), key=lambda item: item[0].value)
    }
    encoded = json.dumps(serializable, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def evaluate(template: Template, state: WorldState, bindings: Bindings) -> Resolution:
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

    for branch in template.branches:
        if branch.conditions(state, bindings):
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
            )

    return Resolution(
        template_id=template.id,
        priority=template.priority,
        binding_hash=digest,
        bindings=bindings,
        passes=False,
    )


def evaluate_stack(
    templates: Iterable[Template], state: WorldState, bindings: Bindings
) -> Optional[Resolution]:
    """Evaluate templates in priority order and return the first firing branch."""

    for template in sorted(templates, key=lambda item: item.priority, reverse=True):
        result = evaluate(template, state, bindings)
        if result.passes:
            return result
    return None


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
