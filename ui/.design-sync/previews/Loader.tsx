import { Loader } from "nexus-ui";

// The spinner at its size scale. Each is the AI "thinking" indicator; the SVG
// strokes inherit currentColor, so they pick up the Veil foreground tone.
export const Sizes = () => (
  <div style={{ display: "flex", gap: 32, alignItems: "center" }}>
    <Loader size={16} />
    <Loader size={24} />
    <Loader size={40} />
    <Loader size={64} />
  </div>
);

// In context: a storyteller-is-writing row, the loader beside its status copy.
export const Composing = () => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 12,
      color: "var(--muted-foreground)",
      fontSize: 14,
    }}
  >
    <Loader size={20} />
    <span>The Narrator Is Writing the Next Chapter…</span>
  </div>
);

// Color-driven variants: the loader takes whatever text color its container
// sets, shown here against the primary and destructive theme tokens.
export const Tones = () => (
  <div style={{ display: "flex", gap: 32, alignItems: "center" }}>
    <span style={{ color: "var(--primary)" }}>
      <Loader size={36} />
    </span>
    <span style={{ color: "var(--destructive)" }}>
      <Loader size={36} />
    </span>
    <span style={{ color: "var(--foreground)" }}>
      <Loader size={36} />
    </span>
  </div>
);
