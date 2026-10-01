"""Offline contract for the crossed-boundary enumerator (issue 780).

The two producer classes below are written against the contract's extension
point (``BoundaryProducer``); they read nothing from a database, so the
enumerator's validation and ordering are exercised without one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import pytest

from nexus.agents.orrery.boundaries import (
    DEFAULT_PRODUCERS,
    BoundaryClass,
    BoundaryWindow,
    CrossedBoundary,
    ProducerScan,
    enumerate_crossed_boundaries,
)
from nexus.config.settings_models import OrrerySettings

T0 = datetime(2189, 10, 17, 18, 7, tzinfo=timezone.utc)
# The fixed producers never touch the cursor or the settings.
NO_CURSOR: Any = None
NO_SETTINGS: Any = None


@dataclass
class FixedProducer:
    """A producer that returns a fixed list of instants for one subject kind."""

    name: str
    boundary_class: BoundaryClass
    precedence: int
    owner_issue: int | None
    instants: Sequence[tuple[tuple[str | int, ...], datetime]] = ()
    already_due: int = 0
    tamper: dict[str, Any] = field(default_factory=dict)

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Return every configured instant as a crossing, stamped as declared."""

        crossings = tuple(
            replace(
                CrossedBoundary(
                    producer=self.name,
                    subject_key=subject_key,
                    occurs_at_world_time=instant,
                    boundary_class=self.boundary_class,
                    precedence=self.precedence,
                    owner_issue=self.owner_issue,
                    detail={},
                ),
                **self.tamper,
            )
            for subject_key, instant in self.instants
        )
        return ProducerScan(crossings=crossings, at_or_before_previous=self.already_due)


def _deterministic(**overrides: Any) -> FixedProducer:
    values: dict[str, Any] = {
        "name": "fixed_deterministic",
        "boundary_class": BoundaryClass.DETERMINISTIC,
        "precedence": 5,
        "owner_issue": None,
    }
    values.update(overrides)
    return FixedProducer(**values)


def _adjudicable(**overrides: Any) -> FixedProducer:
    values: dict[str, Any] = {
        "name": "fixed_adjudicable",
        "boundary_class": BoundaryClass.ADJUDICABLE,
        "precedence": 50,
        "owner_issue": 785,
    }
    values.update(overrides)
    return FixedProducer(**values)


def _window(hours: float = 3.0) -> BoundaryWindow:
    return BoundaryWindow.projected_child_clock(T0, timedelta(hours=hours))


def _enumerate(*producers: FixedProducer, window: BoundaryWindow | None = None) -> Any:
    return enumerate_crossed_boundaries(
        NO_CURSOR,
        window or _window(),
        settings=NO_SETTINGS,
        producers=producers,
    )


