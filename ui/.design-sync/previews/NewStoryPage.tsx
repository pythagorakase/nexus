import { NewStoryPage } from "nexus-ui";
// The top-level new-story route: composes the wizard shell, which opens on the
// memory-slot selector — the NEXUS marquee top bar (hamburger menu + ABORT),
// the framed slot grid, and the slot cards themselves. The slot list is fetched
// from /api/story/new/slots; in the headless preview that fetch falls back, so
// the screen renders its chrome and the empty slot grid (an exemplar of the
// entry phase, not a missing render). Rendered in the default Veil theme inside
// a sized, clipped viewport box so the h-screen flex column resolves in-frame.

export const Screen = () => (
  <div
    style={{
      position: "relative",
      width: 900,
      height: 690,
      overflow: "hidden",
    }}
  >
    <NewStoryPage />
  </div>
);
