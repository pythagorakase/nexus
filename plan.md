# 1) Tips for integrating `geoalchemy2` now (for Claude Code)

**Goal:** let SQLAlchemy understand PostGIS types, and give you clean helpers for proximity/containment without changing your DB layout.

## A. Install + import (registers PostGIS types so reflection stops warning)

```bash
# psycopg3 path (recommended)
pip install "geoalchemy2>=0.15" "psycopg[binary]" shapely

# or psycopg2 classic
pip install geoalchemy2 psycopg2-binary shapely
```

In your Python bootstrap (before reflecting/declaring models):

```python
# registers geometry/geography with the PG dialect
import geoalchemy2  # noqa: F401
```

_(If you’re using SQLAlchemy Automap/Inspector, that import alone is enough to avoid the  
“Did not recognize type 'geometry/geography'” warnings.)_

## B. Add one computed `geometry` column for fast KNN

`places.coordinates` is `geography(PointZM,4326)` (great for meters). Add a stored cast for **KNN** and spatial overlays:

```sql
ALTER TABLE public.places
  ADD COLUMN IF NOT EXISTS geom geometry(Point,4326)
  GENERATED ALWAYS AS (coordinates::geometry) STORED;

CREATE INDEX IF NOT EXISTS idx_places_geom_gist
  ON public.places USING gist (geom);
```

(You already have `zones.boundary` as `geometry(MULTIPOLYGON,4326)` with a GiST index—perfect.)

## C. Minimal ORM models (only what you need)

```python
# models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey
from geoalchemy2 import Geometry, Geography

class Base(DeclarativeBase): pass

class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    boundary = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326))
    places = relationship("Place", back_populates="zone_fk")

class Place(Base):
    __tablename__ = "places"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    zone: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    coordinates = mapped_column(Geography(geometry_type="POINT", srid=4326))  # your real column
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326))          # generated column
    zone_fk = relationship("Zone", back_populates="places")
```

## D. Two core queries you said you’ll want

**Containment** (places in the same zone as a given place, with meters + KNN ordering):

```python
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from models import Place

def places_in_same_zone(session: Session, place_id: int, limit: int | None = None):
    origin = session.get(Place, place_id)
    if not origin or origin.zone is None:
        return []

    q = (
        select(
            Place.id,
            Place.name,
            func.ST_DistanceSphere(Place.geom, origin.geom).label("meters")
        )
        .where(Place.zone == origin.zone, Place.id != origin.id)
        .order_by(Place.geom.op("<->")(origin.geom))  # KNN index
    )
    if limit:
        q = q.limit(limit)
    return session.execute(q).all()
```

**Nearest-N to arbitrary lon/lat** (cross-zone):

```python
from models import Place, Zone

def nearest_places(session: Session, lon: float, lat: float, k: int = 10):
    pt = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    q = (
        select(
            Place.id,
            Place.name,
            Zone.name.label("zone_name"),
            func.ST_DistanceSphere(Place.geom, pt).label("meters")
        )
        .join(Zone, Zone.id == Place.zone, isouter=True)
        .order_by(Place.geom.op("<->")(pt))  # KNN
        .limit(k)
    )
    return session.execute(q).all()
```

**Nice to add** (for narration): bearing & travel-time estimate

```python
bearing_deg = func.degrees(func.ST_Azimuth(origin.geom, Place.geom)).label("bearing_deg")
eta_min = (func.ST_DistanceSphere(Place.geom, origin.geom) / 1000.0 / 70.0 * 60.0).label("eta_min")  # 70 km/h motorcycle
```

## E. Keep LLM payloads tiny (optional views)

```sql
CREATE OR REPLACE VIEW v_llm_places AS
SELECT id, name,
       ROUND(ST_Y(coordinates::geometry)::numeric, 6) AS lat,
       ROUND(ST_X(coordinates::geometry)::numeric, 6) AS lon,
       zone
FROM public.places;

CREATE OR REPLACE VIEW v_llm_zones AS
SELECT id, name,
       ROUND(ST_Y(ST_Centroid(boundary))::numeric, 6) AS centroid_lat,
       ROUND(ST_X(ST_Centroid(boundary))::numeric, 6) AS centroid_lon,
       ST_AsGeoJSON(ST_SimplifyPreserveTopology(boundary, 0.05)) AS boundary_geojson
FROM public.zones;
```

Use these for a compact “atlas” JSON that GAIA or LORE can attach to a chunk; keep heavy geometries in PostGIS.

