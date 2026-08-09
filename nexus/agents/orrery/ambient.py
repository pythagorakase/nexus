"""Typed, deterministic ambient-scene seeds for the current Storyteller turn."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from nexus.agents.orrery.reciprocal import OrreryJointBeat
from nexus.agents.orrery.substrate import WorldState, seeded_stochastic_rng
from nexus.config.settings_models import OrreryAmbientSettings


AMBIENT_EXPOSURE_TEMPLATE_ID = "ambient_scene_seed"


class AmbientParticipant(BaseModel):
    """One NPC admitted to an ambient-scene seed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: int = Field(ge=1)
    name: str = Field(min_length=1)
    speaking_eligible: bool


class AmbientEntitlement(BaseModel):
    """Exact actor-owned records one participant may draw on when speaking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    participant_entity_id: int = Field(ge=1)
    claim_ids: Tuple[int, ...] = ()
    character_experience_ids: Tuple[int, ...] = ()

    @model_validator(mode="after")
    def _validate_owned_ids(self) -> "AmbientEntitlement":
        """Entitlement identifiers must be positive, sorted, and unique."""

        for label, values in (
            ("claim_ids", self.claim_ids),
            ("character_experience_ids", self.character_experience_ids),
        ):
            if any(value <= 0 for value in values):
                raise ValueError(f"{label} must contain only positive identifiers")
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{label} must be sorted and unique")
        return self


class AmbientLocationConstraint(BaseModel):
    """Where the current-turn ambient exchange is allowed to occur."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["current_scene"] = "current_scene"
    place_id: Optional[int] = Field(default=None, ge=1)


