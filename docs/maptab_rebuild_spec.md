# MapTab Clean-Room Rebuild Spec

This document is a frontend-focused reference for reimplementing the NEXUS
in-game map. It was captured immediately before the original `MapTab.tsx`
was deleted as part of the `ui-rebuild` demolition (May 2026). The map
implementation has historically been rebuilt incorrectly multiple times;
this spec exists so the next implementation has authoritative reference
without needing to read the original code.

For the database / API / GeoJSON layer, see
`docs/geojson-integration.md` — it is current and not repeated here.

---

## 1. Data Layer (Summary)

The map consumes three Express endpoints (full shapes in
`geojson-integration.md`):

- `GET /api/places?slot={slot}` — all places with `geometry` populated from
  `ST_AsGeoJSON(coordinates)::json`. Geometry is a GeoJSON `Point` with
  `[longitude, latitude]` in that order.
- `GET /api/zones?slot={slot}` — zone metadata; current renderer does not
  draw zone boundaries, only uses zone IDs to group places in the
  sidebar.
- `GET /api/places/{placeId}/images?slot={slot}` — only fetched when a
  place is selected, drives the details modal + gallery.

Mutations on `place_images` (POST upload, PUT set-main, DELETE) all live
under `/api/places/{placeId}/images/...` and invalidate the corresponding
React Query cache key on success.

**Coordinate validation** happens client-side after the fetch (see §6
"Failure Modes"): geometry must be `type: "Point"`, both coords finite,
lat ∈ [-90, 90], lng ∈ [-180, 180]. Invalid geometry is silently dropped
with a `console.warn`.

---

## 2. Rendering Technique

**SVG-based**, **not** Leaflet / MapLibre / Canvas / WebGL. Projection
provided by `d3-geo`.

### 2.1 The SVG element

A single `<svg>` element fills the tab. Sizing is responsive via a
`ResizeObserver` watching `svgRef.current?.parentElement`. The viewBox
attribute (not a child `<g>` transform) is the mutable surface for
pan/zoom:

```jsx
<svg
  ref={svgRef}
  viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
  preserveAspectRatio="xMidYMid slice"
  onWheel={handleWheel}
  onPointerDown={handlePointerDown}
  onPointerMove={handlePointerMove}
  onPointerUp={handlePointerUp}
/>
```

Choosing viewBox manipulation over a CSS/SVG transform on a wrapper `<g>`
is what makes label/pin sizing predictable: stroke widths and font sizes
divide by `zoom` to stay visually constant.

### 2.2 The projection (`useGeoProjection` hook)

```ts
import { geoEquirectangular, geoPath } from "d3-geo";

const proj = geoEquirectangular();
proj.fitSize([mapDimensions.width, mapDimensions.height], fitObject);
const transformCoordinates = (lng: number, lat: number) => proj([lng, lat]);
const pathGenerator = geoPath().projection(proj);
```

- `geoEquirectangular` is the right choice for a fictional-world map —
  it's a simple linear mapping of lat/lng to pixels, no distortion to
  reason about, no globe wrap-around concerns.
- `fitSize` accepts a GeoJSON object describing the area to include and
  computes scale/translate so that area fills the canvas. **Do not pass a
  bounding polygon** — see §6.5 (spherical fit winding). Pass winding-free
  corner points instead (`boundsToFitObject` in `lib/map-geometry.ts`):
  `{ type: "MultiPoint", coordinates: [[minLng, minLat], [maxLng, maxLat]] }`.
- `geoPath()` returns a path generator that converts arbitrary GeoJSON
  geometry → SVG path strings, used for the continent outlines.

### 2.3 Layer order (paint order)

Inside the `<svg>`, in order back-to-front:

1. **Background**: a black `<rect>` covering the viewBox.
2. **Grid pattern**: a `<defs><pattern>` defining a 50×50px grid line,
   referenced by a full-canvas `<rect fill="url(#grid)" />`. 10% opacity,
   theme-aware stroke.
3. **World countries**: each continent feature from the static
   `world-outline.ts` (Natural Earth 110m, FeatureCollection of
   MultiPolygons) rendered as a `<path d={pathGenerator(geom)}>`. Fill +
   stroke are theme-aware; opacity ~0.45.
4. **Place pins**: per-place `<g>` containing circle, optional pulse
   ring, and optional label box.

---

## 3. Visual Layers

### 3.1 Pin circle

```jsx
<circle
  cx={coords.x}
  cy={coords.y}
  r={3 / zoom}
  fill={pinColor}
  filter={`drop-shadow(0 0 ${8 / zoom}px ${pinColor})`}
/>
```

Radius and glow blur both divide by `zoom` so the pin stays visually
constant as the user zooms in or out.

