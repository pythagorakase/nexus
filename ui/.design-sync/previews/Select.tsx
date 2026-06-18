import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectLabel,
  SelectItem,
  SelectSeparator,
} from "nexus-ui";

// Open model picker: trigger + portalled content rendered visible via defaultOpen.
export const ModelPicker = () => (
  <div style={{ width: 300, paddingBottom: 220 }}>
    <Select defaultValue="frontier" open>
      <SelectTrigger>
        <SelectValue placeholder="Choose a Model" />
      </SelectTrigger>
      <SelectContent position="item-aligned">
        <SelectGroup>
          <SelectLabel>Storyteller</SelectLabel>
          <SelectItem value="frontier">Frontier Author</SelectItem>
          <SelectItem value="balanced">Balanced Narrator</SelectItem>
          <SelectItem value="economy">Economy Draft</SelectItem>
        </SelectGroup>
        <SelectSeparator />
        <SelectGroup>
          <SelectLabel>Local Curators</SelectLabel>
          <SelectItem value="retrieval">Retrieval Only</SelectItem>
          <SelectItem value="offline" disabled>
            Offline (Unavailable)
          </SelectItem>
        </SelectGroup>
      </SelectContent>
    </Select>
  </div>
);

// Closed resting trigger with a selected value — the collapsed state of the control.
export const Closed = () => (
  <div style={{ width: 300 }}>
    <Select defaultValue="seven">
      <SelectTrigger>
        <SelectValue placeholder="Jump to Chapter" />
      </SelectTrigger>
      <SelectContent position="item-aligned">
        <SelectItem value="five">Chapter Five — The Flood District</SelectItem>
        <SelectItem value="six">Chapter Six — Tidewardens</SelectItem>
        <SelectItem value="seven">Chapter Seven — The Spire Lights</SelectItem>
      </SelectContent>
    </Select>
  </div>
);
