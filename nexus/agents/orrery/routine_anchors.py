"""Routine-anchor custody: the shared model, its validator and the ledger writer.

Issue #783 makes a character's home and work anchors authored facts. Every
runtime writer (the Gaia state-update commit, wizard-time Retrograde,
Retrograde maturation, the verified arrival that completes an accepted
relocation, and the offline ladder) sends the same ``RoutineAnchorDelta``,
resolves its names to ids as a ``RoutineAnchorChange``, and applies it through
:func:`apply_routine_anchor_changes_sync` or
:func:`apply_routine_anchor_changes_async`. Custody refuses a malformed change
before any write, records one ``character_routine_anchor_log`` row per change
(migration 145) and writes the anchor row in the caller's transaction.

A missing fact stays missing: an unknown schedule is ``None`` (SQL NULL), never
an empty object, and a clear deletes the anchor, which returns it to unknown.
Name resolution is the caller's job and is not in this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Optional, Sequence, TypeAlias

import psycopg2.extensions
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROUTINE_ANCHOR_TYPES: tuple[str, ...] = ("home", "work")
ROUTINE_MOBILITY_POLICIES: tuple[str, ...] = (
    "fixed_place",
    "zone_resolved",
    "works_from_home",
    "nomadic",
    "none",
)
ROUTINE_ANCHOR_WRITERS: tuple[str, ...] = (
    "skald_state_update",
    "retrograde_expansion",
    "retrograde_maturation",
    "relocation_arrival",
    "offline_ladder",
)

if TYPE_CHECKING:
    RoutineAnchorType: TypeAlias = str
    RoutineMobilityPolicy: TypeAlias = str
    RoutineAnchorWriter: TypeAlias = str
else:
    RoutineAnchorType = Literal[ROUTINE_ANCHOR_TYPES]
    RoutineMobilityPolicy = Literal[ROUTINE_MOBILITY_POLICIES]
    RoutineAnchorWriter = Literal[ROUTINE_ANCHOR_WRITERS]

_CLOCK_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$", re.ASCII)
_HOME_DESTINATION_POLICIES = frozenset({"fixed_place", "zone_resolved"})
_IMAGE_KEYS = ("mobility_policy", "place_id", "zone_id", "schedule")


class RoutineAnchorCustodyError(ValueError):
    """The database state refuses a routine-anchor change; nothing was kept."""


class RoutineSchedule(BaseModel):
    """Authored timing of one routine anchor; unknown timing is ``None``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    always: bool = Field(
        default=False,
        description="True when the routine is due at every hour.",
    )
    weekdays: Optional[list[int]] = Field(
        default=None,
        description="Days the routine applies, 0=Monday through 6=Sunday.",
    )
    start: Optional[str] = Field(
        default=None,
        description="Local start time, HH:MM.",
    )
    end: Optional[str] = Field(
        default=None,
        description=(
            "Local end time, HH:MM; earlier than start for an overnight window."
        ),
    )

    @field_validator("weekdays", mode="before")
    @classmethod
    def _refuse_boolean_weekdays(cls, value: Any) -> Any:
        """Refuse a bool before lax validation turns it into 0 or 1."""

        if isinstance(value, (list, tuple)) and any(
            isinstance(day, bool) for day in value
        ):
            raise ValueError("weekdays holds a bool; a weekday is an integer 0-6")
        return value

    @field_validator("weekdays")
    @classmethod
    def _check_weekdays(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        """Require a non-empty set of weekdays 0-6 and sort it ascending."""

        if value is None:
            return None
        if not value:
            raise ValueError("weekdays is empty; omit weekdays for every day")
        outside = [day for day in value if not 0 <= day <= 6]
        if outside:
            raise ValueError(f"weekdays {outside} are outside 0-6")
        if len(set(value)) != len(value):
            raise ValueError(f"weekdays {value} repeat a day")
        return sorted(value)

    @field_validator("start", "end")
    @classmethod
    def _check_clock_time(cls, value: Optional[str]) -> Optional[str]:
        """Require zero-padded 24-hour HH:MM."""

        if value is not None and _CLOCK_TIME.fullmatch(value) is None:
            raise ValueError(f"{value!r} is not zero-padded HH:MM")
        return value

    @model_validator(mode="after")
    def _check_schedule(self) -> RoutineSchedule:
        """Refuse an always-due schedule with fields, an empty one, or start == end."""

        has_fields = any(
            value is not None for value in (self.weekdays, self.start, self.end)
        )
        if self.always and has_fields:
            raise ValueError("an always-due schedule has no weekdays, start or end")
        if not self.always and not has_fields:
            raise ValueError(
                "the schedule is empty; an unknown schedule is null, not an "
                "empty object"
            )
        if self.start is not None and self.start == self.end:
            raise ValueError(f"start and end are both {self.start}")
        return self

    def as_json(self) -> dict[str, Any]:
        """Return the stored JSON object: ``{"always": true}`` or the known keys."""

        if self.always:
            return {"always": True}
        stored: dict[str, Any] = {}
        if self.weekdays is not None:
            stored["weekdays"] = sorted(self.weekdays)
        if self.start is not None:
            stored["start"] = self.start
        if self.end is not None:
            stored["end"] = self.end
        return stored


def _check_anchor_shape(
    *,
    anchor_type: str,
    mobility_policy: Optional[str],
    has_place: bool,
    has_zone: bool,
    has_schedule: bool,
    clear: bool,
) -> None:
    """Apply the anchor shape rules shared by the wire and the resolved model."""

    if clear:
        if mobility_policy is not None or has_place or has_zone or has_schedule:
            raise ValueError("a clear has no mobility_policy, place, zone or schedule")
        return
    if mobility_policy is None:
        raise ValueError("an upsert needs a mobility_policy")
    if mobility_policy == "fixed_place":
        if not has_place or has_zone:
            raise ValueError("fixed_place needs a place and no zone")
    elif mobility_policy == "zone_resolved":
        if not has_zone or has_place:
            raise ValueError("zone_resolved needs a zone and no place")
    elif mobility_policy == "works_from_home":
        if anchor_type != "work":
            raise ValueError("works_from_home is a work anchor policy")
        if has_place or has_zone:
            raise ValueError("works_from_home has no place or zone")
    elif has_place or has_zone:
        raise ValueError(f"{mobility_policy} has no place or zone")
    if mobility_policy == "none" and has_schedule:
        raise ValueError("none records an authored absence and has no schedule")


class RoutineAnchorDelta(BaseModel):
    """One sparse routine-anchor change as a writer names it on the wire."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    character: str = Field(min_length=1, description="Canonical character name.")
    anchor_type: RoutineAnchorType = Field(description="Which routine anchor changes.")
    mobility_policy: Optional[RoutineMobilityPolicy] = Field(
        default=None,
        description=(
            "How the routine moves the character; none records an authored absence."
        ),
    )
    place: Optional[str] = Field(
        default=None,
        description="Canonical place name for fixed_place; null otherwise.",
    )
    zone: Optional[str] = Field(
        default=None,
        description="Canonical zone name for zone_resolved; null otherwise.",
    )
    schedule: Optional[RoutineSchedule] = Field(
        default=None,
        description="Authored timing; null when the timing is unknown.",
    )
    clear: bool = Field(default=False, description="True removes this anchor.")

    @model_validator(mode="after")
    def _check_shape(self) -> RoutineAnchorDelta:
        """Refuse a delta whose policy, place, zone and schedule disagree."""

        _check_anchor_shape(
            anchor_type=self.anchor_type,
            mobility_policy=self.mobility_policy,
            has_place=self.place is not None,
            has_zone=self.zone is not None,
            has_schedule=self.schedule is not None,
            clear=self.clear,
        )
        return self


class RoutineAnchorChange(BaseModel):
    """One routine-anchor change with ids resolved, as custody applies it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    character_entity_id: int
    anchor_type: RoutineAnchorType = Field(description="Which routine anchor changes.")
    mobility_policy: Optional[RoutineMobilityPolicy] = Field(
        description=(
            "How the routine moves the character; none records an authored absence."
        ),
    )
    place_id: Optional[int]
    zone_id: Optional[int]
    schedule: Optional[RoutineSchedule] = Field(
        description="Authored timing; null when the timing is unknown.",
    )
    clear: bool = Field(description="True removes this anchor.")

    @model_validator(mode="after")
    def _check_shape(self) -> RoutineAnchorChange:
        """Refuse a change whose policy, place, zone and schedule disagree."""

        _check_anchor_shape(
            anchor_type=self.anchor_type,
            mobility_policy=self.mobility_policy,
            has_place=self.place_id is not None,
            has_zone=self.zone_id is not None,
            has_schedule=self.schedule is not None,
            clear=self.clear,
        )
        return self

    @classmethod
    def from_delta(
        cls,
        delta: RoutineAnchorDelta,
        *,
        character_entity_id: int,
        place_id: Optional[int],
        zone_id: Optional[int],
    ) -> RoutineAnchorChange:
        """Carry ``delta`` over to resolved ids; each id must match its name."""

        if (place_id is None) != (delta.place is None):
            raise ValueError(
                f"place_id={place_id!r} does not match place={delta.place!r}: "
                "a named place needs its id and an unnamed one takes none"
            )
        if (zone_id is None) != (delta.zone is None):
            raise ValueError(
                f"zone_id={zone_id!r} does not match zone={delta.zone!r}: "
                "a named zone needs its id and an unnamed one takes none"
            )
        return cls(
            character_entity_id=character_entity_id,
            anchor_type=delta.anchor_type,
            mobility_policy=delta.mobility_policy,
            place_id=place_id,
            zone_id=zone_id,
            schedule=delta.schedule,
            clear=delta.clear,
        )

    def after_image(self) -> dict[str, Any]:
        """Return the anchor this upsert writes, in the ledger image shape."""

        return {
            "mobility_policy": self.mobility_policy,
            "place_id": self.place_id,
            "zone_id": self.zone_id,
            "schedule": None if self.schedule is None else self.schedule.as_json(),
        }


# ---------------------------------------------------------------------------
# Custody: pure planning shared by both twins
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PlannedWrite:
    """One ledger row and the anchor write it records."""

    change: RoutineAnchorChange
    operation: str
    chunk_sequence: int
    before_image: Optional[dict[str, Any]]
    after_image: Optional[dict[str, Any]]


def _refusal(index: int, change: RoutineAnchorChange, rule: str) -> str:
    return (
        f"Routine anchor change {index} (character_entity_id="
        f"{change.character_entity_id}, anchor_type={change.anchor_type}): {rule}"
    )


def _require_changes(changes: Sequence[RoutineAnchorChange]) -> tuple[Any, ...]:
    batch = tuple(changes)
    for index, change in enumerate(batch):
        if not isinstance(change, RoutineAnchorChange):
            raise TypeError(
                f"Routine anchor change {index} is {type(change).__name__}, "
                "not RoutineAnchorChange"
            )
    return batch


def _require_writer(writer_kind: str) -> None:
    if writer_kind not in ROUTINE_ANCHOR_WRITERS:
        raise RoutineAnchorCustodyError(
            f"Routine anchor custody refuses writer_kind={writer_kind!r}; "
            f"expected one of {list(ROUTINE_ANCHOR_WRITERS)}"
        )


def _require_world_time(source_chunk_id: int, world_time: Any) -> datetime:
    if not isinstance(world_time, datetime):
        raise RoutineAnchorCustodyError(
            "Routine anchor custody requires chunk_metadata.world_time for "
            f"source_chunk_id={source_chunk_id}; found {world_time!r}"
        )
    return world_time


def _refuse_duplicate_pairs(batch: Sequence[RoutineAnchorChange]) -> None:
    seen: dict[tuple[int, str], int] = {}
    for index, change in enumerate(batch):
        pair = (change.character_entity_id, change.anchor_type)
        if pair in seen:
            raise RoutineAnchorCustodyError(
                _refusal(
                    index,
                    change,
                    f"the batch already changes this anchor at change {seen[pair]}",
                )
            )
        seen[pair] = index


def _refuse_unresolved_references(
    batch: Sequence[RoutineAnchorChange],
    *,
    entity_kinds: dict[int, str],
    place_ids: set[int],
    zone_ids: set[int],
) -> None:
    for index, change in enumerate(batch):
        kind = entity_kinds.get(change.character_entity_id)
        if kind is None:
            raise RoutineAnchorCustodyError(
                _refusal(index, change, "the entity does not exist")
            )
        if kind != "character":
            raise RoutineAnchorCustodyError(
                _refusal(index, change, f"the entity is a {kind}, not a character")
            )
        if change.place_id is not None and change.place_id not in place_ids:
            raise RoutineAnchorCustodyError(
                _refusal(index, change, f"places.id={change.place_id} does not exist")
            )
        if change.zone_id is not None and change.zone_id not in zone_ids:
            raise RoutineAnchorCustodyError(
                _refusal(index, change, f"zones.id={change.zone_id} does not exist")
            )


def _stored_image(
    mobility_policy: str,
    place_id: Optional[int],
    zone_id: Optional[int],
    schedule_text: Optional[str],
) -> dict[str, Any]:
    """Return a locked anchor row as a ledger image."""

    return {
        "mobility_policy": mobility_policy,
        "place_id": None if place_id is None else int(place_id),
        "zone_id": None if zone_id is None else int(zone_id),
        "schedule": None if schedule_text is None else json.loads(schedule_text),
    }


def _plan_writes(
    batch: Sequence[RoutineAnchorChange],
    *,
    existing: dict[tuple[int, str], dict[str, Any]],
    last_sequence: int,
) -> list[_PlannedWrite]:
    """Refuse a clear of an absent anchor, then number the ledger rows."""

    for index, change in enumerate(batch):
        if change.clear and (change.character_entity_id, change.anchor_type) not in (
            existing
        ):
            raise RoutineAnchorCustodyError(
                _refusal(index, change, "a clear needs an existing anchor")
            )
    plan: list[_PlannedWrite] = []
    for offset, change in enumerate(batch, start=1):
        before = existing.get((change.character_entity_id, change.anchor_type))
        plan.append(
            _PlannedWrite(
                change=change,
                operation="clear" if change.clear else "upsert",
                chunk_sequence=last_sequence + offset,
                before_image=before,
                after_image=None if change.clear else change.after_image(),
            )
        )
    return plan


def _refuse_homeless_works_from_home(
    batch: Sequence[RoutineAnchorChange],
    anchors: dict[tuple[int, str], str],
) -> None:
    """Refuse a works_from_home work anchor without a home destination."""

    first_index: dict[int, int] = {}
    for index, change in enumerate(batch):
        first_index.setdefault(change.character_entity_id, index)
    for entity_id, index in first_index.items():
        if anchors.get((entity_id, "work")) != "works_from_home":
            continue
        home_policy = anchors.get((entity_id, "home"))
        if home_policy in _HOME_DESTINATION_POLICIES:
            continue
        cited = next(
            (
                position
                for position, change in enumerate(batch)
                if change.character_entity_id == entity_id
                and change.anchor_type == "work"
            ),
            index,
        )
        raise RoutineAnchorCustodyError(
            _refusal(
                cited,
                batch[cited],
                "a works_from_home work anchor needs a home anchor with "
                f"fixed_place or zone_resolved; the home anchor is {home_policy!r}",
            )
        )


def _image_text(image: Optional[dict[str, Any]]) -> Optional[str]:
    if image is None:
        return None
    if tuple(image) != _IMAGE_KEYS:
        raise ValueError(
            f"Routine anchor image keys {list(image)} are not {list(_IMAGE_KEYS)}"
        )
    return json.dumps(image)


def _schedule_text(change: RoutineAnchorChange) -> Optional[str]:
    if change.schedule is None:
        return None
    return json.dumps(change.schedule.as_json())


# ---------------------------------------------------------------------------
# Custody: psycopg2
# ---------------------------------------------------------------------------

_SYNC_WORLD_TIME_SQL = "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s"
_SYNC_ENTITY_KINDS_SQL = "SELECT id, kind::text FROM entities WHERE id = ANY(%s)"
_SYNC_PLACES_SQL = "SELECT id FROM places WHERE id = ANY(%s)"
_SYNC_ZONES_SQL = "SELECT id FROM zones WHERE id = ANY(%s)"
_SYNC_LOCK_ANCHORS_SQL = """
    SELECT character_entity_id, anchor_type::text, mobility_policy::text,
           place_id, zone_id, schedule::text
    FROM character_routine_anchors
    WHERE character_entity_id = ANY(%s)
    ORDER BY character_entity_id, anchor_type
    FOR UPDATE
"""
_SYNC_LAST_SEQUENCE_SQL = """
    SELECT COALESCE(MAX(chunk_sequence), 0)
    FROM character_routine_anchor_log
    WHERE source_chunk_id = %s
"""
_SYNC_INSERT_LOG_SQL = """
    INSERT INTO character_routine_anchor_log (
        character_entity_id, anchor_type, operation, writer_kind,
        source_chunk_id, chunk_sequence, source_event_id, world_time,
        before_image, after_image
    ) VALUES (
        %s, %s::orrery_routine_anchor_type, %s, %s::orrery_routine_anchor_writer,
        %s, %s, %s, %s, %s::jsonb, %s::jsonb
    )
    RETURNING id
"""
_SYNC_UPSERT_SQL = """
    INSERT INTO character_routine_anchors (
        character_entity_id, anchor_type, mobility_policy, place_id, zone_id,
        schedule, source, last_log_id, updated_at
    ) VALUES (
        %s, %s::orrery_routine_anchor_type, %s::orrery_routine_mobility_policy,
        %s, %s, %s::jsonb, %s, %s, now()
    )
    ON CONFLICT (character_entity_id, anchor_type) DO UPDATE SET
        mobility_policy = EXCLUDED.mobility_policy,
        place_id = EXCLUDED.place_id,
        zone_id = EXCLUDED.zone_id,
        schedule = EXCLUDED.schedule,
        source = EXCLUDED.source,
        last_log_id = EXCLUDED.last_log_id,
        updated_at = now()
"""
_SYNC_DELETE_SQL = """
    DELETE FROM character_routine_anchors
    WHERE character_entity_id = %s AND anchor_type = %s::orrery_routine_anchor_type
"""
_SYNC_POLICIES_SQL = """
    SELECT character_entity_id, anchor_type::text, mobility_policy::text
    FROM character_routine_anchors
    WHERE character_entity_id = ANY(%s)
"""


def apply_routine_anchor_changes_sync(
    cur: Any,
    changes: Sequence[RoutineAnchorChange],
    *,
    writer_kind: str,
    source_chunk_id: int,
    source_event_id: Optional[int] = None,
) -> list[int]:
    """Apply ``changes`` through custody on psycopg2; return the ledger ids.

    Runs in the caller's transaction on its own plain cursor and never commits
    or rolls back. Every refusal raises ``RoutineAnchorCustodyError`` before
    any write, except the final works_from_home home check, which raises after
    the writes so the caller's rollback discards them.
    """

    conn = cur.connection
    if conn.autocommit:
        raise RoutineAnchorCustodyError(
            "Routine anchor custody runs in the caller's transaction; the "
            "psycopg2 connection is in autocommit mode"
        )
    batch = _require_changes(changes)
    _require_writer(writer_kind)
    with conn.cursor(cursor_factory=psycopg2.extensions.cursor) as own:
        own.execute(_SYNC_WORLD_TIME_SQL, (source_chunk_id,))
        row = own.fetchone()
        world_time = _require_world_time(
            source_chunk_id, None if row is None else row[0]
        )
        _refuse_duplicate_pairs(batch)
        entity_ids = sorted({change.character_entity_id for change in batch})
        own.execute(_SYNC_ENTITY_KINDS_SQL, (entity_ids,))
        entity_kinds = {int(eid): str(kind) for eid, kind in own.fetchall()}
        own.execute(
            _SYNC_PLACES_SQL,
            (sorted({c.place_id for c in batch if c.place_id is not None}),),
        )
        place_ids = {int(pid) for (pid,) in own.fetchall()}
        own.execute(
            _SYNC_ZONES_SQL,
            (sorted({c.zone_id for c in batch if c.zone_id is not None}),),
        )
        zone_ids = {int(zid) for (zid,) in own.fetchall()}
        _refuse_unresolved_references(
            batch, entity_kinds=entity_kinds, place_ids=place_ids, zone_ids=zone_ids
        )
        own.execute(_SYNC_LOCK_ANCHORS_SQL, (entity_ids,))
        existing = {
            (int(eid), str(anchor_type)): _stored_image(policy, pid, zid, schedule)
            for eid, anchor_type, policy, pid, zid, schedule in own.fetchall()
        }
        own.execute(_SYNC_LAST_SEQUENCE_SQL, (source_chunk_id,))
        last_sequence = int(own.fetchone()[0])
        plan = _plan_writes(batch, existing=existing, last_sequence=last_sequence)

        log_ids: list[int] = []
        for write in plan:
            change = write.change
            own.execute(
                _SYNC_INSERT_LOG_SQL,
                (
                    change.character_entity_id,
                    change.anchor_type,
                    write.operation,
                    writer_kind,
                    source_chunk_id,
                    write.chunk_sequence,
                    source_event_id,
                    world_time,
                    _image_text(write.before_image),
                    _image_text(write.after_image),
                ),
            )
            log_id = int(own.fetchone()[0])
            if write.operation == "upsert":
                own.execute(
                    _SYNC_UPSERT_SQL,
                    (
                        change.character_entity_id,
                        change.anchor_type,
                        change.mobility_policy,
                        change.place_id,
                        change.zone_id,
                        _schedule_text(change),
                        writer_kind,
                        log_id,
                    ),
                )
            else:
                own.execute(
                    _SYNC_DELETE_SQL,
                    (change.character_entity_id, change.anchor_type),
                )
            if own.rowcount != 1:
                raise RoutineAnchorCustodyError(
                    f"Routine anchor {write.operation} of "
                    f"(character_entity_id={change.character_entity_id}, "
                    f"anchor_type={change.anchor_type}) touched {own.rowcount} rows"
                )
            log_ids.append(log_id)

        own.execute(_SYNC_POLICIES_SQL, (entity_ids,))
        policies = {
            (int(eid), str(anchor_type)): str(policy)
            for eid, anchor_type, policy in own.fetchall()
        }
        _refuse_homeless_works_from_home(batch, policies)
    return log_ids


# ---------------------------------------------------------------------------
# Custody: asyncpg
# ---------------------------------------------------------------------------

_ASYNC_WORLD_TIME_SQL = "SELECT world_time FROM chunk_metadata WHERE chunk_id = $1"
_ASYNC_ENTITY_KINDS_SQL = (
    "SELECT id, kind::text AS kind FROM entities WHERE id = ANY($1::bigint[])"
)
_ASYNC_PLACES_SQL = "SELECT id FROM places WHERE id = ANY($1::bigint[])"
_ASYNC_ZONES_SQL = "SELECT id FROM zones WHERE id = ANY($1::bigint[])"
_ASYNC_LOCK_ANCHORS_SQL = """
    SELECT character_entity_id, anchor_type::text AS anchor_type,
           mobility_policy::text AS mobility_policy,
           place_id, zone_id, schedule::text AS schedule
    FROM character_routine_anchors
    WHERE character_entity_id = ANY($1::bigint[])
    ORDER BY character_entity_id, anchor_type
    FOR UPDATE
"""
_ASYNC_LAST_SEQUENCE_SQL = """
    SELECT COALESCE(MAX(chunk_sequence), 0)
    FROM character_routine_anchor_log
    WHERE source_chunk_id = $1
"""
_ASYNC_INSERT_LOG_SQL = """
    INSERT INTO character_routine_anchor_log (
        character_entity_id, anchor_type, operation, writer_kind,
        source_chunk_id, chunk_sequence, source_event_id, world_time,
        before_image, after_image
    ) VALUES (
        $1, $2::orrery_routine_anchor_type, $3, $4::orrery_routine_anchor_writer,
        $5, $6, $7, $8, $9::jsonb, $10::jsonb
    )
    RETURNING id
"""
_ASYNC_UPSERT_SQL = """
    INSERT INTO character_routine_anchors (
        character_entity_id, anchor_type, mobility_policy, place_id, zone_id,
        schedule, source, last_log_id, updated_at
    ) VALUES (
        $1, $2::orrery_routine_anchor_type, $3::orrery_routine_mobility_policy,
        $4, $5, $6::jsonb, $7, $8, now()
    )
    ON CONFLICT (character_entity_id, anchor_type) DO UPDATE SET
        mobility_policy = EXCLUDED.mobility_policy,
        place_id = EXCLUDED.place_id,
        zone_id = EXCLUDED.zone_id,
        schedule = EXCLUDED.schedule,
        source = EXCLUDED.source,
        last_log_id = EXCLUDED.last_log_id,
        updated_at = now()
"""
_ASYNC_DELETE_SQL = """
    DELETE FROM character_routine_anchors
    WHERE character_entity_id = $1 AND anchor_type = $2::orrery_routine_anchor_type
"""
_ASYNC_POLICIES_SQL = """
    SELECT character_entity_id, anchor_type::text AS anchor_type,
           mobility_policy::text AS mobility_policy
    FROM character_routine_anchors
    WHERE character_entity_id = ANY($1::bigint[])
"""


def _command_rowcount(status: str) -> int:
    """Return the row count of an asyncpg command status such as ``DELETE 1``."""

    return int(status.rsplit(" ", 1)[-1])


async def apply_routine_anchor_changes_async(
    conn: Any,
    changes: Sequence[RoutineAnchorChange],
    *,
    writer_kind: str,
    source_chunk_id: int,
    source_event_id: Optional[int] = None,
) -> list[int]:
    """Async twin of :func:`apply_routine_anchor_changes_sync` on asyncpg.

    Requires an open ``conn.transaction()``; never commits or rolls back.
    """

    if not conn.is_in_transaction():
        raise RoutineAnchorCustodyError(
            "Routine anchor custody runs in the caller's transaction; the "
            "asyncpg connection is not in a transaction"
        )
    batch = _require_changes(changes)
    _require_writer(writer_kind)
    world_time = _require_world_time(
        source_chunk_id, await conn.fetchval(_ASYNC_WORLD_TIME_SQL, source_chunk_id)
    )
    _refuse_duplicate_pairs(batch)
    entity_ids = sorted({change.character_entity_id for change in batch})
    entity_kinds = {
        int(row["id"]): str(row["kind"])
        for row in await conn.fetch(_ASYNC_ENTITY_KINDS_SQL, entity_ids)
    }
    place_ids = {
        int(row["id"])
        for row in await conn.fetch(
            _ASYNC_PLACES_SQL,
            sorted({c.place_id for c in batch if c.place_id is not None}),
        )
    }
    zone_ids = {
        int(row["id"])
        for row in await conn.fetch(
            _ASYNC_ZONES_SQL,
            sorted({c.zone_id for c in batch if c.zone_id is not None}),
        )
    }
    _refuse_unresolved_references(
        batch, entity_kinds=entity_kinds, place_ids=place_ids, zone_ids=zone_ids
    )
    existing = {
        (int(row["character_entity_id"]), str(row["anchor_type"])): _stored_image(
            row["mobility_policy"], row["place_id"], row["zone_id"], row["schedule"]
        )
        for row in await conn.fetch(_ASYNC_LOCK_ANCHORS_SQL, entity_ids)
    }
    last_sequence = int(await conn.fetchval(_ASYNC_LAST_SEQUENCE_SQL, source_chunk_id))
    plan = _plan_writes(batch, existing=existing, last_sequence=last_sequence)

    log_ids: list[int] = []
    for write in plan:
        change = write.change
        log_id = int(
            await conn.fetchval(
                _ASYNC_INSERT_LOG_SQL,
                change.character_entity_id,
                change.anchor_type,
                write.operation,
                writer_kind,
                source_chunk_id,
                write.chunk_sequence,
                source_event_id,
                world_time,
                _image_text(write.before_image),
                _image_text(write.after_image),
            )
        )
        if write.operation == "upsert":
            status = await conn.execute(
                _ASYNC_UPSERT_SQL,
                change.character_entity_id,
                change.anchor_type,
                change.mobility_policy,
                change.place_id,
                change.zone_id,
                _schedule_text(change),
                writer_kind,
                log_id,
            )
        else:
            status = await conn.execute(
                _ASYNC_DELETE_SQL, change.character_entity_id, change.anchor_type
            )
        touched = _command_rowcount(status)
        if touched != 1:
            raise RoutineAnchorCustodyError(
                f"Routine anchor {write.operation} of "
                f"(character_entity_id={change.character_entity_id}, "
                f"anchor_type={change.anchor_type}) touched {touched} rows"
            )
        log_ids.append(log_id)

    policies = {
        (int(row["character_entity_id"]), str(row["anchor_type"])): str(
            row["mobility_policy"]
        )
        for row in await conn.fetch(_ASYNC_POLICIES_SQL, entity_ids)
    }
    _refuse_homeless_works_from_home(batch, policies)
    return log_ids
