/**
 * Pure geometry logic for the MapPane (no React, no DOM).
 *
 * This module concentrates the historical failure modes documented in
 * docs/maptab_rebuild_spec.md §6 into testable pure functions:
 *
 *  1. Label culling        → computeLabelVisibility (priority + AABB overlap)
 *  2. Zoom-cursor anchoring → zoomViewBoxAtCursor (solve for the new origin
 *                             so the SVG point under the cursor stays put)
 *  3. Pointer capture       → the capture calls are DOM-coupled and live in
 *                             MapPane.tsx, but the drag lifecycle itself
 *                             (active-pointer guard, click-vs-drag movement
 *                             threshold, incremental deltas) is the pure
 *                             drag-session machine here: beginDragSession /
 *                             applyDragMove / endDragSession
 *  4. lng/lat ordering      → extractCoordinates (GeoJSON is [lng, lat])
 *  5. Spherical fit winding → boundsToFitObject (winding-free corner points
 *                             for fitSize; a bounding polygon ring wound
 *                             the wrong way fits the whole globe)
 *
 * Plus two view rules that keep the map honest about what it shows:
 *
 *  - Resize refit          → preserveViewAcrossRefit (the projection refits
 *                             to every canvas size; the pan/zoom window is
 *                             carried across as a geographic center + zoom)
 *  - Coincident pins       → offsetCoincidentPins (places sharing a point
 *                             fan out onto a small ring, deterministically)
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

/**
 * The projected extent the pan/zoom window is allowed to roam, in SVG
 * units (for MapPane this is the whole projected world, i.e. the Natural
 * Earth box [-180..180, -90..90] pushed through the current projection).
 */
export interface PanBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export const MIN_ZOOM = 0.2;
export const MAX_ZOOM = 100;

/**
 * Pointer movement (client px, straight-line from pointerdown) below which
 * a press-release is a click, at or above which it is a pan. Keeps
 * click-to-select working: a click with a couple px of jitter still
 * selects, while any real drag suppresses selection.
 */
export const DRAG_THRESHOLD_PX = 4;

/**
 * Fraction of the viewport (per axis) that must still overlap the world
 * after clamping — the user can pan anywhere on the globe, but can never
 * drag the world fully off-screen and get lost in the void.
 *
 * Must stay ≤ 0.5: above that, the clamp range in clampViewBox inverts
 * whenever the world box is smaller than the window (deep zoom-out), and
 * min/max clamping silently pins the view to one bound. Guarded below.
 */
export const MIN_WORLD_VISIBLE_FRACTION = 0.2;

if (MIN_WORLD_VISIBLE_FRACTION > 0.5) {
  throw new Error(
    "MIN_WORLD_VISIBLE_FRACTION must be <= 0.5: larger fractions invert " +
      "the clampViewBox range when the world is smaller than the window",
  );
}

/**
 * Minimum geographic span (degrees) for the projection fit. Without a
 * floor, a world with a single charted place collapses the bounding box
 * to ~0.0001° — fitSize then zooms the projection to a viewport a couple
 * of meters across, and no coastline can possibly be in frame. Part of
 * the slot-5 "blank void" bug (with failure mode 5).
 */
export const MIN_BOUNDS_SPAN_DEG = 1;

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
 * Geographic bounding box across every place with valid coordinates,
 * padded by 10% so border pins don't hug the canvas edge. Spans below
 * MIN_BOUNDS_SPAN_DEG are widened around their center (see the
 * constant's doc). Returns null when no place has usable geometry (the
 * projection then falls back to the whole world).
 */
