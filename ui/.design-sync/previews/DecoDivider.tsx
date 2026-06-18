import { DecoDivider } from "nexus-ui";
// Art Deco section divider — shown in the Gilded theme.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "gilded");

export const Variants = () => (
  <div style={{ width: 380, display: "flex", flexDirection: "column", gap: 10 }}>
    <DecoDivider variant="diamond" />
    <DecoDivider variant="chevron" />
    <DecoDivider variant="line" />
    <DecoDivider variant="glyph" />
  </div>
);
