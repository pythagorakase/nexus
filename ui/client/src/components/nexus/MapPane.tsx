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
 *  3. Pointer capture → setPointerCapture on pointerdown + an
 *                       activePointerId ref that rejects events from any
 *                       other pointer (multi-touch / trackpad safety)
 *  4. lng/lat order   → extractCoordinates is the only place the GeoJSON
 *                       [longitude, latitude] array is destructured
 *  5. Spherical fit winding → boundsToFitObject in lib/map-geometry.ts
 *                       feeds fitSize winding-free corner points; a
 *                       bounding polygon ring wound the wrong way makes
 *                       d3 fit the sphere-complement (i.e. the whole
 *                       globe), which shipped in the original rebuild
 *
 * Worlds: the bundled Natural Earth outline renders only when the slot's
 * world layer (GET /api/layers) is Earth. Generated worlds have no
 * coastline data, so they get a deliberate abstract survey chart instead:
 * open sea, grid, dashed zone survey boundaries, place beacons.
 *
 * Design: theme-token colors only (--brass / --bronze / --bg-elev-* plus
 * the --map-* mixes on .mappane-canvas), menu-font labels — theme-aware
 * across Veil / Gilded / Vector with zero map-specific colors.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import type { GeoPermissibleObjects } from "d3-geo";
