"""Offline contract for the crossed-boundary enumerator (issue 780).

The two producer classes below are written against the contract's extension
point (``BoundaryProducer``), the way #785, #781, #782 and #797 will plug in:
each declares its own name, class, precedence and owner issue as class
attributes and returns its own crossings from ``scan()``. They read nothing
from a database, so the enumerator's validation and ordering are exercised
without one. The stamping-mismatch cases use a separate small subclass, so
that path does not stand in for the extension point.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import pytest

from nexus.agents.orrery.boundaries import (
    DEFAULT_PRODUCERS,
    BoundaryClass,
    BoundaryProducer,
    BoundaryWindow,
    CrossedBoundary,
    ProducerScan,
    enumerate_crossed_boundaries,
)
from nexus.config.settings_models import OrrerySettings

T0 = datetime(2189, 10, 17, 18, 7, tzinfo=timezone.utc)
# The fixture producers never touch the cursor or the settings.
NO_CURSOR: Any = None
NO_SETTINGS: Any = None

SubjectInstants = Sequence[tuple[tuple[str | int, ...], datetime]]


class DeterministicFixture:
    """A deterministic producer that returns fixed instants for any subjects."""

    name = "fixed_deterministic"
    boundary_class = BoundaryClass.DETERMINISTIC
    precedence = 5
    owner_issue: int | None = None

    def __init__(self, instants: SubjectInstants = (), already_due: int = 0) -> None:
        self.instants = tuple(instants)
        self.already_due = already_due

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Return every configured instant as a crossing of this producer."""

        crossings = tuple(
            CrossedBoundary(
                producer=self.name,
                subject_key=subject_key,
                occurs_at_world_time=instant,
                boundary_class=self.boundary_class,
                precedence=self.precedence,
                owner_issue=self.owner_issue,
            )
            for subject_key, instant in self.instants
        )
        return ProducerScan(crossings=crossings, at_or_before_previous=self.already_due)


class AdjudicableFixture:
    """An adjudicable producer, owned by another issue, keyed by project ID."""

    name = "fixed_adjudicable"
    boundary_class = BoundaryClass.ADJUDICABLE
    precedence = 50
    owner_issue: int | None = 785

    def __init__(self, due: Mapping[int, datetime] | None = None) -> None:
        self.due = dict(due or {})

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Return one crossing per project whose instant lies in the window."""

        crossings: list[CrossedBoundary] = []
        pending = 0
        for project_id, instant in self.due.items():
            if instant <= window.previous_world_time:
                pending += 1
            elif window.contains(instant):
                crossings.append(
                    CrossedBoundary(
                        producer=self.name,
                        subject_key=("project", project_id),
                        occurs_at_world_time=instant,
                        boundary_class=self.boundary_class,
                        precedence=self.precedence,
                        owner_issue=self.owner_issue,
                        detail={"project_id": project_id},
                    )
                )
        return ProducerScan(crossings=tuple(crossings), at_or_before_previous=pending)


class NameClashFixture(AdjudicableFixture):
    """An adjudicable producer that reuses the deterministic fixture's name."""

    name = DeterministicFixture.name


class PrecedenceClashFixture(AdjudicableFixture):
    """An adjudicable producer that reuses the deterministic fixture's precedence."""

    precedence = DeterministicFixture.precedence


class MisstampedFixture(DeterministicFixture):
    """A deterministic producer whose crossings disagree with its declaration."""

    def __init__(self, instants: SubjectInstants, tamper: Mapping[str, Any]) -> None:
        super().__init__(instants)
        self.tamper = dict(tamper)

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Return the parent's crossings with the tampered fields replaced."""

        scan = super().scan(cur, window, settings)
        return ProducerScan(
            crossings=tuple(replace(c, **self.tamper) for c in scan.crossings),
            at_or_before_previous=scan.at_or_before_previous,
        )


def _window(hours: float = 3.0) -> BoundaryWindow:
    return BoundaryWindow.projected_child_clock(T0, timedelta(hours=hours))


def _enumerate(
    *producers: BoundaryProducer, window: BoundaryWindow | None = None
) -> Any:
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
    enumeration = _enumerate(DeterministicFixture(already_due=2), window=zero)
    assert enumeration.crossings == ()
    assert enumeration.at_or_before_previous["fixed_deterministic"] == 2


def test_crossings_order_by_instant_then_precedence() -> None:
    at_two = T0 + timedelta(hours=2)
    adjudicable = AdjudicableFixture(due={2: at_two, 1: at_two})
    deterministic = DeterministicFixture(
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
    enumeration = _enumerate(DeterministicFixture(), AdjudicableFixture())
    assert enumeration.counts == {"fixed_deterministic": 0, "fixed_adjudicable": 0}
    assert enumeration.at_or_before_previous == {
        "fixed_deterministic": 0,
        "fixed_adjudicable": 0,
    }


def test_duplicate_producer_names_raise() -> None:
    with pytest.raises(ValueError, match="Duplicate boundary producer names"):
        _enumerate(DeterministicFixture(), NameClashFixture())


def test_duplicate_producer_precedences_raise() -> None:
    with pytest.raises(ValueError, match="Duplicate boundary producer precedences"):
        _enumerate(DeterministicFixture(), PrecedenceClashFixture())


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
    producer = MisstampedFixture(
        [(("entity_tag", 1), T0 + timedelta(minutes=30))], tamper=tamper
    )
    with pytest.raises(ValueError, match="returned a crossing stamped"):
        _enumerate(producer)


@pytest.mark.parametrize(
    "instant",
    [T0, T0 - timedelta(minutes=10), T0 + timedelta(hours=3, seconds=1)],
)
def test_crossing_outside_the_window_raises(instant: datetime) -> None:
    producer = DeterministicFixture(instants=[(("entity_tag", 1), instant)])
    with pytest.raises(ValueError, match="outside the window"):
        _enumerate(producer)


def test_repeated_crossing_raises() -> None:
    instant = T0 + timedelta(hours=1)
    producer = DeterministicFixture(
        instants=[(("entity_tag", 1), instant), (("entity_tag", 1), instant)]
    )
    with pytest.raises(ValueError, match="repeated the crossing"):
        _enumerate(producer)


def test_same_subject_at_two_instants_is_two_crossings() -> None:
    producer = DeterministicFixture(
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


def test_crossing_is_hashable_and_detail_still_compares() -> None:
    crossing = CrossedBoundary(
        producer="p",
        subject_key=("entity_tag", 1),
        occurs_at_world_time=T0,
        boundary_class=BoundaryClass.DETERMINISTIC,
        precedence=1,
        owner_issue=None,
        detail={"tag": "off_grid"},
    )
    assert len({crossing, crossing}) == 1
    assert len({crossing, replace(crossing)}) == 1
    other_detail = replace(crossing, detail={"tag": "watched"})
    assert hash(other_detail) == hash(crossing)
    assert other_detail != crossing


def test_both_fixture_classes_satisfy_the_producer_contract() -> None:
    producers: tuple[BoundaryProducer, ...] = (
        DeterministicFixture(),
        AdjudicableFixture(),
    )
    assert {type(p) for p in producers} == {DeterministicFixture, AdjudicableFixture}
    assert [
        (p.name, p.boundary_class, p.precedence, p.owner_issue) for p in producers
    ] == [
        ("fixed_deterministic", BoundaryClass.DETERMINISTIC, 5, None),
        ("fixed_adjudicable", BoundaryClass.ADJUDICABLE, 50, 785),
    ]


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
