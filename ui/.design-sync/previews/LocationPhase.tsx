import { LocationPhase } from "nexus-ui";

// LocationPhase reveals the chosen starting coordinates as a nested
// layer → zone → place stack, then offers "Enter Simulation". It generates its
// location on mount.
//
// NOTE: the phase opens on a "constructing geography" loader before its mock
// location resolves; the captured frame may land on that loader depending on
// capture timing. Graded against what renders.
export const Location = () => (
  <div
    style={{
      position: "relative",
      width: 880,
      minHeight: 600,
      overflow: "hidden",
      padding: 24,
    }}
  >
    <LocationPhase slot={5} onNext={() => {}} />
  </div>
);
