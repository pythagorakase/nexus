"""Resolve character declarations before any persistent identity is minted."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from difflib import SequenceMatcher
import unicodedata
from typing import Any, Literal, Mapping, Sequence

from nexus.api.native_structured_output import WireContractViolation
from nexus.config import load_settings
from nexus.config.settings_models import CharacterIdentitySettings
from nexus.presence.roster import IdentityIndex, RosterEntry, _rows


@dataclass(frozen=True)
class IdentityResolution:
    """One exact binding, an explicit review requirement, or a novel name."""

    status: Literal["resolved", "ambiguous", "novel"]
    existing_id: int | None = None
    candidates: tuple[RosterEntry, ...] = ()
    reason: str = ""


class CharacterIdentityAmbiguity(WireContractViolation):
    """Terminal identity rejection; provider retries cannot adjudicate people."""

    def __init__(self, name: str, result: IdentityResolution) -> None:
        self.name = name
        self.candidates = result.candidates
        self.reason = result.reason
        super().__init__(
            f"Ambiguous character declaration {name!r}: {result.reason}; candidates: "
            + ", ".join(f"{c.name} ({c.kind} id={c.id})" for c in result.candidates)
            + ". Review requires same_as, create_new, or distinct_from."
        )


def _normalize(name: str, cfg: CharacterIdentitySettings) -> str:
    value = " ".join(name.split())
    if cfg.case_folding:
        value = value.casefold()
    if cfg.strip_diacritics:
        value = "".join(
            char
            for char in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(char)
        )
    return value


def _normalized_name(name: str, cfg: CharacterIdentitySettings) -> str:
    """Apply the same configured title normalization to either side of a match."""
    parts = _normalize(name, cfg).split()
    titles = {_normalize(title, cfg).rstrip(".") for title in cfg.titles}
    if cfg.strip_titles and parts and parts[0].rstrip(".") in titles:
        parts = parts[1:]
    return " ".join(parts)


def alias_forms(name: str, cfg: CharacterIdentitySettings) -> set[str]:
    """Return deterministic first, surname, and authored-title forms."""
    parts = name.split()
    if not parts:
        return set()
    title = None
    if cfg.strip_titles and parts[0].rstrip(".").casefold() in cfg.titles:
        title, parts = parts[0], parts[1:]
    if not parts:
        return set()
    forms = {parts[0], parts[-1], " ".join(parts)}
    if title:
        forms.add(f"{title} {parts[-1]}")
    return forms - {name}


def resolve_character_declaration(
    declaration: Mapping[str, Any],
    index: IdentityIndex,
    *,
    descriptors: str | None = None,
    role: str | None = None,
    scene_location: str | None = None,
    settings: CharacterIdentitySettings | None = None,
) -> IdentityResolution:
    """Bind exact names/aliases only; partial and fuzzy evidence needs review.

    Descriptors, role, and location can narrow review candidates. They never
    turn a near match or a collision into an automatic identity binding.
    """
    cfg = settings or load_settings().character_identity
    name = str(declaration["name"])
    kind = str(declaration.get("kind", "character"))
    normalized = _normalized_name(name, cfg)
    descriptors = descriptors or declaration.get("descriptors")
    role = role or declaration.get("role")
    declared_location = declaration.get("scene_location")
    locations = list(
        dict.fromkeys(value for value in (scene_location, declared_location) if value)
    )
    exact: set[tuple] = set()
    near: set[tuple] = set()
    for candidate_kind, label, key in index.labels:
        if _normalized_name(label, cfg) == normalized:
            is_exact = candidate_kind == kind and _normalize(label, cfg) == _normalize(
                name, cfg
            )
            (exact if is_exact else near).add(key)
    if not exact:
        for _, label, key in index.labels:
            if (
                SequenceMatcher(None, normalized, _normalized_name(label, cfg)).ratio()
                >= cfg.fuzzy_threshold
            ):
                near.add(key)
    # Detect shared surnames even when collision avoidance withheld that alias.
    for key, candidate in index.by_id.items():
        forms = alias_forms(candidate.name, cfg)
        if any(_normalized_name(form, cfg) == normalized for form in forms):
            near.add(key)
    location_conflict = False
    if len(exact) == 1 and not (near - exact):
        key = next(iter(exact))
        existing_location = index.evidence.get(key, {}).get("current_location")
        location_conflict = bool(
            existing_location
            and any(
                _normalize(str(existing_location), cfg)
                != _normalize(str(location), cfg)
                for location in locations
            )
        )
        if not location_conflict:
            return IdentityResolution("resolved", existing_id=index.by_id[key].id)
    candidates = exact | near
    if candidates:
        reason = (
            "location conflict"
            if location_conflict
            else ("name or alias collision" if exact else "partial or fuzzy name match")
        )
        evidence = [str(value) for value in (descriptors, role, *locations) if value]
        for field, value in (
            ("summary", descriptors),
            ("role", role),
            *(("current_location", location) for location in locations),
        ):
            if not value:
                continue
            supported = {
                key
                for key in candidates
                if _normalize(str(value), cfg)
                in _normalize(str(index.evidence.get(key, {}).get(field) or ""), cfg)
            }
            if supported:
                candidates = supported
        if evidence:
            reason += "; declared evidence: " + "; ".join(evidence)
        return IdentityResolution(
            "ambiguous",
            candidates=tuple(index.by_id[key] for key in sorted(candidates)),
            reason=reason,
        )
    return IdentityResolution("novel")


def validate_character_batch(
    declarations: Sequence[Mapping[str, Any]],
    index: IdentityIndex,
    *,
    scene_location: str | None = None,
) -> None:
    """Validate against catalog plus earlier novel declarations before any writes."""
    # Copy mutable index containers; database row records are read-only evidence.
    index = copy(index)
    index.by_id = dict(index.by_id)
    index.by_name = {key: set(keys) for key, keys in index.by_name.items()}
    index.labels = list(index.labels)
    index.evidence = dict(index.evidence)
    provisional_id = min([0, *(entry.id for entry in index.by_id.values())]) - 1
    for declaration in declarations:
        if declaration.get("kind", "character") != "character":
            continue
        result = resolve_character_declaration(
            declaration,
            index,
            descriptors=declaration.get("summary"),
            scene_location=scene_location,
        )
        if result.status == "ambiguous":
            raise CharacterIdentityAmbiguity(str(declaration["name"]), result)
        if result.status == "novel":
            entry = RosterEntry(
                kind="character", id=provisional_id, name=str(declaration["name"])
            )
            provisional_id -= 1
            index.by_id[entry.key] = entry
            index.labels.append((entry.kind, entry.name, entry.key))
            index.by_name.setdefault((entry.kind, entry.name.casefold()), set()).add(
                entry.key
            )
            index.evidence[entry.key] = {
                **declaration,
                "current_location": declaration.get("scene_location") or scene_location,
            }


_CHARACTER_SQL = "SELECT c.id, c.name, c.entity_id, c.summary, p.name AS current_location FROM characters c LEFT JOIN places p ON p.id = c.current_location WHERE c.name IS NOT NULL"
_ALIAS_SQL = "SELECT character_id, alias FROM character_aliases"
_OTHER_SQL = "SELECT 'place' AS kind, id, name, entity_id, summary FROM places UNION ALL SELECT 'faction' AS kind, id, name, entity_id, summary FROM factions"


def identity_index(
    characters: Sequence[Mapping[str, Any]], aliases: Sequence[Mapping[str, Any]]
) -> IdentityIndex:
    """Use the roster's catalog and alias index for declaration resolution."""
    return IdentityIndex(
        [
            RosterEntry(
                kind=row.get("kind", "character"),
                **{
                    k: row[k]
                    for k in ("id", "name", "entity_id", "summary")
                    if k in row
                },
            )
            for row in characters
        ],
        aliases,
        evidence={
            (row.get("kind", "character"), int(row["id"])): row for row in characters
        },
    )


