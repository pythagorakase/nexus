"""Read-only enumeration of world-clock boundaries a turn would cross.

A boundary is a world-clock instant at which some scheduled Orrery state
changes truth: a tag expires, a bounded claim reaches its next knower, a
journey's ETA arrives, or a project falls due, falls behind, or reaches its
abandonment point. A turn that moves the clock from ``previous_world_time``
to ``target_world_time`` crosses every boundary in that half-open interval
``(previous, target]``.

This module is the contract that a future accepting phase (issue 780) and its
QA family read. It issues SELECT statements only. It materializes nothing,
simulates no reschedule or rearm, and coalesces nothing: every crossing is
reported at its own instant, ordered by ``(occurs_at_world_time, precedence,
producer, subject_key)``. Occurrence times are world-clock instants
(``timestamptz``); tick and chunk IDs never stand in for them.

Deterministic producers sit below adjudicable ones in precedence because the
commit materializes deterministic state (the tag sweep) before the state that
an adjudicable phase would read (the propagation drain runs after it).
External producers (issues 785, 781, 782, 797) join by adding to
``DEFAULT_PRODUCERS`` in their own slices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol, Sequence

from nexus.agents.orrery.db_rows import row_get
from nexus.agents.orrery.propagation import plan_due_propagations_sync
from nexus.agents.orrery.substrate import ProjectPolicy, coerce_project_policy
from nexus.config.settings_models import OrrerySettings


WindowSource = Literal["projected_child_clock", "target_horizon"]
_WINDOW_SOURCES: frozenset[str] = frozenset({"projected_child_clock", "target_horizon"})


class BoundaryClass(str, Enum):
    """Whether a crossing materializes by rule or needs adjudication."""

    DETERMINISTIC = "deterministic"
    ADJUDICABLE = "adjudicable"


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware, got naive {value!r}")


@dataclass(frozen=True)
class BoundaryWindow:
    """The half-open world-clock interval ``(previous, target]`` one turn spans.

    ``source`` records how the target was chosen: projected from a child
    chunk's ``time_delta`` or supplied as an explicit horizon. A zero-time
    window (``previous == target``) contains no instant.
    """

    previous_world_time: datetime
    target_world_time: datetime
    source: WindowSource

    def __post_init__(self) -> None:
        _require_aware(self.previous_world_time, "previous_world_time")
        _require_aware(self.target_world_time, "target_world_time")
        if self.source not in _WINDOW_SOURCES:
            raise ValueError(f"Unknown boundary window source {self.source!r}")
        if self.target_world_time < self.previous_world_time:
            raise ValueError(
                f"Boundary window target {self.target_world_time.isoformat()} "
                f"is before its previous clock "
                f"{self.previous_world_time.isoformat()}"
            )

    @classmethod
    def projected_child_clock(
        cls, previous_world_time: datetime, time_delta: timedelta
    ) -> "BoundaryWindow":
        """Return the window a child chunk with ``time_delta`` would span."""

        if not isinstance(time_delta, timedelta):
            raise ValueError(
                f"time_delta must be a timedelta, got {type(time_delta).__name__}"
            )
        if time_delta < timedelta(0):
            raise ValueError(f"Boundary window time_delta {time_delta} is negative")
        _require_aware(previous_world_time, "previous_world_time")
        return cls(
            previous_world_time=previous_world_time,
            target_world_time=previous_world_time + time_delta,
            source="projected_child_clock",
        )

    @classmethod
    def target_horizon(
        cls, previous_world_time: datetime, target_world_time: datetime
    ) -> "BoundaryWindow":
        """Return the window from the previous clock to an explicit target."""

        return cls(
            previous_world_time=previous_world_time,
            target_world_time=target_world_time,
            source="target_horizon",
        )

    def contains(self, instant: datetime) -> bool:
        """Return whether ``previous < instant <= target``."""

        return self.previous_world_time < instant <= self.target_world_time


def parent_world_time(cur: Any, parent_chunk_id: int) -> datetime:
    """Return a primary-layer parent chunk's world clock, or raise.

    Raises ``ValueError`` naming the chunk when its ``chunk_metadata`` row is
    missing, its ``world_time`` is NULL, or its layer is not ``primary``.
    There is no fallback clock.
    """

    cur.execute(
        """
        SELECT world_time, world_layer::text AS world_layer
        FROM chunk_metadata
        WHERE chunk_id = %s
        """,
        (parent_chunk_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Parent chunk {parent_chunk_id} has no chunk_metadata row")
    world_time = row_get(row, "world_time", 0)
    world_layer = row_get(row, "world_layer", 1)
    if world_time is None:
        raise ValueError(f"Parent chunk {parent_chunk_id} has a NULL world_time")
    if world_layer != "primary":
        raise ValueError(
            f"Parent chunk {parent_chunk_id} is on the {world_layer!r} layer, "
            "not 'primary'"
        )
    if not isinstance(world_time, datetime):
        raise ValueError(
            f"Parent chunk {parent_chunk_id} world_time is not a timestamp: "
            f"{world_time!r}"
        )
    return world_time


@dataclass(frozen=True)
class CrossedBoundary:
    """One scheduled state change whose instant lies inside a window.

    ``subject_key`` names what changes; its first element is the subject kind
    (``"entity_tag"``, ``"claim_hop"``, ``"travel"``, ``"project"``).
    ``owner_issue`` names the issue that owns materializing the crossing when
    another slice does. ``detail`` takes part in equality but not in the
    hash (it is held as a read-only mapping, which cannot be hashed), so a
    crossing hashes on its producer, subject, instant, class, precedence and
    owner issue.
    """

    producer: str
    subject_key: tuple[str | int, ...]
    occurs_at_world_time: datetime
    boundary_class: BoundaryClass
    precedence: int
    owner_issue: int | None
    detail: Mapping[str, Any] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        _require_aware(self.occurs_at_world_time, "occurs_at_world_time")
        if not self.subject_key or not isinstance(self.subject_key[0], str):
            raise ValueError(
                f"Crossing from {self.producer!r} needs a subject_key whose "
                f"first element is the subject kind, got {self.subject_key!r}"
            )
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))


@dataclass(frozen=True)
class ProducerScan:
    """One producer's crossings plus its subjects already pending at the start.

    ``at_or_before_previous`` counts subjects whose instant is at or before
    the window's previous clock and that are still pending (not yet
    materialized), so they are not crossings of this window.
    """

    crossings: tuple[CrossedBoundary, ...]
    at_or_before_previous: int


class BoundaryProducer(Protocol):
    """A registered source of crossed boundaries."""

    name: str
    boundary_class: BoundaryClass
    precedence: int
    owner_issue: int | None

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Return the crossings inside ``window`` and the count already due."""
        ...


