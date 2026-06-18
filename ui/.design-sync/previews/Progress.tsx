import { Progress } from "nexus-ui";

// A few fill levels — the core visual axis of a progress bar.
export const Levels = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 360 }}>
    <Progress value={12} />
    <Progress value={48} />
    <Progress value={87} />
    <Progress value={100} />
  </div>
);

// In context: labeled progress for narrative-generation phases.
export const GenerationPhases = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 360 }}>
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <span>Embedding Chapter 40</span>
        <span style={{ opacity: 0.7 }}>64%</span>
      </div>
      <Progress value={64} />
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <span>Building Warm Context</span>
        <span style={{ opacity: 0.7 }}>30%</span>
      </div>
      <Progress value={30} />
    </div>
  </div>
);