def read_identity_index(conn: Any) -> IdentityIndex:
    """Read identities within the caller's existing transaction."""
    return identity_index(
        _rows(conn, _CHARACTER_SQL, {}) + _rows(conn, _OTHER_SQL, {}),
        _rows(conn, _ALIAS_SQL, {}),
    )


async def read_identity_index_async(conn: Any) -> IdentityIndex:
    """Read the same identity catalog through an async acceptance transaction."""
    return identity_index(
        list(await conn.fetch(_CHARACTER_SQL)) + list(await conn.fetch(_OTHER_SQL)),
        await conn.fetch(_ALIAS_SQL),
    )


def require_character_identity(
    conn: Any,
    name: str,
    *,
    descriptors: str | None = None,
    scene_location: str | None = None,
    declared_location: str | None = None,
) -> RosterEntry | None:
    """Serialize pre-insert resolution and return the exact existing binding."""
    _rows(
        conn,
        "SELECT pg_advisory_xact_lock(hashtext(current_database()), hashtext('character-identity'))",
        {},
    )
    index = read_identity_index(conn)
    result = resolve_character_declaration(
        {"name": name, "scene_location": declared_location},
        index,
        descriptors=descriptors,
        scene_location=scene_location,
    )
    if result.status == "ambiguous":
        raise CharacterIdentityAmbiguity(name, result)
    return (
        index.by_id[("character", result.existing_id)]
        if result.existing_id is not None
        else None
    )