Color priority (`getPinColor` logic):
- Place name matches `currentChunkLocation` prop → **yellow** (the
  narrative is "here").
- User has selected this place → **cyan**.
- User is hovering this place → bright theme accent.
- Otherwise → muted theme accent.

### 3.2 Pulse ring (selected/hovered only)

A `<circle>` with `r={8/zoom}`, no fill, `stroke={pinColor}`,
`strokeWidth={1/zoom}`, opacity `0.6`, plus Tailwind's `animate-pulse`
class. Rendered only when `selectedLocation === place.id ||
hoveredLocation === place.id`.

### 3.3 Label

A `<g style={{display: labelVisible ? '' : 'none'}}>` containing:
- A `<rect>` background (rounded, semi-opaque black) sized to fit the
  label text.
- A `<text>` element with the place name; font size `11/zoom`, monospace,
  drop-shadow glow.

**Crucial**: labels are kept in the DOM and hidden via CSS `display: none`
(not conditionally rendered) — this avoids React reconciliation thrash
when zoom changes and label visibility flips frequently.

### 3.4 Empty state

When the places query returns an empty array, render
`<text x="50%" y="50%">[NO LOCATION DATA AVAILABLE]</text>`. Don't gate
the entire SVG behind a loading skeleton — keep the grid + world outline
visible.

---

## 4. Interactions

### 4.1 Pan (pointer drag)

- `onPointerDown` on the `<svg>`: capture pointer ID, store start point,
  begin a drag session.
- `onPointerMove`: compute delta from start, scale by current `viewBox.width
  / svgClientWidth`, subtract from `viewBox.x/y`. Call `clampViewBox`.
- `onPointerUp`: release pointer capture, clear drag state.

**Click-vs-drag threshold** (June 2026 rework): a press is not a drag
until the pointer moves a few px (`DRAG_THRESHOLD_PX`, straight-line
from pointerdown). Below the threshold the map must not move and the
release counts as a click (pin selection); at or above it the press is
a pan and the release must never fire a selection — even if the pointer
returns to its origin before release. The session logic is pure and
unit-tested (`beginDragSession` / `applyDragMove` / `endDragSession` in
`lib/map-geometry.ts`).

**Pointer capture is mandatory**, not optional:
`svgRef.current.setPointerCapture(e.pointerId)` ensures `pointermove`
continues firing on the SVG even when the pointer leaves the SVG bounds
(e.g., dragged off the side of the tab). Without it, drag breaks on
mobile and on fast cursor movement.

**Multi-pointer safety**: store `activePointerId` in a ref; ignore any
`pointermove`/`pointerup` whose `pointerId` doesn't match. Without this,
two-finger trackpad gestures fight over drag state.

### 4.2 Zoom (wheel)

The mathematically interesting part. Goal: after zoom, the SVG point
that was under the cursor should still be under the cursor.

```ts
const delta = e.deltaY > 0 ? 0.9 : 1.1;
const newZoom = Math.min(Math.max(zoom * delta, 0.2), 100);

const rect = svgRef.current!.getBoundingClientRect();
const mouseX = e.clientX - rect.left;
const mouseY = e.clientY - rect.top;

setViewBox(prev => {
  // The SVG-space point currently under the cursor:
  const svgX = prev.x + mouseX * (prev.width / rect.width);
  const svgY = prev.y + mouseY * (prev.height / rect.height);
  // New viewBox dimensions:
  const newWidth = mapDimensions.width / newZoom;
  const newHeight = mapDimensions.height / newZoom;
  // Solve for the new top-left so the cursor still hits (svgX, svgY):
  return clampViewBox({
    x: svgX - (mouseX / rect.width) * newWidth,
    y: svgY - (mouseY / rect.height) * newHeight,
    width: newWidth,
    height: newHeight,
  });
});
setZoom(newZoom);
```

Zoom range: 0.2× to 100×. Don't allow negative or zero.

### 4.3 ViewBox clamping

After every pan or zoom, run `clampViewBox(viewBox)` to ensure the world
outline stays at least partially visible.

**The mistake to avoid** (shipped in the U4 rebuild): clamping the
window to the initially *fitted* region. At 1.00× zoom the window
exactly equals the fit box, the clamp range collapses to zero on both
axes, and every drag is silently clamped back — pan handlers that look
correct but do nothing. Clamp against the **whole projected world**
instead (for equirectangular, the two projected corners of
[-180..180, -90..90]), requiring some minimum fraction of the viewport
(`MIN_WORLD_VISIBLE_FRACTION`) to still overlap the world box, so the
map can roam anywhere but never be dragged fully off-screen.

### 4.4 Place selection / details modal

