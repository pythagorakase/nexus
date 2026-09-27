"""Evidence-linked return recap for the reader (issue #832).

A player coming back to a story sees where it stands: the current setting,
who is present, their last accepted action, and the decision still open.
The recap is deterministic. It calls no model and writes nothing back;
dismissing it is client state.

Setting, cast and last action come from committed canon. The open decision
comes from the pending draft while one waits in the incubator (the live
reading loop commits each answered draft, so the committed frontier is then
already answered), and from the committed frontier's menu otherwise.

Every item cites the rows it came from as source handles, and an item whose
source is missing is left out rather than invented. Before the recap leaves
the server, :func:`verify_recap_sources` checks each cited ID again, within
the same snapshot as the reads. Handles name only rows the player is
already served: playable committed chunks, places, characters, and the
pending draft by the session ID ``/api/slot/state`` reports with its menu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, List, Literal, Optional, Set, Tuple, Union
from uuid import UUID

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


class DraftHandle(BaseModel):
    """The pending draft a recap item cites, by its generation session ID.

    Drafts have no chunk ID until acceptance. ``/api/slot/state`` already
    serves this session ID and the draft's menu to the player.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["draft"]
    id: UUID


RecapSource = Annotated[Union[SourceHandle, DraftHandle], Field(discriminator="kind")]


class RecapItem(BaseModel):
    """One recap line and the rows it came from.

    Each item cites exactly one anchor, a chunk or the pending draft, and a
    location or roster also cites the places or characters it names.
    ``open_decision`` text holds one presented option per line.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["location", "roster", "last_action", "open_decision"]
    text: str = Field(min_length=1)
    sources: List[RecapSource] = Field(min_length=1)


class ReturnRecap(BaseModel):
    """The recap a returning player sees above the latest committed chunk."""

    model_config = ConfigDict(extra="forbid")

    due: bool
    last_played: Optional[datetime]
    items: List[RecapItem]


class RecapEvidenceError(RuntimeError):
    """A recap item cites a row that is not canon or the pending draft."""


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
class DraftRow:
    """The pending incubator draft's generation session and response fields."""

    session_id: str
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
    draft: Optional[DraftRow],
) -> ReturnRecap:
    """Build the recap from typed rows, omitting every unsourced item.

    Args:
        last_played: When the last accepted player action was recorded.
        now: The clock the hiatus is measured against.
        hiatus_hours: Hours of absence after which the recap is due.
        roster_limit: Most present characters to name.
        setting: The latest committed setting places, if any are recorded.
        roster: Characters present on the frontier chunk.
        last_action: The latest committed chunk with an accepted action.
        frontier: The latest committed playable chunk, if the story has one;
            with no draft pending, its presented options are the open
            decision until it records a response.
        draft: The pending incubator draft, if one waits. It supersedes the
            frontier's menu: its presented options are the open decision
            until it records a response.

    Returns:
        The recap, its items in location, roster, last action, open decision
        order.

    Raises:
        ValueError: If ``roster_limit`` is below one or the stored
            ``choice_object`` that decides the open decision is malformed.
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
    decision = _open_decision(frontier, draft)
    if decision is not None:
        items.append(decision)
    return ReturnRecap(
        due=is_recap_due(last_played, now, hiatus_hours),
        last_played=last_played,
        items=items,
    )


def _open_decision(
    frontier: Optional[FrontierRow], draft: Optional[DraftRow]
) -> Optional[RecapItem]:
    """The pending draft's open menu, else the frontier's, citing its row."""
    source: RecapSource
    if draft is not None:
        options = _open_options(draft.choice_text, draft.choice_object)
        source = DraftHandle(kind="draft", id=UUID(draft.session_id))
    elif frontier is not None:
        options = _open_options(frontier.choice_text, frontier.choice_object)
        source = SourceHandle(kind="chunk", id=frontier.chunk_id)
    else:
        return None
    if not options:
        return None
    return RecapItem(kind="open_decision", text="\n".join(options), sources=[source])


def _open_options(choice_text: Optional[str], raw_choice_object: Any) -> List[str]:
    """Presented options still open, or none once a response is recorded."""
    if (choice_text or "").strip():
        return []
    choice_object = normalize_choice_object(raw_choice_object)
    if choice_object is None:
        return []
    return [option.strip() for option in choice_object["presented"] if option.strip()]


_CHUNK_FIELDS_SQL = """
    FROM narrative_chunks nc
    JOIN chunk_metadata cm ON cm.chunk_id = nc.id
    WHERE {predicate}
"""

# One read-only snapshot for every read and the verification that follows,
# so a draft accepted or replaced mid-request cannot mix generations.
_SNAPSHOT_SQL = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"

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

# The incubator holds at most one draft (id is a TRUE singleton).
_DRAFT_SQL = """
    SELECT session_id::text AS session_id, choice_text, choice_object
    FROM incubator
    WHERE id = true
