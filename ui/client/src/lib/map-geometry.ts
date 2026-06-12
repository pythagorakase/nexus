/**
 * Pure geometry logic for the MapPane (no React, no DOM).
 *
 * This module concentrates the four historical failure modes documented in
 * docs/maptab_rebuild_spec.md §6 into testable pure functions:
 *
 *  1. Label culling        → computeLabelVisibility (priority + AABB overlap)
 *  2. Zoom-cursor anchoring → zoomViewBoxAtCursor (solve for the new origin
 *                             so the SVG point under the cursor stays put)
 *  3. Pointer capture       → DOM-coupled; lives in MapPane.tsx (see the
 *                             pointer handlers there), not here
 *  4. lng/lat ordering      → extractCoordinates (GeoJSON is [lng, lat])
 *
 * Unit tests: map-geometry.test.ts.
 */
import type { Place } from "@shared/schema";

export interface LatLng {
  latitude: number;
  longitude: number;
}

export interface ViewBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MapBounds {
  minLng: number;
  maxLng: number;
  minLat: number;
  maxLat: number;
}

export const MIN_ZOOM = 0.2;
export const MAX_ZOOM = 100;

/**
 * Minimum geographic span (degrees) for the projection fit. Without a
 * floor, a world with a single charted place collapses the bounding box
 * to ~0.0001° — fitSize then zooms the projection to a viewport a couple
 * of meters across, and nothing (grid, coastline, zone boundary) can
 * possibly be in frame. This was the slot-5 "blank void" bug.
 */
export const MIN_BOUNDS_SPAN_DEG = 1;

/** Polygonal GeoJSON accepted for zone survey boundaries. */
export interface BoundaryGeometry {
  type: "Polygon" | "MultiPolygon";
  coordinates: unknown[];
}

/**
 * The bundled Natural Earth outline is Earth's geography. Drawing it under
 * a generated world (e.g. the fictional planet "Veyport") would be fake
 * cartography, so the continents render only when the slot's world layer
 * is literally Earth.
 */
export function worldIsEarth(layers: Array<{ name: string }>): boolean {
  return layers.some((layer) => layer.name === "Earth");
}

/**
 * Parse a zone's boundary into validated polygonal GeoJSON.
 *
 * The API serves `ST_AsGeoJSON(boundary)::json`; depending on the driver
 * path the client may still receive it as a JSON string. Anything that is
 * not a Polygon/MultiPolygon with coordinates is dropped with a
 * console.warn — bad data must never take down the map.
 */
export function extractZoneBoundary(zone: {
  id: number;
  boundary?: unknown;
}): BoundaryGeometry | null {
  const raw = zone.boundary;
  if (raw === null || raw === undefined) return null;

  let geometry: unknown = raw;
  if (typeof raw === "string") {
    try {
      geometry = JSON.parse(raw);
    } catch {
      console.warn(`Zone ${zone.id} has unparseable boundary geometry`);
      return null;
    }
  }

  if (
    typeof geometry !== "object" ||
    geometry === null ||
    !("type" in geometry) ||
    !("coordinates" in geometry)
  ) {
    console.warn(`Zone ${zone.id} has invalid boundary structure`);
    return null;
  }

  const candidate = geometry as { type: unknown; coordinates: unknown };
  if (candidate.type !== "Polygon" && candidate.type !== "MultiPolygon") {
    console.warn(
      `Zone ${zone.id} has unsupported boundary type: ${String(candidate.type)}`,
    );
    return null;
  }
  if (!Array.isArray(candidate.coordinates) || candidate.coordinates.length === 0) {
    console.warn(`Zone ${zone.id} has empty boundary coordinates`);
    return null;
  }

  return candidate as BoundaryGeometry;
}

/**
 * Build the GeoJSON object that useGeoProjection feeds to fitSize.
 *
 * A bounding polygon ring is the natural choice but is a winding trap:
 * d3-geo polygons are SPHERICAL, so a ring wound the wrong way denotes
 * the complement of the box — fitSize then quietly fits the whole globe
 * and every regional map renders as a world-scale speck (the original
 * MapPane rebuild shipped with exactly that bug). Corner points carry no
 * winding, so the fit is unambiguous.
 */
export function boundsToFitObject(bounds: MapBounds): {
  type: "MultiPoint";
  coordinates: Array<[number, number]>;
} {
  return {
    type: "MultiPoint",
    coordinates: [
      [bounds.minLng, bounds.minLat],
      [bounds.maxLng, bounds.maxLat],
    ],
  };
}

/** Walk every [lng, lat] position in nested GeoJSON coordinate arrays. */
function forEachPosition(
  coords: unknown,
  visit: (lng: number, lat: number) => void,
): void {
  if (!Array.isArray(coords)) return;
  if (
    coords.length >= 2 &&
    typeof coords[0] === "number" &&
    typeof coords[1] === "number"
  ) {
    visit(coords[0], coords[1]);
    return;
  }
  for (const child of coords) forEachPosition(child, visit);
}

