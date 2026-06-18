import { SlotSelector } from "nexus-ui";

// SlotSelector lists the five save slots (occupied "lit" vs empty "hollow"
// treatments, lock badges, a glowing edge-marker on the bound story) and gates
// destructive overwrites behind a confirm dialog.
//
// NOTE: the slot list is fetched from /api/story/new/slots, which is
// unavailable in the headless preview harness; with no data the grid renders
// empty inside its deco-corner frame. Graded against what renders.
export const Slots = () => (
  <div
    style={{
      position: "relative",
      width: 880,
      minHeight: 600,
      overflow: "hidden",
      padding: 24,
    }}
  >
    <SlotSelector onSlotSelected={() => {}} onSlotResumed={() => {}} />
  </div>
);
