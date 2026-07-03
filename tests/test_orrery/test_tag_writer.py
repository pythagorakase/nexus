"""Tests for nexus.agents.orrery.tag_writer.apply_tag_bestowal.

These use a small fake cursor that maintains in-memory state for the SQL
patterns the writer issues. The cursor is not a faithful psycopg2 emulator —
it only handles the writer's specific SQL — but that's enough to verify the
business-logic outcomes (counters, idempotency, canonicalization, category
gating, clearance). End-to-end behavior against a real database is exercised
in Phase 2/3 of the Skald-tag-bestowal plan.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest
from pydantic import ValidationError

from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import (
    apply_exclusive_tag_bestowal,
    apply_tag_bestowal,
    clear_entity_tag,
)


_WORLD_TIME = datetime(2073, 10, 31, 9, 44, tzinfo=timezone.utc)


class _FakeRow:
    """Dict + tuple hybrid row for cursor-style tests."""

    def __init__(self, mapping: dict[str, Any], order: list[str]):
        self._mapping = mapping
        self._order = order

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._mapping[self._order[key]]
        return self._mapping[key]

    def get(self, key, default=None):
        return self._mapping.get(key, default)

    def keys(self):
        return list(self._order)


class FakeCursor:
    """In-memory simulator for the SQL apply_tag_bestowal issues.

    Tracks the live tag vocabulary and the entity_tags state. The writer's
    SQL is dispatched by pattern-matching the leading keywords; each branch
    updates ``rowcount`` and queues the next ``fetchone`` result.
    """

    def __init__(
        self,
        *,
        tags: Optional[dict[str, dict[str, Any]]] = None,
        entity_tags: Optional[list[dict[str, Any]]] = None,
        category_registry: Optional[dict[str, set[str]]] = None,
        world_time: Optional[datetime] = _WORLD_TIME,
    ):
        self.tags = dict(
            tags or {}
        )  # name -> {id, category, is_ephemeral, reapplication_policy, ...}
        self.entity_tags = list(entity_tags or [])
        self.category_registry = category_registry or _default_category_registry()
        self.world_time = world_time
        self.chunk_world_times: dict[int, datetime] = {}
        self.rowcount = 0
        self._next_row: Any = None
        self._next_rows: list[Any] = []
        self._next_id = 1000
        self._next_entity_tag_id = 1
        for row in self.entity_tags:
            row.setdefault("id", self._next_entity_tag_id)
            self._next_entity_tag_id += 1
        self.inserted_tag_rows: list[dict[str, Any]] = []
        self.inserted_entity_tag_rows: list[dict[str, Any]] = []
        self.inserted_category_rows: list[dict[str, Any]] = []
        self.cleared_keys: list[tuple[int, int]] = []
        self.clearance_log_rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        params = params or ()
        sql_trimmed = sql.strip()
        sql_upper = sql_trimmed.upper()
        if sql_upper.startswith("SELECT MAX(WORLD_TIME)"):
            self._next_row = _FakeRow({"world_time": self.world_time}, ["world_time"])
            self.rowcount = 1
            return
        if sql_upper.startswith("SELECT WORLD_TIME FROM CHUNK_METADATA"):
            (chunk_id,) = params
            world_time = self.chunk_world_times.get(chunk_id)
            self._next_row = (
                _FakeRow({"world_time": world_time}, ["world_time"])
                if world_time is not None
                else None
            )
            self.rowcount = 1 if world_time is not None else 0
            return
        if sql_upper.startswith("INSERT INTO TAG_CLEARANCE_LOG"):
            cleared_id, world_time, justification, source_chunk_id = params
            key = (
                "entity_pair_tag_id"
                if "ENTITY_PAIR_TAG_ID" in sql_upper
                else "entity_tag_id"
            )
            self.clearance_log_rows.append(
                {
                    key: cleared_id,
                    "mechanism": "authored",
                    "cleared_at_world_time": world_time,
                    "justification": justification,
                    "source_chunk_id": source_chunk_id,
                }
            )
            self.rowcount = 1
            return
        if (
            "FROM TAG_CATEGORY_REGISTRY" in sql_upper
            and "WHERE ENTITY_KIND" in sql_upper
        ):
            (entity_kind,) = params
            rows = [
                _FakeRow({"category": category}, ["category"])
                for category, kinds in self.category_registry.items()
                if entity_kind in kinds
            ]
            self._next_rows = rows
            self.rowcount = len(rows)
            return
        if "FROM TAG_CATEGORY_REGISTRY" in sql_upper and "WHERE CATEGORY" in sql_upper:
            (category,) = params
            kinds = self.category_registry.get(category, set())
            rows = [
                _FakeRow({"entity_kind": entity_kind}, ["entity_kind"])
                for entity_kind in sorted(kinds)
            ]
            self._next_rows = rows
            self.rowcount = len(rows)
            return
        if sql_upper.startswith("INSERT INTO TAG_CATEGORY_REGISTRY"):
            category, entity_kind, _description = params
            self.category_registry.setdefault(category, set()).add(entity_kind)
            self.inserted_category_rows.append(
                {"category": category, "entity_kind": entity_kind}
            )
            self.rowcount = 1
            return
        if sql_upper.startswith("INSERT INTO TAGS"):
            tag, category, is_ephemeral, clearance_kind, description = params
            if tag in self.tags:
                self.rowcount = 0
                return
            tag_id = self._next_id
            self._next_id += 1
            self.tags[tag] = {
                "id": tag_id,
                "category": category,
                "is_ephemeral": is_ephemeral,
                "reapplication_policy": None,
                "clearance_kind": clearance_kind,
                "deprecated": False,
                "synonym_for": None,
            }
            self.inserted_tag_rows.append(
                {
                    "tag": tag,
                    "category": category,
                    "is_ephemeral": is_ephemeral,
                    "clearance_kind": clearance_kind,
                    "description": description,
                }
            )
            self.rowcount = 1
            return
        if sql_upper.startswith("SELECT ID, CATEGORY, IS_EPHEMERAL"):
            (name,) = params
            row = self.tags.get(name)
            if (
                row is None
                or row.get("deprecated")
                or row.get("synonym_for") is not None
            ):
                self._next_row = None
                self.rowcount = 0
                return
            self._next_row = _FakeRow(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "is_ephemeral": row["is_ephemeral"],
                    "reapplication_policy": row.get("reapplication_policy"),
                },
                ["id", "category", "is_ephemeral", "reapplication_policy"],
            )
            self.rowcount = 1
            return
        if sql_upper.startswith("INSERT INTO ENTITY_TAGS"):
            (
                entity_id,
                tag_id,
                world_time,
                expires_at_world_time,
                source_kind,
                source_chunk_id,
            ) = params[:6]
            duration_override = params[6] if len(params) > 6 else None
            for row in self.entity_tags:
                if (
                    row["entity_id"] == entity_id
                    and row["tag_id"] == tag_id
                    and row["cleared_at"] is None
                ):
                    if "GREATEST" in sql_upper:
                        base = max(
                            row.get("expires_at_world_time") or world_time,
                            world_time,
                        )
                        row["applied_at_world_time"] = world_time
                        row["expires_at_world_time"] = base + duration_override
                        row["source_kind"] = source_kind
                        row["source_chunk_id"] = source_chunk_id
                        self.rowcount = 1
                        return
                    if "DO UPDATE SET" in sql_upper:
                        row["applied_at_world_time"] = world_time
                        row["expires_at_world_time"] = expires_at_world_time
                        row["source_kind"] = source_kind
                        row["source_chunk_id"] = source_chunk_id
                        self.rowcount = 1
                        return
                    self.rowcount = 0
                    return
            new_row = {
                "id": self._next_entity_tag_id,
                "entity_id": entity_id,
                "tag_id": tag_id,
                "applied_at_world_time": world_time,
                "expires_at_world_time": expires_at_world_time,
                "source_kind": source_kind,
                "source_chunk_id": source_chunk_id,
                "cleared_at": None,
            }
            self._next_entity_tag_id += 1
            self.entity_tags.append(new_row)
            self.inserted_entity_tag_rows.append(new_row)
            self.rowcount = 1
            return
        if sql_upper.startswith("UPDATE ENTITY_TAGS ET") and "T.TAG =" in sql_upper:
            entity_id, tag = params
            tag_row = self.tags.get(tag)
            cleared_ids: list[int] = []
            if (
                tag_row is not None
                and not tag_row.get("deprecated")
                and tag_row.get("synonym_for") is None
            ):
                tag_id = tag_row["id"]
                for row in self.entity_tags:
                    if (
                        row["entity_id"] == entity_id
                        and row["tag_id"] == tag_id
                        and row["cleared_at"] is None
                    ):
                        row["cleared_at"] = "now"
                        cleared_ids.append(row["id"])
                        self.cleared_keys.append((entity_id, tag_id))
            self._queue_returning_ids(cleared_ids)
            return
        if sql_upper.startswith("UPDATE ENTITY_TAGS ET"):
            entity_id, category, keep_tag_id = params
            cleared_ids = []
            tag_id_to_category = {
                row["id"]: row["category"] for row in self.tags.values()
            }
            for row in self.entity_tags:
                if (
                    row["entity_id"] == entity_id
                    and row["tag_id"] != keep_tag_id
                    and row["cleared_at"] is None
                    and tag_id_to_category.get(row["tag_id"]) == category
                ):
                    row["cleared_at"] = "now"
                    cleared_ids.append(row["id"])
                    self.cleared_keys.append((entity_id, row["tag_id"]))
            self._queue_returning_ids(cleared_ids)
            return
        if sql_upper.startswith("UPDATE ENTITY_TAGS"):
            entity_id, tag_id = params
            cleared_ids = []
            for row in self.entity_tags:
                if (
                    row["entity_id"] == entity_id
                    and row["tag_id"] == tag_id
                    and row["cleared_at"] is None
                ):
                    row["cleared_at"] = "now"
                    cleared_ids.append(row["id"])
                    self.cleared_keys.append((entity_id, tag_id))
            self._queue_returning_ids(cleared_ids)
            return
        raise AssertionError(f"FakeCursor: unhandled SQL: {sql_trimmed[:80]!r}")

    def _queue_returning_ids(self, cleared_ids: list[int]) -> None:
        """Model ``UPDATE ... RETURNING id``: queue one id-row per cleared row."""
        self._next_rows = [_FakeRow({"id": row_id}, ["id"]) for row_id in cleared_ids]
        self.rowcount = len(cleared_ids)

    def fetchone(self):
        row = self._next_row
        self._next_row = None
        return row

    def fetchall(self):
        rows = self._next_rows
        self._next_rows = []
        return rows


def _registered(*entries):
    """Quick helper to build the vocabulary dict for the fake cursor."""
    table = {}
    for entry in entries:
        if len(entry) == 3:
            name, category, ephemeral = entry
            reapplication_policy = None
        else:
            name, category, ephemeral, reapplication_policy = entry
        table[name] = {
            "id": hash(name) & 0xFFFFFF,
            "category": category,
            "is_ephemeral": ephemeral,
            "reapplication_policy": reapplication_policy,
            "clearance_kind": "semantic" if ephemeral else None,
            "deprecated": False,
            "synonym_for": None,
        }
    return table


def _default_category_registry() -> dict[str, set[str]]:
    return {
        "bodyform": {"character"},
        "bodyform.condition": {"character"},
        "bodyform.lineage": {"character"},
        "capacity": {"character"},
        "disposition": {"character"},
        "orrery_need": {"character"},
        "orrery_state": {"character"},
        "place_affordance": {"place"},
        "power_posture": {"faction"},
        "profession_lite": {"character"},
        "role.function": {"character"},
        "role.fame": {"character"},
        "role.resources": {"character"},
        "state": {"character"},
    }


def test_applies_registered_character_tag():
    cur = FakeCursor(
        tags=_registered(
            ("corporate_exile", "state", False),
            ("informant_handler", "profession_lite", False),
        )
    )
    bestowal = OrreryTagBestowal(applied_tags=["corporate_exile", "informant_handler"])
    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=bestowal,
    )
    assert counters["applied"] == 2
    inserted = {
        (r["entity_id"], r["source_kind"]) for r in cur.inserted_entity_tag_rows
    }
    assert inserted == {(42, "skald_inline")}


def test_idempotent_when_open_row_exists():
    tag_id = hash("corporate_exile") & 0xFFFFFF
    existing = [
        {
            "entity_id": 42,
            "tag_id": tag_id,
            "applied_at_world_time": _WORLD_TIME,
            "source_kind": "llm_generated",
            "cleared_at": None,
        }
    ]
    cur = FakeCursor(
        tags=_registered(("corporate_exile", "state", False)),
        entity_tags=existing,
    )
    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["corporate_exile"]),
    )
    assert counters["applied"] == 0
    assert len(cur.inserted_entity_tag_rows) == 0


def test_duration_override_sets_expiry_on_insert():
    cur = FakeCursor(tags=_registered(("intoxicated:stimulant", "state", True)))

    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["intoxicated:stimulant"]),
        duration_override=timedelta(hours=2),
        world_time=_WORLD_TIME,
    )

    assert counters["applied"] == 1
    assert cur.inserted_entity_tag_rows[0]["expires_at_world_time"] == (
        _WORLD_TIME + timedelta(hours=2)
    )


def test_new_row_policy_preserves_existing_open_row_on_reapply():
    tag_id = hash("intoxicated:stimulant") & 0xFFFFFF
    original_expiry = _WORLD_TIME + timedelta(minutes=30)
    cur = FakeCursor(
        tags=_registered(
            ("intoxicated:stimulant", "state", True, "new_row"),
        ),
        entity_tags=[
            {
                "entity_id": 42,
                "tag_id": tag_id,
                "applied_at_world_time": _WORLD_TIME,
                "expires_at_world_time": original_expiry,
                "source_kind": "skald_inline",
                "cleared_at": None,
            }
        ],
    )

    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["intoxicated:stimulant"]),
        duration_override=timedelta(hours=2),
        world_time=_WORLD_TIME + timedelta(minutes=10),
    )

    assert counters["applied"] == 0
    assert cur.entity_tags[0]["expires_at_world_time"] == original_expiry


def test_extend_expiry_policy_extends_from_later_of_expiry_or_world_time():
    tag_id = hash("intoxicated:stimulant") & 0xFFFFFF
    original_expiry = _WORLD_TIME + timedelta(minutes=30)
    cur = FakeCursor(
        tags=_registered(
            ("intoxicated:stimulant", "state", True, "extend_expiry"),
        ),
        entity_tags=[
            {
                "entity_id": 42,
                "tag_id": tag_id,
                "applied_at_world_time": _WORLD_TIME,
                "expires_at_world_time": original_expiry,
                "source_kind": "skald_inline",
                "cleared_at": None,
            }
        ],
    )

    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["intoxicated:stimulant"]),
        duration_override=timedelta(hours=1),
        world_time=_WORLD_TIME + timedelta(minutes=10),
        source_kind="system",
    )

    assert counters["applied"] == 1
    assert cur.entity_tags[0]["expires_at_world_time"] == (
        original_expiry + timedelta(hours=1)
    )
    assert cur.entity_tags[0]["applied_at_world_time"] == (
        _WORLD_TIME + timedelta(minutes=10)
    )
    assert cur.entity_tags[0]["source_kind"] == "system"


def test_extend_expiry_policy_requires_duration_override():
    cur = FakeCursor(
        tags=_registered(
            ("intoxicated:stimulant", "state", True, "extend_expiry"),
        )
    )

    with pytest.raises(ValueError, match="extend_expiry.*duration_override"):
        apply_tag_bestowal(
            cur,
            entity_id=42,
            entity_kind="character",
            bestowal=OrreryTagBestowal(applied_tags=["intoxicated:stimulant"]),
            world_time=_WORLD_TIME,
        )

    assert cur.entity_tags == []


def test_replace_policy_restamps_existing_open_row():
    tag_id = hash("disguised") & 0xFFFFFF
    cur = FakeCursor(
        tags=_registered(("disguised", "state", True, "replace")),
        entity_tags=[
            {
                "entity_id": 42,
                "tag_id": tag_id,
                "applied_at_world_time": _WORLD_TIME,
                "expires_at_world_time": _WORLD_TIME + timedelta(hours=1),
                "source_kind": "skald_inline",
                "cleared_at": None,
            }
        ],
    )
    new_world_time = _WORLD_TIME + timedelta(days=1)

    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["disguised"]),
        duration_override=timedelta(hours=3),
        world_time=new_world_time,
        source_kind="system",
    )

    assert counters["applied"] == 1
    assert cur.entity_tags[0]["applied_at_world_time"] == new_world_time
    assert cur.entity_tags[0]["expires_at_world_time"] == (
        new_world_time + timedelta(hours=3)
    )
    assert cur.entity_tags[0]["source_kind"] == "system"


def test_closed_bestowal_schema_rejects_runtime_vocabulary_growth_field():
    with pytest.raises(ValidationError):
        OrreryTagBestowal.model_validate({"new_" + "tag_proposals": []})


def test_clears_existing_tag():
    tag_id = hash("scrying_target") & 0xFFFFFF
    cur = FakeCursor(
        tags=_registered(("scrying_target", "orrery_state", True)),
        entity_tags=[
            {
                "entity_id": 11,
                "tag_id": tag_id,
                "applied_at_world_time": _WORLD_TIME,
                "source_kind": "skald_inline",
                "cleared_at": None,
            }
        ],
    )
    counters = apply_tag_bestowal(
        cur,
        entity_id=11,
        entity_kind="character",
        bestowal=OrreryTagBestowal(tags_to_clear=["scrying_target"]),
    )
    assert counters["cleared"] == 1
    assert cur.cleared_keys == [(11, tag_id)]
    assert len(cur.clearance_log_rows) == 1
    assert cur.clearance_log_rows[0]["entity_tag_id"] == cur.entity_tags[0]["id"]
    assert cur.clearance_log_rows[0]["mechanism"] == "authored"


def test_clear_entity_tag_marks_known_active_tag_cleared():
    tag_id = hash("scrying_target") & 0xFFFFFF
    cur = FakeCursor(
        tags=_registered(("scrying_target", "orrery_state", True)),
        entity_tags=[
            {
                "entity_id": 11,
                "tag_id": tag_id,
                "applied_at_world_time": _WORLD_TIME,
                "source_kind": "skald_inline",
                "cleared_at": None,
            }
        ],
    )

    cleared = clear_entity_tag(cur, entity_id=11, tag="scrying_target")

    assert cleared is True
    assert cur.entity_tags[0]["cleared_at"] == "now"
    assert cur.cleared_keys == [(11, tag_id)]
    assert len(cur.clearance_log_rows) == 1
    assert cur.clearance_log_rows[0]["entity_tag_id"] == cur.entity_tags[0]["id"]


def test_clear_entity_tag_is_idempotent():
    tag_id = hash("scrying_target") & 0xFFFFFF
    cur = FakeCursor(
        tags=_registered(("scrying_target", "orrery_state", True)),
        entity_tags=[
            {
                "entity_id": 11,
                "tag_id": tag_id,
                "applied_at_world_time": _WORLD_TIME,
                "source_kind": "skald_inline",
                "cleared_at": None,
            }
        ],
    )

    assert clear_entity_tag(cur, entity_id=11, tag="scrying_target") is True
    assert clear_entity_tag(cur, entity_id=11, tag="scrying_target") is False
    # Only the first (effective) clear writes a clearance-log row.
    assert len(cur.clearance_log_rows) == 1


def test_clear_entity_tag_returns_false_when_no_active_row():
    cur = FakeCursor(tags=_registered(("scrying_target", "orrery_state", True)))

    assert clear_entity_tag(cur, entity_id=11, tag="scrying_target") is False


def test_clear_entity_tag_resolves_canonical_alias():
    tag_id = hash("corporate_exile") & 0xFFFFFF
    cur = FakeCursor(
        tags=_registered(("corporate_exile", "state", False)),
        entity_tags=[
            {
                "entity_id": 42,
                "tag_id": tag_id,
                "applied_at_world_time": _WORLD_TIME,
                "source_kind": "skald_inline",
                "cleared_at": None,
            }
        ],
    )

    cleared = clear_entity_tag(cur, entity_id=42, tag="corporate_defector")

    assert cleared is True
    assert cur.entity_tags[0]["cleared_at"] == "now"


def test_clear_entity_tag_unknown_or_deprecated_tag_is_noop():
    tag_rows = _registered(("retired_signal", "orrery_state", True))
    tag_rows["retired_signal"]["deprecated"] = True
    tag_id = tag_rows["retired_signal"]["id"]
    cur = FakeCursor(
        tags=tag_rows,
        entity_tags=[
            {
                "entity_id": 11,
                "tag_id": tag_id,
                "applied_at_world_time": _WORLD_TIME,
                "source_kind": "skald_inline",
                "cleared_at": None,
            }
        ],
    )

    assert clear_entity_tag(cur, entity_id=11, tag="retired_signal") is False
    assert clear_entity_tag(cur, entity_id=11, tag="not_registered") is False
    assert cur.entity_tags[0]["cleared_at"] is None


def test_incompatible_category_raises():
    cur = FakeCursor(tags=_registered(("safe_house", "place_affordance", False)))
    with pytest.raises(ValueError, match="not registered for entity_kind"):
        apply_tag_bestowal(
            cur,
            entity_id=42,
            entity_kind="character",
            bestowal=OrreryTagBestowal(applied_tags=["safe_house"]),
        )
    assert cur.inserted_entity_tag_rows == []


def test_unknown_tag_raises():
    cur = FakeCursor(tags={})
    with pytest.raises(ValueError, match="Unknown or deprecated Orrery tag"):
        apply_tag_bestowal(
            cur,
            entity_id=42,
            entity_kind="character",
            bestowal=OrreryTagBestowal(applied_tags=["nonexistent_tag"]),
        )


def test_canonical_alias_applied_as_canonical():
    cur = FakeCursor(tags=_registered(("corporate_exile", "state", False)))
    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["corporate_defector"]),
    )
    assert counters["applied"] == 1
    canonical_id = hash("corporate_exile") & 0xFFFFFF
    assert cur.inserted_entity_tag_rows[0]["tag_id"] == canonical_id


def test_bodyform_alias_applied_as_canonical_character_anchor():
    cur = FakeCursor(tags=_registered(("inorganic", "bodyform.lineage", False)))

    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["bodyform:android"]),
    )

    assert counters["applied"] == 1
    canonical_id = hash("inorganic") & 0xFFFFFF
    assert cur.inserted_entity_tag_rows[0]["tag_id"] == canonical_id


def test_none_bestowal_is_noop():
    cur = FakeCursor()
    counters = apply_tag_bestowal(
        cur, entity_id=1, entity_kind="character", bestowal=None
    )
    assert counters == {
        "applied": 0,
        "cleared": 0,
    }


def test_unknown_entity_kind_raises():
    cur = FakeCursor()
    with pytest.raises(ValueError, match="Unknown entity_kind"):
        apply_tag_bestowal(
            cur,
            entity_id=1,
            entity_kind="zombie",
            bestowal=OrreryTagBestowal(),
        )


def test_mixed_bestowal_validates_before_writing():
    cur = FakeCursor(
        tags=_registered(
            ("militarized", "power_posture", False),
            ("corporate_exile", "state", False),  # state is character-only
        )
    )
    with pytest.raises(ValueError, match="not registered for entity_kind"):
        apply_tag_bestowal(
            cur,
            entity_id=7,
            entity_kind="faction",
            bestowal=OrreryTagBestowal(applied_tags=["militarized", "corporate_exile"]),
        )
    assert cur.inserted_entity_tag_rows == []


def test_disallowed_runtime_source_kind_rejected():
    cur = FakeCursor(tags=_registered(("corporate_exile", "state", False)))
    with pytest.raises(ValueError, match="auto-register"):
        apply_tag_bestowal(
            cur,
            entity_id=42,
            entity_kind="character",
            bestowal=OrreryTagBestowal(applied_tags=["corporate_exile"]),
            source_kind="auto_" "registered",
        )


def test_exclusive_tag_bestowal_clears_siblings_and_applies_new_value():
    obscure_id = hash("obscure") & 0xFFFFFF
    known_id = hash("known") & 0xFFFFFF
    strong_id = hash("strong") & 0xFFFFFF
    cur = FakeCursor(
        tags=_registered(
            ("obscure", "role.fame", False),
            ("known", "role.fame", False),
            ("strong", "capacity", False),
        ),
        entity_tags=[
            {
                "entity_id": 42,
                "tag_id": obscure_id,
                "applied_at_world_time": _WORLD_TIME,
                "source_kind": "llm_generated",
                "cleared_at": None,
            },
            {
                "entity_id": 42,
                "tag_id": strong_id,
                "applied_at_world_time": _WORLD_TIME,
                "source_kind": "llm_generated",
                "cleared_at": None,
            },
        ],
    )

    inserted = apply_exclusive_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        tag="known",
    )

    assert inserted is True
    assert cur.cleared_keys == [(42, obscure_id)]
    assert {
        (row["tag_id"], row["cleared_at"])
        for row in cur.entity_tags
        if row["entity_id"] == 42
    } == {
        (obscure_id, "now"),
        (strong_id, None),
        (known_id, None),
    }
