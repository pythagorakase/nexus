/**
 * Unit tests for the MapPane geometry core.
 *
 * Each block maps to a historical failure mode from
 * docs/maptab_rebuild_spec.md §6:
 *   - extractCoordinates  → §6.4 GeoJSON [lng, lat] ordering + validation
 *   - zoomViewBoxAtCursor → §6.2 cursor-anchored zoom
 *   - computeLabelVisibility → §6.1 priority + AABB label culling
 *   - clampViewBox / panViewBox / computeMapBounds → §4.1/§4.3 pan + bounds
 *   - beginDragSession / applyDragMove / endDragSession → §6.3 pointer
 *     lifecycle (owning-pointer guard) + click-vs-drag threshold
 * (The setPointerCapture / releasePointerCapture DOM calls themselves are
 * verified in a real browser — see PR evidence.)
 */
import { geoEquirectangular } from "d3-geo";
import { describe, expect, it, vi } from "vitest";
import type { Place } from "@shared/schema";
import {
  applyDragMove,
  beginDragSession,
  boundsToFitObject,
  centerViewBoxOn,
  clampViewBox,
  clampZoom,
  computeLabelVisibility,
  computeMapBounds,
  DRAG_THRESHOLD_PX,
  endDragSession,
  extractCoordinates,
  MIN_BOUNDS_SPAN_DEG,
  MIN_WORLD_VISIBLE_FRACTION,
  panViewBox,
  shouldDisplayLabelByZoom,
  zoomViewBoxAtCursor,
  type LabelCandidate,
  type PanBounds,
  type ViewBox,
} from "./map-geometry";

function makePlace(id: number, geometry: unknown): Place {
  return { id, name: `Place ${id}`, geometry } as unknown as Place;
}

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

/** A projected world so large no clamp engages (regional-fit geometry). */
const OPEN_WORLD: PanBounds = {
  minX: -100000,
  minY: -100000,
  maxX: 100000,
  maxY: 100000,
};

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
      OPEN_WORLD,
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
      OPEN_WORLD,
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
    const next = zoomViewBoxAtCursor(
      prev,
      400,
      300,
      800,
      600,
      2,
      MAP_W,
      MAP_H,
      OPEN_WORLD,
    );
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

describe("clampViewBox (§4.3 pan bounds: world never fully off-screen)", () => {
  // A projected world that extends beyond the 800×600 canvas, as it does
  // for any regional fit (the fitted region maps to the canvas, the rest
  // of the globe projects outside it).
  const world: PanBounds = { minX: -1000, minY: -800, maxX: 1800, maxY: 1400 };

  it("leaves an interior window untouched", () => {
    const box = clampViewBox({ x: 250, y: 130, width: 400, height: 300 }, world);
    expect(box).toEqual({ x: 250, y: 130, width: 400, height: 300 });
  });

  it("allows panning beyond the fitted region (the 1.00x pan-lock bug)", () => {
    // REGRESSION: the old clamp confined the window to the fitted region
    // [0, 0, mapW, mapH]; at zoom 1 the slack was zero on both axes and
    // every drag was silently clamped back — "the map has no panning".
    const box = clampViewBox({ x: 300, y: 200, width: 800, height: 600 }, world);
    expect(box.x).toBe(300);
    expect(box.y).toBe(200);

    const negative = clampViewBox(
      { x: -350, y: -250, width: 800, height: 600 },
      world,
    );
    expect(negative.x).toBe(-350);
    expect(negative.y).toBe(-250);
  });

  it("keeps the minimum world fraction visible at the right/bottom edge", () => {
    const box = clampViewBox(
      { x: 99999, y: 99999, width: 800, height: 600 },
      world,
    );
    expect(box.x).toBe(world.maxX - 800 * MIN_WORLD_VISIBLE_FRACTION);
    expect(box.y).toBe(world.maxY - 600 * MIN_WORLD_VISIBLE_FRACTION);
  });

  it("keeps the minimum world fraction visible at the left/top edge", () => {
    const box = clampViewBox(
      { x: -99999, y: -99999, width: 800, height: 600 },
      world,
    );
    expect(box.x).toBe(world.minX - 800 + 800 * MIN_WORLD_VISIBLE_FRACTION);
    expect(box.y).toBe(world.minY - 600 + 600 * MIN_WORLD_VISIBLE_FRACTION);
  });

  it("keeps a small world inside a large window (deep zoom-out)", () => {
    const tiny: PanBounds = { minX: 0, minY: 0, maxX: 100, maxY: 80 };
    const big = { width: 4000, height: 3000 };

    const right = clampViewBox({ x: 5000, y: 5000, ...big }, tiny);
    expect(right.x).toBeLessThanOrEqual(tiny.minX);
    expect(right.x + big.width).toBeGreaterThanOrEqual(tiny.maxX);
    expect(right.y).toBeLessThanOrEqual(tiny.minY);
    expect(right.y + big.height).toBeGreaterThanOrEqual(tiny.maxY);

    const left = clampViewBox({ x: -5000, y: -5000, ...big }, tiny);
    expect(left.x).toBeLessThanOrEqual(tiny.minX);
    expect(left.x + big.width).toBeGreaterThanOrEqual(tiny.maxX);
  });

  it("centerViewBoxOn centers a point and respects the pan bounds", () => {
    const prev: ViewBox = { x: 0, y: 0, width: 400, height: 300 };
    const centered = centerViewBoxOn({ x: 400, y: 300 }, prev, world);
    expect(centered.x).toBe(200);
    expect(centered.y).toBe(150);

    const farOut = centerViewBoxOn({ x: 99999, y: 99999 }, prev, world);
    expect(farOut.x).toBe(world.maxX - 400 * MIN_WORLD_VISIBLE_FRACTION);
    expect(farOut.y).toBe(world.maxY - 300 * MIN_WORLD_VISIBLE_FRACTION);
  });
});

