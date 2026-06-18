import { DecoRays } from "nexus-ui";
// Off-screen brass ray field from the Gilded splash — an absolute full-bleed
// sunburst whose origin sits above the frame. Shown in the Gilded (Art Deco
// brass) theme inside a sized relative container, with the NEXUS marquee it
// backs on the home screen.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "gilded");

const gilded = {
  bg: "hsl(0 0% 4%)",
  brassBright: "#e8c766",
} as const;

// The splash-tuned ray config (GILDED_SPLASH_RAYS), with the origin nudged
// just above the framed scene so the radiating spokes read in-frame.
export const Hero = () => (
  <div
    style={{
      position: "relative",
      width: 760,
      height: 460,
      background: gilded.bg,
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
    }}
  >
    <DecoRays
      sourceXvw={50}
      sourceYvh={-8}
      rayCount={64}
      spinSeconds={0}
      reachVmax={1.4}
      spreadDeg={360}
      color="#c9a227"
      accentColor="#e8c766"
      thickness={1.4}
      intensity={0.55}
      falloff={0.6}
      rings={false}
      zIndex={0}
    />
    <h1
      style={{
        position: "relative",
        zIndex: 2,
        margin: 0,
        fontFamily: "var(--font-display)",
        fontSize: 104,
        fontWeight: 400,
        letterSpacing: "0.1em",
        lineHeight: 1,
        color: gilded.brassBright,
        textShadow:
          "0 0 12px hsl(43 74% 47% / .6), 0 0 24px hsl(43 74% 47% / .35)",
      }}
    >
      NEXUS
    </h1>
  </div>
);

// The concentric-ring variant (rings on), a denser radial ornament.
export const Rayed = () => (
  <div
    style={{
      position: "relative",
      width: 460,
      height: 460,
      background: gilded.bg,
      overflow: "hidden",
    }}
  >
    <DecoRays
      sourceXvw={50}
      sourceYvh={50}
      rayCount={96}
      spinSeconds={0}
      reachVmax={0.9}
      spreadDeg={360}
      color="#c9a227"
      accentColor="#e8c766"
      accentEvery={4}
      thickness={2}
      intensity={0.6}
      falloff={0.55}
      rings
      ringCount={4}
      zIndex={0}
    />
  </div>
);
