"""ID-first scene rosters shared by prompts, cognition, and persistence.

IDs are the kind-specific character/place/faction IDs, never spine entity IDs.
Name keys exist only while a wire reference awaits identity resolution.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

if TYPE_CHECKING:
    from nexus.agents.logon.skald_wire import (
        PresenceBaseline,
        PresenceDelta,
        PresenceRef,
    )

Kind = Literal["character", "place", "faction"]
RosterKey = tuple[Kind, int | str]


class RosterEntry(BaseModel):
    """One named identity, optionally carrying its Orrery spine identity."""

    kind: Kind
    id: int | None = None
    name: str = Field(min_length=1)
    entity_id: int | None = None
    is_active: bool = True
    summary: str | None = None
    evidence: str | None = None
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    @property
    def key(self) -> RosterKey:
        """Return the canonical key, falling back only before resolution."""
        return self.kind, self.id if self.id is not None else self.name.casefold()


class PresenceRoster(BaseModel):
    """Disjoint scene views; transitioning records the wire's transit places."""

    present: dict[RosterKey, RosterEntry] = Field(default_factory=dict)
    transitioning: dict[RosterKey, RosterEntry] = Field(default_factory=dict)
    referenced: dict[RosterKey, RosterEntry] = Field(default_factory=dict)
    setting: dict[RosterKey, RosterEntry] = Field(default_factory=dict)

    @property
    def all_references(self) -> dict[RosterKey, RosterEntry]:
        """Return every reference, including the physical roster and setting."""
        return {**self.referenced, **self.transitioning, **self.setting, **self.present}

    @property
    def present_character_ids(self) -> set[int]:
        """Return physical character IDs, refusing unresolved scene identities."""
        return {required_id(entry) for entry in self.present.values()}

    @property
    def present_entity_ids(self) -> set[int]:
        """Return active physical characters' Orrery spine IDs."""
        return {
            entry.entity_id
            for entry in self.present.values()
            if entry.entity_id is not None and entry.is_active
        }


def required_id(entry: RosterEntry) -> int:
    """Require resolution before persistence or identity-sensitive reads."""
    if entry.id is None:
        raise ValueError(f"Unresolved {entry.kind} reference: {entry.name!r}")
    return entry.id


def _entry(reference: PresenceRef | RosterEntry) -> RosterEntry:
    if isinstance(reference, RosterEntry):
        return reference
    return RosterEntry.model_validate(reference.model_dump())


def roster_from_baseline(baseline: PresenceBaseline) -> PresenceRoster:
    """Adapt the provider-facing parent baseline into the owner representation."""
    entries = [_entry(ref) for ref in baseline.present]
    setting = _entry(baseline.setting) if baseline.setting is not None else None
    return PresenceRoster(
        present={entry.key: entry for entry in entries},
        setting={setting.key: setting} if setting is not None else {},
    )


def apply_delta(
    roster: PresenceRoster,
    delta: PresenceDelta | None,
    *,
    resolve: Callable[[RosterEntry], RosterEntry] | None = None,
) -> PresenceRoster:
    """Apply sparse wire changes; an exit from outside the roster is an error."""

    def canonical(reference: Any) -> RosterEntry:
        entry = _entry(reference)
        return resolve(entry) if resolve is not None else entry

    def keyed(references: Iterable[Any]) -> dict[RosterKey, RosterEntry]:
        return {entry.key: entry for entry in map(canonical, references)}

    present = keyed(roster.present.values())
    setting = keyed(roster.setting.values())
    transitioning = keyed(delta.transit if delta is not None else [])
    referenced = keyed(delta.mentions if delta is not None else [])
    crossings: dict[RosterKey, RosterEntry] = {}
    if delta is not None:
        enters = keyed(delta.enter)
        exits = keyed(delta.exit)
        # Only catalog-resolved identities may cancel. Never infer an exit ID
        # from the other entries on the wire: those are not the catalog.
        for entry in exits.values():
            required_id(entry)
        crossings = {key: entry for key, entry in enters.items() if key in exits}
        if delta.scene_reset is not None:
            present = keyed(delta.scene_reset.present)
            setting = keyed([delta.scene_reset.place])
        else:
            present.update(
                {key: entry for key, entry in enters.items() if key not in crossings}
            )
            for key, entry in exits.items():
                if key in crossings:
                    continue
                if key not in present:
                    raise ValueError(
                        f"Cannot exit non-present {entry.kind} {entry.name!r} (id={entry.id})"
                    )
                del present[key]
    referenced = {**crossings, **referenced}
    for key in present | setting:
        transitioning.pop(key, None)
    for key in present | setting | transitioning:
        referenced.pop(key, None)
    return PresenceRoster(
        present=present,
        setting=setting,
        transitioning=transitioning,
        referenced=referenced,
    )