- Click a pin → set `selectedLocation = place.id`, open details dialog.
  NOTE: with pointer capture on the `<svg>`, the browser retargets the
  derived `click` event to the capture element, so a pin `onClick` never
  fires once the svg captures on pointerdown. Select on the svg's
  `pointerup` instead, keyed off the original pointerdown target (the
  release target is retargeted too), and only when the drag session
  stayed below the click-vs-drag threshold (§4.1).
- Click a place in the sidebar → set `selectedLocation` AND programmatically
  reposition the viewBox so the place sits at the canvas center
  (manually compute new viewBox.x/y from `placeCoordinates.get(id)`).

### 4.5 Sidebar (location index)

Right-side panel listing all places grouped by `zone`. Zone headers
collapse / expand via a `Set<number>` of expandedZones IDs. Place items
show name, type (if `"vehicle"`), and a color dot matching pin color.

### 4.6 Place details dialog

When `selectedLocation !== null && detailsDialogOpen`, render a Radix
`<Dialog>` with:
- Thumbnail (first / main image from `placeImagesQuery`).
- Metadata: name, ID, type, zone, coordinates (lat/lng to 6 decimals).
- Long-form text sections: summary, history, current status, inhabitants
  (parsed from either array or PG-quoted-string format), secrets.
- Upload button (hidden `<input type="file">` triggered programmatically).
- "View Gallery" button → opens `<ImageGalleryModal>`.

---

## 5. State Management

### 5.1 Local state

```ts
const [hoveredLocation, setHoveredLocation] = useState<number | null>(null);
const [selectedLocation, setSelectedLocation] = useState<number | null>(null);
const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
const [galleryOpen, setGalleryOpen] = useState(false);
const [expandedZones, setExpandedZones] = useState<Set<number>>(new Set());
const [mapDimensions, setMapDimensions] = useState({ width: 800, height: 600 });
const [mapBounds, setMapBounds] = useState<MapBounds | null>(null);
const [isDragging, setIsDragging] = useState(false);
const [viewBox, setViewBox] = useState({ x: 0, y: 0, width: 800, height: 600 });
const [zoom, setZoom] = useState(1);
```

Refs: `svgRef`, `activePointerId`, `dragStartRef`.

### 5.2 Server state (React Query)

```ts
useQuery({ queryKey: ["/api/places", slot], queryFn: ... });
useQuery({ queryKey: ["/api/zones", slot], queryFn: ... });
useQuery({
  queryKey: ["/api/places", selectedLocation, "images", slot],
  enabled: !!selectedLocation,
  queryFn: ...,
});
```

Three mutations (upload / set-main / delete) all `invalidateQueries`
on the place-images cache key on success.

### 5.3 Memoized derivations

- `placeCoordinates: Map<placeId, {x,y}>` — projected SVG coords per
  place. Recompute when `visiblePlaces` or projection changes.
- `labelVisibility: Map<placeId, boolean>` — see §6.1.
- `worldCountries: string[]` — pre-rendered SVG path strings for each
  continent feature. Recompute only when the projection changes (not on
  every render).

### 5.4 No persistence

Map zoom/pan does **not** persist to URL or localStorage. Reloads reset
to the default viewBox. This is a deliberate choice — the map is meant
to feel like a live window, not a navigable document.

---

## 6. Known Subtleties (The Historical Failure Modes)

These are the five areas where past rebuilds went wrong:

### 6.1 Label collision detection

Without culling, dense place maps become an unreadable wall of overlapping
text. The algorithm:

1. Walk every visible place and tag it with a priority:
   - `4` = currently selected
   - `3` = currently hovered
   - `2` = matches `currentChunkLocation`
   - `1` = everything else
2. Sort by priority descending (selected first).
3. Maintain a running array of bounding-box rectangles already accepted.
4. For each place in priority order:
   - If priority > 1, always show (force-visible).
   - Otherwise, gate by zoom level (rough thresholds):
     - zoom ≥ 3.0: all labels
     - zoom 2.0–3.0: every 5th
     - zoom 1.5–2.0: every 10th
     - zoom 1.0–1.5: every 20th
     - zoom < 1.0: none
   - AABB overlap test against accepted rectangles. If overlaps AND not
     force-visible, hide. Otherwise add to accepted list, show.

Label box dimensions scale with zoom (`labelWidth = 80/zoom`,
`labelHeight = 16/zoom`, vertical offset `25/zoom`). All in SVG units.

**The mistake to avoid**: a naive "show all labels above zoom X, hide
all below" produces both unreadable overlap and missing critical labels
(current location absent at low zoom). Priority + AABB is the working
solution.

### 6.2 Zoom-cursor anchoring

