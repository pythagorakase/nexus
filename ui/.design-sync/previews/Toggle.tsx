import { Toggle } from "nexus-ui";
import { Bold, Italic, Eye } from "lucide-react";

// Variant axis: default vs outline, each shown off and pressed (on).
export const Variants = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Toggle aria-label="Bold (off)">
      <Bold />
    </Toggle>
    <Toggle defaultPressed aria-label="Bold (on)">
      <Bold />
    </Toggle>
    <Toggle variant="outline" aria-label="Italic (off)">
      <Italic />
    </Toggle>
    <Toggle variant="outline" defaultPressed aria-label="Italic (on)">
      <Italic />
    </Toggle>
  </div>
);

// Size scale on the outline variant with a text label.
export const Sizes = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Toggle variant="outline" size="sm">
      Ironman
    </Toggle>
    <Toggle variant="outline" size="default" defaultPressed>
      Ironman
    </Toggle>
    <Toggle variant="outline" size="lg">
      Ironman
    </Toggle>
  </div>
);

// A single labeled toggle in context: reveal the hidden ledger.
export const RevealLedger = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Toggle variant="outline" defaultPressed aria-label="Show Ledger">
      <Eye />
      Show Ledger
    </Toggle>
    <Toggle variant="outline" disabled aria-label="Show Map (locked)">
      <Eye />
      Show Map
    </Toggle>
  </div>
);
