import { ModeSelector } from "nexus-ui";

// The first wizard step: choose between conversational ("Express") and
// structured ("Advanced") story initialization. Two parallel mode cards with
// icon badges, a RECOMMENDED tag, and feature lists. onSelectMode is inert.
export const Modes = () => (
  <div style={{ width: 860 }}>
    <ModeSelector onSelectMode={() => {}} />
  </div>
);