The arithmetic in §4.2 is non-obvious and easy to get wrong. The
intuition: think of the viewBox as a window onto SVG space. Before the
zoom, the SVG point `(svgX, svgY)` is under the cursor. After the zoom,
the window changes size — solve for the new window origin so that same
SVG point still sits at the cursor's relative position within the
window.

**The mistake to avoid**: just multiplying viewBox dimensions by
`1/newZoom` without adjusting `x/y` produces "zoom into the top-left
corner" behavior, which feels broken.

### 6.3 Pointer capture

`setPointerCapture(pointerId)` on `pointerdown`, `releasePointerCapture`
on `pointerup`. Skip this on the assumption that React event delegation
handles it, and drag breaks the moment the cursor leaves the SVG.

`activePointerId` ref: track which pointer is "the dragger". Ignore
`pointermove`/`pointerup` from any other pointer. Without this,
multi-touch (or even a stray trackpad gesture) corrupts the drag state.

### 6.4 Coordinate parsing & validation

PostGIS returns GeoJSON Point with `coordinates: [lng, lat]` in that
order. **GeoJSON puts longitude first**, the opposite of how humans
usually say "lat/lng". Mixing them up shows places mirrored across the
diagonal.

Validation: both numbers `Number.isFinite()`, lat ∈ [-90,90],
lng ∈ [-180,180]. Out-of-range coords are silently dropped with
`console.warn`. Don't throw — bad data shouldn't take down the map.

Currently only `Point` is rendered. `Polygon` / `LineString` geometries
are returned by the API as-is but are dropped at the renderer; future
work would compute centroids for Polygon and midpoints for LineString.

### 6.5 Spherical Fit Winding

d3-geo polygons are **spherical**: a ring's winding order decides which
side is the inside. A bounding-box ring wound the wrong way denotes the
*complement* of the box (the entire globe minus it), so `fitSize` quietly
fits the whole world and every regional map renders as a world-scale
speck. The U4 rebuild shipped with exactly this bug — on an Earth slot it
masqueraded as a plausible whole-world view; on a generated world (one
zone, one place) it produced a blank void.

**The fix**: never feed `fitSize` a bounding polygon. Use winding-free
corner points (`boundsToFitObject` in `lib/map-geometry.ts`):

```ts
proj.fitSize([width, height], {
  type: "MultiPoint",
  coordinates: [[minLng, minLat], [maxLng, maxLat]],
});
```

Regression-tested in `map-geometry.test.ts` ("failure mode 5").

---

## 7. External Dependencies

| Package | Version | Role |
|---|---|---|
| `d3-geo` | ^3.1.1 | Equirectangular projection, geoPath generator |
| `@types/d3-geo` | ^3.1.0 | TS types for d3-geo |
| `@tanstack/react-query` | ^5.60.5 | Server state for places / zones / images |
| `@radix-ui/react-dialog` | ^1.1.15 | Place details + image gallery modals |
| `@radix-ui/react-scroll-area` | ^1.2.4 | Sidebar scroll |
| `lucide-react` | ^0.453.0 | Pin, chevron, upload, star, trash icons |
| `clsx` | ^2.1.1 | Class name composition |
| `tailwindcss-animate` | ^1.0.7 | `animate-pulse` class for selection rings |

The static world outline (`Natural Earth 110m`) is bundled in
`lib/world-outline.ts` rather than fetched at runtime — it's tiny (~50KB
unminified) and not worth a separate HTTP round-trip.

---

## 8. Out of Scope (Future Work)

These were noted as gaps in the old implementation:

- **Zone boundary polygons**: `zones.boundary` is a PostGIS geometry that
  is fetched but never rendered. Future versions could draw zone borders
  underneath place pins.
- **Polygon / LineString places**: API returns these but renderer drops
  them. Should compute centroid / midpoint for placement.
- **Mini-map / overview**: useful for very-zoomed-in navigation; not yet
  built.
- **Distance / pathing tools**: not built; PostGIS `ST_Distance` makes
  this cheap on the backend if a feature wants it.
- **Persisted view state**: deliberately not persisted, but could move to
  URL params if a "shareable map link" feature is desired.

---

## Appendix: Key Source References (Pre-Demolition)

For posterity, these were the canonical files in the original
implementation (now deleted on the `ui-rebuild` branch):

- `ui/client/src/components/MapTab.tsx` — main component (~1100 lines)
- `ui/client/src/hooks/useGeoProjection.ts` — projection hook
- `ui/client/src/lib/world-outline.ts` — Natural Earth 110m bundle
- `ui/server/routes.ts` — `/api/places`, `/api/zones`, image CRUD
- `ui/server/storage.ts` — `getAllPlaces`, `getAllZones`, place_images
- `ui/shared/schema.ts` — Drizzle table definitions

The backend (`server/`, `shared/`) is **not** part of the demolition and
remains intact.
