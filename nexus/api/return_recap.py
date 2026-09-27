"""Evidence-linked return recap for the reader (issue #832).

A player coming back to a story sees where it stands: the current setting,
who is present, their last accepted action, and the decision still open.
The recap is deterministic. It reads committed canon only, calls no model,
and writes nothing back; dismissing it is client state.

Every item cites the committed rows it came from as source handles, and an
item whose source is missing is left out rather than invented. Before the
recap leaves the server, :func:`verify_recap_sources` checks each cited ID
against committed rows again. Handles name only rows the reader already
serves: playable committed chunks, places, and characters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, ConfigDict, Field

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.api.choice_handling import normalize_choice_object
from nexus.presence.roster import read_roster, required_id


class SourceHandle(BaseModel):
    """One committed row a recap item cites."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["chunk", "place", "character"]
    id: int


class RecapItem(BaseModel):
    """One recap line and the committed rows it came from.

    ``open_decision`` text holds one presented option per line.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["location", "roster", "last_action", "open_decision"]
    text: str = Field(min_length=1)
    sources: List[SourceHandle] = Field(min_length=1)


class ReturnRecap(BaseModel):
    """The recap a returning player sees above the frontier."""

    model_config = ConfigDict(extra="forbid")

    due: bool
    last_played: Optional[datetime]
    items: List[RecapItem]


class RecapEvidenceError(RuntimeError):
    """A recap item cites a row that is not committed, playable canon."""


@dataclass(frozen=True)
class NamedRow:
    """A place or character row: its ID and its stored, natural-case name."""

    id: int
    name: str


@dataclass(frozen=True)
class SettingRows:
    """The setting places recorded on the latest committed chunk that has any."""

    chunk_id: int
    places: Tuple[NamedRow, ...]


@dataclass(frozen=True)
class RosterRows:
    """Characters present on the frontier chunk, in character-ID order."""

    chunk_id: int
    characters: Tuple[NamedRow, ...]


@dataclass(frozen=True)
class FrontierRow:
    """The latest committed playable chunk's recorded response fields."""

    chunk_id: int
    choice_text: Optional[str]
    choice_object: Any


@dataclass(frozen=True)
class ActionRow:
    """The latest committed playable chunk carrying an accepted action."""

    chunk_id: int
    choice_text: str


def is_recap_due(
    last_played: Optional[datetime], now: datetime, hiatus_hours: float
) -> bool:
    """Whether at least ``hiatus_hours`` have passed since the last accepted action.

    A story with no recorded action is never due; the recap then opens only
    on demand.
    """
    if last_played is None:
        return False
    return now - last_played >= timedelta(hours=hiatus_hours)


def compose_recap(
    *,
    last_played: Optional[datetime],
    now: datetime,
    hiatus_hours: float,
    roster_limit: int,
    setting: Optional[SettingRows],
    roster: Optional[RosterRows],
    last_action: Optional[ActionRow],
    frontier: Optional[FrontierRow],
) -> ReturnRecap:
    """Build the recap from typed committed rows, omitting every unsourced item.

    Args:
        last_played: When the last accepted player action was recorded.
        now: The clock the hiatus is measured against.
        hiatus_hours: Hours of absence after which the recap is due.
        roster_limit: Most present characters to name.
        setting: The latest committed setting places, if any are recorded.
        roster: Characters present on the frontier chunk.
        last_action: The latest committed chunk with an accepted action.
        frontier: The latest committed playable chunk, if the story has one;
            its presented options are the open decision until it records a
            response.

    Returns:
        The recap, its items in location, roster, last action, open decision
        order.

    Raises:
        ValueError: If ``roster_limit`` is below one or the frontier's stored
            ``choice_object`` is malformed.
    """
    if roster_limit < 1:
        raise ValueError(f"roster_limit must be at least 1, got {roster_limit}")

    items: List[RecapItem] = []
    if setting is not None and setting.places:
        items.append(
            RecapItem(
                kind="location",
                text=", ".join(place.name for place in setting.places),
                sources=[
                    SourceHandle(kind="chunk", id=setting.chunk_id),
                    *(SourceHandle(kind="place", id=p.id) for p in setting.places),
                ],
            )
        )
    named = roster.characters[:roster_limit] if roster is not None else ()
    if roster is not None and named:
        items.append(
            RecapItem(
                kind="roster",
                text=", ".join(character.name for character in named),
                sources=[
                    SourceHandle(kind="chunk", id=roster.chunk_id),
                    *(SourceHandle(kind="character", id=c.id) for c in named),
                ],
            )
        )
    action_text = last_action.choice_text.strip() if last_action else ""
    if last_action is not None and action_text:
        items.append(
            RecapItem(
                kind="last_action",
                text=action_text,
                sources=[SourceHandle(kind="chunk", id=last_action.chunk_id)],
            )
        )
    options = _open_options(frontier)
    if frontier is not None and options:
        items.append(
            RecapItem(
                kind="open_decision",
                text="\n".join(options),
                sources=[SourceHandle(kind="chunk", id=frontier.chunk_id)],
            )
        )
    return ReturnRecap(
        due=is_recap_due(last_played, now, hiatus_hours),
        last_played=last_played,
        items=items,
    )


