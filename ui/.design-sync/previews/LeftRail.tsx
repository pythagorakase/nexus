import { LeftRail } from "nexus-ui";

// The 60px vertical icon rail (primary navigation): Home, then the four pane
// tabs. The active tab carries the magenta edge marker + glow (CSS ::before
// on .rail-btn.on). .rail-left brings its own column flex; it just needs an
// explicit height to lay all its buttons out (the shell grid would clamp it
// to a single row). Extra left padding so the active tab's -12px edge marker
// is captured in-frame.
//
// The Backstage sigil sits above Settings only in developer mode (NexusLayout
// passes showBackstage={effectiveDeveloperMode}); the tab cells show the
// player's rail without it.

const noop = () => {};
const inert = { onTabChange: noop, onHome: noop, onBackstageToggle: noop };

const RailFrame = ({ children }: { children: React.ReactNode }) => (
  <div style={{ height: 320, display: "flex", paddingLeft: 16 }}>
    {children}
  </div>
);

// Narrative tab active.
export const NarrativeActive = () => (
  <RailFrame>
    <LeftRail tab="narrative" showBackstage={false} backstageOpen={false} {...inert} />
  </RailFrame>
);

// Map tab active — the edge marker tracks a different row.
export const MapActive = () => (
  <RailFrame>
    <LeftRail tab="map" showBackstage={false} backstageOpen={false} {...inert} />
  </RailFrame>
);

// Settings tab active.
export const SettingsActive = () => (
  <RailFrame>
    <LeftRail tab="settings" showBackstage={false} backstageOpen={false} {...inert} />
  </RailFrame>
);

// Developer mode, drawer closed: the accent sigil with its pulsing dot.
export const BackstageClosed = () => (
  <RailFrame>
    <LeftRail tab="narrative" showBackstage backstageOpen={false} {...inert} />
  </RailFrame>
);

// Developer mode, drawer open: the sigil lights like an active tab.
export const BackstageOpen = () => (
  <RailFrame>
    <LeftRail tab="narrative" showBackstage backstageOpen {...inert} />
  </RailFrame>
);
