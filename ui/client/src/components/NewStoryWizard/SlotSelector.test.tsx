/**
 * SlotSelector interaction tests - the guarded occupied-slot initialization
 * (tenet 9: a single click/Enter must not silently wipe an occupied slot).
 *
 * The query cache is pre-seeded with rows in the shape the component's
 * queryFn produces from GET /api/story/new/slots (slot_number -> slot,
 * is_active, is_locked, wizard_*), mirroring the live five-slot layout:
 * occupied slots, an empty dev slot, and a locked archive. No fetch fires.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SlotSelector } from "./SlotSelector";

interface SeedSlot {
    slot: number;
    is_active?: boolean;
    is_locked?: boolean;
    wizard_in_progress?: boolean;
    wizard_phase?: "setting" | "character" | "seed";
}

function renderSelector(slots: SeedSlot[]) {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    queryClient.setQueryData(["/api/story/new/slots"], slots);
    const onSlotSelected = vi.fn();
    const onSlotResumed = vi.fn();
    render(
        <QueryClientProvider client={queryClient}>
            <SlotSelector
                onSlotSelected={onSlotSelected}
                onSlotResumed={onSlotResumed}
            />
        </QueryClientProvider>,
    );
    return { onSlotSelected, onSlotResumed };
}

const FIVE_SLOTS: SeedSlot[] = [
    { slot: 1, is_active: true },
    { slot: 2, is_active: true },
    { slot: 3, is_active: true },
    { slot: 4, is_active: false, is_locked: true },
    { slot: 5, is_active: false },
];

const card = (n: number) =>
    screen.getByRole("group", { name: new RegExp(`Memory Slot ${n}`) });

describe("SlotSelector occupied-slot guard", () => {
    it("clicking an occupied slot opens the overwrite confirmation instead of initializing", () => {
        const { onSlotSelected } = renderSelector(FIVE_SLOTS);
        fireEvent.click(card(2));
        expect(onSlotSelected).not.toHaveBeenCalled();
        expect(screen.getByTestId("overwrite-confirm")).toBeInTheDocument();
        expect(screen.getByText(/Overwrite Slot 2/)).toBeInTheDocument();
    });

    it("confirming the overwrite proceeds with initialization", () => {
        const { onSlotSelected } = renderSelector(FIVE_SLOTS);
        fireEvent.click(card(2));
        fireEvent.click(screen.getByTestId("overwrite-confirm-action"));
        expect(onSlotSelected).toHaveBeenCalledTimes(1);
        expect(onSlotSelected).toHaveBeenCalledWith(2);
    });

    it("cancelling the overwrite leaves the slot untouched", () => {
        const { onSlotSelected } = renderSelector(FIVE_SLOTS);
        fireEvent.click(card(2));
        fireEvent.click(screen.getByTestId("overwrite-cancel"));
        expect(onSlotSelected).not.toHaveBeenCalled();
        expect(screen.queryByTestId("overwrite-confirm")).not.toBeInTheDocument();
    });

    it("gates the keyboard path: Enter on an occupied card opens the confirmation", () => {
        const { onSlotSelected } = renderSelector(FIVE_SLOTS);
        fireEvent.keyDown(card(3), { key: "Enter" });
        expect(onSlotSelected).not.toHaveBeenCalled();
        expect(screen.getByTestId("overwrite-confirm")).toBeInTheDocument();
    });

    it("gates Space on an occupied card too", () => {
        const { onSlotSelected } = renderSelector(FIVE_SLOTS);
        fireEvent.keyDown(card(1), { key: " " });
        expect(onSlotSelected).not.toHaveBeenCalled();
        expect(screen.getByTestId("overwrite-confirm")).toBeInTheDocument();
    });

    it("a wizard-in-progress slot (occupied) is gated as well", () => {
        const { onSlotSelected } = renderSelector([
            {
                slot: 2,
                is_active: true,
                wizard_in_progress: true,
                wizard_phase: "character",
            },
            { slot: 5, is_active: false },
        ]);
        fireEvent.click(card(2));
        expect(onSlotSelected).not.toHaveBeenCalled();
        expect(screen.getByTestId("overwrite-confirm")).toBeInTheDocument();
    });
});

describe("SlotSelector empty and locked slots", () => {
    it("an empty slot initializes on a single click, no confirmation", () => {
        const { onSlotSelected } = renderSelector(FIVE_SLOTS);
        fireEvent.click(card(5));
        expect(onSlotSelected).toHaveBeenCalledTimes(1);
        expect(onSlotSelected).toHaveBeenCalledWith(5);
        expect(screen.queryByTestId("overwrite-confirm")).not.toBeInTheDocument();
    });

    it("an empty slot initializes on a single Enter as well", () => {
        const { onSlotSelected } = renderSelector(FIVE_SLOTS);
        fireEvent.keyDown(card(5), { key: "Enter" });
        expect(onSlotSelected).toHaveBeenCalledWith(5);
        expect(screen.queryByTestId("overwrite-confirm")).not.toBeInTheDocument();
    });

    it("a locked slot neither initializes nor confirms", () => {
        const { onSlotSelected } = renderSelector(FIVE_SLOTS);
        fireEvent.click(card(4));
        expect(onSlotSelected).not.toHaveBeenCalled();
        expect(screen.queryByTestId("overwrite-confirm")).not.toBeInTheDocument();
    });
});
