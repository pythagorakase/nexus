"""The issue 785 travel reachability probe against a seeded disposable clone.

``tests.pg_fixtures`` owns creation, seeding, and drop: a played story whose
off-screen cast member is a roster actor standing at a second place. The probe
runs as its real command line, by subprocess, and reads the clone through its
read-only session; no live slot is touched.
"""

from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import psycopg2.errors
import pytest
import sqlalchemy.exc
from sqlalchemy import text

from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_entity_tag,
    seed_place,
    seed_played_story,
)

pytestmark = pytest.mark.requires_postgres

TRAVELER = "Fixture Traveler"
PROTAGONIST = "Fixture Player"
EXPECTED_ROWS = [
    {"template_id": "routine_commute", "label": "Commute to the scheduled workplace"},
    {
        "template_id": "routine_commute",
        "label": "Commute home after the day's obligations",
    },
    {"template_id": "travel", "label": "Charter private transport"},
    {"template_id": "travel", "label": "Slip out along covert routes"},
    {"template_id": "travel", "label": "Depart toward the planned destination"},
    {"template_id": "socialize", "label": "Seek company after extended isolation"},
    {"template_id": "socialize", "label": "Set out toward public company"},
    {"template_id": "advance_relocation_plan", "label": "Commit to the road"},
    {"template_id": "start_relocation_plan", "label": "Begin putting something aside"},
]
SOCIAL_DESTINATION = (
    "has_location_class_destination(commerce,entertainment,meeting,place_open@actor)"
)


def _probe(dbname: str) -> dict[str, Any]:
    """Run the real probe command line with ``--json`` and parse its stdout."""

    result = subprocess.run(
        [
            sys.executable,
            "scripts/qa_shift/travel_reachability.py",
            "--dbname",
            dbname,
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path.cwd())},
    )
    report: dict[str, Any] = json.loads(result.stdout)
    return report


def _traveler(report: dict[str, Any]) -> dict[str, Any]:
    """Return the traveler's actor record from the only probed database."""

    matches = [
        actor for actor in report["databases"][0]["actors"] if actor["name"] == TRAVELER
    ]
    assert len(matches) == 1, report["databases"][0]["actors"]
    return matches[0]


def _row(actor: dict[str, Any], template_id: str, label: str) -> dict[str, Any]:
    """Return one probed row of an actor record."""

    matches = [
        row
        for row in actor["rows"]
        if row["template_id"] == template_id and row["label"] == label
    ]
    assert len(matches) == 1, actor["rows"]
    return matches[0]


def test_probe_reports_anchor_blockers() -> None:
    """Without routine anchors, the commute and relocation gates name them."""

    with disposable_slot_database("qa640_785_reach") as dbname:
        seed_played_story(dbname, turns=3, cast=(TRAVELER,))
        report = _probe(dbname)

    database = report["databases"][0]
    assert database["dbname"] == dbname
    assert database["rows"] == EXPECTED_ROWS
    traveler = _traveler(report)
    assert traveler["in_roster"] is True
    protagonists = [
        actor for actor in database["actors"] if actor["name"] == PROTAGONIST
    ]
    assert len(protagonists) == 1, database["actors"]
    assert protagonists[0]["in_roster"] is False
    assert database["substrate"]["roster_size"] == 1
    commute_work = _row(
        traveler, "routine_commute", "Commute to the scheduled workplace"
    )
    assert "has_routine_anchor(work@actor)" in commute_work["gate_blockers"]
    relocation = _row(
        traveler, "start_relocation_plan", "Begin putting something aside"
    )
    assert "at_routine_anchor(home@actor)" in relocation["gate_blockers"]


def test_social_class_destination_differential() -> None:
    """A commerce-tagged place clears the social destination blocker."""

    with disposable_slot_database("qa640_785_reach") as dbname:
        seed_played_story(dbname, turns=3, cast=(TRAVELER,))
        before = _probe(dbname)
        _, market_entity_id = seed_place(dbname, name="Fixture Market")
        seed_entity_tag(dbname, entity_id=market_entity_id, tag="commerce")
        after = _probe(dbname)

    label = "Set out toward public company"
    before_row = _row(_traveler(before), "socialize", label)
    after_row = _row(_traveler(after), "socialize", label)
    assert SOCIAL_DESTINATION in before_row["branch_blockers"]
    assert SOCIAL_DESTINATION not in after_row["branch_blockers"]
    assert before["databases"][0]["substrate"]["social_class_places"] == 0
    assert after["databases"][0]["substrate"]["social_class_places"] == 1


def test_session_is_read_only() -> None:
    """The probe's session refuses a write at the server."""

    from scripts.qa_shift.travel_reachability import read_only_session

    with disposable_slot_database("qa640_785_reach") as dbname:
        with read_only_session(dbname) as session:
            with pytest.raises(sqlalchemy.exc.InternalError) as exc:
                session.execute(
                    text(
                        "INSERT INTO places (name, summary, coordinates) "
                        "VALUES ('Probe Write', 'Must be refused.', "
                        "ST_SetSRID(ST_MakePoint(-73.9857, 40.7484, 0, 0), "
                        "4326)::geography)"
                    )
                )
        assert isinstance(exc.value.orig, psycopg2.errors.ReadOnlySqlTransaction)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM places WHERE name = 'Probe Write'")
            assert cur.fetchone()[0] == 0
