"""Pinned Natural Earth reference geometry and the queries that read it.

Issue #840, slice S1 (Decisions 840-Q1 and 840-Q2): the 10m ``land``,
``admin_0`` and ``admin_1`` layers of one pinned Natural Earth release are
vendored under ``data/natural_earth/`` and described by its ``manifest.json``.
``scripts/load_natural_earth.py`` checks the files against the manifest and
loads them into each story database's ``public.natural_earth_features`` table
(migration 147); fresh slots copy the rows from the template as seed data.

Every query function takes the caller's cursor, so it runs inside the
caller's transaction, and first proves the table holds exactly the manifest's
release and feature counts. A missing or partial load raises
``ReferenceDataError``; it never reads as open ocean.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus.runtime.home import repo_root

LayerName = Literal["land", "admin_0", "admin_1"]
REGION_LAYERS: tuple[str, ...] = ("admin_0", "admin_1")
LAYER_NAMES: tuple[str, ...] = ("land", "admin_0", "admin_1")

MANIFEST_PATH = repo_root() / "data" / "natural_earth" / "manifest.json"


class ReferenceDataError(RuntimeError):
    """The reference table does not hold the manifest's release and counts."""


class RegionNotFoundError(LookupError):
    """No reference region has the requested name."""


class AmbiguousRegionError(LookupError):
    """Several reference regions share the requested name."""

    def __init__(self, message: str, candidates: tuple["ReferenceRegion", ...]):
        super().__init__(message)
        self.candidates = candidates


class InvalidGeometryError(ValueError):
    """A caller's GeoJSON is not a valid Polygon or MultiPolygon, or clips away."""


class NaturalEarthLayer(BaseModel):
    """One vendored Natural Earth layer: its zip, shapefile and pinned digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layer: LayerName
    file: str = Field(min_length=1)
    shapefile: str = Field(min_length=1)
    url: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_count: int = Field(gt=0)


class NaturalEarthRepair(BaseModel):
    """One source feature that is invalid as published and repaired at load."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layer: Literal["admin_0", "admin_1"]
    ne_id: int
    reason: str = Field(min_length=1)


class NaturalEarthManifest(BaseModel):
    """The pinned Natural Earth release: three layers and the expected repairs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset: str = Field(min_length=1)
    release: str = Field(min_length=1)
    scale: str = Field(min_length=1)
    license: str = Field(min_length=1)
    layers: tuple[NaturalEarthLayer, ...]
    repairs: tuple[NaturalEarthRepair, ...]

    @model_validator(mode="after")
    def _exactly_three_unique_layers(self) -> "NaturalEarthManifest":
        names = [layer.layer for layer in self.layers]
        if len(names) != len(set(names)) or set(names) != set(LAYER_NAMES):
            raise ValueError(
                f"Manifest layers must be exactly {', '.join(LAYER_NAMES)}, "
                f"each once; got {names}"
            )
        repairs = [(repair.layer, repair.ne_id) for repair in self.repairs]
        if len(repairs) != len(set(repairs)):
            raise ValueError(f"Manifest repairs repeat a feature: {repairs}")
        return self

    def layer(self, name: str) -> NaturalEarthLayer:
        """Return the manifest entry for layer ``name``."""
        for layer in self.layers:
            if layer.layer == name:
                return layer
        raise KeyError(name)


def load_manifest(path: Path = MANIFEST_PATH) -> NaturalEarthManifest:
    """Read and validate a Natural Earth manifest."""
    return NaturalEarthManifest.model_validate(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


@lru_cache(maxsize=1)
def _pinned_manifest() -> NaturalEarthManifest:
    return load_manifest(MANIFEST_PATH)


@dataclass(frozen=True)
class ReferenceRegion:
    """One named administrative region of the reference table."""

    layer: str
    ne_id: int
    name: str
    adm0_a3: str
    adm1_code: Optional[str]
    iso_code: Optional[str]

    @property
    def code(self) -> str:
        """The region's identifying code: ``adm1_code`` or ``adm0_a3``."""
        if self.layer == "admin_1" and self.adm1_code is not None:
            return self.adm1_code
        return self.adm0_a3


_REFERENCE_STATE_SQL = """
    SELECT layer, count(*), count(*) FILTER (WHERE release <> %s)
    FROM natural_earth_features
    GROUP BY layer
"""


def require_reference(cur: Any) -> None:
    """Raise ``ReferenceDataError`` unless the table holds the pinned release.

    Each layer must hold exactly the manifest's ``feature_count`` rows, all
    stamped with the manifest's ``release``.
    """
    manifest = _pinned_manifest()
    cur.execute(_REFERENCE_STATE_SQL, (manifest.release,))
    state = {row[0]: (int(row[1]), int(row[2])) for row in cur.fetchall()}
    problems = []
    for layer in manifest.layers:
        rows, off_release = state.get(layer.layer, (0, 0))
        if rows != layer.feature_count or off_release:
            problems.append(
                f"{layer.layer} holds {rows} rows (manifest {layer.feature_count}),"
                f" {off_release} not at release {manifest.release}"
            )
    if problems:
        raise ReferenceDataError(
            "Natural Earth reference data is missing or stale: "
            + "; ".join(problems)
            + ". Load it with scripts/load_natural_earth.py."
        )


