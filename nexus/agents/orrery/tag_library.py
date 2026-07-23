"""Prompt-facing Orrery tag library helpers."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import os
import re
from typing import Iterator, Literal, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.resolver import (
    load_anchor_world_time,
    load_current_entity_tags,
)
from nexus.api.slot_utils import get_slot_db_url

VALID_ENTITY_KINDS = frozenset({"character", "faction", "place"})
_SLOT_DB_RE = re.compile(r"^save_0[1-5]$")
EntityKind = Literal["character", "faction", "place"]


@dataclass(frozen=True, slots=True)
class TagLibraryEntry:
    """One registered tag exposed to Skald as reusable vocabulary."""

    entity_kind: str
    category: str
    tag: str
    is_ephemeral: bool
    description: str
    category_description: str
    prompt_order: int


@dataclass(frozen=True, slots=True)
class EntityRowReference:
    """One kind-scoped subtype row ID, before canonical entity translation."""

    kind: EntityKind
    row_id: int


@dataclass(frozen=True, slots=True)
class TagLibraryContext:
    """Scene state that selects which registered tags receive descriptions.

    ``present_entity_refs`` deliberately carries kind-scoped subtype row IDs.
    The active-tag lookup owns translation to ``entities.id`` so no caller can
    accidentally pass a character/place/faction row ID as a canonical entity
    ID.
    """

    present_entity_refs: list[EntityRowReference]
    proposal_tag_names: set[str]
    has_pending_proposals: bool
    anchor_chunk_id: Optional[int] = None


@dataclass(frozen=True, slots=True)
class TagCategoryEntry:
    """One prompt-facing category in the closed tag taxonomy."""

    entity_kind: str
    category: str
    description: str
    prompt_order: int


@dataclass(frozen=True, slots=True)
class PairTagLibraryEntry:
    """One registered directed pair-tag exposed to Skald."""

    tag: str
    description: str


def read_tag_library(
    dbname: Optional[str] = None,
    *,
    entity_kinds: Optional[Sequence[str]] = None,
) -> list[TagLibraryEntry]:
    """Read promptable Orrery tags from the target slot database."""

    kind_filter = _normalize_entity_kinds(entity_kinds)
    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            params: list[object] = []
            where = [
                "t.deprecated = FALSE",
                "t.synonym_for IS NULL",
            ]
            if kind_filter is not None:
                where.append("r.entity_kind = ANY(%s::entity_kind[])")
                params.append(list(kind_filter))
            cur.execute(
                f"""
                SELECT
                    r.entity_kind::text AS entity_kind,
                    r.category,
                    r.description AS category_description,
                    r.prompt_order,
                    t.tag,
                    t.is_ephemeral,
                    t.description
                FROM tag_category_registry r
                JOIN tags t ON t.category = r.category
                WHERE {' AND '.join(where)}
                ORDER BY
                    r.entity_kind::text,
                    r.prompt_order,
                    r.category,
                    t.tag
                """,
                tuple(params),
            )
            return [
                TagLibraryEntry(
                    entity_kind=str(row["entity_kind"]),
                    category=str(row["category"]),
                    tag=str(row["tag"]),
                    is_ephemeral=bool(row["is_ephemeral"]),
                    description=str(row["description"] or ""),
                    category_description=str(row["category_description"] or ""),
                    prompt_order=int(row["prompt_order"]),
                )
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def read_tag_categories(dbname: Optional[str] = None) -> list[TagCategoryEntry]:
    """Read the complete prompt-facing category taxonomy."""

    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    entity_kind::text AS entity_kind,
                    category,
                    description,
                    prompt_order
                FROM tag_category_registry
                ORDER BY entity_kind::text, prompt_order, category
                """
            )
            return [
                TagCategoryEntry(
                    entity_kind=str(row["entity_kind"]),
                    category=str(row["category"]),
                    description=str(row["description"] or ""),
                    prompt_order=int(row["prompt_order"]),
                )
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def read_event_types(dbname: Optional[str] = None) -> list[str]:
    """Read active world event types from the target slot database."""

    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT type
                FROM event_types
                WHERE deprecated = FALSE
                ORDER BY type
                """
            )
            return [str(row["type"]) for row in cur.fetchall()]
    finally:
        conn.close()


def read_event_type_categories(dbname: Optional[str] = None) -> dict[str, str]:
    """Read the registry category of every active world event type."""

    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT type, category
                FROM event_types
                WHERE deprecated = FALSE
                ORDER BY type
                """
            )
            return {str(row["type"]): str(row["category"]) for row in cur.fetchall()}
    finally:
        conn.close()


