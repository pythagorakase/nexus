"""Dry-run resolver integration for Orrery behavior packages."""

from __future__ import annotations

from collections.abc import Iterable as IterableABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Tuple

from sqlalchemy import text

from nexus.agents.orrery.substrate import (
    Bindings,
    EventRecord,
    INTIMACY_SUPPRESSOR_TAGS,
    PresentTargetPolicy,
    Resolution,
    Slot,
    Template,
    WorldState,
    binding_hash,
    evaluate_stack,
)
from nexus.agents.orrery.needs import (
    NEED_SEVERITY_PREFIX,
    NeedTuning,
    coerce_need_tuning,
    effective_debt_score,
    severity_for_debt,
)


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
    changed_fields: Tuple[str, ...] = ()
    magnitude: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this draft."""

        return {
            "template_id": self.template_id,
            "priority": self.priority,
            "binding_hash": self.binding_hash,
            "bindings": dict(self.bindings),
            "branch_label": self.branch_label,
            "narrative_stub": self.narrative_stub,
            "state_delta": dict(self.state_delta),
            "event_type": self.event_type,
            "changed_fields": list(self.changed_fields),
            "magnitude": self.magnitude,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OrreryResolutionDraft":
        """Hydrate a draft from incubator JSONB data."""

        return cls(
            template_id=str(data["template_id"]),
            priority=int(data["priority"]),
            binding_hash=str(data["binding_hash"]),
            bindings=dict(data.get("bindings") or {}),
            branch_label=str(data["branch_label"]),
            narrative_stub=str(data["narrative_stub"]),
            state_delta=dict(data.get("state_delta") or {}),
            event_type=data.get("event_type"),
            changed_fields=tuple(data.get("changed_fields") or ()),
            magnitude=float(data.get("magnitude") or 0.0),
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
) -> WorldState:
    """Hydrate the read-side Orrery state snapshot from database tables."""

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
    for row in session.execute(
        text(
            """
            /* orrery:location_classes */
            SELECT p.id, p.type::text AS location_class, true AS is_primary
            FROM places p
            WHERE p.type IS NOT NULL
            UNION ALL
            SELECT p.id, etc.tag AS location_class, false AS is_primary
            FROM places p
            JOIN entity_tags_current etc ON etc.entity_id = p.entity_id
            WHERE etc.entity_kind = 'place'
              AND etc.category = 'place_affordance'
            """
        )
    ).mappings():
        place_id = row["id"]
        class_name = row["location_class"]
        if class_name is None:
            continue
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
    world_time = _load_world_time(session, anchor_chunk_id=anchor_chunk_id)
    time_of_day = _load_time_of_day(world_time)
    weather = _load_weather(session)
    need_debt_scores = _load_need_debt_scores(
        session,
        current_world_time=world_time,
        need_tuning=need_tuning,
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
        faction_memberships={
            entity_id: frozenset(values)
            for entity_id, values in faction_memberships.items()
        },
        location_class=location_class,
        location_classes={
            location_id: frozenset(values)
            for location_id, values in location_classes.items()
        },
        need_debt_scores=need_debt_scores,
        recent_events=recent_events,
        time_of_day=time_of_day,
        weather=weather,
        current_tick=anchor_chunk_id or 0,
    )


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


def resolve_dry_run(
    session: Any,
    templates: Iterable[Template],
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
    sunhelm_settings: Optional[Any] = None,
) -> OrreryTickProposal:
    """Hydrate, bind, and evaluate Orrery packages without database writes."""

    need_tuning = coerce_need_tuning(sunhelm_settings)
    state = hydrate_world_state(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
        need_tuning=need_tuning,
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
        resolution = evaluate_stack(actor_only_templates, state, bindings)
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
            resolution = evaluate_stack(actor_target_templates, state, bindings)
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
                resolution = evaluate_stack(pressure_templates, state, bindings)
                if resolution is not None and resolution.passes:
                    scene_pressure_results.append(resolution)

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
                   last_evaluated_at
            FROM character_need_states cns
            JOIN entities e
              ON e.id = cns.character_entity_id
             AND e.kind = 'character'
             AND e.is_active = true
            """
        )
    ).mappings():
        need_type = str(row["need_type"])
        scores[(row["character_entity_id"], need_type)] = effective_debt_score(
            need_type,
            float(row["debt_score"] or 0.0),
            last_evaluated_at=row["last_evaluated_at"],
            current_world_time=current_world_time,
            tuning=need_tuning,
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
            f"Orrery resolution {resolution.template_id!r} passed gate but lacks branch data"
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
    return (
        "{actor} is carrying "
        f"{label} ({debt_score:.1f}). You may render wanting, suppression, "
        "privacy-seeking, or deferral with appropriate restraint, but Orrery "
        "does not decide what {actor} does in scene or who they choose."
    )


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
