"""Regressions for capped entity-reference query semantics."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from nexus.agents.lore.utils.entity_queries import (
    fetch_all_characters_with_references,
    fetch_all_places_with_references,
    fetch_place_ids_by_names,
    fetch_present_character_ids,
)


class _Row:
    """Small SQLAlchemy row stand-in with attribute and mapping access."""

    def __init__(self, **values: Any) -> None:
        self._mapping = values
        for key, value in values.items():
            setattr(self, key, value)


class _Result:
    """Small SQLAlchemy result stand-in."""

    def __init__(self, rows: Optional[list[_Row]] = None) -> None:
        self.rows = rows or []

    def fetchall(self) -> list[_Row]:
        return self.rows

    def fetchone(self) -> Optional[_Row]:
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _CharacterQuerySession:
    """Evaluate the character query's cap-relevant behavior in memory."""

    def __init__(self) -> None:
        self.user_character_id = 1
        self.references = [
            _Row(character_id=1, reference="present", chunk_id=100),
            _Row(character_id=2, reference="present", chunk_id=100),
            _Row(character_id=3, reference="mentioned", chunk_id=99),
            _Row(character_id=4, reference="mentioned", chunk_id=98),
        ]
        self.characters = {
            character_id: _Row(
                id=character_id,
                name=f"Character {character_id}",
                current_location=None,
            )
            for character_id in range(1, 5)
        }
        self.executed: list[tuple[str, Dict[str, Any]]] = []

    def execute(
        self,
        statement: Any,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> _Result:
        sql = str(statement)
        params = parameters or {}
        self.executed.append((sql, params))

        if "FROM global_variables" in sql:
            return _Result([_Row(user_character=self.user_character_id)])

        if "FROM chunk_character_references" in sql:
            eligible = [
                row for row in self.references if row.chunk_id in params["chunk_ids"]
            ]
            if "character_id IS DISTINCT FROM :user_character_id" in sql:
                eligible = [
                    row
                    for row in eligible
                    if row.character_id != params["user_character_id"]
                ]

            latest_by_character: dict[int, _Row] = {}
            for row in sorted(
                eligible,
                key=lambda candidate: (
                    candidate.character_id,
                    -candidate.chunk_id,
                ),
            ):
                latest_by_character.setdefault(row.character_id, row)
            selected = sorted(
                latest_by_character.values(),
                key=lambda row: (-row.chunk_id, row.character_id),
            )[: params["max_featured_characters"]]
            return _Result(selected)

        if "FROM characters" in sql and "WHERE id = ANY(:ids)" in sql:
            return _Result(
                [self.characters[character_id] for character_id in params["ids"]]
            )

        if "FROM characters" in sql:
            return _Result(list(self.characters.values()))

        raise AssertionError(f"Unexpected character query: {sql}")


class _PlaceQuerySession:
    """Evaluate place caps and reference winner priority in memory."""

    def __init__(self) -> None:
        self.places = {
            10: _Row(id=10, name="Newest Setting"),
            11: _Row(id=11, name="Transit Stop"),
            12: _Row(id=12, name="Older Mention"),
            13: _Row(id=13, name="Old Setting"),
            99: _Row(id=99, name="Character Haven"),
        }
        self.references = [
            _Row(place_id=10, reference_type="mentioned", chunk_id=100),
            _Row(place_id=10, reference_type="setting", chunk_id=100),
            _Row(place_id=11, reference_type="transit", chunk_id=99),
            _Row(place_id=12, reference_type="mentioned", chunk_id=98),
            _Row(place_id=13, reference_type="setting", chunk_id=97),
        ]
        self.executed: list[tuple[str, Dict[str, Any]]] = []

    def execute(
        self,
        statement: Any,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> _Result:
        sql = str(statement)
        params = parameters or {}
        self.executed.append((sql, params))

        if "WHERE name = ANY(:place_names)" in sql:
            requested_names = set(params["place_names"])
            return _Result(
                [
                    place
                    for place in self.places.values()
                    if place.name in requested_names
                ]
            )

        if "FROM place_chunk_references" in sql:
            eligible = [
                row for row in self.references if row.chunk_id in params["chunk_ids"]
            ]
            priority = {"setting": 0, "transit": 1, "mentioned": 2}
            has_priority_tiebreaker = "CASE reference_type::text" in sql
            winner_by_place: dict[int, _Row] = {}
            winner_keys: dict[int, tuple[int, int, str]] = {}
            for row in eligible:
                reference_priority = (
                    priority[row.reference_type] if has_priority_tiebreaker else 0
                )
                key = (-row.chunk_id, reference_priority, row.reference_type)
                if row.place_id not in winner_keys or key < winner_keys[row.place_id]:
                    winner_by_place[row.place_id] = row
                    winner_keys[row.place_id] = key
            selected = sorted(
                winner_by_place.values(),
                key=lambda row: (-row.chunk_id, row.place_id),
            )[: params["max_featured_places"]]
            return _Result(selected)

        if "FROM places" in sql and "WHERE id = ANY(:ids)" in sql:
            return _Result([self.places[place_id] for place_id in params["ids"]])

        if "FROM places" in sql:
            return _Result(list(self.places.values()))

        raise AssertionError(f"Unexpected place query: {sql}")


def test_present_character_ids_use_exact_chunk_roster() -> None:
    """Presence retrieval carries only sorted present rows from its anchor."""

    class PresenceSession:
        def execute(
            self, statement: Any, parameters: Optional[Dict[str, Any]] = None
        ) -> _Result:
            assert "reference::text = 'present'" in str(statement)
            assert parameters == {"chunk_id": 42}
            return _Result(
                [
                    _Row(character_id=9),
                    _Row(character_id=3),
                    _Row(character_id=9),
                ]
            )

    assert fetch_present_character_ids(PresenceSession(), 42) == [3, 9]


def test_user_character_does_not_consume_non_user_character_cap() -> None:
    """A newest user reference still permits the full NPC cap plus the user."""
    session = _CharacterQuerySession()

    result = fetch_all_characters_with_references(
        session,
        [100, 99, 98],
        max_featured_characters=2,
    )

    featured_by_id = {row["id"]: row for row in result["featured"]}
    assert set(featured_by_id) == {1, 2, 3}
    assert len(set(featured_by_id) - {session.user_character_id}) == 2
    assert featured_by_id[session.user_character_id]["reference_type"] == (
        "user_character"
    )

    reference_sql, reference_params = next(
        (sql, params)
        for sql, params in session.executed
        if "FROM chunk_character_references" in sql
    )
    assert "character_id IS DISTINCT FROM :user_character_id" in reference_sql
    assert reference_params["user_character_id"] == session.user_character_id


def test_featured_location_bypasses_cap_and_place_winner_is_deterministic() -> None:
    """Character locations survive beyond the cap; setting wins a newest tie."""
    session = _PlaceQuerySession()
    featured_location_ids = fetch_place_ids_by_names(
        session,
        {"Character Haven"},
    )

    result = fetch_all_places_with_references(
        session,
        [100, 99, 98, 97],
        featured_location_ids,
        max_featured_places=2,
    )

    featured_by_id = {row["id"]: row for row in result["featured"]}
    assert set(featured_by_id) == {10, 11, 99}
    assert featured_by_id[10]["reference_type"] == "setting"
    assert featured_by_id[99]["reference_type"] == "character_location"

    reference_sql = next(
        sql for sql, _params in session.executed if "FROM place_chunk_references" in sql
    )
    assert "place_reference_type is setting, transit, mentioned" in reference_sql
    assert reference_sql.index("WHEN 'setting' THEN 0") < reference_sql.index(
        "WHEN 'transit' THEN 1"
    )
    assert reference_sql.index("WHEN 'transit' THEN 1") < reference_sql.index(
        "WHEN 'mentioned' THEN 2"
    )


def test_featured_location_name_resolution_fails_loudly() -> None:
    """An unresolved location cannot silently lose its required dossier."""
    with pytest.raises(ValueError, match="did not resolve.*Missing Place"):
        fetch_place_ids_by_names(
            _PlaceQuerySession(),
            {"Missing Place"},
        )