_REFERENCE_SQL = """
    /* presence:roster */
    WITH refs AS (
        SELECT r.chunk_id, 'character' AS kind, c.id, c.name, c.summary,
               c.entity_id, e.is_active, r.reference::text AS reference,
               NULL::text AS evidence
        FROM chunk_character_references r
        JOIN characters c ON c.id = r.character_id
        LEFT JOIN entities e ON e.id = c.entity_id
        WHERE r.chunk_id = ANY(:chunk_ids)
        UNION ALL
        SELECT r.chunk_id, 'place', p.id, p.name, p.summary, p.entity_id,
               e.is_active, r.reference_type::text, r.evidence
        FROM place_chunk_references r
        JOIN places p ON p.id = r.place_id
        LEFT JOIN entities e ON e.id = p.entity_id
        WHERE r.chunk_id = ANY(:chunk_ids)
        UNION ALL
        SELECT r.chunk_id, 'faction', f.id, f.name, f.summary, f.entity_id,
               e.is_active, 'mentioned', NULL::text
        FROM chunk_faction_references r
        JOIN factions f ON f.id = r.faction_id
        LEFT JOIN entities e ON e.id = f.entity_id
        WHERE r.chunk_id = ANY(:chunk_ids)
    )
    SELECT nc.id AS chunk_id, refs.kind, refs.id, refs.name, refs.summary,
           refs.entity_id, refs.is_active, refs.reference, refs.evidence
    FROM narrative_chunks nc LEFT JOIN refs ON refs.chunk_id = nc.id
    WHERE nc.id = ANY(:chunk_ids)
    ORDER BY nc.id, refs.kind, refs.id
"""