def lookup_region(
    cur: Any, name: str, *, layer: str, adm0_a3: Optional[str] = None
) -> ReferenceRegion:
    """Resolve one ``admin_0`` or ``admin_1`` region by case-insensitive name.

    ``adm0_a3`` narrows the match to one country. Raises
    ``RegionNotFoundError`` when nothing matches and ``AmbiguousRegionError``,
    listing every candidate's code, when several do.
    """
    if layer not in REGION_LAYERS:
        raise ValueError(f"layer must be one of {REGION_LAYERS}, got {layer!r}")
    require_reference(cur)
    query = (
        "SELECT layer, ne_id, name, adm0_a3, adm1_code, iso_code "
        "FROM natural_earth_features "
        "WHERE layer = %s AND lower(name) = lower(%s)"
    )
    params: list[Any] = [layer, name]
    if adm0_a3 is not None:
        query += " AND adm0_a3 = %s"
        params.append(adm0_a3)
    cur.execute(query + " ORDER BY ne_id", params)
    regions = tuple(
        ReferenceRegion(
            layer=row[0],
            ne_id=int(row[1]),
            name=row[2],
            adm0_a3=row[3],
            adm1_code=row[4],
            iso_code=row[5],
        )
        for row in cur.fetchall()
    )
    scope = f" in {adm0_a3}" if adm0_a3 is not None else ""
    if not regions:
        raise RegionNotFoundError(f"No {layer} region named {name!r}{scope}")
    if len(regions) > 1:
        codes = ", ".join(region.code for region in regions)
        raise AmbiguousRegionError(
            f"{len(regions)} {layer} regions are named {name!r}{scope}: {codes}",
            regions,
        )
    return regions[0]


def point_on_land(cur: Any, *, longitude: float, latitude: float) -> bool:
    """Return whether a WGS 84 point is covered by a ``land`` feature."""
    if not (math.isfinite(longitude) and -180.0 <= longitude <= 180.0):
        raise ValueError(f"longitude out of range: {longitude!r}")
    if not (math.isfinite(latitude) and -90.0 <= latitude <= 90.0):
        raise ValueError(f"latitude out of range: {latitude!r}")
    require_reference(cur)
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM natural_earth_features "
        "WHERE layer = 'land' "
        "AND ST_Covers(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)))",
        (longitude, latitude),
    )
    return bool(cur.fetchone()[0])


def _geojson_text(geojson: Mapping[str, Any] | str) -> str:
    return geojson if isinstance(geojson, str) else json.dumps(geojson)


_INPUT_SQL = "SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS geom"


def _require_valid_polygon(cur: Any, geojson_text: str) -> None:
    cur.execute(
        f"WITH input AS ({_INPUT_SQL}) "
        "SELECT GeometryType(geom), ST_IsValid(geom), ST_IsValidReason(geom) "
        "FROM input",
        (geojson_text,),
    )
    geometry_type, valid, reason = cur.fetchone()
    if geometry_type not in ("POLYGON", "MULTIPOLYGON"):
        raise InvalidGeometryError(
            f"Expected a Polygon or MultiPolygon, got {geometry_type}"
        )
    if not valid:
        raise InvalidGeometryError(f"Invalid polygon: {reason}")


def require_valid_polygon(cur: Any, geojson: Mapping[str, Any] | str) -> None:
    """Raise ``InvalidGeometryError`` unless ``geojson`` is a valid polygon.

    The geometry is read with SRID 4326; the error carries
    ``ST_IsValidReason`` for an invalid one, and names the type of anything
    that is not a Polygon or MultiPolygon.
    """
    require_reference(cur)
    _require_valid_polygon(cur, _geojson_text(geojson))


# The land part of the input: the union of its intersections with every land
# feature it touches, kept as polygons only.
_LAND_PART_SQL = f"""
    WITH input AS ({_INPUT_SQL})
    SELECT ST_Multi(ST_CollectionExtract(ST_UnaryUnion(ST_Collect(
               ST_Intersection(f.geom, input.geom))), 3)) AS geom
    FROM natural_earth_features AS f
    CROSS JOIN input
    WHERE f.layer = 'land' AND ST_Intersects(f.geom, input.geom)
"""


def clip_to_land(cur: Any, geojson: Mapping[str, Any] | str) -> dict[str, Any]:
    """Return the land part of a valid polygon as a GeoJSON MultiPolygon.

    Raises ``InvalidGeometryError`` when the input is invalid or no land
    area remains.
    """
    require_reference(cur)
    text = _geojson_text(geojson)
    _require_valid_polygon(cur, text)
    cur.execute(
        f"WITH land AS ({_LAND_PART_SQL}) "
        "SELECT ST_AsGeoJSON(geom), geom IS NULL OR ST_IsEmpty(geom) FROM land",
        (text,),
    )
    clipped, empty = cur.fetchone()
    if empty:
        raise InvalidGeometryError("The polygon covers no land")
    return dict(json.loads(clipped))


def land_coverage(cur: Any, geojson: Mapping[str, Any] | str) -> float:
    """Return the land share of a valid polygon's geography area (0.0 to 1.0)."""
    require_reference(cur)
    text = _geojson_text(geojson)
    _require_valid_polygon(cur, text)
    cur.execute(
        f"WITH land AS ({_LAND_PART_SQL}), input AS ({_INPUT_SQL}) "
        "SELECT ST_Area(input.geom::geography), "
        "COALESCE(ST_Area(land.geom::geography), 0) "
        "FROM input CROSS JOIN land",
        (text, text),
    )
    input_area, land_area = cur.fetchone()
    if not input_area:
        raise InvalidGeometryError("The polygon has no area")
    return float(land_area) / float(input_area)
