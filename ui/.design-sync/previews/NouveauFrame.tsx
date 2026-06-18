import { NouveauFrame } from "nexus-ui";
// Licensed Art Nouveau border around the Veil wordmark — full-bleed overlay
// (viewBox 1200x700, slice-fit), so it needs a sized relative container.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "veil");

export const Default = () => (
  <div style={{ position: "relative", width: 560, height: 360, background: "hsl(var(--background))", overflow: "hidden" }}>
    <NouveauFrame />
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
