import { TraitSelectorGrid } from "nexus-ui";

// The trait grid as it lives inside the artifact panel. Two modes:

// select: two-column toggle buttons by category, suggested traits ring-marked,
// indicator dots + a live count caption underneath.
export const SelectMode = () => (
  <div style={{ width: 360 }}>
    <TraitSelectorGrid
      mode="select"
      suggestedTraits={["allies", "reputation", "enemies"]}
      selectedTraits={["allies", "reputation", "enemies"]}
      onSelectionChange={() => {}}
      maxTraits={3}
    />
  </div>
);

// display: the chosen traits as an expandable list with descriptions, examples,
// and the storyteller's rationale for each ("why this trait?").
export const DisplayMode = () => (
  <div style={{ width: 360 }}>
    <TraitSelectorGrid
      mode="display"
      suggestedTraits={[]}
      selectedTraits={["allies", "reputation", "enemies"]}
      traitRationales={{
        allies: "Her old squad still answers when she calls — at a price.",
        reputation: "In Sector 4, the name Sandoval opens doors and draws knives.",
        enemies: "The executives who burned her squad want the loose end tied off.",
      }}
      maxTraits={3}
    />
  </div>
);
