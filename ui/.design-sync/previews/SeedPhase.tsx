import { SeedPhase } from "nexus-ui";

// SeedPhase presents three inciting-incident cards to pick from, then a
// "Begin Simulation" confirm. It self-generates its options on mount, so the
// preview composes the real component with a pre-selected option id.
//
// NOTE: the phase shows a brief generating loader before its mock options
// resolve; the captured frame may land on that loader depending on capture
// timing. Graded against what renders.
export const Seeds = () => (
  <div
    style={{
      position: "relative",
      width: 880,
      minHeight: 600,
      overflow: "hidden",
      padding: 24,
    }}
  >
    <SeedPhase slot={5} onNext={() => {}} initialData={{ id: 2 }} />
  </div>
);