/**
 * Parse a place's GeoJSON geometry into validated lat/lng.
 *
 * GeoJSON Point coordinates are ordered [longitude, latitude] — the
 * opposite of spoken "lat/lng" (spec §6.4). Mixing the order mirrors every
 * pin across the diagonal, so this is the only place in the client where
 * the array is destructured.
 *
 * Invalid geometry returns null (with a console.warn): bad data must never
 * take down the whole map.
 */
export function extractCoordinates(place: Place): LatLng | null {
  if (!place.geometry) return null;

  try {
    if (typeof place.geometry !== "object" || !place.geometry.type) {
      console.warn(`Place ${place.id} has invalid geometry structure`);
      return null;
    }

    switch (place.geometry.type) {
      case "Point": {
        // GeoJSON Point order: [longitude, latitude, (elevation)]
        const [lng, lat] = place.geometry.coordinates as number[];

        if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
          console.warn(`Place ${place.id} has non-finite coordinates`);
          return null;
        }
        if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
          console.warn(`Place ${place.id} has out-of-range coordinates`);
          return null;
        }
        return { latitude: lat, longitude: lng };
      }

      case "Polygon":
      case "LineString":
        // Returned by the API but not yet rendered (spec §8 future work).
        return null;

      default:
        console.warn(
          `Place ${place.id} has unsupported geometry type: ${place.geometry.type}`,
        );
        return null;
    }
  } catch (error) {
    console.error(`Failed to parse geometry for place ${place.id}:`, error);
    return null;
  }
}

/**
 * Geographic bounding box across every place with valid coordinates plus
 * every rendered survey boundary, padded by 10% so border features don't
 * hug the canvas edge. Spans below MIN_BOUNDS_SPAN_DEG are widened around
 * their center (see the constant's doc). Returns null when nothing has
 * usable geometry (the projection then falls back to the whole world).
 */
export function computeMapBounds(
  places: Place[],
  boundaries: BoundaryGeometry[] = [],
): MapBounds | null {
  let minLng = Infinity;
  let maxLng = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;
  let found = false;

  const accumulate = (lng: number, lat: number) => {
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
    found = true;
    minLng = Math.min(minLng, lng);
    maxLng = Math.max(maxLng, lng);
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
  };

  for (const place of places) {
    const coords = extractCoordinates(place);
    if (coords) accumulate(coords.longitude, coords.latitude);
  }
  for (const boundary of boundaries) {
    forEachPosition(boundary.coordinates, accumulate);
  }

  if (!found) return null;

  // Widen degenerate spans before padding: a lone beacon should sit in a
  // regional frame, not a meters-wide one.
  if (maxLng - minLng < MIN_BOUNDS_SPAN_DEG) {
    const center = (minLng + maxLng) / 2;
    minLng = center - MIN_BOUNDS_SPAN_DEG / 2;
    maxLng = center + MIN_BOUNDS_SPAN_DEG / 2;
  }
  if (maxLat - minLat < MIN_BOUNDS_SPAN_DEG) {
    const center = (minLat + maxLat) / 2;
    minLat = center - MIN_BOUNDS_SPAN_DEG / 2;
    maxLat = center + MIN_BOUNDS_SPAN_DEG / 2;
  }

  const lngRange = maxLng - minLng;
  const latRange = maxLat - minLat;
  const padding = 0.1;

  return {
    minLng: Math.max(minLng - lngRange * padding, -180),
    maxLng: Math.min(maxLng + lngRange * padding, 180),
    minLat: Math.max(minLat - latRange * padding, -90),
    maxLat: Math.min(maxLat + latRange * padding, 90),
  };
}

/**
 * Keep the viewBox inside the projected map area so the user can never
 * pan the world fully out of frame (spec §4.3).
 */
export function clampViewBox(
  box: ViewBox,
  mapWidth: number,
  mapHeight: number,
): ViewBox {
  const safeWidth = Math.max(mapWidth, 1);
  const safeHeight = Math.max(mapHeight, 1);
  const maxX = Math.max(0, safeWidth - box.width);
  const maxY = Math.max(0, safeHeight - box.height);

  return {
    x: Math.min(Math.max(box.x, 0), maxX),
    y: Math.min(Math.max(box.y, 0), maxY),
    width: box.width,
    height: box.height,
  };
}

/**
 * Cursor-anchored zoom (spec §4.2 / §6.2).
 *
 * The viewBox is a window onto SVG space. Before the zoom, the SVG point
 * (svgX, svgY) sits under the cursor. After resizing the window we solve
 * for the new origin so that the same SVG point still sits at the cursor's
 * relative position. Skipping the origin solve is the classic
 * "zoom into the top-left corner" bug.
 *
 * @param prev      current viewBox
 * @param cursorX/Y cursor position in client px, relative to the SVG rect
 * @param rectW/H   the SVG element's client size in px
 * @param newZoom   the already-clamped target zoom factor
 */
