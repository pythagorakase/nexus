/**
 * MapPane tests - the reader's view survives a canvas resize, and places
 * sharing a point fan out on the canvas while everything else keeps using
 * the true point.
 *
 * Component tests render against pre-seeded react-query caches (no fetch
 * interception), like CharactersPane.test.tsx. jsdom has no layout engine,
 * so the canvas size arrives through a ResizeObserver that delivers the
 * entries a browser would, and the SVG gets the bounding rect the wheel
 * handler reads for its cursor math. The projection, geometry and React
 * wiring are all the real ones.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { geoEquirectangular } from "d3-geo";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import {
  boundsToFitObject,
  COINCIDENT_PIN_RING_PX,
  computeMapBounds,
  invertEquirectangular,
  type PanBounds,
} from "@/lib/map-geometry";
import type { CurrentPlace, Place, Zone } from "@shared/schema";
import { MapPane } from "./MapPane";

const SLOT = 5;

function makePlace(
  id: number,
  name: string,
  point: [number, number] | null,
): Place {
  return {
    id,
    name,
    type: "fixed_location",
    zone: 1,
    summary: null,
    inhabitants: null,
    history: null,
    currentStatus: null,
    secrets: null,
    extraData: null,
    createdAt: new Date("2026-09-01T00:00:00Z"),
    updatedAt: new Date("2026-09-01T00:00:00Z"),
    coordinates: null,
    geom: null,
    // GET /api/places serves ST_AsGeoJSON: [longitude, latitude].
    geometry: point ? { type: "Point", coordinates: point } : null,
  };
}

// Two places charted at one point (a wharf and the warehouse on it), a
// third nearby, and one uncharted.
const PLACES: Place[] = [
  makePlace(101, "Bryggen Wharf", [5.3242, 60.3975]),
  makePlace(102, "Hanseatic Warehouse", [5.3242, 60.3975]),
  makePlace(103, "Floyen Station", [5.344, 60.3945]),
  makePlace(104, "Sunken Chapel", null),
];

const ZONES: Zone[] = [
  { id: 1, name: "Bergen", summary: null, boundary: null },
];

const CURRENT: CurrentPlace[] = [
  { placeId: 103, name: "Floyen Station", chunkId: 1 },
];

/** Delivers the resize entries jsdom's layout-free DOM never produces. */
class CanvasResizeObserver {
  static latest: CanvasResizeObserver | null = null;
  constructor(private readonly callback: ResizeObserverCallback) {
    CanvasResizeObserver.latest = this;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
  deliver(width: number, height: number) {
    this.callback(
      [{ contentRect: { width, height } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }
}

function resizeCanvas(width: number, height: number) {
  const observer = CanvasResizeObserver.latest;
  if (!observer) throw new Error("MapPane never observed its canvas");
  const svg = screen.getByTestId("map-svg");
  const rect = { left: 0, top: 0, right: width, bottom: height };
  svg.getBoundingClientRect = () => ({ ...rect, width, height }) as DOMRect;
  act(() => observer.deliver(width, height));
}

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["/api/places", SLOT], PLACES);
  client.setQueryData(["/api/zones", SLOT], ZONES);
  client.setQueryData(["/api/current-place", SLOT], CURRENT);
  for (const place of PLACES) {
    client.setQueryData(["/api/places", place.id, "images", SLOT], []);
  }
  render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <MapPane slot={SLOT} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return client;
}

function readViewBox() {
  const [x, y, width, height] = screen
    .getByTestId("map-svg")
    .getAttribute("viewBox")!
    .split(" ")
    .map(Number);
  return { x, y, width, height };
}

/** The projected world box MapPane fits for this canvas (useGeoProjection). */
function worldFor(width: number, height: number): PanBounds {
  const projection = geoEquirectangular();
  projection.fitSize(
    [width, height],
    boundsToFitObject(computeMapBounds(PLACES)!),
  );
  const [minX, minY] = projection([-180, 90])!;
  const [maxX, maxY] = projection([180, -90])!;
  return { minX, minY, maxX, maxY };
}

function viewCenterLngLat(width: number, height: number) {
  const box = readViewBox();
  return invertEquirectangular(
    { x: box.x + box.width / 2, y: box.y + box.height / 2 },
    worldFor(width, height),
  );
}

function pinCenter(placeId: number) {
  const dot = screen
    .getByTestId(`map-pin-${placeId}`)
    .querySelector("circle")!;
  return {
    x: Number(dot.getAttribute("cx")),
    y: Number(dot.getAttribute("cy")),
  };
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", CanvasResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
  CanvasResizeObserver.latest = null;
});

describe("MapPane", () => {
  it("keeps pan and zoom across a canvas resize", () => {
    renderPane();
    resizeCanvas(1000, 600);
    expect(screen.getByText("1.00×")).toBeInTheDocument();

    // Zoom in three wheel ticks toward the upper right: both the zoom and
    // the geographic center move away from the current-place framing.
    const svg = screen.getByTestId("map-svg");
    for (let tick = 0; tick < 3; tick++) {
      fireEvent.wheel(svg, { deltaY: -100, clientX: 850, clientY: 120 });
    }
    expect(screen.getByText("1.33×")).toBeInTheDocument();
    const before = viewCenterLngLat(1000, 600);

    resizeCanvas(700, 800);

    // REGRESSION: the resize used to reset the window to the canvas
    // (1.00×) and re-center on the current place, discarding both.
    expect(screen.getByText("1.33×")).toBeInTheDocument();
    const after = viewCenterLngLat(700, 800);
    expect(after.longitude).toBeCloseTo(before.longitude, 9);
    expect(after.latitude).toBeCloseTo(before.latitude, 9);
    const box = readViewBox();
    expect(box.width / box.height).toBeCloseTo(700 / 800, 9);
  });

  it("keeps the pan when a places refetch keeps the extent", async () => {
    const client = renderPane();
    resizeCanvas(1000, 600);
    const svg = screen.getByTestId("map-svg");
    for (let tick = 0; tick < 3; tick++) {
      fireEvent.wheel(svg, { deltaY: -100, clientX: 850, clientY: 120 });
    }
    const panned = screen.getByTestId("map-svg").getAttribute("viewBox");

    // A turn charts a new place inside the existing extent and revises
    // another: the places data changes, the charted extent does not.
    // REGRESSION: the centering guard compared the rebuilt mapBounds
    // object by reference and snapped back to the current place.
    const refetched: Place[] = [
      ...PLACES.map((place) =>
        place.id === 102 ? { ...place, summary: "Stockfish stores" } : place,
      ),
      makePlace(105, "Tyskebryggen Quay", [5.334, 60.396]),
    ];
    expect(computeMapBounds(refetched)).toEqual(computeMapBounds(PLACES));
    act(() => {
      client.setQueryData(["/api/places", SLOT], refetched);
    });

    // react-query notifies observers on a timer, not synchronously.
    expect(await screen.findByTestId("map-pin-105")).toBeInTheDocument();
    expect(screen.getByTestId("map-svg").getAttribute("viewBox")).toBe(panned);
    expect(screen.getByText("1.33×")).toBeInTheDocument();
  });

  it("fans coincident places out, with leaders back to the true point", () => {
    renderPane();
    resizeCanvas(1000, 600);

    const wharf = pinCenter(101);
    const warehouse = pinCenter(102);
    // Zoom 1.00: the pair sits a ring diameter apart, lowest id on top.
    const spread = Math.hypot(warehouse.x - wharf.x, warehouse.y - wharf.y);
    expect(spread).toBeCloseTo(2 * COINCIDENT_PIN_RING_PX, 6);
    expect(wharf.y).toBeLessThan(warehouse.y);

    // Labels and hit targets move with the pin.
    const wharfLabel = screen.getByText("Bryggen Wharf", { selector: "text" });
    expect(Number(wharfLabel.getAttribute("x"))).toBeCloseTo(wharf.x, 9);

    // Each displaced pin draws a hairline from the true point; the lone
    // current place is drawn at its true point and has none.
    const truePoint = {
      x: (wharf.x + warehouse.x) / 2,
      y: (wharf.y + warehouse.y) / 2,
    };
    for (const [placeId, pin] of [
      [101, wharf],
      [102, warehouse],
    ] as const) {
      const leader = screen.getByTestId(`map-pin-leader-${placeId}`);
      expect(Number(leader.getAttribute("x1"))).toBeCloseTo(truePoint.x, 6);
      expect(Number(leader.getAttribute("y1"))).toBeCloseTo(truePoint.y, 6);
      expect(Number(leader.getAttribute("x2"))).toBeCloseTo(pin.x, 9);
      expect(Number(leader.getAttribute("y2"))).toBeCloseTo(pin.y, 9);
    }
    expect(screen.queryByTestId("map-pin-leader-103")).not.toBeInTheDocument();

    // Selecting from the index centers on the TRUE point, and the dialog
    // reports the true coordinates.
    fireEvent.click(screen.getByTestId("map-zone-1"));
    fireEvent.click(screen.getByTestId("map-place-row-101"));
    const box = readViewBox();
    expect(box.x + box.width / 2).toBeCloseTo(truePoint.x, 6);
    expect(box.y + box.height / 2).toBeCloseTo(truePoint.y, 6);
    expect(screen.getByRole("dialog")).toHaveTextContent("60.397500, 5.324200");
  });
});
