"""Migration 149 protects new points without freezing or rewriting legacy rows."""

from contextlib import closing
from pathlib import Path
import re
from typing import Iterator

from psycopg2.errors import NotNullViolation
import pytest

from nexus.maintenance import migrate
from tests.pg_fixtures import connect, disposable_slot_database, seed_zone

pytestmark = pytest.mark.requires_postgres
ROOT = Path(__file__).resolve().parents[2]
POINT = "ST_SetSRID(ST_MakePoint(0, 0, 0, 0), 4326)::geography"
ORDERED_COMMENTS = {
    "FUNCTION public.places_refuse_missing_point()": (
        "Trigger function for trg_places_require_point and "
        "trg_places_keep_point: raises not_null_violation naming the place. "
        "Every place inserted since migration 149 carries a real-Earth point, "
        "whatever its type, and a point is never removed (#840, Decisions "
        "840-Q5 and 840-Q6)."
    ),
    "TRIGGER trg_places_require_point ON public.places": (
        "Refuses an INSERT of a places row whose coordinates is NULL, for "
        "every place type, virtual places and vehicles included."
    ),
    "TRIGGER trg_places_keep_point ON public.places": (
        "Refuses an UPDATE that sets a non-NULL coordinates to NULL. A row "
        "inserted before migration 149 without a point stays updatable and "
        "may gain a point."
    ),
    "COLUMN public.places.coordinates": (
        "Real-Earth point of the place (geography PointZM, SRID 4326, "
        "longitude as x; z and m are 0). Every row inserted since migration "
        "149 carries one, authored by the structured output that introduced "
        "the place; a point is never removed. Rows inserted earlier may be "
        "NULL and are left as they are (#840)."
    ),
}


@pytest.fixture
def point_db() -> Iterator[str]:
    with disposable_slot_database("qa640_840s2_guard") as dbname:
        yield dbname


@pytest.mark.parametrize("kind", ["fixed_location", "vehicle", "virtual", "other"])
def test_insert_without_point_refused(point_db: str, kind: str) -> None:
    """Every place type is refused without a point and accepted with one."""
    with closing(connect(point_db)) as conn:
        with pytest.raises(NotNullViolation, match="has no point") as caught:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO places (name, type) VALUES (%s, %s::place_type)",
                    ("No Point", kind),
                )
        assert caught.value.diag.column_name == "coordinates"
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO places (name, type, coordinates) "
                f"VALUES (%s, %s::place_type, {POINT}) RETURNING id",
                ("With Point", kind),
            )
            assert cur.fetchone()[0] is not None


def test_legacy_row_stays_updatable(point_db: str) -> None:
    """A legacy missing point permits unrelated updates and can only be added."""
    zone = seed_zone(
        point_db,
        name="Legacy Zone",
        min_longitude=-1,
        min_latitude=-1,
        max_longitude=1,
        max_latitude=1,
    )
    with closing(connect(point_db)) as conn:
        with conn, conn.cursor() as cur:
            # This disposable row deliberately represents a pre-149 place.
            cur.execute("ALTER TABLE places DISABLE TRIGGER trg_places_require_point")
            cur.execute(
                "INSERT INTO places (name, type) "
                "VALUES ('Legacy Place', 'fixed_location') RETURNING id"
            )
            place_id = cur.fetchone()[0]
            cur.execute("ALTER TABLE places ENABLE TRIGGER trg_places_require_point")
            cur.execute(
                "UPDATE places SET summary = 'Still editable', zone = %s "
                "WHERE id = %s RETURNING coordinates IS NULL",
                (zone, place_id),
            )
            assert cur.fetchone() == (True,)
            cur.execute(
                f"UPDATE places SET coordinates = {POINT} WHERE id = %s",
                (place_id,),
            )
        with pytest.raises(NotNullViolation, match="has no point"):
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE places SET coordinates = NULL WHERE id = %s",
                    (place_id,),
                )
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT summary, zone, coordinates IS NOT NULL FROM places "
                "WHERE id = %s",
                (place_id,),
            )
            assert cur.fetchone() == ("Still editable", zone, True)


def test_migration_149_keeps_existing_rows(point_db: str) -> None:
    """Reapplication installs exact guards/comments without changing legacy xmin."""
    with closing(connect(point_db)) as conn, conn, conn.cursor() as cur:
        cur.execute("DROP TRIGGER trg_places_require_point ON places")
        cur.execute("DROP TRIGGER trg_places_keep_point ON places")
        cur.execute("DROP FUNCTION public.places_refuse_missing_point()")
        # The column outlives the replay; clear its comment so only the
        # re-applied migration can set it again.
        cur.execute("COMMENT ON COLUMN public.places.coordinates IS NULL")
        cur.execute("DELETE FROM schema_migrations WHERE version = '149'")
        cur.execute(
            "INSERT INTO places (name, type) "
            "VALUES ('Before Migration', 'other') RETURNING id, xmin::text"
        )
        place_id, before_xmin = cur.fetchone()
    assert migrate.migrate_database(point_db, skip_locked=False) == (1, 0)
    with closing(connect(point_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT xmin::text, coordinates FROM places WHERE id = %s", (place_id,)
        )
        assert cur.fetchone() == (before_xmin, None)
        cur.execute(
            "SELECT tgname, tgenabled FROM pg_trigger "
            "WHERE tgrelid = 'places'::regclass "
            "AND tgname IN ('trg_places_keep_point', 'trg_places_require_point') "
            "ORDER BY tgname"
        )
        assert cur.fetchall() == [
            ("trg_places_keep_point", "O"),
            ("trg_places_require_point", "O"),
        ]
        cur.execute(
            "SELECT 'FUNCTION public.places_refuse_missing_point()', "
            "obj_description('public.places_refuse_missing_point()'::regprocedure, "
            "'pg_proc') UNION ALL SELECT 'TRIGGER ' || tgname || "
            "' ON public.places', obj_description(oid, 'pg_trigger') FROM pg_trigger "
            "WHERE tgrelid = 'places'::regclass AND tgname IN "
            "('trg_places_require_point', 'trg_places_keep_point') "
            "UNION ALL SELECT 'COLUMN public.places.coordinates', "
            "col_description('places'::regclass, attnum) "
            "FROM pg_attribute WHERE attrelid = 'places'::regclass "
            "AND attname = 'coordinates'"
        )
        observed = dict(cur.fetchall())
    # Pinned verbatim from work order 840-S2 item 1, so drift in the migration
    # text is caught; the parse of the migration file below is a second check.
    assert observed == ORDERED_COMMENTS
    source = (ROOT / "migrations/149_place_point_required.sql").read_text()
    expected = {
        object_name: value.replace("''", "'")
        for object_name, value in re.findall(
            r"COMMENT ON (.*?) IS '((?:[^']|'')*)';", source
        )
    }
    assert len(expected) == 4
    assert observed == expected
