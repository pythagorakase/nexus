import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { MapPin, Loader2, ChevronRight, ChevronDown } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Place, Zone } from "@shared/schema";
import { worldOutline } from "@/lib/world-outline";
import type { FeatureCollection } from 'geojson';

interface MapTabProps {
  currentChunkLocation?: string | null;
}

const parseInhabitants = (value: unknown): string[] => {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((entry) => String(entry).trim()).filter(Boolean);
  }
  if (typeof value !== "string") {
    return [];
  }

  const trimmed = value.trim();
  if (!trimmed) return [];

  const withoutBraces = trimmed.replace(/^[{\[]|[}\]]$/g, "");
  return withoutBraces
    .split(/","|",\s*"|\"\s*,\s*\"/)
    .map((segment) => segment.replace(/^"/, "").replace(/"$/, "").replace(/\\"/g, '"').trim())
    .filter(Boolean);
};

const toParagraphs = (value: string | null | undefined): string[] => {
  if (!value) return [];
  return value
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
};

export function MapTab({ currentChunkLocation = null }: MapTabProps) {
  // State management for location interactions
  const [hoveredLocation, setHoveredLocation] = useState<number | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<number | null>(null);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);

  const [expandedZones, setExpandedZones] = useState<Set<number>>(new Set());
  
  // Map control states
  const svgRef = useRef<SVGSVGElement>(null);
  const activePointerId = useRef<number | null>(null);
  const [mapDimensions, setMapDimensions] = useState({ width: 800, height: 600 });
  const [mapBounds, setMapBounds] = useState<{ minLng: number; maxLng: number; minLat: number; maxLat: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [viewBox, setViewBox] = useState({ x: 0, y: 0, width: 800, height: 600 });
  const [zoom, setZoom] = useState(1);

  const clampViewBox = useCallback(
    (box: { x: number; y: number; width: number; height: number }) => {
      const safeWidth = Math.max(mapDimensions.width, 1);
      const safeHeight = Math.max(mapDimensions.height, 1);

      const maxX = Math.max(0, safeWidth - box.width);
      const maxY = Math.max(0, safeHeight - box.height);

      return {
        x: Math.min(Math.max(box.x, 0), maxX),
        y: Math.min(Math.max(box.y, 0), maxY),
        width: box.width,
        height: box.height,
      };
    },
    [mapDimensions.height, mapDimensions.width],
  );

  // Fetch places
  const {
    data: places = [],
    isLoading: placesLoading,
    isError: placesError,
    error: placesErrorData,
  } = useQuery<Place[]>({
    queryKey: ["/api/places"],
  });

  // Fetch zones
  const {
    data: zones = [],
    isLoading: zonesLoading,
    isError: zonesError,
    error: zonesErrorData,
  } = useQuery<Zone[]>({
    queryKey: ["/api/zones"],
  });
  
  useEffect(() => {
    const handleResize = () => {
      if (svgRef.current?.parentElement) {
        const { width, height } = svgRef.current.parentElement.getBoundingClientRect();
        const safeWidth = Math.max(width, 1);
        const safeHeight = Math.max(height, 1);
        setMapDimensions({ width: safeWidth, height: safeHeight });
        setViewBox({ x: 0, y: 0, width: safeWidth, height: safeHeight });
        setZoom(1);
        setIsDragging(false);
        activePointerId.current = null;
      }
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const extractCoordinates = (place: Place): { latitude: number; longitude: number } | null => {
    // API now returns clean lat/lng extracted from PostGIS
    const lat = place.latitude !== null && place.latitude !== undefined ? Number(place.latitude) : null;
    const lng = place.longitude !== null && place.longitude !== undefined ? Number(place.longitude) : null;

    if (lat !== null && lng !== null && Number.isFinite(lat) && Number.isFinite(lng)) {
      return { latitude: lat, longitude: lng };
    }

    return null;
  };

  // Calculate bounds from place data only (zones not needed for display)
  useEffect(() => {
    if (!places.length) return;

    let minLng = Infinity;
    let maxLng = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;

    // Extract coordinates from places only
    places.forEach(place => {
      const coords = extractCoordinates(place);
      if (coords) {
        minLng = Math.min(minLng, coords.longitude);
        maxLng = Math.max(maxLng, coords.longitude);
        minLat = Math.min(minLat, coords.latitude);
        maxLat = Math.max(maxLat, coords.latitude);
      }
    });

    // Add padding (10% on each side) to ensure everything fits nicely
    if (minLng !== Infinity && maxLng !== -Infinity) {
      const lngRange = Math.max(maxLng - minLng, 0.0001);
      const latRange = Math.max(maxLat - minLat, 0.0001);
      const padding = 0.1;

      const bounds = {
        minLng: minLng - lngRange * padding,
        maxLng: maxLng + lngRange * padding,
        minLat: minLat - latRange * padding,
        maxLat: maxLat + latRange * padding
      };

      setMapBounds(bounds);
    }
  }, [places]);

  const isLoading = placesLoading || zonesLoading;

  // Transform coordinates for SVG display using dynamic bounds
  const transformCoordinates = (lng: number, lat: number) => {
    // Use dynamic bounds if available, otherwise use global defaults
    const bounds = mapBounds || {
      minLng: -180,
      maxLng: 180,
      minLat: -90,
      maxLat: 90
    };

    const lngSpan = Math.max(bounds.maxLng - bounds.minLng, 0.0001);
    const latSpan = Math.max(bounds.maxLat - bounds.minLat, 0.0001);
    const width = Math.max(mapDimensions.width, 1);
    const height = Math.max(mapDimensions.height, 1);

    const x = ((lng - bounds.minLng) / lngSpan) * width;
    const y = height - ((lat - bounds.minLat) / latSpan) * height;

    return { x, y };
  };

  // Get place coordinates - only return valid coordinates, no fallbacks
  const getPlaceCoordinates = (place: Place): { x: number; y: number } | null => {
    const coords = extractCoordinates(place);
    if (coords) {
      return transformCoordinates(coords.longitude, coords.latitude);
    }
    return null;
  };

  // Convert GeoJSON MultiPolygon coordinates to SVG path data
  const geoJsonToSvgPath = (boundary: any): string | null => {
    if (!boundary || boundary.type !== 'MultiPolygon') return null;

    const paths: string[] = [];

    // MultiPolygon structure: [[[polygon coordinates]]]
    for (const polygon of boundary.coordinates) {
      for (const ring of polygon) {
        const pathData = ring.map(([lng, lat]: [number, number], index: number) => {
          const { x, y } = transformCoordinates(lng, lat);
          return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
        }).join(' ') + ' Z';
        paths.push(pathData);
      }
    }

    return paths.join(' ');
  };

  const visiblePlaces = places;

  // Group places by zone for the sidebar
  const placesByZone = visiblePlaces.reduce((acc, place) => {
    const zoneId = place.zoneId ?? (place as any).zone ?? 0;
    if (!acc[zoneId]) acc[zoneId] = [];
    acc[zoneId].push(place);
    return acc;
  }, {} as Record<number, Place[]>);

  // Toggle zone expansion in sidebar
  const toggleZoneExpansion = (zoneId: number) => {
    setExpandedZones(prev => {
      const newSet = new Set(prev);
      if (newSet.has(zoneId)) {
        newSet.delete(zoneId);
      } else {
        newSet.add(zoneId);
      }
      return newSet;
    });
  };

  const isInteractiveTarget = (target: EventTarget | null) => {
    if (!(target instanceof Element)) return false;
    return Boolean(target.closest("[data-interactive='true']"));
  };

  const endDrag = useCallback(() => {
    setIsDragging(false);
    activePointerId.current = null;
  }, []);

  const handlePointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    if (isInteractiveTarget(e.target)) return;

    activePointerId.current = e.pointerId;
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
    svgRef.current?.setPointerCapture?.(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!isDragging || activePointerId.current !== e.pointerId) {
      return;
    }

    e.preventDefault();
    const deltaX = e.clientX - dragStart.x;
    const deltaY = e.clientY - dragStart.y;

    setViewBox(prev => {
      const scaleX = prev.width / Math.max(mapDimensions.width, 1);
      const scaleY = prev.height / Math.max(mapDimensions.height, 1);
      const next = clampViewBox({
        ...prev,
        x: prev.x - deltaX * scaleX,
        y: prev.y - deltaY * scaleY,
      });
      return next;
    });

    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handlePointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    if (activePointerId.current !== e.pointerId) {
      return;
    }

    svgRef.current?.releasePointerCapture?.(e.pointerId);
    endDrag();
  };

  const handlePointerLeave = (e: React.PointerEvent<SVGSVGElement>) => {
    if (activePointerId.current !== e.pointerId) {
      return;
    }

    svgRef.current?.releasePointerCapture?.(e.pointerId);
    endDrag();
  };

  const handlePointerCancel = (e: React.PointerEvent<SVGSVGElement>) => {
    if (activePointerId.current !== e.pointerId) {
      return;
    }

    svgRef.current?.releasePointerCapture?.(e.pointerId);
    endDrag();
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.min(Math.max(zoom * delta, 0.2), 100);

    if (newZoom === zoom) {
      return;
    }

    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) {
      setZoom(newZoom);
      return;
    }

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    setViewBox(prev => {
      const svgX = prev.x + mouseX * (prev.width / rect.width);
      const svgY = prev.y + mouseY * (prev.height / rect.height);
      const newWidth = Math.max(mapDimensions.width, 1) / newZoom;
      const newHeight = Math.max(mapDimensions.height, 1) / newZoom;

      return clampViewBox({
        x: svgX - (mouseX / rect.width) * newWidth,
        y: svgY - (mouseY / rect.height) * newHeight,
        width: newWidth,
        height: newHeight,
      });
    });

    setZoom(newZoom);
  };

  // Determine pin color based on state
  const getPinColor = (place: Place) => {
    if (currentChunkLocation && place.name === currentChunkLocation) {
      return "#ffff00"; // Yellow for current narrative location
    }
    if (selectedLocation === place.id) {
      return "#00ffff"; // Cyan for selected
    }
    if (hoveredLocation === place.id) {
      return "#00ff80"; // Brighter green for hover
    }
    return "#00ff41"; // Default green
  };

  const shouldDisplayLabelByZoom = useCallback((index: number) => {
    if (zoom >= 3.0) {
      return true;
    }
    if (zoom >= 2.0) {
      return index % 5 === 0;
    }
    if (zoom >= 1.5) {
      return index % 10 === 0;
    }
    if (zoom >= 1.0) {
      return index % 20 === 0;
    }

    return false;
  }, [zoom]);

  const placeCoordinates = useMemo(() => {
    const cache = new Map<number, { x: number; y: number } | null>();
    visiblePlaces.forEach(place => {
      cache.set(place.id, getPlaceCoordinates(place));
    });
    return cache;
  }, [visiblePlaces, mapBounds, mapDimensions]);

  const labelVisibility = useMemo(() => {
    const boxes: Array<{ x1: number; y1: number; x2: number; y2: number }> = [];
    const visibility = new Map<number, boolean>();

    const prioritized = visiblePlaces
      .map((place, index) => {
        const coords = placeCoordinates.get(place.id);
        if (!coords) return null;

        let priority = 1;
        if (selectedLocation === place.id) {
          priority = 4;
        } else if (hoveredLocation === place.id) {
          priority = 3;
        } else if (currentChunkLocation && place.name === currentChunkLocation) {
          priority = 2;
        }

        return { place, index, coords, priority };
      })
      .filter((entry): entry is { place: Place; index: number; coords: { x: number; y: number }; priority: number } => Boolean(entry));

    prioritized.sort((a, b) => {
      if (b.priority !== a.priority) {
        return b.priority - a.priority;
      }
      return a.index - b.index;
    });

    for (const { place, index, coords, priority } of prioritized) {
      const forceVisible = priority > 1;
      const baseVisibility = forceVisible || shouldDisplayLabelByZoom(index);

      if (!baseVisibility) {
        visibility.set(place.id, false);
        continue;
      }

      const labelWidth = 80 / zoom;
      const labelHeight = 16 / zoom;
      const labelOffsetY = 25 / zoom;

      const rect = {
        x1: coords.x - labelWidth / 2,
        y1: coords.y - labelOffsetY,
        x2: coords.x + labelWidth / 2,
        y2: coords.y - labelOffsetY + labelHeight,
      };

      const overlaps = boxes.some(box => {
        return !(rect.x2 < box.x1 || rect.x1 > box.x2 || rect.y2 < box.y1 || rect.y1 > box.y2);
      });

      if (overlaps && !forceVisible) {
        visibility.set(place.id, false);
        continue;
      }

      boxes.push(rect);
      visibility.set(place.id, true);
    }

    visiblePlaces.forEach(place => {
      if (!visibility.has(place.id)) {
        visibility.set(place.id, false);
      }
    });

    return visibility;
  }, [visiblePlaces, placeCoordinates, zoom, selectedLocation, hoveredLocation, currentChunkLocation, shouldDisplayLabelByZoom]);

  // Convert each country feature to SVG path data
  const worldCountries = useMemo(() => {
    if (!worldOutline || worldOutline.type !== 'FeatureCollection') return [];

    return worldOutline.features.map((feature, index) => {
      const pathData = geoJsonToSvgPath(feature.geometry);
      return {
        id: index,
        pathData,
      };
    }).filter(country => country.pathData !== null);
  }, [mapBounds, mapDimensions]);

  return (
    <div className="flex h-full bg-background">
      {/* Map Area */}
      <div className="flex-1 relative overflow-hidden">
        {(isLoading) && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-50">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        {(placesError || zonesError) && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/90 z-50 p-6">
            <div className="text-center space-y-3">
              <p className="font-mono text-destructive">Failed to load map data.</p>
              <p className="text-xs text-muted-foreground">
                {placesError && `Places: ${placesErrorData instanceof Error ? placesErrorData.message : 'Unknown error'}`}
                {placesError && zonesError ? '\n' : ''}
                {zonesError && `Zones: ${zonesErrorData instanceof Error ? zonesErrorData.message : 'Unknown error'}`}
              </p>
            </div>
          </div>
        )}

        <svg
          ref={svgRef}
          className={`w-full h-full ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
          viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
          preserveAspectRatio="xMidYMid slice"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerLeave}
          onPointerCancel={handlePointerCancel}
          onWheel={handleWheel}
        >
          {/* Background */}
          <rect width={mapDimensions.width} height={mapDimensions.height} fill="#000000" />

          {/* Grid pattern for cyberpunk aesthetic */}
          <defs>
            <pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
              <path
                d="M 50 0 L 0 0 0 50"
                fill="none"
                stroke="#00ff0010"
                strokeWidth="0.5"
              />
            </pattern>
          </defs>
          <rect width={mapDimensions.width} height={mapDimensions.height} fill="url(#grid)" />

          {/* World countries */}
          <g opacity="0.45">
            {worldCountries.map((country) => (
              <path
                key={country.id}
                d={country.pathData!}
                fill="#001a00"
                fillOpacity={0.35}
                stroke="#00ff41"
                strokeOpacity={0.4}
                strokeWidth={1 / zoom}
              />
            ))}
          </g>

          {/* Zone boundaries */}
          <g opacity="0.6">
            {zones.map((zone) => {
              const pathData = geoJsonToSvgPath(zone.boundary);
              if (!pathData) return null;

              return (
                <path
                  key={zone.id}
                  d={pathData}
                  fill="none"
                  stroke="#00ff41"
                  strokeWidth={2 / zoom}
                  strokeDasharray={`${4 / zoom},${4 / zoom}`}
                  data-zone-id={zone.id}
                />
              );
            })}
          </g>

          {/* Places - All pins and labels rendered, visibility controlled by CSS */}
          {visiblePlaces.map((place, index) => {
            const coords = placeCoordinates.get(place.id);
            if (!coords) return null;

            const pinColor = getPinColor(place);
            const labelVisible = labelVisibility.get(place.id) ?? false;

            // Scale sizes inversely with zoom to maintain constant visual size
            const pinRadius = 3 / zoom;
            const ringRadius = 8 / zoom;
            const fontSize = 11 / zoom;
            const labelHeight = 16 / zoom;
            const labelWidth = 80 / zoom;
            const labelOffsetY = 25 / zoom;
            const textOffsetY = 12 / zoom;

            return (
              <g
                key={place.id}
                className="cursor-pointer"
                data-interactive="true"
                onPointerEnter={() => {
                  if (!isDragging) {
                    setHoveredLocation(place.id);
                  }
                }}
                onPointerLeave={() => {
                  if (!isDragging) {
                    setHoveredLocation(null);
                  }
                }}
                onPointerDown={(e) => {
                  e.stopPropagation();
                }}
                onClick={(e) => {
                  if (!isDragging) {
                    e.stopPropagation();
                    setSelectedLocation(place.id);
                    setDetailsDialogOpen(true);
                  }
                }}
                data-testid={`place-${place.id}`}
              >
                {/* Pin circle */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r={pinRadius}
                  fill={pinColor}
                  className="transition-all duration-200"
                  style={{
                    filter: `drop-shadow(0 0 ${8 / zoom}px ${pinColor})`
                  }}
                />

                {/* Outer ring for selected/hovered states */}
                {(selectedLocation === place.id || hoveredLocation === place.id) && (
                  <circle
                    cx={coords.x}
                    cy={coords.y}
                    r={ringRadius}
                    fill="transparent"
                    stroke={pinColor}
                    strokeWidth={1 / zoom}
                    opacity="0.6"
                    className="animate-pulse"
                    style={{
                      filter: `drop-shadow(0 0 ${4 / zoom}px ${pinColor})`
                    }}
                  />
                )}

                {/* Label - always in DOM, visibility controlled by display property */}
                <g style={{ display: labelVisible ? '' : 'none' }}>
                  <rect
                    x={coords.x - labelWidth / 2}
                    y={coords.y - labelOffsetY}
                    width={labelWidth}
                    height={labelHeight}
                    fill="#000000"
                    opacity="0.8"
                    rx={2 / zoom}
                  />
                  <text
                    x={coords.x}
                    y={coords.y - textOffsetY}
                    fill={pinColor}
                    fontSize={fontSize}
                    textAnchor="middle"
                    className="font-mono transition-all duration-200"
                    style={{
                      userSelect: "none",
                      filter: `drop-shadow(0 0 ${2 / zoom}px ${pinColor})`
                    }}
                  >
                    {place.name}
                  </text>
                </g>
              </g>
            );
          })}

          {/* Empty state message */}
          {!isLoading && visiblePlaces.length === 0 && (
            <text
              x="50%"
              y="50%"
              textAnchor="middle"
              fill="#00ff0080"
              fontSize="14"
              className="font-mono"
            >
              [NO LOCATION DATA AVAILABLE]
            </text>
          )}
        </svg>

        {/* Legend and Controls */}
        <div className="absolute bottom-4 left-4 bg-card/90 border border-border p-3 rounded-md font-mono text-xs">
          <div className="text-primary mb-2">[MAP CONTROLS]</div>
          <div className="space-y-1 text-muted-foreground">
            <div>Drag to pan • Scroll to zoom</div>
            <div>Click location to select</div>
            <div className="mt-2 flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: "#00ff41" }} />
                <span>Default</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: "#ffff00" }} />
                <span>Current</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: "#00ffff" }} />
                <span>Selected</span>
              </div>
            </div>
          </div>
        </div>

        {/* Zoom indicator */}
        <div className="absolute top-4 left-4 bg-card/90 border border-border px-3 py-2 rounded-md font-mono text-xs">
          <div className="text-muted-foreground">
            ZOOM: {zoom >= 10 ? zoom.toFixed(1) : zoom.toFixed(2)}×
          </div>
        </div>
      </div>

      {/* Location Index Sidebar */}
      <div className="w-80 bg-card border-l border-border flex flex-col">
        <div className="p-4 border-b border-border">
          <h3 className="text-sm font-mono text-primary flex items-center gap-2">
            <MapPin className="h-4 w-4" />
            LOCATION INDEX
          </h3>
          <div className="text-xs text-foreground mt-1">
            {visiblePlaces.length} locations across {Object.keys(placesByZone).length} zones
          </div>
        </div>
        
        <ScrollArea className="flex-1">
          <div className="p-4 space-y-2">
            {Object.entries(placesByZone)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([zoneId, zonePlaces]) => {
                const zone = zones.find(z => z.id === Number(zoneId));
                const isExpanded = expandedZones.has(Number(zoneId));
                
                return (
                  <div key={zoneId} className="border border-border rounded-md overflow-hidden">
                    <Button
                      variant="ghost"
                      className="w-full justify-start p-3 hover-elevate text-foreground"
                      onClick={() => toggleZoneExpansion(Number(zoneId))}
                      data-testid={`button-zone-${zoneId}`}
                    >
                      <div className="flex items-center justify-between w-full">
                        <div className="flex items-center gap-2">
                          {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                          <span className="text-xs font-mono">
                            {zone?.name || `Zone ${zoneId}`}
                          </span>
                        </div>
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          {zonePlaces.length}
                        </Badge>
                      </div>
                    </Button>
                    
                    {isExpanded && (
                      <div className="border-t border-border">
                        {zonePlaces.map(place => {
                          const isSelected = selectedLocation === place.id;
                          const isCurrent = currentChunkLocation === place.name;
                          
                          return (
                            <Button
                              key={place.id}
                              variant="ghost"
                              className={`w-full justify-start px-6 py-2 text-xs font-mono hover-elevate text-foreground ${
                                isSelected ? 'bg-accent' : ''
                              } ${isCurrent ? 'text-yellow-400' : ''}`}
                              onClick={() => {
                                setSelectedLocation(place.id);
                                setDetailsDialogOpen(true);
                                // Pan to location if it has coordinates
                                const coords = getPlaceCoordinates(place);
                                if (coords) {
                                  setViewBox({
                                    x: coords.x - mapDimensions.width / (2 * zoom),
                                    y: coords.y - mapDimensions.height / (2 * zoom),
                                    width: mapDimensions.width / zoom,
                                    height: mapDimensions.height / zoom
                                  });
                                }
                              }}
                              onMouseEnter={() => setHoveredLocation(place.id)}
                              onMouseLeave={() => setHoveredLocation(null)}
                              data-testid={`button-location-${place.id}`}
                            >
                              <div className="flex items-center gap-2 w-full">
                                <div 
                                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                                  style={{ 
                                    background: isCurrent ? "#ffff00" : (isSelected ? "#00ffff" : "#00ff41"),
                                    boxShadow: `0 0 4px ${isCurrent ? "#ffff00" : (isSelected ? "#00ffff" : "#00ff41")}`
                                  }}
                                />
                                <span className="truncate text-left">
                                  {place.name}
                                </span>
                                {place.type && (
                                  <span className="text-[10px] text-foreground/70 ml-auto">
                                    {place.type}
                                  </span>
                                )}
                              </div>
                            </Button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        </ScrollArea>
      </div>

      {/* Place Details Dialog */}
      <Dialog open={detailsDialogOpen} onOpenChange={setDetailsDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-mono text-primary">
              {selectedLocation ? places.find(p => p.id === selectedLocation)?.name : 'Location Details'}
            </DialogTitle>
          </DialogHeader>
          {selectedLocation && (() => {
            const place = places.find(p => p.id === selectedLocation);
            if (!place) return null;

            const zone = zones.find(z => z.id === place.zoneId);
            const coords = extractCoordinates(place);
            const historyParagraphs = toParagraphs(place.history);
            const statusParagraphs = toParagraphs(place.currentStatus);
            const secretsParagraphs = toParagraphs(place.secrets);
            const inhabitantsList = parseInhabitants(place.inhabitants);

            return (
              <ScrollArea className="max-h-[60vh]">
                <div className="space-y-4 font-mono text-sm pr-4">
                  {place.type && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Type</div>
                      <div className="text-foreground">{place.type}</div>
                    </div>
                  )}

                  {zone && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Zone</div>
                      <div className="text-foreground">{zone.name}</div>
                    </div>
                  )}

                  {coords && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Coordinates</div>
                      <div className="text-foreground">
                        {coords.latitude.toFixed(6)}, {coords.longitude.toFixed(6)}
                      </div>
                    </div>
                  )}

                  {place.summary && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Summary</div>
                      <div className="text-foreground whitespace-pre-wrap leading-relaxed">{place.summary}</div>
                    </div>
                  )}

                  {historyParagraphs.length > 0 && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">History</div>
                      <div className="space-y-3 text-foreground whitespace-pre-wrap leading-relaxed">
                        {historyParagraphs.map((paragraph, index) => (
                          <p key={`history-${index}`}>{paragraph}</p>
                        ))}
                      </div>
                    </div>
                  )}

                  {statusParagraphs.length > 0 && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Current Status</div>
                      <div className="space-y-3 text-foreground whitespace-pre-wrap leading-relaxed">
                        {statusParagraphs.map((paragraph, index) => (
                          <p key={`status-${index}`}>{paragraph}</p>
                        ))}
                      </div>
                    </div>
                  )}

                  {inhabitantsList.length > 0 && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Inhabitants</div>
                      <ul className="list-disc pl-4 space-y-1 text-foreground whitespace-pre-wrap">
                        {inhabitantsList.map((name, index) => (
                          <li key={`inhabitant-${index}`}>{name}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {secretsParagraphs.length > 0 && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Secrets</div>
                      <div className="space-y-3 text-foreground italic whitespace-pre-wrap leading-relaxed">
                        {secretsParagraphs.map((paragraph, index) => (
                          <p key={`secret-${index}`}>{paragraph}</p>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </ScrollArea>
            );
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
}