import { ChevronDown, ChevronRight, MapPin } from "lucide-react";
import { useGeoProjection } from "@/hooks/useGeoProjection";
import {
  centerViewBoxOn,
  clampViewBox,
  clampZoom,
  computeLabelVisibility,
  computeMapBounds,
  extractCoordinates,
  extractZoneBoundary,
  worldIsEarth,
  zoomViewBoxAtCursor,
  type BoundaryGeometry,
  type LabelCandidate,
  type ViewBox,
} from "@/lib/map-geometry";
import {
  getCurrentPlace,
  getLayers,
  getPlaces,
  getZones,
} from "@/lib/narrative-api";
import { worldOutline } from "@/lib/world-outline";
import type { CurrentPlace, Place, WorldLayer, Zone } from "@shared/schema";
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

  const { data: layers = [], error: layersError } = useQuery<WorldLayer[]>({
    queryKey: ["/api/layers", slot],
    queryFn: () => getLayers(slot),
  });

  const { data: currentPlace = null } = useQuery<CurrentPlace | null>({
    queryKey: ["/api/current-place", slot],
    queryFn: () => getCurrentPlace(slot),
  });

  // The bundled Natural Earth outline is Earth's geography; it renders
  // only when the slot's world layer is literally Earth. Generated worlds
  // (no coastline data exists for them) get the abstract survey chart:
  // open sea, grid, zone survey boundaries, place beacons.
  const earthWorld = worldIsEarth(layers);

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
  const activePointerId = useRef<number | null>(null);
  const dragStartRef = useRef({ x: 0, y: 0 });
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
  // Survey boundaries (zones.boundary polygons) are real per-world data;
  // they are drawn — and counted toward the projection fit — only on
  // non-Earth worlds, where they are the chart's primary shapes.
  const surveyGeometries = useMemo<Array<{ id: number; geometry: BoundaryGeometry }>>(() => {
    if (earthWorld) return [];
    return zones.flatMap((zone) => {
      const geometry = extractZoneBoundary(zone);
      return geometry ? [{ id: zone.id, geometry }] : [];
    });
  }, [zones, earthWorld]);

  const mapBounds = useMemo(
    () =>
      computeMapBounds(
        places,
        surveyGeometries.map((entry) => entry.geometry),
      ),
    [places, surveyGeometries],
  );

  const { transformCoordinates, geoJsonToSvgPath } = useGeoProjection({
    mapDimensions,
    mapBounds,
  });

  const worldCountries = useMemo(() => {
    if (!earthWorld) return [];
    return worldOutline.features
      .map((feature, index) => ({
        id: index,
        pathData: geoJsonToSvgPath(feature.geometry),
      }))
      .filter(
        (country): country is { id: number; pathData: string } =>
          country.pathData !== null,
      );
  }, [earthWorld, geoJsonToSvgPath]);

  const surveyBoundaries = useMemo(() => {
    return surveyGeometries
      .map((entry) => ({
        id: entry.id,
        pathData: geoJsonToSvgPath(entry.geometry as GeoPermissibleObjects),
      }))
      .filter(
        (boundary): boundary is { id: number; pathData: string } =>
          boundary.pathData !== null,
      );
  }, [surveyGeometries, geoJsonToSvgPath]);

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
        );
      });
    };

    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  // ── Pan (failure mode 3: pointer capture + active-pointer guard) ────
  const isInteractiveTarget = (target: EventTarget | null) => {
    if (!(target instanceof Element)) return false;
    return Boolean(target.closest("[data-interactive='true']"));
  };

  const endDrag = useCallback(() => {
    setIsDragging(false);
    activePointerId.current = null;
  }, []);

  const handlePointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    if (isInteractiveTarget(e.target)) return;

    activePointerId.current = e.pointerId;
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX, y: e.clientY };
    // Mandatory: keeps pointermove firing when the cursor leaves the SVG
    // mid-drag. Without capture, drag breaks on fast cursor movement.
    svgRef.current?.setPointerCapture?.(e.pointerId);
  };

  const handlePointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    // Reject any pointer that isn't the dragger (multi-touch safety).
    if (!isDragging || activePointerId.current !== e.pointerId) return;

    const deltaX = e.clientX - dragStartRef.current.x;
    const deltaY = e.clientY - dragStartRef.current.y;
    dragStartRef.current = { x: e.clientX, y: e.clientY };

    const dims = dimensionsRef.current;
    setViewBox((prev) => {
      const scaleX = prev.width / Math.max(dims.width, 1);
      const scaleY = prev.height / Math.max(dims.height, 1);
      return clampViewBox(
        {
          ...prev,
          x: prev.x - deltaX * scaleX,
          y: prev.y - deltaY * scaleY,
        },
        dims.width,
        dims.height,
      );
    });
  };

  const handlePointerEnd = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (activePointerId.current !== e.pointerId) return;
    svgRef.current?.releasePointerCapture?.(e.pointerId);
    endDrag();
  };

  // ── Selection ───────────────────────────────────────────────────────
  const selectPlace = (placeId: number, center: boolean) => {
    setSelectedId(placeId);
    setDialogOpen(true);
    if (center) {
      const coords = placeCoordinates.get(placeId);
      if (coords) {
        const dims = dimensionsRef.current;
        setViewBox((prev) =>
          centerViewBoxOn(coords, prev, dims.width, dims.height),
        );
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

  const dataError = (placesError ?? zonesError ?? layersError) as Error | null;

  return (
    <div className="mappane" data-testid="map-pane">
      {/* ── Location index ─────────────────────────────────────────── */}
      <div className="mappane-list">
        <span className="eyebrow brass-glow">
          ATLAS · {places.length} {places.length === 1 ? "PLACE" : "PLACES"}
        </span>
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
          onPointerUp={handlePointerEnd}
          onPointerLeave={handlePointerEnd}
          onPointerCancel={handlePointerEnd}
          data-testid="map-svg"
        >
          {/* Background + survey grid */}
          <rect
            width={mapDimensions.width}
            height={mapDimensions.height}
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
            width={mapDimensions.width}
            height={mapDimensions.height}
            fill="url(#nexus-map-grid)"
          />

          {/* World outline (Natural Earth 110m, bundled) — Earth worlds
              only. Land/coast colors are theme-token mixes defined on
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

          {/* Zone survey boundaries (zones.boundary) — non-Earth worlds.
              Dashed survey lines, not coastlines: deliberate "charted
              extent" cartography for worlds without landmass data. */}
          {surveyBoundaries.map((boundary) => (
            <path
              key={boundary.id}
              d={boundary.pathData}
              fill="var(--map-survey)"
              stroke="var(--map-survey-line)"
              strokeWidth={1 / zoom}
              strokeDasharray={`${6 / zoom} ${4 / zoom}`}
              strokeLinejoin="round"
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
                data-interactive="true"
                onPointerEnter={() => {
                  if (!isDragging) setHoveredId(place.id);
                }}
                onPointerLeave={() => {
                  if (!isDragging) setHoveredId(null);
                }}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  if (isDragging) return;
                  e.stopPropagation();
                  selectPlace(place.id, false);
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

          {/* Empty state: grid stays visible (spec §3.4) */}
          {!placesLoading &&
            placeCoordinates.size === 0 &&
            surveyBoundaries.length === 0 && (
              <text
                x="50%"
                y="50%"
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
