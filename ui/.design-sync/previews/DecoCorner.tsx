import { DecoCorner } from "nexus-ui";
// Art Deco corner motif — its brass palette belongs to the Gilded theme.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "gilded");

export const FramedPanel = () => (
  <div
    style={{
      position: "relative",
      width: 300,
      height: 170,
      border: "1px solid hsl(var(--card-border))",
      background: "hsl(var(--card))",
    }}
  >
    <DecoCorner position="tl" size={30} />
    <DecoCorner position="tr" size={30} />
    <DecoCorner position="bl" size={30} />
    <DecoCorner position="br" size={30} />
    <div style={{ display: "grid", placeItems: "center", height: "100%", color: "hsl(var(--foreground))" }}>
      Chapter Seven
    </div>
  </div>
);

export const Sizes = () => (
  <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
    {[18, 30, 48].map((s) => (
      <div
        key={s}
        style={{ position: "relative", width: 90, height: 90, border: "1px solid hsl(var(--card-border))", background: "hsl(var(--card))" }}
      >
        <DecoCorner position="tl" size={s} />
        <DecoCorner position="br" size={s} />
      </div>
    ))}
  </div>
);
