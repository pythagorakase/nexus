import { CharacterPhase } from "nexus-ui";

// CharacterPhase has two states. Passing `initialData` renders the
// "protagonist profile" review: a portrait/stats column beside a background +
// skills column — bypassing the entry form and its generate API call.
export const Profile = () => (
  <div style={{ width: 820 }}>
    <CharacterPhase
      slot={5}
      onNext={() => {}}
      initialData={{
        name: "Mira Sandoval",
        archetype: "Street Samurai",
        background:
          "Raised in the Sector 4 tenements, Mira traded a corporate security contract for freelance work after her squad was burned by the very executives they protected. She keeps one foot in the underworld and one eye on the exit.",
        stats: { STR: 8, DEX: 12, INT: 10, TECH: 14 },
        skills: ["Hacking", "Small Arms", "Stealth", "Corporate Protocol"],
      }}
    />
  </div>
);
