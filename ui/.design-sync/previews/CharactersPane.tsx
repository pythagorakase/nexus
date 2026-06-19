import { CharactersPane } from "nexus-ui";

// Data-bound cast roster + dossier. The DesignThemeRoot fetch stub feeds
// GET /api/characters?slot, so the pane renders populated (list on the left,
// dossier on the right). Plain sized flex container — the nexus shell's 100vh
// grid would clip a lone pane (see NOTES.md). Unlike SettingsPane, CharactersPane
// has no shell-scoped controls, so it needs no `nexus-shell` wrapper.
export const Roster = () => (
  <div style={{ width: 820, height: 460, display: "flex", overflow: "hidden" }}>
    {/* slot is cosmetic — the stub matches on URL substring, not the query param */}
    <CharactersPane slot={2} />
  </div>
);
