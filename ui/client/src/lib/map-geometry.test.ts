/**
 * Unit tests for the MapPane geometry core.
 *
 * Each block maps to a historical failure mode from
 * docs/maptab_rebuild_spec.md §6:
 *   - extractCoordinates  → §6.4 GeoJSON [lng, lat] ordering + validation
 *   - zoomViewBoxAtCursor → §6.2 cursor-anchored zoom
 *   - computeLabelVisibility → §6.1 priority + AABB label culling
 *   - clampViewBox / computeMapBounds → §4.3 pan clamping
 * (§6.3 pointer capture is DOM behavior — verified manually, see PR.)
 */
import { geoEquirectangular } from "d3-geo";
import { describe, expect, it, vi } from "vitest";
import type { Place } from "@shared/schema";
import {
  boundsToFitObject,
  centerViewBoxOn,
  clampViewBox,
  clampZoom,
  computeLabelVisibility,
  computeMapBounds,
  extractCoordinates,
  MIN_BOUNDS_SPAN_DEG,
  shouldDisplayLabelByZoom,
  zoomViewBoxAtCursor,
  type LabelCandidate,
  type ViewBox,
} from "./map-geometry";

function makePlace(id: number, geometry: unknown): Place {
  return { id, name: `Place ${id}`, geometry } as unknown as Place;
}

describe("extractCoordinates (failure mode 4: lng/lat ordering)", () => {
  it("reads GeoJSON Point as [longitude, latitude]", () => {
    // New Orleans: lng -90.07, lat 29.95 — reversing the order would put
    // the pin in Antarctica-adjacent open ocean (lat -90 is out of range).
    const place = makePlace(1, {
      type: "Point",
      coordinates: [-90.07, 29.95],
    });
    expect(extractCoordinates(place)).toEqual({
      latitude: 29.95,
      longitude: -90.07,
    });
  });

  it("accepts the PostGIS 3-element form [lng, lat, elevation]", () => {
    const place = makePlace(2, {
      type: "Point",
      coordinates: [-64.637290453, 12.534674011, 0],
    });
    expect(extractCoordinates(place)).toEqual({
      latitude: 12.534674011,
      longitude: -64.637290453,
    });
  });

  it("drops out-of-range latitude without throwing", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const place = makePlace(3, { type: "Point", coordinates: [10, 91] });
    expect(extractCoordinates(place)).toBeNull();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("drops out-of-range longitude without throwing", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const place = makePlace(4, { type: "Point", coordinates: [181, 10] });
    expect(extractCoordinates(place)).toBeNull();
    warn.mockRestore();
  });

  it("drops non-finite coordinates", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(
      extractCoordinates(
        makePlace(5, { type: "Point", coordinates: [NaN, 10] }),
      ),
    ).toBeNull();
    expect(
      extractCoordinates(
        makePlace(6, { type: "Point", coordinates: [10, Infinity] }),
      ),
    ).toBeNull();
    warn.mockRestore();
  });

  it("returns null for missing or malformed geometry", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(extractCoordinates(makePlace(7, null))).toBeNull();
    expect(extractCoordinates(makePlace(8, "not-geojson"))).toBeNull();
    expect(extractCoordinates(makePlace(9, {}))).toBeNull();
    warn.mockRestore();
  });

  it("returns null for Polygon/LineString (not yet rendered)", () => {
    expect(
      extractCoordinates(
        makePlace(10, { type: "Polygon", coordinates: [[[0, 0]]] }),
      ),
    ).toBeNull();
    expect(
      extractCoordinates(
        makePlace(11, {
          type: "LineString",
          coordinates: [
            [0, 0],
            [1, 1],
          ],
        }),
      ),
    ).toBeNull();
  });
});

