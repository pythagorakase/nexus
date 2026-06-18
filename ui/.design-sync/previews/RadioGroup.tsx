import { RadioGroup, RadioGroupItem, Label } from "nexus-ui";

// Canonical group: options with a preselected defaultValue.
export const NarrativeTone = () => (
  <RadioGroup defaultValue="noir" style={{ maxWidth: 320 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <RadioGroupItem value="noir" id="tone-noir" />
      <Label htmlFor="tone-noir">Noir</Label>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <RadioGroupItem value="hopeful" id="tone-hopeful" />
      <Label htmlFor="tone-hopeful">Hopeful</Label>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <RadioGroupItem value="bleak" id="tone-bleak" />
      <Label htmlFor="tone-bleak">Bleak</Label>
    </div>
  </RadioGroup>
);

// With a disabled option and a longer descriptive row.
export const ModelTier = () => (
  <RadioGroup defaultValue="balanced" style={{ maxWidth: 360 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <RadioGroupItem value="fast" id="tier-fast" />
      <Label htmlFor="tier-fast">Fast — quicker chapters, lighter prose</Label>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <RadioGroupItem value="balanced" id="tier-balanced" />
      <Label htmlFor="tier-balanced">Balanced — the default storyteller</Label>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <RadioGroupItem value="deep" id="tier-deep" disabled />
      <Label htmlFor="tier-deep">Deep — unavailable on this slot</Label>
    </div>
  </RadioGroup>
);
