import { DevMarkdownPreview } from "nexus-ui";
// The narrative markdown harness: renders a committed prose block (episode
// heading, storyteller voice, bold/italic spans, a blockquote aside, the
// deep-heading floor check) plus a player-voice line and a live typewriter
// reveal — the exact .reader / .prose-block / .md-part markup NarrativePane
// uses. Rendered in the default Veil theme inside a sized, clipped viewport
// box so the 100vh reader frame resolves and the reveal stays in-frame.

export const Reader = () => (
  <div
    style={{
      position: "relative",
      width: 900,
      height: 690,
      overflow: "hidden",
    }}
  >
    <DevMarkdownPreview />
  </div>
);
