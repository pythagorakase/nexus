/**
 * TopBar - the 52px operator strip across the top of the NexusLayout.
 *
 * Left: NEXUS wordmark (the single marquee-font element on this surface)
 * plus the slot label. Right: SKALD status field. Per the locked design
 * decisions there is no scene cartouche and no MODEL field.
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
        <span className="field">
          <span className="k">SKALD</span>
          <span
            className={`v ${skaldStatus.toLowerCase()}`}
            data-testid="text-skald-status"
          >
            {skaldStatus}
          </span>
        </span>
      </div>
    </header>
  );
}