def read_pair_tag_library(dbname: Optional[str] = None) -> list[str]:
    """Read active Orrery pair-tag names from the target slot database."""

    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tag
                FROM pair_tags
                WHERE deprecated = FALSE
                ORDER BY tag
                """
            )
            return [str(row["tag"]) for row in cur.fetchall()]
    finally:
        conn.close()


def read_pair_tag_entries(
    dbname: Optional[str] = None,
) -> list[PairTagLibraryEntry]:
    """Read active pair-tag names and their short semantic descriptions."""

    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tag, description
                FROM pair_tags
                WHERE deprecated = FALSE
                ORDER BY tag
                """
            )
            return [
                PairTagLibraryEntry(
                    tag=str(row["tag"]),
                    description=str(row["description"] or ""),
                )
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def read_current_entity_tag_names(
    dbname: Optional[str],
    *,
    entity_refs: Sequence[EntityRowReference],
    anchor_chunk_id: Optional[int],
) -> set[str]:
    """Read active tags for kind-scoped subtype rows at the anchor world time.

    Translation from ``characters.id`` / ``places.id`` / ``factions.id`` to
    canonical ``entities.id`` happens here, in one query. Callers therefore
    cannot accidentally select an unrelated canonical entity with the same
    numeric ID.
    """

    normalized_refs = _normalize_entity_refs(entity_refs)
    if not normalized_refs:
        return set()

    with _slot_session(dbname) as session:
        canonical_ids = _translate_entity_row_refs(session, normalized_refs)
        if not canonical_ids:
            return set()
        world_time = load_anchor_world_time(
            session,
            anchor_chunk_id=anchor_chunk_id,
        )
        durable, ephemeral = load_current_entity_tags(
            session,
            current_world_time=world_time,
        )

    return {
        tag
        for entity_id in canonical_ids
        for tag in durable.get(entity_id, set()) | ephemeral.get(entity_id, set())
    }


def format_tag_library_for_prompt(
    dbname: Optional[str] = None,
    *,
    entity_kinds: Optional[Sequence[str]] = None,
) -> str:
    """Render the live Orrery tag vocabulary for Skald's system prompt."""

    entries = read_tag_library(dbname, entity_kinds=entity_kinds)
    if not entries:
        return (
            "## Current Orrery Tag Library\n\n"
            "No registered Orrery tags are currently available in this slot. "
            "Do not invent tag names; leave `orrery_tags` empty until the "
            "slot has registered vocabulary."
        )

    by_kind: dict[str, dict[str, list[TagLibraryEntry]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for entry in entries:
        by_kind[entry.entity_kind][entry.category].append(entry)

    lines = [
        "## Current Orrery Tag Library",
        "",
        "These are the tags already registered in this slot. Prefer exact "
        "registered tags when they fit. Do not invent new tag names at runtime; "
        "omit marginal or unsupported tags instead.",
        "",
    ]
    for entity_kind in ("character", "place", "faction"):
        categories = by_kind.get(entity_kind)
        if not categories:
            continue
        lines.append(f"### {entity_kind.title()} Tags")
        lines.append("")
        for category, category_entries in sorted(
            categories.items(),
            key=lambda item: (
                item[1][0].prompt_order if item[1] else 1000,
                item[0],
            ),
        ):
            first = category_entries[0]
            tags = ", ".join(_format_tag_entry(entry) for entry in category_entries)
            if first.category_description:
                lines.append(
                    f"- `{category}` — {first.category_description} Tags: {tags}"
                )
            else:
                lines.append(f"- `{category}` — Tags: {tags}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_contextual_tag_library(
    dbname: Optional[str],
    *,
    context: TagLibraryContext,
) -> str:
    """Render a complete name index with scene-contextual descriptions."""

    entries = read_tag_library(dbname)
    categories = read_tag_categories(dbname)
    pair_entries = read_pair_tag_entries(dbname)
    event_types = read_event_types(dbname)
    active_tag_names = read_current_entity_tag_names(
        dbname,
        entity_refs=context.present_entity_refs,
        anchor_chunk_id=context.anchor_chunk_id,
    )

    by_kind: dict[str, dict[str, list[TagLibraryEntry]]] = defaultdict(
        lambda: defaultdict(list)
    )
    entries_by_name: dict[str, list[TagLibraryEntry]] = defaultdict(list)
    for entry in entries:
        by_kind[entry.entity_kind][entry.category].append(entry)
        entries_by_name[entry.tag].append(entry)

    categories_by_kind: dict[str, list[TagCategoryEntry]] = defaultdict(list)
    for category in categories:
        categories_by_kind[category.entity_kind].append(category)

    pair_tag_names = [entry.tag for entry in pair_entries]
    digest = _registry_digest(
        tag_names=[entry.tag for entry in entries],
        pair_tag_names=pair_tag_names,
        event_types=event_types,
    )
    lines = [
        "## Current Orrery Tag Library",
        "",
        f"registry digest: {digest}",
        "",
        "Every registered single-entity tag appears in the complete index; "
        "descriptions are expanded only for tags relevant to this scene.",
        "",
        "### Category Taxonomy",
        "",
    ]

    for entity_kind in ("character", "place", "faction"):
        kind_categories = categories_by_kind.get(entity_kind, [])
        if not kind_categories:
            continue
        lines.extend([f"#### {entity_kind.title()}", ""])
        for category in sorted(
            kind_categories,
            key=lambda item: (item.prompt_order, item.category),
        ):
            description = _clean_description(category.description)
            if description:
                lines.append(f"- {category.category} — {description}")
            else:
                lines.append(f"- {category.category}")
        lines.append("")

    lines.extend(["### Complete Tag-Name Index", ""])
    for entity_kind in ("character", "place", "faction"):
        kind_categories = categories_by_kind.get(entity_kind, [])
        if not kind_categories:
            continue
        lines.extend([f"#### {entity_kind.title()} Tags", ""])
        for category in sorted(
            kind_categories,
            key=lambda item: (item.prompt_order, item.category),
        ):
            names = ", ".join(
                entry.tag
                for entry in by_kind.get(entity_kind, {}).get(category.category, [])
            )
            lines.append(f"- {category.category} — {names or '(none)'}")
        lines.append("")

    lines.extend(["### Pair-Tag Names", ""])
    if pair_entries:
        for pair_entry in pair_entries:
            description = _short_description(pair_entry.description)
            if description:
                lines.append(f"- `{pair_entry.tag}` — {description}")
            else:
                lines.append(f"- `{pair_entry.tag}`")
    else:
        lines.append("(none)")
    lines.append("")

    if context.has_pending_proposals:
        lines.extend(
            [
                "### Event-Type Names",
                "",
                ", ".join(event_types) or "(none)",
                "",
            ]
        )

    relevant_names = active_tag_names | set(context.proposal_tag_names)
    relevant_entries = [
        entry
        for tag_name in sorted(relevant_names)
        for entry in entries_by_name.get(tag_name, [])
    ]
    lines.extend(["### Scene-Relevant Tags", ""])
    if relevant_entries:
        for entry in sorted(
            relevant_entries,
            key=lambda item: (
                _kind_order(item.entity_kind),
                item.prompt_order,
                item.category,
                item.tag,
            ),
        ):
            lines.append(
                f"- {entry.entity_kind}/{entry.category}: {_format_tag_entry(entry)}"
            )
    else:
        lines.append(
            "No present entity or pending proposal currently selects a full tag entry."
        )

    return "\n".join(lines).rstrip()


def _registry_digest(
    *,
    tag_names: Sequence[str],
    pair_tag_names: Sequence[str],
    event_types: Sequence[str],
) -> str:
    """Return a stable short digest over every closed vocabulary name."""

    digest_lines = [
        *(f"tag:{name}" for name in sorted(tag_names)),
        *(f"pair:{name}" for name in sorted(pair_tag_names)),
        *(f"event:{name}" for name in sorted(event_types)),
    ]
    return sha256("\n".join(digest_lines).encode("utf-8")).hexdigest()[:12]


def _kind_order(entity_kind: str) -> int:
    """Return stable prompt ordering for registered entity kinds."""

    try:
        return ("character", "place", "faction").index(entity_kind)
    except ValueError:
        return 1000


def _normalize_entity_kinds(
    entity_kinds: Optional[Sequence[str]],
) -> Optional[tuple[str, ...]]:
    if entity_kinds is None:
        return None
    normalized = tuple(dict.fromkeys(str(kind) for kind in entity_kinds))
    unknown = sorted(set(normalized) - VALID_ENTITY_KINDS)
    if unknown:
        raise ValueError(
            "Unknown Orrery entity kind(s): "
            f"{unknown}; expected {sorted(VALID_ENTITY_KINDS)}"
        )
    return normalized


def _normalize_entity_refs(
    entity_refs: Sequence[EntityRowReference],
) -> tuple[EntityRowReference, ...]:
    """Validate and deduplicate kind-scoped subtype row references."""

    normalized: list[EntityRowReference] = []
    seen: set[EntityRowReference] = set()
    for reference in entity_refs:
        if reference.kind not in VALID_ENTITY_KINDS:
            raise ValueError(
                f"Unknown Orrery entity kind {reference.kind!r}; "
                f"expected {sorted(VALID_ENTITY_KINDS)}"
            )
        if isinstance(reference.row_id, bool) or reference.row_id <= 0:
            raise ValueError(
                "Orrery subtype row IDs must be positive integers, "
                f"got {reference.row_id!r}"
            )
        if reference not in seen:
            normalized.append(reference)
            seen.add(reference)
    return tuple(normalized)


def _translate_entity_row_refs(
    session: Session,
    entity_refs: Sequence[EntityRowReference],
) -> tuple[int, ...]:
    """Translate all kind-scoped subtype row IDs to canonical entity IDs."""

    rows = session.execute(
        text(
            """
            /* orrery:tag_library_entity_id_translation */
            WITH requested AS (
                SELECT *
                FROM unnest(
                    CAST(:entity_kinds AS text[]),
                    CAST(:row_ids AS bigint[])
                ) AS requested(entity_kind, row_id)
            ),
            translated AS (
                SELECT CASE requested.entity_kind
                           WHEN 'character' THEN characters.entity_id
                           WHEN 'place' THEN places.entity_id
                           WHEN 'faction' THEN factions.entity_id
                       END AS entity_id
                FROM requested
                LEFT JOIN characters
                  ON requested.entity_kind = 'character'
                 AND characters.id = requested.row_id
                LEFT JOIN places
                  ON requested.entity_kind = 'place'
                 AND places.id = requested.row_id
                LEFT JOIN factions
                  ON requested.entity_kind = 'faction'
                 AND factions.id = requested.row_id
            )
            SELECT DISTINCT entity_id
            FROM translated
            WHERE entity_id IS NOT NULL
            ORDER BY entity_id
            """
        ),
        {
            "entity_kinds": [reference.kind for reference in entity_refs],
            "row_ids": [reference.row_id for reference in entity_refs],
        },
    ).mappings()
    return tuple(int(row["entity_id"]) for row in rows)


def _format_tag_name(tag: str, is_ephemeral: bool) -> str:
    suffix = " (ephemeral)" if is_ephemeral else ""
    return f"`{tag}`{suffix}"


def _format_tag_entry(entry: TagLibraryEntry) -> str:
    name = _format_tag_name(entry.tag, entry.is_ephemeral)
    if not entry.description:
        return name
    return f"{name}: {_clean_description(entry.description)}"


def _clean_description(description: str, *, max_length: int = 140) -> str:
    cleaned = " ".join(description.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3].rstrip()}..."


def _short_description(description: str, *, max_length: int = 140) -> str:
    """Return a one-line description only when it is already inexpensive."""

    cleaned = " ".join(description.split())
    return cleaned if len(cleaned) <= max_length else ""


def _connect(dbname: Optional[str]):
    resolved = _resolve_dbname(dbname)
    return psycopg2.connect(
        dbname=resolved,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        cursor_factory=RealDictCursor,
    )


@contextmanager
def _slot_session(dbname: Optional[str]) -> Iterator[Session]:
    """Open a short read session for canonical Orrery state helpers."""

    resolved = _resolve_dbname(dbname)
    engine = create_engine(
        get_slot_db_url(
            dbname=resolved,
            user=os.environ.get("PGUSER", "pythagor"),
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5432")),
        ),
        future=True,
    )
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _resolve_dbname(dbname: Optional[str]) -> str:
    if dbname:
        resolved = dbname
    else:
        slot = os.environ.get("NEXUS_SLOT")
        if slot and slot.isdigit():
            resolved = f"save_{int(slot):02d}"
        else:
            resolved = os.environ.get("PGDATABASE", "")
    if not _SLOT_DB_RE.match(resolved):
        raise ValueError(
            "Orrery tag library requires a slot database name "
            f"(save_01..save_05), got {resolved!r}"
        )
    return resolved
