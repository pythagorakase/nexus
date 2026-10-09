import {
  createContext,
  useContext,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { ViewBox } from "@/lib/map-geometry";

export interface MapCenteredOn {
  slot: number | null;
  placeId: number;
  boundsKey: string | null;
}

interface MapViewState {
  mapDimensions: { width: number; height: number };
  setMapDimensions: Dispatch<SetStateAction<{ width: number; height: number }>>;
  viewBox: ViewBox;
  setViewBox: Dispatch<SetStateAction<ViewBox>>;
  selectedId: number | null;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
  expandedZones: Set<number>;
  setExpandedZones: Dispatch<SetStateAction<Set<number>>>;
  centeredOnRef: MutableRefObject<MapCenteredOn | null>;
}

const MapViewContext = createContext<MapViewState | null>(null);

/** Hold the map's view across pane unmounts, for this shell mount only. */
export function MapViewProvider({ children }: { children: ReactNode }) {
  const [mapDimensions, setMapDimensions] = useState({ width: 800, height: 600 });
  const [viewBox, setViewBox] = useState<ViewBox>({
    x: 0, y: 0, width: 800, height: 600,
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [expandedZones, setExpandedZones] = useState<Set<number>>(new Set());
  const centeredOnRef = useRef<MapCenteredOn | null>(null);
  return (
    <MapViewContext.Provider value={{
      mapDimensions, setMapDimensions, viewBox, setViewBox,
      selectedId, setSelectedId, expandedZones, setExpandedZones, centeredOnRef,
    }}>
      {children}
    </MapViewContext.Provider>
  );
}

/** Read the shell-owned map view; bare MapPane mounts are a wiring error. */
export function useMapView(): MapViewState {
  const state = useContext(MapViewContext);
  if (!state) throw new Error("useMapView must be used inside MapViewProvider");
  return state;
}
