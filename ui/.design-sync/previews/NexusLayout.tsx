import { NexusLayout } from "nexus-ui";

// The full app shell: 52px top operator strip, 60px left icon rail, the main
// pane router, and the 320px right Session Ledger on the narrative tab. It is
// self-mounting and full-screen (reads the active slot from localStorage and
// drives every pane from live fetches), so it can't take props. In the
// headless preview there is no active slot and no read API, so the shell
// renders its real chrome — wordmark/slot strip + the icon rail — around the
// "[ NO ACTIVE SLOT ]" pane notice. The populated reading surface is exercised
// live and via the NarrativePane / RightLedger cards.
//
// Sized to roughly the capture viewport so the absolutely/vh-positioned shell
// internals resolve in-frame.

export const Shell = () => (
  <div style={{ width: 900, height: 660, position: "relative", overflow: "hidden" }}>
    <NexusLayout />
  </div>
);
