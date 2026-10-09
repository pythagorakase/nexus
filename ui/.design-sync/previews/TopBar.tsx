import { TopBar } from "nexus-ui";

// The 52px operator strip. Styled by .nexus-shell > .topbar in nexus-layout
// css, so each cell mounts inside a shell wrapper sized to the strip. The right
// side stays quiet: the frontier story clock (the server's face, verbatim) and
// the memory meter while a local model serves (DesignThemeRoot stubs one); the
// only flagged state is backend unreachability (OFFLINE).

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="nexus-shell" style={{ width: 760 }}>
    {children}
  </div>
);

const frontierClock = {
  instant: "2073-03-14T21:40:00+00:00",
  face: "14 Mar 2073 · 21:40",
};

// Resting state: wordmark, brass pip, slot label, player character; the
// frontier story clock on the right.
export const Active = () => (
  <Shell>
    <TopBar
      slot={2}
      characterName="Mira Vale"
      skaldStatus="READY"
      failedGeneration={null}
      toastedFailureSessionId={null}
      frontierClock={frontierClock}
    />
  </Shell>
);

// No active character yet (fresh slot): the slot label stands alone and there
// is no frontier to clock.
export const NoCharacter = () => (
  <Shell>
    <TopBar
      slot={5}
      characterName={null}
      skaldStatus="READY"
      failedGeneration={null}
      toastedFailureSessionId={null}
      frontierClock={null}
    />
  </Shell>
);

// Backend unreachable: the one state with no other surface flags OFFLINE on
// the right, and only while true.
export const Offline = () => (
  <Shell>
    <TopBar
      slot={2}
      characterName="Mira Vale"
      skaldStatus="OFFLINE"
      failedGeneration={null}
      toastedFailureSessionId={null}
      frontierClock={frontierClock}
    />
  </Shell>
);
