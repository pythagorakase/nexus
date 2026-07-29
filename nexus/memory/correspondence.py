"""Accepted-state storage and rendering for private storyteller correspondence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.lore.utils.chunk_operations import calculate_chunk_tokens


@dataclass(frozen=True)
class GeneratedCorrespondence:
    """Private output traveling beside, never inside, a player response."""

    writer_letter: str
    gaia_letter: Optional[str]


@dataclass(frozen=True)
class CorrespondenceExchange:
    """One accepted turn's atomic correspondence exchange."""

    chunk_id: int
    letters: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CorrespondenceContext:
    """Current accepted digest plus uncompacted exchange pairs."""

    digest: Optional[str]
    compacted_through_chunk_id: Optional[int]
    exchanges: tuple[CorrespondenceExchange, ...]

    def render(self, *, max_tokens: int) -> str:
        """Render the complete private block, failing rather than truncating."""

        parts = [
            "=== PRIVATE STORYTELLER CORRESPONDENCE ===",
            (
                "This authorial correspondence is invisible to the player "
                "and is not canon."
            ),
            "",
            "DIGEST",
            self.digest or "(No compacted correspondence yet.)",
            "",
            "RECENT EXCHANGES (VERBATIM)",
        ]
        if not self.exchanges:
            parts.append("(No accepted correspondence yet.)")
        for exchange in self.exchanges:
            parts.extend(["", f"[Accepted chunk {exchange.chunk_id}]"])
            for seat, body in exchange.letters:
                label = {
                    "writer": "Skald",
                    "gaia": "Gaia",
                    "single_pass": "Skald/Gaia",
                }[seat]
                parts.extend([f"{label}:", body])
        rendered = "\n".join(parts)
        token_count = calculate_chunk_tokens(rendered)
        if token_count > max_tokens:
            raise ValueError(
                "Private storyteller correspondence exceeds "
                "storyteller.correspondence.max_rendered_tokens: "
                f"{token_count} > {max_tokens}. Refusing to truncate immutable "
                "letters or the digest."
            )
        return rendered


@dataclass(frozen=True)
class CorrespondenceCompactionPlan:
    """Aging exchanges and bearings for one post-accept compaction."""

    accepting_chunk_id: int
    compacted_through_chunk_id: int
    previous_digest: Optional[str]
    aging_exchanges: tuple[CorrespondenceExchange, ...]
    recent_exchanges: tuple[CorrespondenceExchange, ...]

    def render_user_prompt(self) -> str:
        """Render the private input consumed by the compaction utility call."""

        parts = [
            "CURRENT DIGEST",
            self.previous_digest or "(empty)",
            "",
            "EXCHANGES AGING OUT",
        ]
        parts.extend(_render_exchanges(self.aging_exchanges))
        parts.extend(["", "RECENT EXCHANGES FOR BEARINGS"])
        parts.extend(_render_exchanges(self.recent_exchanges))
        return "\n".join(parts)


