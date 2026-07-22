"""Parse-and-recompute evidence for Orrery leaf predicates.

The explain layer records that a leaf predicate returned True or False; this
module recovers *why* — the actual state values the predicate read — without
touching the 53 predicate factories in :mod:`substrate`. Every factory stamps
a machine-parseable ``__name__`` (``has_need_debt_at_or_above(sleep,16@actor)``),
and the catalog's ``_PREDICATE_PARSERS`` regexes already parse all of them;
this module reuses those exact patterns, so there is one grammar, defined once.

Each resolver returns a uniform evidence payload::

    {
        "kind":     "has_any_tag",          # factory name
        "params":   {...},                   # config parsed from __name__
        "entities": {"actor": 5},            # slot -> resolved entity id
        "observed": {...},                   # the state values actually read
        "matched":  [...] | None,            # which members/ids satisfied it
        "result":   True,                    # recomputed verdict
    }

``result`` is the drift tripwire: the caller (``explain.trace_condition``)
compares it against the real predicate's return value and raises loudly on
mismatch, the same discipline ``explain_template`` applies against
``evaluate``. Recomputation deliberately reuses substrate's own helper
functions (``_tier_rank``, ``_at_routine_anchor``, ...) where they exist —
the goal is exposing the values production reads, not reimplementing them.

Family predicates (``has_any_*``, ``is_hidden``, ``is_constrained``, ...)
always name the specific member(s) that matched in ``matched`` — a bare bool
cannot answer "which suppressor tag killed this package."

The one name-unrecoverable input is ``recent_event``'s ``changed_fields``
filter (the name carries only a ``,fields`` marker). No builtin template uses
it; when it appears, ``result`` is ``None`` and the caller skips the
cross-check rather than pretending to a verdict it cannot recompute.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Callable, Mapping, Optional

from nexus.agents.orrery.catalog import _PREDICATE_PARSERS
from nexus.agents.orrery.status_family import (
    STATUS_LEVEL_RANKS,
    STATUS_TAG_PREFIX,
)
from nexus.agents.orrery.substrate import (
    CONSTRAINED_TAGS,
    CONTACT_PAIR_TAGS,
    DEFAULT_FAME_TIER,
    DEFAULT_RESOURCES_TIER,
    DRAMATIC_CONTACT_TAGS,
    ESTABLISHED_PARTNER_RELATIONSHIP_TYPES,
    FAME_TIER_RANKS,
    HIDDEN_TAGS,
    INTIMACY_SUPPRESSOR_TAGS,
    LOADED_TRUST_FORWARD_MIN,
    LOADED_TRUST_REVERSE_MAX,
    PUBLIC_MOBILITY_TAGS,
    PUBLIC_PLACE_CLASSES,
    RESOURCES_TIER_RANKS,
    Bindings,
    Slot,
    WorldState,
    active_mood,
    _at_routine_anchor,
    _is_in_transit,
    _possessed_claim_knowledge,
    _routine_anchor,
    _routine_anchor_destination_available,
    _routine_schedule_due,
    _trust_values_are_asymmetric,
    project_faction_is,
    project_faction_is_active,
    project_due,
    project_overdue_hours,
    project_target_is,
    project_target_is_active,
    weather_for_actor,
)


class EvidenceResolutionError(RuntimeError):
    """A leaf predicate name has no evidence resolver.

    Raised loudly: on an audit surface, a leaf whose reasoning cannot be
    shown is a coverage bug, not a degradation to tolerate silently.
    """


_Resolver = Callable[["re.Match[str]", WorldState, Bindings], "dict[str, Any]"]

_RESOLVERS: dict[str, _Resolver] = {}


def _resolver(kind: str) -> Callable[[_Resolver], _Resolver]:
    def _register(func: _Resolver) -> _Resolver:
        _RESOLVERS[kind] = func
        return func

    return _register


def _entity(bindings: Bindings, slot_name: str) -> Optional[int]:
    value = bindings.get(Slot(slot_name))
    return value if isinstance(value, int) else None


def _current_tags(state: WorldState, entity_id: Optional[int]) -> frozenset[str]:
    if entity_id is None:
        return frozenset()
    return state.tags.get(entity_id, frozenset()) | state.ephemeral_tags.get(
        entity_id, frozenset()
    )


def _evidence(
    kind: str,
    *,
    params: Mapping[str, Any],
    entities: Mapping[str, Optional[int]],
    observed: Mapping[str, Any],
    result: Optional[bool],
    matched: Optional[list[Any]] = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "params": dict(params),
        "entities": dict(entities),
        "observed": dict(observed),
        "matched": matched,
        "result": result,
    }


# ---------------------------------------------------------------------------
# Tags (durable / ephemeral / union)
# ---------------------------------------------------------------------------


@_resolver("has_tag")
def _has_tag(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot, tag = match["slot"], match["tag"]
    entity_id = _entity(bindings, slot)
    tags = (
        state.tags.get(entity_id, frozenset()) if entity_id is not None else frozenset()
    )
    return _evidence(
        "has_tag",
        params={"tag": tag, "slot": slot},
        entities={slot: entity_id},
        observed={"durable_tags": sorted(tags)},
        matched=[tag] if tag in tags else [],
        result=entity_id is not None and tag in tags,
    )


@_resolver("lacks_tag")
def _lacks_tag(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot, tag = match["slot"], match["tag"]
    entity_id = _entity(bindings, slot)
    tags = (
        state.tags.get(entity_id, frozenset()) if entity_id is not None else frozenset()
    )
    return _evidence(
        "lacks_tag",
        params={"tag": tag, "slot": slot},
        entities={slot: entity_id},
        observed={"durable_tags": sorted(tags)},
        matched=[tag] if tag in tags else [],
        result=entity_id is None or tag not in tags,
    )


@_resolver("has_any_tag")
def _has_any_tag(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot = match["slot"]
    candidates = match["tags"].split(",")
    entity_id = _entity(bindings, slot)
    tags = (
        state.tags.get(entity_id, frozenset()) if entity_id is not None else frozenset()
    )
    matched = sorted(frozenset(candidates) & tags)
    return _evidence(
        "has_any_tag",
        params={"tags": candidates, "slot": slot},
        entities={slot: entity_id},
        observed={"durable_tags": sorted(tags)},
        matched=matched,
        result=entity_id is not None and bool(matched),
    )


@_resolver("has_any_current_tag")
def _has_any_current_tag(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot = match["slot"]
    candidates = match["tags"].split(",")
    entity_id = _entity(bindings, slot)
    tags = _current_tags(state, entity_id)
    matched = sorted(frozenset(candidates) & tags)
    return _evidence(
        "has_any_current_tag",
        params={"tags": candidates, "slot": slot},
        entities={slot: entity_id},
        observed={"current_tags": sorted(tags)},
        matched=matched,
        result=entity_id is not None and bool(matched),
    )


@_resolver("has_ephemeral")
def _has_ephemeral(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot, tag = match["slot"], match["tag"]
    entity_id = _entity(bindings, slot)
    tags = (
        state.ephemeral_tags.get(entity_id, frozenset())
        if entity_id is not None
        else frozenset()
    )
    return _evidence(
        "has_ephemeral",
        params={"tag": tag, "slot": slot},
        entities={slot: entity_id},
        observed={"ephemeral_tags": sorted(tags)},
        matched=[tag] if tag in tags else [],
        result=entity_id is not None and tag in tags,
    )


def _family_resolver(kind: str, family_name: str, family: frozenset[str]) -> None:
    def _resolve(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
        slot = match["slot"]
        entity_id = _entity(bindings, slot)
        tags = _current_tags(state, entity_id)
        matched = sorted(family & tags)
        return _evidence(
            kind,
            params={
                "family": family_name,
                "family_members": sorted(family),
                "slot": slot,
            },
            entities={slot: entity_id},
            observed={"current_tags": sorted(tags)},
            matched=matched,
            result=entity_id is not None and bool(matched),
        )

    _RESOLVERS[kind] = _resolve


_family_resolver("is_constrained", "constrained_tags", CONSTRAINED_TAGS)
_family_resolver("is_hidden", "hidden_tags", HIDDEN_TAGS)
_family_resolver(
    "has_any_intimacy_suppressor",
    "intimacy_suppressor_tags",
    INTIMACY_SUPPRESSOR_TAGS,
)


@_resolver("has_severity_tag")
def _has_severity_tag(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot, prefix = match["slot"], match["prefix"]
    entity_id = _entity(bindings, slot)
    tags = _current_tags(state, entity_id)
    marker = f"{prefix}_"
    matched = sorted(tag for tag in tags if tag.startswith(marker))
    return _evidence(
        "has_severity_tag",
        params={"prefix": prefix, "slot": slot},
        entities={slot: entity_id},
        observed={"current_tags": sorted(tags)},
        matched=matched,
        result=entity_id is not None and bool(matched),
    )


@_resolver("has_severity_tag_at_or_above")
def _has_severity_tag_at_or_above(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, prefix = match["slot"], match["prefix"]
    level = int(match["level"])
    entity_id = _entity(bindings, slot)
    tags = _current_tags(state, entity_id)
    marker = f"{prefix}_"
    track: list[dict[str, Any]] = []
    matched: list[str] = []
    for tag in sorted(tags):
        if not tag.startswith(marker):
            continue
        numeric, _sep, _label = tag.removeprefix(marker).partition("_")
        try:
            parsed = int(numeric)
        except ValueError:
            track.append({"tag": tag, "level": None})
            continue
        track.append({"tag": tag, "level": parsed})
        if parsed >= level:
            matched.append(tag)
    return _evidence(
        "has_severity_tag_at_or_above",
        params={"prefix": prefix, "level": level, "slot": slot},
        entities={slot: entity_id},
        observed={"severity_track": track},
        matched=matched,
        result=entity_id is not None and bool(matched),
    )


# ---------------------------------------------------------------------------
# Exclusive tier ladders (fame / resources)
# ---------------------------------------------------------------------------


def _tier_resolver(
    kind: str,
    ranks: Mapping[str, int],
    default_tier: str,
    at_or_above: bool,
) -> None:
    def _resolve(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
        slot, tier = match["slot"], match["tier"]
        threshold_rank = ranks[tier]
        entity_id = _entity(bindings, slot)
        present = (
            sorted(
                tag for tag in state.tags.get(entity_id, frozenset()) if tag in ranks
            )
            if entity_id is not None
            else []
        )
        if len(present) > 1:
            # Mirror _tier_rank's corrupt-ladder refusal rather than guessing.
            raise ValueError(
                f"Entity {entity_id} holds multiple tier tags {present}; "
                "exclusive ladder is corrupt"
            )
        resolved = present[0] if present else default_tier
        resolved_rank = ranks[resolved]
        satisfied = (
            resolved_rank >= threshold_rank
            if at_or_above
            else resolved_rank < threshold_rank
        )
        return _evidence(
            kind,
            params={
                "tier": tier,
                "threshold_rank": threshold_rank,
                "slot": slot,
                "comparator": ">=" if at_or_above else "<",
            },
            entities={slot: entity_id},
            observed={
                "tier_tags_present": present,
                "resolved_tier": resolved,
                "resolved_rank": resolved_rank,
                "defaulted": not present,
            },
            matched=present,
            result=entity_id is not None and satisfied,
        )

    _RESOLVERS[kind] = _resolve


_tier_resolver("fame_at_or_above", FAME_TIER_RANKS, DEFAULT_FAME_TIER, True)
_tier_resolver("fame_below", FAME_TIER_RANKS, DEFAULT_FAME_TIER, False)
_tier_resolver(
    "resources_at_or_above", RESOURCES_TIER_RANKS, DEFAULT_RESOURCES_TIER, True
)
_tier_resolver("resources_below", RESOURCES_TIER_RANKS, DEFAULT_RESOURCES_TIER, False)


@_resolver("mood_is")
def _mood_is(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot = match["slot"]
    candidates = match["values"].split(",")
    entity_id = _entity(bindings, slot)
    observed_mood = active_mood(state, bindings, Slot(slot))
    matched = [observed_mood] if observed_mood in candidates else []
    return _evidence(
        "mood_is",
        params={"moods": candidates, "slot": slot},
        entities={slot: entity_id},
        observed={
            "mood_enabled": state.mood_enabled,
            "active_mood": observed_mood,
        },
        matched=matched,
        result=entity_id is not None and bool(matched),
    )


# ---------------------------------------------------------------------------
# Pair tags
# ---------------------------------------------------------------------------


def _edge_tags(
    state: WorldState, subject_id: Optional[int], object_id: Optional[int]
) -> frozenset[str]:
    if subject_id is None or object_id is None:
        return frozenset()
    return state.pair_tags.get((subject_id, object_id), frozenset())


@_resolver("has_pair_tag")
def _has_pair_tag(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    subj, obj, tag = match["subj"], match["obj"], match["tag"]
    subject_id = _entity(bindings, subj)
    object_id = _entity(bindings, obj)
    edge = _edge_tags(state, subject_id, object_id)
    return _evidence(
        "has_pair_tag",
        params={"tag": tag, "subject_slot": subj, "object_slot": obj},
        entities={subj: subject_id, obj: object_id},
        observed={"edge_tags": sorted(edge)},
        matched=[tag] if tag in edge else [],
        result=subject_id is not None and object_id is not None and tag in edge,
    )


@_resolver("lacks_pair_tag")
def _lacks_pair_tag(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    subj, obj, tag = match["subj"], match["obj"], match["tag"]
    subject_id = _entity(bindings, subj)
    object_id = _entity(bindings, obj)
    edge = _edge_tags(state, subject_id, object_id)
    return _evidence(
        "lacks_pair_tag",
        params={"tag": tag, "subject_slot": subj, "object_slot": obj},
        entities={subj: subject_id, obj: object_id},
        observed={"edge_tags": sorted(edge)},
        matched=[tag] if tag in edge else [],
        result=subject_id is None or object_id is None or tag not in edge,
    )


@_resolver("has_any_pair_tag")
def _has_any_pair_tag(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    subj, obj = match["subj"], match["obj"]
    candidates = match["tags"].split(",")
    subject_id = _entity(bindings, subj)
    object_id = _entity(bindings, obj)
    edge = _edge_tags(state, subject_id, object_id)
    matched = sorted(frozenset(candidates) & edge)
    return _evidence(
        "has_any_pair_tag",
        params={"tags": candidates, "subject_slot": subj, "object_slot": obj},
        entities={subj: subject_id, obj: object_id},
        observed={"edge_tags": sorted(edge)},
        matched=matched,
        result=subject_id is not None and object_id is not None and bool(matched),
    )


@_resolver("has_pair_tag_to_current_location")
def _has_pair_tag_to_current_location(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, tag = match["slot"], match["tag"]
    entity_id = _entity(bindings, slot)
    place_id = state.locations.get(entity_id) if entity_id is not None else None
    place_entity_id = (
        state.location_entity_ids.get(place_id) if place_id is not None else None
    )
    edge = _edge_tags(state, entity_id, place_entity_id)
    return _evidence(
        "has_pair_tag_to_current_location",
        params={"tag": tag, "slot": slot},
        entities={slot: entity_id},
        observed={
            "place_id": place_id,
            "place_entity_id": place_entity_id,
            "edge_tags": sorted(edge),
        },
        matched=[tag] if tag in edge else [],
        result=(entity_id is not None and place_entity_id is not None and tag in edge),
    )


@_resolver("has_inbound_pair_tag")
def _has_inbound_pair_tag_evidence(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, tag = match["slot"], match["tag"]
    entity_id = _entity(bindings, slot)
    matched = sorted(
        subject_id
        for (subject_id, object_id), tags in state.pair_tags.items()
        if entity_id is not None and object_id == entity_id and tag in tags
    )
    return _evidence(
        "has_inbound_pair_tag",
        params={"tag": tag, "slot": slot},
        entities={slot: entity_id},
        observed={"inbound_subject_ids": matched},
        matched=matched,
        result=bool(matched),
    )


@_resolver("has_contact_of_kind")
def _has_contact_of_kind(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, kind = match["slot"], match["kind"]
    pair_tag = CONTACT_PAIR_TAGS[kind]
    entity_id = _entity(bindings, slot)
    matched = sorted(
        object_id
        for (subject_id, object_id), tags in state.pair_tags.items()
        if entity_id is not None and subject_id == entity_id and pair_tag in tags
    )
    return _evidence(
        "has_contact_of_kind",
        params={"kind": kind, "pair_tag": pair_tag, "slot": slot},
        entities={slot: entity_id},
        observed={"outbound_object_ids": matched},
        matched=matched,
        result=bool(matched),
    )


@_resolver("has_any_status_at_or_above")
def _has_any_status_at_or_above(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, level = match["slot"], match["level"]
    threshold_rank = STATUS_LEVEL_RANKS[level]
    entity_id = _entity(bindings, slot)
    edges: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []
    for (subject_id, object_id), tags in state.pair_tags.items():
        if entity_id is None or subject_id != entity_id:
            continue
        for tag in sorted(tags):
            if not tag.startswith(STATUS_TAG_PREFIX):
                continue
            status_level = tag.removeprefix(STATUS_TAG_PREFIX)
            rank = STATUS_LEVEL_RANKS.get(status_level)
            entry = {
                "scope_entity_id": object_id,
                "tag": tag,
                "rank": rank,
            }
            edges.append(entry)
            if rank is not None and rank >= threshold_rank:
                matched.append(entry)
    return _evidence(
        "has_any_status_at_or_above",
        params={"level": level, "threshold_rank": threshold_rank, "slot": slot},
        entities={slot: entity_id},
        observed={"status_edges": edges},
        matched=matched,
        result=bool(matched),
    )


# ---------------------------------------------------------------------------
# Composite context predicates
# ---------------------------------------------------------------------------


@_resolver("has_minimal_context")
def _has_minimal_context(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot = match["slot"]
    entity_id = _entity(bindings, slot)
    sources = {
        "tags": bool(
            entity_id is not None
            and (state.tags.get(entity_id) or state.ephemeral_tags.get(entity_id))
        ),
        "location_or_activity": bool(
            entity_id is not None
            and (entity_id in state.locations or entity_id in state.activities)
        ),
        "travel_state": entity_id in state.travel_states,
        "recent_events": any(
            entity_id is not None
            and entity_id in (event.actor_entity_id, event.target_entity_id)
            for event in state.recent_events
        ),
    }
    matched = sorted(name for name, present in sources.items() if present)
    return _evidence(
        "has_minimal_context",
        params={"slot": slot},
        entities={slot: entity_id},
        observed={"context_sources": sources},
        matched=matched,
        result=entity_id is not None and bool(matched),
    )


@_resolver("can_move_publicly")
def _can_move_publicly(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot = match["slot"]
    entity_id = _entity(bindings, slot)
    in_transit = entity_id is not None and _is_in_transit(state, entity_id)
    tags = _current_tags(state, entity_id)
    constrained = sorted(CONSTRAINED_TAGS & tags)
    mobility = sorted(PUBLIC_MOBILITY_TAGS & tags)
    social_tag = CONTACT_PAIR_TAGS["social"]
    social_contacts = sorted(
        object_id
        for (subject_id, object_id), edge in state.pair_tags.items()
        if entity_id is not None and subject_id == entity_id and social_tag in edge
    )
    place_id = state.locations.get(entity_id) if entity_id is not None else None
    semantic = (
        state.location_classes.get(place_id, frozenset())
        if place_id is not None
        else frozenset()
    )
    legacy = state.location_class.get(place_id) if place_id is not None else None
    public_classes = sorted(
        (PUBLIC_PLACE_CLASSES & semantic)
        | ({legacy} if legacy in PUBLIC_PLACE_CLASSES else set())
    )
    if entity_id is None or in_transit or constrained:
        result = False
        granted_by: Optional[str] = None
    elif mobility:
        result, granted_by = True, "public_mobility_tag"
    elif social_contacts:
        result, granted_by = True, "social_contact"
    elif public_classes:
        result, granted_by = True, "public_place_class"
    else:
        result, granted_by = False, None
    return _evidence(
        "can_move_publicly",
        params={"slot": slot},
        entities={slot: entity_id},
        observed={
            "in_transit": in_transit,
            "constrained_tags": constrained,
            "public_mobility_tags": mobility,
            "social_contact_ids": social_contacts,
            "place_id": place_id,
            "public_place_classes": public_classes,
            "granted_by": granted_by,
        },
        matched=mobility + public_classes,
        result=result,
    )


# ---------------------------------------------------------------------------
# Needs
# ---------------------------------------------------------------------------


@_resolver("has_need_debt_at_or_above")
def _has_need_debt_at_or_above(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, need = match["slot"], match["need"]
    threshold = float(match["threshold"])
    entity_id = _entity(bindings, slot)
    score = (
        state.need_debt_scores.get((entity_id, need), 0.0)
        if entity_id is not None
        else 0.0
    )
    return _evidence(
        "has_need_debt_at_or_above",
        params={"need_type": need, "threshold": threshold, "slot": slot},
        entities={slot: entity_id},
        observed={"debt_score": score},
        result=entity_id is not None and score >= threshold,
    )


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


def _place_classes(state: WorldState, place_id: Optional[int]) -> dict[str, Any]:
    if place_id is None:
        return {"place_id": None, "semantic_classes": [], "legacy_class": None}
    return {
        "place_id": place_id,
        "semantic_classes": sorted(state.location_classes.get(place_id, frozenset())),
        "legacy_class": state.location_class.get(place_id),
    }


@_resolver("in_location_class")
def _in_location_class(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot, location_class = match["slot"], match["lc"]
    entity_id = _entity(bindings, slot)
    in_transit = entity_id is not None and _is_in_transit(state, entity_id)
    place_id = state.locations.get(entity_id) if entity_id is not None else None
    place = _place_classes(state, place_id)
    hit = location_class in place["semantic_classes"] or (
        place["legacy_class"] == location_class
    )
    return _evidence(
        "in_location_class",
        params={"location_class": location_class, "slot": slot},
        entities={slot: entity_id},
        observed={"in_transit": in_transit, **place},
        matched=[location_class] if hit else [],
        result=(
            entity_id is not None and not in_transit and place_id is not None and hit
        ),
    )


@_resolver("has_location_class_destination")
def _has_location_class_destination(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot = match["slot"]
    classes = frozenset(match["lc"].split(","))
    entity_id = _entity(bindings, slot)
    in_transit = entity_id is not None and _is_in_transit(state, entity_id)
    current_place_id = state.locations.get(entity_id) if entity_id is not None else None
    matched_places: set[int] = set()
    if entity_id is not None and not in_transit and current_place_id is not None:
        for place_id, semantic_classes in state.location_classes.items():
            if place_id != current_place_id and classes & semantic_classes:
                matched_places.add(place_id)
        for place_id, legacy_class in state.location_class.items():
            if place_id != current_place_id and legacy_class in classes:
                matched_places.add(place_id)
    return _evidence(
        "has_location_class_destination",
        params={"location_classes": sorted(classes), "slot": slot},
        entities={slot: entity_id},
        observed={
            "in_transit": in_transit,
            "current_place_id": current_place_id,
            "destination_count": len(matched_places),
        },
        matched=sorted(matched_places),
        result=bool(matched_places),
    )


@_resolver("in_location")
def _in_location(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot = match["slot"]
    target_place = int(match["lid"])
    entity_id = _entity(bindings, slot)
    in_transit = entity_id is not None and _is_in_transit(state, entity_id)
    place_id = state.locations.get(entity_id) if entity_id is not None else None
    return _evidence(
        "in_location",
        params={"location_id": target_place, "slot": slot},
        entities={slot: entity_id},
        observed={"in_transit": in_transit, "place_id": place_id},
        result=entity_id is not None and not in_transit and place_id == target_place,
    )


@_resolver("co_located")
def _co_located(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot_a, slot_b = match["a"], match["b"]
    left = _entity(bindings, slot_a)
    right = _entity(bindings, slot_b)
    left_transit = left is not None and _is_in_transit(state, left)
    right_transit = right is not None and _is_in_transit(state, right)
    left_place = state.locations.get(left) if left is not None else None
    right_place = state.locations.get(right) if right is not None else None
    return _evidence(
        "co_located",
        params={"slot_a": slot_a, "slot_b": slot_b},
        entities={slot_a: left, slot_b: right},
        observed={
            "places": {slot_a: left_place, slot_b: right_place},
            "in_transit": {slot_a: left_transit, slot_b: right_transit},
        },
        result=(
            left is not None
            and right is not None
            and not left_transit
            and not right_transit
            and left_place is not None
            and left_place == right_place
        ),
    )


@_resolver("count_co_located")
def _count_co_located(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot = match["slot"]
    minimum = int(match["n"])
    with_tag = match["tag"]
    with_ephemeral = match["ephemeral"]
    entity_id = _entity(bindings, slot)
    in_transit = entity_id is not None and _is_in_transit(state, entity_id)
    place_id = state.locations.get(entity_id) if entity_id is not None else None
    matched: list[int] = []
    if entity_id is not None and not in_transit and place_id is not None:
        for other_id, other_place in state.locations.items():
            if other_id == entity_id or other_place != place_id:
                continue
            if _is_in_transit(state, other_id):
                continue
            if with_tag and with_tag not in state.tags.get(other_id, frozenset()):
                continue
            if with_ephemeral and with_ephemeral not in state.ephemeral_tags.get(
                other_id, frozenset()
            ):
                continue
            matched.append(other_id)
    matched.sort()
    return _evidence(
        "count_co_located",
        params={
            "minimum": minimum,
            "with_tag": with_tag,
            "with_ephemeral": with_ephemeral,
            "slot": slot,
        },
        entities={slot: entity_id},
        observed={
            "in_transit": in_transit,
            "place_id": place_id,
            "count": len(matched),
        },
        matched=matched,
        result=(
            entity_id is not None
            and not in_transit
            and place_id is not None
            and len(matched) >= minimum
        ),
    )


@_resolver("has_established_partner_co_located")
def _has_established_partner_co_located(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot = match["slot"]
    entity_id = _entity(bindings, slot)
    in_transit = entity_id is not None and _is_in_transit(state, entity_id)
    place_id = state.locations.get(entity_id) if entity_id is not None else None
    matched: list[dict[str, Any]] = []
    if entity_id is not None and not in_transit and place_id is not None:
        for (source, target), relationship_types in state.relationship_types.items():
            if entity_id not in (source, target):
                continue
            partner_types = sorted(
                ESTABLISHED_PARTNER_RELATIONSHIP_TYPES & relationship_types
            )
            if not partner_types:
                continue
            partner_id = target if source == entity_id else source
            if (
                not _is_in_transit(state, partner_id)
                and state.locations.get(partner_id) == place_id
            ):
                matched.append(
                    {
                        "partner_entity_id": partner_id,
                        "relationship_types": partner_types,
                    }
                )
    return _evidence(
        "has_established_partner_co_located",
        params={
            "slot": slot,
            "family": "established_partner_relationship_types",
            "family_members": sorted(ESTABLISHED_PARTNER_RELATIONSHIP_TYPES),
        },
        entities={slot: entity_id},
        observed={"in_transit": in_transit, "place_id": place_id},
        matched=matched,
        result=bool(matched),
    )


# ---------------------------------------------------------------------------
# Travel
# ---------------------------------------------------------------------------


def _travel_state(state: WorldState, entity_id: Optional[int]) -> Optional[dict]:
    if entity_id is None:
        return None
    travel = state.travel_states.get(entity_id)
    return asdict(travel) if travel is not None else None


@_resolver("is_in_transit")
def _is_in_transit_evidence(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot = match["slot"]
    entity_id = _entity(bindings, slot)
    travel = _travel_state(state, entity_id)
    return _evidence(
        "is_in_transit",
        params={"slot": slot},
        entities={slot: entity_id},
        observed={"travel_status": travel["status"] if travel else None},
        result=entity_id is not None and _is_in_transit(state, entity_id),
    )


@_resolver("has_travel_destination")
def _has_travel_destination(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot = match["slot"]
    entity_id = _entity(bindings, slot)
    travel = _travel_state(state, entity_id)
    destination = travel["destination_place_id"] if travel else None
    return _evidence(
        "has_travel_destination",
        params={"slot": slot},
        entities={slot: entity_id},
        observed={"destination_place_id": destination},
        result=entity_id is not None and destination is not None,
    )


@_resolver("travel_progress_at_or_above")
def _travel_progress_at_or_above(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot = match["slot"]
    threshold = float(match["threshold"])
    entity_id = _entity(bindings, slot)
    travel = _travel_state(state, entity_id)
    progress = travel["progress_ratio"] if travel else None
    return _evidence(
        "travel_progress_at_or_above",
        params={"threshold": threshold, "slot": slot},
        entities={slot: entity_id},
        observed={"progress_ratio": progress},
        result=(
            entity_id is not None and progress is not None and progress >= threshold
        ),
    )


@_resolver("travel_purpose_is")
def _travel_purpose_is(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot = match["slot"]
    candidates = match["purpose"].split(",")
    entity_id = _entity(bindings, slot)
    travel = _travel_state(state, entity_id)
    raw_purpose = travel["route_purpose"] if travel else None
    normalized = str(raw_purpose).strip().lower() if raw_purpose is not None else None
    matched = [normalized] if normalized in candidates else []
    return _evidence(
        "travel_purpose_is",
        params={"purposes": candidates, "slot": slot},
        entities={slot: entity_id},
        observed={"route_purpose": raw_purpose},
        matched=matched,
        result=entity_id is not None and bool(matched),
    )


@_resolver("travel_risk_is")
def _travel_risk_is(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot = match["slot"]
    candidates = match["values"].split(",")
    entity_id = _entity(bindings, slot)
    travel = _travel_state(state, entity_id)
    risk = travel["risk"] if travel else None
    matched = [risk] if risk in candidates else []
    return _evidence(
        "travel_risk_is",
        params={"risks": candidates, "slot": slot},
        entities={slot: entity_id},
        observed={"risk": risk},
        matched=matched,
        result=entity_id is not None and travel is not None and bool(matched),
    )


# ---------------------------------------------------------------------------
# Routine anchors
# ---------------------------------------------------------------------------


def _anchor_observation(
    state: WorldState, entity_id: Optional[int], anchor_type: str
) -> tuple[Optional[Any], dict[str, Any]]:
    anchor = (
        _routine_anchor(state, entity_id, anchor_type)
        if entity_id is not None
        else None
    )
    observed: dict[str, Any] = {
        "anchor": asdict(anchor) if anchor is not None else None,
        "current_place_id": (
            state.locations.get(entity_id) if entity_id is not None else None
        ),
    }
    return anchor, observed


def _anchor_active(anchor: Optional[Any]) -> bool:
    return bool(anchor and anchor.mobility_policy not in {"none", "nomadic"})


@_resolver("has_routine_anchor")
def _has_routine_anchor(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot, anchor_type = match["slot"], match["anchor"]
    entity_id = _entity(bindings, slot)
    anchor, observed = _anchor_observation(state, entity_id, anchor_type)
    return _evidence(
        "has_routine_anchor",
        params={"anchor_type": anchor_type, "slot": slot},
        entities={slot: entity_id},
        observed=observed,
        result=entity_id is not None and _anchor_active(anchor),
    )


@_resolver("routine_anchor_due")
def _routine_anchor_due(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot, anchor_type = match["slot"], match["anchor"]
    entity_id = _entity(bindings, slot)
    anchor, observed = _anchor_observation(state, entity_id, anchor_type)
    observed["world_time"] = (
        state.world_time.isoformat() if state.world_time is not None else None
    )
    due = (
        anchor is not None
        and _anchor_active(anchor)
        and _routine_schedule_due(anchor.schedule, state.world_time)
    )
    return _evidence(
        "routine_anchor_due",
        params={"anchor_type": anchor_type, "slot": slot},
        entities={slot: entity_id},
        observed=observed,
        result=entity_id is not None and due,
    )


@_resolver("at_routine_anchor")
def _at_routine_anchor_evidence(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, anchor_type = match["slot"], match["anchor"]
    entity_id = _entity(bindings, slot)
    _, observed = _anchor_observation(state, entity_id, anchor_type)
    current_place = observed["current_place_id"]
    observed["current_place_zone"] = (
        state.location_zones.get(current_place) if current_place is not None else None
    )
    return _evidence(
        "at_routine_anchor",
        params={"anchor_type": anchor_type, "slot": slot},
        entities={slot: entity_id},
        observed=observed,
        result=(
            entity_id is not None and _at_routine_anchor(state, entity_id, anchor_type)
        ),
    )


@_resolver("away_from_routine_anchor")
def _away_from_routine_anchor(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, anchor_type = match["slot"], match["anchor"]
    entity_id = _entity(bindings, slot)
    anchor, observed = _anchor_observation(state, entity_id, anchor_type)
    current_place = observed["current_place_id"]
    observed["current_place_zone"] = (
        state.location_zones.get(current_place) if current_place is not None else None
    )
    return _evidence(
        "away_from_routine_anchor",
        params={"anchor_type": anchor_type, "slot": slot},
        entities={slot: entity_id},
        observed=observed,
        result=(
            entity_id is not None
            and _anchor_active(anchor)
            and not _at_routine_anchor(state, entity_id, anchor_type)
        ),
    )


@_resolver("routine_anchor_has_destination")
def _routine_anchor_has_destination(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot, anchor_type = match["slot"], match["anchor"]
    entity_id = _entity(bindings, slot)
    anchor, observed = _anchor_observation(state, entity_id, anchor_type)
    observed["known_zone_ids"] = sorted(set(state.location_zones.values()))
    return _evidence(
        "routine_anchor_has_destination",
        params={"anchor_type": anchor_type, "slot": slot},
        entities={slot: entity_id},
        observed=observed,
        result=(
            entity_id is not None
            and _routine_anchor_destination_available(state, entity_id, anchor_type)
        ),
    )


# ---------------------------------------------------------------------------
# Trust and relationships
# ---------------------------------------------------------------------------


def _directed_trust(
    state: WorldState, source: Optional[int], target: Optional[int]
) -> int:
    if source is None or target is None:
        return 0
    return state.trust.get((source, target), 0)


@_resolver("trust_at_least")
def _trust_at_least(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot_a, slot_b = match["a"], match["b"]
    threshold = int(match["thresh"])
    source = _entity(bindings, slot_a)
    target = _entity(bindings, slot_b)
    trust = _directed_trust(state, source, target)
    return _evidence(
        "trust_at_least",
        params={"threshold": threshold, "from_slot": slot_a, "to_slot": slot_b},
        entities={slot_a: source, slot_b: target},
        observed={"trust": trust},
        result=source is not None and target is not None and trust >= threshold,
    )


@_resolver("trust_below")
def _trust_below(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    slot_a, slot_b = match["a"], match["b"]
    threshold = int(match["thresh"])
    source = _entity(bindings, slot_a)
    target = _entity(bindings, slot_b)
    trust = _directed_trust(state, source, target)
    return _evidence(
        "trust_below",
        params={"threshold": threshold, "from_slot": slot_a, "to_slot": slot_b},
        entities={slot_a: source, slot_b: target},
        observed={"trust": trust},
        result=source is not None and target is not None and trust < threshold,
    )


@_resolver("relationship_is_mutual_warm")
def _relationship_is_mutual_warm(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot_a, slot_b = match["a"], match["b"]
    source = _entity(bindings, slot_a)
    target = _entity(bindings, slot_b)
    forward = _directed_trust(state, source, target)
    reverse = _directed_trust(state, target, source)
    return _evidence(
        "relationship_is_mutual_warm",
        params={
            "forward_min": 2,
            "reverse_min": 1,
            "slot_a": slot_a,
            "slot_b": slot_b,
        },
        entities={slot_a: source, slot_b: target},
        observed={"forward_trust": forward, "reverse_trust": reverse},
        result=(
            source is not None and target is not None and forward >= 2 and reverse >= 1
        ),
    )


@_resolver("relationship_is_asymmetric")
def _relationship_is_asymmetric(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot_a, slot_b = match["a"], match["b"]
    threshold = int(match["thresh"])
    source = _entity(bindings, slot_a)
    target = _entity(bindings, slot_b)
    forward = _directed_trust(state, source, target)
    reverse = _directed_trust(state, target, source)
    loaded = forward >= LOADED_TRUST_FORWARD_MIN and reverse <= LOADED_TRUST_REVERSE_MAX
    return _evidence(
        "relationship_is_asymmetric",
        params={"gap_threshold": threshold, "slot_a": slot_a, "slot_b": slot_b},
        entities={slot_a: source, slot_b: target},
        observed={
            "forward_trust": forward,
            "reverse_trust": reverse,
            "gap": abs(forward - reverse),
            "loaded_one_sided": loaded,
        },
        result=(
            source is not None
            and target is not None
            and _trust_values_are_asymmetric(forward, reverse, threshold)
        ),
    )


@_resolver("direct_contact_is_dramatic")
def _direct_contact_is_dramatic(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot_a, slot_b = match["a"], match["b"]
    source = _entity(bindings, slot_a)
    target = _entity(bindings, slot_b)
    source_dramatic = sorted(DRAMATIC_CONTACT_TAGS & _current_tags(state, source))
    target_dramatic = sorted(DRAMATIC_CONTACT_TAGS & _current_tags(state, target))
    forward = _directed_trust(state, source, target)
    reverse = _directed_trust(state, target, source)
    triggers: list[str] = []
    if source_dramatic or target_dramatic:
        triggers.append("dramatic_tags")
    if reverse <= -2:
        triggers.append("reverse_trust_hostile")
    if _trust_values_are_asymmetric(forward, reverse):
        triggers.append("trust_asymmetry")
    return _evidence(
        "direct_contact_is_dramatic",
        params={"from_slot": slot_a, "to_slot": slot_b},
        entities={slot_a: source, slot_b: target},
        observed={
            "dramatic_tags": {slot_a: source_dramatic, slot_b: target_dramatic},
            "forward_trust": forward,
            "reverse_trust": reverse,
        },
        matched=triggers,
        result=source is not None and target is not None and bool(triggers),
    )


@_resolver("has_relationship_of_type")
def _has_relationship_of_type(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot_from, slot_to = match["from"], match["to"]
    relationship_type = match["type"]
    source = _entity(bindings, slot_from)
    target = _entity(bindings, slot_to)
    edge = (
        state.relationship_types.get((source, target), frozenset())
        if source is not None and target is not None
        else frozenset()
    )
    return _evidence(
        "has_relationship_of_type",
        params={
            "relationship_type": relationship_type,
            "from_slot": slot_from,
            "to_slot": slot_to,
        },
        entities={slot_from: source, slot_to: target},
        observed={"edge_types": sorted(edge)},
        matched=[relationship_type] if relationship_type in edge else [],
        result=(
            source is not None and target is not None and relationship_type in edge
        ),
    )


@_resolver("has_symmetric_relationship_of_type")
def _has_symmetric_relationship_of_type(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot_a, slot_b = match["a"], match["b"]
    relationship_type = match["type"]
    left = _entity(bindings, slot_a)
    right = _entity(bindings, slot_b)
    forward_edge = (
        state.relationship_types.get((left, right), frozenset())
        if left is not None and right is not None
        else frozenset()
    )
    reverse_edge = (
        state.relationship_types.get((right, left), frozenset())
        if left is not None and right is not None
        else frozenset()
    )
    matched = [
        direction
        for direction, edge in (("forward", forward_edge), ("reverse", reverse_edge))
        if relationship_type in edge
    ]
    return _evidence(
        "has_symmetric_relationship_of_type",
        params={
            "relationship_type": relationship_type,
            "slot_a": slot_a,
            "slot_b": slot_b,
        },
        entities={slot_a: left, slot_b: right},
        observed={
            "forward_edge_types": sorted(forward_edge),
            "reverse_edge_types": sorted(reverse_edge),
        },
        matched=matched,
        result=bool(matched),
    )


@_resolver("faction_member")
def _faction_member(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    member_slot, faction_slot = match["member"], match["faction"]
    member_id = _entity(bindings, member_slot)
    faction_id = _entity(bindings, faction_slot)
    memberships = (
        state.faction_memberships.get(member_id, frozenset())
        if member_id is not None
        else frozenset()
    )
    return _evidence(
        "faction_member",
        params={"member_slot": member_slot, "faction_slot": faction_slot},
        entities={member_slot: member_id, faction_slot: faction_id},
        observed={"faction_ids": sorted(memberships)},
        matched=[faction_id] if faction_id in memberships else [],
        result=(
            member_id is not None
            and faction_id is not None
            and faction_id in memberships
        ),
    )


@_resolver("relative_orbit_distance")
def _relative_orbit_distance(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    slot_a, slot_b = match["a"], match["b"]
    max_distance = int(match["n"])
    source = _entity(bindings, slot_a)
    target = _entity(bindings, slot_b)
    distance = (
        state.orbit_distance.get((source, target))
        if source is not None and target is not None
        else None
    )
    return _evidence(
        "relative_orbit_distance",
        params={"max_distance": max_distance, "from_slot": slot_a, "to_slot": slot_b},
        entities={slot_a: source, slot_b: target},
        observed={"orbit_distance": distance},
        result=distance is not None and distance <= max_distance,
    )


# ---------------------------------------------------------------------------
# Global scalars
# ---------------------------------------------------------------------------


@_resolver("time_of_day_in")
def _time_of_day_in(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    candidates = match["values"].split(",")
    matched = [state.time_of_day] if state.time_of_day in candidates else []
    return _evidence(
        "time_of_day_in",
        params={"times": candidates},
        entities={},
        observed={"time_of_day": state.time_of_day},
        matched=matched,
        result=bool(matched),
    )


@_resolver("weather_is")
def _weather_is(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    candidates = match["values"].split(",")
    actor_id = _entity(bindings, Slot.ACTOR.value)
    observed_weather = weather_for_actor(state, bindings)
    matched = [observed_weather] if observed_weather in candidates else []
    return _evidence(
        "weather_is",
        params={"weather": candidates},
        entities={Slot.ACTOR.value: actor_id},
        observed={"actor_weather": observed_weather},
        matched=matched,
        result=bool(matched),
    )


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def _event_payload(event: Any) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "tick": event.tick,
        "actor_entity_id": event.actor_entity_id,
        "target_entity_id": event.target_entity_id,
    }


@_resolver("recent_event")
def _recent_event(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    event_type = match["event"]
    within_ticks = int(match["n"])
    actor_slot = match["actor"]
    target_slot = match["target"]
    fields_filter_active = match.group(0).rstrip(")").endswith(",fields")
    actor_id = _entity(bindings, actor_slot) if actor_slot else None
    target_id = _entity(bindings, target_slot) if target_slot else None
    cutoff = state.current_tick - within_ticks
    matched: list[dict[str, Any]] = []
    slot_unbound = (actor_slot is not None and actor_id is None) or (
        target_slot is not None and target_id is None
    )
    if not slot_unbound:
        for event in state.recent_events:
            if event.tick < cutoff:
                continue
            if event_type != "*" and event.event_type != event_type:
                continue
            if actor_id is not None and event.actor_entity_id != actor_id:
                continue
            if target_id is not None and event.target_entity_id != target_id:
                continue
            matched.append(_event_payload(event))
    entities: dict[str, Optional[int]] = {}
    if actor_slot:
        entities[actor_slot] = actor_id
    if target_slot:
        entities[target_slot] = target_id
    return _evidence(
        "recent_event",
        params={
            "event_type": None if event_type == "*" else event_type,
            "within_ticks": within_ticks,
            "actor_slot": actor_slot,
            "target_slot": target_slot,
            "changed_fields_filter": fields_filter_active,
        },
        entities=entities,
        observed={"current_tick": state.current_tick, "cutoff_tick": cutoff},
        matched=matched,
        # The changed_fields filter set lives only inside the closure; with
        # the marker present the verdict is not recomputable from the name.
        result=None if fields_filter_active else bool(matched),
    )


@_resolver("knows_recent_event")
def _knows_recent_event(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    event_type = match["event"]
    within_ticks = int(match["n"])
    actor_slot = match["actor"]
    target_slot = match["target"]
    fields_filter_active = match.group(0).rstrip(")").endswith(",fields")
    knower_id = _entity(bindings, "actor")
    actor_id = _entity(bindings, actor_slot) if actor_slot else None
    target_id = _entity(bindings, target_slot) if target_slot else None
    cutoff = state.current_tick - within_ticks
    slot_unbound = (actor_slot is not None and actor_id is None) or (
        target_slot is not None and target_id is None
    )
    candidates: list[dict[str, Any]] = []
    known_event_ids: frozenset[int] = frozenset()
    if knower_id is not None:
        known_event_ids = state.awareness_by_entity.get(knower_id, frozenset())
    if not slot_unbound and (knower_id is not None or not state.epistemics_enabled):
        for event in state.recent_events:
            if event.tick < cutoff:
                continue
            if event_type != "*" and event.event_type != event_type:
                continue
            if actor_id is not None and event.actor_entity_id != actor_id:
                continue
            if target_id is not None and event.target_entity_id != target_id:
                continue
            scope = (
                state.claimed_event_scopes.get(event.event_id)
                if event.event_id is not None
                else None
            )
            actor_holds_awareness = event.event_id in known_event_ids
            visible_to_actor = (
                not state.epistemics_enabled
                or scope is None
                or scope == "common"
                or actor_holds_awareness
            )
            candidates.append(
                {
                    **_event_payload(event),
                    "claim_scope": scope,
                    "actor_holds_awareness": actor_holds_awareness,
                    "visible_to_actor": visible_to_actor,
                }
            )
    visible_candidates = [
        candidate for candidate in candidates if candidate["visible_to_actor"]
    ]
    if visible_candidates:
        selected = visible_candidates[0]
        event_id = selected["event_id"]
        if not state.epistemics_enabled:
            reason = "eligible because Epistemics is disabled"
        elif selected["claim_scope"] is None:
            reason = f"eligible because event {event_id} has no claim"
        elif selected["claim_scope"] == "common":
            reason = f"eligible because claim on event {event_id} is common"
        else:
            reason = f"eligible because actor holds awareness of event {event_id}"
    elif candidates:
        reason = (
            f"blocked: claim on event {candidates[0]['event_id']} not known to actor"
        )
    elif knower_id is None and state.epistemics_enabled:
        reason = "blocked: actor slot has no bound knower"
    else:
        reason = "blocked: no matching recent event"
    entities: dict[str, Optional[int]] = {"actor": knower_id}
    if actor_slot:
        entities[actor_slot] = actor_id
    if target_slot:
        entities[target_slot] = target_id
    return _evidence(
        "knows_recent_event",
        params={
            "event_type": None if event_type == "*" else event_type,
            "within_ticks": within_ticks,
            "knower_slot": "actor",
            "actor_slot": actor_slot,
            "target_slot": target_slot,
            "changed_fields_filter": fields_filter_active,
        },
        entities=entities,
        observed={
            "current_tick": state.current_tick,
            "cutoff_tick": cutoff,
            "epistemics_enabled": state.epistemics_enabled,
            "reason": reason,
        },
        matched=candidates,
        result=None if fields_filter_active else bool(visible_candidates),
    )


@_resolver("knows_claim_about")
def _knows_claim_about(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    subject_slot = match["subject"]
    about_slot = match["about"]
    subject_id = _entity(bindings, subject_slot)
    about_id = _entity(bindings, about_slot)
    possessed = (
        _possessed_claim_knowledge(state, subject_id) if subject_id is not None else ()
    )
    matched = [
        {
            "claim_id": record.claim_id,
            "tier": record.source_tier,
            "scope": record.scope,
        }
        for record in possessed
        if about_id is not None and about_id in record.about_entity_ids
    ]
    return _evidence(
        "knows_claim_about",
        params={"subject_slot": subject_slot, "about_slot": about_slot},
        entities={subject_slot: subject_id, about_slot: about_id},
        observed={
            "possessed_claims": [
                {"claim_id": record.claim_id, "tier": record.source_tier}
                for record in possessed
            ]
        },
        matched=matched,
        result=bool(matched),
    )


@_resolver("heard_secondhand")
def _heard_secondhand(match: re.Match, state: WorldState, bindings: Bindings) -> dict:
    subject_slot = match["subject"]
    subject_id = _entity(bindings, subject_slot)
    records = (
        _possessed_claim_knowledge(state, subject_id) if subject_id is not None else ()
    )
    matched = [
        {
            "claim_id": record.claim_id,
            "tier": record.source_tier,
            "channel": record.channel,
            "immediate_source_entity_id": record.immediate_source_entity_id,
        }
        for record in records
        if record.source_tier == "told"
    ]
    return _evidence(
        "heard_secondhand",
        params={"subject_slot": subject_slot},
        entities={subject_slot: subject_id},
        observed={"awareness_count": len(records)},
        matched=matched,
        result=bool(matched),
    )


@_resolver("since_last_event_at_least")
def _since_last_event_at_least(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    event_type = match["event"]
    minimum_ticks = int(match["n"])
    actor_slot = match["actor"]
    target_slot = match["target"]
    actor_id = _entity(bindings, actor_slot)
    target_id = _entity(bindings, target_slot) if target_slot else None
    latest_tick: Optional[int] = None
    if actor_id is not None and not (target_slot is not None and target_id is None):
        for event in state.recent_events:
            if event.event_type != event_type:
                continue
            if event.actor_entity_id != actor_id:
                continue
            if target_id is not None and event.target_entity_id != target_id:
                continue
            if latest_tick is None or event.tick > latest_tick:
                latest_tick = event.tick
    elapsed = state.current_tick - latest_tick if latest_tick is not None else None
    entities: dict[str, Optional[int]] = {actor_slot: actor_id}
    if target_slot:
        entities[target_slot] = target_id
    if actor_id is None or (target_slot is not None and target_id is None):
        result = False
    else:
        result = elapsed is None or elapsed >= minimum_ticks
    return _evidence(
        "since_last_event_at_least",
        params={
            "event_type": event_type,
            "minimum_ticks": minimum_ticks,
            "actor_slot": actor_slot,
            "target_slot": target_slot,
        },
        entities=entities,
        observed={
            "current_tick": state.current_tick,
            "latest_matching_tick": latest_tick,
            "elapsed_ticks": elapsed,
        },
        result=result,
    )


@_resolver("project_due")
def _project_due(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict[str, Any]:
    project_type = match["project"]
    mode = match["mode"]
    slot = match["slot"]
    entity_id = _entity(bindings, slot)
    project = state.project_states.get(entity_id) if entity_id is not None else None
    project_payload = asdict(project) if project is not None else None
    if project_payload is not None:
        next_eligible = project_payload.get("next_eligible_at_world_time")
        if next_eligible is not None:
            project_payload["next_eligible_at_world_time"] = next_eligible.isoformat()
    overdue_hours: Optional[float] = None
    if (
        project is not None
        and project.next_eligible_at_world_time is not None
        and state.world_time is not None
    ):
        overdue_hours = project_overdue_hours(
            state.world_time, project.next_eligible_at_world_time
        )
    condition = project_due(
        mode,
        project_type=project_type,
        slot=Slot(slot),
    )

    return _evidence(
        "project_due",
        params={
            "project_type": project_type,
            "mode": mode,
            "slot": slot,
        },
        entities={slot: entity_id},
        observed={
            "world_time": (
                state.world_time.isoformat() if state.world_time is not None else None
            ),
            "project": project_payload,
            "overdue_hours": overdue_hours,
            "advance_interval_hours": (state.project_policy.advance_interval_hours),
            "stall_abandon_threshold": (state.project_policy.stall_abandon_threshold),
            "abandon_after_stalled_world_hours": (
                state.project_policy.abandon_after_stalled_world_hours
            ),
        },
        result=condition(state, bindings),
    )


@_resolver("project_target_is")
def _project_target_is(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict[str, Any]:
    slot = match["slot"]
    actor_entity_id = _entity(bindings, Slot.ACTOR.value)
    bound_target_entity_id = _entity(bindings, slot)
    project = (
        state.project_states.get(actor_entity_id)
        if actor_entity_id is not None
        else None
    )
    project_target_entity_id = (
        project.target_character_entity_id if project is not None else None
    )
    project_target_active = (
        project.target_character_is_active if project is not None else None
    )
    condition = project_target_is(Slot(slot))
    result = condition(state, bindings)
    if result:
        explanation = f"advancing recruitment of {slot}"
    else:
        explanation = "blocked: bound target is not the project's recruit"
    return _evidence(
        "project_target_is",
        params={"slot": slot},
        entities={"actor": actor_entity_id, slot: bound_target_entity_id},
        observed={
            "project_id": project.id if project is not None else None,
            "project_type": project.project_type if project is not None else None,
            "project_target_entity_id": project_target_entity_id,
            "project_target_is_active": project_target_active,
            "bound_target_entity_id": bound_target_entity_id,
            "explanation": explanation,
        },
        result=result,
        matched=[bound_target_entity_id] if result else [],
    )


@_resolver("project_target_is_active")
def _project_target_is_active(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict[str, Any]:
    slot = match["slot"]
    actor_entity_id = _entity(bindings, Slot.ACTOR.value)
    bound_target_entity_id = _entity(bindings, slot)
    project = (
        state.project_states.get(actor_entity_id)
        if actor_entity_id is not None
        else None
    )
    project_target_entity_id = (
        project.target_character_entity_id if project is not None else None
    )
    project_target_active = (
        project.target_character_is_active if project is not None else None
    )
    condition = project_target_is_active(Slot(slot))
    result = condition(state, bindings)
    if result:
        explanation = "project's recruit is an active character"
    elif (
        project_target_entity_id == bound_target_entity_id
        and project_target_entity_id is not None
    ):
        explanation = "project's recruit is inactive or not a character"
    else:
        explanation = "blocked: bound target is not the project's recruit"
    return _evidence(
        "project_target_is_active",
        params={"slot": slot},
        entities={"actor": actor_entity_id, slot: bound_target_entity_id},
        observed={
            "project_id": project.id if project is not None else None,
            "project_type": project.project_type if project is not None else None,
            "project_target_entity_id": project_target_entity_id,
            "project_target_is_active": project_target_active,
            "bound_target_entity_id": bound_target_entity_id,
            "explanation": explanation,
        },
        result=result,
        matched=[bound_target_entity_id] if result else [],
    )


@_resolver("project_faction_is")
def _project_faction_is(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict[str, Any]:
    slot = match["slot"]
    actor_entity_id = _entity(bindings, Slot.ACTOR.value)
    bound_faction_entity_id = _entity(bindings, slot)
    project = (
        state.project_states.get(actor_entity_id)
        if actor_entity_id is not None
        else None
    )
    project_faction_entity_id = (
        project.target_faction_entity_id if project is not None else None
    )
    project_faction_active = (
        project.target_faction_is_active if project is not None else None
    )
    condition = project_faction_is(Slot(slot))
    result = condition(state, bindings)
    return _evidence(
        "project_faction_is",
        params={"slot": slot},
        entities={"actor": actor_entity_id, slot: bound_faction_entity_id},
        observed={
            "project_id": project.id if project is not None else None,
            "project_type": project.project_type if project is not None else None,
            "project_faction_entity_id": project_faction_entity_id,
            "project_faction_is_active": project_faction_active,
            "bound_faction_entity_id": bound_faction_entity_id,
            "explanation": (
                "advancing the stored institutional counterparty"
                if result
                else "blocked: bound faction is not the project's counterparty"
            ),
        },
        result=result,
        matched=[bound_faction_entity_id] if result else [],
    )


@_resolver("project_faction_is_active")
def _project_faction_is_active(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict[str, Any]:
    slot = match["slot"]
    actor_entity_id = _entity(bindings, Slot.ACTOR.value)
    bound_faction_entity_id = _entity(bindings, slot)
    project = (
        state.project_states.get(actor_entity_id)
        if actor_entity_id is not None
        else None
    )
    project_faction_entity_id = (
        project.target_faction_entity_id if project is not None else None
    )
    project_faction_active = (
        project.target_faction_is_active if project is not None else None
    )
    condition = project_faction_is_active(Slot(slot))
    result = condition(state, bindings)
    if result:
        explanation = "project's institutional counterparty is an active faction"
    elif (
        project_faction_entity_id == bound_faction_entity_id
        and project_faction_entity_id is not None
    ):
        explanation = (
            "project's institutional counterparty is inactive or not a faction"
        )
    else:
        explanation = "blocked: bound faction is not the project's counterparty"
    return _evidence(
        "project_faction_is_active",
        params={"slot": slot},
        entities={"actor": actor_entity_id, slot: bound_faction_entity_id},
        observed={
            "project_id": project.id if project is not None else None,
            "project_type": project.project_type if project is not None else None,
            "project_faction_entity_id": project_faction_entity_id,
            "project_faction_is_active": project_faction_active,
            "bound_faction_entity_id": bound_faction_entity_id,
            "explanation": explanation,
        },
        result=result,
        matched=[bound_faction_entity_id] if result else [],
    )


@_resolver("count_recent_events_at_least")
def _count_recent_events_at_least(
    match: re.Match, state: WorldState, bindings: Bindings
) -> dict:
    event_type = match["event"]
    min_count = int(match["count"])
    within_ticks = int(match["n"])
    actor_slot = match["actor"]
    target_slot = match["target"]
    actor_id = _entity(bindings, actor_slot)
    target_id = _entity(bindings, target_slot) if target_slot else None
    slot_unbound = actor_id is None or (target_slot is not None and target_id is None)
    cutoff = state.current_tick - within_ticks
    matched: list[dict[str, Any]] = []
    if not slot_unbound:
        for event in state.recent_events:
            if event.tick < cutoff:
                continue
            if event.event_type != event_type:
                continue
            if event.actor_entity_id != actor_id:
                continue
            if target_id is not None and event.target_entity_id != target_id:
                continue
            matched.append(_event_payload(event))
    entities: dict[str, Optional[int]] = {actor_slot: actor_id}
    if target_slot:
        entities[target_slot] = target_id
    return _evidence(
        "count_recent_events_at_least",
        params={
            "event_type": event_type,
            "min_count": min_count,
            "within_ticks": within_ticks,
            "actor_slot": actor_slot,
            "target_slot": target_slot,
        },
        entities=entities,
        observed={
            "current_tick": state.current_tick,
            "cutoff_tick": cutoff,
            "matched_count": len(matched),
        },
        matched=matched,
        result=False if slot_unbound else len(matched) >= min_count,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def resolve_evidence(
    name: str, state: WorldState, bindings: Bindings
) -> dict[str, Any]:
    """Return the evidence payload for one leaf predicate name.

    Raises :class:`EvidenceResolutionError` for names with no resolver —
    coverage over every builtin leaf is enforced by tests, so an unknown
    name means a new predicate factory landed without evidence support.
    """

    if name == "ALWAYS":
        return _evidence("always", params={}, entities={}, observed={}, result=True)
    if name == "NEVER":
        return _evidence("never", params={}, entities={}, observed={}, result=False)

    kind = name.split("(", 1)[0]
    resolver = _RESOLVERS.get(kind)
    if resolver is None:
        raise EvidenceResolutionError(
            f"No evidence resolver for predicate kind {kind!r} (leaf {name!r}); "
            "add one to nexus/agents/orrery/evidence.py"
        )
    for pattern, _formatter in _PREDICATE_PARSERS:
        match = pattern.fullmatch(name)
        if match is not None:
            return resolver(match, state, bindings)
    raise EvidenceResolutionError(
        f"Leaf {name!r} matched no catalog parser; the __name__ grammar and "
        "catalog._PREDICATE_PARSERS have drifted"
    )
