"""Dry-run resolver integration for Orrery behavior packages."""

from __future__ import annotations

from collections.abc import Iterable as IterableABC
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Tuple

from sqlalchemy import text

from nexus.agents.orrery.reciprocal import (
    OrreryJointBeat,
    coerce_joint_beats,
    detect_joint_beats,
)
from nexus.agents.orrery.substrate import (
    PackageSelection,
    coerce_branch_selection,
    coerce_habituation,
    coerce_package_selection,
    Bindings,
    EventRecord,
    INTIMACY_SUPPRESSOR_TAGS,
    PresentTargetPolicy,
    Resolution,
    RoutineAnchor,
    Slot,
    Template,
    TravelState,
    WorldState,
    binding_hash,
    evaluate_stack,
)
from nexus.agents.orrery.needs import (
    NEED_SEVERITY_PREFIX,
    NeedTuning,
    coerce_need_tuning,
    effective_debt_score,
    need_applies_to_tags,
    severity_for_debt,
)

LOCATION_CLASS_TAG_CATEGORIES: tuple[str, ...] = (
    "place_function",
    "place_visibility",
    "place_access",
    "place_environment",
    "place_threat",
)
# Safe: assembled only from hardcoded LOCATION_CLASS_TAG_CATEGORIES values.
_LOCATION_CLASS_CATEGORY_SQL = ", ".join(
    f"'{category}'" for category in LOCATION_CLASS_TAG_CATEGORIES
)


def _proposal_id(template_id: str, binding_hash_value: str) -> str:
    """Return the stable public identifier for one tick proposal."""

    return f"{template_id}:{binding_hash_value}"


