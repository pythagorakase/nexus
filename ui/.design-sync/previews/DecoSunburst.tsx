import { DecoSunburst } from "nexus-ui";
// Radiating Art Deco sunburst — Gilded theme. Opacity bumped from the subtle
// default so the rays read clearly in a catalog card.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "gilded");

export const HalfBurst = () => (
  <div style={{ width: 260, height: 140, display: "grid", placeItems: "center", background: "hsl(var(--card))" }}>
    <DecoSunburst size={240} rays={24} opacity={0.55} />
  </div>
);

export const FullBurst = () => (
  <div style={{ width: 220, height: 220, display: "grid", placeItems: "center", background: "hsl(var(--card))" }}>
    <DecoSunburst size={200} rays={36} spread={360} opacity={0.5} />
  </div>
);