def _open_options(frontier: Optional[FrontierRow]) -> List[str]:
    """Presented options still open on the frontier, or none once it is answered."""
    if frontier is None or (frontier.choice_text or "").strip():
        return []
    choice_object = normalize_choice_object(frontier.choice_object)
    if choice_object is None:
        return []
    return [option.strip() for option in choice_object["presented"] if option.strip()]


_CHUNK_FIELDS_SQL = """
    FROM narrative_chunks nc
    JOIN chunk_metadata cm ON cm.chunk_id = nc.id
    WHERE {predicate}
"""

_GLOBAL_SQL = """
    SELECT last_played, now() AS checked_at
    FROM global_variables
    WHERE id = true
"""

_FRONTIER_SQL = (
    "SELECT nc.id, nc.choice_text, nc.choice_object"
    + _CHUNK_FIELDS_SQL.format(predicate=playable_narrative_predicate())
    + "ORDER BY nc.id DESC LIMIT 1"
)

# [^[:space:]] matches Python's str.strip(): a whitespace-only response is
# not an action.
_LAST_ACTION_SQL = (
    "SELECT nc.id, nc.choice_text"
    + _CHUNK_FIELDS_SQL.format(predicate=playable_narrative_predicate())
    + "AND nc.choice_text ~ '[^[:space:]]' ORDER BY nc.id DESC LIMIT 1"
)

# The /api/current-place read, restricted to playable committed chunks.
_SETTING_SQL = f"""
    WITH latest AS (
        SELECT max(pcr.chunk_id) AS chunk_id
        FROM place_chunk_references pcr
        JOIN narrative_chunks nc ON nc.id = pcr.chunk_id
        JOIN chunk_metadata cm ON cm.chunk_id = nc.id
        WHERE pcr.reference_type = 'setting'
          AND {playable_narrative_predicate()}
    )
    SELECT pcr.place_id, p.name, pcr.chunk_id
    FROM place_chunk_references pcr
    JOIN places p ON p.id = pcr.place_id
    JOIN latest ON latest.chunk_id = pcr.chunk_id
    WHERE pcr.reference_type = 'setting'
    ORDER BY pcr.place_id
"""

_PLAYABLE_SQL = (
    "SELECT nc.id"
    + _CHUNK_FIELDS_SQL.format(predicate=playable_narrative_predicate())
    + "AND nc.id = ANY(%s)"
)

_SETTING_PAIRS_SQL = """
    SELECT pcr.chunk_id, pcr.place_id
    FROM place_chunk_references pcr
    JOIN places p ON p.id = pcr.place_id
    WHERE pcr.reference_type = 'setting' AND pcr.chunk_id = ANY(%s)
"""

_PRESENT_PAIRS_SQL = """
    SELECT ccr.chunk_id, ccr.character_id
    FROM chunk_character_references ccr
    JOIN characters c ON c.id = ccr.character_id
    WHERE ccr.reference = 'present' AND ccr.chunk_id = ANY(%s)
"""


def _fetchall(cur: Any, query: str, params: Tuple[Any, ...] = ()) -> List[Any]:
    """Run one read and return its rows."""
    cur.execute(query, params)
    return list(cur.fetchall())


