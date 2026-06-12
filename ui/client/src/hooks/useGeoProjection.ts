/**
 * Custom hook for D3.js geographic projection handling.
 *
 * Provides proper date-line crossing, polygon winding, and anti-meridian
 * cutting that the custom linear transform cannot handle correctly.
 *
 * This hook enables future support for alternate map data (paleographic maps,
 * fictional worlds) by using D3's data-agnostic projection system.
 */

import { useMemo, useCallback } from "react";
import { geoEquirectangular, geoPath } from "d3-geo";
import type { GeoProjection, GeoPath, GeoPermissibleObjects } from "d3-geo";

import { boundsToFitObject } from "@/lib/map-geometry";

interface MapBounds {
  minLng: number;
  maxLng: number;
  minLat: number;
  maxLat: number;
}

interface MapDimensions {
  width: number;
  height: number;
}

interface ProjectionConfig {
  mapDimensions: MapDimensions;
  mapBounds: MapBounds | null;
}

interface UseGeoProjectionResult {
  /** D3 projection function for coordinate transforms */
  projection: GeoProjection;
  /** D3 path generator for converting GeoJSON to SVG paths */
  pathGenerator: GeoPath<unknown, GeoPermissibleObjects>;
  /** Transform geographic coordinates to SVG coordinates (returns null if projection fails) */
  transformCoordinates: (lng: number, lat: number) => { x: number; y: number } | null;
  /** Convert GeoJSON geometry to SVG path string */
  geoJsonToSvgPath: (geometry: GeoPermissibleObjects | null | undefined) => string | null;
}

/**
 * Hook that creates a D3 geographic projection and path generator.
 *
 * @param config - Map dimensions and optional geographic bounds
 * @returns Projection utilities for coordinate transforms and path generation
 *
 * @example
 * ```tsx
 * const { transformCoordinates, geoJsonToSvgPath } = useGeoProjection({
 *   mapDimensions: { width: 1000, height: 600 },
 *   mapBounds: { minLng: -180, maxLng: 180, minLat: -90, maxLat: 90 }
 * });
 *
 * // Transform a point
 * const { x, y } = transformCoordinates(178.5, -17.5); // Fiji
 *
 * // Generate SVG path from GeoJSON
 * const pathD = geoJsonToSvgPath(continentGeometry);
 * ```
 */
export function useGeoProjection({ mapDimensions, mapBounds }: ProjectionConfig): UseGeoProjectionResult {
  const projection = useMemo<GeoProjection>(() => {
    const bounds = mapBounds || {
      minLng: -180,
      maxLng: 180,
      minLat: -90,
      maxLat: 90
    };

    const proj = geoEquirectangular();

    // Fit the projection to the requested geographic area. NOTE: this must
    // NOT be a polygon ring — d3-geo polygons are spherical, and a ring
    // wound the wrong way means "everything but this box", which makes
    // fitSize quietly fit the entire globe (regional maps then render as
    // world-scale specks). boundsToFitObject uses winding-free corner
    // points instead; see its doc comment in lib/map-geometry.ts.
    proj.fitSize(
      [mapDimensions.width, mapDimensions.height],
      boundsToFitObject(bounds)
    );

    return proj;
  }, [mapDimensions.width, mapDimensions.height, mapBounds]);

  const pathGenerator = useMemo<GeoPath<unknown, GeoPermissibleObjects>>(() => {
    return geoPath().projection(projection);
  }, [projection]);

  const transformCoordinates = useCallback((lng: number, lat: number): { x: number; y: number } | null => {
    const coords = projection([lng, lat]);
    if (!coords) {
      // Return null for fail-fast behavior - callers should handle missing coordinates
      console.warn(`Failed to project coordinates: [${lng}, ${lat}]`);
      return null;
    }
    return { x: coords[0], y: coords[1] };
  }, [projection]);

  const geoJsonToSvgPath = useCallback((geometry: GeoPermissibleObjects | null | undefined): string | null => {
    if (!geometry) return null;

    // D3's pathGenerator handles all the complex cases:
    // - Date-line crossing (anti-meridian cutting)
    // - Polygon winding (interior vs exterior rings)
    // - Sphere clipping
    // - Multi-geometry types (MultiPolygon, MultiLineString, etc.)
    const path = pathGenerator(geometry);
    return path || null;
  }, [pathGenerator]);

  return {
    projection,
    pathGenerator,
    transformCoordinates,
    geoJsonToSvgPath
  };
}
