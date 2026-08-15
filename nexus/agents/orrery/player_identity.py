"""Canonical player-character identity lookup for Orrery boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text


_PLAYER_IDENTITY_SQL = """
    /* orrery:canonical_player_identity */
    SELECT globals.user_character,
           character.id AS character_id,
           character.entity_id
    FROM global_variables globals
    LEFT JOIN characters character ON character.id = globals.user_character
    WHERE globals.id = true
"""


class PlayerIdentityNotEstablishedError(RuntimeError):
    """Raised when a valid pre-story slot has no player character yet."""


def _coerce_player_identity(row: Any) -> tuple[int, int]:
    """Validate and return ``(character_id, entity_id)`` from one DB row."""

    if row is None:
        raise RuntimeError(
            "Cannot resolve canonical player identity: global_variables "
            "row id=true is missing"
        )
    if not isinstance(row, Mapping) and hasattr(row, "_mapping"):
        row = row._mapping
    if isinstance(row, Mapping):
        user_character = row["user_character"]
        character_id = row["character_id"]
        entity_id = row["entity_id"]
    else:
        user_character = row[0]
        character_id = row[1]
        entity_id = row[2]
    if user_character is None:
        raise PlayerIdentityNotEstablishedError(
            "Cannot resolve canonical player identity: user_character is NULL"
        )
    if character_id is None:
        raise RuntimeError(f"Player character row {user_character} does not exist")
    if entity_id is None:
        raise RuntimeError(
            f"Player character row {user_character} has no canonical entity id"
        )
    return int(character_id), int(entity_id)


def _canonical_player_identity(session_or_cur: Any) -> tuple[int, int]:
    """Load the canonical player ids through a sync database surface."""

    if hasattr(session_or_cur, "fetchone"):
        session_or_cur.execute(_PLAYER_IDENTITY_SQL)
        row = session_or_cur.fetchone()
    else:
        result = session_or_cur.execute(text(_PLAYER_IDENTITY_SQL))
        row = result.mappings().one_or_none()
    return _coerce_player_identity(row)


def canonical_player_character_id(session_or_cur: Any) -> int:
    """Return the player ``characters.id`` from the canonical global row.

    Both SQLAlchemy sessions/connections and psycopg-compatible cursors are
    accepted because Orrery formation and recall cross those two DB surfaces.
    An incomplete identity is a corrupt story state, so every missing link is
    rejected loudly rather than interpreted as permission to include the
    player.
    """

    character_id, _entity_id = _canonical_player_identity(session_or_cur)
    return character_id


async def canonical_player_character_id_async(conn: Any) -> int:
    """Return the canonical player ``characters.id`` through asyncpg.

    The asynchronous commit route uses asyncpg rather than the SQLAlchemy and
    psycopg surfaces accepted by :func:`canonical_player_character_id`. An
    incomplete identity has the same loud corruption contract on every
    database surface.
    """

    row = await conn.fetchrow(_PLAYER_IDENTITY_SQL)
    character_id, _entity_id = _coerce_player_identity(row)
    return character_id


def canonical_player_entity_id(session_or_cur: Any) -> int:
    """Return the player entity id from the canonical global character row.

    Both SQLAlchemy sessions/connections and psycopg-compatible cursors are
    accepted because Orrery formation and recall cross those two DB surfaces.
    An incomplete identity is a corrupt story state, so every missing link is
    rejected loudly rather than interpreted as permission to include the
    player.
    """

    _character_id, entity_id = _canonical_player_identity(session_or_cur)
    return entity_id
