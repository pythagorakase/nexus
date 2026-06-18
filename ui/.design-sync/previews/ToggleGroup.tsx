import { ToggleGroup, ToggleGroupItem } from "nexus-ui";
import { AlignLeft, AlignCenter, AlignJustify } from "lucide-react";

// Single-select group with one option pressed — prose density choice.
export const ProseDensity = () => (
  <ToggleGroup type="single" defaultValue="standard" variant="outline">
    <ToggleGroupItem value="terse">Terse</ToggleGroupItem>
    <ToggleGroupItem value="standard">Standard</ToggleGroupItem>
    <ToggleGroupItem value="lavish">Lavish</ToggleGroupItem>
  </ToggleGroup>
);

// Multi-select group with two options pressed — narration channels.
export const Channels = () => (
  <ToggleGroup type="multiple" defaultValue={["dialogue", "interiority"]}>
    <ToggleGroupItem value="dialogue">Dialogue</ToggleGroupItem>
    <ToggleGroupItem value="action">Action</ToggleGroupItem>
    <ToggleGroupItem value="interiority">Interiority</ToggleGroupItem>
  </ToggleGroup>
);

// Icon-only group — text alignment, default size.
export const Alignment = () => (
  <ToggleGroup type="single" defaultValue="left" variant="outline">
    <ToggleGroupItem value="left" aria-label="Align Left">
      <AlignLeft />
    </ToggleGroupItem>
    <ToggleGroupItem value="center" aria-label="Align Center">
      <AlignCenter />
    </ToggleGroupItem>
    <ToggleGroupItem value="justify" aria-label="Justify">
      <AlignJustify />
    </ToggleGroupItem>
  </ToggleGroup>
);
