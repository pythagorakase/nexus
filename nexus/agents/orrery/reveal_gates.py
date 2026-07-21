"""Pure template-authored gates for durable backstory secrets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Callable, Mapping

from nexus.agents.orrery.substrate import WorldState


@dataclass(frozen=True, slots=True)
class SecretContext:
    """Immutable claim and holder facts supplied to one reveal gate."""

    secret_id: int
    claim_id: int
    holder_entity_id: int
    world_event_id: int
    participant_entity_ids: tuple[int, ...]
    created_at: datetime


RevealGate = Callable[[WorldState, SecretContext], bool]


def holder_death(state: WorldState, context: SecretContext) -> bool:
    """Reveal a secret when its keeper can no longer keep it in the world."""

    if context.holder_entity_id not in state.is_active:
        # Irreversible reveals require positive evidence; missing activity is
        # unknown, not proof that the holder is dead.
        return False
    return not state.is_active[context.holder_entity_id]


def participants_reunited(state: WorldState, context: SecretContext) -> bool:
    """Reveal when two fellow participants safely reunite with the holder."""

    holder_id = context.holder_entity_id
    holder_location = state.locations.get(holder_id)
    if holder_location is None or _in_transit(state, holder_id):
        return False
    reunited = {
        participant_id
        for participant_id in context.participant_entity_ids
        if participant_id != holder_id
        and state.locations.get(participant_id) == holder_location
        and not _in_transit(state, participant_id)
    }
    return len(reunited) >= 2


def trust_earned(state: WorldState, context: SecretContext) -> bool:
    """Reveal after a participant and holder establish deep mutual confidence."""

    holder_id = context.holder_entity_id
    return any(
        participant_id != holder_id
        and state.trust.get((participant_id, holder_id), 0) >= 3
        and state.trust.get((holder_id, participant_id), 0) >= 2
        for participant_id in context.participant_entity_ids
    )


def _in_transit(state: WorldState, entity_id: int) -> bool:
    travel_state = state.travel_states.get(entity_id)
    return bool(travel_state and travel_state.is_in_transit)


REVEAL_GATES: Mapping[str, RevealGate] = {
    "holder_death": holder_death,
    "participants_reunited": participants_reunited,
    "trust_earned": trust_earned,
}

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def validate_reveal_gate_registry(
    registry: Mapping[str, RevealGate] = REVEAL_GATES,
) -> None:
    """Reject blank, malformed, or non-callable reveal-gate registrations."""

    invalid_names = sorted(
        name for name in registry if not name or _SNAKE_CASE.fullmatch(name) is None
    )
    if invalid_names:
        raise ValueError(
            "Reveal gate registry keys must be non-empty snake_case names: "
            f"{invalid_names}"
        )
    non_callable = sorted(name for name, gate in registry.items() if not callable(gate))
    if non_callable:
        raise TypeError(f"Reveal gate registry values must be callable: {non_callable}")


validate_reveal_gate_registry()
