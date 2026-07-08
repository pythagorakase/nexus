"""Tick-floor need accrual: story time rescues world-clock starvation.

The narrative advances ~5 in-world minutes per chunk, so hour-denominated
need thresholds effectively never re-arm on the world clock alone. The
floor makes each elapsed chunk count as at least
``min_accrual_hours_per_chunk`` world-hours for the configured needs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nexus.agents.orrery.needs import NeedTuning, effective_debt_score

BASE = datetime(2073, 10, 31, 12, tzinfo=timezone.utc)

FLOORED = NeedTuning.from_mapping({"min_accrual_hours_per_chunk": {"socialize": 0.5}})


def test_floor_engages_when_story_outpaces_world_clock() -> None:
    """Five in-world minutes across 10 chunks accrues 5 floor-hours."""

    debt = effective_debt_score(
        "socialize",
        0.0,
        last_evaluated_at=BASE,
        current_world_time=BASE + timedelta(minutes=5),
        tuning=FLOORED,
        last_evaluated_chunk_id=100,
        current_chunk_id=110,
    )
    world_only = effective_debt_score(
        "socialize",
        0.0,
        last_evaluated_at=BASE,
        current_world_time=BASE + timedelta(minutes=5),
        tuning=FLOORED,
    )
    rate = FLOORED.accrual_rates["socialize"]
    assert debt == 10 * 0.5 * rate
    assert world_only < debt, "without chunk ids the floor is inert"


def test_world_clock_wins_when_it_exceeds_the_floor() -> None:
    """max() semantics: a long in-world gap is never reduced by the floor."""

    debt = effective_debt_score(
        "socialize",
        0.0,
        last_evaluated_at=BASE,
        current_world_time=BASE + timedelta(hours=30),
        tuning=FLOORED,
        last_evaluated_chunk_id=100,
        current_chunk_id=102,
    )
    rate = FLOORED.accrual_rates["socialize"]
    assert debt == 30 * rate


def test_unfloored_needs_and_null_stamps_reproduce_legacy_accrual() -> None:
    """Defaults are exact no-ops: 0.0 floors, NULL stamps, unlisted needs."""

    rate = FLOORED.accrual_rates["hunger"]
    legacy = effective_debt_score(
        "hunger",
        1.0,
        last_evaluated_at=BASE,
        current_world_time=BASE + timedelta(hours=2),
        tuning=FLOORED,
        last_evaluated_chunk_id=100,
        current_chunk_id=200,
    )
    assert legacy == 1.0 + 2 * rate

    null_stamp = effective_debt_score(
        "socialize",
        1.0,
        last_evaluated_at=BASE,
        current_world_time=BASE + timedelta(minutes=5),
        tuning=FLOORED,
        last_evaluated_chunk_id=None,
        current_chunk_id=200,
    )
    assert null_stamp == effective_debt_score(
        "socialize",
        1.0,
        last_evaluated_at=BASE,
        current_world_time=BASE + timedelta(minutes=5),
        tuning=FLOORED,
    )


def test_default_tuning_floors_are_all_zero() -> None:
    tuning = NeedTuning.default()
    assert set(tuning.min_accrual_hours_per_chunk) == {
        "sleep",
        "hunger",
        "thirst",
        "socialize",
        "intimacy",
    }
    assert all(v == 0.0 for v in tuning.min_accrual_hours_per_chunk.values())


def test_resolver_loader_threads_chunk_stamp() -> None:
    """The hydration path applies the floor from stored chunk stamps."""

    import sys

    sys.path.insert(0, "tests/test_orrery")
    from test_resolver import FakeSession

    from nexus.agents.orrery.resolver import _load_need_debt_scores

    session = FakeSession(
        need_debt_rows=[
            {
                "character_entity_id": 1,
                "need_type": "socialize",
                "debt_score": 0.0,
                "last_evaluated_at": BASE,
                "last_evaluated_chunk_id": 100,
            }
        ],
    )
    scores = _load_need_debt_scores(
        session,
        current_world_time=BASE + timedelta(minutes=5),
        need_tuning=FLOORED,
        tags_by_entity={},
        anchor_chunk_id=120,
    )
    rate = FLOORED.accrual_rates["socialize"]
    assert scores[(1, "socialize")] == 20 * 0.5 * rate
