import { useState, useRef, useEffect, useMemo, useId } from "react";
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
import { WORLD_OUTLINES } from "@/lib/world-outline";

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
  const [mapDimensions, setMapDimensions] = useState({ width: 800, height: 600 });
  const [mapBounds, setMapBounds] = useState<{ minLng: number; maxLng: number; minLat: number; maxLat: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const dragHasMovedRef = useRef(false);
  const dragOriginRef = useRef({ x: 0, y: 0 });
  const [viewBox, setViewBox] = useState({ x: 0, y: 0, width: 800, height: 600 });
  const [zoom, setZoom] = useState(1);
  const maskId = useId();

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
        setMapDimensions({ width, height });
        setViewBox({ x: 0, y: 0, width, height });
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
      const lngRange = maxLng - minLng;
      const latRange = maxLat - minLat;
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
    
    const x = ((lng - bounds.minLng) / (bounds.maxLng - bounds.minLng)) * mapDimensions.width;
    const y = mapDimensions.height - ((lat - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * mapDimensions.height;
    
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

  // Handle mouse events for drag
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) {
      return;
    }

    dragHasMovedRef.current = false;
    dragOriginRef.current = { x: e.clientX, y: e.clientY };
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      const scaleX = mapDimensions.width > 0 ? viewBox.width / mapDimensions.width : 1;
      const scaleY = mapDimensions.height > 0 ? viewBox.height / mapDimensions.height : 1;
      const dx = (e.clientX - dragStart.x) * scaleX;
      const dy = (e.clientY - dragStart.y) * scaleY;

      setViewBox(prev => clampViewBox({
        ...prev,
        x: prev.x - dx,
        y: prev.y - dy
      }));
      setDragStart({ x: e.clientX, y: e.clientY });

      if (!dragHasMovedRef.current) {
        const movedDistance = Math.abs(e.clientX - dragOriginRef.current.x) + Math.abs(e.clientY - dragOriginRef.current.y);
        if (movedDistance > 3) {
          dragHasMovedRef.current = true;
        }
      }
    }
  };

  const handleMouseUp = () => {
    if (isDragging) {
      setIsDragging(false);
      setTimeout(() => {
        dragHasMovedRef.current = false;
      }, 0);
    }
  };

  const handleMouseLeave = () => {
    if (isDragging) {
      setIsDragging(false);
      dragHasMovedRef.current = false;
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.min(Math.max(zoom * factor, 0.25), 100);

    // Zoom towards mouse position
    const rect = svgRef.current?.getBoundingClientRect();
    if (rect) {
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const svgX = viewBox.x + mouseX * (viewBox.width / rect.width);
      const svgY = viewBox.y + mouseY * (viewBox.height / rect.height);
      
      const newWidth = mapDimensions.width / newZoom;
      const newHeight = mapDimensions.height / newZoom;

      setViewBox(prev => clampViewBox({
        ...prev,
        x: svgX - (mouseX / rect.width) * newWidth,
        y: svgY - (mouseY / rect.height) * newHeight,
        width: newWidth,
        height: newHeight
      }));
      setZoom(newZoom);
    }
  };

  const clampViewBox = (next: typeof viewBox) => {
    const minX = Math.min(0, mapDimensions.width - next.width);
    const maxX = Math.max(0, mapDimensions.width - next.width);
    const minY = Math.min(0, mapDimensions.height - next.height);
    const maxY = Math.max(0, mapDimensions.height - next.height);

    const clamp = (value: number, min: number, max: number) => {
      if (value < min) return min;
      if (value > max) return max;
      return value;
    };

    return {
      ...next,
      x: clamp(next.x, minX, maxX),
      y: clamp(next.y, minY, maxY),
    };
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

  // Progressive label display based on zoom and importance
  const labelVisibility = useMemo(() => {
    const visibleLabels = new Set<number>();
    const placedBoxes: Array<{ x1: number; y1: number; x2: number; y2: number }> = [];

    const baseEntries = visiblePlaces
      .map((place, index) => {
        const coords = getPlaceCoordinates(place);
        if (!coords) return null;

        const isFocus = hoveredLocation === place.id || selectedLocation === place.id || (currentChunkLocation && place.name === currentChunkLocation);

        let baseVisible = false;
        if (zoom >= 3) {
          baseVisible = true;
        } else if (zoom >= 2) {
          baseVisible = index % 5 === 0;
        } else if (zoom >= 1.5) {
          baseVisible = index % 10 === 0;
        } else if (zoom >= 1) {
          baseVisible = index % 20 === 0;
        }

        return {
          place,
          coords,
          forceVisible: isFocus,
          baseVisible,
          priority: isFocus ? 0 : index + 1,
        };
      })
      .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry));

    baseEntries.sort((a, b) => a.priority - b.priority);

    const labelWidth = 80 / zoom;
    const labelHeight = 16 / zoom;
    const labelOffsetY = 25 / zoom;

    const intersects = (box: { x1: number; y1: number; x2: number; y2: number }) => {
      return placedBoxes.some(existing => !(
        box.x2 < existing.x1 ||
        box.x1 > existing.x2 ||
        box.y2 < existing.y1 ||
        box.y1 > existing.y2
      ));
    };

    for (const entry of baseEntries) {
      if (!entry.forceVisible && !entry.baseVisible) {
        continue;
      }

      const x1 = entry.coords.x - labelWidth / 2;
      const y1 = entry.coords.y - labelOffsetY;
      const box = {
        x1,
        y1,
        x2: x1 + labelWidth,
        y2: y1 + labelHeight,
      };

      if (!intersects(box) || entry.forceVisible) {
        visibleLabels.add(entry.place.id);
        placedBoxes.push(box);
      }
    }

    return visibleLabels;
  }, [
    visiblePlaces,
    zoom,
    hoveredLocation,
    selectedLocation,
    currentChunkLocation,
    mapBounds,
    mapDimensions.height,
    mapDimensions.width,
  ]);

  const isLabelVisible = (place: Place) => labelVisibility.has(place.id);

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
          className="w-full h-full cursor-move"
          viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
          preserveAspectRatio="xMidYMid slice"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
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
            <mask id={`${maskId}-world-mask`}>
              <rect width={mapDimensions.width} height={mapDimensions.height} fill="black" />
              {WORLD_OUTLINES.map((polygon, index) => {
                if (!polygon.length) return null;
                const pathData = polygon
                  .map(([lng, lat], pointIndex) => {
                    const { x, y } = transformCoordinates(lng, lat);
                    return `${pointIndex === 0 ? "M" : "L"} ${x} ${y}`;
                  })
                  .join(" ") + " Z";

                return (
                  <path key={`mask-${index}`} d={pathData} fill="white" />
                );
              })}
            </mask>
          </defs>
          <rect width={mapDimensions.width} height={mapDimensions.height} fill="url(#grid)" />

          {/* World outline */}
          <g mask={`url(#${maskId}-world-mask)`} opacity="0.35">
            <rect width={mapDimensions.width} height={mapDimensions.height} fill="#00ff1a20" />
          </g>
          <g opacity="0.45">
            {WORLD_OUTLINES.map((polygon, index) => {
              if (!polygon.length) return null;

              const pathData = polygon
                .map(([lng, lat], pointIndex) => {
                  const { x, y } = transformCoordinates(lng, lat);
                  return `${pointIndex === 0 ? "M" : "L"} ${x} ${y}`;
                })
                .join(" ") + " Z";

              return (
                <path
                  key={`outline-${index}`}
                  d={pathData}
                  fill="none"
                  stroke="#00ff41"
                  strokeWidth={1.5 / zoom}
                  strokeOpacity={0.4}
                />
              );
            })}
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
            const coords = getPlaceCoordinates(place);
            if (!coords) return null;

            const pinColor = getPinColor(place);
            const labelVisible = isLabelVisible(place);

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
                onMouseEnter={() => {
                  if (!isDragging) {
                    setHoveredLocation(place.id);
                  }
                }}
                onMouseLeave={() => {
                  if (!isDragging) {
                    setHoveredLocation(null);
                  }
                }}
                onClick={(e) => {
                  if (!dragHasMovedRef.current) {
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
            ZOOM: {Math.round(zoom * 100)}%
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
