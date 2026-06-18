import { NewStoryWizard } from "nexus-ui";

// NewStoryWizard (WizardShell) is the top-level new-story screen: the NEXUS
// title bar with menu + exit, wrapping the slot-selection step that opens the
// flow. It takes no props — it drives the whole wizard internally.
//
// NOTE: the slot list under the title bar is fetched from the API, which is
// unavailable in the headless preview harness, so the slot grid renders empty;
// the persistent wizard chrome (title bar, menu, exit) renders fully. Graded
// against what renders.
export const Shell = () => (
  <div style={{ position: "relative", width: 880, height: 620, overflow: "hidden" }}>
    <NewStoryWizard />
  </div>
);
