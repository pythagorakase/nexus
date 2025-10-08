# GeoJSON Integration with PostGIS

## Overview

Places use PostGIS native `geography` type for coordinates, with GeoJSON as the standard interchange format. This architecture provides flexibility for future spatial features like boundaries, routes, and zones.

## Database Structure

### PostGIS Column

```sql
places (
  -- ... other fields
  coordinates geography(Point, 4326) NOT NULL
  -- 4326 = WGS 84 coordinate system (standard lat/lng)
)
```

### Why Geography Type?

- **Native spatial queries**: ST_Distance, ST_Within, ST_DWithin, etc.
- **Automatic projection handling**: Works with lat/lng directly
- **Future-proof**: Supports Points, Polygons, LineStrings, MultiPolygons
- **Index support**: Can create spatial indexes for performance

## Backend Implementation

### Returning GeoJSON

The backend extracts GeoJSON using PostGIS's `ST_AsGeoJSON` function:

```typescript
// storage.ts - getAllPlaces()
const result = await this.db.execute(sql`
  SELECT
    id,
    name,
    -- ... other fields
    ST_AsGeoJSON(coordinates)::json as geometry
  FROM places
`);
```

### GeoJSON Format

PostGIS returns standard GeoJSON geometry objects:

```json
{
  "type": "Point",
  "coordinates": [longitude, latitude, elevation]
}
```

**Important**: GeoJSON uses `[lng, lat]` order, opposite of typical `[lat, lng]`!

## Frontend Implementation

### Parsing Coordinates

```typescript
// MapTab.tsx - extractCoordinates()
const extractCoordinates = (place: Place): { latitude: number; longitude: number } | null => {
  if (!place.geometry) return null;

  try {
    // Validate geometry structure
    if (typeof place.geometry !== 'object' || !place.geometry.type) {
      console.warn(`Place ${place.id} has invalid geometry structure`);
      return null;
    }

    switch (place.geometry.type) {
      case 'Point': {
        // GeoJSON Point format: [longitude, latitude]
        const [lng, lat] = place.geometry.coordinates;

        // Validate finite numbers
        if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
          console.warn(`Place ${place.id} has non-finite coordinates`);
          return null;
        }

        // Validate coordinate ranges
        if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
          console.warn(`Place ${place.id} has out-of-range coordinates`);
          return null;
        }

        return { latitude: lat, longitude: lng };
      }

      case 'Polygon':
      case 'LineString':
        // Not yet implemented
        return null;

      default:
        console.warn(`Unsupported geometry type: ${place.geometry.type}`);
        return null;
    }
  } catch (error) {
    console.error(`Failed to parse geometry for place ${place.id}:`, error);
    return null;
  }
};
```

### Error Handling

The `extractCoordinates` function validates:

1. **Structure**: Geometry object exists and has `type` field
2. **Coordinates**: Array with at least 2 elements
3. **Finite values**: No NaN, Infinity, or undefined
4. **Valid ranges**:
   - Latitude: -90 to 90
   - Longitude: -180 to 180

Invalid geometries return `null` and log warnings for debugging.

## TypeScript Type Safety

```typescript
// shared/schema.ts
export type Place = typeof places.$inferSelect & {
  geometry?: any | null; // GeoJSON geometry from ST_AsGeoJSON
};
```

Currently uses `any` for flexibility. Could be refined with proper GeoJSON types:

```typescript
type GeoJSONPoint = {
  type: 'Point';
  coordinates: [number, number] | [number, number, number];
};

type GeoJSONPolygon = {
  type: 'Polygon';
  coordinates: number[][][];
};

type PlaceGeometry = GeoJSONPoint | GeoJSONPolygon | LineString | null;
```

## Future Enhancements

### Polygon Support (Boundaries/Zones)

```typescript
case 'Polygon': {
  // Calculate centroid for map pin
  const centroid = calculateCentroid(place.geometry.coordinates[0]);
  return centroid;
}
```

### LineString Support (Routes/Paths)

```typescript
case 'LineString': {
  // Use midpoint for map pin
  const coords = place.geometry.coordinates;
  const midIdx = Math.floor(coords.length / 2);
  const [lng, lat] = coords[midIdx];
  return { latitude: lat, longitude: lng };
}
```

### PostGIS Queries

With native geography type, we can perform:

```sql
-- Find places within 10km of a point
SELECT * FROM places
WHERE ST_DWithin(coordinates, ST_MakePoint(-122.4194, 37.7749)::geography, 10000);

-- Find places within a polygon boundary
SELECT * FROM places
WHERE ST_Within(coordinates, ST_GeomFromGeoJSON('{"type":"Polygon",...}'));

-- Calculate distance between two places
SELECT ST_Distance(
  (SELECT coordinates FROM places WHERE id = 1),
  (SELECT coordinates FROM places WHERE id = 2)
) / 1000 as km;
```

## Migration Path

### Old Approach (Before GeoJSON)

Previously, coordinates were stored as separate `latitude` and `longitude` columns. The migration to PostGIS geography:

1. Preserved existing data in PostGIS `coordinates` column
2. Backend converts to GeoJSON via `ST_AsGeoJSON`
3. Frontend extracts lat/lng from GeoJSON for map rendering

### Benefits of Migration

- **Extensibility**: Can add boundaries (Polygons), routes (LineStrings), zones (MultiPolygons)
- **Spatial queries**: Native PostGIS functions for distance, containment, intersection
- **Standards compliance**: GeoJSON is widely supported format
- **Future mapping features**: Ready for advanced visualizations

## Best Practices

1. **Always validate**: Use extractCoordinates helper, don't access geometry.coordinates directly
2. **Handle nulls gracefully**: Missing or invalid coordinates should not crash the app
3. **Log warnings**: Help debug data quality issues
4. **Coordinate order**: Remember GeoJSON uses [lng, lat], not [lat, lng]
5. **Ranges**: Validate latitude (-90 to 90) and longitude (-180 to 180)
