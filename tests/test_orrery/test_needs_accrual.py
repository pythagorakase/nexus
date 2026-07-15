"""Pure world-clock accrual for Orrery character needs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from inspect import signature

import pytest

from nexus.agents.orrery.needs import NeedTuning, effective_debt_score

BASE = datetime(2073, 10, 31, 12, tzinfo=timezone.utc)


def test_need_debt_accrues_from_positive_world_time_only() -> None:
    """Elapsed diegetic hours accrue at the configured per-hour rate."""

    tuning = NeedTuning.from_mapping({"accrual_rates": {"socialize": 2.0}})

    debt = effective_debt_score(
        "socialize",
        1.5,
        last_evaluated_at=BASE,
        current_world_time=BASE + timedelta(hours=2, minutes=15),
        tuning=tuning,
    )

    assert debt == 6.0


@pytest.mark.parametrize(
    ("last_evaluated_at", "current_world_time"),
    [
        (None, BASE),
        (BASE, None),
        (BASE, BASE),
        (BASE, BASE - timedelta(minutes=1)),
    ],
)
def test_missing_or_nonpositive_world_time_does_not_accrue(
    last_evaluated_at: datetime | None,
    current_world_time: datetime | None,
) -> None:
    """Unknown, stationary, and regressed clocks leave debt unchanged."""

    debt = effective_debt_score(
        "hunger",
        3.25,
        last_evaluated_at=last_evaluated_at,
        current_world_time=current_world_time,
    )

    assert debt == 3.25


def test_need_accrual_contract_has_no_narrative_chunk_clock() -> None:
    """Chunk-id gaps cannot influence the diegetic accrual authority."""

    assert tuple(signature(effective_debt_score).parameters) == (
        "need_type",
        "debt_score",
        "last_evaluated_at",
        "current_world_time",
        "tuning",
    )


def test_need_debt_remains_nonnegative_without_elapsed_world_time() -> None:
    """The existing lower bound still applies when no time elapses."""

    debt = effective_debt_score(
        "thirst",
        -2.0,
        last_evaluated_at=BASE,
        current_world_time=BASE,
    )

    assert debt == 0.0
