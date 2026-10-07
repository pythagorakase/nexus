#!/usr/bin/env python3
"""Load the pinned Natural Earth reference geometry into story databases.

Issue #840, slice S1. The three vendored 10m zips under ``data/natural_earth/``
are checked against ``manifest.json`` before any connection: each zip's sha256
must equal the manifest's, each zip's ``<stem>.VERSION.txt`` must name the
manifest's release, and ``ogr2ogr`` must read exactly the manifest's feature
count from each shapefile. A mismatch refuses the whole run.

One transaction per database then replaces every ``natural_earth_features``
row, checks that the invalid features are exactly the manifest's ``repairs``,
repairs those with ``ST_MakeValid(..., 'method=structure')``, proves every row
valid, and commits. Any error rolls the database back to its previous rows.

Targets mirror ``scripts/rebuild_memory_idf.py``: under ``--all``, ``--slot``
and ``--template`` a database that does not exist is skipped (``absent``) and
a locked one is skipped (``skipped_locked``) unless ``--write-locked-slot`` is
given; neither is a failure. An explicit ``--dbname`` must exist, and a
read-only one needs ``--write-locked-slot``. The files are read once per run.

Usage:
    python scripts/load_natural_earth.py --all              # Template + unlocked slots
    python scripts/load_natural_earth.py --slot 1 --write-locked-slot
    python scripts/load_natural_earth.py --template
    python scripts/load_natural_earth.py --dbname qa640_clone
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Optional, Sequence
import zipfile

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.agents.orrery.geo_reference import (  # noqa: E402
    MANIFEST_PATH,
    NaturalEarthManifest,
    load_manifest,
)
from nexus.database import maintenance_connection, subprocess_env  # noqa: E402
from scripts.database_targets import evaluation_dbname  # noqa: E402
from scripts.migrate import (  # noqa: E402
    SLOT_DBS,
    TEMPLATE_DB,
    db_exists,
    get_connection,
    is_db_locked,
)
from scripts.new_story_setup import _postgres_tools  # noqa: E402

LOG = logging.getLogger("nexus.load_natural_earth")


class NaturalEarthChecksumError(ValueError):
    """A vendored zip's sha256 differs from the manifest."""


class NaturalEarthReleaseError(ValueError):
    """A vendored zip's VERSION.txt names a release other than the manifest's."""


class NaturalEarthFeatureCountError(ValueError):
    """ogr2ogr read a feature count other than the manifest's."""


class NaturalEarthValidityError(RuntimeError):
    """The invalid source features differ from the manifest's repairs."""


@dataclass(frozen=True)
class ReferenceRow:
    """One feature as inserted into ``natural_earth_features``."""

    layer: str
    source_index: int
    ne_id: Optional[int]
    adm0_a3: Optional[str]
    adm1_code: Optional[str]
    iso_code: Optional[str]
    name: Optional[str]
    geometry: str


@dataclass(frozen=True)
class ReferenceFiles:
    """The checked manifest and every feature read from its three zips."""

    manifest: NaturalEarthManifest
    rows: tuple[ReferenceRow, ...]


