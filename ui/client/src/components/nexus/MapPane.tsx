/**
 * MapPane - the rebuilt PostGIS world map (milestone U4).
 *
 * SVG + d3-geo equirectangular per docs/maptab_rebuild_spec.md. The
 * viewBox attribute is the single mutable pan/zoom surface (zoom is
 * DERIVED from viewBox width — no separate zoom state to drift), so
 * stroke widths and font sizes divide by zoom to stay visually constant.
 *
 * The four historical failure modes (spec §6) and where they are handled:
 *  1. Label culling   → computeLabelVisibility in lib/map-geometry.ts
 *                       (priority + AABB; labels stay mounted, hidden via
 *                       CSS display so React never reconciles them away)
 *  2. Zoom anchoring  → zoomViewBoxAtCursor in lib/map-geometry.ts, driven
 *                       by a NATIVE non-passive wheel listener (React 17+
 *                       root wheel listeners are passive: preventDefault
 *                       would silently fail and scroll the page)
 *  3. Pointer capture → setPointerCapture on pointerdown (drag keeps
 *                       working across the pane edge, releases cleanly)
 *                       + the pure drag-session machine in
 *                       lib/map-geometry.ts: an owning-pointer guard that
 *                       rejects events from any other pointer
 *                       (multi-touch / trackpad safety) and a small
 *                       movement threshold separating click from drag —
 *                       pin selection fires only below it
 *  4. lng/lat order   → extractCoordinates is the only place the GeoJSON
 *                       [longitude, latitude] array is destructured
 *  5. Spherical fit winding → boundsToFitObject in lib/map-geometry.ts
 *                       feeds fitSize winding-free corner points; a
 *                       bounding polygon ring wound the wrong way makes
 *                       d3 fit the sphere-complement (i.e. the whole
 *                       globe), which shipped in the original rebuild
 *
 * Geography: ALL NEXUS worlds are Earth-shaped by design — GIS
 * coordinates are real-Earth positions regardless of genre (deliberate
 * cognitive offloading for LLM spatial reasoning: latitude implies
 * climate, terrain implies travel modes). The bundled Natural Earth
 * outline therefore renders for every slot.
 *
 * Design: theme-token colors only (--brass / --bronze / --bg-elev-* plus
 * the --map-* mixes on .mappane-canvas), menu-font labels — theme-aware
 * across Veil / Gilded / Vector with zero map-specific colors.
 */
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, MapPin } from "lucide-react";
import { useGeoProjection } from "@/hooks/useGeoProjection";
import {
  applyDragMove,
  beginDragSession,
  centerViewBoxOn,
  clampZoom,
  computeLabelVisibility,
  computeMapBounds,
  extractCoordinates,
  panViewBox,
  zoomViewBoxAtCursor,
  type DragSession,
  type LabelCandidate,
  type PanBounds,
  type ViewBox,
} from "@/lib/map-geometry";
import { getCurrentPlace, getPlaces, getZones } from "@/lib/narrative-api";
import { worldOutline } from "@/lib/world-outline";
import type { CurrentPlace, Place, Zone } from "@shared/schema";
import { MapPlaceDialog } from "./MapPlaceDialog";

interface MapPaneProps {
  slot: number | null;
}

/** Approximate label box width in SVG units for the AABB culler. */
function estimateLabelWidth(name: string, zoom: number): number {
  return (name.length * 11 * 0.75 + 12) / zoom;
}

