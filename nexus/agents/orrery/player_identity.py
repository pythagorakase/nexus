"""Canonical player-character identity lookup for Orrery boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text


_PLAYER_IDENTITY_SQL = """
    SELECT globals.user_character, character.entity_id
    FROM global_variables globals
    LEFT JOIN characters character ON character.id = globals.user_character
    WHERE globals.id = true
"""


def canonical_player_entity_id(session_or_cur: Any) -> int:
    """Return the player entity id from the canonical global character row.

    Both SQLAlchemy sessions/connections and psycopg-compatible cursors are
    accepted because Orrery formation and recall cross those two DB surfaces.
    An incomplete identity is a corrupt story state, so every missing link is
    rejected loudly rather than interpreted as permission to include the
    player.
    """

    if type(session_or_cur).__module__.startswith("sqlalchemy"):
        result = session_or_cur.execute(text(_PLAYER_IDENTITY_SQL))
        row = result.mappings().one_or_none()
    else:
        session_or_cur.execute(_PLAYER_IDENTITY_SQL)
        row = session_or_cur.fetchone()
    if row is None:
        raise RuntimeError(
            "Cannot resolve canonical player identity: global_variables "
            "row id=true is missing"
        )
    if isinstance(row, Mapping):
        user_character = row["user_character"]
        entity_id = row["entity_id"]
    else:
        user_character = row[0]
        entity_id = row[1]
    if user_character is None:
        raise RuntimeError(
            "Cannot resolve canonical player identity: user_character is NULL"
        )
    if entity_id is None:
        raise RuntimeError(
            f"Player character row {user_character} has no canonical entity id"
        )
    return int(entity_id)
