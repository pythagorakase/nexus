import { Input, Label } from "nexus-ui";

// Labeled fields — the canonical Input + Label pairing across NEXUS settings.
export const Labeled = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 360 }}>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <Label htmlFor="story-title">Story Title</Label>
      <Input id="story-title" defaultValue="The Drowned Archive" />
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <Label htmlFor="protagonist">Protagonist</Label>
      <Input id="protagonist" placeholder="Name your point-of-view character" />
    </div>
  </div>
);

// Input states: filled, placeholder, disabled, and a typed value.
export const States = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 360 }}>
    <Input defaultValue="Slot 02 — Chapter Seven" />
    <Input placeholder="Search chapters and characters…" />
    <Input type="password" defaultValue="archivist" />
    <Input disabled defaultValue="Locked — Ironman save" />
  </div>
);

// Typed variants: number and date inputs for world-time and chapter counts.
export const Types = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 360 }}>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <Label htmlFor="ctx-len">Context Length (tokens)</Label>
      <Input id="ctx-len" type="number" defaultValue={128000} />
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <Label htmlFor="start-date">In-World Start Date</Label>
      <Input id="start-date" type="date" defaultValue="2087-04-12" />
    </div>
  </div>
);
