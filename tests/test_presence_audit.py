"""Presence-roster drift audit tests (issue #567)."""

from __future__ import annotations

import logging
import os

import pytest

from nexus.api.presence_audit import (
    audit_chunk_presence,
    diff_presence,
    presence_audit_enabled,
)
from nexus.memory.entity_detector import HighSpecificityEntityDetector

RUN_POSTGRES = os.environ.get("NEXUS_RUN_POSTGRES") == "1"


def _detector_with_characters(
    records: dict[str, dict],
) -> HighSpecificityEntityDetector:
    """Build a DB-less detector with an injected character lookup."""
    detector = HighSpecificityEntityDetector(db_connection=None)
    detector.character_lookup.update(records)
    return detector


KOSI = {"id": 7, "name": "Kosi", "summary": None}
NNEKA = {"id": 9, "name": "Nneka", "summary": None}


def test_prose_present_roster_absent_yields_one_finding_per_character(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each unaccounted prose-named character = exactly one structured warning."""
    detector = _detector_with_characters(
        {"kosi": KOSI, "nneka": NNEKA, "the boatman": KOSI}
    )
    match = detector.detect_entities(
        "Kosi lifts the boat hook while Nneka watches. Kosi nods. "
        "The boatman says nothing."
    )

    with caplog.at_level(logging.WARNING, logger="nexus.api.presence_audit"):
        findings = diff_presence(match, {9}, chunk_id=4242)
        from nexus.api.presence_audit import _emit_findings

        _emit_findings(findings)

    # Kosi appears by name AND alias, twice by name — one finding, one warning.
    assert findings == [{"chunk_id": 4242, "character_id": 7, "name": "Kosi"}]
    warnings = [
        record for record in caplog.records if record.name == "nexus.api.presence_audit"
    ]
    assert len(warnings) == 1
    assert "chunk 4242" in warnings[0].getMessage()
    assert "'Kosi'" in warnings[0].getMessage()
    assert "id=7" in warnings[0].getMessage()


def test_roster_present_name_absent_yields_no_warning() -> None:
    """Pronoun-blindness guardrail: name-absence is never evidence of absence.

    The roster carries character 7, the prose says only "she" — the audit
    must stay silent (chunk n names her, chunk n+1 uses pronouns).
    """
    detector = _detector_with_characters({"kosi": KOSI})
    match = detector.detect_entities("She lowers the hook and waits in the dark.")

    findings = diff_presence(match, {7}, chunk_id=4243)

    assert findings == []


def test_accounted_mention_is_not_a_missed_entry() -> None:
    """Any junction row (present OR mentioned) accounts for a prose name."""
    detector = _detector_with_characters({"kosi": KOSI})
    match = detector.detect_entities("They speak of Kosi in a low voice.")

    findings = diff_presence(match, {7}, chunk_id=4244)

    assert findings == []


def test_audit_errors_never_escape(caplog: pytest.LogCaptureFixture) -> None:
    """A diagnostics failure after a successful commit must not raise."""

    class ExplodingConn:
        def cursor(self):
            raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="nexus.api.presence_audit"):
        findings = audit_chunk_presence(ExplodingConn(), 4245, "Kosi waits.")

    assert findings == []
    assert any(
        "presence audit failed for committed chunk 4245" in record.getMessage()
        for record in caplog.records
    )


def test_presence_audit_enabled_reads_shipped_default() -> None:
    """The shipped [lore.presence_audit] gate is on."""
    assert presence_audit_enabled() is True


@pytest.mark.skipif(not RUN_POSTGRES, reason="requires live slot database")
def test_live_audit_runs_read_only_on_a_real_chunk() -> None:
    """The sync orchestrator runs against a real slot without mutating state."""
    import psycopg2

    from nexus.api.slot_utils import require_slot_dbname

    dbname = require_slot_dbname()
    conn = psycopg2.connect(host="localhost", database=dbname, user="pythagor")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nc.id, nc.raw_text FROM narrative_chunks nc "
                "JOIN chunk_character_references ccr ON ccr.chunk_id = nc.id "
                "WHERE nc.raw_text IS NOT NULL "
                "ORDER BY nc.id DESC LIMIT 1"
            )
            row = cur.fetchone()
            assert row is not None, "slot has no chunk with junction rows"
            chunk_id, prose = row
            cur.execute("SELECT COUNT(*) FROM chunk_character_references")
            before = cur.fetchone()[0]

        findings = audit_chunk_presence(conn, chunk_id, prose)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunk_character_references")
            after = cur.fetchone()[0]
        assert before == after
        for finding in findings:
            assert set(finding) == {"chunk_id", "character_id", "name"}
            assert finding["chunk_id"] == chunk_id
    finally:
        conn.close()


def test_narrated_departure_is_accounted_by_parent_presence() -> None:
    """presence.exit removes the junction row by design; the departing
    character's name in prose must not be flagged (PR #584 Codex finding).

    Under delta-presence, silence carries a present character forward, so a
    parent-present character can only lack a row via an authored exit —
    the exclusion is exact.
    """
    detector = _detector_with_characters({"kosi": KOSI})
    match = detector.detect_entities(
        "Kosi shoulders the boat hook and walks into the rain."
    )

    parent_present = {7}
    findings = diff_presence(match, set() | parent_present, chunk_id=4246)

    assert findings == []
