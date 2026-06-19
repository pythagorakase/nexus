import { SettingsPane } from "nexus-ui";

// Data-bound settings console. The fetch stub feeds GET /api/settings (Veil
// theme, keeper fonts, model roles, slider bounds), so all seven sections
// render — the anchor rail plus Theme / Typography / Test Mode / Model /
// Context Length / Typewriter / App Icon cards.
export const Console = () => (
  <div style={{ width: 900, height: 680, display: "flex", overflow: "hidden" }}>
    <SettingsPane />
  </div>
);
