import { VeilSplash } from "nexus-ui";
// The canonical NEXUS IRIS hero (Veil Hero Spiral v3): a living
// logarithmic-spiral field draws the gold Megrim NEXUS wordmark, the licensed
// magenta crescent ornament runs full-bleed around the composition, and the
// three-button menu (Continue / Load / Settings) drops to the lower third.
// Rendered in the Veil (Art Nouveau magenta) theme inside a sized, clipped
// container so the full-bleed hero is captured in-frame.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "veil");

export const Splash = () => (
  <div
    style={{
      position: "relative",
      width: 900,
      height: 690,
      overflow: "hidden",
      backgroundColor: "#09101c",
    }}
  >
    <VeilSplash />
  </div>
);
