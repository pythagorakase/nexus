"""Natural Earth reference table, loader and geometry service (issue #840 S1)."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Iterator

import pytest

from nexus.agents.orrery.geo_reference import (
    MANIFEST_PATH,
    AmbiguousRegionError,
    InvalidGeometryError,
    ReferenceDataError,
    RegionNotFoundError,
    clip_to_land,
    land_coverage,
    load_manifest,
    lookup_region,
    point_on_land,
    require_valid_polygon,
)
from nexus.database import AmbiguousCommit
from scripts import load_natural_earth, new_story_setup
from scripts.load_natural_earth import (
    NaturalEarthChecksumError,
    NaturalEarthReadError,
    NaturalEarthValidityError,
    load_reference,
    read_reference_files,
)
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres

EXPECTED_COUNTS = {"land": 11, "admin_0": 258, "admin_1": 4596}
DENVER = (-104.9903, 39.7392)
OPEN_PACIFIC = (-140.0, 30.0)


@dataclass(frozen=True)
class LoadedClone:
    dbname: str
    load_seconds: float


def _counts(dbname: str) -> dict[str, int]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT layer, count(*) FROM natural_earth_features GROUP BY layer")
        return {layer: int(count) for layer, count in cur.fetchall()}


def _row_versions(dbname: str) -> list[tuple[str, int, str]]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT layer, source_index, xmin::text FROM natural_earth_features "
            "ORDER BY layer, source_index"
        )
        return [tuple(row) for row in cur.fetchall()]


def _geometry_digest(dbname: str) -> str:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT md5(string_agg(ST_AsEWKB(geom)::text, '' "
            "ORDER BY layer, source_index)) FROM natural_earth_features"
        )
        return str(cur.fetchone()[0])


def _box(west: float, south: float, east: float, north: float) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


def _manifest_copy(tmp_path: Path, **overrides: Any) -> Path:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data.update(overrides)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _timed_initialize(
    timings: list[float],
) -> Callable[..., None]:
    original = new_story_setup.initialize_slot_database

    def initialize(*args: Any, **kwargs: Any) -> None:
        started = time.perf_counter()
        original(*args, **kwargs)
        timings.append(time.perf_counter() - started)

    return initialize


@pytest.fixture(scope="module")
def loaded_clone() -> Iterator[LoadedClone]:
    with disposable_slot_database("qa640_840_geo") as dbname:
        started = time.perf_counter()
        counts = load_reference(dbname)
        load_seconds = time.perf_counter() - started
        assert counts == EXPECTED_COUNTS
        yield LoadedClone(dbname=dbname, load_seconds=load_seconds)


@pytest.fixture(scope="module")
def empty_clone() -> Iterator[str]:
    with disposable_slot_database("qa640_840_empty") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM natural_earth_features")
            cur.execute("SELECT count(*) FROM natural_earth_features")
            assert cur.fetchone()[0] == 0
        yield dbname


def test_checksum_mismatch_refuses(tmp_path: Path, empty_clone: str) -> None:
    manifest = load_manifest()
    manifest_path = _manifest_copy(tmp_path)
    for layer in manifest.layers:
        source = MANIFEST_PATH.parent / layer.file
        target = tmp_path / layer.file
        if layer.file == "ne_10m_land.zip":
            shutil.copyfile(source, target)
            with target.open("ab") as handle:
                handle.write(b"\0")
        else:
            target.symlink_to(source)

    with pytest.raises(NaturalEarthChecksumError, match="ne_10m_land.zip"):
        load_reference(empty_clone, manifest_path=manifest_path)
    assert _counts(empty_clone) == {}


def test_unlisted_invalid_feature_refuses(
    tmp_path: Path, loaded_clone: LoadedClone
) -> None:
    manifest_path = _manifest_copy(tmp_path, repairs=[])
    for layer in load_manifest().layers:
        (tmp_path / layer.file).symlink_to(MANIFEST_PATH.parent / layer.file)
    before = _row_versions(loaded_clone.dbname)

    with pytest.raises(NaturalEarthValidityError) as raised:
        load_reference(loaded_clone.dbname, manifest_path=manifest_path)

    message = str(raised.value)
    assert "admin_0 1159320575" in message
    assert "admin_1 1159309897" in message
    assert _counts(loaded_clone.dbname) == EXPECTED_COUNTS
    assert _row_versions(loaded_clone.dbname) == before


def test_reference_rows_match_manifest(loaded_clone: LoadedClone) -> None:
    dbname = loaded_clone.dbname
    assert _counts(dbname) == EXPECTED_COUNTS
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT array_agg(DISTINCT release), "
            "count(*) FILTER (WHERE NOT ST_IsValid(geom)), "
            "count(*) FILTER (WHERE ST_SRID(geom) <> 4326), "
            "count(*) FILTER (WHERE GeometryType(geom) <> 'MULTIPOLYGON') "
            "FROM natural_earth_features"
        )
        releases, invalid, other_srid, other_type = cur.fetchone()
    assert releases == ["5.1.1"]
    assert (invalid, other_srid, other_type) == (0, 0, 0)

    assert load_natural_earth.main(["--dbname", dbname]) == 0
    assert _counts(dbname) == EXPECTED_COUNTS


def test_land_point_covered_ocean_point_not(loaded_clone: LoadedClone) -> None:
    with closing(connect(loaded_clone.dbname)) as conn, conn.cursor() as cur:
        assert point_on_land(cur, longitude=DENVER[0], latitude=DENVER[1]) is True
        assert (
            point_on_land(cur, longitude=OPEN_PACIFIC[0], latitude=OPEN_PACIFIC[1])
            is False
        )


def test_admin1_name_resolves(loaded_clone: LoadedClone) -> None:
    with closing(connect(loaded_clone.dbname)) as conn, conn.cursor() as cur:
        colorado = lookup_region(cur, "Colorado", layer="admin_1")
        assert (colorado.adm1_code, colorado.adm0_a3) == ("USA-3522", "USA")
        assert lookup_region(cur, "goiás", layer="admin_1").adm1_code == "BRA-1294"

        with pytest.raises(AmbiguousRegionError) as raised:
            lookup_region(cur, "La Paz", layer="admin_1")
        for code in ("BOL-1936", "HND-649", "SLV-1347"):
            assert code in str(raised.value)
        assert len(raised.value.candidates) == 3
        bolivia = lookup_region(cur, "La Paz", layer="admin_1", adm0_a3="BOL")
        assert bolivia.adm1_code == "BOL-1936"

        with pytest.raises(RegionNotFoundError):
            lookup_region(cur, "Nowhere Such Province", layer="admin_1")
        with pytest.raises(ValueError):
            lookup_region(cur, "Colorado", layer="land")


def test_invalid_polygon_rejected(loaded_clone: LoadedClone) -> None:
    bow_tie = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
    }
    with closing(connect(loaded_clone.dbname)) as conn, conn.cursor() as cur:
        with pytest.raises(InvalidGeometryError, match="Self-intersection"):
            require_valid_polygon(cur, bow_tie)
        require_valid_polygon(cur, _box(0, 0, 1, 1))
        with pytest.raises(InvalidGeometryError, match="POINT"):
            require_valid_polygon(cur, {"type": "Point", "coordinates": [0, 0]})


def test_clip_and_coverage(loaded_clone: LoadedClone) -> None:
    coast = _box(-125, 45, -120, 50)
    ocean = _box(-150, 25, -145, 30)
    with closing(connect(loaded_clone.dbname)) as conn, conn.cursor() as cur:
        clipped = clip_to_land(cur, coast)
        coverage = land_coverage(cur, coast)
        cur.execute(
            "WITH c AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS g), "
            "b AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS g) "
            "SELECT GeometryType(c.g), ST_IsValid(c.g), "
            "ST_Area(c.g::geography), ST_Area(b.g::geography) FROM c, b",
            (json.dumps(clipped), json.dumps(coast)),
        )
        geometry_type, valid, clipped_area, box_area = cur.fetchone()
        assert clipped["type"] == "MultiPolygon"
        assert (geometry_type, valid) == ("MULTIPOLYGON", True)
        assert 0 < clipped_area < box_area
        assert 0.0 < coverage < 1.0
        assert abs(coverage - clipped_area / box_area) <= 1e-9

        assert land_coverage(cur, ocean) == 0.0
        with pytest.raises(InvalidGeometryError):
            clip_to_land(cur, ocean)


def test_stale_reference_refuses(empty_clone: str, loaded_clone: LoadedClone) -> None:
    with closing(connect(empty_clone)) as conn, conn.cursor() as cur:
        with pytest.raises(ReferenceDataError):
            point_on_land(cur, longitude=DENVER[0], latitude=DENVER[1])

    with closing(connect(loaded_clone.dbname)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE natural_earth_features SET release = '5.1.0' "
                    "WHERE layer = 'admin_1' AND source_index = 0"
                )
                with pytest.raises(ReferenceDataError, match="admin_1"):
                    point_on_land(cur, longitude=DENVER[0], latitude=DENVER[1])
        finally:
            conn.rollback()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM natural_earth_features "
                    "WHERE layer = 'admin_1' AND source_index = 0"
                )
                with pytest.raises(ReferenceDataError, match="admin_1"):
                    point_on_land(cur, longitude=DENVER[0], latitude=DENVER[1])
        finally:
            conn.rollback()
    assert _counts(loaded_clone.dbname) == EXPECTED_COUNTS


def test_missing_table_refuses(empty_clone: str) -> None:
    # A database without migration 147 must refuse with ReferenceDataError
    # naming every layer, not with UndefinedTable aborting the caller's
    # transaction.
    with closing(connect(empty_clone)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE natural_earth_features")
                with pytest.raises(
                    ReferenceDataError, match="land, admin_0, admin_1"
                ) as raised:
                    point_on_land(cur, longitude=DENVER[0], latitude=DENVER[1])
                assert "migration 147" in str(raised.value)
                cur.execute("SELECT 1")
                assert cur.fetchone() == (1,)
        finally:
            conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.natural_earth_features')")
            assert cur.fetchone()[0] is not None
        conn.rollback()


def test_fresh_slot_copies_reference(
    empty_clone: str,
    loaded_clone: LoadedClone,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from_loaded: list[float] = []
    monkeypatch.setattr(
        new_story_setup, "initialize_slot_database", _timed_initialize(from_loaded)
    )
    with disposable_slot_database(
        "qa640_840_fresh", source_db=loaded_clone.dbname
    ) as fresh:
        assert _counts(fresh) == EXPECTED_COUNTS
        assert _geometry_digest(fresh) == _geometry_digest(loaded_clone.dbname)

    from_empty: list[float] = []
    monkeypatch.setattr(
        new_story_setup, "initialize_slot_database", _timed_initialize(from_empty)
    )
    with disposable_slot_database("qa640_840_fresh", source_db=empty_clone) as fresh:
        assert _counts(fresh) == {}

    with capsys.disabled():
        print(
            f"\n840 timings: load_reference {loaded_clone.load_seconds:.2f}s; "
            f"initialize_slot_database from loaded clone {from_loaded[0]:.2f}s, "
            f"from empty clone {from_empty[0]:.2f}s"
        )


def test_ogr2ogr_failure_carries_gdal_message() -> None:
    # The refusal must show GDAL's own stderr, not only an exit status.
    ogr2ogr = new_story_setup._postgres_tools("ogr2ogr")["ogr2ogr"]
    land_zip = MANIFEST_PATH.parent / "ne_10m_land.zip"
    with pytest.raises(NaturalEarthReadError) as raised:
        load_natural_earth._read_features(ogr2ogr, land_zip, "qa840_missing.shp")
    message = str(raised.value)
    assert str(land_zip) in message
    assert "ogr2ogr exited 1 reading qa840_missing.shp" in message
    assert "Unable to open datasource" in message


def _drop_connection_at_commit(dbname: str) -> None:
    """Make every commit that inserted reference rows lose its connection.

    A deferred constraint trigger fires inside COMMIT and terminates its own
    backend, so the driver itself raises a connection-loss OperationalError
    from ``conn.commit()``. Nothing in the client is replaced.
    """
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE FUNCTION qa840_drop_connection() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_terminate_backend(pg_backend_pid());
                RETURN NULL;
            END $$;
            CREATE CONSTRAINT TRIGGER qa840_drop_connection
            AFTER INSERT ON natural_earth_features
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION qa840_drop_connection();
            """
        )