describe("zoomViewBoxAtCursor (failure mode 2: zoom anchoring)", () => {
  const MAP_W = 800;
  const MAP_H = 600;

  /** SVG-space point under a client cursor position for a given viewBox. */
  function svgPointUnderCursor(
    box: ViewBox,
    cursorX: number,
    cursorY: number,
    rectW: number,
    rectH: number,
  ) {
    return {
      x: box.x + cursorX * (box.width / rectW),
      y: box.y + cursorY * (box.height / rectH),
    };
  }

  it("keeps the SVG point under the cursor invariant across a zoom-in", () => {
    const prev: ViewBox = { x: 100, y: 80, width: 400, height: 300 };
    const cursor = { x: 530, y: 190 };
    const rect = { w: 800, h: 600 };

    const before = svgPointUnderCursor(
      prev,
      cursor.x,
      cursor.y,
      rect.w,
      rect.h,
    );
    // zoom 2 → 2.2 (one wheel tick in)
    const next = zoomViewBoxAtCursor(
      prev,
      cursor.x,
      cursor.y,
      rect.w,
      rect.h,
      2.2,
      MAP_W,
      MAP_H,
    );
    const after = svgPointUnderCursor(next, cursor.x, cursor.y, rect.w, rect.h);

    expect(after.x).toBeCloseTo(before.x, 6);
    expect(after.y).toBeCloseTo(before.y, 6);
    expect(next.width).toBeCloseTo(MAP_W / 2.2, 6);
    expect(next.height).toBeCloseTo(MAP_H / 2.2, 6);
  });

  it("keeps the cursor point invariant across a zoom-out (until clamped)", () => {
    const prev: ViewBox = { x: 200, y: 150, width: 200, height: 150 };
    const cursor = { x: 400, y: 300 };
    const rect = { w: 800, h: 600 };

    const before = svgPointUnderCursor(
      prev,
      cursor.x,
      cursor.y,
      rect.w,
      rect.h,
    );
    // zoom 4 → 3.6 (one wheel tick out); interior enough not to clamp
    const next = zoomViewBoxAtCursor(
      prev,
      cursor.x,
      cursor.y,
      rect.w,
      rect.h,
      3.6,
      MAP_W,
      MAP_H,
    );
    const after = svgPointUnderCursor(next, cursor.x, cursor.y, rect.w, rect.h);

    expect(after.x).toBeCloseTo(before.x, 6);
    expect(after.y).toBeCloseTo(before.y, 6);
  });

  it("does NOT exhibit the top-left-corner bug (origin must shift)", () => {
    // The classic regression: shrinking width/height without solving for
    // x/y zooms toward the top-left corner. With the cursor at the canvas
    // center, a correct zoom-in must move the origin down-right.
    const prev: ViewBox = { x: 0, y: 0, width: 800, height: 600 };
    const next = zoomViewBoxAtCursor(prev, 400, 300, 800, 600, 2, MAP_W, MAP_H);
    expect(next.x).toBeGreaterThan(0);
    expect(next.y).toBeGreaterThan(0);
    expect(next.x).toBeCloseTo(200, 6);
    expect(next.y).toBeCloseTo(150, 6);
  });

  it("clamps zoom factors to the supported range", () => {
    expect(clampZoom(0.01)).toBe(0.2);
    expect(clampZoom(500)).toBe(100);
    expect(clampZoom(1.5)).toBe(1.5);
  });
});

describe("clampViewBox (§4.3 pan clamping)", () => {
  it("clamps negative origins to zero", () => {
    const box = clampViewBox(
      { x: -50, y: -20, width: 400, height: 300 },
      800,
      600,
    );
    expect(box.x).toBe(0);
    expect(box.y).toBe(0);
  });

  it("clamps the origin so the window stays inside the map", () => {
    const box = clampViewBox(
      { x: 700, y: 500, width: 400, height: 300 },
      800,
      600,
    );
    expect(box.x).toBe(400); // 800 - 400
    expect(box.y).toBe(300); // 600 - 300
  });

  it("pins to origin when the window is larger than the map (zoom < 1)", () => {
    const box = clampViewBox(
      { x: 120, y: 90, width: 1600, height: 1200 },
      800,
      600,
    );
    expect(box.x).toBe(0);
    expect(box.y).toBe(0);
  });

  it("centerViewBoxOn centers a point and respects clamping", () => {
    const prev: ViewBox = { x: 0, y: 0, width: 400, height: 300 };
    const centered = centerViewBoxOn({ x: 400, y: 300 }, prev, 800, 600);
    expect(centered.x).toBe(200);
    expect(centered.y).toBe(150);

    const nearEdge = centerViewBoxOn({ x: 790, y: 590 }, prev, 800, 600);
    expect(nearEdge.x).toBe(400); // clamped to map edge
    expect(nearEdge.y).toBe(300);
  });
});

describe("computeMapBounds", () => {
  it("returns a padded bounding box over valid places only", () => {
    const places = [
      makePlace(1, { type: "Point", coordinates: [-90, 30] }),
      makePlace(2, { type: "Point", coordinates: [-60, 10] }),
      makePlace(3, { type: "Point", coordinates: [999, 999] }), // dropped
      makePlace(4, null), // dropped
    ];
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const bounds = computeMapBounds(places);
    warn.mockRestore();

    expect(bounds).not.toBeNull();
    // lngRange = 30, latRange = 20, padding 10%
    expect(bounds!.minLng).toBeCloseTo(-93, 6);
    expect(bounds!.maxLng).toBeCloseTo(-57, 6);
    expect(bounds!.minLat).toBeCloseTo(8, 6);
    expect(bounds!.maxLat).toBeCloseTo(32, 6);
  });

  it("returns null when no place has usable geometry", () => {
    expect(computeMapBounds([makePlace(1, null)])).toBeNull();
    expect(computeMapBounds([])).toBeNull();
  });

  it("widens a single-place box to the minimum span (slot-5 blank-void bug)", () => {
    // One charted place used to collapse the fit to a ~0.0001-degree box,
    // zooming the projection to a viewport a couple of meters across.
    const bounds = computeMapBounds([
      makePlace(1, { type: "Point", coordinates: [5.322, 60.392, 0] }),
    ]);

    expect(bounds).not.toBeNull();
    const lngSpan = bounds!.maxLng - bounds!.minLng;
    const latSpan = bounds!.maxLat - bounds!.minLat;
    expect(lngSpan).toBeGreaterThanOrEqual(MIN_BOUNDS_SPAN_DEG);
    expect(latSpan).toBeGreaterThanOrEqual(MIN_BOUNDS_SPAN_DEG);
    // Still centered on the place:
    expect((bounds!.minLng + bounds!.maxLng) / 2).toBeCloseTo(5.322, 6);
    expect((bounds!.minLat + bounds!.maxLat) / 2).toBeCloseTo(60.392, 6);
  });
});

