/**
 * Pure visual-state classification for the slot manager.
 *
 * Maps slot API data (GET /api/story/new/slots) onto the IRIS/Veil visual
 * vocabulary with zero text labels:
 *   - occupied  -> "lit": full-opacity surface, solid primary-tinted border
 *   - empty     -> "hollow": recessed surface, faint dashed border, dimmed
 *   - wizard    -> lit + a pulsing corner mote on the slot-number tile
 *   - bound     -> 3px glowing left edge-marker (the same "you are here"
 *                  cue nexus-layout.css uses for the current chunk)
 *   - selected  -> existing primary ring, forced solid so it stays legible
 *                  on top of a hollow (dashed) slot
 *   - locked    -> existing destructive tint, takes precedence on the tile
 *
 * Kept free of React so the classification logic is unit-testable.
 */
import { cn } from "@/lib/utils";

export type SlotOccupancy = "empty" | "occupied" | "wizard";

export interface SlotVisualInput {
    slot: number;
    is_active?: boolean;
    is_locked?: boolean;
    wizard_in_progress?: boolean;
    wizard_phase?: string;
}

export interface SlotVisualSpec {
    occupancy: SlotOccupancy;
    bound: boolean;
    /** Card (outer button surface) classes. */
    card: string;
    /** Slot-number tile classes. */
    tile: string;
    /** Inner content-row classes (dimming for hollow slots). */
    content: string;
    /** Screen-reader description of the full visual state. */
    ariaLabel: string;
}

/** Classify occupancy. Wizard-in-progress outranks plain occupancy. */
export function classifySlot(slot: SlotVisualInput): SlotOccupancy {
    if (slot.wizard_in_progress) return "wizard";
    return slot.is_active ? "occupied" : "empty";
}

/**
 * Read the currently-bound story slot from localStorage ('activeSlot').
 * Same safe-access pattern as pages/splash/shared.tsx getActiveSlot().
 */
export function readBoundSlot(): number | null {
    try {
        const raw = localStorage.getItem("activeSlot");
        if (raw === null) return null;
        const parsed = Number.parseInt(raw, 10);
        return Number.isNaN(parsed) ? null : parsed;
    } catch {
        return null;
    }
}

const CARD_BASE =
    "p-4 cursor-pointer transition-all duration-300 group relative overflow-hidden";

const CARD_BY_OCCUPANCY: Record<SlotOccupancy, string> = {
    empty: "border-dashed border-muted-foreground/30 bg-card/20 hover:bg-card/40 hover:border-primary/40",
    occupied: "border-solid border-primary/30 bg-card hover:border-primary/60",
    wizard: "border-solid border-primary/30 bg-card hover:border-primary/60",
};

const TILE_BASE =
    "relative h-12 w-12 rounded-sm flex items-center justify-center font-mono text-lg font-bold border";

const TILE_BY_OCCUPANCY: Record<SlotOccupancy, string> = {
    empty: "border-dashed border-muted-foreground/40 text-muted-foreground/60 bg-transparent",
    occupied: "border-primary text-primary bg-primary/10 terminal-glow",
    wizard: "border-primary text-primary bg-primary/10 terminal-glow",
};

const TILE_LOCKED = "border-destructive/50 text-destructive bg-destructive/10";

const CONTENT_DIMMED =
    "opacity-50 group-hover:opacity-90 transition-opacity duration-300";

const OCCUPANCY_DESCRIPTION: Record<SlotOccupancy, string> = {
    empty: "empty",
    occupied: "occupied",
    wizard: "story setup in progress",
};

export function slotAriaLabel(
    slot: SlotVisualInput,
    occupancy: SlotOccupancy,
    opts: { selected: boolean; bound: boolean },
): string {
    let label = `Memory Slot ${slot.slot}: ${OCCUPANCY_DESCRIPTION[occupancy]}`;
    if (occupancy === "wizard" && slot.wizard_phase) {
        label += ` (${slot.wizard_phase} phase)`;
    }
    if (slot.is_locked) label += ", locked";
    if (opts.bound) label += ", current story";
    if (opts.selected) label += ", selected";
    return label;
}

/** Resolve the complete visual spec for one slot card. */
export function getSlotVisuals(
    slot: SlotVisualInput,
    opts: { selected: boolean; boundSlot: number | null },
): SlotVisualSpec {
    const occupancy = classifySlot(slot);
    const bound = opts.boundSlot !== null && opts.boundSlot === slot.slot;

    const card = cn(
        CARD_BASE,
        CARD_BY_OCCUPANCY[occupancy],
        opts.selected &&
            "border-solid border-primary bg-primary/5 ring-1 ring-primary",
        slot.is_locked &&
            "opacity-80 cursor-not-allowed hover:border-destructive/50 hover:bg-destructive/5",
    );

    const tile = cn(
        TILE_BASE,
        slot.is_locked ? TILE_LOCKED : TILE_BY_OCCUPANCY[occupancy],
    );

    const content = cn(
        occupancy === "empty" && !opts.selected && CONTENT_DIMMED,
    );

    return {
        occupancy,
        bound,
        card,
        tile,
        content,
        ariaLabel: slotAriaLabel(slot, occupancy, { selected: opts.selected, bound }),
    };
}
