import { WaitScreen } from "nexus-ui";

// WaitScreen is a fixed full-screen overlay (fixed inset-0). It resolves its
// vh/vw against the viewport, so a sized relative wrapper frames it for capture.
const Frame = ({ children }: { children: React.ReactNode }) => (
  <div style={{ position: "relative", width: 880, height: 600, overflow: "hidden" }}>
    {children}
  </div>
);

// The genesis stages the new-story wizard waits on, in pipeline order.
const STAGES = [
  "packet",
  "seed_candidates",
  "expansion",
  "persistence",
  "embedding",
  "bootstrap",
] as const;

// The generating state shown while the story is being built: status line, a
// large MM:SS timer counting up, the stage track (two stages done, the third
// glowing), and Cancel / Retry.
export const Generating = () => (
  <Frame>
    <WaitScreen
      statusText="Initializing Your World"
      elapsedSeconds={87}
      stages={STAGES}
      currentStage="expansion"
      onRetry={() => {}}
      onCancel={() => {}}
    />
  </Frame>
);

// The error state: the heading flips to "Generation Failed", an error chip
// appears, the failed stage's pip turns the danger colour, and the Retry
// button is emphasized (filled + pulsing).
export const Failed = () => (
  <Frame>
    <WaitScreen
      statusText="Initializing Your World"
      elapsedSeconds={142}
      stages={STAGES}
      currentStage="persistence"
      hasError
      errorMessage="Retrograde persistence is blocked by 2 unresolved references."
      onRetry={() => {}}
      onCancel={() => {}}
    />
  </Frame>
);