**Gotchas to remember**
- Use `geometry` for KNN/overlays; use `geography` (or `ST_DistanceSphere`) for meters.
- For zones that cross the antimeridian, prefer **MultiPolygon** (two lobes) or run `ST_ShiftLongitude` once.
- GiST indexes on `zones.boundary` and `places.geom` are key to speed.

# 2) Guidance for updating `docs/blueprint_gaia.md` (future use)

Here’s a concise outline you can paste into the doc.

---

## GAIA: World State Tracker – Spatial Mini-Map Plan

### 1. Purpose

Produce a per-scene “mini-map” pack for the narrator:
- **Containment:** other `places` in the current `zone`.
- **Proximity:** nearest `places` to the current `place` and to arbitrary mentions.
- **Summaries:** human-readable distance, bearing, and rough travel time.

### 2. Data contracts

**Postgres inputs**
- `places(id, name, zone, coordinates: geography(PointZM,4326), geom: geometry(Point,4326))`
- `zones(id, name, boundary: geometry(MULTIPOLYGON,4326))`

**Read views for LLM/GAIA (lightweight)**
- `v_llm_places(id, name, lat, lon, zone)`
- `v_llm_zones(id, name, centroid_lat, centroid_lon, boundary_geojson [simplified])`
_(Views keep tokens low; full geometry stays in DB.)_

### 3. Core algorithms

- **Same-zone neighbors**
    - Input: `origin_place_id`
    - SQL/ORM:
        - filter `Place.zone == origin.zone`
        - sort by `geom <-> origin.geom` (KNN)
        - compute `ST_DistanceSphere` for meters
    - Output fields: `place_id`, `name`, `meters`, `bearing_deg`, `eta_min`
- **Nearest-N to arbitrary lon/lat**
    - Input: `lon, lat, k`
    - KNN order by `geom <-> ST_SetSRID(ST_MakePoint(lon,lat),4326)`
    - Add meters via `ST_DistanceSphere`
- **Containment (on demand)**
    - If FK is missing or needs verification:
        - `ST_Contains(zones.boundary, places.geom)`
- **Optional**: “far mentions”
    - If a mentioned place is in another zone, include it with meters/bearing for contrast.

### 4. Output JSON schema (example)

```json
{
  "origin": {
    "id": 181,
    "name": "The Silo",
    "zone": "Badlands",
    "lat": 38.123456,
    "lon": -76.123456
  },
  "same_zone_nearby": [
    {"id": 190, "name": "Old Pump Station", "km": 4.2, "bearing_deg": 110.0, "eta_min_moto": 4.0},
    {"id": 175, "name": "Dry Dock", "km": 7.8, "bearing_deg": 255.0, "eta_min_moto": 7.0}
  ],
  "global_mentions": [
    {"id": 119, "name": "Night City Streets", "km": 52.6, "bearing_deg": 300.0, "eta_min_moto": 45.0}
  ],
  "zone_outline_geojson": "{...simplified polygon...}"
}
```

### 5. API surface (internal)

- `gaia.places_in_same_zone(place_id: int, limit: int=10) -> List[Neighbor]`
- `gaia.nearest_places(lon: float, lat: float, k: int=10) -> List[Neighbor]`
- `gaia.minimap_for_chunk(origin_place_id: int, mentions: List[int]) -> Dict`

### 6. Performance & indexing

- Ensure:
    - `CREATE INDEX idx_places_geom_gist ON places USING gist (geom);`
    - `CREATE INDEX idx_zones_boundary_gist ON zones USING gist (boundary);` 
- For huge datasets: pre-filter with `ST_DWithin(..., radius_m)` before KNN.

### 7. Edge cases / geometry hygiene

- **Antimeridian:** store ocean-scale regions as **MultiPolygon** (two parts) or `ST_ShiftLongitude` after digitising.
- **Topology:** use snapping/topological editing in QGIS so zone mosaics are gap-free.
- **SRIDs:** keep everything in 4326; distances via `ST_DistanceSphere`/`geography`.

### 8. Testing

- Unit tests for:
    - KNN results are monotonic with distance.
    - Containment agrees with FK for a sample set.
    - JSON payloads stay under target token budget.
- Golden-file tests for `v_llm_*` views.

### 9. Roadmap

- **Now:** add `geom`, indexes, and two queries; expose `v_llm_*` views.
- **Soon:** `gaia.minimap_for_chunk()` that returns the JSON schema above.
- **Later:** triggers to auto-assign `places.zone` on coordinate change; caching of per-zone neighbor lists; optional map tile snapshots.
