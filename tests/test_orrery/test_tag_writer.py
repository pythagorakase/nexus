"""Tests for nexus.agents.orrery.tag_writer.apply_tag_bestowal.

These use a small fake cursor that maintains in-memory state for the SQL
patterns the writer issues. The cursor is not a faithful psycopg2 emulator —
it only handles the writer's specific SQL — but that's enough to verify the
business-logic outcomes (counters, idempotency, canonicalization, category
gating, clearance). End-to-end behavior against a real database is exercised
in Phase 2/3 of the Skald-tag-bestowal plan.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from nexus.agents.orrery.tag_schemas import NewTagProposal, OrreryTagBestowal
from nexus.agents.orrery.tag_writer import apply_tag_bestowal


_WORLD_TIME = datetime(2073, 10, 31, 9, 44, tzinfo=timezone.utc)


class _FakeRow:
    """Dict + tuple hybrid row, mimics both psycopg2.extras.DictCursor and a tuple cursor."""

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
        )  # name → {id, category, is_ephemeral, deprecated, synonym_for}
        self.entity_tags = list(entity_tags or [])
        self.category_registry = category_registry or _default_category_registry()
        self.world_time = world_time
        self.rowcount = 0
        self._next_row: Any = None
        self._next_rows: list[Any] = []
        self._next_id = 1000
        self.inserted_tag_rows: list[dict[str, Any]] = []
        self.inserted_entity_tag_rows: list[dict[str, Any]] = []
        self.inserted_category_rows: list[dict[str, Any]] = []
        self.cleared_keys: list[tuple[int, int]] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        params = params or ()
        sql_trimmed = sql.strip()
        sql_upper = sql_trimmed.upper()
        if sql_upper.startswith("SELECT MAX(WORLD_TIME)"):
            self._next_row = _FakeRow({"world_time": self.world_time}, ["world_time"])
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
                },
                ["id", "category", "is_ephemeral"],
            )
            self.rowcount = 1
            return
        if sql_upper.startswith("INSERT INTO ENTITY_TAGS"):
            entity_id, tag_id, world_time, source_kind = params
            for row in self.entity_tags:
                if (
                    row["entity_id"] == entity_id
                    and row["tag_id"] == tag_id
                    and row["cleared_at"] is None
                ):
                    self.rowcount = 0
                    return
            new_row = {
                "entity_id": entity_id,
                "tag_id": tag_id,
                "applied_at_world_time": world_time,
                "source_kind": source_kind,
                "cleared_at": None,
            }
            self.entity_tags.append(new_row)
            self.inserted_entity_tag_rows.append(new_row)
            self.rowcount = 1
            return
        if sql_upper.startswith("UPDATE ENTITY_TAGS"):
            entity_id, tag_id = params
            cleared = 0
            for row in self.entity_tags:
                if (
                    row["entity_id"] == entity_id
                    and row["tag_id"] == tag_id
                    and row["cleared_at"] is None
                ):
                    row["cleared_at"] = "now"
                    cleared += 1
                    self.cleared_keys.append((entity_id, tag_id))
            self.rowcount = cleared
            return
        raise AssertionError(f"FakeCursor: unhandled SQL: {sql_trimmed[:80]!r}")

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
        name, category, ephemeral = entry
        table[name] = {
            "id": hash(name) & 0xFFFFFF,
            "category": category,
            "is_ephemeral": ephemeral,
            "clearance_kind": "semantic" if ephemeral else None,
            "deprecated": False,
            "synonym_for": None,
        }
    return table


def _default_category_registry() -> dict[str, set[str]]:
    return {
        "bodyform": {"character"},
        "capacity": {"character"},
        "disposition": {"character"},
        "orrery_need": {"character"},
        "orrery_state": {"character"},
        "place_affordance": {"place"},
        "power_posture": {"faction"},
        "profession_lite": {"character"},
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
    assert counters["skipped_unknown"] == 0
    assert counters["skipped_category"] == 0
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


def test_new_tag_proposal_inserts_both_tag_and_entity_tag():
    cur = FakeCursor(tags={})
    bestowal = OrreryTagBestowal(
        new_tag_proposals=[
            NewTagProposal(
                tag="bodyform:elf",
                category="bodyform",
                scope="durable",
                evidence="Half-elven scholar with pointed ears and centuries of memory.",
            )
        ]
    )
    counters = apply_tag_bestowal(
        cur,
        entity_id=99,
        entity_kind="character",
        bestowal=bestowal,
    )
    assert counters["proposed"] == 1
    assert counters["applied"] == 1
    assert cur.inserted_tag_rows[0]["tag"] == "bodyform:elf"
    assert cur.inserted_tag_rows[0]["is_ephemeral"] is False
    assert cur.inserted_tag_rows[0]["clearance_kind"] is None
    assert cur.inserted_entity_tag_rows[0]["entity_id"] == 99


def test_new_tag_proposal_registers_new_category_for_entity_kind():
    cur = FakeCursor(tags={})
    bestowal = OrreryTagBestowal(
        new_tag_proposals=[
            NewTagProposal(
                tag="oath_bound",
                category="fantasy_oath_state",
                scope="durable",
                evidence="The oath-sigil burns when the knight speaks a vow.",
            )
        ]
    )

    counters = apply_tag_bestowal(
        cur,
        entity_id=99,
        entity_kind="character",
        bestowal=bestowal,
    )

    assert counters["proposed"] == 1
    assert counters["applied"] == 1
    assert cur.inserted_category_rows == [
        {"category": "fantasy_oath_state", "entity_kind": "character"}
    ]


def test_new_tag_proposal_rejects_existing_category_for_wrong_entity_kind():
    cur = FakeCursor(tags={})
    bestowal = OrreryTagBestowal(
        new_tag_proposals=[
            NewTagProposal(
                tag="hidden_gallery",
                category="place_affordance",
                scope="durable",
                evidence="The person is standing in a hall with hidden galleries.",
            )
        ]
    )

    counters = apply_tag_bestowal(
        cur,
        entity_id=99,
        entity_kind="character",
        bestowal=bestowal,
    )

    assert counters["proposed"] == 0
    assert counters["applied"] == 0
    assert counters["skipped_category"] == 1
    assert cur.inserted_tag_rows == []


def test_ephemeral_proposal_sets_clearance_kind_semantic():
    cur = FakeCursor(tags={})
    bestowal = OrreryTagBestowal(
        new_tag_proposals=[
            NewTagProposal(
                tag="scrying_target",
                category="orrery_state",
                scope="ephemeral",
                evidence="The hedge witch's mirror flickers when she walks past.",
            )
        ]
    )
    apply_tag_bestowal(cur, entity_id=7, entity_kind="character", bestowal=bestowal)
    assert cur.inserted_tag_rows[0]["is_ephemeral"] is True
    assert cur.inserted_tag_rows[0]["clearance_kind"] == "semantic"


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


def test_incompatible_category_silently_skipped():
    cur = FakeCursor(tags=_registered(("safe_house", "place_affordance", False)))
    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["safe_house"]),
    )
    assert counters["applied"] == 0
    assert counters["skipped_category"] == 1
    assert cur.inserted_entity_tag_rows == []


def test_unknown_tag_silently_skipped():
    cur = FakeCursor(tags={})
    counters = apply_tag_bestowal(
        cur,
        entity_id=42,
        entity_kind="character",
        bestowal=OrreryTagBestowal(applied_tags=["nonexistent_tag"]),
    )
    assert counters["applied"] == 0
    assert counters["skipped_unknown"] == 1


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


def test_none_bestowal_is_noop():
    cur = FakeCursor()
    counters = apply_tag_bestowal(
        cur, entity_id=1, entity_kind="character", bestowal=None
    )
    assert counters == {
        "applied": 0,
        "proposed": 0,
        "cleared": 0,
        "skipped_category": 0,
        "skipped_unknown": 0,
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


def test_faction_category_gating():
    cur = FakeCursor(
        tags=_registered(
            ("militarized", "power_posture", False),
            ("corporate_exile", "state", False),  # state is character-only
        )
    )
    counters = apply_tag_bestowal(
        cur,
        entity_id=7,
        entity_kind="faction",
        bestowal=OrreryTagBestowal(applied_tags=["militarized", "corporate_exile"]),
    )
    assert counters["applied"] == 1
    assert counters["skipped_category"] == 1