class AmbientSceneSeed(BaseModel):
    """Advisory, state-free direction for one bounded ambient exchange."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed_id: str = Field(min_length=1)
    participants: Tuple[AmbientParticipant, ...]
    topic: str = Field(min_length=1)
    tension: str = Field(min_length=1)
    why_now: str = Field(min_length=1)
    entitlements: Tuple[AmbientEntitlement, ...]
    location_constraint: AmbientLocationConstraint
    dedup_key: str = Field(min_length=1)
    cooldown_turns: int = Field(ge=0)
    expiry_turns: int = Field(ge=1)
    source_turn: int = Field(ge=1)
    line_budget: int = Field(ge=1)
    turn_budget: int = Field(ge=1)
    silence_ok: Literal[True] = True

    @model_validator(mode="after")
    def _validate_participant_boundary(self) -> "AmbientSceneSeed":
        """Require one entitlement record for each distinct participant."""

        participant_ids = tuple(item.entity_id for item in self.participants)
        if len(participant_ids) < 2:
            raise ValueError("ambient scene seeds require at least two participants")
        if len(set(participant_ids)) != len(participant_ids):
            raise ValueError("ambient scene participants must be unique")
        entitlement_ids = tuple(
            item.participant_entity_id for item in self.entitlements
        )
        if entitlement_ids != participant_ids:
            raise ValueError(
                "ambient entitlements must match participants in participant order"
            )
        return self


@dataclass(frozen=True, slots=True)
class _AmbientCandidate:
    """One deterministic signal-derived candidate before entitlement hydration."""

    participant_ids: Tuple[int, int]
    topic: str
    tension: str
    why_now: str
    source_turn: int
    source_rank: int


def shared_ambient_pacing_allows(anchor_chunk_id: int, density: float) -> bool:
    """Return the replay-safe pacing decision shared by Bleed and ambient seeds."""

    if not 0.0 <= density <= 1.0:
        raise ValueError(f"Bleed density must be between 0.0 and 1.0, got {density}")
    if density == 0.0:
        return False
    if density == 1.0:
        return True
    rng = seeded_stochastic_rng("bleed", anchor_chunk_id, "density")
    return rng.random() < density


def build_ambient_scene_seeds(
    session: Any,
    *,
    anchor_chunk_id: Optional[int],
    state: WorldState,
    present_actor_ids: Iterable[int],
    joint_beats: Iterable[OrreryJointBeat],
    entity_names: Mapping[int, str],
    settings: Any,
    pacing_allowed: bool,
) -> Tuple[AmbientSceneSeed, ...]:
    """Build bounded current-turn seeds using read-only Orrery state and ledgers."""

    ambient_settings = OrreryAmbientSettings.model_validate(settings)
    if anchor_chunk_id is None or ambient_settings.max_seeds == 0 or not pacing_allowed:
        return ()

    present_ids = frozenset(int(value) for value in present_actor_ids)
    protagonist_id = _load_protagonist_entity_id(session)
    eligible_ids = present_ids - ({protagonist_id} if protagonist_id else set())
    if len(eligible_ids) < 2:
        return ()

    candidates = _joint_beat_candidates(
        joint_beats,
        anchor_chunk_id=anchor_chunk_id,
        eligible_ids=eligible_ids,
    )
    candidates.extend(
        _relationship_candidates(
            state,
            anchor_chunk_id=anchor_chunk_id,
            eligible_ids=eligible_ids,
        )
    )
    candidates.extend(
        _claim_acquisition_candidates(
            session,
            anchor_chunk_id=anchor_chunk_id,
            expiry_turns=ambient_settings.expiry_turns,
            eligible_ids=eligible_ids,
        )
    )
    candidates.extend(
        _committed_resolution_candidates(
            session,
            anchor_chunk_id=anchor_chunk_id,
            expiry_turns=ambient_settings.expiry_turns,
            eligible_ids=eligible_ids,
        )
    )

    unexpired = [
        candidate
        for candidate in candidates
        if anchor_chunk_id - candidate.source_turn < ambient_settings.expiry_turns
        and _shares_current_location(state, candidate.participant_ids)
    ]
    by_dyad: dict[Tuple[int, int], _AmbientCandidate] = {}
    for candidate in sorted(
        unexpired,
        key=lambda item: (
            item.participant_ids,
            -item.source_turn,
            item.source_rank,
            item.why_now,
        ),
    ):
        by_dyad.setdefault(candidate.participant_ids, candidate)

    suppressed_keys = _load_suppressed_dedup_keys(
        session,
        anchor_chunk_id=anchor_chunk_id,
        cooldown_turns=ambient_settings.per_dyad_cooldown_turns,
    )
    selectable = [
        candidate
        for candidate in by_dyad.values()
        if _dyad_dedup_key(candidate.participant_ids) not in suppressed_keys
    ]
    selectable.sort(
        key=lambda item: (
            item.participant_ids,
            -item.source_turn,
            item.source_rank,
            item.why_now,
        )
    )
    rng = seeded_stochastic_rng("ambient_scene", anchor_chunk_id, "seed_selection")
    rng.shuffle(selectable)
    selected = selectable[: ambient_settings.max_seeds]

    participant_ids = sorted(
        {entity_id for item in selected for entity_id in item.participant_ids}
    )
    possessed_claims = _load_possessed_claim_ids(session, participant_ids)
    return tuple(
        _seed_from_candidate(
            candidate,
            state=state,
            entity_names=entity_names,
            possessed_claims=possessed_claims,
            settings=ambient_settings,
        )
        for candidate in selected
    )


def _load_protagonist_entity_id(session: Any) -> Optional[int]:
    row = (
        session.execute(
            text(
                """
                /* orrery:ambient_protagonist */
                SELECT c.entity_id
                FROM global_variables gv
                JOIN characters c ON c.id = gv.user_character
                WHERE gv.id = true
                """
            )
        )
        .mappings()
        .first()
    )
    if row is None or row.get("entity_id") is None:
        return None
    return int(row["entity_id"])


def _joint_beat_candidates(
    joint_beats: Iterable[OrreryJointBeat],
    *,
    anchor_chunk_id: int,
    eligible_ids: frozenset[int],
) -> list[_AmbientCandidate]:
    candidates: list[_AmbientCandidate] = []
    for beat in joint_beats:
        participants = _ordered_dyad(beat.entity_a, beat.entity_b)
        if not set(participants).issubset(eligible_ids):
            continue
        candidates.append(
            _AmbientCandidate(
                participant_ids=participants,
                topic=(f"{beat.forward_template_id} / {beat.reverse_template_id}"),
                tension=f"{beat.kind} intent at magnitude {beat.magnitude:.3f}",
                why_now=(
                    "joint beat "
                    f"{beat.forward_proposal_id} + {beat.reverse_proposal_id}"
                ),
                source_turn=anchor_chunk_id,
                source_rank=0,
            )
        )
    return candidates


def _relationship_candidates(
    state: WorldState,
    *,
    anchor_chunk_id: int,
    eligible_ids: frozenset[int],
) -> list[_AmbientCandidate]:
    dyads = {
        _ordered_dyad(source, target)
        for source, target in state.relationship_types
        if source != target and {source, target}.issubset(eligible_ids)
    }
    candidates: list[_AmbientCandidate] = []
    for participants in sorted(dyads):
        entity_a, entity_b = participants
        forward = sorted(state.relationship_types.get((entity_a, entity_b), ()))
        reverse = sorted(state.relationship_types.get((entity_b, entity_a), ()))
        relationship_bits = []
        if forward:
            relationship_bits.append(f"{entity_a}->{entity_b}:{','.join(forward)}")
        if reverse:
            relationship_bits.append(f"{entity_b}->{entity_a}:{','.join(reverse)}")
        trust_values = [
            value
            for value in (
                state.trust.get((entity_a, entity_b)),
                state.trust.get((entity_b, entity_a)),
            )
            if value is not None
        ]
        tension = (
            "relationship valence " + "/".join(str(value) for value in trust_values)
            if trust_values
            else "active relationship state"
        )
        relationship_state = "; ".join(relationship_bits)
        candidates.append(
            _AmbientCandidate(
                participant_ids=participants,
                topic=relationship_state,
                tension=tension,
                why_now=f"relationship state {relationship_state}",
                source_turn=anchor_chunk_id,
                source_rank=3,
            )
        )
    return candidates


def _claim_acquisition_candidates(
    session: Any,
    *,
    anchor_chunk_id: int,
    expiry_turns: int,
    eligible_ids: frozenset[int],
) -> list[_AmbientCandidate]:
    lower_bound = max(0, anchor_chunk_id - expiry_turns + 1)
    rows = session.execute(
        text(
            """
            /* orrery:ambient_claim_acquisitions */
            SELECT awareness.id AS acquisition_id,
                   awareness.claim_id,
                   awareness.knower_entity_id,
                   awareness.immediate_source_entity_id,
                   awareness.source_chunk_id,
                   claim.summary,
                   claim.scope
            FROM claim_awareness awareness
            JOIN claims claim ON claim.id = awareness.claim_id
            WHERE awareness.source_chunk_id BETWEEN :lower_bound AND :anchor
              AND awareness.immediate_source_entity_id IS NOT NULL
            ORDER BY awareness.source_chunk_id DESC, awareness.id
            """
        ),
        {"lower_bound": lower_bound, "anchor": anchor_chunk_id},
    ).mappings()
    candidates: list[_AmbientCandidate] = []
    for row in rows:
        participants = _ordered_dyad(
            int(row["knower_entity_id"]),
            int(row["immediate_source_entity_id"]),
        )
        if not set(participants).issubset(eligible_ids):
            continue
        candidates.append(
            _AmbientCandidate(
                participant_ids=participants,
                topic=str(row["summary"]),
                tension=f"new {row['scope']} claim {int(row['claim_id'])}",
                why_now=f"claim acquisition {int(row['acquisition_id'])}",
                source_turn=int(row["source_chunk_id"]),
                source_rank=1,
            )
        )
    return candidates


def _committed_resolution_candidates(
    session: Any,
    *,
    anchor_chunk_id: int,
    expiry_turns: int,
    eligible_ids: frozenset[int],
) -> list[_AmbientCandidate]:
    lower_bound = max(0, anchor_chunk_id - expiry_turns + 1)
    rows = session.execute(
        text(
            """
            /* orrery:ambient_committed_resolutions */
            SELECT resolution.id AS resolution_id,
                   resolution.tick_chunk_id,
                   resolution.template_id,
                   resolution.brief,
                   resolution.magnitude,
                   event.id AS event_id,
                   event.event_type,
                   event.actor_entity_id,
                   event.target_entity_id
            FROM orrery_resolutions resolution
            JOIN world_events event ON event.resolution_id = resolution.id
            WHERE resolution.tick_chunk_id BETWEEN :lower_bound AND :anchor
              AND event.actor_entity_id IS NOT NULL
              AND event.target_entity_id IS NOT NULL
              AND event.superseded_by_event_id IS NULL
            ORDER BY resolution.tick_chunk_id DESC, event.id
            """
        ),
        {"lower_bound": lower_bound, "anchor": anchor_chunk_id},
    ).mappings()
    candidates: list[_AmbientCandidate] = []
    for row in rows:
        participants = _ordered_dyad(
            int(row["actor_entity_id"]), int(row["target_entity_id"])
        )
        if not set(participants).issubset(eligible_ids):
            continue
        topic = str(row.get("brief") or row["template_id"])
        magnitude = float(row.get("magnitude") or 0.0)
        candidates.append(
            _AmbientCandidate(
                participant_ids=participants,
                topic=topic,
                tension=f"{row['event_type']} at magnitude {magnitude:.3f}",
                why_now=(
                    f"event {int(row['event_id'])} from committed resolution "
                    f"{int(row['resolution_id'])}"
                ),
                source_turn=int(row["tick_chunk_id"]),
                source_rank=2,
            )
        )
    return candidates


def _load_suppressed_dedup_keys(
    session: Any,
    *,
    anchor_chunk_id: int,
    cooldown_turns: int,
) -> frozenset[str]:
    if cooldown_turns <= 0:
        return frozenset()
    cutoff = max(0, anchor_chunk_id - cooldown_turns)
    rows = session.execute(
        text(
            """
            /* orrery:ambient_exposure_cooldown */
            SELECT DISTINCT binding_hash
            FROM orrery_prompt_exposures
            WHERE kind = 'scene_pressure'
              AND template_id = :template_id
              AND tick_chunk_id BETWEEN :cutoff AND :anchor
            """
        ),
        {
            "template_id": AMBIENT_EXPOSURE_TEMPLATE_ID,
            "cutoff": cutoff,
            "anchor": anchor_chunk_id,
        },
    ).mappings()
    return frozenset(str(row["binding_hash"]) for row in rows)


def _load_possessed_claim_ids(
    session: Any, participant_ids: Sequence[int]
) -> dict[int, Tuple[int, ...]]:
    if not participant_ids:
        return {}
    rows = session.execute(
        text(
            """
            /* orrery:ambient_possessed_claims */
            SELECT knower_entity_id, claim_id
            FROM claim_awareness
            WHERE knower_entity_id = ANY(:participant_ids)
            ORDER BY knower_entity_id, claim_id
            """
        ),
        {"participant_ids": list(participant_ids)},
    ).mappings()
    claims: dict[int, list[int]] = {}
    for row in rows:
        claims.setdefault(int(row["knower_entity_id"]), []).append(int(row["claim_id"]))
    return {
        entity_id: tuple(sorted(set(claim_ids)))
        for entity_id, claim_ids in claims.items()
    }


def _seed_from_candidate(
    candidate: _AmbientCandidate,
    *,
    state: WorldState,
    entity_names: Mapping[int, str],
    possessed_claims: Mapping[int, Tuple[int, ...]],
    settings: OrreryAmbientSettings,
) -> AmbientSceneSeed:
    dedup_key = _dyad_dedup_key(candidate.participant_ids)
    seed_material = f"{dedup_key}:{candidate.why_now}"
    return AmbientSceneSeed(
        seed_id=sha256(seed_material.encode("utf-8")).hexdigest(),
        participants=tuple(
            AmbientParticipant(
                entity_id=entity_id,
                name=entity_names.get(entity_id, f"entity {entity_id}"),
                speaking_eligible=True,
            )
            for entity_id in candidate.participant_ids
        ),
        topic=candidate.topic,
        tension=candidate.tension,
        why_now=candidate.why_now,
        entitlements=tuple(
            AmbientEntitlement(
                participant_entity_id=entity_id,
                claim_ids=possessed_claims.get(entity_id, ()),
            )
            for entity_id in candidate.participant_ids
        ),
        location_constraint=AmbientLocationConstraint(
            place_id=_shared_place_id(state, candidate.participant_ids)
        ),
        dedup_key=dedup_key,
        cooldown_turns=settings.per_dyad_cooldown_turns,
        expiry_turns=settings.expiry_turns,
        source_turn=candidate.source_turn,
        line_budget=settings.line_budget,
        turn_budget=settings.turn_budget,
        silence_ok=True,
    )


def _ordered_dyad(entity_a: int, entity_b: int) -> Tuple[int, int]:
    if entity_a == entity_b:
        raise ValueError("ambient scene dyads require distinct participants")
    first, second = sorted((int(entity_a), int(entity_b)))
    return first, second


def _dyad_dedup_key(participant_ids: Tuple[int, int]) -> str:
    entity_a, entity_b = participant_ids
    return sha256(f"ambient_scene:{entity_a}:{entity_b}".encode("utf-8")).hexdigest()


def _shared_place_id(
    state: WorldState, participant_ids: Tuple[int, int]
) -> Optional[int]:
    entity_a, entity_b = participant_ids
    place_a = state.locations.get(entity_a)
    place_b = state.locations.get(entity_b)
    if place_a is None or place_b is None:
        return None
    if place_a != place_b:
        return None
    return int(place_a)


def _shares_current_location(
    state: WorldState, participant_ids: Tuple[int, int]
) -> bool:
    entity_a, entity_b = participant_ids
    place_a = state.locations.get(entity_a)
    place_b = state.locations.get(entity_b)
    return place_a is None or place_b is None or place_a == place_b