@dataclass(frozen=True)
class BoundaryEnumeration:
    """The ordered crossings of one window across every producer.

    ``counts`` and ``at_or_before_previous`` carry every producer's name,
    zeros included.
    """

    window: BoundaryWindow
    crossings: tuple[CrossedBoundary, ...]
    counts: Mapping[str, int]
    at_or_before_previous: Mapping[str, int]

    @property
    def total(self) -> int:
        """Return the number of crossings in the window."""

        return len(self.crossings)


def _crossing(
    producer: BoundaryProducer,
    subject_key: tuple[str | int, ...],
    occurs_at_world_time: datetime,
    detail: Mapping[str, Any],
) -> CrossedBoundary:
    return CrossedBoundary(
        producer=producer.name,
        subject_key=subject_key,
        occurs_at_world_time=occurs_at_world_time,
        boundary_class=producer.boundary_class,
        precedence=producer.precedence,
        owner_issue=producer.owner_issue,
        detail=detail,
    )


def _split(
    producer: BoundaryProducer,
    window: BoundaryWindow,
    candidates: Sequence[tuple[tuple[str | int, ...], datetime, Mapping[str, Any]]],
) -> ProducerScan:
    """Partition candidate instants into crossings and already-due subjects."""

    crossings: list[CrossedBoundary] = []
    already_due = 0
    for subject_key, instant, detail in candidates:
        if instant <= window.previous_world_time:
            already_due += 1
        elif instant <= window.target_world_time:
            crossings.append(_crossing(producer, subject_key, instant, detail))
    return ProducerScan(crossings=tuple(crossings), at_or_before_previous=already_due)


