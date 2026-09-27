/**
 * ReturnRecapCard - where the story stands, just above the latest committed
 * chunk (the one whose setting and cast it reports).
 *
 * A quiet history glyph toggles the card. The card opens on its own when the
 * gateway reports a recap due (a real-world hiatus since the last accepted
 * action), and it closes on the glyph or once the next action is accepted.
 * Closing is this reader's own state, held per slot above the panes the
 * reader swaps (ReaderRecapState): nothing is written to the story or the
 * browser, and a closed due recap stays closed, through history and pane
 * switches alike, until a new action moves last_played.
 *
 * Each line leads with an icon, never a label: the setting (pin), who is
 * present (people), the last accepted action (footsteps, in the player's
 * voice), and the options still open (fork), one per line. The gateway has
 * already verified every line against its source and omits any fact it
 * cannot source; the pane leaves out only a last action whose player line is
 * printed right beside the card (recapBeside).
 */
import {
  useCallback,
  useId,
  type Dispatch,
  type SetStateAction,
} from "react";
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

/**
 * The recap as shown beside the chunks `printedChunkIds`, the committed chunks
 * bordering the card that print a player line: the one above ends with it,
 * the one below closes with it after its prose. A last action cited to one of
 * them is that line, already on screen next to the card, so the card does not
 * repeat it.
 */
export function recapBeside(
  recap: ReturnRecap | undefined,
  printedChunkIds: readonly number[],
): ReturnRecap | undefined {
  if (!recap || printedChunkIds.length === 0) return recap;
  const items = recap.items.filter(
    (item) =>
      item.kind !== "last_action"
      || !item.sources.some(
        (source) =>
          source.kind === "chunk" && printedChunkIds.includes(source.id),
      ),
  );
  return items.length === recap.items.length ? recap : { ...recap, items };
}

export interface ReturnRecapVisibility {
  open: boolean;
  /** Open on demand, or close. */
  toggle: () => void;
  /** Close, as the next accepted action does. */
  close: () => void;
}

/** One slot's recap as the player left it in this reader. */
export interface RecapSlotState {
  /** Opened on demand. */
  requested: boolean;
  /** The last_played whose due recap the player closed. */
  closedFor: string | null;
}

/** Recap state by slot number; a slot absent here is untouched. */
export type RecapSlotStates = Readonly<Partial<Record<number, RecapSlotState>>>;

/**
 * The reader's recap state and its setter, a useState pair held by the reader
 * shell (NexusLayout) above the panes it swaps. Leaving the narrative pane
 * unmounts it; the state outlives that, so coming back neither reopens a
 * recap the player closed nor closes one they opened. Keyed by slot, so what
 * the player did with one slot's recap never carries to another's, even a
 * clone's that shares its last_played.
 */
export type ReaderRecapState = readonly [
  RecapSlotStates,
  Dispatch<SetStateAction<RecapSlotStates>>,
];

const UNTOUCHED: RecapSlotState = { requested: false, closedFor: null };

/**
 * Card visibility for `slot` in this reader. The state lives above the pane
 * and the card, so moving the frontier, reading history or switching panes
 * does not reopen a recap the player closed.
 */
export function useReturnRecapVisibility(
  recap: ReturnRecap | undefined,
  slot: number,
  [states, setStates]: ReaderRecapState,
): ReturnRecapVisibility {
  const { requested, closedFor } = states[slot] ?? UNTOUCHED;
  const lastPlayed = recap?.last_played ?? null;
  const open =
    (recap?.items.length ?? 0) > 0
    && (requested || (!!recap?.due && closedFor !== lastPlayed));
  const close = useCallback(() => {
    setStates((prev) => ({
      ...prev,
      [slot]: { requested: false, closedFor: lastPlayed },
    }));
  }, [slot, lastPlayed, setStates]);
  const toggle = useCallback(() => {
    if (open) close();
    else {
      setStates((prev) => ({
        ...prev,
        [slot]: { ...(prev[slot] ?? UNTOUCHED), requested: true },
      }));
    }
  }, [open, close, slot, setStates]);
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
