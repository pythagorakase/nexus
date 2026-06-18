import { SettingPhase } from "nexus-ui";

// SettingPhase has two states. Passing `initialData` jumps straight to the
// "world parameters established" review card — the generated-setting summary the
// player confirms — bypassing the entry form and its generate API call.
export const Generated = () => (
  <div style={{ width: 720 }}>
    <SettingPhase
      slot={5}
      onNext={() => {}}
      initialData={{
        name: "Neo-Veridia Prime",
        description:
          "A sprawling metropolis built on the ruins of the old world, where neon lights obscure the decay beneath and every rooftop garden hides a debt.",
        genre: "Cyberpunk",
        tech_level: "High Tech / Low Life",
        tone: "Gritty",
        themes: ["Transhumanism", "Corporate Greed", "Digital Decay"],
      }}
    />
  </div>
);
