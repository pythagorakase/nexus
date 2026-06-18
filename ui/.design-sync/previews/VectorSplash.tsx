import { VectorSplash } from "nexus-ui";
// The Vector terminal home screen: animated cyan grid + moving scan-lines, an
// Arwes corner frame, the deciphering NEXUS title, and octagonal menu buttons
// (Continue / Load / Settings). Rendered in the Vector (terminal/cyberpunk)
// theme inside a sized, clipped container so the full scene is captured.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "vector");

export const Splash = () => (
  <div
    style={{
      position: "relative",
      width: 900,
      height: 690,
      overflow: "hidden",
      background: "#000906",
    }}
  >
    <VectorSplash />
  </div>
);
