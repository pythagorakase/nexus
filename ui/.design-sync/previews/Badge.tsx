import { Badge } from "nexus-ui";

export const Variants = () => (
  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
    <Badge>Canon</Badge>
    <Badge variant="secondary">Draft</Badge>
    <Badge variant="destructive">Diverged</Badge>
    <Badge variant="outline">Archived</Badge>
  </div>
);

export const ChapterTags = () => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
    <Badge>Chapter 7</Badge>
    <Badge variant="secondary">Mira</Badge>
    <Badge variant="secondary">Cassius</Badge>
    <Badge variant="outline">Night</Badge>
    <Badge variant="outline">The Spires</Badge>
    <Badge variant="destructive">Combat</Badge>
  </div>
);

export const SlotStatus = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Badge>Active</Badge>
    <Badge variant="secondary">Locked</Badge>
    <Badge variant="outline">Empty</Badge>
  </div>
);
