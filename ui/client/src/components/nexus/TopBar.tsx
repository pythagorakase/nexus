/**
 * TopBar - the 52px operator strip across the top of the NexusLayout.
 *
 * Left: NEXUS wordmark (the single marquee-font element on this surface)
 * plus the slot label. Right: nothing at rest. Per the visual minimalism
 * doctrine the old persistent `SKALD <status>` field is gone - it carried
 * an internal module name, sat on screen while idle, and during generation
 * restated the in-reader status line and the ledger telemetry. The one
 * state with no other surface is backend unreachability, which renders as
 * a plain OFFLINE flag only while true. Per the locked design decisions
 * there is no scene cartouche and no MODEL field.
 */
import type { SkaldStatus } from "@/types/narrative";

interface TopBarProps {
  slot: number | null;
  characterName: string | null;
  skaldStatus: SkaldStatus;
}

export function TopBar({ slot, characterName, skaldStatus }: TopBarProps) {
  return (
    <header className="topbar" data-testid="nexus-topbar">
      <div className="topbar-left">
        <span className="wordmark">NEXUS</span>
        <span className="brass-pip" aria-hidden="true" />
        <span className="slot-label" data-testid="text-slot-label">
          SLOT <b>{slot ?? "—"}</b>
          {characterName && (
            <>
              {" · "}
              <em>{characterName}</em>
            </>
          )}
        </span>
      </div>

      <div className="topbar-right">
        {skaldStatus === "OFFLINE" && (
          <span className="field">
            <span className="v offline" data-testid="text-skald-status">
              OFFLINE
            </span>
          </span>
        )}
      </div>
    </header>
  );
}
