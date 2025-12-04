import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MapPin, Loader2, ChevronRight, ChevronDown, Upload, Image as ImageIcon } from "lucide-react";
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
import { ImageGalleryModal, type ImageData } from "@/components/ImageGalleryModal";
import { worldOutline } from "@/lib/world-outline";
import { useGeoProjection } from "@/hooks/useGeoProjection";
import { useTheme } from "@/contexts/ThemeContext";

// Theme-aware color palettes for the map
const MAP_COLORS = {
  cyberpunk: {
    default: "#00ff41",      // Matrix green
    hover: "#00ff80",        // Brighter green
    selected: "#00ffff",     // Cyan
    current: "#ffff00",      // Yellow
    grid: "#00ff0010",       // Faint green grid
    landFill: "#001a00",     // Dark green land
    landStroke: "#00ff41",   // Green border
  },
  gilded: {
    default: "#c9a227",      // Brass gold
    hover: "#e6b82e",        // Brighter gold
    selected: "#f5d442",     // Bright gold
    current: "#ff6b35",      // Warm orange for current
    grid: "#c9a22710",       // Faint brass grid
    landFill: "#1a1408",     // Dark sepia land
    landStroke: "#c9a227",   // Brass border
  },
} as const;

interface MapTabProps {
  currentChunkLocation?: string | null;
  slot?: number | null;
}

type MultiPolygonGeometry = typeof worldOutline.features[number]["geometry"];

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