describe("boundsToFitObject (failure mode 5: spherical fit winding)", () => {
  // The original rebuild fed fitSize a bounding POLYGON whose ring was
  // wound so that d3-geo (spherical winding semantics) read it as the
  // box's sphere-complement: fitSize quietly fit the whole globe, and
  // every regional map rendered as a world-scale speck. Corner points
  // carry no winding, so this cannot regress silently again.
  const region = {
    minLng: 17.34,
    maxLng: 19.67,
    minLat: 41.13,
    maxLat: 42.87,
  };

  it("fits the projection to the region, not the sphere-complement", () => {
    const proj = geoEquirectangular();
    proj.fitSize([1026, 792], boundsToFitObject(region));

    const world = geoEquirectangular();
    world.fitSize(
      [1026, 792],
      boundsToFitObject({ minLng: -180, maxLng: 180, minLat: -90, maxLat: 90 }),
    );

    // A ~2-degree region must be fit at a far larger scale than the globe.
    expect(proj.scale()).toBeGreaterThan(world.scale() * 50);
  });

  it("centers the region in the canvas", () => {
    const proj = geoEquirectangular();
    proj.fitSize([1026, 792], boundsToFitObject(region));
    const center = proj([
      (region.minLng + region.maxLng) / 2,
      (region.minLat + region.maxLat) / 2,
    ]);
    expect(center).not.toBeNull();
    expect(center![0]).toBeCloseTo(1026 / 2, 0);
    expect(center![1]).toBeCloseTo(792 / 2, 0);
  });

  it("still fits the whole world for the null-bounds fallback box", () => {
    const world = geoEquirectangular();
    world.fitSize(
      [1026, 792],
      boundsToFitObject({ minLng: -180, maxLng: 180, minLat: -90, maxLat: 90 }),
    );
    // Full longitudinal span maps to the full canvas width.
    const west = world([-180, 0])!;
    const east = world([180, 0])!;
    expect(east[0] - west[0]).toBeCloseTo(1026, 0);
  });
});

describe("computeLabelVisibility (failure mode 1: label culling)", () => {
  function candidate(
    placeId: number,
    index: number,
    x: number,
    y: number,
    priority = 1,
  ): LabelCandidate {
    return { placeId, index, coords: { x, y }, priority };
  }

  it("hides overlapping priority-1 labels, keeps the first accepted", () => {
    // Two labels at nearly the same position at zoom 3 (all labels pass
    // the stride gate); the second must be culled by the AABB test.
    const result = computeLabelVisibility(
      [candidate(1, 0, 100, 100), candidate(2, 1, 105, 100)],
      3,
    );
    expect(result.get(1)).toBe(true);
    expect(result.get(2)).toBe(false);
  });

  it("force-shows selected/hovered/current labels even when overlapping", () => {
    const result = computeLabelVisibility(
      [
        candidate(1, 0, 100, 100, 1),
        candidate(2, 1, 102, 100, 4), // selected
        candidate(3, 2, 104, 100, 2), // current narrative location
      ],
      3,
    );
    expect(result.get(2)).toBe(true);
    expect(result.get(3)).toBe(true);
    // The priority-1 label lost the collision against the forced ones:
    expect(result.get(1)).toBe(false);
  });

  it("applies the zoom stride to priority-1 labels", () => {
    // zoom 1.2 → only every 20th index is even considered.
    expect(shouldDisplayLabelByZoom(0, 1.2)).toBe(true);
    expect(shouldDisplayLabelByZoom(7, 1.2)).toBe(false);
    expect(shouldDisplayLabelByZoom(20, 1.2)).toBe(true);
    // zoom 2.5 → every 5th.
    expect(shouldDisplayLabelByZoom(5, 2.5)).toBe(true);
    expect(shouldDisplayLabelByZoom(6, 2.5)).toBe(false);
    // zoom 3+ → all.
    expect(shouldDisplayLabelByZoom(13, 3.0)).toBe(true);
  });

  it("hides every priority-1 label below zoom 1, but keeps forced ones", () => {
    const result = computeLabelVisibility(
      [
        candidate(1, 0, 100, 100, 1),
        candidate(2, 1, 400, 300, 2), // current location survives
      ],
      0.5,
    );
    expect(result.get(1)).toBe(false);
    expect(result.get(2)).toBe(true);
  });

  it("shows non-overlapping priority-1 labels at high zoom", () => {
    const result = computeLabelVisibility(
      [candidate(1, 0, 100, 100), candidate(2, 1, 400, 300)],
      3,
    );
    expect(result.get(1)).toBe(true);
    expect(result.get(2)).toBe(true);
  });
});