async def require_character_identity_async(
    conn: Any,
    name: str,
    *,
    descriptors: str | None = None,
    scene_location: str | None = None,
    declared_location: str | None = None,
) -> RosterEntry | None:
    """Apply the same resolver within an asyncpg acceptance transaction."""
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext(current_database()), hashtext('character-identity'))"
    )
    index = await read_identity_index_async(conn)
    result = resolve_character_declaration(
        {"name": name, "scene_location": declared_location},
        index,
        descriptors=descriptors,
        scene_location=scene_location,
    )
    if result.status == "ambiguous":
        raise CharacterIdentityAmbiguity(name, result)
    return (
        index.by_id[("character", result.existing_id)]
        if result.existing_id is not None
        else None
    )


def generated_aliases(index: IdentityIndex) -> list[tuple[int, str]]:
    """Generate only forms owned by exactly one identity in the entire slot."""
    cfg = load_settings().character_identity
    owners: dict[str, set[int]] = {}
    forms: dict[int, set[str]] = {}
    for key, entry in index.by_id.items():
        if entry.kind != "character":
            continue
        forms[entry.id] = alias_forms(entry.name, cfg)
        for label in forms[entry.id] | {entry.name}:
            owners.setdefault(_normalize(label, cfg), set()).add(entry.id)
    for (kind, label), keys in index.by_name.items():
        if kind != "character":
            continue
        owners.setdefault(_normalize(label, cfg), set()).update(
            int(key[1]) for key in keys
        )
    return sorted(
        (character_id, alias)
        for character_id, labels in forms.items()
        for alias in labels
        if owners[_normalize(alias, cfg)] == {character_id}
    )


def refresh_generated_aliases(conn: Any) -> None:
    """Recompute collision-free generated aliases, preserving authored aliases."""
    _rows(
        conn,
        "DELETE FROM character_aliases WHERE provenance = 'generated' RETURNING character_id",
        {},
    )
    for character_id, alias in generated_aliases(read_identity_index(conn)):
        _rows(
            conn,
            "INSERT INTO character_aliases (character_id, alias, provenance) VALUES (:id, :alias, 'generated') ON CONFLICT DO NOTHING RETURNING character_id",
            {"id": character_id, "alias": alias},
        )


async def refresh_generated_aliases_async(conn: Any) -> None:
    """Recompute generated aliases through the async acceptance transaction."""
    await conn.execute("DELETE FROM character_aliases WHERE provenance = 'generated'")
    index = identity_index(
        list(await conn.fetch(_CHARACTER_SQL)) + list(await conn.fetch(_OTHER_SQL)),
        await conn.fetch(_ALIAS_SQL),
    )
    for character_id, alias in generated_aliases(index):
        await conn.execute(
            "INSERT INTO character_aliases (character_id, alias, provenance) VALUES ($1, $2, 'generated') ON CONFLICT DO NOTHING",
            character_id,
            alias,
        )