def test_window_constructors_reject_naive_negative_and_reversed() -> None:
    naive = T0.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        BoundaryWindow.projected_child_clock(naive, timedelta(hours=1))
    with pytest.raises(ValueError, match="negative"):
        BoundaryWindow.projected_child_clock(T0, timedelta(minutes=-1))
    with pytest.raises(ValueError, match="timezone-aware"):
        BoundaryWindow.target_horizon(T0, naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        BoundaryWindow.target_horizon(naive, T0)
    with pytest.raises(ValueError, match="before its previous clock"):
        BoundaryWindow.target_horizon(T0, T0 - timedelta(seconds=1))


def test_window_sources_and_half_open_interval() -> None:
    projected = BoundaryWindow.projected_child_clock(T0, timedelta(hours=1))
    assert projected.source == "projected_child_clock"
    assert projected.target_world_time == T0 + timedelta(hours=1)
    horizon = BoundaryWindow.target_horizon(T0, T0 + timedelta(days=10))
    assert horizon.source == "target_horizon"
    assert not projected.contains(T0)
    assert projected.contains(T0 + timedelta(microseconds=1))
    assert projected.contains(T0 + timedelta(hours=1))
    assert not projected.contains(T0 + timedelta(hours=1, microseconds=1))


def test_zero_time_window_contains_nothing() -> None:
    zero = BoundaryWindow.projected_child_clock(T0, timedelta(0))
    assert zero.target_world_time == zero.previous_world_time
    for offset in (timedelta(0), timedelta(microseconds=1), -timedelta(minutes=10)):
        assert not zero.contains(T0 + offset)
    enumeration = _enumerate(_deterministic(already_due=2), window=zero)
    assert enumeration.crossings == ()
    assert enumeration.at_or_before_previous["fixed_deterministic"] == 2


def test_crossings_order_by_instant_then_precedence() -> None:
    at_two = T0 + timedelta(hours=2)
    adjudicable = _adjudicable(
        instants=[(("project", 2), at_two), (("project", 1), at_two)]
    )
    deterministic = _deterministic(
        instants=[
            (("claim_hop", 9, 4), at_two),
            (("claim_hop", 9, 3), T0 + timedelta(hours=1)),
        ],
        already_due=1,
    )
    enumeration = _enumerate(adjudicable, deterministic)

    assert [
        (crossing.producer, crossing.subject_key, crossing.occurs_at_world_time)
        for crossing in enumeration.crossings
    ] == [
        ("fixed_deterministic", ("claim_hop", 9, 3), T0 + timedelta(hours=1)),
        ("fixed_deterministic", ("claim_hop", 9, 4), at_two),
        ("fixed_adjudicable", ("project", 1), at_two),
        ("fixed_adjudicable", ("project", 2), at_two),
    ]
    assert enumeration.counts == {"fixed_adjudicable": 2, "fixed_deterministic": 2}
    assert enumeration.at_or_before_previous == {
        "fixed_adjudicable": 0,
        "fixed_deterministic": 1,
    }
    assert enumeration.total == 4


def test_every_producer_reports_counts_with_zeros() -> None:
    enumeration = _enumerate(_deterministic(), _adjudicable())
    assert enumeration.counts == {"fixed_deterministic": 0, "fixed_adjudicable": 0}
    assert enumeration.at_or_before_previous == {
        "fixed_deterministic": 0,
        "fixed_adjudicable": 0,
    }


def test_duplicate_producer_names_raise() -> None:
    with pytest.raises(ValueError, match="Duplicate boundary producer names"):
        _enumerate(_deterministic(), _adjudicable(name="fixed_deterministic"))


def test_duplicate_producer_precedences_raise() -> None:
    with pytest.raises(ValueError, match="Duplicate boundary producer precedences"):
        _enumerate(_deterministic(), _adjudicable(precedence=5))


@pytest.mark.parametrize(
    "tamper",
    [
        {"producer": "someone_else"},
        {"boundary_class": BoundaryClass.ADJUDICABLE},
        {"precedence": 6},
        {"owner_issue": 781},
    ],
)
def test_crossing_stamped_unlike_its_producer_raises(tamper: dict[str, Any]) -> None:
    producer = _deterministic(
        instants=[(("entity_tag", 1), T0 + timedelta(minutes=30))], tamper=tamper
    )
    with pytest.raises(ValueError, match="returned a crossing stamped"):
        _enumerate(producer)


@pytest.mark.parametrize(
    "instant",
    [T0, T0 - timedelta(minutes=10), T0 + timedelta(hours=3, seconds=1)],
)
def test_crossing_outside_the_window_raises(instant: datetime) -> None:
    producer = _deterministic(instants=[(("entity_tag", 1), instant)])
    with pytest.raises(ValueError, match="outside the window"):
        _enumerate(producer)


def test_repeated_crossing_raises() -> None:
    instant = T0 + timedelta(hours=1)
    producer = _deterministic(
        instants=[(("entity_tag", 1), instant), (("entity_tag", 1), instant)]
    )
    with pytest.raises(ValueError, match="repeated the crossing"):
        _enumerate(producer)


def test_same_subject_at_two_instants_is_two_crossings() -> None:
    producer = _deterministic(
        instants=[
            (("entity_tag", 1), T0 + timedelta(hours=2)),
            (("entity_tag", 1), T0 + timedelta(hours=1)),
        ]
    )
    enumeration = _enumerate(producer)
    assert [c.occurs_at_world_time for c in enumeration.crossings] == [
        T0 + timedelta(hours=1),
        T0 + timedelta(hours=2),
    ]


def test_crossing_rejects_naive_instant_and_kindless_subject() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        CrossedBoundary(
            producer="p",
            subject_key=("entity_tag", 1),
            occurs_at_world_time=T0.replace(tzinfo=None),
            boundary_class=BoundaryClass.DETERMINISTIC,
            precedence=1,
            owner_issue=None,
        )
    with pytest.raises(ValueError, match="subject kind"):
        CrossedBoundary(
            producer="p",
            subject_key=(1, "entity_tag"),
            occurs_at_world_time=T0,
            boundary_class=BoundaryClass.DETERMINISTIC,
            precedence=1,
            owner_issue=None,
        )


def test_default_producers_registry() -> None:
    assert [
        (p.name, p.boundary_class, p.precedence, p.owner_issue)
        for p in DEFAULT_PRODUCERS
    ] == [
        ("tag_expiry", BoundaryClass.DETERMINISTIC, 10, None),
        ("claim_propagation", BoundaryClass.DETERMINISTIC, 20, None),
        ("travel_eta", BoundaryClass.ADJUDICABLE, 30, 785),
        ("project_due", BoundaryClass.ADJUDICABLE, 40, None),
        ("project_neglected", BoundaryClass.ADJUDICABLE, 41, None),
        ("project_abandon", BoundaryClass.ADJUDICABLE, 42, None),
    ]
