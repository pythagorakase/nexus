"""Dry-run resolver integration for Orrery behavior packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Tuple

from sqlalchemy import text

from nexus.agents.orrery.substrate import (
    Bindings,
    EventRecord,
    Resolution,
    Slot,
    Template,
    WorldState,
    evaluate_stack,
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


@dataclass(frozen=True, slots=True)
class OrreryTickProposal:
    """No-write Orrery proposal produced before accepted chunk commit."""

    anchor_chunk_id: Optional[int]
    actor_count: int
    resolutions: Tuple[OrreryResolutionDraft, ...]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def resolution_count(self) -> int:
        """Return the number of draft resolutions in this proposal."""

        return len(self.resolutions)


def hydrate_world_state(
    session: Any,
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
) -> WorldState:
    """Hydrate the read-side Orrery state snapshot from database tables."""

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

    location_class = {
        row["id"]: row["location_class"]
        for row in session.execute(
            text(
                """
                /* orrery:location_classes */
                SELECT id, type::text AS location_class
                FROM places
                WHERE type IS NOT NULL
                """
            )
        ).mappings()
    }

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
    for row in session.execute(
        text(
            """
            /* orrery:relationship_types */
            SELECT c1.entity_id AS source_entity_id,
                   c2.entity_id AS target_entity_id,
                   cr.relationship_type::text AS relationship_type
            FROM character_relationships cr
            JOIN characters c1 ON c1.id = cr.character1_id
            JOIN characters c2 ON c2.id = cr.character2_id
            WHERE c1.entity_id IS NOT NULL
              AND c2.entity_id IS NOT NULL
              AND cr.relationship_type IS NOT NULL
            """
        )
    ).mappings():
        relationship_types.setdefault(
            (row["source_entity_id"], row["target_entity_id"]), set()
        ).add(row["relationship_type"])

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
    time_of_day = _load_time_of_day(session, anchor_chunk_id=anchor_chunk_id)
    weather = _load_weather(session)

    return WorldState(
        tags={entity_id: frozenset(values) for entity_id, values in tags.items()},
        ephemeral_tags={
            entity_id: frozenset(values) for entity_id, values in ephemeral_tags.items()
        },
        locations=locations,
        activities=activities,
        # TODO: Hydrate trust and orbit_distance when the resolver has an
        # authoritative source. Current built-in packages do not use them.
        relationship_types={
            key: frozenset(values) for key, values in relationship_types.items()
        },
        faction_memberships={
            entity_id: frozenset(values)
            for entity_id, values in faction_memberships.items()
        },
        location_class=location_class,
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
    """Compose ACTOR-only bindings for recently relevant character entities."""

    actor_ids: set[int] = set()

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

    return tuple({Slot.ACTOR: actor_id} for actor_id in sorted(actor_ids))


def resolve_dry_run(
    session: Any,
    templates: Iterable[Template],
    *,
    anchor_chunk_id: Optional[int],
    window_chunks: int,
) -> OrreryTickProposal:
    """Hydrate, bind, and evaluate Orrery packages without database writes."""

    state = hydrate_world_state(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
    )
    actor_bindings = compose_actor_bindings(
        session,
        anchor_chunk_id=anchor_chunk_id,
        window_chunks=window_chunks,
    )
    drafts = []
    for bindings in actor_bindings:
        resolution = evaluate_stack(templates, state, bindings)
        if resolution is not None and resolution.passes:
            drafts.append(_draft_from_resolution(resolution))

    return OrreryTickProposal(
        anchor_chunk_id=anchor_chunk_id,
        actor_count=len(actor_bindings),
        resolutions=tuple(drafts),
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


def _load_time_of_day(session: Any, *, anchor_chunk_id: Optional[int]) -> str:
    if anchor_chunk_id is None:
        return "midday"

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
    world_time = row["world_time"] if row else None
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
