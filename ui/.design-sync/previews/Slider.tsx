import { Slider, Label } from "nexus-ui";

// Single-value control: narrative temperature with a labeled readout.
export const Temperature = () => (
  <div style={{ width: 360, display: "flex", flexDirection: "column", gap: 10 }}>
    <div style={{ display: "flex", justifyContent: "space-between" }}>
      <Label>Narrative Temperature</Label>
      <span style={{ fontSize: 14, opacity: 0.8 }}>0.7</span>
    </div>
    <Slider defaultValue={[70]} max={100} step={1} />
  </div>
);

// Range (two thumbs): the warm-slice chapter window.
export const ChapterWindow = () => (
  <div style={{ width: 360, display: "flex", flexDirection: "column", gap: 10 }}>
    <div style={{ display: "flex", justifyContent: "space-between" }}>
      <Label>Warm Chapter Window</Label>
      <span style={{ fontSize: 14, opacity: 0.8 }}>Ch. 5 – 12</span>
    </div>
    <Slider defaultValue={[5, 12]} min={1} max={20} step={1} />
  </div>
);

// Disabled control — locked while a chapter is generating.
export const Locked = () => (
  <div style={{ width: 360, display: "flex", flexDirection: "column", gap: 10 }}>
    <Label>Memory Depth (Locked During Generation)</Label>
    <Slider defaultValue={[40]} max={100} step={1} disabled />
  </div>
);