def correspondence_settings(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return validated correspondence settings from a runtime settings mapping."""

    storyteller = settings.get("storyteller")
    if not isinstance(storyteller, Mapping):
        raise ValueError("storyteller settings are required")
    correspondence = storyteller.get("correspondence")
    if not isinstance(correspondence, Mapping):
        raise ValueError("storyteller.correspondence settings are required")
    return correspondence


def load_accepted_correspondence(
    dbname: str,
    *,
    max_tokens: int,
) -> str:
    """Read and render only accepted correspondence from the slot database."""

    conn = psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            context = read_accepted_correspondence(cur)
    finally:
        conn.close()
    return context.render(max_tokens=max_tokens)


def read_accepted_correspondence(cur: Any) -> CorrespondenceContext:
    """Read the current digest and visible journal from an open DB cursor."""

    cur.execute(
        """
        SELECT d.accepting_chunk_id, d.compacted_through_chunk_id, d.digest
        FROM storyteller_correspondence_digest_versions AS d
        JOIN narrative_chunks AS accepting
          ON accepting.id = d.accepting_chunk_id
        ORDER BY d.accepting_chunk_id DESC
        LIMIT 1
        """
    )
    digest_row = cur.fetchone()
    compacted_through = (
        int(digest_row["compacted_through_chunk_id"]) if digest_row else None
    )
    cur.execute(
        """
        SELECT l.chunk_id, l.seat, l.body
        FROM storyteller_correspondence_letters AS l
        JOIN narrative_chunks AS nc ON nc.id = l.chunk_id
        WHERE (%s IS NULL OR l.chunk_id > %s)
        ORDER BY l.chunk_id,
                 CASE l.seat
                    WHEN 'writer' THEN 1
                    WHEN 'gaia' THEN 2
                    ELSE 1
                 END,
                 l.id
        """,
        (compacted_through, compacted_through),
    )
    exchanges = _group_exchange_rows(cur.fetchall())
    return CorrespondenceContext(
        digest=str(digest_row["digest"]) if digest_row else None,
        compacted_through_chunk_id=compacted_through,
        exchanges=exchanges,
    )


def persist_staged_correspondence(
    cur: Any,
    *,
    chunk_id: int,
    writer_letter: Optional[str],
    gaia_letter: Optional[str],
) -> None:
    """Append one staged exchange inside the accepting chunk transaction."""

    writer = _normalized_letter(writer_letter, "writer")
    gaia = _normalized_letter(gaia_letter, "gaia")
    if writer is None and gaia is None:
        return
    if writer is None:
        raise ValueError("A staged Gaia letter requires its writer letter")

    rows: Sequence[tuple[int, str, str]]
    if gaia is None:
        rows = ((chunk_id, "single_pass", writer),)
    else:
        rows = (
            (chunk_id, "writer", writer),
            (chunk_id, "gaia", gaia),
        )
    cur.executemany(
        """
        INSERT INTO storyteller_correspondence_letters (chunk_id, seat, body)
        VALUES (%s, %s, %s)
        """,
        rows,
    )


def plan_correspondence_compaction(
    cur: Any,
    *,
    accepting_chunk_id: int,
    floor_turns: int,
    ceiling_turns: int,
) -> Optional[CorrespondenceCompactionPlan]:
    """Plan hysteresis compaction after an exchange has been accepted.

    The call occurs after acceptance, but implements the ruled "before the
    11th append" arithmetic: the prior floor survives, and the newly accepted
    exchange remains verbatim as an additional turn.
    """

    context = read_accepted_correspondence(cur)
    exchanges = context.exchanges
    if len(exchanges) <= ceiling_turns:
        return None
    if exchanges[-1].chunk_id != accepting_chunk_id:
        raise RuntimeError(
            "Correspondence compaction trigger chunk is not the newest accepted "
            f"exchange: accepting={accepting_chunk_id}, "
            f"newest={exchanges[-1].chunk_id}"
        )
    retained_count = floor_turns + 1
    aging = exchanges[:-retained_count]
    recent = exchanges[-retained_count:]
    if not aging:
        raise RuntimeError(
            "Correspondence exceeded the ceiling but produced no aging exchanges"
        )
    return CorrespondenceCompactionPlan(
        accepting_chunk_id=accepting_chunk_id,
        compacted_through_chunk_id=aging[-1].chunk_id,
        previous_digest=context.digest,
        aging_exchanges=aging,
        recent_exchanges=recent,
    )


def insert_digest_version(
    cur: Any,
    *,
    plan: CorrespondenceCompactionPlan,
    digest: str,
) -> None:
    """Append an immutable digest version after validating model output."""

    normalized = digest.strip()
    if not normalized:
        raise ValueError("Correspondence compaction returned an empty digest")
    cur.execute(
        """
        INSERT INTO storyteller_correspondence_digest_versions (
            accepting_chunk_id, compacted_through_chunk_id, digest
        )
        VALUES (%s, %s, %s)
        """,
        (
            plan.accepting_chunk_id,
            plan.compacted_through_chunk_id,
            normalized,
        ),
    )


def load_compaction_system_prompt() -> str:
    """Load the frozen compaction instructions without fallback prose."""

    path = (
        Path(__file__).resolve().parents[2] / "prompts" / "correspondence_compaction.md"
    )
    prompt = path.read_text()
    if not prompt.strip():
        raise ValueError(f"Correspondence compaction prompt is empty: {path}")
    return prompt


def _normalized_letter(value: Optional[str], seat: str) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"Staged {seat} correspondence letter is empty")
    return normalized


def _group_exchange_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[CorrespondenceExchange, ...]:
    grouped: list[CorrespondenceExchange] = []
    current_chunk: Optional[int] = None
    current_letters: list[tuple[str, str]] = []
    for row in rows:
        chunk_id = int(row["chunk_id"])
        if current_chunk is not None and chunk_id != current_chunk:
            grouped.append(
                CorrespondenceExchange(
                    chunk_id=current_chunk,
                    letters=tuple(current_letters),
                )
            )
            current_letters = []
        current_chunk = chunk_id
        current_letters.append((str(row["seat"]), str(row["body"])))
    if current_chunk is not None:
        grouped.append(
            CorrespondenceExchange(
                chunk_id=current_chunk,
                letters=tuple(current_letters),
            )
        )
    return tuple(grouped)


def _render_exchanges(exchanges: Sequence[CorrespondenceExchange]) -> list[str]:
    if not exchanges:
        return ["(none)"]
    parts: list[str] = []
    for exchange in exchanges:
        parts.append(f"[Accepted chunk {exchange.chunk_id}]")
        for seat, body in exchange.letters:
            parts.extend([f"{seat}:", body])
    return parts
