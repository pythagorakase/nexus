import { Checkbox, Label } from "nexus-ui";

export const States = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Checkbox id="c1" />
      <Label htmlFor="c1">Unchecked</Label>
    </div>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Checkbox id="c2" defaultChecked />
      <Label htmlFor="c2">Checked</Label>
    </div>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Checkbox id="c3" disabled />
      <Label htmlFor="c3">Disabled</Label>
    </div>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Checkbox id="c4" defaultChecked disabled />
      <Label htmlFor="c4">Disabled Checked</Label>
    </div>
  </div>
);

export const StoryOptions = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 14, width: 320 }}>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Checkbox id="o1" defaultChecked />
      <Label htmlFor="o1">Enable Mature Content</Label>
    </div>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Checkbox id="o2" defaultChecked />
      <Label htmlFor="o2">Autosave After Each Chapter</Label>
    </div>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Checkbox id="o3" />
      <Label htmlFor="o3">Show Divergence Warnings</Label>
    </div>
  </div>
);