export function MapPane({ slot }: MapPaneProps) {
  // ── Server state ────────────────────────────────────────────────────
  const {
    data: places = [],
    isLoading: placesLoading,
    error: placesError,
  } = useQuery<Place[]>({
    queryKey: ["/api/places", slot],
    queryFn: () => getPlaces(slot),
  });

  const { data: zones = [], error: zonesError } = useQuery<Zone[]>({
    queryKey: ["/api/zones", slot],
    queryFn: () => getZones(slot),
  });

  const { data: currentPlace = null } = useQuery<CurrentPlace | null>({
    queryKey: ["/api/current-place", slot],
    queryFn: () => getCurrentPlace(slot),
  });

  // ── Local state ─────────────────────────────────────────────────────
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [expandedZones, setExpandedZones] = useState<Set<number>>(new Set());
  const [mapDimensions, setMapDimensions] = useState({
    width: 800,
    height: 600,
  });
  const [viewBox, setViewBox] = useState<ViewBox>({
    x: 0,
    y: 0,
    width: 800,
    height: 600,
  });
  const [isDragging, setIsDragging] = useState(false);

  const svgRef = useRef<SVGSVGElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const dragSessionRef = useRef<DragSession | null>(null);
  const downTargetRef = useRef<EventTarget | null>(null);
  const dimensionsRef = useRef(mapDimensions);
  dimensionsRef.current = mapDimensions;

  // Zoom is derived, never stored: one source of truth for pan/zoom.
  const zoom = mapDimensions.width / viewBox.width;

  // ── Responsive sizing (spec §2.1: ResizeObserver on the parent) ─────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const width = Math.max(entry.contentRect.width, 1);
      const height = Math.max(entry.contentRect.height, 1);
      setMapDimensions({ width, height });
      // Reset the window on resize — the projection refits to the new
      // canvas, so a stale viewBox would show the wrong region.
      setViewBox({ x: 0, y: 0, width, height });
    });

    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  // ── Projection ──────────────────────────────────────────────────────
  // Fit to the charted places only. Zone boundaries are deliberately NOT
  // part of the fit: legacy slots carry near-global zones (Pacific Ocean,
  // Antarctic) that would blow the frame back out to world scale.
  const mapBounds = useMemo(() => computeMapBounds(places), [places]);

  const { transformCoordinates, geoJsonToSvgPath } = useGeoProjection({
    mapDimensions,
    mapBounds,
  });

  // Pan bounds: the whole projected world, not the initially fitted
  // region. The old clamp confined the window to the fit box, which at
  // 1.00× zoom had zero slack — dragging was a silent no-op. Equirect
  // projection is linear, so the two corners bound the projected globe.
  const panBounds = useMemo<PanBounds>(() => {
    const a = transformCoordinates(-180, 90);
    const b = transformCoordinates(180, -90);
    if (!a || !b) {
      throw new Error("Map projection failed to project the world corners");
    }
    return {
      minX: Math.min(a.x, b.x),
      minY: Math.min(a.y, b.y),
      maxX: Math.max(a.x, b.x),
      maxY: Math.max(a.y, b.y),
    };
  }, [transformCoordinates]);
  const panBoundsRef = useRef(panBounds);
  panBoundsRef.current = panBounds;

  const worldCountries = useMemo(() => {
    return worldOutline.features
      .map((feature, index) => ({
        id: index,
        pathData: geoJsonToSvgPath(feature.geometry),
      }))
      .filter(
        (country): country is { id: number; pathData: string } =>
          country.pathData !== null,
      );
  }, [geoJsonToSvgPath]);

  const placeCoordinates = useMemo(() => {
    const cache = new Map<number, { x: number; y: number }>();
    for (const place of places) {
      const latLng = extractCoordinates(place);
      if (!latLng) continue;
      const projected = transformCoordinates(latLng.longitude, latLng.latitude);
      if (projected) cache.set(place.id, projected);
    }
    return cache;
  }, [places, transformCoordinates]);

  // ── Label culling (failure mode 1) ──────────────────────────────────
  const labelVisibility = useMemo(() => {
    const candidates: LabelCandidate[] = [];
    places.forEach((place, index) => {
      const coords = placeCoordinates.get(place.id);
      if (!coords) return;

      let priority = 1;
      if (selectedId === place.id) priority = 4;
      else if (hoveredId === place.id) priority = 3;
      else if (currentPlace?.placeId === place.id) priority = 2;

      candidates.push({
        placeId: place.id,
        index,
        coords,
        priority,
        labelWidthUnits: estimateLabelWidth(place.name, zoom),
      });
    });
    return computeLabelVisibility(candidates, zoom);
  }, [places, placeCoordinates, zoom, selectedId, hoveredId, currentPlace]);

  // ── Zoom (failure mode 2): native non-passive wheel listener ────────
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const dims = dimensionsRef.current;
      const cursorX = e.clientX - rect.left;
      const cursorY = e.clientY - rect.top;
      const factor = e.deltaY > 0 ? 0.9 : 1.1;

      setViewBox((prev) => {
        const currentZoom = dims.width / prev.width;
        const newZoom = clampZoom(currentZoom * factor);
        if (newZoom === currentZoom) return prev;
        return zoomViewBoxAtCursor(
          prev,
          cursorX,
          cursorY,
          rect.width,
          rect.height,
          newZoom,
          dims.width,
          dims.height,
          panBoundsRef.current,
        );
      });
    };

    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  // ── Pan (failure mode 3: pointer capture + drag-session machine) ────
  // Every press starts a session — including presses on pins, so a drag
  // that begins on a pin pans the map. Selection happens on release,
  // only when the session never crossed the drag threshold.
  const handlePointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;

    dragSessionRef.current = beginDragSession(e.pointerId, e.clientX, e.clientY);
    downTargetRef.current = e.target;
    // Mandatory (spec §6.3): capture keeps pointermove firing when the
    // cursor leaves the SVG mid-drag and guarantees a clean release.
    svgRef.current?.setPointerCapture?.(e.pointerId);
  };

  const handlePointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const session = dragSessionRef.current;
    if (!session) return;

    const move = applyDragMove(session, e.pointerId, e.clientX, e.clientY);
    if (!move) return; // foreign pointer (multi-touch safety)
    dragSessionRef.current = move.session;

    if (move.session.panned && !isDragging) setIsDragging(true);
    if (move.deltaX === 0 && move.deltaY === 0) return;

    const dims = dimensionsRef.current;
    setViewBox((prev) =>
      panViewBox(
        prev,
        move.deltaX,
        move.deltaY,
        dims.width,
        dims.height,
        panBounds,
      ),
    );
  };

  const handlePointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    const session = dragSessionRef.current;
    if (!session || session.pointerId !== e.pointerId) return;

    dragSessionRef.current = null;
    setIsDragging(false);
    svgRef.current?.releasePointerCapture?.(e.pointerId);

    // Below the drag threshold this press was a click. Pointer capture
    // retargets the click event to the SVG itself, so pin selection lives
    // here — keyed off the original pointerdown target, never the (re-
    // targeted) release target.
    if (!session.panned && downTargetRef.current instanceof Element) {
      const pin = downTargetRef.current.closest("[data-place-id]");
      if (pin) {
        const placeId = Number(pin.getAttribute("data-place-id"));
        if (Number.isFinite(placeId)) selectPlace(placeId, false);
      }
    }
    downTargetRef.current = null;
  };

  // Aborted gestures (pointercancel, capture stolen/lost without a
  // pointerup): reset drag state, never fire a selection.
  const handlePointerAbort = (e: ReactPointerEvent<SVGSVGElement>) => {
    const session = dragSessionRef.current;
    if (!session || session.pointerId !== e.pointerId) return;
    dragSessionRef.current = null;
    downTargetRef.current = null;
    setIsDragging(false);
  };

  // ── Selection ───────────────────────────────────────────────────────
  const selectPlace = (placeId: number, center: boolean) => {
    setSelectedId(placeId);
    setDialogOpen(true);
    if (center) {
      const coords = placeCoordinates.get(placeId);
      if (coords) {
        setViewBox((prev) => centerViewBoxOn(coords, prev, panBounds));
      }
    }
  };

  const toggleZone = (zoneId: number) => {
    setExpandedZones((prev) => {
      const next = new Set(prev);
      if (next.has(zoneId)) next.delete(zoneId);
      else next.add(zoneId);
      return next;
    });
  };

  // ── Derived view data ───────────────────────────────────────────────
  const placesByZone = useMemo(() => {
    const groups = new Map<number, Place[]>();
    for (const place of places) {
      const zoneId = Number(place.zone ?? 0);
      const group = groups.get(zoneId);
      if (group) group.push(place);
      else groups.set(zoneId, [place]);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a - b);
  }, [places]);

  const zoneById = useMemo(() => {
    const map = new Map<number, Zone>();
    for (const zone of zones) map.set(zone.id, zone);
    return map;
  }, [zones]);

  const selectedPlace = useMemo(
    () => places.find((p) => p.id === selectedId) ?? null,
    [places, selectedId],
  );

  const pinState = (place: Place): "current" | "selected" | "hovered" | "rest" => {
    if (currentPlace?.placeId === place.id) return "current";
    if (selectedId === place.id) return "selected";
    if (hoveredId === place.id) return "hovered";
    return "rest";
  };

  // IRIS adaptation of the spec's pin palette (yellow/cyan are off-system):
  // current → brass-bright, selected/hovered → brass, rest → bronze.
  const PIN_COLOR: Record<string, string> = {
    current: "var(--brass-bright)",
    selected: "var(--brass)",
    hovered: "var(--brass-bright)",
    rest: "var(--bronze)",
  };

  const dataError = (placesError ?? zonesError) as Error | null;

  return (
    <div className="mappane" data-testid="map-pane">
      {/* ── Location index ─────────────────────────────────────────────
          No header: the rail's Map tab already names this surface, and a
          place count would restate the visible list (tenets 3/5; same
          rationale as the cast roster's removed "CAST · N" header). */}
      <div className="mappane-list">
        <ul>
          {placesByZone.map(([zoneId, zonePlaces]) => {
            const zone = zoneById.get(zoneId);
            const isExpanded = expandedZones.has(zoneId);
            return (
              <li key={zoneId} className="map-zone">
                <button
                  type="button"
                  className="map-zone-header"
                  onClick={() => toggleZone(zoneId)}
                  data-testid={`map-zone-${zoneId}`}
                >
                  {isExpanded ? (
                    <ChevronDown size={12} aria-hidden="true" />
                  ) : (
                    <ChevronRight size={12} aria-hidden="true" />
                  )}
                  <span className="map-zone-name">
                    {zone?.name ?? `Zone ${zoneId}`}
                  </span>
                  <span className="map-zone-count">{zonePlaces.length}</span>
                </button>
                {isExpanded && (
                  <ul className="map-zone-places">
                    {zonePlaces.map((place: Place) => {
                      const state = pinState(place);
                      return (
                        <li key={place.id}>
                          <button
                            type="button"
                            className={`map-place-row ${
                              selectedId === place.id ? "on" : ""
                            } ${state === "current" ? "here" : ""}`}
                            onClick={() => selectPlace(place.id, true)}
                            data-testid={`map-place-row-${place.id}`}
                          >
                            <span
                              className="map-place-dot"
                              style={{ background: PIN_COLOR[state] }}
                            />
                            <span className="map-place-name">{place.name}</span>
                            {!placeCoordinates.has(place.id) && (
                              <span className="map-place-uncharted">
                                UNCHARTED
                              </span>
                            )}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      {/* ── Map canvas ─────────────────────────────────────────────── */}
      <div className="mappane-canvas" ref={canvasRef}>
        <svg
          ref={svgRef}
          className={`mappane-svg ${isDragging ? "dragging" : ""}`}
          viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
          preserveAspectRatio="xMidYMid slice"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerAbort}
          onLostPointerCapture={handlePointerAbort}
          data-testid="map-svg"
        >
          {/* Background + survey grid track the window: the viewBox can
              now roam beyond the initially fitted region, so a fixed
              canvas-sized rect would run out from under the sea. */}
          <rect
            x={viewBox.x}
            y={viewBox.y}
            width={viewBox.width}
            height={viewBox.height}
            fill="var(--map-sea)"
          />
          <defs>
            <pattern
              id="nexus-map-grid"
              width="50"
              height="50"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M50 0H0V50"
                fill="none"
                stroke="var(--brass)"
                strokeOpacity="0.08"
                strokeWidth="0.5"
              />
            </pattern>
          </defs>
          <rect
            x={viewBox.x}
            y={viewBox.y}
            width={viewBox.width}
            height={viewBox.height}
            fill="url(#nexus-map-grid)"
          />

          {/* World outline (Natural Earth 110m, bundled). Every NEXUS
              world uses real-Earth geography, so this renders for all
              slots. Land/coast colors are theme-token mixes defined on
              .mappane-canvas so all three themes keep land/sea contrast. */}
          {worldCountries.map((country) => (
            <path
              key={country.id}
              d={country.pathData}
              fill="var(--map-land)"
              stroke="var(--map-coast)"
              strokeWidth={1 / zoom}
            />
          ))}

          {/* Place pins */}
          {places.map((place) => {
            const coords = placeCoordinates.get(place.id);
            if (!coords) return null;

            const state = pinState(place);
            const pinColor = PIN_COLOR[state];
            const labelVisible = labelVisibility.get(place.id) ?? false;
            const fontSize = 11 / zoom;
            const labelWidth = estimateLabelWidth(place.name, zoom);
            const ringVisible = state !== "rest";

            return (
              <g
                key={place.id}
                className="map-pin"
                data-place-id={place.id}
                onPointerEnter={() => {
                  if (!isDragging) setHoveredId(place.id);
                }}
                onPointerLeave={() => {
                  if (!isDragging) setHoveredId(null);
                }}
                data-testid={`map-pin-${place.id}`}
              >
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r={3 / zoom}
                  fill={pinColor}
                  style={{
                    filter: `drop-shadow(0 0 ${8 / zoom}px ${pinColor})`,
                  }}
                />
                {ringVisible && (
                  <circle
                    cx={coords.x}
                    cy={coords.y}
                    r={8 / zoom}
                    fill="none"
                    stroke={pinColor}
                    strokeWidth={1 / zoom}
                    opacity={0.6}
                    className={state === "current" ? "" : "animate-pulse"}
                  />
                )}
                {/* Label: kept mounted, toggled via CSS display so zoom
                    changes never thrash React reconciliation (spec §3.3) */}
                <g style={{ display: labelVisible ? "" : "none" }}>
                  <rect
                    x={coords.x - labelWidth / 2}
                    y={coords.y - 25 / zoom}
                    width={labelWidth}
                    height={16 / zoom}
                    fill="var(--bg-elev-1)"
                    opacity={0.82}
                    rx={2 / zoom}
                  />
                  <text
                    x={coords.x}
                    y={coords.y - 13 / zoom}
                    fill={pinColor}
                    fontSize={fontSize}
                    textAnchor="middle"
                    style={{
                      fontFamily: "var(--font-menu)",
                      letterSpacing: "0.08em",
                      userSelect: "none",
                    }}
                  >
                    {place.name}
                  </text>
                </g>
              </g>
            );
          })}

          {/* Empty state: grid + world outline stay visible (spec §3.4) */}
          {!placesLoading && placeCoordinates.size === 0 && (
            <text
              x={viewBox.x + viewBox.width / 2}
              y={viewBox.y + viewBox.height / 2}
              textAnchor="middle"
              className="map-empty-text"
            >
              [ UNCHARTED ]
            </text>
          )}
        </svg>

        {/* Chrome: zoom readout */}
        <div className="map-chrome map-zoom-readout">
          <span className="eyebrow">
            {zoom >= 10 ? zoom.toFixed(1) : zoom.toFixed(2)}×
          </span>
        </div>

        {/* Chrome: current-location readout (pin glyph carries the
            meaning — no caption) */}
        {currentPlace && (
          <div className="map-chrome map-readout">
            <span className="map-readout-name">
              <MapPin size={12} aria-hidden="true" /> {currentPlace.name}
            </span>
          </div>
        )}

        {/* Data errors surface visibly — no silent fallback */}
        {dataError && (
          <div className="map-chrome map-error">
            <span className="eyebrow">[ SURVEY FAULT ]</span>
            <span className="map-error-detail">{dataError.message}</span>
          </div>
        )}
      </div>

      <MapPlaceDialog
        place={selectedPlace}
        zone={
          selectedPlace ? zoneById.get(Number(selectedPlace.zone)) ?? null : null
        }
        slot={slot}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
