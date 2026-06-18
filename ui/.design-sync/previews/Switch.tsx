import { Switch, Label } from "nexus-ui";

export const States = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Switch id="s1" />
      <Label htmlFor="s1">Off</Label>
    </div>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Switch id="s2" defaultChecked />
      <Label htmlFor="s2">On</Label>
    </div>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Switch id="s3" disabled />
      <Label htmlFor="s3">Disabled</Label>
    </div>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
      <Switch id="s4" defaultChecked disabled />
      <Label htmlFor="s4">Disabled On</Label>
    </div>
  </div>
);

export const Preferences = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 16, width: 320 }}>
    <div
      style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
    >
      <Label htmlFor="p1">Typewriter Animation</Label>
      <Switch id="p1" defaultChecked />
    </div>
    <div
      style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
    >
      <Label htmlFor="p2">Mature Content</Label>
      <Switch id="p2" defaultChecked />
    </div>
    <div
      style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
    >
      <Label htmlFor="p3">Ironman Mode</Label>
      <Switch id="p3" />
    </div>
  </div>
);