class TagExpiryProducer:
    """Uncleared entity tags whose ``expires_at_world_time`` falls due."""

    name: str = "tag_expiry"
    boundary_class: BoundaryClass = BoundaryClass.DETERMINISTIC
    precedence: int = 10
    owner_issue: int | None = None

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Read uncleared expiring tags up to the window's target."""

        cur.execute(
            """
            SELECT et.id, et.entity_id, et.tag_id, t.tag,
                   et.expires_at_world_time
            FROM entity_tags et
            JOIN tags t ON t.id = et.tag_id
            WHERE et.cleared_at IS NULL
              AND et.expires_at_world_time IS NOT NULL
              AND et.expires_at_world_time <= %s
            ORDER BY et.expires_at_world_time, et.id
            """,
            (window.target_world_time,),
        )
        candidates = []
        for row in cur.fetchall():
            entity_tag_id = int(row_get(row, "id", 0))
            candidates.append(
                (
                    ("entity_tag", entity_tag_id),
                    row_get(row, "expires_at_world_time", 4),
                    {
                        "entity_id": int(row_get(row, "entity_id", 1)),
                        "tag_id": int(row_get(row, "tag_id", 2)),
                        "tag": str(row_get(row, "tag", 3)),
                    },
                )
            )
        return _split(self, window, candidates)


class ClaimPropagationProducer:
    """Bounded-claim hops the propagation planner schedules inside the window."""

    name: str = "claim_propagation"
    boundary_class: BoundaryClass = BoundaryClass.DETERMINISTIC
    precedence: int = 20
    owner_issue: int | None = None

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Plan every hop due by the target; nothing when contagion is off."""

        planned = plan_due_propagations_sync(
            cur,
            horizon_world_time=window.target_world_time,
            settings=settings.contagion,
            distortion_settings=settings.distortion,
        )
        candidates = [
            (
                (
                    "claim_hop",
                    hop.incident_world_event_id,
                    hop.knower_entity_id,
                ),
                hop.acquired_at_world_time,
                {
                    "claim_id": hop.claim_id,
                    "delivered_claim_id": hop.delivered_claim_id,
                    "immediate_source_entity_id": hop.immediate_source_entity_id,
                    "root_source_entity_id": hop.root_source_entity_id,
                    "channel": hop.channel,
                    "depth": hop.depth,
                    "latency_seconds": hop.latency_seconds,
                },
            )
            for hop in planned
        ]
        return _split(self, window, candidates)


class TravelEtaProducer:
    """In-transit journeys whose ``eta_world_time`` arrives (issue 785 owns it).

    An in-transit row with a NULL ETA has no scheduled instant and produces
    nothing; today's arrival package is gated on progress, not on the ETA.
    """

    name: str = "travel_eta"
    boundary_class: BoundaryClass = BoundaryClass.ADJUDICABLE
    precedence: int = 30
    owner_issue: int | None = 785

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Read in-transit rows whose ETA is at or before the target."""

        cur.execute(
            """
            SELECT character_entity_id, origin_place_id, destination_place_id,
                   progress_ratio, eta_world_time
            FROM character_travel_states
            WHERE status = 'in_transit'
              AND eta_world_time IS NOT NULL
              AND eta_world_time <= %s
            ORDER BY eta_world_time, character_entity_id
            """,
            (window.target_world_time,),
        )
        candidates = []
        for row in cur.fetchall():
            entity_id = int(row_get(row, "character_entity_id", 0))
            candidates.append(
                (
                    ("travel", entity_id),
                    row_get(row, "eta_world_time", 4),
                    {
                        "origin_place_id": row_get(row, "origin_place_id", 1),
                        "destination_place_id": row_get(row, "destination_place_id", 2),
                        "progress_ratio": str(row_get(row, "progress_ratio", 3)),
                    },
                )
            )
        return _split(self, window, candidates)


