import { StoryChoices } from "nexus-ui";

// The branching choice list as the player sees it after a chapter — numbered,
// serif, hover-revealed actions. onSelect is required but inert in preview.
export const Branches = () => (
  <div style={{ width: 600 }}>
    <StoryChoices
      choices={[
        "Accept the Prince's writ of safe conduct.",
        "Slip away and seek out the Nosferatu instead.",
        "Demand to speak with the Archivist before deciding.",
      ]}
      onSelect={() => {}}
    />
  </div>
);

// A two-branch fork with the player's previous pick highlighted (the accent
// left-border marks what was chosen before a regeneration).
export const PreviousPick = () => (
  <div style={{ width: 600 }}>
    <StoryChoices
      choices={[
        "Cross the flood district by skiff under cover of dark.",
        "Wait for the tide to fall and take the customs-house bridge.",
      ]}
      previousSelection={{ label: 1, text: "", edited: false }}
      onSelect={() => {}}
    />
  </div>
);

// The disabled state, shown while the next chapter is generating — dimmed and
// non-interactive across all four branches.
export const Generating = () => (
  <div style={{ width: 600 }}>
    <StoryChoices
      choices={[
        "Light the salt lantern and descend the iron stair.",
        "Follow the cold air through the curtained arch.",
        "Search the clerk's office for the vault ledger.",
        "Leave the reading room and bar the door behind you.",
      ]}
      disabled
      onSelect={() => {}}
    />
  </div>
);
