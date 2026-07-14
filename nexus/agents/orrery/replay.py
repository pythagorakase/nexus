"""Replay consumer for the reconstruction-sufficiency layer (issue #426).

Reconstructs the mutable world-state surface at an arbitrary chunk N from
the artifacts the write side (migrations 064/065, ``reconstruction.py``)
produces. Sections and their replay sources:

- ``characters`` / ``places`` scalars — forward from the base checkpoint:
  ``state_delta_log`` rows (Skald, applied first within a chunk), then
  ``orrery_resolutions.state_delta`` keys ``character.current_activity``
  and ``travel.arrive`` (whose location write is *not* Skald-ledgered).
- ``entity_tags`` / ``entity_pair_tags`` — forward from the checkpoint via
  the provenance tables alone: bestowals keyed by ``source_chunk_id``,
  clearances by ``tag_clearance_log.source_chunk_id``. The tag keys inside
  ``orrery_resolutions.state_delta`` are deliberately ignored: the same
  commit already wrote them to the provenance tables (double-entry), and
  ``need.fulfill``'s derived severity tags exist *only* in provenance.
- the three relationship tables — backward from the *current* rows,
  unwinding ``relationship_versions`` pre-images (``id DESC``), then
  dropping rows whose ``created_at`` postdates chunk N (INSERTs never fire
  the versioning triggers; wall-clock correlation is the only insert-time
  evidence).
- ``character_need_states`` — forward, re-executing ``need.fulfill``
  through the same ``effective_debt_score`` authority production used.
  Exact only while ``[orrery.sunhelm]`` tuning matches its value at the
  original commit; the tuning is not versioned. The un-ledgered
  need-applicability trigger (migration 057: entity_tags changes insert/
  delete need rows and clear severity tags) is mirrored after tag replay:
  row presence follows the final tag set, and rows whose applicability
  toggled off-and-back inside the window are reset to the trigger's
  fresh-insert shape (detected chronologically from chunk-keyed
  immunity-tag events).
- ``character_travel_states`` — forward for explicit payloads;
  ``travel.start`` resolves destinations and routes from live state at
  commit time, so windows containing travel deltas are approximate.
- ``character_project_states`` — forward from the five ``project.*``
  transitions. Every transition carries the exact applied project projection,
  so cadence and applier-derived values are independent of current tuning;
  project.complete also replays its explicit-destination travel.start handoff.
- ``character_routine_anchors`` — checkpoint pass-through (no runtime
  writer; offline seed scripts mutate it invisibly between checkpoints).

Known undetectable gaps: (1) reapplication policies ``replace`` and
``extend_expiry`` overwrite a live tag row's ``source_chunk_id`` in place
with no history row — a tag bestowed inside the window and re-applied
after N reads as bestowed later and drops out of the reconstruction;
(2) a manual checkpoint taken long after its chunk committed snapshots
capture-time state, but replay correlates wall-clock evidence against the
chunk's created_at — offline edits in that gap blur the boundary.

``verify_checkpoints_sync`` turns every stored checkpoint pair into a
regression oracle: reconstruct forward from checkpoint A to checkpoint B's
chunk and diff against B's stored document. Any writer that ships
un-ledgered shows up as drift here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from nexus.agents.orrery.needs import (
    NEED_IMMUNITY_TAGS,
    NEED_TYPES,
    effective_debt_score,
    load_need_tuning,
    need_applies_to_tags,
    severity_tags_for_need,
)
from nexus.agents.orrery.reconstruction import CHECKPOINT_SECTIONS
from nexus.agents.orrery.substrate import ProjectPolicy, coerce_project_policy

# Composite natural keys, verbatim column order (faction_relationships
# enforces faction1_id < faction2_id; character_relationships only c1 <> c2
# — never re-canonicalize when re-inserting delete pre-images).
RELATIONSHIP_KEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "character_relationships": ("character1_id", "character2_id"),
    "faction_character_relationships": ("faction_id", "character_id"),
    "faction_relationships": ("faction1_id", "faction2_id"),
}

# Wall-clock columns the DB stamps with now() at write time; excluded from
# verify comparison because replay cannot reproduce them by design.
VOLATILE_COLUMNS: dict[str, frozenset[str]] = {
    "character_need_states": frozenset({"created_at", "updated_at"}),
    "character_travel_states": frozenset({"created_at", "updated_at"}),
    "character_project_states": frozenset({"id", "created_at", "updated_at"}),
}

SKALD_SCALAR_FIELDS = frozenset(
    {
        "characters.emotional_state",
        "characters.current_activity",
        "characters.current_location",
        "places.current_status",
    }
)

# Delta keys whose effects live entirely in the tag provenance tables;
# replaying them here would double-count.
TAG_DELTA_KEYS = frozenset(
    {
        "entity_tags.add",
        "entity_tags.remove",
        "entity_tags_target.add",
        "entity_tags_target.remove",
        "entity_pair_tags.add_outbound",
        "entity_pair_tags.clear_outbound",
        "entity_pair_tags_target.clear_inbound",
    }
)

REPLAYED_DELTA_KEYS = frozenset(
    {
        # Append-only producer ledger metadata. Epistemics rows reconstruct
        # themselves from their provenance and are intentionally not replayed.
        "applied",
        "character.current_activity",
        "need.fulfill",
        "travel.start",
        "travel.advance",
        "travel.delay",
        "travel.arrive",
        "project.start",
        "project.advance",
        "project.stall",
        "project.abandon",
        "project.complete",
    }
)

# Mirrors the applier default at events.py _apply_travel_advance_sync.
TRAVEL_ADVANCE_DEFAULT_DELTA = 0.35


def _pg_round(value: float, places: int) -> float:
    """Round the way Postgres numeric(_, places) storage does — half away
    from zero, not Python's banker's rounding."""

    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


@dataclass
class ReplayResult:
    """A reconstructed state document plus its honesty report."""

    target_chunk_id: int
    base_checkpoint_id: int
    base_checkpoint_chunk_id: int
    state: dict[str, list[dict[str, Any]]]
    notes: dict[str, list[str]] = field(default_factory=dict)
    approximate_sections: set[str] = field(default_factory=set)
    # (section, row_key, column) triples replay could not reproduce
    # (e.g. timestamps from a NULL-world-time tick); verify skips these.
    unreproducible: set[tuple[str, str, str]] = field(default_factory=set)
    # (section, row_key) pairs whose PRESENCE at the target is undecidable:
    # Step 8.6 of the commit (maturation stubs + tag hints) runs after the
    # Step 8.55 checkpoint inside one transaction, and now() is constant
    # across it, so wall-clock bounds cannot split "before capture" from
    # "after capture" at the target chunk. Verify skips presence mismatches
    # on these rows instead of reporting phantom drift.
    uncertain_rows: set[tuple[str, str]] = field(default_factory=set)

    def add_note(self, section: str, note: str, *, approximate: bool) -> None:
        self.notes.setdefault(section, []).append(note)
        if approximate:
            self.approximate_sections.add(section)


@dataclass
class Drift:
    section: str
    row_key: str
    column: Optional[str]
    kind: str  # 'missing_row' | 'extra_row' | 'value'
    expected: Any
    actual: Any


@dataclass
class CheckpointPairVerdict:
    base_checkpoint_id: int
    base_chunk_id: int
    target_checkpoint_id: int
    target_chunk_id: int
    drifts: list[Drift]
    skipped_unreproducible: int
    notes: dict[str, list[str]]


def _as_document(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _row_value(row: Any, index: int) -> Any:
    return row[index]


def _fetch_chunk_created_at(cur: Any, chunk_id: int) -> datetime:
    cur.execute("SELECT created_at FROM narrative_chunks WHERE id = %s", (chunk_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Chunk {chunk_id} does not exist")
    created_at = _row_value(row, 0)
    if created_at is None:
        raise ValueError(
            f"Chunk {chunk_id} has NULL created_at; wall-clock correlation "
            "for relationship inserts is impossible"
        )
    return created_at


def _fetch_world_time(cur: Any, chunk_id: int) -> Optional[datetime]:
    cur.execute(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s", (chunk_id,)
    )
    row = cur.fetchone()
    return _row_value(row, 0) if row is not None else None


def _isoformat(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _canonical_datetime(value: datetime) -> str:
    # Same instant, different offsets ("+00:00" vs "-04:00") must compare
    # equal; aware datetimes normalize to UTC before serializing.
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def canonicalize(value: Any) -> Any:
    """Normalize a leaf value for cross-representation equality.

    Checkpoint documents come from ``to_jsonb`` (timestamps as ISO strings,
    numerics as JSON numbers); replayed rows carry Python datetimes and
    floats. Both sides funnel through here before comparison.
    """

    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return _canonical_datetime(datetime.fromisoformat(value))
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _coerce_need_payload(raw: Any) -> dict[str, Any]:
    """Mirror events._coerce_need_fulfillment for byte-identical metadata."""

    if isinstance(raw, str):
        payload: dict[str, Any] = {"type": raw}
    elif isinstance(raw, dict):
        payload = dict(raw)
    else:
        raise ValueError(f"need.fulfill must be a string or mapping, got {raw!r}")
    need_type = payload.get("type") or payload.get("need")
    if need_type is None:
        raise ValueError("need.fulfill payload lacks a 'type'/'need' field")
    payload["type"] = str(need_type).lower()
    discharge = payload.get("discharge_debt", payload.get("discharge", 9999.0))
    payload["discharge_debt"] = float(discharge)
    return payload


def _coerce_travel_payload(raw: Any) -> dict[str, Any]:
    # Mirror events._coerce_travel_payload: None and True both mean "use
    # defaults" — a JSON null travel value is a live production write path.
    if raw is None or raw is True:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    raise ValueError(f"travel payload must be a mapping, null, or true, got {raw!r}")


def _coerce_project_payload(raw: Any) -> dict[str, Any]:
    if raw is None or raw is True:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    raise ValueError(f"project payload must be a mapping, null, or true, got {raw!r}")


def _load_project_policy() -> ProjectPolicy:
    from nexus.config import load_settings

    settings = load_settings()
    if settings.orrery is None:
        raise ValueError("Replay of project deltas requires [orrery.projects]")
    return coerce_project_policy(settings.orrery.projects)


class _Replayer:
    """Single-use forward/backward replay over one (checkpoint, N] window."""

    def __init__(self, cur: Any, target_chunk_id: int) -> None:
        self.cur = cur
        self.target_chunk_id = target_chunk_id
        self.target_created_at = _fetch_chunk_created_at(cur, target_chunk_id)
        self.need_tuning = load_need_tuning()
        self.project_policy = _load_project_policy()
        self.missing_base_sections: set[str] = set()

    # -- base checkpoint ---------------------------------------------------

    def load_base_checkpoint(
        self, base_checkpoint_id: Optional[int]
    ) -> tuple[int, int, datetime, dict[str, Any]]:
        if base_checkpoint_id is not None:
            self.cur.execute(
                """
                SELECT id, chunk_id, created_at, state FROM state_checkpoints
                WHERE id = %s
                """,
                (base_checkpoint_id,),
            )
        else:
            self.cur.execute(
                """
                SELECT id, chunk_id, created_at, state FROM state_checkpoints
                WHERE chunk_id IS NOT NULL AND chunk_id <= %s
                ORDER BY chunk_id DESC, id DESC
                LIMIT 1
                """,
                (self.target_chunk_id,),
            )
        row = self.cur.fetchone()
        if row is None:
            raise ValueError(
                f"No checkpoint at or before chunk {self.target_chunk_id}; "
                "that chunk predates the instrumentation era (migration 065) "
                "and is not reconstructable"
            )
        checkpoint_id = _row_value(row, 0)
        chunk_id = _row_value(row, 1)
        created_at = _row_value(row, 2)
        state = _as_document(_row_value(row, 3))
        if chunk_id is None or chunk_id > self.target_chunk_id:
            raise ValueError(
                f"Checkpoint {checkpoint_id} (chunk {chunk_id}) is not a valid "
                f"base for reconstruction at chunk {self.target_chunk_id}"
            )
        missing = set(CHECKPOINT_SECTIONS) - set(state)
        allowed_missing = {"character_project_states"}
        unexpected_missing = missing - allowed_missing
        if unexpected_missing:
            raise ValueError(
                f"Checkpoint {checkpoint_id} lacks sections "
                f"{sorted(unexpected_missing)}"
            )
        if "character_project_states" in missing:
            state["character_project_states"] = []
            self.missing_base_sections.add("character_project_states")
        return checkpoint_id, chunk_id, created_at, state

    # -- forward scalar replay ----------------------------------------------

    def replay(self, base_checkpoint_id: Optional[int] = None) -> ReplayResult:
        checkpoint_id, base_chunk, base_created_at, base_state = (
            self.load_base_checkpoint(base_checkpoint_id)
        )
        result = ReplayResult(
            target_chunk_id=self.target_chunk_id,
            base_checkpoint_id=checkpoint_id,
            base_checkpoint_chunk_id=base_chunk,
            state={},
        )
        if "character_project_states" in self.missing_base_sections:
            result.add_note(
                "character_project_states",
                "base checkpoint predates migration 074 and lacks the project "
                "section; treated as empty because no project table/writer "
                "existed at that checkpoint",
                approximate=True,
            )

        characters = {row["id"]: dict(row) for row in base_state["characters"]}
        places = {row["id"]: dict(row) for row in base_state["places"]}
        needs = {
            (row["character_entity_id"], row["need_type"]): dict(row)
            for row in base_state["character_need_states"]
        }
        travel = {
            row["character_entity_id"]: dict(row)
            for row in base_state["character_travel_states"]
        }
        projects: dict[Any, dict[str, Any]] = {
            row["id"]: dict(row) for row in base_state["character_project_states"]
        }

        born_entities = self._seed_window_births(characters, places, result)

        if base_chunk < self.target_chunk_id:
            for chunk_id in self._window_chunks(base_chunk):
                self._apply_skald_rows(chunk_id, characters, places, result)
                self._apply_orrery_resolutions(
                    chunk_id, characters, needs, travel, projects, result
                )

        tag_workings, tag_touched_entities = self._replay_tags(
            base_chunk, base_created_at, base_state, result
        )
        self._sync_need_applicability(
            born_entities | tag_touched_entities,
            characters,
            tag_workings["entity_tags"],
            needs,
            base_chunk,
            base_state,
            result,
        )
        for section, working in tag_workings.items():
            result.state[section] = sorted(working.values(), key=lambda r: r["id"])

        result.state["characters"] = sorted(characters.values(), key=lambda r: r["id"])
        result.state["places"] = sorted(places.values(), key=lambda r: r["id"])
        result.state["character_need_states"] = [
            needs[key] for key in sorted(needs, key=lambda k: (k[0], k[1]))
        ]
        result.state["character_travel_states"] = [
            travel[key] for key in sorted(travel)
        ]
        result.state["character_project_states"] = sorted(
            projects.values(),
            key=lambda row: (
                row["character_entity_id"],
                row.get("source_chunk_id") or -1,
                row.get("id") or -1,
            ),
        )
        result.state["character_routine_anchors"] = sorted(
            (dict(row) for row in base_state["character_routine_anchors"]),
            key=lambda r: r["id"],
        )
        result.add_note(
            "character_routine_anchors",
            "checkpoint pass-through; the table has no runtime writer, but "
            "offline seed/backfill scripts are invisible between checkpoints",
            approximate=False,
        )

        for table in RELATIONSHIP_KEY_COLUMNS:
            self._unwind_relationships(table, result)
        return result

    def _window_chunks(self, base_chunk: int) -> list[int]:
        self.cur.execute(
            """
            SELECT DISTINCT chunk_id FROM (
                SELECT source_chunk_id AS chunk_id FROM state_delta_log
                WHERE source_chunk_id > %(base)s AND source_chunk_id <= %(n)s
                UNION
                SELECT tick_chunk_id FROM orrery_resolutions
                WHERE tick_chunk_id > %(base)s AND tick_chunk_id <= %(n)s
            ) w ORDER BY chunk_id
            """,
            {"base": base_chunk, "n": self.target_chunk_id},
        )
        return [_row_value(row, 0) for row in self.cur.fetchall()]

    def _seed_window_births(
        self,
        characters: dict[int, dict[str, Any]],
        places: dict[int, dict[str, Any]],
        result: ReplayResult,
    ) -> set[int]:
        """Entities INSERTed between checkpoint and N are un-ledgered.

        Their existence is seeded (wall-clock bounded) but their initial
        scalar values are NOT copied from the current rows — the current
        values may include writes from after N, which would both mask
        un-ledgered drift and fabricate phantom drift in verify. Scalars
        start ``None`` and are marked unreproducible; a ledgered write in
        the window clears the mark for the column it sets. Rows whose
        created_at equals the target chunk's are presence-uncertain (the
        Step 8.6 stub-creation ambiguity). Returns born character entity
        ids for the need-applicability sync.
        """

        born_entities: set[int] = set()
        for section, sql, columns in (
            (
                "characters",
                "SELECT id, entity_id, created_at FROM characters "
                "WHERE created_at <= %s",
                ("current_location", "current_activity", "emotional_state"),
            ),
            (
                "places",
                "SELECT id, entity_id, created_at FROM places "
                "WHERE created_at <= %s",
                ("current_status",),
            ),
        ):
            working = characters if section == "characters" else places
            self.cur.execute(sql, (self.target_created_at,))
            births = 0
            for row_id, entity_id, created_at in self.cur.fetchall():
                if row_id in working:
                    continue
                working[row_id] = {
                    "id": row_id,
                    "entity_id": entity_id,
                    **{column: None for column in columns},
                }
                births += 1
                for column in columns:
                    result.unreproducible.add((section, str(row_id), column))
                if created_at == self.target_created_at:
                    result.uncertain_rows.add((section, str(row_id)))
                if section == "characters" and entity_id is not None:
                    born_entities.add(entity_id)
            if births:
                result.add_note(
                    section,
                    f"{births} row(s) born in the window; initial scalars are "
                    "un-ledgered INSERTs — seeded as unknown, filled only by "
                    "ledgered writes",
                    approximate=True,
                )
        return born_entities

    def _apply_skald_rows(
        self,
        chunk_id: int,
        characters: dict[int, dict[str, Any]],
        places: dict[int, dict[str, Any]],
        result: ReplayResult,
    ) -> None:
        self.cur.execute(
            """
            SELECT field, entity_id, new_value FROM state_delta_log
            WHERE source_chunk_id = %s ORDER BY id
            """,
            (chunk_id,),
        )
        by_entity_char = {row["entity_id"]: row for row in characters.values()}
        by_entity_place = {row["entity_id"]: row for row in places.values()}
        for db_field, entity_id, new_value in self.cur.fetchall():
            if db_field not in SKALD_SCALAR_FIELDS:
                raise ValueError(
                    f"state_delta_log chunk {chunk_id} carries unknown field "
                    f"{db_field!r}; the replayer must be taught about it"
                )
            table, column = db_field.split(".", 1)
            rows = by_entity_char if table == "characters" else by_entity_place
            row = rows.get(entity_id)
            if row is None:
                raise ValueError(
                    f"state_delta_log chunk {chunk_id} targets entity "
                    f"{entity_id} with no {table} row in the working state"
                )
            row[column] = new_value
            # A ledgered write makes the column reproducible even for a
            # window-born row seeded as unknown.
            result.unreproducible.discard((table, str(row["id"]), column))

    def _apply_orrery_resolutions(
        self,
        chunk_id: int,
        characters: dict[int, dict[str, Any]],
        needs: dict[tuple[int, str], dict[str, Any]],
        travel: dict[int, dict[str, Any]],
        projects: dict[Any, dict[str, Any]],
        result: ReplayResult,
    ) -> None:
        self.cur.execute(
            """
            SELECT id, actor_entity_id, state_delta FROM orrery_resolutions
            WHERE tick_chunk_id = %s ORDER BY id
            """,
            (chunk_id,),
        )
        resolutions = [
            (row[0], row[1], _as_document(row[2])) for row in self.cur.fetchall()
        ]
        if not resolutions:
            return
        world_time = _fetch_world_time(self.cur, chunk_id)
        by_entity = {row["entity_id"]: row for row in characters.values()}
        for resolution_id, actor_entity_id, delta in resolutions:
            unknown = set(delta) - REPLAYED_DELTA_KEYS - TAG_DELTA_KEYS
            if unknown:
                raise ValueError(
                    f"orrery_resolutions row {resolution_id} carries delta "
                    f"keys {sorted(unknown)} the replayer must be taught about"
                )
            # Per-resolution key order mirrors the applier's if-chain.
            if "character.current_activity" in delta:
                row = by_entity.get(actor_entity_id)
                if row is None:
                    raise ValueError(
                        f"resolution {resolution_id} actor {actor_entity_id} "
                        "has no character row in the working state"
                    )
                row["current_activity"] = delta["character.current_activity"]
                result.unreproducible.discard(
                    ("characters", str(row["id"]), "current_activity")
                )
            if "need.fulfill" in delta:
                self._replay_need_fulfill(
                    chunk_id,
                    actor_entity_id,
                    delta["need.fulfill"],
                    world_time,
                    needs,
                    result,
                )
            for project_key in (
                "project.start",
                "project.advance",
                "project.stall",
                "project.abandon",
                "project.complete",
            ):
                if project_key in delta:
                    self._replay_project(
                        project_key,
                        chunk_id,
                        actor_entity_id,
                        delta[project_key],
                        world_time,
                        projects,
                        travel,
                        by_entity,
                        result,
                    )
            for travel_key in (
                "travel.start",
                "travel.advance",
                "travel.delay",
                "travel.arrive",
            ):
                if travel_key in delta:
                    self._replay_travel(
                        travel_key,
                        chunk_id,
                        actor_entity_id,
                        delta[travel_key],
                        world_time,
                        travel,
                        by_entity,
                        result,
                    )

    def _open_project(
        self,
        projects: dict[Any, dict[str, Any]],
        actor_entity_id: int,
    ) -> tuple[Any, dict[str, Any]]:
        matches = [
            (key, row)
            for key, row in projects.items()
            if row["character_entity_id"] == actor_entity_id
            and row["status"] in {"active", "paused", "stalled"}
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Actor {actor_entity_id} has {len(matches)} open projects "
                "in replay working state"
            )
        key, row = matches[0]
        if row["project_type"] != "plan_relocation":
            raise ValueError(
                f"Actor {actor_entity_id} has unsupported replay project "
                f"type {row['project_type']!r}"
            )
        return key, row

    def _replay_project(
        self,
        delta_key: str,
        chunk_id: int,
        actor_entity_id: int,
        raw_payload: Any,
        world_time: Optional[datetime],
        projects: dict[Any, dict[str, Any]],
        travel: dict[int, dict[str, Any]],
        characters_by_entity: dict[int, dict[str, Any]],
        result: ReplayResult,
    ) -> None:
        """Forward one project transition and its completion handoff."""

        payload = _coerce_project_payload(raw_payload)
        applied = payload.get("applied")
        if not isinstance(applied, dict):
            raise ValueError(
                f"{delta_key} at chunk {chunk_id} is missing its required "
                "applied project projection"
            )
        required_applied = {
            "project_type",
            "status",
            "stage",
            "target_place_id",
            "progress",
            "stall_count",
            "next_eligible_at_world_time",
            "source_chunk_id",
        }
        missing_applied = required_applied - set(applied)
        if missing_applied:
            raise ValueError(
                f"{delta_key} at chunk {chunk_id} has incomplete applied project "
                f"projection: missing {sorted(missing_applied)}"
            )
        project_type = str(applied["project_type"])
        stage = str(applied["stage"])
        if project_type != "plan_relocation":
            raise ValueError(f"Unsupported replay project type {project_type!r}")
        if stage not in {"saving", "scouting", "committing"}:
            raise ValueError(f"Unsupported replay project stage {stage!r}")
        expected_status = {
            "project.start": "active",
            "project.advance": "active",
            "project.stall": "stalled",
            "project.abandon": "abandoned",
            "project.complete": "completed",
        }[delta_key]
        if applied["status"] != expected_status:
            raise ValueError(
                f"{delta_key} at chunk {chunk_id} applied status must be "
                f"{expected_status!r}, got {applied['status']!r}"
            )

        applied_row = {
            "project_type": project_type,
            "status": expected_status,
            "stage": stage,
            "target_place_id": applied["target_place_id"],
            "progress": _pg_round(float(applied["progress"]), 4),
            "stall_count": int(applied["stall_count"]),
            "next_eligible_at_world_time": applied["next_eligible_at_world_time"],
            "source_chunk_id": int(applied["source_chunk_id"]),
        }
        if applied_row["source_chunk_id"] != chunk_id:
            raise ValueError(
                f"{delta_key} at chunk {chunk_id} applied source_chunk_id is "
                f"{applied_row['source_chunk_id']}"
            )
        if delta_key == "project.start":
            if any(
                row["character_entity_id"] == actor_entity_id
                and row["status"] in {"active", "paused", "stalled"}
                for row in projects.values()
            ):
                raise ValueError(
                    f"project.start at chunk {chunk_id} for actor "
                    f"{actor_entity_id} already holding an open project"
                )
            projects[("new", chunk_id, actor_entity_id)] = {
                "id": None,
                "character_entity_id": actor_entity_id,
                **applied_row,
            }
            return

        _project_key, row = self._open_project(projects, actor_entity_id)
        if row["project_type"] != project_type:
            raise ValueError(
                f"{delta_key} at chunk {chunk_id} changes project type from "
                f"{row['project_type']!r} to {project_type!r}"
            )
        if delta_key == "project.advance":
            row.update(applied_row)
            return
        if delta_key == "project.stall":
            row.update(applied_row)
            return
        if delta_key == "project.abandon":
            row.update(applied_row)
            return
        if delta_key == "project.complete":
            if applied_row["stage"] != "committing":
                raise ValueError("project.complete replay requires committing stage")
            if float(applied_row["progress"] or 0.0) < 1.0:
                raise ValueError("project.complete replay requires full progress")
            destination = applied_row["target_place_id"]
            if destination is None:
                raise ValueError(
                    "project.complete replay requires project target_place_id"
                )
            row.update(applied_row)
            travel_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"applied", "milestone", "reason"}
            }
            travel_payload["destination_place_id"] = destination
            self._replay_travel(
                "travel.start",
                chunk_id,
                actor_entity_id,
                travel_payload,
                world_time,
                travel,
                characters_by_entity,
                result,
            )
            return
        raise AssertionError(f"Unhandled project replay key {delta_key!r}")

    def _replay_need_fulfill(
        self,
        chunk_id: int,
        actor_entity_id: int,
        raw_payload: Any,
        world_time: Optional[datetime],
        needs: dict[tuple[int, str], dict[str, Any]],
        result: ReplayResult,
    ) -> None:
        payload = _coerce_need_payload(raw_payload)
        need_type = payload["type"]
        key = (actor_entity_id, need_type)
        row_key = f"{actor_entity_id}:{need_type}"
        if key not in needs:
            needs[key] = {
                "character_entity_id": actor_entity_id,
                "need_type": need_type,
                "debt_score": 0.0,
                "last_evaluated_at": _isoformat(world_time),
                "last_evaluated_chunk_id": None,
                "last_fulfilled_at": None,
                "metadata": {},
            }
        row = needs[key]
        last_evaluated = row.get("last_evaluated_at")
        if isinstance(last_evaluated, str):
            last_evaluated = datetime.fromisoformat(last_evaluated)
        current_debt = effective_debt_score(
            need_type,
            float(row.get("debt_score") or 0.0),
            last_evaluated_at=last_evaluated,
            current_world_time=world_time,
            tuning=self.need_tuning,
        )
        # numeric(8,2) storage rounds; mirror it.
        row["debt_score"] = _pg_round(
            max(0.0, current_debt - payload["discharge_debt"]), 2
        )
        row["last_evaluated_chunk_id"] = chunk_id
        metadata = dict(row.get("metadata") or {})
        metadata["last_fulfillment"] = payload
        row["metadata"] = metadata
        if world_time is None:
            # Production fell back to wall-clock now() at commit time and
            # accrued debt against it — the timestamps AND the debt math are
            # unreproducible; leave prior timestamp values and flag all three
            # columns.
            for column in ("last_evaluated_at", "last_fulfilled_at", "debt_score"):
                result.unreproducible.add(("character_need_states", row_key, column))
            result.add_note(
                "character_need_states",
                f"chunk {chunk_id} has NULL world_time; production stamped "
                f"wall-clock now() on {row_key} — timestamps and accrued "
                "debt unreproducible",
                approximate=True,
            )
        else:
            row["last_evaluated_at"] = _isoformat(world_time)
            row["last_fulfilled_at"] = _isoformat(world_time)
        result.add_note(
            "character_need_states",
            "need.fulfill replayed through effective_debt_score with the "
            "*current* [orrery.sunhelm] tuning; exact only while tuning "
            "matches its value at original commit",
            approximate=False,
        )

    def _replay_travel(
        self,
        delta_key: str,
        chunk_id: int,
        actor_entity_id: int,
        raw_payload: Any,
        world_time: Optional[datetime],
        travel: dict[int, dict[str, Any]],
        characters_by_entity: dict[int, dict[str, Any]],
        result: ReplayResult,
    ) -> None:
        payload = _coerce_travel_payload(raw_payload)
        row = travel.get(actor_entity_id)
        if world_time is None:
            # Production stamped wall-clock now() on this tick's travel
            # world-time columns; replay writes NULLs it cannot back.
            time_columns = ["updated_at_world_time"]
            if delta_key == "travel.start":
                time_columns.append("started_at_world_time")
            for column in time_columns:
                result.unreproducible.add(
                    ("character_travel_states", str(actor_entity_id), column)
                )
        if delta_key == "travel.start":
            destination = payload.get("destination_place_id")
            origin = payload.get("origin_place_id") or (
                characters_by_entity.get(actor_entity_id, {}).get("current_location")
            )
            base = dict(row) if row else {"character_entity_id": actor_entity_id}
            base.update(
                {
                    "status": "in_transit",
                    # Production anchors an in-transit row at its origin.
                    "anchor_place_id": origin,
                    "origin_place_id": origin,
                    "destination_place_id": destination,
                    "progress_ratio": float(payload.get("initial_progress", 0.0)),
                    "updated_at_world_time": _isoformat(world_time),
                    "started_at_world_time": _isoformat(world_time),
                }
            )
            travel[actor_entity_id] = base
            note = (
                f"travel.start at chunk {chunk_id}: destination, route, and "
                "route-adjusted mode/risk are resolved from live state at "
                "commit time; replayed row is approximate"
            )
            if destination is None:
                note += " (destination not explicit in payload — unknown)"
            result.add_note("character_travel_states", note, approximate=True)
            # Route selection derives these from live graph/place state (and
            # may override the payload's mode/risk); not reconstructable.
            unreproducible_columns = [
                "route_method",
                "travel_mode",
                "risk",
                "estimated_distance_m",
                "estimated_duration_minutes",
                "eta_world_time",
                "route_metadata",
            ]
            if destination is None:
                unreproducible_columns.append("destination_place_id")
            for column in unreproducible_columns:
                result.unreproducible.add(
                    ("character_travel_states", str(actor_entity_id), column)
                )
            return
        if row is None:
            raise ValueError(
                f"{delta_key} at chunk {chunk_id} for actor {actor_entity_id} "
                "with no travel row in the working state"
            )
        if delta_key == "travel.advance":
            delta = float(payload.get("progress_delta", TRAVEL_ADVANCE_DEFAULT_DELTA))
            row["progress_ratio"] = _pg_round(
                min(1.0, max(0.0, float(row.get("progress_ratio") or 0.0) + delta)),
                4,
            )
            row["updated_at_world_time"] = _isoformat(world_time)
        elif delta_key == "travel.delay":
            if payload.get("risk"):
                row["risk"] = payload["risk"]
            metadata = dict(row.get("route_metadata") or {})
            metadata["last_delay"] = payload
            row["route_metadata"] = metadata
            row["updated_at_world_time"] = _isoformat(world_time)
        elif delta_key == "travel.arrive":
            destination = payload.get("destination_place_id") or row.get(
                "destination_place_id"
            )
            if destination is None:
                # Production DID move the character (destination came from
                # live travel state at commit time); replay cannot know
                # where. Flag every column the arrival wrote so verify skips
                # instead of reporting false drift.
                character = characters_by_entity.get(actor_entity_id)
                if character is not None:
                    result.unreproducible.add(
                        ("characters", str(character["id"]), "current_location")
                    )
                for column in ("anchor_place_id", "route_metadata"):
                    result.unreproducible.add(
                        ("character_travel_states", str(actor_entity_id), column)
                    )
                result.add_note(
                    "characters",
                    f"travel.arrive at chunk {chunk_id} for actor "
                    f"{actor_entity_id} has no reconstructable destination; "
                    "current_location and arrival columns flagged "
                    "unreproducible",
                    approximate=True,
                )
            else:
                character = characters_by_entity.get(actor_entity_id)
                if character is None:
                    raise ValueError(
                        f"travel.arrive actor {actor_entity_id} has no "
                        "character row in the working state"
                    )
                character["current_location"] = destination
                result.unreproducible.discard(
                    ("characters", str(character["id"]), "current_location")
                )
            metadata = dict(row.get("route_metadata") or {})
            metadata["last_arrived_place_id"] = destination
            row.update(
                {
                    "status": "at_place",
                    "anchor_place_id": destination,
                    "origin_place_id": None,
                    "destination_place_id": None,
                    "progress_ratio": 0.0,
                    "estimated_distance_m": None,
                    "estimated_duration_minutes": None,
                    "started_at_world_time": None,
                    "updated_at_world_time": _isoformat(world_time),
                    "eta_world_time": None,
                    "route_metadata": metadata,
                }
            )

    # -- tag provenance replay -----------------------------------------------

    def _replay_tags(
        self,
        base_chunk: int,
        base_created_at: datetime,
        base_state: dict[str, Any],
        result: ReplayResult,
    ) -> tuple[dict[str, dict[int, dict[str, Any]]], set[int]]:
        """Forward-replay both tag sections from provenance.

        Returns the working row sets (finalized by the caller after the
        need-applicability sync) and the set of character entity ids whose
        entity_tags changed in the window — the population the
        need-applicability trigger fired for.
        """

        workings: dict[str, dict[int, dict[str, Any]]] = {}
        touched_entities: set[int] = set()
        for section, log_column in (
            ("entity_tags", "entity_tag_id"),
            ("entity_pair_tags", "entity_pair_tag_id"),
        ):
            working = {row["id"]: dict(row) for row in base_state[section]}
            self.cur.execute(
                f"""
                SELECT to_jsonb(t) FROM {section} t
                WHERE t.source_chunk_id > %s AND t.source_chunk_id <= %s
                """,
                (base_chunk, self.target_chunk_id),
            )
            for (row_json,) in self.cur.fetchall():
                row = _as_document(row_json)
                # Active-at-N normalization: a row cleared after N was live
                # at N; the checkpoint shape stores active rows with NULL
                # cleared_at.
                row["cleared_at"] = None
                working[row["id"]] = row
                if section == "entity_tags":
                    touched_entities.add(row["entity_id"])
            self.cur.execute(
                f"""
                SELECT {log_column} FROM tag_clearance_log
                WHERE {log_column} IS NOT NULL
                  AND source_chunk_id > %s AND source_chunk_id <= %s
                """,
                (base_chunk, self.target_chunk_id),
            )
            for (tag_row_id,) in self.cur.fetchall():
                removed = working.pop(tag_row_id, None)
                if removed is not None and section == "entity_tags":
                    touched_entities.add(removed["entity_id"])

            # Best-effort inclusion of un-keyed bestowals inside the window
            # (mid-commit new-entity bestowals, Step 8.6 tag hints, offline
            # tools) via wall-clock bounds; excluding them is guaranteed
            # wrong, including them is approximate. The lower bound is
            # inclusive because Step 8.6 of the BASE chunk's commit bestows
            # after the base checkpoint was captured, at the identical
            # transaction timestamp; rows the base checkpoint already holds
            # dedupe by id. Rows at the upper bound are presence-uncertain
            # (same ambiguity at the target chunk).
            self.cur.execute(
                f"""
                SELECT to_jsonb(t) FROM {section} t
                WHERE t.source_chunk_id IS NULL
                  AND t.applied_at >= %s AND t.applied_at <= %s
                """,
                (base_created_at, self.target_created_at),
            )
            unkeyed = 0
            for (row_json,) in self.cur.fetchall():
                row = _as_document(row_json)
                if row["id"] not in working:
                    row["cleared_at"] = None
                    working[row["id"]] = row
                    unkeyed += 1
                    if section == "entity_tags":
                        touched_entities.add(row["entity_id"])
                    applied_at = canonicalize(row.get("applied_at"))
                    if applied_at == canonicalize(self.target_created_at):
                        result.uncertain_rows.add((section, str(row["id"])))
            if unkeyed:
                result.add_note(
                    section,
                    f"{unkeyed} bestowal(s) in the window carry NULL "
                    "source_chunk_id (new-entity mid-commit, Step 8.6 tag "
                    "hints, or offline tools); included by wall-clock "
                    "correlation",
                    approximate=True,
                )
            # Clears with NULL attribution cannot be positioned at all.
            self.cur.execute(
                f"""
                SELECT count(*) FROM tag_clearance_log
                WHERE {log_column} IS NOT NULL AND source_chunk_id IS NULL
                  AND cleared_at > %s AND cleared_at <= %s
                """,
                (base_created_at, self.target_created_at),
            )
            null_clears = _row_value(self.cur.fetchone(), 0)
            if null_clears:
                result.add_note(
                    section,
                    f"{null_clears} clearance(s) in the wall-clock window "
                    "carry NULL source_chunk_id and were NOT applied",
                    approximate=True,
                )
            workings[section] = working
        return workings, touched_entities

    # -- need-applicability trigger mirror ------------------------------------

    def _sync_need_applicability(
        self,
        affected_entities: set[int],
        characters: dict[int, dict[str, Any]],
        entity_tags_working: dict[int, dict[str, Any]],
        needs: dict[tuple[int, str], dict[str, Any]],
        base_chunk: int,
        base_state: dict[str, Any],
        result: ReplayResult,
    ) -> None:
        """Mirror ``orrery_sync_character_need_states`` (migration 057).

        Production triggers on entity_tags changes (and character INSERTs)
        ensure need rows for every applicable need type, DELETE rows for
        needs the entity's tags make inapplicable, and clear that need's
        severity tags — all un-ledgered. Row PRESENCE at the target is a
        pure function of the final active tag set; row CONTENTS are not —
        an applicability toggle (immunity tag applied then cleared inside
        one window) makes production delete and re-insert a FRESH row, so
        toggled rows are reset to the fresh-insert shape here with their
        wall-clock-dependent columns flagged unreproducible. Toggles are
        detected by walking the window's chunk-keyed immunity-tag events
        chronologically.
        """

        if not affected_entities:
            return
        character_entities = {
            row["entity_id"]
            for row in characters.values()
            if row.get("entity_id") is not None
        }
        tag_ids = {
            row["tag_id"]
            for row in entity_tags_working.values()
            if row["entity_id"] in affected_entities
        }
        tag_names: dict[int, str] = {}
        if tag_ids:
            self.cur.execute(
                "SELECT id, tag FROM tags WHERE id = ANY(%s)",
                (list(tag_ids),),
            )
            tag_names = dict(self.cur.fetchall())
        went_inapplicable = self._needs_that_toggled_inapplicable(
            affected_entities & character_entities, base_chunk, base_state
        )

        synthesized = 0
        deleted = 0
        reset = 0
        severity_cleared = 0
        for entity_id in sorted(affected_entities & character_entities):
            active_tags = {
                tag_names[row["tag_id"]]
                for row in entity_tags_working.values()
                if row["entity_id"] == entity_id and row["tag_id"] in tag_names
            }
            applicable = {
                need for need in NEED_TYPES if need_applies_to_tags(need, active_tags)
            }
            for need in NEED_TYPES:
                key = (entity_id, need)
                row_key = f"{entity_id}:{need}"
                if need in applicable and key not in needs:
                    needs[key] = {
                        "character_entity_id": entity_id,
                        "need_type": need,
                        "debt_score": 0.0,
                        "last_evaluated_at": None,
                        "last_evaluated_chunk_id": None,
                        "last_fulfilled_at": None,
                        "metadata": {"synced_by": "need_applicability"},
                    }
                    synthesized += 1
                    # The trigger stamps MAX(chunk_metadata.world_time) at
                    # firing time — not reconstructable after the fact.
                    result.unreproducible.add(
                        ("character_need_states", row_key, "last_evaluated_at")
                    )
                elif need in applicable and key in needs and key in went_inapplicable:
                    # Applicability toggled off then back on inside the
                    # window: production deleted the row and re-inserted a
                    # FRESH one; the checkpoint-inherited contents are stale.
                    fulfilled_after = (
                        needs[key].get("last_evaluated_chunk_id") or 0
                    ) > base_chunk
                    needs[key] = {
                        "character_entity_id": entity_id,
                        "need_type": need,
                        "debt_score": 0.0,
                        "last_evaluated_at": None,
                        "last_evaluated_chunk_id": None,
                        "last_fulfilled_at": None,
                        "metadata": {"synced_by": "need_applicability"},
                    }
                    reset += 1
                    columns = ["last_evaluated_at"]
                    if fulfilled_after:
                        # A need.fulfill also landed in the window; whether
                        # it hit the pre-toggle or post-toggle row is not
                        # reconstructable from the ledger's chunk grain.
                        columns += [
                            "debt_score",
                            "last_evaluated_chunk_id",
                            "last_fulfilled_at",
                            "metadata",
                        ]
                    for column in columns:
                        result.unreproducible.add(
                            ("character_need_states", row_key, column)
                        )
                elif need not in applicable and key in needs:
                    del needs[key]
                    deleted += 1
                    # The trigger also clears this need's severity tags with
                    # NO tag_clearance_log row — mirror the clear here.
                    severity = set(severity_tags_for_need(need))
                    for row_id in [
                        rid
                        for rid, row in entity_tags_working.items()
                        if row["entity_id"] == entity_id
                        and tag_names.get(row["tag_id"]) in severity
                    ]:
                        del entity_tags_working[row_id]
                        severity_cleared += 1
        if synthesized or deleted or reset or severity_cleared:
            result.add_note(
                "character_need_states",
                "need-applicability trigger mirrored: "
                f"{synthesized} row(s) synthesized, {deleted} deleted, "
                f"{reset} reset after an applicability toggle, "
                f"{severity_cleared} un-logged severity tag clear(s) applied",
                approximate=False,
            )

    def _needs_that_toggled_inapplicable(
        self,
        entities: set[int],
        base_chunk: int,
        base_state: dict[str, Any],
    ) -> set[tuple[int, str]]:
        """(entity, need) pairs whose applicability went FALSE at some point
        in the window, per a chronological walk of chunk-keyed immunity-tag
        bestowals and clearances. An immunity tag both bestowed and cleared
        in the SAME chunk counts as a toggle (the trigger fires per
        statement; intra-chunk order is not reconstructable)."""

        if not entities:
            return set()
        all_immunity = frozenset().union(*NEED_IMMUNITY_TAGS.values())
        self.cur.execute(
            "SELECT id, tag FROM tags WHERE tag = ANY(%s)",
            (list(all_immunity),),
        )
        immunity_by_id: dict[int, str] = dict(self.cur.fetchall())
        if not immunity_by_id:
            return set()

        current: dict[int, set[str]] = {entity: set() for entity in entities}
        for row in base_state["entity_tags"]:
            name = immunity_by_id.get(row["tag_id"])
            if name is not None and row["entity_id"] in current:
                current[row["entity_id"]].add(name)

        events: dict[tuple[int, int], tuple[set[str], set[str]]] = {}

        def _event(entity: int, chunk: int) -> tuple[set[str], set[str]]:
            return events.setdefault((entity, chunk), (set(), set()))

        self.cur.execute(
            """
            SELECT entity_id, tag_id, source_chunk_id FROM entity_tags
            WHERE entity_id = ANY(%s) AND tag_id = ANY(%s)
              AND source_chunk_id > %s AND source_chunk_id <= %s
            """,
            (
                list(entities),
                list(immunity_by_id),
                base_chunk,
                self.target_chunk_id,
            ),
        )
        for entity_id, tag_id, chunk in self.cur.fetchall():
            _event(entity_id, chunk)[0].add(immunity_by_id[tag_id])
        self.cur.execute(
            """
            SELECT et.entity_id, et.tag_id, l.source_chunk_id
            FROM tag_clearance_log l
            JOIN entity_tags et ON et.id = l.entity_tag_id
            WHERE et.entity_id = ANY(%s) AND et.tag_id = ANY(%s)
              AND l.source_chunk_id > %s AND l.source_chunk_id <= %s
            """,
            (
                list(entities),
                list(immunity_by_id),
                base_chunk,
                self.target_chunk_id,
            ),
        )
        for entity_id, tag_id, chunk in self.cur.fetchall():
            _event(entity_id, chunk)[1].add(immunity_by_id[tag_id])

        toggled: set[tuple[int, str]] = set()
        for (entity_id, _chunk), (added, cleared) in sorted(
            events.items(), key=lambda item: (item[0][0], item[0][1])
        ):
            transient = added & cleared
            state = current[entity_id]
            state |= added
            state -= cleared
            for need in NEED_TYPES:
                immunity = NEED_IMMUNITY_TAGS[need]
                if immunity & state or immunity & transient:
                    toggled.add((entity_id, need))
        return toggled

    # -- relationship unwind ---------------------------------------------------

    def _unwind_relationships(self, table: str, result: ReplayResult) -> None:
        key_columns = RELATIONSHIP_KEY_COLUMNS[table]
        self.cur.execute(f"SELECT to_jsonb(t) FROM {table} t")
        working: dict[tuple[Any, ...], dict[str, Any]] = {}
        for (row_json,) in self.cur.fetchall():
            row = _as_document(row_json)
            working[tuple(row[c] for c in key_columns)] = row

        self.cur.execute(
            """
            SELECT operation, old_row, source_chunk_id, created_at
            FROM relationship_versions
            WHERE relationship_table = %s
              AND (
                source_chunk_id > %s
                OR (source_chunk_id IS NULL AND created_at > %s)
              )
            ORDER BY id DESC
            """,
            (table, self.target_chunk_id, self.target_created_at),
        )
        null_attributed = 0
        for (
            operation,
            old_row_json,
            source_chunk_id,
            _created_at,
        ) in self.cur.fetchall():
            old_row = _as_document(old_row_json)
            if source_chunk_id is None:
                null_attributed += 1
            # For both 'update' and 'delete' the pre-image IS the row state
            # before the mutation; assignment restores it (delete pre-images
            # re-insert).
            working[tuple(old_row[c] for c in key_columns)] = old_row
        if null_attributed:
            result.add_note(
                table,
                f"{null_attributed} unattributed version row(s) unwound by "
                "wall-clock correlation (NULL source_chunk_id)",
                approximate=True,
            )

        # Rows INSERTed after N never fired the trigger; the only insertion
        # evidence is created_at (also preserved inside pre-images, so this
        # filter must run AFTER the unwind).
        survivors = []
        dropped = 0
        for row in working.values():
            created = row.get("created_at")
            created_dt = (
                datetime.fromisoformat(created) if isinstance(created, str) else created
            )
            if created_dt is not None and created_dt > self.target_created_at:
                dropped += 1
                continue
            survivors.append(row)
        if dropped:
            result.add_note(
                table,
                f"{dropped} row(s) dropped as post-chunk INSERTs by "
                "wall-clock correlation (inserts never fire the versioning "
                "trigger)",
                approximate=True,
            )
        result.state[table] = sorted(
            survivors,
            key=lambda r: tuple(str(r[c]) for c in key_columns),
        )


def reconstruct_state_at_sync(
    cur: Any,
    chunk_id: int,
    *,
    base_checkpoint_id: Optional[int] = None,
) -> ReplayResult:
    """Reconstruct the full mutable state surface as of ``chunk_id``.

    ``base_checkpoint_id`` pins the starting checkpoint (used by verify to
    force replay across a window that ends at a stored checkpoint); by
    default the latest checkpoint at or before ``chunk_id`` is used.
    """

    return _Replayer(cur, chunk_id).replay(base_checkpoint_id)


def _values_equal(expected: Any, actual: Any) -> bool:
    """Pairwise-aware equality across jsonb/Python representations.

    When BOTH sides are strings the numeric coercion is skipped — free-text
    scalar drift like ``"12"`` vs ``"12.0"`` must count as drift; only
    genuinely mixed representations (jsonb number vs Python float, ISO
    string vs datetime) are normalized.
    """

    if isinstance(expected, str) and isinstance(actual, str):
        try:
            return _canonical_datetime(
                datetime.fromisoformat(expected)
            ) == _canonical_datetime(datetime.fromisoformat(actual))
        except ValueError:
            return expected == actual
    exp_value = canonicalize(expected)
    act_value = canonicalize(actual)
    if isinstance(exp_value, float) and isinstance(act_value, float):
        return abs(exp_value - act_value) < 1e-9
    return exp_value == act_value


def _diff_section(
    section: str,
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    key_fn: Any,
    unreproducible: set[tuple[str, str, str]],
    uncertain_rows: set[tuple[str, str]],
) -> tuple[list[Drift], int]:
    volatile = VOLATILE_COLUMNS.get(section, frozenset())
    expected = {key_fn(row): row for row in expected_rows}
    actual = {key_fn(row): row for row in actual_rows}
    drifts: list[Drift] = []
    skipped = 0
    for key in sorted(set(expected) | set(actual), key=str):
        if key not in actual or key not in expected:
            if (section, str(key)) in uncertain_rows:
                skipped += 1
                continue
            if key not in actual:
                drifts.append(
                    Drift(section, str(key), None, "missing_row", expected[key], None)
                )
            else:
                drifts.append(
                    Drift(section, str(key), None, "extra_row", None, actual[key])
                )
            continue
        exp_row, act_row = expected[key], actual[key]
        for column in sorted(set(exp_row) | set(act_row)):
            if column in volatile:
                continue
            if (section, str(key), column) in unreproducible:
                skipped += 1
                continue
            if _values_equal(exp_row.get(column), act_row.get(column)):
                continue
            drifts.append(
                Drift(
                    section,
                    str(key),
                    column,
                    "value",
                    exp_row.get(column),
                    act_row.get(column),
                )
            )
    return drifts, skipped


def _section_key_fn(section: str) -> Any:
    if section in RELATIONSHIP_KEY_COLUMNS:
        columns = RELATIONSHIP_KEY_COLUMNS[section]
        return lambda row: tuple(row[c] for c in columns)
    if section == "character_need_states":
        return lambda row: f"{row['character_entity_id']}:{row['need_type']}"
    if section == "character_travel_states":
        return lambda row: row["character_entity_id"]
    if section == "character_project_states":
        return lambda row: (
            f"{row['character_entity_id']}:{row['project_type']}:"
            f"{row.get('source_chunk_id')}"
        )
    return lambda row: row["id"]


def _load_checkpoint_state(cur: Any, checkpoint_id: int) -> dict[str, Any]:
    cur.execute("SELECT state FROM state_checkpoints WHERE id = %s", (checkpoint_id,))
    state = _as_document(_row_value(cur.fetchone(), 0))
    state.setdefault("character_project_states", [])
    return state


def verify_checkpoints_sync(cur: Any) -> list[CheckpointPairVerdict]:
    """Replay every consecutive checkpoint pair and diff against the stored
    target document. Zero drift means the ledgers were sufficient across
    that window; any drift names the writer that shipped un-ledgered.

    Two checkpoints at the SAME chunk (e.g. interval + manual) are diffed
    stored-vs-stored — anything written between the two captures surfaces
    as drift there instead of being silently skipped.

    Known blind spot: relationship sections replay backward from the
    CURRENT tables, so when nothing touched a relationship after the target
    checkpoint the diff compares live rows against a snapshot of the same
    live rows. The unwind path itself is exercised by dedicated tests, not
    by this oracle.
    """

    cur.execute(
        """
        SELECT id, chunk_id FROM state_checkpoints
        WHERE chunk_id IS NOT NULL ORDER BY chunk_id, id
        """
    )
    checkpoints = cur.fetchall()
    verdicts: list[CheckpointPairVerdict] = []
    for (base_id, base_chunk), (target_id, target_chunk) in zip(
        checkpoints, checkpoints[1:]
    ):
        if base_chunk == target_chunk:
            # Same-chunk captures must be identical documents; diff them
            # directly, no replay involved.
            base_stored = _load_checkpoint_state(cur, base_id)
            target_stored = _load_checkpoint_state(cur, target_id)
            drifts = []
            for section in CHECKPOINT_SECTIONS:
                section_drifts, _ = _diff_section(
                    section,
                    base_stored[section],
                    target_stored[section],
                    _section_key_fn(section),
                    set(),
                    set(),
                )
                drifts.extend(section_drifts)
            verdicts.append(
                CheckpointPairVerdict(
                    base_checkpoint_id=base_id,
                    base_chunk_id=base_chunk,
                    target_checkpoint_id=target_id,
                    target_chunk_id=target_chunk,
                    drifts=drifts,
                    skipped_unreproducible=0,
                    notes={
                        "_pair": [
                            "same-chunk captures compared directly "
                            "(stored vs stored)"
                        ]
                    },
                )
            )
            continue
        result = reconstruct_state_at_sync(
            cur, target_chunk, base_checkpoint_id=base_id
        )
        stored = _load_checkpoint_state(cur, target_id)
        drifts = []
        skipped = 0
        for section in CHECKPOINT_SECTIONS:
            section_drifts, section_skipped = _diff_section(
                section,
                stored[section],
                result.state[section],
                _section_key_fn(section),
                result.unreproducible,
                result.uncertain_rows,
            )
            drifts.extend(section_drifts)
            skipped += section_skipped
        verdicts.append(
            CheckpointPairVerdict(
                base_checkpoint_id=base_id,
                base_chunk_id=base_chunk,
                target_checkpoint_id=target_id,
                target_chunk_id=target_chunk,
                drifts=drifts,
                skipped_unreproducible=skipped,
                notes=result.notes,
            )
        )
    return verdicts
