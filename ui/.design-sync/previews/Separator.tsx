import { Separator } from "nexus-ui";

export const Horizontal = () => (
  <div style={{ width: 360 }}>
    <div style={{ fontFamily: "serif", fontSize: 18 }}>The Veil</div>
    <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 12 }}>
      A drowned-city mystery in forty-one chapters
    </div>
    <Separator />
    <p style={{ marginTop: 12, marginBottom: 0, fontSize: 14 }}>
      The rain hadn't stopped for three days. Mira watched the spire lights
      bleed across the wet glass.
    </p>
  </div>
);

export const Vertical = () => (
  <div style={{ display: "flex", height: 24, alignItems: "center", gap: 16 }}>
    <span style={{ fontSize: 14 }}>Continue</span>
    <Separator orientation="vertical" />
    <span style={{ fontSize: 14 }}>Load</span>
    <Separator orientation="vertical" />
    <span style={{ fontSize: 14 }}>Settings</span>
  </div>
);
