import { Label, Input, Checkbox } from "nexus-ui";

// Labels paired with inputs — the primary, intended use.
export const WithInputs = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 340 }}>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <Label htmlFor="setting">Setting</Label>
      <Input id="setting" defaultValue="Drowned city of New Lisbon" />
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <Label htmlFor="tone">Narrative Tone</Label>
      <Input id="tone" placeholder="e.g. Noir, Hopeful, Bleak" />
    </div>
  </div>
);

// Label beside a control, and the peer-disabled dimming behavior.
export const WithControls = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 340 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <Checkbox id="ironman" defaultChecked />
      <Label htmlFor="ironman">Ironman Mode</Label>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <Checkbox id="autosave" disabled />
      <Label htmlFor="autosave">Autosave Each Chapter</Label>
    </div>
  </div>
);