# Source attribute names per layer: (ne_id, adm0_a3, adm1_code, iso_code, name).
_ATTRIBUTES: Mapping[str, tuple[Optional[str], ...]] = {
    "land": (None, None, None, None, None),
    "admin_0": ("NE_ID", "ADM0_A3", None, "ISO_A3", "NAME"),
    "admin_1": ("ne_id", "adm0_a3", "adm1_code", "iso_3166_2", "name"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _version_member(shapefile: str) -> str:
    return f"{Path(shapefile).stem}.VERSION.txt"


def _read_features(ogr2ogr: str, zip_path: Path, shapefile: str) -> list[Any]:
    result = subprocess.run(
        [
            ogr2ogr,
            "-f",
            "GeoJSON",
            "/vsistdout/",
            f"/vsizip/{zip_path.resolve()}/{shapefile}",
        ],
        check=True,
        capture_output=True,
        env=subprocess_env(),
    )
    return list(json.loads(result.stdout)["features"])


def _row(layer: str, index: int, feature: Mapping[str, Any]) -> ReferenceRow:
    properties = feature["properties"]
    values = [None if key is None else properties[key] for key in _ATTRIBUTES[layer]]
    ne_id, adm0_a3, adm1_code, iso_code, name = values
    return ReferenceRow(
        layer=layer,
        source_index=index,
        ne_id=None if ne_id is None else int(ne_id),
        adm0_a3=adm0_a3,
        adm1_code=adm1_code,
        iso_code=None if iso_code == "-99" else iso_code,
        name=name,
        geometry=json.dumps(feature["geometry"]),
    )


def read_reference_files(manifest_path: Path = MANIFEST_PATH) -> ReferenceFiles:
    """Check the vendored zips against the manifest and read every feature.

    Raises before any database work: ``NaturalEarthChecksumError`` on a
    digest mismatch, ``NaturalEarthReleaseError`` on a VERSION.txt mismatch,
    ``NaturalEarthFeatureCountError`` on a feature-count mismatch.
    """
    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)
    directory = manifest_path.parent
    for layer in manifest.layers:
        actual = _sha256(directory / layer.file)
        if actual != layer.sha256:
            raise NaturalEarthChecksumError(
                f"{directory / layer.file}: sha256 {actual} does not match the "
                f"manifest's {layer.sha256}"
            )
    for layer in manifest.layers:
        member = _version_member(layer.shapefile)
        with zipfile.ZipFile(directory / layer.file) as archive:
            release = archive.read(member).decode("ascii").strip()
        if release != manifest.release:
            raise NaturalEarthReleaseError(
                f"{directory / layer.file}: {member} names release {release!r}, "
                f"the manifest pins {manifest.release!r}"
            )
    ogr2ogr = _postgres_tools("ogr2ogr")["ogr2ogr"]
    rows: list[ReferenceRow] = []
    for layer in manifest.layers:
        features = _read_features(ogr2ogr, directory / layer.file, layer.shapefile)
        if len(features) != layer.feature_count:
            raise NaturalEarthFeatureCountError(
                f"{directory / layer.file}: ogr2ogr read {len(features)} "
                f"{layer.layer} features, the manifest expects "
                f"{layer.feature_count}"
            )
        rows.extend(
            _row(layer.layer, index, feature) for index, feature in enumerate(features)
        )
    return ReferenceFiles(manifest=manifest, rows=tuple(rows))


_REPAIR_SQL = (
    "ST_Multi(ST_CollectionExtract(ST_MakeValid(geom, 'method=structure'), 3))"
)


def write_reference(
    dbname: str, files: ReferenceFiles, *, write_locked_slot: bool = False
) -> dict[str, int]:
    """Replace the database's reference rows in one transaction.

    Raises ``NaturalEarthValidityError`` and rolls back when the invalid
    features differ from the manifest's repairs or a repair leaves an invalid
    row. Returns the committed row count per layer.
    """
    manifest = files.manifest
    expected = {(repair.layer, repair.ne_id) for repair in manifest.repairs}
    with closing(
        maintenance_connection(
            dbname,
            write_locked_slot=write_locked_slot,
            operation="load_natural_earth",
        )
    ) as conn:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM natural_earth_features")
            execute_values(
                cur,
                "INSERT INTO natural_earth_features (layer, source_index, release, "
                "ne_id, adm0_a3, adm1_code, iso_code, name, geom) VALUES %s",
                [
                    (
                        row.layer,
                        row.source_index,
                        manifest.release,
                        row.ne_id,
                        row.adm0_a3,
                        row.adm1_code,
                        row.iso_code,
                        row.name,
                        row.geometry,
                    )
                    for row in files.rows
                ],
                template=(
                    "(%s, %s, %s, %s, %s, %s, %s, %s, "
                    "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))"
                ),
                page_size=200,
            )
            cur.execute(
                "SELECT layer, ne_id, source_index, ST_IsValidReason(geom) "
                "FROM natural_earth_features WHERE NOT ST_IsValid(geom) "
                "ORDER BY layer, source_index"
            )
            invalid = cur.fetchall()
            for layer, ne_id, source_index, reason in invalid:
                LOG.info(
                    "%s: invalid %s feature ne_id=%s source_index=%s: %s",
                    dbname,
                    layer,
                    ne_id,
                    source_index,
                    reason,
                )
            found = {(layer, ne_id) for layer, ne_id, _, _ in invalid}
            if found != expected:
                unlisted = [
                    f"{layer} {ne_id} ({reason})"
                    for layer, ne_id, _, reason in invalid
                    if (layer, ne_id) not in expected
                ]
                valid_repairs = sorted(expected - found)
                raise NaturalEarthValidityError(
                    f"{dbname}: invalid features differ from the manifest's "
                    f"repairs; invalid but not listed: {unlisted or 'none'}; "
                    f"listed but valid: {valid_repairs or 'none'}"
                )
            for layer, ne_id in sorted(expected):
                cur.execute(
                    f"UPDATE natural_earth_features SET geom = {_REPAIR_SQL} "
                    "WHERE layer = %s AND ne_id = %s",
                    (layer, ne_id),
                )
                if cur.rowcount != 1:
                    raise NaturalEarthValidityError(
                        f"{dbname}: repair of {layer} {ne_id} matched "
                        f"{cur.rowcount} rows"
                    )
            cur.execute(
                "SELECT layer, source_index, ST_IsValidReason(geom) "
                "FROM natural_earth_features "
                "WHERE NOT ST_IsValid(geom) OR ST_IsEmpty(geom) "
                "ORDER BY layer, source_index"
            )
            still_invalid = cur.fetchall()
            if still_invalid:
                raise NaturalEarthValidityError(
                    f"{dbname}: rows still invalid after repair: {still_invalid}"
                )
            cur.execute(
                "SELECT layer, count(*) FROM natural_earth_features GROUP BY layer"
            )
            counts = {layer: int(count) for layer, count in cur.fetchall()}
    return {layer.layer: counts.get(layer.layer, 0) for layer in manifest.layers}


def load_reference(
    dbname: str,
    *,
    manifest_path: Path = MANIFEST_PATH,
    write_locked_slot: bool = False,
) -> dict[str, int]:
    """Check the vendored files, then load them into ``dbname``.

    Returns the committed row count per layer.
    """
    files = read_reference_files(manifest_path)
    return write_reference(dbname, files, write_locked_slot=write_locked_slot)


def _load_target(
    dbname: str, files: ReferenceFiles, *, write_locked_slot: bool
) -> tuple[str, Optional[dict[str, int]]]:
    if not db_exists(dbname):
        LOG.warning("Database %s does not exist, skipping", dbname)
        return "absent", None
    if is_db_locked(dbname) and not write_locked_slot:
        LOG.warning(
            "Database %s is LOCKED (read-only), skipping; rerun with "
            "--write-locked-slot to load it",
            dbname,
        )
        return "skipped_locked", None
    try:
        counts = write_reference(dbname, files, write_locked_slot=write_locked_slot)
    except (
        NaturalEarthValidityError,
        psycopg2.Error,
    ) as exc:  # nexus-exception-disposition: fail; reason=logged; safety=exit 1
        LOG.error("%s: Natural Earth load FAILED and rolled back: %s", dbname, exc)
        return "failed", None
    return "loaded", counts


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments, load each target, print its status, return the exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Load the pinned Natural Earth reference geometry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--all", action="store_true", help="NEXUS_template and every slot"
    )
    target_group.add_argument(
        "--slot", type=int, choices=range(1, 6), metavar="N", help="One slot (1-5)"
    )
    target_group.add_argument(
        "--template", action="store_true", help="NEXUS_template only"
    )
    target_group.add_argument(
        "--dbname",
        type=evaluation_dbname,
        help="An explicitly named qa640_* or ref_* database",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="Natural Earth manifest (default: data/natural_earth/manifest.json)",
    )
    parser.add_argument(
        "--write-locked-slot",
        action="store_true",
        help="Override read-only policy only for this maintenance session",
    )
    args = parser.parse_args(argv)

    if args.all:
        targets = [TEMPLATE_DB, *SLOT_DBS]
    elif args.slot is not None:
        targets = [f"save_{args.slot:02d}"]
    elif args.template:
        targets = [TEMPLATE_DB]
    else:
        # An explicitly named database must exist (the connection raises
        # otherwise) and a read-only one needs the override, so a typo or a
        # locked name never exits 0 having done nothing.
        with closing(get_connection(args.dbname)) as conn, conn.cursor() as cur:
            cur.execute("SHOW default_transaction_read_only")
            if cur.fetchone()[0] == "on" and not args.write_locked_slot:
                parser.error(f"Database {args.dbname} is read-only")
        targets = [args.dbname]

    files = read_reference_files(args.manifest)
    failed = []
    for dbname in targets:
        status, counts = _load_target(
            dbname, files, write_locked_slot=args.write_locked_slot
        )
        detail = (
            " " + " ".join(f"{layer}={count}" for layer, count in counts.items())
            if counts
            else ""
        )
        print(f"{dbname}: {status}{detail}")
        if status == "failed":
            failed.append(dbname)
    if failed:
        LOG.error("Natural Earth load failed for %s", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
