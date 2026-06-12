/**
 * Unit tests for the slot manager's visual-state classification
 * (slot API data -> visual state classes), per the empty/occupied/
 * wizard/locked/selected/bound vocabulary in slotVisualState.ts.
 */
import { describe, expect, it } from "vitest";
import {
    classifySlot,
    getSlotVisuals,
    readBoundSlot,
    slotAriaLabel,
} from "./slotVisualState";

const emptySlot = { slot: 3, is_active: false };
const occupiedSlot = { slot: 1, is_active: true };
const wizardSlot = {
    slot: 2,
    is_active: true,
    wizard_in_progress: true,
    wizard_phase: "character",
};
const lockedSlot = { slot: 4, is_active: true, is_locked: true };

const noSelection = { selected: false, boundSlot: null };

describe("classifySlot", () => {
    it("classifies slots without data as empty", () => {
        expect(classifySlot(emptySlot)).toBe("empty");
        expect(classifySlot({ slot: 5 })).toBe("empty");
    });

    it("classifies slots with data as occupied", () => {
        expect(classifySlot(occupiedSlot)).toBe("occupied");
    });

    it("ranks wizard-in-progress above plain occupancy", () => {
        expect(classifySlot(wizardSlot)).toBe("wizard");
        expect(
            classifySlot({ slot: 5, is_active: false, wizard_in_progress: true }),
        ).toBe("wizard");
    });
});

describe("getSlotVisuals card classes", () => {
    it("renders empty slots hollow: dashed faint border, recessed surface", () => {
        const { card, tile, content } = getSlotVisuals(emptySlot, noSelection);
        expect(card).toContain("border-dashed");
        expect(card).toContain("bg-card/20");
        expect(tile).toContain("border-dashed");
        expect(tile).not.toContain("terminal-glow");
        expect(content).toContain("opacity-50");
    });

    it("renders occupied slots lit: solid border, full surface, glowing tile", () => {
        const { card, tile, content } = getSlotVisuals(occupiedSlot, noSelection);
        expect(card).toContain("border-solid");
        expect(card).toContain("border-primary/30");
        expect(card).not.toContain("border-dashed");
        expect(tile).toContain("terminal-glow");
        expect(content).toBe("");
    });

    it("renders wizard slots with the lit treatment", () => {
        const { card, tile } = getSlotVisuals(wizardSlot, noSelection);
        expect(card).toContain("border-solid");
        expect(tile).toContain("terminal-glow");
    });

    it("keeps the selection ring and forces a solid border on empty slots", () => {
        const { card } = getSlotVisuals(emptySlot, {
            selected: true,
            boundSlot: null,
        });
        expect(card).toContain("ring-1");
        expect(card).toContain("ring-primary");
        // tailwind-merge resolves the dashed/solid conflict to the later class
        expect(card).toContain("border-solid");
        expect(card).not.toContain("border-dashed");
    });

    it("lifts the hollow dimming when an empty slot is selected", () => {
        const { content } = getSlotVisuals(emptySlot, {
            selected: true,
            boundSlot: null,
        });
        expect(content).toBe("");
    });

    it("applies the destructive locked treatment over occupancy", () => {
        const { card, tile } = getSlotVisuals(lockedSlot, noSelection);
        expect(card).toContain("cursor-not-allowed");
        expect(tile).toContain("border-destructive/50");
        expect(tile).not.toContain("terminal-glow");
    });
});

describe("bound-slot beacon", () => {
    it("marks the slot matching the bound slot", () => {
        const visuals = getSlotVisuals(occupiedSlot, {
            selected: false,
            boundSlot: 1,
        });
        expect(visuals.bound).toBe(true);
    });

    it("does not mark other slots", () => {
        const visuals = getSlotVisuals(occupiedSlot, {
            selected: false,
            boundSlot: 2,
        });
        expect(visuals.bound).toBe(false);
    });

    it("marks nothing when no slot is bound", () => {
        const visuals = getSlotVisuals(occupiedSlot, noSelection);
        expect(visuals.bound).toBe(false);
    });
});

describe("readBoundSlot", () => {
    it("parses the localStorage activeSlot value", () => {
        localStorage.setItem("activeSlot", "4");
        expect(readBoundSlot()).toBe(4);
        localStorage.removeItem("activeSlot");
    });

    it("returns null when unset", () => {
        localStorage.removeItem("activeSlot");
        expect(readBoundSlot()).toBeNull();
    });

    it("returns null for non-numeric garbage", () => {
        localStorage.setItem("activeSlot", "banana");
        expect(readBoundSlot()).toBeNull();
        localStorage.removeItem("activeSlot");
    });
});

describe("slotAriaLabel", () => {
    it("describes empty slots", () => {
        expect(slotAriaLabel(emptySlot, "empty", { selected: false, bound: false }))
            .toBe("Memory Slot 3: empty");
    });

    it("describes occupied slots", () => {
        expect(
            slotAriaLabel(occupiedSlot, "occupied", { selected: false, bound: false }),
        ).toBe("Memory Slot 1: occupied");
    });

    it("describes wizard slots with phase", () => {
        expect(
            slotAriaLabel(wizardSlot, "wizard", { selected: false, bound: false }),
        ).toBe("Memory Slot 2: story setup in progress (character phase)");
    });

    it("appends locked, current story, and selected modifiers", () => {
        expect(
            slotAriaLabel(lockedSlot, "occupied", { selected: true, bound: true }),
        ).toBe("Memory Slot 4: occupied, locked, current story, selected");
    });
});
