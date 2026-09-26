import { InteractiveWizard } from "nexus-ui";

// InteractiveWizard is the conversational core of the new-story flow: a
// resizable two-pane shell — a chat transcript with structured choices + a
// freeform slot on the left, and the artifact drawer on the right. It boots a
// wizard session over the API on mount.
//
// NOTE: the session bootstrap (/api/story/new/setup/start) is unavailable in
// the headless preview harness, so the transcript starts empty; the two-pane
// chrome, header, choice input, and collapsed artifact rail still render.
// Graded against what renders.
export const Shell = () => (
  <div style={{ position: "relative", width: 880, height: 620, overflow: "hidden" }}>
    <InteractiveWizard
      slot={5}
      onComplete={() => {}}
      onCancel={() => {}}
      onPhaseChange={() => {}}
      onArtifactConfirmed={() => {}}
      onResumeRequired={() => {}}
      wizardData={{
        slot: 5,
        setting: null,
        character: null,
        seed: null,
        location: null,
      }}
      setWizardData={() => {}}
      initialPhase="setting"
    />
  </div>
);

// The Introduction (seed) phase header adds the three strangeness glyphs
// beside the phase title: circle, diamond, sparkle, least to most strange.
// A resumed ready wizard needs no API: the stored selection (high) renders
// filled and the introduction artifact waits in the drawer for Confirm.
export const Introduction = () => (
  <div style={{ position: "relative", width: 880, height: 620, overflow: "hidden" }}>
    <InteractiveWizard
      slot={5}
      onComplete={() => {}}
      onCancel={() => {}}
      onPhaseChange={() => {}}
      onArtifactConfirmed={() => {}}
      onResumeRequired={() => {}}
      wizardData={{
        slot: 5,
        setting: { world_name: "The Glass Orchard" },
        character: null,
        seed: null,
        location: null,
      }}
      setWizardData={() => {}}
      resumeData={{
        thread_id: "conv_preview",
        current_phase: "ready",
        messages: [
          {
            role: "assistant",
            content: "The orchard gate stands open. Your story is ready to begin.",
          },
        ],
        choices: [],
        setting_draft: { world_name: "The Glass Orchard" },
        character_draft: null,
        character_state: null,
        selected_seed: {
          title: "The Orchard Gate",
          hook: "Rain needles the glass while a lantern moves among the trees.",
        },
        layer_draft: { name: "Verdance" },
        zone_draft: { name: "Lower Terraces" },
        initial_location: { name: "Orchard Gate" },
        weird_level: "high",
      }}
      initialPhase="seed"
    />
  </div>
);
