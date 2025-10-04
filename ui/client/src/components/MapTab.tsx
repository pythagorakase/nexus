import { useState, useRef, useEffect, useMemo } from "react";
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

type WorldFeature = {
  name: string;
  polygons: ReadonlyArray<ReadonlyArray<[number, number]>>;
};

const WORLD_MAP_OUTLINES: ReadonlyArray<WorldFeature> = [
  {
    name: "North America",
    polygons: [
      [
        [-168, 72],
        [-153, 70],
        [-140, 65],
        [-132, 58],
        [-125, 52],
        [-115, 49],
        [-105, 50],
        [-95, 52],
        [-85, 50],
        [-78, 44],
        [-74, 38],
        [-83, 30],
        [-95, 23],
        [-108, 23],
        [-120, 27],
        [-128, 33],
        [-135, 42],
        [-145, 54],
        [-158, 63],
        [-168, 72],
      ],
    ],
  },
  {
    name: "Greenland",
    polygons: [
      [
        [-55, 83],
        [-47, 82],
        [-38, 78],
        [-32, 72],
        [-38, 65],
        [-45, 61],
        [-53, 68],
        [-55, 83],
      ],
    ],
  },
  {
    name: "South America",
    polygons: [
      [
        [-82, 12],
        [-74, 7],
        [-68, 0],
        [-64, -10],
        [-66, -20],
        [-72, -32],
        [-70, -46],
        [-60, -52],
        [-50, -55],
        [-45, -50],
        [-48, -30],
        [-56, -10],
        [-65, 0],
        [-70, 6],
        [-82, 12],
      ],
    ],
  },
  {
    name: "Europe",
    polygons: [
      [
        [-10, 71],
        [0, 72],
        [20, 70],
        [35, 66],
        [40, 60],
        [32, 50],
        [22, 44],
        [15, 40],
        [5, 36],
        [-5, 42],
        [-10, 55],
        [-10, 71],
      ],
      [
        [-8, 58],
        [-2, 58],
        [0, 55],
        [-3, 51],
        [-8, 52],
        [-8, 58],
      ],
      [
        [5, 60],
        [12, 63],
        [20, 64],
        [25, 60],
        [20, 57],
        [12, 57],
        [5, 60],
      ],
    ],
  },
  {
    name: "Africa",
    polygons: [
      [
        [-18, 35],
        [0, 37],
        [15, 34],
        [28, 32],
        [35, 24],
        [40, 10],
        [42, -5],
        [36, -15],
        [30, -25],
        [20, -33],
        [10, -35],
        [0, -30],
        [-10, -25],
        [-15, -10],
        [-18, 10],
        [-18, 35],
      ],
      [
        [45, -12],
        [50, -12],
        [50, -17],
        [45, -22],
        [42, -18],
        [45, -12],
      ],
    ],
  },
  {
    name: "Middle East & Central Asia",
    polygons: [
      [
        [30, 40],
        [40, 45],
        [55, 45],
        [65, 40],
        [70, 35],
        [65, 30],
        [55, 25],
        [45, 25],
        [35, 30],
        [30, 35],
        [30, 40],
      ],
    ],
  },
  {
    name: "Asia",
    polygons: [
      [
        [40, 75],
        [55, 78],
        [80, 76],
        [100, 70],
        [115, 65],
        [130, 58],
        [145, 52],
        [155, 45],
        [155, 35],
        [145, 30],
        [135, 20],
        [145, 15],
        [155, 10],
        [150, 5],
        [135, 5],
        [120, 10],
        [108, 5],
        [100, 10],
        [90, 5],
        [80, 10],
        [75, 18],
        [70, 28],
        [60, 35],
        [50, 45],
        [45, 55],
        [40, 65],
        [40, 75],
      ],
      [
        [128, 36],
        [135, 38],
        [142, 38],
        [142, 32],
        [135, 32],
        [128, 36],
      ],
      [
        [139, 46],
        [145, 46],
        [150, 43],
        [148, 38],
        [142, 38],
        [139, 46],
      ],
    ],
  },
  {
    name: "Southeast Asia",
    polygons: [
      [
        [95, 25],
        [105, 20],
        [110, 15],
        [105, 5],
        [98, 0],
        [92, 10],
        [95, 25],
      ],
      [
        [110, 5],
        [120, 8],
        [126, 5],
        [122, -2],
        [114, -4],
        [110, 5],
      ],
      [
        [120, -5],
        [130, -2],
        [135, -8],
        [128, -12],
        [118, -10],
        [120, -5],
      ],
    ],
  },
  {
    name: "Australia",
    polygons: [
      [
        [110, -10],
        [130, -12],
        [145, -18],
        [150, -28],
        [145, -38],
        [130, -42],
        [118, -38],
        [112, -28],
        [110, -10],
      ],
    ],
  },
  {
    name: "New Zealand",
    polygons: [
      [
        [165, -34],
        [175, -36],
        [175, -45],
        [167, -47],
        [165, -34],
      ],
      [
        [170, -45],
        [178, -47],
        [178, -52],
        [170, -52],
        [170, -45],
      ],
    ],
  },
  {
    name: "Antarctica",
    polygons: [
      [
        [-180, -70],
        [-120, -72],
        [-60, -74],
        [0, -78],
        [60, -74],
        [120, -72],
        [180, -70],
        [180, -82],
        [120, -84],
        [60, -86],
        [0, -88],
        [-60, -86],
        [-120, -84],
        [-180, -82],
        [-180, -70],
      ],
    ],
  },
];

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
  const [viewBox, setViewBox] = useState({ x: 0, y: 0, width: 800, height: 600 });
  const [zoom, setZoom] = useState(1);

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

  useEffect(() => {
    const handleGlobalMouseUp = () => {
      setIsDragging(false);
    };

    window.addEventListener("mouseup", handleGlobalMouseUp);
    window.addEventListener("mouseleave", handleGlobalMouseUp);
    return () => {
      window.removeEventListener("mouseup", handleGlobalMouseUp);
      window.removeEventListener("mouseleave", handleGlobalMouseUp);
    };
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

  const placeOrder = useMemo(() => {
    return new Map(visiblePlaces.map((place, index) => [place.id, index]));
  }, [visiblePlaces]);

  const placesForRendering = useMemo(() => {
    const priorityForPlace = (place: Place) => {
      if (currentChunkLocation && place.name === currentChunkLocation) {
        return 3;
      }
      if (selectedLocation === place.id) {
        return 2;
      }
      if (hoveredLocation === place.id) {
        return 1;
      }
      return 0;
    };

    return [...visiblePlaces].sort((a, b) => {
      const priorityDiff = priorityForPlace(b) - priorityForPlace(a);
      if (priorityDiff !== 0) {
        return priorityDiff;
      }

      const indexA = placeOrder.get(a.id) ?? 0;
      const indexB = placeOrder.get(b.id) ?? 0;
      if (indexA !== indexB) {
        return indexA - indexB;
      }

      return a.id - b.id;
    });
  }, [visiblePlaces, hoveredLocation, selectedLocation, currentChunkLocation, placeOrder]);

  const placedLabelBoxes: { x1: number; y1: number; x2: number; y2: number }[] = [];

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
    if (e.button !== 0) return;

    const target = e.target as HTMLElement | null;
    if (target?.closest('[data-interactive="true"]')) {
      return;
    }

    e.preventDefault();
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      const dx = (e.clientX - dragStart.x) * (1 / zoom);
      const dy = (e.clientY - dragStart.y) * (1 / zoom);
      setViewBox(prev => ({
        ...prev,
        x: prev.x - dx,
        y: prev.y - dy
      }));
      setDragStart({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseUp = () => {
    if (isDragging) {
      setIsDragging(false);
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.min(Math.max(zoom * delta, 0.25), 100);
    
    // Zoom towards mouse position
    const rect = svgRef.current?.getBoundingClientRect();
    if (rect) {
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const svgX = viewBox.x + mouseX * (viewBox.width / rect.width);
      const svgY = viewBox.y + mouseY * (viewBox.height / rect.height);
      
      const newWidth = mapDimensions.width / newZoom;
      const newHeight = mapDimensions.height / newZoom;
      
      setViewBox({
        x: svgX - (mouseX / rect.width) * newWidth,
        y: svgY - (mouseY / rect.height) * newHeight,
        width: newWidth,
        height: newHeight
      });
      setZoom(newZoom);
    }
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
  const isLabelVisible = (place: Place, index: number) => {
    // Always show for hovered, selected, or current location
    if (hoveredLocation === place.id ||
        selectedLocation === place.id ||
        (currentChunkLocation && place.name === currentChunkLocation)) {
      return true;
    }

    // Progressive reveal based on zoom level
    // At 1.0x zoom: show every 20th place
    // At 2.0x zoom: show every 5th place
    // At 3.0x zoom: show all places
    if (zoom >= 3.0) {
      return true;
    } else if (zoom >= 2.0) {
      return index % 5 === 0;
    } else if (zoom >= 1.5) {
      return index % 10 === 0;
    } else if (zoom >= 1.0) {
      return index % 20 === 0;
    }

    return false;
  };

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
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
        >
          {/* Background */}
          <rect
            width={mapDimensions.width}
            height={mapDimensions.height}
            fill="#000000"
            style={{ pointerEvents: "none" }}
          />

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
          <rect
            width={mapDimensions.width}
            height={mapDimensions.height}
            fill="url(#grid)"
            style={{ pointerEvents: "none" }}
          />

          {/* World outlines */}
          <g
            opacity="0.25"
            stroke="#00ff41"
            strokeWidth={1.2 / zoom}
            fill="none"
            style={{ pointerEvents: "none" }}
          >
            {WORLD_MAP_OUTLINES.map(feature => {
              const pathData = feature.polygons
                .map(polygon =>
                  polygon
                    .map(([lng, lat], index) => {
                      const { x, y } = transformCoordinates(lng, lat);
                      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
                    })
                    .join(" ") + " Z"
                )
                .join(" ");

              if (!pathData) return null;

              return (
                <path
                  key={feature.name}
                  d={pathData}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              );
            })}
          </g>

          {/* Zone boundaries */}
          <g opacity="0.6" style={{ pointerEvents: "none" }}>
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
          {placesForRendering.map((place) => {
            const coords = getPlaceCoordinates(place);
            if (!coords) return null;

            const pinColor = getPinColor(place);
            const originalIndex = placeOrder.get(place.id) ?? 0;
            let labelVisible = isLabelVisible(place, originalIndex);

            // Scale sizes inversely with zoom to maintain constant visual size
            const pinRadius = 3 / zoom;
            const ringRadius = 8 / zoom;
            const fontSize = 11 / zoom;
            const baseLabelWidth = Math.max(96, place.name.length * 8);
            const labelWidth = baseLabelWidth / zoom;
            const labelHeight = 20 / zoom;
            const labelOffsetY = 30 / zoom;
            const textOffsetY = 14 / zoom;

            if (labelVisible) {
              const x1 = coords.x - labelWidth / 2;
              const y1 = coords.y - labelOffsetY;
              const x2 = x1 + labelWidth;
              const y2 = y1 + labelHeight;

              const overlaps = placedLabelBoxes.some(box => {
                return (
                  x1 < box.x2 &&
                  x2 > box.x1 &&
                  y1 < box.y2 &&
                  y2 > box.y1
                );
              });

              if (!overlaps) {
                placedLabelBoxes.push({ x1, y1, x2, y2 });
              } else {
                labelVisible = false;
              }
            }

            return (
              <g
                key={place.id}
                className="cursor-pointer"
                data-interactive="true"
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