export function computeMapBounds(places: Place[]): MapBounds | null {
  let minLng = Infinity;
  let maxLng = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;
  let found = false;

  for (const place of places) {
    const coords = extractCoordinates(place);
    if (!coords) continue;
    found = true;
    minLng = Math.min(minLng, coords.longitude);
    maxLng = Math.max(maxLng, coords.longitude);
    minLat = Math.min(minLat, coords.latitude);
    maxLat = Math.max(maxLat, coords.latitude);
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
 * Pan-bounds clamp (spec §4.3, reworked).
 *
 * The original clamp confined the window to the initially fitted region
 * ([0..mapWidth] × [0..mapHeight]) — at 1.00× zoom that range has zero
 * slack, so dragging was a silent no-op and the map "had no panning".
 *
 * The window may now roam the entire projected world; the only rule is
 * that at least MIN_WORLD_VISIBLE_FRACTION of the viewport (per axis)
 * must still overlap the world box, so the map can never be dragged
 * fully off-screen. When the window is larger than the world (deep
 * zoom-out), the same arithmetic keeps the world inside the window.
 */
export function clampViewBox(box: ViewBox, world: PanBounds): ViewBox {
  const keepX = box.width * MIN_WORLD_VISIBLE_FRACTION;
  const keepY = box.height * MIN_WORLD_VISIBLE_FRACTION;

  // Range is never inverted: maxX ≥ minX ⇔ worldWidth ≥ -(1 - 2f)·boxWidth,
  // which holds for any fraction f ≤ 0.5.
  const minX = world.minX - box.width + keepX;
  const maxX = world.maxX - keepX;
  const minY = world.minY - box.height + keepY;
  const maxY = world.maxY - keepY;

  return {
    x: Math.min(Math.max(box.x, minX), maxX),
    y: Math.min(Math.max(box.y, minY), maxY),
    width: box.width,
    height: box.height,
  };
}

/**
 * Drag-to-pan (spec §4.1): convert a pointer delta in client px into a
 * viewBox translation in SVG units. The delta divides by the current
 * zoom (prev.width / rectW), so a given mouse movement always moves the
 * map the same distance ON SCREEN regardless of zoom level.
 */
export function panViewBox(
  prev: ViewBox,
  deltaXPx: number,
  deltaYPx: number,
  rectW: number,
  rectH: number,
  world: PanBounds,
): ViewBox {
  const scaleX = prev.width / Math.max(rectW, 1);
  const scaleY = prev.height / Math.max(rectH, 1);

  return clampViewBox(
    {
      ...prev,
      x: prev.x - deltaXPx * scaleX,
      y: prev.y - deltaYPx * scaleY,
    },
    world,
  );
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
 * @param world     projected world extent for the pan-bounds clamp
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
  world: PanBounds,
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
    world,
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
  world: PanBounds,
): ViewBox {
  return clampViewBox(
    {
      x: point.x - prev.width / 2,
      y: point.y - prev.height / 2,
      width: prev.width,
      height: prev.height,
    },
    world,
  );
}

// ─── Resize refit: carry the view across a projection refit ────────────
//
// useGeoProjection refits the projection to every canvas size, so after a
// resize the same SVG coordinates name a different place on Earth. The
// window is therefore captured in projection-independent terms (the
// geographic point at its center plus the zoom factor) against the old
// fit and rebuilt against the new one.

/** A pan/zoom window expressed independently of the projection's fit. */
export interface ViewAnchor {
  /** Geographic point at the center of the window (unwrapped, see
   *  invertEquirectangular). */
  center: LatLng;
  /** Zoom factor: canvas width / viewBox width. */
  zoom: number;
}

function assertWorldExtent(world: PanBounds): void {
  if (!(world.maxX > world.minX) || !(world.maxY > world.minY)) {
    throw new Error(
      `Degenerate projected world extent: ${JSON.stringify(world)}`,
    );
  }
}

/**
 * Inverse of the fitted equirectangular projection, read off the projected
 * world box (the two projected corners of [-180..180] × [-90..90], i.e.
 * MapPane's pan bounds).
 *
 * Equirectangular is linear in both axes, so the world box fixes the
 * mapping exactly. Unlike d3's projection.invert, the longitude is NOT
 * wrapped into [-180, 180]: a view center panned past the antimeridian
 * keeps its side, so re-projecting it lands on the same spot instead of
 * jumping a world-width away.
 */
export function invertEquirectangular(
  point: { x: number; y: number },
  world: PanBounds,
): LatLng {
  assertWorldExtent(world);
  return {
    longitude:
      -180 + ((point.x - world.minX) / (world.maxX - world.minX)) * 360,
    latitude: 90 - ((point.y - world.minY) / (world.maxY - world.minY)) * 180,
  };
}

/** Forward twin of invertEquirectangular (same unwrapped linear mapping). */
export function projectEquirectangular(
  latLng: LatLng,
  world: PanBounds,
): { x: number; y: number } {
  assertWorldExtent(world);
  return {
    x:
      world.minX + ((latLng.longitude + 180) / 360) * (world.maxX - world.minX),
    y: world.minY + ((90 - latLng.latitude) / 180) * (world.maxY - world.minY),
  };
}

/** Capture a window as its geographic center plus zoom (old fit). */
export function captureViewAnchor(
  box: ViewBox,
  mapWidth: number,
  world: PanBounds,
): ViewAnchor {
  return {
    center: invertEquirectangular(
      { x: box.x + box.width / 2, y: box.y + box.height / 2 },
      world,
    ),
    zoom: mapWidth / box.width,
  };
}

/**
 * Rebuild a captured window against a (new) fit: same geographic center,
 * same zoom factor, the canvas's aspect ratio, and the usual pan clamp.
 */
export function restoreViewAnchor(
  anchor: ViewAnchor,
  mapWidth: number,
  mapHeight: number,
  world: PanBounds,
): ViewBox {
  return centerViewBoxOn(
    projectEquirectangular(anchor.center, world),
    {
      x: 0,
      y: 0,
      width: mapWidth / anchor.zoom,
      height: mapHeight / anchor.zoom,
    },
    world,
  );
}

/**
 * Carry a pan/zoom window across a projection refit (a canvas resize):
 * the geographic point at the center stays centered and the zoom readout
 * stays put. Resetting the window to the new canvas instead (the original
 * behavior) threw away every pan and zoom on each resize.
 *
 * @param prev          the window, in the OLD fit's SVG coordinates
 * @param prevMapWidth  the canvas width the old fit was made for
 * @param prevWorld     the projected world box under the old fit
 * @param nextMapWidth/nextMapHeight  the new canvas size
 * @param nextWorld     the projected world box under the new fit
 */
export function preserveViewAcrossRefit(
  prev: ViewBox,
  prevMapWidth: number,
  prevWorld: PanBounds,
  nextMapWidth: number,
  nextMapHeight: number,
  nextWorld: PanBounds,
): ViewBox {
  return restoreViewAnchor(
    captureViewAnchor(prev, prevMapWidth, prevWorld),
    nextMapWidth,
    nextMapHeight,
    nextWorld,
  );
}

// ─── Drag session (failure mode 3: pointer lifecycle + click-vs-drag) ──────
//
// The DOM half of failure mode 3 (setPointerCapture / releasePointerCapture)
// lives in MapPane.tsx; everything decidable without a DOM lives here so it
// can be unit-tested: which pointer owns the drag, when a press stops being
// a click and becomes a pan, and what delta each move contributes.

export interface DragSession {
  /** The pointer that owns this drag — all others are ignored (§6.3). */
  pointerId: number;
  /** pointerdown position (client px) — anchor for the click-vs-drag test. */
  originX: number;
  originY: number;
  /** Last applied position (client px) — anchor for incremental deltas. */
  lastX: number;
  lastY: number;
  /** True once movement exceeded the threshold: this press is a pan, and
   *  the release must not fire a click. Never resets within a session. */
  panned: boolean;
}

export interface DragMoveResult {
  session: DragSession;
  /** Pan delta to apply, in client px. Zero until the threshold trips. */
  deltaX: number;
  deltaY: number;
}

export function beginDragSession(
  pointerId: number,
  clientX: number,
  clientY: number,
): DragSession {
  return {
    pointerId,
    originX: clientX,
    originY: clientY,
    lastX: clientX,
    lastY: clientY,
    panned: false,
  };
}

/**
 * Advance the drag session for a pointermove.
 *
 * Returns null for a foreign pointer (multi-touch / stray trackpad
 * contact — spec §6.3: ignore every pointer but the dragger). Below the
 * movement threshold the press is still a potential click and the map
 * must not move. The move that crosses the threshold applies the full
 * displacement accumulated since pointerdown, so no pixels are swallowed.
 */
export function applyDragMove(
  session: DragSession,
  pointerId: number,
  clientX: number,
  clientY: number,
  thresholdPx: number = DRAG_THRESHOLD_PX,
): DragMoveResult | null {
  if (pointerId !== session.pointerId) return null;

  if (!session.panned) {
    const dx = clientX - session.originX;
    const dy = clientY - session.originY;
    if (Math.hypot(dx, dy) < thresholdPx) {
      return { session, deltaX: 0, deltaY: 0 };
    }
    return {
      session: { ...session, lastX: clientX, lastY: clientY, panned: true },
      deltaX: dx,
      deltaY: dy,
    };
  }

  return {
    session: { ...session, lastX: clientX, lastY: clientY },
    deltaX: clientX - session.lastX,
    deltaY: clientY - session.lastY,
  };
}

/**
 * Close the drag session for a pointerup. Returns null for a foreign
 * pointer (the drag survives another pointer's release); otherwise
 * reports whether the session panned — a panned release must NOT count
 * as a click on whatever the press started on.
 */
export function endDragSession(
  session: DragSession,
  pointerId: number,
): { panned: boolean } | null {
  if (pointerId !== session.pointerId) return null;
  return { panned: session.panned };
}

// ─── Coincident pins ───────────────────────────────────────────────────

/** Pin dot radius in screen px (MapPane divides it by zoom). */
export const PIN_RADIUS_PX = 3;

/**
 * Screen distance (px) at or below which two pins count as coincident: a
 * pin whose center lies inside another pin's dot can be neither seen nor
 * clicked on its own. MapPane divides it by zoom, so zooming in resolves
 * near-but-distinct pins back onto their true positions.
 */
export const COINCIDENT_PIN_EPSILON_PX = PIN_RADIUS_PX;

/**
 * Base radius (screen px) of the ring coincident pins fan out onto.
 * MapPane divides it by zoom so the fan stays the same size on screen.
 */
export const COINCIDENT_PIN_RING_PX = 8;

/**
 * Fan coincident pins out onto a small ring so each stays visible and
 * clickable.
 *
 * - Pins within `epsilon` of each other are grouped transitively (single
 *   linkage: connected components of the within-epsilon graph), which
 *   makes the grouping independent of visiting order.
 * - Each group's members are sorted by place id and placed around the
 *   group's centroid, the lowest id at the top (angle -π/2) and the rest
 *   clockwise at angle -π/2 + 2πi/n.
 * - The ring radius is `radius`, grown for large groups just enough that
 *   neighbors on the ring stay at least `radius` apart (chord ≥ radius).
 * - Pins with no neighbor within `epsilon` keep their exact position.
 *
 * The output depends only on the id → point pairs, never on the input
 * map's insertion order (entries come back in ascending id order). It is
 * display-only: centering and the place dialog use the true coordinates.
 *
 * @param coords  projected SVG coordinates per place id
 * @param epsilon grouping distance in SVG units (≥ 0)
 * @param radius  base ring radius in SVG units (> 0)
 */
export function offsetCoincidentPins(
  coords: ReadonlyMap<number, { x: number; y: number }>,
  epsilon: number,
  radius: number,
): Map<number, { x: number; y: number }> {
  if (!Number.isFinite(epsilon) || epsilon < 0) {
    throw new Error(
      `Coincident-pin epsilon must be finite and >= 0: ${epsilon}`,
    );
  }
  if (!Number.isFinite(radius) || radius <= 0) {
    throw new Error(
      `Coincident-pin ring radius must be finite and > 0: ${radius}`,
    );
  }

  const ids = Array.from(coords.keys()).sort((a, b) => a - b);
  const points = ids.map((id) => {
    const point = coords.get(id)!;
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {
      throw new Error(`Place ${id} has non-finite projected coordinates`);
    }
    return point;
  });

  // Union-find over the within-epsilon graph; the root of each component
  // is its lowest index (= lowest place id).
  const parent = ids.map((_, index) => index);
  const find = (index: number): number => {
    let root = index;
    while (parent[root] !== root) root = parent[root];
    while (parent[index] !== root) {
      const next = parent[index];
      parent[index] = root;
      index = next;
    }
    return root;
  };
  for (let i = 0; i < points.length; i++) {
    for (let j = i + 1; j < points.length; j++) {
      const dx = points[j].x - points[i].x;
      const dy = points[j].y - points[i].y;
      if (Math.hypot(dx, dy) > epsilon) continue;
      const rootI = find(i);
      const rootJ = find(j);
      if (rootI !== rootJ) {
        parent[Math.max(rootI, rootJ)] = Math.min(rootI, rootJ);
      }
    }
  }

  // Members in ascending index order, i.e. sorted by place id.
  const groups = new Map<number, number[]>();
  points.forEach((_, index) => {
    const root = find(index);
    const members = groups.get(root);
    if (members) members.push(index);
    else groups.set(root, [index]);
  });

  const placed: Array<{ x: number; y: number }> = new Array(points.length);
  groups.forEach((members) => {
    if (members.length === 1) {
      const [only] = members;
      placed[only] = { x: points[only].x, y: points[only].y };
      return;
    }

    const n = members.length;
    let sumX = 0;
    let sumY = 0;
    for (const index of members) {
      sumX += points[index].x;
      sumY += points[index].y;
    }
    const centerX = sumX / n;
    const centerY = sumY / n;
    // Adjacent chord = 2·r·sin(π/n); keep it ≥ radius (n ≤ 6 fit as is).
    const ringRadius = Math.max(radius, radius / (2 * Math.sin(Math.PI / n)));

    members.forEach((index, position) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * position) / n;
      placed[index] = {
        x: centerX + ringRadius * Math.cos(angle),
        y: centerY + ringRadius * Math.sin(angle),
      };
    });
  });

  return new Map(ids.map((id, index) => [id, placed[index]]));
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
