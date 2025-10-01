import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { MapPin, Loader2, ChevronRight, ChevronDown } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Place, Zone } from "@shared/schema";

interface MapTabProps {
  currentChunkLocation?: string | null;
}

export function MapTab({ currentChunkLocation = null }: MapTabProps) {
  // State management for location interactions
  const [hoveredLocation, setHoveredLocation] = useState<number | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<number | null>(null);
  
  // Debug: Log when selectedLocation changes
  useEffect(() => {
    console.log('[MapTab] selectedLocation changed to:', selectedLocation);
  }, [selectedLocation]);
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
  const { data: places = [], isLoading: placesLoading } = useQuery<Place[]>({
    queryKey: ["/api/places"],
  });

  // Fetch zones
  const { data: zones = [], isLoading: zonesLoading } = useQuery<Zone[]>({
    queryKey: ["/api/zones"],
  });
  
  // Debug: Log when places data is loaded
  useEffect(() => {
    if (places.length > 0) {
      console.log(`[MapTab] Loaded ${places.length} places`);
    }
  }, [places]);

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

  // Calculate bounds from place data only (zones not needed for display)
  useEffect(() => {
    if (!places.length) return;

    let minLng = Infinity;
    let maxLng = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;

    // Extract coordinates from places only
    places.forEach(place => {
      if (place.longitude && place.latitude) {
        const lng = parseFloat(place.longitude);
        const lat = parseFloat(place.latitude);
        if (!isNaN(lng) && !isNaN(lat)) {
          minLng = Math.min(minLng, lng);
          maxLng = Math.max(maxLng, lng);
          minLat = Math.min(minLat, lat);
          maxLat = Math.max(maxLat, lat);
        }
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

  // Get place coordinates
  const getPlaceCoordinates = (place: Place): { x: number; y: number } | null => {
    if (place.longitude && place.latitude) {
      const lng = parseFloat(place.longitude);
      const lat = parseFloat(place.latitude);
      if (!isNaN(lng) && !isNaN(lat)) {
        return transformCoordinates(lng, lat);
      }
    }
    return null;
  };

  // Filter places with valid coordinates
  const visiblePlaces = places.filter(place => place.longitude && place.latitude);

  // Group places by zone for the sidebar
  const placesByZone = visiblePlaces.reduce((acc, place) => {
    const zoneId = place.zoneId || 0;
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
    // Only start dragging on the background, not on interactive elements
    if (e.button === 0 && e.target === e.currentTarget) { // Left click only on SVG itself
      console.log('[MapTab] Starting drag');
      setIsDragging(true);
      setDragStart({ x: e.clientX, y: e.clientY });
    }
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
      console.log('[MapTab] Ending drag');
      setIsDragging(false);
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.min(Math.max(zoom * delta, 0.5), 5);
    
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

  // Check if label should be visible
  const isLabelVisible = (place: Place) => {
    return hoveredLocation === place.id || 
           selectedLocation === place.id || 
           (currentChunkLocation && place.name === currentChunkLocation);
  };

  return (
    <div className="flex h-full bg-background">
      {/* Map Area */}
      <div className="flex-1 relative overflow-hidden">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-50">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
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

          {/* Minimal landmass outlines (simplified boundaries) */}
          <g opacity="0.2">
            <path
              d="M 100 300 Q 200 250 300 280 T 500 320 Q 600 340 700 330"
              fill="none"
              stroke="#00ff41"
              strokeWidth="0.5"
              strokeDasharray="2,4"
            />
            <path
              d="M 150 400 Q 250 380 350 390 T 550 410"
              fill="none"
              stroke="#00ff41"
              strokeWidth="0.5"
              strokeDasharray="2,4"
            />
          </g>

          {/* Places - All pins and labels rendered, visibility controlled by CSS */}
          {visiblePlaces.map((place) => {
            const coords = getPlaceCoordinates(place);
            if (!coords) return null;

            const pinColor = getPinColor(place);
            const labelVisible = isLabelVisible(place);

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
                  if (!isDragging) {
                    e.stopPropagation();
                    console.log(`[MapTab] Clicked location ${place.id}: ${place.name}`);
                    setSelectedLocation(place.id);
                    console.log(`[MapTab] Selected location set to ${place.id}`);
                  }
                }}
                data-testid={`place-${place.id}`}
              >
                {/* Pin circle */}
                <circle
                  cx={coords.x}
                  cy={coords.y}
                  r="3"
                  fill={pinColor}
                  className="transition-all duration-200"
                  style={{
                    filter: `drop-shadow(0 0 8px ${pinColor})`
                  }}
                />
                
                {/* Outer ring for selected/hovered states */}
                {(selectedLocation === place.id || hoveredLocation === place.id) && (
                  <circle
                    cx={coords.x}
                    cy={coords.y}
                    r="8"
                    fill="transparent"
                    stroke={pinColor}
                    strokeWidth="1"
                    opacity="0.6"
                    className="animate-pulse"
                    style={{
                      filter: `drop-shadow(0 0 4px ${pinColor})`
                    }}
                  />
                )}
                
                {/* Label - always in DOM, visibility controlled by display property */}
                <g style={{ display: labelVisible ? '' : 'none' }}>
                  <rect
                    x={coords.x - 40}
                    y={coords.y - 25}
                    width="80"
                    height="16"
                    fill="#000000"
                    opacity="0.8"
                    rx="2"
                  />
                  <text
                    x={coords.x}
                    y={coords.y - 12}
                    fill={pinColor}
                    fontSize="11"
                    textAnchor="middle"
                    className="font-mono transition-all duration-200"
                    style={{ 
                      userSelect: "none",
                      filter: `drop-shadow(0 0 2px ${pinColor})`
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
          <div className="text-xs text-muted-foreground mt-1">
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
                      className="w-full justify-start p-3 hover-elevate"
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
                              className={`w-full justify-start px-6 py-2 text-xs font-mono hover-elevate ${
                                isSelected ? 'bg-accent' : ''
                              } ${isCurrent ? 'text-yellow-400' : ''}`}
                              onClick={() => {
                                setSelectedLocation(place.id);
                                // Optionally pan to location
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
                                  <span className="text-[10px] text-muted-foreground ml-auto">
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
    </div>
  );
}