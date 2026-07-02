"""What-if overrides over a hydrated Orrery :class:`WorldState`.

The audit dashboard's sandbox mode ("what-if") re-resolves a tick against a
copy of the hydrated world state with developer edits applied — toggle a tag,
set a need, move an actor, inject a recent event — without any database
writes. :class:`WorldState` is a frozen dataclass, so the copy-with-edits is
a :func:`dataclasses.replace` over rebuilt mappings.

Scope: overrides edit **world state only**. Actor roster and binding
composition are derived from SQL (`compose_actor_bindings` /
`compose_actor_target_bindings`), not from ``WorldState``, so a moved actor
changes how location predicates evaluate but does not recompose pairs or the
roster. The payload echo carries this scope marker so the UI's honesty label
can render it.

Validation split: this module performs the *state-dependent* checks (a tag
toggle must actually change state; need types must be real needs). Vocabulary
and existence checks that require the database — tag/pair-tag/event-type
vocabularies, entity and place ids — belong to the caller
(:func:`nexus.agents.orrery.audit.explain_dry_run`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Optional, Tuple

from nexus.agents.orrery.needs import NEED_SEVERITY_PREFIX
from nexus.agents.orrery.substrate import EventRecord, WorldState

OVERRIDE_SCOPE = "world_state_only"

_TAG_OPS = ("add", "remove")


class OverrideValidationError(ValueError):
    """A what-if override is invalid: unknown vocabulary or a no-op toggle.

    Distinct from plain ``ValueError`` so the API layer can map caller
    mistakes to 400 without swallowing genuine server-side failures.
    """


@dataclass(frozen=True, slots=True)
class TagOverride:
    """Toggle a durable or ephemeral tag on one entity."""

    entity_id: int
    tag: str
    op: str
    ephemeral: bool = False


@dataclass(frozen=True, slots=True)
class PairTagOverride:
    """Toggle a directed pair tag between two entities."""

    subject_entity_id: int
    object_entity_id: int
    tag: str
    op: str


@dataclass(frozen=True, slots=True)
class NeedOverride:
    """Set one entity's debt score for one need type."""

    entity_id: int
    need_type: str
    debt_score: float


@dataclass(frozen=True, slots=True)
class LocationOverride:
    """Move one entity to a place."""

    entity_id: int
    place_id: int


@dataclass(frozen=True, slots=True)
class EventOverride:
    """Inject a recent event, ``ticks_ago`` ticks before the current tick."""

    event_type: str
    actor_entity_id: Optional[int] = None
    target_entity_id: Optional[int] = None
    location_id: Optional[int] = None
    ticks_ago: int = 0
    changed_fields: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorldStateOverrides:
    """The full override set for one what-if re-resolve."""

    tags: Tuple[TagOverride, ...] = ()
    pair_tags: Tuple[PairTagOverride, ...] = ()
    needs: Tuple[NeedOverride, ...] = ()
    locations: Tuple[LocationOverride, ...] = ()
    events: Tuple[EventOverride, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (
            self.tags or self.pair_tags or self.needs or self.locations or self.events
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable echo of the applied overrides, with scope label."""

        return {
            "scope": OVERRIDE_SCOPE,
            "tags": [asdict(item) for item in self.tags],
            "pair_tags": [asdict(item) for item in self.pair_tags],
            "needs": [asdict(item) for item in self.needs],
            "locations": [asdict(item) for item in self.locations],
            "events": [
                {**asdict(item), "changed_fields": list(item.changed_fields)}
                for item in self.events
            ],
        }


def _toggle(members: set[str], tag: str, op: str, *, subject: str) -> None:
    if op not in _TAG_OPS:
        raise OverrideValidationError(
            f"Unknown tag override op {op!r} for {subject}; expected one of {_TAG_OPS}"
        )
    if op == "add":
        if tag in members:
            raise OverrideValidationError(
                f"Override asked to add tag {tag!r} to {subject}, "
                "which already carries it — the override would be a no-op"
            )
        members.add(tag)
    else:
        if tag not in members:
            raise OverrideValidationError(
                f"Override asked to remove tag {tag!r} from {subject}, "
                "which does not carry it — the override would be a no-op"
            )
        members.remove(tag)


def apply_overrides(state: WorldState, overrides: WorldStateOverrides) -> WorldState:
    """Return a copy of ``state`` with the override set applied.

    Tag and pair-tag toggles are state-dependent and raise
    :class:`OverrideValidationError` when they would be no-ops; need,
    location, and event overrides are set/append operations. Never mutates
    ``state``.
    """

    changes: dict[str, Any] = {}

    if overrides.tags:
        durable = {key: set(value) for key, value in state.tags.items()}
        ephemeral = {key: set(value) for key, value in state.ephemeral_tags.items()}
        for item in overrides.tags:
            target = ephemeral if item.ephemeral else durable
            layer = "ephemeral" if item.ephemeral else "durable"
            _toggle(
                target.setdefault(item.entity_id, set()),
                item.tag,
                item.op,
                subject=f"entity {item.entity_id} ({layer})",
            )
        changes["tags"] = {key: frozenset(value) for key, value in durable.items()}
        changes["ephemeral_tags"] = {
            key: frozenset(value) for key, value in ephemeral.items()
        }

    if overrides.pair_tags:
        pair_tags = {key: set(value) for key, value in state.pair_tags.items()}
        for pair in overrides.pair_tags:
            key = (pair.subject_entity_id, pair.object_entity_id)
            _toggle(
                pair_tags.setdefault(key, set()),
                pair.tag,
                pair.op,
                subject=f"pair {key[0]}->{key[1]}",
            )
        changes["pair_tags"] = {
            key: frozenset(value) for key, value in pair_tags.items()
        }

    if overrides.needs:
        need_debt_scores = dict(state.need_debt_scores)
        for need in overrides.needs:
            if need.need_type not in NEED_SEVERITY_PREFIX:
                raise OverrideValidationError(
                    f"Unknown need type {need.need_type!r} in override; "
                    f"expected one of {sorted(NEED_SEVERITY_PREFIX)}"
                )
            if need.debt_score < 0:
                raise OverrideValidationError(
                    f"Need debt override for entity {need.entity_id} must be "
                    f">= 0, got {need.debt_score}"
                )
            need_debt_scores[(need.entity_id, need.need_type)] = need.debt_score
        changes["need_debt_scores"] = need_debt_scores

    if overrides.locations:
        locations = dict(state.locations)
        for move in overrides.locations:
            locations[move.entity_id] = move.place_id
        changes["locations"] = locations

    if overrides.events:
        injected = []
        for event in overrides.events:
            if event.ticks_ago < 0:
                raise OverrideValidationError(
                    f"Event override ticks_ago must be >= 0, got {event.ticks_ago}"
                )
            injected.append(
                EventRecord(
                    event_type=event.event_type,
                    tick=state.current_tick - event.ticks_ago,
                    actor_entity_id=event.actor_entity_id,
                    target_entity_id=event.target_entity_id,
                    location_id=event.location_id,
                    changed_fields=event.changed_fields,
                )
            )
        changes["recent_events"] = state.recent_events + tuple(injected)

    if not changes:
        return state
    return replace(state, **changes)
