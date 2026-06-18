import { Button } from "nexus-ui";

// Primary variant axis: every visual variant in one row.
export const Variants = () => (
  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
    <Button>Begin Story</Button>
    <Button variant="secondary">Secondary</Button>
    <Button variant="destructive">Wipe Slot</Button>
    <Button variant="outline">Outline</Button>
    <Button variant="ghost">Ghost</Button>
    <Button variant="link">Link</Button>
  </div>
);

// Size scale.
export const Sizes = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Button size="sm">Small</Button>
    <Button size="default">Default</Button>
    <Button size="lg">Large</Button>
  </div>
);

// Statically-renderable states.
export const States = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Button>Enabled</Button>
    <Button disabled>Disabled</Button>
    <Button variant="outline" disabled>
      Disabled Outline
    </Button>
  </div>
);