export function zoomViewBoxAtCursor(
  prev: ViewBox,
  cursorX: number,
  cursorY: number,
  rectW: number,
  rectH: number,
  newZoom: number,
  mapWidth: number,
  mapHeight: number,
): ViewBox {
  // The SVG-space point currently under the cursor:
  const svgX = prev.x + cursorX * (prev.width / rectW);
  const svgY = prev.y + cursorY * (prev.height / rectH);

  // New window dimensions:
  const newWidth = Math.max(mapWidth, 1) / newZoom;
  const newHeight = Math.max(mapHeight, 1) / newZoom;

  // Solve for the new top-left so the cursor still hits (svgX, svgY):
  return clampViewBox(
    {
      x: svgX - (cursorX / rectW) * newWidth,
      y: svgY - (cursorY / rectH) * newHeight,
      width: newWidth,
      height: newHeight,
    },
    mapWidth,
    mapHeight,
  );
}

/** Clamp a raw wheel-derived zoom factor into the supported range. */
export function clampZoom(zoom: number): number {
  return Math.min(Math.max(zoom, MIN_ZOOM), MAX_ZOOM);
}

/**
 * Center the viewBox on an SVG-space point at the current zoom — used when
 * a sidebar row is clicked (spec §4.4).
 */
export function centerViewBoxOn(
  point: { x: number; y: number },
  prev: ViewBox,
  mapWidth: number,
  mapHeight: number,
): ViewBox {
  return clampViewBox(
    {
      x: point.x - prev.width / 2,
      y: point.y - prev.height / 2,
      width: prev.width,
      height: prev.height,
    },
    mapWidth,
    mapHeight,
  );
}

export interface LabelCandidate {
  placeId: number;
  /** stable index in the places array — used for zoom-stride sampling */
  index: number;
  /** projected SVG coordinates */
  coords: { x: number; y: number };
  /** 4 = selected, 3 = hovered, 2 = current narrative location, 1 = rest */
  priority: number;
  /**
   * Optional per-name label width in SVG units (long place names need a
   * wider collision box). Defaults to the spec's 80/zoom.
   */
  labelWidthUnits?: number;
}

/**
 * Zoom-stride gate for priority-1 labels (spec §6.1): at low zoom only a
 * deterministic sample of labels is even considered, so the map never
 * becomes a wall of text.
 */
export function shouldDisplayLabelByZoom(index: number, zoom: number): boolean {
  if (zoom >= 3.0) return true;
  if (zoom >= 2.0) return index % 5 === 0;
  if (zoom >= 1.5) return index % 10 === 0;
  if (zoom >= 1.0) return index % 20 === 0;
  return false;
}

/**
 * Priority + AABB label culling (spec §6.1).
 *
 * 1. Sort candidates by priority descending (selected > hovered > current
 *    location > rest), index ascending as the tiebreaker.
 * 2. Priority > 1 labels are force-visible; priority-1 labels must first
 *    pass the zoom-stride gate.
 * 3. Each surviving label's bounding box is tested against the boxes
 *    already accepted; overlapping non-forced labels are hidden.
 *
 * The naive alternative — "show all labels above zoom X" — yields both
 * unreadable overlap and a missing current-location label at low zoom.
 */
export function computeLabelVisibility(
  candidates: LabelCandidate[],
  zoom: number,
): Map<number, boolean> {
  const visibility = new Map<number, boolean>();
  const accepted: Array<{ x1: number; y1: number; x2: number; y2: number }> =
    [];

  const labelHeight = 16 / zoom;
  const labelOffsetY = 25 / zoom;

  const ordered = [...candidates].sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    return a.index - b.index;
  });

  for (const { placeId, index, coords, priority, labelWidthUnits } of ordered) {
    const forceVisible = priority > 1;

    if (!forceVisible && !shouldDisplayLabelByZoom(index, zoom)) {
      visibility.set(placeId, false);
      continue;
    }

    const labelWidth = labelWidthUnits ?? 80 / zoom;
    const rect = {
      x1: coords.x - labelWidth / 2,
      y1: coords.y - labelOffsetY,
      x2: coords.x + labelWidth / 2,
      y2: coords.y - labelOffsetY + labelHeight,
    };

    const overlaps = accepted.some(
      (box) =>
        !(
          rect.x2 < box.x1 ||
          rect.x1 > box.x2 ||
          rect.y2 < box.y1 ||
          rect.y1 > box.y2
        ),
    );

    if (overlaps && !forceVisible) {
      visibility.set(placeId, false);
      continue;
    }

    accepted.push(rect);
    visibility.set(placeId, true);
  }

  return visibility;
}
