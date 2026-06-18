import { SplashThemeMenu } from "nexus-ui";
// The splash-screen theme picker: an unlabeled corner control (the
// visual-minimalism "guessable icon" pattern) that opens a dropdown to swap
// between the Gilded / Vector / Veil palettes. It positions itself
// absolutely top-left, so it's shown over a themed splash backdrop. Rendered
// in the Veil theme (its splash home), where the trigger glows magenta.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "veil");

// The control in situ — a Megrim-quiet top bar over a deep Veil-navy field,
// the corner glyph reading as chrome exactly where it lives on the splash.
export const Picker = () => (
  <div
    style={{
      position: "relative",
      width: 560,
      height: 220,
      overflow: "hidden",
      background:
        "radial-gradient(120% 90% at 50% -10%, hsl(320 45% 18% / 0.55), #09101c 60%)",
    }}
  >
    <SplashThemeMenu />
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        placeItems: "center",
        color: "hsl(42 45% 80%)",
        fontFamily: "var(--font-display)",
        fontSize: 56,
        letterSpacing: "0.18em",
        opacity: 0.45,
      }}
    >
      NEXUS
    </div>
  </div>
);

// The control isolated on a screen corner — a faint frame edge anchors the
// glyph as top-left chrome so the resting state + hit area read on their own.
export const Trigger = () => (
  <div
    style={{
      position: "relative",
      width: 240,
      height: 180,
      overflow: "hidden",
      background:
        "radial-gradient(140% 120% at 0% 0%, hsl(320 45% 16% / 0.5), #09101c 55%)",
      borderTop: "1px solid hsl(320 40% 40% / 0.35)",
      borderLeft: "1px solid hsl(320 40% 40% / 0.35)",
    }}
  >
    <SplashThemeMenu />
  </div>
);