export function MapTab({ currentChunkLocation = null, slot = null }: MapTabProps) {
  // Theme-aware colors
  const { isCyberpunk } = useTheme();
  const colors = isCyberpunk ? MAP_COLORS.cyberpunk : MAP_COLORS.gilded;

  // State management for location interactions
  const [hoveredLocation, setHoveredLocation] = useState<number | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<number | null>(null);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
  const [galleryOpen, setGalleryOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

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

  // D3.js geo projection for proper date-line handling and alternate geography support
  const { transformCoordinates, geoJsonToSvgPath } = useGeoProjection({
    mapDimensions,
    mapBounds,
  });

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
    queryKey: ["/api/places", slot],
    queryFn: async () => {
      const res = await fetch(`/api/places${slot ? `?slot=${slot}` : ""}`);
      if (!res.ok) throw new Error("Failed to fetch places");
      return res.json();
    },
  });

  // Fetch zones
  const {
    data: zones = [],
    isLoading: zonesLoading,
    isError: zonesError,
    error: zonesErrorData,
  } = useQuery<Zone[]>({
    queryKey: ["/api/zones", slot],
    queryFn: async () => {
      const res = await fetch(`/api/zones${slot ? `?slot=${slot}` : ""}`);
      if (!res.ok) throw new Error("Failed to fetch zones");
      return res.json();
    },
  });

  // Fetch place images
  const {
    data: placeImages = [],
  } = useQuery<ImageData[]>({
    queryKey: ["/api/places", selectedLocation, "images", slot],
    queryFn: async () => {
      if (!selectedLocation) return [];
      const res = await fetch(`/api/places/${selectedLocation}/images${slot ? `?slot=${slot}` : ""}`);
      if (!res.ok) {
        throw new Error("Failed to load images");
      }
      return res.json();
    },
    enabled: !!selectedLocation,
  });

  const uploadImagesMutation = useMutation({
    mutationFn: async (files: FileList) => {
      if (!selectedLocation) throw new Error("No place selected");
      const formData = new FormData();
      Array.from(files).forEach((file) => formData.append("images", file));

      const response = await fetch(`/api/places/${selectedLocation}/images${slot ? `?slot=${slot}` : ""}`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to upload images");
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/places", selectedLocation, "images"] });
    },
  });

  const setMainImageMutation = useMutation({
    mutationFn: async (imageId: number) => {
      if (!selectedLocation) throw new Error("No place selected");
      const response = await fetch(`/api/places/${selectedLocation}/images/${imageId}/main${slot ? `?slot=${slot}` : ""}`, {
        method: "PUT",
      });
      if (!response.ok) {
        throw new Error("Failed to set main image");
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/places", selectedLocation, "images"] });
    },
  });

  const deleteImageMutation = useMutation({
    mutationFn: async (imageId: number) => {
      if (!selectedLocation) throw new Error("No place selected");
      const response = await fetch(`/api/places/${selectedLocation}/images/${imageId}${slot ? `?slot=${slot}` : ""}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error("Failed to delete image");
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/places", selectedLocation, "images"] });
    },
  });

  const handleQuickUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      await uploadImagesMutation.mutateAsync(files);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } finally {
      setUploading(false);
    }
  };

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
    // Parse GeoJSON geometry from PostGIS
    if (!place.geometry) return null;

    try {
      // Validate geometry structure
      if (typeof place.geometry !== 'object' || !place.geometry.type) {
        console.warn(`Place ${place.id} has invalid geometry structure`);
        return null;
      }

      switch (place.geometry.type) {
        case 'Point': {
          // GeoJSON Point format: [longitude, latitude]
          if (!Array.isArray(place.geometry.coordinates) || place.geometry.coordinates.length < 2) {
            console.warn(`Place ${place.id} has invalid Point coordinates`);
            return null;
          }

          const [lng, lat] = place.geometry.coordinates;

          // Validate that coordinates are finite numbers
          if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
            console.warn(`Place ${place.id} has non-finite coordinates: [${lng}, ${lat}]`);
            return null;
          }

          // Validate coordinate ranges (lat: -90 to 90, lng: -180 to 180)
          if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
            console.warn(`Place ${place.id} has out-of-range coordinates: [${lng}, ${lat}]`);
            return null;
          }

          return { latitude: lat, longitude: lng };
        }

        case 'Polygon': {
          // Future: calculate centroid for polygon boundaries
          // For now, return null to not display pin
          return null;
        }

        case 'LineString': {
          // Future: use midpoint or start point for routes/paths
          return null;
        }

        default:
          console.warn(`Place ${place.id} has unsupported geometry type: ${place.geometry.type}`);
          return null;
      }
    } catch (error) {
      console.error(`Failed to parse geometry for place ${place.id}:`, error, place.geometry);
      return null;
    }
  };

  // Calculate bounds from place data, but ensure full world is visible
  useEffect(() => {
    if (!places.length) {
      // No places, show entire world
      setMapBounds({
        minLng: -180,
        maxLng: 180,
        minLat: -90,
        maxLat: 90
      });
      return;
    }

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

    if (minLng !== Infinity && maxLng !== -Infinity) {
      const lngRange = Math.max(maxLng - minLng, 0.0001);
      const latRange = Math.max(maxLat - minLat, 0.0001);
      const padding = 0.1;

      // Expand to show full world extent
      const bounds = {
        minLng: Math.min(-180, minLng - lngRange * padding),
        maxLng: Math.max(180, maxLng + lngRange * padding),
        minLat: Math.min(-90, minLat - latRange * padding),
        maxLat: Math.max(90, maxLat + latRange * padding)
      };

      setMapBounds(bounds);
    }
  }, [places]);

  const isLoading = placesLoading || zonesLoading;

  // Get place coordinates - only return valid coordinates, no fallbacks
  const getPlaceCoordinates = (place: Place): { x: number; y: number } | null => {
    const coords = extractCoordinates(place);
    if (coords) {
      return transformCoordinates(coords.longitude, coords.latitude);
    }
    return null;
  };

  const visiblePlaces = places;

  // Group places by zone for the sidebar
  const placesByZone = visiblePlaces.reduce<Record<number, Place[]>>((acc, place) => {
    const zoneId = Number(place.zone ?? (place as any).zoneId ?? 0);
    if (!acc[zoneId]) acc[zoneId] = [];
    acc[zoneId].push(place);
    return acc;
  }, {});

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

  // Determine pin color based on state (uses theme-aware colors)
  const getPinColor = (place: Place) => {
    if (currentChunkLocation && place.name === currentChunkLocation) {
      return colors.current;
    }
    if (selectedLocation === place.id) {
      return colors.selected;
    }
    if (hoveredLocation === place.id) {
      return colors.hover;
    }
    return colors.default;
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
  }, [visiblePlaces, transformCoordinates]);

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

    return worldOutline.features
      .map((feature, index) => {
        const pathData = geoJsonToSvgPath(feature.geometry);
        return {
          id: index,
          pathData,
        };
      })
      // Type guard filter to guarantee non-null pathData for TypeScript
      .filter((country): country is { id: number; pathData: string } =>
        country.pathData !== null
      );
  }, [geoJsonToSvgPath]);

  return (
    <div className="flex h-full min-h-0 w-full bg-background">
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

          {/* Grid pattern - theme-aware */}
          <defs>
            <pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
              <path
                d="M 50 0 L 0 0 0 50"
                fill="none"
                stroke={colors.grid}
                strokeWidth="0.5"
              />
            </pattern>
          </defs>
          <rect width={mapDimensions.width} height={mapDimensions.height} fill="url(#grid)" />

          {/* World countries - theme-aware */}
          <g opacity="0.45">
            {worldCountries.map((country) => (
              <path
                key={country.id}
                d={country.pathData}
                fill={colors.landFill}
                fillOpacity={0.35}
                stroke={colors.landStroke}
                strokeOpacity={0.4}
                strokeWidth={1 / zoom}
              />
            ))}
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
              fill={`${colors.default}80`}
              fontSize="14"
              className="font-mono"
            >
              [NO LOCATION DATA AVAILABLE]
            </text>
          )}
        </svg>

        {/* Legend and Controls - theme-aware */}
        <div className="absolute bottom-4 left-4 bg-card/90 border border-border p-3 rounded-md font-mono text-xs">
          <div className="text-primary mb-2">[MAP CONTROLS]</div>
          <div className="space-y-1 text-muted-foreground">
            <div>Drag to pan • Scroll to zoom</div>
            <div>Click location to select</div>
            <div className="mt-2 flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: colors.default }} />
                <span>Default</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: colors.current }} />
                <span>Current</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: colors.selected }} />
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
          <div className="p-4 pr-2 space-y-2">
            {Object.entries(placesByZone)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([zoneId, zonePlaces]) => {
                const zone = zones.find(z => z.id === Number(zoneId));
                const isExpanded = expandedZones.has(Number(zoneId));

                return (
                  <div key={zoneId} className="border border-border rounded-md overflow-hidden mr-2">
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
                              className={`w-full justify-start px-6 py-2 text-xs font-mono hover-elevate text-foreground ${isSelected ? 'bg-accent' : ''
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
                              <div className="flex items-start gap-2 w-full">
                                <div
                                  className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1"
                                  style={{
                                    background: isCurrent ? colors.current : (isSelected ? colors.selected : colors.default),
                                    boxShadow: `0 0 4px ${isCurrent ? colors.current : (isSelected ? colors.selected : colors.default)}`
                                  }}
                                />
                                <span className="text-left flex-1 break-words">
                                  {place.name}
                                </span>
                                {place.type === 'vehicle' && (
                                  <span className="text-[10px] text-foreground/70 ml-auto flex-shrink-0">
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
        <DialogContent className="sm:max-w-3xl max-h-[85vh] p-0">
          {selectedLocation && (() => {
            const place = places.find(p => p.id === selectedLocation);
            if (!place) return null;

            const zone = zones.find(z => z.id === Number(place.zone ?? (place as any).zoneId ?? 0));
            const coords = extractCoordinates(place);
            const historyParagraphs = toParagraphs(place.history);
            const statusParagraphs = toParagraphs(place.currentStatus);
            const secretsParagraphs = toParagraphs(place.secrets);
            const inhabitantsList = parseInhabitants(place.inhabitants);
            const mainImage = placeImages.find((img) => img.isMain === 1);

            return (
              <ScrollArea className="max-h-[85vh]">
                <div className="p-6">
                  {/* Header with thumbnail */}
                  <div className="flex items-start gap-4 mb-6">
                    <div className="flex-shrink-0">
                      <button
                        onClick={() => setGalleryOpen(true)}
                        className="w-32 max-h-40 rounded-md overflow-hidden border border-border bg-muted/40 flex items-center justify-center hover:border-primary/50 transition-colors cursor-pointer group"
                      >
                        {mainImage ? (
                          <img
                            src={mainImage.filePath}
                            alt={place.name}
                            className="max-w-full max-h-40 object-contain group-hover:opacity-80 transition-opacity"
                          />
                        ) : (
                          <div className="w-32 h-32 flex items-center justify-center text-muted-foreground/60 group-hover:text-muted-foreground">
                            <MapPin className="h-8 w-8" />
                          </div>
                        )}
                      </button>
                      <div className="mt-2 flex gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => fileInputRef.current?.click()}
                          disabled={uploading}
                          className="font-mono text-xs px-2 py-1 h-auto"
                        >
                          {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setGalleryOpen(true)}
                          className="font-mono text-xs px-2 py-1 h-auto"
                        >
                          <ImageIcon className="h-3 w-3" />
                        </Button>
                      </div>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/png,image/jpeg,image/jpg"
                        multiple
                        onChange={handleQuickUpload}
                        className="hidden"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h2 className="text-lg font-mono text-primary terminal-glow">
                        {place.name}
                      </h2>
                      <p className="text-xs text-muted-foreground mt-1">ID: {place.id}</p>
                    </div>
                  </div>

                  {/* Details section */}
                  <div className="space-y-4 font-serif text-sm">
                    {place.type && (
                      <div>
                        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">Type</div>
                        <div className="text-foreground">{place.type}</div>
                      </div>
                    )}

                    {zone && (
                      <div>
                        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">Zone</div>
                        <div className="text-foreground">{zone.name}</div>
                      </div>
                    )}

                    {coords && (
                      <div>
                        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">Coordinates</div>
                        <div className="text-foreground">
                          {coords.latitude.toFixed(6)}, {coords.longitude.toFixed(6)}
                        </div>
                      </div>
                    )}

                    {place.summary && (
                      <div>
                        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">Summary</div>
                        <div className="text-foreground whitespace-pre-wrap leading-relaxed">{place.summary}</div>
                      </div>
                    )}

                    {historyParagraphs.length > 0 && (
                      <div>
                        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">History</div>
                        <div className="space-y-3 text-foreground whitespace-pre-wrap leading-relaxed">
                          {historyParagraphs.map((paragraph, index) => (
                            <p key={`history-${index}`}>{paragraph}</p>
                          ))}
                        </div>
                      </div>
                    )}

                    {statusParagraphs.length > 0 && (
                      <div>
                        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">Current Status</div>
                        <div className="space-y-3 text-foreground whitespace-pre-wrap leading-relaxed">
                          {statusParagraphs.map((paragraph, index) => (
                            <p key={`status-${index}`}>{paragraph}</p>
                          ))}
                        </div>
                      </div>
                    )}

                    {inhabitantsList.length > 0 && (
                      <div>
                        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">Inhabitants</div>
                        <ul className="list-disc pl-4 space-y-1 text-foreground whitespace-pre-wrap">
                          {inhabitantsList.map((name, index) => (
                            <li key={`inhabitant-${index}`}>{name}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {secretsParagraphs.length > 0 && (
                      <div>
                        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-1">Secrets</div>
                        <div className="space-y-3 text-foreground italic whitespace-pre-wrap leading-relaxed">
                          {secretsParagraphs.map((paragraph, index) => (
                            <p key={`secret-${index}`}>{paragraph}</p>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </ScrollArea>
            );
          })()}
        </DialogContent>
      </Dialog>

      {/* Place Image Gallery */}
      {selectedLocation && (
        <ImageGalleryModal
          open={galleryOpen}
          onOpenChange={setGalleryOpen}
          images={placeImages}
          entityId={selectedLocation}
          entityType="place"
          onUpload={async (files) => {
            await uploadImagesMutation.mutateAsync(files);
          }}
          onSetMain={async (imageId) => {
            await setMainImageMutation.mutateAsync(imageId);
          }}
          onDelete={async (imageId) => {
            await deleteImageMutation.mutateAsync(imageId);
          }}
        />
      )}
    </div>
  );
}
