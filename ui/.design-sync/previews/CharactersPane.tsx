import { CharactersPane } from "nexus-ui";

// Data-bound cast roster + dossier. The DesignThemeRoot fetch stub feeds
// GET /api/characters?slot, so the pane renders populated (list on the left,
// dossier on the right). Plain sized flex container — the nexus shell's 100vh
// grid would clip a lone pane (see NOTES.md).
export const Roster = () => (
  <div style={{ width: 820, height: 460, display: "flex", overflow: "hidden" }}>
    <CharactersPane slot={2} />
  </div>
);
