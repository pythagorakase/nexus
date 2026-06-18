import { GildedSplash } from "nexus-ui";
// The approved Art Deco home screen: off-screen brass ray field behind the
// Megrim NEXUS marquee, the licensed r1c1 Deco frame sliced around the whole
// viewport, and the three-button menu (Continue / Load / Settings). Rendered
// in the Gilded theme inside a sized, clipped container so the full-bleed
// composition is captured in-frame.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "gilded");

export const Splash = () => (
  <div
    style={{
      position: "relative",
      width: 900,
      height: 690,
      overflow: "hidden",
      background: "hsl(0 0% 4%)",
    }}
  >
    <GildedSplash />
  </div>
);