describe("panViewBox (§4.1 drag-to-pan + pan/zoom composition)", () => {
  it("moves the window opposite the drag (content follows the cursor)", () => {
    // Dragging right/down pulls the world right/down → window moves left/up.
    const next = panViewBox(
      { x: 0, y: 0, width: 800, height: 600 },
      50,
      30,
      800,
      600,
      OPEN_WORLD,
    );
    expect(next.x).toBe(-50);
    expect(next.y).toBe(-30);
  });

  it("maps the same px drag through the projection scale at every zoom", () => {
    // zoom 1: viewBox width == rect width → 50 px ⇒ 50 SVG units.
    const z1 = panViewBox(
      { x: 0, y: 0, width: 800, height: 600 },
      50,
      -30,
      800,
      600,
      OPEN_WORLD,
    );
    expect(z1.x).toBeCloseTo(-50, 6);
    expect(z1.y).toBeCloseTo(30, 6);

    // zoom 4: same 50 px covers a quarter of the SVG distance, which is
    // the SAME distance on screen — pan feel is zoom-invariant.
    const z4 = panViewBox(
      { x: 100, y: 80, width: 200, height: 150 },
      50,
      -30,
      800,
      600,
      OPEN_WORLD,
    );
    expect(z4.x).toBeCloseTo(100 - 12.5, 6);
    expect(z4.y).toBeCloseTo(80 + 7.5, 6);
  });

  it("clamps a drag at the world edge", () => {
    const world: PanBounds = { minX: 0, minY: 0, maxX: 1600, maxY: 1200 };
    const next = panViewBox(
      { x: 0, y: 0, width: 800, height: 600 },
      99999, // hard fling right → window pushed far left of the world
      0,
      800,
      600,
      world,
    );
    expect(next.x).toBe(world.minX - 800 + 800 * MIN_WORLD_VISIBLE_FRACTION);
  });

  it("zoom anchoring still holds on a panned window (composition)", () => {
    // Pan first…
    const panned = panViewBox(
      { x: 0, y: 0, width: 400, height: 300 },
      -120,
      90,
      800,
      600,
      OPEN_WORLD,
    );
    expect(panned.x).toBeCloseTo(60, 6); // 120 px × (400/800)
    expect(panned.y).toBeCloseTo(-45, 6);

    // …then zoom at an off-center cursor: the SVG point under the cursor
    // must survive the zoom exactly as it does on an unpanned window.
    const cursor = { x: 250, y: 410 };
    const before = svgPointUnderCursor(panned, cursor.x, cursor.y, 800, 600);
    const next = zoomViewBoxAtCursor(
      panned,
      cursor.x,
      cursor.y,
      800,
      600,
      3,
      800,
      600,
      OPEN_WORLD,
    );
    const after = svgPointUnderCursor(next, cursor.x, cursor.y, 800, 600);
    expect(after.x).toBeCloseTo(before.x, 6);
    expect(after.y).toBeCloseTo(before.y, 6);
  });
});

describe("drag session (failure mode 3: pointer lifecycle + click-vs-drag)", () => {
  it("ignores moves from a foreign pointer (multi-touch safety)", () => {
    const session = beginDragSession(7, 100, 100);
    expect(applyDragMove(session, 9, 300, 300)).toBeNull();
  });

  it("survives a foreign pointer's release", () => {
    const session = beginDragSession(7, 100, 100);
    expect(endDragSession(session, 9)).toBeNull();
    expect(endDragSession(session, 7)).toEqual({ panned: false });
  });

  it("stays a click below the movement threshold (map must not move)", () => {
    const session = beginDragSession(1, 100, 100);
    const move = applyDragMove(session, 1, 102, 101); // ~2.2 px of jitter
    expect(move).not.toBeNull();
    expect(move!.deltaX).toBe(0);
    expect(move!.deltaY).toBe(0);
    expect(move!.session.panned).toBe(false);
    expect(endDragSession(move!.session, 1)).toEqual({ panned: false });
  });

  it("becomes a pan at the threshold, applying the full accumulated delta", () => {
    const session = beginDragSession(1, 100, 100);
    const move = applyDragMove(session, 1, 100 + DRAG_THRESHOLD_PX + 2, 100);
    expect(move!.session.panned).toBe(true);
    expect(move!.deltaX).toBe(DRAG_THRESHOLD_PX + 2); // nothing swallowed
    expect(move!.deltaY).toBe(0);
  });

  it("applies incremental deltas after the threshold", () => {
    let session = beginDragSession(1, 100, 100);
    session = applyDragMove(session, 1, 110, 100)!.session;
    const move = applyDragMove(session, 1, 115, 103);
    expect(move!.deltaX).toBe(5);
    expect(move!.deltaY).toBe(3);
  });

  it("a pan stays a pan even when released back at the origin", () => {
    // Drag out and back: total displacement is zero, but the session
    // panned — the release must still be click-suppressed.
    let session = beginDragSession(1, 100, 100);
    session = applyDragMove(session, 1, 130, 100)!.session;
    session = applyDragMove(session, 1, 100, 100)!.session;
    expect(endDragSession(session, 1)).toEqual({ panned: true });
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
