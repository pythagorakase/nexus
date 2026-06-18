import { ArtifactSidePanel } from "nexus-ui";

// ArtifactSidePanel is the wizard's right-hand artifact drawer (h-full, left
// border). It needs a sized parent. All callbacks are inert in preview.

const setting = {
  world_name: "Neo-Veridia Prime",
  genre: "cyberpunk",
  secondary_genres: ["noir"],
  time_period: "2099",
  tone: "gritty",
  tech_level: "high_tech_low_life",
  major_conflict:
    "Three megacorps wage a proxy war for control of the city's water grid while the undercity drowns.",
  themes: ["Transhumanism", "Corporate Greed", "Digital Decay"],
};

const character = {
  name: "Mira Sandoval",
  archetype: "Street Samurai",
  summary:
    "A burned corporate enforcer turned freelancer, keeping one foot in the underworld and one eye on the exit.",
  traits: ["allies", "reputation", "enemies"],
  wildcard_name: "Ghost Limb",
  wildcard_description:
    "A salvaged cybernetic arm that occasionally acts on instincts that aren't hers.",
};

const seed = {
  seed: {
    title: "The Data Heist",
    hook: "You wake with an encrypted shard in your pocket and no memory of how it got there.",
  },
  layer: { name: "Neo-Veridia" },
  zone: { name: "Sector 4 — The Rust Belt" },
  location: {
    name: "The Neon Lotus Motel",
    summary: "A grimy capsule motel where the rooms rent by the hour and the walls listen.",
  },
};

const Frame = ({ children }: { children: React.ReactNode }) => (
  <div style={{ position: "relative", width: 360, height: 620 }}>{children}</div>
);

// Expanded view: the three story-element sections (Setting, Character, Seed) as
// an accordion. The Setting section opens to show world, genre, tone, conflict,
// and theme chips.
export const Expanded = () => (
  <Frame>
    <ArtifactSidePanel
      isCollapsed={false}
      onToggleCollapse={() => {}}
      mode="view"
      wizardData={{ setting, character, seed }}
      currentPhase="seed"
      completedPhases={new Set(["setting", "character", "seed"])}
      pendingArtifact={null}
      onPhaseClick={() => {}}
      onConfirm={() => {}}
      onRevise={() => {}}
      isLoading={false}
    />
  </Frame>
);

// Collapsed view: the slim icon rail — the three phase icons stacked and linked
// by an animated beam, with completed phases check-marked.
export const Collapsed = () => (
  <Frame>
    <ArtifactSidePanel
      isCollapsed
      onToggleCollapse={() => {}}
      mode="view"
      wizardData={{ setting, character, seed }}
      currentPhase="seed"
      completedPhases={new Set(["setting", "character"])}
      pendingArtifact={null}
      onPhaseClick={() => {}}
      onConfirm={() => {}}
      onRevise={() => {}}
      isLoading={false}
    />
  </Frame>
);