def _rows(conn: Any, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Read through the existing psycopg or SQLAlchemy transaction."""
    if hasattr(conn, "cursor"):
        with conn.cursor() as cur:
            return _rows(cur, query, params)
    if hasattr(conn, "fetchall"):
        conn.execute(re.sub(r"(?<![\w:]):(\w+)", r"%(\1)s", query), params)
        names = [column[0] for column in conn.description]
        return [
            dict(row) if isinstance(row, Mapping) else dict(zip(names, row))
            for row in conn.fetchall()
        ]
    return [dict(row) for row in conn.execute(text(query), params).mappings()]


def _rosters(
    rows: Iterable[Mapping[str, Any]], chunk_ids: Iterable[int]
) -> dict[int, PresenceRoster]:
    rosters: dict[int, PresenceRoster] = {}
    for row in rows:
        roster = rosters.setdefault(int(row["chunk_id"]), PresenceRoster())
        if row["kind"] is None:
            continue
        entry = RosterEntry(
            **{
                key: row[key]
                for key in ("kind", "id", "name", "summary", "entity_id", "evidence")
            },
            is_active=bool(row["is_active"]),
        )
        view = {
            "present": roster.present,
            "setting": roster.setting,
            "transit": roster.transitioning,
        }.get(row["reference"], roster.referenced)
        view[entry.key] = entry
    missing = set(chunk_ids) - rosters.keys()
    if missing:
        raise ValueError(f"Cannot read roster for missing chunks: {sorted(missing)}")
    for chunk_id, roster in rosters.items():
        if len(roster.setting) > 1:
            raise ValueError(f"Chunk {chunk_id} has multiple setting places")
        for key in roster.present | roster.setting | roster.transitioning:
            roster.referenced.pop(key, None)
    return rosters


def read_rosters(conn: Any, chunk_ids: Iterable[int]) -> dict[int, PresenceRoster]:
    """Read named scene views for a batch of chunks with one database query."""
    ids = sorted(set(chunk_ids))
    if not ids:
        return {}
    return _rosters(_rows(conn, _REFERENCE_SQL, {"chunk_ids": ids}), ids)


def read_roster(conn: Any, chunk_id: int) -> PresenceRoster:
    """Read exactly one committed chunk's canonical scene roster."""
    return read_rosters(conn, [chunk_id])[chunk_id]


async def read_roster_async(conn: Any, chunk_id: int) -> PresenceRoster:
    """Read the same roster through an existing asyncpg transaction."""
    rows = await conn.fetch(_REFERENCE_SQL.replace(":chunk_ids", "$1"), [chunk_id])
    return _rosters(rows, [chunk_id])[chunk_id]


def render_roster(
    roster: PresenceRoster, *, player_character_id: int | None = None
) -> str:
    """Render the compact writer frontier with the canonical player identified."""
    names = [
        entry.name + (" (player)" if entry.id == player_character_id else "")
        for entry in roster.present.values()
    ]
    setting = next(iter(roster.setting.values()), None)
    return f"PRESENT: {', '.join(names) or '(none)'} · SETTING: {setting.name if setting else '(none)'}"


class IdentityIndex:
    """Resolve canonical names and stored aliases without choosing an ambiguity."""

    def __init__(
        self, entries: Iterable[RosterEntry], aliases: Iterable[Mapping[str, Any]] = ()
    ) -> None:
        self.by_id = {entry.key: entry for entry in entries}
        self.by_name: dict[tuple[str, str], set[RosterKey]] = {}
        for entry in self.by_id.values():
            self.by_name.setdefault((entry.kind, entry.name.casefold()), set()).add(
                entry.key
            )
        for alias in aliases:
            key: RosterKey = ("character", int(alias["character_id"]))
            if key in self.by_id:
                self.by_name.setdefault(
                    ("character", str(alias["alias"]).casefold()), set()
                ).add(key)

    def resolve(self, entry: RosterEntry) -> RosterEntry:
        """Resolve an ID first, then an unambiguous canonical name or alias."""
        if entry.id is not None:
            return self.by_id.get(entry.key, entry)
        keys = self.by_name.get((entry.kind, entry.name.casefold()), set())
        if len(keys) > 1:
            raise ValueError(
                f"Ambiguous {entry.kind} name {entry.name!r}: {sorted(keys)}"
            )
        return self.by_id[next(iter(keys))] if keys else entry


def character_identity_index(
    character_rows: Iterable[Mapping[str, Any]], alias_rows: Iterable[Mapping[str, Any]]
) -> IdentityIndex:
    """Build the character resolver from the turn's already-prefetched catalog."""
    return IdentityIndex(
        (
            RosterEntry(kind="character", id=int(row["id"]), name=row["name"])
            for row in character_rows
        ),
        alias_rows,
    )


def _resolution_query(
    kind: Kind, id: int | None, name: str | None
) -> tuple[str, dict[str, Any]]:
    table = {"character": "characters", "place": "places", "faction": "factions"}[kind]
    if id is not None:
        predicate, params = "item.id = :id", {"id": id}
    else:
        predicate, params = "lower(item.name) = lower(:name)", {"name": name}
        if kind == "character":
            predicate += " OR EXISTS (SELECT 1 FROM character_aliases a WHERE a.character_id = item.id AND lower(a.alias) = lower(:name))"
    return (
        f"SELECT item.id, item.name, item.entity_id FROM {table} item WHERE {predicate}",
        params,
    )


def _resolved_entry(
    rows: list[Any], kind: Kind, id: int | None, name: str | None
) -> RosterEntry:
    if len(rows) != 1:
        raise ValueError(
            f"{'Ambiguous' if rows else 'Unresolved'} {kind} reference id={id} name={name!r}: {[row['id'] for row in rows]}"
        )
    return RosterEntry(kind=kind, **dict(rows[0]))


def resolve_reference(
    conn: Any, *, kind: Kind, id: int | None, name: str | None
) -> RosterEntry:
    """Resolve a persistent reference, including aliases, or fail loudly."""
    query, params = _resolution_query(kind, id, name)
    return _resolved_entry(_rows(conn, query, params), kind, id, name)


async def resolve_reference_async(
    conn: Any, *, kind: Kind, id: int | None, name: str | None
) -> RosterEntry:
    """Resolve a reference through an existing asyncpg transaction."""
    query, params = _resolution_query(kind, id, name)
    rows = await conn.fetch(
        re.sub(r"(?<![\w:]):(\w+)", "$1", query), next(iter(params.values()))
    )
    return _resolved_entry(list(rows), kind, id, name)


def roster_from_resolved_references(
    character_refs: Iterable[Mapping[str, Any]],
    place_refs: Iterable[Mapping[str, Any]],
    faction_refs: Iterable[Mapping[str, Any]],
) -> PresenceRoster:
    """Build a write roster from commit's resolved canonical references."""
    roster = PresenceRoster()
    for kind, references in (
        ("character", character_refs),
        ("place", place_refs),
        ("faction", faction_refs),
    ):
        for ref in references:
            entry = RosterEntry(
                kind=kind,
                id=ref[f"{kind}_id"],
                name=ref["name"],
                evidence=ref.get("evidence"),
            )
            reference = ref.get("reference", ref.get("reference_type", "mentioned"))
            view = {
                "present": roster.present,
                "setting": roster.setting,
                "transit": roster.transitioning,
            }.get(reference, roster.referenced)
            view[entry.key] = entry
    if len(roster.setting) > 1:
        raise ValueError("Cannot write multiple setting places")
    for key in roster.present | roster.setting | roster.transitioning:
        roster.referenced.pop(key, None)
    return roster


def _write_statements(
    chunk_id: int, roster: PresenceRoster
) -> Iterable[tuple[str, dict[str, Any]]]:
    for reference, view in (
        ("mentioned", roster.referenced),
        ("transit", roster.transitioning),
        ("setting", roster.setting),
        ("present", roster.present),
    ):
        for entry in view.values():
            params = {
                "chunk_id": chunk_id,
                "id": required_id(entry),
                "reference": reference,
            }
            if entry.kind == "character":
                query = """INSERT INTO chunk_character_references (chunk_id, character_id, reference)
                    VALUES (:chunk_id, :id, :reference)
                    ON CONFLICT (chunk_id, character_id) DO UPDATE SET reference = EXCLUDED.reference"""
            elif entry.kind == "place":
                params["evidence"] = entry.evidence
                query = """INSERT INTO place_chunk_references (chunk_id, place_id, reference_type, evidence)
                    VALUES (:chunk_id, :id, :reference, :evidence)
                    ON CONFLICT (place_id, chunk_id, reference_type) DO UPDATE SET evidence = EXCLUDED.evidence"""
            else:
                params.pop("reference")
                query = """INSERT INTO chunk_faction_references (chunk_id, faction_id)
                    VALUES (:chunk_id, :id) ON CONFLICT (chunk_id, faction_id) DO NOTHING"""
            yield query, params


def write_roster(conn: Any, chunk_id: int, roster: PresenceRoster) -> None:
    """Upsert a resolved roster in the caller's transaction."""
    with conn.cursor() as cur:
        for query, params in _write_statements(chunk_id, roster):
            cur.execute(re.sub(r"(?<![\w:]):(\w+)", r"%(\1)s", query), params)


async def write_roster_async(conn: Any, chunk_id: int, roster: PresenceRoster) -> None:
    """Upsert the same roster through the asyncpg commit route."""
    for query, params in _write_statements(chunk_id, roster):
        keys = list(params)
        query = re.sub(
            r"(?<![\w:]):(\w+)", lambda match: f"${keys.index(match[1]) + 1}", query
        )
        await conn.execute(query, *(params[key] for key in keys))