@dataclass(frozen=True)
class _OpenProject:
    id: int
    character_entity_id: int
    project_type: str
    status: str
    stage: str
    stall_count: int
    next_eligible_at_world_time: datetime


def _open_projects(cur: Any) -> list[_OpenProject]:
    """Read every open project; an open row without a due time raises."""

    cur.execute(
        """
        SELECT id, character_entity_id, project_type, status, stage,
               stall_count, next_eligible_at_world_time
        FROM character_project_states
        WHERE status IN ('active', 'paused', 'stalled')
        ORDER BY id
        """
    )
    projects = []
    for row in cur.fetchall():
        project_id = int(row_get(row, "id", 0))
        next_eligible = row_get(row, "next_eligible_at_world_time", 6)
        if next_eligible is None:
            raise ValueError(
                f"Open project {project_id} lacks next_eligible_at_world_time"
            )
        projects.append(
            _OpenProject(
                id=project_id,
                character_entity_id=int(row_get(row, "character_entity_id", 1)),
                project_type=str(row_get(row, "project_type", 2)),
                status=str(row_get(row, "status", 3)),
                stage=str(row_get(row, "stage", 4)),
                stall_count=int(row_get(row, "stall_count", 5)),
                next_eligible_at_world_time=next_eligible,
            )
        )
    return projects


def _project_detail(project: _OpenProject) -> dict[str, Any]:
    return {
        "character_entity_id": project.character_entity_id,
        "project_type": project.project_type,
        "status": project.status,
        "stage": project.stage,
        "stall_count": project.stall_count,
        "next_eligible_at_world_time": project.next_eligible_at_world_time,
    }


class _ProjectProducer:
    """Shared scan for the three project time predicates of ``project_due``.

    Each reports the instant its time predicate turns true for an open
    project, not package eligibility, and simulates no reschedule.
    """

    name: str
    boundary_class: BoundaryClass = BoundaryClass.ADJUDICABLE
    precedence: int
    owner_issue: int | None = None

    def instant(self, project: _OpenProject, policy: ProjectPolicy) -> datetime:
        """Return the instant this producer's predicate turns true."""

        raise NotImplementedError

    def scan(
        self, cur: Any, window: BoundaryWindow, settings: OrrerySettings
    ) -> ProducerScan:
        """Read open projects and partition their instants against the window."""

        policy = coerce_project_policy(settings.projects)
        candidates = [
            (
                ("project", project.id),
                self.instant(project, policy),
                _project_detail(project),
            )
            for project in _open_projects(cur)
        ]
        return _split(self, window, candidates)


class ProjectDueProducer(_ProjectProducer):
    """The instant an open project is due: ``next_eligible_at_world_time``."""

    name = "project_due"
    precedence = 40

    def instant(self, project: _OpenProject, policy: ProjectPolicy) -> datetime:
        """Return the project's due instant."""

        return project.next_eligible_at_world_time


class ProjectNeglectedProducer(_ProjectProducer):
    """The instant a due project has gone one full cadence interval unattended."""

    name = "project_neglected"
    precedence = 41

    def instant(self, project: _OpenProject, policy: ProjectPolicy) -> datetime:
        """Return due time plus ``advance_interval_hours``."""

        return project.next_eligible_at_world_time + timedelta(
            hours=policy.advance_interval_hours
        )


class ProjectAbandonProducer(_ProjectProducer):
    """The instant a due project meets the abandonment predicate.

    A project at or above ``stall_abandon_threshold`` stalls abandons as soon
    as it is due; any other abandons once it is overdue by
    ``abandon_after_stalled_world_hours``.
    """

    name = "project_abandon"
    precedence = 42

    def instant(self, project: _OpenProject, policy: ProjectPolicy) -> datetime:
        """Return the abandonment instant under the current stall count."""

        if project.stall_count >= policy.stall_abandon_threshold:
            return project.next_eligible_at_world_time
        return project.next_eligible_at_world_time + timedelta(
            hours=policy.abandon_after_stalled_world_hours
        )