@dataclass(frozen=True, slots=True)
class OrreryResolutionDraft:
    """Serializable dry-run result for one actor-bound package resolution."""

    template_id: str
    priority: int
    binding_hash: str
    bindings: Mapping[str, Any]
    branch_label: str
    narrative_stub: str
    state_delta: Mapping[str, Any] = field(default_factory=dict)
    event_type: Optional[str] = None
    signal_event_type: Optional[str] = None
    changed_fields: Tuple[str, ...] = ()
    magnitude: float = 0.0
    # Slot name -> entity display name. Skald adjudicates these proposals;
    # without names it cannot tell WHO an off-screen resolution is about and
    # may misattribute it to an on-screen character (M9 gate finding).
    binding_names: Mapping[str, str] = field(default_factory=dict)

    @property
    def proposal_id(self) -> str:
        """Stable identifier Skald can use to adjudicate this proposal."""

        return _proposal_id(self.template_id, self.binding_hash)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this draft."""

        return {
            "proposal_id": self.proposal_id,
            "template_id": self.template_id,
            "priority": self.priority,
            "binding_hash": self.binding_hash,
            "bindings": dict(self.bindings),
            "binding_names": dict(self.binding_names),
            "branch_label": self.branch_label,
            "narrative_stub": self.narrative_stub,
            "state_delta": dict(self.state_delta),
            "event_type": self.event_type,
            "signal_event_type": self.signal_event_type,
            "changed_fields": list(self.changed_fields),
            "magnitude": self.magnitude,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OrreryResolutionDraft":
        """Hydrate a draft from incubator JSONB data."""

        template_id = str(data["template_id"])
        binding_hash_value = str(data["binding_hash"])
        expected_proposal_id = _proposal_id(template_id, binding_hash_value)
        stored_proposal_id = data.get("proposal_id")
        if (
            stored_proposal_id is not None
            and str(stored_proposal_id) != expected_proposal_id
        ):
            raise ValueError(
                "Orrery proposal_id does not match template_id/binding_hash: "
                f"{stored_proposal_id!r} != {expected_proposal_id!r}"
            )

        return cls(
            template_id=template_id,
            priority=int(data["priority"]),
            binding_hash=binding_hash_value,
            bindings=dict(data.get("bindings") or {}),
            branch_label=str(data["branch_label"]),
            narrative_stub=str(data["narrative_stub"]),
            state_delta=dict(data.get("state_delta") or {}),
            event_type=data.get("event_type"),
            signal_event_type=data.get("signal_event_type"),
            changed_fields=tuple(data.get("changed_fields") or ()),
            magnitude=float(data.get("magnitude") or 0.0),
            binding_names=dict(data.get("binding_names") or {}),
        )


@dataclass(frozen=True, slots=True)
class OrreryScenePressureDraft:
    """Serializable Storyteller-facing pressure involving an on-screen target."""

    template_id: str
    priority: int
    binding_hash: str
    bindings: Mapping[str, Any]
    branch_label: str
    pressure_stub: str
    prompt_text: str
    magnitude: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this scene pressure."""

        return {
            "template_id": self.template_id,
            "priority": self.priority,
            "binding_hash": self.binding_hash,
            "bindings": dict(self.bindings),
            "branch_label": self.branch_label,
            "pressure_stub": self.pressure_stub,
            "prompt_text": self.prompt_text,
            "magnitude": self.magnitude,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OrreryScenePressureDraft":
        """Hydrate a scene pressure draft from incubator JSONB data."""

        pressure_stub = str(data["pressure_stub"])
        return cls(
            template_id=str(data["template_id"]),
            priority=int(data["priority"]),
            binding_hash=str(data["binding_hash"]),
            bindings=dict(data.get("bindings") or {}),
            branch_label=str(data["branch_label"]),
            pressure_stub=pressure_stub,
            prompt_text=str(data.get("prompt_text") or pressure_stub),
            magnitude=float(data.get("magnitude") or 0.0),
        )


@dataclass(frozen=True, slots=True)
class OrreryTickProposal:
    """No-write Orrery proposal produced before accepted chunk commit."""

    anchor_chunk_id: Optional[int]
    actor_count: int
    resolutions: Tuple[OrreryResolutionDraft, ...]
    scene_pressures: Tuple[OrreryScenePressureDraft, ...] = ()
    joint_beats: Tuple[OrreryJointBeat, ...] = ()
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def resolution_count(self) -> int:
        """Return the number of draft resolutions in this proposal."""

        return len(self.resolutions)

    @property
    def pressure_count(self) -> int:
        """Return the number of Storyteller-mediated scene pressures."""

        return len(self.scene_pressures)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this proposal."""

        return {
            "anchor_chunk_id": self.anchor_chunk_id,
            "actor_count": self.actor_count,
            "generated_at": self.generated_at,
            "resolutions": [draft.to_dict() for draft in self.resolutions],
            "scene_pressures": [
                pressure.to_dict() for pressure in self.scene_pressures
            ],
            "joint_beats": [beat.to_dict() for beat in self.joint_beats],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OrreryTickProposal":
        """Hydrate a proposal from incubator JSONB data."""

        return cls(
            anchor_chunk_id=data.get("anchor_chunk_id"),
            actor_count=int(data.get("actor_count") or 0),
            generated_at=str(data["generated_at"]),
            resolutions=tuple(
                OrreryResolutionDraft.from_dict(item)
                for item in data.get("resolutions", ())
            ),
            scene_pressures=tuple(
                OrreryScenePressureDraft.from_dict(item)
                for item in data.get("scene_pressures", ())
            ),
            joint_beats=coerce_joint_beats(data.get("joint_beats")),
        )


def _should_replace_trust_magnitude(current: Optional[int], candidate: int) -> bool:
    """Choose a stable representative if a read surface emits duplicate pairs."""

    if current is None:
        return True
    if abs(candidate) != abs(current):
        return abs(candidate) > abs(current)
    return candidate < current


def hydrate_world_state(
    session: Any,
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
    need_tuning: Optional[NeedTuning] = None,
    world_time_override: Optional[datetime] = None,
    win_history_window: int = 0,
) -> WorldState:
    """Hydrate the read-side Orrery state snapshot from database tables.

    ``win_history_window`` > 0 additionally hydrates committed win counts
    per (actor, template) over that many trailing ticks for habituation
    dampening; 0 skips the query (habituation off).
    """

    need_tuning = coerce_need_tuning(need_tuning)

    tags: dict[int, set[str]] = {}
    ephemeral_tags: dict[int, set[str]] = {}
    for row in session.execute(
        text(
            """
            /* orrery:current_tags */
            SELECT entity_id, tag, is_ephemeral
            FROM entity_tags_current
            """
        )
    ).mappings():
        target = ephemeral_tags if row["is_ephemeral"] else tags
        target.setdefault(row["entity_id"], set()).add(row["tag"])

    locations = {
        row["entity_id"]: row["current_location"]
        for row in session.execute(
            text(
                """
                /* orrery:character_locations */
                SELECT entity_id, current_location
                FROM characters
                WHERE entity_id IS NOT NULL
                  AND current_location IS NOT NULL
                """
            )
        ).mappings()
    }

    location_class: dict[int, str] = {}
    location_classes: dict[int, set[str]] = {}
    location_entity_ids: dict[int, int] = {}
    location_zones: dict[int, int] = {}
    for row in session.execute(
        text(
            f"""
            /* orrery:location_classes */
            SELECT p.id,
                   p.entity_id AS place_entity_id,
                   p.zone AS zone_id,
                   p.type::text AS location_class,
                   true AS is_primary
            FROM places p
            WHERE p.type IS NOT NULL
            UNION ALL
            SELECT p.id,
                   p.entity_id AS place_entity_id,
                   p.zone AS zone_id,
                   etc.tag AS location_class,
                   false AS is_primary
            FROM places p
            JOIN entity_tags_current etc ON etc.entity_id = p.entity_id
            WHERE etc.entity_kind = 'place'
              AND etc.category IN ({_LOCATION_CLASS_CATEGORY_SQL})
            """
        )
    ).mappings():
        place_id = row["id"]
        class_name = row["location_class"]
        if class_name is None:
            continue
        place_entity_id = row.get("place_entity_id")
        if place_entity_id is not None:
            location_entity_ids[place_id] = place_entity_id
        zone_id = row.get("zone_id")
        if zone_id is not None:
            location_zones[place_id] = zone_id
        location_classes.setdefault(place_id, set()).add(class_name)
        if row["is_primary"]:
            location_class[place_id] = class_name

    activities = {
        row["entity_id"]: row["current_activity"]
        for row in session.execute(
            text(
                """
                /* orrery:character_activities */
                SELECT entity_id, current_activity
                FROM characters
                WHERE entity_id IS NOT NULL
                  AND current_activity IS NOT NULL
                """
            )
        ).mappings()
    }

    relationship_types: dict[tuple[int, int], set[str]] = {}
    trust: dict[tuple[int, int], int] = {}
    for row in session.execute(
        text(
            """
            /* orrery:relationship_types */
            SELECT source_entity_id,
                   target_entity_id,
                   relationship_type,
                   valence_magnitude
            FROM entity_relationships_v
            WHERE relationship_scope = 'character'
              AND source_entity_id IS NOT NULL
              AND target_entity_id IS NOT NULL
              AND relationship_type IS NOT NULL
            """
        )
    ).mappings():
        key = (row["source_entity_id"], row["target_entity_id"])
        relationship_types.setdefault(key, set()).add(row["relationship_type"])
        if row.get("valence_magnitude") is not None:
            valence_magnitude = int(row["valence_magnitude"])
            if _should_replace_trust_magnitude(trust.get(key), valence_magnitude):
                trust[key] = valence_magnitude

    pair_tags: dict[tuple[int, int], set[str]] = {}
    for row in session.execute(
        text(
            """
            /* orrery:pair_tags */
            SELECT ept.subject_entity_id,
                   ept.object_entity_id,
                   pt.tag
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            JOIN entities subject_entity ON subject_entity.id = ept.subject_entity_id
            JOIN entities object_entity ON object_entity.id = ept.object_entity_id
            WHERE ept.cleared_at IS NULL
              AND NOT pt.deprecated
              AND subject_entity.is_active = true
              AND object_entity.is_active = true
            """
        )
    ).mappings():
        key = (row["subject_entity_id"], row["object_entity_id"])
        pair_tags.setdefault(key, set()).add(row["tag"])

    faction_memberships: dict[int, set[int]] = {}
    for row in session.execute(
        text(
            """
            /* orrery:faction_memberships */
            SELECT c.entity_id AS member_entity_id,
                   f.entity_id AS faction_entity_id
            FROM faction_character_relationships fcr
            JOIN characters c ON c.id = fcr.character_id
            JOIN factions f ON f.id = fcr.faction_id
            WHERE c.entity_id IS NOT NULL
              AND f.entity_id IS NOT NULL
            """
        )
    ).mappings():
        faction_memberships.setdefault(row["member_entity_id"], set()).add(
            row["faction_entity_id"]
        )

    recent_events = _load_recent_events(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
    )
    world_time = world_time_override or _load_world_time(
        session, anchor_chunk_id=anchor_chunk_id
    )
    time_of_day = _load_time_of_day(world_time)
    weather = _load_weather(session)
    need_debt_scores = _load_need_debt_scores(
        session,
        current_world_time=world_time,
        need_tuning=need_tuning,
        tags_by_entity={
            entity_id: frozenset(values) for entity_id, values in tags.items()
        },
        anchor_chunk_id=anchor_chunk_id,
    )
    travel_states = _load_travel_states(session)
    routine_anchors = _load_routine_anchors(session)
    win_history = _load_win_history(
        session,
        anchor_chunk_id=anchor_chunk_id,
        win_history_window=win_history_window,
    )

    return WorldState(
        tags={entity_id: frozenset(values) for entity_id, values in tags.items()},
        ephemeral_tags={
            entity_id: frozenset(values) for entity_id, values in ephemeral_tags.items()
        },
        locations=locations,
        activities=activities,
        trust=trust,
        # TODO: Hydrate orbit_distance when the resolver has an authoritative
        # source. Relationship trust is hydrated from entity_relationships_v.
        relationship_types={
            key: frozenset(values) for key, values in relationship_types.items()
        },
        pair_tags={key: frozenset(values) for key, values in pair_tags.items()},
        faction_memberships={
            entity_id: frozenset(values)
            for entity_id, values in faction_memberships.items()
        },
        location_class=location_class,
        location_classes={
            location_id: frozenset(values)
            for location_id, values in location_classes.items()
        },
        location_entity_ids=location_entity_ids,
        location_zones=location_zones,
        need_debt_scores=need_debt_scores,
        travel_states=travel_states,
        routine_anchors=routine_anchors,
        recent_events=recent_events,
        win_history=win_history,
        time_of_day=time_of_day,
        world_time=world_time,
        weather=weather,
        current_tick=anchor_chunk_id or 0,
    )


def _load_win_history(
    session: Any,
    *,
    anchor_chunk_id: Optional[int],
    win_history_window: int,
) -> dict[tuple[int, str], int]:
    """Committed wins per (actor, template) inside the habituation window."""

    if win_history_window <= 0 or anchor_chunk_id is None:
        return {}
    cutoff = anchor_chunk_id - win_history_window
    rows = session.execute(
        text(
            """
            /* orrery:win_history */
            SELECT actor_entity_id, template_id, COUNT(*) AS wins
            FROM orrery_resolutions
            WHERE tick_chunk_id > :cutoff
              AND tick_chunk_id <= :anchor
              AND actor_entity_id IS NOT NULL
            GROUP BY actor_entity_id, template_id
            """
        ),
        {"cutoff": cutoff, "anchor": anchor_chunk_id},
    ).mappings()
    return {
        (int(row["actor_entity_id"]), str(row["template_id"])): int(row["wins"])
        for row in rows
    }


def _load_routine_anchors(session: Any) -> dict[tuple[int, str], RoutineAnchor]:
    """Load explicit home/work anchors for routine package gates."""

    anchors: dict[tuple[int, str], RoutineAnchor] = {}
    for row in session.execute(
        text(
            """
            /* orrery:routine_anchors */
            SELECT cra.character_entity_id,
                   cra.anchor_type::text AS anchor_type,
                   cra.place_id,
                   cra.zone_id,
                   cra.mobility_policy::text AS mobility_policy,
                   cra.schedule
            FROM character_routine_anchors cra
            JOIN entities e
              ON e.id = cra.character_entity_id
             AND e.kind = 'character'
             AND e.is_active = true
            """
        )
    ).mappings():
        anchor_type = str(row["anchor_type"])
        anchors[(row["character_entity_id"], anchor_type)] = RoutineAnchor(
            anchor_type=anchor_type,
            place_id=row.get("place_id"),
            zone_id=row.get("zone_id"),
            mobility_policy=str(row["mobility_policy"]),
            schedule=row.get("schedule") or {},
        )
    return anchors


def _load_travel_states(session: Any) -> dict[int, TravelState]:
    """Load additive in-transit state without replacing current_location."""

    states: dict[int, TravelState] = {}
    for row in session.execute(
        text(
            """
            /* orrery:travel_states */
            SELECT cts.character_entity_id,
                   cts.status::text AS status,
                   cts.anchor_place_id,
                   cts.origin_place_id,
                   cts.destination_place_id,
                   cts.route_method::text AS route_method,
                   cts.travel_mode::text AS travel_mode,
                   cts.risk::text AS risk,
                   cts.progress_ratio,
                   cts.estimated_distance_m,
                   cts.estimated_duration_minutes,
                   cts.route_metadata ->> 'purpose' AS route_purpose
            FROM character_travel_states cts
            JOIN entities e
              ON e.id = cts.character_entity_id
             AND e.kind = 'character'
             AND e.is_active = true
            """
        )
    ).mappings():
        states[row["character_entity_id"]] = TravelState(
            status=row["status"],
            anchor_place_id=row["anchor_place_id"],
            origin_place_id=row["origin_place_id"],
            destination_place_id=row["destination_place_id"],
            route_method=row["route_method"],
            travel_mode=row["travel_mode"],
            risk=row["risk"],
            progress_ratio=float(row["progress_ratio"] or 0.0),
            estimated_distance_m=(
                float(row["estimated_distance_m"])
                if row["estimated_distance_m"] is not None
                else None
            ),
            estimated_duration_minutes=(
                float(row["estimated_duration_minutes"])
                if row["estimated_duration_minutes"] is not None
                else None
            ),
            route_purpose=row.get("route_purpose"),
        )
    return states


def compose_actor_bindings(
    session: Any,
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
) -> Tuple[Bindings, ...]:
    """Compose ACTOR-only bindings for recently relevant off-screen characters."""

    actor_ids: set[int] = set()
    present_actor_ids = _present_actor_ids_at_anchor(
        session, anchor_chunk_id=anchor_chunk_id
    )

    if anchor_chunk_id is not None:
        lower_bound = max(0, anchor_chunk_id - window_chunks + 1)
        for row in session.execute(
            text(
                """
                /* orrery:actor_bindings_chunk_refs */
                SELECT DISTINCT cer.entity_id
                FROM chunk_entity_references_v cer
                JOIN entities e ON e.id = cer.entity_id
                WHERE e.kind = 'character'
                  AND e.is_active = true
                  AND cer.reference_type IS DISTINCT FROM 'present'
                  AND cer.chunk_id BETWEEN :lower_bound AND :anchor_chunk_id
                """
            ),
            {"lower_bound": lower_bound, "anchor_chunk_id": anchor_chunk_id},
        ).mappings():
            actor_ids.add(row["entity_id"])

        for row in session.execute(
            text(
                """
                /* orrery:actor_bindings_events */
                SELECT DISTINCT candidate.entity_id
                FROM (
                    SELECT actor_entity_id AS entity_id
                    FROM world_events
                    WHERE tick_chunk_id BETWEEN :lower_bound AND :anchor_chunk_id
                      AND (world_layer IS NULL OR world_layer = 'primary')
                      AND superseded_by_event_id IS NULL
                    UNION
                    SELECT target_entity_id AS entity_id
                    FROM world_events
                    WHERE tick_chunk_id BETWEEN :lower_bound AND :anchor_chunk_id
                      AND (world_layer IS NULL OR world_layer = 'primary')
                      AND superseded_by_event_id IS NULL
                ) candidate
                JOIN entities e ON e.id = candidate.entity_id
                WHERE candidate.entity_id IS NOT NULL
                  AND e.kind = 'character'
                  AND e.is_active = true
                """
            ),
            {"lower_bound": lower_bound, "anchor_chunk_id": anchor_chunk_id},
        ).mappings():
            actor_ids.add(row["entity_id"])

    for row in session.execute(
        text(
            """
            /* orrery:actor_bindings_ephemeral */
            SELECT DISTINCT etc.entity_id
            FROM entity_tags_current etc
            JOIN entities e ON e.id = etc.entity_id
            WHERE etc.is_ephemeral = true
              AND e.kind = 'character'
              AND e.is_active = true
            """
        )
    ).mappings():
        actor_ids.add(row["entity_id"])

    for row in session.execute(
        text(
            """
            /* orrery:actor_bindings_inbound_ephemeral_pair_tags */
            SELECT DISTINCT ept.object_entity_id AS entity_id
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            JOIN entities subject_entity ON subject_entity.id = ept.subject_entity_id
            JOIN entities e ON e.id = ept.object_entity_id
            WHERE ept.cleared_at IS NULL
              AND pt.is_ephemeral = true
              AND pt.tag = 'hunting'
              AND NOT pt.deprecated
              AND subject_entity.is_active = true
              AND e.kind = 'character'
              AND e.is_active = true
            """
        )
    ).mappings():
        actor_ids.add(row["entity_id"])

    for row in session.execute(
        text(
            """
            /* orrery:actor_bindings_routine_anchors */
            SELECT DISTINCT cra.character_entity_id AS entity_id
            FROM character_routine_anchors cra
            JOIN entities e ON e.id = cra.character_entity_id
            WHERE e.kind = 'character'
              AND e.is_active = true
              AND cra.mobility_policy NOT IN ('none', 'nomadic')
            """
        )
    ).mappings():
        actor_ids.add(row["entity_id"])

    offscreen_actor_ids = actor_ids - present_actor_ids
    return tuple({Slot.ACTOR: actor_id} for actor_id in sorted(offscreen_actor_ids))


def _present_actor_ids_at_anchor(
    session: Any, *, anchor_chunk_id: Optional[int]
) -> set[int]:
    """Return character entities explicitly present in the current scene anchor."""

    if anchor_chunk_id is None:
        return set()

    return {
        row["entity_id"]
        for row in session.execute(
            text(
                """
                /* orrery:present_actor_ids_at_anchor */
                SELECT DISTINCT c.entity_id
                FROM chunk_character_references ccr
                JOIN characters c ON c.id = ccr.character_id
                JOIN entities e ON e.id = c.entity_id
                WHERE ccr.chunk_id = :anchor_chunk_id
                  AND ccr.reference = 'present'
                  AND e.kind = 'character'
                  AND e.is_active = true
                """
            ),
            {"anchor_chunk_id": anchor_chunk_id},
        ).mappings()
    }


def compose_actor_target_bindings(
    session: Any,
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
    actor_ids: Optional[Iterable[int]] = None,
    target_presence: str = "offscreen",
) -> Tuple[Bindings, ...]:
    """Compose ACTOR+TARGET bindings from actors' relational neighborhoods.

    Yields {Slot.ACTOR: a, Slot.TARGET: t} for each character-to-character
    relationship row where the actor side is in the recently-relevant set.
    Each stored relationship row produces up to two bindings (forward and
    reverse) so templates with symmetric semantics see both orderings; gate
    predicates with asymmetric semantics (handler/asset) filter via
    role-explicit OR clauses.

    When actor_ids is provided (typical: resolve_dry_run threads through
    the actor set it already computed), this skips the redundant
    compose_actor_bindings call. That avoids two costs: the duplicate DB
    queries on every tick, and the READ COMMITTED inconsistency window
    where the two binding passes could see different actor sets if rows
    change between reads. Direct callers (e.g., focused unit tests) may
    omit actor_ids and accept the implicit recomputation.

    target_presence controls whether TARGET may be a character explicitly
    present at the anchor chunk. The default preserves Orrery's hard
    off-screen boundary; "present" is reserved for Storyteller-mediated
    scene-pressure proposals and still never allows a present ACTOR.
    """

    if target_presence not in {"offscreen", "present"}:
        raise ValueError("target_presence must be 'offscreen' or 'present'")

    if actor_ids is None:
        actor_only = compose_actor_bindings(
            session,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
        )
        actor_id_set = {bindings[Slot.ACTOR] for bindings in actor_only}
    else:
        actor_id_set = set(actor_ids)
    present_actor_ids = _present_actor_ids_at_anchor(
        session, anchor_chunk_id=anchor_chunk_id
    )
    actor_id_set -= present_actor_ids
    if not actor_id_set:
        return ()

    pairs: set[Tuple[int, int]] = set()
    for row in session.execute(
        text(
            """
            /* orrery:actor_target_bindings_character_relationships */
            SELECT er.source_entity_id, er.target_entity_id
            FROM entity_relationships_v er
            JOIN entities es ON es.id = er.source_entity_id
            JOIN entities et ON et.id = er.target_entity_id
            WHERE er.relationship_scope = 'character'
              AND er.source_entity_id IS NOT NULL
              AND er.target_entity_id IS NOT NULL
              AND es.kind = 'character'
              AND et.kind = 'character'
              AND es.is_active = true
              AND et.is_active = true
            """
        )
    ).mappings():
        source = row["source_entity_id"]
        target = row["target_entity_id"]
        source_present = source in present_actor_ids
        target_present = target in present_actor_ids
        if (
            source in actor_id_set
            and not source_present
            and (
                (target_presence == "offscreen" and not target_present)
                or (target_presence == "present" and target_present)
            )
        ):
            pairs.add((source, target))
        if (
            target in actor_id_set
            and not target_present
            and (
                (target_presence == "offscreen" and not source_present)
                or (target_presence == "present" and source_present)
            )
        ):
            pairs.add((target, source))

    return tuple(
        {Slot.ACTOR: actor_id, Slot.TARGET: target_id}
        for actor_id, target_id in sorted(pairs)
    )


_ACTOR_ONLY_SLOTS: Tuple[Slot, ...] = (Slot.ACTOR,)
_ACTOR_TARGET_SLOTS: Tuple[Slot, ...] = (Slot.ACTOR, Slot.TARGET)


@dataclass(frozen=True)
class FanoutPolicy:
    """Per-actor cap on two-party drafts ([orrery.fanout]).

    One actor with several eligible targets can otherwise flood the tick
    with near-duplicate pair drafts and crowd everything else out of the
    storyteller prompt's first-N slice. Kept drafts prefer template
    diversity (first draft of each template before any second of one),
    then magnitude, then binding hash — a pure function of the draft set,
    so replays trim identically. Crisis-band drafts are exempt: dropping
    a protection or evasion beat is behavior loss, not noise reduction.
    """

    max_pair_drafts_per_actor: int = 0
    exempt_bands: frozenset[str] = frozenset({"crisis_constraint"})


def _coerce_fanout(raw: Any) -> FanoutPolicy:
    if raw is None:
        return FanoutPolicy()
    if hasattr(raw, "max_pair_drafts_per_actor"):
        return FanoutPolicy(
            max_pair_drafts_per_actor=int(raw.max_pair_drafts_per_actor),
            exempt_bands=frozenset(raw.exempt_bands),
        )
    if isinstance(raw, Mapping):
        return FanoutPolicy(
            max_pair_drafts_per_actor=int(raw.get("max_pair_drafts_per_actor", 0)),
            exempt_bands=frozenset(raw.get("exempt_bands", ("crisis_constraint",))),
        )
    raise ValueError(f"Unsupported fanout settings: {type(raw)!r}")


def _apply_pair_fanout_quota(
    drafts: list[OrreryResolutionDraft],
    templates_list: list[Template],
    *,
    max_pair_drafts_per_actor: int,
    exempt_bands: frozenset[str],
) -> list[OrreryResolutionDraft]:
    if max_pair_drafts_per_actor <= 0:
        return drafts
    band_by_template = {t.id: t.drive_band.value for t in templates_list}

    def is_pair(draft: OrreryResolutionDraft) -> bool:
        return "target" in draft.bindings

    kept: list[OrreryResolutionDraft] = []
    per_actor: dict[Any, list[OrreryResolutionDraft]] = {}
    for draft in drafts:
        if (
            not is_pair(draft)
            or band_by_template.get(draft.template_id) in exempt_bands
        ):
            kept.append(draft)
            continue
        per_actor.setdefault(draft.bindings.get("actor"), []).append(draft)

    for actor, pair_drafts in per_actor.items():
        seen_templates: set[str] = set()
        first_of_template: list[OrreryResolutionDraft] = []
        repeats: list[OrreryResolutionDraft] = []
        for draft in sorted(pair_drafts, key=lambda d: (-d.magnitude, d.binding_hash)):
            if draft.template_id in seen_templates:
                repeats.append(draft)
            else:
                seen_templates.add(draft.template_id)
                first_of_template.append(draft)
        kept.extend((first_of_template + repeats)[:max_pair_drafts_per_actor])

    # Preserve the original draft ordering for everything that survived.
    surviving = {id(d) for d in kept}
    return [draft for draft in drafts if id(draft) in surviving]


def resolve_dry_run(
    session: Any,
    templates: Iterable[Template],
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
    sunhelm_settings: Optional[Any] = None,
    world_time_override: Optional[datetime] = None,
    selection_settings: Optional[Any] = None,
    habituation_settings: Optional[Any] = None,
    package_selection_settings: Optional[Any] = None,
    fanout_settings: Optional[Any] = None,
) -> OrreryTickProposal:
    """Hydrate, bind, and evaluate Orrery packages without database writes."""

    need_tuning = coerce_need_tuning(sunhelm_settings)
    selection = coerce_branch_selection(selection_settings)
    habituation = coerce_habituation(habituation_settings)
    package_selection: Optional[PackageSelection] = coerce_package_selection(
        package_selection_settings
    )
    fanout = _coerce_fanout(fanout_settings)
    state = hydrate_world_state(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
        need_tuning=need_tuning,
        world_time_override=world_time_override,
        win_history_window=habituation.window_ticks if habituation.enabled else 0,
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
            "Orrery resolver does not yet compose bindings for required_slots="
            + ", ".join(
                f"{t.id}:{tuple(s.value for s in t.required_slots)}"
                for t in unsupported
            )
        )

    drafts: list[OrreryResolutionDraft] = []
    scene_pressure_results: list[Resolution] = []

    actor_bindings = compose_actor_bindings(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
    )
    for bindings in actor_bindings:
        resolution = evaluate_stack(
            actor_only_templates,
            state,
            bindings,
            selection,
            habituation,
            package_selection,
        )
        if resolution is not None and resolution.passes:
            drafts.append(_draft_from_resolution(resolution))

    actor_target_bindings: Tuple[Bindings, ...] = ()
    present_target_bindings: Tuple[Bindings, ...] = ()
    if actor_target_templates:
        actor_target_bindings = compose_actor_target_bindings(
            session,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            actor_ids={bindings[Slot.ACTOR] for bindings in actor_bindings},
            target_presence="offscreen",
        )
        for bindings in actor_target_bindings:
            resolution = evaluate_stack(
                actor_target_templates,
                state,
                bindings,
                selection,
                habituation,
                package_selection,
            )
            if resolution is not None and resolution.passes:
                drafts.append(_draft_from_resolution(resolution))

        pressure_templates = [
            template
            for template in actor_target_templates
            if template.present_target_policy
            is PresentTargetPolicy.STORYTELLER_PRESSURE
        ]
        if pressure_templates:
            present_target_bindings = compose_actor_target_bindings(
                session,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=window_chunks,
                actor_ids={bindings[Slot.ACTOR] for bindings in actor_bindings},
                target_presence="present",
            )
            for bindings in present_target_bindings:
                resolution = evaluate_stack(
                    pressure_templates,
                    state,
                    bindings,
                    selection,
                    habituation,
                    package_selection,
                )
                if resolution is not None and resolution.passes:
                    scene_pressure_results.append(resolution)

    drafts = _apply_pair_fanout_quota(
        drafts,
        templates_list,
        max_pair_drafts_per_actor=fanout.max_pair_drafts_per_actor,
        exempt_bands=fanout.exempt_bands,
    )

    # Resolve binding entity names so Skald's adjudication payload says WHO
    # each off-screen proposal is about; bare entity ids invite misattribution
    # to on-screen characters (M9 gate finding).
    draft_entity_ids: set[int] = set()
    for draft in drafts:
        for value in draft.bindings.values():
            if isinstance(value, int):
                draft_entity_ids.add(value)
    draft_entity_names = _load_entity_names(session, draft_entity_ids)
    drafts = [
        replace(
            draft,
            binding_names={
                slot: _entity_label(value, draft_entity_names)
                for slot, value in draft.bindings.items()
            },
            narrative_stub=_render_bound_text(
                draft.narrative_stub,
                draft.bindings,
                draft_entity_names,
                template_id=draft.template_id,
            ),
        )
        for draft in drafts
    ]

    present_need_pressure_specs = _present_need_pressure_specs(
        state,
        present_actor_ids=_present_actor_ids_at_anchor(
            session, anchor_chunk_id=anchor_chunk_id
        ),
        need_tuning=need_tuning,
    )
    pressure_entity_ids = _entity_ids_from_resolutions(scene_pressure_results) | {
        spec["actor_entity_id"] for spec in present_need_pressure_specs
    }
    pressure_entity_names = _load_entity_names(session, pressure_entity_ids)
    scene_pressures = tuple(
        _scene_pressure_from_resolution(resolution, pressure_entity_names)
        for resolution in scene_pressure_results
    ) + tuple(
        _scene_pressure_from_need_spec(
            spec,
            pressure_entity_names,
            need_tuning=need_tuning,
        )
        for spec in present_need_pressure_specs
    )

    unique_actors = (
        {bindings[Slot.ACTOR] for bindings in actor_bindings}
        | {bindings[Slot.ACTOR] for bindings in actor_target_bindings}
        | {bindings[Slot.ACTOR] for bindings in present_target_bindings}
    )

    return OrreryTickProposal(
        anchor_chunk_id=anchor_chunk_id,
        actor_count=len(unique_actors),
        resolutions=tuple(drafts),
        scene_pressures=scene_pressures,
        joint_beats=detect_joint_beats(drafts, draft_entity_names),
    )


def _load_recent_events(
    session: Any,
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
) -> Tuple[EventRecord, ...]:
    if anchor_chunk_id is None:
        return ()

    lower_bound = max(0, anchor_chunk_id - window_chunks + 1)
    events = []
    for row in session.execute(
        text(
            """
            /* orrery:recent_events */
            SELECT event_type,
                   tick_chunk_id,
                   actor_entity_id,
                   target_entity_id,
                   location_id,
                   changed_fields,
                   COALESCE(world_layer::text, 'primary') AS world_layer,
                   payload
            FROM world_events
            WHERE tick_chunk_id BETWEEN :lower_bound AND :anchor_chunk_id
              AND (world_layer IS NULL OR world_layer = 'primary')
              AND superseded_by_event_id IS NULL
            ORDER BY tick_chunk_id DESC, id DESC
            """
        ),
        {"lower_bound": lower_bound, "anchor_chunk_id": anchor_chunk_id},
    ).mappings():
        events.append(
            EventRecord(
                event_type=row["event_type"],
                tick=row["tick_chunk_id"],
                actor_entity_id=row["actor_entity_id"],
                target_entity_id=row["target_entity_id"],
                location_id=row["location_id"],
                changed_fields=tuple(row["changed_fields"] or ()),
                world_layer=row["world_layer"],
                payload=row["payload"] or {},
            )
        )
    return tuple(events)


def _load_time_of_day(world_time: Optional[datetime]) -> str:
    if world_time is None:
        return "midday"

    hour = world_time.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 16:
        return "afternoon"
    if 16 <= hour < 21:
        return "evening"
    return "night"


def _load_world_time(
    session: Any, *, anchor_chunk_id: Optional[int]
) -> Optional[datetime]:
    if anchor_chunk_id is None:
        return None
    row = (
        session.execute(
            text(
                """
                /* orrery:anchor_world_time */
                SELECT world_time
                FROM chunk_metadata
                WHERE chunk_id = :anchor_chunk_id
                """
            ),
            {"anchor_chunk_id": anchor_chunk_id},
        )
        .mappings()
        .first()
    )
    return row["world_time"] if row else None


def _load_need_debt_scores(
    session: Any,
    *,
    current_world_time: Optional[datetime],
    need_tuning: NeedTuning,
    tags_by_entity: Mapping[int, frozenset[str]],
    anchor_chunk_id: Optional[int] = None,
) -> dict[tuple[int, str], float]:
    """Load effective need debt scores without mutating canonical state."""

    scores: dict[tuple[int, str], float] = {}
    for row in session.execute(
        text(
            """
            /* orrery:need_debt_scores */
            SELECT character_entity_id,
                   need_type::text AS need_type,
                   debt_score,
                   last_evaluated_at,
                   last_evaluated_chunk_id
            FROM character_need_states cns
            JOIN entities e
              ON e.id = cns.character_entity_id
             AND e.kind = 'character'
             AND e.is_active = true
            """
        )
    ).mappings():
        need_type = str(row["need_type"])
        if not need_applies_to_tags(
            need_type,
            tags_by_entity.get(row["character_entity_id"], frozenset()),
        ):
            continue
        scores[(row["character_entity_id"], need_type)] = effective_debt_score(
            need_type,
            float(row["debt_score"] or 0.0),
            last_evaluated_at=row["last_evaluated_at"],
            current_world_time=current_world_time,
            tuning=need_tuning,
            last_evaluated_chunk_id=row.get("last_evaluated_chunk_id"),
            current_chunk_id=anchor_chunk_id,
        )
    return scores


def _load_weather(session: Any) -> str:
    # TODO: Replace seed-weather classification with GAIA scene weather once
    # world-state weather has an authoritative runtime table.
    row = (
        session.execute(
            text(
                """
                /* orrery:seed_weather */
                SELECT setting #>> '{story_seed,weather}' AS weather
                FROM global_variables
                WHERE id = true
                """
            )
        )
        .mappings()
        .first()
    )
    raw_weather = (row["weather"] if row else None) or ""
    return _classify_weather(raw_weather)


def _classify_weather(raw_weather: str) -> str:
    weather = raw_weather.lower()
    if any(token in weather for token in ("rain", "sleet", "storm", "thunder")):
        return "rain"
    if "snow" in weather:
        return "snow"
    if "fog" in weather:
        return "fog"
    if any(token in weather for token in ("sun", "clear")):
        return "clear"
    return "clear"


def _draft_from_resolution(resolution: Resolution) -> OrreryResolutionDraft:
    if resolution.branch_label is None or resolution.narrative_stub is None:
        raise RuntimeError(
            f"Orrery resolution {resolution.template_id!r} passed gate but lacks "
            "branch data"
        )
    return OrreryResolutionDraft(
        template_id=resolution.template_id,
        priority=resolution.priority,
        binding_hash=resolution.binding_hash,
        bindings={
            slot.value if isinstance(slot, Slot) else str(slot): value
            for slot, value in resolution.bindings.items()
        },
        branch_label=resolution.branch_label,
        narrative_stub=resolution.narrative_stub,
        state_delta=resolution.state_delta,
        event_type=resolution.event_type,
        signal_event_type=resolution.signal_event_type,
        changed_fields=resolution.changed_fields,
        magnitude=resolution.magnitude,
    )


def _scene_pressure_from_resolution(
    resolution: Resolution,
    entity_names: Mapping[int, str],
) -> OrreryScenePressureDraft:
    if resolution.branch_label is None or resolution.scene_pressure_stub is None:
        raise RuntimeError(
            f"Orrery pressure {resolution.template_id!r} passed gate but lacks "
            "scene_pressure_stub"
        )
    bindings = {
        slot.value if isinstance(slot, Slot) else str(slot): value
        for slot, value in resolution.bindings.items()
    }
    return OrreryScenePressureDraft(
        template_id=resolution.template_id,
        priority=resolution.priority,
        binding_hash=resolution.binding_hash,
        bindings=bindings,
        branch_label=resolution.branch_label,
        pressure_stub=resolution.scene_pressure_stub,
        prompt_text=_render_bound_text(
            resolution.scene_pressure_stub,
            bindings,
            entity_names,
            template_id=resolution.template_id,
        ),
        magnitude=resolution.magnitude,
    )


def _present_need_pressure_specs(
    state: WorldState,
    *,
    present_actor_ids: set[int],
    need_tuning: NeedTuning,
) -> tuple[dict[str, Any], ...]:
    """Build prompt-only pressure specs from present-character need debt."""

    specs: list[dict[str, Any]] = []
    for actor_id in sorted(present_actor_ids):
        for need_type, prefix in NEED_SEVERITY_PREFIX.items():
            if _present_need_pressure_suppressed(state, actor_id, need_type):
                continue
            debt_score = state.need_debt_scores.get((actor_id, need_type), 0.0)
            severity = severity_for_debt(
                need_type,
                debt_score,
                tuning=need_tuning,
            )
            if severity is None:
                continue
            level, severity_name = severity
            if level < need_tuning.pressure.min_severity_level:
                continue
            specs.append(
                {
                    "actor_entity_id": actor_id,
                    "need_type": need_type,
                    "severity_prefix": prefix,
                    "severity_level": level,
                    "severity_name": severity_name,
                    "debt_score": debt_score,
                }
            )
    return tuple(specs)


def _present_need_pressure_suppressed(
    state: WorldState,
    actor_id: int,
    need_type: str,
) -> bool:
    """Return whether a present-character need should stay out of prompt pressure."""

    if need_type != "intimacy":
        return False
    actor_tags = state.tags.get(actor_id, frozenset()) | state.ephemeral_tags.get(
        actor_id, frozenset()
    )
    return bool(INTIMACY_SUPPRESSOR_TAGS & actor_tags)


def _scene_pressure_from_need_spec(
    spec: Mapping[str, Any],
    entity_names: Mapping[int, str],
    *,
    need_tuning: NeedTuning,
) -> OrreryScenePressureDraft:
    """Convert present-character need pressure into Storyteller prompt data."""

    actor_id = int(spec["actor_entity_id"])
    need_type = str(spec["need_type"])
    severity_name = str(spec["severity_name"])
    debt_score = float(spec["debt_score"])
    bindings = {"actor": actor_id, "resource": need_type}
    pressure_stub = _need_pressure_stub(
        need_type, severity_name=severity_name, debt_score=debt_score
    )
    prompt_text = _render_bound_text(
        pressure_stub,
        bindings,
        entity_names,
        template_id=f"{need_type}_need_pressure",
    )
    return OrreryScenePressureDraft(
        template_id=f"{need_type}_need_pressure",
        priority=need_tuning.priorities[need_type],
        binding_hash=binding_hash({Slot.ACTOR: actor_id, Slot.RESOURCE: need_type}),
        bindings=bindings,
        branch_label=f"Present-character {need_type} pressure",
        pressure_stub=pressure_stub,
        prompt_text=prompt_text,
        magnitude=need_tuning.pressure.magnitude_for_level(int(spec["severity_level"])),
    )


def _need_pressure_stub(
    need_type: str, *, severity_name: str, debt_score: float
) -> str:
    label = f"{severity_name} {need_type} debt"
    if need_type == "sleep":
        return (
            "{actor} is carrying "
            f"{label} ({debt_score:.1f}). You may render fatigue, dulled "
            "judgment, irritability, or the pull toward rest, but Orrery "
            "does not decide what {actor} does in scene."
        )
    if need_type == "hunger":
        return (
            "{actor} is carrying "
            f"{label} ({debt_score:.1f}). You may render distraction, "
            "irritability, or interest in food, but Orrery does not decide "
            "what {actor} does in scene."
        )
    if need_type == "thirst":
        return (
            "{actor} is carrying "
            f"{label} ({debt_score:.1f}). You may render thirst, discomfort, "
            "or urgency around water, but Orrery does not decide what {actor} "
            "does in scene."
        )
    if need_type == "socialize":
        return (
            "{actor} is carrying "
            f"{label} ({debt_score:.1f}). You may render loneliness, social "
            "friction, relief at being seen, or the pull toward company, but "
            "Orrery does not decide what {actor} does in scene."
        )
    if need_type == "intimacy":
        return (
            "{actor} is carrying "
            f"{label} ({debt_score:.1f}). You may render wanting, suppression, "
            "privacy-seeking, or deferral with appropriate restraint, but Orrery "
            "does not decide what {actor} does in scene or who they choose."
        )
    raise ValueError(f"Unhandled Orrery need pressure type: {need_type!r}")


def _render_bound_text(
    text_template: str,
    bindings: Mapping[str, Any],
    entity_names: Mapping[int, str],
    *,
    template_id: str,
) -> str:
    values = {
        slot: _entity_label(value, entity_names) for slot, value in bindings.items()
    }
    try:
        rendered = text_template.format(**values)
    except KeyError as exc:
        missing_key = exc.args[0]
        raise ValueError(
            "Orrery template "
            f"{template_id!r} scene_pressure_stub references missing binding "
            f"{missing_key!r}"
        ) from exc
    return " ".join(rendered.split())


def _entity_label(value: Any, entity_names: Mapping[int, str]) -> str:
    if isinstance(value, list):
        return ", ".join(_entity_label(item, entity_names) for item in value)
    if value is None:
        return "unknown"
    try:
        entity_id = int(value)
    except (TypeError, ValueError):
        return str(value)
    return entity_names.get(entity_id, f"entity {entity_id}")


def _entity_ids_from_resolutions(resolutions: Iterable[Resolution]) -> set[int]:
    entity_ids: set[int] = set()
    for resolution in resolutions:
        for value in resolution.bindings.values():
            if isinstance(value, IterableABC) and not isinstance(value, (str, bytes)):
                for item in value:
                    if isinstance(item, int):
                        entity_ids.add(item)
            elif isinstance(value, int):
                entity_ids.add(value)
    return entity_ids


def _load_entity_names(session: Any, entity_ids: set[int]) -> dict[int, str]:
    if not entity_ids:
        return {}
    return {
        row["id"]: row["name"]
        for row in session.execute(
            text(
                """
                /* orrery:entity_names */
                SELECT id, name
                FROM entity_names_v
                WHERE id = ANY(:entity_ids)
                """
            ),
            {"entity_ids": sorted(entity_ids)},
        ).mappings()
    }