def test_connection_lost_at_commit_is_commit_unknown(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A connection lost during COMMIT reports an unknown outcome, never a rollback."""
    files = read_reference_files()
    # Its own clone: the trigger poisons every commit that inserts a row.
    with disposable_slot_database("qa640_840_commit") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM natural_earth_features")
        _drop_connection_at_commit(dbname)

        with pytest.raises(AmbiguousCommit, match=dbname):
            load_reference(dbname)

        caplog.clear()
        with caplog.at_level(logging.ERROR, logger="nexus.load_natural_earth"):
            assert load_natural_earth._load_target(
                dbname, files, write_locked_slot=False
            ) == ("commit_unknown", None)
            assert load_natural_earth.main(["--dbname", dbname]) == 1
        assert f"{dbname}: commit_unknown" in capsys.readouterr().out
        logged = [
            record.getMessage()
            for record in caplog.records
            if record.levelno >= logging.ERROR
        ]
        assert sum("outcome unknown" in message for message in logged) == 2
        assert not any("rolled back" in message for message in logged)

        # This fault ends the backend before the commit record, so nothing
        # landed; the rerun the docs allow replaces the rows.
        assert _counts(dbname) == {}
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DROP TRIGGER qa840_drop_connection ON natural_earth_features")
        assert load_natural_earth.main(["--dbname", dbname]) == 0
        assert _counts(dbname) == EXPECTED_COUNTS
