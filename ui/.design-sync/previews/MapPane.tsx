import { MapPane } from "nexus-ui";

// The rebuilt PostGIS world map. The Natural Earth land outline is a BUNDLED
// module (not a fetch), and the projection is a pure hook, so the map canvas
// renders fully static: sea fill, survey grid, and every continent. The
// places / zones come from headless fetches that return empty, so the left
// index is empty and the canvas shows the [ UNCHARTED ] empty-state marker
// over the real world geography, plus the zoom readout chrome.
//
// The pane is full-bleed (ResizeObserver on its canvas), so it mounts in a
// sized relative container to be captured in-frame.

export const WorldMap = () => (
  <div
    style={{
      position: "relative",
      width: 820,
      height: 540,
      overflow: "hidden",
      border: "1px solid hsl(var(--border))",
    }}
  >
    <MapPane slot={2} />
  </div>
);
