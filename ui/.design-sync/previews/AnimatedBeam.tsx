import { useRef } from "react";
import { AnimatedBeam } from "nexus-ui";

const node: React.CSSProperties = {
  border: "1px solid hsl(var(--border))",
  background: "hsl(var(--card))",
  borderRadius: 12,
  padding: "14px 16px",
  minWidth: 132,
  textAlign: "center",
  boxShadow: "0 6px 18px rgba(0,0,0,0.35)",
};

// Data-flow beam — connects the live story context to the model, the engine's
// retrieval pipeline visualized. Two anchored nodes, beam drawn between them.
export const ContextToModel = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const fromRef = useRef<HTMLDivElement>(null);
  const toRef = useRef<HTMLDivElement>(null);
  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        width: 460,
        padding: "48px 32px",
      }}
    >
      <div ref={fromRef} style={node}>
        <div style={{ color: "hsl(var(--foreground))", fontSize: 14 }}>
          Warm Context
        </div>
        <div style={{ color: "hsl(var(--muted-foreground))", fontSize: 12 }}>
          12 chapters
        </div>
      </div>
      <div ref={toRef} style={node}>
        <div style={{ color: "hsl(var(--foreground))", fontSize: 14 }}>
          Storyteller
        </div>
        <div style={{ color: "hsl(var(--muted-foreground))", fontSize: 12 }}>
          Opus 4.8
        </div>
      </div>
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={fromRef}
        toRef={toRef}
        gradientStartColor="hsl(var(--primary))"
        gradientStopColor="hsl(var(--accent))"
        pathColor="hsl(var(--border))"
        pathWidth={2.5}
        curvature={-40}
      />
    </div>
  );
};

// Curved retrieval beam — memory store feeding the turn loop, with a downward
// curve and reversed gradient travel to show the prop axis.
export const MemoryRetrieval = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const fromRef = useRef<HTMLDivElement>(null);
  const toRef = useRef<HTMLDivElement>(null);
  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        width: 460,
        padding: "48px 32px",
      }}
    >
      <div ref={fromRef} style={node}>
        <div style={{ color: "hsl(var(--foreground))", fontSize: 14 }}>
          Memory Store
        </div>
        <div style={{ color: "hsl(var(--muted-foreground))", fontSize: 12 }}>
          embeddings
        </div>
      </div>
      <div ref={toRef} style={node}>
        <div style={{ color: "hsl(var(--foreground))", fontSize: 14 }}>
          Turn Loop
        </div>
        <div style={{ color: "hsl(var(--muted-foreground))", fontSize: 12 }}>
          assembling
        </div>
      </div>
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={fromRef}
        toRef={toRef}
        reverse
        gradientStartColor="hsl(var(--accent))"
        gradientStopColor="hsl(var(--primary))"
        pathColor="hsl(var(--border))"
        pathWidth={2.5}
        curvature={48}
      />
    </div>
  );
};
