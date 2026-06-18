import { CrescentFrame } from "nexus-ui";
// Edge-stretched Art Nouveau crescent border (Veil theme). It's a full-bleed
// absolute overlay, so it needs a sized relative container to frame.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "veil");

export const Default = () => (
  <div style={{ position: "relative", width: 560, height: 360, background: "hsl(var(--background))", overflow: "hidden" }}>
    <CrescentFrame />
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        placeItems: "center",
        color: "hsl(var(--foreground))",
        fontFamily: "var(--font-display)",
        fontSize: 44,
        letterSpacing: "0.22em",
      }}
    >
      NEXUS
    </div>
  </div>
);
