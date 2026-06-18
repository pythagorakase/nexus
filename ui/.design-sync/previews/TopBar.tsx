import { TopBar } from "nexus-ui";

// The 52px operator strip. Styled by .nexus-shell > .topbar in nexus-layout
// css, so each cell mounts inside a shell wrapper sized to the strip. At rest
// the right side is empty by design (visual-minimalism doctrine); the only
// flagged state is backend unreachability (OFFLINE).

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="nexus-shell" style={{ width: 760 }}>
    {children}
  </div>
);

// Resting state: wordmark, brass pip, slot label, player character — nothing
// on the right.
export const Active = () => (
  <Shell>
    <TopBar slot={2} characterName="Mira Vale" skaldStatus="READY" />
  </Shell>
);

// No active character yet (fresh slot): the em-dash placeholder holds the slot.
export const NoCharacter = () => (
  <Shell>
    <TopBar slot={5} characterName={null} skaldStatus="READY" />
  </Shell>
);

// Backend unreachable: the one state with no other surface flags OFFLINE on
// the right, and only while true.
export const Offline = () => (
  <Shell>
    <TopBar slot={2} characterName="Mira Vale" skaldStatus="OFFLINE" />
  </Shell>
);
