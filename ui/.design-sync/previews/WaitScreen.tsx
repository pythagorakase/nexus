import { WaitScreen } from "nexus-ui";

// WaitScreen is a fixed full-screen overlay (fixed inset-0). It resolves its
// vh/vw against the viewport, so a sized relative wrapper frames it for capture.
const Frame = ({ children }: { children: React.ReactNode }) => (
  <div style={{ position: "relative", width: 880, height: 600, overflow: "hidden" }}>
    {children}
  </div>
);

// The generating state shown while the story is being built: status line, a
// large MM:SS timer counting up, a progress strip, and Cancel / Retry.
export const Generating = () => (
  <Frame>
    <WaitScreen
      statusText="Initializing Your World"
      elapsedSeconds={87}
      maxSeconds={600}
      onRetry={() => {}}
      onCancel={() => {}}
    />
  </Frame>
);

// The error state: the heading flips to "Generation Failed", an error chip
// appears, and the Retry button is emphasized (filled + pulsing).
export const Failed = () => (
  <Frame>
    <WaitScreen
      statusText="Starting Narrative Generation"
      elapsedSeconds={142}
      maxSeconds={600}
      hasError
      errorMessage="The narrative engine timed out. Check your connection and try again."
      onRetry={() => {}}
      onCancel={() => {}}
    />
  </Frame>
);
