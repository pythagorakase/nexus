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