DEFAULT_PRODUCERS: tuple[BoundaryProducer, ...] = (
    TagExpiryProducer(),
    ClaimPropagationProducer(),
    TravelEtaProducer(),
    ProjectDueProducer(),
    ProjectNeglectedProducer(),
    ProjectAbandonProducer(),
)


def _subject_sort_key(subject_key: tuple[str | int, ...]) -> tuple[Any, ...]:
    """Order mixed str/int subject keys totally: ints before strs per position."""

    return tuple((isinstance(part, str), part) for part in subject_key)


def _crossing_sort_key(crossing: CrossedBoundary) -> tuple[Any, ...]:
    return (
        crossing.occurs_at_world_time,
        crossing.precedence,
        crossing.producer,
        _subject_sort_key(crossing.subject_key),
    )


def enumerate_crossed_boundaries(
    cur: Any,
    window: BoundaryWindow,
    *,
    settings: OrrerySettings,
    producers: Sequence[BoundaryProducer] = DEFAULT_PRODUCERS,
) -> BoundaryEnumeration:
    """Return every producer's crossings inside ``window``, totally ordered.

    Raises ``ValueError`` on duplicate producer names or precedences, on a
    crossing whose producer, class, precedence or owner issue differs from
    the producer that returned it, on a crossing outside the window, and on a
    repeated ``(producer, subject_key, occurs_at_world_time)``. Crossings are
    sorted by ``(occurs_at_world_time, precedence, producer, subject_key)``.
    """

    names = [producer.name for producer in producers]
    if len(set(names)) != len(names):
        raise ValueError(f"Duplicate boundary producer names: {names}")
    precedences = [producer.precedence for producer in producers]
    if len(set(precedences)) != len(precedences):
        raise ValueError(f"Duplicate boundary producer precedences: {precedences}")

    crossings: list[CrossedBoundary] = []
    counts: dict[str, int] = {}
    at_or_before: dict[str, int] = {}
    seen: set[tuple[str, tuple[str | int, ...], datetime]] = set()
    for producer in producers:
        scan = producer.scan(cur, window, settings)
        if scan.at_or_before_previous < 0:
            raise ValueError(
                f"Producer {producer.name!r} reported a negative "
                f"at_or_before_previous count {scan.at_or_before_previous}"
            )
        for crossing in scan.crossings:
            stamped = (
                crossing.producer,
                crossing.boundary_class,
                crossing.precedence,
                crossing.owner_issue,
            )
            declared = (
                producer.name,
                producer.boundary_class,
                producer.precedence,
                producer.owner_issue,
            )
            if stamped != declared:
                raise ValueError(
                    f"Producer {producer.name!r} returned a crossing stamped "
                    f"{stamped!r}; it declares {declared!r}"
                )
            if not window.contains(crossing.occurs_at_world_time):
                raise ValueError(
                    f"Producer {producer.name!r} returned a crossing at "
                    f"{crossing.occurs_at_world_time.isoformat()} outside the "
                    f"window ({window.previous_world_time.isoformat()}, "
                    f"{window.target_world_time.isoformat()}]"
                )
            identity = (
                crossing.producer,
                crossing.subject_key,
                crossing.occurs_at_world_time,
            )
            if identity in seen:
                raise ValueError(
                    f"Producer {producer.name!r} repeated the crossing "
                    f"{crossing.subject_key!r} at "
                    f"{crossing.occurs_at_world_time.isoformat()}"
                )
            seen.add(identity)
            crossings.append(crossing)
        counts[producer.name] = len(scan.crossings)
        at_or_before[producer.name] = scan.at_or_before_previous
    return BoundaryEnumeration(
        window=window,
        crossings=tuple(sorted(crossings, key=_crossing_sort_key)),
        counts=MappingProxyType(counts),
        at_or_before_previous=MappingProxyType(at_or_before),
    )
