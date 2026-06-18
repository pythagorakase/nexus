import { LeftRail } from "nexus-ui";

// The 60px vertical icon rail (primary navigation): Home, then the four pane
// tabs. The active tab carries the magenta edge marker + glow (CSS ::before
// on .rail-btn.on). .rail-left brings its own column flex; it just needs an
// explicit height to lay all five buttons out (the shell grid would clamp it
// to a single row). Extra left padding so the active tab's -12px edge marker
// is captured in-frame.

const noop = () => {};

const RailFrame = ({ children }: { children: React.ReactNode }) => (
  <div style={{ height: 320, display: "flex", paddingLeft: 16 }}>
    {children}
  </div>
);

// Narrative tab active.
export const NarrativeActive = () => (
  <RailFrame>
    <LeftRail tab="narrative" onTabChange={noop} onHome={noop} />
  </RailFrame>
);

// Map tab active — the edge marker tracks a different row.
export const MapActive = () => (
  <RailFrame>
    <LeftRail tab="map" onTabChange={noop} onHome={noop} />
  </RailFrame>
);

// Settings tab active.
export const SettingsActive = () => (
  <RailFrame>
    <LeftRail tab="settings" onTabChange={noop} onHome={noop} />
  </RailFrame>
);
