"""Unit regressions for Orrery need-debt persistence limits."""

import pytest

from nexus.agents.orrery.events import (
    NeedDebtScoreDomainError,
    _validate_need_debt_score_domain,
)


def test_need_debt_domain_guard_matches_postgres_numeric_rounding() -> None:
    """Reject values that numeric(8,2) would round out of range."""

    _validate_need_debt_score_domain(
        actor_entity_id=17,
        need_type="thirst",
        debt_score=999999.994,
    )

    with pytest.raises(
        NeedDebtScoreDomainError,
        match=(
            r"need debt score outside numeric\(8,2\) domain: "
            r"character=17, need=thirst, value=999999.995"
        ),
    ):
        _validate_need_debt_score_domain(
            actor_entity_id=17,
            need_type="thirst",
            debt_score=999999.995,
        )