"""

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

_PENDING_DRAFTS_SQL = """
    SELECT session_id::text AS session_id
    FROM incubator
    WHERE session_id = ANY(%s::uuid[])
"""


def _fetchall(cur: Any, query: str, params: Tuple[Any, ...] = ()) -> List[Any]:
    """Run one read and return its rows."""
    cur.execute(query, params)
    return list(cur.fetchall())


def load_return_recap(
    conn: Any, *, hiatus_hours: float, roster_limit: int
) -> ReturnRecap:
    """Read the recap's rows, compose it, and verify its sources.

    Args:
        conn: A psycopg2 connection to the slot database with no transaction
            in progress. Every read, and the verification, runs in one
            read-only REPEATABLE READ transaction; nothing is written.
        hiatus_hours: Hours of absence after which the recap is due.
        roster_limit: Most present characters to name.

    Returns:
        The verified recap.

    Raises:
        RuntimeError: If the slot has no ``global_variables`` row.
        RecapEvidenceError: If a composed item cites an unverifiable row.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(_SNAPSHOT_SQL)
        cur.execute(_GLOBAL_SQL)
        global_row = cur.fetchone()
        if global_row is None:
            raise RuntimeError(
                "global_variables row id=true is missing; cannot build a recap"
            )
        frontier_rows = _fetchall(cur, _FRONTIER_SQL)
        draft_rows = _fetchall(cur, _DRAFT_SQL)
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
    draft = (
        DraftRow(
            session_id=str(draft_rows[0]["session_id"]),
            choice_text=draft_rows[0]["choice_text"],
            choice_object=draft_rows[0]["choice_object"],
        )
        if draft_rows
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
        draft=draft,
    )
    verify_recap_sources(conn, recap)
    return recap


def verify_recap_sources(conn: Any, recap: ReturnRecap) -> None:
    """Check every cited handle against committed, playable rows or the draft.

    Each item cites exactly one anchor: a playable committed chunk the reader
    serves, or the pending draft. A location's places must be settings of its
    chunk, and a roster's characters must be present on it; a draft anchors
    no place or character.

    Raises:
        RecapEvidenceError: Naming every handle that failed verification.
    """
    anchors: List[RecapSource] = []
    for item in recap.items:
        cited = [s for s in item.sources if s.kind in ("chunk", "draft")]
        if len(cited) != 1:
            raise RecapEvidenceError(
                f"Recap {item.kind} item must cite exactly one chunk or draft, "
                f"got {[f'{s.kind} {s.id}' for s in cited]}"
            )
        anchors.append(cited[0])
    if not anchors:
        return

    chunk_ids = sorted({a.id for a in anchors if isinstance(a, SourceHandle)})
    draft_ids = sorted({str(a.id) for a in anchors if isinstance(a, DraftHandle)})
    playable: Set[int] = set()
    settings: Set[Tuple[int, int]] = set()
    present: Set[Tuple[int, int]] = set()
    pending: Set[str] = set()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if chunk_ids:
            playable = {
                int(row["id"]) for row in _fetchall(cur, _PLAYABLE_SQL, (chunk_ids,))
            }
            settings = {
                (int(row["chunk_id"]), int(row["place_id"]))
                for row in _fetchall(cur, _SETTING_PAIRS_SQL, (chunk_ids,))
            }
            present = {
                (int(row["chunk_id"]), int(row["character_id"]))
                for row in _fetchall(cur, _PRESENT_PAIRS_SQL, (chunk_ids,))
            }
        if draft_ids:
            pending = {
                str(row["session_id"])
                for row in _fetchall(cur, _PENDING_DRAFTS_SQL, (draft_ids,))
            }

    evidence: Dict[str, Set[Tuple[int, int]]] = {
        "place": settings,
        "character": present,
    }
    failures: List[str] = []
    for item, anchor in zip(recap.items, anchors):
        if isinstance(anchor, DraftHandle):
            if str(anchor.id) not in pending:
                failures.append(f"{item.kind}: draft {anchor.id}")
        elif anchor.id not in playable:
            failures.append(f"{item.kind}: chunk {anchor.id}")
        for source in item.sources:
            if isinstance(source, DraftHandle) or source.kind == "chunk":
                continue
            if isinstance(anchor, DraftHandle) or (
                (anchor.id, source.id) not in evidence[source.kind]
            ):
                failures.append(
                    f"{item.kind}: {source.kind} {source.id} on "
                    f"{anchor.kind} {anchor.id}"
                )
    if failures:
        raise RecapEvidenceError(
            "Recap cites rows that are not verifiable sources: " + "; ".join(failures)
        )
