/**
 * ReturnRecapCard - where the story stands, just above the frontier.
 *
 * A quiet history glyph toggles the card. The card opens on its own when the
 * gateway reports a recap due (a real-world hiatus since the last accepted
 * action), and it closes on the glyph or once the next action is accepted.
 * Closing is this reader's own state: nothing is written to the story, and a
 * closed due recap stays closed until a new action moves last_played.
 *
 * Each line leads with an icon, never a label: the setting (pin), who is
 * present (people), the last accepted action (footsteps, in the player's
 * voice), and the options still open (fork), one per line. The gateway has
 * already verified every line against committed canon and omits any fact it
 * cannot source, so the card renders exactly what it receives.
 */
import { useCallback, useId, useState } from "react";
import {
  Footprints,
  History,
  MapPin,
  Split,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { RecapItem, ReturnRecap } from "@shared/schema";
import { InlineMarkdown } from "./ProseMarkdown";

const ITEM_ICONS: Record<RecapItem["kind"], LucideIcon> = {
  location: MapPin,
  roster: Users,
  last_action: Footprints,
  open_decision: Split,
};

// The player's and storyteller's prose dialect; names render as stored.
const MARKDOWN_KINDS: ReadonlySet<RecapItem["kind"]> = new Set<RecapItem["kind"]>([
  "last_action",
  "open_decision",
]);

export interface ReturnRecapVisibility {
  open: boolean;
  /** Open on demand, or close. */
  toggle: () => void;
  /** Close, as the next accepted action does. */
  close: () => void;
}

/**
 * Card visibility for one reader. Held by the pane, not the card, so moving
 * the frontier or reading history does not reopen a recap the player closed.
 */
export function useReturnRecapVisibility(
  recap: ReturnRecap | undefined,
): ReturnRecapVisibility {
  const [requested, setRequested] = useState(false);
  // The last_played whose due recap this reader closed.
  const [closedFor, setClosedFor] = useState<string | null>(null);
  const lastPlayed = recap?.last_played ?? null;
  const open =
    (recap?.items.length ?? 0) > 0
    && (requested || (!!recap?.due && closedFor !== lastPlayed));
  const close = useCallback(() => {
    setRequested(false);
    setClosedFor(lastPlayed);
  }, [lastPlayed]);
  const toggle = useCallback(() => {
    if (open) close();
    else setRequested(true);
  }, [open, close]);
  return { open, toggle, close };
}

interface ReturnRecapCardProps {
  recap: ReturnRecap | undefined;
  open: boolean;
  onToggle: () => void;
}

export function ReturnRecapCard({ recap, open, onToggle }: ReturnRecapCardProps) {
  const cardId = useId();
  if (!recap || recap.items.length === 0) return null;
  return (
    <div className="recap" data-testid="return-recap">
      <div className="recap-row">
        <button
          type="button"
          className="reader-nav-btn recap-toggle"
          onClick={onToggle}
          aria-label="Recap"
          aria-expanded={open}
          aria-controls={open ? cardId : undefined}
          data-testid="button-recap"
        >
          <History aria-hidden="true" />
        </button>
      </div>
      {open && (
        <aside
          id={cardId}
          className="recap-card"
          aria-label="Recap"
          data-testid="recap-card"
        >
          <ul>
            {recap.items.map((item) => {
              const Icon = ITEM_ICONS[item.kind];
              return (
                <li
                  key={item.kind}
                  className={`recap-item ${item.kind}`}
                  data-testid={`recap-${item.kind}`}
                >
                  <Icon className="recap-icon" aria-hidden="true" />
                  <div className="recap-text">
                    {item.text.split("\n").map((line, index) => (
                      <div key={index}>
                        {MARKDOWN_KINDS.has(item.kind)
                          ? <InlineMarkdown text={line} />
                          : line}
                      </div>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
        </aside>
      )}
    </div>
  );
}
