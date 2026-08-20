"""Post-commit presence-roster drift audit (issue #567).

Delta-presence semantics (#555 ruling) carry rosters forward on silence: the
writer authors only entries/exits, so a missed entry accretes silently until
a scene reset. The deterministic alias detector is deployed here as the
AUDIT layer, exactly where its precision profile is strong:

- A character name (or alias) appearing in the committed prose (raw_text:
  storyteller prose plus the enacted choice line — what is stored, embedded,
  and searched) while the chunk has no accounting for that character =
  candidate missed entry. Flag it loudly.
- Name-absence is NEVER evidence of absence (chunk n names her, chunk n+1
  says only "she") — this module only iterates DETECTED names, so it is
  structurally incapable of flagging a roster member whose name does not
  appear.
- The audit proposes; it never mutates. Output is one structured warning per
  finding plus a metrics-friendly findings list.

"Accounted" spans two sources:

1. ANY junction reference row for the chunk (a ``mentioned`` row is the
   writer deliberately accounting for an off-scene reference).
2. A ``present`` row on the PARENT chunk. Under delta-presence, silence
   carries a present character forward — the only way a parent-present
   character lacks a row on this chunk is an authored ``presence.exit``, and
   prose narrating a departure legitimately names the departing character
   (PR #584 Codex finding). This exclusion is exact, not heuristic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from nexus.memory.entity_detector import EntityMatch, HighSpecificityEntityDetector

logger = logging.getLogger("nexus.api.presence_audit")


def _character_only_detector(
    character_rows: List[Any],
    alias_rows: List[Any],
) -> HighSpecificityEntityDetector:
    """Build a detector from prefetched character/alias rows.

    Mirrors HighSpecificityEntityDetector._load_characters' record shape
    ({id, name, summary}). Places and factions stay unloaded — the presence
    audit only diffs characters, so loading and regex-scanning them would be
    pure waste on every commit (both orchestrators share this builder).
    """
    from nexus.api.presence_reconciliation import build_character_presence_detector

    return build_character_presence_detector(character_rows, alias_rows)


def diff_presence(
    entity_match: EntityMatch,
    accounted_character_ids: set[int],
    *,
    chunk_id: int,
) -> List[Dict[str, Any]]:
    """Return one finding per prose-detected character with no accounting.

    Pure core: iterates only DETECTED characters (pronoun-blindness
    guardrail — roster members whose names are absent can never be flagged).
    """
    findings: List[Dict[str, Any]] = []
    for character in entity_match.characters:
        if character["id"] in accounted_character_ids:
            continue
        findings.append(
            {
                "chunk_id": chunk_id,
                "character_id": character["id"],
                "name": character["name"],
            }
        )
    return findings


def _emit_findings(findings: List[Dict[str, Any]]) -> None:
    """Emit exactly one structured warning per finding."""
    for finding in findings:
        logger.warning(
            "presence audit: chunk %s prose names %r (character id=%s) "
            "with no junction row — candidate missed entry",
            finding["chunk_id"],
            finding["name"],
            finding["character_id"],
        )


def audit_chunk_presence(
    conn: Any,
    chunk_id: int,
    prose: str,
    *,
    parent_chunk_id: Optional[int] = None,
    detector: Optional[HighSpecificityEntityDetector] = None,
) -> List[Dict[str, Any]]:
    """Audit one committed chunk's prose against its accounting.

    Read-only. Runs post-commit on the sync commit handler's psycopg2
    connection; the chunk's junction rows are ground truth as committed.
    Emits exactly one warning per finding.

    Diagnostics must never fail a turn whose chunk already committed, so any
    internal error is contained and logged loudly instead of raised — this
    is blast-radius containment for a read-only observer, not a fallback
    masking a failure.
    """
    try:
        from psycopg2.extras import RealDictCursor

        with conn.cursor() as cur:
            cur.execute(
                "SELECT character_id FROM chunk_character_references "
                "WHERE chunk_id = %s",
                (chunk_id,),
            )
            accounted = {row[0] for row in cur.fetchall()}
            if parent_chunk_id:
                # Authored-exit accounting: see the module docstring.
                cur.execute(
                    "SELECT character_id FROM chunk_character_references "
                    "WHERE chunk_id = %s AND reference::text = 'present'",
                    (parent_chunk_id,),
                )
                accounted |= {row[0] for row in cur.fetchall()}

        active_detector = detector
        if active_detector is None:
            with conn.cursor(cursor_factory=RealDictCursor) as dict_cur:
                dict_cur.execute(
                    "SELECT id, name, summary FROM characters " "WHERE name IS NOT NULL"
                )
                character_rows = dict_cur.fetchall()
                dict_cur.execute("SELECT character_id, alias FROM character_aliases")
                alias_rows = dict_cur.fetchall()
            active_detector = _character_only_detector(character_rows, alias_rows)

        entity_match = active_detector.detect_entities(prose)
        findings = diff_presence(entity_match, accounted, chunk_id=chunk_id)
        _emit_findings(findings)
        return findings
    except Exception:
        logger.exception(
            "presence audit failed for committed chunk %s; the commit itself "
            "is unaffected",
            chunk_id,
        )
        return []


async def audit_chunk_presence_async(
    conn: Any,
    chunk_id: int,
    prose: str,
    *,
    parent_chunk_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Asyncpg twin of audit_chunk_presence for the async commit handler."""
    try:
        accounted_rows = await conn.fetch(
            "SELECT character_id FROM chunk_character_references "
            "WHERE chunk_id = $1",
            chunk_id,
        )
        accounted = {row["character_id"] for row in accounted_rows}
        if parent_chunk_id:
            # Authored-exit accounting: see the module docstring.
            parent_rows = await conn.fetch(
                "SELECT character_id FROM chunk_character_references "
                "WHERE chunk_id = $1 AND reference::text = 'present'",
                parent_chunk_id,
            )
            accounted |= {row["character_id"] for row in parent_rows}

        character_rows = await conn.fetch(
            "SELECT id, name, summary FROM characters WHERE name IS NOT NULL"
        )
        alias_rows = await conn.fetch(
            "SELECT character_id, alias FROM character_aliases"
        )
        detector = _character_only_detector(list(character_rows), list(alias_rows))
        entity_match = detector.detect_entities(prose)
        findings = diff_presence(entity_match, accounted, chunk_id=chunk_id)
        _emit_findings(findings)
        return findings
    except Exception:
        logger.exception(
            "presence audit failed for committed chunk %s; the commit itself "
            "is unaffected",
            chunk_id,
        )
        return []


def presence_audit_enabled() -> bool:
    """Read the [lore.presence_audit] gate from validated settings."""
    from nexus.config import load_settings

    return load_settings().lore.presence_audit.enabled
