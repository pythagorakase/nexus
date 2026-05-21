"""Tests for centralized ``status:<level>`` helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from nexus.agents.orrery.status_family import (
    enumerate_status_above,
    has_any_status,
    is_negative_status,
    status_at_or_above,
    status_at_or_above_level,
    status_tag_for_level,
)
from nexus.agents.orrery.tag_writer import apply_status_pair_tag_bestowal


_WORLD_TIME = datetime(2073, 10, 31, 9, 44, tzinfo=timezone.utc)


class _FakeRow:
    def __init__(self, mapping: dict[str, Any], order: list[str]):
        self._mapping = mapping
        self._order = order

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._mapping[self._order[key]]
        return self._mapping[key]

    def get(self, key, default=None):
        return self._mapping.get(key, default)


class _PairCursor:
    def __init__(
        self,
        *,
        pair_tags: Optional[dict[str, dict[str, Any]]] = None,
        entity_pair_tags: Optional[list[dict[str, Any]]] = None,
    ):
        self.pair_tags = pair_tags or _status_pair_tags()
        self.entity_pair_tags = list(entity_pair_tags or [])
        self.rowcount = 0
        self._next_row: Any = None
        self._next_rows: list[Any] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        params = params or ()
        sql_upper = sql.strip().upper()
        if sql_upper.startswith("SELECT MAX(WORLD_TIME)"):
            self._next_row = _FakeRow({"world_time": _WORLD_TIME}, ["world_time"])
            self.rowcount = 1
            return
        if sql_upper.startswith("SELECT ID, SUBJECT_KINDS, OBJECT_KINDS"):
            (tag,) = params
            row = self.pair_tags.get(tag)
            if row is None or row.get("deprecated"):
                self._next_row = None
                self.rowcount = 0
                return
            self._next_row = _FakeRow(
                {
                    "id": row["id"],
                    "subject_kinds": row["subject_kinds"],
                    "object_kinds": row["object_kinds"],
                },
                ["id", "subject_kinds", "object_kinds"],
            )
            self.rowcount = 1
            return
        if sql_upper.startswith("UPDATE ENTITY_PAIR_TAGS EPT"):
            subject_id, object_id, tags = params
            tag_names = set(tags)
            cleared = 0
            id_to_tag = {row["id"]: tag for tag, row in self.pair_tags.items()}
            for row in self.entity_pair_tags:
                if (
                    row["subject_entity_id"] == subject_id
                    and row["object_entity_id"] == object_id
                    and row["cleared_at"] is None
                    and id_to_tag.get(row["pair_tag_id"]) in tag_names
                ):
                    row["cleared_at"] = "now"
                    cleared += 1
            self.rowcount = cleared
            return
        if sql_upper.startswith("INSERT INTO ENTITY_PAIR_TAGS"):
            subject_id, object_id, pair_tag_id, world_time, source_kind = params
            for row in self.entity_pair_tags:
                if (
                    row["subject_entity_id"] == subject_id
                    and row["object_entity_id"] == object_id
                    and row["pair_tag_id"] == pair_tag_id
                    and row["cleared_at"] is None
                ):
                    self.rowcount = 0
                    return
            self.entity_pair_tags.append(
                {
                    "subject_entity_id": subject_id,
                    "object_entity_id": object_id,
                    "pair_tag_id": pair_tag_id,
                    "applied_at_world_time": world_time,
                    "source_kind": source_kind,
                    "cleared_at": None,
                }
            )
            self.rowcount = 1
            return
        if sql_upper.startswith("SELECT EPT.OBJECT_ENTITY_ID"):
            subject_id, tags = params
            self._next_rows = self._status_rows(subject_id=subject_id, tags=set(tags))
            self.rowcount = len(self._next_rows)
            return
        if sql_upper.startswith("SELECT PT.TAG"):
            subject_id, object_id, tags = params
            self._next_rows = self._status_rows(
                subject_id=subject_id,
                object_id=object_id,
                tags=set(tags),
            )
            self.rowcount = len(self._next_rows)
            return
        raise AssertionError(f"unhandled SQL: {sql.strip()[:80]!r}")

    def fetchone(self):
        row = self._next_row
        self._next_row = None
        return row

    def fetchall(self):
        rows = self._next_rows
        self._next_rows = []
        return rows

    def _status_rows(
        self,
        *,
        subject_id: int,
        tags: set[str],
        object_id: Optional[int] = None,
    ) -> list[_FakeRow]:
        id_to_tag = {row["id"]: tag for tag, row in self.pair_tags.items()}
        rows = []
        for row in self.entity_pair_tags:
            tag = id_to_tag.get(row["pair_tag_id"])
            if (
                row["subject_entity_id"] == subject_id
                and (object_id is None or row["object_entity_id"] == object_id)
                and row["cleared_at"] is None
                and tag in tags
            ):
                rows.append(
                    _FakeRow(
                        {
                            "scope_faction_entity_id": row["object_entity_id"],
                            "tag": tag,
                        },
                        ["scope_faction_entity_id", "tag"],
                    )
                )
        return rows


def _status_pair_tags() -> dict[str, dict[str, Any]]:
    levels = [
        "junior",
        "respected",
        "senior",
        "elite",
        "executive",
        "sovereign",
        "outcast",
        "pariah",
        "enslaved",
    ]
    return {
        f"status:{level}": {
            "id": index + 1,
            "subject_kinds": ["character", "faction"],
            "object_kinds": ["faction"],
            "deprecated": False,
        }
        for index, level in enumerate(levels)
    }


def _active(subject_id: int, object_id: int, tag: str) -> dict[str, Any]:
    return {
        "subject_entity_id": subject_id,
        "object_entity_id": object_id,
        "pair_tag_id": _status_pair_tags()[tag]["id"],
        "cleared_at": None,
    }


def test_status_level_mapping_and_negative_bucket() -> None:
    assert status_tag_for_level("senior") == "status:senior"
    assert status_tag_for_level("status:senior") == "status:senior"
    assert status_at_or_above_level("executive", "senior") is True
    assert status_at_or_above_level("junior", "senior") is False
    assert is_negative_status("outcast") is True
    assert is_negative_status("senior") is False
    with pytest.raises(ValueError, match="Unknown status level"):
        status_tag_for_level("apprentice")


def test_status_read_helpers_pick_highest_active_level_per_scope() -> None:
    cur = _PairCursor(
        entity_pair_tags=[
            _active(10, 100, "status:junior"),
            _active(10, 100, "status:senior"),
            _active(10, 101, "status:elite"),
            _active(10, 102, "status:outcast"),
        ]
    )

    assert (
        has_any_status(cur, subject_entity_id=10, scope_faction_entity_id=100)
        == "senior"
    )
    assert status_at_or_above(
        cur,
        subject_entity_id=10,
        scope_faction_entity_id=101,
        threshold="senior",
    )
    assert not status_at_or_above(
        cur,
        subject_entity_id=10,
        scope_faction_entity_id=102,
        threshold="junior",
    )
    assert enumerate_status_above(cur, subject_entity_id=10, threshold="senior") == [
        (100, "senior"),
        (101, "elite"),
    ]


def test_status_bestowal_replaces_status_family_within_one_scope_edge() -> None:
    cur = _PairCursor(
        entity_pair_tags=[
            _active(10, 100, "status:junior"),
            _active(10, 100, "status:outcast"),
            _active(10, 101, "status:junior"),
        ]
    )

    inserted = apply_status_pair_tag_bestowal(
        cur,
        subject_entity_id=10,
        scope_faction_entity_id=100,
        subject_kind="character",
        level="senior",
    )

    assert inserted is True
    assert (
        has_any_status(cur, subject_entity_id=10, scope_faction_entity_id=100)
        == "senior"
    )
    assert (
        has_any_status(cur, subject_entity_id=10, scope_faction_entity_id=101)
        == "junior"
    )
    active_rows_for_scope = [
        row
        for row in cur.entity_pair_tags
        if row["subject_entity_id"] == 10
        and row["object_entity_id"] == 100
        and row["cleared_at"] is None
    ]
    assert len(active_rows_for_scope) == 1
