"""Prompt-facing Orrery tag library helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import os
import re
from typing import Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

VALID_ENTITY_KINDS = frozenset({"character", "faction", "place"})
_SLOT_DB_RE = re.compile(r"^save_0[1-5]$")


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


def _connect(dbname: Optional[str]):
    resolved = _resolve_dbname(dbname)
    return psycopg2.connect(
        dbname=resolved,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        cursor_factory=RealDictCursor,
    )


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
