"""Pure-unit coverage for template-authored backstory reveal gates."""

from datetime import datetime, timezone

import pytest

from nexus.agents.orrery.reveal_gates import (
    SecretContext,
    holder_death,
    participants_reunited,
    trust_earned,
    validate_reveal_gate_registry,
)
from nexus.agents.orrery.substrate import TravelState, WorldState


HOLDER = 1
FIRST = 2
SECOND = 3


@pytest.fixture()
def context() -> SecretContext:
    return SecretContext(
        secret_id=11,
        claim_id=12,
        holder_entity_id=HOLDER,
        world_event_id=13,
        participant_entity_ids=(HOLDER, FIRST, SECOND),
        created_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )


def test_holder_death_fires_only_for_inactive_holder(context: SecretContext) -> None:
    assert holder_death(WorldState(is_active={}), context) is False
    assert holder_death(WorldState(is_active={HOLDER: False}), context) is True
    assert holder_death(WorldState(is_active={HOLDER: True}), context) is False


def test_participants_reunited_requires_two_safe_copresent_peers(
    context: SecretContext,
) -> None:
    reunited = WorldState(locations={HOLDER: 8, FIRST: 8, SECOND: 8})
    assert participants_reunited(reunited, context) is True

    one_elsewhere = WorldState(locations={HOLDER: 8, FIRST: 8, SECOND: 9})
    assert participants_reunited(one_elsewhere, context) is False

    travelling = WorldState(
        locations={HOLDER: 8, FIRST: 8, SECOND: 8},
        travel_states={SECOND: TravelState(status="in_transit")},
    )
    assert participants_reunited(travelling, context) is False


def test_trust_earned_requires_directional_deep_mutual_trust(
    context: SecretContext,
) -> None:
    earned = WorldState(trust={(FIRST, HOLDER): 3, (HOLDER, FIRST): 2})
    assert trust_earned(earned, context) is True

    shallow_reverse = WorldState(trust={(FIRST, HOLDER): 3, (HOLDER, FIRST): 1})
    assert trust_earned(shallow_reverse, context) is False


def test_registry_validation_rejects_non_snake_case_names() -> None:
    with pytest.raises(ValueError, match="snake_case"):
        validate_reveal_gate_registry({"Not-Snake": holder_death})
