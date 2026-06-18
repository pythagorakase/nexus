import { AspectRatio } from "nexus-ui";

// 16:9 cover frame — the ratio holds a chapter "cover plate" at a fixed width.
export const ChapterCover = () => (
  <div style={{ width: 420 }}>
    <AspectRatio ratio={16 / 9}>
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: 10,
          border: "1px solid hsl(var(--border))",
          background:
            "radial-gradient(120% 120% at 20% 0%, hsl(var(--primary) / 0.55), hsl(var(--background)) 70%)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
          padding: 18,
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-serif, Georgia, serif)",
            fontSize: 22,
            color: "hsl(var(--foreground))",
          }}
        >
          The Drowned Archive
        </div>
        <div style={{ color: "hsl(var(--muted-foreground))", fontSize: 13 }}>
          Chapter Seven · The Veil
        </div>
      </div>
    </AspectRatio>
  </div>
);

// Square 1:1 frame — a character portrait slot, same primitive, different ratio.
export const PortraitFrame = () => (
  <div style={{ width: 240 }}>
    <AspectRatio ratio={1}>
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: 10,
          border: "1px solid hsl(var(--border))",
          background:
            "linear-gradient(160deg, hsl(var(--muted)), hsl(var(--background)))",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          padding: 14,
          boxSizing: "border-box",
        }}
      >
        <span style={{ color: "hsl(var(--foreground))", fontSize: 15 }}>
          Mira Vance
        </span>
      </div>
    </AspectRatio>
  </div>
);