def load_return_recap(
    conn: Any, *, hiatus_hours: float, roster_limit: int
) -> ReturnRecap:
    """Read committed canon for the recap, compose it, and verify its sources.

    Args:
        conn: A psycopg2 connection to the slot database. Every read runs in
            its current transaction; nothing is written.
        hiatus_hours: Hours of absence after which the recap is due.
        roster_limit: Most present characters to name.

    Returns:
        The verified recap.

    Raises:
        RuntimeError: If the slot has no ``global_variables`` row.
        RecapEvidenceError: If a composed item cites an unverifiable row.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(_GLOBAL_SQL)
        global_row = cur.fetchone()
        if global_row is None:
            raise RuntimeError(
                "global_variables row id=true is missing; cannot build a recap"
            )
        frontier_rows = _fetchall(cur, _FRONTIER_SQL)
        action_rows = _fetchall(cur, _LAST_ACTION_SQL)
        setting_rows = _fetchall(cur, _SETTING_SQL)

    frontier = (
        FrontierRow(
            chunk_id=int(frontier_rows[0]["id"]),
            choice_text=frontier_rows[0]["choice_text"],
            choice_object=frontier_rows[0]["choice_object"],
        )
        if frontier_rows
        else None
    )
    last_action = (
        ActionRow(
            chunk_id=int(action_rows[0]["id"]),
            choice_text=str(action_rows[0]["choice_text"]),
        )
        if action_rows
        else None
    )
    setting = (
        SettingRows(
            chunk_id=int(setting_rows[0]["chunk_id"]),
            places=tuple(
                NamedRow(id=int(row["place_id"]), name=str(row["name"]))
                for row in setting_rows
            ),
        )
        if setting_rows
        else None
    )
    roster = None
    if frontier is not None:
        present = read_roster(conn, frontier.chunk_id).present.values()
        roster = RosterRows(
            chunk_id=frontier.chunk_id,
            characters=tuple(
                NamedRow(id=required_id(entry), name=entry.name)
                for entry in present
                if entry.kind == "character"
            ),
        )

    recap = compose_recap(
        last_played=global_row["last_played"],
        now=global_row["checked_at"],
        hiatus_hours=hiatus_hours,
        roster_limit=roster_limit,
        setting=setting,
        roster=roster,
        last_action=last_action,
        frontier=frontier,
    )
    verify_recap_sources(conn, recap)
    return recap


def verify_recap_sources(conn: Any, recap: ReturnRecap) -> None:
    """Check every cited handle against committed, playable rows.

    Each item cites exactly one chunk: a playable committed chunk the reader
    serves. A location's places must be settings of that chunk, and a
    roster's characters must be present on it.

    Raises:
        RecapEvidenceError: Naming every handle that failed verification.
    """
    chunk_ids: Set[int] = set()
    for item in recap.items:
        cited = [source.id for source in item.sources if source.kind == "chunk"]
        if len(cited) != 1:
            raise RecapEvidenceError(
                f"Recap {item.kind} item must cite exactly one chunk, got {cited}"
            )
        chunk_ids.add(cited[0])
    if not chunk_ids:
        return

    ids = sorted(chunk_ids)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        playable = {int(row["id"]) for row in _fetchall(cur, _PLAYABLE_SQL, (ids,))}
        settings = {
            (int(row["chunk_id"]), int(row["place_id"]))
            for row in _fetchall(cur, _SETTING_PAIRS_SQL, (ids,))
        }
        present = {
            (int(row["chunk_id"]), int(row["character_id"]))
            for row in _fetchall(cur, _PRESENT_PAIRS_SQL, (ids,))
        }

    evidence: Dict[str, Set[Tuple[int, int]]] = {
        "place": settings,
        "character": present,
    }
    failures: List[str] = []
    for item in recap.items:
        (chunk_id,) = [s.id for s in item.sources if s.kind == "chunk"]
        if chunk_id not in playable:
            failures.append(f"{item.kind}: chunk {chunk_id}")
        for source in item.sources:
            if source.kind == "chunk":
                continue
            if (chunk_id, source.id) not in evidence[source.kind]:
                failures.append(
                    f"{item.kind}: {source.kind} {source.id} on chunk {chunk_id}"
                )
    if failures:
        raise RecapEvidenceError(
            "Recap cites rows that are not committed canon: " + "; ".join(failures)
        )
