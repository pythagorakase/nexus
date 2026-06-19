import { SettingsPane } from "nexus-ui";

// Data-bound settings console. The fetch stub feeds GET /api/settings (Veil
// theme, keeper fonts, model roles, slider bounds), so all seven sections
// render — the anchor rail plus Theme / Typography / Test Mode / Model /
// Context Length / Typewriter / App Icon cards.
//
// Wrapper keeps the `nexus-shell` class (not a bare flex box) so the console's
// RESET / COMMIT footer buttons — styled by shell-scoped `.nexus-shell .btn-soft`
// / `.nexus-shell .btn-primary` rules — render correctly instead of as default
// browser buttons. The shell's 100vh height and 52px TopBar grid row are
// overridden locally so the lone pane fills the card.
export const Console = () => (
  <div
    className="nexus-shell"
    style={{ width: 900, height: 680, gridTemplateRows: "1fr", overflow: "hidden" }}
  >
    <SettingsPane />
  </div>
);
