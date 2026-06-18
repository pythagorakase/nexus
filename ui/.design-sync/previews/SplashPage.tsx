import { SplashPage } from "nexus-ui";
// The top-level splash route: selects the theme-appropriate home composition.
// In the default Veil theme it resolves to the canonical NEXUS IRIS hero — the
// living logarithmic-spiral field drawing the gold Megrim wordmark, the licensed
// magenta crescent ornament full-bleed around the scene, and the lower-third
// Continue / Load / Settings menu. Rendered inside a sized, clipped viewport box
// so the full-bleed vh/vw composition is captured in-frame.

export const Screen = () => (
  <div
    style={{
      position: "relative",
      width: 900,
      height: 690,
      overflow: "hidden",
      backgroundColor: "#09101c",
    }}
  >
    <SplashPage />
  </div>
);
