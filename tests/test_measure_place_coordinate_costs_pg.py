"""PostgreSQL check that the 840-Q4 report splits genesis rows from play."""

from __future__ import annotations

from contextlib import closing
import json
from typing import Any

import pytest

from nexus.agents.logon.apex_schema import NewEntityDeclaration
from nexus.agents.orrery import retrograde_maturation, retrograde_persistence
from nexus.api import trait_compiler
from scripts.measure_place_coordinate_costs import main
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_committed_chunk,
    seed_place,
    seed_protagonist,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres


def _commit(dbname: str, write: Any) -> Any:
    """Run ``write(cur)`` in its own committed transaction and return its value."""

    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        return write(cur)


def test_stub_counts_attribute_genesis_and_play(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Genesis rows, later rows and their turns come out exactly."""

    with disposable_slot_database("qa640_840_cost") as dbname:
        seed_zone(
            dbname,
            name="Fixture Zone",
            min_longitude=-123.0,
            min_latitude=47.0,
            max_longitude=-122.0,
            max_latitude=48.0,
        )
        opening_place_id, _ = seed_place(
            dbname, name="Opening Place", longitude=-122.3321, latitude=47.6062
        )
        character_id, character_entity_id = seed_protagonist(
            dbname, current_location=opening_place_id
        )
        trait_place_id, _ = _commit(
            dbname,
            lambda cur: trait_compiler._insert_place_stub(
                cur, name="Trait Domain", trait="domain", role="domain"
            ),
        )
        chunk_1 = seed_committed_chunk(dbname, raw_text="First chunk.")
        chunk_2 = seed_committed_chunk(dbname, raw_text="Second chunk.", scene=2)
        chunk_3 = seed_committed_chunk(dbname, raw_text="Third chunk.", scene=3)

        def insert_job(cur: Any) -> int:
            cur.execute(
                """
                INSERT INTO orrery_maturation_jobs (
                    entity_id, entity_kind, entity_subtype_id, entity_name, slot,
                    requesting_chunk_id, declaration
                ) VALUES (%s, 'character', %s, %s, %s, %s, '{}'::jsonb)
                RETURNING id
                """,
                (
                    character_entity_id,
                    character_id,
                    "Fixture Player",
                    dbname,
                    chunk_2,
                ),
            )
            return int(cur.fetchone()[0])

        job_id = _commit(dbname, insert_job)
        _commit(
            dbname,
            lambda cur: retrograde_persistence._insert_place_stub(
                cur,
                entity_ref="Job Vault",
                sources=[{"event_ref": f"maturation_job_{job_id}_fixture"}],
            ),
        )
        _commit(
            dbname,
            lambda cur: retrograde_persistence._insert_place_stub(
                cur,
                entity_ref="Orphan Relay",
                sources=[{"event_ref": "maturation_job_999999_fixture"}],
            ),
        )
        _commit(
            dbname,
            lambda cur: retrograde_maturation._insert_declared_stub(
                cur,
                NewEntityDeclaration(
                    kind="place",
                    name="Declared Lanes",
                    summary="A location declared during play.",
                ),
            ),
        )

        def place_ids(cur: Any) -> dict[str, int]:
            cur.execute("SELECT name, id FROM places")
            return {str(name): int(place_id) for name, place_id in cur.fetchall()}

        ids = _commit(dbname, place_ids)

        assert main(["--dbname", dbname]) == 0
        out = capsys.readouterr().out
        report = json.loads(out)

    section = report["databases"][dbname]
    assert section["places_total"] == 5
    assert section["first_chunk"]["id"] == chunk_1
    assert section["genesis"] == {
        "rows": 2,
        "by_source": {"retrograde": 0, "trait_compiler": 1, "none": 1},
        "by_point": {"present": 1, "null": 1},
    }
    later = section["later"]
    assert {key: later[key] for key in ("rows", "by_source", "by_point")} == {
        "rows": 3,
        "by_source": {"retrograde": 2, "trait_compiler": 0, "none": 1},
        "by_point": {"present": 0, "null": 3},
    }
    assert later["rows_detail"] == [
        {
            "place_id": ids["Job Vault"],
            "name": "Job Vault",
            "source": "retrograde",
            "has_point": False,
            "turn_chunk_id": chunk_2,
            "turn_attribution": "maturation_job",
            "job_id": job_id,
        },
        {
            "place_id": ids["Orphan Relay"],
            "name": "Orphan Relay",
            "source": "retrograde",
            "has_point": False,
            "turn_chunk_id": chunk_3,
            "turn_attribution": "created_at",
            "job_id": 999999,
            "job_row_found": False,
        },
        {
            "place_id": ids["Declared Lanes"],
            "name": "Declared Lanes",
            "source": "none",
            "has_point": False,
            "turn_chunk_id": chunk_3,
            "turn_attribution": "created_at",
        },
    ]
    assert section["turns"] == {
        "chunks_after_first": 2,
        "later_rows_on_first_chunk": 0,
        "later_rows_per_chunk": {
            "mean": 1.5,
            "max": 2,
            "histogram": {"1": 1, "2": 1},
        },
    }
    assert section["shared_points"] == []
    assert ids["Trait Domain"] == trait_place_id

    names = [entry["name"] for entry in report["per_place_output"]["new_place_entries"]]
    assert names == ["Job Vault", "Orphan Relay"]
    assert report["per_place_output"]["new_place_entries_source"] == "retrograde_stubs"
    request = report["dedicated_call"]["request"]
    assert request["places_measured"] == 4
    assert request["by_database"][dbname]["places_measured"] == 4
    assert report["configured_stub_cap"]["value"] >= 1
